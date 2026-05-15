"""Background QThread worker for the Senior Estimator analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from takeoff_pro.estimator.project_analyzer import ProjectAnalysisReport, ProjectAnalyzer


class EstimatorAnalysisWorker(QThread):
    """Runs ProjectAnalyzer on a background thread — keeps the UI responsive."""

    progress = pyqtSignal(str)          # status message
    finished = pyqtSignal(object)       # ProjectAnalysisReport
    error    = pyqtSignal(str)

    def __init__(self, file_paths: list[Path]) -> None:
        super().__init__()
        self._paths = file_paths
        self._analyzer = ProjectAnalyzer()

    def run(self) -> None:
        try:
            report: ProjectAnalysisReport = self._analyzer.analyze(
                self._paths,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Estimator analysis failed: {exc}")
