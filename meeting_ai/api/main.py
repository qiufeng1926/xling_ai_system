from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from utils.logger import setup_logging
from utils.startup import validate_startup_config
from config.config import app_env, cors_origins

import os


# 先于路由模块导入，避免 get_logger 重复初始化日志文件
logger = setup_logging(
    service_name="meeting_ai",
    console=True,
)

from api.routes.meeting import router as meeting_router
from api.routes.websocket import router as websocket_router
from api.routes.auth import router as auth_router
from api.routes.admin import router as admin_router
from api.routes.export import router as export_router
from api.routes.settings import router as settings_router
from api.routes.collaborative import router as collaborative_router
from api.routes.meeting_access import router as meeting_access_router
from api.routes.tingwu_summary import router as tingwu_summary_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_config()
    logger.info("Meeting AI 配置校验通过", extra={"output_params": {"app_env": app_env}})
    yield


app = FastAPI(
    title="Meeting AI",
    version="1.0.0",
    description="会议 AI 助手 - 支持批量和实时语音转文本",
    lifespan=lifespan,
)

logger.info("Meeting AI 服务启动")


def _parse_cors_origins() -> list[str]:
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    if origins:
        return origins
    if app_env == "development":
        return [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "https://localhost:8000",
            "https://127.0.0.1:8000",
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

logger.info(
    "CORS 已配置",
    extra={"output_params": {"origins": _cors_allow_origins, "app_env": app_env}},
)

# 注册路由
app.include_router(
    export_router,
    prefix="/api",
    tags=["文件导出"]
)

app.include_router(
    auth_router,
    prefix="/api",
    tags=["用户认证"]
)

app.include_router(
    admin_router,
    prefix="/api",
    tags=["超级管理"]
)

app.include_router(
    meeting_router,
    prefix="/api",
    tags=["会议处理"]
)

app.include_router(
    websocket_router,
    prefix="/api",
    tags=["实时转写"]
)

app.include_router(
    settings_router,
    prefix="/api",
    tags=["应用设置"]
)

app.include_router(
    collaborative_router,
    prefix="/api",
    tags=["协作会议"]
)

app.include_router(
    meeting_access_router,
    prefix="/api",
    tags=["会议浏览权限"]
)

app.include_router(
    tingwu_summary_router,
    prefix="/api",
    tags=["听悟摘要"]
)


# 挂载静态文件目录
static_dir = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static"
)

if os.path.exists(static_dir):

    app.mount(
        "/static",
        StaticFiles(directory=static_dir),
        name="static"
    )

    logger.info(f"静态文件目录已挂载: {static_dir}")


# 首页
@app.get("/")
async def root():

    """
    首页 - 默认打开实时转写页面
    """

    html_path = os.path.join(
        static_dir,
        "transcribe.html"
    )

    if os.path.exists(html_path):
        return FileResponse(html_path)

    return {
        "message": "Meeting AI API",
        "docs": "/docs"
    }


@app.get("/tingwu-summary")
async def tingwu_summary_page():
    """听悟大模型摘要展示页（独立于 GLM 速览）"""
    html_path = os.path.join(static_dir, "tingwu_summary.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return {"error": "页面不存在"}


# favicon.ico 处理
@app.get("/favicon.ico")
async def favicon():
    """
    返回空响应以避免 404 错误
    """
    from fastapi.responses import Response
    return Response(status_code=204)