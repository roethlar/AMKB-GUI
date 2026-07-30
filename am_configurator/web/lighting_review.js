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
  // Plain-language blocks. Each says what failed, that nothing changed, and the
  // next action the user can take.
  const BLOCKED_MESSAGES = Object.freeze({
    "document-required": "Nothing was changed. Open a matching keyboard profile, then apply this lighting.",
    "result-not-ready": "This lighting is not ready to apply yet. Nothing was changed; try again in a moment.",
    "family-mismatch": "This lighting was made for a different keyboard. Nothing was changed; open the matching profile to use it.",
    "slot-unavailable": "The custom lighting slot it was made for is missing from this profile. Nothing was changed; open the matching profile.",
    "target-mismatch": "The selected lighting area no longer matches this lighting. Nothing was changed; switch back to the original area.",
    "target-unsupported": "This profile does not support every lighting area in this result. Nothing was changed; open the matching profile.",
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
      || "This saved lighting cannot be applied to the open profile. Nothing was changed.";
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
      ? `${recipe.name || "Lighting effect"} · ${recipe.density || "balanced"} · ${layers.length} layer${layers.length === 1 ? "" : "s"}`
      : "Loading the lighting effect…";
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
      ? "The generated lighting is still loading. Nothing has changed yet."
      : !attempt.mapped_result_asset_id
        ? "The generated lighting is unavailable, so nothing was changed. Generate it again."
        : "";
    return Object.freeze({
      previewUrl: assetUrl(options.assetUrls, options.jobId, attempt.preview_asset_id),
      summary,
      detail: `${frameCount} lighting frames · ${options.targetLabel || "Lighting"} · Custom ${customSlot}`,
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
        ? `<img src="${escapeHtml(review.previewUrl)}" alt="Animated lighting preview">`
        : '<div class="library-card-placeholder">Loading animation…</div>'}</div>
      <div class="review-copy"><p class="eyebrow">Saved to Library</p><h3>${escapeHtml(review.summary)}</h3><p>${escapeHtml(review.detail)}</p>
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
