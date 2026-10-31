import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketDisconnect

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from core.clock import FrozenClock
from core.security import create_access_token
from domains.auth.dependencies import get_clock
from domains.bidding.router import get_realtime_broker
from main import create_app
from shared.db.models.enums import (
    EscrowOrderStatus,
    LotCategory,
    LotStatus,
    UserRole,
)
from shared.db.models.lot import Lot
from shared.db.models.user import User
from shared.db.models.wallet import Wallet
from shared.db.session import get_db_session


class AsyncWebsocketSession:
    def __init__(self, app: Any, path: str) -> None:
        self.app = app
        url_parts = path.split("?", 1)
        self.raw_path = url_parts[0]
        self.query_string = url_parts[1] if len(url_parts) > 1 else ""
        self.to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None
        self.closed_code: int | None = None

    async def connect(self) -> None:
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": self.raw_path,
            "raw_path": self.raw_path.encode("ascii"),
            "query_string": self.query_string.encode("ascii"),
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
        }

        async def receive() -> dict[str, Any]:
            return await self.to_app.get()

        async def send(message: dict[str, Any]) -> None:
            await self.from_app.put(message)

        self.task = asyncio.create_task(self.app(scope, receive, send))
        await self.to_app.put({"type": "websocket.connect"})
        first_resp = await asyncio.wait_for(self.from_app.get(), timeout=5.0)
        if first_resp["type"] == "websocket.close":
            self.closed_code = first_resp.get("code", 1000)
            raise WebSocketDisconnect(code=self.closed_code)
        assert first_resp["type"] == "websocket.accept"

    async def send_text(self, text: str) -> None:
        await self.to_app.put({"type": "websocket.receive", "text": text})

    async def send_json(self, data: dict[str, Any]) -> None:
        await self.send_text(json.dumps(data))

    async def receive_text(self) -> str:
        msg = await asyncio.wait_for(self.from_app.get(), timeout=5.0)
        if msg["type"] == "websocket.close":
            self.closed_code = msg.get("code", 1000)
            raise WebSocketDisconnect(code=self.closed_code)
        assert msg["type"] == "websocket.send"
        return str(msg.get("text", ""))

    async def receive_json(self) -> dict[str, Any]:
        raw = await self.receive_text()
        return dict(json.loads(raw))

    async def close(self) -> None:
        await self.to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self.task is not None:
            try:
                await asyncio.wait_for(self.task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError, WebSocketDisconnect):
                self.task.cancel()

    async def __aenter__(self) -> "AsyncWebsocketSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


def validate_iso8601(dt_str: str) -> bool:
    try:
        datetime.fromisoformat(dt_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_lot_snapshot_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "LOT_SNAPSHOT"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert event["status"] in [s.value for s in LotStatus]
    assert Decimal(event["current_price"]) >= Decimal("0.00")
    assert Decimal(event["min_valid_bid"]) >= Decimal("0.00")
    assert isinstance(event["bid_count"], int)
    if event["leader_user_id"] is not None:
        assert isinstance(uuid.UUID(event["leader_user_id"]), uuid.UUID)
    if event["leader_username_masked"] is not None:
        assert isinstance(event["leader_username_masked"], str)
    assert isinstance(event["is_buy_now_available"], bool)
    assert isinstance(event["is_reserve_met"], bool)
    assert validate_iso8601(event["ends_at"])
    assert isinstance(event["anti_snipe_extensions_count"], int)
    assert validate_iso8601(event["server_time"])


def validate_bid_placed_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "BID_PLACED"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert isinstance(uuid.UUID(event["bid_id"]), uuid.UUID)
    assert Decimal(event["amount"]) > Decimal("0.00")
    assert Decimal(event["min_valid_bid"]) >= Decimal("0.00")
    assert isinstance(event["bid_count"], int)
    assert isinstance(uuid.UUID(event["leader_user_id"]), uuid.UUID)
    assert isinstance(event["leader_username_masked"], str)
    assert isinstance(event["is_buy_now_available"], bool)
    assert isinstance(event["is_reserve_met"], bool)
    assert validate_iso8601(event["ends_at"])
    assert isinstance(event["triggered_anti_snipe"], bool)
    assert validate_iso8601(event["server_time"])


def validate_lot_extended_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "LOT_EXTENDED"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert validate_iso8601(event["new_ends_at"])
    assert isinstance(event["anti_snipe_extensions_count"], int)
    assert validate_iso8601(event["server_time"])


def validate_lot_sold_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "LOT_SOLD"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert isinstance(uuid.UUID(event["winner_user_id"]), uuid.UUID)
    assert Decimal(event["final_price"]) > Decimal("0.00")
    assert isinstance(event["via_buy_now"], bool)
    assert validate_iso8601(event["server_time"])


def validate_lot_ended_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "LOT_ENDED"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert event["status"] in [s.value for s in LotStatus]
    if event["winner_user_id"] is not None:
        assert isinstance(uuid.UUID(event["winner_user_id"]), uuid.UUID)
    assert Decimal(event["final_price"]) >= Decimal("0.00")
    assert validate_iso8601(event["server_time"])


def validate_auth_ok_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "AUTH_OK"
    assert isinstance(uuid.UUID(event["user_id"]), uuid.UUID)
    assert validate_iso8601(event["server_time"])


def validate_hold_became_claimable_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "HOLD_BECAME_CLAIMABLE"
    assert isinstance(uuid.UUID(event["hold_id"]), uuid.UUID)
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert isinstance(event["lot_title"], str) and len(event["lot_title"]) > 0
    assert Decimal(event["amount"]) > Decimal("0.00")
    assert event["reason"] in ["OUTBID", "RESERVE_NOT_MET", "LOT_CANCELLED"]
    assert Decimal(event["new_claimable_balance"]) >= Decimal("0.00")
    assert validate_iso8601(event["server_time"])


def validate_lot_won_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "LOT_WON"
    assert isinstance(uuid.UUID(event["lot_id"]), uuid.UUID)
    assert isinstance(uuid.UUID(event["order_id"]), uuid.UUID)
    assert Decimal(event["final_amount"]) > Decimal("0.00")
    assert validate_iso8601(event["server_time"])


def validate_order_status_changed_contract(event: dict[str, Any]) -> None:
    assert event["event_type"] == "ORDER_STATUS_CHANGED"
    assert isinstance(uuid.UUID(event["order_id"]), uuid.UUID)
    assert event["status"] in [s.value for s in EscrowOrderStatus]
    assert validate_iso8601(event["server_time"])


def test_contract_schema_validators() -> None:
    now_iso = "2026-10-23T14:28:15.420000+00:00"
    lot_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    bid_id = str(uuid.uuid4())
    hold_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())

    validate_lot_snapshot_contract(
        {
            "event_type": "LOT_SNAPSHOT",
            "lot_id": lot_id,
            "status": "LIVE",
            "current_price": "1450.00",
            "min_valid_bid": "1500.00",
            "bid_count": 7,
            "leader_user_id": user_id,
            "leader_username_masked": "k***y",
            "is_buy_now_available": False,
            "is_reserve_met": True,
            "ends_at": now_iso,
            "anti_snipe_extensions_count": 1,
            "server_time": now_iso,
        }
    )

    validate_bid_placed_contract(
        {
            "event_type": "BID_PLACED",
            "lot_id": lot_id,
            "bid_id": bid_id,
            "amount": "1500.00",
            "min_valid_bid": "1550.00",
            "bid_count": 8,
            "leader_user_id": user_id,
            "leader_username_masked": "a***x",
            "is_buy_now_available": False,
            "is_reserve_met": True,
            "ends_at": now_iso,
            "triggered_anti_snipe": False,
            "server_time": now_iso,
        }
    )

    validate_lot_extended_contract(
        {
            "event_type": "LOT_EXTENDED",
            "lot_id": lot_id,
            "new_ends_at": now_iso,
            "anti_snipe_extensions_count": 2,
            "server_time": now_iso,
        }
    )

    validate_lot_sold_contract(
        {
            "event_type": "LOT_SOLD",
            "lot_id": lot_id,
            "winner_user_id": user_id,
            "final_price": "2200.00",
            "via_buy_now": True,
            "server_time": now_iso,
        }
    )

    validate_lot_ended_contract(
        {
            "event_type": "LOT_ENDED",
            "lot_id": lot_id,
            "status": "ENDED_WON",
            "winner_user_id": user_id,
            "final_price": "1850.00",
            "server_time": now_iso,
        }
    )

    validate_auth_ok_contract(
        {
            "event_type": "AUTH_OK",
            "user_id": user_id,
            "server_time": now_iso,
        }
    )

    validate_hold_became_claimable_contract(
        {
            "event_type": "HOLD_BECAME_CLAIMABLE",
            "hold_id": hold_id,
            "lot_id": lot_id,
            "lot_title": "Raf Simons Camo Bomber",
            "amount": "4200.00",
            "reason": "OUTBID",
            "new_claimable_balance": "4200.00",
            "server_time": now_iso,
        }
    )

    validate_lot_won_contract(
        {
            "event_type": "LOT_WON",
            "lot_id": lot_id,
            "order_id": order_id,
            "final_amount": "4500.00",
            "server_time": now_iso,
        }
    )

    validate_order_status_changed_contract(
        {
            "event_type": "ORDER_STATUS_CHANGED",
            "order_id": order_id,
            "status": "SHIPPED",
            "server_time": now_iso,
        }
    )


async def setup_test_users_and_lot(
    session: AsyncSession,
    clock_time: datetime,
) -> tuple[User, User, User, Lot]:
    seller = User(
        email="seller@example.com",
        username="seller_archivist",
        role=UserRole.MEMBER,
        is_active=True,
    )
    user_a = User(
        email="user_a@example.com",
        username="collector_alpha",
        role=UserRole.MEMBER,
        is_active=True,
    )
    user_b = User(
        email="user_b@example.com",
        username="bidder_bravo",
        role=UserRole.MEMBER,
        is_active=True,
    )
    session.add_all([seller, user_a, user_b])
    await session.flush()

    wallet_seller = Wallet(
        user_id=seller.id,
        available_balance=Decimal("0.00"),
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    wallet_a = Wallet(
        user_id=user_a.id,
        available_balance=Decimal("10000.00"),
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    wallet_b = Wallet(
        user_id=user_b.id,
        available_balance=Decimal("10000.00"),
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    session.add_all([wallet_seller, wallet_a, wallet_b])
    await session.flush()

    lot = Lot(
        seller_id=seller.id,
        category=LotCategory.APPAREL,
        status=LotStatus.LIVE,
        title="Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
        subtitle="Iconic piece from runway",
        description="Rare collector archival piece in pristine condition",
        specs={
            "brand": "Raf Simons",
            "season_era": "AW01",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 58.0,
                "shoulders": 50.0,
                "length": 68.0,
                "sleeve": 64.0,
            },
            "materials": ["100% Cotton", "Riri Zippers"],
        },
        start_price=Decimal("1000.00"),
        reserve_price=Decimal("2000.00"),
        buy_now_price=Decimal("5000.00"),
        min_bid_increment=Decimal("100.00"),
        current_price=Decimal("1000.00"),
        bid_count=0,
        leader_user_id=None,
        anti_snipe_extensions_count=0,
        starts_at=clock_time - timedelta(hours=1),
        ends_at=clock_time + timedelta(hours=2),
    )
    session.add(lot)
    await session.commit()
    return seller, user_a, user_b, lot


@pytest.mark.asyncio
async def test_lot_stream_snapshot_and_unknown_lot_rejection(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, _, lot = await setup_test_users_and_lot(session, clock_time)
        lot_id = lot.id

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    with pytest.raises(WebSocketDisconnect) as exc_missing:
        async with AsyncWebsocketSession(app, f"/ws/lots/{uuid.uuid4()}"):
            assert True
    assert exc_missing.value.code == 1008

    async with AsyncWebsocketSession(app, f"/ws/lots/{lot_id}") as lot_sock:
        snapshot = await lot_sock.receive_json()
        validate_lot_snapshot_contract(snapshot)
        assert snapshot["lot_id"] == str(lot_id)
        assert snapshot["status"] == "LIVE"
        assert snapshot["current_price"] == "1000.00"
        assert snapshot["min_valid_bid"] == "1000.00"
        assert snapshot["bid_count"] == 0
        assert snapshot["leader_user_id"] is None
        assert snapshot["is_buy_now_available"] is True
        assert snapshot["is_reserve_met"] is False


@pytest.mark.asyncio
async def test_user_notifications_auth_modes(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, user_a, _, _ = await setup_test_users_and_lot(session, clock_time)
        user_a_id = user_a.id

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    valid_token = create_access_token(user_id=user_a_id, role=UserRole.MEMBER.value, now=clock_time)
    expired_token = create_access_token(
        user_id=user_a_id,
        role=UserRole.MEMBER.value,
        now=clock_time - timedelta(hours=5),
    )

    with pytest.raises(WebSocketDisconnect) as exc_expired_query:
        async with AsyncWebsocketSession(app, f"/ws/user/notifications?token={expired_token}"):
            assert True
    assert exc_expired_query.value.code == 1008

    ws_url = f"/ws/user/notifications?token={valid_token}"
    async with AsyncWebsocketSession(app, ws_url) as sock_valid:
        assert sock_valid is not None

    async with AsyncWebsocketSession(app, "/ws/user/notifications") as sock_first_frame:
        await sock_first_frame.send_json({"type": "AUTH", "token": valid_token})
        auth_ok = await sock_first_frame.receive_json()
        validate_auth_ok_contract(auth_ok)
        assert auth_ok["user_id"] == str(user_a_id)

    with pytest.raises(WebSocketDisconnect) as exc_invalid_first_frame:
        async with AsyncWebsocketSession(app, "/ws/user/notifications") as sock_invalid:
            await sock_invalid.send_json({"type": "INVALID", "token": valid_token})
            await sock_invalid.receive_json()
    assert exc_invalid_first_frame.value.code == 1008


@pytest.mark.asyncio
async def test_two_clients_live_bid_placed_and_outbid_claimable_integration(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, user_a, user_b, lot = await setup_test_users_and_lot(session, clock_time)
        lot_id = lot.id
        user_a_id = user_a.id
        user_b_id = user_b.id

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    token_a = create_access_token(user_id=user_a_id, role=UserRole.MEMBER.value, now=clock_time)
    token_b = create_access_token(user_id=user_b_id, role=UserRole.MEMBER.value, now=clock_time)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        bid_a_resp = await http_client.post(
            f"/api/v1/lots/{lot_id}/bids",
            json={"amount": "1000.00"},
            headers={
                "Authorization": f"Bearer {token_a}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert bid_a_resp.status_code == 201

        async with (
            AsyncWebsocketSession(app, f"/ws/lots/{lot_id}") as lot_sock_a,
            AsyncWebsocketSession(app, f"/ws/lots/{lot_id}") as lot_sock_b,
            AsyncWebsocketSession(app, f"/ws/user/notifications?token={token_a}") as user_a_sock,
        ):
            initial_snap_a = await lot_sock_a.receive_json()
            validate_lot_snapshot_contract(initial_snap_a)
            assert initial_snap_a["bid_count"] == 1
            assert initial_snap_a["current_price"] == "1000.00"
            assert initial_snap_a["leader_user_id"] == str(user_a_id)

            initial_snap_b = await lot_sock_b.receive_json()
            validate_lot_snapshot_contract(initial_snap_b)
            assert initial_snap_b["bid_count"] == 1
            assert initial_snap_b["current_price"] == "1000.00"

            bid_b_resp = await http_client.post(
                f"/api/v1/lots/{lot_id}/bids",
                json={"amount": "1100.00"},
                headers={
                    "Authorization": f"Bearer {token_b}",
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            assert bid_b_resp.status_code == 201

            lot_event_a = await lot_sock_a.receive_json()
            validate_bid_placed_contract(lot_event_a)
            assert lot_event_a["amount"] == "1100.00"
            assert lot_event_a["bid_count"] == 2
            assert lot_event_a["leader_user_id"] == str(user_b_id)

            lot_event_b = await lot_sock_b.receive_json()
            validate_bid_placed_contract(lot_event_b)
            assert lot_event_b["amount"] == "1100.00"
            assert lot_event_b["bid_count"] == 2
            assert lot_event_b["leader_user_id"] == str(user_b_id)

            user_a_event = await user_a_sock.receive_json()
            validate_hold_became_claimable_contract(user_a_event)
            assert user_a_event["lot_id"] == str(lot_id)
            assert user_a_event["amount"] == "1000.00"
            assert user_a_event["reason"] == "OUTBID"
            assert user_a_event["new_claimable_balance"] == "1000.00"


@pytest.mark.asyncio
async def test_buy_now_emits_lot_sold_and_winner_notification(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, _, user_b, lot = await setup_test_users_and_lot(session, clock_time)
        lot_id = lot.id
        user_b_id = user_b.id

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    token_b = create_access_token(user_id=user_b_id, role=UserRole.MEMBER.value, now=clock_time)

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as http_client,
        AsyncWebsocketSession(app, f"/ws/lots/{lot_id}") as lot_sock,
    ):
        await lot_sock.receive_json()

        async with AsyncWebsocketSession(
            app, f"/ws/user/notifications?token={token_b}"
        ) as user_b_sock:
            buy_now_resp = await http_client.post(
                f"/api/v1/lots/{lot_id}/buy-now",
                headers={
                    "Authorization": f"Bearer {token_b}",
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            assert buy_now_resp.status_code == 200

            lot_event = await lot_sock.receive_json()
            validate_lot_sold_contract(lot_event)
            assert lot_event["lot_id"] == str(lot_id)
            assert lot_event["winner_user_id"] == str(user_b_id)
            assert lot_event["final_price"] == "5000.00"
            assert lot_event["via_buy_now"] is True

            user_b_event = await user_b_sock.receive_json()
            validate_lot_won_contract(user_b_event)
            assert user_b_event["lot_id"] == str(lot_id)
            assert user_b_event["final_amount"] == "5000.00"


@pytest.mark.asyncio
async def test_websocket_abrupt_disconnect_during_auth(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    session = AsyncWebsocketSession(app, "/ws/user/notifications")
    await session.connect()
    await session.close()
    assert True


@pytest.mark.asyncio
async def test_bid_in_anti_snipe_window_broadcasts_bid_placed_and_lot_extended(
    db_engine: AsyncEngine,
) -> None:
    clock_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(clock_time)
    fake_broker = InMemoryRealtimeBrokerAdapter()
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        _, user_a, _, lot = await setup_test_users_and_lot(session, clock_time)
        lot.ends_at = clock_time + timedelta(seconds=60)
        await session.commit()
        lot_id = lot.id
        user_a_id = user_a.id

    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_realtime_broker] = lambda: fake_broker

    async def override_db() -> Any:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db

    token_a = create_access_token(user_id=user_a_id, role=UserRole.MEMBER.value, now=clock_time)

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as http_client,
        AsyncWebsocketSession(app, f"/ws/lots/{lot_id}") as lot_sock,
    ):
        initial_snap = await lot_sock.receive_json()
        validate_lot_snapshot_contract(initial_snap)

        bid_resp = await http_client.post(
            f"/api/v1/lots/{lot_id}/bids",
            json={"amount": "1000.00"},
            headers={
                "Authorization": f"Bearer {token_a}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert bid_resp.status_code == 201

        bid_event = await lot_sock.receive_json()
        validate_bid_placed_contract(bid_event)
        assert bid_event["triggered_anti_snipe"] is True
        assert bid_event["amount"] == "1000.00"

        extended_event = await lot_sock.receive_json()
        validate_lot_extended_contract(extended_event)
        assert extended_event["lot_id"] == str(lot_id)
        assert extended_event["anti_snipe_extensions_count"] == 1
        assert extended_event["new_ends_at"] == (clock_time + timedelta(seconds=120)).isoformat()
