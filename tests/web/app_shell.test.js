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
  assert.match(js, /\$\$\("\.palette-key"\)\.forEach\(button => button\.addEventListener\("click", \(\) => \{\s*assignSelected\(button\.dataset\.code\);/);
  assert.doesNotMatch(js, /pendingCode/);
  assert.match(js, /applied to this key immediately/);
});

test("lossless raw assignment still round-trips", () => {
  assert.match(js, /id="raw-code" class="text-field" value="\$\{esc\(current\)\}" maxlength="9" aria-label="Raw keycode"/);
  assert.match(js, /\$\("#apply-raw"\)\?\.addEventListener\("click", \(\) => assignSelected\(\$\("#raw-code"\)\.value\.trim\(\)\)\)/);
  assert.match(js, /#\[0-9a-f\]\{8\}\$\/i\.test\(code\)/);
  assert.match(js, /\/api\/keymap\/assignment/);
});

test("normal macro path is Type text and Record keys; event editing stays complete under Advanced", () => {
  assert.match(js, /● Record keys/);
  assert.match(js, /<strong>Type text<\/strong>/);
  assert.match(js, /Delay between keys/);
  assert.match(js, /raise it if an app drops characters/);
  assert.match(js, /<details id="macro-advanced" class="advanced-disclosure"/);
  assert.match(js, /<summary>Edit individual events<\/summary>/);
  const macros = jsFunction("renderMacros", "const DOM_USAGE");
  const advancedAt = macros.indexOf('id="macro-advanced"');
  assert.ok(advancedAt >= 0);
  for (const marker of ['id="add-event"', "data-action=", "data-event-key=", "data-delay=", "data-remove=", "limit-meter"]) {
    const template = macros.slice(0, macros.indexOf("$(\"#add-macro\")"));
    assert.ok(template.indexOf(marker) > advancedAt, `${marker} must sit inside the Edit individual events disclosure`);
  }
  // Track counts and the capacity meter left the normal header.
  const header = macros.slice(macros.indexOf("screen-header"), macros.indexOf("macro-layout"));
  assert.doesNotMatch(header, /tracks|limit-meter|capacity\.used/);
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

test("every Relic key ends on the board", () => {
  const marker = "const RELIC_LAYOUT = [";
  const start = js.indexOf(marker);
  assert.ok(start >= 0);
  const end = js.indexOf("];", start);
  const body = js.slice(start + marker.length, end).replace(/,\s*$/, "");
  const layout = JSON.parse("[" + body + "]");
  assert.ok(layout.length > 80);
  for (const [index, x, , w = 4.8] of layout) {
    assert.ok(x + w <= 100.0001, `key ${index} ends at ${(x + w).toFixed(1)}% of the stage`);
  }
});

test("sidebar counts carry visible or accessible labels", () => {
  assert.match(js, /\["#nav-layers", state\.config \? layers\(\)\.length : null, "layer", "layers"\]/);
  assert.match(js, /"macro", "macros"\]/);
  assert.match(js, /"lighting slot", "lighting slots"\]/);
  assert.match(js, /node\.setAttribute\("aria-label", label\)/);
});
