# User Guide

## Start the App

Run:

```powershell
uv run takeoff-pro
```

The application opens a desktop window titled "Takeoff Pro".

## Open a Job Folder

Use `File > Open Job Folder...` and choose a folder that contains legacy `Data.xml` job content. Pages appear in the left panel. Selecting a page renders its local PDF or TIFF image when the file is available.

Native `.tkjob` folders can also be opened from the same command.

## Viewer Controls

- `Ctrl+wheel`: zoom in or out.
- Middle-drag: pan.
- Space-drag: pan.
- `F`: fit the page to the window.
- `1`: show the page at actual size.
- `R`: rotate the view clockwise.

## Create Takeoff

Use `File > New Blank Job` to start a local job with one blank page. Select a takeoff tool from the toolbar:

- Length: click two points to create one length measurement.
- Area: click polygon points, then double-click to finish.
- Count: click once per marker.

Use `Tools > Set Scale`, click two points on the page, then enter the real-world distance and units. New measurements use the page scale for LF, SF, or count quantities.

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
