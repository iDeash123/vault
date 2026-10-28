import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.db.models.enums import LotCategory, LotStatus, MediaSlotType
from shared.schemas.specs import LotSpecs


class LotSortOrder(StrEnum):
    ENDING_SOON = "ending_soon"
    HOT_BIDS = "hot_bids"
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


class CreateLotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: LotCategory
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    specs: LotSpecs
    start_price: Decimal = Field(gt=Decimal("0.00"))
    reserve_price: Decimal | None = None
    buy_now_price: Decimal | None = None
    min_bid_increment: Decimal = Field(default=Decimal("1.00"), ge=Decimal("1.00"))
    starts_at: datetime
    ends_at: datetime

    @field_validator("start_price", "min_bid_increment", mode="after")
    @classmethod
    def quantize_required_prices(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if quantized != value:
            raise ValueError("Price must have at most 2 decimal places")
        return quantized

    @field_validator("reserve_price", "buy_now_price", mode="after")
    @classmethod
    def quantize_optional_prices(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if quantized != value:
            raise ValueError("Price must have at most 2 decimal places")
        return quantized


class LotMediaItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slot_type: MediaSlotType
    public_url: str
    mime_type: str
    sort_order: int


class LotMediaUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    slot_type: MediaSlotType
    storage_key: str
    public_url: str
    mime_type: str
    size_bytes: int
    sort_order: int
    server_time: datetime


class LotBidItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bidder_id: uuid.UUID
    bidder_username_masked: str
    amount: Decimal
    is_buy_now: bool
    triggered_anti_snipe: bool
    created_at: datetime


class LotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seller_id: uuid.UUID
    leader_user_id: uuid.UUID | None
    category: LotCategory
    status: LotStatus
    title: str
    subtitle: str
    description: str
    specs: LotSpecs
    start_price: Decimal
    reserve_price: Decimal | None
    buy_now_price: Decimal | None
    min_bid_increment: Decimal
    current_price: Decimal
    min_valid_bid: Decimal
    bid_count: int
    is_buy_now_available: bool
    is_reserve_met: bool
    anti_snipe_extensions_count: int
    starts_at: datetime
    ends_at: datetime
    media: list[LotMediaItemResponse]
    server_time: datetime


class LotDetailResponse(LotResponse):
    bids: list[LotBidItemResponse] = Field(default_factory=list)


class LotCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LotResponse]
    total: int
    limit: int
    offset: int
    server_time: datetime
