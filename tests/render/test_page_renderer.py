from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from takeoff_pro.render import PageRenderError, render_page_to_image


def test_render_page_to_image_supports_pdf_and_tiff(tmp_path: Path) -> None:
    tiff_path = tmp_path / "page.tiff"
    Image.new("RGB", (80, 40), "white").save(tiff_path, format="TIFF")

    pdf_path = tmp_path / "page.pdf"
    document = pymupdf.open()
    page = document.new_page(width=120, height=60)
    page.insert_text((12, 24), "Synthetic")
    document.save(pdf_path)
    document.close()

    tiff_image = render_page_to_image(tiff_path)
    pdf_image = render_page_to_image(pdf_path)

    assert tiff_image.width() > 0
    assert tiff_image.height() > 0
    assert pdf_image.width() > 0
    assert pdf_image.height() > 0


def test_render_page_to_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PageRenderError):
        render_page_to_image(tmp_path / "missing.tiff")
