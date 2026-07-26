"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEVICE_TARGETS,
  FAMILY_SPECS,
  UNKNOWN_FAMILY_SPEC,
  familySpec,
  filterAssignmentOptions,
  neonPaletteAssignment,
  productFamily,
  projectVialKeyLayout,
  renderTargetControls,
  specForProduct,
  supportedFamily,
  trackColorCount,
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

test("the Neon palette exposes only assignments its QMK wire format accepts", () => {
  const options = [
    {label: "None", code: "#00000000"},
    {label: "A", code: "#00070004"},
    {label: "Volume up", code: "#000C00E9"},
    {label: "Next LED", code: "#00920100"},
    {label: "Macro 16", code: "#0095150F"},
    {label: "Macro 17", code: "#00951510"},
  ];

  assert.deepEqual(
    filterAssignmentOptions("NEON80", options).map(option => option.label),
    ["None", "A", "Macro 16"],
  );
  assert.deepEqual(filterAssignmentOptions("AM21", options), options);
  assert.equal(neonPaletteAssignment("#01070004"), true);
  assert.equal(neonPaletteAssignment("#11070004"), false);
  assert.equal(neonPaletteAssignment("#00FF5101"), false);
});
