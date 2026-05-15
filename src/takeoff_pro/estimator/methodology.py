"""
Senior Construction Estimator — Core Methodology Constants

All planning ratios, sanity ranges, coverage rates, and calculation rules
learned from drywall and paint takeoff analysis are encoded here.

These are derived from:
  - Declan Huntersville takeoff workbook (April 2026, 318-unit Type V-A MF)
  - CFEvans 8220 Apartments estimate (July 2025, 304-unit MF)
  - RSMeans 09 21 16 / MPI / GA-214 / GA-216 industry standards

Every ratio here has a confirmed source. When overridden by a project document,
the document value takes precedence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrywallRatios:
    """
    Planning ratios for drywall board SF calculation.
    Basis: Type V-A NFPA 13R 4-story multifamily walk-up, double-loaded corridor.
    Assemblies: UL U301 / U305 / U356 / V337 / L563 / L576.
    """

    # Board SF per building GSF
    board_sf_per_residential_gsf: float = 3.80
    board_sf_per_nonres_gsf: float = 3.20  # clubhouse / amenity
    board_sf_per_sfr_gsf: float = 2.20     # single-family residential

    # Board type fractions (of residential board SF)
    mr_board_fraction: float = 0.04        # bath/laundry/kitchen MR/purple board
    shaft_wall_fraction: float = 0.02      # 1-hr elev/MEP shaft liner + face
    abuse_resistant_fraction: float = 0.15 # corridor wainscot 0-48" AFF (of common SF)

    # CBU (cement backer) — tub/shower surrounds
    cbu_sf_per_unit: float = 60.0          # 3 walls × 5' × 4'

    # Waste factors
    waste_factor_board: float = 0.07       # RSMeans 09 21 16 standard
    waste_factor_accessories: float = 0.05 # corner bead, CJ, J-trim

    # Wall LF planning ratios (per unit, for framing coordination reference)
    demising_lf_per_unit: float = 80.0     # party walls + tenant entry
    interior_partition_lf_per_unit: float = 140.0  # bed/bath/closet/kitchen/LR
    corridor_lf_per_unit: float = 14.0    # corridor both sides of unit door
    exterior_interior_face_lf_per_unit: float = 36.0  # interior face of ext wall

    # Average finished ceiling height
    avg_ceiling_height_unit: float = 9.0
    avg_ceiling_height_common: float = 9.0
    avg_ceiling_height_clubhouse: float = 12.0

    # Accessories (LF per project GSF)
    corner_bead_lf_per_gsf: float = 0.35
    control_joint_lf_per_gsf: float = 0.02    # GA-216: 1 per 30 LF run
    j_trim_lf_per_gsf: float = 0.08

    # Accessories (LF per unit)
    firestop_lf_per_unit: float = 40.0         # UL F-C-2034/2088/1074
    acoustic_sealant_lf_per_unit: float = 160.0  # demising perimeter both sides

    # Productivity (reference only — adjust per crew)
    hang_rate_bft_per_crew_day: float = 3500.0    # 4-man crew, residential Type X
    finish_rate_bft_per_crew_day: float = 2800.0  # tape+bed+skim+sand, Level 4


@dataclass(frozen=True)
class PaintRatios:
    """
    Planning ratios for paint surface SF and gallonage calculation.
    Basis: Level 4 finish per GA-214, MPI system.
    """

    # Surface SF per NRSF (unit net rentable SF)
    wall_sf_per_unit_nrsf: float = 1.80       # 9-ft ceiling, standard perimeter
    ceiling_sf_per_unit_nrsf: float = 0.95    # flat ceilings only

    # Surface SF per common GSF (corridors/stairs/vestibules)
    common_wall_sf_per_common_gsf: float = 2.16   # higher wall:floor ratio
    common_ceiling_sf_per_common_gsf: float = 0.95

    # Surface SF per unit (trim and doors)
    trim_sf_per_unit: float = 180.0    # base (100 LF × 4") + 6-door casing + window
    door_sf_per_unit: float = 100.0    # 5 doors × 2 sides × ~10 SF face

    # Clubhouse / amenity
    clubhouse_wall_sf_per_gsf: float = 1.50
    clubhouse_ceiling_sf_per_gsf: float = 0.70
    accent_wall_fraction_nonres: float = 0.15  # 3-5 colors typical in amenity

    # Coat counts (new construction)
    wall_coats: int = 3        # 1 PVA primer + 2 acrylic eggshell
    ceiling_coats: int = 2     # 1 PVA primer + 1 flat white
    trim_coats: int = 3        # 1 factory primer + 2 SG waterborne alkyd
    door_coats: int = 3        # same as trim

    # Waste factor (MPI standard)
    waste_factor: float = 0.10  # mixing / cutting / spoilage

    # Productivity (reference only)
    wall_roll_rate_sf_per_mh: float = 220.0    # cut-in + roll, Level 4
    ceiling_spray_rate_sf_per_mh: float = 380.0  # airless spray + backroll
    trim_brush_rate_lf_per_mh: float = 55.0


@dataclass(frozen=True)
class CoverageRates:
    """Paint coverage rates in SF per gallon. Source: published product data sheets."""

    primer_pva_wall: float = 300.0          # PVA/drywall sealer, first coat
    walls_level4_sealed: float = 350.0      # acrylic eggshell over sealed new gyp
    ceilings_flat: float = 375.0            # flat white on primed gyp
    trim_doors_sg: float = 400.0            # SG waterborne alkyd on primed wood
    exterior_paint: float = 300.0           # elastomeric/exterior acrylic
    masonry_block_filler: float = 100.0     # first coat on CMU
    masonry_finish: float = 200.0           # finish coat on sealed CMU


@dataclass(frozen=True)
class SanityRanges:
    """
    Sanity-check target ranges for key per-unit / per-GSF metrics.
    If a project falls outside these ranges, flag for review.
    Basis: Type V-A multifamily walk-up (4-story, double-loaded, NFPA 13R).
    """

    # Drywall
    board_sf_per_unit_min: float = 4_500
    board_sf_per_unit_max: float = 5_500
    board_sf_per_unit_sfr_min: float = 1_200
    board_sf_per_unit_sfr_max: float = 2_000
    board_sf_per_gsf_min: float = 4.0
    board_sf_per_gsf_max: float = 4.8

    # Paint
    paint_gal_per_unit_min: float = 25.0
    paint_gal_per_unit_max: float = 35.0

    # Pricing (turnkey labor + material, multifamily)
    drywall_per_unit_min: float = 7_000
    drywall_per_unit_max: float = 12_000
    paint_per_unit_interior_min: float = 2_500
    paint_per_unit_interior_max: float = 4_500
    drywall_labor_per_sheet_min: float = 25.0
    drywall_labor_per_sheet_max: float = 55.0


@dataclass(frozen=True)
class DocumentSourcePriority:
    """
    Priority order for evidence when multiple documents conflict.
    Lower index = higher priority.
    """

    order: tuple[str, ...] = (
        "signed_estimate",
        "client_facing_proposal",
        "native_pricing_spreadsheet",
        "takeoff_report",
        "material_list",
        "supplier_quote",
        "drawing",
        "finish_schedule",
        "wall_type_legend",
        "scope_note",
        "email",
        "filename",
    )


# Module-level singletons — import these in analysis code.
DRYWALL = DrywallRatios()
PAINT = PaintRatios()
COVERAGE = CoverageRates()
SANITY = SanityRanges()
SOURCE_PRIORITY = DocumentSourcePriority()


# ── Calculation helpers ───────────────────────────────────────────────────────

def project_board_sf(
    units: int,
    residential_gsf: float,
    nonres_gsf: float = 0.0,
    *,
    ratios: DrywallRatios = DRYWALL,
) -> dict[str, float]:
    """
    Return a dictionary of projected board SF quantities using planning ratios.
    All returned values INCLUDE the standard 7% waste factor.
    """
    base_res = residential_gsf * ratios.board_sf_per_residential_gsf
    base_nonres = nonres_gsf * ratios.board_sf_per_nonres_gsf
    waste = ratios.waste_factor_board

    res_std = base_res * (1 + waste)
    res_mr = base_res * ratios.mr_board_fraction * (1 + waste)
    res_cbu = units * ratios.cbu_sf_per_unit * (1 + waste)
    res_shaft = base_res * ratios.shaft_wall_fraction * (1 + waste)
    nonres_std = base_nonres * (1 + waste)
    nonres_mr = base_nonres * 0.08 * (1 + waste)  # 8% MR of non-res

    total = res_std + res_mr + res_cbu + res_shaft + nonres_std + nonres_mr

    return {
        "residential_std_type_x": round(res_std, 1),
        "residential_mr": round(res_mr, 1),
        "residential_cbu": round(res_cbu, 1),
        "residential_shaft_wall": round(res_shaft, 1),
        "nonres_std": round(nonres_std, 1),
        "nonres_mr": round(nonres_mr, 1),
        "total": round(total, 1),
    }


def project_paint_gallons(
    units: int,
    unit_nrsf: float,
    common_gsf: float = 0.0,
    nonres_gsf: float = 0.0,
    *,
    ratios: PaintRatios = PAINT,
    coverage: CoverageRates = COVERAGE,
) -> dict[str, float]:
    """
    Return projected paint gallons using planning ratios.
    All returned values INCLUDE the 10% waste factor.
    """
    total_nrsf = units * unit_nrsf
    waste = 1 + ratios.waste_factor

    wall_sf = total_nrsf * ratios.wall_sf_per_unit_nrsf
    ceil_sf = total_nrsf * ratios.ceiling_sf_per_unit_nrsf
    trim_sf = units * ratios.trim_sf_per_unit
    door_sf = units * ratios.door_sf_per_unit
    common_wall_sf = common_gsf * ratios.common_wall_sf_per_common_gsf
    common_ceil_sf = common_gsf * ratios.common_ceiling_sf_per_common_gsf
    clubhouse_wall = nonres_gsf * ratios.clubhouse_wall_sf_per_gsf
    clubhouse_ceil = nonres_gsf * ratios.clubhouse_ceiling_sf_per_gsf

    primer_gal = (wall_sf + ceil_sf + common_wall_sf + common_ceil_sf + clubhouse_wall + clubhouse_ceil) / coverage.primer_pva_wall * waste
    wall_gal = wall_sf * ratios.wall_coats / coverage.walls_level4_sealed * waste
    ceil_gal = (ceil_sf + common_ceil_sf + clubhouse_ceil) * 1 / coverage.ceilings_flat * waste
    trim_gal = trim_sf * ratios.trim_coats / coverage.trim_doors_sg * waste
    door_gal = door_sf * ratios.door_coats / coverage.trim_doors_sg * waste
    common_wall_gal = (common_wall_sf + clubhouse_wall) * 2 / coverage.walls_level4_sealed * waste

    total = primer_gal + wall_gal + ceil_gal + trim_gal + door_gal + common_wall_gal

    return {
        "primer_gal": round(primer_gal, 1),
        "wall_finish_gal": round(wall_gal, 1),
        "ceiling_gal": round(ceil_gal, 1),
        "trim_gal": round(trim_gal, 1),
        "door_gal": round(door_gal, 1),
        "common_wall_gal": round(common_wall_gal, 1),
        "total_gal": round(total, 1),
        "gal_per_unit": round(total / units, 2) if units else 0,
    }
