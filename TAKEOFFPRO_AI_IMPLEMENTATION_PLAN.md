# TakeoffPro AI Implementation Plan

## Current Architecture Snapshot

- Frontend/runtime: local Python 3.12 desktop app using PyQt6 and PyQt6-WebEngine.
- Workspace UI: static HTML/CSS/JavaScript in `src/takeoff_pro/ui/assets`, persisted in browser IndexedDB.
- Native backend/core: Python packages under `src/takeoff_pro` for data models, PDF/TIFF rendering, drawing import, local analysis, estimating, and reports.
- Database/storage: no remote database; native `.tkjob` folders use `job.json`, and the web workspace stores state/files locally in IndexedDB.
- Auth/deployment: no auth layer; packaged as a Windows desktop executable with PyInstaller.
- PDF processing: PyMuPDF is already used by `data.drawing_importer`, `render.page_renderer`, and `analysis.drawing_analyzer`.
- Existing AI-like code: local automated drawing review only; no external AI provider is wired.
- Testing: Python `pytest`, `ruff`, `mypy`; web logic tests use Node's built-in test runner.

## Phase 1 - MVP AI Takeoff Foundation

- [x] Document phased implementation plan.
- [x] Reuse existing PDF upload/import concepts rather than adding a separate backend service.
- [x] Add page raster metadata and AI takeoff result models to the native data layer.
- [x] Add PyMuPDF page rasterization helper for AI/page-image use.
- [x] Add painting takeoff formula, validation, prompt, normalization, and provider adapter modules.
- [x] Add API-shaped local takeoff runner with graceful "AI not configured" fallback.
- [x] Extend the web workspace with a painting-focused Run AI Takeoff flow.
- [x] Add a quantities panel with room breakdown, confidence, warnings, totals, and export support.
- [x] Extend manual scale UI with custom pixels-per-foot and measurement source metadata.
- [x] Add focused tests for core formula/normalization/export behavior.
- [x] Update developer docs for AI environment variables and local-only fallback.

## Phase 2 - TakeoffPro.CHAT / Document Assistant

- [ ] Extract searchable PDF text chunks with page references.
- [ ] Add repo-compatible local persistence for chunks and conversations.
- [ ] Add provider-backed document Q&A with citations and cannot-answer behavior.
- [ ] Add a chat panel optimized for painting estimator questions.

## Phase 3 - Formula + Assembly Engine

- [ ] Add safe painting assembly templates and formula evaluator.
- [ ] Let users create/edit assemblies.
- [ ] Apply assemblies to rooms or classifications.
- [ ] Roll up material and labor summaries.

## Phase 4 - AI Validation / Estimator QA

- [ ] Add `validate` service for suspicious quantities, missing elements, special prep risks, and low confidence.
- [ ] Surface QA flags in the quantities/review UI.

## Phase 5 - Drawing Comparison

- [ ] Support original/revised drawing sets.
- [ ] Match pages by sheet metadata.
- [ ] Compare page images and summarize painting-scope impact.

## Phase 6 - AI Image / Symbol Search

- [ ] Add selected-region crop workflow.
- [ ] Search similar symbols across plan pages.
- [ ] Return matches with page/location/confidence for estimator review.
