from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image
from PyQt6.QtWidgets import QListWidget
from pytestqt.qtbot import QtBot

from takeoff_pro.ui.main_window import MainWindow
from takeoff_pro.ui.viewport import PageViewport

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_job"


def test_main_window_opens_job_and_switches_pages(tmp_path: Path, qtbot: QtBot) -> None:
    job_root = tmp_path / "sample_job"
    shutil.copytree(FIXTURE_ROOT, job_root)
    _write_tiff(
        job_root / "Pages" / "A101 Floor Plan" / "{21000000-0000-0000-0000-000000000004}.tiff"
    )
    _write_tiff(
        job_root
        / "Pages"
        / "A102 Reflected Ceiling"
        / "{22000000-0000-0000-0000-000000000004}.tiff"
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.open_job_folder(job_root)

    page_list = window.findChild(QListWidget, "pageList")
    viewport = window.findChild(PageViewport, "pageViewport")
    status_bar = window.statusBar()

    assert page_list is not None
    assert viewport is not None
    assert status_bar is not None
    assert page_list.count() == 2
    assert "A101 Floor Plan" in status_bar.currentMessage()

    page_list.setCurrentRow(1)
    assert "A102 Reflected Ceiling" in status_bar.currentMessage()

    viewport.zoom_by(1.2)
    viewport.actual_size()
    viewport.rotate_clockwise()
    viewport.fit_to_window()


def _write_tiff(path: Path) -> None:
    image = Image.new("RGB", (120, 80), "white")
    image.save(path, format="TIFF")
