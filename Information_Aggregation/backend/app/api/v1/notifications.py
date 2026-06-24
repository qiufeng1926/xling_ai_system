import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.notification_hub import notification_hub
from app.utils.security import decode_access_token

router = APIRouter(prefix="/notifications", tags=["通知"])


def _resolve_user(token: str) -> int:
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")
    db: Session = SessionLocal()
    try:
        from app.models import User

        user = db.query(User).filter(User.username == username, User.status == 1).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
        return user.id
    finally:
        db.close()


@router.get("/stream")
async def notification_stream(token: str = Query(..., description="JWT，用于 EventSource 鉴权")):
    user_id = _resolve_user(token)

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
