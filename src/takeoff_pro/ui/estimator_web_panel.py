"""
Estimator workspace panel — PulseHubX web UI embedded via QWebEngineView.

Loads the self-contained AI Takeoff Estimator HTML prototype and bridges it to
the Python analysis backend:
  • Drag-and-drop / native file picker → EstimatorAnalysisWorker
  • Analysis progress → shows the 'analysis' screen in the web UI
  • Analysis complete → injects real data via window.__injectReport()
  • Falls back to the Qt-widget EstimatorPanel if WebEngine is unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

from takeoff_pro.estimator.document_classifier import DocumentRelevance
from takeoff_pro.estimator.project_analyzer import ProjectAnalysisReport
from takeoff_pro.ui.estimator_worker import EstimatorAnalysisWorker

_ASSETS_DIR = Path(__file__).parent / "assets"
_UI_HTML    = _ASSETS_DIR / "estimator_ui.html"

# Injected once after page load: wires native file-picker into the web UI.
_BRIDGE_JS = """
(function() {
  if (window.__pytakoff_patched) return;
  window.__pytakoff_patched = true;

  /* Intercept "Choose files" / "Import from Drive" clicks */
  document.addEventListener('click', function(e) {
    var btn = e.target.closest && e.target.closest('button');
    if (!btn) return;
    var txt = btn.textContent.trim();
    if (txt === 'Choose files' || txt === 'Import from Drive' || txt === 'Connect Gmail · Bid invites') {
      e.stopPropagation();
      e.preventDefault();
      window.location.href = 'qtbridge://openfiles';
    }
  }, true);

  /* Override default drag-drop in the upload zone so Qt widget level still fires */
  document.addEventListener('dragover',  function(e) { e.stopPropagation(); }, true);
  document.addEventListener('drop',      function(e) { e.stopPropagation(); }, true);
})();
"""


class EstimatorWebPanel(QWidget):
    """Full estimator workspace — PulseHubX web UI + Python analysis backend."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: EstimatorAnalysisWorker | None = None
        self._view: Optional[QWebEngineView] = None
        self.setAcceptDrops(True)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if _HAS_WEBENGINE and _UI_HTML.exists():
            self._view = QWebEngineView()
            page = self._view.page()
            if page:
                page.navigationRequested.connect(self._on_navigation)
                page.loadFinished.connect(self._on_page_loaded)
                s = page.settings()
                if s:
                    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                    s.setAttribute(
                        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
                    )
            self._view.load(QUrl.fromLocalFile(str(_UI_HTML)))
            layout.addWidget(self._view)
        else:
            # Graceful fallback — Qt-widget estimator panel
            from takeoff_pro.ui.estimator_panel import EstimatorPanel

            fallback = EstimatorPanel(self)
            layout.addWidget(fallback)

    # ── Page events ───────────────────────────────────────────────────────────

    def _on_page_loaded(self, ok: bool) -> None:
        if not ok or self._view is None:
            return
        self._view.page().runJavaScript(_BRIDGE_JS)

    def _on_navigation(self, request: object) -> None:
        """Intercept 'qtbridge://openfiles' navigation → native file picker."""
        # QWebEngineNavigationRequest has .url and .action
        try:
            url   = request.url()  # type: ignore[attr-defined]
            if url.scheme() == "qtbridge" and url.host() == "openfiles":
                request.reject()  # type: ignore[attr-defined]
                self._open_native_file_picker()
        except Exception:
            pass

    # ── File picking ──────────────────────────────────────────────────────────

    def _open_native_file_picker(self) -> None:
        paths_str, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Project Files",
            "",
            "Estimates, Takeoffs & Drawings (*.pdf *.xlsx *.xls *.docx *.txt *.csv)",
        )
        if paths_str:
            self._run_analysis([Path(p) for p in paths_str])

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
                    if f.is_file()
                    and f.suffix.lower() in {".pdf", ".xlsx", ".xls", ".docx", ".txt"}
                )
        if paths:
            event.acceptProposedAction()
            self._run_analysis(paths)

    # ── Analysis pipeline ─────────────────────────────────────────────────────

    def _run_analysis(self, paths: list[Path]) -> None:
        if self._worker and self._worker.isRunning():
            return
        if self._view:
            self._view.page().runJavaScript(
                "window.__setScreen && window.__setScreen('analysis');"
            )
        worker = EstimatorAnalysisWorker(paths)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        self._worker = worker
        worker.start()

    def _on_finished(self, report: object) -> None:
        self._worker = None
        if not isinstance(report, ProjectAnalysisReport):
            return
        if self._view:
            payload = json.dumps(_report_to_js(report))
            self._view.page().runJavaScript(
                f"window.__injectReport && window.__injectReport({payload});"
            )

    def _on_error(self, _msg: str) -> None:
        self._worker = None
        if self._view:
            self._view.page().runJavaScript(
                "window.__setScreen && window.__setScreen('upload');"
            )


# ── Report → JS data model ────────────────────────────────────────────────────

def _report_to_js(r: ProjectAnalysisReport) -> dict:  # noqa: C901
    """Map a ProjectAnalysisReport to the window globals the React app reads."""
    conf_pct = {"high": 88, "medium": 64, "low": 32}.get(r.confidence, 50)
    dw_fmt   = f"${r.drywall_price:,.0f}"  if r.drywall_price  else "—"
    pt_fmt   = f"${r.paint_price:,.0f}"    if r.paint_price    else "—"
    tot_fmt  = f"${r.total_price:,.0f}"    if r.total_price    else "—"

    # ── PROJECT ───────────────────────────────────────────────────────────
    project = {
        "name":       r.project_name or "Untitled Project",
        "client":     "—",
        "address":    "—",
        "type":       "Construction · Division 09",
        "drawingSet": "—",
        "addenda":    [],
        "sheets":     len(r.documents),
        "bidDue":     "—",
        "status":     "AI Draft · Awaiting Estimator Review",
        "confidence": conf_pct,
    }

    # ── SHEETS (document register) ────────────────────────────────────────
    _rel_status = {
        DocumentRelevance.RELEVANT:   "ok",
        DocumentRelevance.SUPPORTING: "warn",
        DocumentRelevance.IGNORE:     "ok",
    }
    sheets = [
        {
            "id":    doc.path.stem[:12],
            "title": doc.path.name,
            "disc":  str(doc.doc_type).split(".")[-1].replace("_", " ").title(),
            "date":  "—",
            "rev":   "—",
            "add":   "—",
            "status": _rel_status.get(doc.relevance, "ok"),
            "conf":  int(doc.classifier_confidence * 100),
        }
        for doc in r.documents
    ] or [{"id": "—", "title": "No documents", "disc": "—",
            "date": "—", "rev": "—", "add": "—", "status": "warn", "conf": 0}]

    # ── NEXT_ACTIONS ──────────────────────────────────────────────────────
    actions: list[dict] = []
    if r.drywall_price or r.paint_price or r.total_price:
        actions.append({
            "type":  "ok",
            "title": f"{r.project_name or 'Project'} — analysis complete",
            "body":  f"Drywall: {dw_fmt}  ·  Paint: {pt_fmt}  ·  Total: {tot_fmt}  ·  Confidence: {r.confidence}",
            "cta":   "View takeoff",
        })
    _sev = {"critical": "risk", "high": "risk", "medium": "warn", "low": "info"}
    for flag in (r.qc_flags or [])[:4]:
        actions.append({
            "type":  _sev.get(flag.severity, "info"),
            "title": flag.description[:60],
            "body":  flag.recommendation[:100],
            "cta":   "Review",
        })
    if not actions:
        actions.append({
            "type":  "info",
            "title": "Analysis complete — no confirmed pricing found",
            "body":  "Upload estimate PDFs (bid proposals, quotes) to extract drywall and paint prices.",
            "cta":   "Upload more files",
        })

    return {
        "PROJECT":      project,
        "SHEETS":       sheets,
        "NEXT_ACTIONS": actions,
    }
