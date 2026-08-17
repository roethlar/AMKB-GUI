"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("volatile preview has a separate exact-confirmation dialog", () => {
  assert.match(html, /id="stream-dialog"/);
  assert.match(html, /id="stream-confirmation"/);
  assert.match(html, /id="stream-start"/);
  assert.match(html, /id="stream-stop"/);
  assert.match(html, /Volatile keyboard preview/);
  assert.match(html, /never saved/);
  assert.match(css, /\.hub-animation-preview-list/);
  assert.match(css, /\.stream-status/);
});

test("preview lifecycle uses only the four authenticated stream routes", () => {
  const flow = js.slice(
    js.indexOf("function hubStreamActive"),
    js.indexOf("function renderLightingEdit"),
  );
  for (const route of ["preflight", "start", "status", "stop"]) {
    assert.match(flow, new RegExp(`/api/hub/vial/stream/${route}`));
    assert.match(server, new RegExp(`/api/hub/vial/stream/${route}`));
  }
  assert.match(flow, /profile:state\.hubEditor\.profile/);
  assert.match(flow, /animation_index:animationIndex/);
  assert.match(flow, /reduceHubStreamState/);
  assert.match(flow, /PREVIEW/);
  assert.match(flow, /setTimeout\(pollHubStream/);
  assert.doesNotMatch(flow, /\/api\/hub\/vial\/write/);
  assert.doesNotMatch(flow, /lighting_saves|save_lighting/);
});

test("active volatile preview excludes persistent Write and exposes Stop", () => {
  const actions = js.slice(
    js.indexOf("function updateDeviceActions"),
    js.indexOf("async function scanDevices"),
  );
  const editor = js.slice(
    js.indexOf("function renderHubLightingEdit"),
    js.indexOf("function mutateHubLighting"),
  );
  assert.match(actions, /hubStreamActive\(\)/);
  assert.match(actions, /Stop the volatile preview before persistent Write/);
  assert.match(editor, /Preview on keyboard/);
  assert.match(editor, /Stop preview/);
  assert.match(editor, /data-hub-stream-animation/);
});
