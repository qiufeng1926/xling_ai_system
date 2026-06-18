"""LLM 客户端抽象基类：共享纪要/图文/JSON 修复逻辑"""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from config.config import llm_temperature
from llm.prompt import SYSTEM_PROMPT, build_meeting_prompt
from llm.prompt_visual import (
    SYSTEM_PROMPT_VISUAL,
    build_visual_prompt,
    build_visual_chunk_prompt,
)
from utils.executors import io_executor

REPAIR_JSON_SYSTEM = """
你是 JSON 修复工具。用户给出一段几乎正确但语法错误的 JSON，你只输出修复后的完整 JSON 对象。
不要 Markdown、不要代码块、不要任何解释文字。
"""


class BaseLLMClient(ABC):
    """GLM / DeepSeek 等提供商的统一接口"""

    def __init__(self, model: str):
        self.model = model
        self.executor = io_executor

    @abstractmethod
    def chat(
        self,
        prompt: str,
        temperature: float = llm_temperature,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> str:
        ...

    async def chat_async(
        self,
        prompt: str,
        temperature: float = llm_temperature,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.chat(prompt, temperature, system_prompt),
        )

    def summary_meeting(
        self,
        transcript: str,
        meeting_name: str | None = None,
        meeting_started_at: datetime | str | None = None,
    ) -> str:
        prompt = build_meeting_prompt(transcript, meeting_name, meeting_started_at)
        return self.chat(prompt)

    async def summary_meeting_async(
        self,
        transcript: str,
        meeting_name: str | None = None,
        meeting_started_at: datetime | str | None = None,
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.summary_meeting(transcript, meeting_name, meeting_started_at),
        )

    def summary_visual(
        self,
        transcript: str,
        meeting_name: str | None = None,
        part_index: int | None = None,
        total_parts: int | None = None,
    ) -> str:
        if part_index is not None and total_parts is not None and total_parts > 1:
            prompt = build_visual_chunk_prompt(
                transcript, meeting_name, part_index, total_parts
            )
        else:
            prompt = build_visual_prompt(transcript, meeting_name)
        return self.chat(prompt, system_prompt=SYSTEM_PROMPT_VISUAL)

    async def summary_visual_async(
        self,
        transcript: str,
        meeting_name: str | None = None,
        part_index: int | None = None,
        total_parts: int | None = None,
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.summary_visual(
                transcript, meeting_name, part_index, total_parts
            ),
        )

    def repair_json(self, broken_text: str) -> str:
        prompt = (
            "请修复以下内容为合法 JSON（仅输出 JSON）：\n\n"
            f"{broken_text[:14000]}"
        )
        return self.chat(prompt, temperature=0.1, system_prompt=REPAIR_JSON_SYSTEM)

    async def repair_json_async(self, broken_text: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.repair_json, broken_text)
