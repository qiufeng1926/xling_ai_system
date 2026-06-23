"""飞书云文档正文导出（docx raw_content）"""

from __future__ import annotations

from typing import Any

import httpx

from config.config import feishu_api_base
from integrations.feishu.errors import FeishuError
from integrations.feishu.file_types import build_file_url


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def _check(data: dict[str, Any], *, action: str) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or f"{action}失败"),
        )
    return data.get("data") or {}


def _export_docx(user_access_token: str, document_id: str) -> dict[str, str]:
    base = feishu_api_base.rstrip("/")
    meta_url = f"{base}/open-apis/docx/v1/documents/{document_id}"
    raw_url = f"{base}/open-apis/docx/v1/documents/{document_id}/raw_content"

    with httpx.Client(timeout=30.0) as client:
        meta_resp = client.get(meta_url, headers=_headers(user_access_token))
        meta = _check(meta_resp.json(), action="获取文档元数据")
        document = meta.get("document") or {}
        title = (document.get("title") or "").strip()
        url = (document.get("url") or "").strip() or build_file_url("docx", document_id)

        raw_resp = client.get(raw_url, headers=_headers(user_access_token), params={"lang": 0})
        raw = _check(raw_resp.json(), action="导出文档正文")
        content = (raw.get("content") or "").strip()

    return {"title": title, "content": content, "url": url}


def export_document_text(user_access_token: str, *, token: str, file_type: str) -> dict[str, str]:
    """按类型导出可读文本；目前 docx 支持正文，其它类型仅返回链接与标题占位。"""
    normalized = (file_type or "docx").strip().lower()
    doc_token = (token or "").strip()
    if not doc_token:
        raise ValueError("缺少文档 token")

    if normalized in {"docx", "doc"}:
        return _export_docx(user_access_token, doc_token)

    return {
        "title": "",
        "content": "",
        "url": build_file_url(normalized, doc_token),
    }
