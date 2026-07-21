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
    CONCEPTS: "concepts",
    ANIMATE: "animate",
    REVIEW: "review",
  });
  const VALID_ROUTES = new Set(Object.values(ROUTES));
  const DOCUMENT_ROUTES = new Set([ROUTES.KEYMAP, ROUTES.MACROS, ROUTES.CREATE, ROUTES.EDIT]);
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  function normalizedRoute(value) {
    return VALID_ROUTES.has(value) ? value : ROUTES.EDIT;
  }

  function normalizedStage(value) {
    return Object.values(STAGES).includes(value) ? value : STAGES.CONCEPTS;
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

  function copyProgress(value) {
    if (!value || typeof value !== "object") return null;
    const completed = Number(value.completed);
    const total = Number(value.total);
    if (!Number.isFinite(completed) || !Number.isFinite(total) || total < 0) return null;
    return {completed, total};
  }

  function copyTarget(value) {
    if (!value || typeof value !== "object") return null;
    const targets = Array.isArray(value.targets) ? value.targets.map(String) : [];
    return {
      family: String(value.family || value.productFamily || value.product_family || ""),
      productId: String(value.productId || value.product_id || ""),
      targets,
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
      selectedCandidateId: value.selectedCandidateId == null ? null : String(value.selectedCandidateId),
      resultAssetId: value.resultAssetId == null ? null : String(value.resultAssetId),
      target: copyTarget(value.target),
    };
  }

  function createLightingState(saved = {}) {
    const activeJob = copyJob(saved.activeJob);
    return {
      route: normalizedRoute(saved.route),
      create: {
        stage: normalizedStage(saved.create?.stage),
        selectedCandidateId: saved.create?.selectedCandidateId == null
          ? (activeJob?.selectedCandidateId || null)
          : String(saved.create.selectedCandidateId),
      },
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

  function jobStage(job) {
    if (job?.resultAssetId) return STAGES.REVIEW;
    const phase = String(job?.phase || "").toLowerCase();
    if (job?.selectedCandidateId || phase.includes("video") || phase.includes("animat") || phase.includes("process")) {
      return STAGES.ANIMATE;
    }
    return STAGES.CONCEPTS;
  }

  function routeAvailability(route, document) {
    const candidate = normalizedRoute(route);
    if (DOCUMENT_ROUTES.has(candidate) && !document) {
      return {available: false, reason: "document-required"};
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
    const attempts = Array.isArray(manifest?.animation_attempts) ? manifest.animation_attempts : [];
    const latestAttempt = attempts.length ? attempts[attempts.length - 1] : null;
    return {
      id: manifest?.job_id,
      status: manifest?.status,
      phase: manifest?.phase,
      progress: manifest?.progress,
      selectedCandidateId: manifest?.selected_candidate_id,
      resultAssetId: latestAttempt?.mapped_result_asset_id || null,
      target: manifest?.target,
    };
  }

  function reduceLightingState(input, event = {}, context = {}) {
    const state = input || createLightingState();
    switch (event.type) {
      case "NAVIGATE": {
        const route = normalizedRoute(event.route);
        if (route === state.route) return result(state);
        return result({...state, route});
      }
      case "JOB_SYNCED": {
        const activeJob = copyJob(event.job);
        const sameJob = Boolean(activeJob && activeJob.id === state.activeJob?.id);
        const selectedCandidateId = activeJob
          ? (activeJob.selectedCandidateId || (sameJob ? state.create.selectedCandidateId : null))
          : null;
        const becameReady = sameJob && !state.activeJob?.resultAssetId && activeJob?.resultAssetId;
        const beganAnimation = sameJob && !state.activeJob?.selectedCandidateId && activeJob?.selectedCandidateId;
        const phase = String(activeJob?.phase || "").toLowerCase();
        const restartedAnimation = sameJob
          && state.activeJob?.resultAssetId
          && !activeJob?.resultAssetId
          && (phase.includes("video") || phase.includes("animat") || phase.includes("process"));
        return result({
          ...state,
          create: {
            stage: !activeJob
              ? STAGES.CONCEPTS
              : (!sameJob || becameReady || beganAnimation || restartedAnimation
                ? jobStage(activeJob)
                : state.create.stage),
            selectedCandidateId,
          },
          activeJob,
        });
      }
      case "SELECT_CANDIDATE": {
        const selectedCandidateId = event.candidateId == null ? null : String(event.candidateId);
        if (selectedCandidateId === state.create.selectedCandidateId) return result(state);
        return result({...state, create: {...state.create, selectedCandidateId}});
      }
      case "SHOW_CONCEPTS":
        if (state.create.stage === STAGES.CONCEPTS) return result(state);
        return result({...state, create: {...state.create, stage: STAGES.CONCEPTS}});
      case "SHOW_ANIMATE":
        if (!state.create.selectedCandidateId) return result(state, "selection-required");
        if (state.create.stage === STAGES.ANIMATE) return result(state);
        return result({...state, create: {...state.create, stage: STAGES.ANIMATE}});
      case "SHOW_REVIEW":
        if (!state.activeJob?.resultAssetId) return result(state, "result-not-ready");
        if (state.create.stage === STAGES.REVIEW) return result(state);
        return result({...state, create: {...state.create, stage: STAGES.REVIEW}});
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
    createLightingState,
    formatLightingHash,
    nextGridIndex,
    parseLightingHash,
    projectLightingJob,
    reduceLightingState,
    routeAvailability,
  });
});
