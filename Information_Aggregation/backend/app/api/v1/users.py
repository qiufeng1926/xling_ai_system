from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, SuperAdminUser
from app.constants.roles import ROLE_LABELS
from app.schemas import PageResult, ResponseBase
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.user_service import UserService
from app.utils.access_control import normalize_role

router = APIRouter(prefix="/users", tags=["用户管理"])


def _user_out(user) -> UserOut:
    data = UserService.to_out(user)
    return UserOut(**data)


@router.get("", response_model=ResponseBase[PageResult[UserOut]])
def list_users(
    db: DbSession,
    _: SuperAdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = UserService.list_users(db, page, page_size)
    return ResponseBase(
        data=PageResult(
            items=[_user_out(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ResponseBase[UserOut], status_code=status.HTTP_201_CREATED)
def create_user(db: DbSession, operator: SuperAdminUser, data: UserCreate):
    try:
        user = UserService.create_user(db, data, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_user_out(user), message="用户已创建")


@router.put("/{user_id}", response_model=ResponseBase[UserOut])
def update_user(db: DbSession, operator: SuperAdminUser, user_id: int, data: UserUpdate):
    try:
        user = UserService.update_user(db, user_id, data, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_user_out(user), message="用户已更新")


@router.delete("/{user_id}", response_model=ResponseBase[None])
def delete_user(db: DbSession, operator: SuperAdminUser, user_id: int):
    try:
        UserService.delete_user(db, user_id, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(message="用户已删除")


@router.get("/roles", response_model=ResponseBase[list])
def list_roles(_: SuperAdminUser):
    return ResponseBase(
        data=[{"value": k, "label": v} for k, v in ROLE_LABELS.items() if k in ("super_admin", "admin", "user")]
    )


@router.get("/search", response_model=ResponseBase[list])
def search_users(
    db: DbSession,
    user: CurrentUser,
    keyword: str = Query("", max_length=64),
    limit: int = Query(10, ge=1, le=30),
):
    items = UserService.search_users(db, keyword, limit, exclude_username=user.username)
    return ResponseBase(
        data=[
            {
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname or u.username,
            }
            for u in items
        ]
    )
