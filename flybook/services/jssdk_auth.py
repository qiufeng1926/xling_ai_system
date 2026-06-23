"""飞书网页组件 SDK 鉴权（jsapi_ticket + SHA1 签名）"""

from __future__ import annotations

import hashlib
import secrets
import time

import httpx

from config.config import feishu_app_id, feishu_api_base
from integrations.feishu.errors import FeishuError


def get_jsapi_ticket(user_access_token: str) -> str:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/jssdk/ticket/get"
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            url,
            headers={"Authorization": f"Bearer {user_access_token}"},
            json={},
        )
    data = resp.json()
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or "获取 jsapi_ticket 失败"),
        )
    ticket = (data.get("data") or {}).get("ticket")
    if not ticket:
        raise FeishuError(-1, "飞书未返回 jsapi_ticket")
    return ticket


def build_component_auth(*, user_access_token: str, open_id: str, page_url: str) -> dict:
    """生成云文档组件 DocComponentSdk 所需 auth 参数"""
    ticket = get_jsapi_ticket(user_access_token)
    nonce_str = secrets.token_urlsafe(16)
    timestamp = int(time.time() * 1000)
    sign_url = page_url.split("#")[0].split("?")[0]
    raw = f"jsapi_ticket={ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={sign_url}"
    signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return {
        "appId": feishu_app_id,
        "openId": open_id,
        "signature": signature,
        "timestamp": timestamp,
        "nonceStr": nonce_str,
        "url": sign_url,
        "jsApiList": ["DocsComponent"],
    }
