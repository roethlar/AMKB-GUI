(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingState = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const ROUTES = Object.freeze({
    KEYMAP: "keymap",
    MACROS: "macros",
    CREATE: "lighting/create",
    LIBRARY: "lighting/library",
    EDIT: "lighting/edit",
    SETTINGS: "settings",
  });
  const STAGES = Object.freeze({
    PROMPT: "prompt",
    PROGRESS: "progress",
    REVIEW: "review",
  });
  const VALID_ROUTES = new Set(Object.values(ROUTES));
  const DOCUMENT_ROUTES = new Set([ROUTES.KEYMAP, ROUTES.MACROS, ROUTES.CREATE, ROUTES.EDIT]);
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  function normalizedRoute(value) {
    return VALID_ROUTES.has(value) ? value : ROUTES.EDIT;
  }

  function normalizedStage(value) {
    return Object.values(STAGES).includes(value) ? value : STAGES.PROMPT;
  }

  function nextGridIndex(index, key, count, columns) {
    const total = Math.max(0, Math.trunc(Number(count) || 0));
    if (!total) return -1;
    const current = Math.min(total - 1, Math.max(0, Math.trunc(Number(index) || 0)));
    const width = Math.max(1, Math.trunc(Number(columns) || 1));
    if (key === "Home") return 0;
    if (key === "End") return total - 1;
    if (key === "ArrowLeft") return Math.max(0, current - 1);
    if (key === "ArrowRight") return Math.min(total - 1, current + 1);
    if (key === "ArrowUp") return Math.max(0, current - width);
    if (key === "ArrowDown") return Math.min(total - 1, current + width);
    return current;
  }

  function createPaintStrokeController({releaseTarget, checkpoint, paint}) {
    if (!releaseTarget || typeof releaseTarget.addEventListener !== "function" || typeof releaseTarget.removeEventListener !== "function") {
      throw new TypeError("A paint stroke release target is required.");
    }
    if (typeof checkpoint !== "function" || typeof paint !== "function") {
      throw new TypeError("Paint stroke callbacks are required.");
    }

    let painting = false;
    const finish = () => {
      painting = false;
      releaseTarget.removeEventListener("pointerup", finish);
      releaseTarget.removeEventListener("pointercancel", finish);
    };
    return Object.freeze({
      pointerDown(pixel) {
        if (!painting) {
          checkpoint();
          painting = true;
          releaseTarget.addEventListener("pointerup", finish);
          releaseTarget.addEventListener("pointercancel", finish);
        }
        paint(pixel);
        return true;
      },
      pointerEnter(pixel, buttons) {
        if (!painting || !buttons) return false;
        paint(pixel);
        return true;
      },
      teardown: finish,
    });
  }

  function copyProgress(value) {
    if (!value || typeof value !== "object") return null;
    const completed = Number(value.completed);
    const total = Number(value.total);
    if (!Number.isFinite(completed) || !Number.isFinite(total) || total < 0) return null;
    return {completed, total};
  }

  function copyTarget(value) {
    if (!value || typeof value !== "object") return null;
    return {
      family: String(value.family || value.productFamily || value.product_family || ""),
      productId: String(value.productId || value.product_id || ""),
      targets: Array.isArray(value.targets) ? value.targets.map(String) : [],
      frameCap: Number(value.frameCap ?? value.frame_cap ?? 0) || 0,
    };
  }

  function copyJob(value) {
    if (!value || typeof value !== "object" || !UUID.test(String(value.id || ""))) return null;
    return {
      id: String(value.id),
      status: String(value.status || ""),
      phase: String(value.phase || ""),
      progress: copyProgress(value.progress),
      resultAssetId: value.resultAssetId == null ? null : String(value.resultAssetId),
      previewAssetId: value.previewAssetId == null ? null : String(value.previewAssetId),
      recipeAssetId: value.recipeAssetId == null ? null : String(value.recipeAssetId),
      target: copyTarget(value.target),
    };
  }

  function jobStage(job) {
    if (job?.resultAssetId) return STAGES.REVIEW;
    if (job && ["in_progress", "accepted", "processing"].includes(job.status)) return STAGES.PROGRESS;
    return STAGES.PROMPT;
  }

  function createLightingState(saved = {}) {
    const activeJob = copyJob(saved.activeJob);
    return {
      route: normalizedRoute(saved.route),
      create: {stage: activeJob ? jobStage(activeJob) : normalizedStage(saved.create?.stage)},
      activeJob,
    };
  }

  function canonicalFamily(value) {
    const id = String(value || "").trim().toUpperCase();
    if (id === "80" || id === "AM21") return "80";
    if (id === "ALICE" || id === "AFA" || id === "AFA2" || id === "AFA 2") return "ALICE";
    if (id === "CB" || id.startsWith("CB")) return "CB";
    return id;
  }

  function routeAvailability(route, document, options = {}) {
    const candidate = normalizedRoute(route);
    if (DOCUMENT_ROUTES.has(candidate) && !document) {
      return {available: false, reason: "document-required"};
    }
    if (candidate === ROUTES.CREATE && options.aiReady !== true && !options.hasActiveJob) {
      return {available: false, reason: "ai-not-ready"};
    }
    return {available: true, reason: null};
  }

  function applyCompatibility(job, document, destination) {
    if (!document) return {compatible: false, reason: "document-required"};
    if (!job?.resultAssetId) return {compatible: false, reason: "result-not-ready"};
    const jobTarget = job.target || {};
    const jobFamily = canonicalFamily(jobTarget.family || jobTarget.productId);
    const documentFamily = canonicalFamily(document.family || document.productId);
    if (!jobFamily || jobFamily !== documentFamily) return {compatible: false, reason: "family-mismatch"};
    const slot = Number(destination?.slot);
    if (!Array.isArray(document.slots) || !document.slots.map(Number).includes(slot)) {
      return {compatible: false, reason: "slot-unavailable"};
    }
    const targets = Array.isArray(jobTarget.targets) ? jobTarget.targets.map(String) : [];
    const destinationTarget = String(destination?.target || "");
    if (!targets.length || targets[0] !== destinationTarget) {
      return {compatible: false, reason: "target-mismatch"};
    }
    const supported = new Set(Array.isArray(document.supportedTargets) ? document.supportedTargets.map(String) : []);
    if (targets.some(target => !supported.has(target))) {
      return {compatible: false, reason: "target-unsupported"};
    }
    return {compatible: true, reason: null};
  }

  function result(state, blocked = null, intent = null) {
    return {state, blocked, intent};
  }

  function projectLightingJob(manifest) {
    const attempts = Array.isArray(manifest?.procedural_attempts) ? manifest.procedural_attempts : [];
    const latestAttempt = attempts.length ? attempts[attempts.length - 1] : null;
    return {
      id: manifest?.job_id,
      status: manifest?.status,
      phase: manifest?.phase,
      progress: manifest?.progress,
      resultAssetId: latestAttempt?.mapped_result_asset_id || null,
      previewAssetId: latestAttempt?.preview_asset_id || null,
      recipeAssetId: latestAttempt?.recipe_asset_id || null,
      target: manifest?.target,
    };
  }

  function reduceLightingState(input, event = {}, context = {}) {
    const state = input || createLightingState();
    switch (event.type) {
      case "NAVIGATE": {
        const route = normalizedRoute(event.route);
        return route === state.route ? result(state) : result({...state, route});
      }
      case "JOB_SYNCED": {
        const activeJob = copyJob(event.job);
        return result({...state, create: {stage: activeJob ? jobStage(activeJob) : STAGES.PROMPT}, activeJob});
      }
      case "SHOW_PROMPT":
        return state.create.stage === STAGES.PROMPT
          ? result(state)
          : result({...state, create: {stage: STAGES.PROMPT}});
      case "SHOW_REVIEW":
        if (!state.activeJob?.resultAssetId) return result(state, "result-not-ready");
        return state.create.stage === STAGES.REVIEW
          ? result(state)
          : result({...state, create: {stage: STAGES.REVIEW}});
      case "APPLY_REQUESTED": {
        const compatibility = applyCompatibility(state.activeJob, context.document, context.destination);
        if (!compatibility.compatible) return result(state, compatibility.reason);
        return result(state, null, {
          type: "apply-lighting-result",
          jobId: state.activeJob.id,
          assetId: state.activeJob.resultAssetId,
          destination: {
            slot: Number(context.destination.slot),
            target: String(context.destination.target),
          },
        });
      }
      default:
        return result(state);
    }
  }

  function formatLightingHash(route, jobId = null) {
    const base = `#/${normalizedRoute(route)}`;
    return UUID.test(String(jobId || "")) ? `${base}?job=${encodeURIComponent(jobId)}` : base;
  }

  function parseLightingHash(value) {
    const raw = String(value || "");
    const match = /^#?\/([^?]*)(?:\?(.*))?$/.exec(raw);
    const route = normalizedRoute(match?.[1] || "");
    const params = new URLSearchParams(match?.[2] || "");
    const candidate = params.get("job") || "";
    return {route, jobId: UUID.test(candidate) ? candidate : null};
  }

  return Object.freeze({
    ROUTES,
    STAGES,
    applyCompatibility,
    createPaintStrokeController,
    createLightingState,
    formatLightingHash,
    nextGridIndex,
    parseLightingHash,
    projectLightingJob,
    reduceLightingState,
    routeAvailability,
  });
});
