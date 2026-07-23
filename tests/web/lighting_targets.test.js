"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEVICE_TARGETS,
  renderTargetControls,
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

test("target controls preserve pressed and destination-locked state", () => {
  const host = new FakeElement("div", new FakeDocument());
  let selections = 0;
  renderTargetControls(host, DEVICE_TARGETS.CB, "frames", true, () => { selections += 1; });

  assert.deepEqual(host.children.map(button => button.disabled), [true, true]);
  assert.deepEqual(host.children.map(button => button.getAttribute("aria-pressed")), ["false", "true"]);
  host.children[0].click();
  assert.equal(selections, 0);
});
