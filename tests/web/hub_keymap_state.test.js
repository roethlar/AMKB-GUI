"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  createHubKeymapState,
  reduceHubKeymapState,
} = require(path.join(
  __dirname,
  "../../am_configurator/web/hub_keymap_state.js",
));

function profile() {
  return {
    schema_version: 1,
    identity: {
      ecosystem: "via",
      family: "Fixture Pad",
      wire_identity: "CAFE:BEEF",
      endpoint: {vid: 0xcafe, pid: 0xbeef, transport: "hid"},
      protocol: {via_protocol: 9},
      definition: {source: "user_import", hash: `sha256-${"ab".repeat(32)}`},
    },
    capabilities: {
      keymap: {layers: 2, keys_per_layer: 2, encoders: 0},
    },
    keymap: {
      layers: [
        {index: 0, keys: [
          {key: "K_R0_C0", code: 0x0004},
          {key: "K_R0_C1", code: 0x0005},
        ]},
        {index: 1, keys: [
          {key: "K_R0_C0", code: 0x0006},
          {key: "K_R0_C1", code: 0x0007},
        ]},
      ],
      matrix: {
        rows: 1,
        cols: 2,
        map: {K_R0_C0: [0, 0], K_R0_C1: [0, 1]},
      },
    },
    macros: [{slot: 0, events: [{tap: 0x0004}]}],
    provenance: {
      "/identity": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/capabilities": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/keymap": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/macros": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
    },
  };
}

function layout() {
  return [
    {key: "K_R0_C0", matrix_row: 0, matrix_col: 0, x: 0, y: 0, width: 45, height: 86, rotation: 0},
    {key: "K_R0_C1", matrix_row: 0, matrix_col: 1, x: 50, y: 0, width: 45, height: 86, rotation: 0},
  ];
}

function target() {
  return {
    ecosystem: "via",
    address: "hid:fixture-a",
    definition: {name: "Fixture Pad", vendorId: "0xCAFE", productId: "0xBEEF"},
  };
}

test("a generic hub editor document validates and owns immutable input", () => {
  const sourceProfile = profile();
  const sourceLayout = layout();
  const sourceTarget = target();
  const sourceReport = {version: 1, items: [{path: "/keymap", verdict: "carried"}]};
  const sourceWorklist = [{kind: "key", source: {layer: 0, key: "K_R0_C0", code: 4}}];
  const state = createHubKeymapState({
    profile: sourceProfile,
    layout: sourceLayout,
    target: sourceTarget,
    report: sourceReport,
    worklist: sourceWorklist,
  });

  sourceProfile.keymap.layers[0].keys[0].code = 0xffff;
  sourceLayout[0].x = 99;
  sourceTarget.definition.name = "Changed elsewhere";
  sourceReport.items[0].verdict = "dropped";
  sourceWorklist[0].source.code = 0xffff;

  assert.equal(state.profile.keymap.layers[0].keys[0].code, 0x0004);
  assert.equal(state.layout[0].x, 0);
  assert.equal(state.target.definition.name, "Fixture Pad");
  assert.equal(state.report.items[0].verdict, "carried");
  assert.equal(state.worklist[0].source.code, 4);
  assert.equal(state.layer, 0);
  assert.equal(state.selectedKey, null);
  assert.equal(state.dirty, false);
  assert.deepEqual(state.undo, []);
  assert.deepEqual(state.redo, []);
  assert.equal(Object.isFrozen(state), true);
  assert.equal(Object.isFrozen(state.profile.keymap.layers[0].keys[0]), true);
  assert.equal(Object.isFrozen(state.worklist[0].source), true);
  assert.equal("target" in state.profile, false);
  assert.equal("layout" in state.profile, false);
});

test("selection, key assignment, undo, redo, and save stay immutable", () => {
  const initial = createHubKeymapState({profile: profile(), layout: layout(), target: target()});
  const selected = reduceHubKeymapState(initial, {type: "SELECT_KEY", key: "K_R0_C1"});
  const changed = reduceHubKeymapState(selected, {type: "SET_KEY_CODE", code: 0x1234});

  assert.notStrictEqual(selected, initial);
  assert.strictEqual(selected.profile, initial.profile);
  assert.equal(selected.selectedKey, "K_R0_C1");
  assert.equal(selected.dirty, false);
  assert.equal(changed.profile.keymap.layers[0].keys[1].code, 0x1234);
  assert.equal(selected.profile.keymap.layers[0].keys[1].code, 0x0005);
  assert.equal(changed.profile.macros[0].events[0].tap, 0x0004);
  assert.equal(changed.undo.length, 1);
  assert.equal(changed.redo.length, 0);
  assert.equal(changed.dirty, true);

  const undone = reduceHubKeymapState(changed, {type: "UNDO"});
  assert.equal(undone.profile.keymap.layers[0].keys[1].code, 0x0005);
  assert.equal(undone.dirty, false);
  assert.equal(undone.redo.length, 1);

  const redone = reduceHubKeymapState(undone, {type: "REDO"});
  assert.equal(redone.profile.keymap.layers[0].keys[1].code, 0x1234);
  assert.equal(redone.dirty, true);

  const saved = reduceHubKeymapState(redone, {type: "MARK_SAVED"});
  assert.equal(saved.dirty, false);
  assert.strictEqual(saved.profile, redone.profile);
  assert.equal(reduceHubKeymapState(saved, {type: "UNDO"}).dirty, true);
});

test("layer selection is bounded and VIA live reads require an imported definition", () => {
  const initial = createHubKeymapState({profile: profile(), layout: layout(), target: target()});
  const layerOne = reduceHubKeymapState(initial, {type: "SELECT_LAYER", layer: 1});

  assert.equal(layerOne.layer, 1);
  assert.equal(layerOne.selectedKey, null);
  assert.throws(
    () => reduceHubKeymapState(initial, {type: "SELECT_LAYER", layer: 2}),
    /layer/i,
  );
  assert.throws(
    () => reduceHubKeymapState(initial, {type: "SET_KEY_CODE", code: 4}),
    /select/i,
  );
  assert.throws(
    () => createHubKeymapState({
      profile: profile(),
      layout: layout(),
      target: {ecosystem: "via", address: "hid:fixture-a"},
    }),
    /definition/i,
  );
});

test("replacing a profile is one undoable document checkpoint", () => {
  const initial = createHubKeymapState({profile: profile(), layout: layout(), target: target()});
  const overlaid = profile();
  overlaid.keymap.layers[0].keys[0].code = 0x004c;

  const changed = reduceHubKeymapState(initial, {type: "REPLACE_PROFILE", profile: overlaid});
  assert.equal(changed.profile.keymap.layers[0].keys[0].code, 0x004c);
  assert.equal(changed.undo.length, 1);
  assert.equal(changed.dirty, true);
  assert.equal(reduceHubKeymapState(changed, {type: "UNDO"}).profile.keymap.layers[0].keys[0].code, 0x0004);
});

test("unknown 16-bit codes survive selection, save, assignment, and undo", () => {
  const source = profile();
  source.keymap.layers[0].keys[0].code = 0xffff;
  const initial = createHubKeymapState({profile: source, layout: layout(), target: target()});
  const selected = reduceHubKeymapState(initial, {type: "SELECT_KEY", key: "K_R0_C0"});
  const saved = reduceHubKeymapState(selected, {type: "MARK_SAVED"});
  const changed = reduceHubKeymapState(saved, {type: "SET_KEY_CODE", code: 0x7f34});
  const restored = reduceHubKeymapState(changed, {type: "UNDO"});

  assert.equal(saved.profile.keymap.layers[0].keys[0].code, 0xffff);
  assert.equal(changed.profile.keymap.layers[0].keys[0].code, 0x7f34);
  assert.equal(changed.undo.length, 1);
  assert.equal(restored.profile.keymap.layers[0].keys[0].code, 0xffff);
  assert.equal(restored.dirty, false);
});
