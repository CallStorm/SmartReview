from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import get_db
from app.deps import require_admin
from app.models.user import User, UserRole
from app.schemas.users import AdminUserCreate, AdminUserUpdate, UserListItem

router = APIRouter(prefix="/users", tags=["users"])


def _admin_count_excluding(db: Session, exclude_user_id: int | None) -> int:
    q = db.query(func.count(User.id)).filter(User.role == UserRole.admin)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return int(q.scalar() or 0)


@router.get("", response_model=list[UserListItem])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> User:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    if db.query(User).filter(User.phone == body.phone).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="手机号已存在")
    row = User(
        username=body.username,
        phone=body.phone,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{user_id}", response_model=UserListItem)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
) -> User:
    row = db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if body.username is not None and body.username != row.username:
        if db.query(User).filter(User.username == body.username, User.id != user_id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
        row.username = body.username

    if body.phone is not None and body.phone != row.phone:
        if db.query(User).filter(User.phone == body.phone, User.id != user_id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="手机号已存在")
        row.phone = body.phone

    if body.password is not None:
        row.password_hash = hash_password(body.password)

    if body.role is not None and body.role != row.role:
        if row.role == UserRole.admin and body.role == UserRole.user:
            if _admin_count_excluding(db, row.id) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="至少保留一名管理员，无法将该用户降为普通用户",
                )
        row.role = body.role

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录用户")

    row = db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if row.role == UserRole.admin and _admin_count_excluding(db, row.id) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少保留一名管理员，无法删除该用户",
        )

    db.delete(row)
    db.commit()
