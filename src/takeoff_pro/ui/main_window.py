"""Main application window — premium redesign."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QMimeData, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QDragEnterEvent, QDropEvent, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
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
    QProgressBar,
    QPushButton,
    QSizePolicy,
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
from takeoff_pro.ui.ai_worker import AIAnalysisWorker
from takeoff_pro.ui.commands import AddMeasurementCommand
from takeoff_pro.ui.estimate_dialog import EstimateEditorDialog
from takeoff_pro.ui.scale_dialog import ScaleCalibrationDialog
from takeoff_pro.ui.viewport import PageViewport

LOGGER = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────────
_BG        = "#FAFAF8"
_PANEL     = "#FFFFFF"
_SOFT      = "#F4F4F2"
_INK1      = "#0E0E0F"
_INK2      = "#3A3A3C"
_INK3      = "#6E6E73"
_INK4      = "#A1A1A6"
_HAIRLINE  = "rgba(15,15,18,0.07)"
_HAIRLINE2 = "rgba(15,15,18,0.12)"
_OK        = "#16a34a"
_OK_BG     = "#f0fdf4"
_WARN      = "#d97706"
_WARN_BG   = "#fffbeb"
_RISK      = "#dc2626"
_RISK_BG   = "#fef2f2"
_INFO      = "#2563eb"
_INFO_BG   = "#eff6ff"


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Main desktop shell for Takeoff Pro."""

    def __init__(self) -> None:
        """Initialise the main window."""
        super().__init__()
        self.setWindowTitle("Takeoff Pro")
        self.setMinimumSize(QSize(980, 660))
        self.resize(QSize(1380, 880))
        self.setAcceptDrops(True)

        self._job: Job | None = None
        self._current_page: Page | None = None
        self._pages_by_id: dict[str, Page] = {}
        self._last_review: DrawingReview | None = None
        self._undo_stack = QUndoStack(self)
        self._ai_worker: AIAnalysisWorker | None = None

        # Widgets populated in _build_* helpers
        self._sidebar = QListWidget(self)
        self._workspace_stack = QStackedWidget(self)
        self._workspace_title = QLabel("Dashboard", self)
        self._workspace_subtitle = QLabel("No job open", self)
        self._metric_labels: dict[str, QLabel] = {}
        self._metric_sub: dict[str, QLabel] = {}
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
        self._apply_stylesheet()
        self._page_list.currentItemChanged.connect(self._on_page_changed)
        self._sidebar.currentRowChanged.connect(self._on_workspace_changed)
        self._document_table.cellDoubleClicked.connect(self._open_document_row)
        self._viewport.set_placeholder("Open a job folder or upload drawings to begin.")
        self._sidebar.setCurrentRow(0)
        self._refresh_workspace()

    # ── Public API ────────────────────────────────────────────────────────────

    def new_blank_job(self) -> None:
        """Create a blank native job."""
        self._set_job(create_blank_job())
        self._sidebar.setCurrentRow(2)

    def open_job_folder(self, folder_path: str | Path) -> None:
        """Open an imported or native job folder."""
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
        """Import drawings and launch background AI analysis."""
        try:
            job = import_drawings(file_paths)
        except DrawingImportError as exc:
            LOGGER.exception("Could not import drawing files")
            QMessageBox.critical(self, "Upload Drawings", str(exc))
            return
        self._set_job(job)
        self._sidebar.setCurrentRow(3)
        self._run_automated_review()

    def save_job_folder(self, folder_path: str | Path) -> None:
        """Save the current job to a native folder."""
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
        """Export flat CSV report."""
        if self._job is None:
            return
        try:
            out = export_csv(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            QMessageBox.critical(self, "Export CSV", str(exc))
            return
        self._show_status(f"Exported CSV: {out.name}.")

    def export_xlsx_report(self, file_path: str | Path) -> None:
        """Export XLSX workbook."""
        if self._job is None:
            return
        try:
            out = export_xlsx(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            QMessageBox.critical(self, "Export XLSX", str(exc))
            return
        self._show_status(f"Exported XLSX: {out.name}.")

    def export_pdf_report(self, file_path: str | Path) -> None:
        """Export PDF report."""
        if self._job is None:
            return
        try:
            out = export_pdf(self._job, file_path)
        except (OSError, UnitConversionError) as exc:
            QMessageBox.critical(self, "Export PDF", str(exc))
            return
        self._show_status(f"Exported PDF: {out.name}.")

    def fit_to_window(self) -> None:
        """Fit the active page to the viewport."""
        self._viewport.fit_to_window()

    def actual_size(self) -> None:
        """Show the active page at 100%."""
        self._viewport.actual_size()

    def rotate_clockwise(self) -> None:
        """Rotate the active page clockwise."""
        self._viewport.rotate_clockwise()

    def start_scale_calibration(self) -> None:
        """Start two-click scale calibration."""
        if self._current_page is None:
            self._show_status("Open a page before setting scale.")
            return
        self._viewport.start_calibration(self._finish_scale_calibration)
        self._show_status("Click two points to define a known distance.")

    def activate_tool(self, kind: MeasurementKind | None) -> None:
        """Activate a takeoff drawing tool."""
        self._viewport.set_active_tool(kind)
        self._show_status(f"{kind.value.title()} tool active." if kind else "Tool cleared.")

    def attach_estimate_to_section(
        self, section_id: str, reference_type: str, reference_id: str
    ) -> None:
        """Attach an item or assembly to a takeoff section."""
        if self._job is None:
            return
        for section in self._job.takeoff_sections:
            if section.id == section_id:
                section.estimate_reference_type = reference_type
                section.estimate_reference_id = reference_id
                self._refresh_measurement_panel()
                return

    # ── Drag-and-drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        """Accept dragged drawing files."""
        if event is None:
            return
        mime: QMimeData = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if any(
                Path(u.toLocalFile()).suffix.casefold() in {".pdf", ".tif", ".tiff"}
                for u in urls
            ):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent | None) -> None:
        """Import dropped drawing files."""
        if event is None:
            return
        mime = event.mimeData()
        if not mime.hasUrls():
            return
        paths = [
            Path(u.toLocalFile())
            for u in mime.urls()
            if Path(u.toLocalFile()).suffix.casefold() in {".pdf", ".tif", ".tiff"}
        ]
        if paths:
            event.acceptProposedAction()
            self.import_drawing_files(paths)

    # ── Layout construction ───────────────────────────────────────────────────

    def _create_workspace(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content_area(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebarFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(0)

        # Brand
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        mark = QLabel("▲")
        mark.setObjectName("brandMark")
        mark.setFixedSize(QSize(28, 28))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        name_lbl = QLabel("Takeoff Pro")
        name_lbl.setObjectName("brandName")
        sub_lbl = QLabel("Estimating Workspace")
        sub_lbl.setObjectName("brandSub")
        name_col.addWidget(name_lbl)
        name_col.addWidget(sub_lbl)
        brand_row.addWidget(mark)
        brand_row.addLayout(name_col)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(20)

        # Quick actions
        for label, callback in (
            ("Upload drawings", self._choose_drawing_files),
            ("Open job folder", self._choose_job_folder),
            ("New blank job",   self.new_blank_job),
        ):
            btn = QPushButton(label)
            btn.setObjectName("sidebarBtn")
            btn.clicked.connect(callback)
            layout.addWidget(btn)
        layout.addSpacing(16)

        # Nav separator label
        sep = QLabel("WORKSPACE")
        sep.setObjectName("navSection")
        layout.addWidget(sep)

        # Nav list
        self._sidebar.setObjectName("workspaceNav")
        nav_items = ["Dashboard", "Documents", "Takeoff", "AI Review", "Estimate", "Reports"]
        self._sidebar.addItems(nav_items)
        layout.addWidget(self._sidebar, 1)

        # User chip at bottom
        layout.addSpacing(8)
        user_frame = QFrame()
        user_frame.setObjectName("userChip")
        uf_layout = QHBoxLayout(user_frame)
        uf_layout.setContentsMargins(8, 6, 8, 6)
        uf_layout.setSpacing(10)
        avatar = QLabel("SR")
        avatar.setObjectName("userAvatar")
        avatar.setFixedSize(QSize(26, 26))
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_meta = QVBoxLayout()
        user_meta.setSpacing(0)
        user_name = QLabel("Sarah Reyes")
        user_name.setObjectName("userName")
        user_org = QLabel("NW Drywall & Finishing")
        user_org.setObjectName("userOrg")
        user_meta.addWidget(user_name)
        user_meta.addWidget(user_org)
        uf_layout.addWidget(avatar)
        uf_layout.addLayout(user_meta)
        layout.addWidget(user_frame)
        return frame

    def _build_content_area(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setObjectName("topBar")
        topbar.setFixedHeight(56)
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        tb_layout.setSpacing(12)
        self._workspace_title.setObjectName("workspaceTitle")
        self._workspace_subtitle.setObjectName("workspaceSubtitle")
        tb_layout.addWidget(self._workspace_title)
        sep = QLabel("/")
        sep.setObjectName("crumbSep")
        tb_layout.addWidget(sep)
        tb_layout.addWidget(self._workspace_subtitle)
        tb_layout.addStretch(1)

        self._ai_status_label = QLabel("")
        self._ai_status_label.setObjectName("aiStatusLabel")
        self._ai_status_label.hide()
        tb_layout.addWidget(self._ai_status_label)

        self._ai_progress = QProgressBar()
        self._ai_progress.setObjectName("aiProgress")
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setFixedWidth(140)
        self._ai_progress.setFixedHeight(6)
        self._ai_progress.hide()
        tb_layout.addWidget(self._ai_progress)

        save_btn = QPushButton("Save job…")
        save_btn.setObjectName("topBtn")
        save_btn.clicked.connect(self._choose_save_folder)
        tb_layout.addWidget(save_btn)

        export_btn = QPushButton("Export")
        export_btn.setObjectName("topBtnPrimary")
        export_btn.clicked.connect(self._quick_export)
        tb_layout.addWidget(export_btn)

        layout.addWidget(topbar)

        # Page stack
        self._workspace_stack.addWidget(self._build_dashboard_page())   # 0
        self._workspace_stack.addWidget(self._build_documents_page())   # 1
        self._workspace_stack.addWidget(self._build_takeoff_page())     # 2
        self._workspace_stack.addWidget(self._build_review_page())      # 3
        self._workspace_stack.addWidget(self._build_estimate_page())    # 4
        self._workspace_stack.addWidget(self._build_reports_page())     # 5
        layout.addWidget(self._workspace_stack, 1)
        return container

    # ── Page builders ─────────────────────────────────────────────────────────

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(12)
        for key, label, sub in (
            ("pages",          "Pages",          "Drawing sheets loaded"),
            ("measurements",   "Measurements",   "Auto + manual takeoff"),
            ("scaled_pages",   "Scaled pages",   "Scale detected or set"),
            ("estimate_total", "Estimate total", "Based on attached items"),
        ):
            card, value, sublabel = self._metric_card(label, sub)
            self._metric_labels[key] = value
            self._metric_sub[key] = sublabel
            metric_row.addWidget(card)
        layout.addLayout(metric_row)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        for label, callback in (
            ("Upload drawings",  self._choose_drawing_files),
            ("Open job folder",  self._choose_job_folder),
            ("Run AI review",    self._run_automated_review),
            ("Edit estimate",    self._edit_estimate_library),
        ):
            btn = QPushButton(label)
            btn.setObjectName("actionBtn")
            btn.clicked.connect(callback)
            quick_row.addWidget(btn)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        # Sections table
        lbl = QLabel("Takeoff sections")
        lbl.setObjectName("sectionLabel")
        layout.addWidget(lbl)
        self._dashboard_sections = QTableWidget(page)
        self._configure_table(
            self._dashboard_sections,
            ["Section", "Kind", "Measurements", "Total quantity", "Confidence"],
        )
        layout.addWidget(self._dashboard_sections, 1)
        return page

    def _build_documents_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        row = QHBoxLayout()
        for label, callback in (
            ("Upload drawings", self._choose_drawing_files),
            ("Open job folder", self._choose_job_folder),
        ):
            btn = QPushButton(label)
            btn.setObjectName("actionBtn")
            btn.clicked.connect(callback)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)

        self._configure_table(
            self._document_table,
            ["Page name", "Source file", "Page #", "Scale", "Status"],
        )
        layout.addWidget(self._document_table, 1)
        return page

    def _build_takeoff_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(page)
        splitter.setObjectName("takeoffSplitter")

        # Page list
        page_panel = QFrame()
        page_panel.setObjectName("sidePanel")
        pp_layout = QVBoxLayout(page_panel)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(0)
        page_lbl = QLabel("Sheets")
        page_lbl.setObjectName("panelHeader")
        pp_layout.addWidget(page_lbl)
        pp_layout.addWidget(self._page_list)
        splitter.addWidget(page_panel)

        splitter.addWidget(self._viewport)

        # Measurement list
        meas_panel = QFrame()
        meas_panel.setObjectName("sidePanel")
        mp_layout = QVBoxLayout(meas_panel)
        mp_layout.setContentsMargins(0, 0, 0, 0)
        mp_layout.setSpacing(0)
        meas_lbl = QLabel("Measurements")
        meas_lbl.setObjectName("panelHeader")
        mp_layout.addWidget(meas_lbl)
        mp_layout.addWidget(self._measurement_list)
        splitter.addWidget(meas_panel)

        splitter.setSizes([220, 800, 300])
        layout.addWidget(splitter)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        row = QHBoxLayout()
        run_btn = QPushButton("Run AI review")
        run_btn.setObjectName("actionBtnPrimary")
        run_btn.clicked.connect(self._run_automated_review)
        row.addWidget(run_btn)

        self._review_progress_label = QLabel("")
        self._review_progress_label.setObjectName("reviewProgressLabel")
        row.addWidget(self._review_progress_label)
        row.addStretch(1)
        layout.addLayout(row)

        self._configure_table(
            self._review_table,
            ["Sheet", "Scale detected", "Suggested", "Applied", "Scale source"],
        )
        layout.addWidget(self._review_table, 2)

        notes_lbl = QLabel("Review notes")
        notes_lbl.setObjectName("sectionLabel")
        layout.addWidget(notes_lbl)
        layout.addWidget(self._review_notes, 1)
        return page

    def _build_estimate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        row = QHBoxLayout()
        for label, callback in (
            ("Items & assemblies", self._edit_estimate_library),
            ("Attach first item",      self._attach_first_item),
            ("Attach first assembly",  self._attach_first_assembly),
        ):
            btn = QPushButton(label)
            btn.setObjectName("actionBtn")
            btn.clicked.connect(callback)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)

        self._configure_table(
            self._estimate_table,
            ["Item ID", "Description", "Quantity", "Unit", "Unit cost", "Total"],
        )
        layout.addWidget(self._estimate_table, 1)

        self._estimate_total_label = QLabel("")
        self._estimate_total_label.setObjectName("estimateTotalLabel")
        layout.addWidget(self._estimate_total_label)
        return page

    def _build_reports_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        self._report_summary.setObjectName("reportSummary")
        self._report_summary.setWordWrap(True)
        layout.addWidget(self._report_summary)

        row = QHBoxLayout()
        for label, callback in (
            ("Export CSV",  self._choose_csv_report),
            ("Export XLSX", self._choose_xlsx_report),
            ("Export PDF",  self._choose_pdf_report),
        ):
            btn = QPushButton(label)
            btn.setObjectName("actionBtn")
            btn.clicked.connect(callback)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _metric_card(self, label: str, sub: str) -> tuple[QFrame, QLabel, QLabel]:
        frame = QFrame()
        frame.setObjectName("metricCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        cap = QLabel(label.upper())
        cap.setObjectName("metricCaption")
        value = QLabel("0")
        value.setObjectName("metricValue")
        sublabel = QLabel(sub)
        sublabel.setObjectName("metricSub")
        layout.addWidget(cap)
        layout.addWidget(value)
        layout.addWidget(sublabel)
        return frame, value, sublabel

    def _configure_table(self, table: QTableWidget, headers: list[str]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.setWordWrap(False)
        vh = table.verticalHeader()
        if vh is not None:
            vh.setVisible(False)
            vh.setDefaultSectionSize(38)
        hh = table.horizontalHeader()
        if hh is not None:
            hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            hh.setHighlightSections(False)

    # ── Menu & toolbar ────────────────────────────────────────────────────────

    def _create_actions(self) -> None:
        mb = self.menuBar()
        if mb is None:
            return
        file_menu = mb.addMenu("&File")
        edit_menu = mb.addMenu("&Edit")
        view_menu = mb.addMenu("&View")
        tools_menu = mb.addMenu("&Tools")
        estimate_menu = mb.addMenu("&Estimate")
        reports_menu = mb.addMenu("&Reports")
        if not isinstance(file_menu, QMenu):
            return

        new_act = QAction("&New Blank Job", self)
        new_act.setShortcut(QKeySequence.StandardKey.New)
        new_act.triggered.connect(self.new_blank_job)
        file_menu.addAction(new_act)

        open_act = QAction("&Open Job Folder…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._choose_job_folder)
        file_menu.addAction(open_act)

        upload_act = QAction("&Upload Drawings…", self)
        upload_act.triggered.connect(self._choose_drawing_files)
        file_menu.addAction(upload_act)

        save_act = QAction("&Save As Native Job…", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._choose_save_folder)
        file_menu.addAction(save_act)

        if isinstance(edit_menu, QMenu):
            undo_act = self._undo_stack.createUndoAction(self, "&Undo")
            if undo_act:
                undo_act.setShortcut(QKeySequence.StandardKey.Undo)
                edit_menu.addAction(undo_act)
            redo_act = self._undo_stack.createRedoAction(self, "&Redo")
            if redo_act:
                redo_act.setShortcut(QKeySequence.StandardKey.Redo)
                edit_menu.addAction(redo_act)

        if isinstance(view_menu, QMenu):
            fit_act = QAction("&Fit to Window", self)
            fit_act.setShortcut(QKeySequence("F"))
            fit_act.triggered.connect(self.fit_to_window)
            view_menu.addAction(fit_act)
            actual_act = QAction("&Actual Size", self)
            actual_act.setShortcut(QKeySequence("1"))
            actual_act.triggered.connect(self.actual_size)
            view_menu.addAction(actual_act)
            rotate_act = QAction("&Rotate Clockwise", self)
            rotate_act.setShortcut(QKeySequence("R"))
            rotate_act.triggered.connect(self.rotate_clockwise)
            view_menu.addAction(rotate_act)

        scale_act = QAction("&Set Scale", self)
        scale_act.triggered.connect(self.start_scale_calibration)
        if isinstance(tools_menu, QMenu):
            tools_menu.addAction(scale_act)

        # Toolbar
        toolbar = QToolBar("Takeoff Tools", self)
        toolbar.setObjectName("takeoffToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(14, 14))
        self.addToolBar(toolbar)
        toolbar.addAction(new_act)
        toolbar.addAction(open_act)
        toolbar.addAction(upload_act)
        toolbar.addAction(save_act)
        toolbar.addSeparator()

        tool_group = QActionGroup(self)
        for label, kind in (
            ("Length ↗", MeasurementKind.LENGTH),
            ("Area ▪", MeasurementKind.AREA),
            ("Count •", MeasurementKind.COUNT),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(
                lambda checked, k=kind: self._activate_tool(k, checked)
            )
            tool_group.addAction(act)
            toolbar.addAction(act)
            if isinstance(tools_menu, QMenu):
                tools_menu.addAction(act)
        toolbar.addAction(scale_act)

        finish_act = QAction("Finish", self)
        finish_act.triggered.connect(self._viewport.finish_active_measurement)
        toolbar.addAction(finish_act)
        if isinstance(tools_menu, QMenu):
            tools_menu.addAction(finish_act)

        if isinstance(estimate_menu, QMenu):
            edit_lib_act = QAction("&Items and Assemblies…", self)
            edit_lib_act.triggered.connect(self._edit_estimate_library)
            estimate_menu.addAction(edit_lib_act)
            attach_item = QAction("Attach First &Item", self)
            attach_item.triggered.connect(self._attach_first_item)
            estimate_menu.addAction(attach_item)
            attach_asm = QAction("Attach First &Assembly", self)
            attach_asm.triggered.connect(self._attach_first_assembly)
            estimate_menu.addAction(attach_asm)

        if isinstance(reports_menu, QMenu):
            for label, callback in (
                ("Export &CSV…",  self._choose_csv_report),
                ("Export &XLSX…", self._choose_xlsx_report),
                ("Export &PDF…",  self._choose_pdf_report),
            ):
                act = QAction(label, self)
                act.triggered.connect(callback)
                reports_menu.addAction(act)

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow {{ background: {_BG}; }}

            /* ── Sidebar ──────────────────────────────────────────── */
            #sidebarFrame {{
                background: {_SOFT};
                border-right: 1px solid {_HAIRLINE};
                min-width: 220px;
                max-width: 220px;
            }}
            #brandMark {{
                background: {_INK1};
                color: white;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 700;
            }}
            #brandName {{
                font-size: 13.5px;
                font-weight: 700;
                color: {_INK1};
                letter-spacing: -0.3px;
            }}
            #brandSub {{
                font-size: 10px;
                color: {_INK3};
            }}
            #navSection {{
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.06em;
                color: {_INK4};
                padding: 4px 10px 4px;
                text-transform: uppercase;
            }}
            #sidebarBtn {{
                background: transparent;
                border: 1px solid {_HAIRLINE2};
                border-radius: 7px;
                color: {_INK2};
                font-size: 12.5px;
                height: 30px;
                padding: 0 12px;
                text-align: left;
                margin-bottom: 4px;
            }}
            #sidebarBtn:hover {{ background: {_PANEL}; color: {_INK1}; }}
            #workspaceNav {{
                background: transparent;
                border: 0;
                outline: 0;
                color: {_INK2};
                font-size: 13px;
            }}
            #workspaceNav::item {{
                padding: 7px 10px;
                margin: 1px 0;
                border-radius: 7px;
            }}
            #workspaceNav::item:hover {{
                background: rgba(15,15,18,0.04);
                color: {_INK1};
            }}
            #workspaceNav::item:selected {{
                background: {_PANEL};
                color: {_INK1};
                font-weight: 500;
            }}
            #userChip {{ border-radius: 8px; }}
            #userChip:hover {{ background: rgba(15,15,18,0.04); }}
            #userAvatar {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #d6d3c8, stop:1 #6e6e73);
                color: white;
                border-radius: 13px;
                font-size: 10px;
                font-weight: 700;
            }}
            #userName {{ font-size: 12.5px; font-weight: 500; color: {_INK1}; }}
            #userOrg  {{ font-size: 10.5px; color: {_INK3}; }}

            /* ── Top bar ──────────────────────────────────────────── */
            #topBar {{
                background: rgba(255,255,255,0.82);
                border-bottom: 1px solid {_HAIRLINE};
            }}
            #workspaceTitle {{
                font-size: 13px;
                font-weight: 500;
                color: {_INK1};
            }}
            #crumbSep {{ color: {_INK4}; font-size: 13px; }}
            #workspaceSubtitle {{ font-size: 13px; color: {_INK3}; }}
            #aiStatusLabel {{ font-size: 11.5px; color: {_INK3}; }}
            #aiProgress {{
                border: none;
                border-radius: 3px;
                background: {_SOFT};
            }}
            #aiProgress::chunk {{ background: {_INK1}; border-radius: 3px; }}
            #topBtn {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE2};
                border-radius: 8px;
                font-size: 12.5px;
                color: {_INK1};
                height: 30px;
                padding: 0 12px;
            }}
            #topBtn:hover {{ background: {_SOFT}; }}
            #topBtnPrimary {{
                background: {_INK1};
                border: 1px solid {_INK1};
                border-radius: 8px;
                font-size: 12.5px;
                color: white;
                height: 30px;
                padding: 0 14px;
            }}
            #topBtnPrimary:hover {{ background: #000; }}

            /* ── Metric cards ──────────────────────────────────────── */
            #metricCard {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE};
                border-radius: 12px;
            }}
            #metricCaption {{
                font-size: 10.5px;
                font-weight: 600;
                letter-spacing: 0.07em;
                color: {_INK3};
            }}
            #metricValue {{
                font-size: 26px;
                font-weight: 500;
                color: {_INK1};
                letter-spacing: -0.5px;
            }}
            #metricSub {{ font-size: 11px; color: {_INK4}; }}

            /* ── Action buttons ────────────────────────────────────── */
            #actionBtn {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE2};
                border-radius: 8px;
                font-size: 12.5px;
                color: {_INK1};
                height: 32px;
                padding: 0 14px;
            }}
            #actionBtn:hover {{ background: {_SOFT}; }}
            #actionBtnPrimary {{
                background: {_INK1};
                border: 1px solid {_INK1};
                border-radius: 8px;
                font-size: 12.5px;
                color: white;
                height: 32px;
                padding: 0 14px;
            }}
            #actionBtnPrimary:hover {{ background: #000; }}

            /* ── Labels ────────────────────────────────────────────── */
            #sectionLabel {{
                font-size: 13px;
                font-weight: 500;
                color: {_INK1};
            }}
            #reportSummary {{ font-size: 13px; color: {_INK2}; }}
            #estimateTotalLabel {{
                font-size: 15px;
                font-weight: 600;
                color: {_INK1};
                padding: 8px 0;
            }}
            #reviewProgressLabel {{ font-size: 12px; color: {_INK3}; }}

            /* ── Tables ────────────────────────────────────────────── */
            QTableWidget {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE};
                border-radius: 12px;
                gridline-color: transparent;
                font-size: 12.5px;
                color: {_INK1};
                selection-background-color: rgba(15,15,18,0.04);
                selection-color: {_INK1};
            }}
            QHeaderView::section {{
                background: {_SOFT};
                color: {_INK3};
                font-size: 10.5px;
                font-weight: 600;
                letter-spacing: 0.07em;
                text-transform: uppercase;
                border: none;
                border-bottom: 1px solid {_HAIRLINE};
                padding: 8px 14px;
            }}
            QTableWidget::item {{ padding: 0 14px; border-bottom: 1px solid {_HAIRLINE}; }}
            QTableWidget::item:selected {{ background: rgba(15,15,18,0.03); }}

            /* ── List widgets ──────────────────────────────────────── */
            QListWidget {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE};
                border-radius: 10px;
                font-size: 12.5px;
                color: {_INK2};
                outline: 0;
            }}
            QListWidget::item {{ padding: 7px 12px; }}
            QListWidget::item:selected {{
                background: rgba(15,15,18,0.05);
                color: {_INK1};
                border-radius: 6px;
            }}
            QListWidget::item:hover {{ background: rgba(15,15,18,0.03); }}

            /* ── Takeoff panels ────────────────────────────────────── */
            #takeoffSplitter::handle {{ background: {_HAIRLINE}; width: 1px; }}
            #sidePanel {{
                background: {_SOFT};
                border-right: 1px solid {_HAIRLINE};
            }}
            #panelHeader {{
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.07em;
                color: {_INK4};
                padding: 10px 12px 6px;
                text-transform: uppercase;
            }}
            #pageList, #measurementList {{
                border: 0;
                border-radius: 0;
                background: transparent;
            }}
            #pageViewport {{ background: {_BG}; border: 0; }}

            /* ── Toolbar ───────────────────────────────────────────── */
            QToolBar {{
                background: {_PANEL};
                border-bottom: 1px solid {_HAIRLINE};
                spacing: 4px;
                padding: 4px 8px;
            }}
            QToolBar QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
                color: {_INK2};
            }}
            QToolBar QToolButton:hover {{ background: {_SOFT}; }}
            QToolBar QToolButton:checked {{
                background: {_INK1};
                color: white;
            }}

            /* ── Status bar ────────────────────────────────────────── */
            QStatusBar {{ background: {_SOFT}; color: {_INK3}; font-size: 11.5px; }}

            /* ── Scrollbars ────────────────────────────────────────── */
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0,0,0,0.12);
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(0,0,0,0.12);
                border-radius: 4px;
                min-width: 24px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

            /* ── Dialogs ───────────────────────────────────────────── */
            QDialog {{ background: {_PANEL}; }}
            QMessageBox {{ background: {_PANEL}; }}
            QPushButton {{
                background: {_PANEL};
                border: 1px solid {_HAIRLINE2};
                border-radius: 8px;
                font-size: 12.5px;
                color: {_INK1};
                height: 32px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_SOFT}; }}
            QPushButton:default {{
                background: {_INK1};
                color: white;
                border-color: {_INK1};
            }}
            QPushButton:default:hover {{ background: #000; }}
        """)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_workspace_changed(self, index: int) -> None:
        titles = ["Dashboard", "Documents", "Takeoff", "AI Review", "Estimate", "Reports"]
        if 0 <= index < len(titles):
            self._workspace_stack.setCurrentIndex(index)
            self._workspace_title.setText(titles[index])

    def _open_document_row(self, row: int, column: int) -> None:
        _ = column
        if 0 <= row < self._page_list.count():
            self._page_list.setCurrentRow(row)
            self._sidebar.setCurrentRow(2)

    # ── File dialogs ──────────────────────────────────────────────────────────

    def _choose_job_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Job Folder")
        if folder:
            self.open_job_folder(folder)

    def _choose_drawing_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Upload Drawings", "", "Drawings (*.pdf *.tif *.tiff)"
        )
        if paths:
            self.import_drawing_files(paths)

    def _choose_save_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save Native Job Folder")
        if folder:
            self.save_job_folder(folder)

    def _choose_csv_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV Report", "", "CSV (*.csv)")
        if path:
            self.export_csv_report(_path_with_suffix(path, ".csv"))

    def _choose_xlsx_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export XLSX Report", "", "Excel Workbook (*.xlsx)"
        )
        if path:
            self.export_xlsx_report(_path_with_suffix(path, ".xlsx"))

    def _choose_pdf_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF Report", "", "PDF (*.pdf)")
        if path:
            self.export_pdf_report(_path_with_suffix(path, ".pdf"))

    def _quick_export(self) -> None:
        """Export to XLSX — fast one-click export from the top bar."""
        if self._job is None:
            self._show_status("Open a job before exporting.")
            return
        self._choose_xlsx_report()

    # ── AI review ─────────────────────────────────────────────────────────────

    def _run_automated_review(self) -> None:
        if self._job is None:
            self._show_status("Upload or open drawings before running AI review.")
            return
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self._show_status("AI review is already running.")
            return

        self._ai_progress.show()
        self._ai_status_label.setText("AI reviewing drawings…")
        self._ai_status_label.show()
        if hasattr(self, "_review_progress_label"):
            self._review_progress_label.setText("Running…")

        worker = AIAnalysisWorker(self._job)
        worker.progress.connect(self._on_review_progress)
        worker.finished.connect(self._on_review_finished)
        worker.error.connect(self._on_review_error)
        self._ai_worker = worker
        worker.start()

    def _on_review_progress(self, message: str) -> None:
        self._ai_status_label.setText(message)
        if hasattr(self, "_review_progress_label"):
            self._review_progress_label.setText(message)

    def _on_review_finished(self, added: int, review: DrawingReview) -> None:
        self._last_review = review
        self._recalculate_all_measurements()
        self._refresh_workspace()
        self._ai_progress.hide()
        self._ai_status_label.hide()
        msg = (
            f"AI review complete · {review.measurement_count} suggestions · "
            f"{added} applied"
        )
        self._show_status(msg)
        if hasattr(self, "_review_progress_label"):
            self._review_progress_label.setText(
                f"{review.measurement_count} suggested · {added} applied"
            )
        self._ai_worker = None

    def _on_review_error(self, message: str) -> None:
        self._ai_progress.hide()
        self._ai_status_label.hide()
        QMessageBox.critical(self, "AI Review Error", message)
        self._ai_worker = None

    # ── Job state ─────────────────────────────────────────────────────────────

    def _set_job(self, job: Job) -> None:
        self._job = job
        self._current_page = None
        self._pages_by_id = {p.id: p for p in job.pages}
        self._last_review = None
        self._undo_stack.clear()
        self._page_list.clear()
        self._measurement_list.clear()
        for page in job.pages:
            item = QListWidgetItem(page.name)
            item.setData(Qt.ItemDataRole.UserRole, page.id)
            self._page_list.addItem(item)
        self._refresh_measurement_panel()
        self._show_status(f"Opened '{job.name}' · {len(job.pages)} page(s).")
        if job.pages:
            self._page_list.setCurrentRow(0)  # triggers _load_page which updates status
        else:
            self._viewport.set_placeholder("No pages found in this job folder.")
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
        if isinstance(page_id, str):
            page = self._pages_by_id.get(page_id)
            if page is not None:
                self._load_page(page)

    def _load_page(self, page: Page) -> None:
        self._current_page = page
        self._viewport.set_current_page_id(page.id)
        if page.image_path is None:
            self._viewport.set_blank_page(page.canvas_width, page.canvas_height)
            self._refresh_current_page_overlays()
            self._show_status(page.name)
            return
        try:
            image = render_page_to_image(page.image_path, page_index=page.source_page_index)
        except PageRenderError as exc:
            LOGGER.exception("Could not render page %s", page.image_path)
            self._viewport.set_placeholder("Page image could not be rendered.")
            self._show_status(f"{page.name}: {exc}")
            return
        self._viewport.set_image(image)
        self._refresh_current_page_overlays()
        self._show_status(page.name)

    # ── Tools ─────────────────────────────────────────────────────────────────

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
            self._show_status("Scale points must be distinct.")
            return
        dialog = ScaleCalibrationDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._current_page.scale_pixels_per_unit = pixel_distance / dialog.distance()
        self._current_page.scale_unit = dialog.unit()
        self._current_page.scale_units = dialog.unit()
        self._current_page.scale_source = "manual"
        self._recalculate_page_measurements(self._current_page)
        self._refresh_workspace()
        self._show_status(
            f"Scale set: {self._current_page.scale_pixels_per_unit:.4f} px/{dialog.unit()}"
        )

    def _on_job_changed(self) -> None:
        self._refresh_measurement_panel()
        self._refresh_current_page_overlays()
        self._refresh_workspace()

    # ── Refresh helpers ───────────────────────────────────────────────────────

    def _refresh_measurement_panel(self) -> None:
        self._measurement_list.clear()
        if self._job is None:
            return
        for section in self._job.takeoff_sections:
            self._measurement_list.addItem(f"▸  {section.name}  ({section.kind.value})")
            if section.estimate_reference_type and section.estimate_reference_id:
                self._measurement_list.addItem(
                    f"     └ {section.estimate_reference_type} · {section.estimate_reference_id}"
                )
            for m in section.measurements:
                self._measurement_list.addItem(f"     {self._format_measurement(m)}")
        try:
            lines = price_job(self._job)
        except UnitConversionError as exc:
            self._measurement_list.addItem(f"Pricing error: {exc}")
            return
        if lines:
            total = sum(line.total_cost for line in lines)
            self._measurement_list.addItem(f"  Total: ${total:,.2f}")

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
            self._metric_labels["estimate_total"].setText("$0")
            self._dashboard_sections.setRowCount(0)
            return

        all_measurements = [
            m for s in self._job.takeoff_sections for m in s.measurements
        ]
        scaled = sum(
            (
                p.scale_pixels_per_unit is not None
                or (p.scale_x is not None and p.scale_y is not None)
            )
            for p in self._job.pages
        )
        self._metric_labels["pages"].setText(str(len(self._job.pages)))
        self._metric_labels["measurements"].setText(str(len(all_measurements)))
        self._metric_labels["scaled_pages"].setText(str(scaled))

        try:
            total = sum(line.total_cost for line in price_job(self._job))
        except UnitConversionError:
            total = 0.0
        self._metric_labels["estimate_total"].setText(f"${total:,.0f}")

        rows = self._job.takeoff_sections
        self._dashboard_sections.setRowCount(len(rows))
        for row, section in enumerate(rows):
            qty = sum(m.quantity or 0.0 for m in section.measurements)
            unit = next((m.unit for m in section.measurements if m.unit), "")
            avg_conf = (
                sum(m.confidence or 1.0 for m in section.measurements) / len(section.measurements)
                if section.measurements
                else None
            )
            conf_text = f"{avg_conf:.0%}" if avg_conf is not None else "—"
            values = [
                section.name,
                section.kind.value.title(),
                str(len(section.measurements)),
                f"{qty:,.2f} {unit}".strip() if qty else "—",
                conf_text,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 4 and avg_conf is not None:
                    item.setForeground(
                        QColor(_OK if avg_conf >= 0.85 else _WARN if avg_conf >= 0.65 else _RISK)
                    )
                self._dashboard_sections.setItem(row, col, item)

    def _refresh_document_table(self) -> None:
        pages = self._job.pages if self._job is not None else []
        self._document_table.setRowCount(len(pages))
        for row, page in enumerate(pages):
            source = page.image_path.name if page.image_path is not None else "Blank canvas"
            scale = self._format_page_scale(page)
            status = "Ready" if page.image_path is not None else "Blank"
            values = [
                page.name, source, str(page.source_page_index + 1), scale, status,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 4:
                    item.setForeground(
                        QColor(_OK if status == "Ready" else _INK3)
                    )
                self._document_table.setItem(row, col, item)

    def _refresh_review_panel(self) -> None:
        page_reviews = self._last_review.pages if self._last_review is not None else ()
        self._review_table.setRowCount(len(page_reviews))
        self._review_notes.clear()
        applied = self._automated_measurement_counts()

        for row, pr in enumerate(page_reviews):
            page = self._pages_by_id.get(pr.page_id)
            name = page.name if page is not None else pr.page_id
            scale_label = pr.detected_scale.label if pr.detected_scale is not None else "Not detected"
            scale_source = "auto" if pr.detected_scale is not None else "—"
            values = [
                name,
                _scale_label_short(pr.detected_scale.pixels_per_unit, pr.detected_scale.unit)
                if pr.detected_scale is not None else "—",
                str(len(pr.measurements)),
                str(applied.get(pr.page_id, 0)),
                scale_label,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 1 and pr.detected_scale is None:
                    item.setForeground(QColor(_WARN))
                self._review_table.setItem(row, col, item)
            for note in pr.notes:
                self._review_notes.addItem(f"{name}: {note}")

        if not page_reviews:
            self._review_notes.addItem(
                "Upload drawings and click 'Run AI review' to generate automatic measurement suggestions."
            )

    def _refresh_estimate_table(self) -> None:
        if self._job is None:
            self._estimate_table.setRowCount(0)
            if hasattr(self, "_estimate_total_label"):
                self._estimate_total_label.setText("")
            return
        try:
            lines = price_job(self._job)
        except UnitConversionError as exc:
            self._estimate_table.setRowCount(1)
            self._estimate_table.setItem(0, 0, QTableWidgetItem("Pricing error"))
            self._estimate_table.setItem(0, 1, QTableWidgetItem(str(exc)))
            return
        self._estimate_table.setRowCount(len(lines))
        total = 0.0
        for row, line in enumerate(lines):
            total += line.total_cost
            values = [
                line.item_id,
                line.description,
                f"{line.quantity:,.2f}",
                line.unit,
                f"${line.unit_cost:,.2f}",
                f"${line.total_cost:,.2f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._estimate_table.setItem(row, col, item)
        if hasattr(self, "_estimate_total_label"):
            self._estimate_total_label.setText(f"Estimated total: ${total:,.2f}")

    def _refresh_report_summary(self) -> None:
        if self._job is None:
            self._report_summary.setText("Open a job before exporting reports.")
            return
        meas_count = sum(len(s.measurements) for s in self._job.takeoff_sections)
        self._report_summary.setText(
            f"{self._job.name} · {len(self._job.pages)} page(s) · "
            f"{meas_count} measurement(s) · "
            f"{len(self._job.takeoff_sections)} section(s) ready for export."
        )

    # ── Overlays & recalc ─────────────────────────────────────────────────────

    def _refresh_current_page_overlays(self) -> None:
        self._viewport.show_measurements(self._measurements_for_current_page())

    def _measurements_for_current_page(self) -> list[Measurement]:
        if self._job is None or self._current_page is None:
            return []
        return [
            m
            for s in self._job.takeoff_sections
            for m in s.measurements
            if m.page_id == self._current_page.id
        ]

    def _recalculate_page_measurements(self, page: Page) -> None:
        for section in self._job.takeoff_sections if self._job is not None else []:
            for m in section.measurements:
                if m.page_id != page.id:
                    continue
                result = calculate_measurement(m.kind, m.points, page)
                m.quantity = result.quantity
                m.unit = result.unit
                m.secondary_quantity = result.secondary_quantity
                m.secondary_unit = result.secondary_unit
        self._on_job_changed()

    def _recalculate_all_measurements(self) -> None:
        if self._job is None:
            return
        for page in self._job.pages:
            for section in self._job.takeoff_sections:
                for m in section.measurements:
                    if m.page_id != page.id:
                        continue
                    result = calculate_measurement(m.kind, m.points, page)
                    m.quantity = result.quantity
                    m.unit = result.unit
                    m.secondary_quantity = result.secondary_quantity
                    m.secondary_unit = result.secondary_unit
        self._refresh_measurement_panel()
        self._refresh_current_page_overlays()

    # ── Estimate library ──────────────────────────────────────────────────────

    def _edit_estimate_library(self) -> None:
        if self._job is None:
            self._show_status("Open a job before editing the estimate library.")
            return
        self._ensure_default_estimate_library()
        dialog = EstimateEditorDialog(self._job.items, self._job.assemblies, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._job.items = dialog.items()
            self._job.assemblies = dialog.assemblies()
            self._refresh_measurement_panel()
            self._refresh_estimate_table()

    def _attach_first_item(self) -> None:
        if self._job is None or not self._job.takeoff_sections:
            return
        self._ensure_default_estimate_library()
        if self._job.items:
            self.attach_estimate_to_section(
                self._job.takeoff_sections[0].id, "item", self._job.items[0].item_id
            )

    def _attach_first_assembly(self) -> None:
        if self._job is None or not self._job.takeoff_sections:
            return
        self._ensure_default_estimate_library()
        if self._job.assemblies:
            self.attach_estimate_to_section(
                self._job.takeoff_sections[0].id, "assembly", self._job.assemblies[0].assembly_id
            )

    def _ensure_default_estimate_library(self) -> None:
        if self._job is None:
            return
        if not self._job.items:
            self._job.items = [
                EstimateItem(item_id="PAINT", description="Paint", unit="GAL", unit_cost=35.0),
                EstimateItem(item_id="LABOR", description="Labor", unit="HR",  unit_cost=65.0),
                EstimateItem(item_id="WALL",  description="Wall material", unit="LF", unit_cost=4.5),
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

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _format_measurement(self, measurement: Measurement) -> str:
        qty = measurement.quantity
        unit = measurement.unit
        if qty is None or unit is None:
            page = self._pages_by_id.get(measurement.page_id or "")
            result = calculate_measurement(measurement.kind, measurement.points, page)
            qty, unit = result.quantity, result.unit
        text = f"{measurement.name}: {qty:,.2f} {unit}"
        if measurement.secondary_quantity is not None and measurement.secondary_unit is not None:
            text += f" | {measurement.secondary_quantity:,.2f} {measurement.secondary_unit}"
        if measurement.source != "manual" and measurement.confidence is not None:
            text += f"  [{measurement.confidence:.0%}]"
        return text

    def _format_page_scale(self, page: Page) -> str:
        if page.scale_pixels_per_unit is not None and page.scale_unit is not None:
            return _scale_label_short(page.scale_pixels_per_unit, page.scale_unit)
        if page.scale_x is not None and page.scale_y is not None and page.scale_units is not None:
            return _scale_label_short(page.scale_x, page.scale_units)
        return "Unscaled"

    def _automated_measurement_counts(self) -> dict[str, int]:
        if self._job is None:
            return {}
        counts: dict[str, int] = {}
        for section in self._job.takeoff_sections:
            for m in section.measurements:
                if m.source != "automated-review" or m.page_id is None:
                    continue
                counts[m.page_id] = counts.get(m.page_id, 0) + 1
        return counts

    def _show_status(self, message: str) -> None:
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(message, 8000)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _path_with_suffix(file_path: str | Path, suffix: str) -> Path:
    path = Path(file_path)
    return path if path.suffix else path.with_suffix(suffix)


def _scale_label_short(pixels_per_unit: float, unit: str) -> str:
    """Return a human-readable scale label, e.g. 1/4″ = 1′."""
    if pixels_per_unit <= 0:
        return "Unknown"
    # pixels here are PDF points (72 pt/in)
    drawing_inches = pixels_per_unit / 72.0
    if unit in {"FT", "FEET", "FOOT"}:
        real_unit = "ft"
        inv = 1.0 / drawing_inches if drawing_inches > 0 else 0
        return f"1″ = {inv:.2g}′" if inv >= 1 else f"1/{round(1/drawing_inches)}″ = 1′"
    return f"{pixels_per_unit:.2f} pt/{unit}"
