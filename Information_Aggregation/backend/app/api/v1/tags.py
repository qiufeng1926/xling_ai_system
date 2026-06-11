from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.constants.tag_seed import TAG_CATEGORY_LABELS
from app.schemas import ResponseBase
from app.schemas.tag import TagAttachAction, TagCreate, TagOut, TagUpdate
from app.services.influencer_service import InfluencerService
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["标签管理"])


def _tag_out(tag, count: int = 0, children: list | None = None) -> TagOut:
    return TagOut(
        id=tag.id,
        name=tag.name,
        category=tag.category,
        parent_id=tag.parent_id,
        level=tag.level,
        influencer_count=count,
        children=children or [],
    )


@router.get("/categories", response_model=ResponseBase[dict])
def list_tag_categories(_: CurrentUser):
    return ResponseBase(data=TAG_CATEGORY_LABELS)


@router.get("", response_model=ResponseBase[list[TagOut]])
def list_tags(
    db: DbSession,
    _: CurrentUser,
    category: str | None = None,
    tree: bool = Query(False, description="是否返回树形结构"),
):
    tags = TagService.list_tags(db, category)
    counts = TagService.get_tag_counts(db)

    if tree:
        tree_data = TagService.build_tree(tags, counts)

        def to_out(node: dict) -> TagOut:
            return TagOut(
                id=node["id"],
                name=node["name"],
                category=node["category"],
                parent_id=node["parent_id"],
                level=node["level"],
                influencer_count=node["influencer_count"],
                children=[to_out(c) for c in node["children"]],
            )

        return ResponseBase(data=[to_out(n) for n in tree_data])

    return ResponseBase(
        data=[_tag_out(t, counts.get(t.id, 0)) for t in tags]
    )


@router.post("", response_model=ResponseBase[TagOut], status_code=status.HTTP_201_CREATED)
def create_tag(db: DbSession, _: AdminUser, data: TagCreate):
    try:
        tag = TagService.create(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_tag_out(tag))


@router.put("/{tag_id}", response_model=ResponseBase[TagOut])
def update_tag(db: DbSession, _: AdminUser, tag_id: int, data: TagUpdate):
    tag = TagService.get_by_id(db, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    try:
        tag = TagService.update(db, tag, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    counts = TagService.get_tag_counts(db)
    return ResponseBase(data=_tag_out(tag, counts.get(tag.id, 0)))


@router.delete("/{tag_id}", response_model=ResponseBase[None])
def delete_tag(db: DbSession, _: AdminUser, tag_id: int):
    tag = TagService.get_by_id(db, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    try:
        TagService.delete(db, tag)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(message="删除成功")


@router.post("/influencers/{influencer_id}/attach", response_model=ResponseBase[dict])
def attach_influencer_tags(
    db: DbSession,
    _: CurrentUser,
    influencer_id: int,
    data: TagAttachAction,
):
    influencer = InfluencerService.get_by_id(db, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在")
    if not data.tag_ids and not data.tag_names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请提供 tag_ids 或 tag_names")

    count = TagService.attach_to_influencer(
        db,
        influencer_id,
        tag_ids=data.tag_ids,
        tag_names=data.tag_names,
        source="manual",
    )
    return ResponseBase(data={"attached": count}, message=f"已添加 {count} 个标签")


@router.put("/influencers/{influencer_id}", response_model=ResponseBase[dict])
def set_influencer_tags(
    db: DbSession,
    _: CurrentUser,
    influencer_id: int,
    data: TagAttachAction,
):
    influencer = InfluencerService.get_by_id(db, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在")

    TagService.set_influencer_tags(db, influencer_id, data.tag_ids)
    return ResponseBase(message="标签已更新")


@router.delete("/influencers/{influencer_id}/{tag_id}", response_model=ResponseBase[None])
def detach_influencer_tag(
    db: DbSession,
    _: CurrentUser,
    influencer_id: int,
    tag_id: int,
):
    influencer = InfluencerService.get_by_id(db, influencer_id)
    if not influencer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="达人不存在")

    TagService.detach_from_influencer(db, influencer_id, tag_id)
    return ResponseBase(message="已移除标签")
