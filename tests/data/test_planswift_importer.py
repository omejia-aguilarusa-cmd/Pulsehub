from __future__ import annotations

from pathlib import Path

import pytest

from takeoff_pro.data import LegacyImportError, MeasurementKind, import_job, import_jobs

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_job"


def test_import_job_parses_synthetic_fixture() -> None:
    job = import_job(FIXTURE_ROOT)

    assert job.name == "Synthetic Training Job"
    assert job.measurement_system == "English"
    assert job.description == "Synthetic fixture for importer tests"
    assert len(job.pages) == 2
    assert len(job.takeoff_sections) == 3
    assert len(job.autolists) == 1

    first_page = job.pages[0]
    assert first_page.name == "A101 Floor Plan"
    assert first_page.scale_x == 24
    assert first_page.scale_y == 24
    assert first_page.scale_units == "FT"
    assert first_page.image_guid == "{21000000-0000-0000-0000-000000000004}"
    assert first_page.image_path is None

    length_section = job.takeoff_sections[0]
    assert length_section.name == "Wall Length"
    assert length_section.kind == MeasurementKind.LENGTH
    assert length_section.description == "Interior wall run"
    assert length_section.scale_units == "FT"
    assert len(length_section.measurements) == 1

    length_measurement = length_section.measurements[0]
    assert length_measurement.kind == MeasurementKind.LENGTH
    assert length_measurement.page_id == first_page.id
    assert length_measurement.z_order == 1
    assert length_measurement.visible is True
    assert [(point.x, point.y) for point in length_measurement.points] == [(10, 15), (110, 15)]

    area_section = job.takeoff_sections[1]
    assert area_section.kind == MeasurementKind.AREA
    assert len(area_section.measurements[0].points) == 4

    count_section = job.takeoff_sections[2]
    assert count_section.kind == MeasurementKind.COUNT
    assert count_section.measurements[0].page_id == job.pages[1].id
    assert len(count_section.measurements[0].points) == 2


def test_import_jobs_parses_multiple_folders() -> None:
    jobs = import_jobs([FIXTURE_ROOT, FIXTURE_ROOT])

    assert [job.name for job in jobs] == ["Synthetic Training Job", "Synthetic Training Job"]


def test_import_job_allows_missing_root_data_xml(tmp_path: Path) -> None:
    pages = tmp_path / "Pages" / "Only Page"
    pages.mkdir(parents=True)
    (pages / "Data.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Item Class="Page" Name="Only Page" GUID="{50000000-0000-0000-0000-000000000001}">
  <Properties>
    <Property Class="Text" GUID="" Name="Name">Only Page</Property>
    <Property
      Class="Type"
      GUID="{50000000-0000-0000-0000-000000000002}"
      Name="Type"
    >.TIF Page</Property>
    <Property
      Class="Number"
      GUID="{50000000-0000-0000-0000-000000000003}"
      Name="OrderIndex"
    >0</Property>
  </Properties>
</Item>
""",
        encoding="utf-8",
    )

    job = import_job(tmp_path)

    assert job.name == tmp_path.name
    assert job.id == tmp_path.name
    assert [page.name for page in job.pages] == ["Only Page"]


def test_import_job_rejects_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(LegacyImportError):
        import_job(tmp_path / "missing")
