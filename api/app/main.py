from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .admin import change_user_role, list_all_users, require_role
from .config import Settings, get_settings
from .database import get_db, init_db
from .models import Upload, User, UserRole
from .schemas import RegisterRequest, RoleChangeRequest, TokenRequest, TokenResponse, UserResponse
from .security import create_access_token, get_current_user, get_user_by_identifier, hash_password, verify_password
from .uploads import (
    check_profile_picture_rate_limit,
    get_upload_object,
    logger as upload_logger,
    profile_picture_storage_key,
    put_upload_object,
    read_profile_picture_content,
    sanitize_profile_picture,
    validate_profile_picture,
)


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

    existing = db.exec(select(User).where((User.username == username) | (User.email == email))).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    with db.begin_nested():
        first_user = db.exec(select(User.id).limit(1)).first()
        role = UserRole.ADMIN if first_user is None else UserRole.GAMER
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


@app.post("/api/me/profile-picture", response_model=UserResponse)
async def upload_profile_picture(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    check_profile_picture_rate_limit(current_user.id)
    content = await read_profile_picture_content(file)
    content_type = validate_profile_picture(file, content)
    content = sanitize_profile_picture(content, content_type)
    storage_key = profile_picture_storage_key(current_user.id, content_type)

    put_upload_object(settings, storage_key, content, content_type)

    upload = Upload(
        owner_user_id=current_user.id,
        upload_type="profile_picture",
        original_filename=file.filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(content),
    )
    db.add(upload)
    db.flush()

    current_user.profile_picture_upload_id = upload.id
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    upload_logger.info(
        "profile_picture_upload_success user_id=%s upload_id=%s size_bytes=%s content_type=%s",
        current_user.id,
        upload.id,
        len(content),
        content_type,
    )
    return current_user


@app.get("/api/me/profile-picture")
def get_profile_picture(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    if current_user.profile_picture_upload_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile picture not found")

    upload = db.get(Upload, current_user.profile_picture_upload_id)
    if upload is None or upload.owner_user_id != current_user.id or upload.upload_type != "profile_picture":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile picture not found")

    body, content_type = get_upload_object(settings, upload.storage_key)
    return StreamingResponse(body, media_type=content_type)


@app.get("/api/admin/users", response_model=list[UserResponse])
def admin_list_users(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> list[User]:
    return list_all_users(db, current_user)


@app.patch("/api/admin/users/{user_id}/role", response_model=UserResponse)
def admin_change_user_role(
    user_id: str,
    request: RoleChangeRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> User:
    return change_user_role(db, current_user, user_id, request.role)


@app.delete("/api/game-entries/{entry_id}")
def delete_game_entry(entry_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> dict[str, str | bool]:
    return {
        "success": True,
        "message": f"Protected delete pattern accepted for entry {entry_id} by {current_user.username}.",
    }
