"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  createLightingProvenance,
  createMediaDraft,
  lightingProvenanceForPage,
  mediaDraftCanApply,
  nextMediaRenderEpoch,
  reduceMediaDraft,
} = require(path.join(
  __dirname,
  "../../am_configurator/web/library_state.js",
));

function transform(changes = {}) {
  return {
    version: 1,
    offset_x: 0,
    offset_y: 0,
    scale_x: 1,
    scale_y: 1,
    aspect_locked: true,
    sampling: "box",
    background: "#000000",
    ...changes,
  };
}

test("a banked media draft stays immutable across render epochs", () => {
  const initial = createMediaDraft({
    catalogId: "item:11111111-1111-4111-8111-111111111111",
    source: {
      asset_id: "22222222-2222-4222-8222-222222222222",
      mime_type: "image/png",
      width: 1600,
      height: 900,
      frame_count: 1,
      duration_ms: 0,
    },
    destination: {
      productId: "NEON80",
      target: "axial",
      targets: ["axial"],
      width: 17,
      height: 6,
    },
    transform: transform(),
  });
  const before = JSON.stringify(initial.source);
  const rendering = reduceMediaDraft(initial, {
    type: "RENDER_REQUESTED",
    epoch: 4,
  });
  const stale = reduceMediaDraft(rendering, {
    type: "RENDER_SUCCEEDED",
    epoch: 3,
    mappedResult: {tracks: {}},
  });
  assert.strictEqual(stale, rendering);
  const ready = reduceMediaDraft(rendering, {
    type: "RENDER_SUCCEEDED",
    epoch: 4,
    mappedResult: {tracks: {axial: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.equal(ready.status, "ready");
  assert.equal(mediaDraftCanApply(ready), true);
  assert.equal(JSON.stringify(ready.source), before);
});

test("cancelling discards only the draft and retains its banked catalog identity", () => {
  const initial = createMediaDraft({
    catalogId: "item:11111111-1111-4111-8111-111111111111",
    source: {
      asset_id: "22222222-2222-4222-8222-222222222222",
      mime_type: "image/gif",
      width: 400,
      height: 200,
      frame_count: 8,
      duration_ms: 720,
    },
    destination: {
      productId: "80",
      target: "keyframes",
      targets: ["keyframes", "spotlight_frames"],
      width: 18,
      height: 7,
    },
    transform: transform(),
  });
  const cancelled = reduceMediaDraft(initial, {type: "CANCELLED"});
  assert.equal(cancelled.status, "cancelled");
  assert.equal(cancelled.catalogId, initial.catalogId);
  assert.deepEqual(cancelled.source, initial.source);
  assert.equal(cancelled.mappedResult, null);
  assert.equal(mediaDraftCanApply(cancelled), false);
});

test("transform and effect changes invalidate an accepted preview", () => {
  let draft = createMediaDraft({
    catalogId: "item:11111111-1111-4111-8111-111111111111",
    source: {
      asset_id: "22222222-2222-4222-8222-222222222222",
      mime_type: "image/bmp",
      width: 40,
      height: 20,
      frame_count: 1,
      duration_ms: 0,
    },
    destination: {
      productId: "CB04",
      target: "frames",
      targets: ["frames"],
      width: 40,
      height: 5,
    },
    transform: transform(),
  });
  draft = reduceMediaDraft(draft, {type: "RENDER_REQUESTED", epoch: 1});
  draft = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 1,
    mappedResult: {tracks: {frames: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.equal(mediaDraftCanApply(draft), true);
  const transformed = reduceMediaDraft(draft, {
    type: "TRANSFORM_CHANGED",
    transform: transform({offset_x: 0.25}),
  });
  assert.equal(transformed.status, "draft");
  assert.equal(transformed.mappedResult, null);
  const effected = reduceMediaDraft(transformed, {
    type: "EFFECTS_CHANGED",
    effects: [{
      version: 1,
      type: "pulse",
      frame_count: 8,
      duration_ms: 90,
      parameters: {minimum_brightness: 0.2},
    }],
  });
  assert.equal(effected.effects.length, 1);
  assert.equal(mediaDraftCanApply(effected), false);
});

test("render epochs are process-safe and strictly increase across reopened drafts", () => {
  const seeded = nextMediaRenderEpoch(0, 1_700_000_000_000);
  assert.equal(seeded, 1_700_000_000_000_000);
  assert.equal(
    nextMediaRenderEpoch(seeded, 1_700_000_000_000),
    seeded + 1,
  );
  assert.throws(
    () => nextMediaRenderEpoch(Number.MAX_SAFE_INTEGER, 1),
    /exhausted/,
  );
});

test("saved-lighting provenance survives exact pages and expires after edits", () => {
  const page = {
    page_index: 5,
    lightness: 72,
    speed_ms: 90,
    keyframes: {
      valid: 1,
      frame_num: 1,
      frame_data: [{frame_index: 0, frame_RGB: ["#112233"]}],
    },
  };
  const effect = {
    version: 1,
    type: "pulse",
    frame_count: 8,
    duration_ms: 90,
    parameters: {minimum_brightness: 0.2},
  };
  const provenance = createLightingProvenance({
    slot: 5,
    target: "keyframes",
    sourceCatalogId: null,
    transform: null,
    effects: [effect],
    page,
  });
  assert.deepEqual(
    lightingProvenanceForPage(provenance, {
      slot: 5,
      target: "keyframes",
      page,
    }),
    {
      source_catalog_id: null,
      transform: null,
      effects: [effect],
    },
  );
  const changed = structuredClone(page);
  changed.lightness = 71;
  assert.equal(
    lightingProvenanceForPage(provenance, {
      slot: 5,
      target: "keyframes",
      page: changed,
    }),
    null,
  );
});
