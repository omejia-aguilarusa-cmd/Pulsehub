# Takeoff Pro

Takeoff Pro is a local desktop construction takeoff and estimating tool built with Python and PyQt.

## Status

Phases 0 through 5 are implemented locally: toolchain, legacy XML import, page viewer, takeoff tools, estimating, report exports, Windows executable packaging, and a task-based workspace with local automated drawing review.

## Prerequisites

- Windows 10 or newer
- Python 3.12
- `uv`
- Git

If `uv` was installed but is not visible in a new terminal, run:

```powershell
uv python update-shell
```

Then open a new PowerShell window and verify:

```powershell
uv --version
uv python list
```

## Quickstart

From the repository root:

```powershell
uv sync
uv run takeoff-pro
```

For local checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=src/takeoff_pro --cov-report=term-missing
```

Build the Windows executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The packaged app is written to `dist\TakeoffPro.exe`.

## Current Capabilities

- Upload local PDF or TIFF drawings directly into a native job.
- Expand multi-page source files into individual document pages.
- Review uploaded drawings locally for common PDF scale notes, vector linework, and rectangular regions.
- Create confidence-tagged automated measurements after upload when linework is detected.
- Keep unscaled drawings in page units until a reliable scale is available, instead of claiming field units prematurely.

## Development

Run the package entry point directly:

```powershell
uv run python -m takeoff_pro
```

Install Git hooks after `uv sync`:

```powershell
uv run pre-commit install
```

## Private Remote Setup

Create a private GitHub repository first. Then run:

```powershell
git remote add origin <PRIVATE_REPO_URL>
git push -u origin main
git push --tags
```

Do not push client data or generated build artifacts.

## Data Safety

This repository is configured to ignore page images, PDFs, executables, DLLs, and known local reference job names. Keep real project data outside version control.
