import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.enums import LedgerEntryType, WalletHoldStatus
from shared.db.models.lot import Lot
from shared.db.models.wallet import (
    StripeWebhookEvent,
    Wallet,
    WalletHold,
    WalletLedgerEntry,
)


class WalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_wallet_by_user_id(
        self,
        user_id: uuid.UUID,
        for_update: bool = False,
    ) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_wallet(
        self,
        user_id: uuid.UUID,
        for_update: bool = False,
    ) -> Wallet:
        wallet = await self.get_wallet_by_user_id(user_id=user_id, for_update=for_update)
        if wallet is not None:
            return wallet
        new_wallet = Wallet(
            user_id=user_id,
            currency="USD",
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            claimable_balance=Decimal("0.00"),
        )
        self._session.add(new_wallet)
        await self._session.flush()
        if for_update:
            locked = await self.get_wallet_by_user_id(user_id=user_id, for_update=True)
            if locked is not None:
                return locked
        return new_wallet

    async def get_stripe_webhook_event(
        self,
        stripe_event_id: str,
    ) -> StripeWebhookEvent | None:
        stmt = select(StripeWebhookEvent).where(
            StripeWebhookEvent.stripe_event_id == stripe_event_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_stripe_webhook_event(
        self,
        stripe_event_id: str,
        event_type: str,
        user_id: uuid.UUID,
        amount_usd: Decimal,
        processed_at: datetime,
    ) -> StripeWebhookEvent:
        event_record = StripeWebhookEvent(
            stripe_event_id=stripe_event_id,
            event_type=event_type,
            user_id=user_id,
            amount_usd=amount_usd,
            processed_at=processed_at,
        )
        self._session.add(event_record)
        await self._session.flush()
        return event_record

    async def create_ledger_entry(
        self,
        wallet: Wallet,
        entry_type: LedgerEntryType,
        amount: Decimal,
        available_delta: Decimal,
        held_delta: Decimal,
        claimable_delta: Decimal,
        idempotency_key: str,
        reference_lot_id: uuid.UUID | None = None,
        reference_hold_id: uuid.UUID | None = None,
    ) -> WalletLedgerEntry:
        entry = WalletLedgerEntry(
            wallet_id=wallet.id,
            user_id=wallet.user_id,
            entry_type=entry_type,
            amount=amount,
            available_delta=available_delta,
            held_delta=held_delta,
            claimable_delta=claimable_delta,
            balance_available_after=wallet.available_balance,
            balance_held_after=wallet.held_balance,
            balance_claimable_after=wallet.claimable_balance,
            reference_lot_id=reference_lot_id,
            reference_hold_id=reference_hold_id,
            idempotency_key=idempotency_key,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_active_and_claimable_holds(
        self,
        user_id: uuid.UUID,
    ) -> list[tuple[WalletHold, str]]:
        stmt = (
            select(WalletHold, Lot.title)
            .join(Lot, WalletHold.lot_id == Lot.id)
            .where(
                WalletHold.user_id == user_id,
                WalletHold.status.in_([WalletHoldStatus.ACTIVE_HOLD, WalletHoldStatus.CLAIMABLE]),
            )
            .order_by(WalletHold.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [(row[0], str(row[1])) for row in result.all()]

    async def list_recent_ledger_entries(
        self,
        wallet_id: uuid.UUID,
        limit: int = 50,
    ) -> list[WalletLedgerEntry]:
        stmt = (
            select(WalletLedgerEntry)
            .where(WalletLedgerEntry.wallet_id == wallet_id)
            .order_by(WalletLedgerEntry.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
