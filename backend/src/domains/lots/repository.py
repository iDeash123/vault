import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.db.models.lot import Lot, LotMedia


class LotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_lot(self, lot: Lot) -> Lot:
        self.session.add(lot)
        await self.session.flush()
        return lot

    async def get_lot_by_id(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = select(Lot).where(Lot.id == lot_id).options(selectinload(Lot.media))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lot_by_id_for_update(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = (
            select(Lot).where(Lot.id == lot_id).with_for_update().options(selectinload(Lot.media))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_media(self, media: LotMedia) -> LotMedia:
        self.session.add(media)
        await self.session.flush()
        return media

    async def get_lot_media(self, lot_id: uuid.UUID) -> list[LotMedia]:
        stmt = select(LotMedia).where(LotMedia.lot_id == lot_id).order_by(LotMedia.sort_order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
