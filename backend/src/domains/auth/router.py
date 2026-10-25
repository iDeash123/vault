from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from core.config import get_settings
from core.exceptions import DomainError
from domains.auth.dependencies import get_auth_service, get_current_user
from domains.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    LogoutResponse,
    OAuthAuthorizeResponse,
    RegisterRequest,
    UserProfileResponse,
)
from domains.auth.service import AuthService
from shared.db.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    settings = get_settings()
    max_age = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    cookie_domain = (
        settings.COOKIE_DOMAIN
        if settings.COOKIE_DOMAIN not in {"localhost", "127.0.0.1", ""}
        else None
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        domain=cookie_domain,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    cookie_domain = (
        settings.COOKIE_DOMAIN
        if settings.COOKIE_DOMAIN not in {"localhost", "127.0.0.1", ""}
        else None
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/",
        domain=cookie_domain,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


def _extract_client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client is not None else None
    return user_agent, ip_address


@router.post(
    "/register",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessTokenResponse:
    user_agent, ip_address = _extract_client_meta(request)
    token_response, raw_refresh = await service.register(
        payload=payload,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, raw_refresh)
    return token_response


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessTokenResponse:
    user_agent, ip_address = _extract_client_meta(request)
    token_response, raw_refresh = await service.login(
        payload=payload,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, raw_refresh)
    return token_response


@router.get("/oauth/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(
    provider: str,
    service: Annotated[AuthService, Depends(get_auth_service)],
    redirect_uri: Annotated[str | None, Query()] = None,
) -> OAuthAuthorizeResponse:
    return service.build_oauth_authorize_url(
        provider_raw=provider,
        redirect_uri=redirect_uri,
    )


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    if not code or not state:
        raise DomainError(
            message="Both 'code' and 'state' query parameters are required",
            error_code="INVALID_OAUTH_CALLBACK",
            status_code=400,
        )
    user_agent, ip_address = _extract_client_meta(request)
    _, raw_refresh, frontend_redirect_url = await service.handle_oauth_callback(
        provider_raw=provider,
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    redirect_response = RedirectResponse(
        url=frontend_redirect_url,
        status_code=status.HTTP_302_FOUND,
    )
    _set_refresh_cookie(redirect_response, raw_refresh)
    return redirect_response


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AccessTokenResponse:
    user_agent, ip_address = _extract_client_meta(request)
    token_response, new_raw_refresh = await service.refresh_session(
        raw_refresh_token=refresh_token,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, new_raw_refresh)
    return token_response


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> LogoutResponse:
    result = await service.logout(
        raw_refresh_token=refresh_token,
        user_id=current_user.id,
    )
    _clear_refresh_cookie(response)
    return result


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserProfileResponse:
    return await service.get_profile(current_user)
