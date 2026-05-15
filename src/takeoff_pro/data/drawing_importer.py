"""Import local PDF and TIFF drawings as native jobs."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import pymupdf  # type: ignore[import-untyped]

from takeoff_pro.data.models import Job, Page

LOGGER = logging.getLogger(__name__)
_SUPPORTED_SUFFIXES = {".pdf", ".tif", ".tiff"}


class DrawingImportError(RuntimeError):
    """Raised when a drawing cannot be imported."""


def import_drawings(paths: Sequence[str | Path], *, job_name: str | None = None) -> Job:
    """Create a native job from local PDF or TIFF drawing files."""
    normalized_paths = [_normalize_source_path(path) for path in paths]
    if not normalized_paths:
        msg = "Select at least one PDF or TIFF drawing."
        raise DrawingImportError(msg)

    pages: list[Page] = []
    for source_path in normalized_paths:
        pages.extend(_pages_from_source(source_path, start_index=len(pages)))

    source_root = normalized_paths[0].parent
    resolved_name = job_name or (
        normalized_paths[0].stem if len(normalized_paths) == 1 else "Imported Drawings"
    )
    return Job(
        id=str(uuid4()),
        name=resolved_name,
        source_root=source_root,
        pages=pages,
    )


def _normalize_source_path(path: str | Path) -> Path:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        msg = f"Drawing file does not exist: {source_path}"
        raise DrawingImportError(msg)
    if not source_path.is_file():
        msg = f"Drawing path is not a file: {source_path}"
        raise DrawingImportError(msg)
    if source_path.suffix.casefold() not in _SUPPORTED_SUFFIXES:
        msg = f"Unsupported drawing file type: {source_path.suffix or '<none>'}"
        raise DrawingImportError(msg)
    return source_path


def _pages_from_source(source_path: Path, *, start_index: int) -> list[Page]:
    try:
        document = pymupdf.open(str(source_path))
    except Exception as exc:
        msg = f"Could not open drawing file: {source_path}"
        raise DrawingImportError(msg) from exc

    try:
        pages: list[Page] = []
        # For TIFF files, read DPI metadata once for all pages in the file.
        tiff_dpi = _tiff_dpi(source_path) if source_path.suffix.casefold() in {".tif", ".tiff"} else None

        for page_index in range(document.page_count):
            source_page = document.load_page(page_index)
            page_number = page_index + 1
            page_name = (
                source_path.stem
                if document.page_count == 1
                else f"{source_path.stem} - Page {page_number}"
            )
            # Seed scale from TIFF DPI so geometry calculations are accurate
            # for scanned drawings even before the AI review runs.
            scale_pixels_per_unit: float | None = None
            scale_unit: str | None = None
            scale_source: str | None = None
            if tiff_dpi is not None and tiff_dpi > 0:
                scale_pixels_per_unit = tiff_dpi
                scale_unit = "IN"
                scale_source = f"TIFF DPI metadata ({tiff_dpi:.0f} dpi)"

            pages.append(
                Page(
                    id=str(uuid4()),
                    name=page_name,
                    order_index=start_index + page_index,
                    image_path=source_path,
                    source_page_index=page_index,
                    canvas_width=max(1, round(source_page.rect.width)),
                    canvas_height=max(1, round(source_page.rect.height)),
                    scale_pixels_per_unit=scale_pixels_per_unit,
                    scale_unit=scale_unit,
                    scale_units=scale_unit,
                    scale_source=scale_source,
                )
            )
        return pages
    finally:
        document.close()


def _tiff_dpi(path: Path) -> float | None:
    """Return the horizontal DPI from a TIFF file, or None if unavailable."""
    try:
        from PIL import Image  # type: ignore[import-untyped]

        with Image.open(str(path)) as img:
            dpi_info = img.info.get("dpi")
            if isinstance(dpi_info, tuple) and len(dpi_info) >= 1:
                val = float(dpi_info[0])
                return val if val > 0 else None
    except Exception:
        LOGGER.debug("Could not read TIFF DPI from %s", path, exc_info=True)
    return None
