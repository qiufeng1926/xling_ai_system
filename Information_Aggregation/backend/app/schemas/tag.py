from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str | None = Field(default="content", max_length=50)
    parent_id: int | None = None
    level: int = Field(default=1, ge=1, le=3)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    parent_id: int | None = None
    level: int | None = Field(default=None, ge=1, le=3)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None
    parent_id: int | None
    level: int
    influencer_count: int = 0
    children: list["TagOut"] = []


class TagAttachAction(BaseModel):
    tag_ids: list[int] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)


TagOut.model_rebuild()
