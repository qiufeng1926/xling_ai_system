"""飞书流式语音识别（tenant_access_token）"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from config.config import feishu_api_base
from integrations.feishu.client import FeishuClient
from integrations.feishu.errors import FeishuError


def stream_recognize(
    *,
    stream_id: str,
    sequence_id: int,
    action: int,
    pcm_bytes: bytes,
) -> dict[str, Any]:
    """
    action: 1 首包, 0 中间包, 2 正常结束, 3 中断
    """
    client = FeishuClient()
    token = client.get_tenant_access_token()
    url = f"{feishu_api_base.rstrip('/')}/open-apis/speech_to_text/v1/speech/stream_recognize"
    payload = {
        "speech": {"speech": base64.b64encode(pcm_bytes).decode("ascii")},
        "config": {
            "stream_id": stream_id,
            "sequence_id": sequence_id,
            "action": action,
            "format": "pcm",
            "engine_type": "16k_auto",
        },
    }
    with httpx.Client(timeout=30.0) as http:
        resp = http.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
    data = resp.json()
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or "飞书语音识别失败"),
        )
    return data.get("data") or {}
