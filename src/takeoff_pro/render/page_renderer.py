"""PyMuPDF-backed page rendering helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pymupdf  # type: ignore[import-untyped]
from PyQt6.QtGui import QImage


class PageRenderError(RuntimeError):
    """Raised when a page cannot be rendered."""


class _PixmapLike(Protocol):
    samples: bytes
    width: int
    height: int
    stride: int


def render_page_to_image(
    source_path: str | Path,
    *,
    page_index: int = 0,
    zoom: float = 1.0,
    rotation_degrees: int = 0,
) -> QImage:
    """Render a PDF or TIFF page into a detached Qt image."""
    path = Path(source_path).expanduser().resolve()
    if not path.exists():
        msg = f"Page file does not exist: {path}"
        raise PageRenderError(msg)
    if not path.is_file():
        msg = f"Page path is not a file: {path}"
        raise PageRenderError(msg)
    if zoom <= 0:
        msg = "Render zoom must be greater than zero."
        raise PageRenderError(msg)

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        msg = f"Could not open page file: {path}"
        raise PageRenderError(msg) from exc

    try:
        if page_index < 0 or page_index >= document.page_count:
            msg = f"Page index {page_index} is outside 0..{document.page_count - 1}."
            raise PageRenderError(msg)
        page = document.load_page(page_index)
        matrix = pymupdf.Matrix(zoom, zoom).prerotate(rotation_degrees)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return _pixmap_to_image(pixmap)
    finally:
        document.close()


def _pixmap_to_image(pixmap: _PixmapLike) -> QImage:
    image = QImage(
        pixmap.samples,
        pixmap.width,
        pixmap.height,
        pixmap.stride,
        QImage.Format.Format_RGB888,
    )
    if image.isNull():
        msg = "PyMuPDF produced an empty image."
        raise PageRenderError(msg)
    return image.copy()
