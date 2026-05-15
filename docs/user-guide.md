# User Guide

## Start the App

Run:

```powershell
uv run takeoff-pro
```

The application opens a desktop window titled "Takeoff Pro".

## Start a Job

The left workspace rail gives direct access to:

- `New blank job` for manual takeoff work.
- `Upload drawings` for local PDF or TIFF files.
- `Open job folder` for imported legacy jobs or native `.tkjob` folders.

Uploaded multi-page PDFs become one page entry per source page. The app runs a local automated review immediately after upload and opens the `AI Review` workspace so the generated results are visible without extra setup.

Native `.tkjob` folders can also be opened from `File > Open Job Folder...`.

## Viewer Controls

- `Ctrl+wheel`: zoom in or out.
- Middle-drag: pan.
- Space-drag: pan.
- `F`: fit the page to the window.
- `1`: show the page at actual size.
- `R`: rotate the view clockwise.

## Workspace Sections

- `Dashboard` summarizes pages, measurements, scaled pages, and estimate total.
- `Documents` lists imported pages, source files, and scale status. Double-click a row to open it in takeoff.
- `Takeoff` contains the page list, drawing viewport, and live measurements panel.
- `AI Review` shows detected scales, generated suggestions, applied measurements, and review notes.
- `Estimate` exposes the priced BOM and estimate-library actions.
- `Reports` exports CSV, XLSX, and PDF output.

## Create Takeoff

Use `File > New Blank Job` to start a local job with one blank page. Select a takeoff tool from the toolbar:

- Length: click polyline points, then double-click or use `Tools > Finish Measurement`.
- Area: click polygon points, then double-click to finish.
- Count: click once per marker.

Use `Tools > Set Scale`, click two points on the page, then enter the real-world distance and units. Existing measurements on the calibrated page are recalculated immediately, and future measurements use the updated page scale for LF, SF, or count quantities. Unscaled pages report measurements in page units instead of pretending to be field units.

Use `File > Save As Native Job...` to save the current job as a `.tkjob` folder. The native job can be reopened with `File > Open Job Folder...`.

## Estimate

Use `Estimate > Items and Assemblies...` to edit the job's estimating library. Items have an ID, description, unit, and unit cost. Assemblies bundle one or more items per unit of takeoff.

Use `Estimate > Attach First Item` or `Estimate > Attach First Assembly` to attach the first library entry to the first takeoff section. The measurements panel shows the estimated total when attached sections can be priced.

## Export Reports

Use the `Reports` menu to export the current job:

- `Reports > Export CSV...` writes a flat takeoff and cost file.
- `Reports > Export XLSX...` writes a workbook with summary, takeoff detail, and cost detail tabs.
- `Reports > Export PDF...` writes a printable report with summary and detail tables.

Reports use the same attached item and assembly pricing shown in the measurements panel.

## Automated Review

`AI Review` is fully local and makes no network calls. On vector PDFs it can read common scale notes such as `1" = 10'`, detect straight vector linework, identify rectangular vector regions, and create suggested length or area measurements automatically. Raster drawings without a readable scale note can still produce visual suggestions, but they stay in page units until a reliable scale is available.

Automated output is intended as a fast first pass. Review the detected scale source and confidence before using the results for pricing or field decisions.
