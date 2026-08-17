"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");

test("OpenKeeb owns the visible application identity", () => {
  assert.match(html, /<title>OpenKeeb<\/title>/);
  assert.match(html, /class="brand-lockup"/);
  assert.match(html, /class="brand-name">OpenKeeb</);
  assert.match(html, /id="about-title">OpenKeeb</);
  assert.doesNotMatch(html, /AM Configurator/);
});

test("shell separates document work from keyboard hardware actions", () => {
  assert.match(html, /class="top-actions document-actions"/);
  assert.match(html, /class="top-actions hardware-actions"/);
  assert.match(html, /class="command-divider"/);
  assert.match(html, /class="workspace-context"/);
});

test("empty state positions the broad local keyboard workbench", () => {
  assert.match(html, /One workbench for open keyboards/);
  assert.match(html, /AM, Vial, and VIA/);
  assert.match(html, /Connect a keyboard/);
  assert.match(html, /Open a profile/);
});

test("OpenKeeb workbench tokens are structural and responsive", () => {
  assert.match(css, /--brand-violet:/);
  assert.match(css, /--live-cyan:/);
  assert.match(css, /\.brand-rail/);
  assert.match(css, /\.command-bar/);
  assert.match(css, /\.workspace-context/);
  assert.match(css, /@media \(max-width: 1000px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});

test("every work surface uses the ecosystem-aware workbench hierarchy", () => {
  assert.ok((js.match(/class="screen-header workbench-header"/g) || []).length >= 3);
  assert.match(js, /class="ecosystem-badge"/);
  assert.match(js, /Angry Miao workspace/);
  assert.match(js, /OpenKeeb profile/);
  assert.match(js, /Keyboard unchanged until Write/);
  assert.match(html, /<h1 id="lighting-title"[^>]*>Lighting Studio</);
  assert.match(html, /class="lighting-capability-note"/);
  assert.match(css, /\.workbench-header/);
  assert.match(css, /\.ecosystem-badge/);
  assert.match(css, /\.safety-note/);
});

test("dialogs and supporting routes use product language instead of internal hub jargon", () => {
  assert.doesNotMatch(html, />Hub profile</);
  assert.doesNotMatch(html, />Open hub document</);
  assert.match(html, />OpenKeeb profile</);
  assert.match(html, /class="ecosystem-key"/);
  assert.match(html, /AM · Vial · VIA/);
  assert.match(html, /OpenKeeb Library/);
  assert.match(js, /OpenKeeb profile saved/);
  assert.doesNotMatch(js, /Hub document (saved|opened)/);
});
