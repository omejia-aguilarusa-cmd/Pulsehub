from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from takeoff_pro.data import load_job
from takeoff_pro.data.models import MeasurementKind
from takeoff_pro.estimate import EstimateItem
from takeoff_pro.estimate.pricing import price_job
from takeoff_pro.ui.main_window import MainWindow
from takeoff_pro.ui.viewport import PageViewport


def test_length_tool_draws_saves_and_reopens(tmp_path: Path, qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.new_blank_job()
    assert window._job is not None
    window._job.pages[0].scale_pixels_per_unit = 1
    window._job.pages[0].scale_unit = "FT"
    window._job.pages[0].scale_units = "FT"
    qtbot.wait(50)
    window.activate_tool(MeasurementKind.LENGTH)

    viewport = window.findChild(PageViewport, "pageViewport")
    assert viewport is not None
    viewport.add_tool_point(120, 120)
    viewport.add_tool_point(220, 120)
    viewport.finish_active_measurement()
    qtbot.wait(50)

    save_folder = tmp_path / "drawn.tkjob"
    window.save_job_folder(save_folder)
    loaded = load_job(save_folder)

    assert len(loaded.takeoff_sections) == 1
    measurement = loaded.takeoff_sections[0].measurements[0]
    assert measurement.kind.value == "length"
    assert len(measurement.points) == 2
    assert measurement.quantity == 100

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.open_job_folder(save_folder)
    reloaded = load_job(save_folder)

    assert reloaded.takeoff_sections[0].measurements[0].points == measurement.points


def test_section_can_attach_item_and_produce_priced_bom(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_blank_job()
    assert window._job is not None
    window._job.pages[0].scale_pixels_per_unit = 1
    window._job.pages[0].scale_unit = "FT"
    window._job.pages[0].scale_units = "FT"
    window.activate_tool(MeasurementKind.LENGTH)
    viewport = window.findChild(PageViewport, "pageViewport")
    assert viewport is not None

    viewport.add_tool_point(0, 0)
    viewport.add_tool_point(10, 0)
    viewport.finish_active_measurement()

    section = window._job.takeoff_sections[0]
    window._job.items = [EstimateItem(item_id="WALL", description="Wall", unit="LF", unit_cost=4)]
    window.attach_estimate_to_section(section.id, "item", "WALL")
    lines = price_job(window._job)

    assert lines[0].quantity == 10
    assert lines[0].total_cost == 40


def test_length_tool_supports_polylines(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_blank_job()
    assert window._job is not None
    window._job.pages[0].scale_pixels_per_unit = 1
    window._job.pages[0].scale_unit = "FT"
    window._job.pages[0].scale_units = "FT"
    window.activate_tool(MeasurementKind.LENGTH)
    viewport = window.findChild(PageViewport, "pageViewport")
    assert viewport is not None

    viewport.add_tool_point(0, 0)
    viewport.add_tool_point(30, 0)
    viewport.add_tool_point(30, 40)
    viewport.finish_active_measurement()

    measurement = window._job.takeoff_sections[0].measurements[0]
    assert len(measurement.points) == 3
    assert measurement.quantity == 70


def test_recalibration_updates_existing_measurements(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_blank_job()
    assert window._job is not None
    page = window._job.pages[0]
    window.activate_tool(MeasurementKind.LENGTH)
    viewport = window.findChild(PageViewport, "pageViewport")
    assert viewport is not None

    viewport.add_tool_point(0, 0)
    viewport.add_tool_point(10, 0)
    viewport.finish_active_measurement()
    measurement = window._job.takeoff_sections[0].measurements[0]
    assert measurement.unit == "PX"

    page.scale_pixels_per_unit = 2
    page.scale_unit = "FT"
    page.scale_units = "FT"
    window._recalculate_page_measurements(page)

    assert measurement.quantity == 5
    assert measurement.unit == "LF"
