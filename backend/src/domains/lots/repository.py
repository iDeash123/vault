import uuid
from decimal import Decimal

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domains.lots.schemas import LotSortOrder
from shared.db.models.bid import Bid
from shared.db.models.enums import LotCategory, LotStatus
from shared.db.models.lot import Lot, LotMedia
from shared.db.models.user import User


class LotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_lot(self, lot: Lot) -> Lot:
        self.session.add(lot)
        await self.session.flush()
        return lot

    async def get_lot_by_id(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = (
            select(Lot)
            .where(Lot.id == lot_id)
            .options(selectinload(Lot.media))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lot_by_id_for_update(self, lot_id: uuid.UUID) -> Lot | None:
        stmt = (
            select(Lot)
            .where(Lot.id == lot_id)
            .with_for_update()
            .options(selectinload(Lot.media))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_media(self, media: LotMedia) -> LotMedia:
        self.session.add(media)
        await self.session.flush()
        return media

    async def count_media(self, lot_id: uuid.UUID) -> int:
        stmt = select(func.count(LotMedia.id)).where(LotMedia.lot_id == lot_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_lot_media(self, lot_id: uuid.UUID) -> list[LotMedia]:
        stmt = select(LotMedia).where(LotMedia.lot_id == lot_id).order_by(LotMedia.sort_order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_lot_recent_bids(
        self,
        lot_id: uuid.UUID,
        limit: int = 20,
    ) -> list[tuple[Bid, str]]:
        stmt = (
            select(Bid, User.username)
            .join(User, Bid.bidder_id == User.id)
            .where(Bid.lot_id == lot_id)
            .order_by(Bid.created_at.desc(), Bid.amount.desc(), Bid.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def list_lots(
        self,
        q: str | None = None,
        category: LotCategory | None = None,
        status: LotStatus | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sort: LotSortOrder = LotSortOrder.ENDING_SOON,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Lot], int]:
        filters = []
        if category is not None:
            filters.append(Lot.category == category)
        if status is not None:
            filters.append(Lot.status == status)

        effective_price = case(
            (Lot.bid_count > 0, Lot.current_price),
            else_=Lot.start_price,
        )

        if min_price is not None:
            filters.append(effective_price >= min_price)
        if max_price is not None:
            filters.append(effective_price <= max_price)

        if q is not None and q.strip():
            clean_q = q.strip()
            escaped_q = clean_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            ts_query = func.plainto_tsquery("english", clean_q)
            search_condition = or_(
                Lot.search_vector.op("@@")(ts_query),
                Lot.title.op("%")(clean_q),
                Lot.title.op("%>")(clean_q),
                func.word_similarity(clean_q, Lot.title) >= 0.35,
                func.word_similarity(clean_q, Lot.subtitle) >= 0.35,
                func.word_similarity(clean_q, cast(Lot.specs, String)) >= 0.35,
                Lot.title.ilike(f"%{escaped_q}%", escape="\\"),
                Lot.subtitle.ilike(f"%{escaped_q}%", escape="\\"),
                Lot.description.ilike(f"%{escaped_q}%", escape="\\"),
                cast(Lot.specs, String).ilike(f"%{escaped_q}%", escape="\\"),
            )
            filters.append(search_condition)

        count_stmt = select(func.count(Lot.id)).where(*filters)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        stmt = (
            select(Lot)
            .where(*filters)
            .options(selectinload(Lot.media))
            .execution_options(populate_existing=True)
        )

        if sort == LotSortOrder.ENDING_SOON:
            stmt = stmt.order_by(Lot.ends_at.asc(), Lot.id.asc())
        elif sort == LotSortOrder.HOT_BIDS:
            stmt = stmt.order_by(Lot.bid_count.desc(), Lot.ends_at.asc(), Lot.id.asc())
        elif sort == LotSortOrder.NEWEST:
            stmt = stmt.order_by(Lot.created_at.desc(), Lot.id.asc())
        elif sort == LotSortOrder.PRICE_ASC:
            stmt = stmt.order_by(effective_price.asc(), Lot.id.asc())
        elif sort == LotSortOrder.PRICE_DESC:
            stmt = stmt.order_by(effective_price.desc(), Lot.id.asc())
        else:
            stmt = stmt.order_by(Lot.ends_at.asc(), Lot.id.asc())

        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        lots = list(result.scalars().all())
        return lots, total
