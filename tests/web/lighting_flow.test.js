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
const {
  boardFrameSetFromDocument,
  boardFrameSetFromMappedResult,
  createBoardFrameSet,
  createLightingWorkspace,
  reduceLightingWorkspace,
  workspaceContextKey,
} = require("../../am_configurator/web/lighting_workspace.js");
const {mediaDraftCanApply} = require("../../am_configurator/web/library_state.js");

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

test("media builds its preview automatically while effect cards update the Board immediately", () => {
  const edit = jsFunction("renderLightingEdit");
  const mediaStart = edit.indexOf('<div class="media-composition-actions">');
  const media = edit.slice(mediaStart, edit.indexOf('</div>', mediaStart));
  assert.doesNotMatch(media, /id="media-compose-preview"/);
  assert.match(media, /id="media-compose-apply"[^>]*>\$\{mediaApplyLabel\}</);
  assert.match(media, /id="media-compose-cancel"[^>]*>Cancel</);
  assert.doesNotMatch(jsFunction("wireStudioInspector"), /#media-compose-preview/);
  assert.match(jsFunction("renderMediaCompositionFrameAttempt"), /scheduleMediaCompositionPreview\(\)/);
  assert.doesNotMatch(jsFunction("applyMediaCompositionDraft"), /Preview required|Create a preview/);
  const mediaStatus = jsFunction("mediaCompositionStatusText");
  assert.doesNotMatch(mediaStatus, /lightingAppliedDetail|keyboard is unchanged/i);
  assert.match(mediaStatus, /Board ready/);
  assert.match(jsFunction("dispatchLightingWorkspace"), /type:"RENDER_DISCARDED"/);
  assert.match(jsFunction("setStudioTool"), /resumeUnfinishedMediaComposition\(\)/);
  assert.match(jsFunction("renderLightingShell"), /resumeUnfinishedMediaComposition\(\)/);
  assert.match(
    jsFunction("resumeUnfinishedMediaComposition"),
    /status!=="draft"[\s\S]*renderMediaCompositionPreview\(\)/,
  );
  assert.doesNotMatch(jsFunction("openLibrarySource"), /renderMediaCompositionPreview\(\)/);
  assert.match(css, /\.media-composition-actions \{[^}]*grid-template-columns: minmax\(0, 1fr\) auto/);
  assert.match(css, /#media-compose-apply \{[^}]*white-space: normal/);

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

test("Studio and Library navigation preserves accepted and applied media work", () => {
  const frames = [
    ["#112233", "#445566"],
    ["#778899", "#AABBCC"],
  ];
  const timeline = [
    {index: 0, source_frame_index: 0},
    {index: 1, source_frame_index: 1},
  ];
  let workspace = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "source",
    route: "lighting/edit",
  });
  const transition = event => {
    workspace = reduceLightingWorkspace(workspace, event).state;
  };
  transition({
    type: "MEDIA_OPENED",
    media: {catalog_id: "media-a", asset_id: "source-a", requested_revision: 4},
  });
  transition({type: "TRANSFORM_REQUESTED", media_revision: 4, transform: {scale_x: 1.5}});
  transition({type: "SEQUENCE_RENDER_STARTED"});
  const accepted = createBoardFrameSet({
    context: {
      document_epoch: 7,
      slot: 5,
      target: "keyframes",
      source_kind: "media_render",
      revision: 4,
    },
    frames_by_target: {keyframes: frames},
    frame_count: 2,
    duration_ms: 90,
    timeline,
    provenance: "media_render",
  }, {targetLengths: {keyframes: 2}, allowedDurations: [90], maxFrames: 8});
  transition({
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: workspace.preview.request_epoch,
    context_key: workspace.preview.request_context_key,
    media_revision: 4,
    frame_set: accepted,
    target_lengths: {keyframes: 2},
    allowed_durations: [90],
    max_frames: 8,
  });
  transition({type: "ROUTE_CHANGED", route: "lighting/library"});
  transition({type: "ROUTE_CHANGED", route: "lighting/edit"});
  assert.equal(workspace.preview.board_frame_set, null);
  assert.equal(workspace.media.accepted_revision, 4);

  const draft = {
    status: "ready",
    catalogId: "media-a",
    source: {asset_id: "source-a"},
    destination: {productId: "CYBERBOARD", target: "keyframes", targets: ["keyframes"]},
    revision: 4,
    acceptedRevision: 4,
    transform: {scale_x: 1.5},
    effects: [],
    mappedResult: {
      duration_ms: 90,
      tracks: {keyframes: {frame_count: 2, frames}},
    },
  };
  const page = {speed_ms: 90, keyframes: {frame_data: [["#000000", "#000000"]]}};
  const state = {
    config: {},
    studioTool: "source",
    ledSlot: 5,
    ledTarget: "keyframes",
    mediaComposition: draft,
    appliedLightingProvenance: null,
  };
  const context = {
    state,
    lightingWorkspace: workspace,
    ROUTES: {EDIT: "lighting/edit"},
    LED_SPEEDS: [90],
    mediaDraftCanApply,
    productId: () => "CYBERBOARD",
    getPage: () => page,
    lightingProvenanceForPage: () => null,
    lightingWorkspaceTargetLengths: () => ({keyframes: 2}),
    activeFamilySpec: () => ({frameCap: 8}),
    lightingWorkspaceFrameContext: sourceKind => ({
      document_epoch: context.lightingWorkspace.context.document_epoch,
      slot: context.lightingWorkspace.context.slot,
      target: context.lightingWorkspace.context.target,
      source_kind: sourceKind,
      revision: context.lightingWorkspace.preview.accepted_epoch,
    }),
    boardFrameSetFromDocument,
    boardFrameSetFromMappedResult,
    workspaceContextKey,
    console,
  };
  vm.runInNewContext(
    [
      "mediaCompositionHasAcceptedResult",
      "mediaCompositionResultMatchesDocument",
      "mediaCompositionCanPresent",
      "activeMediaPreviewTrack",
      "mediaCompositionCanApply",
      "currentLightingBoardFrameSet",
    ].map(jsFunction).join("\n")
      + "\nglobalThis.activeTrack=activeMediaPreviewTrack;"
      + "globalThis.canApply=mediaCompositionCanApply;"
      + "globalThis.matchesDocument=mediaCompositionResultMatchesDocument;"
      + "globalThis.restoreFrameSet=currentLightingBoardFrameSet;",
    context,
  );

  const restoredTrack = context.activeTrack();
  assert.equal(JSON.stringify(restoredTrack.frames), JSON.stringify(frames));
  const restored = context.restoreFrameSet({
    model: {},
    page,
    track: page.keyframes,
    mediaPreviewTrack: restoredTrack,
    activeDraft: null,
    transientPreview: null,
  });
  workspace = reduceLightingWorkspace(workspace, {
    type: "BOARD_FRAME_SET_ACCEPTED",
    frame_set: restored,
    target_lengths: {keyframes: 2},
    allowed_durations: [90],
    max_frames: 8,
  }).state;
  context.lightingWorkspace = workspace;
  assert.equal(context.canApply(), true);

  draft.status = "applied";
  state.appliedLightingProvenance = {version: 1};
  context.lightingProvenanceForPage = () => ({
    source_catalog_id: draft.catalogId,
    transform: draft.transform,
    effects: draft.effects,
  });
  assert.equal(context.matchesDocument(), true);
  assert.equal(context.canApply(), false);
  assert.equal(JSON.stringify(context.activeTrack().frames), JSON.stringify(frames));

  context.lightingProvenanceForPage = () => null;
  assert.equal(context.matchesDocument(), false);
  assert.equal(context.canApply(), true, "Undo must make the exact accepted draft applicable again");
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
  const companionFrames = {spotlight_frames: [["#010101"], ["#020202"]]};
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
    dependentLightingFramesByTarget: options => {
      assert.equal(options.primaryTarget, "keyframes");
      assert.equal(options.frameCount, renderedFrames.length);
      return companionFrames;
    },
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
      assert.strictEqual(value.companionFramesByTarget, companionFrames);
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

test("Apply accepts only the exact current BoardFrameSet", () => {
  const frameSet = {
    context: {document_epoch: 7, slot: 5, target: "keyframes"},
    frames_by_target: {keyframes: [["#010203"]]},
    provenance: "media_render",
  };
  const context = {
    state: {ledSlot: 5, ledTarget: "keyframes"},
    lightingWorkspace: {
      context: {document_epoch: 7},
      preview: {
        status: "ready",
        context_key: "current-context",
        board_frame_set: frameSet,
      },
    },
    workspaceContextKey: () => "current-context",
    console,
  };
  vm.runInNewContext(
    `${jsFunction("acceptedBoardFrameSetForApply")}\nglobalThis.accept=acceptedBoardFrameSetForApply;`,
    context,
  );

  assert.strictEqual(context.accept({
    provenance: "media_render",
    expected: frameSet,
    contextKey: "current-context",
  }), frameSet);
  assert.throws(
    () => context.accept({provenance: "procedural_result", expected: frameSet}),
    /exact Board preview has expired/,
  );
  assert.throws(
    () => context.accept({provenance: "media_render", expected: {...frameSet}}),
    /exact Board preview has expired/,
  );
  context.lightingWorkspace.preview.context_key = "stale-context";
  assert.throws(
    () => context.accept({provenance: "media_render", expected: frameSet}),
    /exact Board preview has expired/,
  );
});

test("the common BoardFrameSet writer copies exact accepted arrays and duration", () => {
  const frameSet = {
    context: {slot: 5, target: "keyframes"},
    duration_ms: 76,
    frame_count: 2,
    frames_by_target: {
      keyframes: [
        ["#112233", "#445566"],
        ["#778899", "#AABBCC"],
      ],
      spotlight_frames: [
        ["#010101"],
        ["#020202"],
      ],
    },
  };
  const before = JSON.stringify(frameSet);
  const page = {speed_ms: 90};
  const context = {
    mappedResultFromBoardFrameSet: value => {
      assert.strictEqual(value, frameSet);
      return {
        duration_ms: value.duration_ms,
        source_frames: value.frame_count,
        tracks: Object.fromEntries(Object.entries(value.frames_by_target).map(
          ([target, frames]) => [target, {
            frame_count: frames.length,
            frames: frames.map(colors => [...colors]),
          }],
        )),
      };
    },
    console,
  };
  vm.runInNewContext(
    `${jsFunction("applyLedResultToPage")}\n${jsFunction("applyBoardFrameSetToPage")}\nglobalThis.applyBoard=applyBoardFrameSetToPage;`,
    context,
  );
  context.applyBoard(page, frameSet, "keyframes");

  assert.equal(page.valid, 1);
  assert.equal(page.speed_ms, 76);
  assert.equal(page.keyframes.frame_num, 2);
  assert.equal(page.spotlight_frames.frame_num, 2);
  assert.equal(
    JSON.stringify(page.keyframes.frame_data.map(frame => frame.frame_RGB)),
    JSON.stringify(frameSet.frames_by_target.keyframes),
  );
  assert.equal(
    JSON.stringify(page.spotlight_frames.frame_data.map(frame => frame.frame_RGB)),
    JSON.stringify(frameSet.frames_by_target.spotlight_frames),
  );
  assert.notStrictEqual(page.keyframes.frame_data[0].frame_RGB, frameSet.frames_by_target.keyframes[0]);
  assert.equal(JSON.stringify(frameSet), before);
});

test("effect Apply consumes the accepted BoardFrameSet through one Undo checkpoint", () => {
  const frameSet = {
    context: {slot: 5, target: "keyframes"},
    duration_ms: 76,
    frames_by_target: {
      keyframes: [["#112233"], ["#445566"]],
      spotlight_frames: [["#010101"], ["#020202"]],
    },
  };
  const page = {};
  const dispatches = [];
  let mutateCalls = 0;
  let applied = null;
  const context = {
    currentLocalAnimationDraft: () => ({board_frame_set: frameSet}),
    acceptedBoardFrameSetForApply: options => {
      assert.strictEqual(options.expected, frameSet);
      assert.equal(options.provenance, "local_effect");
      return frameSet;
    },
    mutate: (fn, rerender, options) => {
      mutateCalls += 1;
      assert.equal(rerender, false);
      assert.equal(options.preserveEffectDraft, true);
      fn();
    },
    getPage: () => page,
    applyBoardFrameSetToPage: (...args) => { applied = args; },
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
  assert.strictEqual(applied[0], page);
  assert.strictEqual(applied[1], frameSet);
  assert.equal(applied[2], "keyframes");
  assert.strictEqual(dispatches[0].event.board_frame_set, frameSet);
  assert.equal(dispatches[0].event.type, "APPLY_COMPLETED");
  assert.equal(JSON.stringify(dispatches[0].options), JSON.stringify({renderWorkspace: true}));
  assert.strictEqual(context.state.appliedLightingProvenance.effects[0], specification);
});

test("every preview-backed Apply consumes the currently accepted BoardFrameSet", () => {
  for (const name of [
    "applyMediaCompositionDraft",
    "applyLocalEffectFrameSet",
    "applyReviewedLighting",
    "applyImportedLighting",
    "applyLibraryPreview",
  ]) {
    const body = jsFunction(name);
    assert.match(body, /acceptedBoardFrameSetForApply\(/, `${name} must retrieve the accepted preview`);
    assert.match(body, /applyBoardFrameSetToPage\(/, `${name} must use the common exact writer`);
    assert.equal((body.match(/mutate\(/g) || []).length, 1, `${name} must create one Undo checkpoint`);
    assert.doesNotMatch(body, /resampleEdgeAnimation\(/, `${name} must not derive an unpreviewed track`);
  }
  assert.doesNotMatch(jsFunction("applyLedResultToPage"), /resampleEdgeAnimation\(/);
  const procedural = jsFunction("applyReviewedLighting");
  assert.match(procedural, /preview\?\.kind!=="procedural"/);
  assert.match(procedural, /preview\.identity!==proceduralPreviewIdentity\(manifest,attempt\)/);
  assert.match(procedural, /expected:preview\.boardFrameSet/);
});

test("Library actions open a read-only Board preview before a separate Apply", () => {
  assert.match(js, /data-library-preview-lighting[^>]*>Preview on board</);
  assert.match(js, /data-library-preview-generated[^>]*>Preview on board</);
  for (const name of ["previewLibraryGenerated", "previewLibraryLighting"]) {
    const body = jsFunction(name);
    assert.match(body, /openLibraryBoardPreview\(/);
    assert.doesNotMatch(body, /mutate\(|applyBoardFrameSetToPage\(|\/api\/library\/save\//);
    const open = body.indexOf("openLibraryBoardPreview({");
    assert.ok(
      open < body.indexOf("lease.release()"),
      `${name} must keep its request current until the Board preview opens`,
    );
    assert.ok(
      open < body.indexOf("state.library.previewingCatalogId=null"),
      `${name} must leave failure cleanup to finally until the Board preview opens`,
    );
  }
  const cancel = jsFunction("cancelLibraryBoardPreview");
  assert.doesNotMatch(cancel, /mutate\(|api\(|fetch\(/);
  const apply = jsFunction("applyLibraryPreview");
  assert.doesNotMatch(apply, /api\(|fetch\(|\/api\/library\/save\//);
  assert.match(apply, /acceptedBoardFrameSetForApply\(/);
  assert.match(apply, /applyBoardFrameSetToPage\(/);
  assert.match(jsFunction("wireLedEditor"), /const paintEnabled=state\.studioTool==="paint"&&!activeTransientLightingPreview\(\)/);
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
    "applyImportedLighting",
    "applyLibraryPreview",
    "replaceEdgeAnimation",
  ]) assert.match(jsFunction(name), /lightingAppliedDetail\(/, `${name} must report where the work went`);
  assert.match(jsFunction("applyLocalAnimationDraft"), /type:"APPLY_REQUESTED"/);

  // The lingering imported-media line stays compact enough to keep the full
  // workspace visible; the Apply toast above owns the detailed Write guidance.
  const mediaStatus = jsFunction("mediaCompositionStatusText");
  assert.match(mediaStatus, /lightingSlotLabel\(\)/);
  assert.match(mediaStatus, /open profile/);
  assert.doesNotMatch(mediaStatus, /lightingAppliedDetail\(\)/);
  assert.match(jsFunction("updateLightingWorkspaceStatus"), /The keyboard is unchanged/);
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
    boardPreviewReady: true,
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
  assert.doesNotMatch(js, /conceptAssetUrls|conceptAssetLoads|loadConceptAsset/);
  assert.doesNotMatch(jsFunction("hydrateProceduralAssets"), /preview_asset_id|MEDIA_OPENED|preview-session/);
  assert.match(jsFunction("renderProceduralReview"), /boardPreviewReady/);
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
