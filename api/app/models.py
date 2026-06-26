from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlmodel import Field, SQLModel


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    GAMER = "GAMER"
    MODERATOR = "MODERATOR"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    username: str = Field(index=True, unique=True, nullable=False, max_length=40)
    email: str = Field(index=True, unique=True, nullable=False, max_length=255)
    password_hash: str = Field(nullable=False, max_length=255)
    display_name: str | None = Field(default=None, max_length=80)
    profile_picture_upload_id: str | None = Field(default=None, max_length=36)
    role: UserRole = Field(default=UserRole.GAMER, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def profile_picture_url(self) -> str | None:
        if self.profile_picture_upload_id is None:
            return None
        return "/api/me/profile-picture"


class Upload(SQLModel, table=True):
    __tablename__ = "uploads"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    owner_user_id: str = Field(foreign_key="users.id", index=True, nullable=False, max_length=36)
    upload_type: str = Field(nullable=False, max_length=40)
    original_filename: str = Field(nullable=False, max_length=255)
    storage_key: str = Field(unique=True, nullable=False, max_length=255)
    content_type: str = Field(nullable=False, max_length=80)
    size_bytes: int = Field(nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
