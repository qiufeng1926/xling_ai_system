import os

from openai import OpenAI

from config.config import (
    deepseek_api_key,
    deepseek_base_url,
    deepseek_model,
    llm_temperature,
)
from llm.base_client import BaseLLMClient
from llm.prompt import SYSTEM_PROMPT
from utils.logger import get_logger

logger = get_logger("deepseek_client")


class DeepSeekClient(BaseLLMClient):

    def __init__(
        self,
        api_key: str | None = deepseek_api_key,
        model: str | None = deepseek_model,
        base_url: str | None = deepseek_base_url,
    ):
        super().__init__(model=model or deepseek_model)

        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise Exception("未找到 DEEPSEEK_API_KEY")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url or deepseek_base_url,
        )

    def chat(
        self,
        prompt: str,
        temperature: float = llm_temperature,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            top_p=0.85,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek 返回空内容")
        return content


if __name__ == "__main__":
    logger_main = get_logger("deepseek_test")
    client = DeepSeekClient()
    result = client.summary_meeting("今天讨论了项目进度，预计下周上线。")
    logger_main.info(result)
