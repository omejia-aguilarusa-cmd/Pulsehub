"""Factory helpers for native Takeoff Pro jobs."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from takeoff_pro.data.models import Job, Page


def create_blank_job(name: str = "Untitled Job") -> Job:
    """Create a blank native job with one drawable page."""
    page = Page(
        id=str(uuid4()),
        name="Blank Page",
        order_index=0,
    )
    return Job(
        id=str(uuid4()),
        name=name,
        measurement_system="English",
        source_root=Path("."),
        pages=[page],
    )
