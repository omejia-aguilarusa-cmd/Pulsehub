"""
Quantity extractor — pulls drywall and paint quantities from document text.

Extraction priority:
1. Explicit labeled rows (e.g. "Total Drywall Board SF: 1,665,312")
2. Inline numeric patterns with context keywords
3. Planning-ratio projections (only when unit count and GSF are known)

Rules:
- Always prefer the largest plausible value for total board SF.
- Unit count must be in range 5–5,000 (construction sanity filter).
- GSF must be > 500 SF.
- Board SF must be > 100 SF.
- Gallons must be between 1 and 200,000.
- All extracted values are returned unmodified — waste is NOT re-applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedQuantities:
    """Raw quantities extracted from a document."""

    # Building program
    units: Optional[int] = None
    gsf: Optional[float] = None
    nrsf: Optional[float] = None
    avg_unit_nrsf: Optional[float] = None

    # Drywall board SF
    drywall_board_sf_total: Optional[float] = None    # may include waste
    drywall_board_sf_residential: Optional[float] = None
    drywall_board_sf_nonres: Optional[float] = None
    drywall_mr_sf: Optional[float] = None
    drywall_cbu_sf: Optional[float] = None
    drywall_shaft_wall_sf: Optional[float] = None
    drywall_board_count: Optional[int] = None

    # Paint
    paint_wall_sf: Optional[float] = None
    paint_ceiling_sf: Optional[float] = None
    paint_trim_sf: Optional[float] = None
    paint_door_sf: Optional[float] = None
    paint_gal_total: Optional[float] = None
    paint_gal_per_unit: Optional[float] = None

    # Scope flags inferred from text
    has_exterior_paint: bool = False
    has_corridors: bool = False
    has_amenities: bool = False

    # Extraction quality
    confidence: str = "low"   # "high", "medium", "low"
    source_patterns: list[str] = field(default_factory=list)


def _clean(s: str) -> float:
    """Parse a comma-formatted number string to float."""
    return float(s.replace(",", "").strip())


# ── Compiled patterns ─────────────────────────────────────────────────────────

# Unit count: "318 units", "304-unit", "318 apartments"
_P_UNITS = [
    re.compile(r"(\d{1,4})\s*[–\-]?\s*unit\b", re.IGNORECASE),
    re.compile(r"(\d{1,4})\s*(?:apartment|apt|dwelling|residence|condo|flat)s?\b", re.IGNORECASE),
    re.compile(r"(?:total|program|count)[:\s]+(\d{1,4})\s*units?\b", re.IGNORECASE),
    re.compile(r"unit\s+count[:\s]+(\d{1,4})\b", re.IGNORECASE),
]

# Gross SF: "382,392 SF", "GSF: 382,392"
_P_GSF = [
    re.compile(r"(?:gross|total|project)\s+(?:building\s+)?(?:SF|sq\.?\s*ft\.?)[:\s]+([\d,]+)", re.IGNORECASE),
    re.compile(r"(?:GSF|gross\s*SF)[:\s]+([\d,]+)", re.IGNORECASE),
    re.compile(r"([\d,]+)\s+(?:SF|sq\.?\s*ft\.?)\s+(?:total|gross|project)\b", re.IGNORECASE),
]

# NRSF: net rentable
_P_NRSF = [
    re.compile(r"(?:NRSF|net\s+rentable)[:\s]+([\d,]+)", re.IGNORECASE),
    re.compile(r"avg\s+unit\s+NRSF[:\s]+([\d,]+)", re.IGNORECASE),
]

# Total drywall board SF (labeled rows preferred)
_P_BOARD_SF_TOTAL = [
    re.compile(r"total\s+drywall\s+board\s+SF[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"total\s+board\s+SF[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(?:BFT|board\s+feet?|board\s+SF)\s+(?:total|with\s+waste)[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"([\d,]+(?:\.\d+)?)\s+SF\s+board\b", re.IGNORECASE),
    re.compile(r"drywall\s+board[:\s]+([\d,]+(?:\.\d+)?)\s+SF\b", re.IGNORECASE),
    re.compile(r"([\d,]+(?:\.\d+)?)\s+(?:BFT|board\s+feet?)\b", re.IGNORECASE),
]

# Residential standard board
_P_BOARD_SF_RES = [
    re.compile(r"residential\s+(?:std|standard|type\s+x)\s+gypsum[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"5/8\"\s+type\s+x\s+(?:std\s+)?gypsum[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# MR board
_P_BOARD_MR = [
    re.compile(r"MR\s+(?:board|gyp)[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"moisture[- ]resistant[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# CBU
_P_CBU = [
    re.compile(r"CBU[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"cement\s+backer[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# Shaft wall
_P_SHAFT = [
    re.compile(r"shaft\s+wall[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"shaftliner[^|]*\|\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# Paint wall SF
_P_PAINT_WALL = [
    re.compile(r"(?:wall|walls)\s+paint\s+(?:surface\s+)?SF[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"paint\s+(?:surface\s+)?SF\s*(?:per\s+coat)?[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# Paint ceiling SF
_P_PAINT_CEIL = [
    re.compile(r"ceiling\s+paint\s+(?:surface\s+)?SF[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
]

# Paint gallons
_P_PAINT_GAL = [
    re.compile(r"total\s+paint\s+(?:gallons?|gal)[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"paint\s+(?:gallons?|gal)\s*(?:all\s+products?)?[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:gallons?|gal)\b", re.IGNORECASE),
]

# Per-unit gallons
_P_GAL_PER_UNIT = [
    re.compile(r"(?:gallons?|gal)?\s*/\s*unit[:\s\|]+([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:gal|gallons?)\s*/\s*unit\b", re.IGNORECASE),
]


def _first_match(patterns: list[re.Pattern], text: str) -> Optional[float]:
    for p in patterns:
        m = p.search(text)
        if m:
            try:
                val = _clean(m.group(1))
                return val
            except (ValueError, IndexError):
                continue
    return None


def _all_matches(patterns: list[re.Pattern], text: str) -> list[float]:
    results: list[float] = []
    for p in patterns:
        for m in p.finditer(text):
            try:
                results.append(_clean(m.group(1)))
            except (ValueError, IndexError):
                continue
    return results


def extract_quantities(text: str) -> ExtractedQuantities:
    """
    Extract key quantity fields from document text.
    Returns an ExtractedQuantities dataclass with None for unconfirmed fields.
    """
    eq = ExtractedQuantities()
    sources: list[str] = []

    # ── Unit count ────────────────────────────────────────────────────────────
    for p in _P_UNITS:
        m = p.search(text)
        if m:
            try:
                val = int(m.group(1))
                if 5 <= val <= 5_000:
                    eq.units = val
                    sources.append(f"units={val}")
                    break
            except ValueError:
                pass

    # ── GSF ───────────────────────────────────────────────────────────────────
    gsf_candidates = _all_matches(_P_GSF, text)
    for c in sorted(gsf_candidates, reverse=True):
        if 500 < c < 50_000_000:
            eq.gsf = c
            sources.append(f"GSF={c:,.0f}")
            break

    # ── NRSF ──────────────────────────────────────────────────────────────────
    nrsf = _first_match(_P_NRSF, text)
    if nrsf and nrsf > 100:
        eq.nrsf = nrsf
        sources.append(f"NRSF={nrsf:,.0f}")

    # ── Drywall board SF total ─────────────────────────────────────────────────
    board_candidates = _all_matches(_P_BOARD_SF_TOTAL, text)
    valid_board = [c for c in board_candidates if 1_000 < c < 50_000_000]
    if valid_board:
        eq.drywall_board_sf_total = max(valid_board)
        sources.append(f"board_SF_total={eq.drywall_board_sf_total:,.0f}")

    # ── Detailed board types ───────────────────────────────────────────────────
    res_board = _first_match(_P_BOARD_SF_RES, text)
    if res_board and res_board > 100:
        eq.drywall_board_sf_residential = res_board

    mr_board = _first_match(_P_BOARD_MR, text)
    if mr_board and mr_board > 10:
        eq.drywall_mr_sf = mr_board

    cbu = _first_match(_P_CBU, text)
    if cbu and cbu > 0:
        eq.drywall_cbu_sf = cbu

    shaft = _first_match(_P_SHAFT, text)
    if shaft and shaft > 0:
        eq.drywall_shaft_wall_sf = shaft

    # ── Board count (explicit) ────────────────────────────────────────────────
    bc_match = re.search(
        r"board\s+count[:\s]+([\d,]+)", text, re.IGNORECASE
    )
    if bc_match:
        try:
            eq.drywall_board_count = int(bc_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # ── Paint wall SF ─────────────────────────────────────────────────────────
    wall_sf = _first_match(_P_PAINT_WALL, text)
    if wall_sf and wall_sf > 100:
        eq.paint_wall_sf = wall_sf

    # ── Paint ceiling SF ──────────────────────────────────────────────────────
    ceil_sf = _first_match(_P_PAINT_CEIL, text)
    if ceil_sf and ceil_sf > 100:
        eq.paint_ceiling_sf = ceil_sf

    # ── Paint gallons ─────────────────────────────────────────────────────────
    gal_candidates = _all_matches(_P_PAINT_GAL, text)
    valid_gal = [g for g in gal_candidates if 1 <= g <= 200_000]
    if valid_gal:
        # Prefer labeled "total paint gallons" over bare gallon counts
        labeled = _first_match(_P_PAINT_GAL[:2], text)  # first two are labeled patterns
        if labeled and 1 <= labeled <= 200_000:
            eq.paint_gal_total = labeled
        else:
            eq.paint_gal_total = max(valid_gal)
        sources.append(f"paint_gal={eq.paint_gal_total:,.1f}")

    # ── Per-unit gallons ──────────────────────────────────────────────────────
    gal_unit = _first_match(_P_GAL_PER_UNIT, text)
    if gal_unit and 5 <= gal_unit <= 200:
        eq.paint_gal_per_unit = gal_unit

    # ── Scope flags ───────────────────────────────────────────────────────────
    t_lower = text.lower()
    eq.has_exterior_paint = any(
        k in t_lower for k in ["exterior paint", "siding paint", "hardie", "fiber cement", "exterior coat"]
    )
    eq.has_corridors = any(k in t_lower for k in ["corridor", "hallway", "common area"])
    eq.has_amenities = any(k in t_lower for k in ["clubhouse", "amenity", "fitness", "leasing", "pool"])

    # ── Confidence ────────────────────────────────────────────────────────────
    confirmed_count = sum(
        1 for v in [eq.units, eq.drywall_board_sf_total, eq.paint_gal_total] if v is not None
    )
    eq.confidence = "high" if confirmed_count >= 2 else "medium" if confirmed_count >= 1 else "low"
    eq.source_patterns = sources

    return eq
