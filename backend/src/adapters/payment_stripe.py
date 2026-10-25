import asyncio
import json
import uuid
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

import stripe

from core.config import Settings, get_settings
from core.exceptions import DomainError
from ports.payment_port import CheckoutSessionResult, PaymentGatewayPort


class StripePaymentGatewayAdapter(PaymentGatewayPort):
    def __init__(
        self,
        settings: Settings | None = None,
        secret_key: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._secret_key = secret_key or cfg.STRIPE_SECRET_KEY.get_secret_value()
        self._webhook_secret = webhook_secret or cfg.STRIPE_WEBHOOK_SECRET.get_secret_value()

    def _create_session_sync(
        self,
        user_id: uuid.UUID,
        unit_amount_cents: int,
        normalized_amount: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult:
        session = stripe.checkout.Session.create(
            api_key=self._secret_key,
            mode="payment",
            client_reference_id=str(user_id),
            metadata={
                "user_id": str(user_id),
                "amount_usd": normalized_amount,
            },
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "OBSOLETE Wallet Top-Up",
                        },
                        "unit_amount": unit_amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        checkout_url = session.url
        if not checkout_url:
            raise DomainError(
                message="Stripe checkout session did not return a redirect URL",
                error_code="STRIPE_CHECKOUT_ERROR",
                status_code=502,
            )
        return CheckoutSessionResult(
            session_id=str(session.id),
            checkout_url=str(checkout_url),
        )

    async def create_checkout_session(
        self,
        user_id: uuid.UUID,
        amount_usd: Decimal,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult:
        quantized = amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if quantized <= Decimal("0.00"):
            raise DomainError(
                message="Checkout amount must be greater than zero",
                error_code="INVALID_PAYMENT_AMOUNT",
                status_code=400,
            )
        unit_amount_cents = int(
            (quantized * Decimal("100")).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        try:
            return await asyncio.to_thread(
                self._create_session_sync,
                user_id,
                unit_amount_cents,
                str(quantized),
                success_url,
                cancel_url,
            )
        except DomainError:
            raise
        except stripe.StripeError as exc:
            raise DomainError(
                message="Failed to create Stripe checkout session",
                error_code="STRIPE_CHECKOUT_ERROR",
                status_code=502,
            ) from exc

    def verify_webhook_event(
        self,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        if not signature or not signature.strip():
            raise DomainError(
                message="Missing Stripe-Signature header",
                error_code="INVALID_STRIPE_SIGNATURE",
                status_code=400,
            )
        try:
            stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=self._webhook_secret,
            )
            parsed = json.loads(payload.decode("utf-8"))
        except stripe.SignatureVerificationError as exc:
            raise DomainError(
                message="Invalid Stripe webhook signature",
                error_code="INVALID_STRIPE_SIGNATURE",
                status_code=400,
            ) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise DomainError(
                message="Malformed Stripe webhook payload",
                error_code="INVALID_STRIPE_SIGNATURE",
                status_code=400,
            ) from exc

        if not isinstance(parsed, dict) or "id" not in parsed or "type" not in parsed:
            raise DomainError(
                message="Invalid Stripe webhook payload structure",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                status_code=400,
            )
        return parsed
