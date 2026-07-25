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
  const ASSIGNMENT_CODE = /^#[0-9a-f]{8}$/i;
  const RGB_COLOR = /^#[0-9a-f]{6}$/i;

  function escapeMarkup(value) {
    return String(value ?? "").replace(
      /[&<>'"]/g,
      character => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[character],
    );
  }

  function canonicalAssignmentCode(value, label) {
    if (typeof value !== "string" || !ASSIGNMENT_CODE.test(value)) {
      throw new Error(`${label} must use # followed by exactly eight hexadecimal digits.`);
    }
    return value.toUpperCase();
  }

  function normalizeImportedAssignmentCodes(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error("The imported configuration must be an object.");
    }
    const layerData = config.key_layer?.layer_data;
    if (Array.isArray(layerData)) {
      layerData.forEach((entry, layerIndex) => {
        if (!Array.isArray(entry?.layer)) return;
        entry.layer = entry.layer.map((code, codeIndex) => canonicalAssignmentCode(
          code,
          `Layer ${layerIndex + 1} assignment ${codeIndex + 1}`,
        ));
      });
    }
    if (config.macro_key !== undefined) {
      if (!Array.isArray(config.macro_key)) {
        throw new Error("macro_key must be an array.");
      }
      config.macro_key.forEach((macro, index) => {
        if (!macro || typeof macro !== "object" || Array.isArray(macro)) {
          throw new Error(`Macro ${index + 1} must be an object.`);
        }
        macro.original_key = canonicalAssignmentCode(
          macro.original_key,
          `Macro ${index + 1} assignment code`,
        );
      });
    }
    return config;
  }

  function canonicalRgbColor(value) {
    if (typeof value !== "string" || !RGB_COLOR.test(value)) {
      throw new Error("Imported lighting contains an invalid RGB color.");
    }
    return value.toUpperCase();
  }

  function safeRgbColor(value) {
    return typeof value === "string" && RGB_COLOR.test(value)
      ? value.toUpperCase()
      : "#000000";
  }

  function normalizeImportedLightingColors(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error("The imported configuration must be an object.");
    }
    if (config.page_data === undefined) return config;
    if (!Array.isArray(config.page_data)) {
      throw new Error("Imported lighting page data must be an array.");
    }
    for (const page of config.page_data) {
      if (!page || typeof page !== "object" || Array.isArray(page)) continue;
      if (page.color && typeof page.color === "object" && !Array.isArray(page.color)) {
        for (const field of ["back_rgb", "rgb"]) {
          if (page.color[field] !== undefined) {
            page.color[field] = canonicalRgbColor(page.color[field]);
          }
        }
      }
      for (const trackName of ["frames", "keyframes", "spotlight_frames"]) {
        const frames = page[trackName]?.frame_data;
        if (!Array.isArray(frames)) continue;
        for (const frame of frames) {
          if (!Array.isArray(frame?.frame_RGB)) continue;
          frame.frame_RGB = frame.frame_RGB.map(canonicalRgbColor);
        }
      }
    }
    return config;
  }

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

  function createEpochLoadRegistry() {
    const owners = new Map();
    return Object.freeze({
      begin(key, epoch) {
        if (typeof key !== "string" || !key || !Number.isSafeInteger(epoch) || epoch < 0) {
          throw new TypeError("Epoch load identity is invalid");
        }
        if (owners.get(key) === epoch) return null;
        owners.set(key, epoch);
        let released = false;
        return Object.freeze({
          current(currentEpoch) {
            return !released && currentEpoch === epoch && owners.get(key) === epoch;
          },
          release() {
            if (released) return;
            released = true;
            if (owners.get(key) === epoch) owners.delete(key);
          },
        });
      },
    });
  }

  function normalizeLocalModels(value) {
    const models = [];
    const seen = new Set();
    if (Array.isArray(value?.models)) {
      for (const candidate of value.models) {
        const modelId = candidate?.model_id;
        const digest = candidate?.digest;
        if (typeof modelId !== "string" || !modelId || typeof digest !== "string" || !digest || seen.has(modelId)) continue;
        seen.add(modelId);
        models.push({
          model_id: modelId,
          digest,
          size_bytes: Number(candidate.size_bytes) || 0,
          parameter_size: typeof candidate.parameter_size === "string" ? candidate.parameter_size : null,
          quantization: typeof candidate.quantization === "string" ? candidate.quantization : null,
        });
      }
    }
    return {
      available: value?.available === true,
      models,
      reason: value?.reason === "upgrade_required" ? "upgrade_required" : null,
      loading: false,
    };
  }

  function localModelRefreshFailed(current) {
    const normalized = normalizeLocalModels(current);
    return {...normalized, available: false, reason: "refresh_failed", loading: false};
  }

  function shouldDiscoverLocalModels(route, status) {
    return route === ROUTES.SETTINGS
      || (status?.enabled === true && status?.backend === "local");
  }

  function projectLocalModelPicker(inventory, local = {}, previousValue = "") {
    const models = Array.isArray(inventory?.models) ? inventory.models : [];
    const loading = inventory?.loading === true;
    const available = inventory?.available === true;
    const reason = ["upgrade_required", "refresh_failed"].includes(inventory?.reason) ? inventory.reason : null;
    const selectedId = typeof local?.model_id === "string" && local.model_id ? local.model_id : null;
    const installedIds = new Set(models.map(model => model.model_id));
    let inventoryState = "available";
    if (loading) inventoryState = "loading";
    else if (reason === "upgrade_required") inventoryState = "upgrade_required";
    else if (reason === "refresh_failed") inventoryState = "transient_failure";
    else if (!available) inventoryState = "unavailable";
    else if (!models.length) inventoryState = "empty";

    let selectionState = "none";
    if (selectedId) {
      if (["loading", "unavailable", "transient_failure"].includes(inventoryState)) selectionState = "transient_failure";
      else if (!installedIds.has(selectedId)) selectionState = "removed";
      else if (local.model_verified !== true) selectionState = "digest_changed";
      else selectionState = "selected";
    }

    const options = models.map(model => {
      const details = [model.parameter_size, model.quantization].filter(Boolean).join(" · ");
      return {
        value: model.model_id,
        label: details ? `${model.model_id} — ${details}` : model.model_id,
        disabled: false,
      };
    });
    if (selectedId && !installedIds.has(selectedId)) {
      options.push({
        value: selectedId,
        label: `${selectedId} — not currently available`,
        disabled: true,
      });
    }
    const optionValues = new Set(options.map(option => option.value));
    const previous = typeof previousValue === "string" ? previousValue : "";
    const value = optionValues.has(previous) ? previous : optionValues.has(selectedId) ? selectedId : "";
    const placeholder = loading
      ? "Checking installed models…"
      : inventoryState === "upgrade_required"
        ? "Upgrade Ollama to discover models"
        : available
          ? models.length ? "Choose an installed model" : "No eligible local models found"
          : "Ollama is not available";
    return {
      available,
      disabled: loading || inventoryState === "upgrade_required" || !available || models.length === 0,
      inventoryState,
      options,
      placeholder,
      selectedId,
      selectionState,
      value,
    };
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
    createEpochLoadRegistry,
    createPaintStrokeController,
    createLightingState,
    escapeMarkup,
    formatLightingHash,
    localModelRefreshFailed,
    nextGridIndex,
    normalizeLocalModels,
    normalizeImportedAssignmentCodes,
    normalizeImportedLightingColors,
    parseLightingHash,
    projectLocalModelPicker,
    projectLightingJob,
    reduceLightingState,
    routeAvailability,
    safeRgbColor,
    shouldDiscoverLocalModels,
  });
});
