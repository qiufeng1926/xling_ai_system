"""将远程设备复制的 Cookie 转为 Playwright storage_state 格式"""

from __future__ import annotations

import json
import re
from typing import Any

PLATFORM_COOKIE_CONFIG: dict[str, dict[str, Any]] = {
    "douyin": {
        "primary_domain": ".xingtu.cn",
        "domains": [".xingtu.cn", ".douyin.com", ".bytedance.com"],
        "host_keywords": ("xingtu", "douyin", "bytedance"),
    },
    "xiaohongshu": {
        "primary_domain": ".xiaohongshu.com",
        "domains": [".xiaohongshu.com", ".pgy.xiaohongshu.com"],
        "host_keywords": ("xiaohongshu", "xhs"),
    },
}


def build_storage_state(platform: str, content: str) -> dict[str, Any]:
    content = content.strip()
    if not content:
        raise ValueError("Cookie 内容不能为空")

    cookies = _parse_any_format(content, platform)
    if not cookies:
        raise ValueError("未能解析出有效 Cookie，请检查复制内容")

    normalized = [_normalize_cookie(item, platform) for item in cookies]
    normalized = [c for c in normalized if c.get("name") and c.get("value") is not None]
    if not normalized:
        raise ValueError("Cookie 格式无效")

    return {"cookies": normalized, "origins": []}


def _parse_any_format(content: str, platform: str) -> list[dict[str, Any]]:
    if content.startswith("{"):
        data = json.loads(content)
        if isinstance(data, dict) and isinstance(data.get("cookies"), list):
            return data["cookies"]
        if isinstance(data, dict):
            raise ValueError("JSON 对象需包含 cookies 数组")
        raise ValueError("不支持的 JSON 对象格式")

    if content.startswith("["):
        data = json.loads(content)
        if isinstance(data, list):
            return data
        raise ValueError("JSON 数组格式不正确")

    return _parse_cookie_header(content, platform)


def _parse_cookie_header(header: str, platform: str) -> list[dict[str, Any]]:
    header = header.strip()
    if header.lower().startswith("cookie:"):
        header = header.split(":", 1)[1].strip()

    cfg = PLATFORM_COOKIE_CONFIG[platform]
    cookies: list[dict[str, Any]] = []
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": cfg["primary_domain"],
            }
        )
    return cookies


def _normalize_cookie(raw: Any, platform: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Cookie 项必须是对象")

    cfg = PLATFORM_COOKIE_CONFIG[platform]
    name = str(raw.get("name") or "").strip()
    value = raw.get("value")
    if value is None:
        value = ""
    value = str(value)

    domain = str(raw.get("domain") or cfg["primary_domain"]).strip()
    if domain and not domain.startswith(".") and "." in domain:
        domain = f".{domain.lstrip('.')}"

    path = str(raw.get("path") or "/")
    expires = raw.get("expires", -1)
    try:
        expires = float(expires) if expires not in (None, "") else -1
    except (TypeError, ValueError):
        expires = -1

    http_only = bool(raw.get("httpOnly", raw.get("http_only", False)))
    secure = bool(raw.get("secure", True))
    same_site = raw.get("sameSite") or raw.get("same_site") or "Lax"
    if same_site not in ("Strict", "Lax", "None"):
        same_site = "Lax"

    return {
        "name": name,
        "value": value,
        "domain": domain or cfg["primary_domain"],
        "path": path or "/",
        "expires": expires,
        "httpOnly": http_only,
        "secure": secure,
        "sameSite": same_site,
    }


def storage_state_to_bytes(state: dict[str, Any]) -> bytes:
    return json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
