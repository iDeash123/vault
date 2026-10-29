import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.bid import Bid
from shared.db.models.enums import WalletHoldStatus
from shared.db.models.escrow import EscrowOrder
from shared.db.models.lot import Lot
from shared.db.models.user import User
from shared.db.models.wallet import Wallet, WalletHold, WalletLedgerEntry


class BiddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_lot_for_update(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = (
            select(Lot)
            .where(Lot.id == lot_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_hold_for_lot_for_update(self, lot_id: uuid.UUID) -> WalletHold | None:
        stmt = (
            select(WalletHold)
            .where(
                WalletHold.lot_id == lot_id,
                WalletHold.status == WalletHoldStatus.ACTIVE_HOLD,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_wallets_for_update(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Wallet]:
        unique_sorted_ids = sorted(set(user_ids))
        stmt = (
            select(Wallet)
            .where(Wallet.user_id.in_(unique_sorted_ids))
            .order_by(Wallet.user_id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        wallets_map = {w.user_id: w for w in result.scalars().all()}
        for uid in unique_sorted_ids:
            if uid not in wallets_map:
                new_wallet = Wallet(user_id=uid)
                self.session.add(new_wallet)
                await self.session.flush()
                wallets_map[uid] = new_wallet
        return wallets_map

    async def get_bid_by_idempotency_key(self, idempotency_key: str) -> Bid | None:
        stmt = select(Bid).where(Bid.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_bid_by_id(self, bid_id: uuid.UUID) -> Bid | None:
        stmt = select(Bid).where(Bid.id == bid_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_bid(self, bid: Bid) -> Bid:
        self.session.add(bid)
        await self.session.flush()
        return bid

    async def create_hold(self, hold: WalletHold) -> WalletHold:
        self.session.add(hold)
        await self.session.flush()
        return hold

    async def get_hold_by_id(self, hold_id: uuid.UUID) -> WalletHold | None:
        stmt = select(WalletHold).where(WalletHold.id == hold_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_ledger_entry(self, entry: WalletLedgerEntry) -> WalletLedgerEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_escrow_order_by_lot_id(self, lot_id: uuid.UUID) -> EscrowOrder | None:
        stmt = select(EscrowOrder).where(EscrowOrder.lot_id == lot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_escrow_order(self, order: EscrowOrder) -> EscrowOrder:
        self.session.add(order)
        await self.session.flush()
        return order
