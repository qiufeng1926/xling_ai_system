from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.integrations.wecom.client import WeComClient
from app.integrations.wecom.errors import translate_wecom_error

SP_STATUS_LABELS: dict[int, str] = {
    1: "审批中",
    2: "已通过",
    3: "已驳回",
    4: "已撤销",
    6: "通过后撤销",
    7: "已删除",
    10: "已支付",
}


class WeComApprovalService:
    @staticmethod
    def get_config() -> dict:
        corp_id = (WeComClient().corp_id or "") if WeComClient.is_configured() else ""
        masked = f"{corp_id[:4]}***{corp_id[-4:]}" if len(corp_id) > 8 else corp_id
        default_template_id = (settings.WECOM_DEFAULT_TEMPLATE_ID or "").strip() or None
        return {
            "configured": WeComClient.is_configured(),
            "corp_id": masked or None,
            "default_template_id": default_template_id,
        }

    @staticmethod
    def _resolve_time_range(days: int) -> tuple[int, int]:
        now = int(time.time())
        span = max(days, 1) * 86400
        return now - span, now

    @staticmethod
    def _status_label(status: int | None) -> str | None:
        if status is None:
            return None
        return SP_STATUS_LABELS.get(status, f"状态 {status}")

    @staticmethod
    def get_template_detail(template_id: str) -> dict:
        template_id = (template_id or "").strip()
        if not template_id:
            raise ValueError("template_id 不能为空")
        client = WeComClient()
        data = client.get_template_detail(template_id)
        return {
            "template_id": template_id,
            "template_names": data.get("template_names") or [],
            "template_content": data.get("template_content") or {},
        }

    @staticmethod
    def _build_filters(
        *,
        sp_status: str | None,
        template_id: str | None,
        creator: str | None,
    ) -> list[dict[str, str]] | None:
        filters: list[dict[str, str]] = []
        if template_id:
            filters.append({"key": "template_id", "value": template_id.strip()})
        if creator:
            filters.append({"key": "creator", "value": creator.strip()})
        if sp_status:
            filters.append({"key": "sp_status", "value": sp_status.strip()})
        return filters or None

    @staticmethod
    def list_approvals(
        *,
        days: int = 7,
        sp_status: str | None = None,
        template_id: str | None = None,
        creator: str | None = None,
        cursor: str | None = None,
        size: int = 50,
    ) -> dict:
        client = WeComClient()
        starttime, endtime = WeComApprovalService._resolve_time_range(days)
        data = client.get_approval_info(
            starttime,
            endtime,
            new_cursor=cursor or "",
            size=size,
            filters=WeComApprovalService._build_filters(
                sp_status=sp_status,
                template_id=template_id,
                creator=creator,
            ),
        )
        sp_no_list = [str(x) for x in (data.get("sp_no_list") or []) if x]
        next_cursor = data.get("new_next_cursor") or None
        items = [{"sp_no": sp_no} for sp_no in sp_no_list]
        return {
            "sp_list": items,
            "next_cursor": next_cursor,
            "has_more": bool(next_cursor),
        }

    @staticmethod
    def get_approval_detail(sp_no: str) -> dict:
        sp_no = (sp_no or "").strip()
        if not sp_no:
            raise ValueError("sp_no 不能为空")
        client = WeComClient()
        data = client.get_approval_detail(sp_no)
        info = data.get("info") or {}
        status = info.get("sp_status")
        return {
            "sp_no": sp_no,
            "sp_name": info.get("sp_name"),
            "sp_status": status,
            "sp_status_label": WeComApprovalService._status_label(status),
            "template_id": info.get("template_id"),
            "apply_time": info.get("apply_time"),
            "applyer": info.get("applyer"),
            "apply_data": info.get("apply_data"),
            "sp_record": info.get("sp_record"),
            "notifyer": info.get("notifyer"),
            "comments": info.get("comments"),
            "process_list": info.get("process_list"),
            "raw": info,
        }

    @staticmethod
    def submit_approval(
        *,
        template_id: str,
        creator_userid: str,
        use_template_approver: int,
        choose_department: int | None,
        contents: list[dict[str, Any]],
        summary_lines: list[str],
        process: dict[str, Any] | None,
    ) -> dict:
        template_id = (template_id or "").strip()
        creator_userid = (creator_userid or "").strip()
        if not template_id:
            raise ValueError("template_id 不能为空")
        if not creator_userid:
            raise ValueError("creator_userid 不能为空")
        if not contents:
            raise ValueError("审批表单 contents 不能为空")
        if use_template_approver == 0 and not process:
            raise ValueError("未使用模板审批流时，必须提供 process 节点")

        summary_list = []
        for line in summary_lines[:3]:
            text = (line or "").strip()
            if text:
                summary_list.append({"summary_info": [{"text": text[:20], "lang": "zh_CN"}]})
        if not summary_list:
            summary_list = [{"summary_info": [{"text": "系统提交审批", "lang": "zh_CN"}]}]

        body: dict[str, Any] = {
            "creator_userid": creator_userid,
            "template_id": template_id,
            "use_template_approver": use_template_approver,
            "apply_data": {"contents": contents},
            "summary_list": summary_list,
        }
        if choose_department is not None:
            body["choose_department"] = choose_department
        if use_template_approver == 0 and process:
            body["process"] = process

        client = WeComClient()
        data = client.apply_event(body)
        sp_no = str(data.get("sp_no") or "").strip()
        if not sp_no:
            raise ValueError("企业微信未返回审批单号 sp_no")
        return {"sp_no": sp_no}

    @staticmethod
    def translate_error(exc: Exception) -> str:
        return translate_wecom_error(exc)
