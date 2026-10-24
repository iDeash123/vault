import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, CreatedAtMixin, UUIDpk


class Bid(Base, CreatedAtMixin):
    __tablename__ = "bids"
    __table_args__ = (
        Index("ix_bids_lot_created_desc", "lot_id", desc("created_at")),
        Index("ix_bids_bidder_id", "bidder_id"),
    )

    id: Mapped[UUIDpk]
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bidder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    wallet_hold_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallet_holds.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_buy_now: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    triggered_anti_snipe: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
