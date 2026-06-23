from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.config import app_env, app_name, cors_origins
from utils.logger import setup_logging
from utils.startup import validate_startup_config

logger = setup_logging(service_name="flybook", console=True)

from api.routes.auth import router as auth_router
from api.routes.callback import router as callback_router
from api.routes.config import router as config_router
from api.routes.docs import router as docs_router
from api.routes.internal_docs import router as internal_docs_router
from api.routes.minutes import router as minutes_router
from api.ws.minutes_transcribe import router as minutes_ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_config()
    logger.info("Flybook 配置校验通过", extra={"output_params": {"app_env": app_env}})
    yield


app = FastAPI(
    title=app_name,
    version="1.0.0",
    description="飞书集成服务 — 开放平台 API、事件回调（独立部署）",
    lifespan=lifespan,
)

logger.info("Flybook 服务启动")


def _parse_cors_origins() -> list[str]:
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    if origins:
        return origins
    if app_env == "development":
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    return []


_cors_allow_origins = _parse_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/flybook")
app.include_router(config_router, prefix="/api/flybook")
app.include_router(callback_router, prefix="/api/flybook")
app.include_router(docs_router, prefix="/api/flybook")
app.include_router(internal_docs_router, prefix="/api/flybook")
app.include_router(minutes_router, prefix="/api/flybook")
app.include_router(minutes_ws_router, prefix="/api/flybook")


@app.get("/health")
def health():
    return {"status": "ok", "service": "flybook"}
