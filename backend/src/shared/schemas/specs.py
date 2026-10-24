from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from shared.db.models.enums import LotCategory


class ApparelMeasurements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chest: float
    shoulders: float
    length: float
    sleeve: float


class ApparelSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[LotCategory.APPAREL] = LotCategory.APPAREL
    brand: str
    season_era: str
    tagged_size: str
    condition_grade: Literal["ARCHIVAL_MINT", "GENTLY_WORN", "DISTRESSED", "ALTERED"]
    measurements_cm: ApparelMeasurements
    materials: list[str]


class VinylSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[LotCategory.VINYL] = LotCategory.VINYL
    artist: str
    album_title: str
    label: str
    catalog_number: str
    release_year: int = Field(ge=1950, le=2026)
    country_pressing: str
    media_grade: Literal["M", "NM", "VG_PLUS", "VG", "G_PLUS"]
    sleeve_grade: Literal["M", "NM", "VG_PLUS", "VG", "G_PLUS"]
    matrix_runout: str
    rpm: Literal[33, 45, 78]


class HardwareSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[LotCategory.HARDWARE] = LotCategory.HARDWARE
    manufacturer: str
    model_name: str
    production_year: int
    serial_number: str
    voltage: Literal["100V_JP", "120V_US", "220V_EU", "MULTI_VOLTAGE", "BATTERY_DC"]
    functional_status: Literal[
        "FULLY_SERVICED_RECAPPED",
        "WORKING_ORIGINAL",
        "POWERS_ON_UNTESTED",
        "FOR_PARTS_RESTORATION",
    ]
    included_accessories: list[str]


class ArtifactDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: float
    height: float
    depth: float
    weight_grams: float


class ArtifactSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[LotCategory.ARTIFACT] = LotCategory.ARTIFACT
    creator_maker: str
    origin_period: str
    primary_material: str
    dimensions_mm: ArtifactDimensions
    provenance_summary: str
    authentication_code: str


LotSpecs = Annotated[
    ApparelSpecs | VinylSpecs | HardwareSpecs | ArtifactSpecs,
    Field(discriminator="category"),
]

lot_specs_adapter: TypeAdapter[LotSpecs] = TypeAdapter(LotSpecs)
