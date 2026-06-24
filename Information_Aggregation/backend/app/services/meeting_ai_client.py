"""调用 meeting_ai 内部离职交接 API"""

from __future__ import annotations

import httpx

from app.config import settings


class MeetingAiClientError(Exception):
    pass


def _base_url() -> str:
    return (settings.MEETING_AI_API_URL or "http://127.0.0.1:8001").rstrip("/")


def _internal_key() -> str:
    key = (settings.PORTAL_INTERNAL_KEY or settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not key:
        raise MeetingAiClientError("未配置 PORTAL_INTERNAL_KEY")
    return key


def offboard_user(
    *,
    departed_username: str,
    handover_username: str,
    offboarding_id: int,
) -> dict:
    url = f"{_base_url()}/api/internal/offboard"
    payload = {
        "departed_username": departed_username,
        "handover_username": handover_username,
        "offboarding_id": offboarding_id,
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            json=payload,
            headers={"X-Portal-Internal-Key": _internal_key()},
        )
    if resp.status_code != 200:
        detail = resp.text[:300]
        raise MeetingAiClientError(f"meeting_ai 交接失败: {detail}")
    body = resp.json()
    if not body.get("success"):
        raise MeetingAiClientError(body.get("message") or "meeting_ai 交接失败")
    return body.get("snapshot") or {}


def revert_offboard(snapshot: dict) -> None:
    if not snapshot:
        return
    url = f"{_base_url()}/api/internal/offboard/revert"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            json={"snapshot": snapshot},
            headers={"X-Portal-Internal-Key": _internal_key()},
        )
    if resp.status_code != 200:
        detail = resp.text[:300]
        raise MeetingAiClientError(f"meeting_ai 回滚失败: {detail}")
