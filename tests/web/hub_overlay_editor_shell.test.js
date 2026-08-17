"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");

test("hub import overlays every open target without a hardware route", () => {
  const flow = js.slice(
    js.indexOf("async function importHubFile"),
    js.indexOf("function freezeImportedValue"),
  );

  assert.match(flow, /\/api\/hub\/open/);
  assert.match(flow, /\/api\/hub\/overlay/);
  assert.match(flow, /state\.hubEditor/);
  assert.match(flow, /\/api\/hub\/export/);
  assert.match(flow, /\/api\/hub\/apply/);
  assert.match(flow, /profile:overlay\.profile/);
  assert.doesNotMatch(flow, /\/preflight|\/write|writeDevice/);
});

test("overlay import and each resolution use one matching history checkpoint", () => {
  assert.match(js, /type:"APPLY_OVERLAY"/);
  assert.match(js, /type:"RESOLVE_WORKLIST"/);
  assert.match(js, /amHubReviewUndo/);
  assert.match(js, /amHubReviewRedo/);
  assert.match(js, /pushUndo\(\)[\s\S]*state\.amHubReview=/);
});

test("Keymap presents counts, plain worklist actions, and disclosed technical data", () => {
  const review = js.slice(
    js.indexOf("function renderHubReview"),
    js.indexOf("function renderHubKeymap"),
  );

  assert.match(review, /carried/);
  assert.match(review, /adapted/);
  assert.match(review, /unresolved/);
  assert.match(review, /Use suggestion/);
  assert.match(review, /Choose a key/);
  assert.match(review, /Leave out/);
  assert.match(review, /<details/);
  assert.match(review, /item\.source\.layer/);
  assert.match(review, /item\.source\.key/);
  assert.match(review, /hubCodeLabel\(item\.source\.code\)/);
  assert.doesNotMatch(review, /JSON\.stringify|innerHTML\s*\+=/);
});

test("the review rail stacks at the existing editor breakpoint", () => {
  assert.match(css, /\.hub-review-worklist\s*\{[^}]*overflow-y:\s*auto/);
  assert.match(css, /@media \(max-width: 1240px\)[\s\S]*\.editor-grid \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(css, /\.hub-review-actions/);
});
