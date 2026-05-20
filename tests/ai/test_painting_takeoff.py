from pathlib import Path

from pytest import MonkeyPatch
from reportlab.pdfgen import canvas

from takeoff_pro.ai.service import AiTakeoffRequest, api_shape, run_ai_takeoff
from takeoff_pro.ai.takeoff.formulas import calculate_painting_quantities
from takeoff_pro.ai.takeoff.result_normalizer import normalize_ai_takeoff_response
from takeoff_pro.data.models import AiTakeoffStatus, Job, Page, PageRasterStatus


def test_painting_formula_layer_deducts_openings_and_trim() -> None:
    result = calculate_painting_quantities(
        floor_area_sf=500,
        perimeter_ft=100,
        ceiling_height_ft=9,
        door_count=2,
        window_count=3,
    )

    assert result.wall_sf == 813
    assert result.ceiling_sf == 500
    assert result.total_trim_lf == 170


def test_normalizer_applies_formula_defaults() -> None:
    pages, totals, confidence, warnings = normalize_ai_takeoff_response(
        {
            "rooms": [
                {
                    "id": "room-1",
                    "name": "Office 101",
                    "type": "office",
                    "pageId": "page-1",
                    "confidence": 0.82,
                    "floorAreaSf": 500,
                    "perimeterFt": 100,
                    "doorCount": 2,
                    "windowCount": 3,
                    "assumptions": ["Ceiling height defaulted to 9 ft."],
                }
            ],
            "elements": [],
            "warnings": [],
            "confidenceScore": 0.82,
        },
        project_id="job-1",
        page_ids=["page-1"],
    )

    assert warnings == []
    assert confidence == 82
    assert pages[0].rooms[0].wall_sf == 813
    assert pages[0].rooms[0].trim_lf == 170
    assert totals.wall_sf == 813


def test_run_ai_takeoff_gracefully_handles_missing_provider(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    pdf_path = tmp_path / "plan.pdf"
    _write_sample_pdf(pdf_path)
    job = Job(
        id="job-1",
        name="Test Job",
        source_root=tmp_path,
        pages=[
            Page(
                id="page-1",
                name="A101",
                image_path=pdf_path,
                source_page_index=0,
                canvas_width=612,
                canvas_height=792,
            )
        ],
    )

    run = run_ai_takeoff(job, AiTakeoffRequest(project_id=job.id))
    response = api_shape(run)

    assert run.status == AiTakeoffStatus.NOT_CONFIGURED
    assert job.pages[0].raster_status == PageRasterStatus.COMPLETE
    assert job.pages[0].raster_image_path is not None
    assert job.pages[0].raster_image_path.exists()
    assert response["projectId"] == "job-1"
    assert response["status"] == "not_configured"


def _write_sample_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.drawString(72, 720, 'SCALE: 1/8" = 1\'-0"')
    c.rect(72, 500, 180, 120)
    c.showPage()
    c.save()
