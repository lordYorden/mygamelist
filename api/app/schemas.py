from datetime import datetime
from urllib.parse import urlsplit

from pydantic import ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlmodel import SQLModel

from .models import UserRole


class RegisterRequest(SQLModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)
    terms_accepted: bool

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        has_lower = any(char.islower() for char in value)
        has_upper = any(char.isupper() for char in value)
        has_digit = any(char.isdigit() for char in value)
        has_symbol = any(not char.isalnum() for char in value)
        if sum([has_lower, has_upper, has_digit, has_symbol]) < 3:
            raise ValueError("password must contain at least three character classes")
        return value

    @model_validator(mode="after")
    def validate_registration(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("passwords do not match")
        if not self.terms_accepted:
            raise ValueError("terms must be accepted")
        return self


class TokenRequest(SQLModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(SQLModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="Bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn")

    model_config = ConfigDict(populate_by_name=True)


class RoleChangeRequest(SQLModel):
    role: UserRole

    model_config = ConfigDict(extra="forbid")


class UserResponse(SQLModel):
    id: str
    username: str
    email: EmailStr
    display_name: str | None = Field(alias="displayName")
    profile_picture_url: str | None = Field(default=None, alias="profilePictureUrl")
    role: UserRole
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageResponse(SQLModel):
    success: bool
    message: str


class WebhookRequest(SQLModel):
    title: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title is required")
        return stripped

    @field_validator("url")
    @classmethod
    def validate_absolute_url(cls, value: str) -> str:
        stripped = value.strip()
        try:
            parsed = urlsplit(stripped)
            _ = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("url must be a valid absolute URL") from exc
        if not parsed.scheme or not parsed.netloc or parsed.hostname is None:
            raise ValueError("url must be an absolute URL with a host")
        return stripped


class WebhookResponse(SQLModel):
    id: str
    title: str
    url: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WebhookTestResult(SQLModel):
    target_status: int | None = Field(default=None, alias="targetStatus")
    message: str

    model_config = ConfigDict(populate_by_name=True)
