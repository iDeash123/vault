import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, TimestampMixin, UUIDpk
from shared.db.models.enums import EscrowOrderStatus


class EscrowOrder(Base, TimestampMixin):
    __tablename__ = "escrow_orders"
    __table_args__ = (
        CheckConstraint(
            "final_amount = platform_fee_amount + seller_payout_amount",
            name="ck_escrow_fee_math",
        ),
    )

    id: Mapped[UUIDpk]
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
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
    final_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    platform_fee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    seller_payout_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[EscrowOrderStatus] = mapped_column(
        Enum(EscrowOrderStatus, native_enum=False, length=32),
        nullable=False,
        default=EscrowOrderStatus.FUNDS_HELD,
        server_default=EscrowOrderStatus.FUNDS_HELD.value,
    )
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipping_carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
