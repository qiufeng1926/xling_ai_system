from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas import (
    ImportResult,
    InfluencerCreate,
    InfluencerFilter,
    InfluencerOut,
    InfluencerProfileOut,
    InfluencerUpdate,
    PageResult,
    ResponseBase,
    TagBrief,
)
from app.services.influencer_service import InfluencerService
from app.utils.access_control import can_view_full_library, influencer_ids_for_user

router = APIRouter(prefix="/influencers", tags=["达人管理"])


def _to_out(influencer) -> InfluencerOut:
    tags = [TagBrief.model_validate(it.tag) for it in influencer.tags if it.tag is not None]
    profile = (
        InfluencerProfileOut.model_validate(influencer.profile)
        if influencer.profile is not None
        else None
    )
    engagement = influencer.engagement_rate
    return InfluencerOut(
        id=influencer.id,
        platform=influencer.platform,
        platform_uid=influencer.platform_uid,
        nickname=influencer.nickname,
        avatar_url=influencer.avatar_url,
        profile_url=influencer.profile_url,
        agency_id=influencer.agency_id,
        follower_count=influencer.follower_count,
        engagement_rate=float(engagement) if engagement is not None else None,
        source=influencer.source,
        status=influencer.status,
        extra_data=influencer.extra_data,
        created_at=influencer.created_at,
        updated_at=influencer.updated_at,
        tags=tags,
        profile=profile,
        agency_name=influencer.agency.name if influencer.agency else None,
    )


def _ensure_influencer_access(db, user, influencer_id: int):
    if can_view_full_library(user):
        return InfluencerService.get_by_id(db, influencer_id)
    allowed = influencer_ids_for_user(db, user.id)
    if influencer_id not in allowed:
        return None
    return InfluencerService.get_by_id(db, influencer_id)


@router.get("", response_model=ResponseBase[PageResult[InfluencerOut]])
def list_influencers(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: str | None = None,
    source: str | None = None,
    keyword: str | None = None,
    follower_min: int | None = None,
    follower_max: int | None = None,
    tag_ids: list[int] | None = Query(None),
    agency_id: int | None = None,
    status: int | None = 1,
):
    filters = InfluencerFilter(
        platform=platform,
        source=source,
        keyword=keyword,
        follower_min=follower_min,
        follower_max=follower_max,
        tag_ids=tag_ids,
        agency_id=agency_id,
        status=status,
    )
    items, total = InfluencerService.list_influencers(db, filters, page, page_size, viewer=user)
    return ResponseBase(
        data=PageResult(
            items=[_to_out(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{influencer_id}", response_model=ResponseBase[InfluencerOut])
def get_influencer(db: DbSession, user: CurrentUser, influencer_id: int):
    influencer = _ensure_influencer_access(db, user, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在或无权查看")
    return ResponseBase(data=_to_out(influencer))


@router.post("", response_model=ResponseBase[InfluencerOut], status_code=status.HTTP_201_CREATED)
def create_influencer(db: DbSession, _: AdminUser, data: InfluencerCreate):
    try:
        influencer = InfluencerService.create(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_to_out(influencer))


@router.put("/{influencer_id}", response_model=ResponseBase[InfluencerOut])
def update_influencer(
    db: DbSession, _: AdminUser, influencer_id: int, data: InfluencerUpdate
):
    influencer = InfluencerService.get_by_id(db, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在")
    influencer = InfluencerService.update(db, influencer, data)
    return ResponseBase(data=_to_out(influencer))


@router.delete("/{influencer_id}", response_model=ResponseBase[None])
def delete_influencer(db: DbSession, _: AdminUser, influencer_id: int):
    influencer = InfluencerService.get_by_id(db, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在")
    InfluencerService.delete(db, influencer)
    return ResponseBase(message="删除成功")


@router.post("/import", response_model=ResponseBase[ImportResult])
async def import_influencers(
    db: DbSession,
    _: AdminUser,
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 Excel 文件")

    content = await file.read()
    result = InfluencerService.import_from_excel(db, content)
    return ResponseBase(data=result)
