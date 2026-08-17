"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");

test("generic Write requires the exact live editor binding", () => {
  const readiness = js.slice(
    js.indexOf("function genericWriteTarget"),
    js.indexOf("function updateDeviceActions"),
  );
  assert.match(readiness, /state\.hubEditor/);
  assert.match(readiness, /target\.address/);
  assert.match(readiness, /target\.scanEpoch!==state\.deviceScanEpoch/);
  assert.match(readiness, /state\.loadedDevice/);
  assert.match(readiness, /deviceKey\(device\)/);
  assert.match(readiness, /selectedDevice\(\)/);
  assert.match(js, /const genericTarget=genericWriteTarget\(\)/);
  assert.match(js, /async function scanDevices\(\) \{\s*state\.deviceScanEpoch\+\+/);
  assert.match(js, /target:\{ecosystem:target\.ecosystem,address:target\.address,scanEpoch/);
});

test("generic preflight presents exact backend proof without writing", () => {
  const flow = js.slice(
    js.indexOf("async function writeHubDevice"),
    js.indexOf("async function writeDevice"),
  );
  assert.match(flow, /\/api\/hub\/\$\{ecosystem\}\/preflight/);
  assert.match(flow, /profile:documentState\.profile/);
  assert.match(flow, /definition/);
  assert.match(flow, /preflight\.confirmation/);
  assert.match(flow, /keymap_bytes/);
  assert.match(flow, /macro_bytes/);
  assert.match(flow, /carried/);
  assert.match(flow, /adapted/);
  assert.match(flow, /dropped/);
  assert.match(flow, /unlock\?\.keys/);
  assert.match(flow, /unlock\.unlocked/);
  assert.match(flow, /unlock\.in_progress/);
  assert.doesNotMatch(flow, /\/write/);
});

test("generic confirmation is exact and accepted failures only re-preflight", () => {
  const confirm = js.slice(
    js.indexOf("async function confirmHubWrite"),
    js.indexOf("async function confirmDeviceWrite"),
  );
  assert.match(confirm, /typedConfirmation!==pending\.confirmation/);
  assert.match(confirm, /\/api\/hub\/\$\{pending\.ecosystem\}\/write/);
  assert.match(confirm, /pending\.verifyOnly=true/);
  assert.match(confirm, /matches_target/);
  assert.match(confirm, /Fresh read \/ verify failed/);
  assert.match(confirm, /Read \/ verify/);
  assert.doesNotMatch(confirm, /toUpperCase\(\)/);
  assert.doesNotMatch(confirm, /Retry/);
});

test("write dialog can switch from AM copy to bounded hub copy", () => {
  assert.match(html, /id="write-eyebrow"/);
  assert.match(html, /id="write-warning-title"/);
  assert.match(html, /id="write-warning-copy"/);
  assert.match(html, /id="write-target-note"/);
  assert.match(html, /id="write-confirm-label"/);
  assert.match(css, /\.keycap\.unlock-required/);
  assert.match(js, /saveHubDocument/);
});
