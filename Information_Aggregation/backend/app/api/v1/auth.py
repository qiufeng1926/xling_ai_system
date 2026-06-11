from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import DbSession, get_current_user
from app.models import User
from app.schemas import ResponseBase, Token, UserInfo, UserRegister
from app.services.user_service import UserService
from app.utils.access_control import normalize_role
from app.utils.rate_limit import check_login_rate_limit, clear_login_attempts, record_login_failure
from app.utils.security import create_access_token, verify_password
from app.utils.user_permissions import effective_permissions

router = APIRouter(prefix="/auth", tags=["认证"])


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
    perms = effective_permissions(user)
    token = create_access_token(
        subject=user.username,
        user_id=user.id,
        role=normalize_role(user.role),
        nickname=user.nickname or user.username,
        permissions=perms,
    )
    return ResponseBase(data=Token(access_token=token))


@router.post("/register", response_model=ResponseBase[Token])
def register(db: DbSession, request: Request, data: UserRegister):
    check_login_rate_limit(request)

    try:
        user = UserService.register_user(db, data)
    except ValueError as exc:
        record_login_failure(request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    clear_login_attempts(request)
    perms = effective_permissions(user)
    token = create_access_token(
        subject=user.username,
        user_id=user.id,
        role=normalize_role(user.role),
        nickname=user.nickname or user.username,
        permissions=perms,
    )
    return ResponseBase(data=Token(access_token=token), message="注册成功")


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
