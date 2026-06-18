"""全局共享 LLM 客户端，按 LLM_PROVIDER 创建 GLM 或 DeepSeek 实例"""
from llm.base_client import BaseLLMClient

_client: BaseLLMClient | None = None


def create_llm_client() -> BaseLLMClient:
    from config.config import llm_provider

    if llm_provider == "deepseek":
        from llm.deepseek_chat import DeepSeekClient

        return DeepSeekClient()
    if llm_provider == "glm":
        from llm.glm_chat import GLMClient

        return GLMClient()
    raise ValueError(f"不支持的 LLM_PROVIDER: {llm_provider!r}，可选 glm | deepseek")


def get_llm_client() -> BaseLLMClient:
    global _client
    if _client is None:
        _client = create_llm_client()
    return _client


def get_glm_client() -> BaseLLMClient:
    """兼容旧调用方，实际返回当前配置的 LLM 客户端"""
    return get_llm_client()
