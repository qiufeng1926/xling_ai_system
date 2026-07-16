"""多模型路由：一期 GLM，预留切换接口"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from config.config import glm_api_key, glm_embedding_model, glm_model, llm_provider, llm_temperature
from utils.logger import get_logger

logger = get_logger("model_router")


def _log_messages(messages: list[dict[str, str]], *, tag: str) -> None:
    """打印完整提示词（用户要求调试时看得到全部）。"""
    logger.info("======== LLM prompt begin tag=%s msgs=%s ========", tag, len(messages))
    for i, m in enumerate(messages):
        role = m.get("role", "?")
        content = m.get("content") or ""
        logger.info("--- prompt[%s] #%s role=%s len=%s ---\n%s", tag, i, role, len(content), content)
    logger.info("======== LLM prompt end tag=%s ========", tag)


class BaseChatModel(ABC):
    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class GLMChatModel(BaseChatModel):
    def __init__(self) -> None:
        if not glm_api_key:
            raise RuntimeError("未配置 GLM_API_KEY")
        from zhipuai import ZhipuAI

        self.client = ZhipuAI(api_key=glm_api_key)
        self.model = glm_model
        self.embedding_model = glm_embedding_model

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        import asyncio

        _log_messages(messages, tag=f"glm.stream/{self.model}")
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            chunks: list[str] = []
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else llm_temperature,
                stream=True,
            )
            for event in stream:
                try:
                    delta = event.choices[0].delta.content
                except Exception:
                    delta = None
                if delta:
                    chunks.append(delta)
            return chunks

        parts = await loop.run_in_executor(None, _run)
        for p in parts:
            yield p

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        import asyncio

        _log_messages(messages, tag=f"glm.chat/{self.model}")
        loop = asyncio.get_event_loop()

        def _run() -> str:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else llm_temperature,
            )
            return resp.choices[0].message.content or ""

        return await loop.run_in_executor(None, _run)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        loop = asyncio.get_event_loop()

        def _run() -> list[list[float]]:
            resp = self.client.embeddings.create(model=self.embedding_model, input=texts)
            return [item.embedding for item in resp.data]

        return await loop.run_in_executor(None, _run)


class EchoChatModel(BaseChatModel):
    """无 API Key 时的降级：便于本地联调 UI"""

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        _log_messages(messages, tag="echo.stream")
        last = messages[-1]["content"] if messages else ""
        text = f"（演示模式，未配置 GLM_API_KEY）已收到：{last[:500]}"
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        parts: list[str] = []
        async for p in self.stream_chat(messages, temperature=temperature):
            parts.append(p)
        return "".join(parts)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 固定维度伪向量，仅用于本地无 Key 时入库联调
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * 64
            for i, ch in enumerate(t[:64]):
                vec[i % 64] += (ord(ch) % 97) / 97.0
            out.append(vec)
        return out


_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    global _model
    if _model is not None:
        return _model
    provider = llm_provider
    if provider == "glm":
        try:
            _model = GLMChatModel()
            logger.info("LLM provider=glm model=%s", glm_model)
            return _model
        except Exception as exc:
            logger.warning("GLM 初始化失败，降级演示模式: %s", exc)
            _model = EchoChatModel()
            return _model
    # 预留：deepseek / openai
    logger.warning("未知 LLM_PROVIDER=%s，使用演示模式", provider)
    _model = EchoChatModel()
    return _model


def extract_json_block(text: str) -> Any | None:
    """提取文本中的第一个完整 JSON 对象（避免多段 ReAct 粘连成超大非法 JSON）。"""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    return json.loads(chunk)
                except Exception:
                    return None
    return None
