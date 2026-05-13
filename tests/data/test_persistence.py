from __future__ import annotations

from pathlib import Path

import pytest

from takeoff_pro.data import PersistenceError, create_blank_job, load_job, save_job
from takeoff_pro.data.models import Measurement, MeasurementKind, Point, TakeoffSection


def test_save_and_load_native_job_round_trips_measurements(tmp_path: Path) -> None:
    job = create_blank_job("Round Trip")
    section = TakeoffSection(id="section-1", name="Length Takeoff", kind=MeasurementKind.LENGTH)
    section.measurements.append(
        Measurement(
            id="measurement-1",
            name="Length",
            kind=MeasurementKind.LENGTH,
            page_id=job.pages[0].id,
            points=[Point(x=1.0, y=2.0), Point(x=11.0, y=2.0)],
            quantity=10.0,
            unit="LF",
        )
    )
    job.takeoff_sections.append(section)

    saved = save_job(job, tmp_path / "round-trip.tkjob")
    loaded = load_job(saved.source_root)

    assert loaded.name == "Round Trip"
    assert loaded.pages[0].id == job.pages[0].id
    assert loaded.takeoff_sections[0].measurements[0].points == [
        Point(x=1.0, y=2.0),
        Point(x=11.0, y=2.0),
    ]
    assert loaded.takeoff_sections[0].measurements[0].quantity == 10.0


def test_load_native_job_rejects_missing_job_file(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError):
        load_job(tmp_path / "missing.tkjob")
