"""Persist PDF/TIFF page images for AI vision and plan workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]

from takeoff_pro.data.models import Job, Page, PageRasterStatus


class PageRasterizationError(RuntimeError):
    """Raised when a page image cannot be rasterized."""


@dataclass(frozen=True)
class RasterizedPage:
    """Metadata for one generated page image."""

    page_id: str
    image_path: Path
    width: int
    height: int
    zoom: float


def rasterize_job_pages(
    job: Job,
    *,
    page_ids: list[str] | None = None,
    output_root: str | Path | None = None,
    zoom: float = 2.0,
) -> list[RasterizedPage]:
    """Rasterize selected job pages and update their page metadata."""
    if zoom <= 0:
        msg = "Rasterization zoom must be greater than zero."
        raise PageRasterizationError(msg)

    selected_ids = set(page_ids or [page.id for page in job.pages])
    target_root = (
        Path(output_root).expanduser().resolve() if output_root else job.source_root / "ai_pages"
    )
    target_root.mkdir(parents=True, exist_ok=True)

    results: list[RasterizedPage] = []
    for page in job.pages:
        if page.id not in selected_ids:
            continue
        results.append(rasterize_page(page, output_root=target_root, zoom=zoom))
    return results


def rasterize_page(page: Page, *, output_root: str | Path, zoom: float = 2.0) -> RasterizedPage:
    """Rasterize one PDF/TIFF page to a PNG and update the page model."""
    if page.image_path is None:
        _mark_failed(page, "No source drawing file is available.")
        msg = f"Page {page.id} has no source drawing file."
        raise PageRasterizationError(msg)

    source_path = page.image_path.expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        _mark_failed(page, f"Source drawing file does not exist: {source_path}")
        msg = f"Source drawing file does not exist: {source_path}"
        raise PageRasterizationError(msg)

    target_dir = Path(output_root).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    image_path = target_dir / f"{page.id}-p{page.source_page_index + 1}.png"

    page.raster_status = PageRasterStatus.PROCESSING
    page.raster_error = None
    try:
        document = pymupdf.open(str(source_path))
    except Exception as exc:
        _mark_failed(page, f"Could not open drawing file: {exc}")
        msg = f"Could not open drawing file: {source_path}"
        raise PageRasterizationError(msg) from exc

    try:
        _check_source_page_index(page, document.page_count)
        source_page = document.load_page(page.source_page_index)
        pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pixmap.save(str(image_path))
    except PageRasterizationError:
        raise
    except Exception as exc:
        _mark_failed(page, f"Could not rasterize page: {exc}")
        msg = f"Could not rasterize page {page.id}."
        raise PageRasterizationError(msg) from exc
    finally:
        document.close()

    page.raster_image_path = image_path
    page.raster_width = int(pixmap.width)
    page.raster_height = int(pixmap.height)
    page.raster_zoom = zoom
    page.raster_status = PageRasterStatus.COMPLETE
    page.raster_error = None
    return RasterizedPage(
        page_id=page.id,
        image_path=image_path,
        width=int(pixmap.width),
        height=int(pixmap.height),
        zoom=zoom,
    )


def _mark_failed(page: Page, error: str) -> None:
    page.raster_status = PageRasterStatus.FAILED
    page.raster_error = error


def _check_source_page_index(page: Page, page_count: int) -> None:
    if page.source_page_index < 0 or page.source_page_index >= page_count:
        msg = f"Source page index {page.source_page_index} outside 0..{page_count - 1}."
        _mark_failed(page, msg)
        raise PageRasterizationError(msg)
