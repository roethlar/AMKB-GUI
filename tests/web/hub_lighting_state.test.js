"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  createHubLightingState,
  reduceHubLightingProfile,
} = require(path.join(
  __dirname,
  "../../am_configurator/web/hub_lighting_state.js",
));
const {
  createHubKeymapState,
  reduceHubKeymapState,
} = require(path.join(
  __dirname,
  "../../am_configurator/web/hub_keymap_state.js",
));

function profile() {
  return {
    schema_version: 2,
    identity: {
      ecosystem: "via",
      family: "Fixture Pad",
      wire_identity: "CAFE:BEEF",
      endpoint: {vid: 0xcafe, pid: 0xbeef, transport: "hid"},
      protocol: {via_protocol: 11},
      definition: {source: "user_import", hash: `sha256-${"ab".repeat(32)}`},
    },
    capabilities: {
      keymap: {layers: 1, keys_per_layer: 2, encoders: 0},
      lighting: {
        surfaces: [
          {
            id: "rgb_matrix",
            role: "keys",
            generation: "qmk_rgb_matrix",
            effects: [
              {id: 0, semantic: "off"},
              {id: 1, semantic: "solid"},
            ],
            brightness: {min: 0, max: 255},
            color: {
              space: "hsv",
              channels: [{min: 0, max: 255}, {min: 0, max: 255}],
            },
            per_key: {
              pixel_count: 2,
              color: {
                space: "hsv",
                channels: [{min: 0, max: 255}, {min: 0, max: 255}],
              },
            },
          },
        ],
      },
    },
    keymap: {
      layers: [
        {
          index: 0,
          keys: [
            {key: "K_R0_C0", code: 0x0004},
            {key: "K_R0_C1", code: 0x0005},
          ],
        },
      ],
    },
    macros: [{slot: 0, events: [{tap: 0x0004}]}],
    lighting: {
      surfaces: [
        {
          id: "rgb_matrix",
          effect_id: 1,
          brightness: 200,
          color: [11, 22],
          per_key: {
            K_R0_C0: [10, 20],
            K_R0_C1: [30, 40],
          },
        },
      ],
    },
    provenance: {
      "/identity": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/capabilities": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/keymap": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/macros": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
      "/lighting": {origin: "device", source_ecosystem: "via", fidelity: "exact"},
    },
  };
}

function geometry() {
  return [
    {
      surface_id: "rgb_matrix",
      pixel_id: "K_R0_C0",
      led_index: 4,
      x: 10,
      y: 20,
      key: "K_R0_C0",
    },
    {
      surface_id: "rgb_matrix",
      pixel_id: "K_R0_C1",
      led_index: 2,
      x: 80,
      y: 20,
      key: "K_R0_C1",
    },
  ];
}

function target() {
  return {
    ecosystem: "via",
    address: "hid:fixture-a",
    scanEpoch: 4,
    definition: {name: "Fixture Pad"},
  };
}

test("controls are projected independently from proved capabilities", () => {
  const state = createHubLightingState({
    profile: profile(),
    geometry: geometry(),
    targetCurrent: true,
  });

  assert.equal(state.available, true);
  assert.equal(state.surfaces.length, 1);
  assert.deepEqual(state.surfaces[0].controls, {
    effect: true,
    brightness: true,
    speed: false,
    color: true,
    perKey: true,
    animation: false,
  });
  assert.equal(state.surfaces[0].evidence, "user_imported_definition");
  assert.deepEqual(
    state.surfaces[0].pixels.map(pixel => pixel.pixel_id),
    ["K_R0_C0", "K_R0_C1"],
  );
  assert.equal(Object.isFrozen(state), true);
  assert.equal(Object.isFrozen(state.surfaces[0].pixels[0]), true);
});

test("global edits are immutable, bounded, and preserve unrelated sections", () => {
  const source = profile();
  const keymap = JSON.stringify(source.keymap);
  const macros = JSON.stringify(source.macros);
  const changed = reduceHubLightingProfile(source, {
    type: "SET_SURFACE_FIELD",
    surfaceId: "rgb_matrix",
    field: "brightness",
    value: 201,
  });

  assert.equal(source.lighting.surfaces[0].brightness, 200);
  assert.equal(changed.lighting.surfaces[0].brightness, 201);
  assert.equal(JSON.stringify(changed.keymap), keymap);
  assert.equal(JSON.stringify(changed.macros), macros);
  assert.equal(Object.isFrozen(changed), true);
  assert.throws(
    () => reduceHubLightingProfile(source, {
      type: "SET_SURFACE_FIELD",
      surfaceId: "rgb_matrix",
      field: "speed",
      value: 1,
    }),
    /not expose speed/i,
  );
  assert.throws(
    () => reduceHubLightingProfile(source, {
      type: "SET_SURFACE_FIELD",
      surfaceId: "rgb_matrix",
      field: "brightness",
      value: 256,
    }),
    /range/i,
  );
});

test("per-key edits require current geometry and preserve canonical identities", () => {
  const source = profile();
  const changed = reduceHubLightingProfile(
    source,
    {
      type: "SET_PIXEL_COLOR",
      surfaceId: "rgb_matrix",
      pixelId: "K_R0_C1",
      value: [99, 88],
    },
    {geometry: geometry(), targetCurrent: true},
  );

  assert.deepEqual(changed.lighting.surfaces[0].per_key.K_R0_C1, [99, 88]);
  assert.deepEqual(Object.keys(changed.lighting.surfaces[0].per_key), [
    "K_R0_C0",
    "K_R0_C1",
  ]);
  assert.throws(
    () => reduceHubLightingProfile(
      source,
      {
        type: "SET_PIXEL_COLOR",
        surfaceId: "rgb_matrix",
        pixelId: "K_R0_C1",
        value: [99, 88],
      },
      {geometry: geometry(), targetCurrent: false},
    ),
    /read the target again/i,
  );
  assert.throws(
    () => reduceHubLightingProfile(
      source,
      {
        type: "SET_PIXEL_COLOR",
        surfaceId: "rgb_matrix",
        pixelId: "K_R9_C9",
        value: [99, 88],
      },
      {geometry: geometry(), targetCurrent: true},
    ),
    /geometry/i,
  );
  assert.throws(
    () => reduceHubLightingProfile(
      source,
      {
        type: "SET_PIXEL_COLOR",
        surfaceId: "rgb_matrix",
        pixelId: "K_R0_C0",
        value: [99, 88],
      },
      {geometry: geometry().slice(0, 1), targetCurrent: true},
    ),
    /every per-key pixel/i,
  );
});

test("VialRGB direct mode stays out of persistent controls while exact animations remain document-only", () => {
  const source = profile();
  source.identity.ecosystem = "vial";
  const capability = source.capabilities.lighting.surfaces[0];
  capability.generation = "vialrgb";
  capability.effects = [{id: 1}];
  capability.stream = {
    protocol: "vialrgb-1",
    pixel_count: 2,
    max_chunk_pixels: 2,
    volatile: true,
  };

  const projected = createHubLightingState({
    profile: source,
    geometry: geometry(),
    targetCurrent: true,
  });
  assert.equal(projected.surfaces[0].controls.effect, false);
  assert.equal(projected.surfaces[0].controls.animation, true);

  const changed = reduceHubLightingProfile(
    source,
    {
      type: "SET_ANIMATION",
      surfaceId: "rgb_matrix",
      name: "Exact pixels",
      pixelIds: ["K_R0_C0", "K_R0_C1"],
      frames: [["#010203", "#AABBCC"]],
      frameMs: 90,
    },
    {geometry: geometry(), targetCurrent: true},
  );
  assert.deepEqual(changed.lighting.animations[0], {
    name: "Exact pixels",
    surface_id: "rgb_matrix",
    pixel_ids: ["K_R0_C0", "K_R0_C1"],
    frames: [["#010203", "#AABBCC"]],
    placement: "geometry_seam",
    frame_ms: 90,
  });
  assert.equal(source.lighting.animations, undefined);

  assert.throws(
    () => reduceHubLightingProfile(
      source,
      {
        type: "SET_ANIMATION",
        surfaceId: "rgb_matrix",
        name: "Incomplete",
        pixelIds: ["K_R0_C0"],
        frames: [["#010203"]],
      },
      {geometry: geometry().slice(0, 1), targetCurrent: true},
    ),
    /every streamed pixel/i,
  );
});

test("lighting mutations share the generic document undo history", () => {
  const initial = createHubKeymapState({
    profile: profile(),
    layout: [
      {key: "K_R0_C0", matrix_row: 0, matrix_col: 0, x: 0, y: 0, width: 45, height: 86, rotation: 0},
      {key: "K_R0_C1", matrix_row: 0, matrix_col: 1, x: 50, y: 0, width: 45, height: 86, rotation: 0},
    ],
    lightingGeometry: geometry(),
    target: target(),
  });
  const changed = reduceHubKeymapState(initial, {
    type: "SET_LIGHTING",
    action: {
      type: "SET_SURFACE_FIELD",
      surfaceId: "rgb_matrix",
      field: "brightness",
      value: 201,
    },
    targetCurrent: true,
  });

  assert.equal(changed.profile.lighting.surfaces[0].brightness, 201);
  assert.equal(changed.undo.length, 1);
  assert.equal(changed.dirty, true);
  const restored = reduceHubKeymapState(changed, {type: "UNDO"});
  assert.equal(restored.profile.lighting.surfaces[0].brightness, 200);
  assert.equal(restored.dirty, false);
});
