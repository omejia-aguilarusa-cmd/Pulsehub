const test = require('node:test');
const assert = require('node:assert/strict');
const logic = require('../../src/takeoff_pro/ui/assets/workspace_logic.js');

test('workspace starts empty and exposes all routes', () => {
  const state = logic.createEmptyState();
  assert.deepEqual(state.projects, []);
  assert.deepEqual(state.drawings, []);
  assert.equal(state.settings.activeProjectId, null);
  assert.deepEqual(logic.ROUTES, [
    'dashboard',
    'documents',
    'drawing-viewer',
    'takeoff',
    'scope-detection',
    'questions-rfis',
    'estimate',
    'risk-confidence',
    'output-center',
    'company-memory',
    'past-projects',
    'settings',
  ]);
});

test('project creation validates names and stores active project', () => {
  const state = logic.createEmptyState();
  assert.throws(() => logic.createProject(state, { name: '   ' }), /required/);
  const project = logic.createProject(state, { name: 'Clinic Fit-Out' });
  assert.equal(state.projects.length, 1);
  assert.equal(state.settings.activeProjectId, project.id);
  assert.equal(project.name, 'Clinic Fit-Out');
});

test('takeoff filters and summary use real rows', () => {
  const rows = [
    { id: '1', roomId: 'r1', floorId: 'f1', buildingId: 'b1', scopeId: 's1', scopeCategory: 'drywall', quantity: 10, wallSf: 100, ceilingSf: 0, paintSf: 0, confidence: 90 },
    { id: '2', roomId: 'r2', floorId: 'f1', buildingId: 'b1', scopeId: 's2', scopeCategory: 'paint', quantity: 5, wallSf: 0, ceilingSf: 0, paintSf: 200, confidence: 60 },
  ];
  const filtered = logic.applyTakeoffFilters(rows, { roomId: '', floorId: 'f1', buildingId: '', scopeId: '', scopeCategory: 'paint', query: '' });
  assert.deepEqual(filtered.map((row) => row.id), ['2']);
  assert.deepEqual(logic.calculateTakeoffSummary(rows), {
    rowCount: 2,
    quantity: 15,
    wallSf: 100,
    ceilingSf: 0,
    paintSf: 200,
    averageConfidence: 75,
    lowConfidenceCount: 1,
  });
});

test('estimate totals and CSV export are calculated from stored data', () => {
  const state = logic.createEmptyState();
  const project = logic.createProject(state, { name: 'Export Test' });
  state.takeoffMeasurements.push({
    id: 'takeoff-1', projectId: project.id, name: 'Wall area', quantity: 100, unit: 'SF', confidence: 95,
  });
  state.estimateLineItems.push({
    id: 'estimate-1', projectId: project.id, description: 'Drywall', quantity: 100, unit: 'SF', unitCost: 1, laborCost: 2, materialCost: 3, markupPercent: 10, taxPercent: 5, confidence: 95,
  });
  const totals = logic.calculateEstimateLine(state.estimateLineItems[0]);
  assert.equal(totals.directCost, 600);
  assert.equal(totals.markupAmount, 60);
  assert.equal(totals.taxAmount, 33);
  assert.equal(totals.total, 693);
  const csv = logic.buildProjectCsv(state, project.id);
  assert.match(csv, /takeoff/);
  assert.match(csv, /estimate/);
  assert.match(csv, /693/);
});

test('painting formulas deduct openings and calculate trim', () => {
  const quantities = logic.calculatePaintingQuantities({
    floorAreaSf: 500,
    perimeterFt: 100,
    ceilingHeightFt: 9,
    doorCount: 2,
    windowCount: 3,
    includeDoors: true,
    includeWindows: true,
    includeTrim: true,
  });

  assert.equal(quantities.wallSf, 813);
  assert.equal(quantities.ceilingSf, 500);
  assert.equal(quantities.trimLf, 170);
});

test('CSV export includes AI painting takeoff rooms', () => {
  const state = logic.createEmptyState();
  const project = logic.createProject(state, { name: 'AI Export Test' });
  state.aiTakeoffRuns.push({
    id: 'run-1',
    projectId: project.id,
    status: 'complete',
    confidenceScore: 82,
    totals: { floorAreaSf: 100, wallSf: 320, ceilingSf: 100, doorCount: 1, windowCount: 2, trimLf: 141 },
    pages: [{
      pageId: 'drawing-1',
      rooms: [{
        id: 'room-1',
        name: 'Office 101',
        pageId: 'drawing-1',
        wallSf: 320,
        ceilingSf: 100,
        doorCount: 1,
        windowCount: 2,
        trimLf: 141,
        confidence: 82,
      }],
    }],
  });

  const csv = logic.buildProjectCsv(state, project.id);
  assert.match(csv, /ai_takeoff_summary/);
  assert.match(csv, /ai_takeoff_room/);
  assert.match(csv, /Office 101/);
});

test('project search includes related takeoff names', () => {
  const state = logic.createEmptyState();
  const project = logic.createProject(state, { name: 'Search Test' });
  state.rooms.push({ id: 'room-1', projectId: project.id, name: 'Main Lobby' });
  state.scopes.push({ id: 'scope-1', projectId: project.id, name: 'Stud Framing' });
  state.takeoffMeasurements.push({
    id: 'takeoff-1',
    projectId: project.id,
    name: 'Wall measurement',
    roomId: 'room-1',
    scopeId: 'scope-1',
    quantity: 100,
    unit: 'SF',
  });

  assert.deepEqual(
    logic.searchProject(state, project.id, 'lobby').map((row) => row.type),
    ['room', 'takeoff'],
  );
  assert.deepEqual(
    logic.searchProject(state, project.id, 'framing').map((row) => row.type),
    ['scope', 'takeoff'],
  );
});
