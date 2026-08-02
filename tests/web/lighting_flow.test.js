"use strict";

// Slice P3 guards: Lighting, Library, and Settings expose one task-led normal
// path (docs/superpowers/plans/2026-07-29-product-experience-remediation.md →
// "Interaction Design → Lighting Studio and Library", "Interaction Design →
// Settings", "Product Language Contract", "Non-Goals", "Slice P3").
//
// The owner acceptance guard lives here too: after Slice P2 the owner reported
// the lighting saving flow as incomprehensible — "render, apply, then save?"
// with no indication whether anything reached the keyboard. Every Apply must
// therefore name the destination slot, state that only the open document
// changed, and name the one action that reaches the keyboard.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const {
  createReviewView,
  renderReview,
} = require("../../am_configurator/web/lighting_review.js");

const root = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("am_configurator/web/index.html");
const js = read("am_configurator/web/app.js");
const review = read("am_configurator/web/lighting_review.js");
const lightingState = read("am_configurator/web/lighting_state.js");
const css = read("am_configurator/web/style.css");

function jsFunction(name) {
  const start = js.indexOf(`function ${name}`);
  assert.ok(start >= 0, `app.js must define ${name}`);
  const end = js.indexOf("\nfunction ", start + 10);
  const asyncEnd = js.indexOf("\nasync function ", start + 10);
  const stop = [end, asyncEnd].filter(index => index >= 0).sort((a, b) => a - b)[0];
  return js.slice(start, stop >= 0 ? stop : js.length);
}

function constantDeclaration(name) {
  const start = js.indexOf(`const ${name} = `);
  assert.ok(start >= 0, `app.js must define ${name}`);
  return js.slice(start, js.indexOf("];", start) + 2);
}

function detailsBlock(source, id) {
  const start = source.indexOf(`<details id="${id}"`);
  assert.ok(start >= 0, `${id} disclosure must exist`);
  const end = source.indexOf("</details>", start);
  assert.ok(end > start, `${id} disclosure must be closed`);
  return source.slice(start, end);
}

class ReviewDom {
  set innerHTML(value) {
    this.html = String(value);
  }

  get innerHTML() {
    return this.html || "";
  }

  querySelector() {
    return null;
  }
}

// ---- Tool names and the two-step boundary ---------------------------------

test("Studio tools read Paint, Import media, Effects, and AI over stable keys", () => {
  for (const [key, label] of [
    ["paint", "Paint"],
    ["source", "Import media"],
    ["animate", "Effects"],
    ["generate", "AI"],
  ]) {
    assert.match(
      js,
      new RegExp(`data-studio-tool="${key}">${label}</button>`),
      `the ${key} tool must present as "${label}"`
    );
  }
  // Internal keys and element ids are unchanged so state, focus management, and
  // every existing selector keep working.
  for (const id of [
    "studio-paint-tab", "studio-source-tab", "studio-animate-tab", "studio-generate-tab",
    "studio-paint-panel", "studio-source-panel", "studio-animate-panel", "studio-generate-panel",
  ]) assert.match(js, new RegExp(`id="${id}"`), `${id} must stay stable`);
  // The implementation-led labels are gone from the tab row.
  assert.doesNotMatch(js, /data-studio-tool="source">Source</);
  assert.doesNotMatch(js, /data-studio-tool="animate">Animate</);
  assert.doesNotMatch(js, /data-studio-tool="generate">Generate</);
  // Longer task names cannot blow the tab row out of the narrow tool column.
  assert.match(css, /\.studio-tool-tabs \{[^}]*grid-template-columns: repeat\(auto-fit, minmax\(88px, 1fr\)\)/);
  assert.match(css, /\.studio-tool-tabs > \* \{ min-width: 0; \}/);
});

test("media previews explicitly while effect cards update the Board immediately", () => {
  const media = js.slice(js.indexOf('<div class="media-composition-actions">'), js.indexOf('</div>', js.indexOf('<div class="media-composition-actions">')));
  assert.match(media, /id="media-compose-preview"[^>]*>Preview</);
  assert.match(media, /id="media-compose-apply"[^>]*>Apply to lighting slot</);
  assert.match(media, /id="media-compose-cancel"[^>]*>Cancel</);

  const effects = js.slice(js.indexOf('<div class="animation-draft-actions">'), js.indexOf('</div>', js.indexOf('<div class="animation-draft-actions">')));
  assert.match(effects, /id="animate-accept"[^>]*>Apply to lighting slot</);
  assert.match(effects, /id="animate-cancel"[^>]*>Cancel</);
  assert.doesNotMatch(js, /id="animate-preview"/);
  const cards = jsFunction("animationEffectCardsMarkup");
  for (const effect of ["pulse", "hue_cycle", "sweep", "shimmer", "move_zoom"]) {
    assert.match(cards, new RegExp(`\\["${effect}"`));
  }
  assert.match(jsFunction("regenerateLocalAnimationDraft"), /type:"EFFECT_DRAFT_ACCEPTED"/);
  assert.match(jsFunction("regenerateLocalAnimationDraft"), /autoplay:!prefersReducedLightingMotion\(\)/);

  assert.match(review, /id="apply-procedural-effect"[^>]*>Apply to lighting slot</);
  // The old per-tool verbs are gone; one boundary is named the same everywhere.
  assert.doesNotMatch(js, />Apply preview</);
  assert.doesNotMatch(review, /class="button primary"[^>]*>Apply</);
});

test("effect cards and every normal parameter regenerate exact Board output immediately", () => {
  const wire = jsFunction("wireStudioInspector");
  assert.doesNotMatch(wire, /throw new Error\("Choose an effect first\."\)/);
  assert.match(wire, /\$\$\('\[data-effect-preset\]'\)[\s\S]*regenerateLocalAnimationDraft\(\{renderWorkspace:true,focusEffect:true\}\)/);
  for (const id of ["animate-minimum", "animate-turns", "animate-width", "animate-depth"]) {
    assert.match(
      wire,
      new RegExp(`#${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[^\\n]*addEventListener\\(\"input\"[^\\n]*regenerateLocalAnimationDraft\\(\\{renderWorkspace:false\\}\\)`),
      `${id} must repaint while the user changes it`,
    );
  }
  assert.match(wire, /#animate-direction"\)\?\.addEventListener\("change"[\s\S]*regenerateLocalAnimationDraft\(\{renderWorkspace:false\}\)/);
  assert.match(wire, /#animate-frame-count"\)\?\.addEventListener\("change"[\s\S]*regenerateLocalAnimationDraft\(\{renderWorkspace:true\}\)/);
  assert.match(wire, /#animate-duration"\)\?\.addEventListener\("change"[\s\S]*regenerateLocalAnimationDraft\(\{renderWorkspace:true\}\)/);
  assert.doesNotMatch(jsFunction("cancelLocalAnimationDraft"), /mutate\(/);
  assert.match(jsFunction("mutate"), /lightingWorkspace\.effect_draft[\s\S]*cancelLocalAnimationDraft\(\{render:false\}\)/);
  assert.match(jsFunction("undo"), /lightingWorkspace\.effect_draft[\s\S]*cancelLocalAnimationDraft\(\{render:false\}\)/);
  assert.match(jsFunction("redo"), /lightingWorkspace\.effect_draft[\s\S]*cancelLocalAnimationDraft\(\{render:false\}\)/);
  assert.match(jsFunction("localAnimationDraftStatus"), /demonstrative_frame===null/);
  assert.match(jsFunction("localAnimationDraftStatus"), /Reduce Motion is on/);
});

test("local effect regeneration publishes one exact draft with motion preference attached", () => {
  const source = {frame_RGB: ["#102030", "#405060"]};
  const renderedFrames = [
    ["#102030", "#405060"],
    ["#081018", "#202830"],
  ];
  const frameSet = {token: "exact-board-frame-set"};
  const dispatches = [];
  const toasts = [];
  const context = {
    state: {
      ledTarget: "keyframes",
      ledSlot: 5,
      localAnimationCoordinates: [{x: 0, y: 0}, {x: 1, y: 0}],
      localAnimationEffect: "pulse",
    },
    LED_MODELS: {"80": {}},
    lightingWorkspace: {effect_draft: null},
    reduced: false,
    localAnimationSourceFrame: () => ({frame: source, index: 0}),
    activeLedModel: () => ({}),
    getPage: () => null,
    toast: (...args) => toasts.push(args),
    currentLocalAnimationSpec: () => ({type: "pulse", duration_ms: 90}),
    clone: value => JSON.parse(JSON.stringify(value)),
    renderColorEffect: frames => {
      assert.equal(JSON.stringify(frames), JSON.stringify([source.frame_RGB]));
      return renderedFrames;
    },
    lightingWorkspaceTargetLengths: () => ({keyframes: 2}),
    activeFamilySpec: () => ({frameCap: 256}),
    lightingWorkspaceFrameContext: () => ({target: "keyframes"}),
    boardFrameSetFromLocalEffect: value => {
      assert.equal(JSON.stringify(value.draft.frames), JSON.stringify(renderedFrames));
      return frameSet;
    },
    LED_SPEEDS: [90],
    selectDemonstrativeEffectFrame: () => 1,
    prefersReducedLightingMotion: () => context.reduced,
    dispatchLightingWorkspace: (event, options) => dispatches.push({event, options}),
    renderLightingBoardProjection: () => {},
    updateLocalAnimationDraftStatus: () => {},
    requestAnimationFrame: () => {},
    $: () => null,
    console,
  };
  vm.runInNewContext(
    `${jsFunction("regenerateLocalAnimationDraft")}\nglobalThis.regenerate=regenerateLocalAnimationDraft;`,
    context,
  );

  context.regenerate({renderWorkspace: false});
  assert.deepEqual(toasts, []);
  assert.strictEqual(dispatches[0].event.frame_set, frameSet);
  assert.equal(dispatches[0].event.demonstrative_frame, 1);
  assert.equal(dispatches[0].event.source_frame_index, 0);
  assert.equal(dispatches[0].event.autoplay, true);
  assert.equal(JSON.stringify(dispatches[0].options), JSON.stringify({renderWorkspace: false}));

  context.reduced = true;
  context.regenerate({renderWorkspace: false});
  assert.equal(dispatches[1].event.autoplay, false);
});

test("effect parameter changes stay pinned to the originating document frame", () => {
  const frames = [
    {frame_RGB: ["#111111"]},
    {frame_RGB: ["#222222"]},
  ];
  const context = {
    trackInfo: () => ({track: {frame_data: frames}}),
    currentLocalAnimationDraft: () => ({source_frame_index: 0}),
    lightingWorkspace: {playhead: {index: 7}},
  };
  vm.runInNewContext(
    `${jsFunction("localAnimationSourceFrame")}\nglobalThis.sourceFrame=localAnimationSourceFrame;`,
    context,
  );
  const selected = context.sourceFrame();
  assert.equal(selected.index, 0);
  assert.equal(selected.frame.frame_RGB[0], "#111111");

  context.currentLocalAnimationDraft = () => null;
  const clamped = context.sourceFrame();
  assert.equal(clamped.index, 1);
  assert.equal(clamped.frame.frame_RGB[0], "#222222");
});

test("effect Apply clones exact accepted arrays once and preserves the dependent edge track", () => {
  const frameSet = {
    context: {slot: 5, target: "keyframes"},
    duration_ms: 76,
    frames_by_target: {keyframes: [
      ["#112233", "#445566"],
      ["#778899", "#AABBCC"],
    ]},
  };
  const before = JSON.stringify(frameSet);
  const track = {valid: 0, frame_num: 1, frame_data: []};
  const page = {
    speed_ms: 90,
    spotlight_frames: {valid: 1, frame_num: 1, frame_data: [{frame_RGB: ["#010101"]}]},
  };
  const relic = {};
  const dispatches = [];
  let mutateCalls = 0;
  let mutateRerender = null;
  let mutateOptions = null;
  let resampled = null;
  const context = {
    currentLocalAnimationDraft: () => ({board_frame_set: frameSet}),
    workspaceContextKey: () => "current-context",
    lightingWorkspace: {},
    clone: value => JSON.parse(JSON.stringify(value)),
    mutate: (fn, rerender, options) => {
      mutateCalls += 1;
      mutateRerender = rerender;
      mutateOptions = options;
      fn();
    },
    getPage: () => page,
    ensureTrack: () => track,
    activeLedModel: () => relic,
    LED_MODELS: {"80": relic},
    resampleEdgeAnimation: (frames, count) => {
      resampled = {frames, count};
      return [{frame_index: 0, frame_RGB: ["#010101"]}, {frame_index: 1, frame_RGB: ["#010101"]}];
    },
    state: {appliedLightingProvenance: null},
    createLightingProvenance: value => value,
    dispatchLightingWorkspace: (event, options) => dispatches.push({event, options}),
    toast: () => {},
    lightingSlotLabel: () => "Custom slot 1",
    lightingAppliedDetail: () => "detail",
    console,
  };
  vm.runInNewContext(
    `${jsFunction("applyLocalEffectFrameSet")}\nglobalThis.applyEffect=applyLocalEffectFrameSet;`,
    context,
  );
  const specification = {type: "pulse"};
  context.applyEffect({
    context_key: "current-context",
    board_frame_set: frameSet,
    specification,
  });

  assert.equal(mutateCalls, 1);
  assert.equal(mutateRerender, false);
  assert.equal(mutateOptions.preserveEffectDraft, true);
  assert.equal(track.valid, 1);
  assert.equal(track.frame_num, 2);
  assert.equal(JSON.stringify(track.frame_data.map(frame => frame.frame_RGB)), JSON.stringify(frameSet.frames_by_target.keyframes));
  assert.notStrictEqual(track.frame_data[0].frame_RGB, frameSet.frames_by_target.keyframes[0]);
  assert.equal(page.speed_ms, 76);
  assert.equal(resampled.count, 2);
  assert.equal(page.spotlight_frames.frame_num, 2);
  assert.equal(JSON.stringify(frameSet), before);
  assert.strictEqual(dispatches[0].event.board_frame_set, frameSet);
  assert.equal(dispatches[0].event.type, "APPLY_COMPLETED");
  assert.equal(JSON.stringify(dispatches[0].options), JSON.stringify({renderWorkspace: true}));
  assert.strictEqual(context.state.appliedLightingProvenance.effects[0], specification);
});

// ---- Owner acceptance guard ------------------------------------------------

test("every Apply names the slot, the document-only change, and the Write action", () => {
  const detail = jsFunction("lightingAppliedDetail");
  assert.match(detail, /lightingSlotLabel\(/, "the destination slot must be named");
  assert.match(detail, /lightingTargetLabel\(/, "the destination lighting area must be named");
  assert.match(detail, /changed in this open document only/, "the scope of the change must be stated");
  assert.match(detail, /Nothing has been written to the keyboard yet/, "the keyboard state must be stated");
  assert.match(detail, /use the \$\{writeActionLabel\(\)\} button/, "the next action must be named");

  assert.match(jsFunction("lightingSlotLabel"), /Custom slot \$\{Number\(slot\)-4\}/);
  // The next action names the real keyboard the app already knows about, so it
  // matches the button the user is looking for in the toolbar.
  const writeLabel = jsFunction("writeActionLabel");
  assert.match(writeLabel, /selectedDevice\(\)\?\.product_id/);
  assert.match(writeLabel, /`Write to \$\{product\}`/);
  assert.match(js, /write\.textContent=`Write to \$\{device\.product_id\}`/);

  // Every apply path routes through the one helper.
  for (const name of [
    "applyMediaCompositionDraft",
    "applyLocalEffectFrameSet",
    "applyReviewedLighting",
    "replaceEdgeAnimation",
    "applyLibraryGenerated",
    "applyLibraryLighting",
  ]) assert.match(jsFunction(name), /lightingAppliedDetail\(/, `${name} must report where the work went`);
  assert.match(jsFunction("applyLocalAnimationDraft"), /type:"APPLY_REQUESTED"/);

  // The imported-media status line repeats the same answer where it lingers.
  assert.match(jsFunction("mediaCompositionStatusText"), /lightingAppliedDetail\(\)/);
});

test("a stale model refresh cannot fill inventory from a previous origin", () => {
  // cx-3: an in-flight refresh against origin A must not populate the
  // inventory after origin B is saved.
  const refresh = jsFunction("refreshOllamaModels");
  assert.match(refresh, /const epoch=state\.ollamaInventoryEpoch/);
  // Each branch carries its own discard: a single loose match would stay
  // green if only the success-path check were removed (cx-3 reopen round 1).
  assert.match(
    refresh,
    /const models=normalizeOllamaModels\(await api\("\/api\/ai\/ollama\/models"\)\);\s*if\(epoch!==state\.ollamaInventoryEpoch\)return;\s*state\.ollamaModels=models;/,
    "the success path must discard stale results before assigning"
  );
  assert.match(
    refresh,
    /catch\(error\)\{if\(epoch!==state\.ollamaInventoryEpoch\)return;/,
    "the failure path must discard stale results before assigning"
  );
  const save = jsFunction("saveOllamaBaseUrl");
  assert.match(save, /state\.ollamaInventoryEpoch\+\+/);
});

test("the generated-result review states the destination, scope, and next action", () => {
  const view = createReviewView({
    assetUrls: new Map(),
    jobId: "8a3f0a4e-2a3c-4f0f-9d0a-2f4b6b9f2c11",
    attempt: {preview_asset_id: "preview", mapped_result_asset_id: "mapped"},
    recipe: {name: "Violet aurora", density: "dense", layers: [{}]},
    quality: {frame_count: 24},
    targetLabel: "Keys",
    destinationSlot: 6,
    mappedResultLoaded: true,
    writeActionLabel: "Write to CB04",
  });
  assert.match(view.applyHint, /Custom slot 2/);
  assert.match(view.applyHint, /Keys/);
  assert.match(view.applyHint, /changes the open document only/);
  assert.match(view.applyHint, /Nothing has been written to the keyboard yet/);
  assert.match(view.applyHint, /Write to CB04 button/);

  const dom = new ReviewDom();
  renderReview(dom, view, () => {});
  assert.ok(dom.innerHTML.includes("Custom slot 2"), "the rendered review must show the destination slot");
  assert.ok(dom.innerHTML.includes("Write to CB04"), "the rendered review must name the Write action");

  // Without a known keyboard the hint still names the toolbar button.
  const fallback = createReviewView({destinationSlot: 5, targetLabel: "Keys"});
  assert.match(fallback.applyHint, /Write to keyboard button/);

  // app.js supplies the real device name to the pure renderer.
  assert.match(js, /writeActionLabel:writeActionLabel\(\)/);
});

// ---- Save to Library stays a separate, consistently labelled action --------

test("Save to Library is one label everywhere and never merged into Apply", () => {
  assert.match(js, /id="save-lighting-library"[^>]*>Save to Library</);
  assert.match(js, /id="save-mapping-library"[^>]*>Save to Library</);
  assert.match(js, /id="save-macros-library"[^>]*>Save to Library</);
  assert.doesNotMatch(js, />Save lighting</);
  assert.doesNotMatch(js, />Save mapping to Library</);
  // Non-Goal: Apply and Save to Library are never the same action.
  assert.doesNotMatch(js, /Apply and save|Apply &amp; save/i);
  for (const name of [
    "applyMediaCompositionDraft",
    "applyLocalAnimationDraft",
    "applyReviewedLighting",
  ]) assert.doesNotMatch(
    jsFunction(name),
    /\/api\/library\/save\//,
    `${name} must not perform a Library save`
  );
  assert.match(jsFunction("saveLightingToLibrary"), /\/api\/library\/save\/lighting/);
  assert.match(jsFunction("saveMappingToLibrary"), /\/api\/library\/save\/profile/);
  // Macros reach the same explicit profile save as Keymap.
  assert.match(js, /\$\("#save-macros-library"\)\?\.addEventListener\("click",\(\)=>saveMappingToLibrary\("save-macros-library"\)\)/);
});

// ---- AI panel --------------------------------------------------------------

test("the AI panel shows destination, model, one prompt, one action, and Cancel", () => {
  const prompt = js.slice(js.indexOf("function renderPromptStage"), js.indexOf("function renderProgressStage"));
  assert.match(prompt, /class="concept-destination">Custom \$\{destinationSlot-4\} · \$\{esc\(targetLabel\)\}/);
  assert.match(prompt, /class="concept-model">\$\{esc\(modelLabel\)\}/);
  assert.equal((prompt.match(/id="effect-prompt"/g) || []).length, 1, "one prompt field");
  assert.equal((prompt.match(/id="generate-effect"/g) || []).length, 1, "one generate action");
  assert.match(prompt, /id="cancel-generation"[^>]*>Cancel</);

  const model = jsFunction("selectedAiModelLabel");
  assert.match(model, /Direct API/);
  assert.match(model, /Ollama/);
  assert.match(model, /Ollama Cloud/);
  assert.match(model, /On this Ollama server/);
  assert.match(js, /modelLabel:selectedAiModelLabel\(\)/);
});

test("a generation failure exposes exactly one Try again action and starts no call", () => {
  const prompt = js.slice(js.indexOf("function renderPromptStage"), js.indexOf("function renderProgressStage"));
  assert.match(prompt, /const failed=Boolean\(state\.conceptError\|\|state\.animationError\|\|state\.documentSyncError\|\|stopped\)/);
  assert.match(prompt, /\$\{failed\?"Try again":"Generate lighting"\}/);
  assert.equal((prompt.match(/id="generate-effect"/g) || []).length, 1, "a failure must not add a second retry control");
  // Rendering a failure never issues a request; only the explicit click does.
  assert.doesNotMatch(prompt, /await api\(|fetch\(/);
  const dismiss = jsFunction("dismissGenerationPrompt");
  assert.doesNotMatch(dismiss, /api\(|fetch\(/, "Cancel must not contact the backend");
  // The one-request contract from the backend plan stays visible here: a single
  // generation entry point, reached only from the explicit action.
  assert.equal((js.match(/\/api\/lighting\/effects/g) || []).length, 1);
  assert.match(js, /\$\("#generate-effect"\)\?\.addEventListener\("click",startProceduralGeneration\)/);
  assert.doesNotMatch(js, /retry_prompt|retry_seed|generate_attempt/);
});

test("AI-off hides AI-only controls while every manual tool stays available", () => {
  const context = {aiReady: () => false};
  vm.runInNewContext(`${jsFunction("availableStudioTools")}\nglobalThis.tools=availableStudioTools();`, context);
  assert.deepEqual(Array.from(context.tools), ["paint", "source", "animate"]);
  const onContext = {aiReady: () => true};
  vm.runInNewContext(`${jsFunction("availableStudioTools")}\nglobalThis.tools=availableStudioTools();`, onContext);
  assert.deepEqual(Array.from(onContext.tools), ["paint", "source", "animate", "generate"]);
  assert.match(js, /const generationTab=aiReady\(\)\?/);
  assert.match(js, /const generationPanel=aiReady\(\)\?/);
  assert.match(jsFunction("renderGenerationStudio"), /if\(!container\|\|!aiReady\(\)\)return/);
  assert.match(jsFunction("setStudioTool"), /if\(!availableStudioTools\(\)\.includes\(tool\)\)return/);
});

// ---- Advanced disclosures --------------------------------------------------

test("technical lighting controls keep their behavior under Advanced", () => {
  const paint = detailsBlock(js, "paint-advanced");
  assert.match(paint, /class="advanced-disclosure"/);
  assert.match(paint, /id="speed"/, "the firmware timing steps live under Advanced");

  const media = detailsBlock(js, "media-advanced");
  assert.match(media, /id="gif-resample"/, "the sampling method lives under Advanced");
  assert.match(media, /id="source-stretch"/, "independent-axis stretch lives under Advanced");
  assert.match(media, /id="source-height"/, "the independent height axis follows stretch");

  // The Effects disclosure is assembled by one function, so the seed markup is
  // checked against that function rather than the raw template slice.
  const effects = jsFunction("animationAdvancedMarkup");
  assert.match(effects, /<details id="effects-advanced" class="advanced-disclosure"/);
  assert.match(effects, /id="animate-frame-count"/, "the raw frame count lives under Advanced");
  assert.match(effects, /id="animate-duration"/, "the firmware timing steps live under Advanced");
  assert.match(effects, /id="animate-seed"/, "the pattern seed lives under Advanced");
  assert.doesNotMatch(jsFunction("animationParameterMarkup"), /animate-seed/, "the seed left the normal effect controls");

  // Every wired behavior survives the move: the handlers still exist.
  const wire = jsFunction("wireStudioInspector");
  for (const selector of ["#gif-resample", "#source-stretch", "#source-height", "#animate-frame-count", "#animate-duration", "#animate-seed"]) {
    assert.ok(
      js.includes(`$("${selector}")`),
      `${selector} must keep its handler after moving under Advanced`
    );
  }
  assert.match(wire, /#animate-seed"\)\?\.addEventListener/);

  // Disclosure state survives a re-render, like the P2 disclosures.
  for (const [id, field] of [
    ["paint-advanced", "paintAdvancedOpen"],
    ["media-advanced", "mediaAdvancedOpen"],
    ["effects-advanced", "effectsAdvancedOpen"],
  ]) {
    assert.match(js, new RegExp(`\\$\\("#${id}"\\)\\?\\.addEventListener\\("toggle",event=>\\{state\\.${field}=event\\.currentTarget\\.open;\\}\\)`));
    assert.match(js, new RegExp(`\\$\\{state\\.${field}\\?"open":""\\}`));
  }
});

test("normal lighting controls are friendly presets constrained to firmware values", () => {
  const context = {};
  vm.runInNewContext(
    `${constantDeclaration("LED_SPEEDS")}\n${constantDeclaration("LED_SPEED_PRESETS")}\n${constantDeclaration("LED_LENGTH_PRESETS")}\n`
    + "globalThis.speeds=LED_SPEEDS;globalThis.speedPresets=LED_SPEED_PRESETS;globalThis.lengthPresets=LED_LENGTH_PRESETS;",
    context
  );
  assert.ok(context.speedPresets.length >= 3, "the normal path needs speed presets");
  for (const [label, speed] of context.speedPresets) {
    assert.ok(label.length > 0);
    assert.ok(
      context.speeds.includes(speed),
      `speed preset ${label} (${speed}ms) is not a firmware timing step`
    );
  }
  for (const [label, count] of context.lengthPresets) {
    assert.ok(label.length > 0);
    assert.ok(Number.isSafeInteger(count) && count >= 2, `length preset ${label} must be a usable frame count`);
  }
  // The presets are clamped to the destination frame cap before rendering.
  assert.match(jsFunction("ledLengthPresetMarkup"), /Math\.max\(2,Math\.min\(cap,count\)\)/);
  assert.match(js, /\$\{ledSpeedPresetMarkup\("paint-speed-presets"/);
  assert.match(js, /\$\{ledSpeedPresetMarkup\("animate-speed-presets"/);
  assert.match(js, /\$\{ledLengthPresetMarkup\("animate-length-presets"/);
  assert.match(js, /data-speed-preset/);
  assert.match(js, /data-length-preset/);
  assert.match(css, /\.speed-presets, \.length-presets \{[^}]*flex-wrap: wrap/);
});

// ---- Settings --------------------------------------------------------------

test("Settings offers Ollama and Direct API with the full Ollama server panel", () => {
  const ollamaPanel = html.slice(html.indexOf('id="settings-ollama-panel"'), html.indexOf('id="settings-api-panel"'));
  assert.match(ollamaPanel, /Ollama server URL/);
  assert.match(ollamaPanel, /http:\/\/127\.0\.0\.1:11434/, "the loopback default must be shown");
  assert.match(ollamaPanel, /192\.168\./, "a LAN example must be shown");
  assert.match(ollamaPanel, /id="settings-ollama-runtime"/, "the configured host's connection status");
  assert.match(ollamaPanel, /id="settings-ollama-refresh"[^>]*>Refresh models</);
  assert.match(ollamaPanel, /id="settings-ollama-select"[^>]*>Use model</);
  assert.match(ollamaPanel, /id="settings-ollama-test"[^>]*>Test setup</);
  assert.match(ollamaPanel, /id="settings-ollama-clear"[^>]*>Clear selection</);
  assert.match(ollamaPanel, /id="settings-ollama-disclosure"/);
  // Connection status never carries a credential.
  assert.doesNotMatch(ollamaPanel, /API key|password|token|credential/i);
  // The picker labels come from the backend contract and stay unchanged.
  assert.match(lightingState, /Ollama Cloud/);
  assert.match(lightingState, /On this Ollama server/);
  // Superseded provider vocabulary is gone from every user-visible surface.
  for (const banned of [/Primary computer/i, /Secondary provider/i, /Installed model/i, /eligible local/i]) {
    for (const [name, source] of [["index.html", html], ["app.js", js], ["lighting_state.js", lightingState]]) {
      assert.doesNotMatch(source, banned, `${name} still uses superseded provider wording`);
    }
  }
});

test("saving a server URL performs no inventory or setup request", () => {
  const save = jsFunction("saveOllamaBaseUrl");
  assert.match(save, /api\("\/api\/settings\/ollama"/, "the URL is persisted");
  assert.doesNotMatch(save, /\/api\/ai\/ollama\/models/);
  assert.doesNotMatch(save, /\/api\/ai\/test/);
  assert.doesNotMatch(save, /refreshOllamaModels\(|testAiBackend\(/);
  // Refresh models and Test setup are the only actions that reach out.
  assert.equal((js.match(/\/api\/ai\/ollama\/models/g) || []).length, 1);
  assert.equal((js.match(/api\("\/api\/ai\/test"/g) || []).length, 1);
  assert.match(jsFunction("refreshOllamaModels"), /\/api\/ai\/ollama\/models/);
  assert.match(jsFunction("testAiBackend"), /api\("\/api\/ai\/test"/);
  assert.match(js, /\$\("#settings-ollama-refresh"\)\.addEventListener/);
  assert.match(js, /\$\("#settings-ollama-test"\)\.addEventListener/);
});
