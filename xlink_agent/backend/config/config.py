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
# 会话摘要向量（与知识库隔离）
qdrant_session_collection = (
    _env("QDRANT_SESSION_COLLECTION", "session_memory") or "session_memory"
)
qdrant_user_memory_collection = (
    _env("QDRANT_USER_MEMORY_COLLECTION", "user_memory") or "user_memory"
)
# 方案默认相似度阈值 0.65；TopK 夹在 3–8
session_memory_score_threshold = float(
    _env("SESSION_MEMORY_SCORE_THRESHOLD", "0.65") or "0.65"
)
_raw_top_k = int(_env("SESSION_MEMORY_TOP_K", "6") or "6")
session_memory_top_k = max(3, min(8, _raw_top_k))
# 窗口内保留最近用户轮数（方案瞬时上下文 ~5 轮）
session_keep_user_turns = int(_env("SESSION_KEEP_USER_TURNS", "5") or "5")
# 权重系数（方案 §3.5）
memory_weight_same_task = float(_env("MEMORY_WEIGHT_SAME_TASK", "2.0") or "2.0")
memory_weight_recent = float(_env("MEMORY_WEIGHT_RECENT", "1.5") or "1.5")
memory_weight_long_term = float(_env("MEMORY_WEIGHT_LONG_TERM", "1.3") or "1.3")
memory_weight_chitchat = float(_env("MEMORY_WEIGHT_CHITCHAT", "0.5") or "0.5")
memory_weight_entity_boost = float(_env("MEMORY_WEIGHT_ENTITY_BOOST", "1.2") or "1.2")

llm_provider = (_env("LLM_PROVIDER", "glm") or "glm").strip().lower()
glm_api_key = _env("GLM_API_KEY", "") or ""
glm_model = _env("GLM_MODEL", "glm-4-flash") or "glm-4-flash"
glm_embedding_model = _env("GLM_EMBEDDING_MODEL", "embedding-2") or "embedding-2"
llm_temperature = float(_env("LLM_TEMPERATURE", "0.3") or "0.3")
llm_max_retries = int(_env("LLM_MAX_RETRIES", "3") or "3")
llm_retry_backoff_sec = float(_env("LLM_RETRY_BACKOFF_SEC", "1.5") or "1.5")

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
agent_max_tool_rounds = int(_env("AGENT_MAX_TOOL_ROUNDS", "12") or "12")

# Open Library：默认关闭；需要时设 OPENLIBRARY_ENABLED=true
openlibrary_enabled = _env_bool("OPENLIBRARY_ENABLED", "false")
openlibrary_user_agent = (
    _env("OPENLIBRARY_USER_AGENT", "XlinkAgent-OpenLibrary (xlink-agent@localhost)")
    or "XlinkAgent-OpenLibrary (xlink-agent@localhost)"
)
openlibrary_rps = float(_env("OPENLIBRARY_RPS", "2.5") or "2.5")
openlibrary_cache_ttl_sec = int(
    _env("OPENLIBRARY_CACHE_TTL_SEC", str(7 * 24 * 3600)) or str(7 * 24 * 3600)
)
