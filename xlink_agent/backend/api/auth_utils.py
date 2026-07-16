"""认证工具：JWT 与 FastAPI 依赖"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.portal_auth import PortalUser, resolve_user_from_payload
from config.config import jwt_secret

security = HTTPBearer(auto_error=False)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的登录凭证（请确认 xlink_agent 的 JWT_SECRET 与门户 SECRET_KEY 一致）",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> PortalUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    token = credentials.credentials
    payload = decode_access_token(token)
    user = resolve_user_from_payload(payload, bearer_token=token)
    if not user or user.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def get_super_admin(user: PortalUser = Depends(get_current_user)) -> PortalUser:
    if not user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超管权限")
    return user


def require_user_id(user: PortalUser) -> int:
    if user.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少用户 ID")
    return int(user.user_id)
