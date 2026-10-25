import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from shared.db.models.enums import OAuthProvider, UserRole


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)
    bio: str | None = Field(default=None, max_length=1000)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    role: UserRole
    is_active: bool
    avatar_url: str | None
    bio: str | None
    available_balance: Decimal
    held_balance: Decimal
    claimable_balance: Decimal
    server_time: datetime


class AccessTokenResponse(BaseModel):
    access_token: str
    user: UserProfileResponse
    server_time: datetime


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str
    provider: OAuthProvider
    server_time: datetime


class LogoutResponse(BaseModel):
    status: str = "logged_out"
    server_time: datetime


class OAuthUserInfo(BaseModel):
    provider: OAuthProvider
    provider_user_id: str
    email: str
    username_hint: str
    avatar_url: str | None = None
