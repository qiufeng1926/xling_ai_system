"""企业微信 API 客户端（access_token 缓存 + 邮件接口）"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from app.config import settings


class WeComError(Exception):
    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"[{errcode}] {errmsg}")


class WeComClient:
    """企业微信自建应用 API 客户端"""

    _token_lock = threading.Lock()
    _cached_token: str | None = None
    _token_expires_at: float = 0.0

    def __init__(
        self,
        corp_id: str | None = None,
        corp_secret: str | None = None,
        api_base: str | None = None,
    ):
        self.corp_id = (corp_id or settings.WECOM_CORP_ID or "").strip()
        self.corp_secret = (corp_secret or settings.WECOM_CORP_SECRET or "").strip()
        self.api_base = (api_base or settings.WECOM_API_BASE or "https://qyapi.weixin.qq.com").rstrip("/")

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.WECOM_CORP_ID and settings.WECOM_CORP_SECRET)

    def _ensure_configured(self) -> None:
        if not self.corp_id or not self.corp_secret:
            raise ValueError(
                "企业微信未配置，请在环境变量中设置 WECOM_CORP_ID 与 WECOM_CORP_SECRET"
            )

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        self._ensure_configured()
        now = time.time()
        with self._token_lock:
            if (
                not force_refresh
                and self._cached_token
                and now < self._token_expires_at - 60
            ):
                return self._cached_token

            url = f"{self.api_base}/cgi-bin/gettoken"
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    url,
                    params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
                )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                raise WeComError(data.get("errcode", -1), data.get("errmsg", "获取 access_token 失败"))

            token = data["access_token"]
            expires_in = int(data.get("expires_in", 7200))
            WeComClient._cached_token = token
            WeComClient._token_expires_at = now + expires_in
            return token

    def post(self, path: str, body: dict[str, Any] | None = None, *, retry: bool = True) -> dict[str, Any]:
        token = self.get_access_token()
        url = f"{self.api_base}{path}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, params={"access_token": token}, json=body or {})
        data = resp.json()
        errcode = data.get("errcode", 0)
        if errcode == 40014 and retry:
            token = self.get_access_token(force_refresh=True)
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, params={"access_token": token}, json=body or {})
            data = resp.json()
            errcode = data.get("errcode", 0)
        if errcode != 0:
            raise WeComError(errcode, data.get("errmsg", "企业微信接口调用失败"))
        return data

    # ── 邮件 API（文档 path/97504, 97516, 97983）──

    def get_mail_list(
        self,
        begin_time: int,
        end_time: int,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "begin_time": begin_time,
            "end_time": end_time,
            "limit": min(max(limit, 1), 1000),
        }
        if cursor:
            body["cursor"] = cursor
        return self.post("/cgi-bin/exmail/app/get_mail_list", body)

    def read_mail(self, mail_id: str) -> dict[str, Any]:
        return self.post("/cgi-bin/exmail/app/read_mail", {"mail_id": mail_id})

    def compose_send(
        self,
        *,
        to_emails: list[str] | None = None,
        to_userids: list[str] | None = None,
        cc_emails: list[str] | None = None,
        cc_userids: list[str] | None = None,
        bcc_emails: list[str] | None = None,
        bcc_userids: list[str] | None = None,
        subject: str,
        content: str,
        content_type: str = "html",
    ) -> dict[str, Any]:
        to_emails = [e.strip() for e in (to_emails or []) if e and e.strip()]
        to_userids = [u.strip() for u in (to_userids or []) if u and u.strip()]
        if not to_emails and not to_userids:
            raise ValueError("收件人不能为空")

        body: dict[str, Any] = {
            "to": {"emails": to_emails, "userids": to_userids},
            "subject": subject,
            "content": content,
            "content_type": content_type,
        }
        if cc_emails or cc_userids:
            body["cc"] = {
                "emails": [e.strip() for e in (cc_emails or []) if e and e.strip()],
                "userids": [u.strip() for u in (cc_userids or []) if u and u.strip()],
            }
        if bcc_emails or bcc_userids:
            body["bcc"] = {
                "emails": [e.strip() for e in (bcc_emails or []) if e and e.strip()],
                "userids": [u.strip() for u in (bcc_userids or []) if u and u.strip()],
            }
        return self.post("/cgi-bin/exmail/app/compose_send", body)

    # ── 审批 API（文档 path/91982, 91853, 91816, 91983）──

    def get_template_detail(self, template_id: str) -> dict[str, Any]:
        return self.post("/cgi-bin/oa/gettemplatedetail", {"template_id": template_id})

    def get_approval_info(
        self,
        starttime: int,
        endtime: int,
        *,
        new_cursor: str = "",
        size: int = 100,
        filters: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "starttime": str(starttime),
            "endtime": str(endtime),
            "new_cursor": new_cursor or "",
            "size": min(max(size, 1), 100),
        }
        if filters:
            body["filters"] = filters
        return self.post("/cgi-bin/oa/getapprovalinfo", body)

    def get_approval_detail(self, sp_no: str) -> dict[str, Any]:
        return self.post("/cgi-bin/oa/getapprovaldetail", {"sp_no": sp_no})

    def apply_event(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("/cgi-bin/oa/applyevent", body)
