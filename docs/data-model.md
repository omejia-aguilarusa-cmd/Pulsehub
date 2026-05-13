# Data Model

This document records the Phase 1 mapping from legacy `Data.xml` folders into Takeoff Pro's internal models. It is schema documentation only; no real job data belongs in this repository.

## Legacy XML Shape

Each importable folder can contain a `Data.xml` file with this general shape:

```xml
<Item Class="..." Name="..." GUID="...">
  <Properties>
    <Property Class="..." GUID="..." Name="...">value</Property>
  </Properties>
</Item>
```

Important conventions:

- The item `GUID` becomes the model `id` when present.
- The `Name` property is preferred over the item attribute for display names.
- Property names are stable enough to map key fields, but property GUIDs vary by job and are retained only as raw metadata.
- Nested folders define hierarchy. A parent measurement item owns child section items.
- Page images are referenced by the `Image` property's GUID. The importer checks for a sibling `{GUID}.tiff` or `{GUID}.tif` file but does not copy it.

## Model Mapping

| Takeoff Pro model | Legacy source | Field mapping |
| --- | --- | --- |
| `Job` | Root `Data.xml` if present | `GUID` -> `id`, `Name` -> `name`, `Measurement Type` -> `measurement_system`, `Description` -> `description` |
| `Page` | `Pages/**/Data.xml` with item class `Page` | `GUID` -> `id`, `Name` -> `name`, `OrderIndex` -> `order_index`, `Image.GUID` -> `image_guid`, `ScaleX` / `ScaleY`, `Scale Units`, `MeasurementType` |
| `TakeoffSection` | `Takeoff/**/Data.xml` with item class `Area`, `Segment`, or `Count` | `Area` -> area, `Segment` -> length, `Count` -> count, plus `Name`, `Description`, `Item #`, `OrderIndex`, `Scale Units` |
| `Measurement` | Child `Data.xml` with item class `Area Section`, `Segment Section`, or `Count Section` | Section class -> measurement kind, `PageGUID` -> `page_id`, `OrderIndex`, `ZOrder`, `Visible`, `DigitizerData` points |
| `Point` | XML embedded in `DigitizerData` | `Point.X` -> `x`, `Point.Y` -> `y`, `Point.PointType` -> `point_type` |
| `Autolist` | `AutoLists/**/Data.xml` | `GUID` -> `id`, `Name` -> `name`, child item names -> `values` where present |
| `LegacyProperty` | Any `<Property>` element | `Name`, `Class`, `GUID`, text value, and non-core attributes |

## Measurement Kinds

The importer normalizes legacy item classes into geometry kinds:

| Legacy item class | Takeoff Pro kind |
| --- | --- |
| `Area`, `Area Section` | `area` |
| `Segment`, `Segment Section` | `length` |
| `Count`, `Count Section` | `count` |

## Tolerance Rules

- Missing root job `Data.xml`: import still succeeds using the folder name as job ID and name.
- Missing `Pages`, `Takeoff`, or `AutoLists` folders: import succeeds with empty lists.
- Missing image files: page model is retained with `image_path = None`.
- Invalid numeric properties: field is left as `None`.
- Malformed item XML: the item is skipped and a warning is logged.
- Malformed digitizer point XML: the measurement is retained with no points and a warning is logged.

## Synthetic Fixture

The automated tests use `tests/fixtures/sample_job/`, which contains synthetic XML only. It includes:

- Two pages.
- One length section with two points.
- One area section with four points.
- One count section with two points.
- One autolist container.
