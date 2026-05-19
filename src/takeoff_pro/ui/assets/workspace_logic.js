(function attachWorkspaceLogic(global) {
  "use strict";

  const ROUTES = [
    "dashboard",
    "documents",
    "drawing-viewer",
    "takeoff",
    "scope-detection",
    "questions-rfis",
    "estimate",
    "risk-confidence",
    "output-center",
    "company-memory",
    "past-projects",
    "settings",
  ];

  const PROJECT_ENTITY_KEYS = [
    "drawings",
    "rooms",
    "floors",
    "buildings",
    "scopes",
    "scopeDetections",
    "drawingMeasurements",
    "drawingIssues",
    "drawingScaleCalibrations",
    "drawingRevisionReviews",
    "takeoffMeasurements",
    "estimateLineItems",
    "rfis",
    "riskItems",
    "exports",
    "activities",
  ];

  const DEFAULT_SETTINGS = Object.freeze({
    activeProjectId: null,
    activeDrawingIdByProject: {},
    companyName: "",
    companyAddress: "",
    companyPhone: "",
    companyEmail: "",
    units: "imperial",
    currency: "USD",
    defaultMarkupPercent: 10,
    defaultTaxPercent: 0,
    lowConfidenceThreshold: 70,
    userName: "",
    userEmail: "",
    reduceMotion: false,
  });

  function nowIso() {
    return new Date().toISOString();
  }

  function createId(prefix) {
    const cryptoObj = typeof global.crypto !== "undefined" ? global.crypto : null;
    const id = cryptoObj && typeof cryptoObj.randomUUID === "function"
      ? cryptoObj.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    return prefix ? `${prefix}-${id}` : id;
  }

  function createEmptyState() {
    return {
      schemaVersion: 1,
      projects: [],
      drawings: [],
      rooms: [],
      floors: [],
      buildings: [],
      scopes: [],
      scopeDetections: [],
      drawingMeasurements: [],
      drawingIssues: [],
      drawingScaleCalibrations: [],
      drawingRevisionReviews: [],
      takeoffMeasurements: [],
      materials: [],
      estimateLineItems: [],
      rfis: [],
      riskItems: [],
      exports: [],
      companyMemoryEntries: [],
      users: [],
      activities: [],
      settings: { ...DEFAULT_SETTINGS },
    };
  }

  function normalizeState(value) {
    const base = createEmptyState();
    if (!value || typeof value !== "object") return base;
    const next = { ...base, ...value };
    for (const key of [
      "projects",
      "drawings",
      "rooms",
      "floors",
      "buildings",
      "scopes",
      "scopeDetections",
      "drawingMeasurements",
      "drawingIssues",
      "drawingScaleCalibrations",
      "drawingRevisionReviews",
      "takeoffMeasurements",
      "materials",
      "estimateLineItems",
      "rfis",
      "riskItems",
      "exports",
      "companyMemoryEntries",
      "users",
      "activities",
    ]) {
      next[key] = Array.isArray(value[key]) ? value[key] : base[key];
    }
    next.settings = { ...DEFAULT_SETTINGS, ...(value.settings || {}) };
    next.settings.activeDrawingIdByProject = {
      ...DEFAULT_SETTINGS.activeDrawingIdByProject,
      ...(value.settings && value.settings.activeDrawingIdByProject
        ? value.settings.activeDrawingIdByProject
        : {}),
    };
    return next;
  }

  function createProject(state, input) {
    const name = String(input && input.name ? input.name : "").trim();
    if (!name) throw new Error("Project name is required.");
    const timestamp = nowIso();
    const project = {
      id: createId("project"),
      name,
      client: cleanText(input.client),
      address: cleanText(input.address),
      description: cleanText(input.description),
      projectType: cleanText(input.projectType),
      units: cleanText(input.units) || state.settings.units,
      archived: false,
      reviewStatus: "draft",
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    state.projects.push(project);
    state.settings.activeProjectId = project.id;
    addActivity(state, project.id, "project.created", `Created project “${project.name}”.`);
    return project;
  }

  function addActivity(state, projectId, type, message) {
    state.activities.unshift({
      id: createId("activity"),
      projectId,
      type,
      message,
      createdAt: nowIso(),
    });
  }

  function cleanText(value) {
    const text = String(value == null ? "" : value).trim();
    return text || "";
  }

  function toNumber(value, fallback) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function roundCurrency(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
  }

  function calculateEstimateLine(input) {
    const quantity = toNumber(input.quantity, 0);
    const unitCost = toNumber(input.unitCost, 0);
    const laborCost = toNumber(input.laborCost, 0);
    const materialCost = toNumber(input.materialCost, 0);
    const markupPercent = toNumber(input.markupPercent, 0);
    const taxPercent = toNumber(input.taxPercent, 0);
    const directUnitCost = unitCost + laborCost + materialCost;
    const directCost = quantity * directUnitCost;
    const markupAmount = directCost * (markupPercent / 100);
    const taxableSubtotal = directCost + markupAmount;
    const taxAmount = taxableSubtotal * (taxPercent / 100);
    const total = taxableSubtotal + taxAmount;
    return {
      quantity,
      unitCost,
      laborCost,
      materialCost,
      markupPercent,
      taxPercent,
      directUnitCost: roundCurrency(directUnitCost),
      directCost: roundCurrency(directCost),
      markupAmount: roundCurrency(markupAmount),
      taxAmount: roundCurrency(taxAmount),
      total: roundCurrency(total),
    };
  }

  function applyTakeoffFilters(rows, filters) {
    const safeRows = Array.isArray(rows) ? rows : [];
    return safeRows.filter((row) => {
      if (filters.roomId && row.roomId !== filters.roomId) return false;
      if (filters.floorId && row.floorId !== filters.floorId) return false;
      if (filters.buildingId && row.buildingId !== filters.buildingId) return false;
      if (filters.scopeId && row.scopeId !== filters.scopeId) return false;
      if (filters.scopeCategory && filters.scopeCategory !== "all" && row.scopeCategory !== filters.scopeCategory) {
        return false;
      }
      const query = cleanText(filters.query).toLowerCase();
      if (query) {
        const haystack = [
          row.name,
          row.roomName,
          row.floorName,
          row.buildingName,
          row.scopeName,
          row.notes,
        ].join(" ").toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }

  function calculateTakeoffSummary(rows) {
    const safeRows = Array.isArray(rows) ? rows : [];
    const wallSf = safeRows.reduce((sum, row) => sum + toNumber(row.wallSf, 0), 0);
    const ceilingSf = safeRows.reduce((sum, row) => sum + toNumber(row.ceilingSf, 0), 0);
    const paintSf = safeRows.reduce((sum, row) => sum + toNumber(row.paintSf, 0), 0);
    const quantity = safeRows.reduce((sum, row) => sum + toNumber(row.quantity, 0), 0);
    const confidenceValues = safeRows
      .map((row) => toNumber(row.confidence, NaN))
      .filter((value) => Number.isFinite(value));
    const averageConfidence = confidenceValues.length
      ? Math.round(confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length)
      : null;
    return {
      rowCount: safeRows.length,
      quantity,
      wallSf,
      ceilingSf,
      paintSf,
      averageConfidence,
      lowConfidenceCount: safeRows.filter((row) => toNumber(row.confidence, 100) < 70).length,
    };
  }

  function filterByProject(rows, projectId) {
    return (Array.isArray(rows) ? rows : []).filter((row) => row.projectId === projectId);
  }

  function projectRecords(state, projectId) {
    const result = {};
    for (const key of PROJECT_ENTITY_KEYS) {
      result[key] = filterByProject(state[key], projectId);
    }
    return result;
  }

  function searchProject(state, projectId, query) {
    const needle = cleanText(query).toLowerCase();
    if (!needle || !projectId) return [];
    const result = [];
    const collections = [
      ["drawing", state.drawings, ["name", "fileName"]],
      ["room", state.rooms, ["name"]],
      ["floor", state.floors, ["name"]],
      ["building", state.buildings, ["name"]],
      ["scope", state.scopes, ["name", "category"]],
      ["drawing-measurement", state.drawingMeasurements, ["label", "category", "status", "calculationSummary"]],
      ["drawing-issue", state.drawingIssues, ["title", "description", "status", "severity"]],
      ["takeoff", state.takeoffMeasurements, ["name", "scopeName", "notes"]],
      ["estimate", state.estimateLineItems, ["description", "unit"]],
      ["rfi", state.rfis, ["title", "question", "answer"]],
    ];
    for (const [type, rows, fields] of collections) {
      for (const row of filterByProject(rows, projectId)) {
        const relatedValues = type === "takeoff"
          ? [
            findLinkedValue(state.drawings, row.drawingId),
            findLinkedValue(state.rooms, row.roomId),
            findLinkedValue(state.floors, row.floorId),
            findLinkedValue(state.buildings, row.buildingId),
            findLinkedValue(state.scopes, row.scopeId),
          ]
          : [];
        const text = [...fields.map((field) => cleanText(row[field])), ...relatedValues]
          .join(" ")
          .toLowerCase();
        if (text.includes(needle)) {
          result.push({ type, id: row.id, label: firstNonEmpty(row.name, row.label, row.title, row.description, row.fileName), row });
        }
      }
    }
    return result;
  }

  function findLinkedValue(rows, id) {
    return cleanText((rows || []).find((row) => row.id === id)?.name);
  }

  function firstNonEmpty(...values) {
    return values.map(cleanText).find(Boolean) || "Untitled";
  }

  function buildProjectBundle(state, projectId) {
    const project = state.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Select a project before exporting.");
    return {
      exportedAt: nowIso(),
      project,
      drawings: filterByProject(state.drawings, projectId),
      rooms: filterByProject(state.rooms, projectId),
      floors: filterByProject(state.floors, projectId),
      buildings: filterByProject(state.buildings, projectId),
      scopes: filterByProject(state.scopes, projectId),
      scopeDetections: filterByProject(state.scopeDetections, projectId),
      drawingMeasurements: filterByProject(state.drawingMeasurements, projectId),
      drawingIssues: filterByProject(state.drawingIssues, projectId),
      drawingScaleCalibrations: filterByProject(state.drawingScaleCalibrations, projectId),
      drawingRevisionReviews: filterByProject(state.drawingRevisionReviews, projectId),
      takeoffMeasurements: filterByProject(state.takeoffMeasurements, projectId),
      estimateLineItems: filterByProject(state.estimateLineItems, projectId),
      rfis: filterByProject(state.rfis, projectId),
      riskItems: filterByProject(state.riskItems, projectId),
      exports: filterByProject(state.exports, projectId),
      activities: filterByProject(state.activities, projectId),
      companyMemoryEntries: state.companyMemoryEntries,
      materials: state.materials,
      settings: state.settings,
    };
  }

  function buildProjectJson(state, projectId) {
    return JSON.stringify(buildProjectBundle(state, projectId), null, 2);
  }

  function buildProjectCsv(state, projectId) {
    const bundle = buildProjectBundle(state, projectId);
    const rows = [
      ["record_type", "id", "name", "quantity", "unit", "status", "confidence", "total"],
    ];
    for (const row of bundle.drawingMeasurements) {
      rows.push([
        "drawing_measurement",
        row.id,
        row.label,
        row.quantity,
        row.unit,
        row.status || "",
        row.confidence,
        "",
      ]);
    }
    for (const row of bundle.takeoffMeasurements) {
      rows.push([
        "takeoff",
        row.id,
        row.name,
        row.quantity,
        row.unit,
        row.status || "",
        row.confidence,
        "",
      ]);
    }
    for (const row of bundle.estimateLineItems) {
      const calc = calculateEstimateLine(row);
      rows.push([
        "estimate",
        row.id,
        row.description,
        row.quantity,
        row.unit,
        row.sourceType || "manual",
        row.confidence,
        calc.total,
      ]);
    }
    for (const row of bundle.rfis) {
      rows.push([
        "rfi",
        row.id,
        row.title,
        "",
        "",
        row.status,
        "",
        "",
      ]);
    }
    return rows.map((row) => row.map(escapeCsv).join(",")).join("\n");
  }

  function escapeCsv(value) {
    const text = String(value == null ? "" : value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function duplicateProject(state, projectId) {
    const original = state.projects.find((item) => item.id === projectId);
    if (!original) throw new Error("Project not found.");
    const timestamp = nowIso();
    const projectMap = new Map([[projectId, createId("project")]]);
    const idMaps = Object.fromEntries(PROJECT_ENTITY_KEYS.map((key) => [key, new Map()]));
    const clonedProject = {
      ...original,
      id: projectMap.get(projectId),
      name: `${original.name} Copy`,
      archived: false,
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    state.projects.push(clonedProject);

    for (const key of PROJECT_ENTITY_KEYS) {
      const clones = filterByProject(state[key], projectId).map((row) => {
        const nextId = createId(key.slice(0, -1));
        idMaps[key].set(row.id, nextId);
        return { ...row, id: nextId, projectId: clonedProject.id, createdAt: timestamp, updatedAt: timestamp };
      });
      state[key].push(...clones);
    }

    remapProjectReferences(state, clonedProject.id, idMaps);
    state.settings.activeProjectId = clonedProject.id;
    addActivity(state, clonedProject.id, "project.duplicated", `Duplicated project “${original.name}”.`);
    return clonedProject;
  }

  function remapProjectReferences(state, projectId, idMaps) {
    for (const drawing of filterByProject(state.drawings, projectId)) {
      drawing.active = false;
    }
    for (const row of filterByProject(state.takeoffMeasurements, projectId)) {
      row.drawingId = remap(idMaps.drawings, row.drawingId);
      row.roomId = remap(idMaps.rooms, row.roomId);
      row.floorId = remap(idMaps.floors, row.floorId);
      row.buildingId = remap(idMaps.buildings, row.buildingId);
      row.scopeId = remap(idMaps.scopes, row.scopeId);
    }
    for (const row of filterByProject(state.scopeDetections, projectId)) {
      row.drawingId = remap(idMaps.drawings, row.drawingId);
      row.roomId = remap(idMaps.rooms, row.roomId);
      row.scopeId = remap(idMaps.scopes, row.scopeId);
      row.promotedMeasurementId = remap(idMaps.takeoffMeasurements, row.promotedMeasurementId);
      row.promotedEstimateItemId = remap(idMaps.estimateLineItems, row.promotedEstimateItemId);
    }
    for (const row of filterByProject(state.drawingMeasurements, projectId)) {
      row.sheetId = remap(idMaps.drawings, row.sheetId);
      row.drawingId = remap(idMaps.drawings, row.drawingId);
      row.linkedTakeoffItemId = remap(idMaps.takeoffMeasurements, row.linkedTakeoffItemId);
    }
    for (const row of filterByProject(state.drawingIssues, projectId)) {
      row.sheetId = remap(idMaps.drawings, row.sheetId);
      row.linkedMeasurementId = remap(idMaps.drawingMeasurements, row.linkedMeasurementId);
    }
    for (const row of filterByProject(state.drawingScaleCalibrations, projectId)) {
      row.sheetId = remap(idMaps.drawings, row.sheetId);
    }
    for (const row of filterByProject(state.drawingRevisionReviews, projectId)) {
      row.sheetId = remap(idMaps.drawings, row.sheetId);
    }
    for (const row of filterByProject(state.estimateLineItems, projectId)) {
      row.sourceMeasurementId = remap(idMaps.takeoffMeasurements, row.sourceMeasurementId);
      row.scopeId = remap(idMaps.scopes, row.scopeId);
    }
    for (const row of filterByProject(state.rfis, projectId)) {
      row.sheetId = remap(idMaps.drawings, row.sheetId);
      row.drawingId = remap(idMaps.drawings, row.drawingId);
      row.roomId = remap(idMaps.rooms, row.roomId);
      row.scopeId = remap(idMaps.scopes, row.scopeId);
      row.estimateItemId = remap(idMaps.estimateLineItems, row.estimateItemId);
      row.linkedMeasurementId = remap(idMaps.drawingMeasurements, row.linkedMeasurementId);
    }
    for (const row of filterByProject(state.riskItems, projectId)) {
      if (row.referenceType === "takeoff") row.referenceId = remap(idMaps.takeoffMeasurements, row.referenceId);
      if (row.referenceType === "scope") row.referenceId = remap(idMaps.scopeDetections, row.referenceId);
      if (row.referenceType === "estimate") row.referenceId = remap(idMaps.estimateLineItems, row.referenceId);
    }
  }

  function remap(map, value) {
    return value ? map.get(value) || value : value;
  }

  function deriveRiskItems(state, projectId) {
    const threshold = toNumber(state.settings.lowConfidenceThreshold, 70);
    const existing = filterByProject(state.riskItems, projectId);
    const byKey = new Map(existing.map((row) => [`${row.referenceType}:${row.referenceId}`, row]));
    const derived = [];
    for (const row of filterByProject(state.takeoffMeasurements, projectId)) {
      addDerivedRisk(derived, byKey, projectId, "takeoff", row.id, row.name, row.confidence, threshold);
    }
    for (const row of filterByProject(state.scopeDetections, projectId)) {
      addDerivedRisk(derived, byKey, projectId, "scope", row.id, row.title, row.confidence, threshold);
    }
    for (const row of filterByProject(state.estimateLineItems, projectId)) {
      addDerivedRisk(derived, byKey, projectId, "estimate", row.id, row.description, row.confidence, threshold);
    }
    return derived;
  }

  function addDerivedRisk(target, byKey, projectId, referenceType, referenceId, label, confidence, threshold) {
    const numeric = toNumber(confidence, 100);
    if (numeric >= threshold) return;
    const key = `${referenceType}:${referenceId}`;
    const saved = byKey.get(key);
    target.push(saved || {
      id: createId("risk"),
      projectId,
      referenceType,
      referenceId,
      label: firstNonEmpty(label),
      confidence: numeric,
      status: "open",
      overrideConfidence: null,
      note: "",
      createdAt: nowIso(),
      updatedAt: nowIso(),
    });
  }

  function averageConfidence(records) {
    const values = (Array.isArray(records) ? records : [])
      .map((row) => toNumber(row.overrideConfidence != null ? row.overrideConfidence : row.confidence, NaN))
      .filter((value) => Number.isFinite(value));
    if (!values.length) return null;
    return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
  }

  const api = {
    ROUTES,
    DEFAULT_SETTINGS,
    createEmptyState,
    normalizeState,
    createProject,
    addActivity,
    cleanText,
    calculateEstimateLine,
    applyTakeoffFilters,
    calculateTakeoffSummary,
    filterByProject,
    projectRecords,
    searchProject,
    buildProjectBundle,
    buildProjectJson,
    buildProjectCsv,
    duplicateProject,
    deriveRiskItems,
    averageConfidence,
    createId,
    nowIso,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.WorkspaceLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
