"""全局共享 GLM 客户端，避免多实例线程池叠加"""
from llm.glm_chat import GLMClient

_client: GLMClient | None = None


def get_glm_client() -> GLMClient:
    global _client
    if _client is None:
        _client = GLMClient()
    return _client
