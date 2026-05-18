(function bootstrapWorkspace() {
  "use strict";

  const {
    ROUTES,
    addActivity,
    averageConfidence,
    buildProjectCsv,
    buildProjectJson,
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
      <div class="app-shell">
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
      <aside class="sidebar ${statefulUi.sidebarOpen ? "open" : ""}" aria-label="Primary navigation">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true">▲</div>
          <div class="brand-copy"><strong>Takeoff</strong><span>Estimating Workspace</span></div>
        </div>
        <div class="sidebar-scroll">
          <button class="sidebar-action" data-action="open-project-modal" aria-label="Create new project"><span class="nav-icon">＋</span><span class="nav-text">New project</span></button>
          <section class="sidebar-section">
            <p class="sidebar-label">Project</p>
            <p class="sidebar-project">${escapeHtml(projectLabel)}</p>
            <nav class="nav-list" aria-label="Workspace pages">
              ${renderNavLink("dashboard", "▦", "Dashboard")}
              ${renderNavLink("documents", "▤", "Documents")}
              ${renderNavLink("drawing-viewer", "▧", "Drawing viewer")}
              ${renderNavLink("takeoff", "▦", "Takeoff")}
              ${renderNavLink("scope-detection", "☑", "Scope detection")}
              ${renderNavLink("questions-rfis", "?", "Questions / RFIs", unresolvedRfis)}
              ${renderNavLink("estimate", "▤", "Estimate")}
              ${renderNavLink("risk-confidence", "△", "Risk & confidence")}
              ${renderNavLink("output-center", "⇧", "Output center")}
            </nav>
          </section>
          <section class="sidebar-section">
            <p class="sidebar-label">Company</p>
            <nav class="nav-list" aria-label="Company pages">
              ${renderNavLink("company-memory", "◔", "Company memory")}
              ${renderNavLink("past-projects", "▱", "Past projects")}
              ${renderNavLink("settings", "⚙", "Settings")}
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

  function renderNavLink(route, icon, label, badge) {
    const active = statefulUi.route === route ? "active" : "";
    return `<a href="#/${route}" class="nav-link ${active}" data-route="${route}"><span class="nav-icon" aria-hidden="true">${icon}</span><span class="nav-text">${label}</span>${badge ? `<span class="nav-badge">${badge}</span>` : ""}</a>`;
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
      case "drawing-viewer": return renderDrawingViewer(project);
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

  function renderTakeoff(project) {
    const rows = enrichTakeoffRows(project.id);
    const filtered = applyTakeoffFilters(rows, statefulUi.takeoffFilters);
    const summary = calculateTakeoffSummary(filtered);
    const rooms = filterByProject(state.rooms, project.id);
    const floors = filterByProject(state.floors, project.id);
    const buildings = filterByProject(state.buildings, project.id);
    const scopes = filterByProject(state.scopes, project.id);
    return `
      <div class="page">
        ${renderPageHeader("Takeoff", "Create, edit, filter, and review persisted takeoff measurements.", `<button class="button primary" data-action="open-measurement-modal">New takeoff row</button>`)}
        <div class="card-grid">
          ${metricCard("Rows", summary.rowCount, "Filtered takeoff rows")}
          ${metricCard("Wall SF", formatNumber(summary.wallSf), "Calculated from rows")}
          ${metricCard("Paint SF", formatNumber(summary.paintSf), "Calculated from rows")}
          ${metricCard("Average confidence", summary.averageConfidence == null ? "—" : `${summary.averageConfidence}%`, `${summary.lowConfidenceCount} low-confidence item${summary.lowConfidenceCount === 1 ? "" : "s"}`)}
        </div>
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
      case "export": return renderExportModal(project);
      default: return "";
    }
  }

  function modalShell(title, body, submitLabel, formName) {
    return `<div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="${escapeAttribute(title)}"><form class="modal" data-form="${formName}"><div class="modal-header"><h2>${title}</h2><button class="button ghost" type="button" data-action="close-modal" aria-label="Close dialog">✕</button></div><div class="modal-body">${body}</div><div class="modal-footer"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">${submitLabel}</button></div></form></div>`;
  }

  function renderProjectForm() {
    return `<div class="form-grid">${field("Project name", "name", "", "text", true)}${field("Client", "client", "")}${field("Address", "address", "")}${field("Project type", "projectType", "")}${selectField("Units", "units", state.settings.units, [{ value: "imperial", label: "Imperial" }, { value: "metric", label: "Metric" }])}${field("Description", "description", "", "text", false, true)}</div>`;
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
    if (shouldRender) render();
  }

  function handleInput(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.dataset.role === "project-search") {
      statefulUi.searchQuery = target.value;
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
    if (!name) return pushToast("Document name is required.");
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
    for (const key of ["drawings", "rooms", "floors", "buildings", "scopes", "scopeDetections", "takeoffMeasurements", "estimateLineItems", "rfis", "riskItems", "exports", "activities"]) {
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
    for (const row of filterByProject(state.estimateLineItems, projectId)) {
      row.sourceMeasurementId = remapImported(maps.takeoffMeasurements, row.sourceMeasurementId);
      row.scopeId = remapImported(maps.scopes, row.scopeId);
    }
    for (const row of filterByProject(state.rfis, projectId)) {
      row.drawingId = remapImported(maps.drawings, row.drawingId);
      row.roomId = remapImported(maps.rooms, row.roomId);
      row.scopeId = remapImported(maps.scopes, row.scopeId);
      row.estimateItemId = remapImported(maps.estimateLineItems, row.estimateItemId);
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
      takeoff: "takeoff",
      estimate: "estimate",
      rfi: "questions-rfis",
    };
    statefulUi.searchQuery = "";
    if (type === "drawing") selectDrawing(id);
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
