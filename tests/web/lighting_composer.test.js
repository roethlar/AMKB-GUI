"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const modulePath = path.join(
  __dirname,
  "../../am_configurator/web/lighting_composer.js",
);
const {
  resolveSourceGeometry,
  defaultSourceTransform,
  interpolateMoveZoom,
  normalizedPointer,
  panSourceTransform,
  presetSourceTransform,
  renderColorEffect,
  scaleSourceTransform,
  validateEffectSpec,
  validateSourceTransform,
  wireSourceTransformStage,
} = require(modulePath);

const geometryVectors = JSON.parse(fs.readFileSync(path.join(
  __dirname,
  "../fixtures/media_geometry_vectors.json",
), "utf8"));

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

function effect(type, parameters, changes = {}) {
  return {
    version: 1,
    type,
    frame_count: 8,
    duration_ms: 90,
    parameters,
    ...changes,
  };
}

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  toggle(name, force) {
    if (force === undefined ? !this.values.has(name) : force) this.values.add(name);
    else this.values.delete(name);
  }

  contains(name) {
    return this.values.has(name);
  }
}

class FakeStage {
  constructor({captureError = null} = {}) {
    this.bounds = {left: 0, top: 0, width: 400, height: 100};
    this.captureError = captureError;
    this.captures = [];
    this.classList = new FakeClassList();
    this.focusCalls = [];
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type, changes = {}) {
    const event = {
      type,
      pointerId: 7,
      isPrimary: true,
      button: 0,
      buttons: 1,
      clientX: 100,
      clientY: 50,
      deltaY: 0,
      key: "",
      shiftKey: false,
      defaultPrevented: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
      ...changes,
    };
    for (const listener of [...(this.listeners.get(type) || [])]) listener(event);
    return event;
  }

  focus(options) {
    this.focusCalls.push(options);
  }

  getBoundingClientRect() {
    return this.bounds;
  }

  listenerCount(type) {
    return this.listeners.get(type)?.size || 0;
  }

  setPointerCapture(pointerId) {
    this.captures.push(pointerId);
    if (this.captureError) throw this.captureError;
  }
}

function sourceInputHarness(options = {}) {
  const stage = new FakeStage(options);
  const commits = [];
  let active = true;
  let previewMode = "result";
  let current = transform({scale_x: 2, scale_y: 2});
  const controller = wireSourceTransformStage(stage, {
    isActive: () => active,
    activate: () => {
      previewMode = "source";
    },
    getTransform: () => current,
    getGeometry: () => ({
      sourceSize: {width: 40, height: 5},
      destinationSizes: [{width: 40, height: 5}],
      primaryIndex: 0,
    }),
    getBounds: () => stage.getBoundingClientRect(),
    commit: next => {
      assert.equal(previewMode, "source", "source view must activate before mutation");
      current = next;
      commits.push(next);
    },
  });
  return {
    stage,
    commits,
    controller,
    current: () => current,
    previewMode: () => previewMode,
    setActive(value) {
      active = value;
    },
  };
}

test("source transforms are exact, finite, bounded, and browser-pixel independent", () => {
  assert.deepEqual(defaultSourceTransform("lanczos"), transform({sampling: "lanczos"}));
  assert.deepEqual(validateSourceTransform(transform()), transform());
  assert.deepEqual(
    normalizedPointer(
      {clientX: 70, clientY: 45},
      {left: 20, top: 20, width: 100, height: 50},
    ),
    {x: 0.5, y: 0.5},
  );
  assert.deepEqual(
    normalizedPointer(
      {clientX: -100, clientY: 500},
      {left: 20, top: 20, width: 100, height: 50},
    ),
    {x: 0, y: 1},
  );

  for (const invalid of [
    {...transform(), extra: true},
    transform({version: 2}),
    transform({offset_x: Number.NaN}),
    transform({offset_y: Number.POSITIVE_INFINITY}),
    transform({scale_x: 0}),
    transform({scale_y: -1}),
    transform({scale_x: 1, scale_y: 2}),
    transform({aspect_locked: "yes"}),
    transform({sampling: "bilinear"}),
    transform({background: "black"}),
  ]) {
    assert.throws(() => validateSourceTransform(invalid));
  }
});

test("Fit, Fill, Center, pan, zoom, and stretch reduce to normalized transforms", () => {
  const source = {width: 100, height: 100};
  const destination = {width: 40, height: 10};
  const current = transform({sampling: "nearest"});

  assert.deepEqual(
    presetSourceTransform("fill", source, destination, current),
    transform({sampling: "nearest"}),
  );
  assert.deepEqual(
    presetSourceTransform("reset", source, destination, current),
    transform({sampling: "nearest"}),
  );
  assert.deepEqual(
    presetSourceTransform("fit", source, destination, current),
    transform({scale_x: 0.25, scale_y: 0.25, sampling: "nearest"}),
  );
  assert.deepEqual(
    presetSourceTransform("center", source, destination, current),
    transform({scale_x: 2.5, scale_y: 2.5, sampling: "nearest"}),
  );
  assert.deepEqual(
    panSourceTransform(current, 0.25, -0.5),
    transform({offset_x: 0.25, offset_y: -0.5, sampling: "nearest"}),
  );
  assert.deepEqual(
    scaleSourceTransform(current, 2),
    transform({scale_x: 2, scale_y: 2, sampling: "nearest"}),
  );
  assert.deepEqual(
    scaleSourceTransform(current, 1.5, "x"),
    transform({
      scale_x: 1.5,
      scale_y: 1,
      aspect_locked: false,
      sampling: "nearest",
    }),
  );

  const sameSize = {width: 40, height: 5};
  assert.deepEqual(
    panSourceTransform(
      transform({offset_x: 0.5, offset_y: -0.5}),
      7.5,
      -7.5,
      sameSize,
      [sameSize],
    ),
    transform(),
  );
  assert.deepEqual(
    scaleSourceTransform(
      transform({offset_x: 0.5, offset_y: -0.5, scale_x: 2, scale_y: 2}),
      0.5,
      "both",
      sameSize,
      [sameSize],
    ),
    transform(),
  );
});

test("browser and backend share exact canonical geometry vectors", () => {
  assert.equal(geometryVectors.version, 1);
  for (const vector of geometryVectors.vectors) {
    const before = JSON.stringify(vector);
    const resolved = resolveSourceGeometry(
      vector.source,
      vector.destinations,
      vector.transform,
    );
    assert.deepEqual(resolved, vector.expected, vector.name);
    assert.equal(JSON.stringify(vector), before, vector.name);
    vector.destinations.forEach((destination, index) => {
      const box = resolved.boxes[index];
      const overlapX = Math.max(
        0,
        Math.min(destination.width, box.left + box.rendered_width)
          - Math.max(0, box.left),
      );
      const overlapY = Math.max(
        0,
        Math.min(destination.height, box.top + box.rendered_height)
          - Math.max(0, box.top),
      );
      assert.equal(overlapX, Math.min(destination.width, box.rendered_width));
      assert.equal(overlapY, Math.min(destination.height, box.rendered_height));
    });
  }

  const moveZoom = geometryVectors.move_zoom;
  assert.deepEqual(
    interpolateMoveZoom(
      moveZoom.effect,
      moveZoom.source,
      moveZoom.destinations,
    ),
    moveZoom.expected_transforms,
  );
});

test("a NotFoundError capture miss still completes one pointer-ID-scoped drag", () => {
  const captureError = Object.assign(new Error("synthetic pointer"), {
    name: "NotFoundError",
  });
  const harness = sourceInputHarness({captureError});
  const {stage} = harness;

  const secondary = stage.dispatch("pointerdown", {pointerId: 5, isPrimary: false});
  const rightButton = stage.dispatch("pointerdown", {pointerId: 6, button: 2});
  assert.equal(secondary.defaultPrevented, false);
  assert.equal(rightButton.defaultPrevented, false);
  assert.equal(stage.classList.contains("dragging"), false);
  let pointerDown;
  assert.doesNotThrow(() => {
    pointerDown = stage.dispatch("pointerdown");
  });
  assert.equal(pointerDown.defaultPrevented, true);
  assert.equal(harness.previewMode(), "source");
  assert.equal(stage.classList.contains("dragging"), true);
  assert.deepEqual(stage.captures, [7]);
  assert.deepEqual(stage.focusCalls, [{preventScroll: true}]);
  for (const type of ["pointermove", "pointerup", "pointercancel", "lostpointercapture"]) {
    assert.equal(stage.listenerCount(type), 1, `${type} must be stage-scoped during the session`);
  }

  stage.dispatch("pointermove", {pointerId: 8, clientX: 150, clientY: 75});
  assert.equal(harness.commits.length, 0, "another pointer cannot move the source");
  const move = stage.dispatch("pointermove", {clientX: 150, clientY: 75});
  assert.equal(move.defaultPrevented, true);
  assert.equal(harness.commits.length, 1);
  assert.equal(harness.current().offset_x, 0.125);
  assert.equal(harness.current().offset_y, 0.25);

  stage.dispatch("pointerup", {pointerId: 8});
  assert.equal(stage.classList.contains("dragging"), true);
  stage.dispatch("pointerup");
  assert.equal(stage.classList.contains("dragging"), false);
  for (const type of ["pointermove", "pointerup", "pointercancel", "lostpointercapture"]) {
    assert.equal(stage.listenerCount(type), 0, `${type} must be released with the session`);
  }
  stage.dispatch("pointermove", {clientX: 200, clientY: 80});
  assert.equal(harness.commits.length, 1);
  harness.controller.teardown();
});

test("pointer cancel, lost capture, teardown, and real capture failures release cleanly", () => {
  const harness = sourceInputHarness();
  const {stage} = harness;
  for (const releaseType of ["pointercancel", "lostpointercapture", "pointerup"]) {
    stage.dispatch("pointerdown");
    assert.equal(stage.classList.contains("dragging"), true);
    stage.dispatch(releaseType);
    assert.equal(stage.classList.contains("dragging"), false);
    assert.equal(stage.listenerCount("pointermove"), 0);
  }
  harness.controller.teardown();
  assert.equal(stage.listenerCount("pointerdown"), 0);
  assert.equal(stage.listenerCount("wheel"), 0);
  assert.equal(stage.listenerCount("keydown"), 0);

  const denied = Object.assign(new Error("capture denied"), {name: "SecurityError"});
  const failed = sourceInputHarness({captureError: denied});
  assert.throws(() => failed.stage.dispatch("pointerdown"), /capture denied/);
  assert.equal(failed.stage.classList.contains("dragging"), false);
  assert.equal(failed.stage.listenerCount("pointermove"), 0);
  failed.controller.teardown();
});

test("wheel and keyboard framing activate source view and share canonical reducers", () => {
  const wheel = sourceInputHarness();
  const wheelEvent = wheel.stage.dispatch("wheel", {deltaY: -1});
  assert.equal(wheelEvent.defaultPrevented, true);
  assert.equal(wheel.previewMode(), "source");

  const keyboard = sourceInputHarness();
  const zoomEvent = keyboard.stage.dispatch("keydown", {key: "+"});
  assert.equal(zoomEvent.defaultPrevented, true);
  assert.equal(keyboard.current().scale_x, wheel.current().scale_x);
  assert.equal(keyboard.current().scale_y, wheel.current().scale_y);
  keyboard.stage.dispatch("keydown", {key: "ArrowRight"});
  assert.equal(keyboard.current().offset_x, 0.025);
  const beforeKeyboardBox = resolveSourceGeometry(
    {width: 40, height: 5},
    [{width: 40, height: 5}],
    keyboard.current(),
  ).boxes[0];
  keyboard.stage.dispatch("keydown", {key: "ArrowDown", shiftKey: true});
  assert.equal(keyboard.current().offset_y, 0.2);
  const afterKeyboardBox = resolveSourceGeometry(
    {width: 40, height: 5},
    [{width: 40, height: 5}],
    keyboard.current(),
  ).boxes[0];
  assert.notEqual(afterKeyboardBox.top, beforeKeyboardBox.top);

  const before = keyboard.commits.length;
  const ignored = keyboard.stage.dispatch("keydown", {key: "Enter"});
  assert.equal(ignored.defaultPrevented, false);
  keyboard.setActive(false);
  keyboard.stage.dispatch("wheel", {deltaY: 1});
  keyboard.stage.dispatch("keydown", {key: "ArrowLeft"});
  keyboard.stage.dispatch("pointerdown");
  assert.equal(keyboard.commits.length, before);
  assert.equal(keyboard.stage.classList.contains("dragging"), false);
  wheel.controller.teardown();
  keyboard.controller.teardown();
});

test("Pulse, Hue cycle, Sweep, and Shimmer are deterministic bounded local reducers", () => {
  const sourceFrames = [["#FF8040", "#204080", "#FFFFFF"]];
  const coordinates = [
    {x: 0, y: 0.5},
    {x: 0.5, y: 0.5},
    {x: 1, y: 0.5},
  ];
  const before = JSON.stringify(sourceFrames);

  const pulse = validateEffectSpec(
    effect("pulse", {minimum_brightness: 0.2}, {frame_count: 5}),
    {frameLimit: 16, stillSource: false},
  );
  const pulsed = renderColorEffect(sourceFrames, pulse, coordinates);
  assert.equal(pulsed.length, 5);
  assert.deepEqual(pulsed[0], sourceFrames[0]);
  assert.deepEqual(pulsed.at(-1), sourceFrames[0]);
  assert.notDeepEqual(pulsed[2], sourceFrames[0]);

  const hue = validateEffectSpec(
    effect("hue_cycle", {turns: 1}, {frame_count: 6}),
    {frameLimit: 16, stillSource: false},
  );
  const hueFrames = renderColorEffect(sourceFrames, hue, coordinates);
  assert.equal(hueFrames.length, 6);
  assert.notDeepEqual(hueFrames[1], sourceFrames[0]);

  const sweep = validateEffectSpec(
    effect("sweep", {
      direction: "left_to_right",
      width: 0.35,
      minimum_brightness: 0.1,
    }),
    {frameLimit: 16, stillSource: false},
  );
  const swept = renderColorEffect(sourceFrames, sweep, coordinates);
  assert.equal(swept.length, 8);
  assert.notDeepEqual(swept[1], swept[6]);

  const shimmer = validateEffectSpec(
    effect("shimmer", {depth: 0.6, seed: 824}),
    {frameLimit: 16, stillSource: false},
  );
  const shimmerA = renderColorEffect(sourceFrames, shimmer, coordinates);
  const shimmerB = renderColorEffect(sourceFrames, shimmer, coordinates);
  assert.deepEqual(shimmerA, shimmerB);
  const otherSeed = validateEffectSpec(
    effect("shimmer", {depth: 0.6, seed: 825}),
    {frameLimit: 16, stillSource: false},
  );
  assert.notDeepEqual(
    shimmerA,
    renderColorEffect(sourceFrames, otherSeed, coordinates),
  );

  for (const frames of [pulsed, hueFrames, swept, shimmerA]) {
    for (const frame of frames) {
      assert.equal(frame.length, sourceFrames[0].length);
      for (const color of frame) assert.match(color, /^#[0-9A-F]{6}$/);
    }
  }
  assert.equal(JSON.stringify(sourceFrames), before);
});

test("effect schemas enforce frame ceilings and Move & zoom remains still-only", () => {
  assert.throws(() => validateEffectSpec(
    effect("pulse", {minimum_brightness: 0.2}, {frame_count: 17}),
    {frameLimit: 16, stillSource: false},
  ));
  assert.throws(() => validateEffectSpec(
    {...effect("pulse", {minimum_brightness: 0.2}), extra: true},
    {frameLimit: 16, stillSource: false},
  ));
  assert.throws(() => validateEffectSpec(
    effect("move_zoom", {
      start_transform: transform(),
      end_transform: transform({offset_x: 0.5, scale_x: 2, scale_y: 2}),
    }, {frame_count: 3}),
    {frameLimit: 16, stillSource: false},
  ));

  const moveZoom = validateEffectSpec(
    effect("move_zoom", {
      start_transform: transform(),
      end_transform: transform({offset_x: 0.5, scale_x: 2, scale_y: 2}),
    }, {frame_count: 3}),
    {frameLimit: 16, stillSource: true},
  );
  const transforms = interpolateMoveZoom(moveZoom);
  assert.equal(transforms.length, 3);
  assert.deepEqual(transforms[0], transform());
  assert.deepEqual(
    transforms.at(-1),
    transform({offset_x: 0.5, scale_x: 2, scale_y: 2}),
  );
  assert.deepEqual(
    transforms[1],
    transform({offset_x: 0.25, scale_x: 1.5, scale_y: 1.5}),
  );
});

test("the pure compositor has no network, provider, or browser-storage path", () => {
  const source = fs.readFileSync(modulePath, "utf8");
  assert.doesNotMatch(
    source,
    /\bfetch\s*\(|XMLHttpRequest|WebSocket|AICapability|sessionStorage|localStorage/,
  );
});
