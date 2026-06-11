import os
import asyncio
from zhipuai import ZhipuAI
from utils.logger import get_logger
from utils.executors import io_executor

logger = get_logger("glm_client")

from config.config import glm_api_key, glm_model, glm_temperature
from llm.prompt import (
    SYSTEM_PROMPT,
    build_meeting_prompt,
)
from llm.prompt_visual import (
    SYSTEM_PROMPT_VISUAL,
    build_visual_prompt,
    build_visual_chunk_prompt,
)

REPAIR_JSON_SYSTEM = """
你是 JSON 修复工具。用户给出一段几乎正确但语法错误的 JSON，你只输出修复后的完整 JSON 对象。
不要 Markdown、不要代码块、不要任何解释文字。
"""


class GLMClient:

    def __init__(
        self,
        api_key=glm_api_key,
        model=glm_model
    ):

        self.api_key = api_key or os.getenv("GLM_API_KEY")

        if not self.api_key:
            raise Exception("未找到 GLM_API_KEY")

        self.client = ZhipuAI(
            api_key=self.api_key
        )

        self.model = model
        self.executor = io_executor

    def chat(
        self,
        prompt: str,
        temperature: float = glm_temperature,
        system_prompt: str = SYSTEM_PROMPT,
    ):

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=temperature,
            top_p=0.85,
        )

        return response.choices[0].message.content
    
    async def chat_async(
        self,
        prompt: str,
        temperature: float = glm_temperature,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        """异步聊天"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self.chat(prompt, temperature, system_prompt),
        )

    def summary_meeting(
        self,
        transcript: str
    ):

        prompt = build_meeting_prompt(
            transcript
        )

        return self.chat(prompt)
    
    async def summary_meeting_async(
        self,
        transcript: str
    ):
        """
        异步生成会议纪要
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.summary_meeting, transcript)

    def summary_visual(
        self,
        transcript: str,
        meeting_name: str | None = None,
        part_index: int | None = None,
        total_parts: int | None = None,
    ):
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
    ):
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


if __name__ == "__main__":
    logger_main = get_logger("glm_test")
    client = GLMClient()

    text = """
    今天召开项目会议。
    
    张三负责前端。
    李四负责后端。
    
    预计下周上线。
    """

    result = client.summary_meeting(text)

    logger_main.info(result)
