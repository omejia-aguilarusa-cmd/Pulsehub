"""Validated data models for imported and native jobs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MeasurementKind(StrEnum):
    """Supported measurement geometry kinds."""

    AREA = "area"
    COUNT = "count"
    LENGTH = "length"
    UNKNOWN = "unknown"


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
    scale_x: float | None = None
    scale_y: float | None = None
    scale_units: str | None = None
    scale_pixels_per_unit: float | None = None
    scale_unit: str | None = None
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
    autolists: list[Autolist] = Field(default_factory=list)
    raw_properties: dict[str, LegacyProperty] = Field(default_factory=dict)


__all__ = [
    "Autolist",
    "Job",
    "LegacyProperty",
    "Measurement",
    "MeasurementKind",
    "Page",
    "Point",
    "TakeoffSection",
]
