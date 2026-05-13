from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from takeoff_pro.data import load_job
from takeoff_pro.data.models import MeasurementKind
from takeoff_pro.ui.main_window import MainWindow
from takeoff_pro.ui.viewport import PageViewport


def test_length_tool_draws_saves_and_reopens(tmp_path: Path, qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.new_blank_job()
    qtbot.wait(50)
    window.activate_tool(MeasurementKind.LENGTH)

    viewport = window.findChild(PageViewport, "pageViewport")
    assert viewport is not None
    viewport.add_tool_point(120, 120)
    viewport.add_tool_point(220, 120)
    qtbot.wait(50)

    save_folder = tmp_path / "drawn.tkjob"
    window.save_job_folder(save_folder)
    loaded = load_job(save_folder)

    assert len(loaded.takeoff_sections) == 1
    measurement = loaded.takeoff_sections[0].measurements[0]
    assert measurement.kind.value == "length"
    assert len(measurement.points) == 2
    assert measurement.quantity is not None
    assert measurement.quantity > 0

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.open_job_folder(save_folder)
    reloaded = load_job(save_folder)

    assert reloaded.takeoff_sections[0].measurements[0].points == measurement.points
