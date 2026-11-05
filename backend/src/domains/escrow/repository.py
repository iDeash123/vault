import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.enums import EscrowOrderStatus
from shared.db.models.escrow import EscrowOrder
from shared.db.models.lot import Lot
from shared.db.models.wallet import Wallet, WalletHold, WalletLedgerEntry


class EscrowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_order_by_id(
        self,
        order_id: uuid.UUID,
        for_update: bool = False,
    ) -> EscrowOrder | None:
        stmt = select(EscrowOrder).where(EscrowOrder.id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_order_with_lot_title(
        self,
        order_id: uuid.UUID,
        for_update: bool = False,
    ) -> tuple[EscrowOrder, str] | None:
        stmt = (
            select(EscrowOrder, Lot.title)
            .join(Lot, EscrowOrder.lot_id == Lot.id)
            .where(EscrowOrder.id == order_id)
        )
        if for_update:
            stmt = stmt.with_for_update(of=EscrowOrder)
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return row[0], str(row[1])

    async def get_lot_for_update(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = select(Lot).where(Lot.id == lot_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_hold_for_update(self, hold_id: uuid.UUID) -> WalletHold | None:
        stmt = select(WalletHold).where(WalletHold.id == hold_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_wallets_for_update(
        self,
        user_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, Wallet]:
        unique_sorted = sorted(set(user_ids))
        stmt = (
            select(Wallet)
            .where(Wallet.user_id.in_(unique_sorted))
            .order_by(Wallet.user_id.asc())
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        wallets = list(result.scalars().all())
        return {w.user_id: w for w in wallets}

    async def create_ledger_entry(self, entry: WalletLedgerEntry) -> WalletLedgerEntry:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_orders_for_user(
        self,
        user_id: uuid.UUID,
        role: str | None = None,
        status: EscrowOrderStatus | None = None,
    ) -> list[tuple[EscrowOrder, str]]:
        role_norm = role.strip().lower() if role else None
        stmt = select(EscrowOrder, Lot.title).join(Lot, EscrowOrder.lot_id == Lot.id)
        if role_norm == "buyer":
            stmt = stmt.where(EscrowOrder.buyer_id == user_id)
        elif role_norm == "seller":
            stmt = stmt.where(EscrowOrder.seller_id == user_id)
        else:
            stmt = stmt.where(
                or_(
                    EscrowOrder.buyer_id == user_id,
                    EscrowOrder.seller_id == user_id,
                )
            )

        if status is not None:
            stmt = stmt.where(EscrowOrder.status == status)

        stmt = stmt.order_by(EscrowOrder.created_at.desc())
        result = await self._session.execute(stmt)
        return [(row[0], str(row[1])) for row in result.all()]
