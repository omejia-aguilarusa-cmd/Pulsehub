from __future__ import annotations

from pathlib import Path

import pymupdf

from takeoff_pro.data import import_drawings


def test_import_drawings_creates_pages_for_each_pdf_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "set.pdf"
    document = pymupdf.open()
    document.new_page(width=200, height=100)
    document.new_page(width=300, height=150)
    document.save(pdf_path)
    document.close()

    job = import_drawings([pdf_path])

    assert job.name == "set"
    assert [page.source_page_index for page in job.pages] == [0, 1]
    assert [page.name for page in job.pages] == ["set - Page 1", "set - Page 2"]
    assert [page.canvas_width for page in job.pages] == [200, 300]
