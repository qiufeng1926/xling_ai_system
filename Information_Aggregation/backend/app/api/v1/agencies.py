from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas import PageResult, ResponseBase
from app.schemas.agency import AgencyCreate, AgencyDetailOut, AgencyOut, AgencyUpdate
from app.services.agency_service import AgencyService

router = APIRouter(prefix="/agencies", tags=["MCN机构"])


def _agency_out(agency, stats: dict | None = None) -> AgencyOut:
    stat = stats or {}
    return AgencyOut(
        id=agency.id,
        name=agency.name,
        platform=agency.platform,
        contact_person=agency.contact_person,
        contact_phone=agency.contact_phone,
        contact_wechat=agency.contact_wechat,
        policy_notes=agency.policy_notes,
        cooperation_terms=agency.cooperation_terms,
        created_at=agency.created_at,
        updated_at=agency.updated_at,
        influencer_count=stat.get("influencer_count", 0),
        avg_follower_count=stat.get("avg_follower_count", 0),
    )


@router.get("/options", response_model=ResponseBase[list[AgencyOut]])
def list_agency_options(db: DbSession, _: AdminUser):
    items = AgencyService.list_options(db)
    stats = AgencyService.get_stats_map(db)
    return ResponseBase(data=[_agency_out(a, stats.get(a.id)) for a in items])


@router.get("", response_model=ResponseBase[PageResult[AgencyOut]])
def list_agencies(
    db: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    platform: str | None = None,
):
    items, total, stats = AgencyService.list_agencies(db, keyword, platform, page, page_size)
    return ResponseBase(
        data=PageResult(
            items=[_agency_out(a, stats.get(a.id)) for a in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{agency_id}", response_model=ResponseBase[AgencyDetailOut])
def get_agency(db: DbSession, _: AdminUser, agency_id: int):
    agency = AgencyService.get_by_id(db, agency_id)
    if not agency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机构不存在")

    stats = AgencyService.get_stats_map(db).get(agency_id, {})
    out = AgencyDetailOut(
        **_agency_out(agency, stats).model_dump(),
        total_followers=stats.get("total_followers", 0),
    )
    return ResponseBase(data=out)


@router.post("", response_model=ResponseBase[AgencyOut], status_code=status.HTTP_201_CREATED)
def create_agency(db: DbSession, _: AdminUser, data: AgencyCreate):
    try:
        agency = AgencyService.create(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_agency_out(agency))


@router.put("/{agency_id}", response_model=ResponseBase[AgencyOut])
def update_agency(db: DbSession, _: AdminUser, agency_id: int, data: AgencyUpdate):
    agency = AgencyService.get_by_id(db, agency_id)
    if not agency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机构不存在")
    try:
        agency = AgencyService.update(db, agency, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    stats = AgencyService.get_stats_map(db).get(agency.id, {})
    return ResponseBase(data=_agency_out(agency, stats))


@router.delete("/{agency_id}", response_model=ResponseBase[None])
def delete_agency(db: DbSession, _: AdminUser, agency_id: int):
    agency = AgencyService.get_by_id(db, agency_id)
    if not agency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机构不存在")
    AgencyService.delete(db, agency)
    return ResponseBase(message="删除成功，旗下达人已解除关联")


@router.get("/{agency_id}/influencers", response_model=ResponseBase[PageResult[dict]])
def list_agency_influencers(
    db: DbSession,
    _: AdminUser,
    agency_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    agency = AgencyService.get_by_id(db, agency_id)
    if not agency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机构不存在")

    items, total = AgencyService.list_influencers(db, agency_id, page, page_size)
    return ResponseBase(
        data=PageResult(
            items=[
                {
                    "id": i.id,
                    "nickname": i.nickname,
                    "platform": i.platform,
                    "platform_uid": i.platform_uid,
                    "follower_count": i.follower_count,
                    "source": i.source,
                }
                for i in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
