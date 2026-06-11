"""标签 CRUD 与达人关联"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.tag_seed import TAG_SEED
from app.models import InfluencerTag, Tag
from app.schemas.tag import TagCreate, TagUpdate


class TagService:
    @staticmethod
    def seed_defaults(db: Session) -> int:
        created = 0
        for item in TAG_SEED:
            exists = db.query(Tag).filter(Tag.name == item["name"]).first()
            if exists:
                continue
            db.add(Tag(**item))
            created += 1
        if created:
            db.commit()
        return created

    @staticmethod
    def get_or_create(db: Session, name: str, category: str = "content") -> Tag:
        clean = name.strip()
        if not clean:
            raise ValueError("标签名不能为空")
        tag = db.query(Tag).filter(Tag.name == clean).first()
        if tag:
            return tag
        tag = Tag(name=clean, category=category, level=1)
        db.add(tag)
        db.flush()
        return tag

    @staticmethod
    def list_tags(db: Session, category: str | None = None) -> list[Tag]:
        query = db.query(Tag).order_by(Tag.category, Tag.name)
        if category:
            query = query.filter(Tag.category == category)
        return query.all()

    @staticmethod
    def get_tag_counts(db: Session) -> dict[int, int]:
        rows = (
            db.query(InfluencerTag.tag_id, func.count(InfluencerTag.influencer_id))
            .group_by(InfluencerTag.tag_id)
            .all()
        )
        return {tag_id: count for tag_id, count in rows}

    @staticmethod
    def build_tree(tags: list[Tag], counts: dict[int, int]) -> list[dict]:
        nodes: dict[int, dict] = {}
        roots: list[dict] = []

        for tag in tags:
            nodes[tag.id] = {
                "id": tag.id,
                "name": tag.name,
                "category": tag.category,
                "parent_id": tag.parent_id,
                "level": tag.level,
                "influencer_count": counts.get(tag.id, 0),
                "children": [],
            }

        for tag in tags:
            node = nodes[tag.id]
            if tag.parent_id and tag.parent_id in nodes:
                nodes[tag.parent_id]["children"].append(node)
            else:
                roots.append(node)

        return roots

    @staticmethod
    def get_by_id(db: Session, tag_id: int) -> Tag | None:
        return db.query(Tag).filter(Tag.id == tag_id).first()

    @staticmethod
    def create(db: Session, data: TagCreate) -> Tag:
        exists = db.query(Tag).filter(Tag.name == data.name.strip()).first()
        if exists:
            raise ValueError(f"标签「{data.name}」已存在")

        if data.parent_id:
            parent = TagService.get_by_id(db, data.parent_id)
            if not parent:
                raise ValueError("父标签不存在")

        tag = Tag(
            name=data.name.strip(),
            category=data.category,
            parent_id=data.parent_id,
            level=data.level,
        )
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return tag

    @staticmethod
    def update(db: Session, tag: Tag, data: TagUpdate) -> Tag:
        if data.name and data.name.strip() != tag.name:
            dup = db.query(Tag).filter(Tag.name == data.name.strip(), Tag.id != tag.id).first()
            if dup:
                raise ValueError(f"标签「{data.name}」已存在")
            tag.name = data.name.strip()

        if data.category is not None:
            tag.category = data.category
        if data.parent_id is not None:
            if data.parent_id == tag.id:
                raise ValueError("不能将标签设为自己的父级")
            if data.parent_id:
                parent = TagService.get_by_id(db, data.parent_id)
                if not parent:
                    raise ValueError("父标签不存在")
            tag.parent_id = data.parent_id
        if data.level is not None:
            tag.level = data.level

        db.commit()
        db.refresh(tag)
        return tag

    @staticmethod
    def delete(db: Session, tag: Tag) -> None:
        child = db.query(Tag).filter(Tag.parent_id == tag.id).first()
        if child:
            raise ValueError("请先删除或移动子标签")

        db.query(InfluencerTag).filter(InfluencerTag.tag_id == tag.id).delete()
        db.delete(tag)
        db.commit()

    @staticmethod
    def attach_to_influencer(
        db: Session,
        influencer_id: int,
        tag_ids: list[int] | None = None,
        tag_names: list[str] | None = None,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> int:
        ids = list(tag_ids or [])
        for name in tag_names or []:
            tag = TagService.get_or_create(db, name)
            ids.append(tag.id)

        attached = 0
        seen: set[int] = set()
        for tag_id in ids:
            if tag_id in seen:
                continue
            seen.add(tag_id)
            if not TagService.get_by_id(db, tag_id):
                continue
            exists = (
                db.query(InfluencerTag)
                .filter(
                    InfluencerTag.influencer_id == influencer_id,
                    InfluencerTag.tag_id == tag_id,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                InfluencerTag(
                    influencer_id=influencer_id,
                    tag_id=tag_id,
                    source=source,
                    confidence=confidence,
                )
            )
            attached += 1
        db.commit()
        return attached

    @staticmethod
    def attach_tags(
        db: Session,
        influencer_id: int,
        tag_names: list[str],
        source: str = "collect",
        confidence: float = 0.8,
    ) -> int:
        return TagService.attach_to_influencer(
            db,
            influencer_id,
            tag_names=tag_names,
            source=source,
            confidence=confidence,
        )

    @staticmethod
    def detach_from_influencer(db: Session, influencer_id: int, tag_id: int) -> None:
        (
            db.query(InfluencerTag)
            .filter(
                InfluencerTag.influencer_id == influencer_id,
                InfluencerTag.tag_id == tag_id,
            )
            .delete()
        )
        db.commit()

    @staticmethod
    def set_influencer_tags(db: Session, influencer_id: int, tag_ids: list[int]) -> None:
        db.query(InfluencerTag).filter(InfluencerTag.influencer_id == influencer_id).delete()
        for tag_id in tag_ids:
            if TagService.get_by_id(db, tag_id):
                db.add(
                    InfluencerTag(
                        influencer_id=influencer_id,
                        tag_id=tag_id,
                        source="manual",
                        confidence=1.0,
                    )
                )
        db.commit()
