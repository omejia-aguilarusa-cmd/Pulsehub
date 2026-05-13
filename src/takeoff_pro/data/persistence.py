"""Native `.tkjob` persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

from takeoff_pro.data.models import Job

JOB_FILE_NAME = "job.json"


class PersistenceError(RuntimeError):
    """Raised when a native job cannot be saved or loaded."""


def save_job(job: Job, folder_path: str | Path) -> Job:
    """Save a native job folder and return the saved model."""
    target_folder = _normalize_job_folder(folder_path)
    target_folder.mkdir(parents=True, exist_ok=True)
    saved_job = job.model_copy(update={"source_root": target_folder})
    job_path = target_folder / JOB_FILE_NAME
    job_path.write_text(
        saved_job.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return saved_job


def load_job(folder_path: str | Path) -> Job:
    """Load a native job folder from `job.json`."""
    target_folder = _normalize_job_folder(folder_path)
    job_path = target_folder / JOB_FILE_NAME
    if not job_path.exists():
        msg = f"Native job file does not exist: {job_path}"
        raise PersistenceError(msg)

    try:
        raw_data = json.loads(job_path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"Could not read native job file: {job_path}"
        raise PersistenceError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse native job file: {job_path}"
        raise PersistenceError(msg) from exc

    try:
        job = Job.model_validate(raw_data)
    except ValueError as exc:
        msg = f"Native job file is invalid: {job_path}"
        raise PersistenceError(msg) from exc
    return job.model_copy(update={"source_root": target_folder})


def is_native_job_folder(folder_path: str | Path) -> bool:
    """Return whether a folder contains a native job file."""
    return (Path(folder_path).expanduser().resolve() / JOB_FILE_NAME).exists()


def _normalize_job_folder(folder_path: str | Path) -> Path:
    path = Path(folder_path).expanduser().resolve()
    if path.suffix.casefold() != ".tkjob":
        return path.with_suffix(".tkjob")
    return path
