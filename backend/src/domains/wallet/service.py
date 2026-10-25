import uuid
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.config import Settings, get_settings
from core.exceptions import DomainError, NotFoundError
from domains.wallet.repository import WalletRepository
from domains.wallet.schemas import (
    LedgerEntryItemResponse,
    StripeWebhookResponse,
    TopupCheckoutRequest,
    TopupCheckoutResponse,
    WalletHoldItemResponse,
    WalletSummaryResponse,
)
from ports.payment_port import PaymentGatewayPort
from shared.db.models.enums import LedgerEntryType
from shared.db.models.user import User

SUPPORTED_TOPUP_EVENTS = {"checkout.session.completed", "payment_intent.succeeded"}
TWO_PLACES = Decimal("0.01")


def _extract_event_user_id(data_object: dict[str, Any]) -> uuid.UUID:
    raw_user_id = data_object.get("client_reference_id")
    if not raw_user_id:
        metadata = data_object.get("metadata")
        if isinstance(metadata, dict):
            raw_user_id = metadata.get("user_id")
    if not isinstance(raw_user_id, str) or not raw_user_id.strip():
        raise DomainError(
            message="Stripe webhook event is missing user reference",
            error_code="INVALID_WEBHOOK_PAYLOAD",
            status_code=400,
        )
    try:
        return uuid.UUID(raw_user_id.strip())
    except ValueError as exc:
        raise DomainError(
            message="Invalid user UUID in Stripe webhook event",
            error_code="INVALID_WEBHOOK_PAYLOAD",
            status_code=400,
        ) from exc


def _extract_event_amount_usd(data_object: dict[str, Any]) -> Decimal:
    cents_val = data_object.get("amount_total")
    if cents_val is None:
        cents_val = data_object.get("amount_received")
    if cents_val is None:
        cents_val = data_object.get("amount")

    if isinstance(cents_val, int | float) and not isinstance(cents_val, bool):
        amount = (Decimal(str(cents_val)) / Decimal("100")).quantize(
            TWO_PLACES,
            rounding=ROUND_HALF_EVEN,
        )
    else:
        metadata = data_object.get("metadata")
        raw_amount = metadata.get("amount_usd") if isinstance(metadata, dict) else None
        if not isinstance(raw_amount, str | int | float) or isinstance(raw_amount, bool):
            raise DomainError(
                message="Stripe webhook event is missing payment amount",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                status_code=400,
            )
        amount = Decimal(str(raw_amount)).quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)

    if amount <= Decimal("0.00"):
        raise DomainError(
            message="Stripe webhook top-up amount must be greater than zero",
            error_code="INVALID_PAYMENT_AMOUNT",
            status_code=400,
        )
    return amount


class WalletService:
    def __init__(
        self,
        session: AsyncSession,
        clock: ClockPort,
        payment_gateway: PaymentGatewayPort,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._repo = WalletRepository(session)
        self._clock = clock
        self._payment_gateway = payment_gateway
        self._settings = settings or get_settings()

    async def get_wallet_summary(self, user_id: uuid.UUID) -> WalletSummaryResponse:
        wallet = await self._repo.get_or_create_wallet(user_id=user_id)
        holds_with_titles = await self._repo.list_active_and_claimable_holds(user_id=user_id)
        ledger_rows = await self._repo.list_recent_ledger_entries(wallet_id=wallet.id)
        await self._session.commit()

        hold_items = [
            WalletHoldItemResponse(
                id=hold.id,
                lot_id=hold.lot_id,
                lot_title=lot_title,
                amount=Decimal(hold.amount).quantize(TWO_PLACES),
                status=hold.status,
                created_at=hold.created_at,
                outbid_at=hold.outbid_at,
                claimed_at=hold.claimed_at,
            )
            for hold, lot_title in holds_with_titles
        ]

        ledger_items = [
            LedgerEntryItemResponse(
                id=entry.id,
                entry_type=entry.entry_type,
                amount=Decimal(entry.amount).quantize(TWO_PLACES),
                available_delta=Decimal(entry.available_delta).quantize(TWO_PLACES),
                held_delta=Decimal(entry.held_delta).quantize(TWO_PLACES),
                claimable_delta=Decimal(entry.claimable_delta).quantize(TWO_PLACES),
                balance_available_after=Decimal(entry.balance_available_after).quantize(TWO_PLACES),
                balance_held_after=Decimal(entry.balance_held_after).quantize(TWO_PLACES),
                balance_claimable_after=Decimal(entry.balance_claimable_after).quantize(TWO_PLACES),
                reference_lot_id=entry.reference_lot_id,
                reference_hold_id=entry.reference_hold_id,
                created_at=entry.created_at,
            )
            for entry in ledger_rows
        ]

        return WalletSummaryResponse(
            available_balance=Decimal(wallet.available_balance).quantize(TWO_PLACES),
            held_balance=Decimal(wallet.held_balance).quantize(TWO_PLACES),
            claimable_balance=Decimal(wallet.claimable_balance).quantize(TWO_PLACES),
            holds=hold_items,
            ledger_entries=ledger_items,
            server_time=self._clock.now(),
        )

    async def create_topup_checkout(
        self,
        user_id: uuid.UUID,
        payload: TopupCheckoutRequest,
    ) -> TopupCheckoutResponse:
        await self._repo.get_or_create_wallet(user_id=user_id)
        result = await self._payment_gateway.create_checkout_session(
            user_id=user_id,
            amount_usd=payload.amount_usd,
            success_url=self._settings.STRIPE_SUCCESS_URL,
            cancel_url=self._settings.STRIPE_CANCEL_URL,
        )
        await self._session.commit()
        return TopupCheckoutResponse(
            checkout_url=result.checkout_url,
            session_id=result.session_id,
            server_time=self._clock.now(),
        )

    async def process_stripe_webhook(
        self,
        raw_payload: bytes,
        signature: str | None,
    ) -> StripeWebhookResponse:
        now = self._clock.now()
        if not signature or not signature.strip():
            raise DomainError(
                message="Missing Stripe-Signature header",
                error_code="INVALID_STRIPE_SIGNATURE",
                status_code=400,
            )
        try:
            event = self._payment_gateway.verify_webhook_event(
                payload=raw_payload,
                signature=signature,
            )
        except DomainError as exc:
            if exc.error_code in {"INVALID_WEBHOOK_SIGNATURE", "INVALID_STRIPE_SIGNATURE"}:
                raise DomainError(
                    message=exc.message,
                    error_code="INVALID_STRIPE_SIGNATURE",
                    status_code=400,
                ) from exc
            raise

        stripe_event_id = str(event.get("id", "")).strip()
        event_type = str(event.get("type", "")).strip()
        if not stripe_event_id or not event_type:
            raise DomainError(
                message="Webhook event missing id or type",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                status_code=400,
            )

        if event_type not in SUPPORTED_TOPUP_EVENTS:
            return StripeWebhookResponse(
                status="ignored",
                stripe_event_id=stripe_event_id,
                idempotent_replay=False,
                server_time=now,
            )

        existing_event = await self._repo.get_stripe_webhook_event(stripe_event_id)
        if existing_event is not None:
            return StripeWebhookResponse(
                status="already_processed",
                stripe_event_id=stripe_event_id,
                idempotent_replay=True,
                server_time=now,
            )

        data_wrapper = event.get("data")
        data_object = data_wrapper.get("object") if isinstance(data_wrapper, dict) else None
        if not isinstance(data_object, dict):
            raise DomainError(
                message="Stripe webhook event data.object is missing",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                status_code=400,
            )

        user_id = _extract_event_user_id(data_object)
        amount_usd = _extract_event_amount_usd(data_object)

        user_row = (
            await self._session.execute(select(User.id).where(User.id == user_id))
        ).scalar_one_or_none()
        if user_row is None:
            raise NotFoundError(
                message="User referenced in Stripe webhook does not exist",
                error_code="USER_NOT_FOUND",
            )

        try:
            wallet = await self._repo.get_or_create_wallet(user_id=user_id, for_update=True)
            await self._repo.create_stripe_webhook_event(
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                user_id=user_id,
                amount_usd=amount_usd,
                processed_at=now,
            )

            wallet.available_balance = (Decimal(wallet.available_balance) + amount_usd).quantize(
                TWO_PLACES, rounding=ROUND_HALF_EVEN
            )
            wallet.held_balance = Decimal(wallet.held_balance).quantize(
                TWO_PLACES, rounding=ROUND_HALF_EVEN
            )
            wallet.claimable_balance = Decimal(wallet.claimable_balance).quantize(
                TWO_PLACES, rounding=ROUND_HALF_EVEN
            )
            wallet.updated_at = now
            await self._session.flush()

            await self._repo.create_ledger_entry(
                wallet=wallet,
                entry_type=LedgerEntryType.STRIPE_TOPUP,
                amount=amount_usd,
                available_delta=amount_usd,
                held_delta=Decimal("0.00"),
                claimable_delta=Decimal("0.00"),
                idempotency_key=f"stripe_topup:{stripe_event_id}",
            )
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return StripeWebhookResponse(
                status="already_processed",
                stripe_event_id=stripe_event_id,
                idempotent_replay=True,
                server_time=now,
            )

        return StripeWebhookResponse(
            status="processed",
            stripe_event_id=stripe_event_id,
            idempotent_replay=False,
            server_time=now,
        )
