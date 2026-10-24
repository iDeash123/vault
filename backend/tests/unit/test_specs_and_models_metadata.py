from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from sqlalchemy import Computed

from shared.db import dispose_engine, get_engine, get_session_maker
from shared.db.base import Base
from shared.db.models import (
    Bid,
    EscrowOrder,
    Lot,
    LotCategory,
    LotMedia,
    ModerationLog,
    RefreshSession,
    StripeWebhookEvent,
    User,
    Wallet,
    WalletHold,
    WalletLedgerEntry,
    WatchlistItem,
)
from shared.schemas import (
    CursorPaginatedResponse,
    CursorPaginationParams,
    PaginatedResponse,
    PaginationParams,
)
from shared.schemas.specs import (
    ApparelSpecs,
    ArtifactSpecs,
    HardwareSpecs,
    VinylSpecs,
    lot_specs_adapter,
)

EXPECTED_TABLES = {
    "users",
    "refresh_sessions",
    "wallets",
    "lots",
    "lot_media",
    "wallet_holds",
    "bids",
    "wallet_ledger_entries",
    "stripe_webhook_events",
    "escrow_orders",
    "watchlist_items",
    "moderation_logs",
}


def test_all_12_tables_registered_in_metadata() -> None:
    registered = set(Base.metadata.tables.keys())
    assert registered == EXPECTED_TABLES
    assert len(registered) == 12

    assert User.__tablename__ == "users"
    assert RefreshSession.__tablename__ == "refresh_sessions"
    assert Wallet.__tablename__ == "wallets"
    assert Lot.__tablename__ == "lots"
    assert LotMedia.__tablename__ == "lot_media"
    assert WalletHold.__tablename__ == "wallet_holds"
    assert Bid.__tablename__ == "bids"
    assert WalletLedgerEntry.__tablename__ == "wallet_ledger_entries"
    assert StripeWebhookEvent.__tablename__ == "stripe_webhook_events"
    assert EscrowOrder.__tablename__ == "escrow_orders"
    assert WatchlistItem.__tablename__ == "watchlist_items"
    assert ModerationLog.__tablename__ == "moderation_logs"


def test_uq_active_hold_per_lot_partial_index() -> None:
    wallet_holds_table = Base.metadata.tables["wallet_holds"]
    index_map = {str(idx.name): idx for idx in wallet_holds_table.indexes if idx.name}
    assert "uq_active_hold_per_lot" in index_map

    index = index_map["uq_active_hold_per_lot"]
    assert index.unique is True
    col_names = [col.name for col in index.columns]
    assert col_names == ["lot_id"]
    where_clause = str(index.dialect_options["postgresql"]["where"])
    assert "ACTIVE_HOLD" in where_clause


def test_table_check_constraints() -> None:
    wallets_table = Base.metadata.tables["wallets"]
    wallet_ck_names = {ck.name for ck in wallets_table.constraints if ck.name}
    assert "ck_wallets_available_non_negative" in wallet_ck_names
    assert "ck_wallets_held_non_negative" in wallet_ck_names
    assert "ck_wallets_claimable_non_negative" in wallet_ck_names

    lots_table = Base.metadata.tables["lots"]
    lot_ck_names = {ck.name for ck in lots_table.constraints if ck.name}
    assert "ck_lots_start_price_positive" in lot_ck_names
    assert "ck_lots_increment_positive" in lot_ck_names
    assert "ck_lots_reserve_gte_start" in lot_ck_names
    assert "ck_lots_ends_after_starts" in lot_ck_names

    lot_media_table = Base.metadata.tables["lot_media"]
    lot_media_ck_names = {ck.name for ck in lot_media_table.constraints if ck.name}
    assert "ck_lot_media_size_limit" in lot_media_ck_names

    wallet_holds_table = Base.metadata.tables["wallet_holds"]
    wallet_hold_ck_names = {ck.name for ck in wallet_holds_table.constraints if ck.name}
    assert "ck_wallet_holds_amount_positive" in wallet_hold_ck_names

    escrow_table = Base.metadata.tables["escrow_orders"]
    escrow_ck_names = {ck.name for ck in escrow_table.constraints if ck.name}
    assert "ck_escrow_fee_math" in escrow_ck_names


def test_lots_indexes() -> None:
    lots_table = Base.metadata.tables["lots"]
    indexes = {str(idx.name): idx for idx in lots_table.indexes if idx.name}
    assert "ix_lots_status_ends_at" in indexes
    assert "ix_lots_category_status" in indexes
    assert "ix_lots_search_vector" in indexes
    assert "ix_lots_title_trgm" in indexes

    assert indexes["ix_lots_search_vector"].dialect_options["postgresql"]["using"] == "gin"
    assert indexes["ix_lots_title_trgm"].dialect_options["postgresql"]["using"] == "gin"
    assert indexes["ix_lots_title_trgm"].dialect_options["postgresql"]["ops"] == {
        "title": "gin_trgm_ops"
    }


def test_foreign_keys_and_ondelete_actions() -> None:
    expected_fks: dict[str, list[tuple[str, str, str]]] = {
        "refresh_sessions": [("user_id", "users.id", "CASCADE")],
        "wallets": [("user_id", "users.id", "RESTRICT")],
        "lots": [
            ("seller_id", "users.id", "RESTRICT"),
            ("leader_user_id", "users.id", "RESTRICT"),
        ],
        "lot_media": [("lot_id", "lots.id", "CASCADE")],
        "wallet_holds": [
            ("wallet_id", "wallets.id", "RESTRICT"),
            ("user_id", "users.id", "RESTRICT"),
            ("lot_id", "lots.id", "RESTRICT"),
        ],
        "bids": [
            ("lot_id", "lots.id", "RESTRICT"),
            ("bidder_id", "users.id", "RESTRICT"),
            ("wallet_hold_id", "wallet_holds.id", "RESTRICT"),
        ],
        "wallet_ledger_entries": [
            ("wallet_id", "wallets.id", "RESTRICT"),
            ("user_id", "users.id", "RESTRICT"),
            ("reference_lot_id", "lots.id", "RESTRICT"),
            ("reference_hold_id", "wallet_holds.id", "RESTRICT"),
        ],
        "stripe_webhook_events": [("user_id", "users.id", "RESTRICT")],
        "escrow_orders": [
            ("lot_id", "lots.id", "RESTRICT"),
            ("buyer_id", "users.id", "RESTRICT"),
            ("seller_id", "users.id", "RESTRICT"),
            ("wallet_hold_id", "wallet_holds.id", "RESTRICT"),
        ],
        "watchlist_items": [
            ("user_id", "users.id", "CASCADE"),
            ("lot_id", "lots.id", "CASCADE"),
        ],
        "moderation_logs": [
            ("lot_id", "lots.id", "CASCADE"),
            ("curator_id", "users.id", "RESTRICT"),
        ],
    }

    for table_name, fks in expected_fks.items():
        table = Base.metadata.tables[table_name]
        actual_fks = {
            (
                fk.parent.name,
                fk.target_fullname,
                (fk.ondelete.upper() if fk.ondelete else None),
            )
            for fk in table.foreign_keys
        }
        for parent_col, target, ondelete in fks:
            assert (parent_col, target, ondelete) in actual_fks


def test_unique_constraints_and_unique_indexes() -> None:
    assert Base.metadata.tables["users"].c.email.unique is True
    assert Base.metadata.tables["users"].c.username.unique is True
    assert Base.metadata.tables["refresh_sessions"].c.token_hash.unique is True
    assert Base.metadata.tables["wallets"].c.user_id.unique is True
    assert Base.metadata.tables["lot_media"].c.storage_key.unique is True
    assert Base.metadata.tables["bids"].c.wallet_hold_id.unique is True
    assert Base.metadata.tables["bids"].c.idempotency_key.unique is True
    assert Base.metadata.tables["wallet_ledger_entries"].c.idempotency_key.unique is True
    assert Base.metadata.tables["stripe_webhook_events"].c.stripe_event_id.unique is True
    assert Base.metadata.tables["escrow_orders"].c.lot_id.unique is True
    assert Base.metadata.tables["escrow_orders"].c.wallet_hold_id.unique is True

    watchlist_table = Base.metadata.tables["watchlist_items"]
    uq_names = {uq.name for uq in watchlist_table.constraints if hasattr(uq, "name") and uq.name}
    assert "uq_watchlist_user_lot" in uq_names


def test_all_indexes_detailed() -> None:
    bids_table = Base.metadata.tables["bids"]
    bids_indexes = {str(idx.name): idx for idx in bids_table.indexes if idx.name}
    assert "ix_bids_lot_created_desc" in bids_indexes
    assert "ix_bids_bidder_id" in bids_indexes

    ledger_table = Base.metadata.tables["wallet_ledger_entries"]
    ledger_indexes = {str(idx.name): idx for idx in ledger_table.indexes if idx.name}
    assert "ix_ledger_wallet_created" in ledger_indexes

    lot_media_table = Base.metadata.tables["lot_media"]
    media_indexes = {str(idx.name): idx for idx in lot_media_table.indexes if idx.name}
    assert "ix_lot_media_lot_sort" in media_indexes

    refresh_table = Base.metadata.tables["refresh_sessions"]
    refresh_indexes = {str(idx.name): idx for idx in refresh_table.indexes if idx.name}
    assert "ix_refresh_sessions_user_id" in refresh_indexes

    holds_table = Base.metadata.tables["wallet_holds"]
    holds_indexes = {str(idx.name): idx for idx in holds_table.indexes if idx.name}
    assert "ix_wallet_holds_user_status" in holds_indexes
    assert "ix_wallet_holds_lot_id" in holds_indexes


def test_lot_search_vector_computed_column() -> None:
    lots_table = Base.metadata.tables["lots"]
    col = lots_table.c.search_vector
    assert isinstance(col.computed, Computed)
    assert col.computed.persisted is True
    assert "to_tsvector" in str(col.computed.sqltext)


def test_pagination_schemas() -> None:
    params = PaginationParams()
    assert params.limit == 20
    assert params.offset == 0

    custom_params = PaginationParams(limit=50, offset=10)
    assert custom_params.limit == 50
    assert custom_params.offset == 10

    with pytest.raises(ValidationError):
        PaginationParams(limit=0)
    with pytest.raises(ValidationError):
        PaginationParams(limit=101)
    with pytest.raises(ValidationError):
        PaginationParams(offset=-1)

    cursor_params = CursorPaginationParams()
    assert cursor_params.limit == 20
    assert cursor_params.cursor is None

    paginated = PaginatedResponse[str](items=["item1", "item2"], total=2, limit=20, offset=0)
    assert len(paginated.items) == 2
    assert paginated.total == 2

    cursor_resp = CursorPaginatedResponse[int](
        items=[10, 20],
        next_cursor="cursor_token",
        has_more=True,
    )
    assert cursor_resp.has_more is True
    assert cursor_resp.next_cursor == "cursor_token"


@pytest.mark.asyncio
async def test_session_engine_and_maker() -> None:
    engine1 = get_engine("postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db")
    maker1 = get_session_maker(engine1)
    session = maker1()
    assert session is not None
    await session.close()
    await engine1.dispose()
    await dispose_engine()


def test_apparel_specs_validation() -> None:
    valid_payload: dict[str, Any] = {
        "category": "APPAREL",
        "brand": "Raf Simons",
        "season_era": "AW01 Riot! Riot! Riot!",
        "tagged_size": "48",
        "condition_grade": "ARCHIVAL_MINT",
        "measurements_cm": {
            "chest": 58.5,
            "shoulders": 49.0,
            "length": 72.0,
            "sleeve": 65.0,
        },
        "materials": ["100% Cotton", "Riri Zippers"],
    }
    specs = lot_specs_adapter.validate_python(valid_payload)
    assert isinstance(specs, ApparelSpecs)
    assert specs.category == LotCategory.APPAREL
    assert specs.brand == "Raf Simons"

    invalid_grade = dict(valid_payload, condition_grade="BRAND_NEW")
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(invalid_grade)

    extra_field = dict(valid_payload, unknown_key="invalid")
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(extra_field)


def test_vinyl_specs_validation() -> None:
    valid_payload: dict[str, Any] = {
        "category": "VINYL",
        "artist": "Aphex Twin",
        "album_title": "Selected Ambient Works 85-92",
        "label": "Apollo",
        "catalog_number": "AMB 3922",
        "release_year": 1992,
        "country_pressing": "Belgium Original",
        "media_grade": "NM",
        "sleeve_grade": "VG_PLUS",
        "matrix_runout": "AMB 3922 A1",
        "rpm": 33,
    }
    specs = lot_specs_adapter.validate_python(valid_payload)
    assert isinstance(specs, VinylSpecs)
    assert specs.rpm == 33

    invalid_rpm = dict(valid_payload, rpm=16)
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(invalid_rpm)

    too_early_year = dict(valid_payload, release_year=1940)
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(too_early_year)

    future_year = dict(valid_payload, release_year=2030)
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(future_year)


def test_hardware_specs_validation() -> None:
    valid_payload: dict[str, Any] = {
        "category": "HARDWARE",
        "manufacturer": "Roland",
        "model_name": "TR-808 Rhythm Composer",
        "production_year": 1981,
        "serial_number": "SN-014902",
        "voltage": "100V_JP",
        "functional_status": "FULLY_SERVICED_RECAPPED",
        "included_accessories": ["Original Manual", "Dust Cover"],
    }
    specs = lot_specs_adapter.validate_python(valid_payload)
    assert isinstance(specs, HardwareSpecs)
    assert specs.manufacturer == "Roland"

    invalid_voltage = dict(valid_payload, voltage="380V_INDUSTRIAL")
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(invalid_voltage)

    invalid_status = dict(valid_payload, functional_status="BROKEN")
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(invalid_status)


def test_artifact_specs_validation() -> None:
    valid_payload: dict[str, Any] = {
        "category": "ARTIFACT",
        "creator_maker": "Dieter Rams",
        "origin_period": "1960s Frankfurt",
        "primary_material": "Anodized Aluminum",
        "dimensions_mm": {
            "width": 250.0,
            "height": 180.0,
            "depth": 95.0,
            "weight_grams": 1450.0,
        },
        "provenance_summary": "Acquired from private collector in Hamburg",
        "authentication_code": "BRAUN-ARCH-1965",
    }
    specs = lot_specs_adapter.validate_python(valid_payload)
    assert isinstance(specs, ArtifactSpecs)
    assert specs.creator_maker == "Dieter Rams"

    missing_dim = dict(
        valid_payload,
        dimensions_mm={"width": 250.0, "height": 180.0, "depth": 95.0},
    )
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(missing_dim)


def test_unknown_category_rejected() -> None:
    payload = {
        "category": "FURNITURE",
        "name": "Eames Lounge Chair",
    }
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(payload)


@given(
    brand=st.text(min_size=1, max_size=50),
    season_era=st.text(min_size=1, max_size=50),
    tagged_size=st.text(min_size=1, max_size=20),
    condition_grade=st.sampled_from(["ARCHIVAL_MINT", "GENTLY_WORN", "DISTRESSED", "ALTERED"]),
    chest=st.floats(min_value=20.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    shoulders=st.floats(min_value=20.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    length=st.floats(min_value=30.0, max_value=150.0, allow_nan=False, allow_infinity=False),
    sleeve=st.floats(min_value=20.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    materials=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=5),
)
def test_hypothesis_apparel_specs(
    brand: str,
    season_era: str,
    tagged_size: str,
    condition_grade: str,
    chest: float,
    shoulders: float,
    length: float,
    sleeve: float,
    materials: list[str],
) -> None:
    data: dict[str, Any] = {
        "category": "APPAREL",
        "brand": brand,
        "season_era": season_era,
        "tagged_size": tagged_size,
        "condition_grade": condition_grade,
        "measurements_cm": {
            "chest": chest,
            "shoulders": shoulders,
            "length": length,
            "sleeve": sleeve,
        },
        "materials": materials,
    }
    parsed = lot_specs_adapter.validate_python(data)
    assert isinstance(parsed, ApparelSpecs)
    assert parsed.brand == brand
    assert parsed.category == LotCategory.APPAREL


@given(
    artist=st.text(min_size=1, max_size=50),
    album_title=st.text(min_size=1, max_size=50),
    label=st.text(min_size=1, max_size=50),
    catalog_number=st.text(min_size=1, max_size=30),
    release_year=st.integers(min_value=1950, max_value=2026),
    country_pressing=st.text(min_size=1, max_size=30),
    media_grade=st.sampled_from(["M", "NM", "VG_PLUS", "VG", "G_PLUS"]),
    sleeve_grade=st.sampled_from(["M", "NM", "VG_PLUS", "VG", "G_PLUS"]),
    matrix_runout=st.text(min_size=1, max_size=50),
    rpm=st.sampled_from([33, 45, 78]),
)
def test_hypothesis_vinyl_specs(
    artist: str,
    album_title: str,
    label: str,
    catalog_number: str,
    release_year: int,
    country_pressing: str,
    media_grade: str,
    sleeve_grade: str,
    matrix_runout: str,
    rpm: int,
) -> None:
    data: dict[str, Any] = {
        "category": "VINYL",
        "artist": artist,
        "album_title": album_title,
        "label": label,
        "catalog_number": catalog_number,
        "release_year": release_year,
        "country_pressing": country_pressing,
        "media_grade": media_grade,
        "sleeve_grade": sleeve_grade,
        "matrix_runout": matrix_runout,
        "rpm": rpm,
    }
    parsed = lot_specs_adapter.validate_python(data)
    assert isinstance(parsed, VinylSpecs)
    assert parsed.artist == artist
    assert parsed.category == LotCategory.VINYL


@given(
    manufacturer=st.text(min_size=1, max_size=50),
    model_name=st.text(min_size=1, max_size=50),
    production_year=st.integers(min_value=1900, max_value=2026),
    serial_number=st.text(min_size=1, max_size=40),
    voltage=st.sampled_from(["100V_JP", "120V_US", "220V_EU", "MULTI_VOLTAGE", "BATTERY_DC"]),
    functional_status=st.sampled_from(
        [
            "FULLY_SERVICED_RECAPPED",
            "WORKING_ORIGINAL",
            "POWERS_ON_UNTESTED",
            "FOR_PARTS_RESTORATION",
        ]
    ),
    included_accessories=st.lists(st.text(min_size=1, max_size=40), min_size=0, max_size=5),
)
def test_hypothesis_hardware_specs(
    manufacturer: str,
    model_name: str,
    production_year: int,
    serial_number: str,
    voltage: str,
    functional_status: str,
    included_accessories: list[str],
) -> None:
    data: dict[str, Any] = {
        "category": "HARDWARE",
        "manufacturer": manufacturer,
        "model_name": model_name,
        "production_year": production_year,
        "serial_number": serial_number,
        "voltage": voltage,
        "functional_status": functional_status,
        "included_accessories": included_accessories,
    }
    parsed = lot_specs_adapter.validate_python(data)
    assert isinstance(parsed, HardwareSpecs)
    assert parsed.manufacturer == manufacturer
    assert parsed.category == LotCategory.HARDWARE


@given(
    creator_maker=st.text(min_size=1, max_size=50),
    origin_period=st.text(min_size=1, max_size=50),
    primary_material=st.text(min_size=1, max_size=50),
    width=st.floats(min_value=1.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    height=st.floats(min_value=1.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    depth=st.floats(min_value=1.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    weight_grams=st.floats(
        min_value=1.0,
        max_value=100000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    provenance_summary=st.text(min_size=1, max_size=200),
    authentication_code=st.text(min_size=1, max_size=50),
)
def test_hypothesis_artifact_specs(
    creator_maker: str,
    origin_period: str,
    primary_material: str,
    width: float,
    height: float,
    depth: float,
    weight_grams: float,
    provenance_summary: str,
    authentication_code: str,
) -> None:
    data: dict[str, Any] = {
        "category": "ARTIFACT",
        "creator_maker": creator_maker,
        "origin_period": origin_period,
        "primary_material": primary_material,
        "dimensions_mm": {
            "width": width,
            "height": height,
            "depth": depth,
            "weight_grams": weight_grams,
        },
        "provenance_summary": provenance_summary,
        "authentication_code": authentication_code,
    }
    parsed = lot_specs_adapter.validate_python(data)
    assert isinstance(parsed, ArtifactSpecs)
    assert parsed.creator_maker == creator_maker
    assert parsed.category == LotCategory.ARTIFACT


@given(
    invalid_category=st.text(min_size=1, max_size=30).filter(
        lambda c: c not in {"APPAREL", "VINYL", "HARDWARE", "ARTIFACT"}
    )
)
def test_hypothesis_invalid_category_rejected(invalid_category: str) -> None:
    payload = {"category": invalid_category, "arbitrary_field": "val"}
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(payload)


@given(
    invalid_year=st.one_of(
        st.integers(max_value=1949),
        st.integers(min_value=2027, max_value=9999),
    )
)
def test_hypothesis_vinyl_invalid_year_rejected(invalid_year: int) -> None:
    payload: dict[str, Any] = {
        "category": "VINYL",
        "artist": "Artist",
        "album_title": "Title",
        "label": "Label",
        "catalog_number": "CAT1",
        "release_year": invalid_year,
        "country_pressing": "UK",
        "media_grade": "NM",
        "sleeve_grade": "NM",
        "matrix_runout": "RUNOUT",
        "rpm": 33,
    }
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(payload)


@given(
    invalid_rpm=st.integers(min_value=-1000, max_value=1000).filter(lambda r: r not in {33, 45, 78})
)
def test_hypothesis_vinyl_invalid_rpm_rejected(invalid_rpm: int) -> None:
    payload: dict[str, Any] = {
        "category": "VINYL",
        "artist": "Artist",
        "album_title": "Title",
        "label": "Label",
        "catalog_number": "CAT1",
        "release_year": 2000,
        "country_pressing": "UK",
        "media_grade": "NM",
        "sleeve_grade": "NM",
        "matrix_runout": "RUNOUT",
        "rpm": invalid_rpm,
    }
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(payload)


@given(
    extra_key=st.text(min_size=1, max_size=15).filter(
        lambda k: (
            k
            not in {
                "category",
                "brand",
                "season_era",
                "tagged_size",
                "condition_grade",
                "measurements_cm",
                "materials",
            }
        )
    )
)
def test_hypothesis_extra_keys_rejected(extra_key: str) -> None:
    valid_payload: dict[str, Any] = {
        "category": "APPAREL",
        "brand": "Raf Simons",
        "season_era": "AW01",
        "tagged_size": "48",
        "condition_grade": "ARCHIVAL_MINT",
        "measurements_cm": {
            "chest": 58.5,
            "shoulders": 49.0,
            "length": 72.0,
            "sleeve": 65.0,
        },
        "materials": ["100% Cotton"],
    }
    valid_payload[extra_key] = "forbidden"
    with pytest.raises(ValidationError):
        lot_specs_adapter.validate_python(valid_payload)
