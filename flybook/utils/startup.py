"""应用启动配置校验"""

from config.config import (
    app_env,
    cors_origins,
    feishu_app_id,
    feishu_app_secret,
    jwt_secret,
    jwt_secret_default,
)


_INSECURE_JWT_SECRETS = frozenset(
    {
        jwt_secret_default,
        "change-me-in-production-use-a-long-random-string",
        "dev-local-secret-key-at-least-32-characters-long",
        "changeme",
        "secret",
    }
)


def validate_startup_config() -> None:
    from utils.logger import get_logger

    logger = get_logger("startup")
    if app_env == "development":
        logger.info("JWT 已加载（前缀=%s…，须与门户 SECRET_KEY 一致）", (jwt_secret or "")[:12])

    issues: list[str] = []

    if not jwt_secret or jwt_secret in _INSECURE_JWT_SECRETS:
        issues.append(
            "JWT_SECRET 未设置或仍为默认值；嵌入 xlink 门户时须与达人后端 SECRET_KEY 完全一致"
        )

    if app_env == "production":
        if not cors_origins.strip():
            issues.append("生产环境必须配置 CORS_ORIGINS（逗号分隔的前端域名）")
        if not feishu_app_id or not feishu_app_secret:
            issues.append("生产环境必须配置 FEISHU_APP_ID 与 FEISHU_APP_SECRET")

    if issues:
        msg = "启动配置检查未通过:\n- " + "\n- ".join(issues)
        if app_env == "production":
            raise RuntimeError(msg)
        logger.warning(msg)
