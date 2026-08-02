"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ROUTES,
  STAGES,
  aiStudioAvailable,
  applyCompatibility,
  classifyImportedJsonSelection,
  escapeMarkup,
  createEpochLoadRegistry,
  createLaunchState,
  createPaintStrokeController,
  createLightingState,
  formatLightingHash,
  importedLightingApplyAvailability,
  ollamaEndpointDataFlow,
  ollamaModelRefreshFailed,
  nextGridIndex,
  normalizeOllamaModels,
  parseLightingHash,
  projectLightingJob,
  projectApiProviderPicker,
  projectOllamaModelPicker,
  reduceLightingState,
  routeAvailability,
  safeRgbColor,
} = require("../../am_configurator/web/lighting_state.js");

const JOB_ID = "4d36e96e-e2aa-4e72-8808-4d03b5ba7e61";
const RESULT_ID = "result-asset";

test("hostile assignment markup is escaped into inert attribute text", () => {
  const hostile = '#00951500"><img src=x onerror="steal()">';
  const escaped = escapeMarkup(hostile);

  assert.equal(
    escaped,
    "#00951500&quot;&gt;&lt;img src=x onerror=&quot;steal()&quot;&gt;",
  );
  assert.doesNotMatch(escaped, /<img|onerror="/);
});

test("CSS declarations and remote URLs cannot enter lighting markup", () => {
  const hostile = [
    "#112233;background:url(https://attacker.invalid/pixel)",
    "url(https://attacker.invalid/pixel)",
  ];
  for (const value of hostile) {
    const markup = `<i style="background:${safeRgbColor(value)}"></i>`;
    assert.equal(markup, '<i style="background:#000000"></i>');
    assert.doesNotMatch(markup, /https|url\(|;/);
  }
});

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

test("Ollama endpoint data flow is classified without DNS or network access", () => {
  assert.deepEqual(
    ollamaEndpointDataFlow("http://127.0.0.1:11434","ollama_server"),
    {disclosureRequired:false,insecureRemote:false,loopback:true},
  );
  assert.deepEqual(
    ollamaEndpointDataFlow("http://ollama.lan:11434","ollama_server"),
    {disclosureRequired:true,insecureRemote:true,loopback:false},
  );
  assert.deepEqual(
    ollamaEndpointDataFlow("https://ollama.lan","ollama_cloud"),
    {disclosureRequired:true,insecureRemote:false,loopback:false},
  );
  assert.equal(
    ollamaEndpointDataFlow("http://localhost:11434","ollama_cloud").disclosureRequired,
    true,
  );
});

test("epoch load ownership lets refresh supersede an in-flight asset safely", () => {
  const registry=createEpochLoadRegistry();
  const oldLoad=registry.begin("job:asset",1);
  assert.ok(oldLoad);
  assert.equal(registry.begin("job:asset",1),null);
  const refreshedLoad=registry.begin("job:asset",2);
  assert.ok(refreshedLoad);
  assert.equal(oldLoad.current(2),false);
  assert.equal(refreshedLoad.current(2),true);
  oldLoad.release();
  assert.equal(refreshedLoad.current(2),true);
  refreshedLoad.release();
  assert.ok(registry.begin("job:asset",2));
});

const MODEL_A = Object.freeze({
  model_id: "ornith:latest",
  digest: "a".repeat(64),
  size_bytes: 5000000,
  location: "ollama_server",
  parameter_size: "9.0B",
  quantization: "Q4_K_M",
});
const MODEL_B = Object.freeze({
  model_id: "small:latest",
  digest: "b".repeat(64),
  size_bytes: 3000000,
  location: "ollama_cloud",
  parameter_size: "4.0B",
  quantization: "Q4_K_M",
});

test("local model picker distinguishes inventory and selected-model states", () => {
  const available=normalizeOllamaModels({available:true,models:[MODEL_A,MODEL_B,null,{model_id:"bad"}]});
  assert.deepEqual(available.models.map(model=>model.model_id),["ornith:latest","small:latest"]);
  assert.equal(projectOllamaModelPicker(available,{}).inventoryState,"available");
  assert.equal(projectOllamaModelPicker(available,{}).disabled,false);

  const empty=normalizeOllamaModels({available:true,models:[]});
  assert.equal(projectOllamaModelPicker(empty,{}).inventoryState,"empty");
  assert.equal(projectOllamaModelPicker(empty,{}).disabled,true);

  const unavailable=normalizeOllamaModels({available:false,models:[]});
  assert.equal(projectOllamaModelPicker(unavailable,{}).inventoryState,"unavailable");

  assert.deepEqual(
    available.models.map(model=>model.label),
    [
      "ornith:latest — On this Ollama server",
      "small:latest — Ollama Cloud",
    ],
  );

  const selected={
    model_id:MODEL_A.model_id,
    model_digest:MODEL_A.digest,
    model_location:MODEL_A.location,
  };
  assert.equal(projectOllamaModelPicker(available,selected).selectionState,"selected");

  const removed=projectOllamaModelPicker(
    normalizeOllamaModels({available:true,models:[MODEL_B]}),
    {
      model_id:MODEL_A.model_id,
      model_digest:MODEL_A.digest,
      model_location:MODEL_A.location,
    },
  );
  assert.equal(removed.selectionState,"removed");
  assert.equal(removed.value,MODEL_A.model_id);
  assert.deepEqual(removed.options.at(-1),{
    value:MODEL_A.model_id,
    label:"ornith:latest — not currently available",
    disabled:true,
  });

  const changed=projectOllamaModelPicker(
    normalizeOllamaModels({available:true,models:[{...MODEL_A,digest:"c".repeat(64)}]}),
    {
      model_id:MODEL_A.model_id,
      model_digest:MODEL_A.digest,
      model_location:MODEL_A.location,
    },
  );
  assert.equal(changed.selectionState,"digest_changed");
  assert.equal(changed.value,MODEL_A.model_id);

  const upgrade=projectOllamaModelPicker(
    normalizeOllamaModels({available:true,models:[],reason:"upgrade_required"}),
    {},
  );
  assert.equal(upgrade.inventoryState,"upgrade_required");
  assert.match(upgrade.placeholder,/Upgrade Ollama/);
});

test("local model picker preserves a preferred choice after transient refresh failure", () => {
  const available=normalizeOllamaModels({available:true,models:[MODEL_A,MODEL_B]});
  const failed=ollamaModelRefreshFailed(available);
  const picker=projectOllamaModelPicker(
    failed,
    {
      model_id:MODEL_A.model_id,
      model_digest:MODEL_A.digest,
      model_location:MODEL_A.location,
    },
    MODEL_B.model_id,
  );
  assert.equal(picker.inventoryState,"transient_failure");
  assert.equal(picker.selectionState,"transient_failure");
  assert.equal(picker.value,MODEL_B.model_id);
  assert.deepEqual(picker.options.map(option=>option.value),[MODEL_A.model_id,MODEL_B.model_id]);
  assert.equal(picker.disabled,true);
});

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

function apiCatalog() {
  const entries = [
    ["xai", "xAI", "grok-4.5", [["grok-4.5", "Grok 4.5"]]],
    ["anthropic", "Anthropic", "claude-sonnet-5", [
      ["claude-sonnet-5", "Claude Sonnet 5"],
      ["claude-opus-5", "Claude Opus 5"],
    ]],
    ["openai", "OpenAI", "gpt-5.6-sol", [["gpt-5.6-sol", "GPT-5.6 Sol"]]],
    ["gemini", "Gemini", "gemini-3.6-flash", [["gemini-3.6-flash", "Gemini 3.6 Flash"]]],
    ["moonshot", "Kimi / Moonshot", "kimi-k3", [["kimi-k3", "Kimi K3"]]],
    ["deepseek", "DeepSeek", "deepseek-v4-pro", [["deepseek-v4-pro", "DeepSeek V4 Pro"]]],
  ];
  return {
    schema_version: 2,
    providers: Object.fromEntries(entries.map(([id, label, defaultModel, models]) => [
      id,
      {
        label,
        default_model: defaultModel,
        disclosure_version: `disclosure-${id}`,
        models: models.map(([modelId, modelLabel]) => ({id: modelId, label: modelLabel})),
      },
    ])),
  };
}

function apiSettings() {
  return {
    selected_provider: "xai",
    providers: Object.fromEntries(
      Object.keys(apiCatalog().providers).map(provider => [
        provider,
        {model_id: provider === "xai" ? "grok-4.5" : null},
      ]),
    ),
  };
}

test("AI Studio exists only for enabled and currently ready capability", () => {
  assert.equal(aiStudioAvailable(null), false);
  assert.equal(aiStudioAvailable({enabled: false, ready: true}), false);
  assert.equal(aiStudioAvailable({enabled: true, ready: false}), false);
  assert.equal(aiStudioAvailable({enabled: true, ready: true}), true);
});

test("provider picker uses all six catalog providers and submits the first default", () => {
  const catalog = apiCatalog();
  const settings = apiSettings();
  const initial = projectApiProviderPicker(catalog, settings, "anthropic");

  assert.deepEqual(
    initial.providers.map(provider => provider.id),
    ["xai", "anthropic", "openai", "gemini", "moonshot", "deepseek"],
  );
  assert.equal(initial.providerId, "anthropic");
  assert.equal(initial.modelId, "claude-sonnet-5");
  assert.equal(initial.disclosureVersion, "disclosure-anthropic");

  settings.providers.anthropic.model_id = "claude-opus-5";
  const restored = projectApiProviderPicker(catalog, settings, "anthropic");
  assert.equal(restored.modelId, "claude-opus-5");
  assert.deepEqual(
    restored.models.map(model => model.id),
    ["claude-sonnet-5", "claude-opus-5"],
  );
});

test("defaults to Keymap at the prompt stage", () => {
  assert.deepEqual(createLightingState(), {
    route: ROUTES.KEYMAP,
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
  assert.deepEqual(parseLightingHash("#/lighting/create"), {route: ROUTES.KEYMAP, jobId: null});
  assert.deepEqual(parseLightingHash("#/not-a-route?job=prompt-text"), {route: ROUTES.KEYMAP, jobId: null});
  assert.deepEqual(parseLightingHash("#/lighting/library?job=../../manifest.json"), {route: ROUTES.LIBRARY, jobId: null});
});

test("every launch starts Keymap while preserving active job identity", () => {
  const saved = {
    route: ROUTES.LIBRARY,
    create: {stage: STAGES.REVIEW},
    activeJob: readyJob(),
  };
  const launched = createLaunchState(
    saved,
    formatLightingHash(ROUTES.SETTINGS, JOB_ID),
  );

  assert.equal(launched.lighting.route, ROUTES.KEYMAP);
  assert.equal(launched.lighting.activeJob.id, JOB_ID);
  assert.equal(launched.jobId, JOB_ID);
  assert.equal(launched.hash, formatLightingHash(ROUTES.KEYMAP, JOB_ID));
  for (const route of Object.values(ROUTES)) {
    assert.equal(createLaunchState({route}, formatLightingHash(route)).lighting.route, ROUTES.KEYMAP);
  }
});

test("Library and Settings remain document-independent without a Create route", () => {
  assert.deepEqual(routeAvailability(ROUTES.LIBRARY,null),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.SETTINGS,null),{available:true,reason:null});
  assert.deepEqual(routeAvailability(ROUTES.EDIT,null),{available:false,reason:"document-required"});
  assert.deepEqual(routeAvailability(ROUTES.EDIT,null,{kind:"lighting"}),{available:true,reason:null});
  assert.equal(Object.hasOwn(ROUTES,"CREATE"),false);
});

test("JSON Open classifies the whole selection before any document action", () => {
  const profile={kind:"profile"};
  const lighting={kind:"lighting"};
  assert.deepEqual(
    classifyImportedJsonSelection([profile,profile]),
    {kind:"profiles",indexes:[0,1]},
  );
  assert.deepEqual(
    classifyImportedJsonSelection([lighting]),
    {kind:"lighting",index:0},
  );
  for(const reports of [[lighting,lighting],[profile,lighting],[lighting,profile]]){
    assert.throws(
      ()=>classifyImportedJsonSelection(reports),
      /one AM Master lighting-only JSON file at a time/i,
    );
  }
  assert.throws(
    ()=>classifyImportedJsonSelection([lighting],{merge:true}),
    /cannot be merged/i,
  );
  assert.throws(
    ()=>classifyImportedJsonSelection([{kind:"unknown"}]),
    /unrecognized import result/i,
  );
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

test("imported AM Master lighting applies only to an exact Neon document and slot", () => {
  const imported={
    kind:"lighting",
    lighting:{
      destination:{family:"NEON",product_id:"NEON80",targets:["head","axial"]},
      tracks:{
        head:{signature:"lighting:v1:head"},
        axial:{signature:"lighting:v1:axial"},
      },
    },
  };
  const document={
    family:"NEON",
    productId:"NEON80",
    slots:[5,6,7],
    supportedTargets:["head","axial"],
  };
  const geometry={
    head:{signature:"lighting:v1:head"},
    axial:{signature:"lighting:v1:axial"},
  };
  assert.deepEqual(
    importedLightingApplyAvailability(imported,document,{slot:5,target:"head"},geometry),
    {compatible:true,reason:null},
  );
  const cases=[
    [null,{slot:5,target:"head"},geometry,"document-required"],
    [{...document,family:"ALICE"},{slot:5,target:"head"},geometry,"family-mismatch"],
    [{...document,slots:[6,7]},{slot:5,target:"head"},geometry,"slot-unavailable"],
    [document,{slot:5,target:"keyframes"},geometry,"target-unsupported"],
    [document,{slot:5,target:"head"},{...geometry,axial:{signature:"wrong"}},"layout-mismatch"],
  ];
  for(const [candidate,destination,served,reason] of cases){
    assert.equal(
      importedLightingApplyAvailability(imported,candidate,destination,served).reason,
      reason,
    );
  }
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
