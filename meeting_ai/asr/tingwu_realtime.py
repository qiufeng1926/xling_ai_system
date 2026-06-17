"""通义听悟实时记录：CreateTask API + MeetingJoinUrl WebSocket 推流。"""



from __future__ import annotations



import asyncio

import json

import time

import uuid

from typing import Awaitable, Callable, Optional



import websockets

from aliyunsdkcore.auth.credentials import AccessKeyCredential

from aliyunsdkcore.client import AcsClient

from aliyunsdkcore.request import CommonRequest



from utils.executors import run_io

from config.config import (

    tingwu_access_key_id,

    tingwu_access_key_secret,

    tingwu_app_key,

    tingwu_audio_format,

    tingwu_domain,

    tingwu_region,

    tingwu_sample_rate,

    tingwu_source_language,


    tingwu_diarization_enabled,
    get_tingwu_diarization_speaker_count,
    tingwu_summarization_enabled,
    TINGWU_SUMMARIZATION_TYPES,
    tingwu_summarization_poll_seconds,

)

from utils.logger import get_logger



logger = get_logger("tingwu_realtime")



SUCCESS_STATUS = 20000000

# 听悟 SDK 示例按约 100ms/3200 字节分包推流

AUDIO_CHUNK_BYTES = 3200



OnResultCallback = Callable[[str, str, bool, Optional[str], Optional[str]], Awaitable[None]]
# (展示文本, 累计全文, 是否句末, speaker_id, 说话人展示名)

OnErrorCallback = Callable[[str], Awaitable[None]]





class TingwuTaskError(Exception):

    """听悟实时任务失败。"""



    def __init__(self, message: str, detail: Optional[dict] = None):

        super().__init__(message)

        self.detail = detail or {}





def _create_common_request(method: str, uri: str) -> CommonRequest:

    request = CommonRequest()

    request.set_accept_format("json")

    request.set_domain(tingwu_domain)

    request.set_version("2023-09-30")

    request.set_protocol_type("https")

    request.set_method(method)

    request.set_uri_pattern(uri)

    request.add_header("Content-Type", "application/json")

    return request





def _build_create_task_body(task_key: str) -> dict:

    return {

        "AppKey": tingwu_app_key,

        "Input": {

            "Format": tingwu_audio_format,

            "SampleRate": tingwu_sample_rate,

            "SourceLanguage": tingwu_source_language,

            "TaskKey": task_key,

        },

        "Parameters": _build_task_parameters(),

    }


def _build_task_parameters() -> dict:
    params: dict = {
        "Transcription": _build_transcription_params(),
    }
    if tingwu_summarization_enabled:
        params["SummarizationEnabled"] = True
        params["Summarization"] = {"Types": list(TINGWU_SUMMARIZATION_TYPES)}
        logger.info(
            "听悟 CreateTask 已启用大模型摘要",
            extra={"output_params": {"types": list(TINGWU_SUMMARIZATION_TYPES)}},
        )
    return params


def _build_transcription_params() -> dict:
    # OutputLevel=2：仅推送句中中间结果，不再单独启用「仅完整句」模式
    transcription: dict = {
        "OutputLevel": 2,
    }
    if tingwu_diarization_enabled:
        transcription["DiarizationEnabled"] = True
        speaker_count = get_tingwu_diarization_speaker_count()
        transcription["Diarization"] = {"SpeakerCount": speaker_count}
    logger.info(
        "听悟 CreateTask 转写参数",
        extra={"output_params": {"transcription": transcription}},
    )
    return transcription





def _create_realtime_task_sync() -> dict:

    if not tingwu_access_key_id or not tingwu_access_key_secret:

        raise ValueError("请配置 ALIBABA_CLOUD_ACCESS_KEY_ID 与 ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    if not tingwu_app_key:

        raise ValueError("请配置 TINGWU_APP_KEY")



    task_key = f"task_{int(time.time() * 1000)}"

    credentials = AccessKeyCredential(tingwu_access_key_id, tingwu_access_key_secret)

    client = AcsClient(region_id=tingwu_region, credential=credentials)



    request = _create_common_request("PUT", "/openapi/tingwu/v2/tasks")

    request.add_query_param("type", "realtime")

    request.set_content(json.dumps(_build_create_task_body(task_key), ensure_ascii=False).encode("utf-8"))



    raw = client.do_action_with_exception(request)

    body = json.loads(raw)

    if body.get("Code") != "0":

        raise RuntimeError(

            f"创建听悟实时任务失败: {body.get('Message')} (code={body.get('Code')})"

        )

    data = body.get("Data") or {}

    task_id = data.get("TaskId")

    meeting_join_url = data.get("MeetingJoinUrl")

    if not task_id or not meeting_join_url:

        raise RuntimeError(f"听悟返回数据不完整: {body}")

    return {

        "TaskId": task_id,

        "TaskKey": data.get("TaskKey") or task_key,

        "MeetingJoinUrl": meeting_join_url,

    }





def _stop_realtime_task_sync(task_id: str) -> None:

    if not task_id:

        return

    credentials = AccessKeyCredential(tingwu_access_key_id, tingwu_access_key_secret)

    client = AcsClient(region_id=tingwu_region, credential=credentials)



    request = _create_common_request("PUT", "/openapi/tingwu/v2/tasks")

    request.add_query_param("type", "realtime")

    request.add_query_param("operation", "stop")

    stop_body = {

        "AppKey": tingwu_app_key,

        "Input": {"TaskId": task_id},

    }

    request.set_content(json.dumps(stop_body, ensure_ascii=False).encode("utf-8"))



    raw = client.do_action_with_exception(request)

    body = json.loads(raw)

    if body.get("Code") != "0":

        logger.warning(

            "结束听悟实时任务返回非成功",

            extra={"output_params": {"code": body.get("Code"), "message": body.get("Message")}},

        )





def _speech_message(name: str, payload: Optional[dict] = None) -> str:

    msg = {

        "header": {

            "name": name,

            "namespace": "SpeechTranscriber",

            "message_id": str(uuid.uuid4()),

        },

        "payload": payload or {},

    }

    return json.dumps(msg, ensure_ascii=False)





def _extract_sentence_text(payload: dict) -> str:

    text = str(payload.get("result") or "").strip()

    stash = payload.get("stash_result") or {}

    if isinstance(stash, dict):

        stash_text = str(stash.get("text") or "").strip()

        if stash_text:

            text = f"{text}{stash_text}"

    return text


def _extract_speaker_id(payload: dict) -> Optional[str]:
    """从听悟 payload 提取说话人 ID（兼容 payload / words 多级字段）"""
    for key in ("speaker_id", "speakerId", "SpeakerId"):
        if key in payload and payload[key] is not None:
            sid = str(payload[key]).strip()
            if sid != "":
                return sid

    words = payload.get("words") or []
    if isinstance(words, list):
        for word in words:
            if not isinstance(word, dict):
                continue
            for key in ("speaker_id", "speakerId", "SpeakerId"):
                if key in word and word[key] is not None:
                    sid = str(word[key]).strip()
                    if sid != "":
                        return sid

    stash = payload.get("stash_result") or {}
    if isinstance(stash, dict):
        stash_words = stash.get("words") or []
        if isinstance(stash_words, list):
            for word in stash_words:
                if not isinstance(word, dict):
                    continue
                for key in ("speaker_id", "speakerId", "SpeakerId"):
                    if key in word and word[key] is not None:
                        sid = str(word[key]).strip()
                        if sid != "":
                            return sid
    return None


def _get_task_info_sync(task_id: str) -> dict:
    if not task_id:
        return {}
    credentials = AccessKeyCredential(tingwu_access_key_id, tingwu_access_key_secret)
    client = AcsClient(region_id=tingwu_region, credential=credentials)
    request = _create_common_request("GET", f"/openapi/tingwu/v2/tasks/{task_id}")
    raw = client.do_action_with_exception(request)
    body = json.loads(raw)
    if str(body.get("Code")) != "0":
        raise RuntimeError(
            f"查询听悟任务失败: {body.get('Message')} (code={body.get('Code')})"
        )
    return body


def _download_json_sync(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _paragraphs_to_diarized_text(paragraphs: list) -> str:
    segments: list[dict[str, str]] = []
    for para in paragraphs:
        if not isinstance(para, dict):
            continue
        speaker_raw = para.get("SpeakerId") or para.get("speakerId") or para.get("speaker_id") or "1"
        speaker_label = f"说话人{speaker_raw}"
        words = para.get("Words") or para.get("words") or []
        if words:
            text = "".join(
                str(w.get("Text") or w.get("text") or "")
                for w in words
                if isinstance(w, dict)
            ).strip()
        else:
            text = str(para.get("Text") or para.get("text") or "").strip()
        if not text:
            continue
        if segments and segments[-1]["speaker"] == speaker_label:
            segments[-1]["text"] = f"{segments[-1]['text']} {text}"
        else:
            segments.append({"speaker": speaker_label, "text": text})
    if not segments:
        return ""
    return "\n".join(f"[{item['speaker']}] {item['text']}" for item in segments) + "\n"


def _transcription_json_to_diarized_text(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    transcription = data.get("Transcription")
    if isinstance(transcription, dict):
        paragraphs = transcription.get("Paragraphs") or transcription.get("paragraphs") or []
        text = _paragraphs_to_diarized_text(paragraphs)
        if text:
            return text
    paragraphs = data.get("Paragraphs") or data.get("paragraphs") or []
    return _paragraphs_to_diarized_text(paragraphs)


async def fetch_diarized_transcript_async(
    task_id: str,
    *,
    max_wait_seconds: float = 90.0,
    poll_interval_seconds: float = 2.0,
) -> str | None:
    if not task_id or not tingwu_diarization_enabled:
        return None

    deadline = time.time() + max_wait_seconds
    last_status = ""

    while time.time() < deadline:
        try:
            body = await run_io(_get_task_info_sync, task_id)
        except Exception as exc:
            logger.warning(f"查询听悟任务状态失败: {exc}")
            await asyncio.sleep(poll_interval_seconds)
            continue

        data = body.get("Data") or {}
        status = str(data.get("TaskStatus") or "")
        last_status = status or last_status

        if status == "FAILED":
            logger.warning(
                "听悟任务失败，无法获取说话人分离转写",
                extra={"output_params": {"task_id": task_id, "error": data.get("ErrorMessage")}},
            )
            return None

        if status in ("COMPLETED", "ONGOING"):
            result = data.get("Result") or {}
            transcription_url = result.get("Transcription")
            if transcription_url:
                try:
                    transcription_json = await run_io(_download_json_sync, transcription_url)
                    diarized = _transcription_json_to_diarized_text(transcription_json)
                    if diarized:
                        return diarized
                except Exception as exc:
                    logger.warning(f"下载听悟 Transcription 结果失败: {exc}")

        if status == "COMPLETED":
            break

        await asyncio.sleep(poll_interval_seconds)

    logger.warning(
        "听悟说话人分离转写未在超时内就绪",
        extra={"output_params": {"task_id": task_id, "last_status": last_status}},
    )
    return None


def _normalize_summarization_payload(data: dict) -> dict:
    """解析听悟 Summarization JSON 为统一结构。"""
    if not isinstance(data, dict):
        return {}
    inner = data.get("Summarization")
    if not isinstance(inner, dict):
        inner = data
    return {
        "task_id": data.get("TaskId"),
        "paragraph_summary": inner.get("ParagraphSummary") or "",
        "conversational_summary": inner.get("ConversationalSummary") or [],
        "questions_answering_summary": inner.get("QuestionsAnsweringSummary") or [],
        "mind_map_summary": inner.get("MindMapSummary") or [],
    }


def _summarization_has_content(normalized: dict) -> bool:
    if not normalized:
        return False
    if (normalized.get("paragraph_summary") or "").strip():
        return True
    for key in ("conversational_summary", "questions_answering_summary", "mind_map_summary"):
        if normalized.get(key):
            return True
    return False


async def _async_none():
    return None


async def _async_skipped_summary():
    return None, "skipped"


async def fetch_tingwu_summarization_async(
    task_id: str,
    *,
    max_wait_seconds: float | None = None,
    poll_interval_seconds: float = 3.0,
) -> tuple[dict | None, str]:
    """任务结束后轮询 GetTask，下载 Summarization JSON。返回 (数据, status)。"""
    if not task_id or not tingwu_summarization_enabled:
        return None, "skipped"

    wait_seconds = max_wait_seconds if max_wait_seconds is not None else tingwu_summarization_poll_seconds
    deadline = time.time() + wait_seconds
    last_status = ""

    while time.time() < deadline:
        try:
            body = await run_io(_get_task_info_sync, task_id)
        except Exception as exc:
            logger.warning(f"查询听悟任务状态失败: {exc}")
            await asyncio.sleep(poll_interval_seconds)
            continue

        data = body.get("Data") or {}
        status = str(data.get("TaskStatus") or "")
        last_status = status or last_status

        if status == "FAILED":
            logger.warning(
                "听悟任务失败，无法获取大模型摘要",
                extra={"output_params": {"task_id": task_id, "error": data.get("ErrorMessage")}},
            )
            return None, "failed"

        if status in ("COMPLETED", "ONGOING"):
            result = data.get("Result") or {}
            summarization_url = result.get("Summarization")
            if summarization_url:
                try:
                    summary_json = await run_io(_download_json_sync, summarization_url)
                    normalized = _normalize_summarization_payload(summary_json)
                    if _summarization_has_content(normalized):
                        return normalized, "completed"
                    return normalized, "completed"
                except Exception as exc:
                    logger.warning(f"下载听悟 Summarization 结果失败: {exc}")

        if status == "COMPLETED":
            break

        await asyncio.sleep(poll_interval_seconds)

    logger.warning(
        "听悟大模型摘要未在超时内就绪",
        extra={"output_params": {"task_id": task_id, "last_status": last_status}},
    )
    return None, "failed"


def _extract_error_message(data: dict) -> str:

    header = data.get("header") or {}

    payload = data.get("payload") or {}

    output = payload.get("output") or {}



    parts: list[str] = []

    for key in ("status_text", "status_message"):

        if header.get(key):

            parts.append(str(header[key]))

    for key in ("message", "status_text"):

        if payload.get(key):

            parts.append(str(payload[key]))

    if output.get("errorMessage"):

        code = output.get("errorCode", "")

        parts.append(f"{code}: {output['errorMessage']}".strip(": "))



    if parts:

        return " | ".join(parts)

    return str(header.get("name") or "听悟转写失败")





class TingwuStreamingSession:

    """单路实时转写：连接 MeetingJoinUrl，推 PCM 并解析识别事件。"""



    def __init__(

        self,

        on_result: Optional[OnResultCallback] = None,

        on_error: Optional[OnErrorCallback] = None,

    ):

        self.on_result = on_result

        self.on_error = on_error

        self.task_id: Optional[str] = None

        self.meeting_join_url: Optional[str] = None

        self._ws = None

        self._recv_task: Optional[asyncio.Task] = None

        self._started_event = asyncio.Event()

        self._completed_text = ""

        self._pending_audio: list[bytes] = []

        self._closed = False

        self._task_failed = False

        self.last_error: Optional[str] = None

        self._speaker_labels: dict[str, str] = {}

        self.summarization_data: dict | None = None
        self.summarization_status: str = "pending"

    def total_text(self) -> str:

        return self._completed_text



    @property

    def is_ready(self) -> bool:

        return self._started_event.is_set() and not self._closed and not self._task_failed

    def resolve_speaker_label(self, speaker_id: Optional[str]) -> Optional[str]:
        """将听悟 speaker_id 映射为「说话人1」等展示名。"""
        if not tingwu_diarization_enabled:
            return None
        if speaker_id is None or str(speaker_id).strip() == "":
            return None
        sid = str(speaker_id).strip()
        if sid not in self._speaker_labels:
            self._speaker_labels[sid] = f"说话人{len(self._speaker_labels) + 1}"
        return self._speaker_labels[sid]

    def _format_with_speaker(self, text: str, speaker_id: Optional[str]) -> str:
        label = self.resolve_speaker_label(speaker_id)
        if label:
            return f"[{label}] {text}"
        return text



    async def start(self) -> None:

        task_info = await run_io(_create_realtime_task_sync)

        self.task_id = task_info["TaskId"]

        self.meeting_join_url = task_info["MeetingJoinUrl"]



        logger.info(

            "听悟实时任务已创建",

            extra={
                "output_params": {
                    "task_id": self.task_id,
                    "diarization_enabled": tingwu_diarization_enabled,
                    "speaker_count": get_tingwu_diarization_speaker_count(),
                }
            },

        )



        self._ws = await websockets.connect(

            self.meeting_join_url,

            ping_interval=20,

            ping_timeout=20,

            max_size=10 * 1024 * 1024,

        )

        # 先启动接收循环，避免错过 TranscriptionStarted

        self._recv_task = asyncio.create_task(self._receive_loop())



        # 与官方网页示例一致：payload 仅传 format（采样率在 CreateTask 中已指定）

        await self._ws.send(

            _speech_message("StartTranscription", {"format": tingwu_audio_format})

        )



        try:

            await asyncio.wait_for(self._started_event.wait(), timeout=15.0)

        except asyncio.TimeoutError as exc:

            raise TingwuTaskError(

                "等待 TranscriptionStarted 超时，请检查 TINGWU_APP_KEY 与听悟服务是否已开通"

            ) from exc



        logger.info("听悟推流通道已就绪", extra={"output_params": {"task_id": self.task_id}})



    async def _receive_loop(self) -> None:

        assert self._ws is not None

        try:

            async for message in self._ws:

                if isinstance(message, bytes):

                    continue

                try:

                    data = json.loads(message)

                except json.JSONDecodeError:

                    continue

                await self._handle_event(data)

        except asyncio.CancelledError:

            pass

        except websockets.ConnectionClosed:

            logger.info("听悟 WebSocket 连接已关闭")

        except Exception as e:

            logger.error(f"听悟接收循环异常: {e}", exc_info=True)



    async def _fail(self, message: str, data: Optional[dict] = None) -> None:

        self._task_failed = True

        self._closed = True

        self.last_error = message

        logger.error(

            "听悟转写失败",

            extra={"output_params": {"error": message, "event": data}},

        )

        if self.on_error:

            await self.on_error(message)



    async def _handle_event(self, data: dict) -> None:

        header = data.get("header") or {}

        name = header.get("name", "")

        payload = data.get("payload") or {}

        status = header.get("status")



        if name in ("TaskFailed", "TranscriptionFailed"):

            await self._fail(_extract_error_message(data), data)

            return



        if status is not None:

            try:

                status_code = int(status)

            except (TypeError, ValueError):

                status_code = None

            if status_code is not None and status_code != SUCCESS_STATUS:

                await self._fail(_extract_error_message(data), data)

                return



        if name == "TranscriptionStarted":

            self._started_event.set()

            await self._flush_pending_audio()

            return



        if name == "TranscriptionResultChanged":

            partial = str(payload.get("result") or "").strip()

            speaker_id = _extract_speaker_id(payload)

            if partial and self.on_result:

                display = self._format_with_speaker(partial, speaker_id)

                await self.on_result(
                    display,
                    self._completed_text,
                    False,
                    speaker_id,
                    self.resolve_speaker_label(speaker_id),
                )

            return



        if name == "SentenceEnd":

            sentence = _extract_sentence_text(payload)

            speaker_id = _extract_speaker_id(payload)

            if sentence:

                line = self._format_with_speaker(sentence, speaker_id)

                if self._completed_text and not self._completed_text.endswith("\n"):

                    self._completed_text += "\n"

                self._completed_text += line + "\n"

                if self.on_result:

                    await self.on_result(
                        line,
                        self._completed_text,
                        True,
                        speaker_id,
                        self.resolve_speaker_label(speaker_id),
                    )

            return



        if name == "TranscriptionCompleted":

            self._closed = True

            return



    async def send_audio(self, audio_bytes: bytes, sample_rate: int = 16000) -> None:

        if not audio_bytes or self._closed or self._task_failed or not self._ws:

            return

        if not self._started_event.is_set():

            self._pending_audio.append(bytes(audio_bytes))

            # 避免启动阶段缓冲无限增长

            pending_bytes = sum(len(chunk) for chunk in self._pending_audio)

            if pending_bytes > 16000 * 60 * 2:

                self._pending_audio = self._pending_audio[-20:]

            return

        await self._send_audio_chunks(audio_bytes, sample_rate)



    async def _flush_pending_audio(self) -> None:

        if not self._pending_audio:

            return

        pending = self._pending_audio

        self._pending_audio = []

        for chunk in pending:

            await self._send_audio_chunks(chunk, tingwu_sample_rate)



    async def _send_audio_chunks(self, audio_bytes: bytes, sample_rate: int) -> None:

        if not audio_bytes or self._closed or self._task_failed or not self._ws:

            return

        if sample_rate != tingwu_sample_rate:

            logger.debug(

                f"音频采样率 {sample_rate} 与配置 {tingwu_sample_rate} 不一致"

            )



        try:

            for offset in range(0, len(audio_bytes), AUDIO_CHUNK_BYTES):

                chunk = audio_bytes[offset : offset + AUDIO_CHUNK_BYTES]

                await self._ws.send(chunk)

        except websockets.ConnectionClosed:

            self._closed = True

            if not self._task_failed:

                logger.warning("听悟连接已关闭，停止发送音频")



    async def send_keepalive(self) -> None:
        """发送静音 PCM，避免 StartTranscription 后长时间无音频触发 IDLE_TIMEOUT。"""
        await self.send_audio(bytes(AUDIO_CHUNK_BYTES))

    async def finalize(self) -> str:

        """发送 StopTranscription，等待句末结果并结束听悟任务。"""

        if not self.task_id:

            return ""

        if self._closed and not self._ws:

            return ""



        self._closed = True



        if self._ws is not None:

            try:

                await self._ws.send(_speech_message("StopTranscription"))

                await asyncio.sleep(1.5)

            except websockets.ConnectionClosed:

                pass

            except Exception as e:

                logger.warning(f"发送 StopTranscription 失败: {e}")



        if self._recv_task and not self._recv_task.done():

            try:

                await asyncio.wait_for(asyncio.shield(self._recv_task), timeout=3.0)

            except asyncio.TimeoutError:

                self._recv_task.cancel()

                try:

                    await self._recv_task

                except asyncio.CancelledError:

                    pass



        if self._ws:

            try:

                await self._ws.close()

            except Exception:

                pass

            self._ws = None



        if self.task_id:

            try:

                await run_io(_stop_realtime_task_sync, self.task_id)

            except Exception as e:

                logger.error(f"结束听悟任务 API 失败: {e}", exc_info=True)

        if self.task_id and not self._task_failed:
            diarized_coro = (
                fetch_diarized_transcript_async(self.task_id)
                if tingwu_diarization_enabled
                else _async_none()
            )
            summary_coro = (
                fetch_tingwu_summarization_async(self.task_id)
                if tingwu_summarization_enabled
                else _async_skipped_summary()
            )
            try:
                diarized, summary_result = await asyncio.gather(
                    diarized_coro,
                    summary_coro,
                )
                if diarized:
                    self._completed_text = diarized
                    logger.info(
                        "已获取听悟说话人分离转写",
                        extra={
                            "output_params": {
                                "task_id": self.task_id,
                                "text_length": len(diarized),
                            }
                        },
                    )
                elif tingwu_diarization_enabled:
                    logger.warning(
                        "听悟说话人分离转写不可用，保留实时句末文本",
                        extra={"output_params": {"task_id": self.task_id}},
                    )

                if tingwu_summarization_enabled:
                    data, status = summary_result
                    self.summarization_data = data
                    self.summarization_status = status
                    if data:
                        logger.info(
                            "已获取听悟大模型摘要",
                            extra={
                                "output_params": {
                                    "task_id": self.task_id,
                                    "status": status,
                                    "has_paragraph": bool(data.get("paragraph_summary")),
                                    "conversational_count": len(data.get("conversational_summary") or []),
                                }
                            },
                        )
            except Exception as e:
                self.summarization_status = "failed"
                logger.warning(f"拉取听悟任务结果失败: {e}", exc_info=True)



        if self._task_failed and self.last_error:

            raise TingwuTaskError(self.last_error)



        return self._completed_text





class TingwuRealtimeEngine:

    """实时转写引擎门面，接口与 FunASREngine 流式方法对齐。"""



    def create_streaming_session(

        self,

        on_result: Optional[OnResultCallback] = None,

        on_error: Optional[OnErrorCallback] = None,

    ) -> TingwuStreamingSession:

        return TingwuStreamingSession(on_result=on_result, on_error=on_error)



    async def start_session_async(self, session: TingwuStreamingSession) -> None:

        await session.start()

    async def send_keepalive_async(self, session: TingwuStreamingSession) -> None:

        await session.send_keepalive()

    async def feed_stream_async(

        self, session: TingwuStreamingSession, audio_bytes: bytes, sample_rate: int

    ) -> str:

        if session._task_failed:

            return ""

        await session.send_audio(audio_bytes, sample_rate)

        return ""



    async def finalize_stream_async(self, session: TingwuStreamingSession) -> str:

        return await session.finalize()


