from __future__ import annotations

from pathlib import Path

import pymupdf

from takeoff_pro.analysis import apply_drawing_review, review_job_drawings
from takeoff_pro.data import import_drawings


def test_automated_review_detects_pdf_scale_and_vector_lines(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scaled.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Scale 1\" = 10'")
    page.draw_line((72, 200), (216, 200), width=2)
    document.save(pdf_path)
    document.close()

    job = import_drawings([pdf_path])
    review = review_job_drawings(job)
    added = apply_drawing_review(job, review)

    assert review.detected_scale_count == 1
    assert added >= 1
    assert job.pages[0].scale_pixels_per_unit == 7.2
    assert job.takeoff_sections[0].measurements[0].unit == "LF"
    assert job.takeoff_sections[0].measurements[0].quantity == 20


def test_automated_review_detects_vector_rectangles_as_areas(tmp_path: Path) -> None:
    pdf_path = tmp_path / "area.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Scale 1\" = 10'")
    page.draw_rect((72, 200, 144, 272), width=2)
    document.save(pdf_path)
    document.close()

    job = import_drawings([pdf_path])
    review = review_job_drawings(job)
    apply_drawing_review(job, review)

    area_sections = [section for section in job.takeoff_sections if section.kind.value == "area"]
    assert area_sections
    assert area_sections[0].measurements[0].unit == "SF"
    assert area_sections[0].measurements[0].quantity == 100
