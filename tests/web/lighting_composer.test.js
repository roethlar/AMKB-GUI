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
