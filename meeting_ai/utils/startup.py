"""应用启动配置校验"""
from config.config import (
    app_env,
    cors_origins,
    deepseek_api_key,
    glm_api_key,
    jwt_secret,
    jwt_secret_default,
    llm_provider,
    seed_default_users_on_startup,
    tingwu_access_key_id,
    tingwu_app_key,
)

_INSECURE_JWT_SECRETS = frozenset(
    {
        jwt_secret_default,
        "meeting-ai-jwt-secret-change-in-production",
        "changeme",
        "secret",
    }
)


def validate_startup_config() -> None:
    """生产环境拒绝不安全配置；开发环境仅告警。"""
    from utils.logger import get_logger

    logger = get_logger("startup")
    if app_env == "development":
        logger.info(
            "JWT 已加载（前缀=%s…，须与门户 SECRET_KEY 一致）",
            (jwt_secret or "")[:12],
        )
        logger.info("LLM 提供商: %s", llm_provider)

    issues: list[str] = []

    if not jwt_secret or jwt_secret in _INSECURE_JWT_SECRETS:
        issues.append(
            "JWT_SECRET 未设置或仍为默认值；嵌入 xlink 门户时须与达人后端 SECRET_KEY 完全一致"
        )

    if app_env == "production":
        if seed_default_users_on_startup:
            issues.append("生产环境禁止 SEED_DEFAULT_USERS=true（勿自动创建默认账号）")
        if not cors_origins.strip():
            issues.append("生产环境必须配置 CORS_ORIGINS（逗号分隔的前端域名）")
        if llm_provider == "deepseek":
            if not deepseek_api_key:
                issues.append("生产环境必须配置 DEEPSEEK_API_KEY（LLM_PROVIDER=deepseek）")
        elif llm_provider == "glm":
            if not glm_api_key:
                issues.append("生产环境必须配置 GLM_API_KEY（LLM_PROVIDER=glm）")
        else:
            issues.append(f"LLM_PROVIDER 无效: {llm_provider!r}，可选 glm | deepseek")
        if not tingwu_access_key_id or not tingwu_app_key:
            issues.append("生产环境必须配置听悟 AccessKey 与 TINGWU_APP_KEY")

    if issues:
        msg = "启动配置检查未通过:\n- " + "\n- ".join(issues)
        if app_env == "production":
            raise RuntimeError(msg)
        from utils.logger import get_logger

        get_logger("startup").warning(msg)
