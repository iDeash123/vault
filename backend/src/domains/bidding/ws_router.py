import asyncio
import contextlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.security import decode_access_token
from domains.auth.dependencies import get_clock
from domains.auth.repository import AuthRepository
from domains.bidding.router import get_realtime_broker
from domains.bidding.service import (
    calculate_min_valid_bid,
    compute_is_buy_now_available,
    compute_is_reserve_met,
    mask_username,
    quantize_usd,
)
from domains.lots.repository import LotRepository
from ports.realtime_port import RealtimeBrokerPort
from shared.db.session import get_db_session

router = APIRouter(prefix="/ws", tags=["websocket"])


async def cleanup_tasks(*tasks: asyncio.Task[Any]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task


@router.websocket("/lots/{lot_id}")
async def lot_ws_endpoint(
    websocket: WebSocket,
    lot_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    realtime_broker: Annotated[RealtimeBrokerPort, Depends(get_realtime_broker)],
) -> None:
    lot_repo = LotRepository(session)
    lot = await lot_repo.get_lot_by_id(lot_id)
    if lot is None:
        await session.close()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    masked_leader: str | None = None
    if lot.leader_user_id is not None:
        auth_repo = AuthRepository(session)
        leader_user = await auth_repo.get_user_by_id(lot.leader_user_id)
        if leader_user is not None and leader_user.username:
            masked_leader = mask_username(leader_user.username)

    min_valid_bid = calculate_min_valid_bid(
        lot.start_price,
        lot.current_price,
        lot.min_bid_increment,
        lot.bid_count,
    )
    is_buy_now = compute_is_buy_now_available(
        lot.status,
        lot.buy_now_price,
        lot.reserve_price,
        lot.current_price,
        lot.min_bid_increment,
        lot.bid_count,
    )
    is_res_met = compute_is_reserve_met(
        lot.reserve_price,
        lot.current_price,
        lot.bid_count,
    )

    snapshot: dict[str, Any] = {
        "event_type": "LOT_SNAPSHOT",
        "lot_id": str(lot.id),
        "status": lot.status.value,
        "current_price": str(quantize_usd(lot.current_price)),
        "min_valid_bid": str(quantize_usd(min_valid_bid)),
        "bid_count": lot.bid_count,
        "leader_user_id": str(lot.leader_user_id) if lot.leader_user_id else None,
        "leader_username_masked": masked_leader,
        "is_buy_now_available": is_buy_now,
        "is_reserve_met": is_res_met,
        "ends_at": lot.ends_at.isoformat(),
        "anti_snipe_extensions_count": lot.anti_snipe_extensions_count,
        "server_time": clock.now().isoformat(),
    }
    await session.close()
    await websocket.send_json(snapshot)

    async def forward_lot_events() -> None:
        try:
            async for event in realtime_broker.subscribe(f"lot:{lot_id}"):
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            return

    async def drain_client() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
        except (WebSocketDisconnect, RuntimeError):
            return

    forward_task = asyncio.create_task(forward_lot_events())
    drain_task = asyncio.create_task(drain_client())

    try:
        done, pending = await asyncio.wait(
            [forward_task, drain_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(
                exc, (asyncio.CancelledError, WebSocketDisconnect, RuntimeError)
            ):
                raise exc
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        await cleanup_tasks(forward_task, drain_task)


@router.websocket("/user/notifications")
async def user_notifications_ws_endpoint(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    realtime_broker: Annotated[RealtimeBrokerPort, Depends(get_realtime_broker)],
    token: Annotated[str | None, Query()] = None,
) -> None:
    auth_repo = AuthRepository(session)
    authenticated_user_id: uuid.UUID | None = None

    if token is not None and token.strip() != "":
        try:
            payload = decode_access_token(token=token.strip(), now=clock.now())
            sub = payload.get("sub")
            user_id = uuid.UUID(str(sub))
            user = await auth_repo.get_user_by_id(user_id)
            if user is None or not user.is_active:
                await session.close()
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            authenticated_user_id = user_id
            await session.close()
            await websocket.accept()
        except WebSocketDisconnect:
            await session.close()
            return
        except Exception:
            await session.close()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        await websocket.accept()
        try:
            raw_frame = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            parsed_frame = json.loads(raw_frame)
            if not isinstance(parsed_frame, dict) or parsed_frame.get("type") != "AUTH":
                await session.close()
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            auth_token = parsed_frame.get("token")
            if not isinstance(auth_token, str) or not auth_token.strip():
                await session.close()
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            payload = decode_access_token(token=auth_token.strip(), now=clock.now())
            sub = payload.get("sub")
            user_id = uuid.UUID(str(sub))
            user = await auth_repo.get_user_by_id(user_id)
            if user is None or not user.is_active:
                await session.close()
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            authenticated_user_id = user_id
            await session.close()
            await websocket.send_json(
                {
                    "event_type": "AUTH_OK",
                    "user_id": str(user_id),
                    "server_time": clock.now().isoformat(),
                }
            )
        except WebSocketDisconnect:
            await session.close()
            return
        except Exception:
            await session.close()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    async def forward_user_events() -> None:
        try:
            async for event in realtime_broker.subscribe(f"user:{authenticated_user_id}"):
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            return

    async def drain_client() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                msg_text = msg.get("text")
                if not msg_text:
                    continue
                parsed_data: Any = None
                try:
                    parsed_data = json.loads(msg_text)
                except (json.JSONDecodeError, TypeError):
                    parsed_data = None
                if isinstance(parsed_data, dict) and parsed_data.get("type") == "AUTH":
                    await websocket.send_json(
                        {
                            "event_type": "AUTH_OK",
                            "user_id": str(authenticated_user_id),
                            "server_time": clock.now().isoformat(),
                        }
                    )
        except (WebSocketDisconnect, RuntimeError):
            return

    forward_task = asyncio.create_task(forward_user_events())
    drain_task = asyncio.create_task(drain_client())

    try:
        done, pending = await asyncio.wait(
            [forward_task, drain_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(
                exc, (asyncio.CancelledError, WebSocketDisconnect, RuntimeError)
            ):
                raise exc
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        await cleanup_tasks(forward_task, drain_task)
