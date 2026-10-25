import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort, SystemClock
from core.exceptions import ForbiddenError, UnauthorizedError
from core.security import decode_access_token
from domains.auth.repository import AuthRepository
from domains.auth.service import AuthService
from shared.db.models.enums import UserRole
from shared.db.models.user import User
from shared.db.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)
_default_clock: ClockPort = SystemClock()


def get_clock() -> ClockPort:
    return _default_clock


def get_oauth_http_client() -> httpx.AsyncClient | None:
    return None


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    http_client: Annotated[httpx.AsyncClient | None, Depends(get_oauth_http_client)],
) -> AuthService:
    return AuthService(session=session, clock=clock, http_client=http_client)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError(
            message="Authentication required",
            error_code="UNAUTHORIZED",
        )

    payload = decode_access_token(token=credentials.credentials, now=clock.now())
    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError(
            message="Invalid user subject in token",
            error_code="INVALID_ACCESS_TOKEN",
        ) from exc

    repo = AuthRepository(session)
    user = await repo.get_user_by_id(user_id)
    if user is None:
        raise UnauthorizedError(
            message="User account not found",
            error_code="USER_NOT_FOUND",
        )
    if not user.is_active:
        raise ForbiddenError(
            message="User account is inactive",
            error_code="USER_INACTIVE",
        )
    return user


def require_roles(
    *allowed_roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    allowed_set = set(allowed_roles)

    async def role_guard(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_set:
            raise ForbiddenError(
                message="Insufficient role permissions",
                error_code="INSUFFICIENT_ROLE",
                details={
                    "required_roles": [role.value for role in allowed_roles],
                    "actual_role": current_user.role.value,
                },
            )
        return current_user

    return role_guard


require_curator_or_admin = require_roles(UserRole.CURATOR, UserRole.ADMIN)
require_admin = require_roles(UserRole.ADMIN)
