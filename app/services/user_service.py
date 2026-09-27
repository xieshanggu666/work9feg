from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate, UserUpdate


def create_user(db: Session, data: UserCreate) -> User:
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        real_name=data.real_name,
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(
        or_(User.username == username, User.email == username)
    ).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if user.status != 1:
        return None
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session, page: int = 1, page_size: int = 10,
               role: str | None = None, keyword: str | None = None):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if keyword:
        query = query.filter(
            or_(User.username.contains(keyword), User.real_name.contains(keyword))
        )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    if data.email is not None:
        user.email = data.email
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.status is not None:
        user.status = data.status
    db.commit()
    db.refresh(user)
    return user
