from __future__ import annotations

import time

from app.integrations.qywechat.client import WeComClient
from app.integrations.qywechat.errors import translate_wecom_error
from app.integrations.qywechat.eml_parser import parse_mail_data


class WeComMailService:
    @staticmethod
    def get_config() -> dict:
        corp_id = (WeComClient().corp_id or "") if WeComClient.is_configured() else ""
        masked = f"{corp_id[:4]}***{corp_id[-4:]}" if len(corp_id) > 8 else corp_id
        return {
            "configured": WeComClient.is_configured(),
            "corp_id": masked or None,
        }

    @staticmethod
    def _resolve_time_range(begin_time: int | None, end_time: int | None, days: int) -> tuple[int, int]:
        now = int(time.time())
        if begin_time is not None and end_time is not None:
            return begin_time, end_time
        span = max(days, 1) * 86400
        return now - span, now

    @staticmethod
    def list_inbox(
        *,
        begin_time: int | None = None,
        end_time: int | None = None,
        cursor: str | None = None,
        limit: int = 50,
        days: int = 7,
    ) -> dict:
        client = WeComClient()
        bt, et = WeComMailService._resolve_time_range(begin_time, end_time, days)
        data = client.get_mail_list(bt, et, cursor=cursor, limit=limit)
        mail_list = [{"mail_id": item.get("mail_id", "")} for item in data.get("mail_list", [])]
        return {
            "mail_list": [m for m in mail_list if m["mail_id"]],
            "next_cursor": data.get("next_cursor") or None,
            "has_more": bool(data.get("has_more")),
        }

    @staticmethod
    def get_mail_detail(mail_id: str) -> dict:
        mail_id = (mail_id or "").strip()
        if not mail_id:
            raise ValueError("mail_id 不能为空")
        client = WeComClient()
        data = client.read_mail(mail_id)
        parsed = parse_mail_data(data.get("mail_data", "") or "")
        return {
            "mail_id": mail_id,
            "subject": parsed["subject"],
            "from_addr": parsed["from"],
            "to_addr": parsed["to"],
            "date": parsed["date"],
            "body_text": parsed["body_text"],
            "body_html": parsed["body_html"],
        }

    @staticmethod
    def send_mail(
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
    ) -> None:
        client = WeComClient()
        client.compose_send(
            to_emails=to_emails,
            to_userids=to_userids,
            cc_emails=cc_emails,
            cc_userids=cc_userids,
            bcc_emails=bcc_emails,
            bcc_userids=bcc_userids,
            subject=subject,
            content=content,
            content_type=content_type,
        )

    @staticmethod
    def translate_error(exc: Exception) -> str:
        return translate_wecom_error(exc)
