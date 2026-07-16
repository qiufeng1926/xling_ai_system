from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import browser_ws, confirmations, conversations, knowledge, memory, skills, workspace
from browser.pool import browser_pool
from config.config import app_env, app_name, cors_origins, portal_frontend_url, workspace_root
from db.seed import seed_builtin_skills
from db.session import SessionLocal, init_db
from utils.logger import setup_logging

logger = setup_logging(service_name="xlink-agent", console=True)


def _parse_cors_origins() -> list[str]:
    if cors_origins.strip():
        return [o.strip() for o in cors_origins.split(",") if o.strip()]
    if app_env == "development":
        return [
            portal_frontend_url,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    return [portal_frontend_url] if portal_frontend_url else ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    workspace_root.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        seed_builtin_skills(db)
    finally:
        db.close()
    logger.info("xlink_agent 启动完成 env=%s", app_env)
    yield
    await browser_pool.shutdown()
    logger.info("xlink_agent 已关闭")


app = FastAPI(
    title=app_name,
    version="0.1.0",
    description="xlink 办公智能体服务",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一前缀 /api/agent
PREFIX = "/api/agent"
app.include_router(conversations.router, prefix=PREFIX)
app.include_router(skills.router, prefix=PREFIX)
app.include_router(knowledge.router, prefix=PREFIX)
app.include_router(workspace.router, prefix=PREFIX)
app.include_router(confirmations.router, prefix=PREFIX)
app.include_router(memory.router, prefix=PREFIX)
app.include_router(browser_ws.router, prefix=PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "service": "xlink-agent"}
