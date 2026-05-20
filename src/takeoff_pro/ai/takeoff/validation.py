"""Rule-based validation helpers for painting takeoff output."""

from __future__ import annotations

from dataclasses import dataclass

from takeoff_pro.data.models import AiTakeoffPageResult


@dataclass(frozen=True)
class TakeoffValidationFlag:
    """A validation flag emitted for estimator review."""

    severity: str
    message: str
    page_id: str | None = None
    room_id: str | None = None


def validate_takeoff_pages(pages: list[AiTakeoffPageResult]) -> list[TakeoffValidationFlag]:
    """Return lightweight estimator QA flags for normalized takeoff pages."""
    flags: list[TakeoffValidationFlag] = []
    for page in pages:
        for room in page.rooms:
            if room.confidence < 60:
                flags.append(
                    TakeoffValidationFlag(
                        severity="warning",
                        message=f"Low confidence room: {room.name}.",
                        page_id=page.page_id,
                        room_id=room.id,
                    )
                )
            if room.floor_area_sf and room.wall_sf:
                ratio = room.wall_sf / room.floor_area_sf
                if ratio < 1.0 or ratio > 8.0:
                    flags.append(
                        TakeoffValidationFlag(
                            severity="warning",
                            message=f"Wall SF looks unusual vs floor area for {room.name}.",
                            page_id=page.page_id,
                            room_id=room.id,
                        )
                    )
            if room.perimeter_ft is None:
                message = (
                    f"Missing perimeter for {room.name}; "
                    "wall and trim quantities may be incomplete."
                )
                flags.append(
                    TakeoffValidationFlag(
                        severity="info",
                        message=message,
                        page_id=page.page_id,
                        room_id=room.id,
                    )
                )
    return flags
