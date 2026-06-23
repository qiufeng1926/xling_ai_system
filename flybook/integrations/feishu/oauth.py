"""飞书网页应用 OAuth 2.0（授权码模式）"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from config.config import (
    feishu_api_base,
    feishu_app_id,
    feishu_app_secret,
    feishu_oauth_redirect_uri,
    feishu_oauth_scope,
)
from integrations.feishu.errors import FeishuError

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = f"{feishu_api_base.rstrip('/')}/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = f"{feishu_api_base.rstrip('/')}/open-apis/authen/v1/user_info"


@dataclass
class FeishuTokenPair:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None = None


@dataclass
class FeishuUserInfo:
    open_id: str
    union_id: str | None
    name: str
    avatar_url: str | None = None
    email: str | None = None
    mobile: str | None = None
    tenant_key: str | None = None


def build_authorize_url(*, state: str) -> str:
    if not feishu_app_id or not feishu_oauth_redirect_uri:
        raise ValueError("飞书 OAuth 未配置 FEISHU_APP_ID 或 FEISHU_OAUTH_REDIRECT_URI")
    params = {
        "client_id": feishu_app_id,
        "response_type": "code",
        "redirect_uri": feishu_oauth_redirect_uri,
        "state": state,
    }
    scope = (feishu_oauth_scope or "offline_access").strip()
    if scope:
        params["scope"] = scope
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> FeishuTokenPair:
    if not feishu_app_id or not feishu_app_secret:
        raise ValueError("飞书未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
    body = {
        "grant_type": "authorization_code",
        "client_id": feishu_app_id,
        "client_secret": feishu_app_secret,
        "code": code,
        "redirect_uri": feishu_oauth_redirect_uri,
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            FEISHU_TOKEN_URL,
            json=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    data = resp.json()
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("error_description") or data.get("msg") or "获取 user_access_token 失败"),
        )
    token = data.get("access_token")
    if not token:
        raise FeishuError(-1, "飞书未返回 access_token")
    return FeishuTokenPair(
        access_token=token,
        refresh_token=(data.get("refresh_token") or "").strip() or None,
        expires_in=int(data.get("expires_in") or 7200),
        scope=(data.get("scope") or "").strip() or None,
    )


def refresh_user_access_token(refresh_token: str) -> FeishuTokenPair:
    if not feishu_app_id or not feishu_app_secret:
        raise ValueError("飞书未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
    body = {
        "grant_type": "refresh_token",
        "client_id": feishu_app_id,
        "client_secret": feishu_app_secret,
        "refresh_token": refresh_token,
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            FEISHU_TOKEN_URL,
            json=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    data = resp.json()
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("error_description") or data.get("msg") or "刷新 user_access_token 失败"),
        )
    token = data.get("access_token")
    if not token:
        raise FeishuError(-1, "飞书未返回 access_token")
    return FeishuTokenPair(
        access_token=token,
        refresh_token=(data.get("refresh_token") or refresh_token or "").strip() or None,
        expires_in=int(data.get("expires_in") or 7200),
        scope=(data.get("scope") or "").strip() or None,
    )


def exchange_code_for_user_access_token(code: str) -> str:
    """兼容旧调用"""
    return exchange_code_for_tokens(code).access_token


def fetch_user_info(user_access_token: str) -> FeishuUserInfo:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
    payload = resp.json()
    if payload.get("code", 0) != 0:
        raise FeishuError(
            int(payload.get("code", -1)),
            str(payload.get("msg") or "获取飞书用户信息失败"),
        )
    data = payload.get("data") or {}
    open_id = (data.get("open_id") or "").strip()
    if not open_id:
        raise FeishuError(-1, "飞书用户信息缺少 open_id")
    name = (data.get("name") or data.get("en_name") or open_id).strip()
    return FeishuUserInfo(
        open_id=open_id,
        union_id=(data.get("union_id") or "").strip() or None,
        name=name,
        avatar_url=(data.get("avatar_url") or "").strip() or None,
        email=(data.get("email") or data.get("enterprise_email") or "").strip() or None,
        mobile=(data.get("mobile") or "").strip() or None,
        tenant_key=(data.get("tenant_key") or "").strip() or None,
    )
