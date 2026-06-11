"""
认证工具：JWT 与 FastAPI 依赖
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.portal_auth import resolve_user_from_payload
from config.config import jwt_secret, jwt_expire_hours
from db.models import User
from db.session import SessionFactory

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=jwt_expire_hours)
    payload = {
        'sub': str(user_id),
        'username': username,
        'role': role,
        'exp': expire,
    }
    return jwt.encode(payload, jwt_secret, algorithm='HS256')


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='登录已过期，请重新登录')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='无效的登录凭证')


def get_db():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def _user_from_payload(db: Session, payload: dict) -> User:
    user = resolve_user_from_payload(db, payload)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='用户不存在')
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='请先登录')
    payload = decode_access_token(credentials.credentials)
    return _user_from_payload(db, payload)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except HTTPException:
        return None
    return resolve_user_from_payload(db, payload)


def get_user_from_token(token: str, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    return resolve_user_from_payload(db, payload)
