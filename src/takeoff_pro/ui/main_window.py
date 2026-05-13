"""Main application window."""

from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMainWindow, QWidget


class MainWindow(QMainWindow):
    """Main desktop shell for Takeoff Pro."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Takeoff Pro")
        self.setMinimumSize(QSize(900, 600))
        self.resize(QSize(1200, 800))
        self.setCentralWidget(QWidget(self))
