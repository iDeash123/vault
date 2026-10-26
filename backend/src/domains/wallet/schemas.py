import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.db.models.enums import LedgerEntryType, WalletHoldStatus


class TopupCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_usd: Decimal = Field(gt=Decimal("0.00"), le=Decimal("1000000.00"))

    @field_validator("amount_usd", mode="after")
    @classmethod
    def quantize_amount(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if quantized != value:
            raise ValueError("amount_usd must have at most 2 decimal places")
        return quantized


class TopupCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    server_time: datetime


class StripeWebhookResponse(BaseModel):
    status: str
    stripe_event_id: str
    idempotent_replay: bool
    server_time: datetime


class WalletHoldItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    lot_title: str
    amount: Decimal
    status: WalletHoldStatus
    created_at: datetime
    outbid_at: datetime | None
    claimed_at: datetime | None


class LedgerEntryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_type: LedgerEntryType
    amount: Decimal
    available_delta: Decimal
    held_delta: Decimal
    claimable_delta: Decimal
    balance_available_after: Decimal
    balance_held_after: Decimal
    balance_claimable_after: Decimal
    reference_lot_id: uuid.UUID | None
    reference_hold_id: uuid.UUID | None
    created_at: datetime


class WalletSummaryResponse(BaseModel):
    available_balance: Decimal
    held_balance: Decimal
    claimable_balance: Decimal
    holds: list[WalletHoldItemResponse]
    ledger_entries: list[LedgerEntryItemResponse]
    server_time: datetime


class ClaimHoldResponse(BaseModel):
    hold: WalletHoldItemResponse
    claimed_amount: Decimal
    available_balance: Decimal
    held_balance: Decimal
    claimable_balance: Decimal
    server_time: datetime


class ClaimAllHoldsResponse(BaseModel):
    claimed_count: int
    claimed_amount: Decimal
    claimed_hold_ids: list[uuid.UUID]
    available_balance: Decimal
    held_balance: Decimal
    claimable_balance: Decimal
    server_time: datetime
