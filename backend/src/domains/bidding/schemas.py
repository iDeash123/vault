import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.db.models.enums import EscrowOrderStatus, LotStatus


class PlaceBidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=Decimal("0.00"))

    @field_validator("amount", mode="after")
    @classmethod
    def quantize_amount(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if quantized != value:
            raise ValueError("Amount must have at most 2 decimal places")
        return quantized


class BidResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    bidder_id: uuid.UUID
    wallet_hold_id: uuid.UUID
    amount: Decimal
    is_buy_now: bool
    triggered_anti_snipe: bool
    idempotency_key: str
    created_at: datetime
    lot_status: LotStatus
    current_price: Decimal
    min_valid_bid: Decimal
    bid_count: int
    ends_at: datetime
    anti_snipe_extensions_count: int
    is_buy_now_available: bool
    is_reserve_met: bool
    server_time: datetime


class BuyNowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: uuid.UUID
    lot_id: uuid.UUID
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    bid_id: uuid.UUID
    wallet_hold_id: uuid.UUID
    amount: Decimal
    platform_fee_amount: Decimal
    seller_payout_amount: Decimal
    lot_status: LotStatus
    order_status: EscrowOrderStatus
    server_time: datetime
