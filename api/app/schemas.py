from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import UserRole


class RegisterRequest(BaseModel):
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


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="Bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn")

    model_config = ConfigDict(populate_by_name=True)


class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    display_name: str | None = Field(alias="displayName")
    role: UserRole
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageResponse(BaseModel):
    success: bool
    message: str
