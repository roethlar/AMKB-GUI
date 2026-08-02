"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  boardFrameSetFromDocument,
  boardFrameSetFromLocalEffect,
  boardFrameSetFromMappedResult,
  createBoardFrameSet,
  createLightingWorkspace,
  friendlyWorkspaceError,
  projectBoardFrame,
  reduceLightingWorkspace,
  selectBoardProjection,
  workspaceContextKey,
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

test("document, local effect, media, and procedural sources share one BoardFrameSet contract", () => {
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

  assert.deepEqual(mediaSet.frames_by_target, proceduralSet.frames_by_target);
  assert.equal(mediaSet.provenance, "media_render");
  assert.equal(proceduralSet.provenance, "procedural_result");
  assert.deepEqual(projectBoardFrame(
    proceduralSet,
    "head",
    1,
    {targetLengths: TARGET_LENGTHS, allowedDurations: FIRMWARE_DURATIONS},
  ), ["#200001", "#200002", "#200003"]);
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
