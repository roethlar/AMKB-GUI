(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingTargets = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  function targets(values) {
    return Object.freeze(values.map(value => Object.freeze({...value})));
  }

  const DEVICE_TARGETS = Object.freeze({
    CB: targets([
      {key: "keyframes", label: "Switch LEDs"},
      {key: "frames", label: "Top display 40×5"},
    ]),
    ALICE: targets([
      {key: "keyframes", label: "Keys + center"},
    ]),
    "80": targets([
      {key: "keyframes", label: "Per-key"},
      {key: "spotlight_frames", label: "Edge lights"},
    ]),
    // Exactly the two tracks the Neon authors. The side zone is derived from
    // the head frames at transmit time and must never appear here: anything
    // listed becomes independently selectable, which would let a user author a
    // zone the device cannot receive.
    NEON: targets([
      {key: "axial", label: "Per-key"},
      {key: "head", label: "Head matrix 46×5"},
    ]),
  });

  // --- Per-family device specification ------------------------------------
  //
  // The browser's copy of `FamilySpec` in am_configurator/device_mapping.py,
  // which is the authority for these numbers. It is kept as a strict-JSON
  // literal so `tests/test_device_mapping.py` can parse it and assert the two
  // sides never drift: change device_mapping.py first, then mirror it here.
  //
  // `trackColors` holds only the tracks a family authors, matching that
  // family's `_LAYOUTS` entry; `sharedTrackColors` covers a track a family does
  // not author, exactly as `_SHARED_TRACK_COLORS` does on the Python side.
  const SPEC_SOURCE = `{
    "sharedTrackColors": {"frames": 200, "keyframes": 90, "spotlight_frames": 24},
    "unknownFrameCap": 256,
    "families": {
      "CB": {"transport": "serial", "frameCap": 80, "macroTracks": 32, "macroEvents": 200, "keysPerLayer": 200,
             "trackColors": {"keyframes": 90, "frames": 200}},
      "80": {"transport": "serial", "frameCap": 200, "macroTracks": 32, "macroEvents": 200, "keysPerLayer": 200,
             "trackColors": {"keyframes": 90, "spotlight_frames": 24}},
      "ALICE": {"transport": "serial", "frameCap": 186, "macroTracks": 32, "macroEvents": 200, "keysPerLayer": 200,
                "trackColors": {"keyframes": 90}},
      "NEON": {"transport": "hid", "frameCap": 256, "macroTracks": 16, "macroEvents": 6677, "keysPerLayer": 90,
               "macroBufferBytes": 6677,
               "trackColors": {"axial": 89, "head": 230}}
    }
  }`;

  const SPEC_DATA = JSON.parse(SPEC_SOURCE);

  const SHARED_TRACK_COLORS = Object.freeze({...SPEC_DATA.sharedTrackColors});

  function freezeSpec(model, spec) {
    return Object.freeze({
      model,
      transport: spec.transport,
      frameCap: spec.frameCap,
      macroTracks: spec.macroTracks,
      macroEvents: spec.macroEvents,
      // Dropping a field here silently hides a real device limit from the
      // editor, which is how macroBufferBytes went missing (finding n567-9).
      macroBufferBytes: spec.macroBufferBytes || 0,
      keysPerLayer: spec.keysPerLayer,
      trackColors: Object.freeze({...spec.trackColors}),
      authoredTracks: Object.freeze(Object.keys(spec.trackColors)),
    });
  }

  const FAMILY_SPECS = Object.freeze(Object.fromEntries(
    Object.entries(SPEC_DATA.families).map(([model, spec]) => [model, freezeSpec(model, spec)]),
  ));

  // Mirrors `_UNKNOWN_FAMILY_SPEC`: a config naming a product this build does
  // not recognise is still editable against the shared limits rather than
  // rejected. This carries no geometry — `supportedFamily` is what refuses to
  // hand an unknown device another device's key map.
  const UNKNOWN_FAMILY_SPEC = freezeSpec("", {
    transport: "serial",
    frameCap: SPEC_DATA.unknownFrameCap,
    macroTracks: 32,
    macroEvents: 200,
    trackColors: {},
  });

  // Mirrors `led_model`, except that an unrecognised product yields its own
  // uppercased identifier rather than raising, so callers can show it.
  function productFamily(value) {
    const id = String(value || "").toUpperCase();
    if (id === "NEON" || id === "NEON80" || id === "AM NEON 80") return "NEON";
    if (id === "80" || id === "AM21") return "80";
    if (id === "ALICE") return "ALICE";
    if (id.startsWith("CB")) return "CB";
    return id;
  }

  function projectVialKeyLayout(device) {
    const source = device?.key_layout;
    if (!Array.isArray(source) || !source.length) return null;
    const seen = new Set();
    const keys = [];
    for (const item of source) {
      const index = Number(item?.index);
      const x = Number(item?.x);
      const y = Number(item?.y);
      const width = Number(item?.width);
      const height = Number(item?.height);
      const rotation = Number(item?.rotation || 0);
      if (
        !Number.isInteger(index) || index < 0 || seen.has(index)
        || ![x, y, width, height, rotation].every(Number.isFinite)
        || x < 0 || y < 0 || width <= 0 || height <= 0
        || x + width > 100.001 || y + height > 100.001
        || Math.abs(rotation) > 180
      ) {
        return null;
      }
      seen.add(index);
      keys.push([index, x, y, width, rotation, height]);
    }
    return keys;
  }

  function neonPaletteAssignment(code, macroTracks = 16) {
    const normalized = String(code || "").toUpperCase();
    if (!/^#[0-9A-F]{8}$/.test(normalized)) return false;
    const modifier = Number.parseInt(normalized.slice(1, 3), 16);
    const page = Number.parseInt(normalized.slice(3, 5), 16);
    const usage = Number.parseInt(normalized.slice(5, 9), 16);
    if (modifier === 0 && page === 0 && usage === 0) return true;
    if (page === 0x07 && usage > 0 && usage <= 0xFF) {
      const left = modifier & 0x0F;
      const right = (modifier & 0xF0) >> 4;
      return !(left && right);
    }
    return (
      modifier === 0
      && page === 0x95
      && (usage >> 8) === 0x15
      && (usage & 0xFF) < macroTracks
    );
  }

  function filterAssignmentOptions(product, options) {
    const values = Array.isArray(options) ? options : [];
    if (productFamily(product) !== "NEON") return values.slice();
    const macroTracks = FAMILY_SPECS.NEON.macroTracks;
    return values.filter(option => neonPaletteAssignment(option?.code, macroTracks));
  }

  // The family key this build actually supports, or null. A null result must
  // never be replaced with a default family: substituting one device's LED
  // geometry for another is how wrong pixel data reaches a keyboard.
  function supportedFamily(value) {
    const family = productFamily(value);
    return Object.prototype.hasOwnProperty.call(FAMILY_SPECS, family) ? family : null;
  }

  // Mirrors `family_spec`: null for an unknown family, never a substitute.
  function familySpec(value) {
    const family = supportedFamily(value);
    return family === null ? null : FAMILY_SPECS[family];
  }

  // Mirrors `spec_for_product`: never null, so limit checks keep working on a
  // configuration whose product this build does not recognise.
  function specForProduct(value) {
    return familySpec(value) || UNKNOWN_FAMILY_SPEC;
  }

  // Mirrors `FamilySpec.track_colors`: the family's own count where it authors
  // the track, otherwise the shared count. Null for a track no one sizes.
  function trackColorCount(spec, field) {
    const key = String(field || "");
    if (spec && Object.prototype.hasOwnProperty.call(spec.trackColors, key)) {
      return spec.trackColors[key];
    }
    if (Object.prototype.hasOwnProperty.call(SHARED_TRACK_COLORS, key)) {
      return SHARED_TRACK_COLORS[key];
    }
    return null;
  }

  function renderTargetControls(host, availableTargets, selectedTarget, locked, onSelect) {
    if (!host || typeof host.replaceChildren !== "function" || !host.ownerDocument) {
      throw new TypeError("A target-control host is required.");
    }
    const document = host.ownerDocument;
    const choices = Array.isArray(availableTargets) ? availableTargets : [];
    if (!choices.length) {
      const empty = document.createElement("button");
      empty.type = "button";
      empty.disabled = true;
      empty.textContent = "Open document";
      host.replaceChildren(empty);
      return;
    }
    const buttons = choices.map(target => {
      const key = String(target.key || "");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.lightingTarget = key;
      button.textContent = String(target.label || key);
      button.className = key === selectedTarget ? "active" : "";
      button.setAttribute("aria-pressed", String(key === selectedTarget));
      button.disabled = Boolean(locked);
      button.addEventListener("click", () => {
        if (!button.disabled && typeof onSelect === "function") onSelect(key);
      });
      return button;
    });
    host.replaceChildren(...buttons);
  }

  return Object.freeze({
    DEVICE_TARGETS,
    FAMILY_SPECS,
    SHARED_TRACK_COLORS,
    SPEC_SOURCE,
    UNKNOWN_FAMILY_SPEC,
    familySpec,
    filterAssignmentOptions,
    neonPaletteAssignment,
    productFamily,
    projectVialKeyLayout,
    renderTargetControls,
    specForProduct,
    supportedFamily,
    trackColorCount,
  });
});
