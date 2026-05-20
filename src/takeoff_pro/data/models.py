"""Validated data models for imported and native jobs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from takeoff_pro.estimate.models import Assembly, EstimateItem


class MeasurementKind(StrEnum):
    """Supported measurement geometry kinds."""

    AREA = "area"
    COUNT = "count"
    LENGTH = "length"
    UNKNOWN = "unknown"


class PageRasterStatus(StrEnum):
    """Rasterization status for AI/page-image workflows."""

    NOT_STARTED = "not_started"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class AiTakeoffStatus(StrEnum):
    """Lifecycle status for an AI takeoff run."""

    NOT_CONFIGURED = "not_configured"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class AiRoomType(StrEnum):
    """Painting takeoff room categories."""

    OFFICE = "office"
    BATHROOM = "bathroom"
    CORRIDOR = "corridor"
    LOBBY = "lobby"
    STORAGE = "storage"
    MECHANICAL = "mechanical"
    UNKNOWN = "unknown"


class AiElementType(StrEnum):
    """Painting-relevant detected element types."""

    DOOR = "door"
    WINDOW = "window"
    WALL = "wall"
    SPECIAL_SURFACE = "special_surface"
    NOTE = "note"
    UNKNOWN = "unknown"


class AiTakeoffTotals(BaseModel):
    """Rollup totals for a painting AI takeoff."""

    model_config = ConfigDict(extra="forbid")

    floor_area_sf: float = 0.0
    wall_sf: float = 0.0
    ceiling_sf: float = 0.0
    door_count: int = 0
    window_count: int = 0
    trim_lf: float = 0.0


class AiRoom(BaseModel):
    """A normalized AI-detected painting room."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: AiRoomType = AiRoomType.UNKNOWN
    page_id: str
    location_description: str = ""
    confidence: float = 0.0
    floor_area_sf: float | None = None
    perimeter_ft: float | None = None
    wall_sf: float | None = None
    ceiling_sf: float | None = None
    door_count: int = 0
    window_count: int = 0
    trim_lf: float | None = None
    assumptions: list[str] = Field(default_factory=list)


class AiElement(BaseModel):
    """A normalized AI-detected painting element."""

    model_config = ConfigDict(extra="forbid")

    type: AiElementType = AiElementType.UNKNOWN
    count: int = 0
    page_id: str
    location_description: str = ""
    confidence: float = 0.0


class AiTakeoffPageResult(BaseModel):
    """AI takeoff results for a single drawing page."""

    model_config = ConfigDict(extra="forbid")

    page_id: str
    rooms: list[AiRoom] = Field(default_factory=list)
    elements: list[AiElement] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AiTakeoffRun(BaseModel):
    """Persisted AI painting takeoff run metadata and normalized output."""

    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    status: AiTakeoffStatus
    scope: str = "painting"
    provider: str | None = None
    model: str | None = None
    prompt_version: str = "painting-takeoff-v1"
    page_ids: list[str] = Field(default_factory=list)
    pages: list[AiTakeoffPageResult] = Field(default_factory=list)
    totals: AiTakeoffTotals = Field(default_factory=AiTakeoffTotals)
    confidence_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    raw_response: str | None = None
    created_at: str
    updated_at: str


class LegacyProperty(BaseModel):
    """Raw property captured from a legacy Data.xml item."""

    model_config = ConfigDict(extra="forbid")

    name: str
    property_class: str | None = None
    value: str | None = None
    guid: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class Point(BaseModel):
    """A page-space point from digitized measurement geometry."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    point_type: str | None = None


class Measurement(BaseModel):
    """A digitized measurement attached to a takeoff section."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: MeasurementKind
    page_id: str | None = None
    order_index: int | None = None
    z_order: int | None = None
    visible: bool = True
    points: list[Point] = Field(default_factory=list)
    quantity: float | None = None
    unit: str | None = None
    secondary_quantity: float | None = None
    secondary_unit: str | None = None
    source: str = "manual"
    confidence: float | None = None
    source_xml_path: Path | None = None
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


class TakeoffSection(BaseModel):
    """A measured estimating section and its child measurements."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: MeasurementKind
    description: str | None = None
    item_number: str | None = None
    order_index: int | None = None
    scale_units: str | None = None
    estimate_reference_type: str | None = None
    estimate_reference_id: str | None = None
    source_xml_path: Path | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


class Page(BaseModel):
    """A plan page imported from a page folder."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    order_index: int | None = None
    image_guid: str | None = None
    image_path: Path | None = None
    source_page_index: int = 0
    source_filename: str | None = None
    source_page_count: int | None = None
    uploaded_at: str | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    scale_units: str | None = None
    scale_pixels_per_unit: float | None = None
    scale_unit: str | None = None
    scale_source: str | None = None
    raster_image_path: Path | None = None
    raster_width: int | None = None
    raster_height: int | None = None
    raster_zoom: float | None = None
    raster_status: PageRasterStatus = PageRasterStatus.NOT_STARTED
    raster_error: str | None = None
    canvas_width: int = 1600
    canvas_height: int = 1000
    measurement_type: str | None = None
    source_xml_path: Path | None = None
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


class Autolist(BaseModel):
    """An imported automatic list container or value list."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    values: list[str] = Field(default_factory=list)
    source_xml_path: Path | None = None
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


class Job(BaseModel):
    """A complete imported construction takeoff job."""

    model_config = ConfigDict(extra="forbid")

    native_format_version: int = 1
    id: str
    name: str
    measurement_system: str | None = None
    description: str | None = None
    source_root: Path
    pages: list[Page] = Field(default_factory=list)
    takeoff_sections: list[TakeoffSection] = Field(default_factory=list)
    items: list[EstimateItem] = Field(default_factory=list)
    assemblies: list[Assembly] = Field(default_factory=list)
    ai_takeoff_runs: list[AiTakeoffRun] = Field(default_factory=list)
    autolists: list[Autolist] = Field(default_factory=list)
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


__all__ = [
    "AiElement",
    "AiElementType",
    "AiRoom",
    "AiRoomType",
    "AiTakeoffPageResult",
    "AiTakeoffRun",
    "AiTakeoffStatus",
    "AiTakeoffTotals",
    "Autolist",
    "Job",
    "LegacyProperty",
    "Measurement",
    "MeasurementKind",
    "Page",
    "PageRasterStatus",
    "Point",
    "TakeoffSection",
]
