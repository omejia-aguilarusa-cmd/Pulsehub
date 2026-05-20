"""Normalize and sanitize AI painting takeoff responses."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, TypeVar
from uuid import uuid4

from takeoff_pro.ai.takeoff.formulas import calculate_painting_quantities
from takeoff_pro.data.models import (
    AiElement,
    AiElementType,
    AiRoom,
    AiRoomType,
    AiTakeoffPageResult,
    AiTakeoffTotals,
)

EnumT = TypeVar("EnumT", bound=StrEnum)


class AiTakeoffNormalizationError(RuntimeError):
    """Raised when an AI response cannot be normalized."""


def normalize_ai_takeoff_response(
    raw_response: str | dict[str, Any],
    *,
    project_id: str,
    page_ids: list[str],
    ceiling_height_ft: float = 9.0,
    include_doors: bool = True,
    include_windows: bool = True,
    include_trim: bool = True,
) -> tuple[list[AiTakeoffPageResult], AiTakeoffTotals, float, list[str]]:
    """Normalize provider JSON into validated Takeoff Pro models."""
    del project_id
    data = _load_response(raw_response)
    valid_page_ids = set(page_ids)
    warnings = [str(item) for item in _as_list(data.get("warnings"))]
    rooms_by_page: dict[str, list[AiRoom]] = {page_id: [] for page_id in page_ids}
    elements_by_page: dict[str, list[AiElement]] = {page_id: [] for page_id in page_ids}

    for row in _as_list(data.get("rooms")):
        if not isinstance(row, dict):
            continue
        page_id = str(row.get("pageId") or row.get("page_id") or "")
        if page_id not in valid_page_ids:
            warnings.append(f"Skipped room with unknown pageId {page_id!r}.")
            continue
        door_count = _safe_int(row.get("doorCount") or row.get("door_count"), 0)
        window_count = _safe_int(row.get("windowCount") or row.get("window_count"), 0)
        floor_area_sf = _safe_optional_float(row.get("floorAreaSf") or row.get("floor_area_sf"))
        perimeter_ft = _safe_optional_float(row.get("perimeterFt") or row.get("perimeter_ft"))
        computed = calculate_painting_quantities(
            floor_area_sf=floor_area_sf,
            perimeter_ft=perimeter_ft,
            door_count=door_count,
            window_count=window_count,
            ceiling_height_ft=ceiling_height_ft,
            include_doors=include_doors,
            include_windows=include_windows,
            include_trim=include_trim,
        )
        room = AiRoom(
            id=str(row.get("id") or uuid4()),
            name=str(row.get("name") or "Unknown room"),
            type=_enum_value(AiRoomType, row.get("type"), AiRoomType.UNKNOWN),
            page_id=page_id,
            location_description=str(
                row.get("locationDescription") or row.get("location_description") or ""
            ),
            confidence=_confidence(row.get("confidence")),
            floor_area_sf=floor_area_sf,
            perimeter_ft=perimeter_ft,
            wall_sf=_safe_optional_float(row.get("wallSf") or row.get("wall_sf"))
            or computed.wall_sf,
            ceiling_sf=_safe_optional_float(row.get("ceilingSf") or row.get("ceiling_sf"))
            or computed.ceiling_sf,
            door_count=door_count,
            window_count=window_count,
            trim_lf=_safe_optional_float(row.get("trimLf") or row.get("trim_lf"))
            or computed.total_trim_lf,
            assumptions=[str(item) for item in _as_list(row.get("assumptions"))],
        )
        rooms_by_page[page_id].append(room)

    for row in _as_list(data.get("elements")):
        if not isinstance(row, dict):
            continue
        page_id = str(row.get("pageId") or row.get("page_id") or "")
        if page_id not in valid_page_ids:
            warnings.append(f"Skipped element with unknown pageId {page_id!r}.")
            continue
        elements_by_page[page_id].append(
            AiElement(
                type=_enum_value(AiElementType, row.get("type"), AiElementType.UNKNOWN),
                count=_safe_int(row.get("count"), 0),
                page_id=page_id,
                location_description=str(
                    row.get("locationDescription") or row.get("location_description") or ""
                ),
                confidence=_confidence(row.get("confidence")),
            )
        )

    pages = [
        AiTakeoffPageResult(
            page_id=page_id,
            rooms=rooms_by_page[page_id],
            elements=elements_by_page[page_id],
            warnings=warnings if index == 0 else [],
        )
        for index, page_id in enumerate(page_ids)
    ]
    totals = _calculate_totals(pages)
    confidence_score = _confidence(data.get("confidenceScore") or data.get("confidence_score"))
    if confidence_score == 0 and pages:
        room_confidences = [room.confidence for page in pages for room in page.rooms]
        element_confidences = [element.confidence for page in pages for element in page.elements]
        values = room_confidences + element_confidences
        confidence_score = sum(values) / len(values) if values else 0.0
    return pages, totals, confidence_score, warnings


def _load_response(raw_response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return raw_response
    try:
        value = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        msg = "AI response was not valid JSON."
        raise AiTakeoffNormalizationError(msg) from exc
    if not isinstance(value, dict):
        msg = "AI response must be a JSON object."
        raise AiTakeoffNormalizationError(msg)
    return value


def _calculate_totals(pages: list[AiTakeoffPageResult]) -> AiTakeoffTotals:
    rooms = [room for page in pages for room in page.rooms]
    return AiTakeoffTotals(
        floor_area_sf=sum(room.floor_area_sf or 0.0 for room in rooms),
        wall_sf=sum(room.wall_sf or 0.0 for room in rooms),
        ceiling_sf=sum(room.ceiling_sf or 0.0 for room in rooms),
        door_count=sum(room.door_count for room in rooms),
        window_count=sum(room.window_count for room in rooms),
        trim_lf=sum(room.trim_lf or 0.0 for room in rooms),
    )


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _safe_optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _safe_int(value: object, fallback: int) -> int:
    try:
        return max(0, int(float(str(value))))
    except (TypeError, ValueError):
        return fallback


def _confidence(value: object) -> float:
    try:
        numeric = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 1:
        numeric *= 100
    return max(0.0, min(100.0, numeric))


def _enum_value(enum_type: type[EnumT], value: object, fallback: EnumT) -> EnumT:
    try:
        return enum_type(str(value))
    except ValueError:
        return fallback
