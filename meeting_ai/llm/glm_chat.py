import os

from zhipuai import ZhipuAI

from config.config import glm_api_key, glm_model, glm_temperature, llm_temperature
from llm.base_client import BaseLLMClient
from llm.prompt import SYSTEM_PROMPT
from utils.logger import get_logger

logger = get_logger("glm_client")


class GLMClient(BaseLLMClient):

    def __init__(
        self,
        api_key: str | None = glm_api_key,
        model: str | None = glm_model,
    ):
        super().__init__(model=model or glm_model)

        self.api_key = api_key or os.getenv("GLM_API_KEY")
        if not self.api_key:
            raise Exception("未找到 GLM_API_KEY")

        self.client = ZhipuAI(api_key=self.api_key)

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
        return response.choices[0].message.content


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
