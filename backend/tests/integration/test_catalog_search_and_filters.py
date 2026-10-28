import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.storage_fake import InMemoryStorageAdapter
from core.clock import FrozenClock
from domains.auth.dependencies import get_clock
from domains.lots.router import get_storage_port
from main import create_app
from shared.db.models.bid import Bid
from shared.db.models.enums import LotCategory, LotStatus, MediaSlotType, WalletHoldStatus
from shared.db.models.lot import Lot, LotMedia
from shared.db.models.user import User
from shared.db.models.wallet import Wallet, WalletHold
from shared.db.session import get_db_session

JPEG_FIXTURE = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32
)


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def fake_storage() -> InMemoryStorageAdapter:
    return InMemoryStorageAdapter(base_url="http://localhost:9000/obsolete-media")


@pytest.fixture
async def catalog_client(
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


async def _create_test_user(
    session: AsyncSession,
    email: str,
    username: str,
) -> tuple[User, Wallet]:
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        password_hash="argon2id$hashed",
    )
    session.add(user)
    await session.flush()
    wallet = Wallet(
        id=uuid.uuid4(),
        user_id=user.id,
        currency="USD",
        available_balance=Decimal("10000.00"),
    )
    session.add(wallet)
    await session.flush()
    return user, wallet


async def _create_seed_lots(
    session: AsyncSession,
    seller: User,
    now: datetime,
) -> dict[str, Lot]:
    lots: dict[str, Lot] = {}

    apparel = Lot(
        id=uuid.uuid4(),
        seller_id=seller.id,
        leader_user_id=None,
        category=LotCategory.APPAREL,
        status=LotStatus.LIVE,
        title="Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
        subtitle="Archival patch bomber jacket from Autumn/Winter 2001",
        description="Legendary oversized MA-1 camo bomber jacket with iconic collaged patches.",
        specs={
            "category": "APPAREL",
            "brand": "Raf Simons",
            "season_era": "AW01 Riot! Riot! Riot!",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 64.0,
                "shoulders": 54.0,
                "length": 72.0,
                "sleeve": 66.0,
            },
            "materials": ["100% Cotton", "Polyester Fill"],
        },
        start_price=Decimal("1500.00"),
        reserve_price=Decimal("3000.00"),
        buy_now_price=Decimal("4500.00"),
        min_bid_increment=Decimal("100.00"),
        current_price=Decimal("2000.00"),
        bid_count=5,
        anti_snipe_extensions_count=0,
        starts_at=now - timedelta(hours=2),
        ends_at=now + timedelta(hours=4),
        version=1,
    )
    session.add(apparel)
    lots["apparel"] = apparel

    vinyl = Lot(
        id=uuid.uuid4(),
        seller_id=seller.id,
        leader_user_id=None,
        category=LotCategory.VINYL,
        status=LotStatus.LIVE,
        title="Aphex Twin - Selected Ambient Works 85-92",
        subtitle="1992 UK Original First Pressing on Apollo / R&S",
        description="Pristine condition original double LP record matrix etched AMB 3922.",
        specs={
            "category": "VINYL",
            "artist": "Aphex Twin",
            "album_title": "Selected Ambient Works 85-92",
            "label": "Apollo",
            "catalog_number": "AMB 3922",
            "release_year": 1992,
            "country_pressing": "UK First Press",
            "media_grade": "NM",
            "sleeve_grade": "VG_PLUS",
            "matrix_runout": "AMB 3922 A1",
            "rpm": 33,
        },
        start_price=Decimal("400.00"),
        reserve_price=Decimal("800.00"),
        buy_now_price=Decimal("1200.00"),
        min_bid_increment=Decimal("50.00"),
        current_price=Decimal("950.00"),
        bid_count=12,
        anti_snipe_extensions_count=0,
        starts_at=now - timedelta(hours=5),
        ends_at=now + timedelta(hours=1),
        version=1,
    )
    session.add(vinyl)
    lots["vinyl"] = vinyl

    hardware = Lot(
        id=uuid.uuid4(),
        seller_id=seller.id,
        leader_user_id=None,
        category=LotCategory.HARDWARE,
        status=LotStatus.SCHEDULED,
        title="Roland TR-808 Rhythm Composer",
        subtitle="Vintage 1982 analog transistor drum machine serial 182740",
        description="Fully serviced and recapped analog rhythm machine in collectors condition.",
        specs={
            "category": "HARDWARE",
            "manufacturer": "Roland",
            "model_name": "TR-808",
            "production_year": 1982,
            "serial_number": "182740",
            "voltage": "100V_JP",
            "functional_status": "FULLY_SERVICED_RECAPPED",
            "included_accessories": ["Original Dust Cover", "Power Cable"],
        },
        start_price=Decimal("3500.00"),
        reserve_price=Decimal("4500.00"),
        buy_now_price=Decimal("6000.00"),
        min_bid_increment=Decimal("200.00"),
        current_price=Decimal("0.00"),
        bid_count=0,
        anti_snipe_extensions_count=0,
        starts_at=now + timedelta(hours=12),
        ends_at=now + timedelta(hours=36),
        version=1,
    )
    session.add(hardware)
    lots["hardware"] = hardware

    artifact = Lot(
        id=uuid.uuid4(),
        seller_id=seller.id,
        leader_user_id=None,
        category=LotCategory.ARTIFACT,
        status=LotStatus.DRAFT,
        title="Braun Dieter Rams TP1 Portable Transistor Radio",
        subtitle="Iconic 1959 industrial design specimen with phonograph",
        description="Minimalist functionalist artifact designed by Dieter Rams for Braun AG.",
        specs={
            "category": "ARTIFACT",
            "creator_maker": "Dieter Rams",
            "origin_period": "1959 West Germany",
            "primary_material": "Anodized Aluminum and ABS",
            "dimensions_mm": {
                "width": 150.0,
                "height": 230.0,
                "depth": 45.0,
                "weight_grams": 1150.0,
            },
            "provenance_summary": "Acquired from Frankfurt private collection.",
            "authentication_code": "BRAUN-TP1-1959-DR",
        },
        start_price=Decimal("1200.00"),
        reserve_price=None,
        buy_now_price=Decimal("2000.00"),
        min_bid_increment=Decimal("100.00"),
        current_price=Decimal("0.00"),
        bid_count=0,
        anti_snipe_extensions_count=0,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=5),
        version=1,
    )
    session.add(artifact)
    lots["artifact"] = artifact

    await session.flush()

    for idx, (lot_obj, slot) in enumerate(
        [
            (apparel, MediaSlotType.PRIMARY),
            (apparel, MediaSlotType.TAG_STAMP),
            (apparel, MediaSlotType.DEFECT),
            (apparel, MediaSlotType.DETAIL),
            (vinyl, MediaSlotType.PRIMARY),
        ]
    ):
        media = LotMedia(
            id=uuid.uuid4(),
            lot_id=lot_obj.id,
            slot_type=slot,
            storage_key=f"lots/{lot_obj.id}/{slot.value}_{idx}.jpg",
            public_url=f"http://localhost:9000/obsolete-media/{lot_obj.id}/{idx}.jpg",
            mime_type="image/jpeg",
            size_bytes=len(JPEG_FIXTURE),
            sort_order=idx,
        )
        session.add(media)

    await session.commit()
    return lots


@pytest.mark.asyncio
async def test_catalog_search_full_text_and_trigram(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller1@obsolete.io", "seller_one")
    await _create_seed_lots(db_session, seller, frozen_clock.now())

    resp_raf = await catalog_client.get("/api/v1/lots", params={"q": "Raf Simons"})
    assert resp_raf.status_code == 200
    data_raf = resp_raf.json()
    assert data_raf["total"] == 1
    assert data_raf["items"][0]["title"] == "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber"
    assert data_raf["items"][0]["category"] == "APPAREL"
    assert "server_time" in data_raf

    resp_tr808 = await catalog_client.get("/api/v1/lots", params={"q": "TR-808"})
    assert resp_tr808.status_code == 200
    data_tr808 = resp_tr808.json()
    assert data_tr808["total"] == 1
    assert data_tr808["items"][0]["title"] == "Roland TR-808 Rhythm Composer"

    resp_aphex = await catalog_client.get("/api/v1/lots", params={"q": "Aphex Twin"})
    assert resp_aphex.status_code == 200
    data_aphex = resp_aphex.json()
    assert data_aphex["total"] == 1
    assert data_aphex["items"][0]["title"] == "Aphex Twin - Selected Ambient Works 85-92"

    resp_rams = await catalog_client.get("/api/v1/lots", params={"q": "Dieter Rams"})
    assert resp_rams.status_code == 200
    data_rams = resp_rams.json()
    assert data_rams["total"] == 1
    assert "Dieter Rams" in data_rams["items"][0]["title"]

    resp_fuzzy = await catalog_client.get("/api/v1/lots", params={"q": "Raf Simon"})
    assert resp_fuzzy.status_code == 200
    data_fuzzy = resp_fuzzy.json()
    assert data_fuzzy["total"] >= 1
    assert any("Raf Simons" in item["title"] for item in data_fuzzy["items"])

    resp_typo_raf = await catalog_client.get("/api/v1/lots", params={"q": "Raf Simns"})
    assert resp_typo_raf.status_code == 200
    data_typo_raf = resp_typo_raf.json()
    assert data_typo_raf["total"] >= 1
    assert any("Raf Simons" in item["title"] for item in data_typo_raf["items"])

    resp_typo_aphex = await catalog_client.get("/api/v1/lots", params={"q": "Aphex Twn"})
    assert resp_typo_aphex.status_code == 200
    data_typo_aphex = resp_typo_aphex.json()
    assert data_typo_aphex["total"] >= 1
    assert any("Aphex Twin" in item["title"] for item in data_typo_aphex["items"])

    resp_typo_roland = await catalog_client.get("/api/v1/lots", params={"q": "Rolnd TR-808"})
    assert resp_typo_roland.status_code == 200
    data_typo_roland = resp_typo_roland.json()
    assert data_typo_roland["total"] >= 1
    assert any("TR-808" in item["title"] for item in data_typo_roland["items"])

    resp_typo_rams = await catalog_client.get("/api/v1/lots", params={"q": "Dietr Rams"})
    assert resp_typo_rams.status_code == 200
    data_typo_rams = resp_typo_rams.json()
    assert data_typo_rams["total"] >= 1
    assert any("Dieter Rams" in item["title"] for item in data_typo_rams["items"])

    resp_pct = await catalog_client.get("/api/v1/lots", params={"q": "100%"})
    assert resp_pct.status_code == 200
    assert any("Raf Simons" in item["title"] for item in resp_pct.json()["items"])

    resp_sub_typo = await catalog_client.get("/api/v1/lots", params={"q": "transistr"})
    assert resp_sub_typo.status_code == 200
    assert any("Roland" in item["title"] for item in resp_sub_typo.json()["items"])

    resp_specs_typo = await catalog_client.get("/api/v1/lots", params={"q": "Frankfrt"})
    assert resp_specs_typo.status_code == 200
    assert any("Dieter Rams" in item["title"] for item in resp_specs_typo.json()["items"])

    resp_empty = await catalog_client.get("/api/v1/lots", params={"q": "   "})
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total"] == 4


@pytest.mark.asyncio
async def test_catalog_category_filtering(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller2@obsolete.io", "seller_two")
    await _create_seed_lots(db_session, seller, frozen_clock.now())

    resp_app = await catalog_client.get("/api/v1/lots", params={"category": "APPAREL"})
    assert resp_app.status_code == 200
    data_app = resp_app.json()
    assert data_app["total"] == 1
    assert data_app["items"][0]["category"] == "APPAREL"

    resp_vin = await catalog_client.get("/api/v1/lots", params={"category": "VINYL"})
    assert resp_vin.status_code == 200
    data_vin = resp_vin.json()
    assert data_vin["total"] == 1
    assert data_vin["items"][0]["category"] == "VINYL"

    resp_hard = await catalog_client.get("/api/v1/lots", params={"category": "HARDWARE"})
    assert resp_hard.status_code == 200
    data_hard = resp_hard.json()
    assert data_hard["total"] == 1
    assert data_hard["items"][0]["category"] == "HARDWARE"

    resp_art = await catalog_client.get("/api/v1/lots", params={"category": "ARTIFACT"})
    assert resp_art.status_code == 200
    data_art = resp_art.json()
    assert data_art["total"] == 1
    assert data_art["items"][0]["category"] == "ARTIFACT"


@pytest.mark.asyncio
async def test_catalog_status_filtering(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller3@obsolete.io", "seller_three")
    await _create_seed_lots(db_session, seller, frozen_clock.now())

    resp_live = await catalog_client.get("/api/v1/lots", params={"status": "LIVE"})
    assert resp_live.status_code == 200
    data_live = resp_live.json()
    assert data_live["total"] == 2
    assert all(item["status"] == "LIVE" for item in data_live["items"])

    resp_sched = await catalog_client.get("/api/v1/lots", params={"status": "SCHEDULED"})
    assert resp_sched.status_code == 200
    data_sched = resp_sched.json()
    assert data_sched["total"] == 1
    assert data_sched["items"][0]["status"] == "SCHEDULED"

    resp_draft = await catalog_client.get("/api/v1/lots", params={"status": "DRAFT"})
    assert resp_draft.status_code == 200
    data_draft = resp_draft.json()
    assert data_draft["total"] == 1
    assert data_draft["items"][0]["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_catalog_price_filtering_and_sorting(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller4@obsolete.io", "seller_four")
    await _create_seed_lots(db_session, seller, frozen_clock.now())

    resp_range = await catalog_client.get(
        "/api/v1/lots",
        params={"min_price": "1000.00", "max_price": "2500.00"},
    )
    assert resp_range.status_code == 200
    data_range = resp_range.json()
    titles = [item["title"] for item in data_range["items"]]
    assert "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber" in titles
    assert "Braun Dieter Rams TP1 Portable Transistor Radio" in titles
    assert "Aphex Twin - Selected Ambient Works 85-92" not in titles

    resp_invalid_range = await catalog_client.get(
        "/api/v1/lots",
        params={"min_price": "3000.00", "max_price": "1000.00"},
    )
    assert resp_invalid_range.status_code == 400
    assert resp_invalid_range.json()["error_code"] == "INVALID_PRICE_RANGE"

    resp_hot = await catalog_client.get("/api/v1/lots", params={"sort": "hot_bids"})
    assert resp_hot.status_code == 200
    items_hot = resp_hot.json()["items"]
    assert items_hot[0]["bid_count"] >= items_hot[1]["bid_count"]
    assert items_hot[0]["title"] == "Aphex Twin - Selected Ambient Works 85-92"

    resp_soon = await catalog_client.get("/api/v1/lots", params={"sort": "ending_soon"})
    assert resp_soon.status_code == 200
    items_soon = resp_soon.json()["items"]
    assert items_soon[0]["ends_at"] <= items_soon[1]["ends_at"]
    assert items_soon[0]["title"] == "Aphex Twin - Selected Ambient Works 85-92"

    resp_price_asc = await catalog_client.get("/api/v1/lots", params={"sort": "price_asc"})
    assert resp_price_asc.status_code == 200
    items_price = resp_price_asc.json()["items"]
    assert items_price[0]["title"] == "Aphex Twin - Selected Ambient Works 85-92"

    resp_price_desc = await catalog_client.get("/api/v1/lots", params={"sort": "price_desc"})
    assert resp_price_desc.status_code == 200
    items_desc = resp_price_desc.json()["items"]
    assert items_desc[0]["title"] == "Roland TR-808 Rhythm Composer"


@pytest.mark.asyncio
async def test_catalog_pagination(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller5@obsolete.io", "seller_five")
    await _create_seed_lots(db_session, seller, frozen_clock.now())

    resp_page1 = await catalog_client.get("/api/v1/lots", params={"limit": 2, "offset": 0})
    assert resp_page1.status_code == 200
    data_page1 = resp_page1.json()
    assert len(data_page1["items"]) == 2
    assert data_page1["total"] == 4
    assert data_page1["limit"] == 2
    assert data_page1["offset"] == 0

    resp_page2 = await catalog_client.get("/api/v1/lots", params={"limit": 2, "offset": 2})
    assert resp_page2.status_code == 200
    data_page2 = resp_page2.json()
    assert len(data_page2["items"]) == 2
    assert data_page2["total"] == 4
    assert data_page2["offset"] == 2

    page1_ids = {item["id"] for item in data_page1["items"]}
    page2_ids = {item["id"] for item in data_page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_lot_detail_endpoint_with_bids_and_flags(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    seller, _ = await _create_test_user(db_session, "seller6@obsolete.io", "seller_six")
    buyer1, wallet1 = await _create_test_user(db_session, "bidder1@obsolete.io", "vintage_fan")
    buyer2, wallet2 = await _create_test_user(db_session, "bidder2@obsolete.io", "audio_head")

    lots = await _create_seed_lots(db_session, seller, frozen_clock.now())
    apparel = lots["apparel"]

    base_time = frozen_clock.now() - timedelta(minutes=50)
    for i in range(1, 26):
        buyer = buyer1 if i % 2 == 1 else buyer2
        wallet = wallet1 if i % 2 == 1 else wallet2
        bid_amount = Decimal(f"{1500 + i * 50}.00")
        is_active = i == 25
        hold = WalletHold(
            id=uuid.uuid4(),
            wallet_id=wallet.id,
            user_id=buyer.id,
            lot_id=apparel.id,
            amount=bid_amount,
            status=WalletHoldStatus.ACTIVE_HOLD if is_active else WalletHoldStatus.CLAIMABLE,
        )
        db_session.add(hold)
        await db_session.flush()

        bid = Bid(
            id=uuid.uuid4(),
            lot_id=apparel.id,
            bidder_id=buyer.id,
            wallet_hold_id=hold.id,
            amount=bid_amount,
            is_buy_now=False,
            triggered_anti_snipe=False,
            idempotency_key=f"bid_idem_{i}",
            created_at=base_time + timedelta(minutes=i),
        )
        db_session.add(bid)

    apparel.current_price = Decimal("2750.00")
    apparel.bid_count = 25
    apparel.leader_user_id = buyer1.id
    await db_session.commit()

    resp = await catalog_client.get(f"/api/v1/lots/{apparel.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == str(apparel.id)
    assert data["title"] == apparel.title
    assert data["category"] == "APPAREL"
    assert data["specs"]["brand"] == "Raf Simons"
    assert len(data["media"]) == 4
    assert len(data["bids"]) == 20

    for idx in range(len(data["bids"]) - 1):
        assert Decimal(data["bids"][idx]["amount"]) > Decimal(data["bids"][idx + 1]["amount"])
        assert data["bids"][idx]["created_at"] >= data["bids"][idx + 1]["created_at"]

    assert data["bids"][0]["amount"] == "2750.00"
    assert data["bids"][0]["bidder_username_masked"] == "v***n"
    assert data["bids"][19]["amount"] == "1800.00"

    assert data["min_valid_bid"] == "2850.00"
    assert data["is_buy_now_available"] is True
    assert data["is_reserve_met"] is False
    assert "server_time" in data

    apparel.current_price = Decimal("3000.00")
    await db_session.commit()

    resp_reserve = await catalog_client.get(f"/api/v1/lots/{apparel.id}")
    assert resp_reserve.status_code == 200
    data_reserve = resp_reserve.json()
    assert data_reserve["is_reserve_met"] is True
    assert data_reserve["is_buy_now_available"] is False
    assert data_reserve["min_valid_bid"] == "3100.00"

    apparel.current_price = Decimal("3200.00")
    await db_session.commit()

    resp_above = await catalog_client.get(f"/api/v1/lots/{apparel.id}")
    assert resp_above.status_code == 200
    data_above = resp_above.json()
    assert data_above["is_reserve_met"] is True
    assert data_above["is_buy_now_available"] is False
    assert data_above["min_valid_bid"] == "3300.00"

    apparel.current_price = Decimal("3900.00")
    await db_session.commit()

    resp_buynow_locked = await catalog_client.get(f"/api/v1/lots/{apparel.id}")
    assert resp_buynow_locked.status_code == 200
    data_buynow_locked = resp_buynow_locked.json()
    assert data_buynow_locked["is_buy_now_available"] is False
    assert data_buynow_locked["min_valid_bid"] == "4000.00"

    artifact = lots["artifact"]
    artifact.status = LotStatus.LIVE
    artifact.current_price = Decimal("0.00")
    artifact.bid_count = 0
    await db_session.commit()

    resp_art_live = await catalog_client.get(f"/api/v1/lots/{artifact.id}")
    assert resp_art_live.status_code == 200
    data_art_live = resp_art_live.json()
    assert data_art_live["is_buy_now_available"] is True
    assert data_art_live["is_reserve_met"] is True
    assert data_art_live["min_valid_bid"] == "1200.00"

    artifact.bid_count = 1
    artifact.current_price = Decimal("1200.00")
    await db_session.commit()

    resp_art_bidded = await catalog_client.get(f"/api/v1/lots/{artifact.id}")
    assert resp_art_bidded.status_code == 200
    data_art_bidded = resp_art_bidded.json()
    assert data_art_bidded["is_buy_now_available"] is False
    assert data_art_bidded["is_reserve_met"] is True
    assert data_art_bidded["min_valid_bid"] == "1300.00"


@pytest.mark.asyncio
async def test_lot_detail_not_found(
    catalog_client: AsyncClient,
) -> None:
    non_existent = uuid.uuid4()
    resp = await catalog_client.get(f"/api/v1/lots/{non_existent}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "LOT_NOT_FOUND"


@pytest.mark.asyncio
async def test_lot_media_eight_photo_limit_enforcement(
    catalog_client: AsyncClient,
    db_session: AsyncSession,
    frozen_clock: FrozenClock,
) -> None:
    reg_resp = await catalog_client.post(
        "/api/v1/auth/register",
        json={
            "email": "photolimit@obsolete.io",
            "username": "photolimit_user",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await catalog_client.post(
        "/api/v1/lots",
        json={
            "category": "APPAREL",
            "title": "Undercover SS03 Scab Ethnic Crust Pants",
            "subtitle": "Hand-distressed crust denim by Jun Takahashi",
            "description": (
                "Museum tier archival pants with intricate embroidery and heavy sashiko stitching."
            ),
            "specs": {
                "category": "APPAREL",
                "brand": "Undercover",
                "season_era": "SS03 Scab",
                "tagged_size": "M",
                "condition_grade": "ARCHIVAL_MINT",
                "measurements_cm": {
                    "chest": 0.0,
                    "shoulders": 0.0,
                    "length": 105.0,
                    "sleeve": 0.0,
                },
                "materials": ["100% Cotton Sashiko"],
            },
            "start_price": "800.00",
            "reserve_price": "1200.00",
            "buy_now_price": "2000.00",
            "min_bid_increment": "50.00",
            "starts_at": (frozen_clock.now() + timedelta(days=1)).isoformat(),
            "ends_at": (frozen_clock.now() + timedelta(days=4)).isoformat(),
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    lot_id = create_resp.json()["id"]

    slot_sequence = [
        "PRIMARY",
        "TAG_STAMP",
        "DEFECT",
        "DETAIL",
        "DETAIL",
        "DETAIL",
        "DETAIL",
        "DETAIL",
    ]
    for idx, slot in enumerate(slot_sequence):
        upload_resp = await catalog_client.post(
            f"/api/v1/lots/{lot_id}/media",
            data={"slot_type": slot},
            files={"file": (f"img_{idx}.jpg", JPEG_FIXTURE, "image/jpeg")},
            headers=headers,
        )
        assert upload_resp.status_code == 201
        upload_data = upload_resp.json()
        assert upload_data["sort_order"] == idx

        if idx == 0:
            immediate_detail = await catalog_client.get(f"/api/v1/lots/{lot_id}")
            assert immediate_detail.status_code == 200
            assert len(immediate_detail.json()["media"]) == 1
            assert immediate_detail.json()["media"][0]["slot_type"] == "PRIMARY"

            immediate_list = await catalog_client.get("/api/v1/lots", params={"status": "DRAFT"})
            assert immediate_list.status_code == 200
            matching_lots = [
                item for item in immediate_list.json()["items"] if item["id"] == str(lot_id)
            ]
            assert len(matching_lots) == 1
            assert len(matching_lots[0]["media"]) == 1
            assert matching_lots[0]["media"][0]["slot_type"] == "PRIMARY"

    ninth_upload_resp = await catalog_client.post(
        f"/api/v1/lots/{lot_id}/media",
        data={"slot_type": "DETAIL"},
        files={"file": ("ninth.jpg", JPEG_FIXTURE, "image/jpeg")},
        headers=headers,
    )
    assert ninth_upload_resp.status_code == 400
    assert ninth_upload_resp.json()["error_code"] == "LOT_MEDIA_LIMIT_EXCEEDED"

    detail_resp = await catalog_client.get(f"/api/v1/lots/{lot_id}")
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["media"]) == 8


@pytest.mark.asyncio
async def test_create_lot_rejects_whitespace_fields(
    catalog_client: AsyncClient,
    frozen_clock: FrozenClock,
) -> None:
    reg_resp = await catalog_client.post(
        "/api/v1/auth/register",
        json={
            "email": "whitespacetest@obsolete.io",
            "username": "ws_tester",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "category": "APPAREL",
        "title": "   ",
        "subtitle": "Archival patch bomber jacket",
        "description": "Legendary oversized MA-1 camo bomber jacket.",
        "specs": {
            "category": "APPAREL",
            "brand": "Raf Simons",
            "season_era": "AW01",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 64.0,
                "shoulders": 54.0,
                "length": 72.0,
                "sleeve": 66.0,
            },
            "materials": ["100% Cotton"],
        },
        "start_price": "1000.00",
        "starts_at": (frozen_clock.now() + timedelta(days=1)).isoformat(),
        "ends_at": (frozen_clock.now() + timedelta(days=4)).isoformat(),
    }
    resp_title = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_title.status_code == 422

    payload["title"] = "Raf Simons Bomber"
    payload["subtitle"] = "   "
    resp_sub = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_sub.status_code == 422

    payload["subtitle"] = "Archival bomber"
    payload["description"] = "   "
    resp_desc = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_desc.status_code == 422

    payload["description"] = "Legendary oversized MA-1 camo bomber jacket."
    payload["title"] = "\t  \n  "
    resp_tab_title = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_tab_title.status_code == 422

    payload["title"] = "Raf Simons Bomber"
    payload["subtitle"] = "   \r\n"
    resp_tab_sub = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_tab_sub.status_code == 422

    payload["subtitle"] = "Archival bomber"
    payload["description"] = "\t\t\n"
    resp_tab_desc = await catalog_client.post("/api/v1/lots", json=payload, headers=headers)
    assert resp_tab_desc.status_code == 422
