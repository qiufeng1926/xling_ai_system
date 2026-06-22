from pathlib import Path
from typing import Annotated
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
# 强制以 backend/.env 为准，避免 shell/conda 中的旧 SECRET_KEY 覆盖文件配置
load_dotenv(BACKEND_DIR / ".env", override=True)

DEFAULT_SECRET_KEY = "change-me-in-production-use-a-long-random-string"
WEAK_SECRET_KEYS = frozenset(
    {
        DEFAULT_SECRET_KEY,
        "dev-secret-key-change-in-production",
    }
)
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "达人信息聚合系统"
    DEBUG: bool = False

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "app_user"
    DB_PASSWORD: str = "app123"
    DB_NAME: str = "influencer_db"
    DATABASE_URL: str = ""

    MYSQL_ROOT_PASSWORD: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # 首次启动无用户时，通过环境变量创建管理员（生产环境必填）
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""

    # 是否开放自助注册（注册后为普通用户，权限需申请或由超管下发）
    ALLOW_PUBLIC_REGISTER: bool = True

    # 登录限流：窗口期内最大失败次数
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # 服务监听（0.0.0.0 允许局域网访问）
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # 日志：{LOG_SERVICE_NAME}_{YYYYMMDD_HHMMSS}.log，10MB 轮转，15 天清理
    LOG_DIR: str = "logs"
    LOG_SERVICE_NAME: str = "influencer-api"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_RETENTION_DAYS: int = 15
    LOG_LEVEL: str = "INFO"
    LOG_CONSOLE: bool = True

    # CORS：逗号分隔，例如 http://localhost:5173,http://192.168.1.10:5173
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    # 开发环境默认可匹配 localhost / 127.0.0.1 / 局域网 IP 的任意端口
    CORS_ORIGIN_REGEX: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def apply_dev_cors_regex(self) -> "Settings":
        if self.DEBUG and not self.CORS_ORIGIN_REGEX:
            self.CORS_ORIGIN_REGEX = (
                r"https?://("
                r"localhost|"
                r"127\.0\.0\.1|"
                r"192\.168\.\d{1,3}\.\d{1,3}|"
                r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
                r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
                r")(:\d+)?"
            )
        return self

    # 采集模式: mock(模拟) / api(星图API) / browser(Playwright星图自动化，推荐)
    COLLECTOR_MODE: str = "browser"
    DOUYIN_API_TOKEN: str = ""
    DOUYIN_API_BASE: str = "https://open.douyin.com"
    DOUYIN_COOKIE: str = ""
    XINGTU_COOKIE: str = ""
    XINGTU_COOKIE_FILE: str = ""
    XINGTU_STORAGE_STATE: str = "cookies/xingtu_state.json"

    XIAOHONGSHU_COOKIE: str = ""
    PUGONGYING_COOKIE: str = ""
    PUGONGYING_COOKIE_FILE: str = ""
    PUGONGYING_STORAGE_STATE: str = "cookies/pugongying_state.json"

    # 企业微信（自建应用 Secret，需开通「邮件」权限并配置应用邮箱）
    WECOM_CORP_ID: str = ""
    WECOM_CORP_SECRET: str = ""
    WECOM_API_BASE: str = "https://qyapi.weixin.qq.com"
    WECOM_DEFAULT_TEMPLATE_ID: str = ""
    WECOM_PUBLIC_BASE_URL: str = ""
    # 接收消息服务器 URL 校验（与管理后台 Token / EncodingAESKey 一致）
    WECOM_CALLBACK_TOKEN: str = ""
    WECOM_ENCODING_AES_KEY: str = ""
    # 网页授权可信域名校验文件（可选，文件名如 WW_verify_xxx.txt）
    WECOM_DOMAIN_VERIFY_FILENAME: str = ""
    WECOM_DOMAIN_VERIFY_CONTENT: str = ""

    # Playwright 配置
    PLAYWRIGHT_HEADLESS: bool = False
    PLAYWRIGHT_SLOW_MO: int = 80
    PLAYWRIGHT_TIMEOUT: int = 60000
    PLAYWRIGHT_WAIT_AFTER_SEARCH: int = 3500
    PLAYWRIGHT_FILTER_WAIT: int = 2500
    PLAYWRIGHT_MAX_SCROLLS: int = 2
    PLAYWRIGHT_MAX_PAGES: int = 10
    PLAYWRIGHT_PAGE_SIZE: int = 20
    PLAYWRIGHT_DETAIL_ENRICH_MAX: int = 0
    PLAYWRIGHT_FALLBACK_MOCK: bool = False
    PLAYWRIGHT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        if not self.DATABASE_URL:
            password = quote_plus(self.DB_PASSWORD)
            self.DATABASE_URL = (
                f"mysql+pymysql://{self.DB_USER}:{password}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
            )

        if self.XINGTU_STORAGE_STATE and not Path(self.XINGTU_STORAGE_STATE).is_absolute():
            self.XINGTU_STORAGE_STATE = str(BACKEND_DIR / self.XINGTU_STORAGE_STATE)

        if self.XINGTU_COOKIE_FILE and not Path(self.XINGTU_COOKIE_FILE).is_absolute():
            self.XINGTU_COOKIE_FILE = str(BACKEND_DIR / self.XINGTU_COOKIE_FILE)

        if self.PUGONGYING_STORAGE_STATE and not Path(self.PUGONGYING_STORAGE_STATE).is_absolute():
            self.PUGONGYING_STORAGE_STATE = str(BACKEND_DIR / self.PUGONGYING_STORAGE_STATE)

        if self.PUGONGYING_COOKIE_FILE and not Path(self.PUGONGYING_COOKIE_FILE).is_absolute():
            self.PUGONGYING_COOKIE_FILE = str(BACKEND_DIR / self.PUGONGYING_COOKIE_FILE)

        return self

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if not self.DEBUG:
            if self.SECRET_KEY in WEAK_SECRET_KEYS or len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    "生产环境（DEBUG=false）必须设置至少 32 位的 SECRET_KEY，"
                    "不能使用默认占位值"
                )
        return self


settings = Settings()
