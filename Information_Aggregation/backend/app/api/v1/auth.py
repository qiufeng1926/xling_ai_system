from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DbSession, get_current_user
from app.config import settings
from app.models import User
from app.schemas import (
    FeishuBindRequest,
    FeishuBindStatus,
    FeishuTokenBundle,
    FeishuTokenBundleRequest,
    FeishuTokenBundleUpdateRequest,
    ResponseBase,
    Token,
    UserInfo,
    UserRegister,
)
from app.services.user_service import UserService
from app.utils.access_control import normalize_role
from app.utils.rate_limit import check_login_rate_limit, clear_login_attempts, record_login_failure
from app.utils.security import create_access_token, verify_password
from app.utils.user_permissions import effective_permissions

router = APIRouter(prefix="/auth", tags=["认证"])


def _issue_portal_token(user: User) -> ResponseBase[Token]:
    perms = effective_permissions(user)
    token = create_access_token(
        subject=user.username,
        user_id=user.id,
        role=normalize_role(user.role),
        nickname=user.nickname or user.username,
        permissions=perms,
    )
    return ResponseBase(data=Token(access_token=token))


@router.get("/feishu/status", response_model=ResponseBase[FeishuBindStatus])
def feishu_bind_status(current_user: User = Depends(get_current_user)):
    """当前 xlink 登录用户各自的飞书绑定状态"""
    data = UserService.get_feishu_bind_status(current_user)
    return ResponseBase(data=FeishuBindStatus(**data))


@router.post("/feishu/unbind", response_model=ResponseBase[dict])
def feishu_unbind(db: DbSession, current_user: User = Depends(get_current_user)):
    """解除当前 xlink 用户与飞书的绑定（不影响其他用户）"""
    try:
        UserService.unbind_feishu(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data={"bound": False}, message="已解除飞书绑定")


@router.post("/feishu/bind", response_model=ResponseBase[dict])
def feishu_bind(
    db: DbSession,
    data: FeishuBindRequest,
    service_key: str | None = Header(default=None, alias="X-Flybook-Service-Key"),
):
    """飞书 OAuth 完成后由 flybook 服务调用，绑定到指定门户用户"""
    expected = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not expected or service_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的服务密钥")

    try:
        UserService.bind_feishu_to_user(
            db,
            user_id=data.user_id,
            open_id=data.open_id,
            union_id=data.union_id,
            name=data.name,
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            token_expires_at=data.token_expires_at,
            oauth_scope=data.oauth_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ResponseBase(data={"bound": True}, message="飞书绑定成功")


@router.post("/feishu/token-bundle", response_model=ResponseBase[FeishuTokenBundle])
def feishu_token_bundle(
    db: DbSession,
    data: FeishuTokenBundleRequest,
    service_key: str | None = Header(default=None, alias="X-Flybook-Service-Key"),
):
    """flybook 内部：读取用户飞书 token"""
    expected = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not expected or service_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的服务密钥")
    try:
        bundle = UserService.get_feishu_token_bundle(db, data.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=FeishuTokenBundle(**bundle))


@router.post("/feishu/token-bundle/update", response_model=ResponseBase[dict])
def feishu_token_bundle_update(
    db: DbSession,
    data: FeishuTokenBundleUpdateRequest,
    service_key: str | None = Header(default=None, alias="X-Flybook-Service-Key"),
):
    """flybook 内部：刷新后写回用户飞书 token"""
    expected = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not expected or service_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的服务密钥")
    try:
        UserService.update_feishu_tokens(
            db,
            user_id=data.user_id,
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            token_expires_at=data.token_expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data={"updated": True})


@router.post("/login", response_model=ResponseBase[Token])
def login(db: DbSession, request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    check_login_rate_limit(request)

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        record_login_failure(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != 1:
        record_login_failure(request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    clear_login_attempts(request)
    return _issue_portal_token(user)


@router.post("/register", response_model=ResponseBase[Token])
def register(db: DbSession, request: Request, data: UserRegister):
    check_login_rate_limit(request)

    try:
        user = UserService.register_user(db, data)
    except ValueError as exc:
        record_login_failure(request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    clear_login_attempts(request)
    return _issue_portal_token(user)


@router.get("/me", response_model=ResponseBase[UserInfo])
def get_me(current_user: User = Depends(get_current_user)):
    perms = effective_permissions(current_user)
    return ResponseBase(
        data=UserInfo(
            id=current_user.id,
            username=current_user.username,
            nickname=current_user.nickname,
            role=normalize_role(current_user.role),
            view_library=perms["view_library"],
            permissions=perms,
        )
    )
