from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import FrozenClock
from domains.auth.dependencies import get_clock, get_oauth_http_client
from main import create_app
from shared.db.models.enums import OAuthProvider
from shared.db.models.user import OAuthAccount, User
from shared.db.models.wallet import Wallet
from shared.db.session import get_db_session


def _mock_oauth_handler(request: Request) -> Response:
    url_str = str(request.url)
    if url_str == "https://oauth2.googleapis.com/token":
        return Response(200, json={"access_token": "google_mock_access_token"})
    if url_str == "https://openidconnect.googleapis.com/v1/userinfo":
        return Response(
            200,
            json={
                "sub": "google-uid-998877",
                "email": "Martin.Margiela@Obsolete.io",
                "name": "Martin Margiela",
                "picture": "https://lh3.googleusercontent.com/a/margiela",
            },
        )
    if url_str == "https://github.com/login/oauth/access_token":
        return Response(200, json={"access_token": "github_mock_access_token"})
    if url_str == "https://api.github.com/user":
        return Response(
            200,
            json={
                "id": 445566,
                "login": "aphex_twin",
                "email": None,
                "avatar_url": "https://avatars.githubusercontent.com/u/445566",
            },
        )
    if url_str == "https://api.github.com/user/emails":
        return Response(
            200,
            json=[
                {"email": "secondary@warp.net", "primary": False, "verified": True},
                {"email": "rdj@warp.net", "primary": True, "verified": True},
            ],
        )
    return Response(404, json={"error": "not_found"})


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 25, 15, 0, 0, tzinfo=UTC))


@pytest.fixture
async def oauth_api_client(
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    mock_http = AsyncClient(transport=MockTransport(_mock_oauth_handler))

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    app.dependency_overrides[get_oauth_http_client] = lambda: mock_http

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost",
        follow_redirects=False,
    ) as client:
        yield client

    await mock_http.aclose()


@pytest.mark.asyncio
async def test_google_oauth_provisions_passwordless_user_and_wallet(
    oauth_api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    auth_resp = await oauth_api_client.get("/api/v1/auth/oauth/google/authorize")
    assert auth_resp.status_code == 200
    auth_data = auth_resp.json()
    assert auth_data["provider"] == "GOOGLE"
    assert "accounts.google.com" in auth_data["authorization_url"]
    state = auth_data["state"]

    cb_resp = await oauth_api_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "google_auth_code_123", "state": state},
    )
    assert cb_resp.status_code == 302
    assert "refresh_token" in cb_resp.cookies

    redirect_location = cb_resp.headers["location"]
    parsed_url = urlparse(redirect_location)
    query_params = parse_qs(parsed_url.query)
    assert "access_token" in query_params
    access_token = query_params["access_token"][0]

    stmt_user = select(User).where(User.email == "martin.margiela@obsolete.io")
    user = (await db_session.execute(stmt_user)).scalar_one()
    assert user.password_hash is None
    assert user.username == "Martin_Margiela"
    assert user.avatar_url == "https://lh3.googleusercontent.com/a/margiela"

    stmt_wallet = select(Wallet).where(Wallet.user_id == user.id)
    wallet = (await db_session.execute(stmt_wallet)).scalar_one()
    assert wallet.available_balance == Decimal("0.00")
    assert wallet.held_balance == Decimal("0.00")
    assert wallet.claimable_balance == Decimal("0.00")

    stmt_oauth = select(OAuthAccount).where(
        OAuthAccount.provider == OAuthProvider.GOOGLE,
        OAuthAccount.provider_user_id == "google-uid-998877",
    )
    oauth_acc = (await db_session.execute(stmt_oauth)).scalar_one()
    assert oauth_acc.user_id == user.id

    me_resp = await oauth_api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "martin.margiela@obsolete.io"

    password_login = await oauth_api_client.post(
        "/api/v1/auth/login",
        json={"email": "martin.margiela@obsolete.io", "password": "AnyPassword123!"},
    )
    assert password_login.status_code == 401
    assert password_login.json()["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_github_oauth_fetches_verified_email_and_handles_username_collision(
    oauth_api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await oauth_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "existing@obsolete.io",
            "username": "aphex_twin",
            "password": "StrongVaultPassword!23",
        },
    )

    auth_resp = await oauth_api_client.get("/api/v1/auth/oauth/github/authorize")
    assert auth_resp.status_code == 200
    state = auth_resp.json()["state"]

    cb_resp = await oauth_api_client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"code": "gh_code_456", "state": state},
    )
    assert cb_resp.status_code == 302

    stmt_user = select(User).where(User.email == "rdj@warp.net")
    user = (await db_session.execute(stmt_user)).scalar_one()
    assert user.password_hash is None
    assert user.username.startswith("aphex_twin_")
    assert user.username != "aphex_twin"

    stmt_wallet = select(Wallet).where(Wallet.user_id == user.id)
    wallet = (await db_session.execute(stmt_wallet)).scalar_one()
    assert wallet.available_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_oauth_links_to_existing_account_with_same_email(
    oauth_api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    reg_resp = await oauth_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "martin.margiela@obsolete.io",
            "username": "maison_99",
            "password": "StrongVaultPassword!23",
        },
    )
    assert reg_resp.status_code == 201
    original_user_id = reg_resp.json()["user"]["id"]

    auth_resp = await oauth_api_client.get("/api/v1/auth/oauth/google/authorize")
    state = auth_resp.json()["state"]

    cb_resp = await oauth_api_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "google_code_link", "state": state},
    )
    assert cb_resp.status_code == 302

    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 1
    assert str(users[0].id) == original_user_id
    assert users[0].username == "maison_99"
    assert users[0].password_hash is not None

    oauth_accounts = (await db_session.execute(select(OAuthAccount))).scalars().all()
    assert len(oauth_accounts) == 1
    assert str(oauth_accounts[0].user_id) == original_user_id


@pytest.mark.asyncio
async def test_oauth_invalid_state_and_unsupported_provider_rejected(
    oauth_api_client: AsyncClient,
) -> None:
    unsupported = await oauth_api_client.get("/api/v1/auth/oauth/discord/authorize")
    assert unsupported.status_code == 400
    assert unsupported.json()["error_code"] == "UNSUPPORTED_OAUTH_PROVIDER"

    bad_state_cb = await oauth_api_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "abc", "state": "forged_invalid_state"},
    )
    assert bad_state_cb.status_code == 400
    assert bad_state_cb.json()["error_code"] == "INVALID_OAUTH_STATE"

    github_auth = await oauth_api_client.get("/api/v1/auth/oauth/github/authorize")
    github_state = github_auth.json()["state"]

    cross_provider_cb = await oauth_api_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "abc", "state": github_state},
    )
    assert cross_provider_cb.status_code == 400
    assert cross_provider_cb.json()["error_code"] == "INVALID_OAUTH_STATE"
