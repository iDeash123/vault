import re
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.config import Settings, get_settings
from core.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    UnauthorizedError,
)
from core.security import (
    OAuthSettings,
    create_access_token,
    create_oauth_state,
    generate_refresh_token,
    get_oauth_settings,
    hash_password,
    hash_refresh_token,
    verify_oauth_state,
    verify_password,
)
from domains.auth.repository import AuthRepository
from domains.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    LogoutResponse,
    OAuthAuthorizeResponse,
    OAuthUserInfo,
    RegisterRequest,
    UserProfileResponse,
)
from shared.db.models.enums import OAuthProvider, UserRole
from shared.db.models.user import User
from shared.db.models.wallet import Wallet

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_EXCHANGE_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_EXCHANGE_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def parse_oauth_provider(provider_raw: str) -> OAuthProvider:
    normalized = provider_raw.strip().upper()
    try:
        return OAuthProvider(normalized)
    except ValueError as exc:
        raise DomainError(
            message=f"Unsupported OAuth provider '{provider_raw}'",
            error_code="UNSUPPORTED_OAUTH_PROVIDER",
            status_code=400,
        ) from exc


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        clock: ClockPort,
        settings: Settings | None = None,
        oauth_settings: OAuthSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self._repo = AuthRepository(session)
        self._clock = clock
        self._settings = settings or get_settings()
        self._oauth_settings = oauth_settings or get_oauth_settings()
        self._http_client = http_client

    def _build_profile_response(self, user: User, wallet: Wallet) -> UserProfileResponse:
        two_places = Decimal("0.01")
        return UserProfileResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            avatar_url=user.avatar_url,
            bio=user.bio,
            available_balance=Decimal(wallet.available_balance).quantize(two_places),
            held_balance=Decimal(wallet.held_balance).quantize(two_places),
            claimable_balance=Decimal(wallet.claimable_balance).quantize(two_places),
            server_time=self._clock.now(),
        )

    async def _issue_session_tokens(
        self,
        user: User,
        wallet: Wallet,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        now = self._clock.now()
        raw_refresh, refresh_hash = generate_refresh_token()
        expires_at = now + timedelta(days=self._settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await self._repo.create_refresh_session(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        access_token = create_access_token(
            user_id=user.id,
            role=user.role.value,
            now=now,
            settings=self._settings,
        )
        profile = self._build_profile_response(user, wallet)
        return (
            AccessTokenResponse(
                access_token=access_token,
                user=profile,
                server_time=now,
            ),
            raw_refresh,
        )

    async def register(
        self,
        payload: RegisterRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        existing_email = await self._repo.get_user_by_email(payload.email)
        if existing_email is not None:
            raise ConflictError(
                message="Email is already registered",
                error_code="EMAIL_ALREADY_REGISTERED",
                details={"email": payload.email},
            )

        existing_username = await self._repo.get_user_by_username(payload.username)
        if existing_username is not None:
            raise ConflictError(
                message="Username is already taken",
                error_code="USERNAME_ALREADY_TAKEN",
                details={"username": payload.username},
            )

        password_digest = hash_password(payload.password)
        user, wallet = await self._repo.create_user_with_wallet(
            email=payload.email,
            username=payload.username,
            password_hash=password_digest,
            role=UserRole.MEMBER,
            bio=payload.bio,
        )
        token_response, raw_refresh = await self._issue_session_tokens(
            user=user,
            wallet=wallet,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._session.commit()
        return token_response, raw_refresh

    async def login(
        self,
        payload: LoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        user = await self._repo.get_user_by_email(payload.email)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(payload.password, user.password_hash)
        ):
            raise UnauthorizedError(
                message="Invalid email or password",
                error_code="INVALID_CREDENTIALS",
            )

        if not user.is_active:
            raise ForbiddenError(
                message="User account is inactive",
                error_code="USER_INACTIVE",
            )

        wallet = await self._repo.get_or_create_wallet(user.id)
        token_response, raw_refresh = await self._issue_session_tokens(
            user=user,
            wallet=wallet,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._session.commit()
        return token_response, raw_refresh

    async def refresh_session(
        self,
        raw_refresh_token: str | None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        if not raw_refresh_token:
            raise UnauthorizedError(
                message="Refresh token cookie is required",
                error_code="MISSING_REFRESH_TOKEN",
            )

        now = self._clock.now()
        token_hash = hash_refresh_token(raw_refresh_token)
        session_record = await self._repo.get_refresh_session_by_hash(
            token_hash=token_hash,
            for_update=True,
        )
        if session_record is None:
            raise UnauthorizedError(
                message="Invalid refresh token",
                error_code="INVALID_REFRESH_TOKEN",
            )

        if session_record.revoked_at is not None:
            await self._repo.revoke_all_user_refresh_sessions(
                user_id=session_record.user_id,
                revoked_at=now,
            )
            await self._session.commit()
            raise UnauthorizedError(
                message="Refresh token has already been revoked",
                error_code="REFRESH_TOKEN_REUSED",
            )

        if session_record.expires_at <= now:
            await self._repo.revoke_refresh_session(session_record, revoked_at=now)
            await self._session.commit()
            raise UnauthorizedError(
                message="Refresh token has expired",
                error_code="REFRESH_TOKEN_EXPIRED",
            )

        user = await self._repo.get_user_by_id(session_record.user_id)
        if user is None:
            raise UnauthorizedError(
                message="User associated with session not found",
                error_code="USER_NOT_FOUND",
            )
        if not user.is_active:
            raise ForbiddenError(
                message="User account is inactive",
                error_code="USER_INACTIVE",
            )

        await self._repo.revoke_refresh_session(session_record, revoked_at=now)
        wallet = await self._repo.get_or_create_wallet(user.id)
        token_response, new_raw_refresh = await self._issue_session_tokens(
            user=user,
            wallet=wallet,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._session.commit()
        return token_response, new_raw_refresh

    async def logout(
        self,
        raw_refresh_token: str | None,
        user_id: uuid.UUID | None = None,
    ) -> LogoutResponse:
        now = self._clock.now()
        if raw_refresh_token:
            token_hash = hash_refresh_token(raw_refresh_token)
            session_record = await self._repo.get_refresh_session_by_hash(
                token_hash=token_hash,
                for_update=True,
            )
            if session_record is not None and session_record.revoked_at is None:
                await self._repo.revoke_refresh_session(session_record, revoked_at=now)
                await self._session.commit()
        elif user_id is not None:
            await self._repo.revoke_all_user_refresh_sessions(user_id=user_id, revoked_at=now)
            await self._session.commit()

        return LogoutResponse(status="logged_out", server_time=now)

    async def get_profile(self, user: User) -> UserProfileResponse:
        wallet = await self._repo.get_or_create_wallet(user.id)
        await self._session.commit()
        return self._build_profile_response(user, wallet)

    def _default_callback_url(self, provider: OAuthProvider) -> str:
        base_api = self._settings.VITE_API_BASE_URL.rstrip("/")
        return f"{base_api}/auth/oauth/{provider.value.lower()}/callback"

    def build_oauth_authorize_url(
        self,
        provider_raw: str,
        redirect_uri: str | None = None,
    ) -> OAuthAuthorizeResponse:
        provider = parse_oauth_provider(provider_raw)
        now = self._clock.now()
        state = create_oauth_state(
            provider=provider.value,
            now=now,
            settings=self._settings,
        )
        callback_uri = redirect_uri or self._default_callback_url(provider)

        if provider == OAuthProvider.GOOGLE:
            query = urlencode(
                {
                    "client_id": self._oauth_settings.GOOGLE_CLIENT_ID,
                    "redirect_uri": callback_uri,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "state": state,
                    "access_type": "offline",
                    "prompt": "select_account",
                }
            )
            auth_url = f"{GOOGLE_AUTH_URL}?{query}"
        else:
            query = urlencode(
                {
                    "client_id": self._oauth_settings.GITHUB_CLIENT_ID,
                    "redirect_uri": callback_uri,
                    "scope": "read:user user:email",
                    "state": state,
                }
            )
            auth_url = f"{GITHUB_AUTH_URL}?{query}"

        return OAuthAuthorizeResponse(
            authorization_url=auth_url,
            state=state,
            provider=provider,
            server_time=now,
        )

    async def _fetch_google_userinfo(
        self,
        client: httpx.AsyncClient,
        code: str,
        redirect_uri: str,
    ) -> OAuthUserInfo:
        token_resp = await client.post(
            GOOGLE_EXCHANGE_URL,
            data={
                "code": code,
                "client_id": self._oauth_settings.GOOGLE_CLIENT_ID,
                "client_secret": self._oauth_settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code >= 400:
            raise DomainError(
                message="Failed to exchange Google OAuth authorization code",
                error_code="OAUTH_TOKEN_EXCHANGE_FAILED",
                status_code=400,
            )
        token_data: dict[str, Any] = token_resp.json()
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise DomainError(
                message="Google OAuth token response missing access_token",
                error_code="OAUTH_TOKEN_EXCHANGE_FAILED",
                status_code=400,
            )

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code >= 400:
            raise DomainError(
                message="Failed to fetch Google user profile",
                error_code="OAUTH_PROFILE_FETCH_FAILED",
                status_code=400,
            )
        profile_data: dict[str, Any] = userinfo_resp.json()
        sub = profile_data.get("sub") or profile_data.get("id")
        email = profile_data.get("email")
        if not sub or not isinstance(email, str) or not email.strip():
            raise DomainError(
                message="Google OAuth profile is missing subject ID or email",
                error_code="OAUTH_EMAIL_REQUIRED",
                status_code=400,
            )
        clean_email = email.strip().lower()
        name_hint = profile_data.get("name") or clean_email.split("@")[0]
        avatar_url = profile_data.get("picture")
        return OAuthUserInfo(
            provider=OAuthProvider.GOOGLE,
            provider_user_id=str(sub),
            email=clean_email,
            username_hint=str(name_hint),
            avatar_url=str(avatar_url) if isinstance(avatar_url, str) else None,
        )

    async def _fetch_github_userinfo(
        self,
        client: httpx.AsyncClient,
        code: str,
        redirect_uri: str,
    ) -> OAuthUserInfo:
        token_resp = await client.post(
            GITHUB_EXCHANGE_URL,
            data={
                "code": code,
                "client_id": self._oauth_settings.GITHUB_CLIENT_ID,
                "client_secret": self._oauth_settings.GITHUB_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )

        if token_resp.status_code >= 400:
            raise DomainError(
                message="Failed to exchange GitHub OAuth authorization code",
                error_code="OAUTH_TOKEN_EXCHANGE_FAILED",
                status_code=400,
            )
        token_data: dict[str, Any] = token_resp.json()
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise DomainError(
                message="GitHub OAuth token response missing access_token",
                error_code="OAUTH_TOKEN_EXCHANGE_FAILED",
                status_code=400,
            )

        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        user_resp = await client.get(GITHUB_USER_URL, headers=auth_headers)
        if user_resp.status_code >= 400:
            raise DomainError(
                message="Failed to fetch GitHub user profile",
                error_code="OAUTH_PROFILE_FETCH_FAILED",
                status_code=400,
            )
        user_data: dict[str, Any] = user_resp.json()
        provider_id = user_data.get("id")
        if provider_id is None:
            raise DomainError(
                message="GitHub profile response missing user id",
                error_code="OAUTH_PROFILE_FETCH_FAILED",
                status_code=400,
            )

        email_val = user_data.get("email")
        resolved_email: str | None = (
            email_val.strip().lower() if isinstance(email_val, str) and email_val.strip() else None
        )

        if resolved_email is None:
            emails_resp = await client.get(GITHUB_EMAILS_URL, headers=auth_headers)
            if emails_resp.status_code < 400:
                emails_list = emails_resp.json()
                if isinstance(emails_list, list):
                    for item in emails_list:
                        if (
                            isinstance(item, dict)
                            and item.get("primary") is True
                            and item.get("verified") is True
                            and isinstance(item.get("email"), str)
                        ):
                            resolved_email = item["email"].strip().lower()
                            break
                    if resolved_email is None:
                        for item in emails_list:
                            if (
                                isinstance(item, dict)
                                and item.get("verified") is True
                                and isinstance(item.get("email"), str)
                            ):
                                resolved_email = item["email"].strip().lower()
                                break

        if not resolved_email:
            raise DomainError(
                message="GitHub account does not have a verified email address",
                error_code="OAUTH_EMAIL_REQUIRED",
                status_code=400,
            )

        login_hint = user_data.get("login") or resolved_email.split("@")[0]
        avatar_url = user_data.get("avatar_url")
        return OAuthUserInfo(
            provider=OAuthProvider.GITHUB,
            provider_user_id=str(provider_id),
            email=resolved_email,
            username_hint=str(login_hint),
            avatar_url=str(avatar_url) if isinstance(avatar_url, str) else None,
        )

    async def exchange_oauth_code_for_userinfo(
        self,
        provider: OAuthProvider,
        code: str,
        redirect_uri: str | None = None,
    ) -> OAuthUserInfo:
        callback_uri = redirect_uri or self._default_callback_url(provider)
        if self._http_client is not None:
            if provider == OAuthProvider.GOOGLE:
                return await self._fetch_google_userinfo(self._http_client, code, callback_uri)
            return await self._fetch_github_userinfo(self._http_client, code, callback_uri)

        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == OAuthProvider.GOOGLE:
                return await self._fetch_google_userinfo(client, code, callback_uri)
            return await self._fetch_github_userinfo(client, code, callback_uri)

    async def _generate_unique_username(self, raw_hint: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_hint).strip("_")
        if len(sanitized) < 3:
            sanitized = f"archivist_{secrets.token_hex(3)}"
        base_candidate = sanitized[:48]
        existing = await self._repo.get_user_by_username(base_candidate)
        if existing is None:
            return base_candidate

        for _ in range(10):
            candidate = f"{base_candidate}_{secrets.token_hex(3)}"
            if await self._repo.get_user_by_username(candidate) is None:
                return candidate
        return f"user_{uuid.uuid4().hex[:12]}"

    async def authenticate_oauth_user(
        self,
        userinfo: OAuthUserInfo,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        oauth_record = await self._repo.get_oauth_account(
            provider=userinfo.provider,
            provider_user_id=userinfo.provider_user_id,
        )

        if oauth_record is not None:
            user = await self._repo.get_user_by_id(oauth_record.user_id)
            if user is None:
                raise UnauthorizedError(
                    message="Linked user account not found",
                    error_code="USER_NOT_FOUND",
                )
            wallet = await self._repo.get_or_create_wallet(user.id)
        else:
            existing_user = await self._repo.get_user_by_email(userinfo.email)
            if existing_user is not None:
                user = existing_user
                if user.avatar_url is None and userinfo.avatar_url is not None:
                    user.avatar_url = userinfo.avatar_url
                wallet = await self._repo.get_or_create_wallet(user.id)
                await self._repo.create_oauth_account(
                    user_id=user.id,
                    provider=userinfo.provider,
                    provider_user_id=userinfo.provider_user_id,
                    email=userinfo.email,
                )
            else:
                unique_username = await self._generate_unique_username(userinfo.username_hint)
                user, wallet = await self._repo.create_user_with_wallet(
                    email=userinfo.email,
                    username=unique_username,
                    password_hash=None,
                    role=UserRole.MEMBER,
                    avatar_url=userinfo.avatar_url,
                )
                await self._repo.create_oauth_account(
                    user_id=user.id,
                    provider=userinfo.provider,
                    provider_user_id=userinfo.provider_user_id,
                    email=userinfo.email,
                )

        if not user.is_active:
            raise ForbiddenError(
                message="User account is inactive",
                error_code="USER_INACTIVE",
            )

        token_response, raw_refresh = await self._issue_session_tokens(
            user=user,
            wallet=wallet,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._session.commit()
        return token_response, raw_refresh

    async def handle_oauth_callback(
        self,
        provider_raw: str,
        code: str,
        state: str,
        redirect_uri: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AccessTokenResponse, str, str]:
        provider = parse_oauth_provider(provider_raw)
        verify_oauth_state(
            state_token=state,
            expected_provider=provider.value,
            now=self._clock.now(),
            settings=self._settings,
        )
        userinfo = await self.exchange_oauth_code_for_userinfo(
            provider=provider,
            code=code,
            redirect_uri=redirect_uri,
        )
        token_response, raw_refresh = await self.authenticate_oauth_user(
            userinfo=userinfo,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        base_redirect = self._oauth_settings.OAUTH_FRONTEND_REDIRECT_URL
        sep = "&" if "?" in base_redirect else "?"
        frontend_redirect_url = f"{base_redirect}{sep}access_token={token_response.access_token}"
        return token_response, raw_refresh, frontend_redirect_url
