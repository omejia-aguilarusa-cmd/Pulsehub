"""Main application window."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
)

from takeoff_pro.data import Job, Page, import_job
from takeoff_pro.data.planswift_importer import LegacyImportError
from takeoff_pro.render import PageRenderError, render_page_to_image
from takeoff_pro.ui.viewport import PageViewport

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main desktop shell for Takeoff Pro."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Takeoff Pro")
        self.setMinimumSize(QSize(900, 600))
        self.resize(QSize(1200, 800))
        self._job: Job | None = None
        self._pages_by_id: dict[str, Page] = {}
        self._page_list = QListWidget(self)
        self._page_list.setObjectName("pageList")
        self._viewport = PageViewport(self)

        splitter = QSplitter(self)
        splitter.addWidget(self._page_list)
        splitter.addWidget(self._viewport)
        splitter.setSizes([280, 920])
        self.setCentralWidget(splitter)

        self._create_actions()
        self._page_list.currentItemChanged.connect(self._on_page_changed)
        self._viewport.set_placeholder("Open a job folder to view pages.")

    def open_job_folder(self, folder_path: str | Path) -> None:
        """Open an imported job folder and populate the page list."""
        try:
            job = import_job(folder_path)
        except LegacyImportError as exc:
            LOGGER.exception("Could not import job folder %s", folder_path)
            QMessageBox.critical(self, "Open Job Folder", str(exc))
            return

        self._set_job(job)

    def fit_to_window(self) -> None:
        """Fit the current page to the viewport."""
        self._viewport.fit_to_window()

    def actual_size(self) -> None:
        """Show the current page at 100 percent scale."""
        self._viewport.actual_size()

    def rotate_clockwise(self) -> None:
        """Rotate the current page clockwise."""
        self._viewport.rotate_clockwise()

    def _create_actions(self) -> None:
        menu_bar = self.menuBar()
        if menu_bar is None:
            msg = "Main window menu bar is unavailable."
            raise RuntimeError(msg)
        file_menu = menu_bar.addMenu("&File")
        view_menu = menu_bar.addMenu("&View")
        if not isinstance(file_menu, QMenu) or not isinstance(view_menu, QMenu):
            msg = "Could not create main window menus."
            raise TypeError(msg)

        open_action = QAction("&Open Job Folder...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._choose_job_folder)
        file_menu.addAction(open_action)

        fit_action = QAction("&Fit to Window", self)
        fit_action.setShortcut(QKeySequence("F"))
        fit_action.triggered.connect(self.fit_to_window)
        view_menu.addAction(fit_action)

        actual_size_action = QAction("&Actual Size", self)
        actual_size_action.setShortcut(QKeySequence("1"))
        actual_size_action.triggered.connect(self.actual_size)
        view_menu.addAction(actual_size_action)

        rotate_action = QAction("&Rotate Clockwise", self)
        rotate_action.setShortcut(QKeySequence("R"))
        rotate_action.triggered.connect(self.rotate_clockwise)
        view_menu.addAction(rotate_action)

    def _choose_job_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Job Folder")
        if folder:
            self.open_job_folder(folder)

    def _set_job(self, job: Job) -> None:
        self._job = job
        self._pages_by_id = {page.id: page for page in job.pages}
        self._page_list.clear()

        for page in job.pages:
            item = QListWidgetItem(page.name)
            item.setData(Qt.ItemDataRole.UserRole, page.id)
            self._page_list.addItem(item)

        if job.pages:
            self._show_status(f"Opened {job.name} with {len(job.pages)} pages.")
            self._page_list.setCurrentRow(0)
        else:
            self._viewport.set_placeholder("No pages found in this job folder.")
            self._show_status(f"Opened {job.name} with no pages.")

    def _on_page_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        _ = previous
        if current is None:
            return
        page_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(page_id, str):
            return
        page = self._pages_by_id.get(page_id)
        if page is None:
            return
        self._load_page(page)

    def _load_page(self, page: Page) -> None:
        if page.image_path is None:
            self._viewport.set_placeholder("Page image unavailable.")
            self._show_status(f"{page.name}: image file not found.")
            return

        try:
            image = render_page_to_image(page.image_path)
        except PageRenderError as exc:
            LOGGER.exception("Could not render page image %s", page.image_path)
            self._viewport.set_placeholder("Page image could not be rendered.")
            self._show_status(f"{page.name}: {exc}")
            return

        self._viewport.set_image(image)
        self._show_status(page.name)

    def _show_status(self, message: str) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message)
