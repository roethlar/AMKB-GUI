(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HubKeycodePalette = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Curated from the pinned QMK tables surveyed in
  // docs/design/2026-08-15-h0-keycode-capability-survey.md. This is a small
  // portable editor vocabulary, not a copy of a VIA or Vial GUI catalog.
  const CATEGORY_LABELS = Object.freeze({
    basic: "Basic & HID keys",
    modifiers: "Modifiers",
    "function-navigation": "Function & navigation",
    keypad: "Keypad",
    layers: "Layer controls",
    macros: "Macros",
  });
  const CATEGORY_ORDER = Object.freeze(Object.keys(CATEGORY_LABELS));

  function freeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    for (const child of Object.values(value)) freeze(child);
    return Object.freeze(value);
  }

  function hex(code) {
    return `0x${code.toString(16).toUpperCase().padStart(4, "0")}`;
  }

  function option(code, key, label, minSpec = "0.0.1") {
    return {code, key, label, minSpec};
  }

  function parseSpec(value) {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value !== "string" || !/^\d+\.\d+\.\d+$/.test(value)) {
      throw new TypeError("The reported QMK keycode spec is invalid.");
    }
    return value.split(".").map(Number);
  }

  function compareSpec(left, right) {
    for (let index = 0; index < 3; index += 1) {
      if (left[index] !== right[index]) return left[index] - right[index];
    }
    return 0;
  }

  function supported(optionValue, reportedSpec) {
    if (reportedSpec === null) return true;
    return compareSpec(optionValue.minSpec.split(".").map(Number), reportedSpec) <= 0;
  }

  function fixedOptions() {
    const basic = [
      option(0x0000, "KC_NO", "None"),
      option(0x0001, "KC_TRANSPARENT", "Transparent"),
    ];
    for (let index = 0; index < 26; index += 1) {
      const letter = String.fromCharCode(65 + index);
      basic.push(option(0x0004 + index, `KC_${letter}`, letter));
    }
    for (let index = 0; index < 10; index += 1) {
      const digit = String((index + 1) % 10);
      basic.push(option(0x001e + index, `KC_${digit}`, digit));
    }
    [
      [0x0028, "KC_ENTER", "Enter"],
      [0x0029, "KC_ESCAPE", "Escape"],
      [0x002a, "KC_BACKSPACE", "Backspace"],
      [0x002b, "KC_TAB", "Tab"],
      [0x002c, "KC_SPACE", "Space"],
      [0x002d, "KC_MINUS", "-"],
      [0x002e, "KC_EQUAL", "="],
      [0x002f, "KC_LEFT_BRACKET", "["],
      [0x0030, "KC_RIGHT_BRACKET", "]"],
      [0x0031, "KC_BACKSLASH", "Backslash"],
      [0x0032, "KC_NONUS_HASH", "Non-US #"],
      [0x0033, "KC_SEMICOLON", ";"],
      [0x0034, "KC_QUOTE", "'"],
      [0x0035, "KC_GRAVE", "`"],
      [0x0036, "KC_COMMA", ","],
      [0x0037, "KC_DOT", "."],
      [0x0038, "KC_SLASH", "/"],
      [0x0039, "KC_CAPS_LOCK", "Caps Lock"],
    ].forEach(values => basic.push(option(...values)));

    const modifiers = [
      option(0x00e0, "KC_LEFT_CTRL", "Left Control"),
      option(0x00e1, "KC_LEFT_SHIFT", "Left Shift"),
      option(0x00e2, "KC_LEFT_ALT", "Left Alt"),
      option(0x00e3, "KC_LEFT_GUI", "Left GUI"),
      option(0x00e4, "KC_RIGHT_CTRL", "Right Control"),
      option(0x00e5, "KC_RIGHT_SHIFT", "Right Shift"),
      option(0x00e6, "KC_RIGHT_ALT", "Right Alt"),
      option(0x00e7, "KC_RIGHT_GUI", "Right GUI"),
    ];

    const navigation = [];
    for (let index = 0; index < 12; index += 1) {
      navigation.push(option(0x003a + index, `KC_F${index + 1}`, `F${index + 1}`));
    }
    [
      [0x0046, "KC_PRINT_SCREEN", "Print Screen"],
      [0x0047, "KC_SCROLL_LOCK", "Scroll Lock"],
      [0x0048, "KC_PAUSE", "Pause"],
      [0x0049, "KC_INSERT", "Insert"],
      [0x004a, "KC_HOME", "Home"],
      [0x004b, "KC_PAGE_UP", "Page Up"],
      [0x004c, "KC_DELETE", "Delete"],
      [0x004d, "KC_END", "End"],
      [0x004e, "KC_PAGE_DOWN", "Page Down"],
      [0x004f, "KC_RIGHT", "Right"],
      [0x0050, "KC_LEFT", "Left"],
      [0x0051, "KC_DOWN", "Down"],
      [0x0052, "KC_UP", "Up"],
      [0x0065, "KC_APPLICATION", "Application"],
    ].forEach(values => navigation.push(option(...values)));
    for (let index = 0; index < 12; index += 1) {
      navigation.push(option(0x0068 + index, `KC_F${index + 13}`, `F${index + 13}`));
    }
    navigation.push(option(0x7c79, "QK_REPEAT_KEY", "Repeat", "0.0.3"));
    navigation.push(option(0x7c7a, "QK_ALT_REPEAT_KEY", "Alternate repeat", "0.0.3"));

    const keypad = [
      option(0x0053, "KC_NUM_LOCK", "Num Lock"),
      option(0x0054, "KC_KP_SLASH", "/"),
      option(0x0055, "KC_KP_ASTERISK", "*"),
      option(0x0056, "KC_KP_MINUS", "-"),
      option(0x0057, "KC_KP_PLUS", "+"),
      option(0x0058, "KC_KP_ENTER", "Enter"),
    ];
    for (let digit = 1; digit <= 9; digit += 1) {
      keypad.push(option(0x0058 + digit, `KC_KP_${digit}`, String(digit)));
    }
    keypad.push(option(0x0062, "KC_KP_0", "0"));
    keypad.push(option(0x0063, "KC_KP_DOT", "."));
    keypad.push(option(0x0067, "KC_KP_EQUAL", "="));

    return {basic, modifiers, "function-navigation": navigation, keypad};
  }

  function normalizeLayerIndexes(layerCount, layerIndexes) {
    if (layerIndexes !== undefined) {
      if (layerCount !== undefined) {
        throw new TypeError("Provide target QMK layer indexes or a layer count, not both.");
      }
      if (!Array.isArray(layerIndexes) || !layerIndexes.length || layerIndexes.length > 32
          || layerIndexes.some(index => !Number.isSafeInteger(index) || index < 0 || index > 31)
          || new Set(layerIndexes).size !== layerIndexes.length) {
        throw new RangeError("The target QMK layer indexes must be unique values between 0 and 31.");
      }
      return [...layerIndexes];
    }
    if (!Number.isSafeInteger(layerCount) || layerCount < 1 || layerCount > 32) {
      throw new RangeError("The target QMK layer count must be between 1 and 32.");
    }
    return Array.from({length: layerCount}, (_, index) => index);
  }

  function layerOptions(layerIndexes) {
    const result = [];
    const controls = [
      [0x5200, "TO", "Switch to"],
      [0x5220, "MO", "Hold layer"],
      [0x5240, "DF", "Set default"],
      [0x5260, "TG", "Toggle"],
      [0x5280, "OSL", "One-shot"],
      [0x52c0, "TT", "Tap-toggle"],
    ];
    for (const [base, key, label] of controls) {
      for (const layer of layerIndexes) {
        result.push(option(base + layer, `${key}(${layer})`, `${label} ${layer}`));
      }
    }
    result.push(option(0x7c7b, "QK_LAYER_LOCK", "Layer Lock", "0.0.6"));
    return result;
  }

  function macroOptions(macroSlots) {
    return Array.from({length: macroSlots}, (_, slot) =>
      option(0x7700 + slot, `QK_MACRO_${slot}`, `Macro ${slot}`));
  }

  function buildQmkPalette({layerCount, layerIndexes, macroSlots, keycodeSpec = null}) {
    const normalizedLayers = normalizeLayerIndexes(layerCount, layerIndexes);
    if (!Number.isSafeInteger(macroSlots) || macroSlots < 0 || macroSlots > 128) {
      throw new RangeError("The target QMK macro slot count must be between 0 and 128.");
    }
    const reportedSpec = parseSpec(keycodeSpec);
    const options = fixedOptions();
    options.layers = layerOptions(normalizedLayers);
    options.macros = macroOptions(macroSlots);
    return freeze(CATEGORY_ORDER.map(id => ({
      id,
      label: CATEGORY_LABELS[id],
      options: options[id].filter(value => supported(value, reportedSpec)).map(value => ({
        code: value.code,
        key: value.key,
        label: value.label,
        technical: hex(value.code),
      })),
    })));
  }

  function filterQmkPalette(palette, query) {
    if (!Array.isArray(palette)) throw new TypeError("The QMK palette is invalid.");
    const normalized = String(query || "").trim().toLocaleLowerCase();
    if (!normalized) return palette;
    return freeze(palette.map(category => ({
      ...category,
      options: category.options.filter(value =>
        `${value.label} ${value.key} ${value.technical}`.toLocaleLowerCase().includes(normalized)),
    })).filter(category => category.options.length));
  }

  function validateCode(code) {
    if (!Number.isSafeInteger(code) || code < 0 || code > 0xffff) {
      throw new RangeError("The QMK keycode must be an unsigned 16-bit integer.");
    }
  }

  function describeQmkKeycode(code, {palette = null, keycodeSpec = null} = {}) {
    validateCode(code);
    const source = palette || buildQmkPalette({layerCount: 32, macroSlots: 128, keycodeSpec});
    const known = source.flatMap(category => category.options).find(value => value.code === code);
    if (known) return {label: known.label, technical: known.key, warning: null};

    const reportedSpec = parseSpec(keycodeSpec);
    const modernRanges = reportedSpec === null || compareSpec(reportedSpec, [0, 0, 2]) >= 0;
    if (code >= 0x7e00 && code <= (modernRanges ? 0x7e3f : 0x7eff)) {
      return {
        label: "Keyboard-specific QMK keycode",
        technical: hex(code),
        warning: "This keyboard-specific code belongs to the source firmware. It is preserved exactly but never offered in the portable palette.",
      };
    }
    if (code >= (modernRanges ? 0x7e40 : 0x7f00) && code <= 0x7fff) {
      return {
        label: "User-specific QMK keycode",
        technical: hex(code),
        warning: "This user-specific code belongs to the source firmware. It is preserved exactly but never offered in the portable palette.",
      };
    }
    return {label: "Unknown QMK keycode", technical: hex(code), warning: null};
  }

  function parseRawQmkCode(value) {
    const normalized = String(value || "").trim();
    if (!/^0x[0-9a-f]{4}$/i.test(normalized)) {
      throw new TypeError("Enter one 16-bit QMK keycode as 0x followed by exactly four hexadecimal digits.");
    }
    return Number.parseInt(normalized.slice(2), 16);
  }

  return Object.freeze({
    buildQmkPalette,
    describeQmkKeycode,
    filterQmkPalette,
    parseRawQmkCode,
  });
});
