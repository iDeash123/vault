from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="MEMBER", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("bio", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "refresh_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_refresh_sessions_user_id",
        "refresh_sessions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "wallets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column(
            "available_balance",
            sa.Numeric(precision=14, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "held_balance",
            sa.Numeric(precision=14, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "claimable_balance",
            sa.Numeric(precision=14, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "available_balance >= 0.00",
            name="ck_wallets_available_non_negative",
        ),
        sa.CheckConstraint("held_balance >= 0.00", name="ck_wallets_held_non_negative"),
        sa.CheckConstraint(
            "claimable_balance >= 0.00",
            name="ck_wallets_claimable_non_negative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "lots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leader_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("specs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("start_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reserve_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("buy_now_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("min_bid_increment", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "current_price",
            sa.Numeric(precision=14, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("bid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "anti_snipe_extensions_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || "
                "coalesce(subtitle, '') || ' ' || coalesce(description, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("start_price > 0.00", name="ck_lots_start_price_positive"),
        sa.CheckConstraint(
            "min_bid_increment >= 1.00",
            name="ck_lots_increment_positive",
        ),
        sa.CheckConstraint(
            "reserve_price IS NULL OR reserve_price >= start_price",
            name="ck_lots_reserve_gte_start",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_lots_ends_after_starts"),
        sa.ForeignKeyConstraint(["leader_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lots_category_status",
        "lots",
        ["category", "status"],
        unique=False,
    )
    op.create_index(
        "ix_lots_status_ends_at",
        "lots",
        ["status", "ends_at"],
        unique=False,
    )
    op.create_index(
        "ix_lots_search_vector",
        "lots",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_lots_title_trgm",
        "lots",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "lot_media",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("public_url", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name="ck_lot_media_size_limit",
        ),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_lot_media_lot_sort",
        "lot_media",
        ["lot_id", "sort_order"],
        unique=False,
    )

    op.create_table(
        "wallet_holds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("outbid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0.00", name="ck_wallet_holds_amount_positive"),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wallet_holds_lot_id",
        "wallet_holds",
        ["lot_id"],
        unique=False,
    )
    op.create_index(
        "ix_wallet_holds_user_status",
        "wallet_holds",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_active_hold_per_lot",
        "wallet_holds",
        ["lot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE_HOLD'"),
    )

    op.create_table(
        "bids",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bidder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wallet_hold_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("is_buy_now", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "triggered_anti_snipe",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bidder_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_hold_id"], ["wallet_holds.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("wallet_hold_id"),
    )
    op.create_index("ix_bids_bidder_id", "bids", ["bidder_id"], unique=False)
    op.create_index(
        "ix_bids_lot_created_desc",
        "bids",
        ["lot_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "wallet_ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=48), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("available_delta", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("held_delta", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("claimable_delta", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "balance_available_after",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "balance_held_after",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "balance_claimable_after",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column("reference_lot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reference_hold_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reference_hold_id"],
            ["wallet_holds.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["reference_lot_id"], ["lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_ledger_wallet_created",
        "wallet_ledger_entries",
        ["wallet_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "stripe_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("stripe_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id"),
    )

    op.create_table(
        "escrow_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wallet_hold_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("final_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "platform_fee_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "seller_payout_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="FUNDS_HELD",
            nullable=False,
        ),
        sa.Column("tracking_number", sa.String(length=128), nullable=True),
        sa.Column("shipping_carrier", sa.String(length=64), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "final_amount = platform_fee_amount + seller_payout_amount",
            name="ck_escrow_fee_math",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_hold_id"], ["wallet_holds.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_id"),
        sa.UniqueConstraint("wallet_hold_id"),
    )

    op.create_table(
        "watchlist_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "lot_id", name="uq_watchlist_user_lot"),
    )

    op.create_table(
        "moderation_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("curator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["curator_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("moderation_logs")
    op.drop_table("watchlist_items")
    op.drop_table("escrow_orders")
    op.drop_table("stripe_webhook_events")
    op.drop_table("wallet_ledger_entries")
    op.drop_table("bids")
    op.drop_table("wallet_holds")
    op.drop_table("lot_media")
    op.drop_table("lots")
    op.drop_table("wallets")
    op.drop_table("refresh_sessions")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
