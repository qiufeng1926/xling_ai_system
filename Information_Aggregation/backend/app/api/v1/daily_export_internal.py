"""内部 API：手动触发每日全量导出。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.deps import DbSession
from app.config import settings
from app.schemas import ResponseBase
from app.services.daily_export_service import DailyExportService

router = APIRouter(prefix="/internal/daily-export", tags=["内部-每日导出"])


def _verify_internal_key(x_portal_internal_key: str = Header(default="")) -> None:
    expected = (settings.PORTAL_INTERNAL_KEY or settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not expected or x_portal_internal_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的内部密钥")


@router.post("/run", response_model=ResponseBase[dict], dependencies=[Depends(_verify_internal_key)])
def run_daily_export(
    db: DbSession,
    export_date: date | None = Query(default=None, description="指定导出日期目录，默认当天"),
):
    manifest = DailyExportService.run_export(db, export_date=export_date)
    return ResponseBase(data=manifest)
