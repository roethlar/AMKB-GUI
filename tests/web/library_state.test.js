"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  compatibleProfileSections,
  createLibraryRequestEpochs,
  createLightingProvenance,
  createMediaDraft,
  libraryCatalogQuery,
  lightingProvenanceForPage,
  mediaDraftCanApply,
  nextCatalogIndex,
  nextMediaRenderEpoch,
  normalizeProfileSections,
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
  const frameReady = reduceMediaDraft(initial, {
    type: "FRAME_RENDER_SUCCEEDED",
    revision: 0,
    transform: transform({offset_x: 0.125}),
    effects: [],
    resolvedTransforms: [],
  });
  assert.equal(frameReady.status, "draft");
  assert.equal(frameReady.revision, 0);
  assert.equal(frameReady.acceptedRevision, null);
  assert.equal(frameReady.transform.offset_x, 0.125);
  assert.equal(mediaDraftCanApply(frameReady), false);
  assert.strictEqual(reduceMediaDraft(frameReady, {
    type: "FRAME_RENDER_SUCCEEDED",
    revision: 1,
    transform: transform(),
    effects: [],
    resolvedTransforms: [],
  }), frameReady);

  const rendering = reduceMediaDraft(frameReady, {
    type: "RENDER_REQUESTED",
    epoch: 4,
    revision: 0,
  });
  const stale = reduceMediaDraft(rendering, {
    type: "RENDER_SUCCEEDED",
    epoch: 3,
    revision: 0,
    mappedResult: {tracks: {}},
  });
  assert.strictEqual(stale, rendering);
  const ready = reduceMediaDraft(rendering, {
    type: "RENDER_SUCCEEDED",
    epoch: 4,
    revision: 0,
    transform: transform({offset_x: 0.25}),
    effects: [],
    resolvedTransforms: [],
    mappedResult: {tracks: {axial: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.equal(ready.status, "ready");
  assert.equal(ready.acceptedRevision, 0);
  assert.equal(mediaDraftCanApply(ready), true);
  assert.deepEqual(ready.transform, transform({offset_x: 0.25}));
  assert.deepEqual(ready.resolvedTransforms, []);
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
  draft = reduceMediaDraft(draft, {type: "RENDER_REQUESTED", epoch: 1, revision: 0});
  draft = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 1,
    revision: 0,
    transform: transform(),
    effects: [],
    resolvedTransforms: [],
    mappedResult: {tracks: {frames: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.equal(mediaDraftCanApply(draft), true);
  const transformed = reduceMediaDraft(draft, {
    type: "TRANSFORM_CHANGED",
    transform: transform({offset_x: 0.25}),
  });
  assert.equal(transformed.status, "draft");
  assert.equal(transformed.revision, 1);
  assert.equal(transformed.acceptedRevision, null);
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

test("a render result atomically adopts canonical Move & zoom state", () => {
  let draft = createMediaDraft({
    catalogId: "item:11111111-1111-4111-8111-111111111111",
    source: {
      asset_id: "22222222-2222-4222-8222-222222222222",
      mime_type: "image/png",
      width: 40,
      height: 5,
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
    transform: transform({offset_x: 8}),
  });
  const effect = {
    version: 1,
    type: "move_zoom",
    frame_count: 2,
    duration_ms: 90,
    parameters: {
      start_transform: transform(),
      end_transform: transform({offset_x: 8, scale_x: 2, scale_y: 2}),
    },
  };
  const resolvedTransforms = [
    transform(),
    transform({offset_x: 0.5, scale_x: 2, scale_y: 2}),
  ];
  draft = reduceMediaDraft(draft, {type: "RENDER_REQUESTED", epoch: 7, revision: 0});
  draft = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 7,
    revision: 0,
    transform: transform(),
    effects: [effect],
    resolvedTransforms,
    mappedResult: {tracks: {frames: {frame_count: 2, frames: [[], []]}}},
  });
  assert.deepEqual(draft.transform, transform());
  assert.deepEqual(draft.effects, [effect]);
  assert.deepEqual(draft.resolvedTransforms, resolvedTransforms);
  assert.equal(Object.isFrozen(draft.resolvedTransforms), true);
});

test("only the exact current media revision can become Apply-ready", () => {
  let draft = createMediaDraft({
    catalogId: "item:11111111-1111-4111-8111-111111111111",
    source: {
      asset_id: "22222222-2222-4222-8222-222222222222",
      mime_type: "image/png",
      width: 40,
      height: 5,
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
  assert.equal(draft.revision, 0);
  assert.equal(draft.acceptedRevision, null);

  draft = reduceMediaDraft(draft, {
    type: "RENDER_REQUESTED",
    epoch: 10,
    revision: 0,
  });
  draft = reduceMediaDraft(draft, {
    type: "TRANSFORM_CHANGED",
    transform: transform({offset_x: 0.25}),
  });
  assert.equal(draft.revision, 1);
  const stale = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 10,
    revision: 0,
    transform: transform(),
    effects: [],
    resolvedTransforms: [],
    mappedResult: {tracks: {frames: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.strictEqual(stale, draft);
  assert.equal(mediaDraftCanApply(stale), false);

  draft = reduceMediaDraft(draft, {
    type: "RENDER_REQUESTED",
    epoch: 11,
    revision: 1,
  });
  const wrongRevision = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 11,
    revision: 0,
    transform: transform(),
    effects: [],
    resolvedTransforms: [],
    mappedResult: {tracks: {frames: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.strictEqual(wrongRevision, draft);

  const discarded = reduceMediaDraft(draft, {
    type: "RENDER_DISCARDED",
    epoch: 11,
    revision: 1,
  });
  assert.equal(discarded.status, "draft");
  assert.equal(mediaDraftCanApply(discarded), false);

  draft = reduceMediaDraft(discarded, {
    type: "RENDER_REQUESTED",
    epoch: 12,
    revision: 1,
  });

  const ready = reduceMediaDraft(draft, {
    type: "RENDER_SUCCEEDED",
    epoch: 12,
    revision: 1,
    transform: transform({offset_x: 0.25}),
    effects: [],
    resolvedTransforms: [],
    mappedResult: {tracks: {frames: {frame_count: 1, frames: [["#000000"]]}}},
  });
  assert.equal(ready.acceptedRevision, 1);
  assert.equal(mediaDraftCanApply(ready), true);
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

test("mixed Library filters project exact paginated catalog queries", () => {
  assert.equal(
    libraryCatalogQuery({filter: "all", page: 2, limit: 12, query: " violet "}),
    "page=2&limit=12&removed=false&query=violet",
  );
  assert.equal(
    libraryCatalogQuery({filter: "lighting", page: 1, limit: 12}),
    "page=1&limit=12&removed=false&kind=lighting",
  );
  assert.equal(
    libraryCatalogQuery({filter: "sources", page: 1, limit: 12}),
    "page=1&limit=12&removed=false&kind=media_source",
  );
  assert.equal(
    libraryCatalogQuery({filter: "keymaps", page: 1, limit: 12}),
    "page=1&limit=12&removed=false&kind=keyboard_profile",
  );
  assert.equal(
    libraryCatalogQuery({filter: "removed", page: 1, limit: 12}),
    "page=1&limit=12&removed=true",
  );
  assert.throws(
    () => libraryCatalogQuery({filter: "partial", page: 1, limit: 12}),
    /filter/i,
  );
});

test("profile selection keeps only server-approved section statuses", () => {
  const plan = {
    sections: {
      keymap: {status: "exact"},
      macros: {status: "portable"},
      lighting: {status: "blocked"},
    },
  };
  assert.deepEqual(compatibleProfileSections(plan), ["keymap", "macros"]);
  assert.deepEqual(
    normalizeProfileSections(plan, ["lighting", "macros", "macros", "keymap"]),
    ["keymap", "macros"],
  );
  assert.throws(
    () => normalizeProfileSections(plan, ["lighting"]),
    /compatible profile section/i,
  );
});

test("Library request leases reject stale filters and superseded mutations", () => {
  const requests = createLibraryRequestEpochs();
  const first = requests.begin("mutation", 7);
  assert.equal(first.current(7), true);
  assert.equal(first.current(8), false);
  const second = requests.begin("mutation", 8);
  assert.equal(first.current(7), false);
  assert.equal(second.current(8), true);
  first.release();
  assert.equal(second.current(8), true);
  second.release();
  assert.equal(second.current(8), false);
});

test("Library grid navigation follows rows and boundary keys", () => {
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "ArrowLeft"}), 3);
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "ArrowRight"}), 5);
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "ArrowUp"}), 1);
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "ArrowDown"}), 7);
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "Home"}), 0);
  assert.equal(nextCatalogIndex({index: 4, count: 8, columns: 3, key: "End"}), 7);
  assert.equal(nextCatalogIndex({index: 0, count: 8, columns: 3, key: "ArrowLeft"}), 0);
});
