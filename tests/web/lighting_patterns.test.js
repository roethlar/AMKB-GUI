"use strict";

// The Patterns studio tool. Its contract is that nothing the interface can
// reach falls outside the settings am_configurator/procedural.py accepts, so
// these guards walk the whole reachable space rather than sampling it.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const js = read("am_configurator/web/app.js");
const css = read("am_configurator/web/style.css");
const engine = read("am_configurator/procedural.py");
const server = read("am_configurator/server.py");
const {
  PATTERN_ARRANGEMENTS,
  PATTERN_COLORS,
  PATTERN_KINDS,
  PATTERN_SPEEDS,
  buildPatternRecipe,
  clampPatternSettings,
  defaultPatternSettings,
  nextPatternSeed,
  patternControlValues,
  patternKindById,
  patternUsesControl,
} = require("../../am_configurator/web/lighting_state.js");

// procedural.recipe_schema() layer bounds, mirrored. The cross-check below
// keeps the kind list itself honest against the engine.
const LAYER_BOUNDS = {
  color_index: [0, 4],
  secondary_color_index: [0, 4],
  phase: [0, 1],
  direction_degrees: [0, 360],
  center_x: [0, 1],
  center_y: [0, 1],
  scale: [0.05, 1.5],
  width: [0.02, 1],
  trail: [0, 1],
  count: [1, 12],
  intensity: [0.05, 1],
  seed: [0, 9999],
};
const LAYER_KEYS = ["kind", "speed", ...Object.keys(LAYER_BOUNDS)].sort();
const SPEEDS = [-3, -2, -1, 1, 2, 3];

// Slice 1 of the picker plan recorded the caps that keep these four inside the
// engine's acceptance checks. They are load-bearing, not decorative.
const RECORDED_CAPS = {
  chase: {count: 2},
  matrix_rain: {trail: 0.1},
  fire: {scale: 0.9},
  heartbeat: {width: 0.6},
};

function maxChannel(color) {
  return Math.max(...[1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16)));
}

// Every settings object the panel can produce for one pattern: each control at
// each of its allowed steps, crossed with every speed and both colour fields.
function reachableSettings(kind) {
  let combinations = [{kind: kind.id}];
  for (const control of kind.controls) {
    const next = [];
    for (const partial of combinations) {
      for (const value of patternControlValues(control)) {
        next.push({...partial, [control.id]: value});
      }
    }
    combinations = next;
  }
  const withSpeed = [];
  for (const partial of combinations) {
    for (const speed of PATTERN_SPEEDS) withSpeed.push({...partial, speed: speed.value});
  }
  const seeds = kind.shuffle ? PATTERN_ARRANGEMENTS : [0];
  const settings = [];
  for (const partial of withSpeed) {
    for (const seed of seeds) settings.push({...partial, seed});
  }
  return settings;
}

test("the fourteen offered patterns are exactly the engine's own primitives", () => {
  const block = engine.slice(engine.indexOf("_KINDS = {"), engine.indexOf("}", engine.indexOf("_KINDS = {")));
  const engineKinds = [...block.matchAll(/"([a-z_]+)"/g)].map(match => match[1]).sort();
  assert.equal(engineKinds.length, 14, "the engine must publish fourteen primitives");
  assert.deepEqual(PATTERN_KINDS.map(kind => kind.id).sort(), engineKinds);
  assert.equal(new Set(PATTERN_KINDS.map(kind => kind.label)).size, PATTERN_KINDS.length);
});

test("every reachable pattern setting builds a recipe inside the engine's bounds", () => {
  let checked = 0;
  for (const kind of PATTERN_KINDS) {
    for (const settings of reachableSettings(kind)) {
      for (const main of PATTERN_COLORS) {
        const recipe = buildPatternRecipe({
          ...settings,
          main_color: main.value,
          second_color: PATTERN_COLORS[(PATTERN_COLORS.indexOf(main) + 4) % PATTERN_COLORS.length].value,
        });
        checked += 1;
        assert.equal(recipe.schema_version, 1);
        assert.ok(recipe.name.length >= 1 && recipe.name.length <= 80);
        assert.equal(recipe.density, "dense");
        assert.match(recipe.background, /^#[0-9A-F]{6}$/);
        assert.ok(recipe.palette.length >= 1 && recipe.palette.length <= 5);
        for (const color of recipe.palette) assert.match(color, /^#[0-9A-F]{6}$/);
        assert.equal(recipe.layers.length, 1);
        const layer = recipe.layers[0];
        assert.deepEqual(Object.keys(layer).sort(), LAYER_KEYS);
        assert.equal(layer.kind, kind.id);
        assert.ok(SPEEDS.includes(layer.speed), `${kind.id} speed ${layer.speed}`);
        assert.ok(layer.color_index < recipe.palette.length);
        assert.ok(layer.secondary_color_index < recipe.palette.length);
        for (const [field, [low, high]] of Object.entries(LAYER_BOUNDS)) {
          assert.ok(
            Number.isFinite(layer[field]) && layer[field] >= low && layer[field] <= high,
            `${kind.id} ${field}=${layer[field]} outside ${low}..${high}`,
          );
        }
        for (const field of ["color_index", "secondary_color_index", "count", "seed", "speed"]) {
          assert.ok(Number.isInteger(layer[field]), `${kind.id} ${field} must be whole`);
        }
        for (const [field, cap] of Object.entries(RECORDED_CAPS[kind.id] || {})) {
          assert.ok(layer[field] <= cap, `${kind.id} ${field}=${layer[field]} exceeds the recorded cap ${cap}`);
        }
      }
    }
  }
  assert.ok(checked > 3000, `the walk must be exhaustive, not a sample (saw ${checked})`);
});

test("the always-on wash keeps every pattern inside its own fullness band", () => {
  // "dense" needs at least 70% of the lights above the engine's lit threshold
  // of 32 on every frame. A wash brighter than that on every light makes the
  // band unconditional, which is why no pattern has to bound its density.
  for (const color of PATTERN_COLORS) {
    assert.ok(maxChannel(color.value) === 255, `${color.label} must have a full channel`);
    const recipe = buildPatternRecipe({...defaultPatternSettings("comet"), main_color: color.value});
    assert.ok(
      maxChannel(recipe.background) > 32,
      `${color.label} wash ${recipe.background} must stay above the lit threshold`,
    );
  }
});

test("only the controls a pattern consumes are offered, and the rest stay fixed", () => {
  const consumed = {
    comet: ["size", "count", "trail", "direction"],
    wave: ["size", "spread", "direction"],
    pulse: ["size", "spread"],
    sparkle: ["count", "seed"],
    orbit: ["size", "spread", "count"],
    sweep: ["size", "direction"],
    noise: ["size", "seed"],
    breathe: ["size"],
    chase: ["count", "trail"],
    ripple: ["size", "spread"],
    matrix_rain: ["trail", "direction", "seed"],
    heartbeat: ["size"],
    fire: ["size", "spread", "seed"],
    twinkle: ["size", "seed"],
  };
  for (const kind of PATTERN_KINDS) {
    const offered = [...kind.controls.map(control => control.id), ...(kind.shuffle ? ["seed"] : [])];
    assert.deepEqual(offered.sort(), [...consumed[kind.id]].sort(), `${kind.id} control surface`);
    for (const control of ["size", "spread", "direction", "count", "trail", "seed"]) {
      assert.equal(
        patternUsesControl(kind.id, control),
        consumed[kind.id].includes(control),
        `${kind.id} ${control}`,
      );
    }
    // Anything the pattern does not consume is written at the fixed default.
    const layer = buildPatternRecipe(defaultPatternSettings(kind.id)).layers[0];
    if (!patternUsesControl(kind.id, "direction")) assert.equal(layer.direction_degrees, 0);
    if (!patternUsesControl(kind.id, "count")) assert.equal(layer.count, 1);
    if (!patternUsesControl(kind.id, "trail")) assert.equal(layer.trail, 0);
    if (!patternUsesControl(kind.id, "seed")) assert.equal(layer.seed, 0);
    assert.equal(layer.phase, 0);
    assert.equal(layer.center_x, 0.5);
    assert.equal(layer.center_y, 0.5);
    assert.equal(layer.intensity, 1);
  }
});

test("settings from anywhere snap onto an allowed step instead of escaping", () => {
  const hostile = clampPatternSettings({
    kind: "not_a_pattern",
    main_color: "#010101",
    second_color: "javascript:alert(1)",
    speed: 99,
    size: 40,
    spread: -12,
    direction: 4000,
    count: 500,
    trail: 7,
    seed: 10 ** 9,
  });
  const fallback = PATTERN_KINDS[0];
  assert.equal(hostile.kind, fallback.id);
  assert.deepEqual(hostile, clampPatternSettings(hostile));
  const recipe = buildPatternRecipe(hostile);
  assert.ok(PATTERN_COLORS.some(color => color.value === recipe.palette[0]));
  assert.ok(PATTERN_COLORS.some(color => color.value === recipe.palette[1]));
  assert.ok([1, 2, 3].includes(recipe.layers[0].speed));
  for (const control of fallback.controls) {
    assert.ok(
      patternControlValues(control).includes(hostile[control.id]),
      `${control.id} must land on an allowed step`,
    );
  }
  assert.deepEqual(
    clampPatternSettings(null),
    clampPatternSettings(defaultPatternSettings(fallback.id)),
  );
});

test("the same arrangement always builds the same lighting", () => {
  const kind = patternKindById("sparkle");
  assert.ok(kind.shuffle, "sparkle must offer an arrangement");
  const [first, second] = PATTERN_ARRANGEMENTS;
  const base = {...defaultPatternSettings("sparkle"), seed: first};
  assert.deepEqual(buildPatternRecipe(base), buildPatternRecipe({...base}));
  assert.notDeepEqual(buildPatternRecipe(base), buildPatternRecipe({...base, seed: second}));
  assert.equal(buildPatternRecipe(base).layers[0].seed, first);

  // Shuffle only ever lands on a checked arrangement, and nothing else moves.
  for (const roll of [0, 0.25, 0.5, 0.999999, 1, -0.25, Number.NaN]) {
    const seed = nextPatternSeed(() => roll);
    assert.ok(PATTERN_ARRANGEMENTS.includes(seed), `roll ${roll} gave ${seed}`);
  }
  assert.equal(nextPatternSeed(() => 0.5), nextPatternSeed(() => 0.5));
  const shuffled = clampPatternSettings({...base, seed: nextPatternSeed(() => 0.1234)});
  assert.deepEqual(
    {...shuffled, seed: base.seed},
    base,
    "shuffling must change the arrangement and nothing else",
  );
  // Every roll in [0, 1) is reachable and stays on the list.
  const reached = new Set();
  for (let step = 0; step < 1000; step += 1) reached.add(nextPatternSeed(() => step / 1000));
  assert.deepEqual([...reached].sort((a, b) => a - b), [...PATTERN_ARRANGEMENTS]);
});

test("arrangements come from the checked list, never a free number", () => {
  assert.ok(PATTERN_ARRANGEMENTS.length >= 8, "the list must offer real variety");
  assert.equal(new Set(PATTERN_ARRANGEMENTS).size, PATTERN_ARRANGEMENTS.length);
  for (const value of PATTERN_ARRANGEMENTS) {
    assert.ok(Number.isInteger(value) && value >= 0 && value <= 9999);
  }
  for (const kind of PATTERN_KINDS.filter(entry => entry.shuffle)) {
    for (const candidate of [-5, 1, 4242, 9999, "3", null]) {
      const settings = clampPatternSettings({...defaultPatternSettings(kind.id), seed: candidate});
      assert.ok(
        PATTERN_ARRANGEMENTS.includes(settings.seed),
        `${kind.id} kept an unchecked arrangement ${settings.seed}`,
      );
    }
  }
  // Sparkle's points can miss every light when they are small, so its size is
  // pinned at the checked constant instead of being offered as a step.
  assert.equal(buildPatternRecipe(defaultPatternSettings("sparkle")).layers[0].width, 1);
  assert.equal(patternKindById("sparkle").fixed.size, 1);
});

test("a pattern without an arrangement ignores a stored one", () => {
  const settings = clampPatternSettings({...defaultPatternSettings("wave"), seed: 777});
  assert.equal(settings.seed, 0);
  assert.equal(buildPatternRecipe(settings).layers[0].seed, 0);
});

test("Create sends exactly the body the render route accepts", () => {
  const start = js.indexOf("async function createPatternLighting()");
  const create = js.slice(start, js.indexOf("\nfunction wireStudioInspector()", start));
  assert.ok(create.length > 0, "createPatternLighting must exist");
  assert.match(create, /api\(\s*"\/api\/lighting\/render",\{/);
  assert.match(create, /method:"POST"/);
  assert.match(create, /recipe:buildPatternRecipe\(settings\)/);
  assert.match(create, /product_id:product/);
  assert.match(create, /targets:\[target\]/);
  // The route rejects any other key set, so the body must stay these three.
  const bodyStart = create.indexOf("JSON.stringify({");
  const body = create.slice(bodyStart, create.indexOf("}),", bodyStart));
  assert.deepEqual(
    [...body.matchAll(/^\s{8}([a-z_]+):/gm)].map(match => match[1]).sort(),
    ["product_id", "recipe", "targets"],
  );
  assert.match(server, /set\(body\) != \{"recipe", "product_id", "targets"\}/);
  // The result opens the way a Library item made this way already opens.
  assert.match(create, /openLibraryBoardPreview\(\{/);
  assert.match(create, /kind:"library_generated"/);
  assert.match(create, /latestLibraryGeneratedAttempt\(detail\)/);
  assert.match(create, /state\.library\.loaded=false/);
  // No second copy of the engine, and no background job machinery.
  assert.doesNotMatch(js, /_sample_layer|renderPatternFrames/);
  assert.doesNotMatch(create, /JOB_SYNCED|activeJob|setInterval|poll/);
});

test("a rejected effect and a stopped one are explained without engine words", () => {
  const start = js.indexOf("function patternFailureDetail(error)");
  const detail = js.slice(start, js.indexOf("\nasync function loadPatternMappedResult", start));
  assert.match(detail, /error\?\.code==="quality_failed"/);
  assert.match(detail, /error\?\.status===409/);
  for (const term of ["quality", "density", "seam", "brightness", "motion", "recipe"]) {
    assert.doesNotMatch(
      detail.replace(/quality_failed/g, ""),
      new RegExp(term, "i"),
      `${term} must not reach the panel copy`,
    );
  }
  assert.match(detail, /Nothing was saved/);
});

// The panel's own markup builders, run for real against the shared tables.
function patternPanel(overrides = {}) {
  const start = js.indexOf("function currentPatternSettings()");
  const source = js.slice(start, js.indexOf("\nfunction wirePatternTool()", start));
  const state = {studioTool: "pattern", patternSettings: null, patternBusy: false, patternError: "", ...overrides};
  const context = {
    state,
    esc: require("../../am_configurator/web/lighting_state.js").escapeMarkup,
    ...require("../../am_configurator/web/lighting_state.js"),
    renderLightingEdit() {},
  };
  vm.runInNewContext(`${source}\nglobalThis.build=patternToolMarkup;globalThis.pick=updatePatternSettings;`, context);
  return {context, state};
}

test("the panel renders one complete control set for every pattern", () => {
  const {context, state} = patternPanel();
  for (const kind of PATTERN_KINDS) {
    context.pick({kind: kind.id});
    const markup = context.build();
    assert.match(markup, /id="studio-pattern-panel"/);
    assert.match(markup, new RegExp(`data-pattern-kind="${kind.id}"[^>]*aria-pressed="true"`));
    assert.match(markup, /data-pattern-color="main_color"/);
    assert.match(markup, /data-pattern-color="second_color"/);
    assert.match(markup, /data-pattern-speed="2"/);
    assert.match(markup, /id="pattern-create"/);
    for (const control of kind.controls) {
      assert.match(
        markup,
        new RegExp(`data-pattern-control="${control.id}"`),
        `${kind.id} must offer ${control.id}`,
      );
      assert.ok(markup.includes(`>${control.label}</label>`), `${kind.id} ${control.label}`);
    }
    for (const control of ["size", "spread", "direction", "count", "trail"]) {
      if (kind.controls.some(entry => entry.id === control)) continue;
      assert.doesNotMatch(
        markup,
        new RegExp(`data-pattern-control="${control}"`),
        `${kind.id} must not offer ${control}`,
      );
    }
    assert.equal(
      markup.includes('id="pattern-shuffle"'),
      kind.shuffle,
      `${kind.id} shuffle button`,
    );
    // No stray template holes and no unbalanced control groups.
    assert.doesNotMatch(markup, /undefined|\[object Object\]|NaN/);
    assert.equal(
      (markup.match(/<div class="control-group">/g) || []).length,
      4 + kind.controls.length + (kind.shuffle ? 1 : 0),
    );
  }
  assert.equal(state.patternSettings.kind, PATTERN_KINDS[PATTERN_KINDS.length - 1].id);
});

test("the panel says plainly what Create does, and what a busy or failed one means", () => {
  assert.match(patternPanel().context.build(), /Create keeps a copy in Library/);
  assert.match(patternPanel({patternBusy: true}).context.build(), /Creating…/);
  const failed = patternPanel({patternError: "Nothing was saved."}).context.build();
  assert.match(failed, /Could not create this lighting/);
  assert.match(failed, /Nothing was saved\./);
});

test("Patterns is a studio tool beside the existing three", () => {
  const tools = js.slice(js.indexOf("function availableStudioTools()"), js.indexOf("function resumeUnfinishedMediaComposition"));
  assert.match(tools, /\["paint","source","animate","pattern"\]/);
  assert.match(js, /data-studio-tool="pattern">Patterns<\/button>/);
  assert.match(js, /id="studio-pattern-panel" class="studio-tool-panel" role="tabpanel"/);
  assert.match(js, /aria-labelledby="studio-pattern-tab"/);
  assert.match(js, /wirePatternTool\(\);/);
  // The existing Effects tool and the dormant job scaffolding are untouched.
  assert.match(js, /data-studio-tool="animate">Effects<\/button>/);
  assert.match(js, /state\.localAnimationEffect/);
  assert.match(css, /\.pattern-swatch \{/);
});
