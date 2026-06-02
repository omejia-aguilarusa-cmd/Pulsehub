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
      { action: "open-scale-modal", label: "Scale (preset)" },
      { action: "start-two-point-calibration", label: "Two-point calibrate", primary: false },
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

  // ---------------------------------------------------------------------------
  // LM Studio integration helpers
  // ---------------------------------------------------------------------------

  function openTakeoffDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open("takeoff-workspace", 1);
      req.onerror = () => reject(req.error || new Error("Could not open workspace database."));
      req.onsuccess = () => resolve(req.result);
      req.onupgradeneeded = () => {};
    });
  }

  function getTakeoffFile(db, id) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("files", "readonly");
        const req = tx.objectStore("files").get(id);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => resolve(null);
      } catch (_) {
        resolve(null);
      }
    });
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }

  function isImageBlob(blob) {
    return blob instanceof Blob && (blob.type || "").startsWith("image/");
  }

  async function checkLmStudioHealth(baseUrl, apiKey, requestedModel) {
    const modelsUrl = baseUrl.replace(/\/+$/, "") + "/models";
    try {
      const resp = await fetch(modelsUrl, {
        method: "GET",
        headers: { Authorization: `Bearer ${apiKey}`, Accept: "application/json" },
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) {
        return { reachable: false, models: [], modelLoaded: false, error: `Server returned ${resp.status}` };
      }
      const data = await resp.json();
      const models = (Array.isArray(data.data) ? data.data : [])
        .filter((m) => m && typeof m.id === "string")
        .map((m) => m.id);
      const modelLoaded = !requestedModel || models.includes(requestedModel);
      return { reachable: true, models, modelLoaded, error: null };
    } catch (err) {
      const msg = err && err.name === "AbortError" ? "Health check timed out." : String(err);
      return { reachable: false, models: [], modelLoaded: false, error: msg };
    }
  }

  async function callLmStudioChatCompletion(chatUrl, apiKey, model, messages, maxTokens) {
    const body = {
      model,
      messages,
      max_tokens: maxTokens || 4096,
      response_format: { type: "json_object" },
    };
    const controller = new AbortController();
    const tid = global.setTimeout(() => controller.abort(), 120000);
    try {
      const resp = await fetch(chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      global.clearTimeout(tid);
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try { const e = await resp.json(); detail = (e.error && e.error.message) || detail; } catch (_) {}
        if (resp.status === 404) throw new Error(`Wrong endpoint: ${chatUrl} returned 404. Check AI_BASE_URL ends with /v1.`);
        if (resp.status === 503) throw new Error(`Model not loaded or LM Studio busy (503): ${detail}`);
        if (resp.status === 422 || resp.status === 400) throw new Error(`Bad request (${resp.status}) — image format may be unsupported: ${detail}`);
        throw new Error(`AI provider request failed: ${detail}`);
      }
      const data = await resp.json();
      const content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
      if (typeof content !== "string" || !content.trim()) throw new Error("LM Studio response did not include content.");
      return content.trim();
    } catch (err) {
      global.clearTimeout(tid);
      if (err && err.name === "AbortError") throw new Error("LM Studio request timed out (120 s). Try a shorter prompt or smaller image.");
      throw err;
    }
  }

  function buildPaintingTakeoffPromptText(options, sheetId) {
    const ch = options.ceilingHeightFt || 9;
    const doors = options.includeDoors !== false;
    const windows = options.includeWindows !== false;
    const trim = options.includeTrim !== false;
    return (
      "You are an expert drywall and painting estimator analyzing architectural construction plans.\n" +
      "Extract EVERY detail relevant to the drywall and paint scope. Do not guess — only report what is visible.\n" +
      "If a quantity is estimated rather than directly measured, mark it in assumptions with your reasoning.\n" +
      "Return strict JSON only. Do not include markdown fences.\n\n" +

      "Scope: drywall and painting\n" +
      "Prompt version: drywall-painting-takeoff-v2\n" +
      `Default ceiling height: ${ch} ft\n` +
      `Include doors: ${doors}\nInclude windows: ${windows}\nInclude trim: ${trim}\n\n` +

      "PAINTING formulas (apply when perimeter/area are available):\n" +
      "  wall_sf = perimeter_ft * ceiling_height_ft - door_count * 21 - window_count * 15\n" +
      "  ceiling_sf = floor_area_sf\n" +
      "  baseboard_lf = perimeter_ft\n" +
      "  door_trim_lf = door_count * 17\n" +
      "  window_trim_lf = window_count * 12\n" +
      "  total_trim_lf = baseboard_lf + door_trim_lf + window_trim_lf\n\n" +

      "DRYWALL formulas:\n" +
      "  gwb_sf = length_lf * height_ft * gwb_layers (both sides of partition)\n" +
      "  corner_bead_lf = number of outside corners * height_ft\n" +
      "  acoustic_sealant_lf = base of all rated partitions\n\n" +

      "Extract for EACH room or area:\n" +
      "  - Room name, type, floor area SF, perimeter FT, wall SF, ceiling SF\n" +
      "  - Door count, window count, trim LF\n" +
      "  - Paint finish code or system if visible (e.g. P-1, eggshell, semi-gloss)\n\n" +

      "Extract for EACH partition/wall assembly:\n" +
      "  - Wall type ID (e.g. WT-1, W-3), length LF, height FT, area SF\n" +
      "  - GWB layers (each side), stud size (e.g. 3-5/8\"), stud spacing\n" +
      "  - Fire rating (1-hr, 2-hr, etc.), STC/sound rating if noted\n" +
      "  - Whether shaft wall, corridor wall, or partition\n\n" +

      "Extract for EACH ceiling assembly:\n" +
      "  - Ceiling type (drywall, ACT, GWB, soffit, open), area SF\n" +
      "  - Finish level if noted (Level 4, Level 5)\n\n" +

      "Also extract overall:\n" +
      "  - Total metal stud framing LF\n" +
      "  - Total corner bead LF\n" +
      "  - Total acoustic sealant LF\n" +
      "  - Total GWB SF\n\n" +

      `Pages:\n- pageId=${sheetId}\n\n` +

      "Required JSON schema (fill every field; use null when unknown):\n" +
      '{"rooms":[{"id":"string","name":"string","type":"office|bathroom|corridor|lobby|storage|mechanical|unknown","pageId":"string","locationDescription":"string","confidence":0.0,"floorAreaSf":null,"perimeterFt":null,"wallSf":null,"ceilingSf":null,"doorCount":0,"windowCount":0,"trimLf":null,"paintFinish":"string","assumptions":[]}],' +
      '"drywallAssemblies":[{"id":"string","wallType":"string","pageId":"string","locationDescription":"string","lengthLf":null,"heightFt":null,"areaSf":null,"gwbLayers":1,"studSize":"string","studSpacing":"string","fireRating":"string","soundRating":"string","isShaftWall":false,"confidence":0.0,"assumptions":[]}],' +
      '"ceilingAssemblies":[{"id":"string","ceilingType":"drywall|ACT|GWB|soffit|open|unknown","pageId":"string","locationDescription":"string","areaSf":null,"finishLevel":"string","confidence":0.0,"assumptions":[]}],' +
      '"elements":[{"type":"door|window|wall|special_surface|note|unknown","count":0,"pageId":"string","locationDescription":"string","confidence":0.0}],' +
      '"totals":{"floorAreaSf":0,"wallSf":0,"ceilingSf":0,"doorCount":0,"windowCount":0,"trimLf":0,"gwbSf":0,"metalStudLf":0,"cornerBeadLf":0,"acousticSealantLf":0},' +
      '"warnings":[],"confidenceScore":0.0}'
    );
  }

  function parseTakeoffJson(rawText, options, sheetIds, model, provider) {
    const cleaned = rawText.replace(/^```(?:json)?\s*/m, "").replace(/\s*```\s*$/m, "").trim();
    let parsed;
    try {
      parsed = JSON.parse(cleaned);
    } catch (err) {
      throw new Error(`JSON parse failed: ${err.message}. Response: ${rawText.substring(0, 200)}`);
    }
    const rooms = Array.isArray(parsed.rooms) ? parsed.rooms : [];
    const drywallAssemblies = Array.isArray(parsed.drywallAssemblies) ? parsed.drywallAssemblies : [];
    const ceilingAssemblies = Array.isArray(parsed.ceilingAssemblies) ? parsed.ceilingAssemblies : [];
    const elements = Array.isArray(parsed.elements) ? parsed.elements : [];
    const warnings = Array.isArray(parsed.warnings) ? parsed.warnings : [];
    const parsedTotals = (parsed.totals && typeof parsed.totals === "object") ? parsed.totals : {};
    const totals = {
      floorAreaSf: Number(parsedTotals.floorAreaSf) || rooms.reduce((s, r) => s + (Number(r.floorAreaSf) || 0), 0),
      wallSf: Number(parsedTotals.wallSf) || rooms.reduce((s, r) => s + (Number(r.wallSf) || 0), 0),
      ceilingSf: Number(parsedTotals.ceilingSf) || rooms.reduce((s, r) => s + (Number(r.ceilingSf) || 0), 0),
      doorCount: Number(parsedTotals.doorCount) || rooms.reduce((s, r) => s + (Number(r.doorCount) || 0), 0),
      windowCount: Number(parsedTotals.windowCount) || rooms.reduce((s, r) => s + (Number(r.windowCount) || 0), 0),
      trimLf: Number(parsedTotals.trimLf) || rooms.reduce((s, r) => s + (Number(r.trimLf) || 0), 0),
      gwbSf: Number(parsedTotals.gwbSf) || drywallAssemblies.reduce((s, a) => s + (Number(a.areaSf) || 0), 0),
      metalStudLf: Number(parsedTotals.metalStudLf) || drywallAssemblies.reduce((s, a) => s + (Number(a.lengthLf) || 0), 0),
      cornerBeadLf: Number(parsedTotals.cornerBeadLf) || 0,
      acousticSealantLf: Number(parsedTotals.acousticSealantLf) || 0,
    };
    const allConfidences = [
      ...rooms.map((r) => Number(r.confidence) || 0),
      ...drywallAssemblies.map((a) => Number(a.confidence) || 0),
    ];
    const confidence = allConfidences.length
      ? Math.round(allConfidences.reduce((s, c) => s + c, 0) / allConfidences.length * 100) / 100
      : 0;
    const timestamp = nowIso();
    return {
      id: createId("ai-takeoff-run"),
      projectId: options.projectId,
      status: "complete",
      scope: "drywall-painting",
      provider: provider || "lmstudio",
      model: model || "",
      promptVersion: "drywall-painting-takeoff-v2",
      pageIds: sheetIds,
      pages: sheetIds.map((pageId) => ({
        pageId,
        rooms: rooms.filter((r) => !r.pageId || r.pageId === pageId).map((r) => ({
          id: r.id || createId("room"),
          name: r.name || "Unnamed room",
          type: r.type || "unknown",
          pageId,
          locationDescription: r.locationDescription || "",
          confidence: Number(r.confidence) || 0,
          floorAreaSf: r.floorAreaSf != null ? Number(r.floorAreaSf) : null,
          perimeterFt: r.perimeterFt != null ? Number(r.perimeterFt) : null,
          wallSf: r.wallSf != null ? Number(r.wallSf) : null,
          ceilingSf: r.ceilingSf != null ? Number(r.ceilingSf) : null,
          doorCount: Number(r.doorCount) || 0,
          windowCount: Number(r.windowCount) || 0,
          trimLf: r.trimLf != null ? Number(r.trimLf) : null,
          paintFinish: r.paintFinish || "",
          assumptions: Array.isArray(r.assumptions) ? r.assumptions : [],
        })),
        drywallAssemblies: drywallAssemblies.filter((a) => !a.pageId || a.pageId === pageId).map((a) => ({
          id: a.id || createId("dw-asm"),
          wallType: a.wallType || "Unknown",
          pageId,
          locationDescription: a.locationDescription || "",
          lengthLf: a.lengthLf != null ? Number(a.lengthLf) : null,
          heightFt: a.heightFt != null ? Number(a.heightFt) : null,
          areaSf: a.areaSf != null ? Number(a.areaSf) : null,
          gwbLayers: Number(a.gwbLayers) || 1,
          studSize: a.studSize || "",
          studSpacing: a.studSpacing || "",
          fireRating: a.fireRating || "",
          soundRating: a.soundRating || "",
          isShaftWall: Boolean(a.isShaftWall),
          confidence: Number(a.confidence) || 0,
          assumptions: Array.isArray(a.assumptions) ? a.assumptions : [],
        })),
        ceilingAssemblies: ceilingAssemblies.filter((c) => !c.pageId || c.pageId === pageId).map((c) => ({
          id: c.id || createId("ceil-asm"),
          ceilingType: c.ceilingType || "unknown",
          pageId,
          locationDescription: c.locationDescription || "",
          areaSf: c.areaSf != null ? Number(c.areaSf) : null,
          finishLevel: c.finishLevel || "",
          confidence: Number(c.confidence) || 0,
          assumptions: Array.isArray(c.assumptions) ? c.assumptions : [],
        })),
        elements: elements.filter((e) => !e.pageId || e.pageId === pageId).map((e) => ({
          type: e.type || "unknown",
          count: Number(e.count) || 0,
          pageId,
          locationDescription: e.locationDescription || "",
          confidence: Number(e.confidence) || 0,
        })),
        measurements: [],
        warnings,
      })),
      totals,
      confidenceScore: confidence,
      warnings,
      options: {
        ceilingHeightFt: Number(options.ceilingHeightFt || 9),
        includeDoors: options.includeDoors !== false,
        includeWindows: options.includeWindows !== false,
        includeTrim: options.includeTrim !== false,
      },
      createdAt: timestamp,
      updatedAt: timestamp,
    };
  }

  function makeFailedTakeoffRun(options, warningMessage, sheetIds, provider) {
    const timestamp = nowIso();
    return {
      id: createId("ai-takeoff-run"),
      projectId: options.projectId,
      status: "failed",
      scope: "painting",
      provider: provider || "lmstudio",
      model: "",
      promptVersion: "painting-takeoff-v1",
      pageIds: sheetIds,
      pages: sheetIds.map((pageId) => ({
        pageId, rooms: [], elements: [], measurements: [], warnings: [warningMessage],
      })),
      totals: { floorAreaSf: 0, wallSf: 0, ceilingSf: 0, doorCount: 0, windowCount: 0, trimLf: 0 },
      confidenceScore: 0,
      warnings: [warningMessage],
      options: {
        ceilingHeightFt: Number(options.ceilingHeightFt || 9),
        includeDoors: options.includeDoors !== false,
        includeWindows: options.includeWindows !== false,
        includeTrim: options.includeTrim !== false,
      },
      createdAt: timestamp,
      updatedAt: timestamp,
    };
  }

  // ---------------------------------------------------------------------------
  // Cloud provider helpers — OpenAI and Anthropic
  // ---------------------------------------------------------------------------

  async function callOpenAiChatCompletion(apiKey, model, messages, maxTokens) {
    const body = {
      model: model || "gpt-4o",
      messages,
      max_tokens: maxTokens || 4096,
      response_format: { type: "json_object" },
    };
    const controller = new AbortController();
    const tid = global.setTimeout(() => controller.abort(), 120000);
    try {
      const resp = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      global.clearTimeout(tid);
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try { const e = await resp.json(); detail = (e.error && e.error.message) || detail; } catch (_) {}
        if (resp.status === 401) throw new Error(`OpenAI API key is invalid or missing. Check OPENAI_API_KEY in your .env file. (${detail})`);
        if (resp.status === 429) throw new Error(`OpenAI rate limit reached. Wait and try again. (${detail})`);
        throw new Error(`OpenAI request failed: ${detail}`);
      }
      const data = await resp.json();
      const content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
      if (typeof content !== "string" || !content.trim()) throw new Error("OpenAI response did not include content.");
      return content.trim();
    } catch (err) {
      global.clearTimeout(tid);
      if (err && err.name === "AbortError") throw new Error("OpenAI request timed out (120 s).");
      throw err;
    }
  }

  async function callAnthropicMessages(apiKey, model, messages, maxTokens) {
    const body = {
      model: model || "claude-3-5-sonnet-latest",
      max_tokens: maxTokens || 4096,
      messages,
    };
    const controller = new AbortController();
    const tid = global.setTimeout(() => controller.abort(), 120000);
    try {
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      global.clearTimeout(tid);
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try { const e = await resp.json(); detail = (e.error && e.error.message) || detail; } catch (_) {}
        if (resp.status === 401) throw new Error(`Anthropic API key is invalid or missing. Check ANTHROPIC_API_KEY in your .env file. (${detail})`);
        throw new Error(`Anthropic request failed: ${detail}`);
      }
      const data = await resp.json();
      const item = Array.isArray(data.content) && data.content.find((c) => c.type === "text");
      if (!item || typeof item.text !== "string" || !item.text.trim()) throw new Error("Anthropic response did not include text content.");
      return item.text.trim();
    } catch (err) {
      global.clearTimeout(tid);
      if (err && err.name === "AbortError") throw new Error("Anthropic request timed out (120 s).");
      throw err;
    }
  }

  // ---------------------------------------------------------------------------
  // Real painting takeoff — calls LM Studio, OpenAI, or Anthropic based on
  // TAKEOFF_AI_CONFIG injected by the Python host at startup.
  // ---------------------------------------------------------------------------

  async function runPaintingTakeoff(options) {
    const config = typeof global.TAKEOFF_AI_CONFIG === "object" && global.TAKEOFF_AI_CONFIG
      ? global.TAKEOFF_AI_CONFIG : null;
    const sheetIds = Array.isArray(options.pageIds) && options.pageIds.length ? options.pageIds : [];
    const provider = config && config.provider ? config.provider : "";

    // No recognised provider — return not_configured stub
    if (!config || !["lmstudio", "openai", "anthropic", "deepseek"].includes(provider)) {
      await sleep(300);
      const timestamp = nowIso();
      const note = config && config.oauthNote ? config.oauthNote : "";
      const warnMsg = provider === "openai_oauth"
        ? note || "OpenAI OAuth is not supported for desktop apps. Set AI_PROVIDER=openai and OPENAI_API_KEY."
        : "AI provider is not configured. Set AI_PROVIDER in your .env file (openai, anthropic, or lmstudio) and restart.";
      return {
        id: createId("ai-takeoff-run"),
        projectId: options.projectId,
        status: "not_configured",
        scope: "painting",
        provider: "none",
        model: "",
        promptVersion: "painting-takeoff-v1",
        pageIds: sheetIds,
        pages: sheetIds.map((pageId) => ({
          pageId, rooms: [], elements: [], measurements: [], warnings: [warnMsg],
        })),
        totals: { floorAreaSf: 0, wallSf: 0, ceilingSf: 0, doorCount: 0, windowCount: 0, trimLf: 0 },
        confidenceScore: 0,
        warnings: [warnMsg],
        options: {
          ceilingHeightFt: Number(options.ceilingHeightFt || 9),
          includeDoors: options.includeDoors !== false,
          includeWindows: options.includeWindows !== false,
          includeTrim: options.includeTrim !== false,
        },
        createdAt: timestamp,
        updatedAt: timestamp,
      };
    }

    const apiKey = config.apiKey || "";
    const model = config.takeoffModel || config.chatModel || "";
    const maxTokens = config.maxTokens || 4096;

    // Validate API key for cloud providers before making any network calls.
    if ((provider === "openai" || provider === "anthropic" || provider === "deepseek") && !apiKey) {
      const keyVar = provider === "openai" ? "OPENAI_API_KEY" : provider === "deepseek" ? "DEEPSEEK_API_KEY" : "ANTHROPIC_API_KEY";
      return makeFailedTakeoffRun(
        options,
        `${provider} API key is missing. Set ${keyVar} in your .env file and restart.`,
        sheetIds,
        provider
      );
    }

    if (typeof options.onProgress === "function") options.onProgress("Checking AI provider", 5);

    // ---------------------------------------------------------------------------
    // LM Studio path
    // ---------------------------------------------------------------------------
    if (provider === "lmstudio") {
      const baseUrl = (config.baseUrl || "http://127.0.0.1:1234/v1").replace(/\/+$/, "");

      const health = await checkLmStudioHealth(baseUrl, apiKey || "lm-studio-local", model);
      if (!health.reachable) {
        return makeFailedTakeoffRun(
          options,
          `LM Studio is not reachable at ${baseUrl}. Start LM Studio and enable the Local Server. (${health.error || ""})`,
          sheetIds,
          "lmstudio"
        );
      }
      if (model && !health.modelLoaded) {
        const loaded = health.models.length ? health.models.join(", ") : "none";
        return makeFailedTakeoffRun(
          options,
          `Model '${model}' is not loaded in LM Studio. Loaded: ${loaded}. Load the required model and try again.`,
          sheetIds,
          "lmstudio"
        );
      }

      if (typeof options.onProgress === "function") options.onProgress("Loading drawing", 15);

      const sheetId = sheetIds[0] || null;
      let imageDataUrl = null;
      if (sheetId) {
        try {
          const db = await openTakeoffDb();
          const file = await getTakeoffFile(db, sheetId);
          if (isImageBlob(file)) imageDataUrl = await blobToDataUrl(file);
        } catch (_) {}
      }

      if (typeof options.onProgress === "function") options.onProgress("Running AI analysis", 30);

      const promptText = buildPaintingTakeoffPromptText(options, sheetId || "unknown");
      const effectiveModel = model || (health.models.length ? health.models[0] : "");
      const messages = imageDataUrl
        ? [{ role: "user", content: [
            { type: "text", text: promptText },
            { type: "image_url", image_url: { url: imageDataUrl } },
          ] }]
        : [{ role: "user", content: promptText }];

      if (typeof options.onProgress === "function") options.onProgress("Waiting for AI response", 50);

      let rawText;
      try {
        rawText = await callLmStudioChatCompletion(
          baseUrl + "/chat/completions", apiKey || "lm-studio-local", effectiveModel, messages, maxTokens
        );
      } catch (err) {
        return makeFailedTakeoffRun(options, String(err), sheetIds, "lmstudio");
      }

      if (typeof options.onProgress === "function") options.onProgress("Parsing results", 85);
      try {
        return parseTakeoffJson(rawText, options, sheetIds, effectiveModel, "lmstudio");
      } catch (err) {
        return makeFailedTakeoffRun(options, String(err), sheetIds, "lmstudio");
      }
    }

    // ---------------------------------------------------------------------------
    // DeepSeek path — OpenAI-compatible, text-only (no vision)
    // ---------------------------------------------------------------------------
    if (provider === "deepseek") {
      const deepseekUrl = (config.baseUrl || "https://api.deepseek.com/v1").replace(/\/+$/, "") + "/chat/completions";
      const deepseekModel = model || config.deepseekModel || "deepseek-chat";
      if (typeof options.onProgress === "function") options.onProgress("Building prompt", 20);
      const promptText = buildPaintingTakeoffPromptText(options, sheetIds[0] || "unknown");
      if (typeof options.onProgress === "function") options.onProgress("Waiting for DeepSeek response", 40);
      let rawText;
      try {
        rawText = await callLmStudioChatCompletion(
          deepseekUrl, apiKey, deepseekModel,
          [{ role: "user", content: promptText }],
          maxTokens
        );
      } catch (err) {
        return makeFailedTakeoffRun(options, String(err), sheetIds, "deepseek");
      }
      if (typeof options.onProgress === "function") options.onProgress("Parsing results", 85);
      try {
        return parseTakeoffJson(rawText, options, sheetIds, deepseekModel, "deepseek");
      } catch (err) {
        return makeFailedTakeoffRun(options, String(err), sheetIds, "deepseek");
      }
    }

    // ---------------------------------------------------------------------------
    // OpenAI and Anthropic paths — support images and PDFs
    // ---------------------------------------------------------------------------
    if (typeof options.onProgress === "function") options.onProgress("Loading drawing", 15);

    const sheetId = sheetIds[0] || null;
    let fileBlob = null;
    let imageDataUrl = null;
    let pdfBase64 = null;

    if (sheetId) {
      try {
        const db = await openTakeoffDb();
        fileBlob = await getTakeoffFile(db, sheetId);
        if (fileBlob instanceof Blob) {
          const isPdfFile = fileBlob.type === "application/pdf" || (fileBlob.name || "").toLowerCase().endsWith(".pdf");
          if (isPdfFile) {
            // Anthropic supports PDFs natively via base64 document type.
            // OpenAI Chat Completions does not — PDFs are sent as text-only for OpenAI.
            if (provider === "anthropic") {
              pdfBase64 = (await blobToDataUrl(fileBlob)).split(",")[1] || "";
            }
          } else if (isImageBlob(fileBlob)) {
            imageDataUrl = await blobToDataUrl(fileBlob);
          }
        }
      } catch (_) {}
    }

    if (typeof options.onProgress === "function") options.onProgress("Running AI analysis", 30);

    const promptText = buildPaintingTakeoffPromptText(options, sheetId || "unknown");
    const effectiveModel = model || (provider === "openai" ? "gpt-4o" : "claude-3-5-sonnet-latest");

    if (typeof options.onProgress === "function") options.onProgress("Waiting for AI response", 50);

    let rawText;
    try {
      if (provider === "openai") {
        const messages = imageDataUrl
          ? [{ role: "user", content: [
              { type: "text", text: promptText },
              { type: "image_url", image_url: { url: imageDataUrl } },
            ] }]
          : [{ role: "user", content: promptText }];
        rawText = await callOpenAiChatCompletion(apiKey, effectiveModel, messages, maxTokens);
      } else {
        // Anthropic — supports image, PDF (base64 document), or text-only
        let content;
        if (pdfBase64) {
          content = [
            { type: "document", source: { type: "base64", media_type: "application/pdf", data: pdfBase64 } },
            { type: "text", text: promptText },
          ];
        } else if (imageDataUrl) {
          content = [
            { type: "image", source: { type: "base64", media_type: imageDataUrl.split(";")[0].split(":")[1] || "image/png", data: imageDataUrl.split(",")[1] || "" } },
            { type: "text", text: promptText },
          ];
        } else {
          content = [{ type: "text", text: promptText }];
        }
        rawText = await callAnthropicMessages(apiKey, effectiveModel, [{ role: "user", content }], maxTokens);
      }
    } catch (err) {
      return makeFailedTakeoffRun(options, String(err), sheetIds, provider);
    }

    if (typeof options.onProgress === "function") options.onProgress("Parsing results", 85);
    try {
      return parseTakeoffJson(rawText, options, sheetIds, effectiveModel, provider);
    } catch (err) {
      return makeFailedTakeoffRun(options, String(err), sheetIds, provider);
    }
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
      pixelsPerFoot: "",
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

  // ---------------------------------------------------------------------------
  // PDF page render service — renders PDF pages to blob-URL images via pdf.js
  // ---------------------------------------------------------------------------
  const pdfPageRenderService = (function () {
    const _pageCache = new Map(); // `${fileUrl}-p${pageNum}` → { blobUrl, pageCount }
    const _docCache = new Map();  // fileUrl → Promise<PDFDocumentProxy>

    function _getDoc(fileUrl) {
      if (_docCache.has(fileUrl)) return _docCache.get(fileUrl);
      if (!global.pdfjsLib) return Promise.reject(new Error("pdf.js not loaded"));
      const p = global.pdfjsLib.getDocument(fileUrl).promise;
      _docCache.set(fileUrl, p);
      return p;
    }

    async function renderPage(fileUrl, pageNum) {
      const key = `${fileUrl}-p${pageNum || 1}`;
      if (_pageCache.has(key)) return _pageCache.get(key);
      try {
        const doc = await _getDoc(fileUrl);
        const page = await doc.getPage(pageNum || 1);
        const viewport = page.getViewport({ scale: 1.8 });
        const canvas = global.document.createElement("canvas");
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport }).promise;
        const blobUrl = await new Promise((res, rej) =>
          canvas.toBlob((b) => (b ? res(URL.createObjectURL(b)) : rej(new Error("toBlob failed"))), "image/png")
        );
        const unscaled = page.getViewport({ scale: 1 });
        const result = { blobUrl, width: canvas.width, height: canvas.height, pageCount: doc.numPages, pdfWidthPt: unscaled.width, pdfHeightPt: unscaled.height };
        _pageCache.set(key, result);
        return result;
      } catch (err) {
        console.warn("[pdfPageRenderService] render failed:", err);
        return null;
      }
    }

    function clearFile(fileUrl) {
      for (const [k, v] of _pageCache) {
        if (k.startsWith(fileUrl + "-p")) {
          if (v && v.blobUrl) URL.revokeObjectURL(v.blobUrl);
          _pageCache.delete(k);
        }
      }
      _docCache.delete(fileUrl);
    }

    function parseScaleToFeetPerUnit(scaleString) {
      // Returns real feet per paper inch for the given scale string.
      // e.g. "1/8\" = 1’-0\"" → 8  (1 paper inch = 8 real feet)
      //      "1/4\" = 1’-0\"" → 4
      //      "1\" = 1’-0\""  → 1
      if (!scaleString || scaleString === "Custom") return null;
      const m1 = scaleString.match(/(\d+)\/(\d+)"\s*=\s*1[‘’\-]/);
      if (m1) return Number(m1[2]) / Number(m1[1]); // e.g. 8/1 = 8 ft/in for "1/8"=1’"
      const m2 = scaleString.match(/(\d+)"\s*=\s*1[‘’\-]/);
      if (m2) return 1 / Number(m2[1]); // e.g. 1/2 ft/in for "2"=1’"
      const m3 = scaleString.match(/1"\s*=\s*(\d+)’/);
      if (m3) return Number(m3[1]); // e.g. 10 ft/in for "1"=10’"
      return null;
    }

    return { renderPage, clearFile, parseScaleToFeetPerUnit };
  })();

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
      runPaintingTakeoff,
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
    pdfPageRenderService,
  };
})(typeof window !== "undefined" ? window : globalThis);
