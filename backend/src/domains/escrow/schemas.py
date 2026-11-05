import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from shared.db.models.enums import EscrowOrderStatus


class ShipOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipping_carrier: str = Field(min_length=1, max_length=64)
    tracking_number: str = Field(min_length=1, max_length=128)


class DisputeOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dispute_reason: str = Field(
        min_length=5,
        max_length=2000,
        validation_alias=AliasChoices("dispute_reason", "reason"),
    )


class EscrowOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    lot_title: str
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    wallet_hold_id: uuid.UUID
    final_amount: Decimal
    platform_fee_amount: Decimal
    seller_payout_amount: Decimal
    status: EscrowOrderStatus
    tracking_number: str | None = None
    shipping_carrier: str | None = None
    shipped_at: datetime | None = None
    completed_at: datetime | None = None
    dispute_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    server_time: datetime


class EscrowOrderListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EscrowOrderResponse]
    total: int
    server_time: datetime
