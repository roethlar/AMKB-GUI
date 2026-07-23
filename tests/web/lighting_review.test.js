"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {STAGES, createLightingState, reduceLightingState} = require("../../am_configurator/web/lighting_state.js");
const {
  REVIEW_BLOCK_REASONS,
  createReviewView,
  renderReview,
  reviewBlockedMessage,
} = require("../../am_configurator/web/lighting_review.js");

const JOB_ID = "4d36e96e-e2aa-4e72-8808-4d03b5ba7e61";

class FakeButton {
  constructor(disabled) {
    this.disabled = disabled;
    this.listeners = [];
  }

  addEventListener(type, listener) {
    if (type === "click") this.listeners.push(listener);
  }

  click() {
    if (!this.disabled) this.listeners.forEach(listener => listener());
  }
}

class ReviewDom {
  set innerHTML(value) {
    this.html = String(value);
    const tag = this.html.match(/<button id="apply-procedural-effect"[^>]*>/)?.[0] || "";
    this.button = new FakeButton(/\sdisabled(?:\s|>)/.test(tag));
  }

  get innerHTML() {
    return this.html || "";
  }

  querySelector(selector) {
    return selector === "#apply-procedural-effect" ? this.button : null;
  }
}

function readyJob() {
  return {
    id: JOB_ID,
    status: "ready",
    phase: "ready_for_review",
    resultAssetId: "mapped-asset",
    previewAssetId: "preview-asset",
    recipeAssetId: "recipe-asset",
    target: {family: "80", productId: "AM21", targets: ["keyframes"], frameCap: 200},
  };
}

function readyAttempt() {
  return {
    preview_asset_id: "preview-asset",
    recipe_asset_id: "recipe-asset",
    mapped_result_asset_id: "mapped-asset",
  };
}

test("ready reducer state renders the authenticated preview and applies exactly once", () => {
  const lighting = reduceLightingState(createLightingState(), {type: "JOB_SYNCED", job: readyJob()}).state;
  assert.equal(lighting.create.stage, STAGES.REVIEW);

  const view = createReviewView({
    assetUrls: new Map([[`${JOB_ID}:preview-asset`, "blob:authenticated-preview"]]),
    jobId: JOB_ID,
    attempt: readyAttempt(),
    recipe: {name: "Violet aurora", density: "dense", layers: [{}, {}]},
    quality: {frame_count: 200},
    targetLabel: "Keys",
    destinationSlot: 5,
    blockedReason: null,
    mappedResultLoaded: true,
  });
  const dom = new ReviewDom();
  let applies = 0;
  renderReview(dom, view, () => { applies += 1; });

  assert.match(dom.innerHTML, /src="blob:authenticated-preview"/);
  assert.match(dom.innerHTML, /Violet aurora · dense · 2 layers/);
  assert.match(dom.innerHTML, /200 exact frames · Keys · Custom 1/);
  assert.equal(dom.button.disabled, false);
  dom.button.click();
  dom.button.disabled = false;
  dom.button.click();
  assert.equal(applies, 1);
});

test("loading assets and every reducer block reason render without applying", () => {
  assert.deepEqual(REVIEW_BLOCK_REASONS, [
    "document-required",
    "result-not-ready",
    "family-mismatch",
    "slot-unavailable",
    "target-mismatch",
    "target-unsupported",
  ]);
  for (const reason of REVIEW_BLOCK_REASONS) {
    const view = createReviewView({
      assetUrls: new Map(),
      jobId: JOB_ID,
      attempt: readyAttempt(),
      recipe: null,
      quality: {},
      targetLabel: "Keys",
      destinationSlot: 5,
      blockedReason: reason,
      mappedResultLoaded: false,
    });
    const dom = new ReviewDom();
    let applies = 0;
    renderReview(dom, view, () => { applies += 1; });

    assert.match(dom.innerHTML, /Loading animation/);
    assert.match(dom.innerHTML, /Loading saved recipe/);
    assert.ok(dom.innerHTML.includes(reviewBlockedMessage(reason)));
    assert.match(dom.innerHTML, /saved LED result is still loading/);
    assert.equal(dom.button.disabled, true);
    dom.button.click();
    assert.equal(applies, 0);
  }
});
