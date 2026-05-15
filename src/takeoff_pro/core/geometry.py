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
    x_scale, y_scale = _scale_pixels_per_unit(page)
    linear_unit = _linear_unit(page)
    if kind == MeasurementKind.COUNT:
        return MeasurementResult(quantity=float(len(points)), unit="EA")
    if kind == MeasurementKind.AREA:
        scaled_points = _scale_points(points, x_scale=x_scale, y_scale=y_scale)
        area = _area(scaled_points)
        perimeter = _length(scaled_points + scaled_points[:1]) if len(points) > 2 else 0.0
        return MeasurementResult(
            quantity=area,
            unit=_area_unit(linear_unit),
            secondary_quantity=perimeter,
            secondary_unit=_length_unit(linear_unit),
        )
    if kind == MeasurementKind.LENGTH:
        scaled_points = _scale_points(points, x_scale=x_scale, y_scale=y_scale)
        return MeasurementResult(quantity=_length(scaled_points), unit=_length_unit(linear_unit))
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


def _scale_points(points: list[Point], *, x_scale: float, y_scale: float) -> list[Point]:
    return [
        Point(
            x=point.x / x_scale,
            y=point.y / y_scale,
            point_type=point.point_type,
        )
        for point in points
    ]


def _scale_pixels_per_unit(page: Page | None) -> tuple[float, float]:
    if page is None:
        return 1.0, 1.0
    if page.scale_pixels_per_unit and page.scale_pixels_per_unit > 0:
        return page.scale_pixels_per_unit, page.scale_pixels_per_unit
    if page.scale_x and page.scale_x > 0 and page.scale_y and page.scale_y > 0:
        return page.scale_x, page.scale_y
    if page.scale_x and page.scale_x > 0:
        return page.scale_x, page.scale_x
    if page.scale_y and page.scale_y > 0:
        return page.scale_y, page.scale_y
    return 1.0, 1.0


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
