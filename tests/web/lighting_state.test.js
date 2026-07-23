"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ROUTES,
  STAGES,
  applyCompatibility,
  createPaintStrokeController,
  createLightingState,
  formatLightingHash,
  nextGridIndex,
  parseLightingHash,
  projectLightingJob,
  reduceLightingState,
  routeAvailability,
} = require("../../am_configurator/web/lighting_state.js");

const JOB_ID = "4d36e96e-e2aa-4e72-8808-4d03b5ba7e61";
const RESULT_ID = "result-asset";

class FakeEventTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type) {
    for (const listener of [...(this.listeners.get(type) || [])]) listener();
  }
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

function readyJob(overrides = {}) {
  return {
    id: JOB_ID,
    status: "ready",
    phase: "ready_for_review",
    progress: {completed: 200, total: 200},
    resultAssetId: RESULT_ID,
    previewAssetId: "preview-asset",
    recipeAssetId: "recipe-asset",
    target: {
      family: "80",
      productId: "AM21",
      targets: ["keyframes", "spotlight_frames"],
      frameCap: 200,
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

test("defaults to the manual Lighting workspace at the prompt stage", () => {
  assert.deepEqual(createLightingState(), {
    route: ROUTES.EDIT,
    create: {stage: STAGES.PROMPT},
    activeJob: null,
  });
});

test("grid focus movement is bounded and supports arrows plus Home and End", () => {
  assert.equal(nextGridIndex(5, "ArrowLeft", 12, 4), 4);
  assert.equal(nextGridIndex(5, "ArrowRight", 12, 4), 6);
  assert.equal(nextGridIndex(5, "ArrowUp", 12, 4), 1);
  assert.equal(nextGridIndex(5, "ArrowDown", 12, 4), 9);
  assert.equal(nextGridIndex(0, "ArrowLeft", 12, 4), 0);
  assert.equal(nextGridIndex(11, "ArrowDown", 12, 4), 11);
  assert.equal(nextGridIndex(7, "Home", 12, 4), 0);
  assert.equal(nextGridIndex(2, "End", 12, 4), 11);
});

test("three paint strokes create three checkpoints and entry alone never paints", () => {
  const releaseTarget = new FakeEventTarget();
  const checkpoints = [];
  const painted = [];
  const controller = createPaintStrokeController({
    releaseTarget,
    checkpoint: () => checkpoints.push("checkpoint"),
    paint: pixel => painted.push(pixel),
  });

  assert.equal(controller.pointerEnter("outside", 1), false);
  for (let stroke = 0; stroke < 3; stroke += 1) {
    assert.equal(controller.pointerDown(`start-${stroke}`), true);
    assert.equal(controller.pointerEnter(`drag-${stroke}`, 1), true);
    releaseTarget.dispatch("pointerup");
  }

  assert.equal(checkpoints.length, 3);
  assert.deepEqual(painted, [
    "start-0", "drag-0",
    "start-1", "drag-1",
    "start-2", "drag-2",
  ]);
  assert.equal(controller.pointerEnter("after-release", 1), false);
  assert.equal(releaseTarget.listeners.get("pointerup")?.size || 0, 0);
  assert.equal(releaseTarget.listeners.get("pointercancel")?.size || 0, 0);
});

test("reducer never mutates frozen input", () => {
  const state = deepFreeze(reduceLightingState(createLightingState(), {type: "JOB_SYNCED", job: readyJob()}).state);
  for (const event of [
    {type: "NAVIGATE", route: ROUTES.LIBRARY},
    {type: "SHOW_PROMPT"},
    {type: "SHOW_REVIEW"},
    {type: "JOB_SYNCED", job: readyJob()},
    {type: "APPLY_REQUESTED"},
  ]) assert.doesNotThrow(() => reduceLightingState(state, event, {
    document: compatibleDocument(),
    destination: {slot: 5, target: "keyframes"},
  }));
});

test("durable job synchronization owns prompt, progress, and review stages", () => {
  const initial=createLightingState();
  const working=reduceLightingState(initial,{type:"JOB_SYNCED",job:readyJob({status:"in_progress",phase:"recipe_generating",resultAssetId:null})}).state;
  assert.equal(working.create.stage,STAGES.PROGRESS);
  assert.equal(working.activeJob.previewAssetId,"preview-asset");
  const ready=reduceLightingState(working,{type:"JOB_SYNCED",job:readyJob()}).state;
  assert.equal(ready.create.stage,STAGES.REVIEW);
  const cleared=reduceLightingState(ready,{type:"JOB_SYNCED",job:null}).state;
  assert.deepEqual(cleared.create,{stage:STAGES.PROMPT});
  assert.equal(cleared.activeJob,null);
});

test("Review cannot be opened before a mapped result exists", () => {
  const initial=createLightingState();
  const blocked=reduceLightingState(initial,{type:"SHOW_REVIEW"});
  assert.equal(blocked.blocked,"result-not-ready");
  assert.strictEqual(blocked.state,initial);
});

test("job projection uses only the latest procedural attempt", () => {
  const manifest={
    job_id:JOB_ID,status:"in_progress",phase:"recipe_generating",progress:null,target:readyJob().target,
    procedural_attempts:[
      {mapped_result_asset_id:"old",preview_asset_id:"old-preview",recipe_asset_id:"old-recipe"},
      {mapped_result_asset_id:null,preview_asset_id:null,recipe_asset_id:"new-recipe"},
    ],
  };
  assert.deepEqual(projectLightingJob(manifest),{
    id:JOB_ID,status:"in_progress",phase:"recipe_generating",progress:null,
    resultAssetId:null,previewAssetId:null,recipeAssetId:"new-recipe",target:readyJob().target,
  });
  manifest.procedural_attempts[1].mapped_result_asset_id="new-result";
  assert.equal(projectLightingJob(manifest).resultAssetId,"new-result");
});

test("hash routing round-trips safe routes and opaque job IDs", () => {
  for (const route of Object.values(ROUTES)) {
    assert.deepEqual(parseLightingHash(formatLightingHash(route, JOB_ID)), {route, jobId: JOB_ID});
  }
  assert.deepEqual(parseLightingHash("#/not-a-route?job=prompt-text"), {route: ROUTES.EDIT, jobId: null});
  assert.deepEqual(parseLightingHash("#/lighting/library?job=../../manifest.json"), {route: ROUTES.LIBRARY, jobId: null});
});

test("Library and Settings remain available while Create requires a ready gate", () => {
  const document=compatibleDocument();
  assert.deepEqual(routeAvailability(ROUTES.LIBRARY,null),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.SETTINGS,null),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.CREATE,document),{available:false,reason:"ai-not-ready"});
  assert.deepEqual(routeAvailability(ROUTES.CREATE,document,{aiReady:true}),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.CREATE,document,{hasActiveJob:true}),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.EDIT,null),{available:false,reason:"document-required"});
});

test("Apply compatibility fails closed with a specific reason", () => {
  const job=readyJob(),destination={slot:5,target:"keyframes"};
  const cases=[
    [null,job,destination,"document-required"],
    [compatibleDocument(),readyJob({resultAssetId:null}),destination,"result-not-ready"],
    [compatibleDocument({family:"ALICE",productId:"ALICE"}),job,destination,"family-mismatch"],
    [compatibleDocument({slots:[6,7]}),job,destination,"slot-unavailable"],
    [compatibleDocument(),job,{slot:5,target:"frames"},"target-mismatch"],
    [compatibleDocument({supportedTargets:["keyframes"]}),job,destination,"target-unsupported"],
  ];
  for(const [document,candidateJob,candidateDestination,reason] of cases){
    assert.deepEqual(applyCompatibility(candidateJob,document,candidateDestination),{compatible:false,reason});
  }
  assert.deepEqual(applyCompatibility(job,compatibleDocument(),destination),{compatible:true,reason:null});
});

test("known product variants share their intended compatibility families", () => {
  const destination={slot:5,target:"keyframes"};
  assert.equal(applyCompatibility(readyJob(),compatibleDocument({family:"AM21",productId:"AM21"}),destination).compatible,true);
  const cyberJob=readyJob({target:{...readyJob().target,family:"CB01",productId:"CB01",targets:["frames"]}});
  const cyberDocument=compatibleDocument({family:"CB",productId:"CB03",supportedTargets:["frames"]});
  assert.equal(applyCompatibility(cyberJob,cyberDocument,{slot:5,target:"frames"}).compatible,true);
});

test("only compatible Apply emits a document mutation intent", () => {
  const ready=reduceLightingState(createLightingState(),{type:"JOB_SYNCED",job:readyJob()}).state;
  const context={document:compatibleDocument(),destination:{slot:5,target:"keyframes"}};
  for(const event of [{type:"NAVIGATE",route:ROUTES.LIBRARY},{type:"SHOW_PROMPT"},{type:"SHOW_REVIEW"},{type:"JOB_SYNCED",job:readyJob()},{type:"UNKNOWN"}]){
    assert.equal(reduceLightingState(ready,event,context).intent,null,event.type);
  }
  const apply=reduceLightingState(ready,{type:"APPLY_REQUESTED"},context);
  assert.deepEqual(apply.intent,{type:"apply-lighting-result",jobId:JOB_ID,assetId:RESULT_ID,destination:{slot:5,target:"keyframes"}});
  const blocked=reduceLightingState(ready,{type:"APPLY_REQUESTED"},{...context,document:compatibleDocument({slots:[6,7]})});
  assert.equal(blocked.blocked,"slot-unavailable");
  assert.equal(blocked.intent,null);
});
