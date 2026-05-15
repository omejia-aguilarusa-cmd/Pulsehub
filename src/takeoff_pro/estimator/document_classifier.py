"""
Document classifier — determines the type and relevance of an uploaded file.

Priority order (highest to lowest evidence quality):
  signed_estimate > client_proposal > pricing_spreadsheet > takeoff_report >
  material_list > supplier_quote > drawing > finish_schedule > wall_type >
  scope_note > email > filename_only

Files classified as IGNORE are not analyzed further unless manually requested.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path


class DocumentType(StrEnum):
    ESTIMATE = "estimate"                    # Client-facing price document
    PROPOSAL = "proposal"                    # Draft or unsigned client document
    TAKEOFF_REPORT = "takeoff_report"        # Quantity takeoff spreadsheet/report
    PRICING_SPREADSHEET = "pricing_spreadsheet"  # Formulas + prices
    MATERIAL_LIST = "material_list"          # Material quantities only
    SUPPLIER_QUOTE = "supplier_quote"        # Vendor/distributor quote
    DRAWING = "drawing"                      # Architectural/structural drawing
    FINISH_SCHEDULE = "finish_schedule"      # Room finish / paint schedule
    WALL_TYPE_LEGEND = "wall_type_legend"    # Partition type legend
    SCOPE_DOCUMENT = "scope_document"        # SOW / scope narrative
    PAYROLL = "payroll"                      # Payroll / paystub — ignore
    FINANCIAL = "financial"                  # PnL / balance sheet — ignore
    LEGAL = "legal"                          # Waiver / contract — ignore
    UNRELATED = "unrelated"                  # Non-drywall, non-paint
    UNKNOWN = "unknown"                      # Cannot classify


class DocumentRelevance(StrEnum):
    RELEVANT = "relevant"       # Directly needed for analysis
    SUPPORTING = "supporting"   # Provides context or corroboration
    IGNORE = "ignore"           # Skip — unrelated or insufficient


# ── Keyword banks ─────────────────────────────────────────────────────────────

_ESTIMATE_STRONG = [
    "grand total", "estimate number", "estimate date", "valid until",
    "bill to", "invoice", "contract amount", "lump sum price",
]
_ESTIMATE_WEAK = [
    "estimate", "proposal", "bid", "quote", "price", "total cost",
    "scope of work", "complete", "labor and material",
]
_TAKEOFF_STRONG = [
    "takeoff", "bft", "board sf", "board count", "drywall takeoff",
    "paint takeoff", "quantity", "sq ft board", "sf board",
    "bft with waste", "bft before waste",
]
_TAKEOFF_WEAK = [
    "gypsum", "gyp board", "type x", "moisture resistant", "cbu",
    "shaft wall", "corner bead", "paint gallons", "gal",
]
_DRAWING_STRONG = [
    "floor plan", "elevation", "section detail", "drawing index",
    "sheet list", "copyright", "drawn by", "checked by",
    "scale:", "scale 1", "1/8\" = 1", "1/4\" = 1",
    "construction plans", "permit and construction",
]
_DRAWING_WEAK = [
    "foundation", "framing", "electrical", "hvac", "roof plan",
    "joist", "rafter", "structural",
]
_SUPPLIER_STRONG = [
    "sherwin williams", "usg corporation", "certainteed", "georgia-pacific",
    "national gypsum", "american gypsum", "gold bond", "proform",
    "distributor", "price per unit", "list price", "net price",
    "purchase order", "p.o. number",
]
_FINISH_STRONG = [
    "finish schedule", "room finish", "color schedule", "paint schedule",
    "interior finish", "material finish tag",
]
_WALL_TYPE_STRONG = [
    "partition type", "wall type legend", "assembly description",
    "ul design", "stud size", "assembly",
]
_SCOPE_STRONG = [
    "statement of work", "scope of work", "requirements",
    "contractor shall", "contractor must", "general contractor",
    "construction task",
]
_PAYROLL_STRONG = [
    "paystub", "payroll", "pay stub", "gross pay", "net pay",
    "hours worked", "earnings statement", "pay period",
    "federal tax", "state tax", "fica",
]
_FINANCIAL_STRONG = [
    "profit and loss", "balance sheet", "income statement",
    "cash flow", "revenue", "expenses", "net income",
]
_LEGAL_STRONG = [
    "conditional waiver", "unconditional waiver", "lien waiver",
    "certificate of insurance", "coi", "bill of sale",
    "agreement", "terms and conditions", "indemnification",
]


def _has_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _count_dollar_amounts(text: str) -> int:
    return len(re.findall(r"\$[\d,]+", text))


def classify_document(
    filename: str,
    text: str,
) -> tuple[DocumentType, DocumentRelevance, float]:
    """
    Classify a document by type and relevance.

    Returns:
        (DocumentType, DocumentRelevance, confidence_score 0.0-1.0)
    """
    fn = filename.lower()
    # Use first 8,000 chars of text for classification speed
    t = text[:8_000].lower()
    dollar_count = _count_dollar_amounts(text[:8_000])

    # ── IGNORE classes ─────────────────────────────────────────────────────────
    if _has_any(fn + t, _PAYROLL_STRONG):
        return DocumentType.PAYROLL, DocumentRelevance.IGNORE, 0.95

    if _has_any(t, _FINANCIAL_STRONG) and "takeoff" not in t:
        return DocumentType.FINANCIAL, DocumentRelevance.IGNORE, 0.90

    if _has_any(t, _LEGAL_STRONG) and dollar_count < 3:
        return DocumentType.LEGAL, DocumentRelevance.IGNORE, 0.85

    # ── Estimate / Proposal ────────────────────────────────────────────────────
    if dollar_count >= 2 and _has_any(t, _ESTIMATE_STRONG):
        # Check for drywall or paint context
        if _has_any(t, ["drywall", "paint", "gypsum", "coating", "hanging"]):
            return DocumentType.ESTIMATE, DocumentRelevance.RELEVANT, 0.95
        return DocumentType.PROPOSAL, DocumentRelevance.RELEVANT, 0.80

    if dollar_count >= 5 and _has_any(t, _ESTIMATE_WEAK):
        return DocumentType.PROPOSAL, DocumentRelevance.RELEVANT, 0.70

    # ── Takeoff report ──────────────────────────────────────────────────────────
    if _has_any(t, _TAKEOFF_STRONG):
        if _has_any(t, ["drywall", "paint", "board", "gypsum"]):
            return DocumentType.TAKEOFF_REPORT, DocumentRelevance.RELEVANT, 0.92

    # ── Pricing spreadsheet ────────────────────────────────────────────────────
    if fn.endswith((".xlsx", ".xls")) and dollar_count >= 3:
        if _has_any(t, ["drywall", "paint", "gypsum", "board sf", "bft"]):
            return DocumentType.PRICING_SPREADSHEET, DocumentRelevance.RELEVANT, 0.85
        return DocumentType.TAKEOFF_REPORT, DocumentRelevance.RELEVANT, 0.70

    # ── Material list ──────────────────────────────────────────────────────────
    if _has_any(t, ["material list", "bill of materials", "bom"]):
        return DocumentType.MATERIAL_LIST, DocumentRelevance.SUPPORTING, 0.80

    # ── Supplier quote ─────────────────────────────────────────────────────────
    if _has_any(t, _SUPPLIER_STRONG):
        return DocumentType.SUPPLIER_QUOTE, DocumentRelevance.SUPPORTING, 0.88

    # ── Drawing ────────────────────────────────────────────────────────────────
    if _has_any(t, _DRAWING_STRONG) and dollar_count < 3:
        return DocumentType.DRAWING, DocumentRelevance.RELEVANT, 0.85

    if _has_any(t, _DRAWING_WEAK) and len(t) > 500 and dollar_count < 3:
        return DocumentType.DRAWING, DocumentRelevance.RELEVANT, 0.65

    # ── Finish schedule ────────────────────────────────────────────────────────
    if _has_any(t, _FINISH_STRONG):
        return DocumentType.FINISH_SCHEDULE, DocumentRelevance.RELEVANT, 0.82

    # ── Wall type legend ───────────────────────────────────────────────────────
    if _has_any(t, _WALL_TYPE_STRONG):
        return DocumentType.WALL_TYPE_LEGEND, DocumentRelevance.RELEVANT, 0.80

    # ── Scope document ─────────────────────────────────────────────────────────
    if _has_any(t, _SCOPE_STRONG):
        return DocumentType.SCOPE_DOCUMENT, DocumentRelevance.SUPPORTING, 0.78

    # ── Unrelated / unknown ────────────────────────────────────────────────────
    if not _has_any(t, ["drywall", "paint", "gyp", "board", "coating", "plaster"]):
        return DocumentType.UNRELATED, DocumentRelevance.IGNORE, 0.60

    return DocumentType.UNKNOWN, DocumentRelevance.IGNORE, 0.10


def relevance_label(doc_type: DocumentType) -> DocumentRelevance:
    """Return the standard relevance label for a document type."""
    _MAP: dict[DocumentType, DocumentRelevance] = {
        DocumentType.ESTIMATE: DocumentRelevance.RELEVANT,
        DocumentType.PROPOSAL: DocumentRelevance.RELEVANT,
        DocumentType.TAKEOFF_REPORT: DocumentRelevance.RELEVANT,
        DocumentType.PRICING_SPREADSHEET: DocumentRelevance.RELEVANT,
        DocumentType.MATERIAL_LIST: DocumentRelevance.SUPPORTING,
        DocumentType.SUPPLIER_QUOTE: DocumentRelevance.SUPPORTING,
        DocumentType.DRAWING: DocumentRelevance.RELEVANT,
        DocumentType.FINISH_SCHEDULE: DocumentRelevance.RELEVANT,
        DocumentType.WALL_TYPE_LEGEND: DocumentRelevance.RELEVANT,
        DocumentType.SCOPE_DOCUMENT: DocumentRelevance.SUPPORTING,
        DocumentType.PAYROLL: DocumentRelevance.IGNORE,
        DocumentType.FINANCIAL: DocumentRelevance.IGNORE,
        DocumentType.LEGAL: DocumentRelevance.IGNORE,
        DocumentType.UNRELATED: DocumentRelevance.IGNORE,
        DocumentType.UNKNOWN: DocumentRelevance.IGNORE,
    }
    return _MAP.get(doc_type, DocumentRelevance.IGNORE)
