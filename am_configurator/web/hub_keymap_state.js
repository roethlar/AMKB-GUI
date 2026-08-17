(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HubKeymapState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const ECOSYSTEMS = new Set(["am", "vial", "via"]);
  const HISTORY_LIMIT = 100;

  function plainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    if (!plainObject(value)) return value;
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, clone(child)]));
  }

  function freeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    for (const child of Object.values(value)) freeze(child);
    return Object.freeze(value);
  }

  function immutableCopy(value) {
    return freeze(clone(value));
  }

  function finite(value, label, {positive = false} = {}) {
    if (typeof value !== "number" || !Number.isFinite(value) || (positive && value <= 0)) {
      throw new TypeError(`${label} is invalid.`);
    }
    return value;
  }

  function validateProfile(value) {
    if (!plainObject(value) || value.schema_version !== 1 || !plainObject(value.identity)) {
      throw new TypeError("The hub profile is invalid.");
    }
    const ecosystem = value.identity.ecosystem;
    if (!ECOSYSTEMS.has(ecosystem)) throw new TypeError("The hub profile ecosystem is invalid.");
    if (typeof value.identity.family !== "string" || !value.identity.family.trim()) {
      throw new TypeError("The hub profile family is invalid.");
    }
    if (!plainObject(value.keymap) || !Array.isArray(value.keymap.layers) || !value.keymap.layers.length) {
      throw new TypeError("The hub profile carries no editable keymap.");
    }
    const layerIndexes = new Set();
    for (const layer of value.keymap.layers) {
      if (!plainObject(layer) || !Number.isSafeInteger(layer.index) || layer.index < 0) {
        throw new TypeError("A hub keymap layer is invalid.");
      }
      if (layerIndexes.has(layer.index)) throw new TypeError("A hub keymap layer is repeated.");
      layerIndexes.add(layer.index);
      if (!Array.isArray(layer.keys)) throw new TypeError("A hub keymap layer has no keys.");
      const keys = new Set();
      for (const key of layer.keys) {
        if (!plainObject(key) || typeof key.key !== "string" || !key.key) {
          throw new TypeError("A hub key identity is invalid.");
        }
        if (keys.has(key.key)) throw new TypeError("A hub key identity is repeated in one layer.");
        keys.add(key.key);
        if (!Number.isSafeInteger(key.code) || key.code < 0 || key.code > 0xffff) {
          throw new TypeError("A hub keycode is invalid.");
        }
      }
    }
    return immutableCopy(value);
  }

  function validateTarget(value, ecosystem) {
    if (!plainObject(value) || value.ecosystem !== ecosystem) {
      throw new TypeError("The hub target binding does not match the profile ecosystem.");
    }
    const address = value.address ?? null;
    if (address !== null && (typeof address !== "string" || !address.trim())) {
      throw new TypeError("The hub target address is invalid.");
    }
    if (ecosystem === "via" && address !== null && !plainObject(value.definition)) {
      throw new TypeError("A user-imported VIA definition is required before reading this keyboard.");
    }
    return immutableCopy({...value, address});
  }

  function validateLayout(value) {
    if (!Array.isArray(value)) throw new TypeError("The hub layout is invalid.");
    const keys = new Set();
    return freeze(value.map((item) => {
      if (!plainObject(item) || typeof item.key !== "string" || !item.key) {
        throw new TypeError("A hub layout key identity is invalid.");
      }
      if (keys.has(item.key)) throw new TypeError("A hub layout key identity is repeated.");
      keys.add(item.key);
      if (!Number.isSafeInteger(item.matrix_row) || item.matrix_row < 0 ||
          !Number.isSafeInteger(item.matrix_col) || item.matrix_col < 0) {
        throw new TypeError("A hub layout matrix position is invalid.");
      }
      const result = {
        ...item,
        x: finite(item.x, "Hub layout x"),
        y: finite(item.y, "Hub layout y"),
        width: finite(item.width, "Hub layout width", {positive: true}),
        height: finite(item.height, "Hub layout height", {positive: true}),
        rotation: finite(item.rotation ?? 0, "Hub layout rotation"),
      };
      if ("rotation_x" in item) result.rotation_x = finite(item.rotation_x, "Hub layout rotation x");
      if ("rotation_y" in item) result.rotation_y = finite(item.rotation_y, "Hub layout rotation y");
      return freeze(result);
    }));
  }

  function validateReview(report, worklist) {
    if (report !== null && !plainObject(report)) {
      throw new TypeError("The hub transfer report is invalid.");
    }
    if (!Array.isArray(worklist) || worklist.some((item) => !plainObject(item))) {
      throw new TypeError("The hub overlay worklist is invalid.");
    }
    for (const item of worklist) {
      if ("source" in item) {
        const source = item.source;
        if (!plainObject(source) || !Number.isSafeInteger(source.layer) || source.layer < 0 ||
            typeof source.key !== "string" || !source.key ||
            !Number.isSafeInteger(source.code) || source.code < 0 || source.code > 0xffff) {
          throw new TypeError("A hub worklist source is invalid.");
        }
      }
      if ("suggestions" in item) {
        if (!Array.isArray(item.suggestions) || item.suggestions.some((suggestion) =>
          !plainObject(suggestion) ||
          !Number.isSafeInteger(suggestion.target_layer) || suggestion.target_layer < 0 ||
          typeof suggestion.target_key !== "string" || !suggestion.target_key)) {
          throw new TypeError("A hub worklist suggestion is invalid.");
        }
      }
    }
    return {
      report: report === null ? null : immutableCopy(report),
      worklist: immutableCopy(worklist),
    };
  }

  function profileText(profile) {
    return JSON.stringify(profile);
  }

  function sameProfile(left, right) {
    return left === right || profileText(left) === profileText(right);
  }

  function sameValue(left, right) {
    return left === right || JSON.stringify(left) === JSON.stringify(right);
  }

  function layerByIndex(profile, index) {
    return profile.keymap.layers.find((layer) => layer.index === index) || null;
  }

  function stateValue(value) {
    return freeze(value);
  }

  function createHubKeymapState({profile, layout = [], target, report = null, worklist = []}) {
    const validatedProfile = validateProfile(profile);
    const validatedTarget = validateTarget(target, validatedProfile.identity.ecosystem);
    const validatedLayout = validateLayout(layout);
    const review = validateReview(report, worklist);
    const layer = validatedProfile.keymap.layers[0].index;
    return stateValue({
      profile: validatedProfile,
      savedProfile: validatedProfile,
      target: validatedTarget,
      layout: validatedLayout,
      report: review.report,
      worklist: review.worklist,
      layer,
      selectedKey: null,
      dirty: false,
      undo: freeze([]),
      redo: freeze([]),
    });
  }

  function replaceState(state, changes) {
    return stateValue({...state, ...changes});
  }

  function documentSnapshot(state) {
    return freeze({
      profile: state.profile,
      report: state.report,
      worklist: state.worklist,
    });
  }

  function dirtyAgainstSaved(profile, state) {
    return !sameProfile(profile, state.savedProfile);
  }

  function checkpoint(state, profile, report = state.report, worklist = state.worklist) {
    if (sameProfile(profile, state.profile) && sameValue(report, state.report) &&
        sameValue(worklist, state.worklist)) return state;
    const undo = freeze([...state.undo, documentSnapshot(state)].slice(-HISTORY_LIMIT));
    return replaceState(state, {
      profile,
      report,
      worklist,
      dirty: dirtyAgainstSaved(profile, state),
      undo,
      redo: freeze([]),
    });
  }

  function keyExists(profile, layerIndex, keyIdentity) {
    const layer = layerByIndex(profile, layerIndex);
    return Boolean(layer?.keys.some((key) => key.key === keyIdentity));
  }

  function setKeyCode(state, code) {
    if (state.selectedKey === null) throw new TypeError("Select a key before assigning a keycode.");
    if (!Number.isSafeInteger(code) || code < 0 || code > 0xffff) {
      throw new TypeError("The assigned keycode is invalid.");
    }
    const profile = clone(state.profile);
    const layer = layerByIndex(profile, state.layer);
    const key = layer?.keys.find((item) => item.key === state.selectedKey);
    if (!key) throw new TypeError("The selected key is absent from this layer.");
    if (key.code === code) return state;
    key.code = code;
    if (state.report !== null) profile.transfer_report = state.report;
    return checkpoint(state, freeze(profile));
  }

  function applyOverlay(state, action) {
    let profile = validateProfile(action.profile);
    if (profile.identity.ecosystem !== state.target.ecosystem) {
      throw new TypeError("The overlay hub profile does not match the target ecosystem.");
    }
    const review = validateReview(action.report ?? null, action.worklist ?? []);
    if (review.report === null) throw new TypeError("The hub overlay has no transfer report.");
    const reviewedProfile = clone(profile);
    reviewedProfile.transfer_report = review.report;
    profile = freeze(reviewedProfile);
    return checkpoint(state, profile, review.report, review.worklist);
  }

  function resolutionTarget(action) {
    if (!plainObject(action.target) || !Number.isSafeInteger(action.target.layer) ||
        action.target.layer < 0 || typeof action.target.key !== "string" || !action.target.key) {
      throw new TypeError("The worklist target key is invalid.");
    }
    return {layer: action.target.layer, key: action.target.key};
  }

  function resolveWorklist(state, action) {
    if (typeof action.path !== "string" || !action.path) {
      throw new TypeError("The worklist path is invalid.");
    }
    const worklistIndex = state.worklist.findIndex((item) => item.path === action.path);
    if (worklistIndex < 0) throw new RangeError("The worklist item is no longer unresolved.");
    const item = state.worklist[worklistIndex];
    if (!plainObject(state.report) || !Array.isArray(state.report.items)) {
      throw new TypeError("The worklist item has no transfer report.");
    }
    const reportIndex = state.report.items.findIndex((entry) => entry.path === action.path);
    if (reportIndex < 0) throw new RangeError("The worklist item is absent from the transfer report.");

    const report = clone(state.report);
    const reportItem = report.items[reportIndex];
    const profile = clone(state.profile);
    if (action.resolution === "leave_out") {
      reportItem.verdict = "dropped";
      reportItem.reason = "Left out by the user during overlay review.";
    } else if (action.resolution === "suggestion" || action.resolution === "chosen") {
      const source = item.source;
      if (!plainObject(source) || !Number.isSafeInteger(source.code) || source.code < 0 ||
          source.code > 0xffff) {
        throw new TypeError("The worklist source key is invalid.");
      }
      const target = resolutionTarget(action);
      if (action.resolution === "suggestion") {
        const offered = Array.isArray(item.suggestions) && item.suggestions.some((suggestion) =>
          suggestion.target_layer === target.layer && suggestion.target_key === target.key);
        if (!offered) throw new RangeError("The chosen placement is not an offered suggestion.");
      }
      const layer = layerByIndex(profile, target.layer);
      const key = layer?.keys.find((entry) => entry.key === target.key);
      if (!key) throw new RangeError("The chosen target key is absent from that layer.");
      key.code = source.code;
      reportItem.verdict = "adapted";
      reportItem.reason = action.resolution === "suggestion"
        ? "Placed using an overlay suggestion accepted by the user."
        : "Placed on a target key chosen by the user.";
    } else {
      throw new RangeError("The worklist resolution is invalid.");
    }

    const frozenReport = freeze(report);
    profile.transfer_report = frozenReport;
    const worklist = freeze(state.worklist.filter((_entry, index) => index !== worklistIndex));
    return checkpoint(state, freeze(profile), frozenReport, worklist);
  }

  function reduceHubKeymapState(state, action) {
    if (!plainObject(state) || !plainObject(action) || typeof action.type !== "string") {
      throw new TypeError("The hub keymap transition is invalid.");
    }
    switch (action.type) {
      case "SELECT_LAYER": {
        if (!Number.isSafeInteger(action.layer) || !layerByIndex(state.profile, action.layer)) {
          throw new RangeError("The selected hub layer is out of range.");
        }
        if (action.layer === state.layer && state.selectedKey === null) return state;
        return replaceState(state, {layer: action.layer, selectedKey: null});
      }
      case "SELECT_KEY": {
        if (typeof action.key !== "string" || !keyExists(state.profile, state.layer, action.key)) {
          throw new RangeError("The selected hub key is absent from this layer.");
        }
        if (action.key === state.selectedKey) return state;
        return replaceState(state, {selectedKey: action.key});
      }
      case "SET_KEY_CODE":
        return setKeyCode(state, action.code);
      case "APPLY_OVERLAY":
        return applyOverlay(state, action);
      case "RESOLVE_WORKLIST":
        return resolveWorklist(state, action);
      case "REPLACE_PROFILE": {
        let profile = validateProfile(action.profile);
        if (profile.identity.ecosystem !== state.target.ecosystem) {
          throw new TypeError("The replacement hub profile does not match the target ecosystem.");
        }
        if (state.report !== null) {
          const reviewedProfile = clone(profile);
          reviewedProfile.transfer_report = state.report;
          profile = freeze(reviewedProfile);
        }
        return checkpoint(state, profile);
      }
      case "UNDO": {
        if (!state.undo.length) return state;
        const document = state.undo[state.undo.length - 1];
        return replaceState(state, {
          profile: document.profile,
          report: document.report,
          worklist: document.worklist,
          dirty: dirtyAgainstSaved(document.profile, state),
          undo: freeze(state.undo.slice(0, -1)),
          redo: freeze([...state.redo, documentSnapshot(state)].slice(-HISTORY_LIMIT)),
        });
      }
      case "REDO": {
        if (!state.redo.length) return state;
        const document = state.redo[state.redo.length - 1];
        return replaceState(state, {
          profile: document.profile,
          report: document.report,
          worklist: document.worklist,
          dirty: dirtyAgainstSaved(document.profile, state),
          undo: freeze([...state.undo, documentSnapshot(state)].slice(-HISTORY_LIMIT)),
          redo: freeze(state.redo.slice(0, -1)),
        });
      }
      case "MARK_SAVED":
        return replaceState(state, {savedProfile: state.profile, dirty: false});
      default:
        throw new RangeError(`Unknown hub keymap transition ${action.type}.`);
    }
  }

  return Object.freeze({
    createHubKeymapState,
    reduceHubKeymapState,
  });
});
