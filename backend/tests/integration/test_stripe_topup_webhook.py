import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from adapters.payment_fake import InMemoryPaymentGatewayAdapter
from adapters.payment_stripe import StripePaymentGatewayAdapter
from core.clock import FrozenClock
from domains.auth.dependencies import get_clock
from domains.wallet.router import get_payment_gateway
from main import create_app
from ports.payment_port import PaymentGatewayPort
from shared.db.models.enums import LedgerEntryType
from shared.db.models.wallet import StripeWebhookEvent, Wallet, WalletLedgerEntry
from shared.db.session import get_db_session

TEST_WEBHOOK_SECRET = "whsec_slice_3_2_integration_secret"


def _compute_stripe_signature(
    payload_bytes: bytes, secret: str, timestamp: int | None = None
) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload_bytes.decode('utf-8')}".encode()
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 25, 16, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_payment_gateway() -> InMemoryPaymentGatewayAdapter:
    return InMemoryPaymentGatewayAdapter(webhook_secret=TEST_WEBHOOK_SECRET)


@pytest.fixture
async def wallet_api_client(
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    app.dependency_overrides[get_payment_gateway] = lambda: fake_payment_gateway

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
async def test_create_topup_checkout_session_and_valid_webhook_credits_wallet(
    wallet_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
) -> None:
    reg_resp = await wallet_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "collector@obsolete.io",
            "username": "helmut_archive",
            "password": "StrongVaultPassword!23",
        },
    )
    assert reg_resp.status_code == 201
    access_token = reg_resp.json()["access_token"]
    user_id = reg_resp.json()["user"]["id"]

    checkout_resp = await wallet_api_client.post(
        "/api/v1/wallet/topup/checkout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount_usd": "500.00"},
    )
    assert checkout_resp.status_code == 200
    checkout_data = checkout_resp.json()
    assert checkout_data["session_id"].startswith("cs_test_")
    assert "session_id=" in checkout_data["checkout_url"]
    assert checkout_data["server_time"] == "2026-10-25T16:00:00Z"

    event_payload = fake_payment_gateway.simulate_checkout_completed(checkout_data["session_id"])
    raw_body = json.dumps(event_payload).encode("utf-8")

    webhook_resp = await wallet_api_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": f"t=1729872000,v1={TEST_WEBHOOK_SECRET}",
        },
    )
    assert webhook_resp.status_code == 200
    wh_data = webhook_resp.json()
    assert wh_data["status"] == "processed"
    assert wh_data["stripe_event_id"] == event_payload["id"]
    assert wh_data["idempotent_replay"] is False

    wallet_resp = await wallet_api_client.get(
        "/api/v1/wallet",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert wallet_resp.status_code == 200
    summary = wallet_resp.json()
    assert summary["available_balance"] == "500.00"
    assert summary["held_balance"] == "0.00"
    assert summary["claimable_balance"] == "0.00"
    assert summary["holds"] == []
    assert len(summary["ledger_entries"]) == 1

    ledger_entry = summary["ledger_entries"][0]
    assert ledger_entry["entry_type"] == "STRIPE_TOPUP"
    assert ledger_entry["amount"] == "500.00"
    assert ledger_entry["available_delta"] == "500.00"
    assert ledger_entry["held_delta"] == "0.00"
    assert ledger_entry["claimable_delta"] == "0.00"
    assert ledger_entry["balance_available_after"] == "500.00"

    db_events = (await db_session.execute(select(StripeWebhookEvent))).scalars().all()
    assert len(db_events) == 1
    assert db_events[0].stripe_event_id == event_payload["id"]
    assert str(db_events[0].user_id) == user_id
    assert db_events[0].amount_usd == Decimal("500.00")


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_invalid_or_missing_signature(
    wallet_api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    reg_resp = await wallet_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "sigtest@obsolete.io",
            "username": "sig_tester",
            "password": "StrongVaultPassword!23",
        },
    )
    user_id = reg_resp.json()["user"]["id"]

    forged_payload = json.dumps(
        {
            "id": "evt_forged_999",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_forged_1",
                    "client_reference_id": user_id,
                    "amount_total": 100000,
                }
            },
        }
    ).encode("utf-8")

    forged_resp = await wallet_api_client.post(
        "/api/v1/webhooks/stripe",
        content=forged_payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "t=1729872000,v1=forged_bad_signature_hex",
        },
    )
    assert forged_resp.status_code == 400
    assert forged_resp.json()["error_code"] == "INVALID_STRIPE_SIGNATURE"

    missing_sig_resp = await wallet_api_client.post(
        "/api/v1/webhooks/stripe",
        content=forged_payload,
        headers={"Content-Type": "application/json"},
    )
    assert missing_sig_resp.status_code == 400
    assert missing_sig_resp.json()["error_code"] == "INVALID_STRIPE_SIGNATURE"

    wallet_row = (await db_session.execute(select(Wallet))).scalar_one()
    assert wallet_row.available_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_stripe_webhook_idempotency_credits_balance_exactly_once(
    wallet_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
) -> None:
    reg_resp = await wallet_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "idempotent@obsolete.io",
            "username": "idem_collector",
            "password": "StrongVaultPassword!23",
        },
    )
    access_token = reg_resp.json()["access_token"]

    checkout_resp = await wallet_api_client.post(
        "/api/v1/wallet/topup/checkout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount_usd": "1250.50"},
    )
    session_id = checkout_resp.json()["session_id"]
    event_payload = fake_payment_gateway.simulate_checkout_completed(session_id)
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig_header = {"Stripe-Signature": TEST_WEBHOOK_SECRET}

    first_delivery = await wallet_api_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers=sig_header,
    )
    assert first_delivery.status_code == 200
    assert first_delivery.json()["status"] == "processed"
    assert first_delivery.json()["idempotent_replay"] is False

    second_delivery = await wallet_api_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers=sig_header,
    )
    assert second_delivery.status_code == 200
    assert second_delivery.json()["status"] == "already_processed"
    assert second_delivery.json()["idempotent_replay"] is True

    wallet_row = (await db_session.execute(select(Wallet))).scalar_one()
    assert wallet_row.available_balance == Decimal("1250.50")

    webhook_events = (await db_session.execute(select(StripeWebhookEvent))).scalars().all()
    assert len(webhook_events) == 1

    ledger_entries = (await db_session.execute(select(WalletLedgerEntry))).scalars().all()
    assert len(ledger_entries) == 1
    assert ledger_entries[0].entry_type == LedgerEntryType.STRIPE_TOPUP
    assert ledger_entries[0].amount == Decimal("1250.50")


@pytest.mark.asyncio
async def test_real_stripe_payment_gateway_adapter_hmac_verification_and_concurrent_idempotency(
    db_engine: AsyncEngine,
    frozen_clock: FrozenClock,
) -> None:
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    real_stripe_adapter = StripePaymentGatewayAdapter(
        secret_key="sk_test_unit_verification",
        webhook_secret=TEST_WEBHOOK_SECRET,
    )
    assert isinstance(real_stripe_adapter, PaymentGatewayPort)

    app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    app.dependency_overrides[get_payment_gateway] = lambda: real_stripe_adapter

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "real_hmac@obsolete.io",
                "username": "hmac_verifier",
                "password": "StrongVaultPassword!23",
            },
        )
        assert reg_resp.status_code == 201
        user_id = reg_resp.json()["user"]["id"]

        bad_hmac_resp = await client.post(
            "/api/v1/webhooks/stripe",
            content=b'{"id":"evt_hmac_1","type":"checkout.session.completed"}',
            headers={"Stripe-Signature": "t=1729872000,v1=deadbeef"},
        )
        assert bad_hmac_resp.status_code == 400
        assert bad_hmac_resp.json()["error_code"] == "INVALID_STRIPE_SIGNATURE"

        valid_event_bytes = json.dumps(
            {
                "id": "evt_real_hmac_777",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_777",
                        "metadata": {"user_id": user_id},
                        "amount_received": 80000,
                    }
                },
            }
        ).encode("utf-8")
        real_sig = _compute_stripe_signature(valid_event_bytes, TEST_WEBHOOK_SECRET)

        async def send_webhook() -> tuple[int, bool]:
            async with AsyncClient(transport=transport, base_url="http://localhost") as wh_client:
                resp = await wh_client.post(
                    "/api/v1/webhooks/stripe",
                    content=valid_event_bytes,
                    headers={"Stripe-Signature": real_sig},
                )
                return resp.status_code, bool(resp.json()["idempotent_replay"])

        results = await asyncio.gather(send_webhook(), send_webhook())
        assert [r[0] for r in results] == [200, 200]
        assert sorted(r[1] for r in results) == [False, True]

    async with session_factory() as verify_session:
        wallet_row = (await verify_session.execute(select(Wallet))).scalar_one()
        assert wallet_row.available_balance == Decimal("800.00")
        events = (await verify_session.execute(select(StripeWebhookEvent))).scalars().all()
        assert len(events) == 1
