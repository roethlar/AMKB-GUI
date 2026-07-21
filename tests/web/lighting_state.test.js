"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ROUTES,
  STAGES,
  applyCompatibility,
  createLightingState,
  formatLightingHash,
  parseLightingHash,
  projectLightingJob,
  reduceLightingState,
  routeAvailability,
} = require("../../am_configurator/web/lighting_state.js");

const JOB_ID = "4d36e96e-e2aa-4e72-8808-4d03b5ba7e61";
const RESULT_ID = "result-asset";

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

function selectedState() {
  return reduceLightingState(createLightingState(), {
    type: "SELECT_CANDIDATE",
    candidateId: "candidate-a",
  }).state;
}

function readyJob(overrides = {}) {
  return {
    id: JOB_ID,
    status: "ready",
    phase: "ready",
    progress: {completed: 32, total: 32},
    selectedCandidateId: "candidate-a",
    resultAssetId: RESULT_ID,
    target: {
      family: "80",
      productId: "AM21",
      targets: ["keyframes", "spotlight_frames"],
      frameCap: 32,
    },
    ...overrides,
  };
}

function compatibleDocument(overrides = {}) {
  return {
    family: "80",
    productId: "80",
    slots: [5, 6, 7],
    supportedTargets: ["keyframes", "spotlight_frames"],
    ...overrides,
  };
}

test("defaults to Lighting Create at the Concepts stage", () => {
  assert.deepEqual(createLightingState(), {
    route: ROUTES.CREATE,
    create: {stage: STAGES.CONCEPTS, selectedCandidateId: null},
    activeJob: null,
  });
});

test("reducer never mutates frozen input", () => {
  const state = deepFreeze(selectedState());
  const events = [
    {type: "NAVIGATE", route: ROUTES.LIBRARY},
    {type: "SELECT_CANDIDATE", candidateId: "candidate-b"},
    {type: "SHOW_CONCEPTS"},
    {type: "SHOW_ANIMATE"},
    {type: "JOB_SYNCED", job: readyJob()},
    {type: "SHOW_REVIEW"},
    {type: "APPLY_REQUESTED"},
  ];
  for (const event of events) {
    assert.doesNotThrow(() => reduceLightingState(state, event, {
      document: compatibleDocument(),
      destination: {slot: 5, target: "keyframes"},
    }));
  }
});

test("selecting a candidate changes only selection and emits no intent", () => {
  const before = createLightingState();
  const result = reduceLightingState(before, {
    type: "SELECT_CANDIDATE",
    candidateId: "candidate-a",
  });
  assert.deepEqual(result.state, {
    ...before,
    create: {...before.create, selectedCandidateId: "candidate-a"},
  });
  assert.equal(result.state.create.stage, STAGES.CONCEPTS);
  assert.equal(result.intent, null);
  assert.equal(result.blocked, null);
});

test("Animate requires an explicit selection and Review requires a result", () => {
  const initial = createLightingState();
  const blockedAnimate = reduceLightingState(initial, {type: "SHOW_ANIMATE"});
  assert.equal(blockedAnimate.blocked, "selection-required");
  assert.strictEqual(blockedAnimate.state, initial);

  const selected = selectedState();
  const animate = reduceLightingState(selected, {type: "SHOW_ANIMATE"});
  assert.equal(animate.state.create.stage, STAGES.ANIMATE);
  assert.equal(animate.intent, null);

  const blockedReview = reduceLightingState(animate.state, {type: "SHOW_REVIEW"});
  assert.equal(blockedReview.blocked, "result-not-ready");
  assert.strictEqual(blockedReview.state, animate.state);

  const synced = reduceLightingState(animate.state, {type: "JOB_SYNCED", job: readyJob()});
  assert.equal(synced.state.create.stage, STAGES.REVIEW);
  assert.equal(synced.state.create.selectedCandidateId, "candidate-a");
});

test("backward stage changes and route navigation preserve job and selection", () => {
  let current = reduceLightingState(selectedState(), {
    type: "JOB_SYNCED",
    job: readyJob(),
  }).state;
  current = reduceLightingState(current, {type: "SHOW_CONCEPTS"}).state;
  assert.equal(current.create.stage, STAGES.CONCEPTS);
  assert.equal(current.create.selectedCandidateId, "candidate-a");

  for (const route of [ROUTES.LIBRARY, ROUTES.SETTINGS, ROUTES.EDIT, ROUTES.CREATE]) {
    current = reduceLightingState(current, {type: "NAVIGATE", route}).state;
  }
  assert.equal(current.route, ROUTES.CREATE);
  assert.equal(current.create.stage, STAGES.CONCEPTS);
  assert.equal(current.create.selectedCandidateId, "candidate-a");
  assert.equal(current.activeJob.id, JOB_ID);
});

test("switching or clearing jobs cannot inherit another job's candidate", () => {
  const first = reduceLightingState(createLightingState(), {
    type: "JOB_SYNCED",
    job: readyJob(),
  }).state;
  const secondJob = readyJob({
    id: "6b7e48f2-9b4b-4fb5-a20e-14e9a0d7d2bd",
    selectedCandidateId: null,
    resultAssetId: null,
    status: "awaiting_selection",
    phase: "awaiting_selection",
  });
  const switched = reduceLightingState(first, {type: "JOB_SYNCED", job: secondJob}).state;
  assert.equal(switched.create.selectedCandidateId, null);
  assert.equal(switched.create.stage, STAGES.CONCEPTS);
  assert.equal(reduceLightingState(switched, {type: "SHOW_ANIMATE"}).blocked, "selection-required");

  const cleared = reduceLightingState(first, {type: "JOB_SYNCED", job: null}).state;
  assert.equal(cleared.activeJob, null);
  assert.deepEqual(cleared.create, {stage: STAGES.CONCEPTS, selectedCandidateId: null});
});

test("job projection never exposes a prior animation attempt's result", () => {
  const manifest = {
    job_id: JOB_ID,
    status: "in_progress",
    phase: "video_polling",
    progress: null,
    selected_candidate_id: "candidate-b",
    target: readyJob().target,
    animation_attempts: [
      {mapped_result_asset_id: "old-result"},
      {mapped_result_asset_id: null},
    ],
  };
  assert.equal(projectLightingJob(manifest).resultAssetId, null);
  manifest.animation_attempts[1].mapped_result_asset_id = "new-result";
  assert.equal(projectLightingJob(manifest).resultAssetId, "new-result");
});

test("a new animation attempt on the same job leaves Review for Animate", () => {
  const reviewed = reduceLightingState(createLightingState(), {
    type: "JOB_SYNCED",
    job: readyJob(),
  }).state;
  const restarted = reduceLightingState(reviewed, {
    type: "JOB_SYNCED",
    job: readyJob({
      status: "in_progress",
      phase: "video_planning",
      resultAssetId: null,
      progress: null,
    }),
  }).state;
  assert.equal(restarted.create.stage, STAGES.ANIMATE);
  assert.equal(restarted.activeJob.resultAssetId, null);
});

test("hash routing round-trips safe routes and opaque job IDs", () => {
  for (const route of Object.values(ROUTES)) {
    assert.deepEqual(parseLightingHash(formatLightingHash(route, JOB_ID)), {route, jobId: JOB_ID});
  }
  assert.deepEqual(parseLightingHash("#/not-a-route?job=prompt-text"), {
    route: ROUTES.CREATE,
    jobId: null,
  });
  assert.deepEqual(parseLightingHash("#/lighting/library?job=../../manifest.json"), {
    route: ROUTES.LIBRARY,
    jobId: null,
  });
});

test("Library and Settings remain available without a document", () => {
  assert.deepEqual(routeAvailability(ROUTES.LIBRARY, null), {available: true, reason: null});
  assert.deepEqual(routeAvailability(ROUTES.SETTINGS, null), {available: true, reason: null});
  assert.deepEqual(routeAvailability(ROUTES.CREATE, null), {available: false, reason: "document-required"});
  assert.deepEqual(routeAvailability(ROUTES.EDIT, null), {available: false, reason: "document-required"});
  assert.deepEqual(routeAvailability(ROUTES.KEYMAP, null), {available: false, reason: "document-required"});
});

test("Apply compatibility fails closed with a specific reason", () => {
  const job = readyJob();
  const destination = {slot: 5, target: "keyframes"};
  const cases = [
    [null, job, destination, "document-required"],
    [compatibleDocument(), readyJob({resultAssetId: null}), destination, "result-not-ready"],
    [compatibleDocument({family: "ALICE", productId: "ALICE"}), job, destination, "family-mismatch"],
    [compatibleDocument({slots: [6, 7]}), job, destination, "slot-unavailable"],
    [compatibleDocument(), job, {slot: 5, target: "frames"}, "target-mismatch"],
    [compatibleDocument({supportedTargets: ["keyframes"]}), job, destination, "target-unsupported"],
  ];
  for (const [document, candidateJob, candidateDestination, reason] of cases) {
    assert.deepEqual(applyCompatibility(candidateJob, document, candidateDestination), {
      compatible: false,
      reason,
    });
  }
  assert.deepEqual(applyCompatibility(job, compatibleDocument(), destination), {
    compatible: true,
    reason: null,
  });
});

test("known product variants share their intended compatibility families", () => {
  const destination = {slot: 5, target: "keyframes"};
  assert.equal(applyCompatibility(readyJob(), compatibleDocument({family: "AM21", productId: "AM21"}), destination).compatible, true);
  const cyberJob = readyJob({target: {...readyJob().target, family: "CB01", productId: "CB01"}});
  const cyberDocument = compatibleDocument({family: "CB", productId: "CB03"});
  assert.equal(applyCompatibility(cyberJob, cyberDocument, destination).compatible, true);
});

test("only a compatible APPLY_REQUESTED emits a document mutation intent", () => {
  const ready = reduceLightingState(createLightingState(), {type: "JOB_SYNCED", job: readyJob()}).state;
  const context = {
    document: compatibleDocument(),
    destination: {slot: 5, target: "keyframes"},
  };
  const nonApplyEvents = [
    {type: "NAVIGATE", route: ROUTES.LIBRARY},
    {type: "SELECT_CANDIDATE", candidateId: "candidate-b"},
    {type: "SHOW_CONCEPTS"},
    {type: "SHOW_ANIMATE"},
    {type: "SHOW_REVIEW"},
    {type: "JOB_SYNCED", job: readyJob()},
    {type: "UNKNOWN"},
  ];
  for (const event of nonApplyEvents) {
    assert.equal(reduceLightingState(ready, event, context).intent, null, event.type);
  }

  const apply = reduceLightingState(ready, {type: "APPLY_REQUESTED"}, context);
  assert.deepEqual(apply.intent, {
    type: "apply-lighting-result",
    jobId: JOB_ID,
    assetId: RESULT_ID,
    destination: {slot: 5, target: "keyframes"},
  });
  assert.strictEqual(apply.state, ready);

  const incompatible = reduceLightingState(ready, {type: "APPLY_REQUESTED"}, {
    ...context,
    document: compatibleDocument({slots: [6, 7]}),
  });
  assert.equal(incompatible.intent, null);
  assert.equal(incompatible.blocked, "slot-unavailable");
  assert.strictEqual(incompatible.state, ready);
});
