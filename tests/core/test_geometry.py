from __future__ import annotations

from takeoff_pro.core import calculate_measurement
from takeoff_pro.data.models import MeasurementKind, Page, Point


def test_calculate_measurement_uses_page_scale_for_length_area_and_count() -> None:
    page = Page(
        id="page-1",
        name="Scaled",
        scale_pixels_per_unit=10.0,
        scale_unit="FT",
    )

    length = calculate_measurement(
        MeasurementKind.LENGTH,
        [Point(x=0, y=0), Point(x=30, y=40)],
        page,
    )
    area = calculate_measurement(
        MeasurementKind.AREA,
        [Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=50), Point(x=0, y=50)],
        page,
    )
    count = calculate_measurement(MeasurementKind.COUNT, [Point(x=1, y=1), Point(x=2, y=2)], page)

    assert length.quantity == 5
    assert length.unit == "LF"
    assert area.quantity == 50
    assert area.unit == "SF"
    assert area.secondary_quantity == 30
    assert area.secondary_unit == "LF"
    assert count.quantity == 2
    assert count.unit == "EA"


def test_calculate_measurement_supports_metric_and_unknown_units() -> None:
    metric_page = Page(id="metric", name="Metric", scale_pixels_per_unit=2, scale_unit="M")
    raw_page = Page(id="raw", name="Raw")

    metric = calculate_measurement(
        MeasurementKind.AREA,
        [Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=4), Point(x=0, y=4)],
        metric_page,
    )
    raw = calculate_measurement(
        MeasurementKind.LENGTH, [Point(x=0, y=0), Point(x=3, y=4)], raw_page
    )
    unknown = calculate_measurement(MeasurementKind.UNKNOWN, [], None)

    assert metric.quantity == 4
    assert metric.unit == "SM"
    assert raw.quantity == 5
    assert raw.unit == "PX"
    assert unknown.quantity == 0
