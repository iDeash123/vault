import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, CreatedAtMixin, UUIDpk
from shared.db.models.enums import LedgerEntryType, WalletHoldStatus


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("available_balance >= 0.00", name="ck_wallets_available_non_negative"),
        CheckConstraint("held_balance >= 0.00", name="ck_wallets_held_non_negative"),
        CheckConstraint("claimable_balance >= 0.00", name="ck_wallets_claimable_non_negative"),
    )

    id: Mapped[UUIDpk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        server_default="USD",
    )
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    held_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    claimable_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WalletHold(Base, CreatedAtMixin):
    __tablename__ = "wallet_holds"
    __table_args__ = (
        CheckConstraint("amount > 0.00", name="ck_wallet_holds_amount_positive"),
        Index(
            "uq_active_hold_per_lot",
            "lot_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE_HOLD'"),
        ),
        Index("ix_wallet_holds_user_status", "user_id", "status"),
        Index("ix_wallet_holds_lot_id", "lot_id"),
    )

    id: Mapped[UUIDpk]
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[WalletHoldStatus] = mapped_column(
        Enum(WalletHoldStatus, native_enum=False, length=32),
        nullable=False,
    )
    outbid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WalletLedgerEntry(Base, CreatedAtMixin):
    __tablename__ = "wallet_ledger_entries"
    __table_args__ = (Index("ix_ledger_wallet_created", "wallet_id", desc("created_at")),)

    id: Mapped[UUIDpk]
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(LedgerEntryType, native_enum=False, length=48),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    available_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    held_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    claimable_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_available_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_held_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_claimable_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_lot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_hold_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallet_holds.id", ondelete="RESTRICT"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    id: Mapped[UUIDpk]
    stripe_event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
