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
    LedgerEntryType,
    LotCategory,
    LotStatus,
    UserRole,
    WalletHoldStatus,
)
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
async def bidding_client(
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


async def _create_live_test_lot(
    db_session: AsyncSession,
    seller_id: uuid.UUID,
    ends_at: datetime | None = None,
    status: LotStatus = LotStatus.LIVE,
) -> Lot:
    now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    lot = Lot(
        seller_id=seller_id,
        category=LotCategory.APPAREL,
        status=status,
        title="Helmut Lang 1999 Astro Moto Jacket",
        subtitle="Iconic archive silhouette",
        description="Pristine condition with technical straps.",
        specs={
            "category": "APPAREL",
            "brand": "Helmut Lang",
            "season_era": "AW99",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 56.0,
                "shoulders": 48.0,
                "length": 65.0,
                "sleeve": 64.0,
            },
            "materials": ["Cotton Canvas", "Goose Down"],
        },
        start_price=Decimal("200.00"),
        reserve_price=Decimal("500.00"),
        buy_now_price=Decimal("1500.00"),
        min_bid_increment=Decimal("25.00"),
        current_price=Decimal("200.00"),
        bid_count=0,
        anti_snipe_extensions_count=0,
        starts_at=now - timedelta(hours=2),
        ends_at=ends_at or (now + timedelta(hours=2)),
    )
    db_session.add(lot)
    await db_session.commit()
    return lot


@pytest.mark.asyncio
async def test_concurrent_ten_bidders_race_no_deadlock_and_single_active_hold(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_race_master")
    lot = await _create_live_test_lot(db_session, seller.id)

    bidders_data: list[tuple[User, str]] = []
    for idx in range(10):
        user, token = await _create_user_with_wallet(
            db_session,
            f"bidder_racer_{idx}",
            available_balance=Decimal("10000.00"),
        )
        bidders_data.append((user, token))
    await db_session.commit()

    async def place_bid_worker(
        bidder_user: User,
        token: str,
        target_amount: Decimal,
        idempotency_key: str,
    ) -> int:
        response = await bidding_client.post(
            f"/api/v1/lots/{lot.id}/bids",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key,
            },
            json={"amount": str(target_amount)},
        )
        return response.status_code

    tasks = [
        place_bid_worker(
            bidder_user=bidders_data[idx][0],
            token=bidders_data[idx][1],
            target_amount=Decimal(str(250 + idx * 30)),
            idempotency_key=f"race-key-{idx}-{uuid.uuid4().hex[:6]}",
        )
        for idx in range(10)
    ]

    results = await asyncio.gather(*tasks)

    for status_code in results:
        assert status_code in (201, 400)

    successful_count = sum(1 for sc in results if sc == 201)
    assert successful_count >= 1

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        active_holds_stmt = select(WalletHold).where(
            WalletHold.lot_id == lot.id,
            WalletHold.status == WalletHoldStatus.ACTIVE_HOLD,
        )
        active_holds_res = await verify_session.execute(active_holds_stmt)
        active_holds = active_holds_res.scalars().all()

        assert len(active_holds) == 1
        final_leader_hold = active_holds[0]

        lot_stmt = select(Lot).where(Lot.id == lot.id)
        lot_res = await verify_session.execute(lot_stmt)
        db_lot = lot_res.scalar_one()

        assert db_lot.leader_user_id == final_leader_hold.user_id
        assert db_lot.current_price == final_leader_hold.amount
        assert db_lot.bid_count == successful_count

        claimable_stmt = select(WalletHold).where(
            WalletHold.lot_id == lot.id,
            WalletHold.status == WalletHoldStatus.CLAIMABLE,
        )
        claimable_res = await verify_session.execute(claimable_stmt)
        claimable_holds = claimable_res.scalars().all()

        assert len(claimable_holds) == successful_count - 1
        for hold in claimable_holds:
            assert hold.outbid_at is not None

        for user, _ in bidders_data:
            wallet_stmt = select(Wallet).where(Wallet.user_id == user.id)
            wallet_res = await verify_session.execute(wallet_stmt)
            w = wallet_res.scalar_one()
            assert (w.available_balance + w.held_balance + w.claimable_balance) == Decimal(
                "10000.00"
            )

            if w.user_id == final_leader_hold.user_id:
                assert w.held_balance == final_leader_hold.amount
            else:
                assert w.held_balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_race(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_idem")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_idem")
    await db_session.commit()

    shared_key = f"same-idempotency-key-{uuid.uuid4().hex}"

    async def send_bid() -> tuple[int, dict[str, Any]]:
        resp = await bidding_client.post(
            f"/api/v1/lots/{lot.id}/bids",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": shared_key,
            },
            json={"amount": "250.00"},
        )
        return resp.status_code, resp.json()

    results = await asyncio.gather(send_bid(), send_bid(), send_bid())

    status_codes = [r[0] for r in results]
    assert status_codes == [201, 201, 201]

    bid_ids = {r[1]["id"] for r in results}
    assert len(bid_ids) == 1

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        bids_stmt = select(Bid).where(Bid.idempotency_key == shared_key)
        bids_res = await verify_session.execute(bids_stmt)
        bids = bids_res.scalars().all()
        assert len(bids) == 1

        holds_stmt = select(WalletHold).where(WalletHold.lot_id == lot.id)
        holds_res = await verify_session.execute(holds_stmt)
        holds = holds_res.scalars().all()
        assert len(holds) == 1


@pytest.mark.asyncio
async def test_idempotency_conflict_with_different_parameters(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_conflict")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_conflict")
    await db_session.commit()

    key = f"conflict-key-{uuid.uuid4().hex}"

    resp1 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"amount": "250.00"},
    )
    assert resp1.status_code == 201

    resp2 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"amount": "300.00"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_bidder_raising_own_bid_self_outbid(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_self")
    lot = await _create_live_test_lot(db_session, seller.id)
    buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_self",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    resp1 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "self-bid-1",
        },
        json={"amount": "250.00"},
    )
    assert resp1.status_code == 201

    resp2 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "self-bid-2",
        },
        json={"amount": "300.00"},
    )
    assert resp2.status_code == 201

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as verify_session:
        active_holds_stmt = select(WalletHold).where(
            WalletHold.lot_id == lot.id,
            WalletHold.status == WalletHoldStatus.ACTIVE_HOLD,
        )
        active_res = await verify_session.execute(active_holds_stmt)
        active_holds = active_res.scalars().all()
        assert len(active_holds) == 1
        assert active_holds[0].amount == Decimal("300.00")

        claimable_stmt = select(WalletHold).where(
            WalletHold.lot_id == lot.id,
            WalletHold.status == WalletHoldStatus.CLAIMABLE,
        )
        claimable_res = await verify_session.execute(claimable_stmt)
        claimable_holds = claimable_res.scalars().all()
        assert len(claimable_holds) == 1
        assert claimable_holds[0].amount == Decimal("250.00")
        assert claimable_holds[0].outbid_at is not None

        wallet_stmt = select(Wallet).where(Wallet.user_id == buyer.id)
        w_res = await verify_session.execute(wallet_stmt)
        w = w_res.scalar_one()
        assert w.available_balance == Decimal("1450.00")
        assert w.held_balance == Decimal("300.00")
        assert w.claimable_balance == Decimal("250.00")

        ledger_stmt = (
            select(WalletLedgerEntry)
            .where(WalletLedgerEntry.user_id == buyer.id)
            .order_by(WalletLedgerEntry.created_at.asc())
        )
        ledger_res = await verify_session.execute(ledger_stmt)
        entries = ledger_res.scalars().all()
        assert len(entries) == 3
        assert entries[0].entry_type == LedgerEntryType.BID_LOCK
        assert entries[1].entry_type == LedgerEntryType.BID_OUTBID_TO_CLAIMABLE
        assert entries[2].entry_type == LedgerEntryType.BID_LOCK


@pytest.mark.asyncio
async def test_anti_snipe_trigger_in_last_120_seconds(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
    fake_realtime_broker: InMemoryRealtimeBrokerAdapter,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_antisnipe")
    initial_ends_at = frozen_clock.now() + timedelta(seconds=60)
    lot = await _create_live_test_lot(db_session, seller.id, ends_at=initial_ends_at)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_antisnipe")
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "antisnipe-key-1",
        },
        json={"amount": "250.00"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["triggered_anti_snipe"] is True
    assert data["anti_snipe_extensions_count"] == 1
    expected_ends_at = frozen_clock.now() + timedelta(seconds=120)
    assert datetime.fromisoformat(data["ends_at"]) == expected_ends_at

    events = fake_realtime_broker.get_published_events(f"lot:{lot.id}")
    event_types = [e["event_type"] for e in events]
    assert "BID_PLACED" in event_types
    assert "LOT_EXTENDED" in event_types


@pytest.mark.asyncio
async def test_seller_cannot_bid_on_own_lot(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, token = await _create_user_with_wallet(db_session, "seller_self_bid")
    lot = await _create_live_test_lot(db_session, seller.id)
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "seller-own-bid",
        },
        json={"amount": "250.00"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "SELF_BIDDING_FORBIDDEN"


@pytest.mark.asyncio
async def test_bidding_validations_on_lot_status_and_time(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_validation")
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_validation")

    draft_lot = await _create_live_test_lot(db_session, seller.id, status=LotStatus.DRAFT)
    past_lot = await _create_live_test_lot(
        db_session,
        seller.id,
        ends_at=frozen_clock.now() - timedelta(minutes=5),
    )
    await db_session.commit()

    resp_draft = await bidding_client.post(
        f"/api/v1/lots/{draft_lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "draft-bid"},
        json={"amount": "250.00"},
    )
    assert resp_draft.status_code == 409
    assert resp_draft.json()["error_code"] == "LOT_NOT_LIVE"

    resp_ended = await bidding_client.post(
        f"/api/v1/lots/{past_lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "ended-bid"},
        json={"amount": "250.00"},
    )
    assert resp_ended.status_code == 409
    assert resp_ended.json()["error_code"] == "LOT_ALREADY_ENDED"


@pytest.mark.asyncio
async def test_bid_amount_too_low_rejected(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_low")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_low")
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "low-bid"},
        json={"amount": "150.00"},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "BID_AMOUNT_TOO_LOW"


@pytest.mark.asyncio
async def test_insufficient_available_balance_rejected(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_broke")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_broke",
        available_balance=Decimal("50.00"),
    )
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "broke-bid"},
        json={"amount": "250.00"},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INSUFFICIENT_AVAILABLE_BALANCE"


@pytest.mark.asyncio
async def test_missing_idempotency_key_header_rejected(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_nokey")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_nokey")
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": "250.00"},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.asyncio
async def test_insufficient_balance_with_claimable_note_format(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_claim_note")
    lot = await _create_live_test_lot(db_session, seller.id)
    user, token = await _create_user_with_wallet(
        db_session,
        "buyer_claim_note",
        available_balance=Decimal("100.00"),
    )
    w_stmt = select(Wallet).where(Wallet.user_id == user.id)
    w_res = await db_session.execute(w_stmt)
    wallet = w_res.scalar_one()
    wallet.claimable_balance = Decimal("400.00")
    await db_session.commit()

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "claim-note-key"},
        json={"amount": "250.00"},
    )
    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error_code"] == "INSUFFICIENT_AVAILABLE_BALANCE"
    assert "that can be manually claimed." in payload["message"]
    assert payload["details"]["available_balance"] == "100.00"
    assert payload["details"]["claimable_balance"] == "400.00"
    assert payload["details"]["required_amount"] == "250.00"


@pytest.mark.asyncio
async def test_idempotency_conflict_across_different_lots(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_cross_lot")
    lot1 = await _create_live_test_lot(db_session, seller.id)
    lot2 = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(
        db_session,
        "buyer_cross_lot",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    key = f"cross-lot-key-{uuid.uuid4().hex}"

    resp1 = await bidding_client.post(
        f"/api/v1/lots/{lot1.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"amount": "250.00"},
    )
    assert resp1.status_code == 201

    resp2 = await bidding_client.post(
        f"/api/v1/lots/{lot2.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"amount": "250.00"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_bidding_with_maximum_length_idempotency_key(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_maxlen")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer1, token1 = await _create_user_with_wallet(
        db_session,
        "buyer_maxlen_1",
        available_balance=Decimal("2000.00"),
    )
    _buyer2, token2 = await _create_user_with_wallet(
        db_session,
        "buyer_maxlen_2",
        available_balance=Decimal("2000.00"),
    )
    await db_session.commit()

    key_128_1 = "k1_" + "x" * 125
    key_128_2 = "k2_" + "y" * 125
    assert len(key_128_1) == 128
    assert len(key_128_2) == 128

    resp1 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token1}", "Idempotency-Key": key_128_1},
        json={"amount": "250.00"},
    )
    assert resp1.status_code == 201

    resp2 = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token2}", "Idempotency-Key": key_128_2},
        json={"amount": "300.00"},
    )
    assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_place_bid_flush_integrity_error_triggers_rollback_and_conflict(
    bidding_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seller, _ = await _create_user_with_wallet(db_session, "seller_flush_conflict")
    lot = await _create_live_test_lot(db_session, seller.id)
    _buyer, token = await _create_user_with_wallet(db_session, "buyer_flush_conflict")
    await db_session.commit()

    async def mock_create_bid(self: Any, bid: Any) -> Any:
        raise IntegrityError("mock insert statement", {}, Exception("unique constraint violation"))

    monkeypatch.setattr(BiddingRepository, "create_bid", mock_create_bid)

    resp = await bidding_client.post(
        f"/api/v1/lots/{lot.id}/bids",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "flush-err-key"},
        json={"amount": "250.00"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
