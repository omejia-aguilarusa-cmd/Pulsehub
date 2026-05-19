(function attachDrawingWorkspaceServices(global) {
  "use strict";

  const logic = global.WorkspaceLogic || {};

  const DEFAULT_DRAWING_LAYERS = Object.freeze([
    { key: "drawing-base", label: "Drawing base", defaultVisible: true },
    { key: "ai-walls", label: "AI detected walls", defaultVisible: true },
    { key: "ai-rooms", label: "AI detected rooms", defaultVisible: true },
    { key: "paint-scope", label: "Paint scope", defaultVisible: true },
    { key: "ceiling-scope", label: "Ceiling scope", defaultVisible: true },
    { key: "flooring-scope", label: "Flooring scope", defaultVisible: true },
    { key: "framing-scope", label: "Framing scope", defaultVisible: false },
    { key: "manual-measurements", label: "Manual measurements", defaultVisible: true },
    { key: "approved-quantities", label: "Approved quantities", defaultVisible: true },
    { key: "low-confidence", label: "Low-confidence items", defaultVisible: true },
    { key: "rfis", label: "RFIs / questions", defaultVisible: true },
    { key: "revision-changes", label: "Revision changes", defaultVisible: true },
    { key: "exclusions", label: "Exclusions", defaultVisible: true },
    { key: "alternates", label: "Alternates", defaultVisible: false },
    { key: "phasing", label: "Phasing", defaultVisible: false },
  ]);

  const SHEET_FILTERS = Object.freeze([
    { key: "all", label: "All sheets" },
    { key: "architectural", label: "Architectural" },
    { key: "structural", label: "Structural" },
    { key: "mep", label: "MEP" },
    { key: "revised", label: "Revised" },
    { key: "needs-review", label: "Needs review" },
    { key: "has-rfis", label: "Has RFIs" },
    { key: "processed", label: "Processed" },
    { key: "not-processed", label: "Not processed" },
  ]);

  const SCALE_OPTIONS = Object.freeze([
    '1/16" = 1\'-0"',
    '1/8" = 1\'-0"',
    '3/16" = 1\'-0"',
    '1/4" = 1\'-0"',
    '1/2" = 1\'-0"',
    '1" = 1\'-0"',
    "Custom",
  ]);

  const MODES = Object.freeze([
    { key: "view", label: "View" },
    { key: "measure", label: "Measure" },
    { key: "scope-review", label: "Scope Review" },
    { key: "compare", label: "Compare" },
    { key: "markup-rfi", label: "Markup / RFI" },
  ]);

  const TOOLSETS = Object.freeze({
    view: [
      { action: "viewer-zoom-out", label: "Zoom out" },
      { action: "viewer-zoom-in", label: "Zoom in" },
      { action: "viewer-fit-page", label: "Fit page" },
      { action: "viewer-fit-width", label: "Fit width" },
      { action: "viewer-rotate", label: "Rotate" },
      { action: "noop", label: "Search sheet" },
    ],
    measure: [
      { action: "open-ai-measurement-modal", label: "Run AI Measurement", primary: true },
      { action: "set-measurement-tool", tool: "line", label: "Line" },
      { action: "set-measurement-tool", tool: "polyline", label: "Polyline" },
      { action: "set-measurement-tool", tool: "area", label: "Area" },
      { action: "set-measurement-tool", tool: "rectangle", label: "Rectangle" },
      { action: "set-measurement-tool", tool: "count", label: "Count" },
      { action: "set-measurement-tool", tool: "deduct", label: "Deduct opening" },
      { action: "set-measurement-tool", tool: "exclusion", label: "Exclusion" },
      { action: "set-measurement-tool", tool: "assembly", label: "Assembly" },
      { action: "open-scale-modal", label: "Scale calibration" },
      { action: "add-sample-manual-measurement", label: "Add sample" },
      { action: "viewer-undo", label: "Undo" },
      { action: "viewer-redo", label: "Redo" },
    ],
    "scope-review": [
      { action: "set-review-filter", filter: "all", label: "Show all detected scope" },
      { action: "set-review-filter", filter: "low-confidence", label: "Low confidence only" },
      { action: "set-review-filter", filter: "unapproved", label: "Unapproved only" },
      { action: "approve-selected-measurement", label: "Accept selected", primary: true },
      { action: "reject-selected-measurement", label: "Reject selected" },
      { action: "edit-selected-measurement", label: "Edit selected" },
      { action: "approve-high-confidence", label: "Accept all high-confidence" },
      { action: "push-approved-to-takeoff", label: "Push approved to Takeoff" },
    ],
    compare: [
      { action: "set-base-revision", label: "Base revision" },
      { action: "set-current-revision", label: "Current revision" },
      { action: "toggle-overlay-compare", label: "Overlay compare" },
      { action: "side-by-side-placeholder", label: "Side-by-side" },
      { action: "toggle-revision-changes", label: "Highlight changes" },
      { action: "show-quantity-delta", label: "Quantity delta" },
    ],
    "markup-rfi": [
      { action: "set-measurement-tool", tool: "comment", label: "Comment pin" },
      { action: "set-measurement-tool", tool: "rfi", label: "RFI pin" },
      { action: "set-measurement-tool", tool: "issue", label: "Issue pin" },
      { action: "add-rfi-pin", label: "Add RFI pin", primary: true },
      { action: "set-rfi-filter", filter: "all", label: "Show RFIs" },
      { action: "set-rfi-filter", filter: "resolved", label: "Resolved" },
      { action: "set-rfi-filter", filter: "unresolved", label: "Unresolved" },
    ],
  });

  function createId(prefix) {
    return typeof logic.createId === "function"
      ? logic.createId(prefix)
      : `${prefix || "id"}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function nowIso() {
    return typeof logic.nowIso === "function" ? logic.nowIso() : new Date().toISOString();
  }

  function cleanText(value) {
    return typeof logic.cleanText === "function" ? logic.cleanText(value) : String(value == null ? "" : value).trim();
  }

  function filterByProject(rows, projectId) {
    return typeof logic.filterByProject === "function"
      ? logic.filterByProject(rows, projectId)
      : (Array.isArray(rows) ? rows : []).filter((row) => row.projectId === projectId);
  }

  function getSheets(state, projectId) {
    const drawings = filterByProject(state.drawings, projectId);
    const measurements = filterByProject(state.drawingMeasurements, projectId);
    const rfis = filterByProject(state.rfis, projectId);
    const calibrations = filterByProject(state.drawingScaleCalibrations, projectId);
    return drawings.map((drawing, index) => {
      const number = drawing.sheetNumber || inferSheetNumber(drawing.name, index);
      const discipline = drawing.discipline || inferDiscipline(number, drawing.name);
      const sheetMeasurements = measurements.filter((item) => item.sheetId === drawing.id || item.drawingId === drawing.id);
      const sheetRfis = rfis.filter((item) => item.sheetId === drawing.id || item.drawingId === drawing.id);
      const calibration = calibrations.find((item) => item.sheetId === drawing.id);
      const statuses = buildSheetStatuses(sheetMeasurements, sheetRfis, calibration, drawing, index);
      return {
        ...drawing,
        sheetId: drawing.id,
        sheetNumber: number,
        sheetTitle: drawing.sheetTitle || inferSheetTitle(drawing.name, number),
        discipline,
        revision: drawing.revision || (index % 3 === 0 ? "Rev 2" : index % 2 === 0 ? "Rev 1" : "Rev 0"),
        revisionName: drawing.revisionName || (index % 3 === 0 ? "Addendum 02" : "Issued for Bid"),
        aiStatus: sheetMeasurements.length ? (sheetMeasurements.some((item) => item.status === "detected") ? "Estimator review" : "AI Draft") : "Not processed",
        confidence: sheetMeasurements.length ? Math.round(sheetMeasurements.reduce((sum, item) => sum + Number(item.confidence || 0), 0) / sheetMeasurements.length) : null,
        statuses,
        scaleCalibration: calibration || null,
      };
    });
  }

  function buildSheetStatuses(measurements, rfis, calibration, drawing, index) {
    const statuses = [];
    if (!measurements.length) statuses.push("Not processed");
    if (measurements.length) statuses.push("AI processed");
    if (measurements.some((item) => ["detected", "reviewed", "edited"].includes(item.status))) statuses.push("Needs review");
    if (!calibration || calibration.scaleSource === "missing") statuses.push("Scale missing");
    if (drawing.changedByAddendum || index % 3 === 0) statuses.push("Changed by addendum");
    if (rfis.length) statuses.push("Has RFI");
    if (measurements.length && measurements.every((item) => ["approved", "pushed_to_takeoff"].includes(item.status))) statuses.push("Approved");
    return statuses;
  }

  function inferSheetNumber(name, index) {
    const match = cleanText(name).match(/\b([A-Z]{1,3}[- ]?\d{2,4}(?:\.\d+)?)\b/i);
    if (match) return match[1].toUpperCase().replace(" ", "-");
    const prefixes = ["A", "S", "M", "E", "P"];
    return `${prefixes[index % prefixes.length]}-${String(index + 101).padStart(3, "0")}`;
  }

  function inferSheetTitle(name, sheetNumber) {
    const withoutExtension = cleanText(name).replace(/\.[^.]+$/, "");
    const title = withoutExtension.replace(sheetNumber, "").replace(/[-_]+/g, " ").trim();
    return title || "Floor Plan";
  }

  function inferDiscipline(number, name) {
    const text = `${number} ${name}`.toLowerCase();
    if (/^s-|struct/.test(text)) return "structural";
    if (/^m-|^e-|^p-|mep|mechanical|electrical|plumb/.test(text)) return "mep";
    return "architectural";
  }

  function defaultVisibleLayers() {
    return Object.fromEntries(DEFAULT_DRAWING_LAYERS.map((layer) => [layer.key, layer.defaultVisible]));
  }

  function measurementLayerKey(item) {
    if (item.createdBy === "user") return "manual-measurements";
    if (item.status === "approved" || item.status === "pushed_to_takeoff") return "approved-quantities";
    if (Number(item.confidence || 0) < 70) return "low-confidence";
    if (item.category === "walls") return "ai-walls";
    if (item.category === "rooms") return "ai-rooms";
    if (item.category === "paint") return "paint-scope";
    if (item.category === "ceilings") return "ceiling-scope";
    if (item.category === "flooring") return "flooring-scope";
    if (item.category === "framing") return "framing-scope";
    if (item.type === "room") return "ai-rooms";
    return "manual-measurements";
  }

  async function runAiMeasurement(options) {
    await sleep(850);
    const sheetIds = Array.isArray(options.sheetIds) && options.sheetIds.length ? options.sheetIds : [options.currentSheetId].filter(Boolean);
    const timestamp = nowIso();
    return sheetIds.flatMap((sheetId, sheetIndex) => mockMeasurementsForSheet({
      projectId: options.projectId,
      sheetId,
      focus: options.focus || "all",
      createdAt: timestamp,
      sheetIndex,
    }));
  }

  function mockMeasurementsForSheet({ projectId, sheetId, focus, createdAt, sheetIndex }) {
    const baseX = 10 + (sheetIndex % 3) * 4;
    const candidates = [
      {
        type: "linear",
        category: "walls",
        label: "L1 corridor wall framing",
        quantity: 148 + sheetIndex * 12,
        unit: "LF",
        confidence: 91,
        geometry: { kind: "line", points: [{ x: baseX, y: 28 }, { x: 70, y: 28 }] },
        calculationSummary: "Linear wall length traced along the main corridor partition run.",
        assumptions: ["Interior partition centerline used.", "Openings excluded in paint calculation only."],
      },
      {
        type: "area",
        category: "paint",
        label: "L1 paintable wall area",
        quantity: 14820 + sheetIndex * 240,
        unit: "SF",
        confidence: 86,
        geometry: { kind: "polygon", points: [{ x: 16, y: 34 }, { x: 66, y: 34 }, { x: 70, y: 55 }, { x: 18, y: 60 }] },
        calculationSummary: "Paintable wall area = wall perimeter x assumed wall height - openings + waste factor.",
        assumptions: ["Wall height assumed at 10 ft.", "5 percent waste included."],
      },
      {
        type: "area",
        category: "ceilings",
        label: "ACT ceiling zone",
        quantity: 6820 + sheetIndex * 120,
        unit: "SF",
        confidence: 74,
        geometry: { kind: "rect", x: 42, y: 43, width: 32, height: 20 },
        calculationSummary: "Ceiling area extracted from room boundary polygons tagged ACT.",
        warnings: ["Ceiling tag is partially obscured near gridline C."],
      },
      {
        type: "count",
        category: "doors",
        label: "Door opening count",
        quantity: 18 + sheetIndex,
        unit: "EA",
        confidence: 63,
        geometry: { kind: "point", x: 31, y: 67 },
        calculationSummary: "Door symbols counted from swing arcs and opening tags.",
        warnings: ["Low contrast in two door tags. Estimator review required."],
      },
    ];
    return candidates
      .filter((item) => focus === "all" || focus === "all-detectable" || item.category === focus)
      .map((item) => ({
        id: createId("drawing-measurement"),
        projectId,
        sheetId,
        drawingId: sheetId,
        source: "mock-ai",
        status: "detected",
        sourceRefs: [{ type: "sheet", id: sheetId }],
        warnings: item.warnings || [],
        assumptions: item.assumptions || [],
        createdBy: "ai",
        createdAt,
        updatedAt: createdAt,
        ...item,
      }));
  }

  function createManualMeasurement({ projectId, sheetId, tool }) {
    const timestamp = nowIso();
    const normalizedTool = tool || "line";
    const geometryByTool = {
      line: { kind: "line", points: [{ x: 22, y: 76 }, { x: 54, y: 76 }] },
      polyline: { kind: "polyline", points: [{ x: 18, y: 70 }, { x: 36, y: 78 }, { x: 58, y: 73 }] },
      area: { kind: "polygon", points: [{ x: 58, y: 18 }, { x: 78, y: 21 }, { x: 75, y: 37 }, { x: 56, y: 35 }] },
      rectangle: { kind: "rect", x: 12, y: 14, width: 22, height: 16 },
      count: { kind: "point", x: 82, y: 58 },
      deduct: { kind: "rect", x: 64, y: 58, width: 7, height: 6 },
      exclusion: { kind: "polygon", points: [{ x: 72, y: 72 }, { x: 86, y: 72 }, { x: 84, y: 85 }, { x: 71, y: 82 }] },
      assembly: { kind: "rect", x: 35, y: 13, width: 18, height: 13 },
    };
    const quantityByTool = {
      line: [32, "LF", "Manual line measurement"],
      polyline: [54, "LF", "Manual polyline measurement"],
      area: [410, "SF", "Manual area measurement"],
      rectangle: [352, "SF", "Manual rectangle area"],
      count: [1, "EA", "Manual count marker"],
      deduct: [28, "SF", "Deduct opening"],
      exclusion: [120, "SF", "Exclusion zone"],
      assembly: [1, "EA", "Assembly measurement"],
    };
    const [quantity, unit, label] = quantityByTool[normalizedTool] || quantityByTool.line;
    return {
      id: createId("drawing-measurement"),
      projectId,
      sheetId,
      drawingId: sheetId,
      type: normalizedTool === "count" || normalizedTool === "assembly" ? "count" : normalizedTool === "line" || normalizedTool === "polyline" ? "linear" : "area",
      category: normalizedTool === "deduct" ? "doors" : normalizedTool === "exclusion" ? "custom" : "custom",
      label,
      quantity,
      unit,
      confidence: 100,
      status: "draft",
      geometry: geometryByTool[normalizedTool] || geometryByTool.line,
      linkedTakeoffItemId: "",
      createdBy: "user",
      createdAt: timestamp,
      updatedAt: timestamp,
      notes: "Mock manual measurement placeholder. Replace with real canvas interaction later.",
      calculationSummary: "Manual measurement placeholder created from the selected tool state.",
      assumptions: [],
      warnings: [],
    };
  }

  function buildTakeoffRowsFromMeasurements(projectId, measurements) {
    const timestamp = nowIso();
    return measurements.map((item) => ({
      id: createId("takeoff"),
      projectId,
      drawingId: item.sheetId || item.drawingId || "",
      roomId: "",
      floorId: "",
      buildingId: "",
      scopeId: "",
      scopeCategory: categoryToScope(item.category),
      name: item.label,
      quantity: Number(item.quantity || 0),
      unit: item.unit || "",
      wallSf: item.category === "walls" || item.category === "paint" ? Number(item.quantity || 0) : 0,
      ceilingSf: item.category === "ceilings" ? Number(item.quantity || 0) : 0,
      paintSf: item.category === "paint" ? Number(item.quantity || 0) : 0,
      confidence: item.confidence,
      notes: `Pushed from Drawing Viewer measurement ${item.id}. AI measurements remain estimator-controlled before estimate generation.`,
      sourceType: "drawing-viewer",
      sourceMeasurementId: item.id,
      createdAt: timestamp,
      updatedAt: timestamp,
    }));
  }

  async function pushToTakeoff({ projectId, measurements }) {
    await sleep(450);
    return buildTakeoffRowsFromMeasurements(projectId, measurements);
  }

  function categoryToScope(category) {
    if (category === "ceilings") return "ceilings";
    if (category === "paint") return "paint";
    if (category === "framing" || category === "walls") return "drywall";
    return "carpentry";
  }

  function defaultScaleCalibration(projectId, sheetId) {
    const timestamp = nowIso();
    return {
      id: createId("scale"),
      projectId,
      sheetId,
      scaleValue: '1/8" = 1\'-0"',
      scaleSource: "auto",
      scaleConfidence: "Needs confirmation",
      scaleLocked: false,
      calibratedBy: "AI draft",
      calibratedAt: timestamp,
      multiScaleZones: [],
      twoPointDistance: "",
    };
  }

  function revisionDelta({ projectId, sheetId }) {
    return {
      revisionId: "rev-current",
      revisionName: "Rev 2",
      addendumName: "Addendum 02",
      uploadedAt: nowIso(),
      changedAreas: [
        { id: `${sheetId}-change-1`, projectId, sheetId, label: "Corridor finish change", geometry: { kind: "rect", x: 18, y: 30, width: 50, height: 18 } },
        { id: `${sheetId}-change-2`, projectId, sheetId, label: "Exam room layout update", geometry: { kind: "polygon", points: [{ x: 60, y: 58 }, { x: 82, y: 58 }, { x: 84, y: 76 }, { x: 61, y: 78 }] } },
      ],
      affectedMeasurements: [],
      quantityDeltas: [
        { label: "L1 paintable walls", previous: 13920, current: 14820, unit: "SF", delta: 900, cause: "Addendum 02 changed corridor paint system." },
        { label: "ACT ceiling zone", previous: 6550, current: 6820, unit: "SF", delta: 270, cause: "Updated soffit boundary near reception." },
      ],
    };
  }

  function createRfiPin({ projectId, sheetId, linkedMeasurementId, title, description }) {
    const timestamp = nowIso();
    return {
      id: createId("rfi"),
      projectId,
      sheetId,
      drawingId: sheetId,
      locationGeometry: { kind: "point", x: 74, y: 42 },
      title: cleanText(title) || "Confirm drawing condition",
      description: cleanText(description),
      question: cleanText(description) || "Confirm scope condition before quantity is pushed to takeoff.",
      status: "Draft",
      priority: "medium",
      linkedMeasurementId: linkedMeasurementId || "",
      createdBy: "estimator",
      createdAt: timestamp,
      updatedAt: timestamp,
    };
  }

  function createRfiFromIssue(issue) {
    return createRfiPin({
      projectId: issue.projectId,
      sheetId: issue.sheetId,
      linkedMeasurementId: issue.linkedMeasurementId || "",
      title: `RFI: ${issue.title || issue.label || "Drawing issue"}`,
      description: issue.description || issue.message || "",
    });
  }

  function searchDrawingWorkspace({ query, sheets, measurements, issues, rfis }) {
    const needle = cleanText(query).toLowerCase();
    if (!needle) return [];
    const results = [];
    for (const sheet of sheets) {
      const haystack = [sheet.sheetNumber, sheet.sheetTitle, sheet.discipline, sheet.revision, sheet.revisionName].join(" ").toLowerCase();
      if (haystack.includes(needle)) {
        results.push({ type: "sheet", id: sheet.id, sheetId: sheet.id, label: `${sheet.sheetNumber} - ${sheet.sheetTitle}` });
      }
    }
    for (const item of measurements) {
      const haystack = [item.label, item.category, item.type, item.status, item.calculationSummary].join(" ").toLowerCase();
      if (haystack.includes(needle)) {
        results.push({ type: "scope item", id: item.id, sheetId: item.sheetId || item.drawingId, label: item.label });
      }
    }
    for (const issue of issues) {
      const haystack = [issue.title, issue.description, issue.status, issue.severity].join(" ").toLowerCase();
      if (haystack.includes(needle)) {
        results.push({ type: "issue", id: issue.id, sheetId: issue.sheetId, label: issue.title });
      }
    }
    for (const rfi of rfis) {
      const haystack = [rfi.title, rfi.description, rfi.question, rfi.status, rfi.priority].join(" ").toLowerCase();
      if (haystack.includes(needle)) {
        results.push({ type: "rfi", id: rfi.id, sheetId: rfi.sheetId || rfi.drawingId, label: rfi.title });
      }
    }
    return results.slice(0, 12);
  }

  function sleep(ms) {
    return new Promise((resolve) => global.setTimeout(resolve, ms));
  }

  global.DrawingWorkspaceServices = {
    DEFAULT_DRAWING_LAYERS,
    SHEET_FILTERS,
    SCALE_OPTIONS,
    MODES,
    TOOLSETS,
    drawingService: {
      getSheets,
      defaultVisibleLayers,
    },
    measurementService: {
      runAiMeasurement,
      createManualMeasurement,
      pushToTakeoff,
      measurementLayerKey,
    },
    scaleService: {
      defaultScaleCalibration,
    },
    revisionService: {
      getRevisionDelta: revisionDelta,
    },
    rfiService: {
      createRfiPin,
      createRfiFromIssue,
    },
    searchService: {
      search: searchDrawingWorkspace,
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
