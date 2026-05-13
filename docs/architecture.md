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
