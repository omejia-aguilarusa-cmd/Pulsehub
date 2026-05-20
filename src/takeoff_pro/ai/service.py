"""API-shaped local service for painting AI takeoff runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from takeoff_pro.ai.providers import (
    AiProviderError,
    AiProviderNotConfiguredError,
    provider_from_env,
)
from takeoff_pro.ai.takeoff.prompt_builder import (
    PROMPT_VERSION,
    TakeoffPromptOptions,
    build_painting_takeoff_prompt,
)
from takeoff_pro.ai.takeoff.result_normalizer import (
    AiTakeoffNormalizationError,
    normalize_ai_takeoff_response,
)
from takeoff_pro.ai.takeoff.validation import validate_takeoff_pages
from takeoff_pro.data.models import (
    AiTakeoffRun,
    AiTakeoffStatus,
    AiTakeoffTotals,
    Job,
    Page,
    PageRasterStatus,
)
from takeoff_pro.render.page_rasterizer import PageRasterizationError, rasterize_job_pages


@dataclass(frozen=True)
class AiTakeoffOptions:
    """Options accepted by the painting AI takeoff endpoint shape."""

    ceiling_height_ft: float = 9.0
    include_doors: bool = True
    include_windows: bool = True
    include_trim: bool = True


@dataclass(frozen=True)
class AiTakeoffRequest:
    """Input shape for `POST /api/ai/takeoff/run` equivalent."""

    project_id: str
    page_ids: list[str] | None = None
    scope: str = "painting"
    options: AiTakeoffOptions = field(default_factory=AiTakeoffOptions)


def run_ai_takeoff(job: Job, request: AiTakeoffRequest) -> AiTakeoffRun:
    """Run a painting AI takeoff and append the result to the job."""
    timestamp = datetime.now(UTC).isoformat()
    selected_pages = _selected_pages(job, request)
    page_ids = [page.id for page in selected_pages]
    run = AiTakeoffRun(
        id=str(uuid4()),
        project_id=request.project_id,
        status=AiTakeoffStatus.PROCESSING,
        scope=request.scope,
        prompt_version=PROMPT_VERSION,
        page_ids=page_ids,
        created_at=timestamp,
        updated_at=timestamp,
    )

    if request.scope != "painting":
        run.status = AiTakeoffStatus.FAILED
        run.warnings.append("Only painting AI takeoff is supported in this release.")
        _finish(job, run)
        return run

    try:
        rasterized = rasterize_job_pages(job, page_ids=page_ids)
    except PageRasterizationError as exc:
        run.status = AiTakeoffStatus.FAILED
        run.warnings.append(str(exc))
        _finish(job, run)
        return run

    image_paths = [item.image_path for item in rasterized]
    prompt_options = TakeoffPromptOptions(
        ceiling_height_ft=request.options.ceiling_height_ft,
        include_doors=request.options.include_doors,
        include_windows=request.options.include_windows,
        include_trim=request.options.include_trim,
    )
    prompt = build_painting_takeoff_prompt(selected_pages, prompt_options)

    try:
        provider = provider_from_env()
        run.provider = provider.name
        run.model = provider.model
        if not provider.is_configured():
            run.status = AiTakeoffStatus.NOT_CONFIGURED
            run.totals = AiTakeoffTotals()
            run.warnings.append("AI provider API key is not configured.")
            _finish(job, run)
            return run
        raw_response = provider.run_vision_json(prompt=prompt, image_paths=image_paths)
        run.raw_response = raw_response
        pages, totals, confidence, warnings = normalize_ai_takeoff_response(
            raw_response,
            project_id=job.id,
            page_ids=page_ids,
            ceiling_height_ft=request.options.ceiling_height_ft,
            include_doors=request.options.include_doors,
            include_windows=request.options.include_windows,
            include_trim=request.options.include_trim,
        )
        validation_flags = validate_takeoff_pages(pages)
        run.pages = pages
        run.totals = totals
        run.confidence_score = confidence
        run.warnings = [
            *warnings,
            *[f"{flag.severity}: {flag.message}" for flag in validation_flags],
        ]
        run.status = AiTakeoffStatus.COMPLETE
    except AiProviderNotConfiguredError as exc:
        run.status = AiTakeoffStatus.NOT_CONFIGURED
        run.totals = AiTakeoffTotals()
        run.warnings.append(str(exc))
    except (AiProviderError, AiTakeoffNormalizationError) as exc:
        run.status = AiTakeoffStatus.FAILED
        run.warnings.append(str(exc))

    _finish(job, run)
    return run


def _selected_pages(job: Job, request: AiTakeoffRequest) -> list[Page]:
    requested = set(request.page_ids or [page.id for page in job.pages])
    return [page for page in job.pages if page.id in requested]


def _finish(job: Job, run: AiTakeoffRun) -> None:
    run.updated_at = datetime.now(UTC).isoformat()
    for page in job.pages:
        if page.id in run.page_ids and page.raster_status == PageRasterStatus.PROCESSING:
            page.raster_status = PageRasterStatus.FAILED
            page.raster_error = "AI takeoff run did not finish rasterization."
    job.ai_takeoff_runs.append(run)


def api_shape(run: AiTakeoffRun) -> dict[str, object]:
    """Return the JSON-compatible endpoint response shape."""
    return {
        "projectId": run.project_id,
        "status": run.status.value,
        "pages": [
            {
                "pageId": page.page_id,
                "rooms": [_room_shape(room.model_dump(mode="json")) for room in page.rooms],
                "elements": [
                    _element_shape(element.model_dump(mode="json")) for element in page.elements
                ],
                "measurements": [
                    measurement.model_dump(mode="json") for measurement in page.measurements
                ],
                "warnings": page.warnings,
            }
            for page in run.pages
        ],
        "totals": {
            "floorAreaSf": run.totals.floor_area_sf,
            "wallSf": run.totals.wall_sf,
            "ceilingSf": run.totals.ceiling_sf,
            "doorCount": run.totals.door_count,
            "windowCount": run.totals.window_count,
            "trimLf": run.totals.trim_lf,
        },
        "confidenceScore": run.confidence_score,
        "warnings": run.warnings,
    }


def _room_shape(room: dict[str, object]) -> dict[str, object]:
    return {
        "id": room["id"],
        "name": room["name"],
        "type": room["type"],
        "pageId": room["page_id"],
        "locationDescription": room["location_description"],
        "confidence": room["confidence"],
        "floorAreaSf": room["floor_area_sf"],
        "perimeterFt": room["perimeter_ft"],
        "wallSf": room["wall_sf"],
        "ceilingSf": room["ceiling_sf"],
        "doorCount": room["door_count"],
        "windowCount": room["window_count"],
        "trimLf": room["trim_lf"],
        "assumptions": room["assumptions"],
    }


def _element_shape(element: dict[str, object]) -> dict[str, object]:
    return {
        "type": element["type"],
        "count": element["count"],
        "pageId": element["page_id"],
        "locationDescription": element["location_description"],
        "confidence": element["confidence"],
    }


__all__ = [
    "AiTakeoffOptions",
    "AiTakeoffRequest",
    "api_shape",
    "run_ai_takeoff",
]
