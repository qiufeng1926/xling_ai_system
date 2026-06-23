"""飞书云文档 Drive / 多类型创建 API（用户身份）"""

from __future__ import annotations

from typing import Any

import httpx

from config.config import feishu_api_base
from integrations.feishu.errors import FeishuError
from integrations.feishu.file_types import (
    CREATE_TYPE_LABELS,
    CREATE_TYPES,
    build_file_url,
)


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


def _normalize_created(
    *,
    file_type: str,
    token: str,
    title: str,
    url: str | None = None,
) -> dict[str, Any]:
    return {
        "type": file_type,
        "token": token,
        "title": title,
        "url": build_file_url(file_type, token, url),
        "embed_editable": file_type in {"docx", "doc"},
    }


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
    return _normalize_created(
        file_type="docx",
        token=doc_id,
        title=document.get("title") or title,
        url=document.get("url"),
    )


def create_spreadsheet(
    user_access_token: str,
    *,
    title: str,
    folder_token: str = "",
) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/sheets/v3/spreadsheets"
    body: dict[str, Any] = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), json=body)
    data = _check(resp.json(), action="创建表格")
    sheet = data.get("spreadsheet") or {}
    token = sheet.get("spreadsheet_token") or ""
    return _normalize_created(
        file_type="sheet",
        token=token,
        title=sheet.get("title") or title,
        url=sheet.get("url"),
    )


def create_bitable(
    user_access_token: str,
    *,
    title: str,
    folder_token: str = "",
) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/bitable/v1/apps"
    body: dict[str, Any] = {"name": title}
    if folder_token:
        body["folder_token"] = folder_token
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), json=body)
    data = _check(resp.json(), action="创建多维表格")
    app = data.get("app") or {}
    token = app.get("app_token") or app.get("token") or ""
    return _normalize_created(
        file_type="bitable",
        token=token,
        title=app.get("name") or title,
        url=app.get("url"),
    )


def _list_wiki_spaces(user_access_token: str) -> list[dict[str, Any]]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/wiki/v2/spaces"
    items: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(5):
        params: dict[str, Any] = {"page_size": 50}
        if page_token:
            params["page_token"] = page_token
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=_headers(user_access_token), params=params)
        data = _check(resp.json(), action="获取知识空间列表")
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token") or ""
        if not page_token:
            break
    return items


def _resolve_wiki_space_id(user_access_token: str) -> str:
    spaces = _list_wiki_spaces(user_access_token)
    if not spaces:
        raise FeishuError(-1, "未找到可用的知识空间，无法创建幻灯片/思维笔记")
    for space in spaces:
        if (space.get("space_type") or "").strip() == "my_library":
            space_id = (space.get("space_id") or "").strip()
            if space_id:
                return space_id
    space_id = (spaces[0].get("space_id") or "").strip()
    if not space_id:
        raise FeishuError(-1, "无法解析知识空间 ID")
    return space_id


def create_wiki_node(
    user_access_token: str,
    *,
    obj_type: str,
    title: str,
) -> dict[str, Any]:
    """在「我的文档库」知识空间创建 slides / mindnote 等节点"""
    if obj_type not in {"slides", "mindnote"}:
        raise ValueError(f"不支持通过知识库创建的类型: {obj_type}")
    space_id = _resolve_wiki_space_id(user_access_token)
    url = f"{feishu_api_base.rstrip('/')}/open-apis/wiki/v2/spaces/{space_id}/nodes"
    body = {
        "obj_type": obj_type,
        "title": title,
        "node_type": "origin",
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), json=body)
    data = _check(resp.json(), action=f"创建{CREATE_TYPE_LABELS.get(obj_type, obj_type)}")
    node = data.get("node") or {}
    token = (node.get("obj_token") or node.get("node_token") or "").strip()
    node_url = (node.get("url") or node.get("origin_url") or "").strip() or None
    return _normalize_created(
        file_type=obj_type,
        token=token,
        title=node.get("title") or title,
        url=node_url,
    )


def create_cloud_file(
    user_access_token: str,
    *,
    file_type: str,
    title: str,
    folder_token: str = "",
) -> dict[str, Any]:
    normalized = (file_type or "docx").strip().lower()
    if normalized not in CREATE_TYPES:
        raise ValueError(f"不支持的创建类型: {file_type}")
    if normalized == "docx":
        return create_document(user_access_token, title=title, folder_token=folder_token)
    if normalized == "sheet":
        return create_spreadsheet(user_access_token, title=title, folder_token=folder_token)
    if normalized == "bitable":
        return create_bitable(user_access_token, title=title, folder_token=folder_token)
    return create_wiki_node(user_access_token, obj_type=normalized, title=title)


def enrich_file_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return item
    file_type = (item.get("type") or "").strip()
    token = (item.get("token") or "").strip()
    if token and file_type:
        item["url"] = build_file_url(file_type, token, item.get("url"))
        item["embed_editable"] = file_type in {"docx", "doc"}
    return item


# 兼容旧调用
def build_doc_url(document_id: str, fallback_url: str | None = None) -> str:
    return build_file_url("docx", document_id, fallback_url)
