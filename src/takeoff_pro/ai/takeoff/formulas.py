"""Painting-specific quantity formulas."""

from dataclasses import dataclass

DEFAULT_CEILING_HEIGHT_FT = 9.0
DOOR_DEDUCTION_SF = 21.0
WINDOW_DEDUCTION_SF = 15.0
DOOR_TRIM_LF = 17.0
WINDOW_TRIM_LF = 12.0


@dataclass(frozen=True)
class PaintingQuantities:
    """Computed painting quantities for a room."""

    wall_sf: float | None
    ceiling_sf: float | None
    baseboard_lf: float | None
    door_trim_lf: float
    window_trim_lf: float
    total_trim_lf: float | None


def calculate_painting_quantities(
    *,
    floor_area_sf: float | None,
    perimeter_ft: float | None,
    door_count: int,
    window_count: int,
    ceiling_height_ft: float = DEFAULT_CEILING_HEIGHT_FT,
    include_doors: bool = True,
    include_windows: bool = True,
    include_trim: bool = True,
) -> PaintingQuantities:
    """Return painting quantities from room geometry and estimator options."""
    safe_doors = max(0, int(door_count)) if include_doors else 0
    safe_windows = max(0, int(window_count)) if include_windows else 0
    safe_height = ceiling_height_ft if ceiling_height_ft > 0 else DEFAULT_CEILING_HEIGHT_FT

    wall_sf: float | None = None
    if perimeter_ft is not None:
        gross_wall_sf = max(0.0, float(perimeter_ft)) * safe_height
        wall_sf = max(
            0.0,
            gross_wall_sf - safe_doors * DOOR_DEDUCTION_SF - safe_windows * WINDOW_DEDUCTION_SF,
        )

    ceiling_sf = max(0.0, float(floor_area_sf)) if floor_area_sf is not None else None
    baseboard_lf = max(0.0, float(perimeter_ft)) if perimeter_ft is not None else None
    door_trim_lf = safe_doors * DOOR_TRIM_LF if include_trim else 0.0
    window_trim_lf = safe_windows * WINDOW_TRIM_LF if include_trim else 0.0
    total_trim_lf = None
    if include_trim and baseboard_lf is not None:
        total_trim_lf = baseboard_lf + door_trim_lf + window_trim_lf

    return PaintingQuantities(
        wall_sf=wall_sf,
        ceiling_sf=ceiling_sf,
        baseboard_lf=baseboard_lf,
        door_trim_lf=door_trim_lf,
        window_trim_lf=window_trim_lf,
        total_trim_lf=total_trim_lf,
    )
