import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.auth_utils import decode_access_token
from api.portal_auth import resolve_user_from_payload
from db.session import SessionFactory
from services.notification_hub import notification_hub

router = APIRouter()


def _resolve_user_id(token: str) -> int:
    payload = decode_access_token(token)
    db = SessionFactory()
    try:
        user = resolve_user_from_payload(db, payload)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
        return user.id
    finally:
        db.close()


@router.get("/notifications/stream")
async def notification_stream(token: str = Query(..., description="JWT，用于 EventSource 鉴权")):
    user_id = _resolve_user_id(token)

    async def event_generator():
        queue = await notification_hub.subscribe(user_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await notification_hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
