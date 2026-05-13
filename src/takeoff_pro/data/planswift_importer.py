"""Importer for legacy Data.xml job folders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from takeoff_pro.data.models import (
    Autolist,
    Job,
    LegacyProperty,
    Measurement,
    MeasurementKind,
    Page,
    Point,
    TakeoffSection,
)

LOGGER = logging.getLogger(__name__)

_PARENT_KIND_BY_CLASS = {
    "Area": MeasurementKind.AREA,
    "Count": MeasurementKind.COUNT,
    "Segment": MeasurementKind.LENGTH,
}
_MEASUREMENT_KIND_BY_CLASS = {
    "Area Section": MeasurementKind.AREA,
    "Count Section": MeasurementKind.COUNT,
    "Segment Section": MeasurementKind.LENGTH,
}


class LegacyImportError(RuntimeError):
    """Raised when a legacy job folder cannot be imported."""


@dataclass(frozen=True)
class _LegacyItem:
    item_class: str
    name: str
    guid: str | None
    xml_path: Path
    folder_path: Path
    properties: dict[str, LegacyProperty]


def import_job(job_folder: str | Path) -> Job:
    """Import a legacy Data.xml job folder into validated models."""
    root_path = Path(job_folder).expanduser().resolve()
    if not root_path.exists():
        msg = f"Job folder does not exist: {root_path}"
        raise LegacyImportError(msg)
    if not root_path.is_dir():
        msg = f"Job path is not a folder: {root_path}"
        raise LegacyImportError(msg)

    root_item = _read_item(root_path) if (root_path / "Data.xml").exists() else None
    root_properties = root_item.properties if root_item is not None else {}
    job_id = _item_id(root_item, fallback=root_path.name)
    job_name = _property_value(root_properties, "Name") or root_path.name

    return Job(
        id=job_id,
        name=job_name,
        measurement_system=_property_value(root_properties, "Measurement Type"),
        description=_empty_to_none(_property_value(root_properties, "Description")),
        source_root=root_path,
        pages=_load_pages(root_path),
        takeoff_sections=_load_takeoff_sections(root_path),
        autolists=_load_autolists(root_path),
        raw_properties=root_properties,
    )


def import_jobs(job_folders: list[str | Path]) -> list[Job]:
    """Import multiple legacy job folders."""
    return [import_job(job_folder) for job_folder in job_folders]


def _load_pages(job_root: Path) -> list[Page]:
    pages_root = job_root / "Pages"
    if not pages_root.exists():
        return []

    pages: list[Page] = []
    for item in _iter_item_dirs(pages_root):
        if item.item_class != "Page":
            continue
        image_guid = _property_guid(item.properties, "Image")
        pages.append(
            Page(
                id=_item_id(item, fallback=item.folder_path.name),
                name=_property_value(item.properties, "Name") or item.name,
                order_index=_property_int(item.properties, "OrderIndex"),
                image_guid=image_guid,
                image_path=_find_image_path(item.folder_path, image_guid),
                scale_x=_property_float(item.properties, "ScaleX"),
                scale_y=_property_float(item.properties, "ScaleY"),
                scale_units=_property_value(item.properties, "Scale Units"),
                measurement_type=_property_value(item.properties, "MeasurementType")
                or _property_value(item.properties, "Measurement Type"),
                source_xml_path=item.xml_path,
                raw_properties=item.properties,
            )
        )
    return sorted(
        pages, key=lambda page: (page.order_index is None, page.order_index or 0, page.name)
    )


def _load_takeoff_sections(job_root: Path) -> list[TakeoffSection]:
    takeoff_root = job_root / "Takeoff"
    if not takeoff_root.exists():
        return []

    sections: list[TakeoffSection] = []
    for item in _iter_item_dirs(takeoff_root):
        kind = _PARENT_KIND_BY_CLASS.get(item.item_class)
        if kind is None:
            continue

        measurements = _load_measurements(item.folder_path)
        sections.append(
            TakeoffSection(
                id=_item_id(item, fallback=item.folder_path.name),
                name=_property_value(item.properties, "Name") or item.name,
                kind=kind,
                description=_empty_to_none(_property_value(item.properties, "Description")),
                item_number=_empty_to_none(_property_value(item.properties, "Item #")),
                order_index=_property_int(item.properties, "OrderIndex"),
                scale_units=_property_value(item.properties, "Scale Units"),
                source_xml_path=item.xml_path,
                measurements=measurements,
                raw_properties=item.properties,
            )
        )

    return sorted(
        sections,
        key=lambda section: (section.order_index is None, section.order_index or 0, section.name),
    )


def _load_measurements(section_root: Path) -> list[Measurement]:
    measurements: list[Measurement] = []
    for item in _iter_item_dirs(section_root):
        kind = _MEASUREMENT_KIND_BY_CLASS.get(item.item_class)
        if kind is None:
            continue

        measurements.append(
            Measurement(
                id=_item_id(item, fallback=item.folder_path.name),
                name=_property_value(item.properties, "Name") or item.name,
                kind=kind,
                page_id=_property_value(item.properties, "PageGUID"),
                order_index=_property_int(item.properties, "OrderIndex"),
                z_order=_property_int(item.properties, "ZOrder"),
                visible=_property_bool(item.properties, "Visible", default=True),
                points=_parse_digitizer_points(
                    _property_value(item.properties, "DigitizerData"),
                    source_path=item.xml_path,
                ),
                source_xml_path=item.xml_path,
                raw_properties=item.properties,
            )
        )

    return sorted(
        measurements,
        key=lambda measurement: (
            measurement.order_index is None,
            measurement.order_index or 0,
            measurement.name,
            measurement.id,
        ),
    )


def _load_autolists(job_root: Path) -> list[Autolist]:
    autolists_root = job_root / "AutoLists"
    if not autolists_root.exists():
        return []

    autolists: list[Autolist] = []
    for item in _iter_item_dirs(autolists_root):
        values = [
            child.name
            for child in _iter_item_dirs(item.folder_path)
            if child.xml_path != item.xml_path and child.name
        ]
        autolists.append(
            Autolist(
                id=_item_id(item, fallback=item.folder_path.name),
                name=_property_value(item.properties, "Name") or item.name,
                values=values,
                source_xml_path=item.xml_path,
                raw_properties=item.properties,
            )
        )
    return autolists


def _iter_item_dirs(root_path: Path) -> list[_LegacyItem]:
    items: list[_LegacyItem] = []
    for xml_path in sorted(
        root_path.rglob("Data.xml"), key=lambda path: path.relative_to(root_path).parts
    ):
        try:
            items.append(_read_item(xml_path.parent))
        except LegacyImportError:
            LOGGER.warning("Skipping unreadable legacy XML item at %s", xml_path, exc_info=True)
    return items


def _read_item(folder_path: Path) -> _LegacyItem:
    xml_path = folder_path / "Data.xml"
    if not xml_path.exists():
        msg = f"Missing Data.xml in {folder_path}"
        raise LegacyImportError(msg)

    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    try:
        document = etree.parse(str(xml_path), parser)
    except OSError as exc:
        msg = f"Could not read XML file: {xml_path}"
        raise LegacyImportError(msg) from exc
    except etree.XMLSyntaxError as exc:
        msg = f"Could not parse XML file: {xml_path}"
        raise LegacyImportError(msg) from exc

    root = document.getroot()
    if root.tag != "Item":
        msg = f"Unsupported Data.xml root element {root.tag!r} in {xml_path}"
        raise LegacyImportError(msg)

    properties = _read_properties(root)
    item_class = root.get("Class") or _property_value(properties, "Type") or "Item"
    return _LegacyItem(
        item_class=item_class,
        name=root.get("Name") or _property_value(properties, "Name") or folder_path.name,
        guid=root.get("GUID") or _property_value(properties, "GUID"),
        xml_path=xml_path,
        folder_path=folder_path,
        properties=properties,
    )


def _read_properties(root: etree._Element) -> dict[str, LegacyProperty]:
    properties: dict[str, LegacyProperty] = {}
    properties_element = root.find("Properties")
    if properties_element is None:
        return properties

    for property_element in properties_element.iterfind("Property"):
        name = property_element.get("Name")
        if not name:
            continue
        attributes = {
            str(key): str(value)
            for key, value in property_element.attrib.items()
            if key not in {"Name", "Class", "GUID"}
        }
        properties[name] = LegacyProperty(
            name=name,
            property_class=property_element.get("Class"),
            value=_empty_to_none(property_element.text),
            guid=property_element.get("GUID"),
            attributes=attributes,
        )
    return properties


def _parse_digitizer_points(raw_xml: str | None, *, source_path: Path) -> list[Point]:
    if raw_xml is None or not raw_xml.strip():
        return []

    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    try:
        points_root = etree.fromstring(raw_xml.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError:
        LOGGER.warning("Could not parse digitizer data in %s", source_path, exc_info=True)
        return []

    points: list[Point] = []
    for point_element in points_root.iterfind("Point"):
        x_value = point_element.get("X")
        y_value = point_element.get("Y")
        if x_value is None or y_value is None:
            LOGGER.warning("Skipping digitizer point without X/Y in %s", source_path)
            continue
        try:
            points.append(
                Point(
                    x=float(x_value),
                    y=float(y_value),
                    point_type=point_element.get("PointType"),
                )
            )
        except ValueError:
            LOGGER.warning(
                "Skipping digitizer point with invalid X/Y in %s", source_path, exc_info=True
            )
    return points


def _find_image_path(page_folder: Path, image_guid: str | None) -> Path | None:
    if image_guid is None:
        return None
    for extension in (".tiff", ".tif", ".TIFF", ".TIF"):
        candidate = page_folder / f"{image_guid}{extension}"
        if candidate.exists():
            return candidate
    return None


def _item_id(item: _LegacyItem | None, *, fallback: str) -> str:
    if item is not None and item.guid:
        return item.guid
    return fallback


def _property_value(properties: dict[str, LegacyProperty], name: str) -> str | None:
    property_value = properties.get(name)
    if property_value is None:
        return None
    return property_value.value


def _property_guid(properties: dict[str, LegacyProperty], name: str) -> str | None:
    property_value = properties.get(name)
    if property_value is None:
        return None
    return property_value.guid


def _property_int(properties: dict[str, LegacyProperty], name: str) -> int | None:
    value = _property_value(properties, name)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _property_float(properties: dict[str, LegacyProperty], name: str) -> float | None:
    value = _property_value(properties, name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _property_bool(
    properties: dict[str, LegacyProperty],
    name: str,
    *,
    default: bool,
) -> bool:
    value = _property_value(properties, name)
    if value is None:
        return default
    return value.strip().casefold() == "true"


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


__all__ = ["LegacyImportError", "import_job", "import_jobs"]
