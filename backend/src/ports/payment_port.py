import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class CheckoutSessionResult:
    session_id: str
    checkout_url: str


@runtime_checkable
class PaymentGatewayPort(Protocol):
    async def create_checkout_session(
        self,
        user_id: uuid.UUID,
        amount_usd: Decimal,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult: ...

    def verify_webhook_event(
        self,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]: ...
