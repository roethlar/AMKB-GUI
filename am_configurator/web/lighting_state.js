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
  const DOCUMENT_ROUTES = new Set([ROUTES.KEYMAP, ROUTES.MACROS, ROUTES.EDIT]);
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const RGB_COLOR = /^#[0-9a-f]{6}$/i;

  function escapeMarkup(value) {
    return String(value ?? "").replace(
      /[&<>'"]/g,
      character => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[character],
    );
  }

  function safeRgbColor(value) {
    return typeof value === "string" && RGB_COLOR.test(value)
      ? value.toUpperCase()
      : "#000000";
  }

  function normalizedRoute(value) {
    return VALID_ROUTES.has(value) ? value : ROUTES.KEYMAP;
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

  function normalizeOllamaModels(value) {
    const models = [];
    const seen = new Set();
    if (Array.isArray(value?.models)) {
      for (const candidate of value.models) {
        const modelId = candidate?.model_id;
        const digest = candidate?.digest;
        const location = candidate?.location;
        if (
          typeof modelId !== "string"
          || !modelId
          || typeof digest !== "string"
          || !digest
          || !["ollama_server", "ollama_cloud"].includes(location)
          || seen.has(modelId)
        ) continue;
        seen.add(modelId);
        models.push({
          model_id: modelId,
          digest,
          size_bytes: Number(candidate.size_bytes) || 0,
          location,
          parameter_size: typeof candidate.parameter_size === "string" ? candidate.parameter_size : null,
          quantization: typeof candidate.quantization === "string" ? candidate.quantization : null,
          label: `${modelId} — ${location === "ollama_cloud" ? "Ollama Cloud" : "On this Ollama server"}`,
        });
      }
    }
    return {
      available: value?.available === true ? true : value?.available === false ? false : null,
      models,
      reason: value?.reason === "upgrade_required" ? "upgrade_required" : null,
      loading: false,
    };
  }

  function ollamaModelRefreshFailed(current) {
    const normalized = normalizeOllamaModels(current);
    return {...normalized, available: false, reason: "refresh_failed", loading: false};
  }

  function ollamaEndpointDataFlow(baseUrl, modelLocation = null) {
    let endpoint;
    try {
      endpoint = new URL(String(baseUrl || ""));
    } catch (error) {
      return {disclosureRequired: false, insecureRemote: false, loopback: false};
    }
    const host = endpoint.hostname.toLowerCase();
    const loopback = (
      host === "localhost"
      || host.endsWith(".localhost")
      || host === "[::1]"
      || host === "::1"
      || /^127(?:\.\d{1,3}){3}$/.test(host)
    );
    return {
      disclosureRequired: !loopback || modelLocation === "ollama_cloud",
      insecureRemote: !loopback && endpoint.protocol === "http:",
      loopback,
    };
  }

  function aiStudioAvailable(status) {
    return status?.enabled === true && status?.ready === true;
  }

  function projectApiProviderPicker(
    catalog,
    apiSettings = {},
    requestedProvider = null,
    requestedModel = null,
  ) {
    const providers = [];
    for (const [id, metadata] of Object.entries(catalog?.providers || {})) {
      if (typeof id !== "string" || !id || typeof metadata?.label !== "string" || !metadata.label) continue;
      const models = [];
      const seen = new Set();
      for (const candidate of Array.isArray(metadata.models) ? metadata.models : []) {
        if (
          typeof candidate?.id !== "string"
          || !candidate.id
          || typeof candidate?.label !== "string"
          || !candidate.label
          || seen.has(candidate.id)
        ) continue;
        seen.add(candidate.id);
        models.push({id: candidate.id, label: candidate.label});
      }
      if (!models.length || !seen.has(metadata.default_model)) continue;
      providers.push({
        id,
        label: metadata.label,
        defaultModel: metadata.default_model,
        disclosureVersion: typeof metadata.disclosure_version === "string"
          ? metadata.disclosure_version
          : null,
        models,
      });
    }
    const providerIds = new Set(providers.map(provider => provider.id));
    const preferredProvider = typeof requestedProvider === "string"
      ? requestedProvider
      : null;
    const storedProvider = typeof apiSettings?.selected_provider === "string"
      ? apiSettings.selected_provider
      : null;
    const providerId = providerIds.has(preferredProvider)
      ? preferredProvider
      : providerIds.has(storedProvider)
        ? storedProvider
        : providers[0]?.id || null;
    const selected = providers.find(provider => provider.id === providerId) || null;
    if (!selected) {
      return {
        providerId: null,
        providerLabel: "API provider",
        providers: [],
        modelId: null,
        models: [],
        disclosureVersion: null,
      };
    }
    const modelIds = new Set(selected.models.map(model => model.id));
    const storedModel = apiSettings?.providers?.[providerId]?.model_id;
    const modelId = modelIds.has(requestedModel)
      ? requestedModel
      : modelIds.has(storedModel)
        ? storedModel
        : selected.defaultModel;
    return {
      providerId,
      providerLabel: selected.label,
      providers: providers.map(provider => ({id: provider.id, label: provider.label})),
      modelId,
      models: selected.models.map(model => ({...model})),
      disclosureVersion: selected.disclosureVersion,
    };
  }

  function projectOllamaModelPicker(inventory, ollama = {}, previousValue = "") {
    const models = Array.isArray(inventory?.models) ? inventory.models : [];
    const loading = inventory?.loading === true;
    const available = inventory?.available === true;
    const reason = ["upgrade_required", "refresh_failed"].includes(inventory?.reason) ? inventory.reason : null;
    const selectedId = typeof ollama?.model_id === "string" && ollama.model_id ? ollama.model_id : null;
    const selectedModel = models.find(model => model.model_id === selectedId) || null;
    const installedIds = new Set(models.map(model => model.model_id));
    let inventoryState = "not_refreshed";
    if (loading) inventoryState = "loading";
    else if (reason === "upgrade_required") inventoryState = "upgrade_required";
    else if (reason === "refresh_failed") inventoryState = "transient_failure";
    else if (inventory?.available === false) inventoryState = "unavailable";
    else if (!available) inventoryState = "not_refreshed";
    else if (!models.length) inventoryState = "empty";
    else inventoryState = "available";

    let selectionState = "none";
    if (selectedId) {
      if (["loading", "unavailable", "transient_failure", "not_refreshed"].includes(inventoryState)) selectionState = "transient_failure";
      else if (!installedIds.has(selectedId)) selectionState = "removed";
      else if (
        selectedModel.digest !== ollama.model_digest
        || selectedModel.location !== ollama.model_location
      ) selectionState = "digest_changed";
      else selectionState = "selected";
    }

    const options = models.map(model => {
      return {
        value: model.model_id,
        label: model.label,
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
      ? "Checking models on this Ollama server…"
      : inventoryState === "upgrade_required"
        ? "Upgrade Ollama to discover models"
        : inventoryState === "not_refreshed"
          ? "Refresh to check models"
        : available
          ? models.length ? "Choose a model" : "No completion models reported"
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

  function routeAvailability(route, document, importedLighting = null) {
    const candidate = normalizedRoute(route);
    const importedReview = candidate === ROUTES.EDIT && importedLighting?.kind === "lighting";
    if (DOCUMENT_ROUTES.has(candidate) && !document && !importedReview) {
      return {available: false, reason: "document-required"};
    }
    return {available: true, reason: null};
  }

  function classifyImportedJsonSelection(reports, {merge = false} = {}) {
    if (!Array.isArray(reports) || !reports.length) {
      throw new Error("Choose at least one JSON file.");
    }
    const kinds = reports.map(report => report?.kind);
    if (kinds.some(kind => !["profile", "lighting"].includes(kind))) {
      throw new Error("One selected JSON file has an unrecognized import result.");
    }
    const lightingIndexes = kinds
      .map((kind, index) => kind === "lighting" ? index : -1)
      .filter(index => index >= 0);
    if (lightingIndexes.length) {
      if (reports.length !== 1 || lightingIndexes.length !== 1) {
        throw new Error(
          "Open one AM Master lighting-only JSON file at a time. It cannot be combined with a keyboard profile.",
        );
      }
      if (merge) {
        throw new Error(
          "AM Master lighting-only JSON cannot be merged. Use Open to review it without changing the current profile.",
        );
      }
      return Object.freeze({kind: "lighting", index: lightingIndexes[0]});
    }
    return Object.freeze({kind: "profiles", indexes: Object.freeze(reports.map((_, index) => index))});
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

  function importedLightingApplyAvailability(
    imported,
    document,
    destination,
    servedTargets,
  ) {
    const lighting = imported?.kind === "lighting" ? imported.lighting : null;
    const importedDestination = lighting?.destination;
    const tracks = lighting?.tracks;
    if (!importedDestination || !tracks || typeof tracks !== "object") {
      return {compatible: false, reason: "import-invalid"};
    }
    if (!document) return {compatible: false, reason: "document-required"};
    const importedFamily = canonicalFamily(
      importedDestination.family || importedDestination.product_id,
    );
    const documentFamily = canonicalFamily(document.family || document.productId);
    if (!importedFamily || importedFamily !== documentFamily) {
      return {compatible: false, reason: "family-mismatch"};
    }
    const slot = Number(destination?.slot);
    if (!Array.isArray(document.slots) || !document.slots.map(Number).includes(slot)) {
      return {compatible: false, reason: "slot-unavailable"};
    }
    const target = String(destination?.target || "");
    const importedTargets = Array.isArray(importedDestination.targets)
      ? importedDestination.targets.map(String)
      : [];
    const supportedTargets = new Set(
      Array.isArray(document.supportedTargets) ? document.supportedTargets.map(String) : [],
    );
    if (!importedTargets.includes(target) || !supportedTargets.has(target)) {
      return {compatible: false, reason: "target-unsupported"};
    }
    for (const [track, metadata] of Object.entries(tracks)) {
      if (
        !importedTargets.includes(track)
        || !supportedTargets.has(track)
        || typeof metadata?.signature !== "string"
        || servedTargets?.[track]?.signature !== metadata.signature
      ) return {compatible: false, reason: "layout-mismatch"};
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

  function createLaunchState(saved = {}, hash = "") {
    const parsed = parseLightingHash(hash);
    const lighting = createLightingState({...saved, route: ROUTES.KEYMAP});
    const jobId = parsed.jobId || lighting.activeJob?.id || null;
    return {
      lighting,
      jobId,
      hash: formatLightingHash(ROUTES.KEYMAP, jobId),
    };
  }

  return Object.freeze({
    ROUTES,
    STAGES,
    aiStudioAvailable,
    applyCompatibility,
    classifyImportedJsonSelection,
    createEpochLoadRegistry,
    createLaunchState,
    createPaintStrokeController,
    createLightingState,
    escapeMarkup,
    formatLightingHash,
    importedLightingApplyAvailability,
    ollamaEndpointDataFlow,
    ollamaModelRefreshFailed,
    nextGridIndex,
    normalizeOllamaModels,
    parseLightingHash,
    projectApiProviderPicker,
    projectOllamaModelPicker,
    projectLightingJob,
    reduceLightingState,
    routeAvailability,
    safeRgbColor,
  });
});
