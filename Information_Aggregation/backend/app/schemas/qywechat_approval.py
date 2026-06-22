from typing import Any

from pydantic import BaseModel, Field


class WeComApprovalConfigOut(BaseModel):
    configured: bool
    corp_id: str | None = None
    default_template_id: str | None = None


class WeComApprovalFilter(BaseModel):
    key: str
    value: str


class WeComApprovalListQuery(BaseModel):
    days: int = Field(7, ge=1, le=31)
    sp_status: str | None = None
    template_id: str | None = None
    creator: str | None = None
    cursor: str | None = None
    size: int = Field(50, ge=1, le=100)


class WeComApprovalListItem(BaseModel):
    sp_no: str
    sp_name: str | None = None
    sp_status: int | None = None
    sp_status_label: str | None = None
    template_id: str | None = None
    apply_time: int | None = None
    applyer_userid: str | None = None


class WeComApprovalListOut(BaseModel):
    sp_list: list[WeComApprovalListItem]
    next_cursor: str | None = None
    has_more: bool = False


class WeComApprovalDetailOut(BaseModel):
    sp_no: str
    sp_name: str | None = None
    sp_status: int | None = None
    sp_status_label: str | None = None
    template_id: str | None = None
    apply_time: int | None = None
    applyer: dict[str, Any] | None = None
    apply_data: dict[str, Any] | None = None
    sp_record: list[Any] | None = None
    notifyer: list[Any] | None = None
    comments: list[Any] | None = None
    process_list: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


class WeComApprovalTemplateRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=200)


class WeComApprovalTemplateOut(BaseModel):
    template_id: str
    template_names: list[dict[str, Any]] = Field(default_factory=list)
    template_content: dict[str, Any] | None = None


class WeComApprovalApplyContent(BaseModel):
    control: str
    id: str
    value: dict[str, Any]


class WeComApprovalApplyRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=200)
    creator_userid: str = Field(..., min_length=1, max_length=64)
    use_template_approver: int = Field(1, ge=0, le=1)
    choose_department: int | None = None
    contents: list[WeComApprovalApplyContent] = Field(..., min_length=1)
    summary_lines: list[str] = Field(default_factory=list, max_length=3)
    process: dict[str, Any] | None = None


class WeComApprovalApplyOut(BaseModel):
    sp_no: str
