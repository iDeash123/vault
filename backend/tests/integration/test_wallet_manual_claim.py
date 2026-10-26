import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.payment_fake import InMemoryPaymentGatewayAdapter
from core.clock import FrozenClock
from core.exceptions import ConflictError, DomainError
from domains.auth.dependencies import get_clock
from domains.wallet.router import get_payment_gateway
from domains.wallet.service import WalletService
from main import create_app
from shared.db.models.enums import (
    LedgerEntryType,
    LotCategory,
    LotStatus,
    UserRole,
    WalletHoldStatus,
)
from shared.db.models.lot import Lot
from shared.db.models.user import User
from shared.db.models.wallet import Wallet, WalletLedgerEntry
from shared.db.session import get_db_session

TEST_WEBHOOK_SECRET = "whsec_slice_3_3_manual_claim_secret"


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_payment_gateway() -> InMemoryPaymentGatewayAdapter:
    return InMemoryPaymentGatewayAdapter(webhook_secret=TEST_WEBHOOK_SECRET)


@pytest.fixture
async def claim_api_client(
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


async def _register_and_topup(
    client: AsyncClient,
    fake_gateway: InMemoryPaymentGatewayAdapter,
    email: str,
    username: str,
    amount_usd: str,
) -> tuple[str, uuid.UUID]:
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "StrongVaultPassword!23",
        },
    )
    assert reg_resp.status_code == 201
    token = str(reg_resp.json()["access_token"])
    user_id = uuid.UUID(str(reg_resp.json()["user"]["id"]))

    if Decimal(amount_usd) > Decimal("0.00"):
        checkout_resp = await client.post(
            "/api/v1/wallet/topup/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount_usd": amount_usd},
        )
        assert checkout_resp.status_code == 200
        session_id = str(checkout_resp.json()["session_id"])
        event_payload = fake_gateway.simulate_checkout_completed(session_id)
        wh_resp = await client.post(
            "/api/v1/webhooks/stripe",
            content=json.dumps(event_payload).encode("utf-8"),
            headers={"Stripe-Signature": TEST_WEBHOOK_SECRET},
        )
        assert wh_resp.status_code == 200

    return token, user_id


async def _create_live_lot(
    session: AsyncSession,
    title: str = "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
) -> Lot:
    seller = User(
        email=f"seller_{uuid.uuid4().hex[:8]}@obsolete.io",
        username=f"seller_{uuid.uuid4().hex[:8]}",
        password_hash="argon2id$seller",
        role=UserRole.MEMBER,
        is_active=True,
    )
    session.add(seller)
    await session.flush()

    now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    lot = Lot(
        seller_id=seller.id,
        category=LotCategory.APPAREL,
        status=LotStatus.LIVE,
        title=title,
        subtitle="Archival museum piece",
        description="Full provenance documented.",
        specs={
            "category": "APPAREL",
            "brand": "Raf Simons",
            "season_era": "AW01",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 62.0,
                "shoulders": 54.0,
                "length": 71.0,
                "sleeve": 66.0,
            },
            "materials": ["100% Cotton"],
        },
        start_price=Decimal("200.00"),
        reserve_price=Decimal("400.00"),
        buy_now_price=Decimal("900.00"),
        min_bid_increment=Decimal("25.00"),
        current_price=Decimal("200.00"),
        bid_count=0,
        anti_snipe_extensions_count=0,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=24),
    )
    session.add(lot)
    await session.commit()
    await session.refresh(lot)
    return lot


@pytest.mark.asyncio
async def test_outbid_hold_becomes_claimable_and_manual_claim_restores_available_balance(
    claim_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    token_a, user_a_id = await _register_and_topup(
        claim_api_client,
        fake_payment_gateway,
        "bidder_a@obsolete.io",
        "bidder_a",
        "420.00",
    )
    lot = await _create_live_lot(db_session)
    service = WalletService(
        session=db_session,
        clock=frozen_clock,
        payment_gateway=fake_payment_gateway,
    )

    hold_a = await service.lock_funds_for_bid(
        user_id=user_a_id,
        lot_id=lot.id,
        amount=Decimal("300.00"),
        idempotency_key="bid_lock_a_1",
    )
    await db_session.commit()
    assert hold_a.status == WalletHoldStatus.ACTIVE_HOLD

    idempotent_replay_hold = await service.lock_funds_for_bid(
        user_id=user_a_id,
        lot_id=lot.id,
        amount=Decimal("300.00"),
        idempotency_key="bid_lock_a_1",
    )
    assert idempotent_replay_hold.id == hold_a.id

    with pytest.raises(ConflictError) as conflict_exc:
        await service.lock_funds_for_bid(
            user_id=user_a_id,
            lot_id=lot.id,
            amount=Decimal("350.00"),
            idempotency_key="bid_lock_a_1",
        )
    assert conflict_exc.value.error_code == "IDEMPOTENCY_KEY_CONFLICT"

    frozen_clock.set_time(frozen_clock.now() + timedelta(minutes=2))
    outbid_hold = await service.transition_hold_to_claimable(
        hold_id=hold_a.id,
        entry_type=LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
    )
    await db_session.commit()
    assert outbid_hold.status == WalletHoldStatus.CLAIMABLE
    assert outbid_hold.outbid_at == frozen_clock.now()

    summary_before_claim = (
        await claim_api_client.get(
            "/api/v1/wallet",
            headers={"Authorization": f"Bearer {token_a}"},
        )
    ).json()
    assert summary_before_claim["available_balance"] == "120.00"
    assert summary_before_claim["held_balance"] == "0.00"
    assert summary_before_claim["claimable_balance"] == "300.00"

    with pytest.raises(DomainError) as insuff_exc:
        await service.lock_funds_for_bid(
            user_id=user_a_id,
            lot_id=lot.id,
            amount=Decimal("250.00"),
            idempotency_key="bid_lock_a_2_fail",
        )
    assert insuff_exc.value.error_code == "INSUFFICIENT_AVAILABLE_BALANCE"
    assert insuff_exc.value.details == {
        "available_balance": "120.00",
        "claimable_balance": "300.00",
        "required_amount": "250.00",
    }
    assert "300.00 USD in claimable outbid holds" in insuff_exc.value.message

    frozen_clock.set_time(frozen_clock.now() + timedelta(minutes=1))
    claim_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{hold_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert claim_resp.status_code == 200
    claim_data = claim_resp.json()
    assert claim_data["claimed_amount"] == "300.00"
    assert claim_data["available_balance"] == "420.00"
    assert claim_data["held_balance"] == "0.00"
    assert claim_data["claimable_balance"] == "0.00"
    assert claim_data["hold"]["id"] == str(hold_a.id)
    assert claim_data["hold"]["status"] == "CLAIMED"
    assert claim_data["hold"]["claimed_at"] is not None
    assert claim_data["server_time"] == frozen_clock.now().isoformat().replace("+00:00", "Z")

    duplicate_claim_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{hold_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert duplicate_claim_resp.status_code == 409
    assert duplicate_claim_resp.json()["error_code"] == "HOLD_ALREADY_CLAIMED"

    wallet_row = (
        await db_session.execute(select(Wallet).where(Wallet.user_id == user_a_id))
    ).scalar_one()
    assert wallet_row.available_balance == Decimal("420.00")
    assert wallet_row.held_balance == Decimal("0.00")
    assert wallet_row.claimable_balance == Decimal("0.00")

    ledger_rows = (
        (
            await db_session.execute(
                select(WalletLedgerEntry)
                .where(WalletLedgerEntry.wallet_id == wallet_row.id)
                .order_by(WalletLedgerEntry.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [e.entry_type for e in ledger_rows] == [
        LedgerEntryType.STRIPE_TOPUP,
        LedgerEntryType.BID_LOCK,
        LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
        LedgerEntryType.BID_MANUAL_CLAIM,
    ]
    assert sum((Decimal(e.available_delta) for e in ledger_rows), Decimal("0.00")) == Decimal(
        "420.00"
    )
    assert sum((Decimal(e.held_delta) for e in ledger_rows), Decimal("0.00")) == Decimal("0.00")
    assert sum((Decimal(e.claimable_delta) for e in ledger_rows), Decimal("0.00")) == Decimal(
        "0.00"
    )


@pytest.mark.asyncio
async def test_claim_all_holds_claims_multiple_outbid_holds_leaving_active_hold_intact(
    claim_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    token, user_id = await _register_and_topup(
        claim_api_client,
        fake_payment_gateway,
        "multi_bidder@obsolete.io",
        "multi_bidder",
        "1500.00",
    )
    lot = await _create_live_lot(db_session, title="Roland TR-808 Rhythm Composer")
    service = WalletService(
        session=db_session,
        clock=frozen_clock,
        payment_gateway=fake_payment_gateway,
    )

    hold_1 = await service.lock_funds_for_bid(
        user_id=user_id,
        lot_id=lot.id,
        amount=Decimal("300.00"),
        idempotency_key="multi_lock_1",
    )
    await service.transition_hold_to_claimable(hold_id=hold_1.id)

    hold_2 = await service.lock_funds_for_bid(
        user_id=user_id,
        lot_id=lot.id,
        amount=Decimal("400.00"),
        idempotency_key="multi_lock_2",
    )
    await service.transition_hold_to_claimable(hold_id=hold_2.id)

    hold_3_active = await service.lock_funds_for_bid(
        user_id=user_id,
        lot_id=lot.id,
        amount=Decimal("500.00"),
        idempotency_key="multi_lock_3",
    )
    await db_session.commit()
    assert hold_3_active.status == WalletHoldStatus.ACTIVE_HOLD

    pre_summary = (
        await claim_api_client.get(
            "/api/v1/wallet",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    assert pre_summary["available_balance"] == "300.00"
    assert pre_summary["held_balance"] == "500.00"
    assert pre_summary["claimable_balance"] == "700.00"
    assert len(pre_summary["holds"]) == 3

    claim_all_resp = await claim_api_client.post(
        "/api/v1/wallet/claims/claim-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert claim_all_resp.status_code == 200
    claim_all_data = claim_all_resp.json()
    assert claim_all_data["claimed_count"] == 2
    assert claim_all_data["claimed_amount"] == "700.00"
    assert set(claim_all_data["claimed_hold_ids"]) == {str(hold_1.id), str(hold_2.id)}
    assert claim_all_data["available_balance"] == "1000.00"
    assert claim_all_data["held_balance"] == "500.00"
    assert claim_all_data["claimable_balance"] == "0.00"

    empty_claim_all_resp = await claim_api_client.post(
        "/api/v1/wallet/claims/claim-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert empty_claim_all_resp.status_code == 200
    assert empty_claim_all_resp.json()["claimed_count"] == 0
    assert empty_claim_all_resp.json()["claimed_amount"] == "0.00"


@pytest.mark.asyncio
async def test_manual_claim_rejects_foreign_hold_active_hold_and_unknown_hold(
    claim_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    token_owner, owner_id = await _register_and_topup(
        claim_api_client,
        fake_payment_gateway,
        "owner@obsolete.io",
        "hold_owner",
        "600.00",
    )
    token_stranger, _ = await _register_and_topup(
        claim_api_client,
        fake_payment_gateway,
        "stranger@obsolete.io",
        "stranger_user",
        "100.00",
    )
    lot = await _create_live_lot(db_session)
    service = WalletService(
        session=db_session,
        clock=frozen_clock,
        payment_gateway=fake_payment_gateway,
    )

    active_hold = await service.lock_funds_for_bid(
        user_id=owner_id,
        lot_id=lot.id,
        amount=Decimal("250.00"),
        idempotency_key="guard_lock_1",
    )
    await db_session.commit()

    active_claim_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{active_hold.id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert active_claim_resp.status_code == 409
    assert active_claim_resp.json()["error_code"] == "HOLD_NOT_CLAIMABLE"

    await service.transition_hold_to_claimable(hold_id=active_hold.id)
    await db_session.commit()

    foreign_claim_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{active_hold.id}",
        headers={"Authorization": f"Bearer {token_stranger}"},
    )
    assert foreign_claim_resp.status_code == 403
    assert foreign_claim_resp.json()["error_code"] == "HOLD_OWNERSHIP_MISMATCH"

    not_found_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error_code"] == "HOLD_NOT_FOUND"


@pytest.mark.asyncio
async def test_bid_lock_and_claimable_transition_boundary_and_error_paths(
    claim_api_client: AsyncClient,
    fake_payment_gateway: InMemoryPaymentGatewayAdapter,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    token_owner, owner_id = await _register_and_topup(
        claim_api_client,
        fake_payment_gateway,
        "boundary_owner@obsolete.io",
        "boundary_owner",
        "800.00",
    )
    lot = await _create_live_lot(db_session, title="Leica M6 TTL Titanium")
    service = WalletService(
        session=db_session,
        clock=frozen_clock,
        payment_gateway=fake_payment_gateway,
    )

    with pytest.raises(DomainError) as empty_key_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key="   ",
        )
    assert empty_key_exc.value.error_code == "INVALID_IDEMPOTENCY_KEY"

    with pytest.raises(DomainError) as overlong_key_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key="k" * 129,
        )
    assert overlong_key_exc.value.error_code == "INVALID_IDEMPOTENCY_KEY"

    with pytest.raises(DomainError) as zero_amt_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("0.00"),
            idempotency_key="zero_amt_key",
        )
    assert zero_amt_exc.value.error_code == "INVALID_BID_AMOUNT"

    with pytest.raises(DomainError) as subcent_amt_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.005"),
            idempotency_key="subcent_amt_key",
        )
    assert subcent_amt_exc.value.error_code == "INVALID_BID_AMOUNT"

    with pytest.raises(DomainError) as nan_amt_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("NaN"),
            idempotency_key="nan_amt_key",
        )
    assert nan_amt_exc.value.error_code == "INVALID_BID_AMOUNT"

    with pytest.raises(DomainError) as bad_type_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key="bad_type_key",
            entry_type=LedgerEntryType.STRIPE_TOPUP,
        )
    assert bad_type_exc.value.error_code == "INVALID_LEDGER_ENTRY_TYPE"

    first_hold = await service.lock_funds_for_bid(
        user_id=owner_id,
        lot_id=lot.id,
        amount=Decimal("200.00"),
        idempotency_key="valid_lock_1",
    )
    await db_session.commit()

    with pytest.raises(ConflictError) as entry_type_conflict_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key="valid_lock_1",
            entry_type=LedgerEntryType.BUY_NOW_LOCK,
        )
    assert entry_type_conflict_exc.value.error_code == "IDEMPOTENCY_KEY_CONFLICT"

    with pytest.raises(ConflictError) as active_conflict_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("250.00"),
            idempotency_key="conflicting_active_lock_2",
        )
    assert active_conflict_exc.value.error_code == "ACTIVE_HOLD_ALREADY_EXISTS"

    with pytest.raises(DomainError) as bad_transition_key_exc:
        await service.transition_hold_to_claimable(
            hold_id=first_hold.id,
            idempotency_key="   ",
        )
    assert bad_transition_key_exc.value.error_code == "INVALID_IDEMPOTENCY_KEY"

    with pytest.raises(DomainError) as bad_transition_type_exc:
        await service.transition_hold_to_claimable(
            hold_id=first_hold.id,
            entry_type=LedgerEntryType.BID_MANUAL_CLAIM,
        )
    assert bad_transition_type_exc.value.error_code == "INVALID_LEDGER_ENTRY_TYPE"

    released_hold = await service.transition_hold_to_claimable(
        hold_id=first_hold.id,
        entry_type=LedgerEntryType.BID_RELEASED_TO_CLAIMABLE,
    )
    await db_session.commit()
    assert released_hold.status == WalletHoldStatus.CLAIMABLE

    with pytest.raises(ConflictError) as cross_op_transition_conflict_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key=f"hold_to_claimable:{first_hold.id}",
        )
    assert cross_op_transition_conflict_exc.value.error_code == "IDEMPOTENCY_KEY_CONFLICT"

    with pytest.raises(ConflictError) as double_transition_exc:
        await service.transition_hold_to_claimable(hold_id=first_hold.id)
    assert double_transition_exc.value.error_code == "INVALID_HOLD_STATE"

    claim_resp = await claim_api_client.post(
        f"/api/v1/wallet/claims/{first_hold.id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["available_balance"] == "800.00"
    assert claim_resp.json()["claimable_balance"] == "0.00"

    with pytest.raises(ConflictError) as cross_op_claim_conflict_exc:
        await service.lock_funds_for_bid(
            user_id=owner_id,
            lot_id=lot.id,
            amount=Decimal("200.00"),
            idempotency_key=f"manual_claim:{first_hold.id}",
        )
    assert cross_op_claim_conflict_exc.value.error_code == "IDEMPOTENCY_KEY_CONFLICT"
