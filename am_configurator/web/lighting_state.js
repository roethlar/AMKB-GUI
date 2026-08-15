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

  // Ready-made lighting patterns (the studio Patterns tool).
  //
  // Every control here is a short list of allowed steps, and every list was
  // checked against the engine's own acceptance rules on each supported board
  // size and frame budget. That is the contract: anything the interface can
  // reach renders and is accepted without weakening a single check. The engine
  // fills the rest of the layer from fixed values the interface never shows.
  const PATTERN_SCHEMA_VERSION = 1;
  const PATTERN_STEPS = 5;
  const PATTERN_BACKGROUND_LEVEL = 40;
  const PATTERN_SPEEDS = Object.freeze([
    Object.freeze({value: 1, label: "Slow"}),
    Object.freeze({value: 2, label: "Medium"}),
    Object.freeze({value: 3, label: "Fast"}),
  ]);
  // Six-digit colors whose brightest channel is 255, so the brightest point of
  // any pattern always clears the engine's brightness requirement.
  const PATTERN_COLORS = Object.freeze([
    Object.freeze({value: "#FF3B30", label: "Red"}),
    Object.freeze({value: "#FF9500", label: "Orange"}),
    Object.freeze({value: "#FFD60A", label: "Yellow"}),
    Object.freeze({value: "#00FF66", label: "Green"}),
    Object.freeze({value: "#00E5FF", label: "Aqua"}),
    Object.freeze({value: "#2E6BFF", label: "Blue"}),
    Object.freeze({value: "#8358FF", label: "Violet"}),
    Object.freeze({value: "#FF2D95", label: "Pink"}),
    Object.freeze({value: "#FFFFFF", label: "White"}),
  ]);
  // Degrees grow clockwise from "right" because the lights are addressed with
  // the top row first, so 90 degrees travels down the keyboard.
  const PATTERN_DIRECTIONS = Object.freeze([
    Object.freeze({value: 0, label: "Right"}),
    Object.freeze({value: 45, label: "Down and right"}),
    Object.freeze({value: 90, label: "Down"}),
    Object.freeze({value: 135, label: "Down and left"}),
    Object.freeze({value: 180, label: "Left"}),
    Object.freeze({value: 225, label: "Up and left"}),
    Object.freeze({value: 270, label: "Up"}),
    Object.freeze({value: 315, label: "Up and right"}),
  ]);
  const PATTERN_STRAIGHT_DIRECTIONS = Object.freeze(
    PATTERN_DIRECTIONS.filter(entry => entry.value % 90 === 0),
  );
  // Values the interface never shows. They are the engine defaults every
  // pattern is bounded around, and they are written into every layer so the
  // saved settings are complete whichever pattern is chosen.
  const PATTERN_FIXED = Object.freeze({
    size: 0.5,
    spread: 0.5,
    direction: 0,
    count: 1,
    trail: 0,
    seed: 0,
  });
  // Shuffle steps through this list rather than any whole number, so the
  // arrangements a pattern can reach are a short checked set instead of ten
  // thousand unchecked ones. Every entry was checked against the engine's
  // acceptance rules for every pattern, every control step, and every
  // supported keyboard.
  const PATTERN_ARRANGEMENTS = Object.freeze([
    0, 14, 21, 42, 63, 70, 77, 84, 91, 112, 119, 140, 147, 154, 161, 168,
  ]);

  function patternControl(id, label, extra = {}) {
    return Object.freeze({id, label, ...extra});
  }

  // `fixed` overrides a value the interface never shows for this pattern —
  // used where one setting has to sit at a checked constant for the pattern to
  // be usable at all, rather than offering a step nothing accepts.
  function patternKind(id, label, blurb, controls, {shuffle = false, fixed = null} = {}) {
    return Object.freeze({
      id,
      label,
      blurb,
      shuffle,
      fixed: Object.freeze({...fixed}),
      controls: Object.freeze(controls),
    });
  }

  const PATTERN_KINDS = Object.freeze([
    patternKind("comet", "Comet", "A bright head that draws a tail behind it.", [
      patternControl("size", "Head size", {min: 0.75, max: 1}),
      patternControl("count", "How many", {min: 1, max: 4, integer: true}),
      patternControl("trail", "Tail length", {min: 0.1, max: 0.8}),
      patternControl("direction", "Direction", {directions: PATTERN_DIRECTIONS}),
    ]),
    patternKind("wave", "Wave", "Rolling bands of light crossing the keyboard.", [
      patternControl("size", "Band width", {min: 0.25, max: 0.9}),
      patternControl("spread", "Band spacing", {min: 0.6, max: 1}),
      patternControl("direction", "Direction", {directions: PATTERN_DIRECTIONS}),
    ]),
    patternKind("pulse", "Pulse", "A ring of light growing out of the middle.", [
      patternControl("size", "Ring width", {min: 0.25, max: 0.9}),
      patternControl("spread", "Ring reach", {min: 0.2, max: 1.2}),
    ]),
    // Sparkle's points sit wherever its arrangement puts them, so a small point
    // can miss every light on a coarse keyboard. Point size stays at its widest
    // and the arrangement comes from the checked list below.
    patternKind("sparkle", "Sparkle", "Scattered points of light fading in and out.", [
      patternControl("count", "How many", {min: 8, max: 12, integer: true}),
    ], {shuffle: true, fixed: {size: 1}}),
    patternKind("orbit", "Orbit", "Dots circling around the middle.", [
      patternControl("size", "Dot size", {min: 0.45, max: 0.9}),
      patternControl("spread", "Circle size", {min: 0.2, max: 1}),
      patternControl("count", "How many", {min: 1, max: 6, integer: true}),
    ]),
    patternKind("sweep", "Sweep", "One wide band passing over and over.", [
      patternControl("size", "Band width", {min: 0.25, max: 0.9}),
      patternControl("direction", "Direction", {directions: PATTERN_DIRECTIONS}),
    ]),
    patternKind("noise", "Drift", "Soft clouds of light drifting across.", [
      patternControl("size", "Cloud fullness", {min: 0.45, max: 0.9}),
    ], {shuffle: true}),
    patternKind("breathe", "Breathe", "The whole keyboard rising and falling together.", [
      patternControl("size", "Glow fullness", {min: 0.25, max: 0.9}),
    ]),
    patternKind("chase", "Chase", "Light walking the keys one after another.", [
      patternControl("count", "How many", {min: 1, max: 2, integer: true}),
      patternControl("trail", "Tail length", {min: 0.05, max: 0.3}),
    ]),
    patternKind("ripple", "Ripple", "Rings spreading out from the middle, one after another.", [
      patternControl("size", "Ring width", {min: 0.25, max: 0.9}),
      patternControl("spread", "Ring spacing", {min: 0.5, max: 0.8}),
    ]),
    patternKind("matrix_rain", "Rainfall", "Falling streaks, each lane on its own timing.", [
      patternControl("trail", "Streak length", {min: 0.02, max: 0.1}),
      patternControl("direction", "Direction", {directions: PATTERN_STRAIGHT_DIRECTIONS}),
    ], {shuffle: true}),
    patternKind("heartbeat", "Heartbeat", "A double beat with a rest between.", [
      patternControl("size", "Beat length", {min: 0.2, max: 0.6}),
    ]),
    patternKind("fire", "Fire", "Flickering heat rising from the bottom row.", [
      patternControl("size", "Flame softness", {min: 0.3, max: 0.9}),
      patternControl("spread", "Flame height", {min: 0.75, max: 0.9}),
    ], {shuffle: true}),
    patternKind("twinkle", "Twinkle", "Every light fading on its own timing.", [
      patternControl("size", "Fade fullness", {min: 0.3, max: 0.9}),
    ], {shuffle: true}),
  ]);

  const PATTERN_KINDS_BY_ID = new Map(PATTERN_KINDS.map(kind => [kind.id, kind]));

  function patternKindById(id) {
    return PATTERN_KINDS_BY_ID.get(String(id ?? "")) || null;
  }

  function patternControlSteps(control) {
    if (!control || control.directions) return [];
    const span = (control.max - control.min) / (PATTERN_STEPS - 1);
    if (control.integer) {
      if (control.max - control.min + 1 <= PATTERN_STEPS) {
        return Array.from(
          {length: control.max - control.min + 1},
          (_, index) => control.min + index,
        );
      }
      return [...new Set(
        Array.from({length: PATTERN_STEPS}, (_, index) => Math.round(control.min + span * index)),
      )].sort((left, right) => left - right);
    }
    return Array.from(
      {length: PATTERN_STEPS},
      (_, index) => Number((control.min + span * index).toFixed(6)),
    );
  }

  function patternControlValues(control) {
    return control?.directions
      ? control.directions.map(entry => entry.value)
      : patternControlSteps(control);
  }

  function nearestAllowedValue(values, candidate) {
    const number = Number(candidate);
    if (!Number.isFinite(number)) return values[Math.floor(values.length / 2)];
    return values.reduce(
      (best, value) => Math.abs(value - number) < Math.abs(best - number) ? value : best,
      values[0],
    );
  }

  function patternColorValue(candidate, fallback) {
    const value = safeRgbColor(candidate);
    return PATTERN_COLORS.some(color => color.value === value) ? value : fallback;
  }

  function defaultPatternSettings(kindId) {
    const kind = patternKindById(kindId) || PATTERN_KINDS[0];
    const settings = {
      kind: kind.id,
      main_color: PATTERN_COLORS[6].value,
      second_color: PATTERN_COLORS[4].value,
      speed: PATTERN_SPEEDS[1].value,
      ...PATTERN_FIXED,
      ...kind.fixed,
    };
    for (const control of kind.controls) {
      const values = patternControlValues(control);
      settings[control.id] = values[Math.floor(values.length / 2)];
    }
    if (kind.shuffle) settings.seed = PATTERN_ARRANGEMENTS[0];
    return settings;
  }

  // Snapping, not rejecting: any stored or restored value collapses onto the
  // nearest step this pattern allows, so no interface path can produce settings
  // outside the checked space.
  function clampPatternSettings(value) {
    const requested = value && typeof value === "object" ? value : {};
    const kind = patternKindById(requested.kind) || PATTERN_KINDS[0];
    const defaults = defaultPatternSettings(kind.id);
    const settings = {
      kind: kind.id,
      main_color: patternColorValue(requested.main_color, defaults.main_color),
      second_color: patternColorValue(requested.second_color, defaults.second_color),
      speed: nearestAllowedValue(
        PATTERN_SPEEDS.map(entry => entry.value),
        requested.speed ?? defaults.speed,
      ),
      ...PATTERN_FIXED,
      ...kind.fixed,
      seed: PATTERN_FIXED.seed,
    };
    for (const control of kind.controls) {
      settings[control.id] = nearestAllowedValue(
        patternControlValues(control),
        requested[control.id] ?? defaults[control.id],
      );
    }
    if (kind.shuffle) {
      settings.seed = nearestAllowedValue(PATTERN_ARRANGEMENTS, requested.seed ?? defaults.seed);
    }
    return settings;
  }

  function patternUsesControl(kindId, controlId) {
    const kind = patternKindById(kindId);
    if (!kind) return false;
    if (controlId === "seed") return kind.shuffle;
    return kind.controls.some(control => control.id === controlId);
  }

  // A dim always-on wash under the pattern. Every offered color has a 255
  // channel, so this is always brighter than the engine's "lit" threshold and
  // the chosen fullness band is met on every frame of every pattern.
  function patternBackgroundColor(color) {
    const value = safeRgbColor(color);
    const channels = [1, 3, 5].map(index => parseInt(value.slice(index, index + 2), 16));
    return `#${channels
      .map(channel => Math.round(channel * PATTERN_BACKGROUND_LEVEL / 255)
        .toString(16)
        .padStart(2, "0"))
      .join("")}`.toUpperCase();
  }

  function nextPatternSeed(random = Math.random) {
    const roll = Number(random());
    const normalized = Number.isFinite(roll) ? Math.abs(roll) % 1 : 0;
    const index = Math.min(
      PATTERN_ARRANGEMENTS.length - 1,
      Math.floor(normalized * PATTERN_ARRANGEMENTS.length),
    );
    return PATTERN_ARRANGEMENTS[index];
  }

  function buildPatternRecipe(value) {
    const settings = clampPatternSettings(value);
    const kind = patternKindById(settings.kind);
    return {
      schema_version: PATTERN_SCHEMA_VERSION,
      name: kind.label,
      density: "dense",
      background: patternBackgroundColor(settings.main_color),
      palette: [settings.main_color, settings.second_color],
      layers: [{
        kind: settings.kind,
        color_index: 0,
        secondary_color_index: 1,
        speed: settings.speed,
        phase: 0,
        direction_degrees: settings.direction,
        center_x: 0.5,
        center_y: 0.5,
        scale: settings.spread,
        width: settings.size,
        trail: settings.trail,
        count: settings.count,
        intensity: 1,
        seed: settings.seed,
      }],
    };
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
    PATTERN_ARRANGEMENTS,
    PATTERN_COLORS,
    PATTERN_KINDS,
    PATTERN_SPEEDS,
    ROUTES,
    STAGES,
    applyCompatibility,
    buildPatternRecipe,
    clampPatternSettings,
    classifyImportedJsonSelection,
    createEpochLoadRegistry,
    createLaunchState,
    createPaintStrokeController,
    createLightingState,
    defaultPatternSettings,
    escapeMarkup,
    formatLightingHash,
    importedLightingApplyAvailability,
    nextGridIndex,
    nextPatternSeed,
    parseLightingHash,
    patternControlValues,
    patternKindById,
    patternUsesControl,
    projectLightingJob,
    reduceLightingState,
    routeAvailability,
    safeRgbColor,
  });
});
