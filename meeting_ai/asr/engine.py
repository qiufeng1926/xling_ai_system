import os
import asyncio
from pathlib import Path
from funasr import AutoModel
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from utils.logger import get_logger
from config.config import (
    asr_model_name,
    asr_streaming_model_name,
    asr_vad_model_name,
    asr_model_hub,
    asr_device,
    ffmpeg_path,
    asr_energy_threshold,
)


# FunASR 内置映射的 iic VAD 在 ModelScope 已不可用，改走 damo
_DAMO_VAD = "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch"
_VAD_MODEL_OVERRIDES = {
    "fsmn-vad": _DAMO_VAD,
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch": _DAMO_VAD,
    # 常见误配（把 ASR 的 vocab8404 拼进 VAD 名）
    "iic/speech_fsmn_vad_zh-cn-16k-common-vocab8404-pytorch": _DAMO_VAD,
}


def _resolve_funasr_model_name(name: str) -> str:
    """将 paraformer-zh / fsmn-vad 等短名映射为 ModelScope 全名。"""
    if name in _VAD_MODEL_OVERRIDES:
        return _VAD_MODEL_OVERRIDES[name]
    try:
        from funasr.download.name_maps_from_hub import name_maps_ms

        resolved = name_maps_ms.get(name, name)
        return _VAD_MODEL_OVERRIDES.get(resolved, resolved)
    except Exception:
        return name

logger = get_logger("asr_engine")

TARGET_SAMPLE_RATE = 16000


class StreamingTranscriber:
    """
    单路 WebSocket 实时转写会话。
    使用流式 Paraformer + VAD，按 FunASR 推荐 chunk 推理，避免短片段幻觉。
    """

    CHUNK_SIZE = [0, 10, 5]
    CHUNK_STRIDE = CHUNK_SIZE[1] * 960  # 600ms @ 16kHz
    ENCODER_CHUNK_LOOK_BACK = 4
    DECODER_CHUNK_LOOK_BACK = 1
    VAD_CHUNK_MS = 200

    def __init__(
        self,
        streaming_model,
        vad_model,
        energy_threshold: float = 0.01,
    ):
        self.asr_model = streaming_model
        self.vad_model = vad_model
        self.energy_threshold = energy_threshold
        self.asr_cache: dict = {}
        self.vad_cache: dict = {}
        self.buffer = np.array([], dtype=np.float32)
        self._last_partial = ""
        self._silence_chunks = 0
        self._max_silence_chunks = 10

    @staticmethod
    def _bytes_to_float(audio_bytes: bytes) -> np.ndarray:
        if not audio_bytes:
            return np.array([], dtype=np.float32)
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        return audio_np.astype(np.float32) / 32768.0

    @staticmethod
    def _resample(audio: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
        if orig_sr == target_sr or len(audio) == 0:
            return audio
        target_len = int(len(audio) * target_sr / orig_sr)
        if target_len <= 0:
            return np.array([], dtype=np.float32)
        indices = np.linspace(0, len(audio) - 1, target_len)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def _has_speech(self, chunk: np.ndarray, is_final: bool = False) -> bool:
        """能量门限判断；VAD 仅记录，避免误杀导致无识别输出。"""
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if rms < self.energy_threshold:
            return False
        try:
            res = self.vad_model.generate(
                input=chunk,
                cache=self.vad_cache,
                is_final=is_final,
                chunk_size=self.VAD_CHUNK_MS,
            )
            if res and len(res) > 0 and len(res[0].get("value", [])) > 0:
                return True
        except Exception as e:
            logger.warning(f"VAD 检测异常，回退能量门限: {e}")
        return True

    @staticmethod
    def _parse_asr_text(result_item: dict) -> str:
        text = result_item.get("text") or result_item.get("value") or ""
        if isinstance(text, list):
            text = ""
        return str(text).replace(" ", "").strip()

    def _extract_delta(self, text: str) -> str:
        if not text:
            return ""
        prev = self._last_partial
        if not prev:
            self._last_partial = text
            return text
        if text == prev:
            return ""
        if text.startswith(prev):
            delta = text[len(prev) :]
        elif prev.startswith(text):
            delta = ""
        else:
            # 非累积输出：整段作为增量
            delta = text
        self._last_partial = text
        return delta

    def _reset_utterance_state(self) -> None:
        self._last_partial = ""
        self._silence_chunks = 0
        self.asr_cache = {}
        self.vad_cache = {}

    def feed(self, audio_bytes: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> str:
        audio_float = self._resample(self._bytes_to_float(audio_bytes), sample_rate)
        if len(audio_float) == 0:
            return ""

        self.buffer = np.concatenate([self.buffer, audio_float])
        deltas: list[str] = []

        while len(self.buffer) >= self.CHUNK_STRIDE:
            chunk = self.buffer[: self.CHUNK_STRIDE].copy()
            self.buffer = self.buffer[self.CHUNK_STRIDE :]

            if not self._has_speech(chunk):
                self._silence_chunks += 1
                if self._silence_chunks >= self._max_silence_chunks:
                    self._reset_utterance_state()
                continue

            self._silence_chunks = 0
            try:
                res = self.asr_model.generate(
                    input=chunk,
                    cache=self.asr_cache,
                    is_final=False,
                    chunk_size=self.CHUNK_SIZE,
                    encoder_chunk_look_back=self.ENCODER_CHUNK_LOOK_BACK,
                    decoder_chunk_look_back=self.DECODER_CHUNK_LOOK_BACK,
                )
                if res and len(res) > 0:
                    raw_text = self._parse_asr_text(res[0])
                    delta = self._extract_delta(raw_text)
                    if delta:
                        deltas.append(delta)
                    elif raw_text:
                        logger.debug(f"流式识别无增量: raw={raw_text!r} prev={self._last_partial!r}")
            except Exception as e:
                logger.error(f"流式识别失败: {e}", exc_info=True)

        return "".join(deltas)

    def finalize(self) -> str:
        deltas: list[str] = []
        if len(self.buffer) > 0:
            chunk = self.buffer.copy()
            self.buffer = np.array([], dtype=np.float32)
            if self._has_speech(chunk, is_final=True):
                try:
                    res = self.asr_model.generate(
                        input=chunk,
                        cache=self.asr_cache,
                        is_final=True,
                        chunk_size=self.CHUNK_SIZE,
                        encoder_chunk_look_back=self.ENCODER_CHUNK_LOOK_BACK,
                        decoder_chunk_look_back=self.DECODER_CHUNK_LOOK_BACK,
                    )
                    if res and len(res) > 0:
                        raw_text = self._parse_asr_text(res[0])
                        delta = self._extract_delta(raw_text)
                        if delta:
                            deltas.append(delta)
                except Exception as e:
                    logger.error(f"流式识别收尾失败: {e}", exc_info=True)
        self._reset_utterance_state()
        return "".join(deltas)


class FunASREngine:
    def __init__(
        self,
        model_name: str | None = None,
        streaming_model_name: str | None = None,
        vad_model_name: str | None = None,
        device: str | None = None,
        ffmpeg_path_str: str | None = None,
        energy_threshold: float | None = None,
    ):
        model_name = _resolve_funasr_model_name(model_name or asr_model_name)
        streaming_model_name = _resolve_funasr_model_name(
            streaming_model_name or asr_streaming_model_name
        )
        vad_model_name = _resolve_funasr_model_name(vad_model_name or asr_vad_model_name)
        device = device or asr_device
        ffmpeg_path_str = ffmpeg_path_str or ffmpeg_path
        self.energy_threshold = (
            energy_threshold if energy_threshold is not None else asr_energy_threshold
        )
        self.streaming_model_name = streaming_model_name
        self.vad_model_name = vad_model_name

        os.environ["PATH"] += os.pathsep + ffmpeg_path_str

        logger.info(
            "加载批量 ASR 模型",
            extra={
                "input_params": {
                    "model": model_name,
                    "vad_model": vad_model_name,
                    "hub": asr_model_hub,
                    "device": device,
                }
            },
        )
        try:
            self.batch_model = AutoModel(
                model=model_name,
                vad_model=vad_model_name,
                hub=asr_model_hub,
                device=device,
                disable_update=True,
            )
        except AssertionError as e:
            raise RuntimeError(
                f"FunASR 模型加载失败: {e}。"
                f"请检查 .env 中 ASR_MODEL_NAME / ASR_VAD_MODEL_NAME 是否为 ModelScope 全名，"
                f"并确认网络可访问 modelscope.cn 以下载模型。"
            ) from e

        self._streaming_model = None
        self._vad_model = None
        # 流式会话（若启用本地 FunASR 流式）与批量转写分离，批量走 asr_batch_executor
        self._stream_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='asr-stream')

    def _get_streaming_model(self):
        if self._streaming_model is None:
            logger.info(
                "加载流式 ASR 模型",
                extra={"input_params": {"model": self.streaming_model_name}},
            )
            self._streaming_model = AutoModel(
                model=self.streaming_model_name,
                hub=asr_model_hub,
                device=asr_device,
                disable_update=True,
            )
        return self._streaming_model

    def _get_vad_model(self):
        if self._vad_model is None:
            logger.info(
                "加载 VAD 模型",
                extra={"input_params": {"model": self.vad_model_name}},
            )
            self._vad_model = AutoModel(
                model=self.vad_model_name,
                hub=asr_model_hub,
                device=asr_device,
                disable_update=True,
            )
        return self._vad_model

    def create_streaming_session(self) -> StreamingTranscriber:
        return StreamingTranscriber(
            self._get_streaming_model(),
            self._get_vad_model(),
            energy_threshold=self.energy_threshold,
        )

    def transcribe(self, audio_path: str) -> str:
        audio_path = str(Path(audio_path).resolve())
        logger.info(f"开始转录音频文件: {audio_path}")

        result = self.batch_model.generate(
            input=audio_path,
            batch_size_s=300,
        )

        text = result[0]["text"]
        return text.replace(" ", "")

    async def transcribe_async(self, audio_path: str) -> str:
        from utils.executors import run_asr_batch
        return await run_asr_batch(self.transcribe, audio_path)

    async def feed_stream_async(
        self, session: StreamingTranscriber, audio_bytes: bytes, sample_rate: int
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._stream_executor, session.feed, audio_bytes, sample_rate
        )

    async def finalize_stream_async(self, session: StreamingTranscriber) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._stream_executor, session.finalize)


if __name__ == "__main__":
    logger_main = get_logger("asr_test")
    engine = FunASREngine()

    text = engine.transcribe(r"./example/asr_example.wav")

    logger_main.info("\n========== ASR RESULT ==========\n")
    logger_main.info(text)
