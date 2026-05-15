"""PyMuPDF-backed page rendering helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pymupdf  # type: ignore[import-untyped]
from PyQt6.QtGui import QImage

from takeoff_pro.render.profiler import profiler

# Render at 2× PDF resolution so images stay sharp when the user zooms in.
# devicePixelRatio is set to the same factor so Qt maps scene coordinates
# back to 1× PDF-point space (measurement coordinates remain correct).
_RENDER_QUALITY: float = 2.0


class PageRenderError(RuntimeError):
    """Raised when a page cannot be rendered."""


class _PixmapLike(Protocol):
    samples: bytes
    width: int
    height: int
    stride: int


# ── Full-page render ──────────────────────────────────────────────────────────

def render_page_to_image(
    source_path: str | Path,
    *,
    page_index: int = 0,
    zoom: float = 1.0,
    rotation_degrees: int = 0,
) -> QImage:
    """Render a PDF or TIFF page into a detached Qt image.

    The returned image has devicePixelRatio == _RENDER_QUALITY so that scene
    coordinates inside QGraphicsView remain in PDF-point units even though the
    physical pixel buffer is _RENDER_QUALITY× larger.
    """
    path = Path(source_path).expanduser().resolve()
    _assert_file(path)
    if zoom <= 0:
        msg = "Render zoom must be greater than zero."
        raise PageRenderError(msg)

    with profiler.measure("pdf_open"):
        try:
            document = pymupdf.open(str(path))
        except Exception as exc:
            msg = f"Could not open page file: {path}"
            raise PageRenderError(msg) from exc

    try:
        _check_index(document, page_index)
        page = document.load_page(page_index)
        render_scale = zoom * _RENDER_QUALITY
        with profiler.measure("pixmap_render"):
            matrix = pymupdf.Matrix(render_scale, render_scale).prerotate(rotation_degrees)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        with profiler.measure("image_convert"):
            image = _pixmap_to_image(pixmap)
        image.setDevicePixelRatio(_RENDER_QUALITY)
        return image
    finally:
        document.close()


# ── Fast thumbnail ────────────────────────────────────────────────────────────

def render_page_thumbnail(
    source_path: str | Path,
    *,
    page_index: int = 0,
    max_px: int = 512,
) -> QImage:
    """Render a fast low-resolution thumbnail for immediate display.

    The returned image has devicePixelRatio == 1.0 (no quality boost needed
    for a thumbnail).  Useful as a placeholder while the full-quality render
    runs on a background thread.
    """
    path = Path(source_path).expanduser().resolve()
    _assert_file(path)

    with profiler.measure("pdf_open_thumb"):
        try:
            document = pymupdf.open(str(path))
        except Exception as exc:
            msg = f"Could not open page file: {path}"
            raise PageRenderError(msg) from exc

    try:
        _check_index(document, page_index)
        page = document.load_page(page_index)
        page_max = max(page.rect.width, page.rect.height)
        zoom = min(float(max_px) / page_max, 1.0) if page_max > 0 else 1.0
        with profiler.measure("pixmap_render_thumb"):
            matrix = pymupdf.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        with profiler.measure("image_convert_thumb"):
            image = _pixmap_to_image(pixmap)
        # Set devicePixelRatio to 1/zoom so the image occupies the full
        # PDF-point canvas in scene space.
        image.setDevicePixelRatio(zoom)
        return image
    finally:
        document.close()


# ── Region render for adaptive quality ───────────────────────────────────────

def render_page_region(
    source_path: str | Path,
    *,
    page_index: int = 0,
    region_pts: tuple[float, float, float, float],
    zoom: float = 2.0,
) -> tuple[QImage, tuple[float, float]]:
    """Render a rectangular sub-region of a page at an arbitrary zoom.

    Parameters
    ----------
    region_pts:
        (x0, y0, x1, y1) in PDF-point coordinates.
    zoom:
        Physical pixels per PDF point (e.g. 4.0 for high-quality close-up).

    Returns
    -------
    image:
        Rendered QImage with devicePixelRatio == zoom so scene coordinates
        remain in PDF-point space.
    origin_pts:
        (x0, y0) — the top-left of the region in PDF points, to be used as
        QGraphicsItem.setPos(origin_x, origin_y) in the scene.
    """
    path = Path(source_path).expanduser().resolve()
    _assert_file(path)
    if zoom <= 0:
        msg = "Render zoom must be greater than zero."
        raise PageRenderError(msg)

    x0, y0, x1, y1 = region_pts
    if x0 >= x1 or y0 >= y1:
        msg = f"Invalid region: ({x0}, {y0}, {x1}, {y1})"
        raise PageRenderError(msg)

    with profiler.measure("pdf_open_region"):
        try:
            document = pymupdf.open(str(path))
        except Exception as exc:
            msg = f"Could not open page file: {path}"
            raise PageRenderError(msg) from exc

    try:
        _check_index(document, page_index)
        page = document.load_page(page_index)
        clip = pymupdf.Rect(x0, y0, x1, y1)
        with profiler.measure("pixmap_render_region"):
            matrix = pymupdf.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        with profiler.measure("image_convert_region"):
            image = _pixmap_to_image(pixmap)
        # devicePixelRatio == zoom keeps the image's logical size equal to
        # (x1-x0) × (y1-y0) PDF points, so .setPos(x0, y0) places it correctly.
        image.setDevicePixelRatio(zoom)
        return image, (x0, y0)
    finally:
        document.close()


# ── Metadata only ─────────────────────────────────────────────────────────────

def get_page_dimensions(
    source_path: str | Path,
    *,
    page_index: int = 0,
) -> tuple[float, float]:
    """Return (width_pts, height_pts) for a page without rendering it."""
    path = Path(source_path).expanduser().resolve()
    _assert_file(path)

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        msg = f"Could not open page file: {path}"
        raise PageRenderError(msg) from exc

    try:
        _check_index(document, page_index)
        page = document.load_page(page_index)
        return float(page.rect.width), float(page.rect.height)
    finally:
        document.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _assert_file(path: Path) -> None:
    if not path.exists():
        msg = f"Page file does not exist: {path}"
        raise PageRenderError(msg)
    if not path.is_file():
        msg = f"Page path is not a file: {path}"
        raise PageRenderError(msg)


def _check_index(document: object, page_index: int) -> None:
    page_count = getattr(document, "page_count", 0)
    if page_index < 0 or page_index >= page_count:
        msg = f"Page index {page_index} is outside 0..{page_count - 1}."
        raise PageRenderError(msg)


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
