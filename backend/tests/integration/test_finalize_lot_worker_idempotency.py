import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from core.clock import FrozenClock
from core.exceptions import ConflictError
from domains.bidding.schemas import PlaceBidRequest
from domains.bidding.service import BiddingService
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
from worker.broker import create_broker
from worker.tasks import finalize_expired_lot_job


async def setup_test_lot_environment(
    session: AsyncSession,
    clock_time: datetime,
    with_reserve: bool = True,
    reserve_met: bool = True,
    bid_count: int = 1,
) -> tuple[User, User, Lot, WalletHold | None]:
    seller = User(
        email="seller_archivist@example.com",
        username="seller_archivist",
        role=UserRole.MEMBER,
        is_active=True,
    )
    bidder = User(
        email="bidder_prime@example.com",
        username="bidder_prime",
        role=UserRole.MEMBER,
        is_active=True,
    )
    session.add_all([seller, bidder])
    await session.flush()

    seller_wallet = Wallet(
        user_id=seller.id,
        available_balance=Decimal("0.00"),
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    bidder_wallet = Wallet(
        user_id=bidder.id,
        available_balance=Decimal("5000.00"),
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    session.add_all([seller_wallet, bidder_wallet])
    await session.flush()

    start_price = Decimal("1000.00")
    reserve_price = Decimal("2000.00") if with_reserve else None
    buy_now_price = Decimal("5000.00")

    if bid_count == 0:
        current_price = start_price
        leader_id = None
    elif reserve_met:
        current_price = Decimal("2500.00")
        leader_id = bidder.id
    else:
        current_price = Decimal("1500.00")
        leader_id = bidder.id

    lot = Lot(
        seller_id=seller.id,
        category=LotCategory.APPAREL,
        status=LotStatus.LIVE,
        title="Helmut Lang 1999 Astro Moto Jacket",
        subtitle="Iconic archival classic",
        description="Pristine condition original vintage piece",
        specs={
            "brand": "Helmut Lang",
            "season_era": "AW99",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 56.0,
                "shoulders": 48.0,
                "length": 65.0,
                "sleeve": 63.0,
            },
            "materials": ["100% Cotton", "Bondage Straps"],
        },
        start_price=start_price,
        reserve_price=reserve_price,
        buy_now_price=buy_now_price,
        min_bid_increment=Decimal("100.00"),
        current_price=current_price,
        bid_count=bid_count,
        leader_user_id=leader_id,
        anti_snipe_extensions_count=0,
        starts_at=clock_time - timedelta(hours=3),
        ends_at=clock_time - timedelta(minutes=5),
    )
    session.add(lot)
    await session.flush()

    hold: WalletHold | None = None
    if leader_id is not None:
        bidder_wallet.available_balance = Decimal(bidder_wallet.available_balance) - current_price
        bidder_wallet.held_balance = current_price

        hold = WalletHold(
            wallet_id=bidder_wallet.id,
            user_id=bidder.id,
            lot_id=lot.id,
            amount=current_price,
            status=WalletHoldStatus.ACTIVE_HOLD,
            created_at=clock_time - timedelta(hours=1),
        )
        session.add(hold)
        await session.flush()

        bid = Bid(
            lot_id=lot.id,
            bidder_id=bidder.id,
            wallet_hold_id=hold.id,
            amount=current_price,
            is_buy_now=False,
            triggered_anti_snipe=False,
            idempotency_key=str(uuid.uuid4()),
            created_at=clock_time - timedelta(hours=1),
        )
        session.add(bid)

    await session.commit()
    return seller, bidder, lot, hold


@pytest.mark.asyncio
async def test_finalize_expired_lot_won_creates_escrow_and_events(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        seller, bidder, lot, hold = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot_id = lot.id
        bidder_id = bidder.id
        seller_id = seller.id
        hold_id = hold.id if hold else uuid.uuid4()

    async with session_factory() as session:
        result = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=lot.ends_at.isoformat(),
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )

    assert result["status"] == "ENDED_WON"
    assert result["lot_id"] == str(lot_id)
    assert result["winner_user_id"] == str(bidder_id)
    assert result["final_price"] == "2500.00"

    async with session_factory() as session:
        refreshed_lot = await session.get(Lot, lot_id)
        assert refreshed_lot is not None
        assert refreshed_lot.status == LotStatus.ENDED_WON

        refreshed_hold = await session.get(WalletHold, hold_id)
        assert refreshed_hold is not None
        assert refreshed_hold.status == WalletHoldStatus.CAPTURED_TO_ESCROW
        assert refreshed_hold.captured_at is not None

        stmt = select(EscrowOrder).where(EscrowOrder.lot_id == lot_id)
        order_res = await session.execute(stmt)
        order = order_res.scalar_one_or_none()
        assert order is not None
        assert order.buyer_id == bidder_id
        assert order.seller_id == seller_id
        assert order.wallet_hold_id == hold_id
        assert order.final_amount == Decimal("2500.00")
        assert order.platform_fee_amount == Decimal("200.00")
        assert order.seller_payout_amount == Decimal("2300.00")
        assert order.status == EscrowOrderStatus.FUNDS_HELD

    lot_events = fake_broker.get_published_events(f"lot:{lot_id}")
    assert any(
        evt.get("event_type") == "LOT_ENDED"
        and evt.get("status") == "ENDED_WON"
        and evt.get("winner_user_id") == str(bidder_id)
        for evt in lot_events
    )

    user_events = fake_broker.get_published_events(f"user:{bidder_id}")
    assert any(
        evt.get("event_type") == "LOT_WON"
        and evt.get("lot_id") == str(lot_id)
        and evt.get("final_amount") == "2500.00"
        for evt in user_events
    )


@pytest.mark.asyncio
async def test_finalize_expired_lot_unsold_reserve_not_met_releases_hold_to_claimable(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, bidder, lot, hold = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=True,
            reserve_met=False,
            bid_count=1,
        )
        lot_id = lot.id
        bidder_id = bidder.id
        hold_id = hold.id if hold else uuid.uuid4()

    async with session_factory() as session:
        result = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=lot.ends_at.isoformat(),
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )

    assert result["status"] == "ENDED_UNSOLD"
    assert result["lot_id"] == str(lot_id)
    assert result["final_price"] == "1500.00"

    async with session_factory() as session:
        refreshed_lot = await session.get(Lot, lot_id)
        assert refreshed_lot is not None
        assert refreshed_lot.status == LotStatus.ENDED_UNSOLD

        refreshed_hold = await session.get(WalletHold, hold_id)
        assert refreshed_hold is not None
        assert refreshed_hold.status == WalletHoldStatus.CLAIMABLE
        assert refreshed_hold.outbid_at is not None

        wallet_stmt = select(Wallet).where(Wallet.user_id == bidder_id)
        wallet_res = await session.execute(wallet_stmt)
        bidder_wallet = wallet_res.scalar_one()
        assert bidder_wallet.held_balance == Decimal("0.00")
        assert bidder_wallet.claimable_balance == Decimal("1500.00")
        assert bidder_wallet.available_balance == Decimal("3500.00")

        ledger_stmt = select(WalletLedgerEntry).where(
            WalletLedgerEntry.reference_hold_id == hold_id,
            WalletLedgerEntry.entry_type == LedgerEntryType.BID_RELEASED_TO_CLAIMABLE,
        )
        ledger_res = await session.execute(ledger_stmt)
        ledger_entry = ledger_res.scalar_one_or_none()
        assert ledger_entry is not None
        assert ledger_entry.amount == Decimal("1500.00")
        assert ledger_entry.held_delta == Decimal("-1500.00")
        assert ledger_entry.claimable_delta == Decimal("1500.00")

    lot_events = fake_broker.get_published_events(f"lot:{lot_id}")
    assert any(
        evt.get("event_type") == "LOT_ENDED"
        and evt.get("status") == "ENDED_UNSOLD"
        and evt.get("winner_user_id") is None
        for evt in lot_events
    )

    user_events = fake_broker.get_published_events(f"user:{bidder_id}")
    assert any(
        evt.get("event_type") == "HOLD_BECAME_CLAIMABLE"
        and evt.get("hold_id") == str(hold_id)
        and evt.get("reason") == "RESERVE_NOT_MET"
        and evt.get("amount") == "1500.00"
        and evt.get("new_claimable_balance") == "1500.00"
        for evt in user_events
    )


@pytest.mark.asyncio
async def test_finalize_expired_lot_unsold_zero_bids(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=False,
            reserve_met=False,
            bid_count=0,
        )
        lot_id = lot.id

    async with session_factory() as session:
        result = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=lot.ends_at.isoformat(),
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )

    assert result["status"] == "ENDED_UNSOLD"
    assert result["final_price"] == "1000.00"

    async with session_factory() as session:
        refreshed_lot = await session.get(Lot, lot_id)
        assert refreshed_lot is not None
        assert refreshed_lot.status == LotStatus.ENDED_UNSOLD

    lot_events = fake_broker.get_published_events(f"lot:{lot_id}")
    assert any(
        evt.get("event_type") == "LOT_ENDED"
        and evt.get("status") == "ENDED_UNSOLD"
        and evt.get("winner_user_id") is None
        for evt in lot_events
    )


@pytest.mark.asyncio
async def test_finalize_expired_lot_noop_when_anti_snipe_extended(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot.ends_at = now_time + timedelta(seconds=90)
        lot_id = lot.id
        await session.commit()

    async with session_factory() as session:
        result = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=None,
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )

    assert result["status"] == "NOOP"
    assert result["reason"] == "ANTI_SNIPE_EXTENDED"

    async with session_factory() as session:
        refreshed_lot = await session.get(Lot, lot_id)
        assert refreshed_lot is not None
        assert refreshed_lot.status == LotStatus.LIVE

    assert len(fake_broker.published_events) == 0


@pytest.mark.asyncio
async def test_finalize_expired_lot_noop_when_lot_not_live(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot.status = LotStatus.CANCELLED
        lot_id = lot.id
        await session.commit()

    async with session_factory() as session:
        result = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=None,
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )

    assert result["status"] == "NOOP"
    assert result["reason"] == "LOT_NOT_LIVE"
    assert result["current_status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_finalize_expired_lot_job_double_call_idempotency(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot_id = lot.id
        ends_at_iso = lot.ends_at.isoformat()

    async with session_factory() as session:
        first_res = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=ends_at_iso,
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert first_res["status"] == "ENDED_WON"

    events_after_first = list(fake_broker.published_events)

    async with session_factory() as session:
        second_res = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso=ends_at_iso,
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert second_res["status"] == "NOOP"
    assert second_res["reason"] == "LOT_NOT_LIVE"
    assert second_res["current_status"] == "ENDED_WON"

    assert len(fake_broker.published_events) == len(events_after_first)

    async with session_factory() as session:
        orders_stmt = select(EscrowOrder).where(EscrowOrder.lot_id == lot_id)
        orders_res = await session.execute(orders_stmt)
        all_orders = list(orders_res.scalars().all())
        assert len(all_orders) == 1

        refreshed_lot = await session.get(Lot, lot_id)
        assert refreshed_lot is not None
        assert refreshed_lot.status == LotStatus.ENDED_WON


@pytest.mark.asyncio
async def test_taskiq_broker_execution(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time,
            with_reserve=False,
            reserve_met=False,
            bid_count=0,
        )
        lot_id = lot.id

    in_memory_broker = create_broker(in_memory=True)
    task = in_memory_broker.register_task(
        finalize_expired_lot_job.original_func,
        task_name="finalize_expired_lot_job",
    )
    await in_memory_broker.startup()
    try:
        real_db_url = db_engine.url.render_as_string(hide_password=False)
        task_res = await task.kiq(
            str(lot_id),
            expected_ends_at_iso=lot.ends_at.isoformat(),
            database_url=real_db_url,
        )
        result = await task_res.wait_result(timeout=5.0)
        assert result.return_value["status"] == "ENDED_UNSOLD"
    finally:
        await in_memory_broker.shutdown()


@pytest.mark.asyncio
async def test_finalize_expired_lot_job_superseded_anti_snipe_iso_with_z_noop(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 5, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time - timedelta(minutes=10),
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot.ends_at = datetime(2026, 10, 26, 12, 2, 0, tzinfo=UTC)
        lot_id = lot.id
        await session.commit()

    async with session_factory() as session:
        result_stale = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso="2026-10-26T12:00:00Z",
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert result_stale["status"] == "NOOP"
    assert result_stale["reason"] == "ANTI_SNIPE_EXTENDED"

    async with session_factory() as session:
        result_actual = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso="2026-10-26T12:02:00Z",
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert result_actual["status"] == "ENDED_WON"


@pytest.mark.asyncio
async def test_concurrent_bid_and_finalize_boundary_race(
    db_engine: AsyncEngine,
) -> None:
    boundary_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(boundary_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, bidder, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=boundary_time - timedelta(hours=1),
            with_reserve=False,
            reserve_met=False,
            bid_count=0,
        )
        lot.ends_at = boundary_time
        lot_id = lot.id
        bidder_id = bidder.id
        await session.commit()

    async def run_finalize() -> dict[str, Any]:
        async with session_factory() as session:
            return await finalize_expired_lot_job(
                lot_id=lot_id,
                expected_ends_at_iso=boundary_time.isoformat(),
                session=session,
                clock=clock,
                realtime_broker=fake_broker,
            )

    async def run_bid() -> str:
        async with session_factory() as session:
            service = BiddingService(
                session=session,
                clock=clock,
                realtime_broker=fake_broker,
            )
            try:
                await service.place_bid(
                    lot_id=lot_id,
                    bidder_id=bidder_id,
                    payload=PlaceBidRequest(amount=Decimal("1000.00")),
                    idempotency_key=str(uuid.uuid4()),
                )
                return "BID_SUCCESS"
            except ConflictError:
                return "BID_REJECTED_CLOSED"

    finalize_task = asyncio.create_task(run_finalize())
    bid_task = asyncio.create_task(run_bid())
    finalize_res, bid_res = await asyncio.gather(finalize_task, bid_task)

    assert finalize_res["status"] in ["ENDED_UNSOLD", "ENDED_WON", "NOOP"]
    assert bid_res in ["BID_SUCCESS", "BID_REJECTED_CLOSED"]

    async with session_factory() as session:
        final_lot = await session.get(Lot, lot_id)
        assert final_lot is not None
        assert final_lot.status in [LotStatus.LIVE, LotStatus.ENDED_WON, LotStatus.ENDED_UNSOLD]


@pytest.mark.asyncio
async def test_finalize_expired_lot_job_superseded_naive_iso_handled_safely(
    db_engine: AsyncEngine,
) -> None:
    now_time = datetime(2026, 10, 26, 12, 5, 0, tzinfo=UTC)
    clock = FrozenClock(now_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, lot, _ = await setup_test_lot_environment(
            session=session,
            clock_time=now_time - timedelta(minutes=10),
            with_reserve=True,
            reserve_met=True,
            bid_count=1,
        )
        lot.ends_at = datetime(2026, 10, 26, 12, 2, 0, tzinfo=UTC)
        lot_id = lot.id
        await session.commit()

    async with session_factory() as session:
        result_stale = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso="2026-10-26T12:00:00",
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert result_stale["status"] == "NOOP"
    assert result_stale["reason"] == "ANTI_SNIPE_EXTENDED"

    async with session_factory() as session:
        result_actual = await finalize_expired_lot_job(
            lot_id=lot_id,
            expected_ends_at_iso="2026-10-26T12:02:00",
            session=session,
            clock=clock,
            realtime_broker=fake_broker,
        )
    assert result_actual["status"] == "ENDED_WON"
