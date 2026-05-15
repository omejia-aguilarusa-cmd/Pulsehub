"""Main application window."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from takeoff_pro.analysis import DrawingReview, apply_drawing_review, review_job_drawings
from takeoff_pro.core import calculate_measurement
from takeoff_pro.data import (
    DrawingImportError,
    Job,
    Page,
    PersistenceError,
    create_blank_job,
    import_drawings,
    import_job,
    is_native_job_folder,
    load_job,
    save_job,
)
from takeoff_pro.data.models import Measurement, MeasurementKind, Point, TakeoffSection
from takeoff_pro.data.planswift_importer import LegacyImportError
from takeoff_pro.estimate import Assembly, AssemblyComponent, EstimateItem
from takeoff_pro.estimate.pricing import UnitConversionError, price_job
from takeoff_pro.render import PageRenderError, render_page_to_image
from takeoff_pro.reports import export_csv, export_pdf, export_xlsx
from takeoff_pro.ui.commands import AddMeasurementCommand
from takeoff_pro.ui.estimate_dialog import EstimateEditorDialog
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
        self._last_review: DrawingReview | None = None
        self._undo_stack = QUndoStack(self)

        self._sidebar = QListWidget(self)
        self._workspace_stack = QStackedWidget(self)
        self._workspace_title = QLabel("Dashboard", self)
        self._workspace_subtitle = QLabel("No job open", self)
        self._metric_labels: dict[str, QLabel] = {}
        self._document_table = QTableWidget(self)
        self._review_table = QTableWidget(self)
        self._review_notes = QListWidget(self)
        self._estimate_table = QTableWidget(self)
        self._report_summary = QLabel(self)
        self._page_list = QListWidget(self)
        self._page_list.setObjectName("pageList")
        self._measurement_list = QListWidget(self)
        self._measurement_list.setObjectName("measurementList")
        self._viewport = PageViewport(self)
        self._viewport.set_measurement_created_callback(self._on_measurement_created)

        self._create_workspace()
        self._create_actions()
        self._apply_workspace_style()
        self._page_list.currentItemChanged.connect(self._on_page_changed)
        self._sidebar.currentRowChanged.connect(self._on_workspace_changed)
        self._document_table.cellDoubleClicked.connect(self._open_document_row)
        self._viewport.set_placeholder("Open a job folder or upload drawings to begin.")
        self._sidebar.setCurrentRow(0)
        self._refresh_workspace()

    def new_blank_job(self) -> None:
        """Create a blank native job for new takeoff work."""
        self._set_job(create_blank_job())
        self._sidebar.setCurrentRow(2)

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
        self._sidebar.setCurrentRow(0)

    def import_drawing_files(self, file_paths: Sequence[str | Path]) -> None:
        """Import local PDF or TIFF drawings and run automated review."""
        try:
            job = import_drawings(file_paths)
        except DrawingImportError as exc:
            LOGGER.exception("Could not import drawing files")
            QMessageBox.critical(self, "Upload Drawings", str(exc))
            return
        self._set_job(job)
        self._run_automated_review()
        self._sidebar.setCurrentRow(3)

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

    def export_csv_report(self, file_path: str | Path) -> None:
        """Export the current job as a flat CSV report."""
        if self._job is None:
            self._show_status("Open a job before exporting reports.")
            return
        try:
            output_path = export_csv(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            LOGGER.exception("Could not export CSV report to %s", file_path)
            QMessageBox.critical(self, "Export CSV Report", str(exc))
            return
        self._show_status(f"Exported CSV report: {output_path.name}.")

    def export_xlsx_report(self, file_path: str | Path) -> None:
        """Export the current job as an XLSX workbook report."""
        if self._job is None:
            self._show_status("Open a job before exporting reports.")
            return
        try:
            output_path = export_xlsx(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            LOGGER.exception("Could not export XLSX report to %s", file_path)
            QMessageBox.critical(self, "Export XLSX Report", str(exc))
            return
        self._show_status(f"Exported XLSX report: {output_path.name}.")

    def export_pdf_report(self, file_path: str | Path) -> None:
        """Export the current job as a PDF report."""
        if self._job is None:
            self._show_status("Open a job before exporting reports.")
            return
        try:
            output_path = export_pdf(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            LOGGER.exception("Could not export PDF report to %s", file_path)
            QMessageBox.critical(self, "Export PDF Report", str(exc))
            return
        self._show_status(f"Exported PDF report: {output_path.name}.")

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

    def _create_workspace(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar_frame = QFrame(root)
        sidebar_frame.setObjectName("sidebarFrame")
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(16, 18, 16, 18)
        sidebar_layout.setSpacing(12)

        brand = QLabel("Takeoff Pro", sidebar_frame)
        brand.setObjectName("brandLabel")
        sidebar_layout.addWidget(brand)

        for label, callback in (
            ("New blank job", self.new_blank_job),
            ("Upload drawings", self._choose_drawing_files),
            ("Open job folder", self._choose_job_folder),
        ):
            button = QPushButton(label, sidebar_frame)
            button.clicked.connect(callback)
            sidebar_layout.addWidget(button)

        self._sidebar.setObjectName("workspaceNav")
        self._sidebar.addItems(
            ["Dashboard", "Documents", "Takeoff", "AI Review", "Estimate", "Reports"]
        )
        sidebar_layout.addWidget(self._sidebar, 1)

        content = QWidget(root)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 24)
        content_layout.setSpacing(16)
        self._workspace_title.setObjectName("workspaceTitle")
        self._workspace_subtitle.setObjectName("workspaceSubtitle")
        content_layout.addWidget(self._workspace_title)
        content_layout.addWidget(self._workspace_subtitle)
        content_layout.addWidget(self._workspace_stack, 1)

        self._workspace_stack.addWidget(self._build_dashboard_page())
        self._workspace_stack.addWidget(self._build_documents_page())
        self._workspace_stack.addWidget(self._build_takeoff_page())
        self._workspace_stack.addWidget(self._build_review_page())
        self._workspace_stack.addWidget(self._build_estimate_page())
        self._workspace_stack.addWidget(self._build_reports_page())

        root_layout.addWidget(sidebar_frame)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        metric_row = QHBoxLayout()
        for key, label in (
            ("pages", "Pages"),
            ("measurements", "Measurements"),
            ("scaled_pages", "Scaled pages"),
            ("estimate_total", "Estimate total"),
        ):
            frame, value = self._metric_frame(label)
            self._metric_labels[key] = value
            metric_row.addWidget(frame)
        layout.addLayout(metric_row)

        quick_actions = QHBoxLayout()
        for label, callback in (
            ("Upload drawings", self._choose_drawing_files),
            ("Open job folder", self._choose_job_folder),
            ("Run AI review", self._run_automated_review),
        ):
            button = QPushButton(label, page)
            button.clicked.connect(callback)
            quick_actions.addWidget(button)
        quick_actions.addStretch(1)
        layout.addLayout(quick_actions)

        self._dashboard_sections = QTableWidget(page)
        self._configure_table(
            self._dashboard_sections,
            ["Section", "Kind", "Measurements", "Quantity"],
        )
        layout.addWidget(self._dashboard_sections, 1)
        return page

    def _build_documents_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        for label, callback in (
            ("Upload drawings", self._choose_drawing_files),
            ("Open job folder", self._choose_job_folder),
        ):
            button = QPushButton(label, page)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._configure_table(
            self._document_table,
            ["Page", "Source", "Source page", "Scale", "Status"],
        )
        layout.addWidget(self._document_table, 1)
        return page

    def _build_takeoff_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(page)
        splitter.addWidget(self._page_list)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._measurement_list)
        splitter.setSizes([240, 760, 280])
        layout.addWidget(splitter)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        run_button = QPushButton("Run review", page)
        run_button.clicked.connect(self._run_automated_review)
        actions.addWidget(run_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._configure_table(
            self._review_table,
            ["Page", "Scale source", "Suggested measurements", "Applied measurements"],
        )
        layout.addWidget(self._review_table, 2)
        layout.addWidget(QLabel("Review notes", page))
        layout.addWidget(self._review_notes, 1)
        return page

    def _build_estimate_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        for label, callback in (
            ("Items and assemblies", self._edit_estimate_library),
            ("Attach first item", self._attach_first_item),
            ("Attach first assembly", self._attach_first_assembly),
        ):
            button = QPushButton(label, page)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._configure_table(
            self._estimate_table,
            ["Item", "Description", "Quantity", "Unit", "Unit cost", "Total"],
        )
        layout.addWidget(self._estimate_table, 1)
        return page

    def _build_reports_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._report_summary.setWordWrap(True)
        layout.addWidget(self._report_summary)
        for label, callback in (
            ("Export CSV", self._choose_csv_report),
            ("Export XLSX", self._choose_xlsx_report),
            ("Export PDF", self._choose_pdf_report),
        ):
            button = QPushButton(label, page)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _metric_frame(self, label: str) -> tuple[QFrame, QLabel]:
        frame = QFrame(self)
        frame.setObjectName("metricFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        caption = QLabel(label, frame)
        caption.setObjectName("metricCaption")
        value = QLabel("0", frame)
        value.setObjectName("metricValue")
        layout.addWidget(caption)
        layout.addWidget(value)
        return frame, value

    def _configure_table(self, table: QTableWidget, headers: list[str]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        vertical_header = table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        horizontal_header = table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _apply_workspace_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f5f6f7; }
            #sidebarFrame { background: #202124; min-width: 210px; max-width: 210px; }
            #brandLabel { color: #ffffff; font-size: 21px; font-weight: 700; }
            #workspaceNav {
                background: transparent;
                color: #d1d5db;
                border: 0;
                outline: 0;
            }
            #workspaceNav::item { padding: 10px 12px; margin: 1px 0; }
            #workspaceNav::item:selected {
                background: #0f766e;
                color: #ffffff;
                border-radius: 4px;
            }
            #workspaceTitle { color: #111827; font-size: 24px; font-weight: 700; }
            #workspaceSubtitle { color: #4b5563; }
            #metricFrame {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 6px;
            }
            #metricCaption { color: #4b5563; }
            #metricValue { color: #111827; font-size: 22px; font-weight: 700; }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 8px 12px;
            }
            QPushButton:hover { border-color: #0f766e; }
            QTableWidget, QListWidget {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 6px;
            }
            """
        )

    def _create_actions(self) -> None:
        menu_bar = self.menuBar()
        if menu_bar is None:
            msg = "Main window menu bar is unavailable."
            raise RuntimeError(msg)
        file_menu = menu_bar.addMenu("&File")
        edit_menu = menu_bar.addMenu("&Edit")
        view_menu = menu_bar.addMenu("&View")
        tools_menu = menu_bar.addMenu("&Tools")
        estimate_menu = menu_bar.addMenu("&Estimate")
        reports_menu = menu_bar.addMenu("&Reports")
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
        if not isinstance(estimate_menu, QMenu):
            msg = "Could not create the estimate menu."
            raise TypeError(msg)
        if not isinstance(reports_menu, QMenu):
            msg = "Could not create the reports menu."
            raise TypeError(msg)

        new_action = QAction("&New Blank Job", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_blank_job)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Job Folder...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._choose_job_folder)
        file_menu.addAction(open_action)

        upload_action = QAction("&Upload Drawings...", self)
        upload_action.triggered.connect(self._choose_drawing_files)
        file_menu.addAction(upload_action)

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
        toolbar.addAction(upload_action)
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

        finish_action = QAction("&Finish Measurement", self)
        finish_action.triggered.connect(self._viewport.finish_active_measurement)
        tools_menu.addAction(finish_action)
        toolbar.addAction(finish_action)

        edit_library_action = QAction("&Items and Assemblies...", self)
        edit_library_action.triggered.connect(self._edit_estimate_library)
        estimate_menu.addAction(edit_library_action)

        attach_item_action = QAction("Attach First &Item", self)
        attach_item_action.triggered.connect(self._attach_first_item)
        estimate_menu.addAction(attach_item_action)

        attach_assembly_action = QAction("Attach First &Assembly", self)
        attach_assembly_action.triggered.connect(self._attach_first_assembly)
        estimate_menu.addAction(attach_assembly_action)

        export_csv_action = QAction("Export &CSV...", self)
        export_csv_action.triggered.connect(self._choose_csv_report)
        reports_menu.addAction(export_csv_action)

        export_xlsx_action = QAction("Export &XLSX...", self)
        export_xlsx_action.triggered.connect(self._choose_xlsx_report)
        reports_menu.addAction(export_xlsx_action)

        export_pdf_action = QAction("Export &PDF...", self)
        export_pdf_action.triggered.connect(self._choose_pdf_report)
        reports_menu.addAction(export_pdf_action)

    def attach_estimate_to_section(
        self,
        section_id: str,
        reference_type: str,
        reference_id: str,
    ) -> None:
        """Attach an item or assembly reference to a takeoff section."""
        if self._job is None:
            return
        for section in self._job.takeoff_sections:
            if section.id == section_id:
                section.estimate_reference_type = reference_type
                section.estimate_reference_id = reference_id
                self._refresh_measurement_panel()
                return

    def _choose_job_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Job Folder")
        if folder:
            self.open_job_folder(folder)

    def _choose_drawing_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Upload Drawings",
            "",
            "Drawings (*.pdf *.tif *.tiff)",
        )
        if file_paths:
            self.import_drawing_files(file_paths)

    def _choose_save_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save Native Job Folder")
        if folder:
            self.save_job_folder(folder)

    def _choose_csv_report(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV Report", "", "CSV (*.csv)")
        if file_path:
            self.export_csv_report(_path_with_suffix(file_path, ".csv"))

    def _choose_xlsx_report(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export XLSX Report",
            "",
            "Excel Workbook (*.xlsx)",
        )
        if file_path:
            self.export_xlsx_report(_path_with_suffix(file_path, ".xlsx"))

    def _choose_pdf_report(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Export PDF Report", "", "PDF (*.pdf)")
        if file_path:
            self.export_pdf_report(_path_with_suffix(file_path, ".pdf"))

    def _on_workspace_changed(self, index: int) -> None:
        labels = ["Dashboard", "Documents", "Takeoff", "AI Review", "Estimate", "Reports"]
        if index < 0 or index >= len(labels):
            return
        self._workspace_stack.setCurrentIndex(index)
        self._workspace_title.setText(labels[index])

    def _open_document_row(self, row: int, column: int) -> None:
        _ = column
        if row < 0 or row >= self._page_list.count():
            return
        self._page_list.setCurrentRow(row)
        self._sidebar.setCurrentRow(2)

    def _run_automated_review(self) -> None:
        if self._job is None:
            self._show_status("Open or upload drawings before running review.")
            return
        review = review_job_drawings(self._job)
        added = apply_drawing_review(self._job, review)
        self._last_review = review
        self._recalculate_all_measurements()
        self._refresh_workspace()
        self._show_status(
            f"Automated review found {review.measurement_count} suggestions and applied {added}."
        )

    def _set_job(self, job: Job) -> None:
        self._job = job
        self._current_page = None
        self._pages_by_id = {page.id: page for page in job.pages}
        self._last_review = None
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
        self._refresh_workspace()

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
            image = render_page_to_image(page.image_path, page_index=page.source_page_index)
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
                "secondary_quantity": result.secondary_quantity,
                "secondary_unit": result.secondary_unit,
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
        self._current_page.scale_source = "manual"
        self._recalculate_page_measurements(self._current_page)
        self._show_status(
            f"Scale set: {self._current_page.scale_pixels_per_unit:.4f} px/{dialog.unit()}."
        )

    def _on_job_changed(self) -> None:
        self._refresh_measurement_panel()
        self._refresh_current_page_overlays()
        self._refresh_workspace()

    def _refresh_measurement_panel(self) -> None:
        self._measurement_list.clear()
        if self._job is None:
            return
        for section in self._job.takeoff_sections:
            self._measurement_list.addItem(f"{section.name} ({section.kind.value})")
            if section.estimate_reference_type and section.estimate_reference_id:
                self._measurement_list.addItem(
                    f"  Estimate: {section.estimate_reference_type} {section.estimate_reference_id}"
                )
            for measurement in section.measurements:
                self._measurement_list.addItem(f"  {self._format_measurement(measurement)}")
        try:
            bom_lines = price_job(self._job)
        except UnitConversionError as exc:
            self._measurement_list.addItem(f"Estimate error: {exc}")
            return
        if bom_lines:
            total = sum(line.total_cost for line in bom_lines)
            self._measurement_list.addItem(f"Estimated Total: ${total:.2f}")

    def _refresh_workspace(self) -> None:
        job_name = self._job.name if self._job is not None else "No job open"
        self._workspace_subtitle.setText(job_name)
        self._refresh_dashboard()
        self._refresh_document_table()
        self._refresh_review_panel()
        self._refresh_estimate_table()
        self._refresh_report_summary()

    def _refresh_dashboard(self) -> None:
        if self._job is None:
            for key in ("pages", "measurements", "scaled_pages"):
                self._metric_labels[key].setText("0")
            self._metric_labels["estimate_total"].setText("$0.00")
            self._dashboard_sections.setRowCount(0)
            return
        measurements = [
            measurement
            for section in self._job.takeoff_sections
            for measurement in section.measurements
        ]
        scaled_pages = sum(
            page.scale_pixels_per_unit is not None
            or (page.scale_x is not None and page.scale_y is not None)
            for page in self._job.pages
        )
        self._metric_labels["pages"].setText(str(len(self._job.pages)))
        self._metric_labels["measurements"].setText(str(len(measurements)))
        self._metric_labels["scaled_pages"].setText(str(scaled_pages))
        try:
            total = sum(line.total_cost for line in price_job(self._job))
        except UnitConversionError:
            total = 0.0
        self._metric_labels["estimate_total"].setText(f"${total:.2f}")
        self._dashboard_sections.setRowCount(len(self._job.takeoff_sections))
        for row, section in enumerate(self._job.takeoff_sections):
            quantity = sum(measurement.quantity or 0.0 for measurement in section.measurements)
            unit = next(
                (measurement.unit for measurement in section.measurements if measurement.unit), ""
            )
            values = [
                section.name,
                section.kind.value.title(),
                str(len(section.measurements)),
                f"{quantity:.2f} {unit}".strip(),
            ]
            for column, value in enumerate(values):
                self._dashboard_sections.setItem(row, column, QTableWidgetItem(value))

    def _refresh_document_table(self) -> None:
        pages = self._job.pages if self._job is not None else []
        self._document_table.setRowCount(len(pages))
        for row, page in enumerate(pages):
            source = page.image_path.name if page.image_path is not None else "Blank canvas"
            scale = self._format_page_scale(page)
            status = (
                "Ready"
                if page.image_path is not None or page.source_xml_path is None
                else "Missing file"
            )
            values = [
                page.name,
                source,
                str(page.source_page_index + 1),
                scale,
                status,
            ]
            for column, value in enumerate(values):
                self._document_table.setItem(row, column, QTableWidgetItem(value))

    def _refresh_review_panel(self) -> None:
        page_reviews = self._last_review.pages if self._last_review is not None else ()
        self._review_table.setRowCount(len(page_reviews))
        self._review_notes.clear()
        applied_counts = self._automated_measurement_counts()
        for row, page_review in enumerate(page_reviews):
            page = self._pages_by_id.get(page_review.page_id)
            page_name = page.name if page is not None else page_review.page_id
            scale_source = (
                page_review.detected_scale.label
                if page_review.detected_scale is not None
                else "Not detected"
            )
            values = [
                page_name,
                scale_source,
                str(len(page_review.measurements)),
                str(applied_counts.get(page_review.page_id, 0)),
            ]
            for column, value in enumerate(values):
                self._review_table.setItem(row, column, QTableWidgetItem(value))
            for note in page_review.notes:
                self._review_notes.addItem(f"{page_name}: {note}")
        if not page_reviews:
            self._review_notes.addItem(
                "Run review after uploading drawings to generate local suggestions."
            )

    def _refresh_estimate_table(self) -> None:
        if self._job is None:
            self._estimate_table.setRowCount(0)
            return
        try:
            lines = price_job(self._job)
        except UnitConversionError as exc:
            self._estimate_table.setRowCount(1)
            self._estimate_table.setItem(0, 0, QTableWidgetItem("Pricing error"))
            self._estimate_table.setItem(0, 1, QTableWidgetItem(str(exc)))
            return
        self._estimate_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            values = [
                line.item_id,
                line.description,
                f"{line.quantity:.2f}",
                line.unit,
                f"${line.unit_cost:.2f}",
                f"${line.total_cost:.2f}",
            ]
            for column, value in enumerate(values):
                self._estimate_table.setItem(row, column, QTableWidgetItem(value))

    def _refresh_report_summary(self) -> None:
        if self._job is None:
            self._report_summary.setText("Open a job before exporting reports.")
            return
        measurement_count = sum(len(section.measurements) for section in self._job.takeoff_sections)
        self._report_summary.setText(
            f"{self._job.name}: {len(self._job.pages)} pages, "
            f"{measurement_count} measurements, "
            f"{len(self._job.takeoff_sections)} takeoff sections ready for export."
        )

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
        formatted = f"{measurement.name}: {quantity:.2f} {unit}"
        if measurement.secondary_quantity is not None and measurement.secondary_unit is not None:
            formatted += (
                f" | perimeter {measurement.secondary_quantity:.2f} {measurement.secondary_unit}"
            )
        if measurement.source != "manual" and measurement.confidence is not None:
            formatted += f" | {measurement.source} {measurement.confidence:.0%}"
        return formatted

    def _recalculate_page_measurements(self, page: Page) -> None:
        for section in self._job.takeoff_sections if self._job is not None else []:
            for measurement in section.measurements:
                if measurement.page_id != page.id:
                    continue
                result = calculate_measurement(measurement.kind, measurement.points, page)
                measurement.quantity = result.quantity
                measurement.unit = result.unit
                measurement.secondary_quantity = result.secondary_quantity
                measurement.secondary_unit = result.secondary_unit
        self._on_job_changed()

    def _recalculate_all_measurements(self) -> None:
        if self._job is None:
            return
        for page in self._job.pages:
            for section in self._job.takeoff_sections:
                for measurement in section.measurements:
                    if measurement.page_id != page.id:
                        continue
                    result = calculate_measurement(measurement.kind, measurement.points, page)
                    measurement.quantity = result.quantity
                    measurement.unit = result.unit
                    measurement.secondary_quantity = result.secondary_quantity
                    measurement.secondary_unit = result.secondary_unit
        self._refresh_measurement_panel()
        self._refresh_current_page_overlays()

    def _automated_measurement_counts(self) -> dict[str, int]:
        if self._job is None:
            return {}
        counts: dict[str, int] = {}
        for section in self._job.takeoff_sections:
            for measurement in section.measurements:
                if measurement.source != "automated-review" or measurement.page_id is None:
                    continue
                counts[measurement.page_id] = counts.get(measurement.page_id, 0) + 1
        return counts

    def _format_page_scale(self, page: Page) -> str:
        if page.scale_pixels_per_unit is not None and page.scale_unit is not None:
            return f"{page.scale_pixels_per_unit:.4f} px/{page.scale_unit}"
        if page.scale_x is not None and page.scale_y is not None and page.scale_units is not None:
            return f"{page.scale_x:.4f} x {page.scale_y:.4f} px/{page.scale_units}"
        return "Unscaled"

    def _show_status(self, message: str) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message)

    def _edit_estimate_library(self) -> None:
        if self._job is None:
            self._show_status("Open a job before editing estimates.")
            return
        self._ensure_default_estimate_library()
        dialog = EstimateEditorDialog(self._job.items, self._job.assemblies, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._job.items = dialog.items()
            self._job.assemblies = dialog.assemblies()
            self._refresh_measurement_panel()

    def _attach_first_item(self) -> None:
        if self._job is None or not self._job.takeoff_sections:
            return
        self._ensure_default_estimate_library()
        if self._job.items:
            self.attach_estimate_to_section(
                self._job.takeoff_sections[0].id,
                "item",
                self._job.items[0].item_id,
            )

    def _attach_first_assembly(self) -> None:
        if self._job is None or not self._job.takeoff_sections:
            return
        self._ensure_default_estimate_library()
        if self._job.assemblies:
            self.attach_estimate_to_section(
                self._job.takeoff_sections[0].id,
                "assembly",
                self._job.assemblies[0].assembly_id,
            )

    def _ensure_default_estimate_library(self) -> None:
        if self._job is None:
            return
        if not self._job.items:
            self._job.items = [
                EstimateItem(item_id="PAINT", description="Paint", unit="GAL", unit_cost=35.0),
                EstimateItem(item_id="LABOR", description="Labor", unit="HR", unit_cost=65.0),
                EstimateItem(item_id="WALL", description="Wall material", unit="LF", unit_cost=4.5),
            ]
        if not self._job.assemblies:
            self._job.assemblies = [
                Assembly(
                    assembly_id="PAINTED-WALL",
                    name="Painted wall",
                    takeoff_unit="SF",
                    components=[
                        AssemblyComponent(item_id="PAINT", quantity_per_takeoff_unit=0.04),
                        AssemblyComponent(item_id="LABOR", quantity_per_takeoff_unit=0.02),
                    ],
                )
            ]


def _path_with_suffix(file_path: str | Path, suffix: str) -> Path:
    path = Path(file_path)
    if path.suffix:
        return path
    return path.with_suffix(suffix)
