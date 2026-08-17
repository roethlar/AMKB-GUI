"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("the pure hub reducer loads before the application adapter", () => {
  const reducer = html.indexOf('<script src="/hub_keymap_state.js"></script>');
  const app = html.indexOf('<script src="/app.js"></script>');
  assert.ok(reducer > 0);
  assert.ok(reducer < app);
  assert.match(js, /const \{createHubKeymapState,reduceHubKeymapState\}=HubKeymapState/);
});

test("one keymap adapter projects AM and generic hub documents", () => {
  const adapter = js.slice(
    js.indexOf("function keymapEditorAdapter"),
    js.indexOf("function renderKeymap"),
  );
  assert.match(adapter, /state\.hubEditor/);
  assert.match(adapter, /activeLayout\(\)/);
  assert.match(adapter, /layers\(\)/);
  assert.match(adapter, /reduceHubKeymapState/);
  assert.match(js, /const editor=keymapEditorAdapter\(\)/);
});

test("device discovery keeps AM, Vial, and VIA candidates explicit", () => {
  const scan = js.slice(
    js.indexOf("async function scanDevices"),
    js.indexOf("async function readDevice"),
  );
  assert.match(scan, /\/api\/devices/);
  assert.match(scan, /\/api\/hub\/vial\/devices/);
  assert.match(scan, /\/api\/hub\/via\/devices/);
  assert.match(js, /device\.ecosystem\|\|"am"/);
  assert.match(scan, /Keymap \+ macros \+ lighting/);
  assert.match(scan, /Definition required/);
});

test("VIA read waits for a user-imported definition", () => {
  assert.match(html, /id="via-definition-input"/);
  assert.match(js, /via-definition-input/);
  assert.match(js, /parseViaDefinitionText\(await file\.text\(\)\)/);
  assert.match(js, /function parseViaDefinitionText\(text\) \{\s*return JSON\.parse\(text\);/);
  const read = js.slice(
    js.indexOf("async function readHubDevice"),
    js.indexOf("async function readDevice"),
  );
  assert.match(read, /\/api\/hub\/via\/read/);
  assert.match(read, /definition/);
  assert.doesNotMatch(read, /\/preflight|\/write/);
});

test("generic hub open and save use canonical authenticated server boundaries", () => {
  assert.match(html, /id="hub-open-input"/);
  assert.match(html, /id="hub-open"/);
  assert.match(js, /\/api\/hub\/open/);
  assert.match(js, /\/api\/hub\/save/);
  assert.match(server, /loads_hub_profile\(payload\)/);
  assert.match(server, /dumps_hub_profile\(body\["profile"\]\)/);
});

test("live generic read response comes from an editor document, not a second read", () => {
  assert.match(server, /vial_transport\.read_hub_document\(address\)/);
  assert.match(server, /via_transport\.read_hub_document/);
  assert.match(server, /"device": document\.device/);
  assert.match(server, /"profile": document\.profile/);
  assert.match(server, /"layout": document\.layout/);
});
