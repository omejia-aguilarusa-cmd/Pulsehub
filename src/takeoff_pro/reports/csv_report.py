"""CSV report export."""

from __future__ import annotations

import csv
from pathlib import Path

from takeoff_pro.data.models import Job
from takeoff_pro.estimate.pricing import price_job
from takeoff_pro.reports.data import build_takeoff_rows


def export_csv(job: Job, path: str | Path) -> Path:
    """Export a flat CSV report."""
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cost_lines = price_job(job)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_type",
                "section",
                "name",
                "kind",
                "quantity",
                "unit",
                "unit_cost",
                "total_cost",
            ],
        )
        writer.writeheader()
        for row in build_takeoff_rows(job):
            writer.writerow(
                {
                    "row_type": "takeoff",
                    "section": row.section_name,
                    "name": row.measurement_name,
                    "kind": row.kind,
                    "quantity": f"{row.quantity:.4f}",
                    "unit": row.unit,
                    "unit_cost": "",
                    "total_cost": "",
                }
            )
        for line in cost_lines:
            writer.writerow(
                {
                    "row_type": "cost",
                    "section": line.section_name,
                    "name": line.description,
                    "kind": line.source_type,
                    "quantity": f"{line.quantity:.4f}",
                    "unit": line.unit,
                    "unit_cost": f"{line.unit_cost:.4f}",
                    "total_cost": f"{line.total_cost:.4f}",
                }
            )
    return output_path
