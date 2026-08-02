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

const {
  REVIEW_BLOCK_REASONS,
  reviewBlockedMessage,
} = require("../../am_configurator/web/lighting_review.js");

const root = path.resolve(__dirname, "../..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const html = read("am_configurator/web/index.html");
const js = read("am_configurator/web/app.js");
const review = read("am_configurator/web/lighting_review.js");
const workspace = read("am_configurator/web/lighting_workspace.js");
const libraryState = read("am_configurator/web/library_state.js");

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
];

test("no banned implementation vocabulary reaches user-visible copy", () => {
  const surfaces = [
    ["index.html", html],
    ["app.js", stringLiterals(js)],
    ["lighting_review.js", stringLiterals(review)],
    ["lighting_workspace.js", stringLiterals(workspace)],
    ["library_state.js", stringLiterals(libraryState)],
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

test("AI progress phases use the plan's task language everywhere they are shown", () => {
  const labels = js.slice(
    js.indexOf("function proceduralPhaseLabel"),
    js.indexOf("function proceduralProgressLabel")
  );
  for (const label of ["Creating lighting", "Checking the result", "Saving to Library"]) {
    assert.ok(labels.includes(`"${label}"`), `phase labels must include "${label}"`);
  }
  // The persistent strip must reuse the same mapping instead of echoing the
  // raw manifest phase name back to the user.
  const strip = js.slice(
    js.indexOf("function renderLightingJobStrip"),
    js.indexOf("function clearConceptAssetUrls")
  );
  assert.match(strip, /proceduralPhaseLabel\(job\.phase\)/);
  assert.doesNotMatch(strip, /job\.phase\.replaceAll/);
});

test("the progress explanation states what continues and what closing does", () => {
  assert.match(
    js,
    /You can open Library while this finishes\. Closing the progress view does not cancel generation\./
  );
});

function aiErrorMessages() {
  const start = js.indexOf("const AI_ERROR_MESSAGES = {");
  assert.ok(start >= 0, "app.js must define AI_ERROR_MESSAGES");
  const body = js.slice(start, js.indexOf("};", start));
  const entries = [...body.matchAll(/^\s{2}([a-z_]+):\s*"((?:[^"\\]|\\.)*)",$/gm)];
  assert.ok(entries.length >= 8, "every typed provider code must stay mapped");
  return entries.map(([, code, message]) => [code, message]);
}

test("every typed AI failure says what changed and what to do next", () => {
  const outcome = /nothing was (generated|changed|saved)/i;
  const action = /try again|then try|Settings|describe/i;
  for (const [code, message] of aiErrorMessages()) {
    assert.match(message, outcome, `${code} must say whether anything was saved or changed`);
    assert.match(message, action, `${code} must offer the next available action`);
  }
});

test("raw exception text is never surfaced through the AI error mapper", () => {
  const mapper = js.slice(
    js.indexOf("function aiErrorMessage(error)"),
    js.indexOf("// ---- Settings route")
  );
  assert.ok(mapper.length > 0, "aiErrorMessage must exist");
  assert.doesNotMatch(mapper, /error\?\.message|error\.message/);
  assert.match(mapper, /AI_ERROR_MESSAGES\[code\] \|\| AI_ERROR_FALLBACK/);
  assert.match(js, /const AI_ERROR_FALLBACK\s*=/);
  // A saved provider failure is reported through the same mapping, not by
  // echoing the stored error code at the user.
  const prompt = js.slice(
    js.indexOf("function renderPromptStage"),
    js.indexOf("function renderProgressStage")
  );
  assert.match(prompt, /aiErrorMessage\(\{code:stopped\}\)/);
  assert.doesNotMatch(prompt, /String\(stopped\)\.replaceAll/);
});

test("every blocked review explains the block, the state, and the next step", () => {
  for (const reason of [...REVIEW_BLOCK_REASONS, "unknown-reason"]) {
    const message = reviewBlockedMessage(reason);
    assert.match(message, /Nothing was changed|nothing has changed/i, `${reason} must state that nothing changed`);
    assert.match(message, /open|switch|try again/i, `${reason} must offer a next action`);
  }
});

test("Ollama and Direct API are the user-facing backend names", () => {
  const ollamaRow = html.slice(
    html.indexOf('id="settings-ai-ollama"'),
    html.indexOf('id="settings-ai-api"')
  );
  const apiRow = html.slice(
    html.indexOf('id="settings-ai-api"'),
    html.indexOf('id="settings-ollama-panel"')
  );
  assert.match(ollamaRow, /<strong>Ollama<\/strong>/);
  assert.match(apiRow, /<strong>Direct API<\/strong>/);
  assert.doesNotMatch(html, /API backend/);
  assert.doesNotMatch(js, /API backend/);
  // The backend contract's model-location labels are unchanged.
  assert.match(js, /On this Ollama server/);
  assert.match(js, /Ollama Cloud/);
});

test("generated-result review speaks in lighting effects and lighting frames", () => {
  assert.match(review, /"Lighting effect"/);
  assert.match(review, /lighting frames/);
  assert.match(review, /alt="Animated lighting preview"/);
  assert.match(review, /Loading the lighting effect/);
  assert.doesNotMatch(stringLiterals(review), /\brecipe\b/i);
});

test("mapped and stored counts sit behind Technical details, not the canvas heading", () => {
  const heading = js.slice(
    js.indexOf('<div class="card-header led-canvas-heading">'),
    js.indexOf('<div class="led-canvas-actions">')
  );
  assert.ok(heading.length > 0, "the LED canvas heading must exist");
  assert.doesNotMatch(heading, /\/ \$\{length\} stored/);
  assert.match(heading, /<summary>Technical details<\/summary>/);
  const technical = heading.slice(heading.indexOf("<summary>Technical details</summary>"));
  assert.match(technical, /\$\{mappedCount\} of \$\{length\} stored colors/);
  assert.match(js, /const canvasSubtitle=\[/);
});

test("internal manifest, route, and element contracts are unchanged", () => {
  for (const field of [
    "procedural_attempts",
    "preview_asset_id",
    "recipe_asset_id",
    "mapped_result_asset_id",
    "raster_animation",
    "media_source",
    "model_location",
  ]) assert.ok(js.includes(field), `${field} must remain an internal manifest field`);
  for (const route of [
    "/api/ai/ollama/models",
    "/api/ai/ollama/select",
    "/api/ai/ollama/clear",
    "/api/library/import/media",
  ]) assert.ok(js.includes(route), `${route} must remain unchanged`);
  assert.match(html, /data-library-filter="sources"/);
  assert.match(html, /id="settings-ai-api"[^>]*value="api"/);
  assert.match(js, /data-source-preview="source"/);
  assert.match(review, /id="apply-procedural-effect"/);
});
