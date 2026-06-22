from dotenv import load_dotenv
import os
from pathlib import Path


_project_root = Path(__file__).resolve().parent.parent
# 强制以项目 .env 为准，避免 conda/系统环境变量中的旧 JWT_SECRET 覆盖文件配置
load_dotenv(_project_root / ".env", override=True)


def _env(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v


def _env_bool(key: str, default: str = "false") -> bool:
    v = _env(key, default) or default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _path_from_env(key: str, default_relative: str) -> str:
    raw = _env(key)
    if raw is None:
        return str(_project_root / default_relative)
    p = Path(raw)
    if not p.is_absolute():
        return str(_project_root / p)
    return str(p)


# ASR 配置（批量上传；短名如 paraformer-zh/fsmn-vad 在部分环境未注册，建议用 ModelScope 全名）
_DEFAULT_ASR_MODEL = "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
_DEFAULT_ASR_STREAMING = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
# iic/ 路径在 ModelScope 已 404，改用 damo/ 同名模型
_DEFAULT_ASR_VAD = "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch"
asr_model_name = _env("ASR_MODEL_NAME", _DEFAULT_ASR_MODEL)
asr_streaming_model_name = _env("ASR_STREAMING_MODEL_NAME", _DEFAULT_ASR_STREAMING)
asr_vad_model_name = _env("ASR_VAD_MODEL_NAME", _DEFAULT_ASR_VAD)
asr_model_hub = _env("ASR_MODEL_HUB", "ms") or "ms"
asr_energy_threshold = float(_env("ASR_ENERGY_THRESHOLD", "0.006") or "0.006")
asr_device = _env("ASR_DEVICE", "cpu")
ffmpeg_path = _env("FFMPEG_PATH", r"D:\AI\ffmpeg-8.1.1-essentials_build\bin")

# LLM 配置（LLM_PROVIDER: glm | deepseek）
llm_provider = (_env("LLM_PROVIDER", "glm") or "glm").strip().lower()
llm_temperature = float(
    _env("LLM_TEMPERATURE", _env("GLM_TEMPERATURE", "0.3")) or "0.3"
)
glm_api_key = _env("GLM_API_KEY", "")
glm_model = _env("GLM_MODEL", "glm-4-flash")
glm_temperature = llm_temperature  # 兼容旧配置名
deepseek_api_key = _env("DEEPSEEK_API_KEY", "")
deepseek_model = _env("DEEPSEEK_MODEL", "deepseek-chat")
deepseek_base_url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com"

# 图文速览（与 Markdown 并行生成，每场必生成）
visual_summary_retry_max = int(_env("VISUAL_SUMMARY_RETRY_MAX", "2") or "2")
visual_chunk_chars = int(_env("VISUAL_CHUNK_CHARS", "6000") or "6000")
visual_chunk_overlap = int(_env("VISUAL_CHUNK_OVERLAP", "400") or "400")
visual_json_repair = _env_bool("VISUAL_JSON_REPAIR", "true")

# 并发：实时转写与批量处理共存时的限流
llm_summary_max_concurrent = int(_env("LLM_SUMMARY_MAX_CONCURRENT", "2") or "2")

# 文件路径配置
upload_dir = _path_from_env("UPLOAD_DIR", "upload")
output_dir = _path_from_env("OUTPUT_DIR", "output")

# ASR 示例文件路径
asr_example_audio = _path_from_env("ASR_EXAMPLE_AUDIO", "asr/example/asr_example.wav")
asr_hotword_file = _path_from_env("ASR_HOTWORD_FILE", "asr/example/hotword.txt")

# MySQL 数据库配置
db_host = _env("DB_HOST", "localhost")
db_port = _env("DB_PORT", "3306")
db_user = _env("DB_USER", "root")
db_password = _env("DB_PASSWORD", "")
db_name = _env("DB_NAME", "meeting_ai")
db_charset = _env("DB_CHARSET", "utf8mb4")

# 构建数据库连接URL
database_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset={db_charset}"

# 应用环境：development | production
app_env = (_env("APP_ENV", "development") or "development").strip().lower()

# JWT 认证配置
jwt_secret_default = "meeting-ai-jwt-secret-change-in-production"
jwt_secret = _env("JWT_SECRET", jwt_secret_default) or jwt_secret_default
jwt_expire_hours = int(_env("JWT_EXPIRE_HOURS", "72") or "72")

# xling 门户 API（用于实时拉取用户权限，避免 JWT 内 perms 过期）
portal_api_url = _env("PORTAL_API_URL", "http://127.0.0.1:8000") or ""

# CORS（逗号分隔；生产环境勿使用 *）
cors_origins = _env("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000") or ""

# 上传限制（字节，默认 100MB）
max_upload_bytes = int(_env("MAX_UPLOAD_BYTES", "104857600") or "104857600")

# 启动时是否自动 seed 默认用户（生产环境应 false）
seed_default_users_on_startup = _env_bool("SEED_DEFAULT_USERS", "false")

# 通过 /api/auth/seed 或启动 seed 时使用的初始密码（未设置则随机生成并写日志）
seed_root_password = _env("SEED_ROOT_PASSWORD", "")
seed_admin_password = _env("SEED_ADMIN_PASSWORD", "")

# 通义听悟实时转写（CreateTask + MeetingJoinUrl WebSocket）
tingwu_access_key_id = _env("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
tingwu_access_key_secret = _env("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
tingwu_app_key = _env("TINGWU_APP_KEY", "")
tingwu_region = _env("TINGWU_REGION", "cn-beijing")
tingwu_domain = _env("TINGWU_DOMAIN", "tingwu.cn-beijing.aliyuncs.com")
tingwu_source_language = _env("TINGWU_SOURCE_LANGUAGE", "cn")
tingwu_audio_format = _env("TINGWU_AUDIO_FORMAT", "pcm")
tingwu_sample_rate = int(_env("TINGWU_SAMPLE_RATE", "16000") or "16000")
# 说话人分离（CreateTask Parameters.Transcription.DiarizationEnabled）
tingwu_diarization_enabled = _env_bool("TINGWU_DIARIZATION_ENABLED", "true")
TINGWU_SPEAKER_COUNT_ENV_KEY = "TINGWU_DIARIZATION_SPEAKER_COUNT"


def get_tingwu_diarization_speaker_count() -> int:
    """读取听悟说话人数量：0=自动识别，2-100=手动指定人数。"""
    raw = _env(TINGWU_SPEAKER_COUNT_ENV_KEY, "0") or "0"
    try:
        return max(0, min(int(raw), 100))
    except ValueError:
        return 0


def set_tingwu_diarization_speaker_count(count: int) -> int:
    """更新内存与环境变量，并持久化到 .env。"""
    import os as _os

    from utils.env_file import update_env_value

    normalized = max(0, min(int(count), 100))
    value = str(normalized)
    _os.environ[TINGWU_SPEAKER_COUNT_ENV_KEY] = value
    update_env_value(TINGWU_SPEAKER_COUNT_ENV_KEY, value)
    global tingwu_diarization_speaker_count
    tingwu_diarization_speaker_count = normalized
    return normalized


_speaker_count_raw = _env(TINGWU_SPEAKER_COUNT_ENV_KEY, "0")
tingwu_diarization_speaker_count: int = get_tingwu_diarization_speaker_count()

# 协作会议
collab_max_participants = int(_env("COLLAB_MAX_PARTICIPANTS", "8") or "8")
collab_max_recorders = int(_env("COLLAB_MAX_RECORDERS", "4") or "4")
