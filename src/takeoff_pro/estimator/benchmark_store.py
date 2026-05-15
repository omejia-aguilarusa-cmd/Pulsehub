"""
Persistent benchmark store for confirmed drywall and paint pricing.

Stores confirmed project metrics in ~/.takeoff_pro/estimator_benchmarks.json.
Pre-seeded with confirmed data from CFEvans 8220 Apartments (Jul 2025)
and Declan Huntersville quantity takeoff (Apr 2026).

RULES:
- Only confirmed client-facing prices are stored with confidence="high".
- Quantity-only projects use confidence="medium".
- Never average benchmarks with confidence="low".
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

_STORE_PATH = Path.home() / ".takeoff_pro" / "estimator_benchmarks.json"

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ProjectBenchmark:
    """All confirmed metrics for a single analyzed project."""

    # Identity
    project_name: str
    location: str
    client_gc: str = ""
    estimate_date: str = ""

    # Building program
    units: int = 0
    gsf: float = 0.0
    nrsf: float = 0.0
    building_type: str = ""      # "multifamily_walk_up", "sfr", "commercial", etc.
    construction_type: str = ""  # "V-A", "III-A", "I-B", etc.

    # Drywall quantities
    drywall_board_sf_before_waste: Optional[float] = None
    drywall_board_sf_with_waste: Optional[float] = None
    drywall_board_count_4x8: Optional[int] = None
    drywall_board_count_4x12: Optional[int] = None
    drywall_board_sf_per_unit: Optional[float] = None
    drywall_board_sf_per_gsf: Optional[float] = None
    drywall_mr_sf: Optional[float] = None
    drywall_cbu_sf: Optional[float] = None
    drywall_shaft_wall_sf: Optional[float] = None
    drywall_waste_factor: Optional[float] = None

    # Paint quantities
    paint_gal_total: Optional[float] = None
    paint_gal_per_unit: Optional[float] = None
    paint_wall_sf: Optional[float] = None
    paint_ceiling_sf: Optional[float] = None
    paint_trim_sf: Optional[float] = None
    paint_door_sf: Optional[float] = None
    paint_interior_sf: Optional[float] = None
    paint_exterior_sf: Optional[float] = None
    paint_waste_factor: Optional[float] = None

    # Pricing — drywall
    drywall_price_turnkey: Optional[float] = None
    drywall_price_labor_only: Optional[float] = None
    drywall_price_material_only: Optional[float] = None
    drywall_price_per_unit: Optional[float] = None
    drywall_price_per_board_sf: Optional[float] = None
    drywall_price_per_gsf: Optional[float] = None
    drywall_labor_per_sheet: Optional[float] = None   # $/sheet labor-only rate

    # Pricing — paint
    paint_price_turnkey: Optional[float] = None
    paint_price_labor_only: Optional[float] = None
    paint_price_material_only: Optional[float] = None
    paint_price_per_unit: Optional[float] = None
    paint_price_per_gsf: Optional[float] = None
    paint_price_per_interior_sf: Optional[float] = None
    paint_price_per_exterior_sf: Optional[float] = None
    paint_interior_exterior_split: bool = False  # True if prices are split

    # Combined
    total_price: Optional[float] = None
    total_price_per_unit: Optional[float] = None
    drywall_pct_of_total: Optional[float] = None
    paint_pct_of_total: Optional[float] = None

    # Scope flags
    includes_exterior_paint: bool = False
    includes_balconies: bool = False
    includes_amenities: bool = False
    includes_corridors: bool = True
    includes_garages: bool = False
    includes_pressure_washing: bool = False
    pricing_type: str = "unknown"  # "turnkey", "labor_only", "material_only"

    # Methodology
    scope_inclusions: list[str] = field(default_factory=list)
    scope_exclusions: list[str] = field(default_factory=list)
    estimating_assumptions: list[str] = field(default_factory=list)

    # Metadata
    source_files: list[str] = field(default_factory=list)
    confidence: str = "medium"  # "high", "medium", "low"
    notes: str = ""


# ── Pre-seeded confirmed benchmarks ──────────────────────────────────────────

_SEED_BENCHMARKS: list[dict] = [
    {
        # CONFIRMED PRICING — high confidence
        # Source: Estimate #1140, July 16 2025, Maka Painters → CFEvans/Patrick Westbury
        "project_name": "CFEvans 8220 Apartments",
        "location": "Charlotte, NC",
        "client_gc": "CFEvans / Patrick Westbury",
        "estimate_date": "2025-07-16",
        "units": 304,
        "gsf": 0.0,
        "nrsf": 0.0,
        "building_type": "multifamily_walk_up",
        "construction_type": "",
        "drywall_board_sf_before_waste": None,
        "drywall_board_sf_with_waste": None,
        "drywall_board_count_4x8": None,
        "drywall_board_count_4x12": None,
        "drywall_board_sf_per_unit": None,
        "drywall_board_sf_per_gsf": None,
        "drywall_mr_sf": None,
        "drywall_cbu_sf": None,
        "drywall_shaft_wall_sf": None,
        "drywall_waste_factor": 0.07,
        "paint_gal_total": None,
        "paint_gal_per_unit": None,
        "paint_wall_sf": None,
        "paint_ceiling_sf": None,
        "paint_trim_sf": None,
        "paint_door_sf": None,
        "paint_interior_sf": None,
        "paint_exterior_sf": None,
        "paint_waste_factor": 0.10,
        "drywall_price_turnkey": 2684000.0,
        "drywall_price_labor_only": None,
        "drywall_price_material_only": None,
        "drywall_price_per_unit": 8829.0,
        "drywall_price_per_board_sf": None,
        "drywall_price_per_gsf": None,
        "drywall_labor_per_sheet": 36.0,
        "paint_price_turnkey": 1317923.0,
        "paint_price_labor_only": None,
        "paint_price_material_only": None,
        "paint_price_per_unit": 4336.0,
        "paint_price_per_gsf": None,
        "paint_price_per_interior_sf": None,
        "paint_price_per_exterior_sf": None,
        "paint_interior_exterior_split": False,
        "total_price": 4001923.0,
        "total_price_per_unit": 13164.0,
        "drywall_pct_of_total": 67.1,
        "paint_pct_of_total": 32.9,
        "includes_exterior_paint": True,
        "includes_balconies": False,
        "includes_amenities": True,
        "includes_corridors": True,
        "includes_garages": True,
        "includes_pressure_washing": False,
        "pricing_type": "turnkey",
        "scope_inclusions": [
            "304 units interior paint — walls, ceilings, trim, doors",
            "Corridors and mechanical closets",
            "Amenities / clubhouse paint",
            "Exterior siding, Hardie plank, fiber cement per drawings",
            "Drywall hang, mud, sand, finish — 304 units + garages + clubhouse",
        ],
        "scope_exclusions": [],
        "estimating_assumptions": [
            "$36/sheet labor-only drywall rate (sheet size unconfirmed)",
            "Interior and exterior paint bundled — cannot separate",
        ],
        "source_files": ["Estimate_1140_2025-08-15 (1).pdf"],
        "confidence": "high",
        "notes": (
            "Only confirmed client-facing estimate in the set. Interior + exterior paint "
            "blended into one line ($1,317,923). Cannot confirm interior-only paint price. "
            "$36/sheet labor-only DW rate explicitly stated. Estimate valid to Aug 15 2025."
        ),
    },
    {
        # QUANTITIES CONFIRMED, PRICING NOT CONFIRMED — medium confidence
        # Source: Declan_Huntersville_Drywall_Paint_Takeoff.xlsx + Sheet Reference Map PDF
        "project_name": "Declan Huntersville",
        "location": "Huntersville, NC (Mecklenburg County)",
        "client_gc": "Flournoy Development",
        "estimate_date": "2026-04",
        "units": 318,
        "gsf": 382392.0,
        "nrsf": 326268.0,
        "building_type": "multifamily_walk_up",
        "construction_type": "V-A",
        "drywall_board_sf_before_waste": 1556366.0,
        "drywall_board_sf_with_waste": 1665312.0,
        "drywall_board_count_4x8": 52041,
        "drywall_board_count_4x12": 34694,
        "drywall_board_sf_per_unit": 5172.63,
        "drywall_board_sf_per_gsf": 4.30,
        "drywall_mr_sf": 59623.0,
        "drywall_cbu_sf": 20416.0,
        "drywall_shaft_wall_sf": 29811.0,
        "drywall_waste_factor": 0.07,
        "paint_gal_total": 19988.0,
        "paint_gal_per_unit": 31.43,
        "paint_wall_sf": 698082.0,
        "paint_ceiling_sf": 359323.0,
        "paint_trim_sf": 57240.0,
        "paint_door_sf": 31800.0,
        "paint_interior_sf": 1875027.0,
        "paint_exterior_sf": 0.0,
        "paint_waste_factor": 0.10,
        "drywall_price_turnkey": None,
        "drywall_price_labor_only": None,
        "drywall_price_material_only": None,
        "drywall_price_per_unit": None,
        "drywall_price_per_board_sf": None,
        "drywall_price_per_gsf": None,
        "drywall_labor_per_sheet": None,
        "paint_price_turnkey": None,
        "paint_price_labor_only": None,
        "paint_price_material_only": None,
        "paint_price_per_unit": None,
        "paint_price_per_gsf": None,
        "paint_price_per_interior_sf": None,
        "paint_price_per_exterior_sf": None,
        "paint_interior_exterior_split": True,
        "total_price": None,
        "total_price_per_unit": None,
        "drywall_pct_of_total": None,
        "paint_pct_of_total": None,
        "includes_exterior_paint": False,
        "includes_balconies": False,
        "includes_amenities": True,
        "includes_corridors": True,
        "includes_garages": False,
        "includes_pressure_washing": False,
        "pricing_type": "unknown",
        "scope_inclusions": [
            "Type X 5/8\" GWB — residential walls + ceilings (double-layer UL U301/V337)",
            "MR board — bath/laundry/kitchen",
            "CBU — tub/shower surrounds",
            "1-hr shaft wall — elev/MEP shafts",
            "Abuse-resistant gyp — corridor wainscot 0-48\" AFF",
            "Clubhouse/amenity std + MR board",
            "Corner bead, control joints, J-trim, firestop, acoustic sealant, SAB batts",
            "Paint: walls (3-coat), ceilings (2-coat), trim (3-coat), doors (3-coat)",
            "Common area + clubhouse paint included",
        ],
        "scope_exclusions": [
            "Exterior field paint (RFI-07 — factory-finished assumed)",
            "Level 5 finish (allowance only — excluded from base)",
            "Garage drywall (assumption: exposed framing)",
            "RC-1 resilient channel",
            "Night/OT acceleration",
        ],
        "estimating_assumptions": [
            "3.80 BF/GSF residential board ratio (Type V-A double-layer)",
            "1.80 SF paint per unit NRSF (walls)",
            "0.95 SF paint per unit NRSF (ceilings)",
            "7% waste factor — board",
            "10% waste factor — paint",
            "Level 4 finish assumed throughout",
            "9'-0\" average ceiling height",
            "318 units, 1,026 avg NRSF — hardcoded from SP-01",
        ],
        "source_files": [
            "Declan_Huntersville_Drywall_Paint_Takeoff.xlsx",
            "Declan_Huntersville_Sheet_Reference_Map.pdf",
        ],
        "confidence": "medium",
        "notes": (
            "Full buyout-grade quantity takeoff. Pricing Checklist tab entirely blank — "
            "NO client-facing price confirmed. Quantities used for methodology validation. "
            "Board SF/unit = 5,172 (within 4,500–5,500 target). Paint gal/unit = 31.4 "
            "(within 25–35 target). 12 open RFIs — highest risk: exterior scope (RFI-07)."
        ),
    },
]


# ── Store class ───────────────────────────────────────────────────────────────

class BenchmarkStore:
    """Persistent storage for project estimating benchmarks."""

    def __init__(self, path: Path = _STORE_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._benchmarks: list[ProjectBenchmark] = self._load()
        if not self._benchmarks:
            self._seed()

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, benchmark: ProjectBenchmark) -> None:
        """Add or replace a benchmark by project name."""
        self._benchmarks = [
            b for b in self._benchmarks if b.project_name != benchmark.project_name
        ]
        self._benchmarks.append(benchmark)
        self._save()
        LOGGER.info("Stored benchmark for %s (confidence=%s)", benchmark.project_name, benchmark.confidence)

    def get_all(self) -> list[ProjectBenchmark]:
        return list(self._benchmarks)

    def get_by_name(self, name: str) -> ProjectBenchmark | None:
        for b in self._benchmarks:
            if b.project_name.lower() == name.lower():
                return b
        return None

    def get_confirmed_drywall(self) -> list[ProjectBenchmark]:
        """Projects with confirmed client-facing drywall price."""
        return [
            b for b in self._benchmarks
            if b.drywall_price_turnkey is not None
            and b.confidence in ("high", "medium")
        ]

    def get_confirmed_paint(self) -> list[ProjectBenchmark]:
        """Projects with confirmed client-facing paint price."""
        return [
            b for b in self._benchmarks
            if b.paint_price_turnkey is not None
            and b.confidence in ("high", "medium")
        ]

    def avg_drywall_per_unit(self) -> float | None:
        data = [
            b.drywall_price_per_unit
            for b in self.get_confirmed_drywall()
            if b.drywall_price_per_unit is not None
        ]
        return round(sum(data) / len(data), 2) if data else None

    def avg_paint_per_unit(self) -> float | None:
        data = [
            b.paint_price_per_unit
            for b in self.get_confirmed_paint()
            if b.paint_price_per_unit is not None
        ]
        return round(sum(data) / len(data), 2) if data else None

    def avg_board_sf_per_unit(self) -> float | None:
        """Average board SF/unit from medium+ confidence quantity takeoffs."""
        data = [
            b.drywall_board_sf_per_unit
            for b in self._benchmarks
            if b.drywall_board_sf_per_unit is not None
            and b.confidence in ("high", "medium")
        ]
        return round(sum(data) / len(data), 1) if data else None

    def compare(self, metric: str, value: float) -> str:
        """Return a human-readable comparison string against the historical average."""
        avg = None
        unit = ""
        if metric == "drywall_per_unit":
            avg = self.avg_drywall_per_unit()
            unit = "/unit"
        elif metric == "paint_per_unit":
            avg = self.avg_paint_per_unit()
            unit = "/unit"
        elif metric == "board_sf_per_unit":
            avg = self.avg_board_sf_per_unit()
            unit = " BF/unit"

        if avg is None:
            return "No prior confirmed benchmark available."
        diff = (value - avg) / avg * 100
        direction = "above" if diff > 0 else "below"
        return f"${value:,.0f}{unit} vs avg ${avg:,.0f}{unit} ({abs(diff):.1f}% {direction} avg)"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> list[ProjectBenchmark]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [ProjectBenchmark(**d) for d in data]
        except Exception as exc:
            LOGGER.warning("Could not load benchmarks from %s: %s", self._path, exc)
            return []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps([asdict(b) for b in self._benchmarks], indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            LOGGER.warning("Could not save benchmarks to %s: %s", self._path, exc)

    def _seed(self) -> None:
        """Populate with confirmed data from the initial analysis session."""
        for d in _SEED_BENCHMARKS:
            b = ProjectBenchmark(**d)
            self._benchmarks.append(b)
        self._save()
        LOGGER.info("Seeded %d initial benchmarks.", len(_SEED_BENCHMARKS))


# Module-level singleton
_store: BenchmarkStore | None = None


def get_store() -> BenchmarkStore:
    global _store
    if _store is None:
        _store = BenchmarkStore()
    return _store
