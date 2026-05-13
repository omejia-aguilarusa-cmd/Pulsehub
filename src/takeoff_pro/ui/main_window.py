"""Main application window."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QToolBar,
)

from takeoff_pro.core import calculate_measurement
from takeoff_pro.data import (
    Job,
    Page,
    PersistenceError,
    create_blank_job,
    import_job,
    is_native_job_folder,
    load_job,
    save_job,
)
from takeoff_pro.data.models import Measurement, MeasurementKind, Point, TakeoffSection
from takeoff_pro.data.planswift_importer import LegacyImportError
from takeoff_pro.render import PageRenderError, render_page_to_image
from takeoff_pro.ui.commands import AddMeasurementCommand
from takeoff_pro.ui.scale_dialog import ScaleCalibrationDialog
from takeoff_pro.ui.viewport import PageViewport

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main desktop shell for Takeoff Pro."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Takeoff Pro")
        self.setMinimumSize(QSize(900, 600))
        self.resize(QSize(1280, 820))
        self._job: Job | None = None
        self._current_page: Page | None = None
        self._pages_by_id: dict[str, Page] = {}
        self._undo_stack = QUndoStack(self)

        self._page_list = QListWidget(self)
        self._page_list.setObjectName("pageList")
        self._measurement_list = QListWidget(self)
        self._measurement_list.setObjectName("measurementList")
        self._viewport = PageViewport(self)
        self._viewport.set_measurement_created_callback(self._on_measurement_created)

        splitter = QSplitter(self)
        splitter.addWidget(self._page_list)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._measurement_list)
        splitter.setSizes([250, 780, 250])
        self.setCentralWidget(splitter)

        self._create_actions()
        self._page_list.currentItemChanged.connect(self._on_page_changed)
        self._viewport.set_placeholder("Open a job folder to view pages.")

    def new_blank_job(self) -> None:
        """Create a blank native job for new takeoff work."""
        self._set_job(create_blank_job())

    def open_job_folder(self, folder_path: str | Path) -> None:
        """Open an imported or native job folder and populate the page list."""
        try:
            job = (
                load_job(folder_path)
                if is_native_job_folder(folder_path)
                else import_job(folder_path)
            )
        except (LegacyImportError, PersistenceError) as exc:
            LOGGER.exception("Could not open job folder %s", folder_path)
            QMessageBox.critical(self, "Open Job Folder", str(exc))
            return

        self._set_job(job)

    def save_job_folder(self, folder_path: str | Path) -> None:
        """Save the current job to a native `.tkjob` folder."""
        if self._job is None:
            self._show_status("No job is open.")
            return
        try:
            self._job = save_job(self._job, folder_path)
        except PersistenceError as exc:
            LOGGER.exception("Could not save job folder %s", folder_path)
            QMessageBox.critical(self, "Save Job", str(exc))
            return
        self._show_status(f"Saved {self._job.name}.")

    def fit_to_window(self) -> None:
        """Fit the current page to the viewport."""
        self._viewport.fit_to_window()

    def actual_size(self) -> None:
        """Show the current page at 100 percent scale."""
        self._viewport.actual_size()

    def rotate_clockwise(self) -> None:
        """Rotate the current page clockwise."""
        self._viewport.rotate_clockwise()

    def start_scale_calibration(self) -> None:
        """Start two-click page scale calibration."""
        if self._current_page is None:
            self._show_status("Open a page before setting scale.")
            return
        self._viewport.start_calibration(self._finish_scale_calibration)
        self._show_status("Click two points on the page to set scale.")

    def activate_tool(self, kind: MeasurementKind | None) -> None:
        """Activate a takeoff drawing tool."""
        self._viewport.set_active_tool(kind)
        if kind is None:
            self._show_status("Tool cleared.")
        else:
            self._show_status(f"{kind.value.title()} tool active.")

    def _create_actions(self) -> None:
        menu_bar = self.menuBar()
        if menu_bar is None:
            msg = "Main window menu bar is unavailable."
            raise RuntimeError(msg)
        file_menu = menu_bar.addMenu("&File")
        edit_menu = menu_bar.addMenu("&Edit")
        view_menu = menu_bar.addMenu("&View")
        tools_menu = menu_bar.addMenu("&Tools")
        if not isinstance(file_menu, QMenu):
            msg = "Could not create the file menu."
            raise TypeError(msg)
        if not isinstance(edit_menu, QMenu):
            msg = "Could not create the edit menu."
            raise TypeError(msg)
        if not isinstance(view_menu, QMenu):
            msg = "Could not create the view menu."
            raise TypeError(msg)
        if not isinstance(tools_menu, QMenu):
            msg = "Could not create main window menus."
            raise TypeError(msg)

        new_action = QAction("&New Blank Job", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_blank_job)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Job Folder...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._choose_job_folder)
        file_menu.addAction(open_action)

        save_action = QAction("&Save As Native Job...", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._choose_save_folder)
        file_menu.addAction(save_action)

        undo_action = self._undo_stack.createUndoAction(self, "&Undo")
        if undo_action is None:
            msg = "Could not create undo action."
            raise RuntimeError(msg)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        redo_action = self._undo_stack.createRedoAction(self, "&Redo")
        if redo_action is None:
            msg = "Could not create redo action."
            raise RuntimeError(msg)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)

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

        scale_action = QAction("&Set Scale", self)
        scale_action.triggered.connect(self.start_scale_calibration)
        tools_menu.addAction(scale_action)

        toolbar = QToolBar("Takeoff Tools", self)
        toolbar.setObjectName("takeoffToolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(new_action)
        toolbar.addAction(open_action)
        toolbar.addAction(save_action)
        toolbar.addSeparator()

        tool_group = QActionGroup(self)
        for label, kind in (
            ("Length", MeasurementKind.LENGTH),
            ("Area", MeasurementKind.AREA),
            ("Count", MeasurementKind.COUNT),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, active_kind=kind: self._activate_tool(active_kind, checked)
            )
            tool_group.addAction(action)
            toolbar.addAction(action)
            tools_menu.addAction(action)
        toolbar.addAction(scale_action)

    def _choose_job_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Job Folder")
        if folder:
            self.open_job_folder(folder)

    def _choose_save_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save Native Job Folder")
        if folder:
            self.save_job_folder(folder)

    def _set_job(self, job: Job) -> None:
        self._job = job
        self._current_page = None
        self._pages_by_id = {page.id: page for page in job.pages}
        self._undo_stack.clear()
        self._page_list.clear()
        self._measurement_list.clear()

        for page in job.pages:
            item = QListWidgetItem(page.name)
            item.setData(Qt.ItemDataRole.UserRole, page.id)
            self._page_list.addItem(item)

        self._refresh_measurement_panel()
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
        self._current_page = page
        self._viewport.set_current_page_id(page.id)
        if page.image_path is None and page.source_xml_path is None:
            self._viewport.set_blank_page(page.canvas_width, page.canvas_height)
            self._refresh_current_page_overlays()
            self._show_status(page.name)
            return
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
        self._refresh_current_page_overlays()
        self._show_status(page.name)

    def _activate_tool(self, kind: MeasurementKind, checked: bool) -> None:
        self.activate_tool(kind if checked else None)

    def _on_measurement_created(self, measurement: Measurement) -> None:
        if self._job is None or self._current_page is None:
            return
        section = self._ensure_section(measurement.kind)
        result = calculate_measurement(measurement.kind, measurement.points, self._current_page)
        measured = measurement.model_copy(
            update={
                "quantity": result.quantity,
                "unit": result.unit,
                "order_index": len(section.measurements),
            }
        )
        self._undo_stack.push(AddMeasurementCommand(section, measured, self._on_job_changed))

    def _ensure_section(self, kind: MeasurementKind) -> TakeoffSection:
        if self._job is None:
            msg = "No job is open."
            raise RuntimeError(msg)
        for section in self._job.takeoff_sections:
            if section.kind == kind:
                return section
        section = TakeoffSection(
            id=str(uuid4()),
            name=f"{kind.value.title()} Takeoff",
            kind=kind,
            order_index=len(self._job.takeoff_sections),
        )
        self._job.takeoff_sections.append(section)
        return section

    def _finish_scale_calibration(self, points: list[Point]) -> None:
        if self._current_page is None or len(points) != 2:
            return
        pixel_distance = math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)
        if pixel_distance <= 0:
            self._show_status("Scale points must be different.")
            return
        dialog = ScaleCalibrationDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._current_page.scale_pixels_per_unit = pixel_distance / dialog.distance()
        self._current_page.scale_unit = dialog.unit()
        self._current_page.scale_units = dialog.unit()
        self._show_status(
            f"Scale set: {self._current_page.scale_pixels_per_unit:.4f} px/{dialog.unit()}."
        )

    def _on_job_changed(self) -> None:
        self._refresh_measurement_panel()
        self._refresh_current_page_overlays()

    def _refresh_measurement_panel(self) -> None:
        self._measurement_list.clear()
        if self._job is None:
            return
        for section in self._job.takeoff_sections:
            self._measurement_list.addItem(f"{section.name} ({section.kind.value})")
            for measurement in section.measurements:
                self._measurement_list.addItem(f"  {self._format_measurement(measurement)}")

    def _refresh_current_page_overlays(self) -> None:
        self._viewport.show_measurements(self._measurements_for_current_page())

    def _measurements_for_current_page(self) -> list[Measurement]:
        if self._job is None or self._current_page is None:
            return []
        return [
            measurement
            for section in self._job.takeoff_sections
            for measurement in section.measurements
            if measurement.page_id == self._current_page.id
        ]

    def _format_measurement(self, measurement: Measurement) -> str:
        quantity = measurement.quantity
        unit = measurement.unit
        if quantity is None or unit is None:
            page = self._pages_by_id.get(measurement.page_id or "")
            result = calculate_measurement(measurement.kind, measurement.points, page)
            quantity = result.quantity
            unit = result.unit
        return f"{measurement.name}: {quantity:.2f} {unit}"

    def _show_status(self, message: str) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message)
