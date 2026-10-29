import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from shared.db.models.enums import LotStatus


class PlaceBidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=Decimal("0.00"))


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
