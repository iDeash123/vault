import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.config import Settings, get_settings
from core.exceptions import ConflictError, DomainError, ForbiddenError, NotFoundError
from domains.escrow.repository import EscrowRepository
from domains.escrow.schemas import (
    DisputeOrderRequest,
    EscrowOrderListResponse,
    EscrowOrderResponse,
    ShipOrderRequest,
)
from ports.realtime_port import RealtimeBrokerPort
from shared.db.models.enums import (
    EscrowOrderStatus,
    LedgerEntryType,
    LotStatus,
    WalletHoldStatus,
)
from shared.db.models.escrow import EscrowOrder
from shared.db.models.wallet import WalletLedgerEntry

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


def calculate_platform_fee_and_payout(
    final_amount: Decimal,
    fee_percent: Decimal,
) -> tuple[Decimal, Decimal]:
    quantized_final = quantize_usd(final_amount)
    fee_rate = fee_percent / Decimal("100.00")
    platform_fee = quantize_usd(quantized_final * fee_rate)
    seller_payout = quantize_usd(quantized_final - platform_fee)
    return platform_fee, seller_payout


class EscrowService:
    def __init__(
        self,
        session: AsyncSession,
        clock: ClockPort,
        realtime_broker: RealtimeBrokerPort,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.realtime_broker = realtime_broker
        self.settings = settings or get_settings()
        self.repo = EscrowRepository(session)

    def _to_response(
        self,
        order: EscrowOrder,
        lot_title: str,
        server_time: datetime,
    ) -> EscrowOrderResponse:
        return EscrowOrderResponse(
            id=order.id,
            lot_id=order.lot_id,
            lot_title=lot_title,
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            wallet_hold_id=order.wallet_hold_id,
            final_amount=quantize_usd(order.final_amount),
            platform_fee_amount=quantize_usd(order.platform_fee_amount),
            seller_payout_amount=quantize_usd(order.seller_payout_amount),
            status=order.status,
            tracking_number=order.tracking_number,
            shipping_carrier=order.shipping_carrier,
            shipped_at=order.shipped_at,
            completed_at=order.completed_at,
            dispute_reason=order.dispute_reason,
            created_at=order.created_at,
            updated_at=order.updated_at,
            server_time=server_time,
        )

    async def list_orders(
        self,
        user_id: uuid.UUID,
        role: str | None = None,
        status: EscrowOrderStatus | None = None,
    ) -> EscrowOrderListResponse:
        now = self.clock.now()
        pairs = await self.repo.list_orders_for_user(
            user_id=user_id,
            role=role,
            status=status,
        )
        items = [self._to_response(order, title, now) for order, title in pairs]
        return EscrowOrderListResponse(
            items=items,
            total=len(items),
            server_time=now,
        )

    async def get_order(
        self,
        order_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EscrowOrderResponse:
        now = self.clock.now()
        pair = await self.repo.get_order_with_lot_title(order_id)
        if pair is None:
            raise NotFoundError(
                message="Order not found",
                error_code="ORDER_NOT_FOUND",
            )
        order, title = pair
        if order.buyer_id != current_user_id and order.seller_id != current_user_id:
            raise ForbiddenError(
                message="Access to this order is restricted to the buyer or seller",
                error_code="ORDER_ACCESS_DENIED",
            )
        return self._to_response(order, title, now)

    async def ship_order(
        self,
        order_id: uuid.UUID,
        current_user_id: uuid.UUID,
        payload: ShipOrderRequest,
    ) -> EscrowOrderResponse:
        now = self.clock.now()
        pair = await self.repo.get_order_with_lot_title(order_id, for_update=True)
        if pair is None:
            raise NotFoundError(
                message="Order not found",
                error_code="ORDER_NOT_FOUND",
            )
        order, title = pair
        if order.seller_id != current_user_id:
            raise ForbiddenError(
                message="Only the seller can mark the order as shipped",
                error_code="ORDER_SELLER_PERMISSION_DENIED",
            )
        if order.status != EscrowOrderStatus.FUNDS_HELD:
            raise ConflictError(
                message="Order cannot be marked as shipped from current status",
                error_code="INVALID_ORDER_STATUS",
            )

        order.status = EscrowOrderStatus.SHIPPED
        order.shipping_carrier = payload.shipping_carrier.strip()
        order.tracking_number = payload.tracking_number.strip()
        order.shipped_at = now
        order.updated_at = now

        order_id_val = order.id
        buyer_id_val = order.buyer_id
        seller_id_val = order.seller_id
        response = self._to_response(order, title, now)

        await self.session.commit()

        event = {
            "event_type": "ORDER_STATUS_CHANGED",
            "order_id": str(order_id_val),
            "status": EscrowOrderStatus.SHIPPED.value,
            "server_time": now.isoformat(),
        }
        await self.realtime_broker.send_user_notification(buyer_id_val, event)
        await self.realtime_broker.send_user_notification(seller_id_val, event)

        return response

    async def confirm_receipt(
        self,
        order_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EscrowOrderResponse:
        now = self.clock.now()
        pair = await self.repo.get_order_with_lot_title(order_id, for_update=True)
        if pair is None:
            raise NotFoundError(
                message="Order not found",
                error_code="ORDER_NOT_FOUND",
            )
        order, title = pair
        if order.buyer_id != current_user_id:
            raise ForbiddenError(
                message="Only the buyer can confirm receipt",
                error_code="ORDER_BUYER_PERMISSION_DENIED",
            )
        if order.status != EscrowOrderStatus.SHIPPED:
            raise ConflictError(
                message="Order must be in SHIPPED status to confirm receipt",
                error_code="INVALID_ORDER_STATUS",
            )

        lot = await self.repo.get_lot_for_update(order.lot_id)
        if lot is None:
            raise NotFoundError(
                message="Associated lot not found",
                error_code="LOT_NOT_FOUND",
            )

        hold = await self.repo.get_hold_for_update(order.wallet_hold_id)
        if hold is None or hold.status != WalletHoldStatus.CAPTURED_TO_ESCROW:
            raise ConflictError(
                message="Wallet hold is missing or not captured to escrow",
                error_code="INVALID_HOLD_STATUS",
            )

        wallets = await self.repo.get_wallets_for_update([order.buyer_id, order.seller_id])
        buyer_wallet = wallets.get(order.buyer_id)
        seller_wallet = wallets.get(order.seller_id)
        if buyer_wallet is None or seller_wallet is None:
            raise NotFoundError(
                message="Wallet not found for buyer or seller",
                error_code="WALLET_NOT_FOUND",
            )

        buyer_held = quantize_usd(buyer_wallet.held_balance)
        if buyer_held < quantize_usd(order.final_amount):
            raise ConflictError(
                message="Insufficient held balance in buyer wallet to release escrow",
                error_code="INSUFFICIENT_HELD_BALANCE",
            )

        final_amt = quantize_usd(order.final_amount)
        seller_payout = quantize_usd(order.seller_payout_amount)

        buyer_wallet.held_balance = quantize_usd(Decimal(buyer_wallet.held_balance) - final_amt)
        buyer_wallet.updated_at = now
        await self.repo.create_ledger_entry(
            WalletLedgerEntry(
                wallet_id=buyer_wallet.id,
                user_id=order.buyer_id,
                entry_type=LedgerEntryType.ESCROW_BUYER_RELEASE,
                amount=final_amt,
                available_delta=Decimal("0.00"),
                held_delta=-final_amt,
                claimable_delta=Decimal("0.00"),
                balance_available_after=quantize_usd(buyer_wallet.available_balance),
                balance_held_after=quantize_usd(buyer_wallet.held_balance),
                balance_claimable_after=quantize_usd(buyer_wallet.claimable_balance),
                reference_lot_id=order.lot_id,
                reference_hold_id=order.wallet_hold_id,
                idempotency_key=f"escrow_release:{order.id}",
                created_at=now,
            )
        )

        seller_wallet.available_balance = quantize_usd(
            Decimal(seller_wallet.available_balance) + seller_payout
        )
        seller_wallet.updated_at = now
        await self.repo.create_ledger_entry(
            WalletLedgerEntry(
                wallet_id=seller_wallet.id,
                user_id=order.seller_id,
                entry_type=LedgerEntryType.ESCROW_SELLER_PAYOUT,
                amount=seller_payout,
                available_delta=seller_payout,
                held_delta=Decimal("0.00"),
                claimable_delta=Decimal("0.00"),
                balance_available_after=quantize_usd(seller_wallet.available_balance),
                balance_held_after=quantize_usd(seller_wallet.held_balance),
                balance_claimable_after=quantize_usd(seller_wallet.claimable_balance),
                reference_lot_id=order.lot_id,
                reference_hold_id=order.wallet_hold_id,
                idempotency_key=f"escrow_payout:{order.id}",
                created_at=now,
            )
        )

        lot.status = LotStatus.SETTLED
        lot.updated_at = now
        lot.version += 1

        order.status = EscrowOrderStatus.COMPLETED
        order.completed_at = now
        order.updated_at = now

        order_id_val = order.id
        buyer_id_val = order.buyer_id
        seller_id_val = order.seller_id
        response = self._to_response(order, title, now)

        await self.session.commit()

        event = {
            "event_type": "ORDER_STATUS_CHANGED",
            "order_id": str(order_id_val),
            "status": EscrowOrderStatus.COMPLETED.value,
            "server_time": now.isoformat(),
        }
        await self.realtime_broker.send_user_notification(buyer_id_val, event)
        await self.realtime_broker.send_user_notification(seller_id_val, event)

        return response

    async def dispute_order(
        self,
        order_id: uuid.UUID,
        current_user_id: uuid.UUID,
        payload: DisputeOrderRequest,
    ) -> EscrowOrderResponse:
        now = self.clock.now()
        pair = await self.repo.get_order_with_lot_title(order_id, for_update=True)
        if pair is None:
            raise NotFoundError(
                message="Order not found",
                error_code="ORDER_NOT_FOUND",
            )
        order, title = pair
        if order.buyer_id != current_user_id:
            raise ForbiddenError(
                message="Only the buyer can open a dispute",
                error_code="ORDER_BUYER_PERMISSION_DENIED",
            )
        if order.status not in (EscrowOrderStatus.FUNDS_HELD, EscrowOrderStatus.SHIPPED):
            raise ConflictError(
                message="Order cannot be disputed in current status",
                error_code="INVALID_ORDER_STATUS",
            )

        order.status = EscrowOrderStatus.DISPUTED
        order.dispute_reason = payload.dispute_reason.strip()
        order.updated_at = now

        order_id_val = order.id
        buyer_id_val = order.buyer_id
        seller_id_val = order.seller_id
        response = self._to_response(order, title, now)

        await self.session.commit()

        event = {
            "event_type": "ORDER_STATUS_CHANGED",
            "order_id": str(order_id_val),
            "status": EscrowOrderStatus.DISPUTED.value,
            "server_time": now.isoformat(),
        }
        await self.realtime_broker.send_user_notification(buyer_id_val, event)
        await self.realtime_broker.send_user_notification(seller_id_val, event)

        return response
