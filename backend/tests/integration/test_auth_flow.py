from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import FrozenClock
from domains.auth.dependencies import (
    get_clock,
    require_admin,
    require_curator_or_admin,
)
from main import create_app
from shared.db.models.enums import UserRole
from shared.db.models.user import RefreshSession, User
from shared.db.models.wallet import Wallet
from shared.db.session import get_db_session


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock

    @app.get("/api/v1/test-curator-only")
    async def curator_endpoint(
        current_user: Annotated[User, Depends(require_curator_or_admin)],
    ) -> dict[str, str]:
        return {"user_id": str(current_user.id), "role": current_user.role.value}

    @app.get("/api/v1/test-admin-only")
    async def admin_endpoint(
        current_user: Annotated[User, Depends(require_admin)],
    ) -> dict[str, str]:
        return {"user_id": str(current_user.id), "role": current_user.role.value}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
async def test_register_creates_user_and_zero_balance_wallet(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "Archivist@Obsolete.io",
            "username": "raf_collector",
            "password": "StrongVaultPassword!23",
            "bio": "Archival collector since 2001",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "server_time" in data
    assert "refresh_token" in response.cookies

    user_payload = data["user"]
    assert user_payload["email"] == "archivist@obsolete.io"
    assert user_payload["username"] == "raf_collector"
    assert user_payload["role"] == "MEMBER"
    assert user_payload["available_balance"] == "0.00"
    assert user_payload["held_balance"] == "0.00"
    assert user_payload["claimable_balance"] == "0.00"

    stmt_user = select(User).where(User.email == "archivist@obsolete.io")
    db_user = (await db_session.execute(stmt_user)).scalar_one()
    assert db_user.password_hash is not None
    assert db_user.password_hash.startswith("$argon2")
    assert db_user.password_hash != "StrongVaultPassword!23"

    stmt_wallet = select(Wallet).where(Wallet.user_id == db_user.id)
    db_wallet = (await db_session.execute(stmt_wallet)).scalar_one()
    assert db_wallet.available_balance == Decimal("0.00")
    assert db_wallet.held_balance == Decimal("0.00")
    assert db_wallet.claimable_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_register_duplicate_email_and_username_rejected(
    api_client: AsyncClient,
) -> None:
    first = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@obsolete.io",
            "username": "unique_handle",
            "password": "StrongVaultPassword!23",
        },
    )
    assert first.status_code == 201

    dup_email = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUP@obsolete.io",
            "username": "another_handle",
            "password": "StrongVaultPassword!23",
        },
    )
    assert dup_email.status_code == 409
    assert dup_email.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"

    dup_username = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "other@obsolete.io",
            "username": "unique_handle",
            "password": "StrongVaultPassword!23",
        },
    )
    assert dup_username.status_code == 409
    assert dup_username.json()["error_code"] == "USERNAME_ALREADY_TAKEN"


@pytest.mark.asyncio
async def test_login_and_me_endpoint(
    api_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "member@obsolete.io",
            "username": "vinyl_hunter",
            "password": "CorrectHorseBatteryStaple1!",
        },
    )

    bad_login = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "member@obsolete.io",
            "password": "WrongPassword999!",
        },
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error_code"] == "INVALID_CREDENTIALS"

    good_login = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "member@obsolete.io",
            "password": "CorrectHorseBatteryStaple1!",
        },
    )
    assert good_login.status_code == 200
    access_token = good_login.json()["access_token"]

    unauth_me = await api_client.get("/api/v1/auth/me")
    assert unauth_me.status_code == 401

    me_resp = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == "vinyl_hunter"
    assert me_data["available_balance"] == "0.00"

    frozen_clock.set_time(frozen_clock.now() + timedelta(minutes=20))
    expired_me = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert expired_me.status_code == 401
    assert expired_me.json()["error_code"] == "ACCESS_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    reg_resp = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "rotate@obsolete.io",
            "username": "rotate_tester",
            "password": "StrongVaultPassword!23",
        },
    )
    assert reg_resp.status_code == 201
    first_refresh_token = reg_resp.cookies["refresh_token"]

    api_client.cookies.set("refresh_token", first_refresh_token)
    refresh_resp = await api_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    second_refresh_token = refresh_resp.cookies["refresh_token"]
    assert second_refresh_token != first_refresh_token

    api_client.cookies.set("refresh_token", first_refresh_token)
    reuse_resp = await api_client.post("/api/v1/auth/refresh")
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["error_code"] == "REFRESH_TOKEN_REUSED"

    api_client.cookies.set("refresh_token", second_refresh_token)
    after_compromise_resp = await api_client.post("/api/v1/auth/refresh")
    assert after_compromise_resp.status_code == 401
    assert after_compromise_resp.json()["error_code"] == "REFRESH_TOKEN_REUSED"

    stmt = select(RefreshSession)
    sessions = (await db_session.execute(stmt)).scalars().all()
    assert len(sessions) == 2
    assert all(s.revoked_at is not None for s in sessions)


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session(
    api_client: AsyncClient,
) -> None:
    reg_resp = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@obsolete.io",
            "username": "logout_user",
            "password": "StrongVaultPassword!23",
        },
    )
    access_token = reg_resp.json()["access_token"]
    refresh_token = reg_resp.cookies["refresh_token"]

    api_client.cookies.set("refresh_token", refresh_token)
    logout_resp = await api_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "logged_out"

    api_client.cookies.set("refresh_token", refresh_token)
    refresh_after_logout = await api_client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_role_guards_member_curator_admin(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    reg_resp = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "roles@obsolete.io",
            "username": "role_tester",
            "password": "StrongVaultPassword!23",
        },
    )
    member_token = reg_resp.json()["access_token"]

    member_curator_try = await api_client.get(
        "/api/v1/test-curator-only",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_curator_try.status_code == 403
    assert member_curator_try.json()["error_code"] == "INSUFFICIENT_ROLE"

    stmt = select(User).where(User.email == "roles@obsolete.io")
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.CURATOR
    await db_session.commit()

    curator_ok = await api_client.get(
        "/api/v1/test-curator-only",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert curator_ok.status_code == 200
    assert curator_ok.json()["role"] == "CURATOR"

    curator_admin_try = await api_client.get(
        "/api/v1/test-admin-only",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert curator_admin_try.status_code == 403

    user.role = UserRole.ADMIN
    await db_session.commit()

    admin_ok = await api_client.get(
        "/api/v1/test-admin-only",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert admin_ok.status_code == 200
    assert admin_ok.json()["role"] == "ADMIN"
