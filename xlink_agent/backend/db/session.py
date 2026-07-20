from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.config import database_url

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from db import models  # noqa: F401
    from db.models import Base
    from sqlalchemy import text

    Base.metadata.create_all(bind=engine)
    # 已有库：TEXT → LONGTEXT，避免 metadata_json / payload 写入 1406
    patches = (
        "ALTER TABLE messages MODIFY COLUMN metadata_json LONGTEXT NULL",
        "ALTER TABLE run_events MODIFY COLUMN payload_json LONGTEXT NULL",
        "ALTER TABLE confirmations MODIFY COLUMN payload_json LONGTEXT NULL",
    )
    with engine.begin() as conn:
        for sql in patches:
            try:
                conn.execute(text(sql))
            except Exception:
                # 表不存在或已是 LONGTEXT / 无权限时忽略
                pass
