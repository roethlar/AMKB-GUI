"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEVICE_TARGETS,
  FAMILY_SPECS,
  NEON_LIGHTING_CONTROLS,
  UNKNOWN_FAMILY_SPEC,
  familySpec,
  filterAssignmentOptions,
  macroCapacityStatus,
  neonPaletteAssignment,
  productFamily,
  projectVialKeyLayout,
  projectVialLedLayout,
  renderTargetControls,
  selectVialLayoutDevice,
  specForProduct,
  supportedFamily,
  trackColorCount,
  vialMacroBufferUsage,
  withDeviceMacroLimits,
} = require("../../am_configurator/web/lighting_targets.js");

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.className = "";
    this.disabled = false;
    this.textContent = "";
    this.focused = false;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  click() {
    if (!this.disabled) this.listeners.get("click")?.();
  }

  focus() {
    this.focused = true;
  }
}

class FakeDocument {
  createElement(tagName) {
    return new FakeElement(tagName, this);
  }
}

const EXPECTED = {
  CB: [["keyframes", "Switch LEDs"], ["frames", "Top display 40×5"]],
  "80": [["keyframes", "Per-key"], ["spotlight_frames", "Edge lights"]],
  ALICE: [["keyframes", "Keys + center"]],
};

test("CyberBoard, Relic, and AFA targets render as selectable valid buttons", () => {
  for (const [family, expected] of Object.entries(EXPECTED)) {
    const host = new FakeElement("div", new FakeDocument());
    let selected = "missing";
    const select = target => {
      selected = target;
      renderTargetControls(host, DEVICE_TARGETS[family], selected, false, select);
    };
    renderTargetControls(host, DEVICE_TARGETS[family], selected, false, select);

    assert.deepEqual(
      host.children.map(button => [button.dataset.lightingTarget, button.textContent]),
      expected,
    );
    assert.ok(host.children.every(button => button.tagName === "BUTTON"));
    host.children.at(-1).click();
    assert.equal(selected, expected.at(-1)[0]);
    assert.equal(host.children.at(-1).getAttribute("aria-pressed"), "true");
    assert.equal(host.children.at(-1).className, "active");
  }
});

test("an unsupported product resolves to no family instead of a default one", () => {
  for (const [product, family] of [["CB04", "CB"], ["cb04", "CB"], ["AM21", "80"], ["80", "80"], ["ALICE", "ALICE"], ["NEON80", "NEON"]]) {
    assert.equal(supportedFamily(product), family);
    assert.equal(familySpec(product).model, family);
  }

  // An unrecognised product must not inherit another device's geometry: that
  // is what would let its pages be painted with CyberBoard maps and written to
  // the keyboard. ("NEON" used to be this test's example of an unknown family;
  // registering that family made the assertion vacuous, and the failure is
  // what caught it.)
  for (const product of ["", null, undefined, "AM99", "NOT-A-BOARD"]) {
    assert.equal(supportedFamily(product), null, `${product} must not resolve to a family`);
    assert.equal(familySpec(product), null);
  }
});

test("an unrecognised product still reports the shared limits for editing", () => {
  const spec = specForProduct("SOME-UNSHIPPED-BOARD");

  assert.equal(spec, UNKNOWN_FAMILY_SPEC);
  assert.equal(spec.model, "");
  assert.equal(spec.macroTracks, 32);
  assert.equal(spec.macroEvents, 200);
  assert.deepEqual(spec.authoredTracks, []);
  assert.equal(specForProduct("CB04"), FAMILY_SPECS.CB);
});

test("track colour counts follow the family that authors the track", () => {
  assert.equal(trackColorCount(FAMILY_SPECS.CB, "frames"), 200);
  assert.equal(trackColorCount(FAMILY_SPECS.CB, "keyframes"), 90);
  assert.equal(trackColorCount(FAMILY_SPECS["80"], "spotlight_frames"), 24);
  assert.equal(trackColorCount(FAMILY_SPECS.ALICE, "keyframes"), 90);
  // A track the family does not author falls back to the shared count, which
  // is what the Python validator has always done for a track that is present.
  assert.equal(trackColorCount(FAMILY_SPECS.ALICE, "spotlight_frames"), 24);
  assert.equal(trackColorCount(FAMILY_SPECS.CB, "not-a-track"), null);
});

test("every family's authored tracks are exactly the targets it offers", () => {
  for (const [family, spec] of Object.entries(FAMILY_SPECS)) {
    assert.deepEqual(
      spec.authoredTracks,
      DEVICE_TARGETS[family].map(target => target.key),
      `${family} offers targets it cannot size`,
    );
  }
  assert.deepEqual(Object.keys(FAMILY_SPECS).sort(), Object.keys(DEVICE_TARGETS).sort());
});

test("productFamily normalises the identifiers the firmware reports", () => {
  assert.equal(productFamily("CB04"), "CB");
  assert.equal(productFamily("am21"), "80");
  assert.equal(productFamily("neon80"), "NEON");
  assert.equal(productFamily("AM Neon 80"), "NEON");
  // An identifier this build does not know passes through uppercased, so the
  // caller can show it; `supportedFamily` is what refuses it.
  assert.equal(productFamily("SOME-UNSHIPPED-BOARD"), "SOME-UNSHIPPED-BOARD");
  assert.equal(productFamily(""), "");
  assert.equal(productFamily(null), "");
});

test("target controls preserve pressed and destination-locked state", () => {
  const host = new FakeElement("div", new FakeDocument());
  let selections = 0;
  renderTargetControls(host, DEVICE_TARGETS.CB, "frames", true, () => { selections += 1; });

  assert.deepEqual(host.children.map(button => button.disabled), [true, true]);
  assert.deepEqual(host.children.map(button => button.getAttribute("aria-pressed")), ["false", "true"]);
  host.children[0].click();
  assert.equal(selections, 0);
});

test("the Neon axial LEDs inherit real key widths from the Vial layout", () => {
  const layout = projectVialLedLayout(
    {
      key_layout: [
        {index: 0, x: 0, y: 0, width: 10, height: 14, rotation: 0},
        {index: 1, x: 10, y: 0, width: 10, height: 14, rotation: 0},
        {index: 2, x: 20, y: 0, width: 60, height: 14, rotation: 0},
        {index: 3, x: 80, y: 0, width: 10, height: 14, rotation: 0},
      ],
    },
    {width: 6, height: 1, count: 6, map: [0, 1, 2, 3, 4, 5]},
  );

  assert.deepEqual(layout.map(item => item.index), [0, 1, 2, 3, 4, 5]);
  assert.deepEqual(layout.map(item => item.keyIndex), [0, 1, 2, 2, 2, 3]);
  assert.deepEqual(
    layout.slice(2, 5).map(item => [item.x, item.w, item.groupPosition, item.groupCount]),
    [[20, 20, 0, 3], [40, 20, 1, 3], [60, 20, 2, 3]],
  );
  assert.deepEqual(layout.slice(2, 5).map(item => item.showLabel), [false, true, false]);
  assert.equal(
    projectVialLedLayout(
      {key_layout: [{index: 0, x: 0, y: 0, width: 10, height: 14, rotation: 0}]},
      {width: 1, height: 2, count: 1, map: [0, -1]},
    ),
    null,
  );
});

test("the validated Vial layout becomes the physical Neon key geometry", () => {
  const keys = projectVialKeyLayout({
    key_layout: [
      {index: 0, x: 0, y: 0, width: 5, height: 14, rotation: 0},
      {index: 15, x: 0, y: 18, width: 7.5, height: 14, rotation: 0},
      {index: 89, x: 90, y: 72, width: 5, height: 14, rotation: 0},
    ],
  });

  assert.deepEqual(keys, [
    [0, 0, 0, 5, 0, 14],
    [15, 0, 18, 7.5, 0, 14],
    [89, 90, 72, 5, 0, 14],
  ]);
  assert.equal(projectVialKeyLayout({key_layout: []}), null);
  assert.equal(projectVialKeyLayout({
    key_layout: [
      {index: 0, x: 0, y: 0, width: 5, height: 14},
      {index: 0, x: 10, y: 0, width: 5, height: 14},
    ],
  }), null);
});

test("one scanned Neon supplies display geometry before a full device read", () => {
  const key_layout = [
    {index: 0, x: 0, y: 0, width: 5, height: 14, rotation: 0},
    {index: 15, x: 0, y: 18, width: 7.5, height: 14, rotation: 0},
  ];
  const first = {
    transport: "hid",
    address: "first",
    product_id: "NEON80",
    key_layout,
  };
  const second = {
    transport: "hid",
    address: "second",
    product_id: "AM Neon 80",
    key_layout,
  };

  assert.equal(selectVialLayoutDevice("NEON80", [first], null), first);
  assert.equal(selectVialLayoutDevice("NEON80", [first, second], null), null);
  assert.equal(
    selectVialLayoutDevice("NEON80", [first, second], "hid:second"),
    second,
  );
  assert.equal(
    selectVialLayoutDevice("NEON80", [second], "hid:first"),
    null,
  );
  assert.equal(selectVialLayoutDevice("AM21", [first], null), null);
  assert.equal(selectVialLayoutDevice("NEON80", [{
    ...first,
    key_layout: [],
  }], null), null);
});

test("portable profile evidence owns Neon geometry even when another layout is connected", () => {
  const embedded = {
    product_id: "NEON80",
    keymap_signature: "keymap:v1:embedded",
    key_layout: [
      {index: 0, x: 0, y: 0, width: 5, height: 14, rotation: 0},
    ],
  };
  const connected = {
    transport: "hid",
    address: "connected",
    product_id: "NEON80",
    key_layout: [
      {index: 0, x: 0, y: 0, width: 9, height: 14, rotation: 0},
    ],
  };

  assert.equal(
    selectVialLayoutDevice("NEON80", [connected], "hid:connected", embedded),
    embedded,
  );
  assert.equal(
    selectVialLayoutDevice("AM21", [connected], "hid:connected", embedded),
    null,
  );
});

test("the Neon palette exposes only assignments its QMK wire format accepts", () => {
  const options = [
    {label: "None", code: "#00000000"},
    {label: "A", code: "#00070004"},
    {label: "Volume up", code: "#000C00E9"},
    {label: "Next LED", code: "#00920100"},
    {label: "Under-key power", code: "#00FF5DBF"},
    {label: "Macro 16", code: "#0095150F"},
    {label: "Macro 17", code: "#00951510"},
  ];

  assert.deepEqual(
    filterAssignmentOptions("NEON80", options).map(option => option.label),
    ["None", "A", "Under-key power", "Macro 16"],
  );
  assert.deepEqual(filterAssignmentOptions("AM21", options), options);
  assert.equal(neonPaletteAssignment("#01070004"), true);
  assert.equal(neonPaletteAssignment("#11070004"), false);
  assert.equal(neonPaletteAssignment("#00FF5101"), false);
  assert.deepEqual(
    filterAssignmentOptions("NEON80", options, 9).map(option => option.label),
    ["None", "A", "Under-key power"],
  );
});

test("the Neon palette owns every firmware lighting control by name", () => {
  assert.equal(NEON_LIGHTING_CONTROLS.length, 14);
  assert.deepEqual(
    NEON_LIGHTING_CONTROLS.map(option => option.code),
    Array.from(
      {length: 14},
      (_, index) => `#00FF5D${(0xB2 + index).toString(16).toUpperCase()}`,
    ),
  );
  assert.deepEqual(
    [...new Set(NEON_LIGHTING_CONTROLS.map(option => option.category))],
    ["Under-key lighting", "Top display lighting"],
  );
  assert.equal(
    filterAssignmentOptions("NEON80", NEON_LIGHTING_CONTROLS).length,
    14,
  );
});

test("connected Neon macro limits overlay the static family fallback", () => {
  const connected = withDeviceMacroLimits(FAMILY_SPECS.NEON, {
    macro_count: 9,
    macro_buffer_bytes: 321,
  });

  assert.equal(connected.macroTracks, 9);
  assert.equal(connected.macroBufferBytes, 321);
  assert.equal(FAMILY_SPECS.NEON.macroTracks, 16);
  assert.equal(withDeviceMacroLimits(FAMILY_SPECS.NEON, {}), FAMILY_SPECS.NEON);
  assert.equal(withDeviceMacroLimits(FAMILY_SPECS.CB, {
    macro_count: 9,
    macro_buffer_bytes: 321,
  }), FAMILY_SPECS.CB);
  const none = withDeviceMacroLimits(FAMILY_SPECS.NEON, {
    macro_count: 0,
    macro_buffer_bytes: 0,
  });
  assert.equal(none.macroTracks, 0);
  assert.equal(none.macroBufferBytes, 0);
  assert.deepEqual(macroCapacityStatus(none, []), {
    used: 0,
    limit: 0,
    unit: "bytes",
    tracks: 0,
    fits: true,
  });
  assert.deepEqual(filterAssignmentOptions("NEON80", [{
    label: "Macro 1",
    code: "#00951500",
  }], 0), []);
});

test("Neon macro usage meters the exact encoded Vial buffer bytes", () => {
  const macros = [
    {
      layer_key: ["#11070004", "#10070004"],
      intvel_ms: [25, 0],
    },
    {
      layer_key: ["#00070005"],
      intvel_ms: [1],
    },
  ];

  // Two slot terminators + three three-byte events + two four-byte delays.
  assert.equal(vialMacroBufferUsage(macros, 2), 19);
  assert.equal(vialMacroBufferUsage([], 9), 9);
  assert.deepEqual(macroCapacityStatus({
    model: "NEON",
    macroTracks: 2,
    macroBufferBytes: 18,
  }, macros), {
    used: 19,
    limit: 18,
    unit: "bytes",
    tracks: 2,
    fits: false,
  });
  assert.deepEqual(macroCapacityStatus({
    model: "CB",
    macroTracks: 32,
    macroEvents: 200,
  }, macros), {
    used: 3,
    limit: 200,
    unit: "events",
    tracks: 32,
    fits: true,
  });
});
