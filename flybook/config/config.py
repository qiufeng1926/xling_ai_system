from dotenv import load_dotenv
import os
from pathlib import Path


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
app_name = _env("APP_NAME", "Flybook") or "Flybook"

api_host = _env("API_HOST", "0.0.0.0") or "0.0.0.0"
api_port = int(_env("API_PORT", "8002") or "8002")

jwt_secret_default = "flybook-jwt-secret-change-in-production"
jwt_secret = _env("JWT_SECRET", jwt_secret_default) or jwt_secret_default
jwt_expire_hours = int(_env("JWT_EXPIRE_HOURS", "72") or "72")

portal_api_url = _env("PORTAL_API_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000"
portal_frontend_url = _env("PORTAL_FRONTEND_URL", "http://localhost:5173") or "http://localhost:5173"
flybook_internal_key = _env("FLYBOOK_INTERNAL_KEY", "") or ""
cors_origins = _env("CORS_ORIGINS", "") or ""

# 飞书 OAuth（网页应用 SSO，须与开放平台「安全设置 → 重定向 URL」逐字一致）
feishu_oauth_redirect_uri = (
    _env("FEISHU_OAUTH_REDIRECT_URI", "http://localhost:5173/api/flybook/auth/callback")
    or "http://localhost:5173/api/flybook/auth/callback"
).strip()

# 飞书开放平台（自建应用）
feishu_app_id = _env("FEISHU_APP_ID", "") or ""
feishu_app_secret = _env("FEISHU_APP_SECRET", "") or ""
feishu_api_base = (_env("FEISHU_API_BASE", "https://open.feishu.cn") or "https://open.feishu.cn").rstrip("/")

# 飞书事件回调（管理后台「事件订阅」）
feishu_verification_token = _env("FEISHU_VERIFICATION_TOKEN", "") or ""
feishu_encrypt_key = _env("FEISHU_ENCRYPT_KEY", "") or ""

# 飞书网页版消息入口（供前端独立窗口打开，可与门户 VITE_FLYBOOK_URL 保持一致）
feishu_messenger_url = (
    _env("FEISHU_MESSENGER_URL", "https://gcnnna81ata3.feishu.cn/next/messenger")
    or "https://gcnnna81ata3.feishu.cn/next/messenger"
)

# 云文档链接前缀（默认从 FEISHU_MESSENGER_URL 提取租户域名）
def _derive_doc_base(messenger: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(messenger).netloc
        if host:
            return f"https://{host}"
    except Exception:
        pass
    return "https://bytedance.feishu.cn"


feishu_doc_base_url = (
    _env("FEISHU_DOC_BASE_URL") or _derive_doc_base(feishu_messenger_url)
).rstrip("/")

# 云文档组件 SDK（前端加载）
feishu_docs_component_sdk_url = (
    _env(
        "FEISHU_DOCS_COMPONENT_SDK_URL",
        "https://sf1-scmcdn-cn.feishucdn.com/obj/feishu-static/docComponentSdk/lib/1.0.13.js",
    )
    or "https://sf1-scmcdn-cn.feishucdn.com/obj/feishu-static/docComponentSdk/lib/1.0.13.js"
)

# OAuth scope：云文档需 drive / docx 权限（用户重新绑定后生效）
feishu_oauth_scope = (
    _env(
        "FEISHU_OAUTH_SCOPE",
        "offline_access drive:drive docx:document docx:document:create "
        "sheets:spreadsheet sheets:spreadsheet:create "
        "base:app:create bitable:app "
        "wiki:wiki wiki:node:create "
        "docs:document:import drive:file:upload "
        "minutes:minutes.search:read minutes:minutes:readonly "
        "minutes:minutes.artifacts:read minutes:minutes",
    )
    or (
        "offline_access drive:drive docx:document docx:document:create "
        "sheets:spreadsheet sheets:spreadsheet:create "
        "base:app:create bitable:app "
        "wiki:wiki wiki:node:create "
        "docs:document:import drive:file:upload "
        "minutes:minutes.search:read minutes:minutes:readonly "
        "minutes:minutes.artifacts:read minutes:minutes"
    )
)

log_dir = _env("LOG_DIR") or str(_project_root / "logs")
log_service_name = _env("LOG_SERVICE_NAME", "flybook") or "flybook"
log_level = _env("LOG_LEVEL", "INFO") or "INFO"
