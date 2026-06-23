"""飞书开放平台 API 客户端（tenant_access_token 缓存）"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from config.config import feishu_api_base, feishu_app_id, feishu_app_secret
from integrations.feishu.errors import FeishuError


class FeishuClient:
    _token_lock = threading.Lock()
    _cached_token: str | None = None
    _token_expires_at: float = 0.0

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        api_base: str | None = None,
    ):
        self.app_id = (app_id or feishu_app_id or "").strip()
        self.app_secret = (app_secret or feishu_app_secret or "").strip()
        self.api_base = (api_base or feishu_api_base or "https://open.feishu.cn").rstrip("/")

    @classmethod
    def is_configured(cls) -> bool:
        return bool(feishu_app_id and feishu_app_secret)

    def _ensure_configured(self) -> None:
        if not self.app_id or not self.app_secret:
            raise ValueError(
                "飞书未配置，请在环境变量中设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET"
            )

    def get_tenant_access_token(self, *, force_refresh: bool = False) -> str:
        self._ensure_configured()
        now = time.time()
        with self._token_lock:
            if (
                not force_refresh
                and self._cached_token
                and now < self._token_expires_at - 60
            ):
                return self._cached_token

            url = f"{self.api_base}/open-apis/auth/v3/tenant_access_token/internal"
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    url,
                    json={"app_id": self.app_id, "app_secret": self.app_secret},
                )
            data = resp.json()
            if data.get("code", 0) != 0:
                raise FeishuError(
                    int(data.get("code", -1)),
                    str(data.get("msg", "获取 tenant_access_token 失败")),
                )

            token = data["tenant_access_token"]
            expires_in = int(data.get("expire", 7200))
            FeishuClient._cached_token = token
            FeishuClient._token_expires_at = now + expires_in
            return token

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        url = f"{self.api_base}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, headers=headers, json=json, params=params)
        data = resp.json()
        code = data.get("code", 0)
        if code in (99991663, 99991668) and retry:
            token = self.get_tenant_access_token(force_refresh=True)
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=30.0) as client:
                resp = client.request(method, url, headers=headers, json=json, params=params)
            data = resp.json()
            code = data.get("code", 0)
        if code != 0:
            raise FeishuError(int(code), str(data.get("msg", "飞书 API 请求失败")))
        return data
