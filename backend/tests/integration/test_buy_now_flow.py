import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from core.clock import FrozenClock
from core.security import create_access_token
from domains.auth.dependencies import get_clock
from domains.bidding.repository import BiddingRepository
from domains.bidding.router import get_realtime_broker
from main import create_app
from shared.db.models.bid import Bid
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
    return FrozenClock(datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_realtime_broker() -> InMemoryRealtimeBrokerAdapter:
    return InMemoryRealtimeBrokerAdapter()


@pytest.fixture
async def buy_now_client(
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


async def _create_user_with_wallet(
    db_session: AsyncSession,
    username: str,
    available_balance: Decimal = Decimal("5000.00"),
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
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    db_session.add(wallet)
    await db_session.flush()

    token = create_access_token(
        user_id=user.id,
        role=UserRole.MEMBER.value,
        now=datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC),
    )
    return user, token


async def _create_buy_now_lot(
    db_session: AsyncSession,
    seller_id: uuid.UUID,
    start_price: Decimal = Decimal("200.00"),
    reserve_price: Decimal | None = Decimal("500.00"),
    buy_now_price: Decimal | None = Decimal("1000.00"),
    min_bid_increment: Decimal = Decimal("25.00"),
    current_price: Decimal = Decimal("200.00"),
    bid_count: int = 0,
    status: LotStatus = LotStatus.LIVE,
) -> Lot:
    now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    lot = Lot(
        seller_id=seller_id,
        category=LotCategory.APPAREL,
        status=status,
        title="Undercover AW02 Witchs Cell Division Velvet Jacket",
        subtitle="Archival Jun Takahashi grail",
        description="Pristine condition with velvet trim and skull crossbones embroidery.",
        specs={
            "category": "APPAREL",
            "brand": "Undercover",
            "season_era": "AW02 Witchs Cell Division",
            "tagged_size": "M",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 52.0,
                "shoulders": 44.0,
                "length": 68.0,
                "sleeve": 63.0,
            },
            "materials": ["100% Cotton Velvet"],
        },
        start_price=start_price,
        reserve_price=reserve_price,
        buy_now_price=buy_now_price,
        min_bid_increment=min_bid_increment,
        current_price=current_price,
        bid_count=bid_count,
        anti_snipe_extensions_count=0,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=3),
    )
    db_session.add(lot)
    await db_session.commit()
    return lot


@pytest.mark.asyncio
async def test_successful_buy_now_without_prior_bids(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_1")
    lot = await _create_buy_now_lot(db_session, seller.id)
    buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_1",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    key = f"buy-now-key-{uuid.uuid4().hex}"
    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()

    assert data["lot_id"] == str(lot.id)
    assert data["buyer_id"] == str(buyer.id)
    assert data["seller_id"] == str(seller.id)
    assert data["amount"] == "1000.00"
    assert data["platform_fee_amount"] == "80.00"
    assert data["seller_payout_amount"] == "920.00"
    assert data["lot_status"] == LotStatus.ENDED_WON.value
    assert data["order_status"] == EscrowOrderStatus.FUNDS_HELD.value

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        lot_res = await verify_session.execute(select(Lot).where(Lot.id == lot.id))
        db_lot = lot_res.scalar_one()
        assert db_lot.status == LotStatus.ENDED_WON
        assert db_lot.current_price == Decimal("1000.00")
        assert db_lot.leader_user_id == buyer.id
        assert db_lot.bid_count == 1

        order_res = await verify_session.execute(
            select(EscrowOrder).where(EscrowOrder.lot_id == lot.id)
        )
        db_order = order_res.scalar_one()
        assert db_order.id == uuid.UUID(data["order_id"])
        assert db_order.buyer_id == buyer.id
        assert db_order.seller_id == seller.id
        assert db_order.final_amount == Decimal("1000.00")
        assert db_order.platform_fee_amount == Decimal("80.00")
        assert db_order.seller_payout_amount == Decimal("920.00")
        assert db_order.status == EscrowOrderStatus.FUNDS_HELD

        hold_res = await verify_session.execute(
            select(WalletHold).where(WalletHold.id == uuid.UUID(data["wallet_hold_id"]))
        )
        db_hold = hold_res.scalar_one()
        assert db_hold.status == WalletHoldStatus.CAPTURED_TO_ESCROW
        assert db_hold.amount == Decimal("1000.00")
        assert db_hold.user_id == buyer.id

        w_res = await verify_session.execute(select(Wallet).where(Wallet.user_id == buyer.id))
        db_w = w_res.scalar_one()
        assert db_w.available_balance == Decimal("1000.00")
        assert db_w.held_balance == Decimal("1000.00")
        assert db_w.claimable_balance == Decimal("0.00")

        ledger_res = await verify_session.execute(
            select(WalletLedgerEntry).where(WalletLedgerEntry.user_id == buyer.id)
        )
        entries = ledger_res.scalars().all()
        assert len(entries) == 1
        assert entries[0].entry_type == LedgerEntryType.BUY_NOW_LOCK
        assert entries[0].amount == Decimal("1000.00")

    lot_events = fake_realtime_broker.get_published_events(f"lot:{lot.id}")
    lot_types = [e["event_type"] for e in lot_events]
    assert "LOT_SOLD" in lot_types

    buyer_events = fake_realtime_broker.get_published_events(f"user:{buyer.id}")
    buyer_types = [e["event_type"] for e in buyer_events]
    assert "LOT_WON" in buyer_types


@pytest.mark.asyncio
async def test_successful_buy_now_with_pre_reserve_bid_transitions_old_hold_to_claimable(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_2")
    lot = await _create_buy_now_lot(db_session, seller.id)
    bidder1, token1 = await _create_user_with_wallet(
        db_session,
        "bidder_buynow_2",
        available_balance=Decimal("1000.00"),
    )
    buyer, token_buyer = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_2",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    bid_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token1}", "Idempotency-Key": "bid-1-key"},
        json={"amount": "250.00"},
    )
    assert bid_resp.status_code == 201
    assert bid_resp.json()["is_buy_now_available"] is True

    buy_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token_buyer}",
            "Idempotency-Key": "buy-now-key-2",
        },
    )
    assert buy_resp.status_code == 200

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        bidder1_holds_res = await verify_session.execute(
            select(WalletHold).where(
                WalletHold.lot_id == lot.id,
                WalletHold.user_id == bidder1.id,
            )
        )
        bidder1_hold = bidder1_holds_res.scalar_one()
        assert bidder1_hold.status == WalletHoldStatus.CLAIMABLE
        assert bidder1_hold.amount == Decimal("250.00")
        assert bidder1_hold.outbid_at is not None

        bidder1_wallet_res = await verify_session.execute(
            select(Wallet).where(Wallet.user_id == bidder1.id)
        )
        b1_wallet = bidder1_wallet_res.scalar_one()
        assert b1_wallet.available_balance == Decimal("750.00")
        assert b1_wallet.held_balance == Decimal("0.00")
        assert b1_wallet.claimable_balance == Decimal("250.00")

        buyer_hold_res = await verify_session.execute(
            select(WalletHold).where(
                WalletHold.lot_id == lot.id,
                WalletHold.user_id == buyer.id,
            )
        )
        b_hold = buyer_hold_res.scalar_one()
        assert b_hold.status == WalletHoldStatus.CAPTURED_TO_ESCROW
        assert b_hold.amount == Decimal("1000.00")

    b1_events = fake_realtime_broker.get_published_events(f"user:{bidder1.id}")
    b1_types = [e["event_type"] for e in b1_events]
    assert "HOLD_BECAME_CLAIMABLE" in b1_types


@pytest.mark.asyncio
async def test_buy_now_rejected_when_bid_meets_or_exceeds_reserve_price(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_3")
    lot = await _create_buy_now_lot(
        db_session,
        seller.id,
        reserve_price=Decimal("500.00"),
        buy_now_price=Decimal("1000.00"),
    )
    _bidder, token_bidder = await _create_user_with_wallet(
        db_session,
        "bidder_buynow_3",
        available_balance=Decimal("2000.00"),
    )
    _buyer, token_buyer = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_3",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    bid_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token_bidder}", "Idempotency-Key": "bid-reserve-key"},
        json={"amount": "500.00"},
    )
    assert bid_resp.status_code == 201
    assert bid_resp.json()["is_reserve_met"] is True
    assert bid_resp.json()["is_buy_now_available"] is False

    buy_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token_buyer}",
            "Idempotency-Key": "buynow-after-reserve",
        },
    )
    assert buy_resp.status_code == 409
    assert buy_resp.json()["error_code"] == "BUY_NOW_UNAVAILABLE"


@pytest.mark.asyncio
async def test_buy_now_rejected_when_bid_approaches_buy_now_within_increment(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_4")
    lot = await _create_buy_now_lot(
        db_session,
        seller.id,
        start_price=Decimal("200.00"),
        reserve_price=Decimal("800.00"),
        buy_now_price=Decimal("400.00"),
        min_bid_increment=Decimal("50.00"),
    )
    _bidder, token_bidder = await _create_user_with_wallet(
        db_session,
        "bidder_buynow_4",
        available_balance=Decimal("2000.00"),
    )
    _buyer, token_buyer = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_4",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    bid_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token_bidder}", "Idempotency-Key": "bid-near-key"},
        json={"amount": "360.00"},
    )
    assert bid_resp.status_code == 201
    assert bid_resp.json()["is_buy_now_available"] is False

    buy_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token_buyer}",
            "Idempotency-Key": "buynow-near-ceiling",
        },
    )
    assert buy_resp.status_code == 409
    assert buy_resp.json()["error_code"] == "BUY_NOW_UNAVAILABLE"


@pytest.mark.asyncio
async def test_buy_now_forbidden_for_seller(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, token_seller = await _create_user_with_wallet(db_session, "seller_buynow_self")
    lot = await _create_buy_now_lot(db_session, seller.id)
    await db_session.commit()

    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token_seller}",
            "Idempotency-Key": "seller-buynow-key",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "SELF_BIDDING_FORBIDDEN"


@pytest.mark.asyncio
async def test_buy_now_rejected_for_insufficient_available_balance(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_broke")
    lot = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1000.00"))
    _buyer, token_buyer = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_broke",
        available_balance=Decimal("300.00"),
    )
    await db_session.commit()

    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token_buyer}",
            "Idempotency-Key": "broke-buynow-key",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INSUFFICIENT_AVAILABLE_BALANCE"


@pytest.mark.asyncio
async def test_buy_now_idempotency_returns_same_order(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_idem")
    lot = await _create_buy_now_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_idem",
        available_balance=Decimal("3000.00"),
    )
    await db_session.commit()

    key = f"idem-buynow-key-{uuid.uuid4().hex}"

    resp1 = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1["order_id"] == data2["order_id"]
    assert data1["bid_id"] == data2["bid_id"]
    assert data1["amount"] == data2["amount"]

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        orders_res = await verify_session.execute(
            select(EscrowOrder).where(EscrowOrder.lot_id == lot.id)
        )
        orders = orders_res.scalars().all()
        assert len(orders) == 1

        bids_res = await verify_session.execute(select(Bid).where(Bid.lot_id == lot.id))
        bids = bids_res.scalars().all()
        assert len(bids) == 1
        assert bids[0].is_buy_now is True


@pytest.mark.asyncio
async def test_buy_now_missing_idempotency_key_rejected(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_nokey")
    lot = await _create_buy_now_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_buynow_nokey")
    await db_session.commit()

    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.asyncio
async def test_concurrent_competing_buyers_buy_now_race(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_compete")
    lot = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1200.00"))
    buyers: list[tuple[User, str]] = []
    for idx in range(3):
        u, tok = await _create_user_with_wallet(
            db_session,
            f"buyer_compete_{idx}",
            available_balance=Decimal("2000.00"),
        )
        buyers.append((u, tok))
    await db_session.commit()

    async def execute_buy(token: str, key_suffix: str) -> tuple[int, dict[str, Any]]:
        resp = await buy_now_client.post(
            f"/api/v1/lots/{lot.id}/buy-now",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"compete-key-{key_suffix}-{uuid.uuid4().hex[:6]}",
            },
        )
        return resp.status_code, resp.json()

    results = await asyncio.gather(
        execute_buy(buyers[0][1], "0"),
        execute_buy(buyers[1][1], "1"),
        execute_buy(buyers[2][1], "2"),
    )

    status_codes = [r[0] for r in results]
    assert status_codes.count(200) == 1
    assert status_codes.count(409) == 2

    winning_resp = next(r[1] for r in results if r[0] == 200)
    winner_buyer_id = uuid.UUID(winning_resp["buyer_id"])

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        orders_res = await verify_session.execute(
            select(EscrowOrder).where(EscrowOrder.lot_id == lot.id)
        )
        orders = orders_res.scalars().all()
        assert len(orders) == 1
        assert orders[0].buyer_id == winner_buyer_id
        assert orders[0].final_amount == Decimal("1200.00")

        lot_res = await verify_session.execute(select(Lot).where(Lot.id == lot.id))
        db_lot = lot_res.scalar_one()
        assert db_lot.status == LotStatus.ENDED_WON
        assert db_lot.leader_user_id == winner_buyer_id

        for u, _ in buyers:
            w_res = await verify_session.execute(select(Wallet).where(Wallet.user_id == u.id))
            w = w_res.scalar_one()
            if u.id == winner_buyer_id:
                assert w.available_balance == Decimal("800.00")
                assert w.held_balance == Decimal("1200.00")
            else:
                assert w.available_balance == Decimal("2000.00")
                assert w.held_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_buy_now_race(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_samekey")
    lot = await _create_buy_now_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_samekey",
        available_balance=Decimal("3000.00"),
    )
    await db_session.commit()

    shared_key = f"buy-now-same-key-{uuid.uuid4().hex}"

    async def call_buy_now() -> tuple[int, dict[str, Any]]:
        resp = await buy_now_client.post(
            f"/api/v1/lots/{lot.id}/buy-now",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": shared_key},
        )
        return resp.status_code, resp.json()

    results = await asyncio.gather(call_buy_now(), call_buy_now(), call_buy_now())

    assert [r[0] for r in results] == [200, 200, 200]
    order_ids = {r[1]["order_id"] for r in results}
    bid_ids = {r[1]["bid_id"] for r in results}
    assert len(order_ids) == 1
    assert len(bid_ids) == 1

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        orders_res = await verify_session.execute(
            select(EscrowOrder).where(EscrowOrder.lot_id == lot.id)
        )
        assert len(orders_res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_buy_now_by_current_pre_reserve_leader(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_leader_buynow")
    lot = await _create_buy_now_lot(
        db_session,
        seller.id,
        start_price=Decimal("200.00"),
        reserve_price=Decimal("600.00"),
        buy_now_price=Decimal("1000.00"),
    )
    buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_leader_buynow",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    bid_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "pre-buy-bid-key"},
        json={"amount": "300.00"},
    )
    assert bid_resp.status_code == 201

    buy_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "self-lead-buynow"},
    )
    assert buy_resp.status_code == 200

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        holds_res = await verify_session.execute(
            select(WalletHold)
            .where(WalletHold.lot_id == lot.id)
            .order_by(WalletHold.created_at.asc())
        )
        holds = holds_res.scalars().all()
        assert len(holds) == 2
        assert holds[0].status == WalletHoldStatus.CLAIMABLE
        assert holds[0].amount == Decimal("300.00")
        assert holds[0].outbid_at is not None
        assert holds[1].status == WalletHoldStatus.CAPTURED_TO_ESCROW
        assert holds[1].amount == Decimal("1000.00")

        w_res = await verify_session.execute(select(Wallet).where(Wallet.user_id == buyer.id))
        w = w_res.scalar_one()
        assert w.available_balance == Decimal("700.00")
        assert w.held_balance == Decimal("1000.00")
        assert w.claimable_balance == Decimal("300.00")

    buyer_events = fake_realtime_broker.get_published_events(f"user:{buyer.id}")
    event_types = [e["event_type"] for e in buyer_events]
    assert "HOLD_BECAME_CLAIMABLE" in event_types
    assert "LOT_WON" in event_types


@pytest.mark.asyncio
async def test_idempotency_key_cross_endpoint_conflict(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_cross_idem")
    lot = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1000.00"))
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_cross_idem",
        available_balance=Decimal("3000.00"),
    )
    await db_session.commit()

    key = f"cross-key-{uuid.uuid4().hex}"
    buy_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert buy_resp.status_code == 200

    bid_resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"amount": "1000.00"},
    )
    assert bid_resp.status_code == 409
    assert bid_resp.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_buy_now_ws_events_strict_contract_validation(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_ws_contract")
    lot = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1500.00"))
    buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_ws_contract",
        available_balance=Decimal("3000.00"),
    )
    await db_session.commit()

    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"ws-contract-key-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 200

    lot_events = fake_realtime_broker.get_published_events(f"lot:{lot.id}")
    sold_event = next(e for e in lot_events if e["event_type"] == "LOT_SOLD")
    assert set(sold_event.keys()) == {
        "event_type",
        "lot_id",
        "winner_user_id",
        "final_price",
        "via_buy_now",
        "server_time",
    }
    assert sold_event["lot_id"] == str(lot.id)
    assert sold_event["winner_user_id"] == str(buyer.id)
    assert sold_event["final_price"] == "1500.00"
    assert sold_event["via_buy_now"] is True

    buyer_events = fake_realtime_broker.get_published_events(f"user:{buyer.id}")
    won_event = next(e for e in buyer_events if e["event_type"] == "LOT_WON")
    assert set(won_event.keys()) == {
        "event_type",
        "lot_id",
        "order_id",
        "final_amount",
        "server_time",
    }
    assert won_event["lot_id"] == str(lot.id)
    assert won_event["final_amount"] == "1500.00"


@pytest.mark.asyncio
async def test_buy_now_cross_lot_idempotency_conflict(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_cross_lot_buynow")
    lot1 = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1000.00"))
    lot2 = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1200.00"))
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_cross_lot_buynow",
        available_balance=Decimal("5000.00"),
    )
    await db_session.commit()

    key = f"cross-lot-buynow-{uuid.uuid4().hex}"
    resp1 = await buy_now_client.post(
        f"/api/v1/lots/{lot1.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp1.status_code == 200

    resp2 = await buy_now_client.post(
        f"/api/v1/lots/{lot2.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_buy_now_with_maximum_length_idempotency_key(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_maxlen")
    lot = await _create_buy_now_lot(
        db_session,
        seller.id,
        start_price=Decimal("100.00"),
        reserve_price=Decimal("500.00"),
        buy_now_price=Decimal("1000.00"),
    )
    _bidder, token_bidder = await _create_user_with_wallet(
        db_session,
        "bidder_buynow_maxlen",
        available_balance=Decimal("2000.00"),
    )
    _buyer, token_buyer = await _create_user_with_wallet(
        db_session,
        "buyer_buynow_maxlen",
        available_balance=Decimal("3000.00"),
    )
    await db_session.commit()

    bid_key_128 = "bid128_" + "a" * 121
    buy_key_128 = "buy128_" + "b" * 121
    assert len(bid_key_128) == 128
    assert len(buy_key_128) == 128

    resp_bid = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token_bidder}", "Idempotency-Key": bid_key_128},
        json={"amount": "200.00"},
    )
    assert resp_bid.status_code == 201

    resp_buy = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token_buyer}", "Idempotency-Key": buy_key_128},
    )
    assert resp_buy.status_code == 200


@pytest.mark.asyncio
async def test_buy_now_flush_integrity_error_triggers_rollback_and_conflict(
    buy_now_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_buynow_flush")
    lot = await _create_buy_now_lot(db_session, seller.id, buy_now_price=Decimal("1000.00"))
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_buynow_flush")
    await db_session.commit()

    async def mock_create_escrow_order(self: Any, order: Any) -> Any:
        raise IntegrityError("mock insert order", {}, Exception("unique constraint violation"))

    monkeypatch.setattr(BiddingRepository, "create_escrow_order", mock_create_escrow_order)

    resp = await buy_now_client.post(
        f"/api/v1/lots/{lot.id}/buy-now",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "buynow-flush-err-key"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
