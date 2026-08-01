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
  const LIBRARY_FILTERS = Object.freeze({
    all: Object.freeze({removed: false}),
    sources: Object.freeze({removed: false, kind: "media_source"}),
    lighting: Object.freeze({removed: false, kind: "lighting"}),
    keymaps: Object.freeze({removed: false, kind: "keyboard_profile"}),
    removed: Object.freeze({removed: true}),
  });
  const PROFILE_SECTIONS = Object.freeze(["keymap", "macros", "lighting"]);

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function deepFreeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
    return value;
  }

  function libraryCatalogQuery({
    filter = "all",
    page = 1,
    limit = 12,
    query = "",
  } = {}) {
    const projection = LIBRARY_FILTERS[filter];
    if (!projection) throw new RangeError("The Library filter is invalid.");
    positiveInteger(page, "The Library page");
    positiveInteger(limit, "The Library page size");
    if (limit > 100) throw new RangeError("The Library page size is invalid.");
    if (typeof query !== "string" || query.length > 200) {
      throw new TypeError("The Library search is invalid.");
    }
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
      removed: String(projection.removed),
    });
    if (projection.kind) params.set("kind", projection.kind);
    const search = query.trim();
    if (search) params.set("query", search);
    return params.toString();
  }

  function compatibleProfileSections(plan) {
    const sections = plan?.sections;
    if (!sections || typeof sections !== "object" || Array.isArray(sections)) {
      return [];
    }
    return PROFILE_SECTIONS.filter(section => {
      const status = sections[section]?.status;
      return section === "macros" ? status === "portable" : status === "exact";
    });
  }

  function normalizeProfileSections(plan, selected) {
    if (!Array.isArray(selected)) {
      throw new TypeError("Select one or more compatible profile sections.");
    }
    const allowed = new Set(compatibleProfileSections(plan));
    const requested = new Set(selected);
    const normalized = PROFILE_SECTIONS.filter(
      section => requested.has(section) && allowed.has(section),
    );
    if (!normalized.length) {
      throw new RangeError("Select one or more compatible profile sections.");
    }
    return normalized;
  }

  function nextCatalogIndex({index, count, columns = 1, key}) {
    if (
      !Number.isSafeInteger(index)
      || !Number.isSafeInteger(count)
      || !Number.isSafeInteger(columns)
      || count <= 0
      || index < 0
      || index >= count
      || columns <= 0
    ) {
      throw new RangeError("The Library grid position is invalid.");
    }
    let next = index;
    if (key === "Home") next = 0;
    else if (key === "End") next = count - 1;
    else if (key === "ArrowLeft") next = index - 1;
    else if (key === "ArrowRight") next = index + 1;
    else if (key === "ArrowUp") next = index - columns;
    else if (key === "ArrowDown") next = index + columns;
    return Math.max(0, Math.min(count - 1, next));
  }

  function createLibraryRequestEpochs() {
    let sequence = 0;
    const active = new Map();
    return Object.freeze({
      begin(key, catalogEpoch) {
        if (
          typeof key !== "string"
          || !key
          || !Number.isSafeInteger(catalogEpoch)
          || catalogEpoch < 0
        ) {
          throw new TypeError("The Library request identity is invalid.");
        }
        const requestEpoch = ++sequence;
        active.set(key, requestEpoch);
        let released = false;
        return Object.freeze({
          current(currentCatalogEpoch) {
            return Boolean(
              !released
              && currentCatalogEpoch === catalogEpoch
              && active.get(key) === requestEpoch,
            );
          },
          release() {
            if (released) return;
            released = true;
            if (active.get(key) === requestEpoch) active.delete(key);
          },
        });
      },
    });
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

  function validateResolvedTransforms(value, effects) {
    if (!Array.isArray(value)) {
      throw new TypeError("The resolved media transforms are invalid.");
    }
    const moveZoom = effects.filter(effect => effect?.type === "move_zoom");
    const expected = moveZoom.length === 1
      && Number.isSafeInteger(moveZoom[0].frame_count)
      ? moveZoom[0].frame_count
      : 0;
    if (moveZoom.length > 1 || value.length !== expected) {
      throw new TypeError("The resolved media transforms are invalid.");
    }
    return value.map(validateTransform);
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
      throw new TypeError("The lighting preview could not be read.");
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
      throw new TypeError("The saved Library item is invalid.");
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
      resolvedTransforms: [],
      error: "",
    });
  }

  function changedDraft(state, changes) {
    return deepFreeze({
      ...state,
      ...changes,
      status: "draft",
      mappedResult: null,
      resolvedTransforms: [],
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
        resolvedTransforms: [],
        error: "",
      });
    }
    if (action.type === "RENDER_SUCCEEDED") {
      if (state.status !== "rendering" || action.epoch !== state.epoch) return state;
      const effects = validateEffects(action.effects);
      return deepFreeze({
        ...state,
        status: "ready",
        transform: validateTransform(action.transform),
        effects,
        mappedResult: validateMappedResult(action.mappedResult),
        resolvedTransforms: validateResolvedTransforms(
          action.resolvedTransforms,
          effects,
        ),
        error: "",
      });
    }
    if (action.type === "RENDER_FAILED") {
      if (state.status !== "rendering" || action.epoch !== state.epoch) return state;
      return deepFreeze({
        ...state,
        status: "failed",
        mappedResult: null,
        resolvedTransforms: [],
        error: String(action.error || "The preview could not be created. Nothing was changed; adjust the framing and try again."),
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
        resolvedTransforms: [],
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
    compatibleProfileSections,
    createLibraryRequestEpochs,
    createLightingProvenance,
    createMediaDraft,
    libraryCatalogQuery,
    lightingProvenanceForPage,
    mediaDraftCanApply,
    nextCatalogIndex,
    nextMediaRenderEpoch,
    normalizeProfileSections,
    reduceMediaDraft,
  });
});
