import json
import uuid
from decimal import Decimal
from typing import Any

from core.exceptions import DomainError, NotFoundError
from ports.payment_port import CheckoutSessionResult, PaymentGatewayPort


class InMemoryPaymentGatewayAdapter(PaymentGatewayPort):
    def __init__(self, webhook_secret: str | None = None) -> None:
        self.webhook_secret = webhook_secret or "whsec_test_mock_secret"
        self.sessions: dict[str, dict[str, Any]] = {}

    async def create_checkout_session(
        self,
        user_id: uuid.UUID,
        amount_usd: Decimal,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult:
        if amount_usd <= Decimal("0.00"):
            raise DomainError(
                message="Checkout amount must be greater than zero",
                error_code="INVALID_PAYMENT_AMOUNT",
                status_code=400,
            )
        session_id = f"cs_test_{uuid.uuid4().hex[:20]}"
        separator = "&" if "?" in success_url else "?"
        checkout_url = f"{success_url}{separator}session_id={session_id}"

        session_record = {
            "session_id": session_id,
            "user_id": str(user_id),
            "amount_usd": str(amount_usd),
            "status": "open",
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        self.sessions[session_id] = session_record

        return CheckoutSessionResult(
            session_id=session_id,
            checkout_url=checkout_url,
        )

    def verify_webhook_event(
        self,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        is_valid_direct = signature == self.webhook_secret
        is_valid_header = signature.startswith("t=") and (
            f"v1={self.webhook_secret}" in signature or self.webhook_secret in signature
        )
        if not signature or not (is_valid_direct or is_valid_header):
            raise DomainError(
                message="Invalid Stripe webhook signature",
                error_code="INVALID_WEBHOOK_SIGNATURE",
                status_code=400,
            )
        try:
            event_data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DomainError(
                message="Malformed JSON webhook payload",
                error_code="MALFORMED_WEBHOOK_PAYLOAD",
                status_code=400,
            ) from exc

        if not isinstance(event_data, dict) or "id" not in event_data or "type" not in event_data:
            raise DomainError(
                message="Missing required event fields (id, type) in webhook",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                status_code=400,
            )
        return event_data

    def get_session(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            raise NotFoundError(
                message=f"Checkout session '{session_id}' not found",
                error_code="SESSION_NOT_FOUND",
            )
        return self.sessions[session_id]

    def simulate_checkout_completed(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        session["status"] = "complete"
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "client_reference_id": session["user_id"],
                    "amount_total": int(Decimal(session["amount_usd"]) * 100),
                    "currency": "usd",
                    "payment_status": "paid",
                }
            },
        }
