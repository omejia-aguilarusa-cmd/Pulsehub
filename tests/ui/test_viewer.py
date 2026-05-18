from __future__ import annotations

from pytestqt.qtbot import QtBot

from takeoff_pro.ui.estimator_web_panel import EstimatorWebPanel
from takeoff_pro.ui.main_window import MainWindow


def test_main_window_hosts_only_workspace_panel(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert isinstance(window.centralWidget(), EstimatorWebPanel)
    assert not window.menuBar().actions()
    assert window.statusBar().currentMessage() == ""
