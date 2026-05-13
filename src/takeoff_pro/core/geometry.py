"""Measurement geometry calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from shapely.geometry import Polygon  # type: ignore[import-untyped]

from takeoff_pro.data.models import MeasurementKind, Page, Point


@dataclass(frozen=True)
class MeasurementResult:
    """Calculated quantity and display units for a measurement."""

    quantity: float
    unit: str
    secondary_quantity: float | None = None
    secondary_unit: str | None = None


def calculate_measurement(
    kind: MeasurementKind,
    points: list[Point],
    page: Page | None,
) -> MeasurementResult:
    """Calculate measurement quantity from page-space points."""
    scale = _scale_pixels_per_unit(page)
    linear_unit = _linear_unit(page)
    if kind == MeasurementKind.COUNT:
        return MeasurementResult(quantity=float(len(points)), unit="EA")
    if kind == MeasurementKind.AREA:
        area = _area(points) / (scale * scale)
        perimeter = _length(points + points[:1]) / scale if len(points) > 2 else 0.0
        return MeasurementResult(
            quantity=area,
            unit=_area_unit(linear_unit),
            secondary_quantity=perimeter,
            secondary_unit=_length_unit(linear_unit),
        )
    if kind == MeasurementKind.LENGTH:
        return MeasurementResult(quantity=_length(points) / scale, unit=_length_unit(linear_unit))
    return MeasurementResult(quantity=0.0, unit="")


def _length(points: list[Point]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(math.hypot(end.x - start.x, end.y - start.y) for start, end in pairwise(points))


def _area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    polygon = Polygon((point.x, point.y) for point in points)
    return abs(float(polygon.area))


def _scale_pixels_per_unit(page: Page | None) -> float:
    if page is None:
        return 1.0
    if page.scale_pixels_per_unit and page.scale_pixels_per_unit > 0:
        return page.scale_pixels_per_unit
    if page.scale_x and page.scale_x > 0:
        return page.scale_x
    return 1.0


def _linear_unit(page: Page | None) -> str:
    if page is None:
        return "PX"
    return (page.scale_unit or page.scale_units or "PX").upper()


def _length_unit(unit: str) -> str:
    if unit in {"FT", "FEET", "FOOT"}:
        return "LF"
    if unit in {"IN", "INCH", "INCHES"}:
        return "IN"
    if unit in {"M", "METER", "METERS"}:
        return "M"
    return unit


def _area_unit(unit: str) -> str:
    if unit in {"FT", "FEET", "FOOT"}:
        return "SF"
    if unit in {"IN", "INCH", "INCHES"}:
        return "SQ IN"
    if unit in {"M", "METER", "METERS"}:
        return "SM"
    return f"SQ {unit}"
