from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.auth_utils import decode_access_token
from api.portal_auth import resolve_user_from_payload
from browser.pool import browser_pool

router = APIRouter(tags=["browser-ws"])


def _auth_user(token: str):
    payload = decode_access_token(token)
    user = resolve_user_from_payload(payload, bearer_token=token)
    if not user or user.user_id is None:
        raise ValueError("无效用户")
    return user


@router.websocket("/v1/ws/browser")
async def ws_browser(websocket: WebSocket, token: str = Query(...)):
    try:
        user = _auth_user(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    uid = int(user.user_id)
    try:
        # 首包：不强制启动 Chromium，避免 Windows 下无操作就炸
        peek = await browser_pool.peek(uid)
        await websocket.send_json(
            {
                "type": "browser.frame",
                "url": peek.get("url") or "about:blank",
                "frame": peek.get("frame"),
                "ready": bool(peek.get("ready")),
            }
        )
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
            except asyncio.TimeoutError:
                peek = await browser_pool.peek(uid)
                await websocket.send_json(
                    {
                        "type": "browser.frame",
                        "url": peek.get("url") or "about:blank",
                        "frame": peek.get("frame"),
                        "ready": bool(peek.get("ready")),
                    }
                )
                continue
            except WebSocketDisconnect:
                break

            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if mtype == "navigate":
                url = msg.get("url") or ""
                try:
                    result = await browser_pool.navigate(uid, url)
                    await websocket.send_json(
                        {
                            "type": "browser.frame",
                            "url": result.get("url"),
                            "frame": result.get("frame"),
                            "ready": True,
                        }
                    )
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                continue
            if mtype == "screenshot":
                try:
                    result = await browser_pool.screenshot(uid)
                    await websocket.send_json(
                        {
                            "type": "browser.frame",
                            "url": result.get("url"),
                            "frame": result.get("frame"),
                            "ready": True,
                        }
                    )
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
