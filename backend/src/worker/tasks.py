import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from core.clock import ClockPort, SystemClock
from core.config import get_settings
from domains.bidding.router import get_realtime_broker
from domains.bidding.service import BiddingService
from ports.realtime_port import RealtimeBrokerPort
from shared.db.session import get_engine, get_session_maker
from worker.broker import broker


@broker.task(task_name="finalize_expired_lot_job")
async def finalize_expired_lot_job(
    lot_id: uuid.UUID | str,
    expected_ends_at_iso: str | None = None,
    session: AsyncSession | None = None,
    clock: ClockPort | None = None,
    realtime_broker: RealtimeBrokerPort | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    resolved_lot_id = uuid.UUID(str(lot_id))
    resolved_clock = clock or SystemClock()
    settings = get_settings()

    if realtime_broker is not None:
        resolved_broker = realtime_broker
    elif database_url is not None or settings.APP_ENV == "test":
        resolved_broker = InMemoryRealtimeBrokerAdapter()
    else:
        resolved_broker = get_realtime_broker()

    if session is not None:
        service = BiddingService(
            session=session,
            clock=resolved_clock,
            realtime_broker=resolved_broker,
        )
        return await service.finalize_lot(
            lot_id=resolved_lot_id,
            expected_ends_at_iso=expected_ends_at_iso,
        )

    custom_engine: AsyncEngine | None = None
    if database_url is not None:
        custom_engine = get_engine(database_url)
        session_maker = get_session_maker(custom_engine)
    elif settings.APP_ENV == "test":
        custom_engine = get_engine(settings.test_database_url_str)
        session_maker = get_session_maker(custom_engine)
    else:
        session_maker = get_session_maker()

    try:
        async with session_maker() as new_session:
            service = BiddingService(
                session=new_session,
                clock=resolved_clock,
                realtime_broker=resolved_broker,
            )
            return await service.finalize_lot(
                lot_id=resolved_lot_id,
                expected_ends_at_iso=expected_ends_at_iso,
            )
    finally:
        if custom_engine is not None:
            await custom_engine.dispose()
