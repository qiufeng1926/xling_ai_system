"""可信门户 HTTP 客户端：直连 PORTAL_API_URL，不经公网 URL 守卫。"""

from __future__ import annotations

from typing import Any

import httpx

from config.config import portal_api_url
from tools.portal_context import get_portal_bearer
from utils.logger import get_logger

logger = get_logger("portal_influencer")


class PortalInfluencerClient:
    def __init__(self, bearer: str | None = None, *, timeout: float = 30.0) -> None:
        self.base = (portal_api_url or "").strip().rstrip("/")
        self.bearer = (bearer if bearer is not None else get_portal_bearer()) or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.bearer:
            return {}
        return {"Authorization": f"Bearer {self.bearer}"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.base:
            return {"ok": False, "error": "未配置 PORTAL_API_URL"}
        if not self.bearer:
            return {"ok": False, "error": "缺少门户登录令牌，无法访问达人库"}
        url = f"{self.base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                resp = await client.get(url, params=params or {}, headers=self._headers())
        except Exception as exc:
            logger.warning("portal GET failed %s: %s", path, exc)
            return {"ok": False, "error": f"门户请求失败: {exc}"}
        if resp.status_code == 401:
            return {"ok": False, "error": "门户鉴权失败（401），请重新登录"}
        if resp.status_code == 403:
            return {"ok": False, "error": "无权限访问达人库（403）"}
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = str(body.get("detail") or body.get("message") or "")[:200]
            except Exception:
                detail = (resp.text or "")[:200]
            return {"ok": False, "error": f"门户 HTTP {resp.status_code}: {detail or 'error'}"}
        try:
            body = resp.json()
        except Exception:
            return {"ok": False, "error": "门户返回非 JSON"}
        if isinstance(body, dict) and "code" in body and body.get("code") not in (0, "0", None):
            return {"ok": False, "error": str(body.get("message") or "业务错误"), "raw": body}
        data = body.get("data") if isinstance(body, dict) else body
        return {"ok": True, "data": data}
