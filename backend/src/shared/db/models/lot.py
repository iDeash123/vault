import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDpk
from shared.db.models.enums import LotCategory, LotStatus, MediaSlotType


class Lot(Base, TimestampMixin):
    __tablename__ = "lots"
    __table_args__ = (
        CheckConstraint("start_price > 0.00", name="ck_lots_start_price_positive"),
        CheckConstraint("min_bid_increment >= 1.00", name="ck_lots_increment_positive"),
        CheckConstraint(
            "reserve_price IS NULL OR reserve_price >= start_price",
            name="ck_lots_reserve_gte_start",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_lots_ends_after_starts"),
        Index("ix_lots_status_ends_at", "status", "ends_at"),
        Index("ix_lots_category_status", "category", "status"),
        Index("ix_lots_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_lots_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUIDpk]
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    leader_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    category: Mapped[LotCategory] = mapped_column(
        Enum(LotCategory, native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[LotStatus] = mapped_column(
        Enum(LotStatus, native_enum=False, length=32),
        nullable=False,
        default=LotStatus.DRAFT,
        server_default=LotStatus.DRAFT.value,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    start_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reserve_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    buy_now_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    min_bid_increment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    bid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    anti_snipe_extensions_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || "
            "coalesce(subtitle, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
        nullable=True,
    )

    media: Mapped[list["LotMedia"]] = relationship(
        "LotMedia",
        back_populates="lot",
        cascade="all, delete-orphan",
        order_by="LotMedia.sort_order",
    )


class LotMedia(Base, CreatedAtMixin):
    __tablename__ = "lot_media"
    __table_args__ = (
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name="ck_lot_media_size_limit",
        ),
        Index("ix_lot_media_lot_sort", "lot_id", "sort_order"),
    )

    id: Mapped[UUIDpk]
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        nullable=False,
    )
    slot_type: Mapped[MediaSlotType] = mapped_column(
        Enum(MediaSlotType, native_enum=False, length=32),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    public_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    lot: Mapped["Lot"] = relationship("Lot", back_populates="media")


class WatchlistItem(Base, CreatedAtMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "lot_id", name="uq_watchlist_user_lot"),)

    id: Mapped[UUIDpk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        nullable=False,
    )
