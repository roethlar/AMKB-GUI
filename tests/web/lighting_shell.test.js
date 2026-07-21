"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("pure lighting state loads before the application adapter", () => {
  const stateScript = html.indexOf('<script src="/lighting_state.js"></script>');
  const appScript = html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript >= 0, "lighting_state.js script is missing");
  assert.ok(stateScript < appScript, "lighting_state.js must load before app.js");
  assert.match(server, /"\/lighting_state\.js":\s*"lighting_state\.js"/);
});

test("persistent job strip is a stable sibling outside routed content", () => {
  const strip = html.indexOf('id="lighting-job-strip"');
  const routeContent = html.indexOf('id="route-content"');
  const routeEnd = html.indexOf("</main>", routeContent);
  assert.ok(strip >= 0 && strip < routeContent, "job strip must precede routed content");
  assert.ok(routeContent >= 0 && routeEnd > routeContent, "routed content must be inside main");
  assert.match(html, /id="lighting-job-phase-live"[^>]*aria-live="polite"/);
  const openingTag = html.slice(html.lastIndexOf("<", strip), html.indexOf(">", strip) + 1);
  assert.doesNotMatch(openingTag, /aria-live|role="status"/);
});

test("Lighting Create, Library, and Edit are semantic roving tabs", () => {
  assert.match(html, /role="tablist"[^>]*aria-label="Lighting Studio"/);
  for (const name of ["create", "library", "edit"]) {
    assert.match(html, new RegExp(`id="lighting-${name}-tab"[^>]*role="tab"[^>]*aria-controls="lighting-${name}-panel"`));
    assert.match(html, new RegExp(`id="lighting-${name}-tab"[^>]*aria-selected="(?:true|false)"[^>]*tabindex="(?:0|-1)"`));
    assert.match(html, new RegExp(`id="lighting-${name}-panel"[^>]*role="tabpanel"[^>]*aria-labelledby="lighting-${name}-tab"`));
  }
  for (const key of ["ArrowLeft", "ArrowRight", "Home", "End"]) assert.match(js, new RegExp(key));
});

test("Lighting tab activation keeps focus within the roving tablist", () => {
  const start = js.indexOf("$$('[data-lighting-route]')");
  const end = js.indexOf("$$('[data-lighting-slot]')", start);
  const wiring = js.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.doesNotMatch(wiring, /focusHeading/);
});

test("destination selectors expose their selected value without relying on color", () => {
  assert.match(html, /class="segmented compact" role="group" aria-label="Custom slot"/);
  assert.match(html, /data-lighting-slot="5"[^>]*aria-pressed="true"[^>]*aria-label="Custom slot 1"/);
  assert.match(html, /id="lighting-target-controls"[^>]*role="group"/);
  assert.match(js, /setAttribute\("aria-pressed"/);
  assert.match(js, /data-lighting-target=.*aria-pressed=/);
});

test("Library and Settings have document-independent routed surfaces", () => {
  assert.match(html, /id="lighting-library-panel"/);
  assert.match(html, /id="settings-screen"/);
  assert.match(js, /ROUTES\.LIBRARY/);
  assert.match(js, /ROUTES\.SETTINGS/);
  assert.match(js, /function renderRoute\s*\(/);
});

test("a restored Settings route refreshes after persisted settings load", () => {
  const refresh = js.match(/function refreshAiGate\s*\(\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(refresh, /ROUTES\.SETTINGS/);
  assert.match(refresh, /populateSettings\(\)/);
});

test("shell supports narrow windows, zoom, focus, and reduced motion", () => {
  assert.doesNotMatch(css, /min-width:\s*880px/);
  assert.match(css, /textarea:focus-visible/);
  assert.match(css, /@media\s*\(max-width:\s*720px\)/);
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
});
