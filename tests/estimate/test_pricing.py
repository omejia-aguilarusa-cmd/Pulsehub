from __future__ import annotations

from pathlib import Path

import pytest

from takeoff_pro.data import create_blank_job
from takeoff_pro.data.models import Measurement, MeasurementKind, Point, TakeoffSection
from takeoff_pro.estimate.library import load_items_csv, save_items_csv
from takeoff_pro.estimate.models import Assembly, AssemblyComponent, EstimateItem
from takeoff_pro.estimate.pricing import UnitConversionError, convert_quantity, price_job


def test_convert_quantity_handles_length_area_and_incompatible_units() -> None:
    assert convert_quantity(12, "IN", "LF") == 1
    assert convert_quantity(144, "SQ IN", "SF") == 1

    with pytest.raises(UnitConversionError):
        convert_quantity(1, "SF", "LF")


def test_price_job_prices_direct_item_and_assembly() -> None:
    job = create_blank_job("Priced")
    page_id = job.pages[0].id
    direct_section = TakeoffSection(
        id="direct",
        name="Baseboard",
        kind=MeasurementKind.LENGTH,
        estimate_reference_type="item",
        estimate_reference_id="WALL",
        measurements=[
            Measurement(
                id="length",
                name="Length",
                kind=MeasurementKind.LENGTH,
                page_id=page_id,
                points=[Point(x=0, y=0), Point(x=10, y=0)],
                quantity=10,
                unit="LF",
            )
        ],
    )
    assembly_section = TakeoffSection(
        id="assembly",
        name="Painted Wall",
        kind=MeasurementKind.AREA,
        estimate_reference_type="assembly",
        estimate_reference_id="PAINTED-WALL",
        measurements=[
            Measurement(
                id="area",
                name="Area",
                kind=MeasurementKind.AREA,
                page_id=page_id,
                points=[Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=10), Point(x=0, y=10)],
                quantity=100,
                unit="SF",
            )
        ],
    )
    job.takeoff_sections = [direct_section, assembly_section]
    job.items = [
        EstimateItem(item_id="WALL", description="Wall material", unit="LF", unit_cost=4.5),
        EstimateItem(item_id="PAINT", description="Paint", unit="GAL", unit_cost=35),
        EstimateItem(item_id="LABOR", description="Labor", unit="HR", unit_cost=65),
    ]
    job.assemblies = [
        Assembly(
            assembly_id="PAINTED-WALL",
            name="Painted wall",
            takeoff_unit="SF",
            components=[
                AssemblyComponent(item_id="PAINT", quantity_per_takeoff_unit=0.04),
                AssemblyComponent(item_id="LABOR", quantity_per_takeoff_unit=0.02),
            ],
        )
    ]

    lines = price_job(job)

    assert len(lines) == 3
    assert lines[0].total_cost == 45
    assert lines[1].quantity == 4
    assert lines[1].total_cost == 140
    assert lines[2].quantity == 2
    assert lines[2].total_cost == 130
    assert sum(line.total_cost for line in lines) == 315


def test_items_csv_round_trip(tmp_path: Path) -> None:
    items = [EstimateItem(item_id="A", description="Alpha", unit="EA", unit_cost=2.5)]
    path = tmp_path / "items.csv"

    save_items_csv(items, path)
    loaded = load_items_csv(path)

    assert loaded == items
