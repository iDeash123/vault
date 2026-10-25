import asyncio
import uuid
from decimal import Decimal

import httpx
import pytest
from taskiq import AsyncBroker

from adapters import (
    InMemoryPaymentGatewayAdapter,
    InMemoryRealtimeBrokerAdapter,
    InMemoryStorageAdapter,
    RedisRealtimeBrokerAdapter,
    S3StorageAdapter,
)
from core.exceptions import DomainError, NotFoundError
from main import app
from ports import (
    JPEG_SIGNATURE,
    PNG_SIGNATURE,
    WEBP_HEADER,
    WEBP_SIGNATURE,
    PaymentGatewayPort,
    RealtimeBrokerPort,
    StoragePort,
    validate_image_bytes,
)
from worker import broker, create_broker

VALID_JPEG_BYTES = (
    JPEG_SIGNATURE + b"\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32
)
VALID_PNG_BYTES = (
    PNG_SIGNATURE + b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
)
VALID_WEBP_BYTES = (
    WEBP_HEADER + b"\x1c\x00\x00\x00" + WEBP_SIGNATURE + b"VP8 \x10\x00\x00\x00" + b"\x00" * 16
)

INVALID_EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 32
INVALID_SVG_BYTES = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
TRUNCATED_BYTES = b"\xff\xd8"
OVERSIZED_BYTES = JPEG_SIGNATURE + b"\x00" * 10_485_760


def test_magic_bytes_detection_valid_formats() -> None:
    assert validate_image_bytes(VALID_JPEG_BYTES) == "image/jpeg"
    assert validate_image_bytes(VALID_PNG_BYTES) == "image/png"
    assert validate_image_bytes(VALID_WEBP_BYTES) == "image/webp"


def test_magic_bytes_rejects_renamed_exe_and_svg() -> None:
    with pytest.raises(DomainError) as exc_exe:
        validate_image_bytes(INVALID_EXE_BYTES)
    assert exc_exe.value.error_code == "INVALID_MEDIA_MAGIC_BYTES"

    with pytest.raises(DomainError) as exc_svg:
        validate_image_bytes(INVALID_SVG_BYTES)
    assert exc_svg.value.error_code == "INVALID_MEDIA_MAGIC_BYTES"


def test_magic_bytes_rejects_truncated_and_oversized() -> None:
    with pytest.raises(DomainError) as exc_small:
        validate_image_bytes(TRUNCATED_BYTES)
    assert exc_small.value.error_code == "INVALID_MEDIA_BYTES"

    with pytest.raises(DomainError) as exc_empty:
        validate_image_bytes(b"")
    assert exc_empty.value.error_code == "INVALID_MEDIA_BYTES"

    with pytest.raises(DomainError) as exc_large:
        validate_image_bytes(OVERSIZED_BYTES)
    assert exc_large.value.error_code == "MEDIA_SIZE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_in_memory_storage_adapter_lifecycle() -> None:
    storage: StoragePort = InMemoryStorageAdapter(base_url="http://localhost:9000/obsolete-media")
    key = "lots/test-1/primary.jpg"

    with pytest.raises(DomainError):
        await storage.upload(key, INVALID_EXE_BYTES)

    url = await storage.upload(key, VALID_JPEG_BYTES)
    assert url == f"http://localhost:9000/obsolete-media/{key}"

    assert await storage.exists(key) is True
    data = await storage.download(key)
    assert data == VALID_JPEG_BYTES

    await storage.delete(key)
    assert await storage.exists(key) is False

    with pytest.raises(NotFoundError):
        await storage.download(key)


@pytest.mark.asyncio
async def test_s3_storage_adapter_protocol_and_guards() -> None:
    adapter = S3StorageAdapter()
    assert isinstance(adapter, StoragePort)

    with pytest.raises(DomainError):
        await adapter.upload("lots/invalid.exe", INVALID_EXE_BYTES)

    with pytest.raises(DomainError):
        await adapter.upload("lots/oversized.jpg", OVERSIZED_BYTES)


@pytest.mark.asyncio
async def test_in_memory_payment_gateway_adapter() -> None:
    gateway = InMemoryPaymentGatewayAdapter(webhook_secret="whsec_contract_test")
    assert isinstance(gateway, PaymentGatewayPort)
    user_id = uuid.uuid4()

    with pytest.raises(DomainError):
        await gateway.create_checkout_session(
            user_id=user_id,
            amount_usd=Decimal("0.00"),
            success_url="http://localhost:5173/wallet?topup=success",
            cancel_url="http://localhost:5173/wallet?topup=cancel",
        )

    session = await gateway.create_checkout_session(
        user_id=user_id,
        amount_usd=Decimal("250.00"),
        success_url="http://localhost:5173/wallet?topup=success",
        cancel_url="http://localhost:5173/wallet?topup=cancel",
    )
    assert session.session_id.startswith("cs_test_")
    assert "session_id=" in session.checkout_url

    with pytest.raises(DomainError) as exc_bad_sig:
        gateway.verify_webhook_event(payload=b'{"id":"evt_1","type":"test"}', signature="bad_sig")
    assert exc_bad_sig.value.error_code == "INVALID_WEBHOOK_SIGNATURE"

    with pytest.raises(DomainError) as exc_fake_t:
        gateway.verify_webhook_event(payload=b'{"id":"evt_1","type":"test"}', signature="t=fake")
    assert exc_fake_t.value.error_code == "INVALID_WEBHOOK_SIGNATURE"

    with pytest.raises(DomainError) as exc_wrong_v1:
        gateway.verify_webhook_event(
            payload=b'{"id":"evt_1","type":"test"}',
            signature="t=123,v1=wrong_signature",
        )
    assert exc_wrong_v1.value.error_code == "INVALID_WEBHOOK_SIGNATURE"

    valid_payload = b'{"id":"evt_1","type":"checkout.session.completed"}'
    verified = gateway.verify_webhook_event(payload=valid_payload, signature="whsec_contract_test")
    assert verified["id"] == "evt_1"
    assert verified["type"] == "checkout.session.completed"

    verified_header = gateway.verify_webhook_event(
        payload=valid_payload,
        signature="t=123456,v1=whsec_contract_test",
    )
    assert verified_header["id"] == "evt_1"

    completed_event = gateway.simulate_checkout_completed(session.session_id)
    assert completed_event["type"] == "checkout.session.completed"
    assert completed_event["data"]["object"]["client_reference_id"] == str(user_id)
    assert gateway.get_session(session.session_id)["status"] == "complete"


@pytest.mark.asyncio
async def test_in_memory_realtime_broker_pub_sub() -> None:
    broker_adapter: RealtimeBrokerPort = InMemoryRealtimeBrokerAdapter()
    channel = "lot:test-room"
    test_event = {"event_type": "BID_PLACED", "amount": "500.00"}

    subscriber = broker_adapter.subscribe(channel)
    received: list[dict[str, object]] = []

    async def consume() -> None:
        async for msg in subscriber:
            received.append(msg)
            break

    consume_task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await broker_adapter.publish(channel, test_event)
    await asyncio.wait_for(consume_task, timeout=1.0)

    assert len(received) == 1
    assert received[0] == test_event


@pytest.mark.asyncio
async def test_realtime_redis_adapter_conformance() -> None:
    redis_adapter = RedisRealtimeBrokerAdapter()
    assert isinstance(redis_adapter, RealtimeBrokerPort)
    await redis_adapter.close()


def test_taskiq_broker_conformance() -> None:
    assert isinstance(broker, AsyncBroker)
    custom_broker = create_broker()
    assert isinstance(custom_broker, AsyncBroker)
    in_memory = create_broker(in_memory=True)
    assert isinstance(in_memory, AsyncBroker)


@pytest.mark.asyncio
async def test_healthcheck_endpoint() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert "server_time" in data
        assert data["version"] == "1.0.0"
