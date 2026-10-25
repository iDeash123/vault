from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.payment_stripe import StripePaymentGatewayAdapter
from core.clock import ClockPort
from domains.auth.dependencies import get_clock, get_current_user
from domains.wallet.schemas import (
    StripeWebhookResponse,
    TopupCheckoutRequest,
    TopupCheckoutResponse,
    WalletSummaryResponse,
)
from domains.wallet.service import WalletService
from ports.payment_port import PaymentGatewayPort
from shared.db.models.user import User
from shared.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["wallet"])


def get_payment_gateway() -> PaymentGatewayPort:
    return StripePaymentGatewayAdapter()


def get_wallet_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    payment_gateway: Annotated[PaymentGatewayPort, Depends(get_payment_gateway)],
) -> WalletService:
    return WalletService(
        session=session,
        clock=clock,
        payment_gateway=payment_gateway,
    )


@router.get("/wallet", response_model=WalletSummaryResponse)
async def get_wallet(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> WalletSummaryResponse:
    return await service.get_wallet_summary(user_id=current_user.id)


@router.post("/wallet/topup/checkout", response_model=TopupCheckoutResponse)
async def create_topup_checkout(
    payload: TopupCheckoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> TopupCheckoutResponse:
    return await service.create_topup_checkout(
        user_id=current_user.id,
        payload=payload,
    )


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    service: Annotated[WalletService, Depends(get_wallet_service)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> StripeWebhookResponse:
    raw_payload = await request.body()
    return await service.process_stripe_webhook(
        raw_payload=raw_payload,
        signature=stripe_signature,
    )
