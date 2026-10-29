import hashlib
import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.config import Settings, get_settings
from core.exceptions import ConflictError, DomainError, ForbiddenError, NotFoundError
from domains.bidding.repository import BiddingRepository
from domains.bidding.schemas import BidResponse, PlaceBidRequest
from ports.realtime_port import RealtimeBrokerPort
from shared.db.models.bid import Bid
from shared.db.models.enums import LedgerEntryType, LotStatus, WalletHoldStatus
from shared.db.models.wallet import WalletHold, WalletLedgerEntry

TWO_PLACES = Decimal("0.01")


def quantize_usd(value: Decimal) -> Decimal:
    dec = Decimal(value)
    if not dec.is_finite():
        raise DomainError(
            message="Monetary amount must be a finite number",
            error_code="INVALID_MONETARY_AMOUNT",
            status_code=400,
        )
    return dec.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


def validate_idempotency_key(raw_key: str) -> str:
    cleaned = raw_key.strip()
    if not cleaned or len(cleaned) > 128:
        raise DomainError(
            message="Idempotency key must be between 1 and 128 characters",
            error_code="INVALID_IDEMPOTENCY_KEY",
            status_code=400,
        )
    return cleaned


def make_ledger_idempotency_key(prefix: str, identifier: str) -> str:
    candidate = f"{prefix}:{identifier}"
    if len(candidate) <= 128:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"[:128]


def calculate_min_valid_bid(
    start_price: Decimal,
    current_price: Decimal,
    min_bid_increment: Decimal,
    bid_count: int,
) -> Decimal:
    if bid_count == 0:
        return quantize_usd(start_price)
    return quantize_usd(current_price + min_bid_increment)


def compute_is_buy_now_available(
    status: LotStatus,
    buy_now_price: Decimal | None,
    reserve_price: Decimal | None,
    current_price: Decimal,
    min_bid_increment: Decimal,
    bid_count: int,
) -> bool:
    if status != LotStatus.LIVE or buy_now_price is None:
        return False
    below_reserve = reserve_price is not None and current_price < reserve_price
    initial_window = bid_count == 0 or below_reserve
    if not initial_window:
        return False
    return (current_price + min_bid_increment) < buy_now_price


def compute_is_reserve_met(
    reserve_price: Decimal | None,
    current_price: Decimal,
    bid_count: int,
) -> bool:
    if reserve_price is None:
        return True
    if bid_count == 0:
        return False
    return current_price >= reserve_price


def evaluate_anti_snipe(
    ends_at: datetime,
    now: datetime,
    extensions_count: int,
    window_seconds: int = 120,
    extension_seconds: int = 120,
) -> tuple[datetime, int, bool]:
    remaining_seconds = (ends_at - now).total_seconds()
    if 0 < remaining_seconds < window_seconds:
        return now + timedelta(seconds=extension_seconds), extensions_count + 1, True
    return ends_at, extensions_count, False


def mask_username(username: str) -> str:
    cleaned = username.strip()
    if len(cleaned) <= 2:
        return f"{cleaned[:1]}***"
    return f"{cleaned[0]}***{cleaned[-1]}"


class BiddingService:
    def __init__(
        self,
        session: AsyncSession,
        clock: ClockPort,
        realtime_broker: RealtimeBrokerPort,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.repo = BiddingRepository(session)
        self.clock = clock
        self.realtime_broker = realtime_broker
        self.settings = settings or get_settings()

    async def place_bid(
        self,
        lot_id: uuid.UUID,
        bidder_id: uuid.UUID,
        payload: PlaceBidRequest,
        idempotency_key: str,
    ) -> BidResponse:
        cleaned_key = validate_idempotency_key(idempotency_key)
        quantized_amount = quantize_usd(payload.amount)
        if quantized_amount <= Decimal("0.00"):
            raise DomainError(
                message="Bid amount must be greater than zero",
                error_code="INVALID_BID_AMOUNT",
                status_code=400,
            )

        lot = await self.repo.get_lot_for_update(lot_id)
        if lot is None:
            raise NotFoundError(message="Lot not found", error_code="LOT_NOT_FOUND")

        existing_bid = await self.repo.get_bid_by_idempotency_key(cleaned_key)
        if existing_bid is not None:
            if (
                existing_bid.lot_id != lot_id
                or existing_bid.bidder_id != bidder_id
                or quantize_usd(existing_bid.amount) != quantized_amount
                or existing_bid.is_buy_now
            ):
                raise ConflictError(
                    message="Idempotency key already used with different parameters",
                    error_code="IDEMPOTENCY_KEY_CONFLICT",
                )
            now = self.clock.now()
            next_min_bid = calculate_min_valid_bid(
                lot.start_price,
                lot.current_price,
                lot.min_bid_increment,
                lot.bid_count,
            )
            is_buy_now = compute_is_buy_now_available(
                lot.status,
                lot.buy_now_price,
                lot.reserve_price,
                lot.current_price,
                lot.min_bid_increment,
                lot.bid_count,
            )
            is_res_met = compute_is_reserve_met(
                lot.reserve_price,
                lot.current_price,
                lot.bid_count,
            )
            return BidResponse(
                id=existing_bid.id,
                lot_id=lot.id,
                bidder_id=existing_bid.bidder_id,
                wallet_hold_id=existing_bid.wallet_hold_id,
                amount=quantize_usd(existing_bid.amount),
                is_buy_now=existing_bid.is_buy_now,
                triggered_anti_snipe=existing_bid.triggered_anti_snipe,
                idempotency_key=existing_bid.idempotency_key,
                created_at=existing_bid.created_at,
                lot_status=lot.status,
                current_price=quantize_usd(lot.current_price),
                min_valid_bid=next_min_bid,
                bid_count=lot.bid_count,
                ends_at=lot.ends_at,
                anti_snipe_extensions_count=lot.anti_snipe_extensions_count,
                is_buy_now_available=is_buy_now,
                is_reserve_met=is_res_met,
                server_time=now,
            )

        if lot.seller_id == bidder_id:
            raise ForbiddenError(
                message="Sellers cannot bid on their own lot",
                error_code="SELF_BIDDING_FORBIDDEN",
            )

        if lot.status != LotStatus.LIVE:
            raise ConflictError(
                message=f"Lot is not live (current status: {lot.status})",
                error_code="LOT_NOT_LIVE",
            )

        now = self.clock.now()
        if now < lot.starts_at:
            raise ConflictError(
                message="Auction has not started yet",
                error_code="LOT_NOT_STARTED",
            )
        if now >= lot.ends_at:
            raise ConflictError(
                message="Auction has already ended",
                error_code="LOT_ALREADY_ENDED",
            )

        min_valid_bid = calculate_min_valid_bid(
            lot.start_price,
            lot.current_price,
            lot.min_bid_increment,
            lot.bid_count,
        )
        if quantized_amount < min_valid_bid:
            raise DomainError(
                message=f"Bid amount {quantized_amount} USD must be at least {min_valid_bid} USD",
                error_code="BID_AMOUNT_TOO_LOW",
                status_code=400,
            )

        active_hold = await self.repo.get_active_hold_for_lot_for_update(lot_id)

        user_ids_to_lock = [bidder_id]
        if active_hold is not None:
            user_ids_to_lock.append(active_hold.user_id)
        wallets = await self.repo.get_wallets_for_update(user_ids_to_lock)
        bidder_wallet = wallets[bidder_id]

        avail = quantize_usd(bidder_wallet.available_balance)
        claimable = quantize_usd(bidder_wallet.claimable_balance)
        if avail < quantized_amount:
            msg = f"Available balance {avail} USD is less than required bid {quantized_amount} USD."
            if claimable > Decimal("0.00"):
                msg = (
                    f"{msg} Note: you have {claimable} USD in claimable outbid holds "
                    "that can be manually claimed."
                )
            raise DomainError(
                message=msg,
                error_code="INSUFFICIENT_AVAILABLE_BALANCE",
                status_code=400,
                details={
                    "available_balance": str(avail),
                    "claimable_balance": str(claimable),
                    "required_amount": str(quantized_amount),
                },
            )

        previous_hold_info: tuple[uuid.UUID, uuid.UUID, Decimal, Decimal] | None = None
        try:
            if active_hold is not None:
                prev_wallet = wallets[active_hold.user_id]
                prev_amount = quantize_usd(active_hold.amount)
                active_hold.status = WalletHoldStatus.CLAIMABLE
                active_hold.outbid_at = now
                prev_wallet.held_balance = quantize_usd(
                    Decimal(prev_wallet.held_balance) - prev_amount
                )
                prev_wallet.claimable_balance = quantize_usd(
                    Decimal(prev_wallet.claimable_balance) + prev_amount
                )
                prev_wallet.updated_at = now
                await self.repo.create_ledger_entry(
                    WalletLedgerEntry(
                        wallet_id=prev_wallet.id,
                        user_id=active_hold.user_id,
                        entry_type=LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
                        amount=prev_amount,
                        available_delta=Decimal("0.00"),
                        held_delta=-prev_amount,
                        claimable_delta=prev_amount,
                        balance_available_after=quantize_usd(prev_wallet.available_balance),
                        balance_held_after=quantize_usd(prev_wallet.held_balance),
                        balance_claimable_after=quantize_usd(prev_wallet.claimable_balance),
                        reference_lot_id=lot.id,
                        reference_hold_id=active_hold.id,
                        idempotency_key=make_ledger_idempotency_key(
                            f"outbid:{active_hold.id}", cleaned_key
                        ),
                        created_at=now,
                    )
                )
                previous_hold_info = (
                    active_hold.id,
                    active_hold.user_id,
                    prev_amount,
                    quantize_usd(prev_wallet.claimable_balance),
                )

            bidder_wallet.available_balance = quantize_usd(
                Decimal(bidder_wallet.available_balance) - quantized_amount
            )
            bidder_wallet.held_balance = quantize_usd(
                Decimal(bidder_wallet.held_balance) + quantized_amount
            )
            bidder_wallet.updated_at = now

            new_hold = WalletHold(
                wallet_id=bidder_wallet.id,
                user_id=bidder_id,
                lot_id=lot.id,
                amount=quantized_amount,
                status=WalletHoldStatus.ACTIVE_HOLD,
                created_at=now,
            )
            await self.repo.create_hold(new_hold)

            await self.repo.create_ledger_entry(
                WalletLedgerEntry(
                    wallet_id=bidder_wallet.id,
                    user_id=bidder_id,
                    entry_type=LedgerEntryType.BID_LOCK,
                    amount=quantized_amount,
                    available_delta=-quantized_amount,
                    held_delta=quantized_amount,
                    claimable_delta=Decimal("0.00"),
                    balance_available_after=quantize_usd(bidder_wallet.available_balance),
                    balance_held_after=quantize_usd(bidder_wallet.held_balance),
                    balance_claimable_after=quantize_usd(bidder_wallet.claimable_balance),
                    reference_lot_id=lot.id,
                    reference_hold_id=new_hold.id,
                    idempotency_key=make_ledger_idempotency_key("bid_lock", cleaned_key),
                    created_at=now,
                )
            )

            new_ends_at, new_extensions_count, triggered_anti_snipe = evaluate_anti_snipe(
                ends_at=lot.ends_at,
                now=now,
                extensions_count=lot.anti_snipe_extensions_count,
                window_seconds=self.settings.ANTI_SNIPE_WINDOW_SECONDS,
                extension_seconds=self.settings.ANTI_SNIPE_EXTENSION_SECONDS,
            )
            lot.ends_at = new_ends_at
            lot.anti_snipe_extensions_count = new_extensions_count

            lot.current_price = quantized_amount
            lot.bid_count += 1
            lot.leader_user_id = bidder_id
            lot.version += 1
            lot.updated_at = now

            bid = Bid(
                lot_id=lot.id,
                bidder_id=bidder_id,
                wallet_hold_id=new_hold.id,
                amount=quantized_amount,
                is_buy_now=False,
                triggered_anti_snipe=triggered_anti_snipe,
                idempotency_key=cleaned_key,
                created_at=now,
            )
            await self.repo.create_bid(bid)

            bidder_user = await self.repo.get_user_by_id(bidder_id)
            masked_username = mask_username(bidder_user.username if bidder_user else "")

            next_min_valid_bid = calculate_min_valid_bid(
                lot.start_price,
                lot.current_price,
                lot.min_bid_increment,
                lot.bid_count,
            )
            is_buy_now_avail = compute_is_buy_now_available(
                lot.status,
                lot.buy_now_price,
                lot.reserve_price,
                lot.current_price,
                lot.min_bid_increment,
                lot.bid_count,
            )
            is_res_met = compute_is_reserve_met(
                lot.reserve_price,
                lot.current_price,
                lot.bid_count,
            )

            lot_id_val = lot.id
            lot_title_val = lot.title
            lot_status_val = lot.status
            ends_at_val = lot.ends_at
            bid_count_val = lot.bid_count
            extensions_count_val = lot.anti_snipe_extensions_count
            bid_id_val = bid.id
            hold_id_val = new_hold.id
            bid_created_at_val = bid.created_at

            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                message="Idempotency key already used with different parameters",
                error_code="IDEMPOTENCY_KEY_CONFLICT",
            ) from exc

        await self.realtime_broker.broadcast_lot_event(
            lot_id_val,
            {
                "event_type": "BID_PLACED",
                "lot_id": str(lot_id_val),
                "bid_id": str(bid_id_val),
                "amount": str(quantized_amount),
                "min_valid_bid": str(next_min_valid_bid),
                "bid_count": bid_count_val,
                "leader_user_id": str(bidder_id),
                "leader_username_masked": masked_username,
                "is_buy_now_available": is_buy_now_avail,
                "is_reserve_met": is_res_met,
                "ends_at": ends_at_val.isoformat(),
                "triggered_anti_snipe": triggered_anti_snipe,
                "server_time": now.isoformat(),
            },
        )

        if triggered_anti_snipe:
            await self.realtime_broker.broadcast_lot_event(
                lot_id_val,
                {
                    "event_type": "LOT_EXTENDED",
                    "lot_id": str(lot_id_val),
                    "new_ends_at": ends_at_val.isoformat(),
                    "anti_snipe_extensions_count": extensions_count_val,
                    "server_time": now.isoformat(),
                },
            )

        if previous_hold_info is not None:
            prev_hold_id, prev_user_id, prev_amt, prev_claimable = previous_hold_info
            await self.realtime_broker.send_user_notification(
                prev_user_id,
                {
                    "event_type": "HOLD_BECAME_CLAIMABLE",
                    "hold_id": str(prev_hold_id),
                    "lot_id": str(lot_id_val),
                    "lot_title": lot_title_val,
                    "amount": str(prev_amt),
                    "reason": "OUTBID",
                    "new_claimable_balance": str(prev_claimable),
                    "server_time": now.isoformat(),
                },
            )

        return BidResponse(
            id=bid_id_val,
            lot_id=lot_id_val,
            bidder_id=bidder_id,
            wallet_hold_id=hold_id_val,
            amount=quantized_amount,
            is_buy_now=False,
            triggered_anti_snipe=triggered_anti_snipe,
            idempotency_key=cleaned_key,
            created_at=bid_created_at_val,
            lot_status=lot_status_val,
            current_price=quantized_amount,
            min_valid_bid=next_min_valid_bid,
            bid_count=bid_count_val,
            ends_at=ends_at_val,
            anti_snipe_extensions_count=extensions_count_val,
            is_buy_now_available=is_buy_now_avail,
            is_reserve_met=is_res_met,
            server_time=now,
        )
