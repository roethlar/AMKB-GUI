(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingReview = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const REVIEW_BLOCK_REASONS = Object.freeze([
    "document-required",
    "result-not-ready",
    "family-mismatch",
    "slot-unavailable",
    "target-mismatch",
    "target-unsupported",
  ]);
  const BLOCKED_MESSAGES = Object.freeze({
    "document-required": "Open a compatible lighting document before applying this result.",
    "result-not-ready": "The saved LED result is not ready to apply yet.",
    "family-mismatch": "This result was generated for a different keyboard family.",
    "slot-unavailable": "The original custom lighting slot is not available in this document.",
    "target-mismatch": "The selected lighting target no longer matches this result.",
    "target-unsupported": "This document does not support every lighting target in this result.",
  });

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character]);
  }

  function assetUrl(assetUrls, jobId, assetId) {
    if (!jobId || !assetId || typeof assetUrls?.get !== "function") return null;
    const value = assetUrls.get(`${jobId}:${assetId}`);
    return typeof value === "string" && value ? value : null;
  }

  function reviewBlockedMessage(reason) {
    return BLOCKED_MESSAGES[reason]
      || "This saved result cannot be applied to the current document.";
  }

  function createReviewView(options = {}) {
    const attempt = options.attempt && typeof options.attempt === "object"
      ? options.attempt
      : {};
    const recipe = options.recipe && typeof options.recipe === "object"
      ? options.recipe
      : null;
    const quality = options.quality && typeof options.quality === "object"
      ? options.quality
      : {};
    const layers = Array.isArray(recipe?.layers) ? recipe.layers : [];
    const summary = recipe
      ? `${recipe.name || "Procedural effect"} · ${recipe.density || "balanced"} · ${layers.length} layer${layers.length === 1 ? "" : "s"}`
      : "Loading saved recipe…";
    const frameValue = Number(quality.frame_count ?? options.frameCap ?? 0);
    const frameCount = Number.isFinite(frameValue) && frameValue >= 0 ? frameValue : 0;
    const slot = Number(options.destinationSlot);
    const customSlot = Number.isFinite(slot) ? slot - 4 : "?";
    const blockedMessage = options.blockedReason
      ? reviewBlockedMessage(options.blockedReason)
      : "";
    const mappedResultLoaded = Boolean(
      attempt.mapped_result_asset_id && options.mappedResultLoaded
    );
    const loadingMessage = attempt.mapped_result_asset_id && !mappedResultLoaded
      ? "The saved LED result is still loading."
      : !attempt.mapped_result_asset_id
        ? "The saved LED result is unavailable."
        : "";
    return Object.freeze({
      previewUrl: assetUrl(options.assetUrls, options.jobId, attempt.preview_asset_id),
      summary,
      detail: `${frameCount} exact frames · ${options.targetLabel || "Lighting"} · Custom ${customSlot}`,
      blockedMessage,
      loadingMessage,
      errorMessage: typeof options.errorMessage === "string" ? options.errorMessage : "",
      applyDisabled: Boolean(blockedMessage || !mappedResultLoaded),
    });
  }

  function renderReview(container, view, onApply) {
    if (!container || typeof container.querySelector !== "function") {
      throw new TypeError("A review container is required.");
    }
    const review = view || createReviewView();
    container.innerHTML = `<div class="review-stage">
      <div class="review-media">${review.previewUrl
        ? `<img src="${escapeHtml(review.previewUrl)}" alt="Animated exact-raster lighting preview">`
        : '<div class="library-card-placeholder">Loading animation…</div>'}</div>
      <div class="review-copy"><p class="eyebrow">Saved locally</p><h3>${escapeHtml(review.summary)}</h3><p>${escapeHtml(review.detail)}</p>
      ${review.blockedMessage ? `<p class="ai-error" role="alert">${escapeHtml(review.blockedMessage)}</p>` : ""}
      ${review.loadingMessage ? `<p class="ai-error" role="status">${escapeHtml(review.loadingMessage)}</p>` : ""}
      ${review.errorMessage ? `<p class="ai-error" role="alert">${escapeHtml(review.errorMessage)}</p>` : ""}
      <div class="button-row"><button id="apply-procedural-effect" type="button" class="button primary" ${review.applyDisabled ? "disabled" : ""}>Apply</button></div>
      <small class="control-help">Apply is one undoable document-only change. Nothing is written to the keyboard.</small></div>
    </div>`;
    const button = container.querySelector("#apply-procedural-effect");
    if (!button) return;
    button.disabled = review.applyDisabled;
    let applied = false;
    button.addEventListener("click", () => {
      if (applied || button.disabled || typeof onApply !== "function") return;
      applied = true;
      button.disabled = true;
      onApply();
    });
  }

  return Object.freeze({
    REVIEW_BLOCK_REASONS,
    assetUrl,
    createReviewView,
    renderReview,
    reviewBlockedMessage,
  });
});
