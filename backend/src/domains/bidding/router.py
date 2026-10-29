import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.realtime_fake import InMemoryRealtimeBrokerAdapter
from adapters.realtime_redis import RedisRealtimeBrokerAdapter
from core.clock import ClockPort
from core.config import get_settings
from core.exceptions import DomainError
from domains.auth.dependencies import get_clock, get_current_user
from domains.bidding.schemas import BidResponse, PlaceBidRequest
from domains.bidding.service import BiddingService
from ports.realtime_port import RealtimeBrokerPort
from shared.db.models.user import User
from shared.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["bidding"])

_in_memory_broker: RealtimeBrokerPort | None = None
_redis_broker: RealtimeBrokerPort | None = None


def get_realtime_broker() -> RealtimeBrokerPort:
    global _in_memory_broker, _redis_broker
    settings = get_settings()
    if settings.APP_ENV == "test":
        if _in_memory_broker is None:
            _in_memory_broker = InMemoryRealtimeBrokerAdapter()
        return _in_memory_broker
    if _redis_broker is None:
        _redis_broker = RedisRealtimeBrokerAdapter()
    return _redis_broker


def get_bidding_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    realtime_broker: Annotated[RealtimeBrokerPort, Depends(get_realtime_broker)],
) -> BiddingService:
    return BiddingService(
        session=session,
        clock=clock,
        realtime_broker=realtime_broker,
    )


@router.post(
    "/lots/{lot_id}/bids",
    response_model=BidResponse,
    status_code=status.HTTP_201_CREATED,
)
async def place_bid_endpoint(
    lot_id: uuid.UUID,
    payload: PlaceBidRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BiddingService, Depends(get_bidding_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BidResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise DomainError(
            message="Idempotency-Key header is required",
            error_code="MISSING_IDEMPOTENCY_KEY",
            status_code=400,
        )
    return await service.place_bid(
        lot_id=lot_id,
        bidder_id=current_user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
