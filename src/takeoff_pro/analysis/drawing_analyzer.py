"""Local automated drawing review for uploaded PDFs and TIFFs."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Protocol, TypeGuard
from uuid import uuid4

import numpy as np
import numpy.typing as npt
import pymupdf  # type: ignore[import-untyped]

from takeoff_pro.core import calculate_measurement
from takeoff_pro.data.models import Job, Measurement, MeasurementKind, Page, Point, TakeoffSection

LOGGER = logging.getLogger(__name__)
_MIN_CONFIDENCE = 0.55

# Pattern 1 \u2013 architectural:  1/4" = 1'-0"  or  3/4" = 1'  or  1" = 10'
_SCALE_PATTERN = re.compile(
    r"(?P<drawing>\d+(?:\s*\d+/\d+|/\d+)?)\s*[\"''\u201d]?\s*=\s*"
    r"(?P<feet>\d+(?:\.\d+)?)\s*['''\u2019\u2018]"
    r"(?:\s*[-\u2013]\s*(?P<inches>\d+(?:\s*\d+/\d+|/\d+)?)\s*[\"''\u201d]?)?",
    re.IGNORECASE,
)

# Pattern 2 \u2013 metric ratio:  1:100  or  1 : 50
_RATIO_PATTERN = re.compile(
    r"\b1\s*:\s*(?P<ratio>\d+(?:\.\d+)?)\b",
)

# Pattern 3 \u2013 written form:  SCALE 1/4" = 1'-0"  or  Scale: 1"=10'
_SCALE_LABEL_PATTERN = re.compile(
    r"(?:scale|sc\.?)\s*:?\s*"
    r"(?P<drawing>\d+(?:\s*\d+/\d+|/\d+)?)\s*[\"''\u201d]?\s*=\s*"
    r"(?P<feet>\d+(?:\.\d+)?)\s*['''\u2019]"
    r"(?:\s*[-\u2013]\s*(?P<inches>\d+(?:\s*\d+/\d+|/\d+)?)\s*[\"''\u201d]?)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DetectedScale:
    """Detected drawing scale in source page units."""

    pixels_per_unit: float
    unit: str
    label: str


@dataclass(frozen=True)
class PageReview:
    """Automated review result for one page."""

    page_id: str
    detected_scale: DetectedScale | None
    measurements: tuple[Measurement, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class DrawingReview:
    """Automated review result for an entire job."""

    pages: tuple[PageReview, ...]

    @property
    def measurement_count(self) -> int:
        """Return the number of generated measurement suggestions."""
        return sum(len(page.measurements) for page in self.pages)

    @property
    def detected_scale_count(self) -> int:
        """Return the number of pages with an inferred scale."""
        return sum(page.detected_scale is not None for page in self.pages)


@dataclass(frozen=True)
class _Segment:
    orientation: str
    start: Point
    end: Point
    confidence: float

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)


@dataclass(frozen=True)
class _Rectangle:
    points: tuple[Point, Point, Point, Point]
    confidence: float


class _PointLike(Protocol):
    x: float
    y: float


class _RectLike(Protocol):
    x0: float
    y0: float
    x1: float
    y1: float


class _PixmapLike(Protocol):
    samples: bytes
    height: int
    width: int


class _PageLike(Protocol):
    def get_text(self, option: str) -> str:
        """Return extracted page text."""

    def get_drawings(self) -> list[dict[str, object]]:
        """Return page vector drawing commands."""

    def get_pixmap(self, *, colorspace: object, alpha: bool) -> _PixmapLike:
        """Return a grayscale page pixmap."""


def review_job_drawings(job: Job, *, max_measurements_per_page: int = 12) -> DrawingReview:
    """Analyze local drawings and return automated measurement suggestions."""
    page_reviews: list[PageReview] = []
    for page in job.pages:
        page_reviews.append(_review_page(page, max_measurements_per_page=max_measurements_per_page))
    return DrawingReview(pages=tuple(page_reviews))


def apply_drawing_review(job: Job, review: DrawingReview) -> int:
    """Apply automated review output to a job and return added measurements."""
    page_by_id = {page.id: page for page in job.pages}
    for section in job.takeoff_sections:
        section.measurements = [
            measurement
            for measurement in section.measurements
            if measurement.source != "automated-review"
        ]
    existing_ids = {
        measurement.id for section in job.takeoff_sections for measurement in section.measurements
    }
    sections_by_kind: dict[MeasurementKind, TakeoffSection] = {}
    added = 0
    for page_review in review.pages:
        page = page_by_id.get(page_review.page_id)
        if page is None:
            continue
        if page_review.detected_scale is not None and page.scale_pixels_per_unit is None:
            page.scale_pixels_per_unit = page_review.detected_scale.pixels_per_unit
            page.scale_unit = page_review.detected_scale.unit
            page.scale_units = page_review.detected_scale.unit
            page.scale_source = page_review.detected_scale.label
        for measurement in page_review.measurements:
            if measurement.id in existing_ids or measurement.confidence is None:
                continue
            if measurement.confidence < _MIN_CONFIDENCE:
                continue
            section = sections_by_kind.setdefault(
                measurement.kind,
                _ensure_automated_section(job, measurement.kind),
            )
            result = calculate_measurement(measurement.kind, measurement.points, page)
            completed = measurement.model_copy(
                update={
                    "quantity": result.quantity,
                    "unit": result.unit,
                    "secondary_quantity": result.secondary_quantity,
                    "secondary_unit": result.secondary_unit,
                    "order_index": len(section.measurements),
                }
            )
            section.measurements.append(completed)
            existing_ids.add(completed.id)
            added += 1
    return added


def _review_page(page: Page, *, max_measurements_per_page: int) -> PageReview:
    if page.image_path is None:
        return PageReview(
            page_id=page.id,
            detected_scale=None,
            measurements=(),
            notes=("No local drawing file is available for automated review.",),
        )
    try:
        document = pymupdf.open(str(page.image_path))
    except Exception as exc:
        LOGGER.exception("Could not open page for automated review: %s", page.image_path)
        return PageReview(
            page_id=page.id,
            detected_scale=None,
            measurements=(),
            notes=(f"Could not open drawing: {exc}",),
        )

    try:
        source_page = document.load_page(page.source_page_index)
        detected_scale = _detect_scale(source_page)
        segments = _vector_segments(source_page)
        rectangles = _vector_rectangles(source_page)
        notes: list[str] = []
        if segments or rectangles:
            notes.append("Vector linework detected.")
        else:
            segments = _raster_segments(source_page)
            if segments:
                notes.append("Raster linework detected.")
        if detected_scale is None:
            notes.append("No reliable scale note was detected; quantities remain in page units.")
        measurements = [
            _measurement_from_segment(index, page.id, segment)
            for index, segment in enumerate(segments[:max_measurements_per_page], start=1)
        ]
        remaining_slots = max(0, max_measurements_per_page - len(measurements))
        measurements.extend(
            _measurement_from_rectangle(index, page.id, rectangle)
            for index, rectangle in enumerate(rectangles[:remaining_slots], start=1)
        )
        return PageReview(
            page_id=page.id,
            detected_scale=detected_scale,
            measurements=tuple(measurements),
            notes=tuple(notes),
        )
    finally:
        document.close()


def _detect_scale(source_page: _PageLike) -> DetectedScale | None:
    """Try multiple strategies to find the drawing scale."""
    try:
        text = str(source_page.get_text("text"))
    except Exception:
        LOGGER.warning("Could not extract page text during automated review.", exc_info=True)
        return None

    # Strategy 1: explicit "Scale: ..." label (highest priority)
    result = _try_architectural_match(_SCALE_LABEL_PATTERN, text, prefix="scale label")
    if result is not None:
        return result

    # Strategy 2: bare architectural notation  1/4" = 1'-0"
    result = _try_architectural_match(_SCALE_PATTERN, text, prefix="scale note")
    if result is not None:
        return result

    # Strategy 3: metric ratio  1:100
    result = _try_ratio_match(text)
    if result is not None:
        return result

    return None


def _try_architectural_match(pattern: re.Pattern[str], text: str, *, prefix: str) -> DetectedScale | None:
    """Parse an architectural scale match into a DetectedScale."""
    match = pattern.search(text)
    if match is None:
        return None
    drawing_inches = _mixed_number(match.group("drawing"))
    real_feet = float(match.group("feet")) + (_mixed_number(match.group("inches")) / 12.0)
    if drawing_inches <= 0 or real_feet <= 0:
        return None
    # PDF points are 72 per inch; pixels_per_unit = PDF-points per real foot
    pixels_per_unit = (72.0 * drawing_inches) / real_feet
    return DetectedScale(
        pixels_per_unit=pixels_per_unit,
        unit="FT",
        label=f"detected {prefix} {match.group(0).strip()!r}",
    )


def _try_ratio_match(text: str) -> DetectedScale | None:
    """Parse a metric ratio scale (1:100 → 1 mm drawing = 100 mm real)."""
    match = _RATIO_PATTERN.search(text)
    if match is None:
        return None
    ratio = float(match.group("ratio"))
    if ratio <= 0:
        return None
    # 1 PDF point = 1/72 inch = 25.4/72 mm ≈ 0.353 mm
    # drawing unit = 1 PDF point = 0.353 mm of real drawing
    # real unit = 0.353 mm * ratio (in mm), converted to metres
    real_metres = (25.4 / 72.0) * ratio / 1000.0
    pixels_per_metre = 1.0 / real_metres  # PDF points per real metre
    pixels_per_unit = pixels_per_metre  # we'll report unit="M"
    return DetectedScale(
        pixels_per_unit=pixels_per_unit,
        unit="M",
        label=f"detected metric ratio 1:{ratio:.0f}",
    )


def _mixed_number(value: str | None) -> float:
    if value is None:
        return 0.0
    parts = value.strip().split()
    if len(parts) == 2:
        return float(parts[0]) + _fraction(parts[1])
    if "/" in value:
        return _fraction(value.strip())
    return float(value)


def _fraction(value: str) -> float:
    numerator, denominator = value.split("/", maxsplit=1)
    return float(numerator) / float(denominator)


def _vector_segments(source_page: _PageLike) -> list[_Segment]:
    segments: list[_Segment] = []
    for drawing in source_page.get_drawings():
        items = drawing.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, tuple) or not item:
                continue
            command = item[0]
            if (
                command == "l"
                and len(item) >= 3
                and _is_point_like(item[1])
                and _is_point_like(item[2])
            ):
                start = _point_from_fitz(item[1])
                end = _point_from_fitz(item[2])
                segment = _axis_aligned_segment(start, end, confidence=0.96)
                if segment is not None:
                    segments.append(segment)
            if command == "re" and len(item) >= 2 and _is_rect_like(item[1]):
                segments.extend(_segments_from_rect(item[1]))
    return _deduplicate_segments(segments)


def _vector_rectangles(source_page: _PageLike) -> list[_Rectangle]:
    rectangles: list[_Rectangle] = []
    for drawing in source_page.get_drawings():
        items = drawing.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            if item[0] == "re" and _is_rect_like(item[1]):
                rectangles.append(_rectangle_from_rect(item[1]))
    return rectangles


def _point_from_fitz(point: _PointLike) -> Point:
    return Point(x=float(point.x), y=float(point.y))


def _segments_from_rect(rect: _RectLike) -> list[_Segment]:
    left = float(rect.x0)
    top = float(rect.y0)
    right = float(rect.x1)
    bottom = float(rect.y1)
    return [
        _Segment("horizontal", Point(x=left, y=top), Point(x=right, y=top), 0.92),
        _Segment("vertical", Point(x=right, y=top), Point(x=right, y=bottom), 0.92),
        _Segment("horizontal", Point(x=left, y=bottom), Point(x=right, y=bottom), 0.92),
        _Segment("vertical", Point(x=left, y=top), Point(x=left, y=bottom), 0.92),
    ]


def _rectangle_from_rect(rect: _RectLike) -> _Rectangle:
    left = float(rect.x0)
    top = float(rect.y0)
    right = float(rect.x1)
    bottom = float(rect.y1)
    return _Rectangle(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        ),
        confidence=0.92,
    )


def _is_point_like(value: object) -> TypeGuard[_PointLike]:
    return hasattr(value, "x") and hasattr(value, "y")


def _is_rect_like(value: object) -> TypeGuard[_RectLike]:
    return all(hasattr(value, attribute) for attribute in ("x0", "y0", "x1", "y1"))


def _axis_aligned_segment(start: Point, end: Point, *, confidence: float) -> _Segment | None:
    delta_x = abs(end.x - start.x)
    delta_y = abs(end.y - start.y)
    if delta_x < 1 and delta_y < 1:
        return None
    if delta_x >= delta_y * 4:
        return _Segment("horizontal", start, end, confidence)
    if delta_y >= delta_x * 4:
        return _Segment("vertical", start, end, confidence)
    return None


def _raster_segments(source_page: _PageLike) -> list[_Segment]:
    # Render at 2× for better line detection on low-DPI PDFs
    try:
        import pymupdf as fitz  # type: ignore[import-untyped]
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = source_page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
    except Exception:
        pixmap = source_page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)

    gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    # Adaptive threshold: use Otsu-like cutoff rather than fixed 160
    threshold = int(np.percentile(gray, 15))
    threshold = max(60, min(threshold, 180))
    mask = gray < threshold
    # Minimum run length: at least 5% of the page dimension, minimum 30px at 2×
    min_run = max(30, round(max(pixmap.width, pixmap.height) * 0.05))
    segments = _scan_runs(mask, min_run=min_run, horizontal=True)
    segments.extend(_scan_runs(mask, min_run=min_run, horizontal=False))
    # Scale points back to 1× PDF-point space
    scaled = [
        _Segment(
            s.orientation,
            Point(x=s.start.x / 2.0, y=s.start.y / 2.0),
            Point(x=s.end.x / 2.0, y=s.end.y / 2.0),
            s.confidence,
        )
        for s in segments
    ]
    return _deduplicate_segments(scaled)


def _scan_runs(
    mask: npt.NDArray[np.bool_],
    *,
    min_run: int,
    horizontal: bool,
) -> list[_Segment]:
    segments: list[_Segment] = []
    scan_mask = mask if horizontal else mask.T
    for fixed_index, row in enumerate(scan_mask):
        start_index: int | None = None
        for current_index, filled in enumerate(np.append(row, False)):
            if filled and start_index is None:
                start_index = current_index
                continue
            if filled or start_index is None:
                continue
            run_length = current_index - start_index
            if run_length >= min_run:
                if horizontal:
                    start = Point(x=float(start_index), y=float(fixed_index))
                    end = Point(x=float(current_index - 1), y=float(fixed_index))
                    orientation = "horizontal"
                else:
                    start = Point(x=float(fixed_index), y=float(start_index))
                    end = Point(x=float(fixed_index), y=float(current_index - 1))
                    orientation = "vertical"
                segments.append(_Segment(orientation, start, end, 0.72))
            start_index = None
    return segments


def _deduplicate_segments(segments: list[_Segment]) -> list[_Segment]:
    ordered = sorted(segments, key=lambda segment: segment.length, reverse=True)
    kept: list[_Segment] = []
    for candidate in ordered:
        if candidate.length < 1:
            continue
        if any(_segments_overlap(candidate, existing) for existing in kept):
            continue
        kept.append(candidate)
    return kept


def _segments_overlap(first: _Segment, second: _Segment) -> bool:
    if first.orientation != second.orientation:
        return False
    if first.orientation == "horizontal":
        if abs(first.start.y - second.start.y) > 3:
            return False
        return _interval_overlap(first.start.x, first.end.x, second.start.x, second.end.x)
    if abs(first.start.x - second.start.x) > 3:
        return False
    return _interval_overlap(first.start.y, first.end.y, second.start.y, second.end.y)


def _interval_overlap(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> bool:
    lower = max(min(first_start, first_end), min(second_start, second_end))
    upper = min(max(first_start, first_end), max(second_start, second_end))
    return upper >= lower


def _measurement_from_segment(index: int, page_id: str, segment: _Segment) -> Measurement:
    return Measurement(
        id=str(uuid4()),
        name=f"Auto line {index}",
        kind=MeasurementKind.LENGTH,
        page_id=page_id,
        points=[segment.start, segment.end],
        source="automated-review",
        confidence=segment.confidence,
    )


def _measurement_from_rectangle(index: int, page_id: str, rectangle: _Rectangle) -> Measurement:
    return Measurement(
        id=str(uuid4()),
        name=f"Auto area {index}",
        kind=MeasurementKind.AREA,
        page_id=page_id,
        points=list(rectangle.points),
        source="automated-review",
        confidence=rectangle.confidence,
    )


def _ensure_automated_section(job: Job, kind: MeasurementKind) -> TakeoffSection:
    for section in job.takeoff_sections:
        if section.name == f"Automated {kind.value.title()} Review" and section.kind == kind:
            return section
    section = TakeoffSection(
        id=str(uuid4()),
        name=f"Automated {kind.value.title()} Review",
        kind=kind,
        description="Measurements suggested by the local automated drawing review.",
        order_index=len(job.takeoff_sections),
    )
    job.takeoff_sections.append(section)
    return section
