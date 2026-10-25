import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt
from pwdlib import PasswordHash
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.config import Settings, get_settings
from core.exceptions import DomainError, UnauthorizedError

_password_hasher = PasswordHash.recommended()


class OAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[3] / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: SecretStr
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: SecretStr
    OAUTH_FRONTEND_REDIRECT_URL: str = "http://localhost:5173/auth/callback"


@lru_cache
def get_oauth_settings() -> OAuthSettings:
    return OAuthSettings()


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_refresh_token(raw_token)


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=cfg.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        cfg.JWT_SECRET_KEY.get_secret_value(),
        algorithm=cfg.JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    current_ts = int((now or datetime.now(UTC)).timestamp())
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            cfg.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[cfg.JWT_ALGORITHM],
            options={"verify_exp": False, "verify_iat": False},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(
            message="Invalid or malformed access token",
            error_code="INVALID_ACCESS_TOKEN",
        ) from exc

    exp_val = payload.get("exp")
    if not isinstance(exp_val, int | float) or exp_val <= current_ts:
        raise UnauthorizedError(
            message="Access token has expired",
            error_code="ACCESS_TOKEN_EXPIRED",
        )

    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise UnauthorizedError(
            message="Invalid access token claims",
            error_code="INVALID_ACCESS_TOKEN",
        )

    return payload


def create_oauth_state(
    provider: str,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=10)
    payload: dict[str, Any] = {
        "type": "oauth_state",
        "provider": provider.upper(),
        "nonce": secrets.token_hex(16),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        cfg.JWT_SECRET_KEY.get_secret_value(),
        algorithm=cfg.JWT_ALGORITHM,
    )


def verify_oauth_state(
    state_token: str,
    expected_provider: str,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    current_ts = int((now or datetime.now(UTC)).timestamp())
    try:
        payload: dict[str, Any] = jwt.decode(
            state_token,
            cfg.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[cfg.JWT_ALGORITHM],
            options={"verify_exp": False, "verify_iat": False},
        )
    except jwt.PyJWTError as exc:
        raise DomainError(
            message="Invalid OAuth state parameter",
            error_code="INVALID_OAUTH_STATE",
            status_code=400,
        ) from exc

    exp_val = payload.get("exp")
    if not isinstance(exp_val, int | float) or exp_val <= current_ts:
        raise DomainError(
            message="OAuth state parameter has expired",
            error_code="OAUTH_STATE_EXPIRED",
            status_code=400,
        )

    if payload.get("type") != "oauth_state" or payload.get("provider") != expected_provider.upper():
        raise DomainError(
            message="OAuth state provider mismatch",
            error_code="INVALID_OAUTH_STATE",
            status_code=400,
        )

    return payload
