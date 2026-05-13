"""Estimating unit conversion and pricing math."""

from __future__ import annotations

from takeoff_pro.core import calculate_measurement
from takeoff_pro.data.models import Job, Page, TakeoffSection
from takeoff_pro.estimate.models import Assembly, BomLine, EstimateItem

_UNIT_ALIASES = {
    "FT": ("length", 1.0),
    "LF": ("length", 1.0),
    "IN": ("length", 1.0 / 12.0),
    "M": ("length", 3.280839895),
    "SF": ("area", 1.0),
    "SQ FT": ("area", 1.0),
    "SQ IN": ("area", 1.0 / 144.0),
    "SM": ("area", 10.7639104167),
    "EA": ("count", 1.0),
}


class UnitConversionError(ValueError):
    """Raised when quantities cannot be converted between units."""


def convert_quantity(quantity: float, from_unit: str, to_unit: str) -> float:
    """Convert a quantity between compatible estimating units."""
    from_dimension, from_factor = _unit_info(from_unit)
    to_dimension, to_factor = _unit_info(to_unit)
    if from_dimension != to_dimension:
        msg = f"Cannot convert {from_unit} to {to_unit}."
        raise UnitConversionError(msg)
    return quantity * from_factor / to_factor


def price_job(job: Job) -> list[BomLine]:
    """Price all takeoff sections with attached items or assemblies."""
    item_lookup = {item.item_id: item for item in job.items}
    assembly_lookup = {assembly.assembly_id: assembly for assembly in job.assemblies}
    page_lookup = {page.id: page for page in job.pages}
    lines: list[BomLine] = []

    for section in job.takeoff_sections:
        if section.estimate_reference_type == "item" and section.estimate_reference_id:
            item = item_lookup.get(section.estimate_reference_id)
            if item is not None:
                lines.append(_price_item_section(section, item, page_lookup))
        elif section.estimate_reference_type == "assembly" and section.estimate_reference_id:
            assembly = assembly_lookup.get(section.estimate_reference_id)
            if assembly is not None:
                lines.extend(_price_assembly_section(section, assembly, item_lookup, page_lookup))
    return lines


def _price_item_section(
    section: TakeoffSection,
    item: EstimateItem,
    page_lookup: dict[str, Page],
) -> BomLine:
    quantity, unit = _section_quantity(section, page_lookup)
    item_quantity = convert_quantity(quantity, unit, item.unit)
    return BomLine(
        section_id=section.id,
        section_name=section.name,
        item_id=item.item_id,
        description=item.description,
        unit=item.unit,
        quantity=item_quantity,
        unit_cost=item.unit_cost,
        total_cost=item_quantity * item.unit_cost,
        source_type="item",
        source_id=item.item_id,
    )


def _price_assembly_section(
    section: TakeoffSection,
    assembly: Assembly,
    item_lookup: dict[str, EstimateItem],
    page_lookup: dict[str, Page],
) -> list[BomLine]:
    takeoff_quantity, takeoff_unit = _section_quantity(section, page_lookup)
    assembly_quantity = convert_quantity(takeoff_quantity, takeoff_unit, assembly.takeoff_unit)
    lines: list[BomLine] = []
    for component in assembly.components:
        item = item_lookup.get(component.item_id)
        if item is None:
            continue
        quantity = assembly_quantity * component.quantity_per_takeoff_unit
        lines.append(
            BomLine(
                section_id=section.id,
                section_name=section.name,
                item_id=item.item_id,
                description=item.description,
                unit=item.unit,
                quantity=quantity,
                unit_cost=item.unit_cost,
                total_cost=quantity * item.unit_cost,
                source_type="assembly",
                source_id=assembly.assembly_id,
            )
        )
    return lines


def _section_quantity(section: TakeoffSection, page_lookup: dict[str, Page]) -> tuple[float, str]:
    total = 0.0
    unit = ""
    for measurement in section.measurements:
        quantity = measurement.quantity
        measurement_unit = measurement.unit
        if quantity is None or measurement_unit is None:
            page = page_lookup.get(measurement.page_id or "")
            result = calculate_measurement(section.kind, measurement.points, page)
            quantity = result.quantity
            measurement_unit = result.unit
        total += quantity
        unit = measurement_unit
    return total, unit or _default_unit_for_section(section)


def _default_unit_for_section(section: TakeoffSection) -> str:
    if section.kind.value == "area":
        return "SF"
    if section.kind.value == "count":
        return "EA"
    return "LF"


def _unit_info(unit: str) -> tuple[str, float]:
    normalized = unit.strip().upper()
    if normalized not in _UNIT_ALIASES:
        msg = f"Unsupported estimating unit: {unit}"
        raise UnitConversionError(msg)
    return _UNIT_ALIASES[normalized]
