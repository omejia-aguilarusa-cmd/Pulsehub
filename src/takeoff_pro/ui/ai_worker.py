"""Background QThread worker for non-blocking AI drawing analysis."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from takeoff_pro.analysis import DrawingReview, apply_drawing_review, review_job_drawings
from takeoff_pro.data.models import Job


class AIAnalysisWorker(QThread):
    """Run automated drawing review on a background thread."""

    progress = pyqtSignal(str)           # status message
    finished = pyqtSignal(int, object)   # (measurements_added, DrawingReview)
    error = pyqtSignal(str)

    def __init__(self, job: Job) -> None:
        """Initialise the worker with the job to analyse."""
        super().__init__()
        self._job = job

    def run(self) -> None:
        """Execute the review pipeline and emit per-page progress."""
        try:
            n = len(self._job.pages)
            self.progress.emit(f"Starting review of {n} page(s)…")

            def on_page_progress(msg: str) -> None:
                self.progress.emit(msg)

            review: DrawingReview = review_job_drawings(
                self._job, progress_callback=on_page_progress
            )
            self.progress.emit(
                f"Applying {review.measurement_count} suggestion(s)…"
            )
            added = apply_drawing_review(self._job, review)
            self.finished.emit(added, review)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"AI review failed: {exc}")
