from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)
    real_name: str = Field(min_length=1, max_length=50)
    role: str = "student"


class UserLogin(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    real_name: str | None = None
    password: str | None = None
    status: int | None = None


class UserResponse(ORMModel):
    id: int
    username: str
    email: str
    real_name: str
    role: str
    status: int
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
