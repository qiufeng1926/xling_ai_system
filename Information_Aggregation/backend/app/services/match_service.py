from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session, joinedload

from app.models import Influencer, InfluencerTag, MatchRequest, MatchResult, User
from app.schemas.match import MatchRequestCreate, MatchRequirements
from app.services.match_engine import rank_influencers
from app.utils.access_control import match_query_for_viewer


class MatchService:
    @staticmethod
    def get_request(
        db: Session,
        request_id: int,
        viewer: User,
    ) -> MatchRequest | None:
        return (
            match_query_for_viewer(db, viewer)
            .filter(MatchRequest.id == request_id)
            .first()
        )

    @staticmethod
    def list_requests(
        db: Session,
        viewer: User,
        page: int,
        page_size: int,
    ) -> tuple[list[MatchRequest], int]:
        query = match_query_for_viewer(db, viewer).order_by(
            MatchRequest.created_at.desc()
        )
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def _load_candidates(db: Session, req: MatchRequirements) -> list[Influencer]:
        query = (
            db.query(Influencer)
            .filter(Influencer.status == 1)
            .options(
                joinedload(Influencer.tags).joinedload(InfluencerTag.tag),
                joinedload(Influencer.profile),
                joinedload(Influencer.agency),
            )
        )
        if req.platform:
            query = query.filter(Influencer.platform == req.platform)
        if req.follower_min is not None:
            query = query.filter(Influencer.follower_count >= req.follower_min)
        if req.follower_max is not None:
            query = query.filter(Influencer.follower_count <= req.follower_max)
        if req.engagement_rate_min is not None:
            query = query.filter(Influencer.engagement_rate >= req.engagement_rate_min)
        if req.keyword:
            keyword = f"%{req.keyword}%"
            query = query.filter(
                (Influencer.nickname.like(keyword)) | (Influencer.platform_uid.like(keyword))
            )
        if req.required_tag_ids:
            for tag_id in req.required_tag_ids:
                query = query.filter(
                    Influencer.id.in_(
                        db.query(InfluencerTag.influencer_id).filter(InfluencerTag.tag_id == tag_id)
                    )
                )
        return query.all()

    @staticmethod
    def create_and_run(
        db: Session,
        user_id: int,
        data: MatchRequestCreate,
    ) -> MatchRequest:
        req = data.requirements
        match_request = MatchRequest(
            user_id=user_id,
            title=data.title or _default_title(req),
            requirements=req.model_dump(exclude_none=True),
            status="running",
        )
        db.add(match_request)
        db.flush()

        try:
            candidates = MatchService._load_candidates(db, req)
            ranked = rank_influencers(candidates, req)

            for rank, item in enumerate(ranked, start=1):
                db.add(
                    MatchResult(
                        request_id=match_request.id,
                        influencer_id=item.influencer.id,
                        match_score=item.score,
                        rank_order=rank,
                        reason=item.reason.model_dump(),
                        is_selected=0,
                    )
                )

            match_request.status = "completed"
            match_request.result_count = len(ranked)
        except Exception:
            match_request.status = "failed"
            match_request.result_count = 0
            raise
        finally:
            if match_request.transfer_pending_user_id and match_request.status in ("completed", "failed"):
                match_request.user_id = match_request.transfer_pending_user_id
                match_request.transfer_pending_user_id = None
            db.commit()
            db.refresh(match_request)

        return match_request

    @staticmethod
    def list_results(
        db: Session,
        request_id: int,
        viewer: User,
        page: int,
        page_size: int,
        selected_only: bool = False,
    ) -> tuple[list[MatchResult], int]:
        if not MatchService.get_request(db, request_id, viewer):
            return [], 0

        query = (
            db.query(MatchResult)
            .filter(MatchResult.request_id == request_id)
            .options(
                joinedload(MatchResult.influencer)
                .joinedload(Influencer.tags)
                .joinedload(InfluencerTag.tag),
                joinedload(MatchResult.influencer).joinedload(Influencer.agency),
            )
            .order_by(MatchResult.rank_order)
        )
        if selected_only:
            query = query.filter(MatchResult.is_selected == 1)

        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def update_selection(
        db: Session,
        request_id: int,
        viewer: User,
        result_ids: list[int],
        selected: bool,
    ) -> int:
        if not MatchService.get_request(db, request_id, viewer):
            return 0

        updated = (
            db.query(MatchResult)
            .filter(
                MatchResult.request_id == request_id,
                MatchResult.id.in_(result_ids),
            )
            .update({MatchResult.is_selected: 1 if selected else 0}, synchronize_session=False)
        )
        db.commit()
        return updated

    @staticmethod
    def count_selected(db: Session, request_id: int) -> int:
        return (
            db.query(MatchResult)
            .filter(MatchResult.request_id == request_id, MatchResult.is_selected == 1)
            .count()
        )

    @staticmethod
    def export_excel(
        db: Session,
        request_id: int,
        viewer: User,
        selected_only: bool = False,
    ) -> BytesIO | None:
        if not MatchService.get_request(db, request_id, viewer):
            return None

        query = (
            db.query(MatchResult)
            .filter(MatchResult.request_id == request_id)
            .options(
                joinedload(MatchResult.influencer)
                .joinedload(Influencer.tags)
                .joinedload(InfluencerTag.tag),
                joinedload(MatchResult.influencer).joinedload(Influencer.agency),
            )
            .order_by(MatchResult.rank_order)
        )
        if selected_only:
            query = query.filter(MatchResult.is_selected == 1)

        results = query.all()
        if not results:
            return None

        wb = Workbook()
        ws = wb.active
        ws.title = "匹配结果"
        headers = [
            "排名",
            "匹配分",
            "昵称",
            "平台",
            "达人ID",
            "粉丝量",
            "互动率",
            "机构",
            "标签",
            "匹配说明",
            "是否选中",
        ]
        ws.append(headers)

        platform_labels = {"douyin": "抖音", "xiaohongshu": "小红书", "kuaishou": "快手", "wechat": "微信"}

        for row in results:
            inf = row.influencer
            tags = ", ".join(it.tag.name for it in inf.tags if it.tag)
            reason = row.reason or {}
            summary = reason.get("summary", "") if isinstance(reason, dict) else ""
            ws.append(
                [
                    row.rank_order,
                    float(row.match_score or 0),
                    inf.nickname or "",
                    platform_labels.get(inf.platform, inf.platform),
                    inf.platform_uid,
                    inf.follower_count,
                    float(inf.engagement_rate) if inf.engagement_rate else "",
                    inf.agency.name if inf.agency else "",
                    tags,
                    summary,
                    "是" if row.is_selected else "否",
                ]
            )

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

    @staticmethod
    def delete_request(
        db: Session,
        request_id: int,
        viewer: User,
    ) -> bool:
        match_request = MatchService.get_request(db, request_id, viewer)
        if not match_request:
            return False
        db.delete(match_request)
        db.commit()
        return True


def _default_title(req: MatchRequirements) -> str:
    parts: list[str] = []
    if req.platform:
        labels = {"douyin": "抖音", "xiaohongshu": "小红书", "kuaishou": "快手"}
        parts.append(labels.get(req.platform, req.platform))
    if req.follower_min or req.follower_max:
        lo = req.follower_min or 0
        hi = req.follower_max or "∞"
        parts.append(f"粉丝{lo}-{hi}")
    return "智能匹配" + ("-" + "/".join(parts) if parts else "")
