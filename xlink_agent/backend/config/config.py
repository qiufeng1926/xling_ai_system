from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env", override=True)


def _env(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v


def _env_bool(key: str, default: str = "false") -> bool:
    v = _env(key, default) or default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


app_env = (_env("APP_ENV", "development") or "development").strip().lower()
app_name = _env("APP_NAME", "xlink-agent") or "xlink-agent"

api_host = _env("API_HOST", "0.0.0.0") or "0.0.0.0"
api_port = int(_env("API_PORT", "8003") or "8003")

jwt_secret_default = "dev-local-secret-key-at-least-32-characters-long"
jwt_secret = _env("JWT_SECRET", jwt_secret_default) or jwt_secret_default

portal_api_url = _env("PORTAL_API_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000"
portal_frontend_url = _env("PORTAL_FRONTEND_URL", "http://localhost:5173") or "http://localhost:5173"
cors_origins = _env("CORS_ORIGINS", "") or ""

db_host = _env("DB_HOST", "127.0.0.1") or "127.0.0.1"
db_port = int(_env("DB_PORT", "3306") or "3306")
db_user = _env("DB_USER", "app_user") or "app_user"
db_password = _env("DB_PASSWORD", "app123") or "app123"
db_name = _env("DB_NAME", "xlink_agent") or "xlink_agent"

database_url = (
    f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    "?charset=utf8mb4"
)

# Qdrant：开发机推荐 local（嵌入式，无需 Docker）；生产用 url + Compose 中的 qdrant 服务
qdrant_mode = (_env("QDRANT_MODE", "local") or "local").strip().lower()
qdrant_url = _env("QDRANT_URL", "") or ""
qdrant_path = Path(
    _env("QDRANT_PATH", str(_project_root / "data" / "qdrant"))
    or str(_project_root / "data" / "qdrant")
)
qdrant_collection = _env("QDRANT_COLLECTION", "kb_chunks") or "kb_chunks"

llm_provider = (_env("LLM_PROVIDER", "glm") or "glm").strip().lower()
glm_api_key = _env("GLM_API_KEY", "") or ""
glm_model = _env("GLM_MODEL", "glm-4-flash") or "glm-4-flash"
glm_embedding_model = _env("GLM_EMBEDDING_MODEL", "embedding-2") or "embedding-2"
llm_temperature = float(_env("LLM_TEMPERATURE", "0.3") or "0.3")

workspace_root = Path(
    _env("WORKSPACE_ROOT", str(_project_root / "data" / "workspaces"))
    or str(_project_root / "data" / "workspaces")
)
browser_idle_ttl_sec = int(_env("BROWSER_IDLE_TTL_SEC", "1800") or "1800")
agent_max_upload_mb = int(_env("AGENT_MAX_UPLOAD_MB", "30") or "30")
browser_headless = _env_bool("BROWSER_HEADLESS", "true")

log_dir = _env("LOG_DIR") or str(_project_root / "logs")
log_service_name = _env("LOG_SERVICE_NAME", "xlink-agent") or "xlink-agent"
log_level = _env("LOG_LEVEL", "INFO") or "INFO"

confirmation_ttl_sec = int(_env("CONFIRMATION_TTL_SEC", "600") or "600")
agent_max_tool_rounds = int(_env("AGENT_MAX_TOOL_ROUNDS", "8") or "8")
