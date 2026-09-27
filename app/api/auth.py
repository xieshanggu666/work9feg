from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.user import UserLogin, TokenResponse, UserResponse
from app.schemas.common import APIResponse
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer(auto_error=False)


@router.post("/login", response_model=APIResponse[TokenResponse])
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = user_service.authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = create_access_token(user.id, user.role)
    return APIResponse(data=TokenResponse(
        access_token=token, user=UserResponse.model_validate(user)
    ))


@router.post("/register", response_model=APIResponse[UserResponse])
def register(data: UserLogin, db: Session = Depends(get_db)):
    """简化注册：仅用于演示，实际注册应使用完整 UserCreate"""
    if user_service.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    from app.schemas.user import UserCreate
    user = user_service.create_user(db, UserCreate(
        username=data.username,
        email=f"{data.username}@example.com",
        password=data.password,
        real_name=data.username,
        role="student",
    ))
    return APIResponse(data=UserResponse.model_validate(user))
