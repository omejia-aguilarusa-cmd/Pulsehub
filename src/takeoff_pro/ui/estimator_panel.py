"""
Estimator workspace panel — tabbed UI for the Senior Estimator analysis engine.

Tabs:
  Summary      Key metrics and benchmark comparison
  Files        Document classification table
  Drywall      Quantity table + methodology
  Paint        Paint scope table
  Pricing      Confirmed prices + normalized metrics
  Benchmarks   Historical benchmark store (all confirmed projects)
  QC Flags     Risk and missing-data flags
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from takeoff_pro.estimator.benchmark_store import ProjectBenchmark, get_store
from takeoff_pro.estimator.document_classifier import DocumentRelevance
from takeoff_pro.estimator.project_analyzer import ProjectAnalysisReport, QCFlag
from takeoff_pro.ui.estimator_worker import EstimatorAnalysisWorker

# Colour palette (shared with main_window)
_OK   = "#16a34a"
_WARN = "#d97706"
_RISK = "#dc2626"
_INK1 = "#0E0E0F"
_INK3 = "#6E6E73"
_SOFT = "#F4F4F2"


class EstimatorPanel(QWidget):
    """Full estimator workspace — drop files, run analysis, view results."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: EstimatorAnalysisWorker | None = None
        self._last_report: Optional[ProjectAnalysisReport] = None
        self.setAcceptDrops(True)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Toolbar row
        bar = QHBoxLayout()
        bar.setSpacing(8)

        upload_btn = QPushButton("Analyze files…")
        upload_btn.setObjectName("actionBtn")
        upload_btn.clicked.connect(self._choose_files)
        bar.addWidget(upload_btn)

        folder_btn = QPushButton("Analyze folder…")
        folder_btn.setObjectName("actionBtn")
        folder_btn.clicked.connect(self._choose_folder)
        bar.addWidget(folder_btn)

        self._status_lbl = QLabel("Drop project files here or click 'Analyze files…'")
        self._status_lbl.setObjectName("aiStatusLabel")
        self._status_lbl.setWordWrap(False)
        bar.addWidget(self._status_lbl, 1)

        self._progress = QProgressBar()
        self._progress.setObjectName("aiProgress")
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        self._progress.setFixedWidth(120)
        self._progress.hide()
        bar.addWidget(self._progress)

        root.addLayout(bar)

        # Drop-zone hint (hidden once a report is loaded)
        self._drop_hint = QLabel(
            "Drag and drop estimate PDFs, takeoff spreadsheets, drawings, or a full project folder."
        )
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setObjectName("reviewProgressLabel")
        root.addWidget(self._drop_hint)

        # Tab widget (hidden until first analysis)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("estimatorTabs")
        self._tabs.hide()

        self._summary_tab  = self._make_tab()
        self._files_tab    = self._make_files_tab()
        self._drywall_tab  = self._make_tab()
        self._paint_tab    = self._make_tab()
        self._pricing_tab  = self._make_tab()
        self._benchmarks_tab = self._make_benchmarks_tab()
        self._qc_tab       = QListWidget()

        self._tabs.addTab(self._summary_tab,    "Summary")
        self._tabs.addTab(self._files_tab,       "Files")
        self._tabs.addTab(self._drywall_tab,     "Drywall")
        self._tabs.addTab(self._paint_tab,       "Paint")
        self._tabs.addTab(self._pricing_tab,     "Pricing")
        self._tabs.addTab(self._benchmarks_tab,  "Benchmarks")
        self._tabs.addTab(self._qc_tab,          "QC Flags")

        root.addWidget(self._tabs, 1)

    def _make_tab(self) -> QWidget:
        w = QWidget()
        QVBoxLayout(w).setContentsMargins(0, 8, 0, 0)
        return w

    def _make_files_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        self._files_table = self._new_table(
            ["File", "Type", "Relevance", "Confidence", "Reason"]
        )
        layout.addWidget(self._files_table)
        return w

    def _make_benchmarks_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        refresh_btn = QPushButton("Refresh benchmarks")
        refresh_btn.setObjectName("actionBtn")
        refresh_btn.clicked.connect(self._refresh_benchmarks)
        layout.addWidget(refresh_btn)
        self._benchmarks_table = self._new_table([
            "Project", "Units", "DW $/Unit", "Paint $/Unit", "Total $/Unit",
            "BF/Unit", "Gal/Unit", "Confidence", "Notes",
        ])
        layout.addWidget(self._benchmarks_table)
        return w

    def _new_table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(False)
        t.setShowGrid(False)
        vh = t.verticalHeader()
        if vh:
            vh.setVisible(False)
            vh.setDefaultSectionSize(34)
        hh = t.horizontalHeader()
        if hh:
            hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            hh.setHighlightSections(False)
        return t

    # ── Drag-and-drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event and event.mimeData().hasUrls():
            event.acceptProposedAction()
        elif event:
            event.ignore()

    def dropEvent(self, event: QDropEvent | None) -> None:
        if event is None:
            return
        mime = event.mimeData()
        if not mime.hasUrls():
            return
        paths: list[Path] = []
        for url in mime.urls():
            p = Path(url.toLocalFile())
            if p.is_file():
                paths.append(p)
            elif p.is_dir():
                paths.extend(
                    f for f in p.rglob("*")
                    if f.is_file() and f.suffix.lower() in {".pdf", ".xlsx", ".xls", ".docx", ".txt"}
                )
        if paths:
            event.acceptProposedAction()
            self._run_analysis(paths)

    # ── File picking ──────────────────────────────────────────────────────────

    def _choose_files(self) -> None:
        paths_str, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Project Files",
            "",
            "Estimates, Takeoffs & Drawings (*.pdf *.xlsx *.xls *.docx *.txt *.csv)",
        )
        if paths_str:
            self._run_analysis([Path(p) for p in paths_str])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if folder:
            paths = [
                f for f in Path(folder).rglob("*")
                if f.is_file() and f.suffix.lower() in {".pdf", ".xlsx", ".xls", ".docx", ".txt"}
            ]
            if paths:
                self._run_analysis(paths)
            else:
                self._status_lbl.setText("No supported files found in folder.")

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _run_analysis(self, paths: list[Path]) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._progress.show()
        self._status_lbl.setText(f"Analyzing {len(paths)} file(s)…")
        self._drop_hint.hide()
        self._tabs.hide()

        worker = EstimatorAnalysisWorker(paths)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        self._worker = worker
        worker.start()

    def _on_progress(self, msg: str) -> None:
        self._status_lbl.setText(msg)

    def _on_finished(self, report: object) -> None:
        self._progress.hide()
        if not isinstance(report, ProjectAnalysisReport):
            return
        self._last_report = report
        self._populate(report)
        self._tabs.show()
        confidence_color = {
            "high": _OK, "medium": _WARN, "low": _RISK
        }.get(report.confidence, _INK3)
        dw = f"${report.drywall_price:,.0f}" if report.drywall_price else "—"
        pt = f"${report.paint_price:,.0f}" if report.paint_price else "—"
        self._status_lbl.setText(
            f"<span style='color:{confidence_color}'>●</span> "
            f"<b>{report.project_name}</b> — DW {dw} · Paint {pt} · "
            f"{len(report.qc_flags)} QC flag(s) · confidence: {report.confidence}"
        )
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._worker = None

    def _on_error(self, msg: str) -> None:
        self._progress.hide()
        self._status_lbl.setText(f"Error: {msg}")
        self._worker = None

    # ── Populate tabs ─────────────────────────────────────────────────────────

    def _populate(self, r: ProjectAnalysisReport) -> None:
        self._populate_summary(r)
        self._populate_files(r)
        self._populate_drywall(r)
        self._populate_paint(r)
        self._populate_pricing(r)
        self._refresh_benchmarks()
        self._populate_qc(r)

    def _populate_summary(self, r: ProjectAnalysisReport) -> None:
        layout = self._summary_tab.layout()
        # Clear previous
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def _row(label: str, value: str, bold: bool = False) -> str:
            style = "font-weight:600;" if bold else ""
            return (
                f"<tr><td style='padding:3px 12px 3px 0;color:{_INK3};'>{label}</td>"
                f"<td style='padding:3px 0;{style}'>{value}</td></tr>"
            )

        conf_color = {"high": _OK, "medium": _WARN, "low": _RISK}.get(r.confidence, _INK3)

        html = f"<table style='font-size:13px;'>"
        html += _row("Project", f"<b>{r.project_name}</b>")
        html += _row("Confidence", f"<span style='color:{conf_color}'>{r.confidence.upper()}</span>")
        html += _row("Units", f"{r.units:,}" if r.units else "Not confirmed")
        html += _row("GSF", f"{r.gsf:,.0f} SF" if r.gsf else "Not confirmed")
        html += _row("Board SF (w/ waste)", f"{r.drywall_board_sf_with_waste:,.0f} SF" if r.drywall_board_sf_with_waste else "Not confirmed")
        html += _row("Paint gal total", f"{r.paint_gal_total:,.0f} gal" if r.paint_gal_total else "Not confirmed")
        html += _row("Drywall price", f"${r.drywall_price:,.0f}" if r.drywall_price else "Cannot confirm")
        html += _row("Paint price", f"${r.paint_price:,.0f}" if r.paint_price else "Cannot confirm")
        html += _row("Total", f"${r.total_price:,.0f}" if r.total_price else "Cannot confirm")
        html += _row("Pricing type", r.pricing_type)
        if r.paint_is_blended:
            html += _row("⚠ Paint scope", "Interior + exterior blended — cannot separate")

        html += "<tr><td colspan=2><hr/></td></tr>"
        html += "<tr><td colspan=2 style='font-weight:600;padding-top:6px;'>Benchmark Comparison</td></tr>"
        for line in r.benchmark_lines:
            html += _row("", line)
        html += "</table>"

        lbl = QLabel(html)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(lbl)
        layout.addStretch(1)

    def _populate_files(self, r: ProjectAnalysisReport) -> None:
        t = self._files_table
        t.setRowCount(len(r.documents))
        relevance_color = {
            DocumentRelevance.RELEVANT: _OK,
            DocumentRelevance.SUPPORTING: _WARN,
            DocumentRelevance.IGNORE: _INK3,
        }
        for row, doc in enumerate(r.documents):
            vals = [
                doc.path.name,
                doc.doc_type,
                doc.relevance,
                f"{doc.classifier_confidence:.0%}",
                doc.reason,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == 2:
                    item.setForeground(QColor(relevance_color.get(doc.relevance, _INK3)))
                t.setItem(row, col, item)

    def _populate_drywall(self, r: ProjectAnalysisReport) -> None:
        layout = self._drywall_tab.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = [
            ("Board SF before waste", _fmt_sf(r.drywall_board_sf_before_waste), "Confirmed from takeoff"),
            ("Board SF with 7% waste", _fmt_sf(r.drywall_board_sf_with_waste), "Confirmed from takeoff"),
            ("Board count (4×8 sheets)", _fmt_n(r.drywall_board_count_4x8), "Total ÷ 32 SF"),
            ("Board count (4×12 sheets)", _fmt_n(r.drywall_board_count_4x12), "Total ÷ 48 SF"),
            ("Board SF / unit", _fmt_ratio(r.metrics.board_sf_per_unit if r.metrics else None), "Target: 4,500–5,500"),
            ("Board SF / GSF", _fmt_ratio(r.metrics.board_sf_per_gsf if r.metrics else None, 2), "Target: 4.0–4.8"),
        ]
        if r.projected_board_sf:
            rows.append(("Projected board SF (methodology)", _fmt_sf(r.projected_board_sf), "3.80 BF/res-GSF + 3.20 BF/nonres-GSF"))

        t = self._new_table(["Metric", "Quantity", "Notes"])
        t.setRowCount(len(rows))
        for i, (label, val, note) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(label))
            t.setItem(i, 1, QTableWidgetItem(val))
            t.setItem(i, 2, QTableWidgetItem(note))
        layout.addWidget(t)
        layout.addStretch(1)

    def _populate_paint(self, r: ProjectAnalysisReport) -> None:
        layout = self._paint_tab.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = [
            ("Total paint gallons", _fmt_gal(r.paint_gal_total), "Incl. 10% waste (MPI)"),
            ("Paint gal / unit", _fmt_ratio(r.metrics.paint_gal_per_unit if r.metrics else None, 1), "Target: 25–35"),
            ("Wall paint SF", _fmt_sf(r.paint_wall_sf), "Per-coat surface"),
            ("Ceiling paint SF", _fmt_sf(r.paint_ceiling_sf), "Per-coat surface"),
            ("Includes exterior", "Yes" if r.includes_exterior else "No", ""),
            ("Includes corridors", "Yes" if r.includes_corridors else "No", ""),
            ("Includes amenities", "Yes" if r.includes_amenities else "No", ""),
            ("Interior/exterior split", "No (blended)" if r.paint_is_blended else "Yes", ""),
        ]
        if r.projected_paint_gal:
            rows.append(("Projected paint gal (methodology)", _fmt_gal(r.projected_paint_gal), "Ratio-based projection"))

        t = self._new_table(["Metric", "Value", "Notes"])
        t.setRowCount(len(rows))
        for i, (label, val, note) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(label))
            t.setItem(i, 1, QTableWidgetItem(val))
            t.setItem(i, 2, QTableWidgetItem(note))
        layout.addWidget(t)
        layout.addStretch(1)

    def _populate_pricing(self, r: ProjectAnalysisReport) -> None:
        layout = self._pricing_tab.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        m = r.metrics
        rows = [
            ("Drywall price", f"${r.drywall_price:,.0f}" if r.drywall_price else "Cannot confirm", "Client-facing"),
            ("Paint price", f"${r.paint_price:,.0f}" if r.paint_price else "Cannot confirm", "Client-facing"),
            ("Total price", f"${r.total_price:,.0f}" if r.total_price else "Cannot confirm", ""),
            ("Pricing type", r.pricing_type, ""),
            ("", "", ""),
            ("DW $/unit", f"${m.drywall_per_unit:,.0f}" if m and m.drywall_per_unit else "—", "= DW price ÷ units"),
            ("DW $/board SF", f"${m.drywall_per_board_sf:.3f}" if m and m.drywall_per_board_sf else "—", "= DW price ÷ board SF w/ waste"),
            ("DW $/GSF", f"${m.drywall_per_gsf:.3f}" if m and m.drywall_per_gsf else "—", "= DW price ÷ project GSF"),
            ("DW labor $/sheet", f"${r.drywall_labor_per_sheet:.0f}" if r.drywall_labor_per_sheet else "—", "Labor only (no material)"),
            ("Paint $/unit", f"${m.paint_per_unit:,.0f}" if m and m.paint_per_unit else "—", "= Paint price ÷ units"),
            ("Paint $/GSF", f"${m.paint_per_gsf:.3f}" if m and m.paint_per_gsf else "—", "= Paint price ÷ project GSF"),
            ("Total $/unit", f"${m.total_per_unit:,.0f}" if m and m.total_per_unit else "—", "= Total ÷ units"),
            ("DW % of total", f"{m.drywall_pct:.1f}%" if m and m.drywall_pct else "—", ""),
            ("Paint % of total", f"{m.paint_pct:.1f}%" if m and m.paint_pct else "—", ""),
        ]

        if r.pricing_warnings:
            rows.append(("", "", ""))
            for w in r.pricing_warnings:
                rows.append(("⚠ Warning", w[:80], ""))

        t = self._new_table(["Metric", "Value", "Formula / Notes"])
        t.setRowCount(len(rows))
        for i, (label, val, note) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(val)
            if "Cannot confirm" in val or "⚠" in label:
                item.setForeground(QColor(_RISK))
            t.setItem(i, 1, item)
            t.setItem(i, 2, QTableWidgetItem(note))
        layout.addWidget(t)
        layout.addStretch(1)

    def _refresh_benchmarks(self) -> None:
        store = get_store()
        benchmarks = store.get_all()
        t = self._benchmarks_table
        t.setRowCount(len(benchmarks))
        for row, b in enumerate(benchmarks):
            conf_color = {"high": _OK, "medium": _WARN, "low": _RISK}.get(b.confidence, _INK3)
            vals = [
                b.project_name,
                str(b.units) if b.units else "—",
                f"${b.drywall_price_per_unit:,.0f}" if b.drywall_price_per_unit else "—",
                f"${b.paint_price_per_unit:,.0f}" if b.paint_price_per_unit else "—",
                f"${b.total_price_per_unit:,.0f}" if b.total_price_per_unit else "—",
                f"{b.drywall_board_sf_per_unit:,.0f}" if b.drywall_board_sf_per_unit else "—",
                f"{b.paint_gal_per_unit:.1f}" if b.paint_gal_per_unit else "—",
                b.confidence.upper(),
                b.notes[:60] if b.notes else "",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == 7:
                    item.setForeground(QColor(conf_color))
                t.setItem(row, col, item)

    def _populate_qc(self, r: ProjectAnalysisReport) -> None:
        self._qc_tab.clear()
        severity_color = {
            "critical": _RISK,
            "high": _RISK,
            "medium": _WARN,
            "low": _INK3,
        }
        if not r.qc_flags:
            item = QListWidgetItem("✓ No QC flags — analysis complete.")
            item.setForeground(QColor(_OK))
            self._qc_tab.addItem(item)
            return

        # Update tab label with count
        idx = self._tabs.indexOf(self._qc_tab)
        if idx >= 0:
            self._tabs.setTabText(idx, f"QC Flags ({len(r.qc_flags)})")

        for flag in sorted(r.qc_flags, key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.severity, 4)):
            header = QListWidgetItem(f"[{flag.severity.upper()}] {flag.category}: {flag.description}")
            header.setForeground(QColor(severity_color.get(flag.severity, _INK3)))
            self._qc_tab.addItem(header)
            rec = QListWidgetItem(f"  → {flag.recommendation}")
            rec.setForeground(QColor(_INK3))
            self._qc_tab.addItem(rec)
            self._qc_tab.addItem(QListWidgetItem(""))


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_sf(v: object) -> str:
    if v is None:
        return "Not confirmed"
    return f"{float(v):,.0f} SF"

def _fmt_n(v: object) -> str:
    if v is None:
        return "Not confirmed"
    return f"{int(v):,}"

def _fmt_gal(v: object) -> str:
    if v is None:
        return "Not confirmed"
    return f"{float(v):,.0f} gal"

def _fmt_ratio(v: object, decimals: int = 0) -> str:
    if v is None:
        return "Not confirmed"
    fmt = f"{{:,.{decimals}f}}"
    return fmt.format(float(v))
