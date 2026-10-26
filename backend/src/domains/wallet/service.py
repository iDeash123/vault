import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.config import Settings, get_settings
from core.exceptions import ConflictError, DomainError, ForbiddenError, NotFoundError
from domains.wallet.repository import WalletRepository
from domains.wallet.schemas import (
    ClaimAllHoldsResponse,
    ClaimHoldResponse,
    LedgerEntryItemResponse,
    StripeWebhookResponse,
    TopupCheckoutRequest,
    TopupCheckoutResponse,
    WalletHoldItemResponse,
    WalletSummaryResponse,
)
from ports.payment_port import PaymentGatewayPort
from shared.db.models.enums import LedgerEntryType, WalletHoldStatus
from shared.db.models.user import User
from shared.db.models.wallet import Wallet, WalletHold

SUPPORTED_TOPUP_EVENTS = {"checkout.session.completed", "payment_intent.succeeded"}
BID_LOCK_ENTRY_TYPES = {
    LedgerEntryType.BID_LOCK,
    LedgerEntryType.BUY_NOW_LOCK,
}
CLAIMABLE_TRANSITION_ENTRY_TYPES = {
    LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
    LedgerEntryType.BID_RELEASED_TO_CLAIMABLE,
}
TWO_PLACES = Decimal("0.01")


def quantize_usd(value: Decimal) -> Decimal:
    dec = Decimal(value)
    if not dec.is_finite():
        raise DomainError(
            message="Monetary amount must be a finite number",
            error_code="INVALID_MONETARY_AMOUNT",
            status_code=400,
        )
    return dec.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


def validate_exact_usd(value: Decimal, error_code: str, field_label: str) -> Decimal:
    dec = Decimal(value)
    if not dec.is_finite():
        raise DomainError(
            message=f"{field_label} must be a finite number",
            error_code=error_code,
            status_code=400,
        )
    quantized = dec.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)
    if quantized != dec:
        raise DomainError(
            message=f"{field_label} must have at most 2 decimal places",
            error_code=error_code,
            status_code=400,
        )
    return quantized


def validate_idempotency_key(raw_key: str) -> str:
    cleaned = raw_key.strip()
    if not cleaned or len(cleaned) > 128:
        raise DomainError(
            message="Idempotency key must be between 1 and 128 characters",
            error_code="INVALID_IDEMPOTENCY_KEY",
            status_code=400,
        )
    return cleaned


def ensure_sufficient_available_balance(wallet: Wallet, required_amount: Decimal) -> None:
    avail = quantize_usd(wallet.available_balance)
    claimable = quantize_usd(wallet.claimable_balance)
    req = quantize_usd(required_amount)
    if avail >= req:
        return
    message = f"Available balance {avail} USD is less than required bid {req} USD."
    if claimable > Decimal("0.00"):
        message = (
            f"{message} Note: you have {claimable} USD in claimable outbid holds "
            "that can be manually claimed."
        )
    raise DomainError(
        message=message,
        error_code="INSUFFICIENT_AVAILABLE_BALANCE",
        status_code=400,
        details={
            "available_balance": str(avail),
            "claimable_balance": str(claimable),
            "required_amount": str(req),
        },
    )


def apply_wallet_topup(
    wallet: Wallet,
    amount_usd: Decimal,
    now: datetime,
) -> tuple[Decimal, Decimal, Decimal]:
    amt = validate_exact_usd(amount_usd, "INVALID_PAYMENT_AMOUNT", "Top-up amount")
    if amt <= Decimal("0.00"):
        raise DomainError(
            message="Top-up amount must be greater than zero",
            error_code="INVALID_PAYMENT_AMOUNT",
            status_code=400,
        )
    wallet.available_balance = quantize_usd(Decimal(wallet.available_balance) + amt)
    wallet.held_balance = quantize_usd(wallet.held_balance)
    wallet.claimable_balance = quantize_usd(wallet.claimable_balance)
    wallet.updated_at = now
    return amt, Decimal("0.00"), Decimal("0.00")


def apply_bid_lock(
    wallet: Wallet,
    amount: Decimal,
    now: datetime,
) -> tuple[Decimal, Decimal, Decimal]:
    amt = validate_exact_usd(amount, "INVALID_BID_AMOUNT", "Bid lock amount")
    if amt <= Decimal("0.00"):
        raise DomainError(
            message="Bid lock amount must be greater than zero",
            error_code="INVALID_BID_AMOUNT",
            status_code=400,
        )
    ensure_sufficient_available_balance(wallet=wallet, required_amount=amt)
    wallet.available_balance = quantize_usd(Decimal(wallet.available_balance) - amt)
    wallet.held_balance = quantize_usd(Decimal(wallet.held_balance) + amt)
    wallet.claimable_balance = quantize_usd(wallet.claimable_balance)
    wallet.updated_at = now
    return -amt, amt, Decimal("0.00")


def apply_hold_to_claimable(
    wallet: Wallet,
    hold: WalletHold,
    now: datetime,
    entry_type: LedgerEntryType = LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
) -> tuple[Decimal, Decimal, Decimal]:
    if entry_type not in CLAIMABLE_TRANSITION_ENTRY_TYPES:
        raise DomainError(
            message=f"Unsupported ledger entry type {entry_type} for claimable transition",
            error_code="INVALID_LEDGER_ENTRY_TYPE",
            status_code=400,
        )
    if hold.status != WalletHoldStatus.ACTIVE_HOLD:
        raise ConflictError(
            message=f"Hold {hold.id} cannot transition to CLAIMABLE from status {hold.status}",
            error_code="INVALID_HOLD_STATE",
            details={"hold_id": str(hold.id), "status": str(hold.status)},
        )
    amt = quantize_usd(hold.amount)
    held = quantize_usd(wallet.held_balance)
    if held < amt:
        raise ConflictError(
            message="Wallet held balance is less than active hold amount",
            error_code="INCONSISTENT_HELD_BALANCE",
            details={"held_balance": str(held), "hold_amount": str(amt)},
        )
    hold.status = WalletHoldStatus.CLAIMABLE
    hold.outbid_at = now
    wallet.available_balance = quantize_usd(wallet.available_balance)
    wallet.held_balance = quantize_usd(held - amt)
    wallet.claimable_balance = quantize_usd(Decimal(wallet.claimable_balance) + amt)
    wallet.updated_at = now
    return Decimal("0.00"), -amt, amt


def apply_manual_hold_claim(
    wallet: Wallet,
    hold: WalletHold,
    requesting_user_id: uuid.UUID,
    now: datetime,
) -> tuple[Decimal, Decimal, Decimal]:
    if hold.user_id != requesting_user_id:
        raise ForbiddenError(
            message="Cannot claim a wallet hold belonging to another user",
            error_code="HOLD_OWNERSHIP_MISMATCH",
            details={"hold_id": str(hold.id)},
        )
    if hold.status == WalletHoldStatus.CLAIMED:
        raise ConflictError(
            message="Hold has already been claimed",
            error_code="HOLD_ALREADY_CLAIMED",
            details={"hold_id": str(hold.id)},
        )
    if hold.status != WalletHoldStatus.CLAIMABLE:
        raise ConflictError(
            message=f"Hold in status {hold.status} cannot be claimed",
            error_code="HOLD_NOT_CLAIMABLE",
            details={"hold_id": str(hold.id), "status": str(hold.status)},
        )
    amt = quantize_usd(hold.amount)
    claimable = quantize_usd(wallet.claimable_balance)
    if claimable < amt:
        raise ConflictError(
            message="Wallet claimable balance is less than claimable hold amount",
            error_code="INCONSISTENT_CLAIMABLE_BALANCE",
            details={"claimable_balance": str(claimable), "hold_amount": str(amt)},
        )
    hold.status = WalletHoldStatus.CLAIMED
    hold.claimed_at = now
    wallet.claimable_balance = quantize_usd(claimable - amt)
    wallet.available_balance = quantize_usd(Decimal(wallet.available_balance) + amt)
    wallet.held_balance = quantize_usd(wallet.held_balance)
    wallet.updated_at = now
    return amt, Decimal("0.00"), -amt


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
                amount=quantize_usd(hold.amount),
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
                amount=quantize_usd(entry.amount),
                available_delta=quantize_usd(entry.available_delta),
                held_delta=quantize_usd(entry.held_delta),
                claimable_delta=quantize_usd(entry.claimable_delta),
                balance_available_after=quantize_usd(entry.balance_available_after),
                balance_held_after=quantize_usd(entry.balance_held_after),
                balance_claimable_after=quantize_usd(entry.balance_claimable_after),
                reference_lot_id=entry.reference_lot_id,
                reference_hold_id=entry.reference_hold_id,
                created_at=entry.created_at,
            )
            for entry in ledger_rows
        ]

        return WalletSummaryResponse(
            available_balance=quantize_usd(wallet.available_balance),
            held_balance=quantize_usd(wallet.held_balance),
            claimable_balance=quantize_usd(wallet.claimable_balance),
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

            avail_delta, held_delta, claim_delta = apply_wallet_topup(
                wallet=wallet,
                amount_usd=amount_usd,
                now=now,
            )
            await self._session.flush()

            await self._repo.create_ledger_entry(
                wallet=wallet,
                entry_type=LedgerEntryType.STRIPE_TOPUP,
                amount=amount_usd,
                available_delta=avail_delta,
                held_delta=held_delta,
                claimable_delta=claim_delta,
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

    async def lock_funds_for_bid(
        self,
        user_id: uuid.UUID,
        lot_id: uuid.UUID,
        amount: Decimal,
        idempotency_key: str,
        entry_type: LedgerEntryType = LedgerEntryType.BID_LOCK,
    ) -> WalletHold:
        now = self._clock.now()
        cleaned_key = validate_idempotency_key(idempotency_key)
        if entry_type not in BID_LOCK_ENTRY_TYPES:
            raise DomainError(
                message=f"Unsupported ledger entry type {entry_type} for bid lock",
                error_code="INVALID_LEDGER_ENTRY_TYPE",
                status_code=400,
            )
        quantized_amount = validate_exact_usd(amount, "INVALID_BID_AMOUNT", "Bid lock amount")
        if quantized_amount <= Decimal("0.00"):
            raise DomainError(
                message="Bid lock amount must be greater than zero",
                error_code="INVALID_BID_AMOUNT",
                status_code=400,
            )

        active_hold = await self._repo.get_active_hold_for_lot(lot_id=lot_id, for_update=True)
        wallet = await self._repo.get_or_create_wallet(user_id=user_id, for_update=True)

        existing_entry = await self._repo.get_ledger_entry_by_idempotency_key(cleaned_key)
        if existing_entry is not None:
            if (
                existing_entry.entry_type != entry_type
                or existing_entry.user_id != user_id
                or existing_entry.reference_lot_id != lot_id
                or quantize_usd(existing_entry.amount) != quantized_amount
                or existing_entry.reference_hold_id is None
            ):
                raise ConflictError(
                    message="Idempotency key already used with different bid lock parameters",
                    error_code="IDEMPOTENCY_KEY_CONFLICT",
                )
            existing_hold = await self._repo.get_hold_by_id(existing_entry.reference_hold_id)
            if existing_hold is not None:
                return existing_hold

        if active_hold is not None:
            raise ConflictError(
                message="Lot already has an active hold that must transition to CLAIMABLE first",
                error_code="ACTIVE_HOLD_ALREADY_EXISTS",
                details={"lot_id": str(lot_id), "active_hold_id": str(active_hold.id)},
            )

        avail_delta, held_delta, claim_delta = apply_bid_lock(
            wallet=wallet,
            amount=quantized_amount,
            now=now,
        )
        hold = await self._repo.create_hold(
            wallet_id=wallet.id,
            user_id=user_id,
            lot_id=lot_id,
            amount=quantized_amount,
            status=WalletHoldStatus.ACTIVE_HOLD,
            created_at=now,
        )
        await self._repo.create_ledger_entry(
            wallet=wallet,
            entry_type=entry_type,
            amount=quantized_amount,
            available_delta=avail_delta,
            held_delta=held_delta,
            claimable_delta=claim_delta,
            idempotency_key=cleaned_key,
            reference_lot_id=lot_id,
            reference_hold_id=hold.id,
        )
        return hold

    async def transition_hold_to_claimable(
        self,
        hold_id: uuid.UUID,
        entry_type: LedgerEntryType = LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
        idempotency_key: str | None = None,
    ) -> WalletHold:
        now = self._clock.now()
        if entry_type not in CLAIMABLE_TRANSITION_ENTRY_TYPES:
            raise DomainError(
                message=f"Unsupported ledger entry type {entry_type} for claimable transition",
                error_code="INVALID_LEDGER_ENTRY_TYPE",
                status_code=400,
            )
        cleaned_key = (
            validate_idempotency_key(idempotency_key) if idempotency_key is not None else None
        )
        hold = await self._repo.get_hold_by_id(hold_id=hold_id, for_update=True)
        if hold is None:
            raise NotFoundError(
                message="Wallet hold not found",
                error_code="HOLD_NOT_FOUND",
            )
        wallet = await self._repo.get_or_create_wallet(user_id=hold.user_id, for_update=True)
        avail_delta, held_delta, claim_delta = apply_hold_to_claimable(
            wallet=wallet,
            hold=hold,
            now=now,
            entry_type=entry_type,
        )
        await self._session.flush()
        resolved_key = cleaned_key if cleaned_key is not None else f"hold_to_claimable:{hold.id}"
        await self._repo.create_ledger_entry(
            wallet=wallet,
            entry_type=entry_type,
            amount=quantize_usd(hold.amount),
            available_delta=avail_delta,
            held_delta=held_delta,
            claimable_delta=claim_delta,
            idempotency_key=resolved_key,
            reference_lot_id=hold.lot_id,
            reference_hold_id=hold.id,
        )
        return hold

    async def claim_hold_manually(
        self,
        user_id: uuid.UUID,
        hold_id: uuid.UUID,
    ) -> ClaimHoldResponse:
        now = self._clock.now()
        hold = await self._repo.get_hold_by_id(hold_id=hold_id, for_update=True)
        if hold is None:
            raise NotFoundError(
                message="Wallet hold not found",
                error_code="HOLD_NOT_FOUND",
            )
        if hold.user_id != user_id:
            raise ForbiddenError(
                message="Cannot claim a wallet hold belonging to another user",
                error_code="HOLD_OWNERSHIP_MISMATCH",
                details={"hold_id": str(hold.id)},
            )
        wallet = await self._repo.get_or_create_wallet(user_id=hold.user_id, for_update=True)
        avail_delta, held_delta, claim_delta = apply_manual_hold_claim(
            wallet=wallet,
            hold=hold,
            requesting_user_id=user_id,
            now=now,
        )
        claimed_amount = quantize_usd(hold.amount)
        await self._session.flush()
        await self._repo.create_ledger_entry(
            wallet=wallet,
            entry_type=LedgerEntryType.BID_MANUAL_CLAIM,
            amount=claimed_amount,
            available_delta=avail_delta,
            held_delta=held_delta,
            claimable_delta=claim_delta,
            idempotency_key=f"manual_claim:{hold.id}",
            reference_lot_id=hold.lot_id,
            reference_hold_id=hold.id,
        )
        lot_title = await self._repo.get_lot_title(hold.lot_id)
        await self._session.commit()

        return ClaimHoldResponse(
            hold=WalletHoldItemResponse(
                id=hold.id,
                lot_id=hold.lot_id,
                lot_title=lot_title,
                amount=claimed_amount,
                status=hold.status,
                created_at=hold.created_at,
                outbid_at=hold.outbid_at,
                claimed_at=hold.claimed_at,
            ),
            claimed_amount=claimed_amount,
            available_balance=quantize_usd(wallet.available_balance),
            held_balance=quantize_usd(wallet.held_balance),
            claimable_balance=quantize_usd(wallet.claimable_balance),
            server_time=now,
        )

    async def claim_all_holds(
        self,
        user_id: uuid.UUID,
    ) -> ClaimAllHoldsResponse:
        now = self._clock.now()
        claimable_holds = await self._repo.list_claimable_holds_for_user(
            user_id=user_id,
            for_update=True,
        )
        wallet = await self._repo.get_or_create_wallet(user_id=user_id, for_update=True)

        total_claimed = Decimal("0.00")
        claimed_ids: list[uuid.UUID] = []

        for hold in claimable_holds:
            avail_delta, held_delta, claim_delta = apply_manual_hold_claim(
                wallet=wallet,
                hold=hold,
                requesting_user_id=user_id,
                now=now,
            )
            amount = quantize_usd(hold.amount)
            await self._session.flush()
            await self._repo.create_ledger_entry(
                wallet=wallet,
                entry_type=LedgerEntryType.BID_MANUAL_CLAIM,
                amount=amount,
                available_delta=avail_delta,
                held_delta=held_delta,
                claimable_delta=claim_delta,
                idempotency_key=f"manual_claim:{hold.id}",
                reference_lot_id=hold.lot_id,
                reference_hold_id=hold.id,
            )
            total_claimed = quantize_usd(total_claimed + amount)
            claimed_ids.append(hold.id)

        await self._session.commit()
        return ClaimAllHoldsResponse(
            claimed_count=len(claimed_ids),
            claimed_amount=total_claimed,
            claimed_hold_ids=claimed_ids,
            available_balance=quantize_usd(wallet.available_balance),
            held_balance=quantize_usd(wallet.held_balance),
            claimable_balance=quantize_usd(wallet.claimable_balance),
            server_time=now,
        )
