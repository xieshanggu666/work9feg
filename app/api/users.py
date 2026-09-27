from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.schemas.common import APIResponse, PageResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("/me", response_model=APIResponse[UserResponse])
def get_me(user: User = Depends(get_current_user)):
    return APIResponse(data=UserResponse.model_validate(user))


@router.get("", response_model=APIResponse[PageResponse[UserResponse]])
def list_users(page: int = 1, page_size: int = 10, role: str | None = None,
               keyword: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(require_roles("admin", "teacher"))):
    total, items = user_service.list_users(db, page, page_size, role, keyword)
    return APIResponse(data=PageResponse(
        total=total, page=page, page_size=page_size,
        items=[UserResponse.model_validate(u) for u in items],
    ))


@router.post("", response_model=APIResponse[UserResponse])
def create_user(data: UserCreate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    if user_service.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    new_user = user_service.create_user(db, data)
    return APIResponse(data=UserResponse.model_validate(new_user))


@router.put("/{user_id}", response_model=APIResponse[UserResponse])
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    target = user_service.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    updated = user_service.update_user(db, target, data)
    return APIResponse(data=UserResponse.model_validate(updated))
