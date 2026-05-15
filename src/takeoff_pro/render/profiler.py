"""Lightweight render-pipeline profiler for Takeoff Pro.

Usage:
    from takeoff_pro.render.profiler import profiler

    with profiler.measure("pdf_open"):
        doc = pymupdf.open(path)
"""

from __future__ import annotations

import contextlib
import time
from collections import deque
from typing import Generator


class RenderProfiler:
    """Rolling-average timing tracker for named pipeline stages."""

    MAX_SAMPLES: int = 120

    def __init__(self) -> None:
        self._timings: dict[str, deque[float]] = {}

    @contextlib.contextmanager
    def measure(self, name: str) -> Generator[None, None, None]:
        """Context manager: record elapsed time (ms) for *name*."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1_000.0
            bucket = self._timings.setdefault(name, deque(maxlen=self.MAX_SAMPLES))
            bucket.append(elapsed_ms)

    def last_ms(self, name: str) -> float:
        """Return the most recent sample for *name*, or 0.0."""
        bucket = self._timings.get(name)
        return bucket[-1] if bucket else 0.0

    def avg_ms(self, name: str) -> float:
        """Return the rolling average for *name*, or 0.0."""
        bucket = self._timings.get(name)
        return sum(bucket) / len(bucket) if bucket else 0.0

    def all_stats(self) -> dict[str, dict[str, float]]:
        """Return {stage: {avg_ms, last_ms}} for every recorded stage."""
        return {
            name: {"avg_ms": self.avg_ms(name), "last_ms": self.last_ms(name)}
            for name in self._timings
        }

    def summary_line(self) -> str:
        """Return a single-line summary suitable for a status bar or log."""
        parts = [
            f"{name} {self.last_ms(name):.0f}ms"
            for name in self._timings
        ]
        return "  |  ".join(parts) if parts else "no profiling data"


# Module-level singleton shared across the render package.
profiler: RenderProfiler = RenderProfiler()
