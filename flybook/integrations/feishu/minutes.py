"""飞书妙记 API（用户身份）"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from config.config import feishu_api_base
from integrations.feishu.errors import FeishuError

_MINUTE_TOKEN_RE = re.compile(r"^[a-z0-9]{24}$", re.IGNORECASE)
_ARTIFACTS_POLL_INTERVAL = 2.0
_ARTIFACTS_POLL_TIMEOUT = 180.0


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def _check(data: dict[str, Any], *, action: str) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or f"{action}失败"),
        )
    return data.get("data") or {}


def extract_minute_token(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if _MINUTE_TOKEN_RE.match(raw):
        return raw
    path = urlparse(raw).path.rstrip("/")
    token = path.rsplit("/", 1)[-1] if path else raw
    return token if _MINUTE_TOKEN_RE.match(token) else ""


def search_minutes(
    user_access_token: str,
    *,
    query: str = "",
    page_size: int = 15,
    page_token: str = "",
) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/minutes/v1/minutes/search"
    params: dict[str, Any] = {"page_size": min(max(page_size, 1), 30)}
    if page_token:
        params["page_token"] = page_token
    body: dict[str, Any] = {}
    if query.strip():
        body["query"] = query.strip()[:50]
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), params=params, json=body)
    data = _check(resp.json(), action="搜索妙记")
    items = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        token = (item.get("token") or "").strip()
        meta = item.get("meta_data") or {}
        items.append(
            {
                "token": token,
                "title": (meta.get("description") or item.get("display_info") or "未命名妙记").strip(),
                "url": meta.get("app_link") or "",
                "cover": meta.get("avatar") or "",
                "display_info": item.get("display_info") or "",
            }
        )
    return {
        "items": items,
        "has_more": bool(data.get("has_more")),
        "page_token": data.get("page_token") or "",
        "total": int(data.get("total") or 0),
    }


def get_minute(user_access_token: str, minute_token: str) -> dict[str, Any]:
    token = extract_minute_token(minute_token)
    if not token:
        raise ValueError("无效的 minute_token")
    url = f"{feishu_api_base.rstrip('/')}/open-apis/minutes/v1/minutes/{token}"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, headers=_headers(user_access_token))
    data = _check(resp.json(), action="获取妙记信息")
    minute = data.get("minute") or {}
    return {
        "token": minute.get("token") or token,
        "title": minute.get("title") or "",
        "url": minute.get("url") or "",
        "cover": minute.get("cover") or "",
        "duration": minute.get("duration") or "",
        "create_time": minute.get("create_time") or "",
        "owner_id": minute.get("owner_id") or "",
    }


def get_minute_artifacts(user_access_token: str, minute_token: str) -> dict[str, Any]:
    token = extract_minute_token(minute_token)
    if not token:
        raise ValueError("无效的 minute_token")
    url = f"{feishu_api_base.rstrip('/')}/open-apis/minutes/v1/minutes/{token}/artifacts"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_headers(user_access_token))
    body = resp.json()
    code = int(body.get("code", 0))
    if code == 2091003:
        return {"ready": False, "status": "processing"}
    data = _check(body, action="获取妙记 AI 产物")
    chapters = []
    for ch in data.get("minute_chapters") or []:
        if not isinstance(ch, dict):
            continue
        chapters.append(
            {
                "title": ch.get("title") or "",
                "start_ms": ch.get("start_ms") or "",
                "stop_ms": ch.get("stop_ms") or "",
                "summary_content": ch.get("summary_content") or "",
            }
        )
    todos = []
    for td in data.get("minute_todos") or []:
        if not isinstance(td, dict):
            continue
        todos.append(
            {
                "content": td.get("content") or "",
                "assignees": td.get("assignees") or [],
            }
        )
    return {
        "ready": True,
        "summary": data.get("summary") or "",
        "chapters": chapters,
        "todos": todos,
    }


def wait_minute_artifacts(user_access_token: str, minute_token: str) -> dict[str, Any]:
    deadline = time.monotonic() + _ARTIFACTS_POLL_TIMEOUT
    last_error: FeishuError | None = None
    while time.monotonic() < deadline:
        try:
            result = get_minute_artifacts(user_access_token, minute_token)
            if result.get("ready"):
                return result
        except FeishuError as exc:
            if exc.code == 2091003:
                last_error = exc
            else:
                raise
        time.sleep(_ARTIFACTS_POLL_INTERVAL)
    if last_error:
        raise last_error
    raise FeishuError(-1, "妙记 AI 产物生成超时，请稍后在飞书中查看")


def create_minute_from_file_token(user_access_token: str, file_token: str) -> dict[str, Any]:
    file_token = (file_token or "").strip()
    if not file_token:
        raise ValueError("缺少 file_token")
    url = f"{feishu_api_base.rstrip('/')}/open-apis/minutes/v1/minutes/upload"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            url,
            headers={**_headers(user_access_token), "Content-Type": "application/json"},
            json={"file_token": file_token},
        )
    data = _check(resp.json(), action="创建妙记")
    minute_url = (data.get("minute_url") or "").strip()
    minute = data.get("minute") or {}
    token = (minute.get("token") or extract_minute_token(minute_url) or "").strip()
    if not token and minute_url:
        token = extract_minute_token(minute_url)
    if not token:
        raise FeishuError(-1, "飞书未返回妙记 token")
    return {
        "token": token,
        "url": minute.get("url") or minute_url,
        "title": minute.get("title") or "",
    }
