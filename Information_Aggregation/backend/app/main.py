from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.v1 import auth, agencies, collection, influencers, match, notifications, offboarding, permissions, tags, users, qywechat_approval, qywechat_callback, qywechat_mail, feishu_documents, feishu_documents_internal
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.middleware.offboarding_guard import OffboardingGuardMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.models import User
from app.models.permission import SystemSetting
from app.constants.roles import SUPER_ADMIN
from app.utils.access_control import SETTING_BLOCK_UPPER_TASKS, normalize_role
from app.utils.logging_config import setup_logging
from app.utils.security import get_password_hash

setup_logging()


def log_collect_env():
    from app.services.collection_service import CollectionService

    print("\n" + "=" * 60)
    print("采集环境检测")
    for platform, label in (("douyin", "抖音/星图"), ("xiaohongshu", "小红书/蒲公英")):
        env = CollectionService.check_environment(platform)
        print(f"  [{label}]")
        print(f"    Python     : {env['python']}")
        print(f"    Playwright : {'已安装' if env['playwright_installed'] else '未安装'}")
        print(f"    Chromium   : {'已就绪' if env['chromium_ready'] else '未就绪'}")
        print(f"    登录态     : {'已配置' if env['storage_configured'] else '未配置'}")
        if env.get("hint"):
            print(f"    提示       : {env['hint']}")
    print("=" * 60 + "\n")


def migrate_rbac(db: Session) -> None:
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "view_library" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN view_library TINYINT DEFAULT 0"))
            for col in (
                "view_all_meetings",
                "view_root_meetings",
                "view_all_root_meetings",
                "download_meetings",
                "approve_meeting_download",
                "approve_meeting_view",
            ):
                if col not in cols:
                    db.execute(text(f"ALTER TABLE users ADD COLUMN {col} TINYINT DEFAULT 0"))
            if "feishu_open_id" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_open_id VARCHAR(64) NULL"))
            if "feishu_union_id" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_union_id VARCHAR(64) NULL"))
            if "feishu_name" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_name VARCHAR(100) NULL"))
            if "feishu_access_token" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_access_token TEXT NULL"))
            if "feishu_refresh_token" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_refresh_token TEXT NULL"))
            if "feishu_token_expires_at" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_token_expires_at DATETIME NULL"))
            if "feishu_oauth_scope" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN feishu_oauth_scope VARCHAR(512) NULL"))
            if "account_status" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN account_status VARCHAR(20) DEFAULT 'active'"))
            if "offboarded_at" not in cols:
                db.execute(text("ALTER TABLE users ADD COLUMN offboarded_at DATETIME NULL"))
            try:
                db.execute(text("CREATE UNIQUE INDEX ix_users_feishu_open_id ON users (feishu_open_id)"))
            except Exception:
                pass
        if "collection_tasks" in inspector.get_table_names():
            task_cols = {c["name"] for c in inspector.get_columns("collection_tasks")}
            if "transfer_pending_user_id" not in task_cols:
                db.execute(text("ALTER TABLE collection_tasks ADD COLUMN transfer_pending_user_id BIGINT NULL"))
        if "match_requests" in inspector.get_table_names():
            match_cols = {c["name"] for c in inspector.get_columns("match_requests")}
            if "transfer_pending_user_id" not in match_cols:
                db.execute(text("ALTER TABLE match_requests ADD COLUMN transfer_pending_user_id BIGINT NULL"))
        if "view_access_requests" in inspector.get_table_names():
            req_cols = {c["name"] for c in inspector.get_columns("view_access_requests")}
            if "request_type" not in req_cols:
                db.execute(
                    text(
                        "ALTER TABLE view_access_requests ADD COLUMN request_type "
                        "VARCHAR(40) DEFAULT 'view_library'"
                    )
                )
            for col, col_def in (
                ("applicant_username", "VARCHAR(64) NULL"),
                ("applicant_nickname", "VARCHAR(64) NULL"),
                ("reviewer_username", "VARCHAR(64) NULL"),
                ("reviewer_nickname", "VARCHAR(64) NULL"),
            ):
                if col not in req_cols:
                    db.execute(text(f"ALTER TABLE view_access_requests ADD COLUMN {col} {col_def}"))
            db.execute(
                text(
                    "UPDATE view_access_requests r "
                    "JOIN users u ON r.user_id = u.id "
                    "SET r.applicant_username = COALESCE(r.applicant_username, u.username), "
                    "r.applicant_nickname = COALESCE(r.applicant_nickname, u.nickname)"
                )
            )
            db.execute(
                text(
                    "UPDATE view_access_requests r "
                    "JOIN users u ON r.reviewer_id = u.id "
                    "SET r.reviewer_username = COALESCE(r.reviewer_username, u.username), "
                    "r.reviewer_nickname = COALESCE(r.reviewer_nickname, u.nickname)"
                )
            )
            try:
                db.execute(text("ALTER TABLE view_access_requests MODIFY user_id BIGINT NULL"))
            except Exception:
                pass
        db.execute(text("UPDATE users SET role='user' WHERE role='operator'"))
        if db.query(User).filter(User.role == SUPER_ADMIN).count() == 0:
            first_admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
            if first_admin:
                first_admin.role = SUPER_ADMIN
        _ensure_bootstrap_super_admin(db)
        db.execute(
            text(
                "UPDATE users SET view_library=1, view_all_meetings=1, download_meetings=1, "
                "approve_meeting_download=1, approve_meeting_view=1 WHERE role='super_admin'"
            )
        )
        db.execute(
            text(
                "UPDATE users SET view_library=1 WHERE role='admin'"
            )
        )
        db.commit()
    except Exception:
        db.rollback()

    if not db.query(SystemSetting).filter(SystemSetting.key == SETTING_BLOCK_UPPER_TASKS).first():
        db.add(SystemSetting(key=SETTING_BLOCK_UPPER_TASKS, value="true"))
        db.commit()


def _ensure_bootstrap_super_admin(db: Session) -> None:
    username = "qiufengai"
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        if normalize_role(existing.role) != SUPER_ADMIN:
            existing.role = SUPER_ADMIN
        if not existing.nickname:
            existing.nickname = "秋枫"
        return

    db.add(
        User(
            username=username,
            password_hash=get_password_hash("qfai12@@"),
            nickname="秋枫",
            role=SUPER_ADMIN,
            view_library=1,
            status=1,
        )
    )


def init_db():
    import app.models.feishu_document  # noqa: F401 — 注册 ORM 表
    import app.models.offboarding  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print("\n" + "=" * 60)
        print("数据库连接失败，请先初始化 MySQL：")
        print("  powershell -ExecutionPolicy Bypass -File scripts\\setup_local.ps1")
        print("或在 backend\\.env 中修改 DATABASE_URL 为你的 MySQL 账号")
        print("=" * 60 + "\n")
        raise exc
    db: Session = SessionLocal()
    try:
        migrate_rbac(db)
        has_users = db.query(User).count() > 0
        if not has_users:
            username = settings.ADMIN_USERNAME.strip()
            password = settings.ADMIN_PASSWORD
            if username and password:
                if len(password) < 8:
                    raise RuntimeError("ADMIN_PASSWORD 长度至少 8 位")
                admin = User(
                    username=username,
                    password_hash=get_password_hash(password),
                    nickname="超级管理员",
                    role=SUPER_ADMIN,
                    view_library=1,
                )
                db.add(admin)
                db.commit()
                print(f"已创建超级管理员账号: {username}")
            else:
                print("\n" + "!" * 60)
                print("警告: 系统中尚无用户，且未配置 ADMIN_USERNAME / ADMIN_PASSWORD")
                print("请在 backend/.env 中设置后重启，或通过数据库手动创建用户")
                print("!" * 60 + "\n")
    finally:
        db.close()

    db = SessionLocal()
    try:
        from app.services.tag_service import TagService

        seeded = TagService.seed_defaults(db)
        if seeded:
            print(f"已初始化 {seeded} 个预置标签")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log_collect_env()
    if settings.DEBUG:
        print(f"CORS origins : {settings.CORS_ORIGINS}")
        if settings.CORS_ORIGIN_REGEX:
            print(f"CORS regex   : {settings.CORS_ORIGIN_REGEX}")

    import asyncio

    async def _expire_offboarded_loop():
        while True:
            await asyncio.sleep(3600)
            db = SessionLocal()
            try:
                from app.services.offboarding_service import OffboardingService

                n = OffboardingService.expire_offboarded_accounts(db)
                if n:
                    print(f"已清理 {n} 个到期离职账号")
            except Exception as exc:
                print(f"离职账号清理任务失败: {exc}")
            finally:
                db.close()

    task = asyncio.create_task(_expire_offboarded_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(RequestLogMiddleware)
app.add_middleware(OffboardingGuardMiddleware)

_cors_kwargs: dict = {
    "allow_origins": settings.CORS_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["Content-Disposition"],
}
if settings.CORS_ORIGIN_REGEX:
    _cors_kwargs["allow_origin_regex"] = settings.CORS_ORIGIN_REGEX

app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(influencers.router, prefix="/api/v1")
app.include_router(collection.router, prefix="/api/v1")
app.include_router(tags.router, prefix="/api/v1")
app.include_router(agencies.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(offboarding.router, prefix="/api/v1")
app.include_router(permissions.router, prefix="/api/v1")
app.include_router(match.router, prefix="/api/v1")
app.include_router(qywechat_mail.router, prefix="/api/v1/qywechat/mail")
app.include_router(qywechat_approval.router, prefix="/api/v1/qywechat/approval")
app.include_router(qywechat_callback.router, prefix="/api/v1/qywechat")
app.include_router(feishu_documents.router, prefix="/api/v1")
app.include_router(feishu_documents_internal.router, prefix="/api/v1")
# 兼容旧路径（企微管理后台回调 URL 可能仍指向 /wecom）
app.include_router(qywechat_mail.router, prefix="/api/v1/wecom/mail", include_in_schema=False)
app.include_router(qywechat_approval.router, prefix="/api/v1/wecom/approval", include_in_schema=False)
app.include_router(qywechat_callback.router, prefix="/api/v1/wecom", include_in_schema=False)


_verify_name = (settings.WECOM_DOMAIN_VERIFY_FILENAME or "").strip().lstrip("/")
_verify_content = (settings.WECOM_DOMAIN_VERIFY_CONTENT or "").strip()
if _verify_name and _verify_content:

    @app.get(f"/{_verify_name}", response_class=PlainTextResponse, include_in_schema=False)
    def qywechat_trusted_domain_verify_file():
        return PlainTextResponse(content=_verify_content, media_type="text/plain")


@app.get("/health")
def health():
    return {"status": "ok"}
