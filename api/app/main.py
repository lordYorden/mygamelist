from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db, init_db
from .models import User, UserRole
from .schemas import RegisterRequest, TokenRequest, TokenResponse, UserResponse
from .security import create_access_token, get_current_user, get_user_by_identifier, hash_password, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="MyGameList API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> User:
    username = request.username.strip()
    email = request.email.lower()

    existing = db.scalar(select(User).where(or_(User.username == username, User.email == email)))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    with db.begin_nested():
        user_count = db.scalar(select(func.count(User.id))) or 0
        role = UserRole.ADMIN if user_count == 0 else UserRole.GAMER
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(request.password),
            display_name=request.display_name.strip() if request.display_name else None,
            role=role,
        )
        db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists") from exc

    db.refresh(user)
    return user


@app.post("/api/auth/token", response_model=TokenResponse)
def issue_token(
    request: TokenRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = get_user_by_identifier(db, request.username)
    if user is None or not user.is_active or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token, expires_in = create_access_token(user, settings)
    return TokenResponse(accessToken=access_token, expiresIn=expires_in)


@app.get("/api/me", response_model=UserResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@app.delete("/api/game-entries/{entry_id}")
def delete_game_entry(entry_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> dict[str, str | bool]:
    return {
        "success": True,
        "message": f"Protected delete pattern accepted for entry {entry_id} by {current_user.username}.",
    }
