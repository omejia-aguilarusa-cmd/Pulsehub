"""Native .tkjob persistence: save and load Job models to/from disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from takeoff_pro.data.models import Job

LOGGER = logging.getLogger(__name__)

_JOB_FILENAME = "job.json"


class PersistenceError(RuntimeError):
    """Raised when a job cannot be saved or loaded from disk."""


def is_native_job_folder(path: Path) -> bool:
    """Return True if *path* looks like a saved .tkjob directory."""
    p = Path(path)
    return p.is_dir() and (p / _JOB_FILENAME).is_file()


def save_job(job: Job, dest: Path) -> Job:
    """Persist *job* to a .tkjob directory at *dest* and return the updated job.

    *dest* is the directory path (e.g. ``project.tkjob``).  It is created if it
    does not already exist.  The job is serialised to ``job.json`` inside it.
    The returned job has ``source_root`` set to the resolved *dest* path.
    """
    dest = Path(dest).expanduser().resolve()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        payload = job.model_dump(mode="json")
        (dest / _JOB_FILENAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        msg = f"Could not save job to {dest}: {exc}"
        raise PersistenceError(msg) from exc

    updated = job.model_copy(update={"source_root": dest})
    LOGGER.info("Saved job '%s' to %s", job.name, dest)
    return updated


def load_job(path: Path) -> Job:
    """Load a Job from a .tkjob directory at *path*.

    Raises :exc:`PersistenceError` if *path* does not exist or does not contain
    a valid ``job.json``.
    """
    folder = Path(path).expanduser().resolve()
    job_file = folder / _JOB_FILENAME
    if not folder.exists():
        msg = f"Job folder does not exist: {folder}"
        raise PersistenceError(msg)
    if not job_file.is_file():
        msg = f"job.json not found in: {folder}"
        raise PersistenceError(msg)
    try:
        raw = job_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Could not read job.json from {folder}: {exc}"
        raise PersistenceError(msg) from exc
    try:
        job = Job.model_validate(data)
    except Exception as exc:
        msg = f"Job data in {folder} is invalid: {exc}"
        raise PersistenceError(msg) from exc

    job = job.model_copy(update={"source_root": folder})
    LOGGER.info("Loaded job '%s' from %s", job.name, folder)
    return job
