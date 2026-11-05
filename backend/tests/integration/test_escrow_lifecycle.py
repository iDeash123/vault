import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from core.clock import FrozenClock
from core.security import create_access_token
from domains.auth.dependencies import get_clock
from domains.bidding.router import get_realtime_broker
from domains.escrow.service import calculate_platform_fee_and_payout, quantize_usd
from main import create_app
from shared.db.models.enums import (
    EscrowOrderStatus,
    LedgerEntryType,
    LotCategory,
    LotStatus,
    UserRole,
    WalletHoldStatus,
)
from shared.db.models.escrow import EscrowOrder
from shared.db.models.lot import Lot
from shared.db.models.user import User
from shared.db.models.wallet import Wallet, WalletHold, WalletLedgerEntry
from shared.db.session import get_db_session


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 27, 14, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_realtime_broker() -> InMemoryRealtimeBrokerAdapter:
    return InMemoryRealtimeBrokerAdapter()


@pytest.fixture
async def escrow_client(
    db_engine: AsyncEngine,
    frozen_clock: FrozenClock,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_realtime_broker

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


async def _create_test_user(
    db_session: AsyncSession,
    username: str,
    available_balance: Decimal = Decimal("5000.00"),
    held_balance: Decimal = Decimal("0.00"),
) -> tuple[User, str]:
    user = User(
        email=f"{username}@obsolete.io",
        username=username,
        password_hash="argon2id$hashed",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    wallet = Wallet(
        user_id=user.id,
        available_balance=available_balance,
        held_balance=held_balance,
        claimable_balance=Decimal("0.00"),
    )
    db_session.add(wallet)
    await db_session.flush()

    token = create_access_token(
        user_id=user.id,
        role=UserRole.MEMBER.value,
        now=datetime(2026, 10, 27, 14, 0, 0, tzinfo=UTC),
    )
    return user, token


async def _setup_escrow_fixture(
    db_session: AsyncSession,
    final_amount: Decimal = Decimal("1000.00"),
    fee_percent: Decimal = Decimal("8.00"),
) -> tuple[User, str, User, str, User, str, Lot, EscrowOrder]:
    seller, seller_token = await _create_test_user(
        db_session,
        f"seller_{uuid.uuid4().hex[:6]}",
        available_balance=Decimal("100.00"),
        held_balance=Decimal("0.00"),
    )
    buyer, buyer_token = await _create_test_user(
        db_session,
        f"buyer_{uuid.uuid4().hex[:6]}",
        available_balance=Decimal("500.00"),
        held_balance=final_amount,
    )
    stranger, stranger_token = await _create_test_user(
        db_session,
        f"stranger_{uuid.uuid4().hex[:6]}",
        available_balance=Decimal("2000.00"),
        held_balance=Decimal("0.00"),
    )

    buyer_wallet_stmt = select(Wallet).where(Wallet.user_id == buyer.id)
    buyer_wallet = (await db_session.execute(buyer_wallet_stmt)).scalar_one()

    now = datetime(2026, 10, 27, 14, 0, 0, tzinfo=UTC)
    lot = Lot(
        seller_id=seller.id,
        category=LotCategory.APPAREL,
        status=LotStatus.ENDED_WON,
        title="Raf Simons Riot Camo Bomber",
        subtitle="AW01 Riot Bomber",
        description="Archival jacket",
        specs={
            "category": "APPAREL",
            "brand": "Raf Simons",
            "season_era": "AW01",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {"chest": 58.0, "shoulders": 50.0, "length": 66.0, "sleeve": 64.0},
            "materials": ["Cotton"],
        },
        start_price=Decimal("500.00"),
        reserve_price=Decimal("800.00"),
        buy_now_price=Decimal("1500.00"),
        current_price=final_amount,
        min_bid_increment=Decimal("50.00"),
        bid_count=3,
        leader_user_id=buyer.id,
        starts_at=now - timedelta(days=2),
        ends_at=now - timedelta(hours=1),
        search_vector=None,
    )
    db_session.add(lot)
    await db_session.flush()

    hold = WalletHold(
        wallet_id=buyer_wallet.id,
        user_id=buyer.id,
        lot_id=lot.id,
        amount=final_amount,
        status=WalletHoldStatus.CAPTURED_TO_ESCROW,
        captured_at=now,
    )
    db_session.add(hold)
    await db_session.flush()

    platform_fee, seller_payout = calculate_platform_fee_and_payout(final_amount, fee_percent)
    order = EscrowOrder(
        lot_id=lot.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        wallet_hold_id=hold.id,
        final_amount=final_amount,
        platform_fee_amount=platform_fee,
        seller_payout_amount=seller_payout,
        status=EscrowOrderStatus.FUNDS_HELD,
    )
    db_session.add(order)
    await db_session.commit()

    return seller, seller_token, buyer, buyer_token, stranger, stranger_token, lot, order


@pytest.mark.asyncio
async def test_escrow_full_happy_path(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, seller_tok, buyer, buyer_tok, _, _, lot, order = await _setup_escrow_fixture(
        db_session,
        final_amount=Decimal("1200.00"),
    )

    buyer_id = buyer.id
    seller_id = seller.id
    lot_id = lot.id

    ship_res = await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={
            "shipping_carrier": "DHL Express",
            "tracking_number": "DHL-9876543210",
        },
    )
    assert ship_res.status_code == 200
    ship_data = ship_res.json()
    assert ship_data["id"] == str(order.id)
    assert ship_data["status"] == "SHIPPED"
    assert ship_data["shipping_carrier"] == "DHL Express"
    assert ship_data["tracking_number"] == "DHL-9876543210"
    assert ship_data["shipped_at"] is not None
    assert "server_time" in ship_data

    buyer_notifs = fake_realtime_broker.get_published_events(f"user:{buyer_id}")
    assert any(
        n.get("event_type") == "ORDER_STATUS_CHANGED" and n.get("status") == "SHIPPED"
        for n in buyer_notifs
    )

    confirm_res = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["status"] == "COMPLETED"
    assert confirm_data["completed_at"] is not None

    buyer_wallet_res = await db_session.execute(
        select(Wallet).where(Wallet.user_id == buyer_id).execution_options(populate_existing=True)
    )
    b_wallet = buyer_wallet_res.scalar_one()
    seller_wallet_res = await db_session.execute(
        select(Wallet).where(Wallet.user_id == seller_id).execution_options(populate_existing=True)
    )
    s_wallet = seller_wallet_res.scalar_one()

    assert quantize_usd(b_wallet.held_balance) == Decimal("0.00")
    assert quantize_usd(s_wallet.available_balance) == Decimal("100.00") + Decimal("1104.00")

    lot_res = await db_session.execute(
        select(Lot).where(Lot.id == lot_id).execution_options(populate_existing=True)
    )
    updated_lot = lot_res.scalar_one()
    assert updated_lot.status == LotStatus.SETTLED

    ledger_res = await db_session.execute(
        select(WalletLedgerEntry).order_by(WalletLedgerEntry.created_at.asc())
    )
    entries = list(ledger_res.scalars().all())
    buyer_release_entries = [
        e for e in entries if e.entry_type == LedgerEntryType.ESCROW_BUYER_RELEASE
    ]
    seller_payout_entries = [
        e for e in entries if e.entry_type == LedgerEntryType.ESCROW_SELLER_PAYOUT
    ]

    assert len(buyer_release_entries) == 1
    assert buyer_release_entries[0].amount == Decimal("1200.00")
    assert buyer_release_entries[0].held_delta == Decimal("-1200.00")
    assert buyer_release_entries[0].user_id == buyer.id

    assert len(seller_payout_entries) == 1
    assert seller_payout_entries[0].amount == Decimal("1104.00")
    assert seller_payout_entries[0].available_delta == Decimal("1104.00")
    assert seller_payout_entries[0].user_id == seller.id


@pytest.mark.asyncio
async def test_escrow_permission_guards(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, seller_tok, _, buyer_tok, _, stranger_tok, _, order = await _setup_escrow_fixture(
        db_session,
    )

    buyer_ship = await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={"shipping_carrier": "FedEx", "tracking_number": "12345"},
    )
    assert buyer_ship.status_code == 403
    assert buyer_ship.json()["error_code"] == "ORDER_SELLER_PERMISSION_DENIED"

    stranger_ship = await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {stranger_tok}"},
        json={"shipping_carrier": "FedEx", "tracking_number": "12345"},
    )
    assert stranger_ship.status_code == 403

    seller_confirm = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {seller_tok}"},
    )
    assert seller_confirm.status_code == 403
    assert seller_confirm.json()["error_code"] == "ORDER_BUYER_PERMISSION_DENIED"

    stranger_confirm = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_confirm.status_code == 403

    seller_dispute = await escrow_client.post(
        f"/api/v1/orders/{order.id}/dispute",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={"dispute_reason": "Seller cannot dispute"},
    )
    assert seller_dispute.status_code == 403
    assert seller_dispute.json()["error_code"] == "ORDER_BUYER_PERMISSION_DENIED"

    unauth_ship = await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        json={"shipping_carrier": "FedEx", "tracking_number": "12345"},
    )
    assert unauth_ship.status_code == 401


@pytest.mark.asyncio
async def test_escrow_invalid_state_transitions(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, seller_tok, _, buyer_tok, _, _, _, order = await _setup_escrow_fixture(
        db_session,
    )

    confirm_before_ship = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert confirm_before_ship.status_code == 409
    assert confirm_before_ship.json()["error_code"] == "INVALID_ORDER_STATUS"

    await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={"shipping_carrier": "UPS", "tracking_number": "UPS-001"},
    )

    double_ship = await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={"shipping_carrier": "UPS", "tracking_number": "UPS-002"},
    )
    assert double_ship.status_code == 409
    assert double_ship.json()["error_code"] == "INVALID_ORDER_STATUS"

    await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )

    double_confirm = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert double_confirm.status_code == 409
    assert double_confirm.json()["error_code"] == "INVALID_ORDER_STATUS"

    dispute_completed = await escrow_client.post(
        f"/api/v1/orders/{order.id}/dispute",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={"dispute_reason": "Order already completed cannot dispute"},
    )
    assert dispute_completed.status_code == 409
    assert dispute_completed.json()["error_code"] == "INVALID_ORDER_STATUS"


@pytest.mark.asyncio
async def test_escrow_dispute_flow(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    _, seller_tok, _, buyer_tok, _, _, _, order = await _setup_escrow_fixture(
        db_session,
    )

    await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={"shipping_carrier": "USPS", "tracking_number": "9400100000000000"},
    )

    dispute_res = await escrow_client.post(
        f"/api/v1/orders/{order.id}/dispute",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={"reason": "Package arrived empty, box was pierced"},
    )
    assert dispute_res.status_code == 200
    dispute_data = dispute_res.json()
    assert dispute_data["status"] == "DISPUTED"
    assert dispute_data["dispute_reason"] == "Package arrived empty, box was pierced"

    seller_notifs = fake_realtime_broker.get_published_events(f"user:{order.seller_id}")
    assert any(
        n.get("event_type") == "ORDER_STATUS_CHANGED" and n.get("status") == "DISPUTED"
        for n in seller_notifs
    )


@pytest.mark.asyncio
async def test_escrow_order_listing_and_filtering(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    (
        _seller,
        seller_tok,
        buyer,
        buyer_tok,
        _,
        stranger_tok,
        lot,
        order,
    ) = await _setup_escrow_fixture(
        db_session,
    )

    buyer_list = await escrow_client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert buyer_list.status_code == 200
    b_data = buyer_list.json()
    assert b_data["total"] >= 1
    assert any(item["id"] == str(order.id) for item in b_data["items"])
    assert b_data["items"][0]["lot_title"] == lot.title
    assert "server_time" in b_data

    seller_list = await escrow_client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {seller_tok}"},
    )
    assert seller_list.status_code == 200
    s_data = seller_list.json()
    assert any(item["id"] == str(order.id) for item in s_data["items"])

    role_buyer_filter = await escrow_client.get(
        "/api/v1/orders?role=buyer",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert role_buyer_filter.status_code == 200
    assert all(item["buyer_id"] == str(buyer.id) for item in role_buyer_filter.json()["items"])

    role_buyer_upper = await escrow_client.get(
        "/api/v1/orders?role=BUYER",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert role_buyer_upper.status_code == 200
    assert all(item["buyer_id"] == str(buyer.id) for item in role_buyer_upper.json()["items"])

    role_seller_filter = await escrow_client.get(
        "/api/v1/orders?role=seller",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert role_seller_filter.status_code == 200
    assert len(role_seller_filter.json()["items"]) == 0

    role_seller_upper = await escrow_client.get(
        "/api/v1/orders?role=SELLER",
        headers={"Authorization": f"Bearer {seller_tok}"},
    )
    assert role_seller_upper.status_code == 200
    assert any(item["id"] == str(order.id) for item in role_seller_upper.json()["items"])

    status_filter = await escrow_client.get(
        "/api/v1/orders?status=COMPLETED",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert status_filter.status_code == 200
    assert len(status_filter.json()["items"]) == 0

    stranger_list = await escrow_client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_list.status_code == 200
    assert not any(item["id"] == str(order.id) for item in stranger_list.json()["items"])

    order_detail = await escrow_client.get(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert order_detail.status_code == 200
    assert order_detail.json()["id"] == str(order.id)

    stranger_detail = await escrow_client.get(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_detail.status_code == 403


@pytest.mark.asyncio
async def test_escrow_invalid_hold_status_on_confirm(
    escrow_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, seller_tok, _, buyer_tok, _, _, _, order = await _setup_escrow_fixture(
        db_session,
    )

    await escrow_client.post(
        f"/api/v1/orders/{order.id}/ship",
        headers={"Authorization": f"Bearer {seller_tok}"},
        json={"shipping_carrier": "UPS", "tracking_number": "UPS-777"},
    )

    hold_stmt = select(WalletHold).where(WalletHold.id == order.wallet_hold_id)
    hold = (await db_session.execute(hold_stmt)).scalar_one()
    hold.status = WalletHoldStatus.CLAIMABLE
    await db_session.commit()

    confirm_res = await escrow_client.post(
        f"/api/v1/orders/{order.id}/confirm-receipt",
        headers={"Authorization": f"Bearer {buyer_tok}"},
    )
    assert confirm_res.status_code == 409
    assert confirm_res.json()["error_code"] == "INVALID_HOLD_STATUS"
