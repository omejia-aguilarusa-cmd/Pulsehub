(function bootstrapWorkspace() {
  "use strict";

  const {
    ROUTES,
    addActivity,
    averageConfidence,
    buildProjectCsv,
    buildProjectJson,
    aiTakeoffRooms,
    calculateAiTakeoffTotals,
    calculateEstimateLine,
    calculateTakeoffSummary,
    cleanText,
    createEmptyState,
    createId,
    createProject,
    deriveRiskItems,
    duplicateProject,
    filterByProject,
    normalizeState,
    nowIso,
    searchProject,
    applyTakeoffFilters,
  } = window.WorkspaceLogic;
  const drawingServices = window.DrawingWorkspaceServices;

  const appRoot = document.getElementById("app");
  const DB_NAME = "takeoff-workspace";
  const DB_VERSION = 1;
  const ROUTE_LABELS = {
    dashboard: "Dashboard",
    documents: "Documents",
    "drawing-viewer": "Drawing viewer",
    takeoff: "Takeoff",
    "scope-detection": "Scope detection",
    "questions-rfis": "Questions / RFIs",
    estimate: "Estimate",
    "risk-confidence": "Risk & confidence",
    "output-center": "Output center",
    "company-memory": "Company memory",
    "past-projects": "Past projects",
    settings: "Settings",
  };

  const PROJECT_ROUTES = new Set([
    "dashboard",
    "documents",
    "drawing-viewer",
    "takeoff",
    "scope-detection",
    "questions-rfis",
    "estimate",
    "risk-confidence",
    "output-center",
  ]);

  const statefulUi = {
    loaded: false,
    error: "",
    route: getRoute(),
    sidebarOpen: false,
    searchQuery: "",
    selectedDrawingId: null,
    viewerPageByDrawingId: {},
    previewUrls: new Map(),
    missingFileIds: new Set(),
    drawingMode: readPreference("lastSelectedMode", "view"),
    sheetNavigatorCollapsed: readPreference("sheetNavigatorCollapsed", false),
    rightInspectorCollapsed: readPreference("rightInspectorCollapsed", false),
    focusModeEnabled: false,
    focusRestoreLayout: null,
    visibleLayers: readJsonPreference("visibleDrawingLayers", drawingServices.drawingService.defaultVisibleLayers()),
    confidenceHeatmap: readPreference("confidenceHeatmap", false),
    selectedMeasurementId: null,
    selectedIssueId: null,
    selectedRfiId: null,
    selectedMeasurementTool: "",
    activeInspectorTab: "selection",
    aiProcessingState: null,
    aiTakeoffStage: "",
    sheetFilters: {
      discipline: "all",
      query: "",
    },
    drawingSearchQuery: "",
    reviewFilter: "all",
    rfiFilter: "all",
    compare: {
      baseRevisionId: "rev-previous",
      currentRevisionId: "rev-current",
      highlightChanges: true,
      overlayCompare: true,
    },
    takeoffFilters: {
      roomId: "",
      floorId: "",
      buildingId: "",
      scopeId: "",
      scopeCategory: "all",
      query: "",
    },
    modal: null,
    toasts: [],
  };

  let state = createEmptyState();
  let dbPromise = null;

  init();

  async function init() {
    try {
      const db = await openDb();
      const stored = await dbGet(db, "state", "workspace");
      state = normalizeState(stored || createEmptyState());
      statefulUi.loaded = true;
      if (!ROUTES.includes(statefulUi.route)) statefulUi.route = "dashboard";
      const activeProject = getActiveProject();
      if (activeProject) {
        statefulUi.selectedDrawingId = state.settings.activeDrawingIdByProject[activeProject.id] || null;
      }
      syncDerivedRisks();
      render();
    } catch (error) {
      statefulUi.error = error instanceof Error ? error.message : String(error);
      statefulUi.loaded = true;
      render();
    }
  }

  async function openDb() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onerror = () => reject(request.error || new Error("Could not open local workspace database."));
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("state")) db.createObjectStore("state");
        if (!db.objectStoreNames.contains("files")) db.createObjectStore("files");
      };
      request.onsuccess = () => resolve(request.result);
    });
    return dbPromise;
  }

  function dbGet(db, store, key) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, "readonly");
      const request = tx.objectStore(store).get(key);
      request.onerror = () => reject(request.error || new Error(`Could not read ${store}.`));
      request.onsuccess = () => resolve(request.result);
    });
  }

  function dbSet(db, store, key, value) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, "readwrite");
      tx.objectStore(store).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error(`Could not write ${store}.`));
    });
  }

  function dbDelete(db, store, key) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, "readwrite");
      tx.objectStore(store).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error(`Could not delete ${store}.`));
    });
  }

  async function saveState() {
    const db = await openDb();
    await dbSet(db, "state", "workspace", state);
  }

  async function saveAndRender(message) {
    syncDerivedRisks();
    await saveState();
    if (message) pushToast(message);
    render();
  }

  function getRoute() {
    return location.hash.replace(/^#\/?/, "") || "dashboard";
  }

  function navigate(route) {
    statefulUi.route = route;
    location.hash = `#/${route}`;
    statefulUi.sidebarOpen = false;
    render();
  }

  window.addEventListener("hashchange", () => {
    statefulUi.route = getRoute();
    statefulUi.sidebarOpen = false;
    render();
  });

  document.addEventListener("click", handleClick);
  document.addEventListener("submit", handleSubmit);
  document.addEventListener("change", handleChange);
  document.addEventListener("input", handleInput);
  document.addEventListener("keydown", handleKeyboardShortcuts);

  function render() {
    if (!statefulUi.loaded) {
      appRoot.innerHTML = `<div class="empty-state" style="margin:24px"><h2>Loading workspace…</h2></div>`;
      return;
    }
    if (statefulUi.error) {
      appRoot.innerHTML = `<div class="empty-state" style="margin:24px"><h2>Workspace could not load</h2><p>${escapeHtml(statefulUi.error)}</p></div>`;
      return;
    }
    const project = getActiveProject();
    appRoot.innerHTML = `
      <div class="app-shell ${statefulUi.focusModeEnabled && statefulUi.route === "drawing-viewer" ? "drawing-focus-mode" : ""}">
        ${renderSidebar(project)}
        ${statefulUi.sidebarOpen ? `<button class="mobile-overlay" data-action="close-sidebar" aria-label="Close navigation"></button>` : ""}
        <main class="main-shell">
          ${renderProjectHeader(project)}
          <section class="content">${renderRoute(project)}</section>
        </main>
      </div>
      ${renderModal(project)}
      ${renderToasts()}
    `;
    hydratePreviewIfNeeded();
  }

  function renderSidebar(project) {
    const unresolvedRfis = project ? filterByProject(state.rfis, project.id).filter((item) => item.status !== "resolved").length : 0;
    const projectLabel = project ? project.name : "No project selected";
    const userName = cleanText(state.settings.userName);
    const userEmail = cleanText(state.settings.userEmail);
    const userInitials = userName ? initials(userName) : "—";
    return `
      <aside class="sidebar ${statefulUi.sidebarOpen ? "open" : ""}" aria-label="Project navigation">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true"><img src="icons/takeoffpro-mark-transparent.svg" alt=""></div>
          <div class="brand-copy"><strong>Takeoff</strong><span>Estimating Workspace</span></div>
        </div>
        <div class="sidebar-scroll">
          <button class="sidebar-action" data-action="open-project-modal" aria-label="Create new project"><span class="nav-icon" aria-hidden="true">${iconSvg("plus")}</span><span class="nav-text">New project</span></button>
          <section class="sidebar-section">
            <p class="sidebar-label">Project</p>
            <p class="sidebar-project">${escapeHtml(projectLabel)}</p>
            <nav class="nav-list" aria-label="Workspace pages">
              ${renderNavLink("dashboard", "Dashboard")}
              ${renderNavLink("documents", "Documents")}
              ${renderNavLink("drawing-viewer", "Drawing viewer")}
              ${renderNavLink("takeoff", "Takeoff")}
              ${renderNavLink("scope-detection", "Scope detection")}
              ${renderNavLink("questions-rfis", "Questions / RFIs", unresolvedRfis)}
              ${renderNavLink("estimate", "Estimate")}
              ${renderNavLink("risk-confidence", "Risk & confidence")}
              ${renderNavLink("output-center", "Output center")}
            </nav>
          </section>
          <section class="sidebar-section">
            <p class="sidebar-label">Company</p>
            <nav class="nav-list" aria-label="Company pages">
              ${renderNavLink("company-memory", "Company memory")}
              ${renderNavLink("past-projects", "Past projects")}
              ${renderNavLink("settings", "Settings")}
            </nav>
          </section>
        </div>
        <div class="user-card">
          <button class="user-button" data-route="settings" aria-label="Open settings">
            <span class="avatar">${escapeHtml(userInitials)}</span>
            <span class="user-meta">
              <strong>${escapeHtml(userName || "Set up profile")}</strong>
              <span>${escapeHtml(userEmail || "Workspace settings")}</span>
            </span>
          </button>
        </div>
      </aside>
    `;
  }

  function renderNavLink(route, label, badge) {
    const active = statefulUi.route === route ? "active" : "";
    return `<a href="#/${route}" class="nav-link ${active}" data-route="${route}"><span class="nav-icon" aria-hidden="true">${iconSvg(route)}</span><span class="nav-text">${label}</span>${badge ? `<span class="nav-badge">${badge}</span>` : ""}</a>`;
  }

  function iconSvg(name) {
    const paths = {
      plus: '<path d="M12 5v14M5 12h14"/>',
      dashboard: '<rect x="4" y="4" width="6" height="6" rx="1.2"/><rect x="14" y="4" width="6" height="6" rx="1.2"/><rect x="4" y="14" width="6" height="6" rx="1.2"/><rect x="14" y="14" width="6" height="6" rx="1.2"/>',
      documents: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5"/><path d="M9.5 12h5M9.5 16h5"/>',
      "drawing-viewer": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="m7 16 4-4 3 3 2-2 3 3"/><circle cx="9" cy="9" r="1.3"/>',
      takeoff: '<path d="M4 5h16M4 11h16M4 17h16M8 5v14M14 5v14"/>',
      "scope-detection": '<path d="M5 12.5 9.5 17 19 7"/><rect x="4" y="4" width="16" height="16" rx="2"/>',
      "questions-rfis": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.8 2.8 0 0 1 5.2 1.4c0 2-2.7 2.2-2.7 4"/><path d="M12 18h.01"/>',
      estimate: '<path d="M8 3h8l3 3v15H8z"/><path d="M16 3v4h4"/><path d="M10.5 11h5M10.5 15h5M10.5 19h3"/>',
      "risk-confidence": '<path d="M12 4 21 20H3z"/><path d="M12 9v5M12 17h.01"/>',
      "output-center": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
      "company-memory": '<path d="M8 4h8l2 3v10l-2 3H8l-2-3V7z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
      "past-projects": '<path d="M4 7h16"/><path d="M6 7l1.5 13h9L18 7"/><path d="M9 7V4h6v3"/><path d="M10 11h4"/>',
      settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    };
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" focusable="false">${paths[name] || paths.dashboard}</svg>`;
  }

  function renderProjectHeader(project) {
    const routeLabel = ROUTE_LABELS[statefulUi.route] || "Workspace";
    const status = projectStatus(project);
    const searchResults = project && statefulUi.searchQuery ? searchProject(state, project.id, statefulUi.searchQuery) : [];
    return `
      <header class="topbar">
        <div class="topbar-left">
          <button class="menu-toggle" data-action="toggle-sidebar" aria-label="Toggle navigation">☰</button>
          <div class="breadcrumb"><strong>${escapeHtml(project ? project.name : "Workspace")}</strong><span>/</span><span>${escapeHtml(routeLabel)}</span></div>
          ${project ? `<span class="status-pill"><span class="status-dot"></span>${escapeHtml(status)}</span>` : ""}
        </div>
        <div class="topbar-right">
          <div class="search-wrap">
            <input class="search-input" data-role="project-search" type="search" value="${escapeAttribute(statefulUi.searchQuery)}" placeholder="Search current project" aria-label="Search current project" ${project ? "" : "disabled"}>
            ${renderSearchResults(searchResults)}
          </div>
          <button class="button primary" data-action="open-export-modal" ${project ? "" : "disabled"} aria-label="Export project data">Export</button>
        </div>
      </header>
    `;
  }

  function renderSearchResults(results) {
    if (!statefulUi.searchQuery) return "";
    if (!results.length) return `<div class="search-results"><div class="search-result"><span>No matching records</span></div></div>`;
    return `<div class="search-results">${results.slice(0, 8).map((item) => `
      <button class="search-result" data-action="open-search-result" data-type="${item.type}" data-id="${item.id}">
        <span>${escapeHtml(item.label)}</span><span class="result-type">${escapeHtml(item.type)}</span>
      </button>`).join("")}</div>`;
  }

  function renderRoute(project) {
    if (PROJECT_ROUTES.has(statefulUi.route) && !project) return renderNoProjectState();
    switch (statefulUi.route) {
      case "dashboard": return renderDashboard(project);
      case "documents": return renderDocuments(project);
      case "drawing-viewer": return renderAdvancedDrawingViewer(project);
      case "takeoff": return renderTakeoff(project);
      case "scope-detection": return renderScopeDetection(project);
      case "questions-rfis": return renderQuestionsRfis(project);
      case "estimate": return renderEstimate(project);
      case "risk-confidence": return renderRiskConfidence(project);
      case "output-center": return renderOutputCenter(project);
      case "company-memory": return renderCompanyMemory();
      case "past-projects": return renderPastProjects();
      case "settings": return renderSettings();
      default: return renderDashboard(project);
    }
  }

  function renderNoProjectState() {
    return `
      <div class="empty-state">
        <h2>Create your first project</h2>
        <p>The workspace starts empty by design. Create a project or import one to begin uploading drawings, measuring takeoff, and producing estimates.</p>
        <div class="inline-actions">
          <button class="button primary" data-action="open-project-modal">New project</button>
          <button class="button" data-action="trigger-project-import">Import project JSON</button>
          <input id="project-import" type="file" accept="application/json,.json" hidden>
        </div>
      </div>
    `;
  }

  function renderDashboard(project) {
    const drawings = filterByProject(state.drawings, project.id);
    const rfis = filterByProject(state.rfis, project.id);
    const unresolvedRfis = rfis.filter((item) => item.status !== "resolved").length;
    const estimateItems = filterByProject(state.estimateLineItems, project.id);
    const estimateTotal = estimateItems.reduce((sum, item) => sum + calculateEstimateLine(item).total, 0);
    const allConfidence = [
      ...filterByProject(state.takeoffMeasurements, project.id),
      ...filterByProject(state.scopeDetections, project.id),
      ...estimateItems,
    ];
    const confidence = averageConfidence(allConfidence);
    const activities = filterByProject(state.activities, project.id).slice(0, 6);
    return `
      <div class="page">
        ${renderPageHeader("Dashboard", "Real project overview, review state, and recent activity.", `<button class="button" data-action="cycle-project-status">Update status</button>`)}
        <div class="card-grid">
          ${metricCard("Project status", projectStatus(project), "Stored review state")}
          ${metricCard("Drawings", drawings.length, "Uploaded documents")}
          ${metricCard("Unresolved RFIs", unresolvedRfis, "Open questions")}
          ${metricCard("Estimate total", formatCurrency(estimateTotal), confidence == null ? "No confidence records yet" : `${confidence}% average confidence`)}
        </div>
        <section class="panel">
          <div class="panel-header"><div><h2>Recent activity</h2><p>Changes saved for this project.</p></div></div>
          <div class="panel-body">
            ${activities.length ? `<div class="activity-list">${activities.map((item) => `<div class="activity-row"><strong>${escapeHtml(item.message)}</strong><span>${formatDateTime(item.createdAt)}</span></div>`).join("")}</div>` : renderInlineEmpty("No project activity yet.", "Upload drawings or add takeoff data to start building the project history.")}
          </div>
        </section>
      </div>
    `;
  }

  function renderDocuments(project) {
    const drawings = filterByProject(state.drawings, project.id);
    return `
      <div class="page">
        ${renderPageHeader("Documents", "Upload, rename, delete, and open real project files.", `<button class="button primary" data-action="trigger-document-upload">Upload files</button><input id="document-upload" type="file" multiple accept="application/pdf,image/*,.pdf,.png,.jpg,.jpeg,.tif,.tiff" hidden>`)}
        <section class="panel">
          <div class="panel-header"><div><h2>Document register</h2><p>${drawings.length ? `${drawings.length} saved file${drawings.length === 1 ? "" : "s"}` : "No documents uploaded"}</p></div></div>
          ${drawings.length ? `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Size</th><th>Uploaded</th><th>Actions</th></tr></thead><tbody>${drawings.map((item) => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.mimeType || item.extension || "Unknown")}</td><td>${formatBytes(item.size)}</td><td>${formatDate(item.uploadedAt)}</td><td><div class="inline-actions"><button class="button ghost" data-action="preview-document" data-id="${item.id}" aria-label="Preview ${escapeAttribute(item.name)}">Preview</button><button class="button ghost" data-action="open-document" data-id="${item.id}" aria-label="Open ${escapeAttribute(item.name)}">Open</button><button class="button ghost" data-action="rename-document" data-id="${item.id}" aria-label="Rename ${escapeAttribute(item.name)}">Rename</button><button class="button ghost" data-action="delete-document" data-id="${item.id}" aria-label="Delete ${escapeAttribute(item.name)}">Delete</button></div></td></tr>`).join("")}</tbody></table></div>` : `<div class="panel-body">${renderInlineEmpty("No documents yet.", "Upload drawings or project documents to populate the register.", `<button class="button primary" data-action="trigger-document-upload">Upload files</button>`)}</div>`}
        </section>
      </div>
    `;
  }

  function renderDrawingViewer(project) {
    const drawings = filterByProject(state.drawings, project.id);
    const activeId = state.settings.activeDrawingIdByProject[project.id] || drawings[0]?.id || null;
    const active = drawings.find((item) => item.id === activeId) || null;
    const page = active ? statefulUi.viewerPageByDrawingId[active.id] || 1 : 1;
    return `
      <div class="page">
        ${renderPageHeader("Drawing viewer", "Preview supported drawing files and choose the active source for takeoff.")}
        ${drawings.length ? `<div class="split-grid"><section class="panel"><div class="panel-header"><div><h2>Drawings</h2><p>Select the active source.</p></div></div><div class="panel-body"><div class="document-list">${drawings.map((item) => `<button class="document-item ${activeId === item.id ? "active" : ""}" data-action="select-drawing" data-id="${item.id}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.mimeType || item.extension || "Unknown")}</span></button>`).join("")}</div></div></section><section class="panel"><div class="panel-header"><div><h2>${escapeHtml(active ? active.name : "Preview")}</h2><p>${active ? "Active drawing source" : "Select a drawing"}</p></div>${active && isPdf(active) ? `<div class="inline-actions"><button class="button" data-action="viewer-prev-page" data-id="${active.id}" aria-label="Previous PDF page">Previous</button><button class="button" data-action="viewer-next-page" data-id="${active.id}" aria-label="Next PDF page">Next</button><input class="button" style="width:78px" type="number" min="1" value="${page}" data-role="viewer-page" data-id="${active.id}" aria-label="PDF page number"></div>` : ""}</div><div class="panel-body">${renderViewer(active, page)}</div></section></div>` : renderInlineEmpty("No drawings available.", "Upload a supported file in Documents to preview it here.", `<button class="button primary" data-route="documents">Go to Documents</button>`)}
      </div>
    `;
  }

  function renderViewer(active, page) {
    if (!active) return "";
    const url = statefulUi.previewUrls.get(active.id);
    if (statefulUi.missingFileIds.has(active.id)) {
      return `<div class="empty-state"><h3>Original file unavailable</h3><p>The document record exists, but the original local file is not stored in this workspace. Re-upload the document to preview it again.</p><button class="button" data-route="documents">Go to Documents</button></div>`;
    }
    if (!url) return `<div class="viewer-frame"><div class="empty-state" style="margin:18px"><h3>Loading preview…</h3></div></div>`;
    if (isPdf(active)) return `<div class="viewer-frame"><iframe title="${escapeAttribute(active.name)} preview" src="${escapeAttribute(url)}#page=${page}"></iframe></div>`;
    if (isImage(active)) return `<div class="viewer-frame"><img alt="${escapeAttribute(active.name)} preview" src="${escapeAttribute(url)}"></div>`;
    return `<div class="empty-state"><h3>Preview not available</h3><p>This file type is stored and can be opened, but it cannot be previewed in the viewer.</p><button class="button" data-action="open-document" data-id="${active.id}">Open file</button></div>`;
  }

  function renderAdvancedDrawingViewer(project) {
    const sheets = drawingServices.drawingService.getSheets(state, project.id);
    const preferredActiveId = state.settings.activeDrawingIdByProject[project.id] || sheets[0]?.id || null;
    const active = sheets.find((item) => item.id === preferredActiveId) || sheets[0] || null;
    const activeId = active?.id || null;
    const page = active ? statefulUi.viewerPageByDrawingId[active.id] || 1 : 1;
    const allMeasurements = filterByProject(state.drawingMeasurements, project.id);
    const measurements = active ? allMeasurements.filter((item) => (item.sheetId || item.drawingId) === active.id) : [];
    const issues = active ? getDrawingIssues(project.id, active, measurements) : [];
    const rfis = active ? getDrawingRfis(project.id, active.id) : [];
    const revision = active ? drawingServices.revisionService.getRevisionDelta({ projectId: project.id, sheetId: active.id }) : null;
    return `
      <div class="drawing-workspace ${statefulUi.focusModeEnabled ? "focus-enabled" : ""}">
        ${renderDrawingTopBar(project, active, measurements, revision)}
        ${sheets.length ? `
          ${renderModeToolbar(active)}
          <div class="drawing-review-layout ${statefulUi.sheetNavigatorCollapsed ? "sheets-collapsed" : ""} ${statefulUi.rightInspectorCollapsed ? "inspector-collapsed" : ""}">
            ${renderSheetNavigator(sheets, activeId)}
            <section class="drawing-canvas-region" aria-label="Drawing canvas">
              ${renderDrawingCanvas(project, active, page, measurements, issues, rfis, revision)}
            </section>
            ${renderRightInspector(project, active, measurements, issues, rfis, revision)}
          </div>
        ` : renderInlineEmpty("No drawings available.", "Upload a supported file in Documents to preview it here.", `<button class="button primary" data-route="documents">Go to Documents</button>`)}
      </div>
    `;
  }

  function renderDrawingTopBar(project, active, measurements, revision) {
    const confidence = measurements.length ? Math.round(measurements.reduce((sum, item) => sum + Number(item.confidence || 0), 0) / measurements.length) : null;
    const aiStatus = statefulUi.aiProcessingState?.status === "processing" ? "Processing" : active ? active.aiStatus : "Not processed";
    const results = active ? getDrawingSearchResults(project, active) : [];
    return `
      <header class="drawing-topbar" aria-label="Drawing Viewer controls">
        <div class="drawing-topbar-main">
          <div class="breadcrumb drawing-breadcrumb"><strong>${escapeHtml(project.name)}</strong><span>/</span><span>Drawing Viewer</span></div>
          <div class="sheet-title-line">
            <strong>${active ? `${escapeHtml(active.sheetNumber)} - ${escapeHtml(active.sheetTitle)}` : "No sheet selected"}</strong>
            ${active ? `<span class="tag">${escapeHtml(active.revision)} - ${escapeHtml(active.revisionName)}</span>` : ""}
            ${renderStatusTag(aiStatus)}
            ${confidence == null ? `<span class="tag">Confidence unavailable</span>` : `<span class="tag ok">Confidence ${confidence}%</span>`}
            <span class="tag warn">Bid due in 10 days</span>
          </div>
        </div>
        <div class="drawing-topbar-actions">
          <div class="search-wrap drawing-search-wrap">
            <input class="search-input drawing-search-input" data-role="drawing-search" type="search" value="${escapeAttribute(statefulUi.drawingSearchQuery)}" placeholder="Search sheet, scope, RFI" aria-label="Search drawings">
            ${renderDrawingSearchResults(results)}
          </div>
          <button class="button" data-action="share-placeholder" aria-label="Share drawing placeholder">Share</button>
          <button class="button primary" data-action="run-ai-takeoff" ${active ? "" : "disabled"} aria-label="Run AI Takeoff">Run AI Takeoff</button>
          <button class="button" data-action="open-export-modal" aria-label="Export drawing data placeholder">Export</button>
          <button class="button ${statefulUi.focusModeEnabled ? "primary" : ""}" data-action="toggle-focus-mode" aria-label="${statefulUi.focusModeEnabled ? "Exit focus mode" : "Enter focus mode"}">${statefulUi.focusModeEnabled ? "Exit focus" : "Focus"}</button>
        </div>
      </header>
      ${statefulUi.aiProcessingState?.status === "processing" ? `<div class="ai-run-strip"><strong>${escapeHtml(statefulUi.aiTakeoffStage || "Running AI Takeoff")}</strong><div class="ai-progress compact"><span style="width:${Number(statefulUi.aiProcessingState.progress || 10)}%"></span></div></div>` : ""}
      ${revision ? `<div class="addendum-strip"><strong>${escapeHtml(revision.addendumName)}</strong><span>${escapeHtml(revision.quantityDeltas[0]?.cause || "Revision delta available.")}</span></div>` : ""}
    `;
  }

  function renderDrawingSearchResults(results) {
    if (!statefulUi.drawingSearchQuery) return "";
    if (!results.length) return `<div class="search-results"><div class="search-result"><span>No drawing results</span></div></div>`;
    return `<div class="search-results">${results.map((item) => `
      <button class="search-result" data-action="open-drawing-search-result" data-id="${escapeAttribute(item.id)}" data-type="${escapeAttribute(item.type)}" data-sheet-id="${escapeAttribute(item.sheetId || "")}">
        <span>${escapeHtml(item.label)}</span><span class="result-type">${escapeHtml(item.type)}</span>
      </button>`).join("")}</div>`;
  }

  function renderModeToolbar(active) {
    return `
      <div class="drawing-toolbar" aria-label="Drawing mode toolbar">
        <div class="mode-selector" role="tablist" aria-label="Drawing mode">
          ${drawingServices.MODES.map((mode) => `<button class="mode-tab ${statefulUi.drawingMode === mode.key ? "active" : ""}" role="tab" aria-selected="${statefulUi.drawingMode === mode.key ? "true" : "false"}" data-action="set-drawing-mode" data-mode="${mode.key}">${escapeHtml(mode.label)}</button>`).join("")}
        </div>
        <div class="secondary-toolbar">
          ${renderSecondaryToolbar(active)}
          ${renderLayerManager()}
        </div>
      </div>
    `;
  }

  function renderSecondaryToolbar(active) {
    const tools = drawingServices.TOOLSETS[statefulUi.drawingMode] || [];
    const toolButtons = tools.map((tool) => {
      if (tool.action === "set-base-revision") {
        return `<label class="compact-field"><span>Base</span><select data-role="base-revision"><option value="rev-previous" ${statefulUi.compare.baseRevisionId === "rev-previous" ? "selected" : ""}>Rev 1</option><option value="rev-current" ${statefulUi.compare.baseRevisionId === "rev-current" ? "selected" : ""}>Rev 2</option></select></label>`;
      }
      if (tool.action === "set-current-revision") {
        return `<label class="compact-field"><span>Current</span><select data-role="current-revision"><option value="rev-current" ${statefulUi.compare.currentRevisionId === "rev-current" ? "selected" : ""}>Rev 2</option><option value="rev-addendum" ${statefulUi.compare.currentRevisionId === "rev-addendum" ? "selected" : ""}>Addendum 02</option></select></label>`;
      }
      const activeTool = tool.action === "set-measurement-tool" && statefulUi.selectedMeasurementTool === tool.tool;
      const activeToggle = (tool.action === "toggle-revision-changes" && statefulUi.compare.highlightChanges) || (tool.action === "toggle-overlay-compare" && statefulUi.compare.overlayCompare);
      return `<button class="tool-button ${tool.primary ? "primary" : ""} ${activeTool || activeToggle ? "active" : ""}" data-action="${tool.action}" ${tool.tool ? `data-tool="${tool.tool}"` : ""} ${tool.filter ? `data-filter="${tool.filter}"` : ""} ${active ? "" : "disabled"} aria-label="${escapeAttribute(tool.label)}">${escapeHtml(tool.label)}</button>`;
    }).join("");
    return toolButtons || `<span class="muted-text">No tools available.</span>`;
  }

  function renderLayerManager() {
    return `
      <details class="layer-manager">
        <summary class="button" aria-label="Open layer manager">Layers</summary>
        <div class="layer-menu">
          <label class="layer-toggle heatmap-toggle"><input type="checkbox" data-role="confidence-heatmap" ${statefulUi.confidenceHeatmap ? "checked" : ""}> Confidence heatmap</label>
          ${drawingServices.DEFAULT_DRAWING_LAYERS.map((layer) => `
            <label class="layer-toggle">
              <input type="checkbox" data-role="drawing-layer" data-layer="${layer.key}" ${statefulUi.visibleLayers[layer.key] ? "checked" : ""}>
              <span>${escapeHtml(layer.label)}</span>
            </label>`).join("")}
        </div>
      </details>
    `;
  }

  function renderSheetNavigator(sheets, activeId) {
    const filtered = filterSheetsForNavigator(sheets);
    if (statefulUi.sheetNavigatorCollapsed) {
      return `<aside class="sheet-navigator collapsed" aria-label="Sheet navigator collapsed"><button class="vertical-tab" data-action="toggle-sheet-navigator" aria-expanded="false" aria-label="Expand sheet navigator">Sheets</button></aside>`;
    }
    return `
      <aside class="sheet-navigator" aria-label="Sheet navigator">
        <div class="navigator-header">
          <div><h2>Sheets</h2><p>${filtered.length} of ${sheets.length} visible</p></div>
          <button class="button ghost icon-button" data-action="toggle-sheet-navigator" aria-label="Collapse sheet navigator" aria-expanded="true">&lt;</button>
        </div>
        <div class="navigator-tools">
          <input class="search-input sheet-search" data-role="sheet-search" type="search" value="${escapeAttribute(statefulUi.sheetFilters.query)}" placeholder="Search sheets" aria-label="Search sheets">
          <div class="sheet-filter-row" aria-label="Sheet filters">
            ${drawingServices.SHEET_FILTERS.map((filter) => `<button class="pill ${statefulUi.sheetFilters.discipline === filter.key ? "active" : ""}" data-action="set-sheet-filter" data-filter="${filter.key}">${escapeHtml(filter.label)}</button>`).join("")}
          </div>
        </div>
        <div class="sheet-list">
          ${filtered.length ? filtered.map((sheet) => renderSheetItem(sheet, activeId)).join("") : renderInlineEmpty("No matching sheets.", "Adjust the sheet filters or search term.")}
        </div>
      </aside>
    `;
  }

  function renderSheetItem(sheet, activeId) {
    return `
      <button class="sheet-item ${activeId === sheet.id ? "active" : ""}" data-action="select-drawing" data-id="${sheet.id}" aria-label="Open sheet ${escapeAttribute(sheet.sheetNumber)}">
        <span class="sheet-thumb" aria-hidden="true">${escapeHtml(sheet.sheetNumber.slice(0, 3))}</span>
        <span class="sheet-meta">
          <strong>${escapeHtml(sheet.sheetNumber)}</strong>
          <span>${escapeHtml(sheet.sheetTitle)}</span>
          <small>${escapeHtml(sheet.revision)} - ${escapeHtml(sheet.revisionName)}</small>
          <span class="sheet-badges">${sheet.statuses.slice(0, 3).map((status) => renderStatusTag(status)).join("")}</span>
        </span>
      </button>
    `;
  }

  function renderDrawingCanvas(project, active, page, measurements, issues, rfis, revision) {
    if (!active) return renderInlineEmpty("No sheet selected.", "Select a sheet from the navigator.");
    const reviewStats = getReviewStats(measurements);
    return `
      <div class="canvas-status-bar">
        <div class="inline-actions">
          ${renderStatusTag(active.aiStatus)}
          ${renderStatusTag(active.scaleCalibration ? active.scaleCalibration.scaleConfidence : "Scale missing")}
          <span class="tag">${reviewStats.needsReview} needs review</span>
          <span class="tag ok">${reviewStats.approved} approved</span>
          <span class="tag">${reviewStats.pushed} pushed</span>
        </div>
        <div class="inline-actions">
          ${isPdf(active) ? `<button class="button ghost" data-action="viewer-prev-page" data-id="${active.id}" aria-label="Previous PDF page">Previous</button><input class="button page-input" type="number" min="1" value="${page}" data-role="viewer-page" data-id="${active.id}" aria-label="PDF page number"><button class="button ghost" data-action="viewer-next-page" data-id="${active.id}" aria-label="Next PDF page">Next</button>` : ""}
          <button class="button ghost" data-action="toggle-right-inspector" aria-label="${statefulUi.rightInspectorCollapsed ? "Show inspector" : "Hide inspector"}" aria-expanded="${statefulUi.rightInspectorCollapsed ? "false" : "true"}">${statefulUi.rightInspectorCollapsed ? "Show inspector" : "Hide inspector"}</button>
        </div>
      </div>
      <div class="drawing-stage ${statefulUi.confidenceHeatmap ? "heatmap-enabled" : ""}">
        <div class="drawing-document-layer">
          ${renderDrawingPreview(active, page)}
        </div>
        ${renderCanvasOverlays(project, active, measurements, issues, rfis, revision)}
      </div>
      ${statefulUi.drawingMode === "compare" ? renderRevisionDeltaPanel(revision) : ""}
      ${statefulUi.selectedMeasurementTool ? `<div class="measurement-tool-callout"><strong>${escapeHtml(titleCase(statefulUi.selectedMeasurementTool))} tool active.</strong><span>Canvas interaction is mocked; use Add sample to create a placeholder measurement.</span></div>` : ""}
    `;
  }

  function renderRevisionDeltaPanel(revision) {
    if (!revision) return "";
    return `
      <div class="revision-delta-panel">
        <strong>${escapeHtml(revision.revisionName)} - ${escapeHtml(revision.addendumName)}</strong>
        <div class="revision-delta-list">
          ${revision.quantityDeltas.map((delta) => `<div class="revision-delta-row"><span>${escapeHtml(delta.label)}</span><strong>${formatNumber(delta.previous)} ${escapeHtml(delta.unit)} -> ${formatNumber(delta.current)} ${escapeHtml(delta.unit)}</strong><em>${delta.delta > 0 ? "+" : ""}${formatNumber(delta.delta)} ${escapeHtml(delta.unit)}</em><small>${escapeHtml(delta.cause)}</small></div>`).join("")}
        </div>
      </div>
    `;
  }

  function renderDrawingPreview(active, page) {
    if (!active) return "";
    const url = statefulUi.previewUrls.get(active.id);
    if (statefulUi.missingFileIds.has(active.id)) {
      return `<div class="empty-state"><h3>Original file unavailable</h3><p>The document record exists, but the original local file is not stored in this workspace. Re-upload the document to preview it again.</p><button class="button" data-route="documents">Go to Documents</button></div>`;
    }
    if (!url) return renderMockPlan(active, "Loading drawing preview...");
    if (isPdf(active)) return `<div class="viewer-frame drawing-preview-frame"><iframe title="${escapeAttribute(active.name)} preview" src="${escapeAttribute(url)}#page=${page}"></iframe></div>`;
    if (isImage(active)) return `<div class="viewer-frame drawing-preview-frame"><img alt="${escapeAttribute(active.name)} preview" src="${escapeAttribute(url)}"></div>`;
    return renderMockPlan(active, "Preview not available for this file type.");
  }

  function renderMockPlan(active, message) {
    return `
      <div class="mock-plan" role="img" aria-label="${escapeAttribute(active.sheetNumber)} placeholder plan">
        <div class="mock-plan-title"><strong>${escapeHtml(active.sheetNumber)}</strong><span>${escapeHtml(active.sheetTitle)}</span></div>
        <div class="mock-grid-line h one"></div><div class="mock-grid-line h two"></div><div class="mock-grid-line h three"></div>
        <div class="mock-grid-line v one"></div><div class="mock-grid-line v two"></div><div class="mock-grid-line v three"></div>
        <div class="mock-room room-a">Exam 101</div>
        <div class="mock-room room-b">Lobby</div>
        <div class="mock-room room-c">Corridor</div>
        <div class="mock-room room-d">Office</div>
        <span class="mock-plan-note">${escapeHtml(message)}</span>
      </div>
    `;
  }

  function renderCanvasOverlays(project, active, measurements, issues, rfis, revision) {
    const visibleMeasurements = measurements.filter((item) => measurementVisible(item));
    const visibleIssues = issues.filter((item) => issueVisible(item));
    const visibleRfis = rfis.filter((item) => rfiVisible(item));
    const revisionAreas = statefulUi.drawingMode === "compare" && statefulUi.compare.highlightChanges && statefulUi.visibleLayers["revision-changes"] ? revision.changedAreas : [];
    return `
      <svg class="drawing-svg-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Drawing overlays">
        ${visibleMeasurements.map((item) => renderMeasurementOverlay(item)).join("")}
        ${revisionAreas.map((item) => renderRevisionOverlay(item)).join("")}
      </svg>
      <div class="pin-overlay">
        ${visibleMeasurements.filter((item) => item.geometry?.kind === "point").map((item) => renderPointPin("measurement", item.id, item.geometry, item.label, item.confidence, item.status)).join("")}
        ${visibleIssues.map((item) => renderPointPin("issue", item.id, item.geometry || { kind: "point", x: 24, y: 18 }, item.title, null, item.status)).join("")}
        ${visibleRfis.map((item) => renderPointPin("rfi", item.id, item.locationGeometry || { kind: "point", x: 70, y: 40 }, item.title, null, item.status)).join("")}
      </div>
    `;
  }

  function renderMeasurementOverlay(item) {
    if (!item.geometry || item.geometry.kind === "point") return "";
    return renderGeometryShape(item.geometry, {
      id: item.id,
      action: "select-measurement",
      label: item.label,
      className: `measurement-overlay ${selectedClass("measurement", item.id)} ${confidenceClass(item.confidence)} status-${escapeAttribute(item.status || "detected")}`,
      title: `${item.label} - ${formatNumber(item.quantity)} ${item.unit || ""} - ${item.confidence == null ? "No" : item.confidence + "%"} confidence - ${titleCase(item.status)}`,
    });
  }

  function renderRevisionOverlay(item) {
    return renderGeometryShape(item.geometry, {
      id: item.id,
      action: "select-revision-change",
      label: item.label,
      className: "revision-overlay",
      title: item.label,
    });
  }

  function renderGeometryShape(geometry, options) {
    const attrs = `data-action="${options.action}" data-id="${escapeAttribute(options.id)}" class="${options.className}" tabindex="0" role="button" aria-label="${escapeAttribute(options.label)}"`;
    const title = `<title>${escapeHtml(options.title || options.label)}</title>`;
    if (geometry.kind === "rect") {
      return `<rect ${attrs} x="${num(geometry.x)}" y="${num(geometry.y)}" width="${num(geometry.width)}" height="${num(geometry.height)}" rx="1">${title}</rect>`;
    }
    if (geometry.kind === "polygon") {
      return `<polygon ${attrs} points="${geometry.points.map((point) => `${num(point.x)},${num(point.y)}`).join(" ")}">${title}</polygon>`;
    }
    if (geometry.kind === "line") {
      return `<line ${attrs} x1="${num(geometry.points[0]?.x)}" y1="${num(geometry.points[0]?.y)}" x2="${num(geometry.points[1]?.x)}" y2="${num(geometry.points[1]?.y)}">${title}</line>`;
    }
    if (geometry.kind === "polyline") {
      return `<polyline ${attrs} points="${geometry.points.map((point) => `${num(point.x)},${num(point.y)}`).join(" ")}">${title}</polyline>`;
    }
    return "";
  }

  function renderPointPin(type, id, geometry, label, confidence, status) {
    const action = type === "measurement" ? "select-measurement" : type === "issue" ? "select-issue" : "select-rfi";
    const className = `overlay-pin ${type}-pin ${selectedClass(type, id)} ${confidenceClass(confidence)}`;
    return `<button class="${className}" data-action="${action}" data-id="${escapeAttribute(id)}" style="left:${num(geometry.x)}%;top:${num(geometry.y)}%" title="${escapeAttribute(`${label} - ${titleCase(status || "")}`)}" aria-label="${escapeAttribute(`${type} pin: ${label}`)}">${type === "rfi" ? "RFI" : type === "issue" ? "!" : "Q"}</button>`;
  }

  function renderRightInspector(project, active, measurements, issues, rfis, revision) {
    if (statefulUi.rightInspectorCollapsed) {
      return `<aside class="right-inspector collapsed" aria-label="Inspector collapsed"><button class="vertical-tab right" data-action="toggle-right-inspector" aria-expanded="false" aria-label="Expand inspector">Inspector</button></aside>`;
    }
    const selected = getSelectedContext(active, measurements, issues, rfis);
    return `
      <aside class="right-inspector" aria-label="Context inspector">
        <div class="inspector-header">
          <div><h2>Inspector</h2><p>${selected ? escapeHtml(selected.label) : active ? `${escapeHtml(active.sheetNumber)} summary` : "No sheet selected"}</p></div>
          <button class="button ghost icon-button" data-action="toggle-right-inspector" aria-label="Collapse inspector" aria-expanded="true">&gt;</button>
        </div>
        <div class="inspector-tabs" role="tablist" aria-label="Inspector tabs">
          ${["selection", "calculation", "issues", "history", "linked-takeoff"].map((tab) => `<button class="inspector-tab ${statefulUi.activeInspectorTab === tab ? "active" : ""}" data-action="set-inspector-tab" data-tab="${tab}" role="tab" aria-selected="${statefulUi.activeInspectorTab === tab ? "true" : "false"}">${escapeHtml(titleCase(tab))}</button>`).join("")}
        </div>
        <div class="inspector-body">
          ${renderInspectorContent(project, active, selected, measurements, issues, rfis, revision)}
        </div>
      </aside>
    `;
  }

  function renderInspectorContent(project, active, selected, measurements, issues, rfis, revision) {
    switch (statefulUi.activeInspectorTab) {
      case "calculation": return renderCalculationTab(selected, active);
      case "issues": return renderIssuesTab(selected, issues);
      case "history": return renderHistoryTab(project, selected, active);
      case "linked-takeoff": return renderLinkedTakeoffTab(project, selected);
      default: return renderSelectionTab(active, selected, measurements, issues, rfis, revision);
    }
  }

  function renderSelectionTab(active, selected, measurements, issues, rfis, revision) {
    if (!selected) {
      const stats = getReviewStats(measurements);
      return `
        <div class="summary-grid">
          ${metricMini("Sheet status", active?.aiStatus || "No sheet")}
          ${metricMini("Detected", stats.detected)}
          ${metricMini("Reviewed", stats.reviewed)}
          ${metricMini("Approved", stats.approved)}
          ${metricMini("Rejected", stats.rejected)}
          ${metricMini("Pushed", stats.pushed)}
          ${metricMini("Needs review", stats.needsReview)}
          ${metricMini("Open RFIs", rfis.filter((item) => !["Closed", "closed", "resolved"].includes(item.status)).length)}
          ${metricMini("Low confidence", measurements.filter((item) => Number(item.confidence || 0) < 70).length)}
          ${metricMini("Revision impact", revision?.quantityDeltas.length || 0)}
          ${metricMini("Scale status", active?.scaleCalibration?.scaleConfidence || "Missing")}
        </div>
        <div class="inspector-section">
          <h3>Review workflow</h3>
          <p>AI quantities stay in Drawing Viewer until an estimator approves them and pushes them to Takeoff. They do not update the final Estimate directly.</p>
        </div>
      `;
    }
    if (selected.kind === "measurement") {
      const item = selected.item;
      return `
        <div class="inspector-section">
          <h3>${escapeHtml(item.label)}</h3>
          <dl class="detail-list">
            <dt>Type</dt><dd>${escapeHtml(titleCase(item.type))} / ${escapeHtml(titleCase(item.category))}</dd>
            <dt>Quantity</dt><dd>${formatNumber(item.quantity)} ${escapeHtml(item.unit || "")}</dd>
            <dt>Status</dt><dd>${renderStatusTag(item.status)}</dd>
            <dt>Confidence</dt><dd>${item.confidence == null ? "Unavailable" : `${item.confidence}%`}</dd>
            <dt>Source</dt><dd>${escapeHtml(item.createdBy === "ai" ? "AI draft" : "Manual")}</dd>
          </dl>
          <div class="inline-actions">
            <button class="button primary" data-action="approve-selected-measurement">Accept</button>
            <button class="button" data-action="reject-selected-measurement">Reject</button>
            <button class="button" data-action="edit-selected-measurement">Edit</button>
            <button class="button ghost" data-action="duplicate-selected-measurement">Duplicate</button>
            <button class="button ghost" data-action="exclude-selected-measurement">Exclude</button>
          </div>
        </div>
      `;
    }
    if (selected.kind === "rfi") {
      const item = selected.item;
      return `<div class="inspector-section"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description || item.question || "No description.")}</p><dl class="detail-list"><dt>Status</dt><dd>${renderStatusTag(item.status)}</dd><dt>Priority</dt><dd>${escapeHtml(item.priority || "medium")}</dd></dl></div>`;
    }
    return `<div class="inspector-section"><h3>${escapeHtml(selected.item.title)}</h3><p>${escapeHtml(selected.item.description || "No issue description.")}</p><button class="button" data-action="create-rfi-from-selected-issue">Create RFI from issue</button></div>`;
  }

  function renderCalculationTab(selected, active) {
    if (!selected || selected.kind !== "measurement") {
      return `<div class="inspector-section"><h3>Scale and calculation basis</h3><p>${active?.scaleCalibration ? `Scale ${escapeHtml(active.scaleCalibration.scaleValue)} from ${escapeHtml(active.scaleCalibration.scaleSource)}.` : "Scale is missing. Calibrate the sheet before relying on measurement quantities."}</p><button class="button" data-action="open-scale-modal">Open scale calibration</button></div>`;
    }
    const item = selected.item;
    return `
      <div class="inspector-section">
        <h3>Calculation</h3>
        <p>${escapeHtml(item.calculationSummary || "No calculation summary available.")}</p>
        <dl class="detail-list">
          <dt>Inputs</dt><dd>${escapeHtml((item.sourceRefs || []).map((ref) => ref.type).join(", ") || "Sheet geometry")}</dd>
          <dt>Deductions</dt><dd>${escapeHtml(item.category === "paint" ? "Openings deducted from AI assumptions." : "None recorded.")}</dd>
          <dt>Waste factor</dt><dd>${escapeHtml(item.category === "paint" ? "5%" : "Not applied")}</dd>
          <dt>Height assumptions</dt><dd>${escapeHtml((item.assumptions || []).join(" ") || "No assumptions recorded.")}</dd>
        </dl>
      </div>
    `;
  }

  function renderIssuesTab(selected, issues) {
    const warnings = selected?.kind === "measurement" ? selected.item.warnings || [] : [];
    return `
      <div class="inspector-section">
        <h3>Issues</h3>
        ${warnings.length ? warnings.map((warning) => `<p class="issue-line">${escapeHtml(warning)}</p>`).join("") : ""}
        ${issues.length ? `<div class="compact-list">${issues.map((issue) => `<button class="compact-row" data-action="select-issue" data-id="${issue.id}"><strong>${escapeHtml(issue.title)}</strong><span>${escapeHtml(issue.status)}</span></button>`).join("")}</div>` : renderInlineEmpty("No issues found.", "Scale, low-confidence, and conflict warnings appear here.")}
      </div>
    `;
  }

  function renderHistoryTab(project, selected, active) {
    const history = [
      active ? { label: `Revision imported for ${active.sheetNumber}`, date: active.updatedAt || active.uploadedAt } : null,
      selected?.kind === "measurement" ? { label: `${titleCase(selected.item.createdBy)} measurement created`, date: selected.item.createdAt } : null,
      selected?.kind === "measurement" && selected.item.updatedAt ? { label: `Measurement status ${titleCase(selected.item.status)}`, date: selected.item.updatedAt } : null,
      ...filterByProject(state.activities, project.id).slice(0, 4).map((item) => ({ label: item.message, date: item.createdAt })),
    ].filter(Boolean);
    return `<div class="activity-list compact-history">${history.map((item) => `<div class="activity-row"><strong>${escapeHtml(item.label)}</strong><span>${formatDateTime(item.date)}</span></div>`).join("")}</div>`;
  }

  function renderLinkedTakeoffTab(project, selected) {
    if (!selected || selected.kind !== "measurement") {
      return `<div class="inspector-section"><h3>Linked Takeoff</h3><p>Select a measurement to review its Takeoff link.</p></div>`;
    }
    const item = selected.item;
    const linked = item.linkedTakeoffItemId ? findById(state.takeoffMeasurements, item.linkedTakeoffItemId) : state.takeoffMeasurements.find((row) => row.sourceMeasurementId === item.id);
    return `
      <div class="inspector-section">
        <h3>Linked Takeoff</h3>
        ${linked ? `<dl class="detail-list"><dt>Item</dt><dd>${escapeHtml(linked.name)}</dd><dt>Quantity</dt><dd>${formatNumber(linked.quantity)} ${escapeHtml(linked.unit)}</dd><dt>Estimate status</dt><dd>Available for estimate generation</dd></dl>` : `<p>No takeoff item is linked yet.</p>`}
        <button class="button primary" data-action="push-selected-to-takeoff" ${item.status === "approved" ? "" : "disabled"}>Push to Takeoff</button>
      </div>
    `;
  }

  function metricMini(label, value) {
    return `<div class="metric-mini"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
  }

  function renderTakeoff(project) {
    const rows = enrichTakeoffRows(project.id);
    const filtered = applyTakeoffFilters(rows, statefulUi.takeoffFilters);
    const summary = calculateTakeoffSummary(filtered);
    const rooms = filterByProject(state.rooms, project.id);
    const floors = filterByProject(state.floors, project.id);
    const buildings = filterByProject(state.buildings, project.id);
    const scopes = filterByProject(state.scopes, project.id);
    const latestAiRun = latestAiTakeoffRun(project.id);
    return `
      <div class="page">
        ${renderPageHeader("Takeoff", "Create, edit, filter, and review persisted takeoff measurements.", `<button class="button primary" data-action="open-measurement-modal">New takeoff row</button>`)}
        <div class="card-grid">
          ${metricCard("Rows", summary.rowCount, "Filtered takeoff rows")}
          ${metricCard("Wall SF", formatNumber(summary.wallSf), "Calculated from rows")}
          ${metricCard("Paint SF", formatNumber(summary.paintSf), "Calculated from rows")}
          ${metricCard("Average confidence", summary.averageConfidence == null ? "—" : `${summary.averageConfidence}%`, `${summary.lowConfidenceCount} low-confidence item${summary.lowConfidenceCount === 1 ? "" : "s"}`)}
        </div>
        ${renderAiQuantitiesPanel(project, latestAiRun)}
        <section class="panel">
          <div class="panel-header"><div><h2>Filters</h2><p>Room, floor, building, scope, and trade filters all apply to real records.</p></div></div>
          <div class="panel-body stack">
            <div class="filter-row">
              ${renderSelect("takeoff-room-filter", "Room", rooms, statefulUi.takeoffFilters.roomId)}
              ${renderSelect("takeoff-floor-filter", "Floor", floors, statefulUi.takeoffFilters.floorId)}
              ${renderSelect("takeoff-building-filter", "Building", buildings, statefulUi.takeoffFilters.buildingId)}
              ${renderSelect("takeoff-scope-filter", "Scope", scopes, statefulUi.takeoffFilters.scopeId)}
            </div>
            <div class="pill-row">
              ${["all", "drywall", "paint", "ceilings", "carpentry"].map((item) => `<button class="pill ${statefulUi.takeoffFilters.scopeCategory === item ? "active" : ""}" data-action="set-scope-category" data-category="${item}">${titleCase(item === "all" ? "all scopes" : item)}</button>`).join("")}
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><h2>Takeoff ledger</h2><p>${filtered.length ? `${filtered.length} visible row${filtered.length === 1 ? "" : "s"}` : "No matching rows"}</p></div></div>
          ${filtered.length ? `<div class="table-wrap"><table><thead><tr><th>Location</th><th>Floor</th><th>Building</th><th>Scope</th><th>Quantity</th><th>Wall SF</th><th>Ceiling SF</th><th>Paint SF</th><th>Confidence</th><th>Actions</th></tr></thead><tbody>${filtered.map((row) => `<tr><td>${escapeHtml(row.roomName || row.name)}</td><td>${escapeHtml(row.floorName || "—")}</td><td>${escapeHtml(row.buildingName || "—")}</td><td>${escapeHtml(row.scopeName || titleCase(row.scopeCategory || ""))}</td><td>${formatNumber(row.quantity)} ${escapeHtml(row.unit || "")}</td><td>${formatNumber(row.wallSf)}</td><td>${formatNumber(row.ceilingSf)}</td><td>${formatNumber(row.paintSf)}</td><td>${renderConfidence(row.confidence)}</td><td><div class="inline-actions"><button class="button ghost" data-action="edit-measurement" data-id="${row.id}" aria-label="Edit ${escapeAttribute(row.name)}">Details</button><button class="button ghost" data-action="delete-measurement" data-id="${row.id}" aria-label="Delete ${escapeAttribute(row.name)}">Delete</button></div></td></tr>`).join("")}</tbody></table></div>` : `<div class="panel-body">${renderInlineEmpty("No takeoff rows yet.", "Add the first measurement or adjust the filters to see saved rows.", `<button class="button primary" data-action="open-measurement-modal">New takeoff row</button>`)}</div>`}
        </section>
      </div>
    `;
  }

  function renderAiQuantitiesPanel(project, run) {
    const totals = run ? (run.totals || calculateAiTakeoffTotals(run)) : null;
    const rooms = run ? aiTakeoffRooms(run) : [];
    const warnings = run ? [...(run.warnings || []), ...(run.pages || []).flatMap((page) => page.warnings || [])] : [];
    return `
      <section class="panel quantities-panel">
        <div class="panel-header">
          <div><h2>AI painting quantities</h2><p>${run ? `${titleCase(run.status || "unknown")} - ${formatDateTime(run.updatedAt || run.createdAt)}` : "No AI takeoff run yet"}</p></div>
          <div class="inline-actions">
            <button class="button" data-action="run-ai-takeoff">Run AI Takeoff</button>
            <button class="button" data-action="export-ai-takeoff-csv" ${run ? "" : "disabled"}>Export AI CSV</button>
          </div>
        </div>
        <div class="panel-body stack">
          ${run ? `<div class="summary-grid">
            ${metricMini("Wall SF", formatNumber(totals.wallSf))}
            ${metricMini("Ceiling SF", formatNumber(totals.ceilingSf))}
            ${metricMini("Doors", formatNumber(totals.doorCount))}
            ${metricMini("Windows", formatNumber(totals.windowCount))}
            ${metricMini("Trim LF", formatNumber(totals.trimLf))}
            ${metricMini("Confidence", run.confidenceScore ? `${formatNumber(run.confidenceScore)}%` : "Unavailable")}
          </div>
          ${warnings.length ? `<div class="notice warn">${warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join("")}</div>` : ""}
          ${rooms.length ? `<div class="table-wrap"><table><thead><tr><th>Room</th><th>Page</th><th>Wall SF</th><th>Ceiling SF</th><th>Doors</th><th>Windows</th><th>Trim LF</th><th>Confidence</th><th>Assumptions</th></tr></thead><tbody>${rooms.map((room) => `<tr><td>${escapeHtml(room.name)}</td><td>${escapeHtml(entityName(state.drawings, room.pageId) || room.pageId || "â€”")}</td><td>${formatNumber(room.wallSf)}</td><td>${formatNumber(room.ceilingSf)}</td><td>${formatNumber(room.doorCount)}</td><td>${formatNumber(room.windowCount)}</td><td>${formatNumber(room.trimLf)}</td><td>${renderConfidence(room.confidence)}</td><td>${escapeHtml((room.assumptions || []).join("; ") || "None recorded")}</td></tr>`).join("")}</tbody></table></div>` : renderInlineEmpty("No AI rooms available.", run.status === "not_configured" ? "Configure an AI provider to extract room-by-room quantities from plan images. Manual takeoff remains available." : "The latest AI run returned no rooms for review.")}` : renderInlineEmpty("No AI takeoff run yet.", "Run AI Takeoff from the drawing viewer or this panel to create a painting-specific review result.", `<button class="button primary" data-action="run-ai-takeoff">Run AI Takeoff</button>`)}
        </div>
      </section>
    `;
  }

  function renderScopeDetection(project) {
    const rows = filterByProject(state.scopeDetections, project.id);
    return `
      <div class="page">
        ${renderPageHeader("Scope detection", "Manual review workflow for detected scope items when no automated service is connected.", `<button class="button primary" data-action="open-scope-modal">New scope item</button>`)}
        <div class="notice">Automatic AI scope detection is not integrated in this build. This page uses a real manual review workflow instead of simulating AI activity.</div>
        <section class="panel">
          <div class="panel-header"><div><h2>Review queue</h2><p>${rows.length ? `${rows.length} item${rows.length === 1 ? "" : "s"}` : "No scope items yet"}</p></div></div>
          <div class="panel-body">
            ${rows.length ? `<div class="list">${rows.map((item) => `<div class="list-item"><div><div class="inline-actions"><h3>${escapeHtml(item.title)}</h3>${renderStatusTag(item.status)}</div><p>${escapeHtml(item.description || "No description")}</p><p>${titleCase(item.category)} · ${item.confidence}% confidence${item.quantity ? ` · ${formatNumber(item.quantity)} ${escapeHtml(item.unit || "")}` : ""}</p></div><div class="inline-actions"><button class="button ghost" data-action="edit-scope" data-id="${item.id}">Edit</button>${item.status !== "approved" ? `<button class="button ghost" data-action="approve-scope" data-id="${item.id}">Approve</button>` : ""}${item.status !== "rejected" ? `<button class="button ghost" data-action="reject-scope" data-id="${item.id}">Reject</button>` : ""}${item.status === "approved" ? `<button class="button" data-action="promote-scope" data-id="${item.id}">Promote</button>` : ""}<button class="button ghost" data-action="delete-scope" data-id="${item.id}">Delete</button></div></div>`).join("")}</div>` : renderInlineEmpty("No detected scope items.", "Create a manual review item, assign confidence, then approve and promote it into takeoff and estimate.", `<button class="button primary" data-action="open-scope-modal">New scope item</button>`)}</div>
        </section>
      </div>
    `;
  }

  function renderQuestionsRfis(project) {
    const rfis = filterByProject(state.rfis, project.id);
    return `
      <div class="page">
        ${renderPageHeader("Questions / RFIs", "Track project questions and resolution state against real linked records.", `<button class="button primary" data-action="open-rfi-modal">New RFI</button>`)}
        <section class="panel">
          <div class="panel-header"><div><h2>RFI register</h2><p>${rfis.length ? `${rfis.filter((item) => item.status !== "resolved").length} unresolved of ${rfis.length}` : "No RFIs yet"}</p></div></div>
          <div class="panel-body">
            ${rfis.length ? `<div class="list">${rfis.map((item) => `<div class="list-item"><div><div class="inline-actions"><h3>${escapeHtml(item.title)}</h3>${renderStatusTag(item.status)}</div><p>${escapeHtml(item.question)}</p><p>${linkedRecordSummary(project.id, item)}</p></div><div class="inline-actions"><button class="button ghost" data-action="edit-rfi" data-id="${item.id}">Edit</button>${item.status !== "resolved" ? `<button class="button ghost" data-action="resolve-rfi" data-id="${item.id}">Resolve</button>` : `<button class="button ghost" data-action="reopen-rfi" data-id="${item.id}">Reopen</button>`}<button class="button ghost" data-action="delete-rfi" data-id="${item.id}">Delete</button></div></div>`).join("")}</div>` : renderInlineEmpty("No RFIs yet.", "Create a question and link it to a drawing, room, scope, or estimate item.", `<button class="button primary" data-action="open-rfi-modal">New RFI</button>`)}</div>
        </section>
      </div>
    `;
  }

  function renderEstimate(project) {
    const rows = filterByProject(state.estimateLineItems, project.id);
    const totals = rows.reduce((acc, row) => {
      const calc = calculateEstimateLine(row);
      acc.direct += calc.directCost;
      acc.markup += calc.markupAmount;
      acc.tax += calc.taxAmount;
      acc.total += calc.total;
      return acc;
    }, { direct: 0, markup: 0, tax: 0, total: 0 });
    return `
      <div class="page">
        ${renderPageHeader("Estimate", "Generate estimate lines from takeoff or add manual items with live cost calculations.", `<div class="inline-actions"><button class="button" data-action="generate-estimate">Generate from takeoff</button><button class="button primary" data-action="open-estimate-modal">Manual line item</button></div>`)}
        <div class="card-grid">
          ${metricCard("Direct cost", formatCurrency(totals.direct), "Quantity × unit, labor, and material cost")}
          ${metricCard("Markup", formatCurrency(totals.markup), `${state.settings.defaultMarkupPercent}% default markup`)}
          ${metricCard("Tax", formatCurrency(totals.tax), `${state.settings.defaultTaxPercent}% default tax`)}
          ${metricCard("Estimate total", formatCurrency(totals.total), `${rows.length} line item${rows.length === 1 ? "" : "s"}`)}
        </div>
        <section class="panel">
          <div class="panel-header"><div><h2>Estimate lines</h2><p>${rows.length ? "Totals recalculate from stored line items." : "No estimate lines yet"}</p></div></div>
          ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit cost</th><th>Labor</th><th>Material</th><th>Markup</th><th>Tax</th><th>Total</th><th>Actions</th></tr></thead><tbody>${rows.map((row) => { const calc = calculateEstimateLine(row); return `<tr><td>${escapeHtml(row.description)}</td><td>${formatNumber(row.quantity)}</td><td>${escapeHtml(row.unit)}</td><td>${formatCurrency(row.unitCost)}</td><td>${formatCurrency(row.laborCost)}</td><td>${formatCurrency(row.materialCost)}</td><td>${formatNumber(row.markupPercent)}%</td><td>${formatNumber(row.taxPercent)}%</td><td>${formatCurrency(calc.total)}</td><td><div class="inline-actions"><button class="button ghost" data-action="edit-estimate" data-id="${row.id}">Edit</button><button class="button ghost" data-action="delete-estimate" data-id="${row.id}">Delete</button></div></td></tr>`; }).join("")}</tbody></table></div>` : `<div class="panel-body">${renderInlineEmpty("No estimate lines yet.", "Generate rows from approved takeoff or add a manual line item.", `<div class="inline-actions"><button class="button" data-action="generate-estimate">Generate from takeoff</button><button class="button primary" data-action="open-estimate-modal">Manual line item</button></div>`)}</div>`}
        </section>
      </div>
    `;
  }

  function renderRiskConfidence(project) {
    const rows = filterByProject(state.riskItems, project.id);
    const open = rows.filter((item) => item.status !== "resolved");
    const avg = averageConfidence(rows);
    return `
      <div class="page">
        ${renderPageHeader("Risk & confidence", "Review low-confidence records from takeoff, scope, and estimate data.")}
        <div class="card-grid">
          ${metricCard("Open issues", open.length, "Low-confidence records")}
          ${metricCard("Resolved issues", rows.length - open.length, "Reviewed by estimator")}
          ${metricCard("Average confidence", avg == null ? "—" : `${avg}%`, "Across tracked confidence items")}
          ${metricCard("Threshold", `${state.settings.lowConfidenceThreshold}%`, "Configured in settings")}
        </div>
        <section class="panel">
          <div class="panel-header"><div><h2>Confidence review queue</h2><p>${rows.length ? `${rows.length} tracked issue${rows.length === 1 ? "" : "s"}` : "No low-confidence items"}</p></div></div>
          <div class="panel-body">
            ${rows.length ? `<div class="list">${rows.map((item) => `<div class="list-item"><div><div class="inline-actions"><h3>${escapeHtml(item.label)}</h3>${renderStatusTag(item.status)}</div><p>${titleCase(item.referenceType)} · ${effectiveConfidence(item)}% confidence${item.overrideConfidence != null ? " after override" : ""}</p>${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}</div><div class="inline-actions"><button class="button ghost" data-action="review-risk" data-id="${item.id}">Review</button>${item.status !== "resolved" ? `<button class="button ghost" data-action="resolve-risk" data-id="${item.id}">Resolve</button>` : `<button class="button ghost" data-action="reopen-risk" data-id="${item.id}">Reopen</button>`}</div></div>`).join("")}</div>` : renderInlineEmpty("No low-confidence items.", "Confidence issues appear here when real takeoff, scope, or estimate records fall below the threshold.")}</div>
        </section>
      </div>
    `;
  }

  function renderOutputCenter(project) {
    const exports = filterByProject(state.exports, project.id);
    return `
      <div class="page">
        ${renderPageHeader("Output center", "Export persisted project data as CSV or JSON.", `<div class="inline-actions"><button class="button" data-action="export-json">Export JSON</button><button class="button primary" data-action="export-csv">Export CSV</button></div>`)}
        <section class="panel">
          <div class="panel-header"><div><h2>Export history</h2><p>${exports.length ? `${exports.length} completed export${exports.length === 1 ? "" : "s"}` : "No exports yet"}</p></div></div>
          <div class="panel-body">
            ${exports.length ? `<div class="list">${exports.map((item) => `<div class="list-item"><div><h3>${escapeHtml(item.fileName)}</h3><p>${escapeHtml(item.format.toUpperCase())} · ${formatDateTime(item.createdAt)}</p></div><span class="tag ok">Complete</span></div>`).join("")}</div>` : renderInlineEmpty("No exports yet.", "Use CSV or JSON export to download the actual project data stored in this workspace.")}
          </div>
        </section>
      </div>
    `;
  }

  function renderCompanyMemory() {
    const scopes = state.companyMemoryEntries.filter((item) => item.type === "standard_scope");
    const laborRates = state.companyMemoryEntries.filter((item) => item.type === "labor_rate");
    const markups = state.companyMemoryEntries.filter((item) => item.type === "markup");
    const notes = state.companyMemoryEntries.filter((item) => item.type === "note_template");
    return `
      <div class="page">
        ${renderPageHeader("Company memory", "Reusable standards that influence future estimates where applicable.", `<button class="button primary" data-action="open-memory-modal">Add memory entry</button>`)}
        <div class="card-grid">
          ${metricCard("Standard scopes", scopes.length, "Reusable scope labels")}
          ${metricCard("Material defaults", state.materials.length, "Used during generated estimates")}
          ${metricCard("Labor rates", laborRates.length, "Reusable labor defaults")}
          ${metricCard("Notes / templates", notes.length, "Reusable text blocks")}
        </div>
        <section class="panel"><div class="panel-header"><div><h2>Stored defaults</h2><p>Material defaults and memory entries are persisted locally.</p></div></div><div class="panel-body stack">${renderMemorySection("Material defaults", state.materials, "material")}${renderMemorySection("Standard scopes", scopes, "standard_scope")}${renderMemorySection("Labor rates", laborRates, "labor_rate")}${renderMemorySection("Markups", markups, "markup")}${renderMemorySection("Notes / templates", notes, "note_template")}</div></section>
      </div>
    `;
  }

  function renderMemorySection(title, rows, type) {
    return `<div class="stack"><h3>${title}</h3>${rows.length ? `<div class="list">${rows.map((item) => `<div class="list-item"><div><h3>${escapeHtml(item.name || item.label)}</h3><p>${escapeHtml(memorySummary(item, type))}</p></div><div class="inline-actions"><button class="button ghost" data-action="edit-memory" data-type="${type}" data-id="${item.id}">Edit</button><button class="button ghost" data-action="delete-memory" data-type="${type}" data-id="${item.id}">Delete</button></div></div>`).join("")}</div>` : renderInlineEmpty(`No ${title.toLowerCase()} yet.`, "Add a real reusable default when you need one.")}</div>`;
  }

  function renderPastProjects() {
    const projects = [...state.projects].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    return `
      <div class="page">
        ${renderPageHeader("Past projects", "Open, duplicate, archive, or delete real saved projects.", `<div class="inline-actions"><button class="button" data-action="trigger-project-import">Import project JSON</button><button class="button primary" data-action="open-project-modal">New project</button><input id="project-import" type="file" accept="application/json,.json" hidden></div>`)}
        <section class="panel"><div class="panel-header"><div><h2>Projects</h2><p>${projects.length ? `${projects.length} saved project${projects.length === 1 ? "" : "s"}` : "No saved projects"}</p></div></div><div class="panel-body">${projects.length ? `<div class="list">${projects.map((item) => `<div class="list-item"><div><div class="inline-actions"><h3>${escapeHtml(item.name)}</h3>${item.archived ? `<span class="tag">Archived</span>` : ""}</div><p>${escapeHtml(item.client || "No client")} · Updated ${formatDateTime(item.updatedAt)}</p></div><div class="inline-actions"><button class="button ghost" data-action="open-project" data-id="${item.id}">Open</button><button class="button ghost" data-action="duplicate-project" data-id="${item.id}">Duplicate</button><button class="button ghost" data-action="toggle-project-archive" data-id="${item.id}">${item.archived ? "Restore" : "Archive"}</button><button class="button ghost" data-action="delete-project" data-id="${item.id}">Delete</button></div></div>`).join("")}</div>` : renderInlineEmpty("No saved projects yet.", "Create a project to start building project history.", `<button class="button primary" data-action="open-project-modal">New project</button>`)}</div></section>
      </div>
    `;
  }

  function renderSettings() {
    return `
      <div class="page">
        ${renderPageHeader("Settings", "Persist workspace profile, preferences, and data controls.")}
        <form class="panel" data-form="settings">
          <div class="panel-header"><div><h2>Workspace & preferences</h2><p>These values are saved locally and used across the app.</p></div></div>
          <div class="panel-body form-grid">
            ${field("Company name", "companyName", state.settings.companyName)}
            ${field("Company email", "companyEmail", state.settings.companyEmail, "email")}
            ${field("Company phone", "companyPhone", state.settings.companyPhone)}
            ${field("Company address", "companyAddress", state.settings.companyAddress)}
            ${selectField("Units", "units", state.settings.units, [{ value: "imperial", label: "Imperial" }, { value: "metric", label: "Metric" }])}
            ${selectField("Currency", "currency", state.settings.currency, [{ value: "USD", label: "USD" }, { value: "CAD", label: "CAD" }, { value: "EUR", label: "EUR" }])}
            ${field("Default markup %", "defaultMarkupPercent", state.settings.defaultMarkupPercent, "number")}
            ${field("Default tax %", "defaultTaxPercent", state.settings.defaultTaxPercent, "number")}
            ${field("Low-confidence threshold %", "lowConfidenceThreshold", state.settings.lowConfidenceThreshold, "number")}
            ${selectField("AI takeoff", "aiTakeoffEnabled", state.settings.aiTakeoffEnabled ? "true" : "false", [{ value: "true", label: "Enabled" }, { value: "false", label: "Disabled" }])}
            ${field("Your name", "userName", state.settings.userName)}
            ${field("Your email", "userEmail", state.settings.userEmail, "email")}
          </div>
          <div class="modal-footer"><button class="button primary" type="submit">Save settings</button></div>
        </form>
        <section class="panel"><div class="panel-header"><div><h2>Data controls</h2><p>Export or clear the local workspace database.</p></div></div><div class="panel-body inline-actions"><button class="button" data-action="export-workspace">Export all data</button><button class="button danger" data-action="clear-workspace">Clear local data</button></div></section>
      </div>
    `;
  }

  function renderPageHeader(title, description, actions = "") {
    return `<div class="page-header"><div class="page-title"><h1>${title}</h1><p>${description}</p></div>${actions ? `<div class="inline-actions">${actions}</div>` : ""}</div>`;
  }

  function metricCard(label, value, subtext) {
    return `<article class="card"><div class="metric-label">${label}</div><div class="metric-value">${escapeHtml(String(value))}</div><div class="metric-subtext">${escapeHtml(subtext)}</div></article>`;
  }

  function renderInlineEmpty(title, body, action = "") {
    return `<div class="empty-state"><h3>${title}</h3><p>${body}</p>${action || ""}</div>`;
  }

  function renderSelect(id, label, rows, selectedId) {
    return `<label class="field" style="min-width:180px"><span>${label}</span><select data-role="${id}"><option value="">All ${label.toLowerCase()}s</option>${rows.map((row) => `<option value="${row.id}" ${selectedId === row.id ? "selected" : ""}>${escapeHtml(row.name)}</option>`).join("")}</select></label>`;
  }

  function renderConfidence(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "—";
    const cls = numeric < 70 ? "risk" : numeric < 85 ? "warn" : "";
    return `<div class="confidence ${cls}"><span class="confidence-bar"><span style="width:${Math.max(0, Math.min(100, numeric))}%"></span></span><span>${numeric}%</span></div>`;
  }

  function renderStatusTag(status) {
    const normalized = cleanText(status) || "pending";
    const cls = normalized === "approved" || normalized === "resolved" ? "ok" : normalized === "rejected" ? "risk" : normalized === "open" ? "warn" : "";
    return `<span class="tag ${cls}">${titleCase(normalized)}</span>`;
  }

  function renderModal(project) {
    if (!statefulUi.modal) return "";
    const { type, payload = {} } = statefulUi.modal;
    switch (type) {
      case "project": return modalShell("New project", renderProjectForm(), "Create project", "project");
      case "documentRename": return modalShell("Rename document", `<div class="field"><label for="document-name">Document name</label><input id="document-name" name="name" value="${escapeAttribute(payload.name)}" required></div>`, "Save", "document-rename");
      case "measurement": return modalShell(payload.id ? "Edit takeoff row" : "New takeoff row", renderMeasurementForm(project, payload), "Save row", "measurement");
      case "scope": return modalShell(payload.id ? "Edit scope item" : "New scope item", renderScopeForm(project, payload), "Save item", "scope");
      case "rfi": return modalShell(payload.id ? "Edit RFI" : "New RFI", renderRfiForm(project, payload), "Save RFI", "rfi");
      case "estimate": return modalShell(payload.id ? "Edit estimate line" : "Manual estimate line", renderEstimateForm(payload), "Save line", "estimate");
      case "risk": return modalShell("Review confidence issue", renderRiskForm(payload), "Save review", "risk");
      case "memory": return modalShell(payload.id ? "Edit memory entry" : "Add memory entry", renderMemoryForm(payload), "Save entry", "memory");
      case "aiMeasurement": return modalShell("Run AI measurement", renderAiMeasurementForm(project), statefulUi.aiProcessingState?.status === "processing" ? "Processing..." : "Run AI", "ai-measurement", statefulUi.aiProcessingState?.status === "processing");
      case "scaleCalibration": return modalShell("Scale & Calibration", renderScaleCalibrationForm(project, payload), "Save scale", "scale-calibration");
      case "drawingMeasurementEdit": return modalShell("Edit drawing measurement", renderDrawingMeasurementEditForm(payload), "Save measurement", "drawing-measurement-edit");
      case "export": return renderExportModal(project);
      default: return "";
    }
  }

  function modalShell(title, body, submitLabel, formName, submitDisabled = false) {
    return `<div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="${escapeAttribute(title)}"><form class="modal" data-form="${formName}"><div class="modal-header"><h2>${title}</h2><button class="button ghost" type="button" data-action="close-modal" aria-label="Close dialog">✕</button></div><div class="modal-body">${body}</div><div class="modal-footer"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit" ${submitDisabled ? "disabled" : ""}>${submitLabel}</button></div></form></div>`;
  }

  function renderProjectForm() {
    return `<div class="form-grid">${field("Project name", "name", "", "text", true)}${field("Client", "client", "")}${field("Address", "address", "")}${field("Project type", "projectType", "")}${selectField("Units", "units", state.settings.units, [{ value: "imperial", label: "Imperial" }, { value: "metric", label: "Metric" }])}${field("Description", "description", "", "text", false, true)}</div>`;
  }

  function renderAiMeasurementForm(project) {
    const sheets = drawingServices.drawingService.getSheets(state, project.id);
    const activeId = state.settings.activeDrawingIdByProject[project.id] || sheets[0]?.id || "";
    const revisedSheets = sheets.filter((sheet) => sheet.statuses.includes("Changed by addendum")).length;
    const processing = statefulUi.aiProcessingState?.status === "processing";
    return `
      <div class="stack">
        <div class="notice">Mock AI processing creates estimator-review measurements only. Results must be approved and pushed to Takeoff before they can be used for estimate generation.</div>
        ${processing ? `<div class="ai-progress"><span style="width:${statefulUi.aiProcessingState.progress || 35}%"></span></div><p>Processing ${statefulUi.aiProcessingState.sheetStatuses?.length || 0} sheet(s)...</p>` : ""}
        <div class="form-grid">
          ${selectField("Scope", "scope", "current", [
            { value: "current", label: "Current sheet" },
            { value: "selected", label: "Selected sheets" },
            { value: "all", label: "All sheets" },
            { value: "revised", label: `Revised sheets only (${revisedSheets})` },
          ])}
          ${selectField("Measurement focus", "focus", "all", [
            { value: "all", label: "All detectable scope" },
            { value: "walls", label: "Walls" },
            { value: "ceilings", label: "Ceilings" },
            { value: "paint", label: "Paint" },
            { value: "flooring", label: "Flooring" },
            { value: "framing", label: "Framing" },
            { value: "doors", label: "Doors / openings" },
            { value: "counts", label: "Counts / symbols" },
          ])}
          <input type="hidden" name="currentSheetId" value="${escapeAttribute(activeId)}">
          ${field("Selected sheet ids", "selectedSheetIds", activeId, "text", false, true)}
        </div>
      </div>
    `;
  }

  function renderScaleCalibrationForm(project, payload) {
    const sheets = drawingServices.drawingService.getSheets(state, project.id);
    const activeId = payload.sheetId || state.settings.activeDrawingIdByProject[project.id] || sheets[0]?.id || "";
    const existing = state.drawingScaleCalibrations.find((item) => item.sheetId === activeId) || drawingServices.scaleService.defaultScaleCalibration(project.id, activeId);
    return `
      <div class="stack">
        <div class="notice">Two-point calibration is a UI placeholder. Real canvas point capture can write into this same scale record later.</div>
        <div class="form-grid">
          ${selectField("Sheet", "sheetId", activeId, sheets.map((sheet) => ({ value: sheet.id, label: `${sheet.sheetNumber} - ${sheet.sheetTitle}` })))}
          <label class="field"><span>Auto-detected scale</span><input value="${escapeAttribute(existing.scaleValue || drawingServices.SCALE_OPTIONS[1])}" disabled></label>
          ${selectField("Manual scale", "scaleValue", existing.scaleValue || '1/8" = 1\'-0"', drawingServices.SCALE_OPTIONS.map((value) => ({ value, label: value })))}
          ${selectField("Scale source", "scaleSource", existing.scaleSource || "manual", [
            { value: "auto", label: "Auto" },
            { value: "manual", label: "Manual" },
            { value: "two_point", label: "Two point" },
            { value: "missing", label: "Missing" },
          ])}
          ${selectField("Scale confidence", "scaleConfidence", existing.scaleConfidence || "Needs confirmation", [
            { value: "Auto-detected", label: "Auto-detected" },
            { value: "Manually set", label: "Manually set" },
            { value: "Needs confirmation", label: "Needs confirmation" },
            { value: "Missing", label: "Missing" },
          ])}
          ${field("Two-point real distance", "twoPointDistance", existing.twoPointDistance || "", "text")}
          ${field("Custom pixels per foot", "pixelsPerFoot", existing.pixelsPerFoot || "", "number")}
          <label class="field"><span>Lock approved scale</span><select name="scaleLocked"><option value="false" ${existing.scaleLocked ? "" : "selected"}>Unlocked</option><option value="true" ${existing.scaleLocked ? "selected" : ""}>Locked</option></select></label>
          ${field("Calibrated by", "calibratedBy", existing.calibratedBy || state.settings.userName || "Estimator")}
          <label class="field full"><span>Multi-scale zones</span><textarea name="multiScaleZones" placeholder="Placeholder for future enlarged plan/detail zones">${escapeHtml((existing.multiScaleZones || []).join("\n"))}</textarea></label>
        </div>
      </div>
    `;
  }

  function renderDrawingMeasurementEditForm(item) {
    const current = item || {};
    return `<div class="form-grid">
      ${field("Label", "label", current.label || "", "text", true)}
      ${selectField("Category", "category", current.category || "custom", [
        { value: "walls", label: "Walls" },
        { value: "paint", label: "Paint" },
        { value: "ceilings", label: "Ceilings" },
        { value: "flooring", label: "Flooring" },
        { value: "framing", label: "Framing" },
        { value: "doors", label: "Doors" },
        { value: "custom", label: "Custom" },
      ])}
      ${field("Quantity", "quantity", current.quantity || "", "number", true)}
      ${field("Unit", "unit", current.unit || "SF", "text", true)}
      ${selectField("Status", "status", current.status === "pushed_to_takeoff" ? "pushed_to_takeoff" : "edited", [
        { value: "detected", label: "Detected" },
        { value: "reviewed", label: "Reviewed" },
        { value: "approved", label: "Approved" },
        { value: "rejected", label: "Rejected" },
        { value: "edited", label: "Edited" },
        { value: "pushed_to_takeoff", label: "Pushed to Takeoff" },
      ])}
      ${field("Notes", "notes", current.notes || "", "text", false, true)}
    </div>`;
  }

  function renderMeasurementForm(project, item) {
    const drawings = filterByProject(state.drawings, project.id);
    const current = item || {};
    return `<div class="form-grid">
      ${field("Name", "name", current.name || "", "text", true)}
      ${selectField("Drawing", "drawingId", current.drawingId || "", drawings.map((row) => ({ value: row.id, label: row.name })), true)}
      ${field("Room / location", "roomName", current.roomName || roomName(current.roomId), "text", true)}
      ${field("Floor", "floorName", current.floorName || entityName(state.floors, current.floorId))}
      ${field("Building", "buildingName", current.buildingName || entityName(state.buildings, current.buildingId))}
      ${field("Scope", "scopeName", current.scopeName || entityName(state.scopes, current.scopeId), "text", true)}
      ${selectField("Scope category", "scopeCategory", current.scopeCategory || "drywall", scopeCategoryOptions())}
      ${field("Quantity", "quantity", current.quantity || "", "number", true)}
      ${field("Unit", "unit", current.unit || "SF", "text", true)}
      ${field("Wall SF", "wallSf", current.wallSf || "", "number")}
      ${field("Ceiling SF", "ceilingSf", current.ceilingSf || "", "number")}
      ${field("Paint SF", "paintSf", current.paintSf || "", "number")}
      ${field("Confidence %", "confidence", current.confidence == null ? 100 : current.confidence, "number", true)}
      ${field("Notes", "notes", current.notes || "", "text", false, true)}
    </div>`;
  }

  function renderScopeForm(project, item) {
    const drawings = filterByProject(state.drawings, project.id);
    const current = item || {};
    return `<div class="form-grid">
      ${field("Title", "title", current.title || "", "text", true)}
      ${selectField("Category", "category", current.category || "drywall", scopeCategoryOptions())}
      ${field("Confidence %", "confidence", current.confidence == null ? 100 : current.confidence, "number", true)}
      ${field("Proposed quantity", "quantity", current.quantity || "", "number")}
      ${field("Unit", "unit", current.unit || "SF")}
      ${selectField("Drawing", "drawingId", current.drawingId || "", drawings.map((row) => ({ value: row.id, label: row.name })), true)}
      ${field("Room / location", "roomName", current.roomName || roomName(current.roomId))}
      ${field("Description", "description", current.description || "", "text", false, true)}
    </div>`;
  }

  function renderRfiForm(project, item) {
    const drawings = filterByProject(state.drawings, project.id);
    const rooms = filterByProject(state.rooms, project.id);
    const scopes = filterByProject(state.scopes, project.id);
    const estimates = filterByProject(state.estimateLineItems, project.id);
    const current = item || {};
    return `<div class="form-grid">
      ${field("Title", "title", current.title || "", "text", true)}
      ${selectField("Status", "status", current.status || "open", [{ value: "open", label: "Open" }, { value: "resolved", label: "Resolved" }])}
      ${selectField("Drawing", "drawingId", current.drawingId || "", drawings.map((row) => ({ value: row.id, label: row.name })), true)}
      ${selectField("Room", "roomId", current.roomId || "", rooms.map((row) => ({ value: row.id, label: row.name })), true)}
      ${selectField("Scope", "scopeId", current.scopeId || "", scopes.map((row) => ({ value: row.id, label: row.name })), true)}
      ${selectField("Estimate item", "estimateItemId", current.estimateItemId || "", estimates.map((row) => ({ value: row.id, label: row.description })), true)}
      ${field("Question", "question", current.question || "", "text", true, true)}
      ${field("Answer / resolution", "answer", current.answer || "", "text", false, true)}
    </div>`;
  }

  function renderEstimateForm(item) {
    const current = item || {};
    return `<div class="form-grid">
      ${field("Description", "description", current.description || "", "text", true)}
      ${field("Quantity", "quantity", current.quantity || "", "number", true)}
      ${field("Unit", "unit", current.unit || "EA", "text", true)}
      ${field("Unit cost", "unitCost", current.unitCost || 0, "number", true)}
      ${field("Labor", "laborCost", current.laborCost || 0, "number", true)}
      ${field("Material", "materialCost", current.materialCost || 0, "number", true)}
      ${field("Markup %", "markupPercent", current.markupPercent == null ? state.settings.defaultMarkupPercent : current.markupPercent, "number", true)}
      ${field("Tax %", "taxPercent", current.taxPercent == null ? state.settings.defaultTaxPercent : current.taxPercent, "number", true)}
      ${field("Confidence %", "confidence", current.confidence == null ? 100 : current.confidence, "number", true)}
    </div>`;
  }

  function renderRiskForm(item) {
    return `<div class="form-grid">${field("Override confidence %", "overrideConfidence", item.overrideConfidence == null ? item.confidence : item.overrideConfidence, "number", true)}${selectField("Status", "status", item.status || "open", [{ value: "open", label: "Open" }, { value: "resolved", label: "Resolved" }])}${field("Review note", "note", item.note || "", "text", false, true)}</div>`;
  }

  function renderMemoryForm(item) {
    const current = item || {};
    const type = current.type || "standard_scope";
    return `<div class="form-grid">
      ${selectField("Entry type", "type", type, [
        { value: "standard_scope", label: "Standard scope" },
        { value: "material", label: "Material default" },
        { value: "labor_rate", label: "Labor rate" },
        { value: "markup", label: "Markup" },
        { value: "note_template", label: "Note / template" },
      ])}
      ${field("Name", "name", current.name || current.label || "", "text", true)}
      ${selectField("Scope category", "scopeCategory", current.scopeCategory || "drywall", scopeCategoryOptions())}
      ${field("Unit", "unit", current.unit || "")}
      ${field("Unit cost", "unitCost", current.unitCost || "", "number")}
      ${field("Labor cost", "laborCost", current.laborCost || "", "number")}
      ${field("Material cost", "materialCost", current.materialCost || "", "number")}
      ${field("Value / notes", "value", current.value || current.note || "", "text", false, true)}
    </div>`;
  }

  function renderExportModal(project) {
    return `<div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="Export project"><div class="modal"><div class="modal-header"><h2>Export ${escapeHtml(project.name)}</h2><button class="button ghost" type="button" data-action="close-modal" aria-label="Close dialog">✕</button></div><div class="modal-body stack"><button class="button" data-action="export-json">Export JSON</button><button class="button primary" data-action="export-csv">Export CSV</button><p>Exports include only real stored project data.</p></div></div></div>`;
  }

  function renderToasts() {
    if (!statefulUi.toasts.length) return "";
    return `<div class="toast-region" aria-live="polite">${statefulUi.toasts.map((toast) => `<div class="toast">${escapeHtml(toast.message)}</div>`).join("")}</div>`;
  }

  function field(label, name, value, type = "text", required = false, full = false) {
    const textarea = full && (name === "description" || name === "question" || name === "answer" || name === "notes" || name === "value" || name === "note");
    return `<label class="field ${full ? "full" : ""}"><span>${label}</span>${textarea ? `<textarea name="${name}" ${required ? "required" : ""}>${escapeHtml(value)}</textarea>` : `<input name="${name}" type="${type}" value="${escapeAttribute(value)}" ${required ? "required" : ""}>`}</label>`;
  }

  function selectField(label, name, value, options, allowBlank = false) {
    return `<label class="field"><span>${label}</span><select name="${name}">${allowBlank ? `<option value="">None</option>` : ""}${options.map((option) => `<option value="${escapeAttribute(option.value)}" ${String(value) === String(option.value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}</select></label>`;
  }

  async function handleClick(event) {
    const routeTarget = event.target.closest("[data-route]");
    if (routeTarget) {
      event.preventDefault();
      navigate(routeTarget.dataset.route);
      return;
    }

    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const id = target.dataset.id;

    switch (action) {
      case "toggle-sidebar": statefulUi.sidebarOpen = !statefulUi.sidebarOpen; render(); return;
      case "close-sidebar": statefulUi.sidebarOpen = false; render(); return;
      case "open-project-modal": openModal("project"); return;
      case "close-modal": closeModal(); return;
      case "trigger-document-upload": document.getElementById("document-upload")?.click(); return;
      case "trigger-project-import": document.getElementById("project-import")?.click(); return;
      case "open-export-modal": if (getActiveProject()) openModal("export"); return;
      case "preview-document": selectDrawingAndRoute(id, "drawing-viewer"); return;
      case "open-document": await openDocument(id); return;
      case "rename-document": openRenameDocument(id); return;
      case "delete-document": await deleteDocument(id); return;
      case "select-drawing": await selectDrawing(id); return;
      case "viewer-prev-page": changeViewerPage(id, -1); return;
      case "viewer-next-page": changeViewerPage(id, 1); return;
      case "toggle-focus-mode": toggleFocusMode(); return;
      case "toggle-sheet-navigator": toggleSheetNavigator(); return;
      case "toggle-right-inspector": toggleRightInspector(); return;
      case "set-drawing-mode": setDrawingMode(target.dataset.mode); return;
      case "set-measurement-tool": setMeasurementTool(target.dataset.tool); return;
      case "set-sheet-filter": statefulUi.sheetFilters.discipline = target.dataset.filter || "all"; render(); return;
      case "set-inspector-tab": statefulUi.activeInspectorTab = target.dataset.tab || "selection"; render(); return;
      case "open-ai-measurement-modal": openModal("aiMeasurement"); return;
      case "run-ai-takeoff": await runAiTakeoff(); return;
      case "export-ai-takeoff-csv": await exportAiTakeoffCsv(); return;
      case "open-scale-modal": openScaleModal(); return;
      case "add-sample-manual-measurement": await addSampleManualMeasurement(); return;
      case "select-measurement": selectMeasurement(id); return;
      case "select-issue": selectIssue(id); return;
      case "select-rfi": selectRfi(id); return;
      case "select-revision-change": pushToast("Revision change selected. Quantity deltas are shown in Compare mode."); render(); return;
      case "approve-selected-measurement": await updateSelectedMeasurementStatus("approved"); return;
      case "reject-selected-measurement": await rejectSelectedMeasurement(); return;
      case "edit-selected-measurement": openSelectedMeasurementEditor(); return;
      case "duplicate-selected-measurement": await duplicateSelectedMeasurement(); return;
      case "exclude-selected-measurement": await excludeSelectedMeasurement(); return;
      case "approve-high-confidence": await approveHighConfidenceMeasurements(); return;
      case "set-review-filter": statefulUi.reviewFilter = target.dataset.filter || "all"; render(); return;
      case "set-rfi-filter": statefulUi.rfiFilter = target.dataset.filter || "all"; render(); return;
      case "push-approved-to-takeoff": await pushApprovedToTakeoff(); return;
      case "push-selected-to-takeoff": await pushSelectedToTakeoff(); return;
      case "toggle-overlay-compare": statefulUi.compare.overlayCompare = !statefulUi.compare.overlayCompare; render(); return;
      case "toggle-revision-changes": statefulUi.compare.highlightChanges = !statefulUi.compare.highlightChanges; render(); return;
      case "side-by-side-placeholder": pushToast("Side-by-side revision compare is a placeholder for future backend rendering."); render(); return;
      case "show-quantity-delta": statefulUi.drawingMode = "compare"; statefulUi.activeInspectorTab = "selection"; render(); return;
      case "add-rfi-pin": await addRfiPin(); return;
      case "create-rfi-from-selected-issue": await createRfiFromSelectedIssue(); return;
      case "open-drawing-search-result": await openDrawingSearchResult(target); return;
      case "share-placeholder": pushToast("Share link placeholder. Connect to project permissions backend later."); render(); return;
      case "viewer-zoom-out":
      case "viewer-zoom-in":
      case "viewer-fit-page":
      case "viewer-fit-width":
      case "viewer-rotate":
      case "viewer-undo":
      case "viewer-redo":
      case "noop": pushToast(`${target.textContent.trim()} is a UI placeholder.`); render(); return;
      case "open-measurement-modal": openModal("measurement"); return;
      case "edit-measurement": openModal("measurement", findById(state.takeoffMeasurements, id)); return;
      case "delete-measurement": await deleteEntity("takeoffMeasurements", id, "Delete this takeoff row?"); return;
      case "set-scope-category": statefulUi.takeoffFilters.scopeCategory = target.dataset.category; render(); return;
      case "open-scope-modal": openModal("scope"); return;
      case "edit-scope": openModal("scope", findById(state.scopeDetections, id)); return;
      case "approve-scope": await updateScopeStatus(id, "approved"); return;
      case "reject-scope": await updateScopeStatus(id, "rejected"); return;
      case "promote-scope": await promoteScope(id); return;
      case "delete-scope": await deleteEntity("scopeDetections", id, "Delete this scope item?"); return;
      case "open-rfi-modal": openModal("rfi"); return;
      case "edit-rfi": openModal("rfi", findById(state.rfis, id)); return;
      case "resolve-rfi": await updateRfiStatus(id, "resolved"); return;
      case "reopen-rfi": await updateRfiStatus(id, "open"); return;
      case "delete-rfi": await deleteEntity("rfis", id, "Delete this RFI?"); return;
      case "generate-estimate": await generateEstimateFromTakeoff(); return;
      case "open-estimate-modal": openModal("estimate"); return;
      case "edit-estimate": openModal("estimate", findById(state.estimateLineItems, id)); return;
      case "delete-estimate": await deleteEntity("estimateLineItems", id, "Delete this estimate line?"); return;
      case "review-risk": openModal("risk", findById(state.riskItems, id)); return;
      case "resolve-risk": await updateRiskStatus(id, "resolved"); return;
      case "reopen-risk": await updateRiskStatus(id, "open"); return;
      case "export-json": await exportProject("json"); return;
      case "export-csv": await exportProject("csv"); return;
      case "open-memory-modal": openModal("memory"); return;
      case "edit-memory": openMemoryEditor(target.dataset.type, id); return;
      case "delete-memory": await deleteMemory(target.dataset.type, id); return;
      case "open-project": await setActiveProject(id); navigate("dashboard"); return;
      case "duplicate-project": await duplicateProjectAction(id); return;
      case "toggle-project-archive": await toggleProjectArchive(id); return;
      case "delete-project": await deleteProject(id); return;
      case "cycle-project-status": await cycleProjectStatus(); return;
      case "export-workspace": exportWorkspace(); return;
      case "clear-workspace": await clearWorkspace(); return;
      case "open-search-result": openSearchResult(target.dataset.type, id); return;
      default: return;
    }
  }

  async function handleSubmit(event) {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    switch (form.dataset.form) {
      case "project": await submitProject(data); return;
      case "document-rename": await submitDocumentRename(data); return;
      case "measurement": await submitMeasurement(data); return;
      case "ai-measurement": await submitAiMeasurement(data); return;
      case "scale-calibration": await submitScaleCalibration(data); return;
      case "drawing-measurement-edit": await submitDrawingMeasurementEdit(data); return;
      case "scope": await submitScope(data); return;
      case "rfi": await submitRfi(data); return;
      case "estimate": await submitEstimate(data); return;
      case "risk": await submitRisk(data); return;
      case "memory": await submitMemory(data); return;
      case "settings": await submitSettings(data); return;
      default: return;
    }
  }

  async function handleChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id === "document-upload") {
      await uploadDocuments(target.files);
      target.value = "";
      return;
    }
    if (target.id === "project-import") {
      await importProjectFile(target.files && target.files[0]);
      target.value = "";
      return;
    }
    let shouldRender = false;
    if (target.dataset.role === "takeoff-room-filter") {
      statefulUi.takeoffFilters.roomId = target.value;
      shouldRender = true;
    }
    if (target.dataset.role === "takeoff-floor-filter") {
      statefulUi.takeoffFilters.floorId = target.value;
      shouldRender = true;
    }
    if (target.dataset.role === "takeoff-building-filter") {
      statefulUi.takeoffFilters.buildingId = target.value;
      shouldRender = true;
    }
    if (target.dataset.role === "takeoff-scope-filter") {
      statefulUi.takeoffFilters.scopeId = target.value;
      shouldRender = true;
    }
    if (target.dataset.role === "viewer-page") {
      statefulUi.viewerPageByDrawingId[target.dataset.id] = Math.max(1, Number(target.value) || 1);
      shouldRender = true;
    }
    if (target.dataset.role === "drawing-layer") {
      statefulUi.visibleLayers[target.dataset.layer] = Boolean(target.checked);
      writeJsonPreference("visibleDrawingLayers", statefulUi.visibleLayers);
      shouldRender = true;
    }
    if (target.dataset.role === "confidence-heatmap") {
      statefulUi.confidenceHeatmap = Boolean(target.checked);
      writePreference("confidenceHeatmap", statefulUi.confidenceHeatmap);
      shouldRender = true;
    }
    if (target.dataset.role === "base-revision") {
      statefulUi.compare.baseRevisionId = target.value;
      shouldRender = true;
    }
    if (target.dataset.role === "current-revision") {
      statefulUi.compare.currentRevisionId = target.value;
      shouldRender = true;
    }
    if (shouldRender) render();
  }

  function handleInput(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.dataset.role === "project-search") {
      statefulUi.searchQuery = target.value;
      render();
    }
    if (target.dataset.role === "sheet-search") {
      statefulUi.sheetFilters.query = target.value;
      render();
    }
    if (target.dataset.role === "drawing-search") {
      statefulUi.drawingSearchQuery = target.value;
      render();
    }
  }

  function openModal(type, payload = {}) {
    statefulUi.modal = { type, payload: payload || {} };
    render();
  }

  function closeModal() {
    statefulUi.modal = null;
    render();
  }

  async function submitProject(data) {
    try {
      const project = createProject(state, data);
      statefulUi.modal = null;
      await saveAndRender(`Created ${project.name}.`);
      navigate("dashboard");
    } catch (error) {
      pushToast(error instanceof Error ? error.message : String(error));
      render();
    }
  }

  async function uploadDocuments(fileList) {
    const project = getActiveProject();
    if (!project || !fileList || !fileList.length) return;
    const db = await openDb();
    const files = Array.from(fileList);
    for (const file of files) {
      const drawing = {
        id: createId("drawing"),
        projectId: project.id,
        name: file.name,
        fileName: file.name,
        mimeType: file.type || inferMimeType(file.name),
        extension: file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "",
        size: file.size,
        pageCount: null,
        processingStatus: isPdf({ mimeType: file.type || inferMimeType(file.name), extension: file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "" }) ? "stored_pdf_pending_native_processing" : "stored",
        pageImages: [],
        uploadedAt: nowIso(),
        createdAt: nowIso(),
        updatedAt: nowIso(),
      };
      state.drawings.push(drawing);
      await dbSet(db, "files", drawing.id, file);
      if (!state.settings.activeDrawingIdByProject[project.id]) {
        state.settings.activeDrawingIdByProject[project.id] = drawing.id;
      }
      addActivity(state, project.id, "document.uploaded", `Uploaded document “${drawing.name}”.`);
    }
    await saveAndRender(`${files.length} file${files.length === 1 ? "" : "s"} uploaded.`);
  }

  async function openDocument(id) {
    const url = await ensurePreviewUrl(id);
    if (url) {
      window.open(url, "_blank", "noopener");
      return;
    }
    pushToast("Original file is not available locally. Re-upload the document.");
    render();
  }

  function openRenameDocument(id) {
    const drawing = findById(state.drawings, id);
    if (drawing) openModal("documentRename", drawing);
  }

  async function submitDocumentRename(data) {
    const id = statefulUi.modal.payload.id;
    const drawing = findById(state.drawings, id);
    if (!drawing) return;
    const name = cleanText(data.name);
    if (!name) return notify("Document name is required.");
    drawing.name = name;
    drawing.updatedAt = nowIso();
    addActivity(state, drawing.projectId, "document.renamed", `Renamed document to “${drawing.name}”.`);
    closeModal();
    await saveAndRender("Document renamed.");
  }

  async function deleteDocument(id) {
    const drawing = findById(state.drawings, id);
    if (!drawing || !window.confirm(`Delete “${drawing.name}”?`)) return;
    state.drawings = state.drawings.filter((item) => item.id !== id);
    const db = await openDb();
    await dbDelete(db, "files", id);
    revokePreviewUrl(id);
    if (state.settings.activeDrawingIdByProject[drawing.projectId] === id) {
      const next = filterByProject(state.drawings, drawing.projectId)[0];
      state.settings.activeDrawingIdByProject[drawing.projectId] = next ? next.id : null;
    }
    addActivity(state, drawing.projectId, "document.deleted", `Deleted document “${drawing.name}”.`);
    await saveAndRender("Document deleted.");
  }

  async function selectDrawing(id) {
    const drawing = findById(state.drawings, id);
    if (!drawing) return;
    state.settings.activeDrawingIdByProject[drawing.projectId] = id;
    statefulUi.selectedDrawingId = id;
    const selected = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (selected && (selected.sheetId || selected.drawingId) !== id) statefulUi.selectedMeasurementId = null;
    const rfi = findById(state.rfis, statefulUi.selectedRfiId);
    if (rfi && (rfi.sheetId || rfi.drawingId) !== id) statefulUi.selectedRfiId = null;
    statefulUi.selectedIssueId = null;
    await ensurePreviewUrl(id);
    await saveAndRender();
  }

  async function selectDrawingAndRoute(id, route) {
    await selectDrawing(id);
    navigate(route);
  }

  function changeViewerPage(id, delta) {
    const current = statefulUi.viewerPageByDrawingId[id] || 1;
    statefulUi.viewerPageByDrawingId[id] = Math.max(1, current + delta);
    render();
  }

  function toggleSheetNavigator() {
    statefulUi.sheetNavigatorCollapsed = !statefulUi.sheetNavigatorCollapsed;
    writePreference("sheetNavigatorCollapsed", statefulUi.sheetNavigatorCollapsed);
    render();
  }

  function toggleRightInspector() {
    statefulUi.rightInspectorCollapsed = !statefulUi.rightInspectorCollapsed;
    writePreference("rightInspectorCollapsed", statefulUi.rightInspectorCollapsed);
    render();
  }

  function toggleFocusMode() {
    statefulUi.focusModeEnabled = !statefulUi.focusModeEnabled;
    if (statefulUi.focusModeEnabled) {
      statefulUi.focusRestoreLayout = {
        sheetNavigatorCollapsed: statefulUi.sheetNavigatorCollapsed,
        rightInspectorCollapsed: statefulUi.rightInspectorCollapsed,
      };
      statefulUi.sheetNavigatorCollapsed = true;
      statefulUi.rightInspectorCollapsed = true;
    } else {
      const restore = statefulUi.focusRestoreLayout || {};
      statefulUi.sheetNavigatorCollapsed = Boolean(restore.sheetNavigatorCollapsed);
      statefulUi.rightInspectorCollapsed = Boolean(restore.rightInspectorCollapsed);
      statefulUi.focusRestoreLayout = null;
    }
    writePreference("sheetNavigatorCollapsed", statefulUi.sheetNavigatorCollapsed);
    writePreference("rightInspectorCollapsed", statefulUi.rightInspectorCollapsed);
    render();
  }

  function setDrawingMode(mode) {
    if (!mode) return;
    statefulUi.drawingMode = mode;
    statefulUi.focusModeEnabled = false;
    writePreference("lastSelectedMode", mode);
    if (mode === "view") statefulUi.selectedMeasurementTool = "";
    render();
  }

  function setMeasurementTool(tool) {
    statefulUi.selectedMeasurementTool = statefulUi.selectedMeasurementTool === tool ? "" : tool;
    render();
  }

  function openScaleModal() {
    const project = getActiveProject();
    if (!project) return;
    const sheetId = state.settings.activeDrawingIdByProject[project.id] || "";
    openModal("scaleCalibration", { sheetId });
  }

  async function submitAiMeasurement(data) {
    const project = getActiveProject();
    if (!project) return;
    const sheetIds = sheetIdsForAiOptions(project.id, data);
    if (!sheetIds.length) {
      pushToast("Select at least one sheet before running AI measurement.");
      render();
      return;
    }
    const approvedExisting = filterByProject(state.drawingMeasurements, project.id).filter((item) => sheetIds.includes(item.sheetId || item.drawingId) && ["approved", "pushed_to_takeoff"].includes(item.status));
    if (approvedExisting.length && !window.confirm("This AI run includes sheets with approved measurements. Existing approvals will be preserved and new AI draft measurements will be added. Continue?")) return;
    statefulUi.aiProcessingState = {
      status: "processing",
      progress: 38,
      sheetStatuses: sheetIds.map((sheetId) => ({ sheetId, status: "queued" })),
    };
    render();
    try {
      const results = await drawingServices.measurementService.runAiMeasurement({
        projectId: project.id,
        currentSheetId: data.currentSheetId,
        sheetIds,
        focus: data.focus,
      });
      state.drawingMeasurements.push(...results);
      statefulUi.aiProcessingState = { status: "complete", progress: 100, sheetStatuses: sheetIds.map((sheetId) => ({ sheetId, status: "complete" })) };
      statefulUi.modal = null;
      addActivity(state, project.id, "drawing.ai_measurement", `AI measurement draft created for ${sheetIds.length} sheet${sheetIds.length === 1 ? "" : "s"}.`);
      await saveAndRender("AI measurement draft created.");
    } catch (error) {
      statefulUi.aiProcessingState = { status: "failed", progress: 0, error: error instanceof Error ? error.message : String(error) };
      pushToast("AI measurement failed.");
      render();
    }
  }

  function sheetIdsForAiOptions(projectId, data) {
    const sheets = drawingServices.drawingService.getSheets(state, projectId);
    if (data.scope === "all") return sheets.map((sheet) => sheet.id);
    if (data.scope === "revised") return sheets.filter((sheet) => sheet.statuses.includes("Changed by addendum")).map((sheet) => sheet.id);
    if (data.scope === "selected") return cleanText(data.selectedSheetIds).split(/[,\s]+/).filter(Boolean);
    return [data.currentSheetId].filter(Boolean);
  }

  async function runAiTakeoff() {
    const project = getActiveProject();
    if (!project) return;
    if (!state.settings.aiTakeoffEnabled) {
      pushToast("AI takeoff is disabled in settings.");
      render();
      return;
    }
    const sheets = drawingServices.drawingService.getSheets(state, project.id);
    const activeId = state.settings.activeDrawingIdByProject[project.id] || sheets[0]?.id || "";
    if (!activeId) {
      pushToast("Upload and select a drawing before running AI takeoff.");
      render();
      return;
    }
    statefulUi.aiTakeoffStage = "Uploading";
    statefulUi.aiProcessingState = { status: "processing", progress: 8, sheetStatuses: [{ sheetId: activeId, status: "queued" }] };
    render();
    try {
      const run = await drawingServices.measurementService.runPaintingTakeoff({
        projectId: project.id,
        pageIds: [activeId],
        scope: "painting",
        ceilingHeightFt: 9,
        includeDoors: true,
        includeWindows: true,
        includeTrim: true,
        onProgress: (stage, progress) => {
          statefulUi.aiTakeoffStage = stage;
          statefulUi.aiProcessingState = { status: "processing", progress, sheetStatuses: [{ sheetId: activeId, status: stage }] };
          render();
        },
      });
      state.aiTakeoffRuns.push(run);
      statefulUi.aiTakeoffStage = "Complete";
      statefulUi.aiProcessingState = { status: "complete", progress: 100, sheetStatuses: [{ sheetId: activeId, status: "complete" }] };
      addActivity(state, project.id, "ai.takeoff", `AI painting takeoff ${run.status === "complete" ? "completed" : "recorded"} for 1 sheet.`);
      await saveAndRender(run.status === "not_configured" ? "AI provider not configured. Manual takeoff remains available." : "AI takeoff complete.");
    } catch (error) {
      statefulUi.aiProcessingState = { status: "failed", progress: 0, error: error instanceof Error ? error.message : String(error) };
      pushToast("AI takeoff failed.");
      render();
    }
  }

  async function exportAiTakeoffCsv() {
    const project = getActiveProject();
    if (!project) return;
    const run = latestAiTakeoffRun(project.id);
    if (!run) {
      pushToast("Run AI Takeoff before exporting AI quantities.");
      render();
      return;
    }
    downloadText(`${slugify(project.name)}-ai-painting-takeoff.csv`, aiTakeoffCsv(run), "text/csv");
    state.exports.unshift({
      id: createId("export"),
      projectId: project.id,
      fileName: `${slugify(project.name)}-ai-painting-takeoff.csv`,
      format: "csv",
      createdAt: nowIso(),
    });
    await saveAndRender("AI takeoff CSV exported.");
  }

  function aiTakeoffCsv(run) {
    const rows = [
      ["record_type", "room", "page_id", "floor_area_sf", "perimeter_ft", "wall_sf", "ceiling_sf", "doors", "windows", "trim_lf", "confidence", "assumptions"],
    ];
    for (const room of aiTakeoffRooms(run)) {
      rows.push([
        "room",
        room.name,
        room.pageId || "",
        room.floorAreaSf || "",
        room.perimeterFt || "",
        room.wallSf || "",
        room.ceilingSf || "",
        room.doorCount || 0,
        room.windowCount || 0,
        room.trimLf || "",
        room.confidence || "",
        (room.assumptions || []).join("; "),
      ]);
    }
    const totals = run.totals || calculateAiTakeoffTotals(run);
    rows.push(["summary", "TOTAL", "", totals.floorAreaSf, "", totals.wallSf, totals.ceilingSf, totals.doorCount, totals.windowCount, totals.trimLf, run.confidenceScore || "", (run.warnings || []).join("; ")]);
    return rows.map((row) => row.map(csvCell).join(",")).join("\n");
  }

  function csvCell(value) {
    const text = String(value == null ? "" : value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  async function submitScaleCalibration(data) {
    const project = getActiveProject();
    if (!project) return;
    const existing = state.drawingScaleCalibrations.find((item) => item.sheetId === data.sheetId);
    if (existing?.scaleLocked && data.scaleLocked !== "true" && !window.confirm("This scale is locked. Overwrite it?")) return;
    const row = existing || {
      id: createId("scale"),
      projectId: project.id,
      sheetId: data.sheetId,
      createdAt: nowIso(),
    };
    Object.assign(row, {
      scaleValue: cleanText(data.scaleValue),
      scaleSource: data.scaleSource,
      scaleConfidence: data.scaleConfidence,
      scaleLocked: data.scaleLocked === "true",
      calibratedBy: cleanText(data.calibratedBy) || state.settings.userName || "Estimator",
      calibratedAt: nowIso(),
      twoPointDistance: cleanText(data.twoPointDistance),
      pixelsPerFoot: optionalNumber(data.pixelsPerFoot),
      multiScaleZones: cleanText(data.multiScaleZones).split(/\n+/).filter(Boolean),
      updatedAt: nowIso(),
    });
    if (!existing) state.drawingScaleCalibrations.push(row);
    statefulUi.modal = null;
    addActivity(state, project.id, "drawing.scale", `Updated scale for drawing sheet.`);
    await saveAndRender("Scale calibration saved.");
  }

  async function submitDrawingMeasurementEdit(data) {
    const measurement = findById(state.drawingMeasurements, statefulUi.modal.payload.id);
    if (!measurement) return;
    Object.assign(measurement, {
      label: cleanText(data.label),
      category: data.category,
      quantity: numberValue(data.quantity),
      unit: cleanText(data.unit),
      status: data.status || "edited",
      notes: cleanText(data.notes),
      updatedAt: nowIso(),
    });
    statefulUi.modal = null;
    addActivity(state, measurement.projectId, "drawing.measurement_edit", `Edited drawing measurement ${measurement.label}.`);
    await saveAndRender("Measurement updated.");
  }

  async function addSampleManualMeasurement() {
    const project = getActiveProject();
    if (!project) return;
    const sheetId = state.settings.activeDrawingIdByProject[project.id];
    if (!sheetId) {
      pushToast("Select a sheet before adding a manual measurement.");
      render();
      return;
    }
    const measurement = drawingServices.measurementService.createManualMeasurement({
      projectId: project.id,
      sheetId,
      tool: statefulUi.selectedMeasurementTool || "line",
    });
    state.drawingMeasurements.push(measurement);
    statefulUi.selectedMeasurementId = measurement.id;
    statefulUi.selectedIssueId = null;
    statefulUi.selectedRfiId = null;
    addActivity(state, project.id, "drawing.manual_measurement", `Created manual drawing measurement ${measurement.label}.`);
    await saveAndRender("Manual measurement placeholder added.");
  }

  function selectMeasurement(id) {
    statefulUi.selectedMeasurementId = id;
    statefulUi.selectedIssueId = null;
    statefulUi.selectedRfiId = null;
    statefulUi.activeInspectorTab = "selection";
    render();
  }

  function selectIssue(id) {
    statefulUi.selectedIssueId = id;
    statefulUi.selectedMeasurementId = null;
    statefulUi.selectedRfiId = null;
    statefulUi.activeInspectorTab = "issues";
    render();
  }

  function selectRfi(id) {
    statefulUi.selectedRfiId = id;
    statefulUi.selectedMeasurementId = null;
    statefulUi.selectedIssueId = null;
    statefulUi.activeInspectorTab = "selection";
    render();
  }

  async function updateSelectedMeasurementStatus(status) {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) return notify("Select a measurement first.");
    measurement.status = status;
    measurement.updatedAt = nowIso();
    addActivity(state, measurement.projectId, "drawing.measurement_status", `${titleCase(status)} drawing measurement ${measurement.label}.`);
    await saveAndRender(`Measurement ${titleCase(status)}.`);
  }

  async function rejectSelectedMeasurement() {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) return notify("Select a measurement first.");
    const reason = window.prompt("Reason for rejecting this measurement (optional):", measurement.rejectionReason || "");
    measurement.status = "rejected";
    measurement.rejectionReason = cleanText(reason);
    measurement.updatedAt = nowIso();
    addActivity(state, measurement.projectId, "drawing.measurement_rejected", `Rejected drawing measurement ${measurement.label}.`);
    await saveAndRender("Measurement rejected.");
  }

  function openSelectedMeasurementEditor() {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) {
      pushToast("Select a measurement first.");
      render();
      return;
    }
    openModal("drawingMeasurementEdit", measurement);
  }

  async function duplicateSelectedMeasurement() {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) return notify("Select a measurement first.");
    const copy = { ...measurement, id: createId("drawing-measurement"), label: `${measurement.label} copy`, status: "draft", createdBy: "user", createdAt: nowIso(), updatedAt: nowIso() };
    state.drawingMeasurements.push(copy);
    statefulUi.selectedMeasurementId = copy.id;
    await saveAndRender("Measurement duplicated.");
  }

  async function excludeSelectedMeasurement() {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) return notify("Select a measurement first.");
    measurement.status = "rejected";
    measurement.excluded = true;
    measurement.updatedAt = nowIso();
    await saveAndRender("Measurement excluded.");
  }

  async function approveHighConfidenceMeasurements() {
    const project = getActiveProject();
    if (!project) return;
    const sheetId = state.settings.activeDrawingIdByProject[project.id];
    let count = 0;
    for (const measurement of filterByProject(state.drawingMeasurements, project.id)) {
      if ((measurement.sheetId || measurement.drawingId) === sheetId && Number(measurement.confidence || 0) >= 85 && !["approved", "pushed_to_takeoff", "rejected"].includes(measurement.status)) {
        measurement.status = "approved";
        measurement.updatedAt = nowIso();
        count += 1;
      }
    }
    await saveAndRender(`Approved ${count} high-confidence measurement${count === 1 ? "" : "s"}.`);
  }

  async function pushSelectedToTakeoff() {
    const measurement = findById(state.drawingMeasurements, statefulUi.selectedMeasurementId);
    if (!measurement) return notify("Select a measurement first.");
    await pushMeasurementsToTakeoff([measurement]);
  }

  async function pushApprovedToTakeoff() {
    const project = getActiveProject();
    if (!project) return;
    const sheetId = state.settings.activeDrawingIdByProject[project.id];
    const measurements = filterByProject(state.drawingMeasurements, project.id).filter((item) => (item.sheetId || item.drawingId) === sheetId && item.status === "approved");
    if (!measurements.length) {
      pushToast("No approved measurements are ready to push.");
      render();
      return;
    }
    if (!window.confirm(`Push ${measurements.length} approved measurement${measurements.length === 1 ? "" : "s"} to Takeoff?`)) return;
    await pushMeasurementsToTakeoff(measurements);
  }

  async function pushMeasurementsToTakeoff(measurements) {
    const project = getActiveProject();
    if (!project) return;
    const valid = measurements.filter((item) => item.status === "approved");
    if (!valid.length) {
      pushToast("Only approved measurements can be pushed to Takeoff.");
      render();
      return;
    }
    try {
      const rows = await drawingServices.measurementService.pushToTakeoff({ projectId: project.id, measurements: valid });
      state.takeoffMeasurements.push(...rows);
      for (let index = 0; index < valid.length; index += 1) {
        valid[index].status = "pushed_to_takeoff";
        valid[index].linkedTakeoffItemId = rows[index]?.id || "";
        valid[index].updatedAt = nowIso();
      }
      addActivity(state, project.id, "drawing.pushed_to_takeoff", `Pushed ${valid.length} approved drawing measurement${valid.length === 1 ? "" : "s"} to Takeoff.`);
      await saveAndRender("Approved measurements pushed to Takeoff.");
    } catch (_error) {
      notify("Push to Takeoff failed.");
    }
  }

  async function addRfiPin() {
    const project = getActiveProject();
    if (!project) return;
    const sheetId = state.settings.activeDrawingIdByProject[project.id];
    if (!sheetId) return notify("Select a sheet before adding an RFI pin.");
    const rfi = drawingServices.rfiService.createRfiPin({
      projectId: project.id,
      sheetId,
      linkedMeasurementId: statefulUi.selectedMeasurementId,
      title: "Confirm scope condition",
      description: "Draft RFI pin created from Drawing Viewer.",
    });
    state.rfis.push(rfi);
    statefulUi.selectedRfiId = rfi.id;
    statefulUi.selectedMeasurementId = null;
    statefulUi.selectedIssueId = null;
    await saveAndRender("RFI pin placeholder added.");
  }

  async function createRfiFromSelectedIssue() {
    const project = getActiveProject();
    if (!project) return;
    const activeSheetId = state.settings.activeDrawingIdByProject[project.id];
    const activeSheet = drawingServices.drawingService.getSheets(state, project.id).find((sheet) => sheet.id === activeSheetId);
    const measurements = filterByProject(state.drawingMeasurements, project.id).filter((item) => (item.sheetId || item.drawingId) === activeSheetId);
    const issue = getDrawingIssues(project.id, activeSheet, measurements).find((item) => item.id === statefulUi.selectedIssueId);
    if (!issue) return notify("Select an issue first.");
    const rfi = drawingServices.rfiService.createRfiFromIssue(issue);
    state.rfis.push(rfi);
    statefulUi.selectedRfiId = rfi.id;
    statefulUi.selectedIssueId = null;
    await saveAndRender("RFI created from issue.");
  }

  async function openDrawingSearchResult(target) {
    const sheetId = target.dataset.sheetId;
    if (sheetId) await selectDrawing(sheetId);
    const type = target.dataset.type;
    statefulUi.drawingSearchQuery = "";
    if (type === "scope item") selectMeasurement(target.dataset.id);
    else if (type === "rfi") selectRfi(target.dataset.id);
    else if (type === "issue") selectIssue(target.dataset.id);
    else render();
  }

  function getDrawingIssues(projectId, sheet, measurements) {
    if (!sheet) return [];
    const stored = filterByProject(state.drawingIssues, projectId).filter((item) => item.sheetId === sheet.id);
    const derived = [];
    if (!sheet.scaleCalibration || sheet.scaleCalibration.scaleSource === "missing") {
      derived.push({
        id: `issue-scale-${sheet.id}`,
        projectId,
        sheetId: sheet.id,
        title: "Scale missing or unconfirmed",
        description: "Calibrate or lock the sheet scale before relying on measured quantities.",
        status: "Open",
        severity: "high",
        geometry: { kind: "point", x: 18, y: 18 },
      });
    }
    for (const measurement of measurements.filter((item) => Number(item.confidence || 0) < 70)) {
      derived.push({
        id: `issue-low-${measurement.id}`,
        projectId,
        sheetId: sheet.id,
        linkedMeasurementId: measurement.id,
        title: `Low confidence: ${measurement.label}`,
        description: (measurement.warnings || []).join(" ") || "Estimator review required before approval.",
        status: "Open",
        severity: "medium",
        geometry: measurement.geometry?.kind === "point" ? measurement.geometry : { kind: "point", x: 31, y: 67 },
      });
    }
    return [...stored, ...derived];
  }

  function getDrawingRfis(projectId, sheetId) {
    return filterByProject(state.rfis, projectId).filter((item) => (item.sheetId || item.drawingId) === sheetId);
  }

  function filterSheetsForNavigator(sheets) {
    const query = cleanText(statefulUi.sheetFilters.query).toLowerCase();
    return sheets.filter((sheet) => {
      const filter = statefulUi.sheetFilters.discipline;
      if (filter && filter !== "all") {
        if (["architectural", "structural", "mep"].includes(filter) && sheet.discipline !== filter) return false;
        if (filter === "revised" && !sheet.statuses.includes("Changed by addendum")) return false;
        if (filter === "needs-review" && !sheet.statuses.includes("Needs review") && !sheet.statuses.includes("Scale missing")) return false;
        if (filter === "has-rfis" && !sheet.statuses.includes("Has RFI")) return false;
        if (filter === "processed" && !sheet.statuses.includes("AI processed")) return false;
        if (filter === "not-processed" && !sheet.statuses.includes("Not processed")) return false;
      }
      if (!query) return true;
      return [sheet.sheetNumber, sheet.sheetTitle, sheet.discipline, sheet.revision, sheet.revisionName].join(" ").toLowerCase().includes(query);
    });
  }

  function getDrawingSearchResults(project, active) {
    const sheets = drawingServices.drawingService.getSheets(state, project.id);
    const measurements = filterByProject(state.drawingMeasurements, project.id);
    const rfis = filterByProject(state.rfis, project.id);
    const issues = sheets.flatMap((sheet) => getDrawingIssues(project.id, sheet, measurements.filter((item) => (item.sheetId || item.drawingId) === sheet.id)));
    return drawingServices.searchService.search({
      query: statefulUi.drawingSearchQuery,
      sheets,
      measurements,
      issues,
      rfis,
      activeSheetId: active?.id,
    });
  }

  function measurementVisible(item) {
    if (statefulUi.reviewFilter === "low-confidence" && Number(item.confidence || 0) >= 70) return false;
    if (statefulUi.reviewFilter === "unapproved" && ["approved", "pushed_to_takeoff", "rejected"].includes(item.status)) return false;
    const layerKey = drawingServices.measurementService.measurementLayerKey(item);
    return statefulUi.visibleLayers[layerKey] !== false;
  }

  function issueVisible(item) {
    if (item.severity === "high") return statefulUi.visibleLayers["low-confidence"] !== false;
    return statefulUi.visibleLayers["low-confidence"] !== false;
  }

  function rfiVisible(item) {
    if (statefulUi.visibleLayers.rfis === false) return false;
    const status = String(item.status || "").toLowerCase();
    if (statefulUi.rfiFilter === "resolved") return ["answered", "closed", "resolved"].includes(status);
    if (statefulUi.rfiFilter === "unresolved") return !["answered", "closed", "resolved"].includes(status);
    return true;
  }

  function selectedClass(type, id) {
    if (type === "measurement" && statefulUi.selectedMeasurementId === id) return "selected";
    if (type === "issue" && statefulUi.selectedIssueId === id) return "selected";
    if (type === "rfi" && statefulUi.selectedRfiId === id) return "selected";
    return "";
  }

  function confidenceClass(confidence) {
    const value = Number(confidence);
    if (!Number.isFinite(value)) return "confidence-blocked";
    if (value >= 85) return "confidence-high";
    if (value >= 70) return "confidence-medium";
    return "confidence-low";
  }

  function getSelectedContext(active, measurements, issues, rfis) {
    const measurement = measurements.find((item) => item.id === statefulUi.selectedMeasurementId);
    if (measurement) return { kind: "measurement", item: measurement, label: measurement.label };
    const issue = issues.find((item) => item.id === statefulUi.selectedIssueId);
    if (issue) return { kind: "issue", item: issue, label: issue.title };
    const rfi = rfis.find((item) => item.id === statefulUi.selectedRfiId);
    if (rfi) return { kind: "rfi", item: rfi, label: rfi.title };
    return null;
  }

  function getReviewStats(measurements) {
    return {
      detected: measurements.filter((item) => item.status === "detected").length,
      reviewed: measurements.filter((item) => item.status === "reviewed" || item.status === "edited").length,
      approved: measurements.filter((item) => item.status === "approved").length,
      rejected: measurements.filter((item) => item.status === "rejected").length,
      pushed: measurements.filter((item) => item.status === "pushed_to_takeoff").length,
      needsReview: measurements.filter((item) => ["detected", "reviewed", "edited", "draft"].includes(item.status)).length,
    };
  }

  function num(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0;
    return Math.max(0, Math.min(100, numeric));
  }

  async function ensurePreviewUrl(id) {
    if (!id) return null;
    if (statefulUi.previewUrls.has(id)) return statefulUi.previewUrls.get(id);
    const db = await openDb();
    const file = await dbGet(db, "files", id);
    if (!file) {
      statefulUi.missingFileIds.add(id);
      return null;
    }
    const url = URL.createObjectURL(file);
    statefulUi.previewUrls.set(id, url);
    statefulUi.missingFileIds.delete(id);
    return url;
  }

  function revokePreviewUrl(id) {
    const url = statefulUi.previewUrls.get(id);
    if (url) URL.revokeObjectURL(url);
    statefulUi.previewUrls.delete(id);
    statefulUi.missingFileIds.delete(id);
  }

  function hydratePreviewIfNeeded() {
    const project = getActiveProject();
    if (statefulUi.route !== "drawing-viewer" || !project) return;
    const id = state.settings.activeDrawingIdByProject[project.id] || filterByProject(state.drawings, project.id)[0]?.id;
    if (id && !statefulUi.previewUrls.has(id)) {
      ensurePreviewUrl(id).then(() => render());
    }
  }

  async function submitMeasurement(data) {
    const project = getActiveProject();
    if (!project) return;
    const existing = statefulUi.modal.payload.id ? findById(state.takeoffMeasurements, statefulUi.modal.payload.id) : null;
    const entities = ensureLocationEntities(project.id, data);
    const scope = ensureScope(project.id, data.scopeName, data.scopeCategory);
    const row = existing || {
      id: createId("takeoff"),
      projectId: project.id,
      createdAt: nowIso(),
    };
    Object.assign(row, {
      drawingId: data.drawingId || "",
      roomId: entities.roomId,
      floorId: entities.floorId,
      buildingId: entities.buildingId,
      scopeId: scope.id,
      scopeCategory: data.scopeCategory,
      name: cleanText(data.name),
      quantity: numberValue(data.quantity),
      unit: cleanText(data.unit),
      wallSf: numberValue(data.wallSf),
      ceilingSf: numberValue(data.ceilingSf),
      paintSf: numberValue(data.paintSf),
      confidence: clampConfidence(data.confidence),
      notes: cleanText(data.notes),
      updatedAt: nowIso(),
    });
    if (!existing) state.takeoffMeasurements.push(row);
    addActivity(state, project.id, existing ? "takeoff.updated" : "takeoff.created", `${existing ? "Updated" : "Created"} takeoff row “${row.name}”.`);
    closeModal();
    await saveAndRender(existing ? "Takeoff row updated." : "Takeoff row created.");
  }

  async function submitScope(data) {
    const project = getActiveProject();
    if (!project) return;
    const existing = statefulUi.modal.payload.id ? findById(state.scopeDetections, statefulUi.modal.payload.id) : null;
    const entities = ensureLocationEntities(project.id, data);
    const row = existing || {
      id: createId("scope-detection"),
      projectId: project.id,
      status: "pending",
      createdAt: nowIso(),
    };
    Object.assign(row, {
      title: cleanText(data.title),
      description: cleanText(data.description),
      category: data.category,
      confidence: clampConfidence(data.confidence),
      quantity: optionalNumber(data.quantity),
      unit: cleanText(data.unit),
      drawingId: data.drawingId || "",
      roomId: entities.roomId,
      updatedAt: nowIso(),
    });
    if (!existing) state.scopeDetections.push(row);
    addActivity(state, project.id, existing ? "scope.updated" : "scope.created", `${existing ? "Updated" : "Created"} scope item “${row.title}”.`);
    closeModal();
    await saveAndRender(existing ? "Scope item updated." : "Scope item created.");
  }

  async function updateScopeStatus(id, status) {
    const row = findById(state.scopeDetections, id);
    if (!row) return;
    row.status = status;
    row.updatedAt = nowIso();
    addActivity(state, row.projectId, "scope.status", `${titleCase(status)} scope item “${row.title}”.`);
    await saveAndRender(`Scope item ${status}.`);
  }

  async function promoteScope(id) {
    const project = getActiveProject();
    const item = findById(state.scopeDetections, id);
    if (!project || !item) return;
    if (item.quantity == null || !item.unit) {
      openModal("scope", item);
      pushToast("Add a proposed quantity and unit before promotion.");
      render();
      return;
    }
    const scope = ensureScope(project.id, item.title, item.category);
    let measurement = item.promotedMeasurementId ? findById(state.takeoffMeasurements, item.promotedMeasurementId) : null;
    if (!measurement) {
      measurement = {
        id: createId("takeoff"),
        projectId: project.id,
        drawingId: item.drawingId || "",
        roomId: item.roomId || "",
        floorId: "",
        buildingId: "",
        scopeId: scope.id,
        scopeCategory: item.category,
        name: item.title,
        quantity: item.quantity,
        unit: item.unit,
        wallSf: item.category === "drywall" ? item.quantity : 0,
        ceilingSf: item.category === "ceilings" ? item.quantity : 0,
        paintSf: item.category === "paint" ? item.quantity : 0,
        confidence: item.confidence,
        notes: item.description || "",
        createdAt: nowIso(),
        updatedAt: nowIso(),
      };
      state.takeoffMeasurements.push(measurement);
      item.promotedMeasurementId = measurement.id;
    }
    const generated = estimateFromMeasurement(project.id, measurement);
    item.promotedEstimateItemId = generated.id;
    item.updatedAt = nowIso();
    addActivity(state, project.id, "scope.promoted", `Promoted scope item “${item.title}” into takeoff and estimate.`);
    await saveAndRender("Scope item promoted.");
  }

  async function submitRfi(data) {
    const project = getActiveProject();
    if (!project) return;
    const existing = statefulUi.modal.payload.id ? findById(state.rfis, statefulUi.modal.payload.id) : null;
    const row = existing || {
      id: createId("rfi"),
      projectId: project.id,
      createdAt: nowIso(),
    };
    Object.assign(row, {
      title: cleanText(data.title),
      status: data.status,
      drawingId: data.drawingId || "",
      roomId: data.roomId || "",
      scopeId: data.scopeId || "",
      estimateItemId: data.estimateItemId || "",
      question: cleanText(data.question),
      answer: cleanText(data.answer),
      updatedAt: nowIso(),
    });
    if (!existing) state.rfis.push(row);
    addActivity(state, project.id, existing ? "rfi.updated" : "rfi.created", `${existing ? "Updated" : "Created"} RFI “${row.title}”.`);
    closeModal();
    await saveAndRender(existing ? "RFI updated." : "RFI created.");
  }

  async function updateRfiStatus(id, status) {
    const row = findById(state.rfis, id);
    if (!row) return;
    row.status = status;
    row.updatedAt = nowIso();
    addActivity(state, row.projectId, "rfi.status", `${titleCase(status)} RFI “${row.title}”.`);
    await saveAndRender(`RFI ${status}.`);
  }

  async function submitEstimate(data) {
    const project = getActiveProject();
    if (!project) return;
    const existing = statefulUi.modal.payload.id ? findById(state.estimateLineItems, statefulUi.modal.payload.id) : null;
    const row = existing || {
      id: createId("estimate"),
      projectId: project.id,
      sourceType: "manual",
      createdAt: nowIso(),
    };
    Object.assign(row, {
      description: cleanText(data.description),
      quantity: numberValue(data.quantity),
      unit: cleanText(data.unit),
      unitCost: numberValue(data.unitCost),
      laborCost: numberValue(data.laborCost),
      materialCost: numberValue(data.materialCost),
      markupPercent: numberValue(data.markupPercent),
      taxPercent: numberValue(data.taxPercent),
      confidence: clampConfidence(data.confidence),
      updatedAt: nowIso(),
    });
    if (!existing) state.estimateLineItems.push(row);
    addActivity(state, project.id, existing ? "estimate.updated" : "estimate.created", `${existing ? "Updated" : "Created"} estimate line “${row.description}”.`);
    closeModal();
    await saveAndRender(existing ? "Estimate line updated." : "Estimate line created.");
  }

  async function generateEstimateFromTakeoff() {
    const project = getActiveProject();
    if (!project) return;
    const rows = filterByProject(state.takeoffMeasurements, project.id);
    if (!rows.length) {
      pushToast("Add takeoff rows before generating an estimate.");
      render();
      return;
    }
    rows.forEach((row) => estimateFromMeasurement(project.id, row));
    addActivity(state, project.id, "estimate.generated", `Generated estimate lines from ${rows.length} takeoff row${rows.length === 1 ? "" : "s"}.`);
    await saveAndRender("Estimate generated from takeoff.");
  }

  function estimateFromMeasurement(projectId, measurement) {
    const existing = filterByProject(state.estimateLineItems, projectId).find((item) => item.sourceMeasurementId === measurement.id);
    const defaultMaterial = state.materials.find((item) => item.scopeCategory === measurement.scopeCategory);
    const defaultLaborRate = state.companyMemoryEntries.find((item) => item.type === "labor_rate" && item.scopeCategory === measurement.scopeCategory);
    const defaultMarkup = state.companyMemoryEntries.find((item) => item.type === "markup" && item.scopeCategory === measurement.scopeCategory);
    const scopeNameValue = entityName(state.scopes, measurement.scopeId) || titleCase(measurement.scopeCategory);
    const row = existing || {
      id: createId("estimate"),
      projectId,
      sourceType: "generated",
      sourceMeasurementId: measurement.id,
      scopeId: measurement.scopeId,
      createdAt: nowIso(),
    };
    Object.assign(row, {
      description: `${scopeNameValue} — ${measurement.name}`,
      quantity: measurement.quantity,
      unit: measurement.unit,
      unitCost: defaultMaterial ? numberValue(defaultMaterial.unitCost) : 0,
      laborCost: defaultLaborRate
        ? numberValue(defaultLaborRate.unitCost || defaultLaborRate.laborCost)
        : defaultMaterial
          ? numberValue(defaultMaterial.laborCost)
          : 0,
      materialCost: defaultMaterial ? numberValue(defaultMaterial.materialCost) : 0,
      markupPercent: defaultMarkup
        ? numberValue(defaultMarkup.unitCost || defaultMarkup.value)
        : state.settings.defaultMarkupPercent,
      taxPercent: state.settings.defaultTaxPercent,
      confidence: measurement.confidence,
      updatedAt: nowIso(),
    });
    if (!existing) state.estimateLineItems.push(row);
    return row;
  }

  async function submitRisk(data) {
    const row = findById(state.riskItems, statefulUi.modal.payload.id);
    if (!row) return;
    row.overrideConfidence = clampConfidence(data.overrideConfidence);
    row.status = data.status;
    row.note = cleanText(data.note);
    row.updatedAt = nowIso();
    addActivity(state, row.projectId, "risk.reviewed", `Reviewed confidence issue “${row.label}”.`);
    closeModal();
    await saveAndRender("Confidence review saved.");
  }

  async function updateRiskStatus(id, status) {
    const row = findById(state.riskItems, id);
    if (!row) return;
    row.status = status;
    row.updatedAt = nowIso();
    addActivity(state, row.projectId, "risk.status", `${titleCase(status)} confidence issue “${row.label}”.`);
    await saveAndRender(`Confidence issue ${status}.`);
  }

  async function exportProject(format) {
    const project = getActiveProject();
    if (!project) return;
    const safeName = slugify(project.name);
    const content = format === "json" ? buildProjectJson(state, project.id) : buildProjectCsv(state, project.id);
    const extension = format === "json" ? "json" : "csv";
    const mime = format === "json" ? "application/json" : "text/csv";
    const fileName = `${safeName || "project"}-${new Date().toISOString().slice(0, 10)}.${extension}`;
    downloadText(fileName, content, mime);
    state.exports.push({
      id: createId("export"),
      projectId: project.id,
      format,
      fileName,
      createdAt: nowIso(),
      updatedAt: nowIso(),
    });
    addActivity(state, project.id, "export.created", `Exported ${format.toUpperCase()} file “${fileName}”.`);
    statefulUi.modal = null;
    await saveAndRender(`${format.toUpperCase()} export created.`);
  }

  async function submitMemory(data) {
    const type = data.type;
    const existingPayload = statefulUi.modal.payload || {};
    if (type === "material") {
      const existing = existingPayload.id ? findById(state.materials, existingPayload.id) : null;
      const row = existing || { id: createId("material"), createdAt: nowIso() };
      Object.assign(row, {
        name: cleanText(data.name),
        scopeCategory: data.scopeCategory,
        unit: cleanText(data.unit),
        unitCost: optionalNumber(data.unitCost) || 0,
        laborCost: optionalNumber(data.laborCost) || 0,
        materialCost: optionalNumber(data.materialCost) || 0,
        note: cleanText(data.value),
        updatedAt: nowIso(),
      });
      if (!existing) state.materials.push(row);
    } else {
      const existing = existingPayload.id ? findById(state.companyMemoryEntries, existingPayload.id) : null;
      const row = existing || { id: createId("memory"), createdAt: nowIso() };
      Object.assign(row, {
        type,
        name: cleanText(data.name),
        scopeCategory: data.scopeCategory,
        unit: cleanText(data.unit),
        unitCost: optionalNumber(data.unitCost),
        laborCost: optionalNumber(data.laborCost),
        materialCost: optionalNumber(data.materialCost),
        value: cleanText(data.value),
        updatedAt: nowIso(),
      });
      if (!existing) state.companyMemoryEntries.push(row);
    }
    closeModal();
    await saveAndRender("Company memory saved.");
  }

  function openMemoryEditor(type, id) {
    const source = type === "material" ? state.materials : state.companyMemoryEntries;
    const item = findById(source, id);
    if (item) openModal("memory", { ...item, type });
  }

  async function deleteMemory(type, id) {
    if (!window.confirm("Delete this company memory entry?")) return;
    if (type === "material") state.materials = state.materials.filter((item) => item.id !== id);
    else state.companyMemoryEntries = state.companyMemoryEntries.filter((item) => item.id !== id);
    await saveAndRender("Company memory deleted.");
  }

  async function setActiveProject(id) {
    const project = findById(state.projects, id);
    if (!project) return;
    state.settings.activeProjectId = id;
    statefulUi.selectedDrawingId = state.settings.activeDrawingIdByProject[id] || null;
    await saveAndRender(`Opened ${project.name}.`);
  }

  async function duplicateProjectAction(id) {
    const originalDrawings = filterByProject(state.drawings, id);
    const project = duplicateProject(state, id);
    const clonedDrawings = filterByProject(state.drawings, project.id);
    const db = await openDb();
    for (let index = 0; index < originalDrawings.length; index += 1) {
      const file = await dbGet(db, "files", originalDrawings[index].id);
      if (file) await dbSet(db, "files", clonedDrawings[index].id, file);
    }
    await saveAndRender(`Duplicated ${project.name}.`);
  }

  async function toggleProjectArchive(id) {
    const project = findById(state.projects, id);
    if (!project) return;
    project.archived = !project.archived;
    project.updatedAt = nowIso();
    await saveAndRender(project.archived ? "Project archived." : "Project restored.");
  }

  async function deleteProject(id) {
    const project = findById(state.projects, id);
    if (!project || !window.confirm(`Delete “${project.name}” and its project data?`)) return;
    const drawingIds = filterByProject(state.drawings, id).map((item) => item.id);
    for (const drawingId of drawingIds) {
      const db = await openDb();
      await dbDelete(db, "files", drawingId);
      revokePreviewUrl(drawingId);
    }
    state.projects = state.projects.filter((item) => item.id !== id);
    for (const key of ["drawings", "rooms", "floors", "buildings", "scopes", "scopeDetections", "drawingMeasurements", "drawingIssues", "drawingScaleCalibrations", "drawingRevisionReviews", "aiTakeoffRuns", "takeoffMeasurements", "estimateLineItems", "rfis", "riskItems", "exports", "activities"]) {
      state[key] = state[key].filter((item) => item.projectId !== id);
    }
    if (state.settings.activeProjectId === id) {
      state.settings.activeProjectId = state.projects.find((item) => !item.archived)?.id || state.projects[0]?.id || null;
    }
    await saveAndRender("Project deleted.");
  }

  async function cycleProjectStatus() {
    const project = getActiveProject();
    if (!project) return;
    const statuses = ["draft", "in_review", "ready"];
    project.reviewStatus = statuses[(statuses.indexOf(project.reviewStatus) + 1) % statuses.length];
    project.updatedAt = nowIso();
    addActivity(state, project.id, "project.status", `Set project status to ${projectStatus(project)}.`);
    await saveAndRender("Project status updated.");
  }

  async function submitSettings(data) {
    Object.assign(state.settings, {
      companyName: cleanText(data.companyName),
      companyEmail: cleanText(data.companyEmail),
      companyPhone: cleanText(data.companyPhone),
      companyAddress: cleanText(data.companyAddress),
      units: data.units,
      currency: data.currency,
      defaultMarkupPercent: numberValue(data.defaultMarkupPercent),
      defaultTaxPercent: numberValue(data.defaultTaxPercent),
      lowConfidenceThreshold: numberValue(data.lowConfidenceThreshold),
      aiTakeoffEnabled: data.aiTakeoffEnabled !== "false",
      userName: cleanText(data.userName),
      userEmail: cleanText(data.userEmail),
    });
    await saveAndRender("Settings saved.");
  }

  function exportWorkspace() {
    downloadText(`takeoff-workspace-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(state, null, 2), "application/json");
    pushToast("Workspace export created.");
    render();
  }

  async function clearWorkspace() {
    if (!window.confirm("Clear all local workspace data and uploaded files?")) return;
    const db = await openDb();
    for (const drawing of state.drawings) await dbDelete(db, "files", drawing.id);
    for (const id of statefulUi.previewUrls.keys()) revokePreviewUrl(id);
    state = createEmptyState();
    statefulUi.route = "dashboard";
    statefulUi.modal = null;
    await saveAndRender("Workspace cleared.");
  }

  async function importProjectFile(file) {
    if (!file) return;
    try {
      const text = await file.text();
      const bundle = JSON.parse(text);
      importProjectBundle(bundle);
      await saveAndRender("Project imported.");
      navigate("dashboard");
    } catch (error) {
      pushToast(error instanceof Error ? error.message : "Could not import project JSON.");
      render();
    }
  }

  function importProjectBundle(bundle) {
    if (!bundle || !bundle.project) throw new Error("Project JSON is missing a project record.");
    const projectId = createId("project");
    const maps = {
      drawings: new Map(),
      rooms: new Map(),
      floors: new Map(),
      buildings: new Map(),
      scopes: new Map(),
      scopeDetections: new Map(),
      drawingMeasurements: new Map(),
      drawingIssues: new Map(),
      drawingScaleCalibrations: new Map(),
      drawingRevisionReviews: new Map(),
      aiTakeoffRuns: new Map(),
      takeoffMeasurements: new Map(),
      estimateLineItems: new Map(),
      rfis: new Map(),
      riskItems: new Map(),
      exports: new Map(),
      activities: new Map(),
    };
    state.projects.push({ ...bundle.project, id: projectId, archived: false, createdAt: nowIso(), updatedAt: nowIso() });
    for (const key of Object.keys(maps)) {
      const rows = Array.isArray(bundle[key]) ? bundle[key] : [];
      for (const row of rows) {
        const nextId = createId(key.slice(0, -1));
        maps[key].set(row.id, nextId);
        state[key].push({ ...row, id: nextId, projectId, createdAt: nowIso(), updatedAt: nowIso() });
      }
    }
    for (const row of filterByProject(state.takeoffMeasurements, projectId)) {
      row.drawingId = remapImported(maps.drawings, row.drawingId);
      row.roomId = remapImported(maps.rooms, row.roomId);
      row.floorId = remapImported(maps.floors, row.floorId);
      row.buildingId = remapImported(maps.buildings, row.buildingId);
      row.scopeId = remapImported(maps.scopes, row.scopeId);
    }
    for (const row of filterByProject(state.scopeDetections, projectId)) {
      row.drawingId = remapImported(maps.drawings, row.drawingId);
      row.roomId = remapImported(maps.rooms, row.roomId);
      row.promotedMeasurementId = remapImported(maps.takeoffMeasurements, row.promotedMeasurementId);
      row.promotedEstimateItemId = remapImported(maps.estimateLineItems, row.promotedEstimateItemId);
    }
    for (const row of filterByProject(state.drawingMeasurements, projectId)) {
      row.sheetId = remapImported(maps.drawings, row.sheetId);
      row.drawingId = remapImported(maps.drawings, row.drawingId);
      row.linkedTakeoffItemId = remapImported(maps.takeoffMeasurements, row.linkedTakeoffItemId);
    }
    for (const row of filterByProject(state.drawingIssues, projectId)) {
      row.sheetId = remapImported(maps.drawings, row.sheetId);
      row.linkedMeasurementId = remapImported(maps.drawingMeasurements, row.linkedMeasurementId);
    }
    for (const row of filterByProject(state.drawingScaleCalibrations, projectId)) {
      row.sheetId = remapImported(maps.drawings, row.sheetId);
    }
    for (const row of filterByProject(state.drawingRevisionReviews, projectId)) {
      row.sheetId = remapImported(maps.drawings, row.sheetId);
    }
    for (const row of filterByProject(state.estimateLineItems, projectId)) {
      row.sourceMeasurementId = remapImported(maps.takeoffMeasurements, row.sourceMeasurementId);
      row.scopeId = remapImported(maps.scopes, row.scopeId);
    }
    for (const row of filterByProject(state.rfis, projectId)) {
      row.sheetId = remapImported(maps.drawings, row.sheetId);
      row.drawingId = remapImported(maps.drawings, row.drawingId);
      row.roomId = remapImported(maps.rooms, row.roomId);
      row.scopeId = remapImported(maps.scopes, row.scopeId);
      row.estimateItemId = remapImported(maps.estimateLineItems, row.estimateItemId);
      row.linkedMeasurementId = remapImported(maps.drawingMeasurements, row.linkedMeasurementId);
    }
    for (const row of filterByProject(state.riskItems, projectId)) {
      if (row.referenceType === "takeoff") row.referenceId = remapImported(maps.takeoffMeasurements, row.referenceId);
      if (row.referenceType === "scope") row.referenceId = remapImported(maps.scopeDetections, row.referenceId);
      if (row.referenceType === "estimate") row.referenceId = remapImported(maps.estimateLineItems, row.referenceId);
    }
    state.settings.activeProjectId = projectId;
    addActivity(state, projectId, "project.imported", `Imported project “${bundle.project.name}”.`);
  }

  function remapImported(map, value) {
    return value ? map.get(value) || "" : "";
  }

  function openSearchResult(type, id) {
    const routeMap = {
      drawing: "documents",
      room: "takeoff",
      floor: "takeoff",
      building: "takeoff",
      scope: "scope-detection",
      "drawing-measurement": "drawing-viewer",
      "drawing-issue": "drawing-viewer",
      takeoff: "takeoff",
      estimate: "estimate",
      rfi: "questions-rfis",
    };
    statefulUi.searchQuery = "";
    if (type === "drawing") selectDrawing(id);
    if (type === "drawing-measurement") {
      const measurement = findById(state.drawingMeasurements, id);
      if (measurement?.sheetId || measurement?.drawingId) selectDrawing(measurement.sheetId || measurement.drawingId);
      statefulUi.selectedMeasurementId = id;
    }
    if (type === "drawing-issue") statefulUi.selectedIssueId = id;
    navigate(routeMap[type] || "dashboard");
  }

  async function deleteEntity(key, id, prompt) {
    const row = findById(state[key], id);
    if (!row || !window.confirm(prompt)) return;
    state[key] = state[key].filter((item) => item.id !== id);
    addActivity(state, row.projectId, `${key}.deleted`, `Deleted ${key} record.`);
    await saveAndRender("Record deleted.");
  }

  function syncDerivedRisks() {
    const project = getActiveProject();
    if (!project) return;
    const derived = deriveRiskItems(state, project.id);
    state.riskItems = [
      ...state.riskItems.filter((item) => item.projectId !== project.id),
      ...derived,
    ];
  }

  function enrichTakeoffRows(projectId) {
    return filterByProject(state.takeoffMeasurements, projectId).map((row) => ({
      ...row,
      roomName: entityName(state.rooms, row.roomId),
      floorName: entityName(state.floors, row.floorId),
      buildingName: entityName(state.buildings, row.buildingId),
      scopeName: entityName(state.scopes, row.scopeId),
    }));
  }

  function latestAiTakeoffRun(projectId) {
    return [...filterByProject(state.aiTakeoffRuns, projectId)].sort((a, b) => String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || "")))[0] || null;
  }

  function ensureLocationEntities(projectId, data) {
    return {
      roomId: ensureNamedEntity("rooms", projectId, data.roomName),
      floorId: ensureNamedEntity("floors", projectId, data.floorName),
      buildingId: ensureNamedEntity("buildings", projectId, data.buildingName),
    };
  }

  function ensureNamedEntity(key, projectId, name) {
    const normalized = cleanText(name);
    if (!normalized) return "";
    let row = filterByProject(state[key], projectId).find((item) => item.name.toLowerCase() === normalized.toLowerCase());
    if (!row) {
      row = { id: createId(key.slice(0, -1)), projectId, name: normalized, createdAt: nowIso(), updatedAt: nowIso() };
      state[key].push(row);
    }
    return row.id;
  }

  function ensureScope(projectId, name, category) {
    const normalized = cleanText(name);
    let row = filterByProject(state.scopes, projectId).find((item) => item.name.toLowerCase() === normalized.toLowerCase() && item.category === category);
    if (!row) {
      row = { id: createId("scope"), projectId, name: normalized, category, createdAt: nowIso(), updatedAt: nowIso() };
      state.scopes.push(row);
    }
    return row;
  }

  function handleKeyboardShortcuts(event) {
    const target = event.target;
    const isTyping = target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "b") {
      event.preventDefault();
      toggleSheetNavigator();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === ".") {
      event.preventDefault();
      toggleRightInspector();
      return;
    }
    if (isTyping || statefulUi.route !== "drawing-viewer") return;
    const key = event.key.toLowerCase();
    if (key === "v") setDrawingMode("view");
    if (key === "m") setDrawingMode("measure");
    if (key === "a") {
      setDrawingMode("measure");
      statefulUi.selectedMeasurementTool = "area";
      render();
    }
    if (key === "l") {
      setDrawingMode("measure");
      statefulUi.selectedMeasurementTool = "line";
      render();
    }
    if (key === "c") {
      setDrawingMode("measure");
      statefulUi.selectedMeasurementTool = "count";
      render();
    }
    if (key === "r") {
      setDrawingMode("markup-rfi");
      statefulUi.selectedMeasurementTool = "rfi";
      render();
    }
    if (key === "/" || key === "s") {
      event.preventDefault();
      document.querySelector("[data-role='drawing-search']")?.focus();
    }
    if (key === "escape") {
      statefulUi.selectedMeasurementTool = "";
      statefulUi.selectedMeasurementId = null;
      statefulUi.selectedIssueId = null;
      statefulUi.selectedRfiId = null;
      render();
    }
  }

  function readPreference(key, fallback) {
    try {
      const value = localStorage.getItem(`takeoff.${key}`);
      if (value == null) return fallback;
      if (value === "true") return true;
      if (value === "false") return false;
      return value;
    } catch (_error) {
      return fallback;
    }
  }

  function writePreference(key, value) {
    try {
      localStorage.setItem(`takeoff.${key}`, String(value));
    } catch (_error) {
      // Local storage may be unavailable in restricted embedded browser modes.
    }
  }

  function readJsonPreference(key, fallback) {
    try {
      const value = localStorage.getItem(`takeoff.${key}`);
      return value ? { ...fallback, ...JSON.parse(value) } : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function writeJsonPreference(key, value) {
    try {
      localStorage.setItem(`takeoff.${key}`, JSON.stringify(value));
    } catch (_error) {
      // Local storage may be unavailable in restricted embedded browser modes.
    }
  }

  function getActiveProject() {
    return state.projects.find((item) => item.id === state.settings.activeProjectId) || null;
  }

  function projectStatus(project) {
    if (!project) return "";
    return project.reviewStatus === "ready" ? "Ready" : project.reviewStatus === "in_review" ? "Estimator review" : "Draft";
  }

  function linkedRecordSummary(projectId, item) {
    const parts = [];
    if (item.drawingId) parts.push(entityName(state.drawings, item.drawingId));
    if (item.roomId) parts.push(entityName(state.rooms, item.roomId));
    if (item.scopeId) parts.push(entityName(state.scopes, item.scopeId));
    if (item.estimateItemId) parts.push(entityName(state.estimateLineItems, item.estimateItemId, "description"));
    return escapeHtml(parts.filter(Boolean).join(" · ") || "No linked records");
  }

  function memorySummary(item, type) {
    if (type === "material") {
      return `${titleCase(item.scopeCategory || "")}${item.unit ? ` · ${item.unit}` : ""} · Unit ${formatCurrency(item.unitCost || 0)} · Labor ${formatCurrency(item.laborCost || 0)} · Material ${formatCurrency(item.materialCost || 0)}`;
    }
    return item.value || [item.scopeCategory, item.unit, item.unitCost, item.laborCost, item.materialCost].filter((value) => value !== "" && value != null).join(" · ") || "Saved memory entry";
  }

  function effectiveConfidence(item) {
    return item.overrideConfidence != null ? item.overrideConfidence : item.confidence;
  }

  function roomName(id) {
    return entityName(state.rooms, id);
  }

  function entityName(rows, id, field = "name") {
    return rows.find((item) => item.id === id)?.[field] || "";
  }

  function findById(rows, id) {
    return rows.find((item) => item.id === id);
  }

  function inferMimeType(name) {
    const lower = name.toLowerCase();
    if (lower.endsWith(".pdf")) return "application/pdf";
    if (/\.(png|jpg|jpeg|gif|webp|tif|tiff)$/.test(lower)) return "image/*";
    return "application/octet-stream";
  }

  function isPdf(item) {
    return item.mimeType === "application/pdf" || item.extension === "pdf";
  }

  function isImage(item) {
    return (item.mimeType || "").startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "tif", "tiff"].includes(item.extension);
  }

  function numberValue(value) {
    return Number(value || 0);
  }

  function optionalNumber(value) {
    return cleanText(value) === "" ? null : Number(value);
  }

  function clampConfidence(value) {
    return Math.max(0, Math.min(100, Number(value || 0)));
  }

  function scopeCategoryOptions() {
    return [
      { value: "drywall", label: "Drywall" },
      { value: "paint", label: "Paint" },
      { value: "ceilings", label: "Ceilings" },
      { value: "carpentry", label: "Carpentry" },
    ];
  }

  function notify(message) {
    pushToast(message);
    render();
  }

  function pushToast(message) {
    statefulUi.toasts.push({ id: createId("toast"), message });
    window.setTimeout(() => {
      statefulUi.toasts.shift();
      render();
    }, 3200);
  }

  function downloadText(fileName, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function slugify(value) {
    return cleanText(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function initials(value) {
    return cleanText(value).split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "—";
  }

  function titleCase(value) {
    return cleanText(value).replace(/[-_]/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: state.settings.currency || "USD", maximumFractionDigits: 2 }).format(Number(value || 0));
  }

  function formatNumber(value) {
    if (value == null || value === "") return "—";
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(Number(value || 0));
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let unit = units[0];
    for (let index = 0; size >= 1024 && index < units.length - 1; index += 1) {
      size /= 1024;
      unit = units[index + 1];
    }
    return `${size.toFixed(size >= 10 ? 0 : 1)} ${unit}`;
  }

  function formatDate(value) {
    return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—";
  }

  function formatDateTime(value) {
    return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }
})();
