"""Background QThread worker for non-blocking AI drawing analysis."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from takeoff_pro.analysis import DrawingReview, apply_drawing_review, review_job_drawings
from takeoff_pro.data.models import Job


class AIAnalysisWorker(QThread):
    """Run automated drawing review on a background thread."""

    progress = pyqtSignal(str)        # status message
    finished = pyqtSignal(int, object)  # (measurements_added, DrawingReview)
    error = pyqtSignal(str)

    def __init__(self, job: Job) -> None:
        """Initialise the worker with the job to analyse."""
        super().__init__()
        self._job = job

    def run(self) -> None:
        """Execute the review pipeline and emit results."""
        try:
            self.progress.emit("Extracting scale notes and linework…")
            review: DrawingReview = review_job_drawings(self._job)
            self.progress.emit(
                f"Found {review.measurement_count} measurement suggestions "
                f"across {len(review.pages)} page(s)…"
            )
            added = apply_drawing_review(self._job, review)
            self.progress.emit(f"Applied {added} measurements.")
            self.finished.emit(added, review)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
