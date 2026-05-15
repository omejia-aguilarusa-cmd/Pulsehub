# Architecture

Takeoff Pro is a local PyQt application with separate packages for UI, rendering, takeoff tools, data persistence, estimating, and reports.

## Phase 0 Shape

- `takeoff_pro.app` owns QApplication bootstrap and process startup.
- `takeoff_pro.ui` owns desktop widgets and windows.
- `takeoff_pro.data` will own validated project models and persistence.
- `takeoff_pro.render` will own PDF and image rendering.
- `takeoff_pro.tools` will own interactive measurement tools.
- `takeoff_pro.estimate` will own cost items and assemblies.
- `takeoff_pro.reports` will own CSV, XLSX, and PDF export.

The runtime app must remain fully local and must not make network calls.

## Phase 1 Import Boundary

The data package now has two layers:

- `takeoff_pro.data.models` defines validated Pydantic models for jobs, pages, takeoff sections, measurements, autolists, and raw legacy properties.
- `takeoff_pro.data.planswift_importer` reads only `Data.xml` files and resolves optional local page image references without copying image data.

The importer is intentionally tolerant of missing top-level job XML so partial exported or sample folders with page-level XML can still be inspected. Parse errors and malformed digitizer data are logged instead of being silently ignored.

## Phase 2 Viewer Boundary

The viewer is split into rendering and interaction layers:

- `takeoff_pro.render.page_renderer` uses PyMuPDF to render PDF and TIFF pages into detached `QImage` instances.
- `takeoff_pro.ui.viewport.PageViewport` owns the `QGraphicsView` scene, zooming, panning, fit-to-window, actual-size, and viewport rotation behavior.
- `takeoff_pro.ui.main_window.MainWindow` owns job-folder opening, the page list, and page-to-viewport wiring.

The renderer returns Qt images rather than scene items so rendering can be tested independently from main-window behavior.

## Phase 3 Native Takeoff Boundary

Native project persistence uses `.tkjob` folders with a `job.json` file containing the Pydantic `Job` model. Page image paths remain references; image files are not copied into the save folder yet.

The takeoff UI is split this way:

- `takeoff_pro.core.geometry` calculates length, area, perimeter, and count quantities from page-space points and page scale.
- `takeoff_pro.ui.viewport.PageViewport` collects drawing points and renders overlays.
- `takeoff_pro.ui.commands` wraps measurement edits in `QUndoCommand` objects.
- `takeoff_pro.ui.main_window.MainWindow` owns the active job, current page, tool selection, scale calibration, and measurements panel.

Scale calibration stores `scale_pixels_per_unit` and `scale_unit` on each page. Imported legacy `ScaleX` values remain available as a fallback when no native calibration is present.

## Phase 4 Estimating Boundary

Estimating is implemented in `takeoff_pro.estimate`:

- `models` defines unit-cost items, assemblies, components, and BOM lines.
- `library` reads and writes CSV item libraries.
- `pricing` owns unit conversion and BOM math.

Native jobs store item and assembly libraries directly in `job.json`. A takeoff section attaches to an estimate reference with `estimate_reference_type` and `estimate_reference_id`. Pricing walks each attached section, sums its measurement quantities, converts compatible units, and emits flat BOM lines.

## Phase 5 Reports and Packaging Boundary

Report exports are implemented in `takeoff_pro.reports`:

- `data` builds reusable takeoff summary rows from the validated job model.
- `csv_report` emits a flat takeoff and cost CSV.
- `xlsx_report` creates a workbook with Job Summary, Takeoff Detail, and Cost Detail worksheets.
- `pdf_report` creates a local PDF report with summary, detail, cost tables, and page footer numbering.

The main window owns file-dialog routing only; report formatting and pricing remain outside the UI layer. Packaging is defined by `TakeoffPro.spec`, and `scripts/build_exe.ps1` runs PyInstaller to produce `dist\TakeoffPro.exe`.

## Accuracy and Automated Review

Measurement math now treats native calibration as isotropic and imported legacy `ScaleX` / `ScaleY` as independent axes. Length, area, and perimeter calculations transform each point into real-world units before performing geometry math, so non-square imported scales remain correct. Recalibration refreshes stored quantities instead of leaving stale numbers in `job.json`.

Uploaded drawings enter through `takeoff_pro.data.drawing_importer`, which expands multi-page PDF or TIFF sources into native `Page` models while keeping source page indices explicit. `takeoff_pro.analysis.drawing_analyzer` performs a fully local automated pass over each uploaded page. It can infer common PDF scale notes, inspect vector commands for straight segments and rectangles, fall back to simple raster line detection, and emit confidence-tagged suggestions that the UI applies into dedicated automated-review sections.

The analyzer is intentionally conservative: if no reliable scale is found, the resulting suggestions stay in page units so the product does not claim field accuracy it does not have.

## Workspace Shell

`takeoff_pro.ui.main_window.MainWindow` now exposes a task-based workspace with functional sections for dashboard, documents, takeoff, automated review, estimating, and reports. The takeoff viewport remains the core working surface, while the surrounding shell makes upload, analysis, BOM, and output tasks available without depending on menu discovery.
