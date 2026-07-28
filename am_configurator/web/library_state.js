(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LibraryState = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const TRANSFORM_FIELDS = new Set([
    "version",
    "offset_x",
    "offset_y",
    "scale_x",
    "scale_y",
    "aspect_locked",
    "sampling",
    "background",
  ]);
  const SOURCE_FIELDS = new Set([
    "asset_id",
    "mime_type",
    "width",
    "height",
    "frame_count",
    "duration_ms",
  ]);
  const DESTINATION_FIELDS = new Set([
    "productId",
    "target",
    "targets",
    "width",
    "height",
  ]);

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function deepFreeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
    return value;
  }

  function exactObject(value, fields, label) {
    if (
      !value
      || typeof value !== "object"
      || Array.isArray(value)
      || Object.keys(value).length !== fields.size
      || Object.keys(value).some(field => !fields.has(field))
    ) {
      throw new TypeError(`${label} is invalid.`);
    }
    return value;
  }

  function positiveInteger(value, label) {
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new RangeError(`${label} is invalid.`);
    }
    return value;
  }

  function validateSource(value) {
    const source = exactObject(value, SOURCE_FIELDS, "The media source");
    if (
      typeof source.asset_id !== "string"
      || !source.asset_id
      || !["image/gif", "image/png", "image/bmp"].includes(source.mime_type)
    ) {
      throw new TypeError("The media source identity is invalid.");
    }
    positiveInteger(source.width, "The media source width");
    positiveInteger(source.height, "The media source height");
    positiveInteger(source.frame_count, "The media source frame count");
    if (
      !Number.isSafeInteger(source.duration_ms)
      || source.duration_ms < 0
      || (source.mime_type === "image/gif" && source.duration_ms === 0)
      || (source.mime_type !== "image/gif"
        && (source.frame_count !== 1 || source.duration_ms !== 0))
    ) {
      throw new RangeError("The media source timing is invalid.");
    }
    return clone(source);
  }

  function validateDestination(value) {
    const destination = exactObject(
      value,
      DESTINATION_FIELDS,
      "The media destination",
    );
    if (
      typeof destination.productId !== "string"
      || !destination.productId
      || typeof destination.target !== "string"
      || !destination.target
      || !Array.isArray(destination.targets)
      || destination.targets.length === 0
      || destination.targets.some(target => typeof target !== "string" || !target)
      || !destination.targets.includes(destination.target)
    ) {
      throw new TypeError("The media destination identity is invalid.");
    }
    positiveInteger(destination.width, "The media destination width");
    positiveInteger(destination.height, "The media destination height");
    return clone(destination);
  }

  function validateTransform(value) {
    const transform = exactObject(value, TRANSFORM_FIELDS, "The source transform");
    if (
      transform.version !== 1
      || !Number.isFinite(transform.offset_x)
      || !Number.isFinite(transform.offset_y)
      || !Number.isFinite(transform.scale_x)
      || !Number.isFinite(transform.scale_y)
      || transform.scale_x <= 0
      || transform.scale_y <= 0
      || typeof transform.aspect_locked !== "boolean"
      || !["nearest", "box", "lanczos"].includes(transform.sampling)
      || transform.background !== "#000000"
    ) {
      throw new TypeError("The source transform is invalid.");
    }
    return clone(transform);
  }

  function validateEffects(value) {
    if (!Array.isArray(value) || value.length > 8) {
      throw new TypeError("The media effects are invalid.");
    }
    return clone(value);
  }

  function nextMediaRenderEpoch(previous, now = Date.now()) {
    if (
      !Number.isSafeInteger(previous)
      || previous < 0
      || !Number.isSafeInteger(now)
      || now < 0
      || now > Math.floor(Number.MAX_SAFE_INTEGER / 1000)
    ) {
      throw new RangeError("The media render epoch is invalid.");
    }
    const epoch = Math.max(previous + 1, now * 1000);
    if (!Number.isSafeInteger(epoch)) {
      throw new RangeError("The media render epoch space is exhausted.");
    }
    return epoch;
  }

  function pageFingerprint(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new TypeError("The lighting page is invalid.");
    }
    const encoded = JSON.stringify(value);
    if (!encoded || encoded.length > 4_000_000) {
      throw new RangeError("The lighting page is too large.");
    }
    return encoded;
  }

  function createLightingProvenance({
    slot,
    target,
    sourceCatalogId = null,
    transform = null,
    effects = [],
    page,
  }) {
    if (!Number.isSafeInteger(slot) || ![5, 6, 7].includes(slot)) {
      throw new RangeError("The lighting provenance slot is invalid.");
    }
    if (typeof target !== "string" || !target) {
      throw new TypeError("The lighting provenance target is invalid.");
    }
    if (
      sourceCatalogId !== null
      && (
        typeof sourceCatalogId !== "string"
        || !sourceCatalogId.startsWith("item:")
      )
    ) {
      throw new TypeError("The lighting provenance source is invalid.");
    }
    if (
      (sourceCatalogId === null && transform !== null)
      || (sourceCatalogId !== null && transform === null)
    ) {
      throw new TypeError("The lighting provenance transform is invalid.");
    }
    return deepFreeze({
      version: 1,
      slot,
      target,
      source_catalog_id: sourceCatalogId,
      transform: transform === null ? null : validateTransform(transform),
      effects: validateEffects(effects),
      page_fingerprint: pageFingerprint(page),
    });
  }

  function lightingProvenanceForPage(provenance, {slot, target, page}) {
    if (
      !provenance
      || provenance.version !== 1
      || provenance.slot !== slot
      || provenance.target !== target
      || provenance.page_fingerprint !== pageFingerprint(page)
    ) {
      return null;
    }
    return deepFreeze({
      source_catalog_id: provenance.source_catalog_id,
      transform: clone(provenance.transform),
      effects: clone(provenance.effects),
    });
  }

  function validateMappedResult(value) {
    if (
      !value
      || typeof value !== "object"
      || Array.isArray(value)
      || !value.tracks
      || typeof value.tracks !== "object"
      || Array.isArray(value.tracks)
      || Object.keys(value.tracks).length === 0
    ) {
      throw new TypeError("The rendered LED result is invalid.");
    }
    return clone(value);
  }

  function createMediaDraft({
    catalogId,
    source,
    destination,
    transform,
    effects = [],
  }) {
    if (typeof catalogId !== "string" || !catalogId.startsWith("item:")) {
      throw new TypeError("The banked media catalog identity is invalid.");
    }
    return deepFreeze({
      version: 1,
      catalogId,
      source: validateSource(source),
      destination: validateDestination(destination),
      transform: validateTransform(transform),
      effects: validateEffects(effects),
      status: "draft",
      epoch: 0,
      mappedResult: null,
      error: "",
    });
  }

  function changedDraft(state, changes) {
    return deepFreeze({
      ...state,
      ...changes,
      status: "draft",
      mappedResult: null,
      error: "",
    });
  }

  function reduceMediaDraft(state, action) {
    if (!state || state.version !== 1 || !action || typeof action !== "object") {
      throw new TypeError("The media draft transition is invalid.");
    }
    if (action.type === "RENDER_REQUESTED") {
      if (
        !Number.isSafeInteger(action.epoch)
        || action.epoch < 0
        || action.epoch < state.epoch
      ) {
        return state;
      }
      return deepFreeze({
        ...state,
        status: "rendering",
        epoch: action.epoch,
        mappedResult: null,
        error: "",
      });
    }
    if (action.type === "RENDER_SUCCEEDED") {
      if (state.status !== "rendering" || action.epoch !== state.epoch) return state;
      return deepFreeze({
        ...state,
        status: "ready",
        mappedResult: validateMappedResult(action.mappedResult),
        error: "",
      });
    }
    if (action.type === "RENDER_FAILED") {
      if (state.status !== "rendering" || action.epoch !== state.epoch) return state;
      return deepFreeze({
        ...state,
        status: "failed",
        mappedResult: null,
        error: String(action.error || "The media preview failed."),
      });
    }
    if (action.type === "TRANSFORM_CHANGED") {
      return changedDraft(state, {
        transform: validateTransform(action.transform),
      });
    }
    if (action.type === "EFFECTS_CHANGED") {
      return changedDraft(state, {
        effects: validateEffects(action.effects),
      });
    }
    if (action.type === "DESTINATION_CHANGED") {
      return changedDraft(state, {
        destination: validateDestination(action.destination),
      });
    }
    if (action.type === "CANCELLED") {
      return deepFreeze({
        ...state,
        status: "cancelled",
        mappedResult: null,
        error: "",
      });
    }
    if (action.type === "APPLIED") {
      if (!mediaDraftCanApply(state)) return state;
      return deepFreeze({...state, status: "applied", error: ""});
    }
    throw new RangeError("The media draft action is unsupported.");
  }

  function mediaDraftCanApply(state) {
    return Boolean(
      state
      && state.status === "ready"
      && state.mappedResult
      && state.mappedResult.tracks
      && Object.keys(state.mappedResult.tracks).length,
    );
  }

  return Object.freeze({
    createLightingProvenance,
    createMediaDraft,
    lightingProvenanceForPage,
    mediaDraftCanApply,
    nextMediaRenderEpoch,
    reduceMediaDraft,
  });
});
