import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from domains.auth.dependencies import get_clock, get_current_user
from domains.bidding.router import get_realtime_broker
from domains.escrow.schemas import (
    DisputeOrderRequest,
    EscrowOrderListResponse,
    EscrowOrderResponse,
    ShipOrderRequest,
)
from domains.escrow.service import EscrowService
from ports.realtime_port import RealtimeBrokerPort
from shared.db.models.enums import EscrowOrderStatus
from shared.db.models.user import User
from shared.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["escrow"])


def get_escrow_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    realtime_broker: Annotated[RealtimeBrokerPort, Depends(get_realtime_broker)],
) -> EscrowService:
    return EscrowService(
        session=session,
        clock=clock,
        realtime_broker=realtime_broker,
    )


@router.get(
    "/orders",
    response_model=EscrowOrderListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[EscrowService, Depends(get_escrow_service)],
    role: Annotated[str | None, Query()] = None,
    order_status: Annotated[EscrowOrderStatus | None, Query(alias="status")] = None,
) -> EscrowOrderListResponse:
    return await service.list_orders(
        user_id=current_user.id,
        role=role,
        status=order_status,
    )


@router.get(
    "/orders/{order_id}",
    response_model=EscrowOrderResponse,
    status_code=status.HTTP_200_OK,
)
async def get_order(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[EscrowService, Depends(get_escrow_service)],
) -> EscrowOrderResponse:
    return await service.get_order(
        order_id=order_id,
        current_user_id=current_user.id,
    )


@router.post(
    "/orders/{order_id}/ship",
    response_model=EscrowOrderResponse,
    status_code=status.HTTP_200_OK,
)
async def ship_order(
    order_id: uuid.UUID,
    payload: ShipOrderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[EscrowService, Depends(get_escrow_service)],
) -> EscrowOrderResponse:
    return await service.ship_order(
        order_id=order_id,
        current_user_id=current_user.id,
        payload=payload,
    )


@router.post(
    "/orders/{order_id}/confirm-receipt",
    response_model=EscrowOrderResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_receipt(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[EscrowService, Depends(get_escrow_service)],
) -> EscrowOrderResponse:
    return await service.confirm_receipt(
        order_id=order_id,
        current_user_id=current_user.id,
    )


@router.post(
    "/orders/{order_id}/dispute",
    response_model=EscrowOrderResponse,
    status_code=status.HTTP_200_OK,
)
async def dispute_order(
    order_id: uuid.UUID,
    payload: DisputeOrderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[EscrowService, Depends(get_escrow_service)],
) -> EscrowOrderResponse:
    return await service.dispute_order(
        order_id=order_id,
        current_user_id=current_user.id,
        payload=payload,
    )
