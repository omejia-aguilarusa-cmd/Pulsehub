"""
Pricing extractor — pulls client-facing drywall and paint prices from documents.

CRITICAL RULES:
1. Only client-facing prices are stored as confirmed benchmarks.
2. Supplier/material quotes must NOT be used as client prices.
3. Labor-only rates must be clearly distinguished from turnkey prices.
4. If pricing type is ambiguous, return pricing_type="unknown".
5. Interior and exterior paint must be separated if possible.
6. If they cannot be separated, flag paint_is_blended=True.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedPricing:
    """Pricing data extracted from a document."""

    # Core prices
    drywall_price: Optional[float] = None
    paint_price: Optional[float] = None
    total_price: Optional[float] = None

    # Labor-only rates
    drywall_labor_per_sheet: Optional[float] = None   # e.g. $36/sheet
    drywall_labor_per_sf: Optional[float] = None      # e.g. $1.20/SF

    # Pricing type
    pricing_type: str = "unknown"   # "turnkey", "labor_only", "material_only"

    # Scope flags
    paint_is_blended: bool = False    # True = interior + exterior not separated
    paint_includes_exterior: bool = False
    paint_includes_corridors: bool = False
    paint_includes_amenities: bool = False

    # Evidence
    source_snippet: str = ""
    confidence: str = "low"  # "high", "medium", "low"
    warnings: list[str] = field(default_factory=list)


# ── Compiled patterns ─────────────────────────────────────────────────────────

# Dollar amount (broad)
_P_DOLLAR = re.compile(r"\$([\d,]+(?:\.\d{2})?)")

# Grand total
_P_GRAND_TOTAL = [
    re.compile(r"grand\s+total\s*(?:\(USD\))?[:\s]+\$?([\d,]+(?:\.\d{2})?)", re.IGNORECASE),
    re.compile(r"total\s+(?:price|amount|cost)[:\s]+\$?([\d,]+(?:\.\d{2})?)", re.IGNORECASE),
    re.compile(r"(?:bid|contract)\s+(?:total|amount)[:\s]+\$?([\d,]+(?:\.\d{2})?)", re.IGNORECASE),
]

# Labor per sheet
_P_LABOR_SHEET = re.compile(
    r"\$?(\d+(?:\.\d{2})?)\s*(?:per|/)\s*sheet\b",
    re.IGNORECASE,
)
_P_LABOR_SF = re.compile(
    r"\$?(\d+(?:\.\d{2})?)\s*(?:per|/)\s*(?:SF|sq\.?\s*ft\.?)\b",
    re.IGNORECASE,
)

# Pricing type indicators
_TURNKEY_PHRASES = [
    "labor and material", "labour and material", "labor & material",
    "l&m", "turnkey", "installed", "complete installation",
    "including material", "incl. material", "all-in",
    "supply and install", "supply & install",
]
_LABOR_ONLY_PHRASES = [
    "labor only", "labour only", "installation only",
    "no material", "materials by owner", "owner-furnished",
    "labor-only", "l/o",
]
_MATERIAL_ONLY_PHRASES = [
    "material only", "material-only", "supply only",
    "owner-installed", "contractor to install",
]


def _clean(s: str) -> float:
    return float(s.replace(",", "").strip())


def _context(text: str, match_start: int, match_end: int, window: int = 120) -> str:
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    return text[start:end]


def _detect_pricing_type(text: str) -> str:
    t = text.lower()
    if any(p in t for p in _TURNKEY_PHRASES):
        return "turnkey"
    if any(p in t for p in _LABOR_ONLY_PHRASES):
        return "labor_only"
    if any(p in t for p in _MATERIAL_ONLY_PHRASES):
        return "material_only"
    return "unknown"


def extract_pricing(text: str) -> ExtractedPricing:
    """
    Extract client-facing pricing from document text.

    Strategy:
    1. Scan all dollar amounts with surrounding context.
    2. Classify each amount as drywall, paint, or total based on context.
    3. If context contains "supplier", "material cost", or "quote", mark as
       supplier price (do NOT assign to drywall/paint client price).
    4. Detect pricing type (turnkey vs labor-only).
    """
    ep = ExtractedPricing()
    warnings: list[str] = []

    text_lower = text.lower()

    # ── Pricing type ──────────────────────────────────────────────────────────
    ep.pricing_type = _detect_pricing_type(text)

    # ── Grand total ───────────────────────────────────────────────────────────
    for p in _P_GRAND_TOTAL:
        m = p.search(text)
        if m:
            try:
                val = _clean(m.group(1))
                if val >= 1_000:
                    ep.total_price = val
                    break
            except ValueError:
                pass

    # ── Find all dollar amounts with context ──────────────────────────────────
    dw_candidates: list[float] = []
    paint_candidates: list[float] = []
    supplier_amounts: list[float] = []

    # Pass 1: line-level extraction (highest confidence)
    # Scan each line of text for a trade keyword + dollar amount on the same line.
    for line in text.splitlines():
        line_lower = line.lower()
        m = _P_DOLLAR.search(line)
        if not m:
            continue
        try:
            val = _clean(m.group(1))
        except ValueError:
            continue
        if val < 1_000:
            continue
        # Skip grand total line
        if any(k in line_lower for k in ["grand total", "total price", "total amount"]):
            continue

        is_supplier_line = any(
            k in line_lower for k in [
                "supplier", "material cost", "quote from", "distributor",
                "price per unit", "list price", "net price", "wholesale",
                "purchase order", "vendor",
            ]
        )
        if is_supplier_line:
            supplier_amounts.append(val)
            continue

        line_is_drywall = any(
            k in line_lower for k in [
                "drywall", "gypsum", "gyp board", "sheetrock", "hanging",
                "gyp ", "dw work",
            ]
        )
        line_is_paint = any(
            k in line_lower for k in [
                "paint work", "painting", "coating",
            ]
        )

        if line_is_drywall and not line_is_paint:
            dw_candidates.append(val)
        elif line_is_paint and not line_is_drywall:
            paint_candidates.append(val)

    # Pass 2: wider context scan for amounts not caught by line-level pass
    for m in _P_DOLLAR.finditer(text):
        try:
            val = _clean(m.group(1))
        except ValueError:
            continue
        if val < 1_000:   # skip trivial amounts ($36/sheet handled separately)
            continue
        if val in dw_candidates or val in paint_candidates:
            continue  # Already captured in pass 1

        ctx = _context(text, m.start(), m.end()).lower()

        # Flag supplier/material-cost context — do not use as client price
        is_supplier = any(
            k in ctx for k in [
                "supplier", "material cost", "quote from", "distributor",
                "price per unit", "list price", "net price", "wholesale",
                "purchase order", "vendor",
            ]
        )
        if is_supplier:
            supplier_amounts.append(val)
            warnings.append(
                f"${val:,.0f} appears to be a supplier/material cost — excluded from client pricing."
            )
            continue

        # Drywall context
        is_drywall = any(
            k in ctx for k in [
                "drywall", "gypsum", "gyp board", "sheetrock", "hanging",
                "board", "mud", "tape", "dw work",
            ]
        )

        # Paint context
        is_paint = any(
            k in ctx for k in [
                "paint work", "painting work", "coating",
            ]
        )

        if is_drywall and not is_paint:
            dw_candidates.append(val)
        elif is_paint and not is_drywall:
            paint_candidates.append(val)
        elif is_drywall and is_paint:
            # Ambiguous — could be a combined line
            if ep.total_price and abs(val - ep.total_price) / ep.total_price < 0.02:
                pass  # It's the grand total, skip
            else:
                warnings.append(
                    f"${val:,.0f} appears in context with both drywall and paint keywords — "
                    "classified as total; verify scope split."
                )

    # Pick the largest plausible candidate for each trade
    valid_dw = [v for v in dw_candidates if v >= 10_000]
    valid_paint = [v for v in paint_candidates if v >= 10_000]

    if valid_dw:
        ep.drywall_price = max(valid_dw)
    if valid_paint:
        ep.paint_price = max(valid_paint)

    # ── Labor-only rates ──────────────────────────────────────────────────────
    m = _P_LABOR_SHEET.search(text)
    if m:
        try:
            val = _clean(m.group(1))
            if 10 <= val <= 200:   # plausible $/sheet range
                ep.drywall_labor_per_sheet = val
        except ValueError:
            pass

    m = _P_LABOR_SF.search(text)
    if m:
        try:
            val = _clean(m.group(1))
            if 0.10 <= val <= 10.0:  # plausible $/SF range
                ep.drywall_labor_per_sf = val
        except ValueError:
            pass

    # ── Scope flags ───────────────────────────────────────────────────────────
    ep.paint_includes_exterior = any(
        k in text_lower for k in [
            "exterior", "siding", "hardie", "fiber cement", "stucco",
            "pressure wash", "exterior coat", "fascia", "soffit paint",
        ]
    )
    ep.paint_includes_corridors = any(
        k in text_lower for k in ["corridor", "hallway", "common area", "mechanical closet"]
    )
    ep.paint_includes_amenities = any(
        k in text_lower for k in ["clubhouse", "amenity", "fitness", "leasing", "pool"]
    )

    # Interior + exterior blended if paint_price found and no separation visible
    if ep.paint_price and ep.paint_includes_exterior:
        interior_keyword = any(
            k in text_lower for k in ["interior paint", "interior only", "interior "]
        )
        exterior_keyword = any(
            k in text_lower for k in ["exterior paint", "exterior only", "exterior "]
        )
        if interior_keyword and exterior_keyword:
            # Check if they're in separate line items
            interior_line = re.search(r"interior\s+paint[^$\n]{0,60}\$[\d,]+", text, re.IGNORECASE)
            exterior_line = re.search(r"exterior\s+paint[^$\n]{0,60}\$[\d,]+", text, re.IGNORECASE)
            ep.paint_is_blended = not (interior_line and exterior_line)
        else:
            ep.paint_is_blended = True
        if ep.paint_is_blended:
            warnings.append(
                "Paint price appears to include exterior scope. "
                "Interior-only price cannot be confirmed. "
                "Do not use as interior-only benchmark."
            )

    # ── Sanity cross-check ────────────────────────────────────────────────────
    if ep.total_price and ep.drywall_price and ep.paint_price:
        implied = ep.drywall_price + ep.paint_price
        if abs(implied - ep.total_price) / ep.total_price > 0.05:
            warnings.append(
                f"Drywall (${ep.drywall_price:,.0f}) + Paint (${ep.paint_price:,.0f}) "
                f"= ${implied:,.0f} does not match Grand Total ${ep.total_price:,.0f}. "
                "Verify line items."
            )

    # ── Confidence ────────────────────────────────────────────────────────────
    confirmed = sum(
        1 for v in [ep.drywall_price, ep.paint_price, ep.total_price] if v is not None
    )
    ep.confidence = "high" if confirmed >= 2 else "medium" if confirmed == 1 else "low"
    ep.warnings = warnings

    # Source snippet
    ep.source_snippet = text[:400].replace("\n", " ")

    return ep
