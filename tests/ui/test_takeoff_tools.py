from __future__ import annotations

from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[2] / "src" / "takeoff_pro" / "ui" / "assets"


def test_workspace_assets_reference_real_spa_files() -> None:
    html = (ASSET_ROOT / "estimator_ui.html").read_text(encoding="utf-8")

    assert "workspace_styles.css" in html
    assert "workspace_logic.js" in html
    assert "workspace_app.js" in html
    assert "Cedar Ridge Medical Office" not in html
    assert "Sarah Reyes" not in html


def test_workspace_logic_declares_all_required_routes() -> None:
    logic = (ASSET_ROOT / "workspace_logic.js").read_text(encoding="utf-8")

    for route in (
        "dashboard",
        "documents",
        "drawing-viewer",
        "takeoff",
        "scope-detection",
        "questions-rfis",
        "estimate",
        "risk-confidence",
        "output-center",
        "company-memory",
        "past-projects",
        "settings",
    ):
        assert route in logic
