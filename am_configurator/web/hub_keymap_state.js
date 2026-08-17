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

  function dirtyAgainstSaved(profile, state) {
    return !sameProfile(profile, state.savedProfile);
  }

  function checkpoint(state, profile) {
    if (sameProfile(profile, state.profile)) return state;
    const undo = freeze([...state.undo, state.profile].slice(-HISTORY_LIMIT));
    return replaceState(state, {
      profile,
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
    return checkpoint(state, freeze(profile));
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
      case "REPLACE_PROFILE": {
        const profile = validateProfile(action.profile);
        if (profile.identity.ecosystem !== state.target.ecosystem) {
          throw new TypeError("The replacement hub profile does not match the target ecosystem.");
        }
        return checkpoint(state, profile);
      }
      case "UNDO": {
        if (!state.undo.length) return state;
        const profile = state.undo[state.undo.length - 1];
        return replaceState(state, {
          profile,
          dirty: dirtyAgainstSaved(profile, state),
          undo: freeze(state.undo.slice(0, -1)),
          redo: freeze([...state.redo, state.profile].slice(-HISTORY_LIMIT)),
        });
      }
      case "REDO": {
        if (!state.redo.length) return state;
        const profile = state.redo[state.redo.length - 1];
        return replaceState(state, {
          profile,
          dirty: dirtyAgainstSaved(profile, state),
          undo: freeze([...state.undo, state.profile].slice(-HISTORY_LIMIT)),
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
