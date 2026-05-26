from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from .models import User, UserRole
from .security import get_current_user


def require_role(required_role: UserRole) -> Callable[[User], User]:
    def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role != required_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency


def list_all_users(db: Session, caller: User) -> list[User]:
    ensure_admin(caller)
    return list(db.exec(select(User).order_by(User.created_at, User.username)).all())


def change_user_role(db: Session, caller: User, target_id: str, role: UserRole) -> User:
    ensure_admin(caller)
    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == caller.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admins cannot change their own role")

    target.role = role
    target.updated_at = datetime.now(timezone.utc)
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def ensure_admin(caller: User) -> None:
    if caller.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
