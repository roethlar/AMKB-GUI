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

const exportFlow = js.slice(
  js.indexOf("async function exportHubProfile"),
  js.indexOf("function showHubReport"),
);
const reportFlow = js.slice(
  js.indexOf("function showHubReport"),
  js.indexOf("async function importHubFile"),
);
const importFlow = js.slice(
  js.indexOf("async function importHubFile"),
  js.indexOf("function freezeImportedValue"),
);

test("the Hub surface exists: toolbar button, dialog, hidden file input", () => {
  assert.match(html, /<button id="hub-button"/);
  assert.match(html, /<dialog id="hub-dialog"/);
  assert.match(html, /<input id="hub-import-input" type="file"/);
  assert.match(html, /id="hub-report-summary"/);
  assert.match(html, /id="hub-report-items"/);
  assert.match(js, /\$\("#hub-button"\)\.addEventListener/);
  assert.match(js, /\$\("#hub-export"\)\.addEventListener/);
  assert.match(js, /\$\("#hub-import-input"\)\.addEventListener/);
});

test("hub import parses on the server, never in the page", () => {
  // Same rule the JSON open path lives by: bytes go to the server, which
  // owns duplicate-key rejection and size caps. No client-side JSON.parse.
  assert.match(importFlow, /arrayBufferToBase64\(await file\.arrayBuffer\(\)\)/);
  assert.doesNotMatch(importFlow, /JSON\.parse/);
  assert.match(importFlow, /\/api\/hub\/apply/);
  assert.match(server, /loads_hub_profile\(payload\)/);
  assert.match(server, /_decode_import_data\(body\["data"\]\)/);
});

test("hub import adopts the document exactly like opening a JSON", () => {
  for (const step of [
    /stashDeviceDocument\(\)/,
    /state\.loadedDevice = null/,
    /state\.documentRevision = null/,
    /resetDocumentView\(\)/,
    /await synchronizeOpenDocument\(\)/,
    /markDirty\(true\)/,
  ]) {
    assert.match(importFlow, step);
  }
  assert.match(importFlow, /closeImportedLightingReview\(\{render: false\}\)/);
});

test("the transfer report renders as text, counts first, reasons for the rest", () => {
  // textContent everywhere: report paths and reasons are data, never markup.
  assert.doesNotMatch(reportFlow, /innerHTML/);
  assert.match(reportFlow, /carried over exactly/);
  assert.match(reportFlow, /adapted/);
  assert.match(reportFlow, /could not fit/);
  assert.match(reportFlow, /item\.reason/);
});

test("hub export downloads the canonical profile from the server", () => {
  assert.match(exportFlow, /\/api\/hub\/export/);
  assert.match(exportFlow, /\.hub\.json/);
  assert.doesNotMatch(exportFlow, /JSON\.parse/);
});

test("the report styles meet the design floors", () => {
  const items = css.match(/\.hub-report-items \{[^}]*\}/);
  assert.ok(items, "hub-report-items has styles");
  const size = items[0].match(/font-size:\s*([\d.]+)px/);
  assert.ok(size && Number(size[1]) >= 13, "report text at or above the 13px floor");
});
