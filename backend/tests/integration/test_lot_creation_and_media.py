import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.storage_fake import InMemoryStorageAdapter
from core.clock import FrozenClock
from domains.auth.dependencies import get_clock
from domains.lots.router import get_storage_port
from main import create_app
from shared.db.session import get_db_session

JPEG_FIXTURE = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32
)
PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP_FIXTURE = b"RIFF\x28\x00\x00\x00WEBPVP8 " + b"\x00" * 32


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_storage() -> InMemoryStorageAdapter:
    return InMemoryStorageAdapter(base_url="http://localhost:9000/obsolete-media")


@pytest.fixture
async def lots_client(
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
    fake_storage: InMemoryStorageAdapter,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    app.dependency_overrides[get_storage_port] = lambda: fake_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


async def _register_user(client: AsyncClient, prefix: str) -> tuple[str, uuid.UUID]:
    unique = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}_{unique}@obsolete.io",
            "username": f"{prefix}_{unique}",
            "password": "StrongPassword!2026",
        },
    )
    assert resp.status_code == 201
    token = str(resp.json()["access_token"])
    user_id = uuid.UUID(str(resp.json()["user"]["id"]))
    return token, user_id


def _build_apparel_payload(now: datetime) -> dict[str, object]:
    return {
        "category": "APPAREL",
        "title": "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
        "subtitle": "Archival patch bomber jacket from Autumn/Winter 2001",
        "description": "Legendary oversized MA-1 camo bomber with collaged patches.",
        "specs": {
            "category": "APPAREL",
            "brand": "Raf Simons",
            "season_era": "AW01 Riot! Riot! Riot!",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 62.0,
                "shoulders": 54.0,
                "length": 71.0,
                "sleeve": 66.0,
            },
            "materials": ["100% Cotton Canvas", "Wool Ribbing", "Riri Hardware"],
        },
        "start_price": "2500.00",
        "reserve_price": "3000.00",
        "buy_now_price": "4500.00",
        "min_bid_increment": "50.00",
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=3)).isoformat(),
    }


def _build_vinyl_payload(now: datetime) -> dict[str, object]:
    return {
        "category": "VINYL",
        "title": "Aphex Twin - Drukqs 5xLP Box Set",
        "subtitle": "Warp Records WARPLP92 First Pressing 2001",
        "description": "Complete limited edition 180g 5xLP box set with original stickers.",
        "specs": {
            "category": "VINYL",
            "artist": "Aphex Twin",
            "album_title": "Drukqs",
            "label": "Warp Records",
            "catalog_number": "WARPLP92",
            "release_year": 2001,
            "country_pressing": "UK First Press",
            "media_grade": "NM",
            "sleeve_grade": "VG_PLUS",
            "matrix_runout": "WARP LP 92 A1",
            "rpm": 33,
        },
        "start_price": "400.00",
        "reserve_price": "550.00",
        "buy_now_price": "800.00",
        "min_bid_increment": "25.00",
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=2)).isoformat(),
    }


def _build_hardware_payload(now: datetime) -> dict[str, object]:
    return {
        "category": "HARDWARE",
        "title": "Roland TR-808 Rhythm Composer",
        "subtitle": "Vintage 1981 Analog Drum Machine Serviced",
        "description": "Original Japanese analog drum machine recapped with fresh capacitors.",
        "specs": {
            "category": "HARDWARE",
            "manufacturer": "Roland",
            "model_name": "TR-808",
            "production_year": 1981,
            "serial_number": "TR808-98421",
            "voltage": "100V_JP",
            "functional_status": "FULLY_SERVICED_RECAPPED",
            "included_accessories": ["Original Dust Cover", "Step-Down Transformer 220V to 100V"],
        },
        "start_price": "3800.00",
        "reserve_price": "4200.00",
        "buy_now_price": "5500.00",
        "min_bid_increment": "100.00",
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=5)).isoformat(),
    }


def _build_artifact_payload(now: datetime) -> dict[str, object]:
    return {
        "category": "ARTIFACT",
        "title": "Dieter Rams Braun T1000 World Receiver",
        "subtitle": "Functional Minimalist Masterpiece 1963",
        "description": "Historical industrial design object engineered in Frankfurt.",
        "specs": {
            "category": "ARTIFACT",
            "creator_maker": "Dieter Rams / Braun AG",
            "origin_period": "1963 Frankfurt West Germany",
            "primary_material": "Anodized Aluminum and Phenolic Resin",
            "dimensions_mm": {
                "width": 360.0,
                "height": 220.0,
                "depth": 135.0,
                "weight_grams": 7200.0,
            },
            "provenance_summary": "Acquired from private collector in Cologne, fully tested.",
            "authentication_code": "BRAUN-T1000-AR-883",
        },
        "start_price": "1200.00",
        "reserve_price": "1500.00",
        "buy_now_price": "2200.00",
        "min_bid_increment": "50.00",
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=4)).isoformat(),
    }


async def test_create_lot_draft_for_all_four_categories(
    lots_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    token, seller_id = await _register_user(lots_client, "creator")
    headers = {"Authorization": f"Bearer {token}"}
    now = frozen_clock.now()

    apparel_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_apparel_payload(now),
        headers=headers,
    )
    assert apparel_resp.status_code == 201
    apparel_data = apparel_resp.json()
    assert apparel_data["category"] == "APPAREL"
    assert apparel_data["status"] == "DRAFT"
    assert apparel_data["seller_id"] == str(seller_id)
    assert apparel_data["specs"]["brand"] == "Raf Simons"
    assert apparel_data["media"] == []
    assert apparel_data["min_valid_bid"] == "2500.00"
    assert apparel_data["is_buy_now_available"] is False
    assert apparel_data["is_reserve_met"] is False
    assert apparel_data["server_time"] == now.isoformat().replace("+00:00", "Z")

    vinyl_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_vinyl_payload(now),
        headers=headers,
    )
    assert vinyl_resp.status_code == 201
    vinyl_data = vinyl_resp.json()
    assert vinyl_data["category"] == "VINYL"
    assert vinyl_data["specs"]["artist"] == "Aphex Twin"
    assert vinyl_data["status"] == "DRAFT"

    hardware_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_hardware_payload(now),
        headers=headers,
    )
    assert hardware_resp.status_code == 201
    hardware_data = hardware_resp.json()
    assert hardware_data["category"] == "HARDWARE"
    assert hardware_data["specs"]["manufacturer"] == "Roland"
    assert hardware_data["status"] == "DRAFT"

    artifact_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_artifact_payload(now),
        headers=headers,
    )
    assert artifact_resp.status_code == 201
    artifact_data = artifact_resp.json()
    assert artifact_data["category"] == "ARTIFACT"
    assert artifact_data["specs"]["creator_maker"] == "Dieter Rams / Braun AG"
    assert artifact_data["status"] == "DRAFT"


async def test_create_lot_validation_invariants(
    lots_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    token, _ = await _register_user(lots_client, "inv_tester")
    headers = {"Authorization": f"Bearer {token}"}
    now = frozen_clock.now()

    mismatch_payload = _build_apparel_payload(now)
    mismatch_payload["category"] = "VINYL"
    mismatch_resp = await lots_client.post(
        "/api/v1/lots",
        json=mismatch_payload,
        headers=headers,
    )
    assert mismatch_resp.status_code in {400, 422}

    low_reserve_payload = _build_apparel_payload(now)
    low_reserve_payload["start_price"] = "2000.00"
    low_reserve_payload["reserve_price"] = "1500.00"
    low_reserve_resp = await lots_client.post(
        "/api/v1/lots",
        json=low_reserve_payload,
        headers=headers,
    )
    assert low_reserve_resp.status_code == 400
    assert low_reserve_resp.json()["error_code"] == "INVALID_RESERVE_PRICE"

    invalid_buynow_payload = _build_apparel_payload(now)
    invalid_buynow_payload["start_price"] = "1000.00"
    invalid_buynow_payload["reserve_price"] = "1500.00"
    invalid_buynow_payload["min_bid_increment"] = "50.00"
    invalid_buynow_payload["buy_now_price"] = "1550.00"
    invalid_buynow_resp = await lots_client.post(
        "/api/v1/lots",
        json=invalid_buynow_payload,
        headers=headers,
    )
    assert invalid_buynow_resp.status_code == 400
    assert invalid_buynow_resp.json()["error_code"] == "INVALID_BUY_NOW_PRICE"

    bad_timing_payload = _build_apparel_payload(now)
    bad_timing_payload["starts_at"] = now.isoformat()
    bad_timing_payload["ends_at"] = (now - timedelta(hours=1)).isoformat()
    bad_timing_resp = await lots_client.post(
        "/api/v1/lots",
        json=bad_timing_payload,
        headers=headers,
    )
    assert bad_timing_resp.status_code == 400
    assert bad_timing_resp.json()["error_code"] == "INVALID_LOT_TIMING"


async def test_media_upload_magic_bytes_and_access_control(
    lots_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    seller_token, _ = await _register_user(lots_client, "seller_user")
    other_token, _ = await _register_user(lots_client, "other_user")
    seller_headers = {"Authorization": f"Bearer {seller_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    now = frozen_clock.now()

    create_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_apparel_payload(now),
        headers=seller_headers,
    )
    assert create_resp.status_code == 201
    lot_id = create_resp.json()["id"]

    forbidden_resp = await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("test.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=other_headers,
    )
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["error_code"] == "LOT_ACCESS_FORBIDDEN"

    random_lot_id = uuid.uuid4()
    not_found_resp = await lots_client.post(
        f"/api/v1/lots/{random_lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("test.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=seller_headers,
    )
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error_code"] == "LOT_NOT_FOUND"

    corrupted_resp = await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("corrupt.txt", b"plain text is not an image at all", "text/plain")},
        headers=seller_headers,
    )
    assert corrupted_resp.status_code == 400
    assert corrupted_resp.json()["error_code"] == "INVALID_MEDIA_MAGIC_BYTES"

    tiny_resp = await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("tiny.jpg", b"\xff\xd8\xff", "image/jpeg")},
        headers=seller_headers,
    )
    assert tiny_resp.status_code == 400
    assert tiny_resp.json()["error_code"] == "INVALID_MEDIA_BYTES"

    upload_primary = await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("primary.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=seller_headers,
    )
    assert upload_primary.status_code == 201
    data = upload_primary.json()
    assert data["slot_type"] == "PRIMARY"
    assert data["mime_type"] == "image/jpeg"
    assert data["sort_order"] == 0
    assert "obsolete-media" in data["public_url"]


async def test_submit_lot_mandatory_slots_and_lifecycle(
    lots_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    seller_token, _ = await _register_user(lots_client, "lifecycle_seller")
    other_token, _ = await _register_user(lots_client, "lifecycle_stranger")
    seller_headers = {"Authorization": f"Bearer {seller_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    now = frozen_clock.now()

    create_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_vinyl_payload(now),
        headers=seller_headers,
    )
    assert create_resp.status_code == 201
    lot_id = create_resp.json()["id"]

    submit_zero = await lots_client.post(
        f"/api/v1/lots/{lot_id}/submit",
        headers=seller_headers,
    )
    assert submit_zero.status_code == 400
    assert submit_zero.json()["error_code"] == "INSUFFICIENT_LOT_MEDIA"

    await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("primary.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "TAG_STAMP"},
        files={"file": ("tag.png", PNG_FIXTURE, "image/png")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "DEFECT"},
        files={"file": ("defect.webp", WEBP_FIXTURE, "image/webp")},
        headers=seller_headers,
    )

    submit_three = await lots_client.post(
        f"/api/v1/lots/{lot_id}/submit",
        headers=seller_headers,
    )
    assert submit_three.status_code == 400
    assert submit_three.json()["error_code"] == "INSUFFICIENT_LOT_MEDIA"
    assert submit_three.json()["details"]["current_count"] == 3

    create_missing_slot_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_hardware_payload(now),
        headers=seller_headers,
    )
    assert create_missing_slot_resp.status_code == 201
    missing_slot_lot_id = create_missing_slot_resp.json()["id"]

    for _ in range(2):
        await lots_client.post(
            f"/api/v1/lots/{missing_slot_lot_id}/media",
            data={"slot_type": "PRIMARY"},
            files={"file": ("primary.jpg", JPEG_FIXTURE, "image/jpeg")},
            headers=seller_headers,
        )
    await lots_client.post(
        f"/api/v1/lots/{missing_slot_lot_id}/media",
        data={"slot_type": "TAG_STAMP"},
        files={"file": ("tag.png", PNG_FIXTURE, "image/png")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{missing_slot_lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("detail.webp", WEBP_FIXTURE, "image/webp")},
        headers=seller_headers,
    )

    submit_missing_defect = await lots_client.post(
        f"/api/v1/lots/{missing_slot_lot_id}/submit",
        headers=seller_headers,
    )
    assert submit_missing_defect.status_code == 400
    assert submit_missing_defect.json()["error_code"] == "MISSING_MANDATORY_MEDIA_SLOTS"
    assert "DEFECT" in submit_missing_defect.json()["details"]["missing_slots"]

    create_missing_tag_resp = await lots_client.post(
        "/api/v1/lots",
        json=_build_artifact_payload(now),
        headers=seller_headers,
    )
    assert create_missing_tag_resp.status_code == 201
    missing_tag_lot_id = create_missing_tag_resp.json()["id"]

    await lots_client.post(
        f"/api/v1/lots/{missing_tag_lot_id}/media",
        data={"slot_type": "PRIMARY"},
        files={"file": ("primary.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{missing_tag_lot_id}/media",
        data={"slot_type": "DEFECT"},
        files={"file": ("defect.png", PNG_FIXTURE, "image/png")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{missing_tag_lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("detail1.webp", WEBP_FIXTURE, "image/webp")},
        headers=seller_headers,
    )
    await lots_client.post(
        f"/api/v1/lots/{missing_tag_lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("detail2.webp", WEBP_FIXTURE, "image/webp")},
        headers=seller_headers,
    )

    submit_missing_tag = await lots_client.post(
        f"/api/v1/lots/{missing_tag_lot_id}/submit",
        headers=seller_headers,
    )
    assert submit_missing_tag.status_code == 400
    assert submit_missing_tag.json()["error_code"] == "MISSING_MANDATORY_MEDIA_SLOTS"
    assert "TAG_STAMP" in submit_missing_tag.json()["details"]["missing_slots"]

    await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("detail.webp", WEBP_FIXTURE, "image/webp")},
        headers=seller_headers,
    )

    stranger_submit = await lots_client.post(
        f"/api/v1/lots/{lot_id}/submit",
        headers=other_headers,
    )
    assert stranger_submit.status_code == 403
    assert stranger_submit.json()["error_code"] == "LOT_ACCESS_FORBIDDEN"

    success_submit = await lots_client.post(
        f"/api/v1/lots/{lot_id}/submit",
        headers=seller_headers,
    )
    assert success_submit.status_code == 200
    lot_data = success_submit.json()
    assert lot_data["status"] == "PENDING_REVIEW"
    assert len(lot_data["media"]) == 4

    cannot_reupload = await lots_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("extra.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=seller_headers,
    )
    assert cannot_reupload.status_code == 409
    assert cannot_reupload.json()["error_code"] == "LOT_NOT_IN_DRAFT"

    cannot_resubmit = await lots_client.post(
        f"/api/v1/lots/{lot_id}/submit",
        headers=seller_headers,
    )
    assert cannot_resubmit.status_code == 409
    assert cannot_resubmit.json()["error_code"] == "LOT_NOT_IN_DRAFT"
