"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");

function htmlSection(id) {
  const start = html.indexOf(`id="${id}"`);
  assert.ok(start >= 0, `index.html must contain id="${id}"`);
  const end = html.indexOf("</section>", start);
  return html.slice(start, end);
}

function jsFunction(name, nextMarker) {
  const start = js.indexOf(`function ${name}`);
  assert.ok(start >= 0, `app.js must define ${name}`);
  return js.slice(start, js.indexOf(nextMarker, start + 1));
}

test("empty state offers connect and open as primary tasks with no merge concepts", () => {
  const emptyState = htmlSection("empty-state");
  assert.match(emptyState, /id="empty-connect"/);
  assert.match(emptyState, /Connect a keyboard/);
  assert.match(emptyState, /never writes/i);
  assert.match(emptyState, /id="empty-open"/);
  assert.match(emptyState, /Open a JSON profile/);
  assert.match(emptyState, /lighting is preserved/i);
  assert.doesNotMatch(emptyState, /merge/i);
  assert.match(js, /\$\("#empty-connect"\)\.addEventListener\("click",showDeviceDialog\)/);
  assert.match(js, /\$\("#empty-open"\)\.addEventListener\("click",\(\)=>\$\("#open-input"\)\.click\(\)\)/);
  assert.match(css, /\.task-card/);
  // The empty state no longer changes copy per route or leads with jargon.
  assert.doesNotMatch(js, /Open a configuration to \$\{label\}/);
  assert.doesNotMatch(html, /Local keyboard studio/);
});

test("merge is contextual: absent without a document, offered for key-only exports", () => {
  assert.match(html, /<button id="merge-button"[^>]*\shidden[^>]*>/);
  assert.match(js, /\$\("#merge-button"\)\.hidden = !state\.config/);
  assert.match(js, /id="merge-led"/);
});

test("matrix numbers and raw keycodes stay hidden until requested", () => {
  assert.match(js, /id="toggle-technical-labels"[^`]*aria-pressed="\$\{technical\}"/);
  assert.match(js, /\$\{technical\?`<span>\$\{index\}<\/span>`:''\}/);
  assert.match(js, /<details id="advanced-keycode" class="advanced-disclosure"/);
  assert.match(js, /<summary>Advanced keycode<\/summary>/);
  const inspector = jsFunction("renderKeyInspector", "async function assignSelected");
  assert.ok(
    inspector.indexOf("Advanced keycode") < inspector.indexOf('id="raw-code"'),
    "raw keycode editing must live inside the Advanced keycode disclosure"
  );
  assert.match(
    inspector,
    /\$\{technical\?`<br><code>\$\{esc\(current\)\}<\/code>`:""\}/,
    new Error("the raw hex readout must only render when technical labels are requested")
  );
  assert.match(inspector, /technical\?` · Matrix \$\{state\.selected\}`:""/);
});

test("palette picks apply to the selected key immediately", () => {
  // A staged Apply proved unusable: the confirmation lived in the inspector,
  // which sits below the whole palette in single-column layouts.
  // cx-5: the handler must await async (Neon) validation before restoring
  // focus, or the post-validation rerender destroys the focused node.
  assert.match(js, /\$\$\("\.palette-key"\)\.forEach\(button => button\.addEventListener\("click", async \(\) => \{\s*await assignSelected\(button\.dataset\.code\);/);
  assert.doesNotMatch(js, /pendingCode/);
  assert.match(js, /applied to this key immediately/);
});

test("lossless raw assignment still round-trips", () => {
  assert.match(js, /id="raw-code" class="text-field" value="\$\{esc\(current\)\}" maxlength="9" aria-label="Raw keycode"/);
  assert.match(js, /\$\("#apply-raw"\)\?\.addEventListener\("click", \(\) => assignSelected\(\$\("#raw-code"\)\.value\.trim\(\)\)\)/);
  assert.match(js, /#\[0-9a-f\]\{8\}\$\/i\.test\(code\)/);
  assert.match(js, /\/api\/keymap\/assignment/);
});

test("macro editor offers Text entry and Flow modes; Advanced keeps structure and capacity", () => {
  assert.match(js, /● Record keys/);
  assert.match(js, /id="mode-text"/);
  assert.match(js, /id="mode-flow"/);
  assert.match(js, />Text entry</);
  assert.match(js, /This macro has events text can't express/);
  // Text entry: the macro is a text box plus one timing choice.
  assert.match(js, /name="macro-timing" value="fast"/);
  assert.match(js, /name="macro-timing" value="slow"/);
  assert.match(js, /name="macro-timing" value="natural"/);
  assert.match(js, /id="macro-wpm"/);
  assert.match(js, /id="cadence-capture"/);
  assert.match(js, /id="text-replace"/);
  assert.match(js, /id="text-append"/);
  assert.match(js, /\{text,\.\.\.macroTimingRequest\(\)\}/);
  assert.match(js, /Raise the delay if an app drops characters/);
  // Mode derivation: Text entry only when the macro decodes as clean text.
  assert.match(js, /state\.macroMode\?\?\(decoded\?"text":"flow"\)/);
  // Flow edits key, press/release, and pause in place.
  const sequence = jsFunction("renderMacroSequence", "const MACRO_TEXT_KEYS");
  assert.match(sequence, /data-action="\$\{event\.index\}"/);
  assert.match(sequence, /data-event-key="\$\{event\.index\}"/);
  assert.match(sequence, /data-delay="\$\{event\.index\}"/);
  assert.match(sequence, /Outside the standard key list/);
  // The Sequence renders before the Advanced disclosure; structure and capacity stay under it.
  const macros = jsFunction("renderMacros", "const DOM_USAGE");
  const template = macros.slice(0, macros.indexOf("$(\"#add-macro\")"));
  const advancedAt = template.indexOf('id="macro-advanced"');
  assert.ok(advancedAt >= 0);
  assert.match(js, /<summary>Edit individual events<\/summary>/);
  for (const marker of ['id="add-event"', "data-remove=", "limit-meter"]) {
    assert.ok(template.indexOf(marker) > advancedAt, `${marker} must sit inside the Edit individual events disclosure`);
  }
  // Track counts and the capacity meter left the normal header.
  const header = macros.slice(macros.indexOf("screen-header"), macros.indexOf("macro-layout"));
  assert.doesNotMatch(header, /tracks|limit-meter|capacity\.used/);
});

test("text entry opens only for clean text; decode is the exact compiler inverse", () => {
  const start = js.indexOf("const MACRO_MODIFIER_NAMES");
  const end = js.indexOf("function renderMacroTextMode", start);
  assert.ok(start >= 0 && end > start);
  const helpers = js.slice(start, end);
  const codeParts = code => {
    const match = /^#([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{4})$/i.exec(code || "");
    return match ? {modifier: parseInt(match[1], 16), page: parseInt(match[2], 16), usage: parseInt(match[3], 16)} : null;
  };
  const macroTextDecode = new Function("codeParts", `${helpers}; return macroTextDecode;`)(codeParts);
  // "ab" compiled at fast timing (fixtures mirror the Python compiler output).
  assert.deepEqual(
    macroTextDecode({layer_key:["#11070004","#10070004","#11070005","#10070005"], intvel_ms:[1,10,1,0]}),
    {text:"ab", rhythm:10}
  );
  // "A!" shares one Shift run.
  assert.deepEqual(
    macroTextDecode({layer_key:["#110700E1","#11070004","#10070004","#1107001E","#1007001E","#100700E1"], intvel_ms:[1,1,10,1,10,0]}),
    {text:"A!", rhythm:10}
  );
  // Staggered pauses are natural timing: still text, no uniform rhythm.
  assert.deepEqual(
    macroTextDecode({layer_key:["#11070004","#10070004","#11070005","#10070005","#11070006","#10070006"], intvel_ms:[1,77,1,123,1,0]}),
    {text:"abc", rhythm:null}
  );
  // Human-recorded presses (pause other than 1ms) and media events are not text.
  assert.equal(macroTextDecode({layer_key:["#11070004","#10070004"], intvel_ms:[5,10]}), null);
  assert.equal(macroTextDecode({layer_key:["#110C00E9"], intvel_ms:[0]}), null);
});

test("cadence capture samples only timing and is wired before macro recording", () => {
  assert.match(js, /if\(state\.cadenceCapture\)\{captureCadenceEvent\(event\);return;\}/);
  assert.match(js, /state\.macroCadence\.push\(Math\.max\(1,Math\.min\(1000,Math\.round\(now-state\.cadenceLast\)\)\)\)/);
  assert.match(js, /id="cadence-capture"/);
  assert.match(js, /pauses sampled/);
});

test("macro sequence keeps lowercase, Shift-uppercase, modifier combinations, key-up ordering, and pauses distinct", () => {
  const start = js.indexOf("const MACRO_MODIFIER_NAMES");
  const end = js.indexOf("async function applyMacroText", start);
  assert.ok(start >= 0 && end > start, "macro sequence helpers must be defined before the editor");
  const helpers = js.slice(start, end);
  const codeParts = code => {
    const match = /^#([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{4})$/i.exec(code || "");
    return match ? {modifier: parseInt(match[1], 16), page: parseInt(match[2], 16), usage: parseInt(match[3], 16)} : null;
  };
  const macroSequence = new Function("codeParts", "makeCode", "decodeCode", `${helpers}; return macroSequence;`)(
    codeParts,
    () => "#00000000",
    () => "other key"
  );
  assert.deepEqual(
    macroSequence({layer_key:["#11070004", "#10070004"], intvel_ms:[10, 0]}),
    [
      {index:0, label:"a", action:"press", delay:10},
      {index:1, label:"a", action:"release", delay:0},
    ]
  );
  assert.deepEqual(
    macroSequence({layer_key:["#110700E1", "#11070004", "#10070004", "#100700E1"], intvel_ms:[1, 10, 1, 0]}),
    [
      {index:0, label:"Shift", action:"press", delay:1},
      {index:1, label:"Shift + A", action:"press", delay:10},
      {index:2, label:"Shift + A", action:"release", delay:1},
      {index:3, label:"Shift", action:"release", delay:0},
    ]
  );
  assert.deepEqual(
    macroSequence({layer_key:["#110700E0", "#110700E1", "#11070004", "#10070004", "#100700E1", "#100700E0"], intvel_ms:[0, 0, 5, 0, 0, 0]}),
    [
      {index:0, label:"Ctrl", action:"press", delay:0},
      {index:1, label:"Shift", action:"press", delay:0},
      {index:2, label:"Ctrl + Shift + A", action:"press", delay:5},
      {index:3, label:"Ctrl + Shift + A", action:"release", delay:0},
      {index:4, label:"Shift", action:"release", delay:0},
      {index:5, label:"Ctrl", action:"release", delay:0},
    ]
  );
  // An unmatched key-up stays a plainly labelled release, in order.
  assert.deepEqual(
    macroSequence({layer_key:["#10070004"], intvel_ms:[0]}),
    [{index:0, label:"a", action:"release", delay:0}]
  );
});

test("sequence rows edit in place; non-standard events stay plainly labelled", () => {
  const start = js.indexOf("const MACRO_MODIFIER_NAMES");
  const end = js.indexOf("async function applyMacroText", start);
  const helpers = js.slice(start, end);
  const codeParts = code => {
    const match = /^#([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{4})$/i.exec(code || "");
    return match ? {modifier: parseInt(match[1], 16), page: parseInt(match[2], 16), usage: parseInt(match[3], 16)} : null;
  };
  const makeCode = (page, usage, modifier = 0) =>
    `#${modifier.toString(16).padStart(2,"0")}${page.toString(16).padStart(2,"0")}${usage.toString(16).padStart(4,"0")}`.toUpperCase();
  const renderMacroSequence = new Function("codeParts", "makeCode", "decodeCode", "esc", `${helpers}; return renderMacroSequence;`)(
    codeParts, makeCode, () => "Media key", String
  );
  const eventOptions = [{label:"A", code:"#00070004"}, {label:"L Shift", code:"#000700E1"}];
  const standard = renderMacroSequence({layer_key:["#11070004", "#10070004"], intvel_ms:[10, 0]}, eventOptions);
  assert.match(standard, /data-action="0"/);
  assert.match(standard, /data-event-key="0"/);
  assert.match(standard, /<option value="#00070004" selected>/);
  assert.match(standard, /value="10" data-delay="0"/);
  const media = renderMacroSequence({layer_key:["#110C00E9"], intvel_ms:[3]}, eventOptions);
  assert.match(media, /Media key/);
  assert.match(media, /Outside the standard key list/);
  assert.doesNotMatch(media, /data-event-key/);
  const malformed = renderMacroSequence({layer_key:["not-a-code"], intvel_ms:[0]}, eventOptions);
  assert.match(malformed, /Unrecognised event/);
  assert.doesNotMatch(malformed, /data-event-key|data-action/);
});

test("capacity failures stay pre-mutation with task language", () => {
  for (const site of [
    /const candidate=clone\(macros\(\)\);\s*candidate\[state\.macro\]\.layer_key\.push\("#11070004"\);[\s\S]{0,200}?if\(capacityError\)return toast\("Macro capacity reached"/,
    /candidate\[state\.macro\]\.layer_key\.push\(makeCode\(7,usage,down\?0x11:0x10\)\);[\s\S]{0,300}?if\(capacityError\)\{state\.recording=false;/,
    /const capacityError=macroCapacityError\(candidate\);\s*if\(capacityError\)throw new Error\(capacityError\);/,
  ]) assert.match(js, site);
  assert.match(js, /Shorten or remove some macros\./);
});

test("disclosures are native and focus is restored after re-renders", () => {
  assert.match(js, /function restoreFocus\(selector\) \{\s*requestAnimationFrame\(\(\) => document\.querySelector\(selector\)\?\.focus\(\{preventScroll: true\}\)\);\s*\}/);
  assert.match(js, /restoreFocus\("#toggle-technical-labels"\)/);
  assert.match(js, /restoreFocus\("#record-macro"\)/);
  assert.match(js, /restoreFocus\(`\.keycap\[data-index="\$\{button\.dataset\.index\}"\]`\)/);
  assert.match(js, /restoreFocus\(`\.palette-key\[data-code="\$\{button\.dataset\.code\}"\]`\)/);
  assert.match(js, /restoreFocus\(`\[data-layer="\$\{button\.dataset\.layer\}"\]`\)/);
  assert.match(js, /restoreFocus\(`\[data-macro="\$\{button\.dataset\.macro\}"\]`\)/);
  // Disclosure state survives re-renders instead of snapping shut.
  assert.match(js, /state\.advancedKeycodeOpen = event\.currentTarget\.open/);
  assert.match(js, /state\.macroAdvancedOpen=event\.currentTarget\.open/);
  assert.match(js, /\$\{state\.advancedKeycodeOpen\?"open":""\}/);
  assert.match(js, /\$\{state\.macroAdvancedOpen\?"open":""\}/);
});

function parseLayout(name) {
  const marker = `const ${name} = [`;
  const start = js.indexOf(marker);
  assert.ok(start >= 0, `${name} must exist`);
  const end = js.indexOf("];", start);
  const body = js.slice(start + marker.length, end).replace(/,\s*$/, "");
  return JSON.parse("[" + body + "]");
}

test("every authored physical key ends on the board", () => {
  for (const [name, minKeys] of [["RELIC_LAYOUT", 81], ["CB04_LAYOUT", 81]]) {
    const layout = parseLayout(name);
    assert.ok(layout.length >= minKeys, `${name} has ${layout.length} keys`);
    const indices = new Set();
    for (const [index, x, , w = 4.8] of layout) {
      assert.ok(!indices.has(index), `${name} repeats matrix index ${index}`);
      indices.add(index);
      assert.ok(x + w <= 100.0001, `${name} key ${index} ends at ${(x + w).toFixed(1)}% of the stage`);
    }
  }
  assert.match(js, /family === "CB" && productId\(\) === "CB04"/);
});

test("sidebar counts carry visible or accessible labels", () => {
  assert.match(js, /\["#nav-layers", state\.config \? layers\(\)\.length : null, "layer", "layers"\]/);
  assert.match(js, /"macro", "macros"\]/);
  assert.match(js, /"lighting slot", "lighting slots"\]/);
  assert.match(js, /node\.setAttribute\("aria-label", label\)/);
});
