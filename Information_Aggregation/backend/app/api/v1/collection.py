from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
import json

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas import PageResult, ResponseBase
from app.schemas.collection import (
    CollectionTaskCreate,
    CollectionTaskDetailOut,
    CollectionTaskOut,
    CollectedInfluencerOut,
    ReviewAction,
    ReviewResult,
    SessionCookieImport,
)
from app.services.collection_service import CollectionService, ERROR_CATEGORY_LABELS
from app.services.session_service import SessionService
from app.utils.filter_summary import build_filter_summary
from app.utils.collected_parsed import is_valid_profile_url, parse_collected_parsed
from app.utils.mcn_utils import extract_mcn_name

router = APIRouter(prefix="/collection", tags=["自动采集"])


def _to_optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num > 1:
        num = num / 100
    return round(num, 4)


def _task_out(task) -> CollectionTaskOut:
    data = CollectionTaskOut.model_validate(task)
    data.filter_summary = build_filter_summary(task.filters)
    return data


def _collected_out(item, library_map: dict[str, int] | None = None) -> CollectedInfluencerOut:
    data = CollectedInfluencerOut.model_validate(item)
    key = f"{item.platform}:{item.platform_uid}"
    if library_map and key in library_map:
        data.in_library = True
        data.existing_influencer_id = library_map[key]
    elif item.extra_data:
        data.in_library = bool(item.extra_data.get("in_library"))
        data.existing_influencer_id = item.extra_data.get("existing_influencer_id")
    data.mcn_name = extract_mcn_name(item.extra_data)
    extra = item.extra_data or {}
    parsed = parse_collected_parsed(extra, item.platform)
    if parsed:
        data.short_id = parsed.get("short_id")
        data.city = parsed.get("city")
        data.content_styles = parsed.get("content_styles") or []
        data.creator_type = parsed.get("creator_type") or extra.get("creator_type")
        data.expected_play_count = parsed.get("expected_play_count") or extra.get("expected_play_count")
        data.completion_rate = _to_optional_float(parsed.get("completion_rate"))
        if data.completion_rate is None and extra.get("completion_rate") is not None:
            data.completion_rate = _to_optional_float(extra.get("completion_rate"))
        data.deal_rate = _to_optional_float(parsed.get("deal_rate"))
        if data.deal_rate is None and extra.get("deal_rate") is not None:
            data.deal_rate = _to_optional_float(extra.get("deal_rate"))
        if data.avg_views is None and data.expected_play_count is not None:
            data.avg_views = data.expected_play_count
        contact = parsed.get("contact") or {}
        data.contact_phone = contact.get("phone")
        data.contact_wechat = contact.get("wechat")
        if not data.profile_url:
            candidate = parsed.get("profile_url")
            if candidate and is_valid_profile_url(str(candidate), item.platform):
                data.profile_url = candidate
        if data.profile_url and not is_valid_profile_url(data.profile_url, item.platform):
            data.profile_url = None
        if item.platform == "xiaohongshu":
            xh = parsed.get("xhs_homepage")
            pgy = parsed.get("pgy_homepage")
            data.xhs_homepage = xh if xh and is_valid_profile_url(str(xh), item.platform) else None
            data.pgy_homepage = pgy if pgy and is_valid_profile_url(str(pgy), item.platform) else None
        else:
            xh = parsed.get("xingtu_homepage")
            dh = parsed.get("douyin_homepage")
            data.xingtu_homepage = xh if xh and is_valid_profile_url(str(xh), item.platform) else None
            data.douyin_homepage = dh if dh and is_valid_profile_url(str(dh), item.platform) else None
        if data.engagement_rate is None and parsed.get("engagement_rate") is not None:
            data.engagement_rate = parsed.get("engagement_rate")
    return data


@router.get("/config", response_model=ResponseBase[dict])
def get_collection_config(_: CurrentUser, platform: str = Query("douyin")):
    return ResponseBase(data=CollectionService.check_environment(platform))


@router.get("/sessions", response_model=ResponseBase[list])
def list_collection_sessions(_: AdminUser):
    return ResponseBase(data=SessionService.list_sessions())


@router.post("/sessions/{platform}/login/start", response_model=ResponseBase[dict])
def start_platform_login(_: AdminUser, platform: str):
    try:
        return ResponseBase(data=SessionService.start_login(platform), message="浏览器已打开，请完成登录")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/sessions/{platform}/login/save", response_model=ResponseBase[dict])
def save_platform_login(_: AdminUser, platform: str):
    try:
        return ResponseBase(data=SessionService.save_login(platform), message="登录态已保存")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sessions/{platform}/login/cancel", response_model=ResponseBase[dict])
def cancel_platform_login(_: AdminUser, platform: str):
    return ResponseBase(data=SessionService.cancel_login(platform), message="已取消登录流程")


@router.post("/sessions/{platform}/import", response_model=ResponseBase[dict])
def import_platform_cookies(_: AdminUser, platform: str, data: SessionCookieImport):
    try:
        return ResponseBase(
            data=SessionService.import_cookies(platform, data.content),
            message="远程登录态已保存",
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sessions/{platform}/upload", response_model=ResponseBase[dict])
async def upload_platform_session(_: AdminUser, platform: str, file: UploadFile = File(...)):
    try:
        content = await file.read()
        return ResponseBase(
            data=SessionService.upload_storage_state(platform, content),
            message="登录态文件已上传",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/sessions/{platform}", response_model=ResponseBase[dict])
def delete_platform_session(_: AdminUser, platform: str):
    return ResponseBase(data=SessionService.delete_storage_state(platform), message="登录态已清除")


@router.get("/stats", response_model=ResponseBase[dict])
def get_collection_stats(db: DbSession, user: CurrentUser):
    return ResponseBase(data=CollectionService.get_stats(db, user))


@router.get("/filter-options", response_model=ResponseBase[dict])
def get_filter_options(_: CurrentUser, platform: str = Query("douyin")):
    if platform == "xiaohongshu":
        from app.constants.pugongying_filters import get_filter_options

        return ResponseBase(data=get_filter_options())
    from app.constants.xingtu_filters import get_filter_options

    return ResponseBase(data=get_filter_options())


@router.post("/tasks", response_model=ResponseBase[CollectionTaskOut], status_code=status.HTTP_201_CREATED)
def create_collection_task(db: DbSession, user: CurrentUser, data: CollectionTaskCreate):
    try:
        task = CollectionService.create_task(db, user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    CollectionService.run_task_async(task.id)
    return ResponseBase(data=_task_out(task), message="采集任务已创建，已加入队列")


@router.get("/tasks", response_model=ResponseBase[PageResult[CollectionTaskOut]])
def list_collection_tasks(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = CollectionService.list_tasks(db, user, page, page_size)
    return ResponseBase(
        data=PageResult(
            items=[_task_out(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/tasks/{task_id}", response_model=ResponseBase[CollectionTaskOut])
def get_collection_task(db: DbSession, user: CurrentUser, task_id: int):
    task = CollectionService.get_task(db, task_id, user)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return ResponseBase(data=_task_out(task))


@router.get("/tasks/{task_id}/detail", response_model=ResponseBase[CollectionTaskDetailOut])
def get_collection_task_detail(db: DbSession, user: CurrentUser, task_id: int):
    detail = CollectionService.get_task_detail(db, task_id, user)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    task = detail["task"]
    out = CollectionTaskDetailOut.model_validate(task)
    out.filter_summary = detail["filter_summary"]
    out.duration_seconds = detail["duration_seconds"]
    out.queue_size = detail["queue_size"]
    out.queue_position = detail["queue_position"]
    out.running_task_id = detail["running_task_id"]
    out.sample_items = [
        _collected_out(i, detail["library_uids"]) for i in detail["sample_items"]
    ]
    if out.error_category:
        label = ERROR_CATEGORY_LABELS.get(out.error_category, out.error_category)
        if out.error_message and label not in out.error_message:
            out.error_message = f"[{label}] {out.error_message}"
    return ResponseBase(data=out)


@router.post("/tasks/{task_id}/retry", response_model=ResponseBase[CollectionTaskOut])
def retry_collection_task(db: DbSession, user: CurrentUser, task_id: int):
    task = CollectionService.get_task(db, task_id, user)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if task.status == "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务正在执行中")

    task.status = "pending"
    task.error_message = None
    task.error_category = None
    db.commit()
    CollectionService.run_task_async(task.id)
    return ResponseBase(data=_task_out(task), message="任务已重新加入队列")


@router.get("/pending", response_model=ResponseBase[PageResult[CollectedInfluencerOut]])
def list_pending_review(
    db: DbSession,
    user: CurrentUser,
    task_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total, library_map = CollectionService.list_pending(
        db, user, task_id, page, page_size
    )
    return ResponseBase(
        data=PageResult(
            items=[_collected_out(i, library_map) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/reviewed", response_model=ResponseBase[PageResult[CollectedInfluencerOut]])
def list_reviewed(
    db: DbSession,
    user: CurrentUser,
    review_status: str = Query("approved", pattern="^(approved|rejected)$"),
    task_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = CollectionService.list_reviewed(
        db, user, review_status, task_id, page, page_size
    )
    return ResponseBase(
        data=PageResult(
            items=[_collected_out(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/approve", response_model=ResponseBase[ReviewResult])
def approve_collected(db: DbSession, user: CurrentUser, data: ReviewAction):
    result = CollectionService.approve_items(db, data.ids, user)
    return ResponseBase(data=result, message=f"已通过 {result.approved} 条")


@router.post("/reject", response_model=ResponseBase[ReviewResult])
def reject_collected(db: DbSession, user: CurrentUser, data: ReviewAction):
    result = CollectionService.reject_items(db, data.ids, user)
    return ResponseBase(data=result, message=f"已拒绝 {result.rejected} 条")
