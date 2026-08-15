"use strict";

// Slice P1 guards: the normal interface and every surfaced failure speak the
// product language contract (docs/superpowers/plans/
// 2026-07-29-product-experience-remediation.md → "Product Language Contract").
// Internal names, manifest fields, routes, and diagnostics keep their
// engineering terms, so these guards read user-visible strings only.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("am_configurator/web/index.html");
const js = read("am_configurator/web/app.js");
const workspace = read("am_configurator/web/lighting_workspace.js");
const libraryState = read("am_configurator/web/library_state.js");
const lightingState = read("am_configurator/web/lighting_state.js");

// Interpolated expressions inside a template literal are code, not copy.
function stripInterpolations(source) {
  let previous = null;
  let current = source;
  for (let pass = 0; pass < 12 && current !== previous; pass += 1) {
    previous = current;
    current = current.replace(/\$\{[^{}]*\}/g, " ");
  }
  return current;
}

// Only string literals can reach the interface; identifiers, object keys, and
// property names never do. Scanning literals keeps the sweep precise.
function stringLiterals(source) {
  const matches = source.match(
    /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g
  ) || [];
  return stripInterpolations(matches.join("\n"));
}

const BANNED = [
  [/\bbank(?:s|ed|ing)?\b/i, "bank/banked/banking → save/saved/saving to Library"],
  [/\bdurable\b/i, "durable job → generation continues in the background"],
  [/\bdeterministic\b/i, "deterministic → preview / plain description"],
  [/procedural recipe/i, "procedural recipe → lighting effect"],
  [/\bprocedural effect\b/i, "procedural effect → lighting effect"],
  [/exact LED frames?/i, "exact LED frames → lighting frames"],
  [/\bexact frames\b/i, "exact frames → lighting frames"],
  [/exact-raster/i, "exact-raster → lighting"],
  [/\braster\b/i, "raster dimensions → keyboard or display size"],
  [/model identity/i, "model identity changed → the model was updated"],
  [/identity changed/i, "model identity changed → the model was updated"],
  [/catalog identity/i, "catalog identity → saved Library item"],
  [/asset identity/i, "asset identity → saved Library item"],
  [/\bai[ _-]?generation\b/i, "ai generation → name what actually made the item"],
  [/quality (?:check|gate|failure)/i, "quality gate → plain reason the lighting was not made"],
];

test("no banned implementation vocabulary reaches user-visible copy", () => {
  const surfaces = [
    ["index.html", html],
    ["app.js", stringLiterals(js)],
    ["lighting_workspace.js", stringLiterals(workspace)],
    ["library_state.js", stringLiterals(libraryState)],
    ["lighting_state.js", stringLiterals(lightingState)],
  ];
  for (const [name, copy] of surfaces) {
    for (const [pattern, replacement] of BANNED) {
      const hit = copy.match(pattern);
      assert.equal(
        hit,
        null,
        `${name} still shows "${hit && hit[0]}" in user-visible copy (${replacement})`
      );
    }
  }
});

test("mapped and stored counts sit behind Technical details, not the canvas heading", () => {
  const heading = js.slice(
    js.indexOf('const boardPane='),
    js.indexOf('const timelineMarkup=')
  );
  assert.ok(heading.length > 0, "the Board heading must exist");
  assert.doesNotMatch(heading, /\/ \$\{length\} stored/);
  assert.match(heading, /<summary>Technical details<\/summary>/);
  const technical = heading.slice(heading.indexOf("<summary>Technical details</summary>"));
  assert.match(technical, /\$\{mappedCount\} of \$\{length\} stored colors/);
  assert.match(js, /const canvasSubtitle=\[/);
});

test("internal manifest, route, and element contracts are unchanged", () => {
  for (const field of [
    "procedural_attempts",
    "mapped_result_asset_id",
    "raster_animation",
    "media_source",
  ]) assert.ok(js.includes(field), `${field} must remain an internal manifest field`);
  for (const route of [
    "/api/library/import/media",
  ]) assert.ok(js.includes(route), `${route} must remain unchanged`);
  assert.match(html, /data-library-filter="sources"/);
  assert.match(js, /id="lighting-source-pane"/);
  assert.doesNotMatch(js, /data-source-preview|sourcePreviewMode/);
});
