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

  // Firmware-defined Neon controls from custom_keycodes_t. Keep this list
  // device-specific: these raw QMK values are not portable AM usage-page
  // assignments, and exposing arbitrary passthrough values would defeat the
  // assignment gate.
  const NEON_LIGHTING_CONTROLS = targets([
    {label: "Next effect", code: "#00FF5DB2", category: "Under-key lighting"},
    {label: "Previous effect", code: "#00FF5DB3", category: "Under-key lighting"},
    {label: "Speed +", code: "#00FF5DB4", category: "Under-key lighting"},
    {label: "Speed −", code: "#00FF5DB5", category: "Under-key lighting"},
    {label: "Brightness +", code: "#00FF5DB6", category: "Under-key lighting"},
    {label: "Brightness −", code: "#00FF5DB7", category: "Under-key lighting"},
    {label: "Next effect", code: "#00FF5DB8", category: "Top display lighting"},
    {label: "Previous effect", code: "#00FF5DB9", category: "Top display lighting"},
    {label: "Speed +", code: "#00FF5DBA", category: "Top display lighting"},
    {label: "Speed −", code: "#00FF5DBB", category: "Top display lighting"},
    {label: "Brightness +", code: "#00FF5DBC", category: "Top display lighting"},
    {label: "Brightness −", code: "#00FF5DBD", category: "Top display lighting"},
    {label: "Power", code: "#00FF5DBE", category: "Top display lighting"},
    {label: "Power", code: "#00FF5DBF", category: "Under-key lighting"},
  ]);
  const NEON_LIGHTING_CONTROL_CODES = new Set(
    NEON_LIGHTING_CONTROLS.map(option => option.code),
  );

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

  function selectVialLayoutDevice(product, devices, loadedDeviceKey = null) {
    if (productFamily(product) !== "NEON") return null;
    const candidates = (Array.isArray(devices) ? devices : []).filter(device => (
      productFamily(device?.product_id) === "NEON"
      && projectVialKeyLayout(device)
    ));
    const preferred = candidates.find(device => (
      `${String(device?.transport || "")}:${String(device?.address || "")}`
      === String(loadedDeviceKey || "")
    ));
    if (preferred) return preferred;
    if (loadedDeviceKey) return null;
    return candidates.length === 1 ? candidates[0] : null;
  }

  function projectVialLedLayout(device, target) {
    const keys = projectVialKeyLayout(device);
    const width = Number(target?.width);
    const height = Number(target?.height);
    const pixelCount = Number(target?.pixels ?? target?.count);
    const map = target?.map;
    if (
      !keys
      || !Number.isInteger(width) || width <= 0
      || !Number.isInteger(height) || height <= 0
      || !Array.isArray(map) || map.length !== width * height
    ) {
      return null;
    }

    const keyRows = [];
    for (const key of [...keys].sort((a, b) => a[2] - b[2] || a[1] - b[1])) {
      let row = keyRows.find(candidate => Math.abs(candidate.y - key[2]) < 0.001);
      if (!row) {
        row = {y: key[2], keys: []};
        keyRows.push(row);
      }
      row.keys.push(key);
    }
    keyRows.sort((a, b) => a.y - b.y);
    if (keyRows.length !== height) return null;

    const projected = [];
    const seenPixels = new Set();
    for (let rowIndex = 0; rowIndex < height; rowIndex += 1) {
      const rowKeys = [...keyRows[rowIndex].keys].sort((a, b) => a[1] - b[1]);
      const rowPixels = map
        .slice(rowIndex * width, (rowIndex + 1) * width)
        .map((index, x) => ({index: Number(index), x}))
        .filter(item => Number.isInteger(item.index) && item.index >= 0);
      if (rowPixels.length < rowKeys.length) return null;

      const ledsPerKey = Array(rowKeys.length).fill(1);
      let extras = rowPixels.length - rowKeys.length;
      if (extras) {
        const widest = rowKeys.reduce(
          (best, key, index) => key[3] > rowKeys[best][3] ? index : best,
          0,
        );
        while (extras > 0) {
          ledsPerKey[widest] += 1;
          extras -= 1;
        }
      }

      let pixelOffset = 0;
      for (let keyOffset = 0; keyOffset < rowKeys.length; keyOffset += 1) {
        const key = rowKeys[keyOffset];
        const groupCount = ledsPerKey[keyOffset];
        const segmentWidth = key[3] / groupCount;
        for (let groupPosition = 0; groupPosition < groupCount; groupPosition += 1) {
          const pixel = rowPixels[pixelOffset + groupPosition];
          if (!pixel || seenPixels.has(pixel.index)) return null;
          seenPixels.add(pixel.index);
          projected.push({
            index: pixel.index,
            keyIndex: key[0],
            x: key[1] + segmentWidth * groupPosition,
            y: key[2],
            w: segmentWidth,
            h: key[5],
            rotation: key[4],
            groupPosition,
            groupCount,
            showLabel: groupCount === 1 || groupPosition === Math.floor(groupCount / 2),
          });
        }
        pixelOffset += groupCount;
      }
      if (pixelOffset !== rowPixels.length) return null;
    }

    if (
      seenPixels.size !== projected.length
      || (Number.isInteger(pixelCount) && pixelCount >= 0 && projected.length !== pixelCount)
    ) {
      return null;
    }
    return projected;
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
    if (
      modifier === 0
      && page === 0xFF
      && NEON_LIGHTING_CONTROL_CODES.has(normalized)
    ) {
      return true;
    }
    return (
      modifier === 0
      && page === 0x95
      && (usage >> 8) === 0x15
      && (usage & 0xFF) < macroTracks
    );
  }

  function filterAssignmentOptions(product, options, reportedMacroTracks = null) {
    const values = Array.isArray(options) ? options : [];
    if (productFamily(product) !== "NEON") return values.slice();
    const macroTracks = Number.isInteger(reportedMacroTracks) && reportedMacroTracks >= 0
      ? reportedMacroTracks
      : FAMILY_SPECS.NEON.macroTracks;
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

  function withDeviceMacroLimits(spec, device) {
    if (!spec || spec.model !== "NEON") return spec;
    const macroTracks = Number(device?.macro_count);
    const macroBufferBytes = Number(device?.macro_buffer_bytes);
    if (
      !Number.isInteger(macroTracks) || macroTracks < 0 || macroTracks > 0xFF
      || !Number.isInteger(macroBufferBytes) || macroBufferBytes < 0
      || macroBufferBytes > 0xFFFF
    ) {
      return spec;
    }
    return Object.freeze({...spec, macroTracks, macroBufferBytes});
  }

  function vialMacroBufferUsage(macros, macroTracks) {
    const tracks = Number(macroTracks);
    if (!Number.isInteger(tracks) || tracks < 0) return 0;
    let bytes = tracks; // Every slot has a one-byte terminator, including empty slots.
    for (const macro of Array.isArray(macros) ? macros : []) {
      const events = Array.isArray(macro?.layer_key) ? macro.layer_key : [];
      const delays = Array.isArray(macro?.intvel_ms) ? macro.intvel_ms : [];
      for (let index = 0; index < events.length; index += 1) {
        bytes += 3; // VIA sequence prefix, action, and one-byte HID usage.
        const delay = Number(delays[index] ?? 0);
        if (Number.isFinite(delay) && delay !== 0) bytes += 4;
      }
    }
    return bytes;
  }

  function macroCapacityStatus(spec, macros) {
    const entries = Array.isArray(macros) ? macros : [];
    const tracks = Number(spec?.macroTracks) || 0;
    if (spec?.model === "NEON" && Number(spec.macroBufferBytes) >= 0) {
      const used = vialMacroBufferUsage(entries, tracks);
      const limit = Number(spec.macroBufferBytes);
      return {
        used,
        limit,
        unit: "bytes",
        tracks,
        fits: entries.length <= tracks && used <= limit,
      };
    }
    const used = entries.reduce(
      (sum, macro) => sum + (Array.isArray(macro?.layer_key) ? macro.layer_key.length : 0),
      0,
    );
    const limit = Number(spec?.macroEvents) || 0;
    return {
      used,
      limit,
      unit: "events",
      tracks,
      fits: entries.length <= tracks && used <= limit,
    };
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
    NEON_LIGHTING_CONTROLS,
    SHARED_TRACK_COLORS,
    SPEC_SOURCE,
    UNKNOWN_FAMILY_SPEC,
    familySpec,
    filterAssignmentOptions,
    macroCapacityStatus,
    neonPaletteAssignment,
    productFamily,
    projectVialKeyLayout,
    projectVialLedLayout,
    renderTargetControls,
    selectVialLayoutDevice,
    specForProduct,
    supportedFamily,
    trackColorCount,
    vialMacroBufferUsage,
    withDeviceMacroLimits,
  });
});
