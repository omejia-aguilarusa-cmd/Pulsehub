"""Shared report row builders."""

from __future__ import annotations

from dataclasses import dataclass

from takeoff_pro.data.models import Job, Measurement
from takeoff_pro.estimate.pricing import price_job


@dataclass(frozen=True)
class TakeoffReportRow:
    """Flat takeoff detail report row."""

    section_name: str
    measurement_name: str
    kind: str
    quantity: float
    unit: str
    point_count: int


def build_takeoff_rows(job: Job) -> list[TakeoffReportRow]:
    """Build flat takeoff rows from a job."""
    rows: list[TakeoffReportRow] = []
    for section in job.takeoff_sections:
        for measurement in section.measurements:
            rows.append(_measurement_row(section.name, measurement))
    return rows


def job_summary_rows(job: Job) -> list[tuple[str, str]]:
    """Build key-value rows for a job summary."""
    cost_total = sum(line.total_cost for line in price_job(job))
    measurement_count = sum(len(section.measurements) for section in job.takeoff_sections)
    return [
        ("Job", job.name),
        ("Pages", str(len(job.pages))),
        ("Takeoff Sections", str(len(job.takeoff_sections))),
        ("Measurements", str(measurement_count)),
        ("Estimated Total", f"{cost_total:.2f}"),
    ]


def _measurement_row(section_name: str, measurement: Measurement) -> TakeoffReportRow:
    return TakeoffReportRow(
        section_name=section_name,
        measurement_name=measurement.name,
        kind=measurement.kind.value,
        quantity=measurement.quantity or 0.0,
        unit=measurement.unit or "",
        point_count=len(measurement.points),
    )
