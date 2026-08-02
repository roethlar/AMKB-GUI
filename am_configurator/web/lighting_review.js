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
    const boardPreviewReady = Boolean(mappedResultLoaded && options.boardPreviewReady);
    const loadingMessage = attempt.mapped_result_asset_id && !mappedResultLoaded
      ? "The generated lighting is still loading. Nothing has changed yet."
      : !attempt.mapped_result_asset_id
        ? "The generated lighting is unavailable, so nothing was changed. Generate it again."
        : "";
    // Apply is document-only. The hint names the destination slot, that scope,
    // and the single action that reaches the keyboard, so the review stage
    // answers "where did my work go?" the same way every other Apply does.
    const writeAction = typeof options.writeActionLabel === "string" && options.writeActionLabel
      ? options.writeActionLabel
      : "Write to keyboard";
    return Object.freeze({
      summary,
      detail: `${frameCount} lighting frames · ${options.targetLabel || "Lighting"} · Custom ${customSlot}`,
      boardMessage: boardPreviewReady
        ? "The exact result is on the physical Board. Play or scrub there to inspect every LED frame before applying."
        : "Preparing the physical Board… Nothing has changed yet.",
      applyHint: `Apply puts this in Custom slot ${customSlot} · ${options.targetLabel || "Lighting"} and changes the open document only. Nothing has been written to the keyboard yet — use the ${writeAction} button when you are ready.`,
      blockedMessage,
      loadingMessage,
      errorMessage: typeof options.errorMessage === "string" ? options.errorMessage : "",
      applyDisabled: Boolean(blockedMessage || !boardPreviewReady),
    });
  }

  function renderReview(container, view, onApply) {
    if (!container || typeof container.querySelector !== "function") {
      throw new TypeError("A review container is required.");
    }
    const review = view || createReviewView();
    container.innerHTML = `<div class="review-stage">
      <div class="review-copy"><p class="eyebrow">Saved to Library</p><h3>${escapeHtml(review.summary)}</h3><p>${escapeHtml(review.detail)}</p>
      <p class="control-help" role="status">${escapeHtml(review.boardMessage || "")}</p>
      ${review.blockedMessage ? `<p class="ai-error" role="alert">${escapeHtml(review.blockedMessage)}</p>` : ""}
      ${review.loadingMessage ? `<p class="ai-error" role="status">${escapeHtml(review.loadingMessage)}</p>` : ""}
      ${review.errorMessage ? `<p class="ai-error" role="alert">${escapeHtml(review.errorMessage)}</p>` : ""}
      <div class="button-row"><button id="apply-procedural-effect" type="button" class="button primary" ${review.applyDisabled ? "disabled" : ""}>Apply to lighting slot</button></div>
      <small class="control-help">${escapeHtml(review.applyHint || "")}</small></div>
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
    createReviewView,
    renderReview,
    reviewBlockedMessage,
  });
});
