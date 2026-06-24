"""调用 flybook 内部 API：全量镜像飞书文档"""

from __future__ import annotations

import httpx

from app.config import settings


class FlybookClientError(Exception):
    pass


def mirror_all_documents_for_user(user_id: int) -> dict:
    base = (settings.FLYBOOK_API_URL or "http://127.0.0.1:8002").rstrip("/")
    key = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not key:
        raise FlybookClientError("未配置 FLYBOOK_INTERNAL_KEY")

    url = f"{base}/api/flybook/internal/documents/mirror-all/{user_id}"
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(url, headers={"X-Flybook-Internal-Key": key})
    if resp.status_code != 200:
        raise FlybookClientError(resp.text[:300])
    return resp.json()
