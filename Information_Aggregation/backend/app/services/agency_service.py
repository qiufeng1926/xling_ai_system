from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Agency, Influencer
from app.schemas.agency import AgencyCreate, AgencyUpdate


class AgencyService:
    @staticmethod
    def _stats_query(db: Session):
        return (
            db.query(
                Influencer.agency_id.label("agency_id"),
                func.count(Influencer.id).label("influencer_count"),
                func.coalesce(func.avg(Influencer.follower_count), 0).label("avg_followers"),
                func.coalesce(func.sum(Influencer.follower_count), 0).label("total_followers"),
            )
            .filter(Influencer.agency_id.isnot(None), Influencer.status == 1)
            .group_by(Influencer.agency_id)
            .subquery()
        )

    @staticmethod
    def get_stats_map(db: Session) -> dict[int, dict]:
        rows = (
            db.query(
                Influencer.agency_id,
                func.count(Influencer.id),
                func.coalesce(func.avg(Influencer.follower_count), 0),
                func.coalesce(func.sum(Influencer.follower_count), 0),
            )
            .filter(Influencer.agency_id.isnot(None), Influencer.status == 1)
            .group_by(Influencer.agency_id)
            .all()
        )
        return {
            agency_id: {
                "influencer_count": count,
                "avg_follower_count": int(avg or 0),
                "total_followers": int(total or 0),
            }
            for agency_id, count, avg, total in rows
        }

    @staticmethod
    def get_by_id(db: Session, agency_id: int) -> Agency | None:
        return db.query(Agency).filter(Agency.id == agency_id).first()

    @staticmethod
    def get_or_create_by_name(
        db: Session,
        name: str,
        platform: str | None = None,
    ) -> Agency | None:
        from app.utils.mcn_utils import normalize_mcn_name

        clean = normalize_mcn_name(name)
        if not clean:
            return None

        agency = db.query(Agency).filter(Agency.name == clean).first()
        if agency:
            if platform and not agency.platform:
                agency.platform = platform
            return agency

        agency = Agency(name=clean, platform=platform)
        db.add(agency)
        db.flush()
        return agency

    @staticmethod
    def resolve_agency_id(
        db: Session,
        platform: str,
        extra_data: dict | None,
    ) -> int | None:
        from app.utils.mcn_utils import extract_mcn_name

        mcn_name = extract_mcn_name(extra_data or {})
        if not mcn_name:
            return None

        agency = AgencyService.get_or_create_by_name(db, mcn_name, platform=platform)
        return agency.id if agency else None

    @staticmethod
    def list_agencies(
        db: Session,
        keyword: str | None,
        platform: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Agency], int, dict[int, dict]]:
        query = db.query(Agency)
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                (Agency.name.like(like))
                | (Agency.contact_person.like(like))
                | (Agency.contact_phone.like(like))
            )
        if platform:
            query = query.filter(Agency.platform == platform)

        total = query.count()
        items = (
            query.order_by(Agency.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        stats = AgencyService.get_stats_map(db)
        return items, total, stats

    @staticmethod
    def create(db: Session, data: AgencyCreate) -> Agency:
        exists = db.query(Agency).filter(Agency.name == data.name.strip()).first()
        if exists:
            raise ValueError(f"机构「{data.name}」已存在")

        agency = Agency(**data.model_dump())
        agency.name = agency.name.strip()
        db.add(agency)
        db.commit()
        db.refresh(agency)
        return agency

    @staticmethod
    def update(db: Session, agency: Agency, data: AgencyUpdate) -> Agency:
        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"]:
            dup = (
                db.query(Agency)
                .filter(Agency.name == update_data["name"].strip(), Agency.id != agency.id)
                .first()
            )
            if dup:
                raise ValueError(f"机构「{update_data['name']}」已存在")
            update_data["name"] = update_data["name"].strip()

        for key, value in update_data.items():
            setattr(agency, key, value)

        db.commit()
        db.refresh(agency)
        return agency

    @staticmethod
    def delete(db: Session, agency: Agency) -> None:
        db.query(Influencer).filter(Influencer.agency_id == agency.id).update(
            {Influencer.agency_id: None},
            synchronize_session=False,
        )
        db.delete(agency)
        db.commit()

    @staticmethod
    def list_influencers(
        db: Session,
        agency_id: int,
        page: int,
        page_size: int,
    ) -> tuple[list[Influencer], int]:
        query = db.query(Influencer).filter(
            Influencer.agency_id == agency_id,
            Influencer.status == 1,
        )
        total = query.count()
        items = (
            query.order_by(Influencer.follower_count.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    @staticmethod
    def list_options(db: Session) -> list[Agency]:
        return db.query(Agency).order_by(Agency.name).all()
