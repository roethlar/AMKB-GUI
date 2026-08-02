"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  boardFrameSetFromDocument,
  boardFrameSetFromLocalEffect,
  boardFrameSetFromMappedFrame,
  boardFrameSetFromMappedResult,
  captureWorkspaceAsyncContext,
  createLightingPlaybackRuntime,
  createBoardFrameSet,
  createLightingWorkspace,
  friendlyWorkspaceError,
  paintBoardProjection,
  projectBoardFrame,
  reduceLightingWorkspace,
  selectBoardProjection,
  selectSourceProjection,
  workspaceContextKey,
  workspaceAsyncContextMatches,
  workspaceDestinationKey,
} = require("../../am_configurator/web/lighting_workspace.js");

const FIRMWARE_DURATIONS = [34, 48, 62, 76, 90];
const TARGET_LENGTHS = Object.freeze({keyframes: 2, frames: 3, head: 3});

function context(overrides = {}) {
  return {
    document_epoch: 7,
    slot: 5,
    target: "keyframes",
    source_kind: "document",
    revision: 0,
    ...overrides,
  };
}

function frameSet({
  workspaceContext = context(),
  framesByTarget = {keyframes: [["#FF0000", "#00FF00"]]},
  durationMs = 90,
  provenance = workspaceContext.source_kind,
} = {}) {
  const frameCount = Object.values(framesByTarget)[0].length;
  return createBoardFrameSet({
    context: workspaceContext,
    frames_by_target: framesByTarget,
    frame_count: frameCount,
    duration_ms: durationMs,
    timeline: Array.from({length: frameCount}, (_, index) => ({index})),
    provenance,
  }, {
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
}

function publish(state, value) {
  return reduceLightingWorkspace(state, {
    type: "BOARD_FRAME_SET_ACCEPTED",
    frame_set: value,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
}

function fakePixel(index) {
  const properties = new Map();
  return {
    dataset: {pixel: String(index)},
    style: {
      background: "",
      setProperty(name, value) { properties.set(name, value); },
      getPropertyValue(name) { return properties.get(name) || ""; },
    },
  };
}

function fakeFrameItem(swatchColors = []) {
  const attributes = new Map();
  const classes = new Set();
  const swatches = swatchColors.map(color => ({style: {background: color}}));
  return {
    swatches,
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
      contains(name) { return classes.has(name); },
    },
    setAttribute(name, value) { attributes.set(name, value); },
    getAttribute(name) { return attributes.get(name); },
    querySelectorAll(selector) {
      return selector === ".frame-thumb > i" ? swatches : [];
    },
  };
}

function fakePlaybackPlatform() {
  let nextTimer = 1;
  const timers = new Map();
  const listeners = new Map();
  return {
    timers,
    setTimer(callback, duration) {
      const handle = nextTimer++;
      timers.set(handle, {callback, duration});
      return handle;
    },
    clearTimer(handle) { timers.delete(handle); },
    lifecycleTarget: {
      addEventListener(type, listener) {
        const current = listeners.get(type) || new Set();
        current.add(listener);
        listeners.set(type, current);
      },
      removeEventListener(type, listener) {
        listeners.get(type)?.delete(listener);
      },
    },
    emit(type) {
      for (const listener of listeners.get(type) || []) listener({type});
    },
    listenerCount(type) { return listeners.get(type)?.size || 0; },
  };
}

test("BoardFrameSet validates shapes and canonicalizes valid RGB spelling", () => {
  const accepted = frameSet({
    framesByTarget: {
      keyframes: [
        ["#FF0000", "#00FF00"],
        ["#0000FF", "#FFFFFF"],
      ],
    },
  });

  assert.equal(accepted.frame_count, 2);
  assert.deepEqual(projectBoardFrame(
    accepted,
    "keyframes",
    1,
    {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS},
  ), ["#0000FF", "#FFFFFF"]);
  assert.ok(Object.isFrozen(accepted));
  assert.ok(Object.isFrozen(accepted.frames_by_target.keyframes[0]));

  assert.throws(
    () => frameSet({framesByTarget: {unknown: [["#FF0000"]]}}),
    error => error.code === "invalid_target",
  );
  const canonicalized = frameSet({
    framesByTarget: {keyframes: [["#ff0000", "#00ff00"]]},
  });
  assert.deepEqual(
    canonicalized.frames_by_target.keyframes[0],
    ["#FF0000", "#00FF00"],
  );
  assert.throws(
    () => frameSet({framesByTarget: {keyframes: [["#FF0000"]]}}),
    error => error.code === "invalid_frame",
  );
  assert.throws(
    () => createBoardFrameSet({
      context: context(),
      frames_by_target: {keyframes: [["#FF0000", "#00FF00"]]},
      frame_count: 2,
      duration_ms: 90,
      timeline: [{index: 0}, {index: 1}],
      provenance: "document",
    }, {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS}),
    error => error.code === "invalid_frame",
  );
  assert.throws(
    () => projectBoardFrame({
      context: context(),
      frames_by_target: {keyframes: [["#FF0000", "not-a-color"]]},
      frame_count: 1,
      duration_ms: 90,
      timeline: [{index: 0}],
      provenance: "document",
    }, "keyframes", 0, {
      targetLengths: TARGET_LENGTHS,
      allowedDurations: FIRMWARE_DURATIONS,
    }),
    error => error.code === "invalid_color",
  );
});

test("one mapped media frame becomes an exact transient Board frame", () => {
  const selected = boardFrameSetFromMappedFrame({
    context: context({source_kind: "media_render", revision: 4}),
    mappedFrame: {
      tracks: {
        keyframes: {pixels: 2, colors: ["#abcdef", "#123456"]},
      },
    },
    timelineEntry: {index: 7, source_frame_index: 3, duration_ms: 90},
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });

  assert.equal(selected.frame_count, 1);
  assert.equal(selected.duration_ms, 90);
  assert.deepEqual(selected.timeline, [{index: 0, source_frame_index: 3}]);
  assert.deepEqual(selected.frames_by_target.keyframes, [["#ABCDEF", "#123456"]]);
});

test("document, local effect, media, procedural, and imported JSON share one BoardFrameSet contract", () => {
  const documentSet = boardFrameSetFromDocument({
    context: context(),
    track: {
      frame_data: [
        {frame_index: 0, frame_RGB: ["#010203", "#AABBCC"]},
        {frame_index: 1, frame_RGB: ["#102030", "#DDEEFF"]},
      ],
    },
    durationMs: 90,
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  assert.equal(documentSet.provenance, "document");
  assert.equal(documentSet.frame_count, 2);

  const effectSet = boardFrameSetFromLocalEffect({
    context: context({source_kind: "local_effect"}),
    draft: {
      frames: [
        ["#112233", "#445566"],
        ["#778899", "#AABBCC"],
      ],
      effect: {duration_ms: 76},
    },
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  assert.equal(effectSet.provenance, "local_effect");

  const mappedResult = {
    duration_ms: 48,
    tracks: {
      keyframes: {
        frame_count: 2,
        frames: [
          ["#000001", "#000002"],
          ["#000003", "#000004"],
        ],
      },
      head: {
        frame_count: 2,
        frames: [
          ["#100001", "#100002", "#100003"],
          ["#200001", "#200002", "#200003"],
        ],
      },
    },
  };
  const mediaSet = boardFrameSetFromMappedResult({
    context: context({source_kind: "media_render"}),
    mappedResult,
    timeline: [
      {index: 0, source_frame_index: 3},
      {index: 1, source_frame_index: 1},
    ],
    provenance: "media_render",
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  const proceduralSet = boardFrameSetFromMappedResult({
    context: context({source_kind: "procedural_result", revision: 12}),
    mappedResult,
    provenance: "procedural_result",
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  const importedSet = boardFrameSetFromMappedResult({
    context: context({source_kind: "imported_json", revision: 13}),
    mappedResult,
    provenance: "imported_json",
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });

  assert.deepEqual(mediaSet.frames_by_target, proceduralSet.frames_by_target);
  assert.deepEqual(importedSet.frames_by_target, proceduralSet.frames_by_target);
  assert.equal(mediaSet.provenance, "media_render");
  assert.deepEqual(mediaSet.timeline, [
    {index: 0, source_frame_index: 3},
    {index: 1, source_frame_index: 1},
  ]);
  assert.equal(proceduralSet.provenance, "procedural_result");
  assert.equal(importedSet.provenance, "imported_json");
  assert.deepEqual(projectBoardFrame(
    proceduralSet,
    "head",
    1,
    {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS},
  ), ["#200001", "#200002", "#200003"]);
});

test("imported Head and Per-key views keep one exact timeline position", () => {
  const targetLengths={head:3,axial:2};
  let state=createLightingWorkspace({
    documentEpoch:7,
    slot:5,
    target:"head",
    tool:"paint",
    route:"lighting/edit",
  });
  state=reduceLightingWorkspace(state,{
    type:"IMPORTED_LIGHTING_OPENED",
    target:"head",
  }).state;
  const mappedResult={
    duration_ms:90,
    tracks:{
      head:{
        frame_count:3,
        frames:[
          ["#100001","#100002","#100003"],
          ["#200001","#200002","#200003"],
          ["#300001","#300002","#300003"],
        ],
      },
      axial:{
        frame_count:3,
        frames:[
          ["#400001","#400002"],
          ["#500001","#500002"],
          ["#600001","#600002"],
        ],
      },
    },
  };
  const publishImported=workspace=>reduceLightingWorkspace(workspace,{
    type:"BOARD_FRAME_SET_ACCEPTED",
    frame_set:boardFrameSetFromMappedResult({
      context:{...workspace.context,source_kind:"imported_json",revision:1},
      mappedResult,
      provenance:"imported_json",
      targetLengths,
      allowedDurations:FIRMWARE_DURATIONS,
    }),
    target_lengths:targetLengths,
    allowed_durations:FIRMWARE_DURATIONS,
  }).state;

  state=publishImported(state);
  state=reduceLightingWorkspace(state,{type:"PLAYHEAD_SCRUBBED",index:1}).state;
  const changed=reduceLightingWorkspace(state,{
    type:"DESTINATION_CHANGED",
    slot:5,
    target:"axial",
    playhead_index:state.playhead.index,
  });
  assert.equal(changed.intents[0].type,"cancel-playback");
  assert.equal(changed.state.playhead.index,1);
  state=publishImported(changed.state);
  const projection=selectBoardProjection(state);
  assert.equal(projection.index,1);
  assert.deepEqual(projection.colors,["#500001","#500002"]);
  assert.equal(projection.frame_set.duration_ms,90);
  assert.equal(projection.frame_set.frame_count,3);
  assert.deepEqual(projection.frame_set.timeline,[{index:0},{index:1},{index:2}]);
});

test("a local effect draft owns exact accepted arrays and starts destination-bound playback", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "animate",
    route: "lighting/edit",
  });
  const rendered = frameSet({
    workspaceContext: context({source_kind: "local_effect"}),
    framesByTarget: {keyframes: [
      ["#101010", "#202020"],
      ["#303030", "#404040"],
      ["#505050", "#606060"],
    ]},
    provenance: "local_effect",
  });
  const specification = {
    version: 1,
    type: "shimmer",
    frame_count: 3,
    duration_ms: 90,
    parameters: {depth: 0.6, seed: 824},
  };

  const accepted = reduceLightingWorkspace(state, {
    type: "EFFECT_DRAFT_ACCEPTED",
    specification,
    frame_set: rendered,
    demonstrative_frame: 1,
    source_frame_index: 0,
    autoplay: true,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  state = accepted.state;
  assert.deepEqual(
    accepted.intents.map(intent => intent.type),
    ["cancel-playback", "start-playback", "render-workspace"],
  );
  assert.equal(state.playhead.playing, true);
  assert.equal(state.playhead.index, 1);
  assert.equal(state.effect_draft.demonstrative_frame, 1);
  assert.equal(state.effect_draft.source_frame_index, 0);
  assert.strictEqual(state.effect_draft.board_frame_set, state.preview.board_frame_set);
  assert.deepEqual(
    state.effect_draft.board_frame_set.frames_by_target,
    rendered.frames_by_target,
  );
  assert.deepEqual(state.effect_draft.specification, specification);
  assert.notStrictEqual(state.effect_draft.specification, specification);
  assert.doesNotThrow(() => JSON.stringify(state));

  const apply = reduceLightingWorkspace(state, {type: "APPLY_REQUESTED"});
  assert.equal(apply.intents.length, 1);
  assert.equal(apply.intents[0].type, "apply-board-frame-set");
  assert.strictEqual(apply.intents[0].board_frame_set, state.effect_draft.board_frame_set);
  assert.strictEqual(apply.intents[0].specification, state.effect_draft.specification);

  const completed = reduceLightingWorkspace(state, {
    type: "APPLY_COMPLETED",
    context_key: apply.intents[0].context_key,
    board_frame_set: apply.intents[0].board_frame_set,
  });
  assert.equal(completed.state.effect_draft, null);
  assert.equal(completed.state.preview.board_frame_set, null);
  assert.equal(completed.state.playhead.playing, false);
  assert.deepEqual(
    completed.intents.map(intent => intent.type),
    ["cancel-playback", "render-workspace"],
  );
});

test("reduced motion selects the representative changed frame without autoplay", () => {
  const initial = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "animate",
  });
  const rendered = frameSet({
    workspaceContext: context({source_kind: "local_effect"}),
    framesByTarget: {keyframes: [
      ["#111111", "#222222"],
      ["#AAAAAA", "#BBBBBB"],
      ["#333333", "#444444"],
    ]},
    provenance: "local_effect",
  });
  const accepted = reduceLightingWorkspace(initial, {
    type: "EFFECT_DRAFT_ACCEPTED",
    specification: {type: "pulse"},
    frame_set: rendered,
    demonstrative_frame: 1,
    source_frame_index: 0,
    autoplay: false,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  assert.equal(accepted.state.playhead.playing, false);
  assert.equal(accepted.state.playhead.index, 1);
  assert.deepEqual(
    accepted.intents.map(intent => intent.type),
    ["cancel-playback", "render-workspace"],
  );
  assert.deepEqual(selectBoardProjection(accepted.state).colors, ["#AAAAAA", "#BBBBBB"]);
  const cancelled = reduceLightingWorkspace(accepted.state, {type: "EFFECT_DRAFT_CANCELLED"});
  assert.equal(cancelled.state.effect_draft, null);
  assert.equal(cancelled.state.playhead.index, 0);
  assert.deepEqual(
    cancelled.intents.map(intent => intent.type),
    ["cancel-playback", "render-workspace"],
  );
});

test("a no-change effect explains itself without autoplay or an Apply intent", () => {
  const initial = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "animate",
  });
  const rendered = frameSet({
    workspaceContext: context({source_kind: "local_effect"}),
    provenance: "local_effect",
  });
  const accepted = reduceLightingWorkspace(initial, {
    type: "EFFECT_DRAFT_ACCEPTED",
    specification: {type: "pulse"},
    frame_set: rendered,
    demonstrative_frame: null,
    source_frame_index: 0,
    autoplay: true,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  assert.equal(accepted.state.playhead.playing, false);
  assert.equal(accepted.state.effect_draft.demonstrative_frame, null);
  assert.equal(accepted.intents.some(intent => intent.type === "start-playback"), false);

  const replaced = reduceLightingWorkspace(accepted.state, {
    type: "EFFECT_DRAFT_ACCEPTED",
    specification: {type: "hue_cycle"},
    frame_set: rendered,
    demonstrative_frame: null,
    source_frame_index: 0,
    autoplay: true,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  assert.equal(replaced.state.effect_draft.specification.type, "hue_cycle");
  assert.ok(replaced.state.preview.accepted_epoch > accepted.state.preview.accepted_epoch);

  const apply = reduceLightingWorkspace(accepted.state, {type: "APPLY_REQUESTED"});
  assert.equal(apply.intents.some(intent => intent.type === "apply-board-frame-set"), false);
  assert.equal(apply.state.preview.error.code, "no_effect_change");
});

test("effect playback and accepted arrays cannot leak across workspace context changes", () => {
  const transitions = [
    {type: "DOCUMENT_OPENED", document_epoch: 8, slot: 5, target: "keyframes"},
    {type: "IMPORTED_LIGHTING_OPENED", target: "head"},
    {type: "IMPORTED_LIGHTING_CLOSED"},
    {type: "DESTINATION_CHANGED", slot: 5, target: "head"},
    {type: "TOOL_SELECTED", tool: "paint"},
    {type: "ROUTE_CHANGED", route: "lighting/library"},
  ];
  for (const transition of transitions) {
    let state = createLightingWorkspace({
      documentEpoch: 7,
      slot: 5,
      target: "keyframes",
      tool: "animate",
      route: "lighting/edit",
    });
    const accepted = reduceLightingWorkspace(state, {
      type: "EFFECT_DRAFT_ACCEPTED",
      specification: {type: "sweep"},
      frame_set: frameSet({
        workspaceContext: context({source_kind: "local_effect"}),
        framesByTarget: {keyframes: [
          ["#101010", "#202020"],
          ["#303030", "#404040"],
        ]},
        provenance: "local_effect",
      }),
      demonstrative_frame: 1,
      source_frame_index: 0,
      autoplay: true,
      target_lengths: TARGET_LENGTHS,
      allowed_durations: FIRMWARE_DURATIONS,
    });
    state = accepted.state;
    const staleSession = state.playhead.session_id;
    const staleContextKey = workspaceContextKey(state);

    const changed = reduceLightingWorkspace(state, transition);
    assert.equal(changed.intents[0]?.type, "cancel-playback", transition.type);
    assert.equal(changed.state.effect_draft, null, transition.type);
    assert.equal(changed.state.playhead.playing, false, transition.type);
    const stale = reduceLightingWorkspace(changed.state, {
      type: "PLAYBACK_TICK",
      session_id: staleSession,
      context_key: staleContextKey,
    });
    assert.equal(stale.state, changed.state, transition.type);
    assert.equal(stale.ignored, "stale", transition.type);
  }
});

test("Source projection and Board projection select one accepted timeline entry", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "source",
    route: "lighting/edit",
  });
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_OPENED",
    media: {catalog_id: "item:media", asset_id: "source"},
  }).state;
  const captured = captureWorkspaceAsyncContext(state);
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "a".repeat(32),
    captured,
  }).state;
  const accepted = boardFrameSetFromMappedResult({
    context: {
      ...state.context,
      source_kind: "media_render",
      revision: state.preview.accepted_epoch,
    },
    mappedResult: {
      duration_ms: 48,
      tracks: {
        keyframes: {
          frame_count: 2,
          frames: [
            ["#000001", "#000002"],
            ["#000003", "#000004"],
          ],
        },
      },
    },
    timeline: [
      {index: 0, source_frame_index: 4},
      {index: 1, source_frame_index: 2},
    ],
    provenance: "media_render",
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  state = publish(state, accepted).state;

  assert.deepEqual(state.media.preview_timeline, accepted.timeline);
  assert.equal(selectBoardProjection(state).index, 0);
  assert.deepEqual(selectSourceProjection(state), {
    catalog_id: "item:media",
    preview_session_id: "a".repeat(32),
    source_frame_index: 4,
    timeline_index: 0,
    context_key: workspaceContextKey(state),
  });

  state = reduceLightingWorkspace(state, {type: "PLAYHEAD_SCRUBBED", index: 1}).state;
  assert.equal(selectBoardProjection(state).index, 1);
  assert.equal(selectSourceProjection(state).source_frame_index, 2);

  const staleSession = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    catalog_id: "item:other",
    asset_id: "source",
    preview_session_id: "b".repeat(32),
    captured,
  });
  assert.equal(staleSession.state, state);
  assert.equal(staleSession.ignored, "stale");
});

test("media playback holds Board until the exact next Source frame is ready", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "source",
    route: "lighting/edit",
  });
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_OPENED",
    media: {catalog_id: "item:media", asset_id: "source", requested_revision: 0},
  }).state;
  const captured = captureWorkspaceAsyncContext(state);
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "a".repeat(32),
    captured,
  }).state;
  const accepted = boardFrameSetFromMappedResult({
    context: {...state.context, source_kind: "media_render", revision: 0},
    mappedResult: {
      duration_ms: 48,
      tracks: {keyframes: {
        frame_count: 3,
        frames: [
          ["#000001", "#000002"],
          ["#000003", "#000004"],
          ["#000005", "#000006"],
        ],
      }},
    },
    timeline: [
      {index: 0, source_frame_index: 4},
      {index: 1, source_frame_index: 2},
      {index: 2, source_frame_index: 7},
    ],
    provenance: "media_render",
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  state = reduceLightingWorkspace(state, {
    type: "BOARD_FRAME_SET_ACCEPTED",
    frame_set: accepted,
    media_revision: 0,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  }).state;
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;
  const session = state.playhead.session_id;
  const contextKey = workspaceContextKey(state);

  const tick = reduceLightingWorkspace(state, {
    type: "PLAYBACK_TICK",
    session_id: session,
    context_key: contextKey,
  });
  assert.equal(tick.state, state);
  assert.deepEqual(tick.intents, [{
    type: "prepare-source-frame",
    session_id: session,
    context_key: contextKey,
    from_index: 0,
    timeline_index: 1,
    source_frame_index: 2,
  }]);
  assert.equal(selectBoardProjection(state).index, 0);
  assert.equal(selectSourceProjection(state).source_frame_index, 4);

  const wrong = reduceLightingWorkspace(state, {
    ...tick.intents[0],
    type: "SOURCE_FRAME_READY",
    source_frame_index: 7,
  });
  assert.equal(wrong.state, state);
  assert.equal(wrong.ignored, "stale");

  const ready = reduceLightingWorkspace(state, {
    ...tick.intents[0],
    type: "SOURCE_FRAME_READY",
  });
  state = ready.state;
  assert.equal(selectBoardProjection(state).index, 1);
  assert.equal(selectSourceProjection(state).source_frame_index, 2);
  assert.deepEqual(ready.intents, [{type: "render-board"}]);

  const duplicate = reduceLightingWorkspace(state, {
    ...tick.intents[0],
    type: "SOURCE_FRAME_READY",
  });
  assert.equal(duplicate.state, state);
  assert.equal(duplicate.ignored, "stale");
});

test("expired media sessions clear only the matching id and preserve the draft", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "source",
    route: "lighting/edit",
  });
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_OPENED",
    media: {catalog_id: "item:media", asset_id: "source", requested_transform: {scale: 2}},
  }).state;
  const captured = captureWorkspaceAsyncContext(state);
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "a".repeat(32),
    captured,
  }).state;
  state = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"}).state;
  state = reduceLightingWorkspace(state, {
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: state.preview.request_epoch,
    context_key: state.preview.request_context_key,
    media_revision: 0,
    frame_set: frameSet({
      workspaceContext: context({source_kind: "media_render", revision: 0}),
      framesByTarget: {keyframes: [
        ["#000001", "#000002"],
        ["#000003", "#000004"],
      ]},
    }),
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  }).state;
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;
  assert.equal(state.playhead.playing, true);
  const beforePreview = state.preview;

  const expired = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_INVALIDATED",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "a".repeat(32),
  });
  state = expired.state;

  assert.equal(state.media.preview_session_id, undefined);
  assert.deepEqual(state.media.requested_transform, {scale: 2});
  assert.equal(state.preview, beforePreview);
  assert.equal(state.playhead.playing, false);
  assert.deepEqual(
    expired.intents.map(intent => intent.type),
    ["cancel-playback", "render-workspace"],
  );

  state = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "b".repeat(32),
    captured,
  }).state;
  const newer = state;
  const stale = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_INVALIDATED",
    catalog_id: "item:media",
    asset_id: "source",
    preview_session_id: "a".repeat(32),
  });
  assert.equal(stale.state, newer);
  assert.equal(stale.ignored, "stale");
  assert.equal(stale.state.media.preview_session_id, "b".repeat(32));
});

test("manual paint updates the accepted document frame without a second authority", () => {
  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  const original = frameSet();
  state = publish(state, original).state;
  const oldContextKey = workspaceContextKey(state);

  const result = reduceLightingWorkspace(state, {
    type: "BOARD_COLOR_UPDATED",
    context_key: oldContextKey,
    target: "keyframes",
    frame_index: 0,
    color_index: 1,
    color: "#ABCDEF",
  });
  state = result.state;

  assert.deepEqual(result.intents.map(intent => intent.type), ["cancel-playback", "render-board"]);
  assert.deepEqual(selectBoardProjection(state).colors, ["#FF0000", "#ABCDEF"]);
  assert.deepEqual(original.frames_by_target.keyframes[0], ["#FF0000", "#00FF00"]);
  assert.notEqual(workspaceContextKey(state), oldContextKey);

  const stale = reduceLightingWorkspace(state, {
    type: "BOARD_COLOR_UPDATED",
    context_key: oldContextKey,
    target: "keyframes",
    frame_index: 0,
    color_index: 0,
    color: "#000000",
  });
  assert.equal(stale.state, state);
  assert.equal(stale.ignored, "stale");
});

test("stale context and request epochs cannot publish preview frames", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    tool: "paint",
    route: "lighting/edit",
  });
  let result = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"});
  state = result.state;
  const staleRequestEpoch = state.preview.request_epoch;
  const staleContextKey = state.preview.request_context_key;
  const staleFrameSet = frameSet();

  result = reduceLightingWorkspace(state, {
    type: "DESTINATION_CHANGED",
    slot: 5,
    target: "head",
  });
  state = result.state;

  const before = state;
  result = reduceLightingWorkspace(state, {
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: staleRequestEpoch,
    context_key: staleContextKey,
    frame_set: staleFrameSet,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  assert.equal(result.state, before);
  assert.equal(result.ignored, "stale");
  assert.deepEqual(result.intents, []);

  result = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"});
  state = result.state;
  const currentKey = state.preview.request_context_key;
  result = reduceLightingWorkspace(state, {
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: state.preview.request_epoch - 1,
    context_key: currentKey,
    frame_set: frameSet({
      workspaceContext: context({target: "head", source_kind: "media_render"}),
      framesByTarget: {head: [["#111111", "#222222", "#333333"]]},
      provenance: "media_render",
    }),
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  assert.equal(result.state, state);
  assert.equal(result.ignored, "stale");
});

test("every context change cancels playback before requesting a render", () => {
  const cases = [
    {type: "DOCUMENT_OPENED", document_epoch: 8, slot: 5, target: "keyframes"},
    {type: "DOCUMENT_CLOSED", document_epoch: 8},
    {type: "DESTINATION_CHANGED", slot: 6, target: "keyframes"},
    {type: "TOOL_SELECTED", tool: "source"},
    {type: "MEDIA_OPENED", media: {catalog_id: "media-a", asset_id: "source"}},
    {type: "MEDIA_CANCELLED"},
    {type: "ROUTE_CHANGED", route: "lighting/library"},
  ];

  for (const event of cases) {
    const initial = createLightingWorkspace({
      documentEpoch: 7,
      slot: 5,
      target: "keyframes",
      tool: "paint",
      route: "lighting/edit",
    });
    const result = reduceLightingWorkspace(initial, event);
    assert.equal(result.intents[0]?.type, "cancel-playback", event.type);
    assert.equal(result.intents.at(-1)?.type, "render-workspace", event.type);
  }
});

test("identical internal errors coalesce into one friendly reducer error", () => {
  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  let result = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"});
  state = result.state;
  const event = {
    type: "SEQUENCE_RENDER_FAILED",
    request_epoch: state.preview.request_epoch,
    context_key: state.preview.request_context_key,
    error: {
      code: "invalid_shape",
      label: "frames_by_target.keyframes[0][37]",
      message: "internal parser path leaked",
    },
  };

  result = reduceLightingWorkspace(state, event);
  state = result.state;
  assert.equal(result.intents.filter(intent => intent.type === "show-error").length, 1);
  assert.equal(state.preview.error.title, "Could not update lights");
  assert.doesNotMatch(state.preview.error.message, /frames_by_target|parser|\[37\]/);

  result = reduceLightingWorkspace(state, event);
  assert.equal(result.state, state);
  assert.equal(result.intents.filter(intent => intent.type === "show-error").length, 0);

  const friendly = friendlyWorkspaceError({
    code: "invalid_target",
    label: "spotlight_frames",
    message: "raw internal target mismatch",
  });
  assert.equal(friendly.title, "Could not update lights");
  assert.doesNotMatch(friendly.message, /spotlight_frames|raw internal/);
});

test("a synchronous Board contract failure clears stale output and cancels playback", () => {
  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  state = publish(state, frameSet()).state;
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;

  const result = reduceLightingWorkspace(state, {
    type: "WORKSPACE_ERROR_REPORTED",
    error: {code: "invalid_frame", label: "internal.frame_data[0]"},
  });
  state = result.state;
  assert.deepEqual(
    result.intents.map(intent => intent.type),
    ["cancel-playback", "show-error", "render-workspace"],
  );
  assert.equal(state.playhead.playing, false);
  assert.equal(state.preview.board_frame_set, null);
  assert.equal(selectBoardProjection(state), null);

  const duplicate = reduceLightingWorkspace(state, {
    type: "WORKSPACE_ERROR_REPORTED",
    error: {code: "invalid_frame", label: "another internal path"},
  });
  assert.equal(duplicate.state, state);
  assert.deepEqual(duplicate.intents, []);
});

test("a Per-key playback session cannot tick after switching to Head matrix", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    route: "lighting/edit",
  });
  state = publish(state, frameSet()).state;
  let result = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"});
  state = result.state;
  const staleSession = state.playhead.session_id;
  const staleContextKey = workspaceContextKey(state);
  assert.equal(state.playhead.playing, true);

  result = reduceLightingWorkspace(state, {
    type: "DESTINATION_CHANGED",
    slot: 5,
    target: "head",
  });
  assert.equal(result.intents[0]?.type, "cancel-playback");
  state = result.state;

  state = publish(state, frameSet({
    workspaceContext: context({target: "head"}),
    framesByTarget: {
      head: [
        ["#0000AA", "#0000BB", "#0000CC"],
        ["#0011AA", "#0011BB", "#0011CC"],
      ],
    },
  })).state;
  const beforeTick = state;
  result = reduceLightingWorkspace(state, {
    type: "PLAYBACK_TICK",
    session_id: staleSession,
    context_key: staleContextKey,
  });

  assert.equal(result.state, beforeTick);
  assert.equal(result.ignored, "stale");
  assert.equal(state.playhead.playing, false);
  assert.deepEqual(selectBoardProjection(state).colors, ["#0000AA", "#0000BB", "#0000CC"]);
  assert.equal(selectBoardProjection(state).target, "head");
});

test("workspace state remains serializable and contains no timer authority", () => {
  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  state = publish(state, frameSet()).state;
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;

  const roundTrip = JSON.parse(JSON.stringify(state));
  assert.equal(roundTrip.playhead.playing, true);
  assert.equal(roundTrip.preview.board_frame_set.frame_count, 1);
  assert.equal(Object.hasOwn(roundTrip, "timer"), false);
  assert.equal(Object.hasOwn(roundTrip.playhead, "timer"), false);
});

test("partial Board projection refreshes timeline thumbnails from the accepted frame set", () => {
  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  const accepted = frameSet({
    workspaceContext: context({source_kind: "local_effect"}),
    framesByTarget: {
      keyframes: [
        ["#102030", "#405060"],
        ["#708090", "#A0B0C0"],
      ],
    },
    provenance: "local_effect",
  });
  state = publish(state, accepted).state;
  const frameItems = [
    fakeFrameItem(["#AAAAAA", "#BBBBBB"]),
    fakeFrameItem(["#CCCCCC", "#DDDDDD"]),
  ];

  paintBoardProjection(state, {
    destination_key: workspaceDestinationKey(state),
    pixels: [fakePixel(0), fakePixel(1)],
    frame_items: frameItems,
  });

  assert.deepEqual(
    frameItems.map(item => item.swatches.map(swatch => swatch.style.background)),
    accepted.frames_by_target.keyframes,
  );
  assert.equal(frameItems[0].classList.contains("active"), true);
  assert.equal(frameItems[1].classList.contains("active"), false);
});

test("playback runtime keeps one timer and one lifecycle listener across repeated starts", () => {
  const platform = fakePlaybackPlatform();
  const dispatched = [];
  const runtime = createLightingPlaybackRuntime({
    dispatch: event => dispatched.push(event),
    setTimer: platform.setTimer,
    clearTimer: platform.clearTimer,
    lifecycleTarget: platform.lifecycleTarget,
  });

  assert.equal(platform.listenerCount("pagehide"), 1);
  for (let session = 1; session <= 25; session += 1) {
    runtime.execute({
      type: "start-playback",
      session_id: session,
      context_key: `context-${session}`,
      duration_ms: 48,
    });
    assert.equal(platform.timers.size, 1);
    assert.equal(platform.listenerCount("pagehide"), 1);
    const staleCallback = [...platform.timers.values()][0].callback;
    runtime.execute({
      type: "cancel-playback",
      session_id: session,
      context_key: `context-${session}`,
    });
    assert.equal(platform.timers.size, 0);
    staleCallback();
    assert.equal(dispatched.length, 0, "a queued callback must be inert after cancellation");
  }

  runtime.execute({
    type: "start-playback",
    session_id: 26,
    context_key: "context-26",
    duration_ms: 48,
  });
  platform.emit("pagehide");
  assert.equal(platform.timers.size, 0);
  assert.deepEqual(dispatched, [{type: "PAUSE_REQUESTED"}]);

  runtime.dispose();
  assert.equal(platform.timers.size, 0);
  assert.equal(platform.listenerCount("pagehide"), 0);
});

test("destination sessions isolate Neon, CyberBoard, and Relic board pixels", () => {
  const cases = [
    {
      name: "Neon Per-key to Head matrix",
      sourceTarget: "axial",
      sourceLength: 89,
      destinationTarget: "head",
      destinationLength: 230,
      visibleLength: 230,
    },
    {
      name: "CyberBoard switches to 40x5 display",
      sourceTarget: "keyframes",
      sourceLength: 90,
      destinationTarget: "frames",
      destinationLength: 200,
      visibleLength: 200,
    },
    {
      name: "Relic keys to edge",
      sourceTarget: "keyframes",
      sourceLength: 90,
      destinationTarget: "spotlight_frames",
      destinationLength: 24,
      visibleLength: 7,
    },
  ];
  const colors = (length, offset) => Array.from({length}, (_, index) => (
    `#${((offset + index) & 0xFFFFFF).toString(16).padStart(6, "0").toUpperCase()}`
  ));

  for (const scenario of cases) {
    const targetLengths = {
      [scenario.sourceTarget]: scenario.sourceLength,
      [scenario.destinationTarget]: scenario.destinationLength,
    };
    const sourceTrack = {
      frame_data: [
        {frame_index: 0, frame_RGB: colors(scenario.sourceLength, 0x110000)},
        {frame_index: 1, frame_RGB: colors(scenario.sourceLength, 0x220000)},
      ],
    };
    const destinationTrack = {
      frame_data: [
        {frame_index: 0, frame_RGB: colors(scenario.destinationLength, 0x330000)},
        {frame_index: 1, frame_RGB: colors(scenario.destinationLength, 0x440000)},
      ],
    };
    const originalTracks = JSON.parse(JSON.stringify({sourceTrack, destinationTrack}));
    let state = createLightingWorkspace({
      documentEpoch: 9,
      slot: 5,
      target: scenario.sourceTarget,
    });
    const platform = fakePlaybackPlatform();
    let board = null;
    let runtime;

    const paint = () => paintBoardProjection(state, {
      destination_key: board.destinationKey,
      pixels: board.pixels,
      frame_items: board.frameItems,
    });
    const execute = decision => {
      state = decision.state;
      for (const intent of decision.intents) {
        if (["start-playback", "cancel-playback"].includes(intent.type)) {
          runtime.execute(intent);
        } else if (intent.type === "render-board") {
          paint();
        }
      }
      return decision;
    };
    const dispatch = event => execute(reduceLightingWorkspace(state, event));
    runtime = createLightingPlaybackRuntime({
      dispatch,
      setTimer: platform.setTimer,
      clearTimer: platform.clearTimer,
      lifecycleTarget: platform.lifecycleTarget,
    });
    const publishTrack = (target, track) => dispatch({
      type: "BOARD_FRAME_SET_ACCEPTED",
      frame_set: boardFrameSetFromDocument({
        context: {
          document_epoch: state.context.document_epoch,
          slot: state.context.slot,
          target,
          source_kind: "document",
          revision: state.preview.accepted_epoch,
        },
        track,
        durationMs: 48,
        targetLengths,
        allowedDurations: FIRMWARE_DURATIONS,
      }),
      target_lengths: targetLengths,
      allowed_durations: FIRMWARE_DURATIONS,
    });
    const bindBoard = visibleLength => {
      board = {
        destinationKey: workspaceDestinationKey(state),
        pixels: Array.from({length: visibleLength}, (_, index) => fakePixel(index)),
        frameItems: [fakeFrameItem(), fakeFrameItem()],
      };
      paint();
    };

    publishTrack(scenario.sourceTarget, sourceTrack);
    bindBoard(scenario.sourceLength);
    const play = dispatch({type: "PLAY_REQUESTED"});
    const staleSession = play.state.playhead.session_id;
    const staleContextKey = workspaceContextKey(play.state);
    const staleTimerCallback = [...platform.timers.values()][0].callback;

    dispatch({
      type: "DESTINATION_CHANGED",
      slot: 5,
      target: scenario.destinationTarget,
    });
    assert.equal(platform.timers.size, 0, scenario.name);
    const oldBoardColors = board.pixels.map(pixel => pixel.style.background);
    publishTrack(scenario.destinationTarget, destinationTrack);
    assert.equal(paint(), null, `${scenario.name}: stale destination DOM accepted paint`);
    assert.deepEqual(
      board.pixels.map(pixel => pixel.style.background),
      oldBoardColors,
      `${scenario.name}: destination colors reached stale DOM`,
    );
    bindBoard(scenario.visibleLength);
    const expected = destinationTrack.frame_data[0].frame_RGB.slice(0, scenario.visibleLength);
    assert.deepEqual(board.pixels.map(pixel => pixel.style.background), expected, scenario.name);

    const beforeStaleTick = state;
    staleTimerCallback();
    assert.equal(state, beforeStaleTick, `${scenario.name}: cleared callback changed state`);
    const stale = dispatch({
      type: "PLAYBACK_TICK",
      session_id: staleSession,
      context_key: staleContextKey,
    });
    assert.equal(stale.ignored, "stale", scenario.name);
    assert.deepEqual(board.pixels.map(pixel => pixel.style.background), expected, scenario.name);
    assert.deepEqual({sourceTrack, destinationTrack}, originalTracks, scenario.name);
    runtime.dispose();
  }
});

test("destination playheads remain independent", () => {
  const targetLengths = {keyframes: 2, head: 3};
  const makeSet = (target, frames) => createBoardFrameSet({
    context: context({target}),
    frames_by_target: {[target]: frames},
    frame_count: frames.length,
    duration_ms: 48,
    timeline: frames.map((_, index) => ({index})),
    provenance: "document",
  }, {targetLengths, allowedDurations: FIRMWARE_DURATIONS});
  const accept = (state, value) => reduceLightingWorkspace(state, {
    type: "BOARD_FRAME_SET_ACCEPTED",
    frame_set: value,
    target_lengths: targetLengths,
    allowed_durations: FIRMWARE_DURATIONS,
  }).state;

  let state = createLightingWorkspace({documentEpoch: 7, slot: 5, target: "keyframes"});
  state = accept(state, makeSet("keyframes", [
    ["#100000", "#100001"],
    ["#200000", "#200001"],
    ["#300000", "#300001"],
  ]));
  const acceptedKeyframes = state.preview.board_frame_set;
  const acceptedKeyframeArrays = JSON.parse(JSON.stringify(acceptedKeyframes.frames_by_target));
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;
  for (let tick = 0; tick < 2; tick += 1) {
    state = reduceLightingWorkspace(state, {
      type: "PLAYBACK_TICK",
      session_id: state.playhead.session_id,
      context_key: workspaceContextKey(state),
    }).state;
  }
  assert.equal(state.playhead.index, 2);
  assert.equal(state.preview.board_frame_set, acceptedKeyframes);
  assert.deepEqual(state.preview.board_frame_set.frames_by_target, acceptedKeyframeArrays);

  state = reduceLightingWorkspace(state, {
    type: "DESTINATION_CHANGED",
    target: "head",
  }).state;
  state = accept(state, makeSet("head", [
    ["#001000", "#001001", "#001002"],
    ["#002000", "#002001", "#002002"],
    ["#003000", "#003001", "#003002"],
  ]));
  state = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"}).state;
  state = reduceLightingWorkspace(state, {
    type: "PLAYBACK_TICK",
    session_id: state.playhead.session_id,
    context_key: workspaceContextKey(state),
  }).state;
  assert.equal(state.playhead.index, 1);

  state = reduceLightingWorkspace(state, {
    type: "DESTINATION_CHANGED",
    target: "keyframes",
  }).state;
  assert.equal(state.playhead.index, 2);
});

test("stale selected-frame and full-render epochs cannot collide after same-destination transitions", () => {
  const transitions = [
    {type: "TOOL_SELECTED", tool: "source"},
    {type: "ROUTE_CHANGED", route: "lighting/library"},
    {type: "MEDIA_OPENED", media: {catalog_id: "media-a", asset_id: "source"}},
    {type: "MEDIA_CANCELLED"},
  ];

  for (const transition of transitions) {
    let state = createLightingWorkspace({
      documentEpoch: 7,
      slot: 5,
      target: "keyframes",
      route: "lighting/edit",
      tool: "paint",
    });
    if (transition.type === "MEDIA_CANCELLED") {
      state = reduceLightingWorkspace(state, {
        type: "MEDIA_OPENED",
        media: {catalog_id: "media-a", asset_id: "source"},
      }).state;
    }
    let oldRequest = reduceLightingWorkspace(state, {type: "FRAME_RENDER_STARTED"});
    state = oldRequest.state;
    const oldAsyncContext = captureWorkspaceAsyncContext(state);
    assert.equal(workspaceAsyncContextMatches(state, oldAsyncContext), true);
    const oldEpoch = state.preview.request_epoch;
    const oldKey = state.preview.request_context_key;
    const oldSession = state.playhead.session_id;
    state = reduceLightingWorkspace(state, transition).state;
    assert.equal(workspaceAsyncContextMatches(state, oldAsyncContext), false, transition.type);
    const newRequest = reduceLightingWorkspace(state, {type: "FRAME_RENDER_STARTED"});
    state = newRequest.state;

    assert.equal(state.preview.request_epoch, oldEpoch, `${transition.type}: epoch should collide`);
    assert.notEqual(state.preview.request_context_key, oldKey, `${transition.type}: key must not collide`);
    for (const type of ["FRAME_RENDER_ACCEPTED", "SEQUENCE_RENDER_ACCEPTED"]) {
      const stale = reduceLightingWorkspace(state, {
        type,
        request_epoch: oldEpoch,
        context_key: oldKey,
        frame_set: frameSet(),
        target_lengths: TARGET_LENGTHS,
        allowed_durations: FIRMWARE_DURATIONS,
      });
      assert.equal(stale.state, state, `${transition.type}/${type}`);
      assert.equal(stale.ignored, "stale", `${transition.type}/${type}`);
    }
    const staleSource = reduceLightingWorkspace(state, {
      type: "SOURCE_FRAME_READY",
      session_id: oldSession,
      context_key: oldKey,
    });
    assert.equal(staleSource.state, state, transition.type);
    assert.equal(staleSource.ignored, "stale", transition.type);
  }
});

test("selected media frames preserve the playhead without promoting partial work", () => {
  let state = createLightingWorkspace({
    documentEpoch: 7,
    slot: 5,
    target: "keyframes",
    route: "lighting/edit",
    tool: "paint",
  });
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_OPENED",
    media: {catalog_id: "media-a", asset_id: "source-a", requested_revision: 0},
  }).state;
  const captured = captureWorkspaceAsyncContext(state);
  state = reduceLightingWorkspace(state, {
    type: "MEDIA_SESSION_READY",
    captured,
    catalog_id: "media-a",
    asset_id: "source-a",
    preview_session_id: "11111111-1111-4111-8111-111111111111",
  }).state;

  let started = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"});
  state = started.state;
  const initialSequence = createBoardFrameSet({
    context: context({source_kind: "media_render", revision: 0}),
    frames_by_target: {
      keyframes: [
        ["#100000", "#001000"],
        ["#200000", "#002000"],
      ],
    },
    frame_count: 2,
    duration_ms: 90,
    timeline: [
      {index: 0, source_frame_index: 0},
      {index: 1, source_frame_index: 1},
    ],
    provenance: "media_render",
  }, {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS});
  state = reduceLightingWorkspace(state, {
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: state.preview.request_epoch,
    context_key: state.preview.request_context_key,
    media_revision: 0,
    frame_set: initialSequence,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  }).state;
  state = reduceLightingWorkspace(state, {type: "PLAYHEAD_SCRUBBED", index: 1}).state;
  state = reduceLightingWorkspace(state, {
    type: "TRANSFORM_REQUESTED",
    media_revision: 1,
    transform: {version: 1},
  }).state;
  const acceptedSequence = state.preview.board_frame_set;

  started = reduceLightingWorkspace(state, {type: "FRAME_RENDER_STARTED"});
  state = started.state;
  const selected = boardFrameSetFromMappedFrame({
    context: context({source_kind: "media_render", revision: 1}),
    mappedFrame: {
      tracks: {
        keyframes: {pixels: 2, colors: ["#ABCDEF", "#123456"]},
      },
    },
    timelineEntry: {index: 1, source_frame_index: 5, duration_ms: 90},
    targetLengths: TARGET_LENGTHS,
    allowedDurations: FIRMWARE_DURATIONS,
  });
  const frameAccepted = reduceLightingWorkspace(state, {
    type: "FRAME_RENDER_ACCEPTED",
    request_epoch: state.preview.request_epoch,
    context_key: state.preview.request_context_key,
    media_revision: 1,
    frame_index: 1,
    frame_set: selected,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  });
  state = frameAccepted.state;

  assert.equal(frameAccepted.ignored, undefined);
  assert.strictEqual(state.preview.board_frame_set, acceptedSequence);
  assert.equal(state.preview.selected_frame.timeline_index, 1);
  assert.equal(state.media.accepted_revision, undefined);
  assert.equal(state.media.accepted_frame_revision, 1);
  assert.equal(state.playhead.index, 1);
  assert.deepEqual(selectBoardProjection(state).colors, ["#ABCDEF", "#123456"]);
  assert.equal(selectBoardProjection(state).frame_set.frame_count, 2);
  assert.deepEqual(selectSourceProjection(state), {
    catalog_id: "media-a",
    preview_session_id: "11111111-1111-4111-8111-111111111111",
    source_frame_index: 5,
    timeline_index: 1,
    context_key: workspaceContextKey(state),
  });
  const blockedPlayback = reduceLightingWorkspace(state, {type: "PLAY_REQUESTED"});
  assert.equal(blockedPlayback.state.playhead.playing, false);
  assert.equal(blockedPlayback.ignored, "stale");

  state = reduceLightingWorkspace(state, {type: "SEQUENCE_RENDER_STARTED"}).state;
  const finalSequence = createBoardFrameSet({
    context: context({source_kind: "media_render", revision: 1}),
    frames_by_target: {
      keyframes: [
        ["#AAAAAA", "#BBBBBB"],
        ["#ABCDEF", "#123456"],
      ],
    },
    frame_count: 2,
    duration_ms: 90,
    timeline: [
      {index: 0, source_frame_index: 4},
      {index: 1, source_frame_index: 5},
    ],
    provenance: "media_render",
  }, {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS});
  state = reduceLightingWorkspace(state, {
    type: "SEQUENCE_RENDER_ACCEPTED",
    request_epoch: state.preview.request_epoch,
    context_key: state.preview.request_context_key,
    media_revision: 1,
    frame_set: finalSequence,
    target_lengths: TARGET_LENGTHS,
    allowed_durations: FIRMWARE_DURATIONS,
  }).state;

  assert.equal(state.preview.selected_frame, null);
  assert.equal(state.media.accepted_revision, 1);
  assert.deepEqual(selectBoardProjection(state).colors, ["#ABCDEF", "#123456"]);
});
