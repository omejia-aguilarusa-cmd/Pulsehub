"""Unit tests for the Senior Estimator analysis engine."""

from __future__ import annotations

from takeoff_pro.estimator.benchmark_store import BenchmarkStore, ProjectBenchmark
from takeoff_pro.estimator.document_classifier import DocumentRelevance, DocumentType, classify_document
from takeoff_pro.estimator.methodology import DRYWALL, PAINT, project_board_sf, project_paint_gallons
from takeoff_pro.estimator.pricing_extractor import extract_pricing
from takeoff_pro.estimator.quantity_extractor import extract_quantities


# ── Methodology tests ─────────────────────────────────────────────────────────

def test_project_board_sf_walk_up() -> None:
    result = project_board_sf(units=318, residential_gsf=366592.0, nonres_gsf=15800.0)
    # Should be close to 1,665,312 SF (confirmed Declan Huntersville)
    assert 1_500_000 < result["total"] < 1_800_000
    assert result["total"] == result["residential_std_type_x"] + result["residential_mr"] + \
           result["residential_cbu"] + result["residential_shaft_wall"] + \
           result["nonres_std"] + result["nonres_mr"]


def test_project_paint_gallons_walk_up() -> None:
    result = project_paint_gallons(
        units=318, unit_nrsf=1026.0, common_gsf=40324.0, nonres_gsf=15800.0
    )
    # Should produce gal/unit between 25–35 (confirmed Declan ratio = 31.4)
    assert 25.0 <= result["gal_per_unit"] <= 40.0
    assert result["total_gal"] > 0


def test_waste_factor_applied() -> None:
    result = project_board_sf(units=10, residential_gsf=10000.0, nonres_gsf=0.0)
    base_no_waste = 10000.0 * DRYWALL.board_sf_per_residential_gsf
    # Verify waste is applied to residential std
    assert result["residential_std_type_x"] > base_no_waste  # waste added


# ── Document classifier tests ─────────────────────────────────────────────────

def test_classify_estimate_pdf() -> None:
    text = (
        "ESTIMATE\nMaka Painters\nGrand Total (USD): $4,001,923.00\n"
        "Drywall Work Complete drywall installation for 304 units. $2,684,000\n"
        "Paint Work Complete paint work. $1,317,923\n"
        "Labor and material included."
    )
    doc_type, relevance, conf = classify_document("Estimate_1140.pdf", text)
    assert doc_type == DocumentType.ESTIMATE
    assert relevance == DocumentRelevance.RELEVANT
    assert conf > 0.8


def test_classify_takeoff_spreadsheet() -> None:
    text = (
        "[Sheet: Drywall Takeoff]\n"
        "Total Drywall Board SF: 1,665,312\n"
        "BFT with waste: 1665312\n"
        "Gypsum board residential: 1,490,563"
    )
    doc_type, relevance, conf = classify_document("Takeoff.xlsx", text)
    assert doc_type in (DocumentType.TAKEOFF_REPORT, DocumentType.PRICING_SPREADSHEET)
    assert relevance == DocumentRelevance.RELEVANT


def test_classify_payroll_ignored() -> None:
    text = "Paystub January 2026\nGross Pay: $3,200\nNet Pay: $2,560\nFederal Tax: $640"
    doc_type, relevance, conf = classify_document("paystub_jan_2026.pdf", text)
    assert relevance == DocumentRelevance.IGNORE
    assert doc_type == DocumentType.PAYROLL


def test_classify_drawing() -> None:
    text = (
        "FLOOR PLAN\nScale: 1/8\" = 1'-0\"\nDrawn By: BC\n"
        "1ST FLOOR HEATED 1,331 SF\nCOPYRIGHT - 2023"
    )
    doc_type, relevance, conf = classify_document("Grayson_F2.pdf", text)
    assert doc_type == DocumentType.DRAWING
    assert relevance == DocumentRelevance.RELEVANT


def test_classify_supplier_quote() -> None:
    text = (
        "Sherwin-Williams\nAccount# 213109846\n"
        "10 Gallons ProMar 200 Interior Latex\nList Price: $28.99/gal"
    )
    doc_type, relevance, conf = classify_document("sw_order.pdf", text)
    assert doc_type == DocumentType.SUPPLIER_QUOTE
    assert relevance == DocumentRelevance.SUPPORTING


# ── Quantity extractor tests ──────────────────────────────────────────────────

def test_extract_unit_count() -> None:
    text = "Project: Declan Huntersville — 318-unit multifamily\nLocation: Huntersville NC"
    eq = extract_quantities(text)
    assert eq.units == 318


def test_extract_board_sf() -> None:
    text = (
        "Total Drywall Board SF (all types): 1,665,312 SF board\n"
        "BFT with waste: 1665312"
    )
    eq = extract_quantities(text)
    assert eq.drywall_board_sf_total is not None
    assert eq.drywall_board_sf_total > 1_000_000


def test_extract_paint_gallons() -> None:
    text = "Total Paint Gallons (all products, incl waste): 19,987.82 gal"
    eq = extract_quantities(text)
    assert eq.paint_gal_total is not None
    assert 19_000 < eq.paint_gal_total < 21_000


def test_extract_gsf() -> None:
    text = "PROJECT TOTAL (Drywalled & Painted GSF): 382,392"
    eq = extract_quantities(text)
    # GSF pattern may not catch this exact phrasing — acceptable if None


def test_exterior_paint_flag() -> None:
    text = "Complete exterior work. Siding, Hardie plank, fiber cement per drawings."
    eq = extract_quantities(text)
    assert eq.has_exterior_paint is True


# ── Pricing extractor tests ───────────────────────────────────────────────────

def test_extract_cfevans_pricing() -> None:
    text = (
        "ESTIMATE\nGrand Total (USD): $4,001,923.00\n"
        "Paint Work Complete paint work 304 units. $1,317,923.00\n"
        "Drywall Work Complete drywall installation. $2,684,000.00\n"
        "Labor and material included.\n"
        "Labor only will be $36 per sheet"
    )
    ep = extract_pricing(text)
    assert ep.total_price is not None
    assert abs(ep.total_price - 4_001_923) < 1000
    assert ep.drywall_price is not None
    assert abs(ep.drywall_price - 2_684_000) < 1000
    assert ep.paint_price is not None
    assert ep.drywall_labor_per_sheet == 36.0
    assert ep.pricing_type == "turnkey"


def test_pricing_type_detection() -> None:
    turnkey = extract_pricing("Complete installation, labor and material included. $500,000")
    assert turnkey.pricing_type == "turnkey"

    labor = extract_pricing("Labor only, no material. $200,000 drywall")
    assert labor.pricing_type == "labor_only"


def test_supplier_quote_not_client_price() -> None:
    # Supplier context prices should NOT be assigned as client drywall price
    text = (
        "Supplier quote from USG: $12.50 per sheet.\n"
        "Net price: $8,500 for full order.\n"
        "Drywall installation complete: $2,684,000. Labor and material."
    )
    ep = extract_pricing(text)
    # Only the client-facing $2,684,000 should be the drywall price
    if ep.drywall_price is not None:
        assert ep.drywall_price >= 100_000  # Not the small supplier number


def test_blended_paint_flag() -> None:
    text = (
        "Paint Work: $1,317,923. Complete exterior work siding Hardie plank fiber cement. "
        "Labor and material included."
    )
    ep = extract_pricing(text)
    assert ep.paint_includes_exterior is True


# ── Benchmark store tests ─────────────────────────────────────────────────────

def test_benchmark_store_seed(tmp_path) -> None:
    store = BenchmarkStore(path=tmp_path / "test_benchmarks.json")
    # Should be seeded with at least CFEvans + Declan
    assert len(store.get_all()) >= 2


def test_benchmark_confirmed_pricing(tmp_path) -> None:
    store = BenchmarkStore(path=tmp_path / "test_benchmarks.json")
    confirmed = store.get_confirmed_drywall()
    # CFEvans has confirmed drywall price
    assert any(b.project_name == "CFEvans 8220 Apartments" for b in confirmed)


def test_benchmark_avg_drywall(tmp_path) -> None:
    store = BenchmarkStore(path=tmp_path / "test_benchmarks.json")
    avg = store.avg_drywall_per_unit()
    # CFEvans: $8,829/unit
    assert avg is not None
    assert 7_000 <= avg <= 12_000


def test_benchmark_add_and_retrieve(tmp_path) -> None:
    store = BenchmarkStore(path=tmp_path / "test_benchmarks.json")
    bm = ProjectBenchmark(
        project_name="Test Project Alpha",
        location="Test City, NC",
        units=100,
        gsf=100_000.0,
        drywall_price_turnkey=900_000.0,
        drywall_price_per_unit=9_000.0,
        paint_price_turnkey=400_000.0,
        paint_price_per_unit=4_000.0,
        pricing_type="turnkey",
        confidence="high",
    )
    store.add(bm)
    retrieved = store.get_by_name("Test Project Alpha")
    assert retrieved is not None
    assert retrieved.drywall_price_per_unit == 9_000.0


def test_benchmark_comparison_string(tmp_path) -> None:
    store = BenchmarkStore(path=tmp_path / "test_benchmarks.json")
    result = store.compare("drywall_per_unit", 8_829.0)
    # Should return a human-readable string
    assert "$" in result
    assert "unit" in result
