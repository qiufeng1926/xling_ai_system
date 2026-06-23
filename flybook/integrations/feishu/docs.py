"""飞书云文档 Drive / Docx API（用户身份）"""

from __future__ import annotations

from typing import Any

import httpx

from config.config import feishu_api_base, feishu_doc_base_url
from integrations.feishu.errors import FeishuError


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def _check(data: dict[str, Any], *, action: str) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or f"{action}失败"),
        )
    return data.get("data") or {}


def get_root_folder_meta(user_access_token: str) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/explorer/v2/root_folder/meta"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, headers=_headers(user_access_token))
    return _check(resp.json(), action="获取根目录")


def list_files(
    user_access_token: str,
    *,
    folder_token: str = "",
    page_size: int = 50,
    page_token: str = "",
) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/v1/files"
    params: dict[str, Any] = {"page_size": page_size}
    if folder_token:
        params["folder_token"] = folder_token
    if page_token:
        params["page_token"] = page_token
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, headers=_headers(user_access_token), params=params)
    return _check(resp.json(), action="获取文件列表")


def create_document(
    user_access_token: str,
    *,
    title: str,
    folder_token: str = "",
) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/docx/v1/documents"
    body: dict[str, Any] = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), json=body)
    data = _check(resp.json(), action="创建文档")
    document = data.get("document") or {}
    doc_id = document.get("document_id") or ""
    if doc_id:
        document["url"] = build_doc_url(doc_id, document.get("url"))
    return document


def build_doc_url(document_id: str, fallback_url: str | None = None) -> str:
    if fallback_url:
        return fallback_url
    base = (feishu_doc_base_url or "https://bytedance.feishu.cn").rstrip("/")
    return f"{base}/docx/{document_id}"
