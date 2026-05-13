"""CSV-backed estimating item library helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from takeoff_pro.estimate.models import EstimateItem

ITEM_CSV_FIELDS = ["item_id", "description", "unit", "unit_cost"]


class EstimateLibraryError(RuntimeError):
    """Raised when an estimating library cannot be read or written."""


def load_items_csv(path: str | Path) -> list[EstimateItem]:
    """Load estimate items from a CSV file."""
    csv_path = Path(path).expanduser().resolve()
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                EstimateItem(
                    item_id=row["item_id"],
                    description=row["description"],
                    unit=row["unit"],
                    unit_cost=float(row["unit_cost"]),
                )
                for row in reader
            ]
    except (OSError, KeyError, ValueError) as exc:
        msg = f"Could not load estimating item CSV: {csv_path}"
        raise EstimateLibraryError(msg) from exc


def save_items_csv(items: list[EstimateItem], path: str | Path) -> None:
    """Save estimate items to a CSV file."""
    csv_path = Path(path).expanduser().resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ITEM_CSV_FIELDS)
            writer.writeheader()
            for item in items:
                writer.writerow(
                    {
                        "item_id": item.item_id,
                        "description": item.description,
                        "unit": item.unit,
                        "unit_cost": f"{item.unit_cost:.4f}",
                    }
                )
    except OSError as exc:
        msg = f"Could not save estimating item CSV: {csv_path}"
        raise EstimateLibraryError(msg) from exc
