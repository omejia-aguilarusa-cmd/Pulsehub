"""Minimal desktop host for the single-workspace Takeoff web application."""

from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMainWindow

from takeoff_pro.ui.estimator_web_panel import EstimatorWebPanel


class MainWindow(QMainWindow):
    """Desktop window that hosts only the production workspace UI."""

    def __init__(self) -> None:
        """Initialise the single-pane application shell."""
        super().__init__()
        self.setWindowTitle("Takeoff Pro")
        self.setMinimumSize(QSize(980, 660))
        self.resize(QSize(1380, 880))
        self.setCentralWidget(EstimatorWebPanel(self))
