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
