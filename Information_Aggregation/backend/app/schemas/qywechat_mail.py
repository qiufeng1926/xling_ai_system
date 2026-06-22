from pydantic import BaseModel, Field


class WeComMailConfigOut(BaseModel):
    configured: bool
    corp_id: str | None = None


class WeComMailListQuery(BaseModel):
    begin_time: int | None = Field(default=None, description="Unix 开始时间")
    end_time: int | None = Field(default=None, description="Unix 结束时间")
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    days: int | None = Field(default=7, ge=1, le=31, description="未指定 begin/end 时拉取最近 N 天")


class WeComMailListItem(BaseModel):
    mail_id: str


class WeComMailListOut(BaseModel):
    mail_list: list[WeComMailListItem]
    next_cursor: str | None = None
    has_more: bool = False


class WeComMailDetailOut(BaseModel):
    mail_id: str
    subject: str = ""
    from_addr: str = ""
    to_addr: str = ""
    date: str = ""
    body_text: str = ""
    body_html: str = ""


class WeComMailSendRequest(BaseModel):
    to_emails: list[str] = Field(default_factory=list)
    to_userids: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    cc_userids: list[str] = Field(default_factory=list)
    bcc_emails: list[str] = Field(default_factory=list)
    bcc_userids: list[str] = Field(default_factory=list)
    subject: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    content_type: str = Field(default="html", pattern="^(html|text)$")
