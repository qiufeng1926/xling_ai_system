from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.models import MatchRequest
from app.schemas import PageResult, ResponseBase
from app.schemas.match import (
    MatchInfluencerBrief,
    MatchReasonOut,
    MatchRequestCreate,
    MatchRequestDetailOut,
    MatchRequestOut,
    MatchResultOut,
    MatchSelectionUpdate,
)
from app.services.match_service import MatchService
from app.utils.access_control import can_use_match

router = APIRouter(prefix="/match", tags=["智能匹配"])


def _result_out(row) -> MatchResultOut:
    inf = row.influencer
    influencer_brief = None
    if inf is not None:
        tags = [it.tag.name for it in inf.tags if it.tag is not None]
        engagement = inf.engagement_rate
        influencer_brief = MatchInfluencerBrief(
            id=inf.id,
            platform=inf.platform,
            platform_uid=inf.platform_uid,
            nickname=inf.nickname,
            avatar_url=inf.avatar_url,
            follower_count=inf.follower_count,
            engagement_rate=float(engagement) if engagement is not None else None,
            agency_name=inf.agency.name if inf.agency else None,
            tags=tags,
        )

    reason = None
    if row.reason and isinstance(row.reason, dict):
        reason = MatchReasonOut.model_validate(row.reason)

    return MatchResultOut(
        id=row.id,
        request_id=row.request_id,
        influencer_id=row.influencer_id,
        match_score=float(row.match_score) if row.match_score is not None else None,
        rank_order=row.rank_order,
        reason=reason,
        is_selected=bool(row.is_selected),
        influencer=influencer_brief,
    )


def _request_out(db, match_request: MatchRequest) -> MatchRequestOut:
    selected = MatchService.count_selected(db, match_request.id)
    return MatchRequestOut(
        id=match_request.id,
        user_id=match_request.user_id,
        title=match_request.title,
        requirements=match_request.requirements,
        status=match_request.status,
        result_count=match_request.result_count,
        created_at=match_request.created_at,
        selected_count=selected,
    )


@router.post("/requests", response_model=ResponseBase[MatchRequestOut], status_code=status.HTTP_201_CREATED)
def create_match_request(db: DbSession, user: CurrentUser, data: MatchRequestCreate):
    if not can_use_match(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="普通用户无权使用智能匹配")
    try:
        match_request = MatchService.create_and_run(db, user.id, data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="匹配执行失败，请稍后重试",
        ) from exc
    return ResponseBase(data=_request_out(db, match_request), message=f"匹配完成，共 {match_request.result_count} 条结果")


@router.get("/requests", response_model=ResponseBase[PageResult[MatchRequestOut]])
def list_match_requests(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = MatchService.list_requests(db, user, page, page_size)
    return ResponseBase(
        data=PageResult(
            items=[_request_out(db, i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/requests/{request_id}", response_model=ResponseBase[MatchRequestDetailOut])
def get_match_request(db: DbSession, user: CurrentUser, request_id: int):
    match_request = MatchService.get_request(db, request_id, user)
    if not match_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="匹配需求不存在")

    top_results, _ = MatchService.list_results(
        db, request_id, user, page=1, page_size=5
    )
    out = MatchRequestDetailOut(
        **_request_out(db, match_request).model_dump(),
        top_results=[_result_out(r) for r in top_results],
    )
    return ResponseBase(data=out)


@router.get("/requests/{request_id}/results", response_model=ResponseBase[PageResult[MatchResultOut]])
def list_match_results(
    db: DbSession,
    user: CurrentUser,
    request_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    selected_only: bool = False,
):
    if not MatchService.get_request(db, request_id, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="匹配需求不存在")

    items, total = MatchService.list_results(
        db, request_id, user, page, page_size, selected_only
    )
    return ResponseBase(
        data=PageResult(
            items=[_result_out(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.put("/requests/{request_id}/selection", response_model=ResponseBase[dict])
def update_match_selection(
    db: DbSession,
    user: CurrentUser,
    request_id: int,
    data: MatchSelectionUpdate,
):
    updated = MatchService.update_selection(
        db,
        request_id,
        user,
        data.result_ids,
        data.selected,
    )
    if updated == 0 and data.result_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可更新的结果")
    return ResponseBase(data={"updated": updated}, message="已更新选中状态")


@router.get("/requests/{request_id}/export")
def export_match_results(
    db: DbSession,
    user: CurrentUser,
    request_id: int,
    selected_only: bool = False,
):
    buffer = MatchService.export_excel(db, request_id, user, selected_only)
    if buffer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="无可导出数据")

    filename = f"match_{request_id}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/requests/{request_id}", response_model=ResponseBase[None])
def delete_match_request(db: DbSession, user: CurrentUser, request_id: int):
    if not MatchService.delete_request(db, request_id, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="匹配需求不存在")
    return ResponseBase(message="已删除")
