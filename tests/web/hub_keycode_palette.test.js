"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  buildQmkPalette,
  describeQmkKeycode,
  filterQmkPalette,
  parseRawQmkCode,
} = require(path.join(
  __dirname,
  "../../am_configurator/web/hub_keycode_palette.js",
));

test("the portable palette exposes every approved category", () => {
  const palette = buildQmkPalette({layerCount: 3, macroSlots: 2});

  assert.deepEqual(
    palette.map(category => category.id),
    ["basic", "modifiers", "function-navigation", "keypad", "layers", "macros"],
  );
  assert.ok(palette.every(category => category.options.length > 0));
  assert.ok(palette.find(category => category.id === "basic").options.some(option => option.key === "KC_A" && option.code === 0x0004));
  assert.ok(palette.find(category => category.id === "modifiers").options.some(option => option.key === "KC_LEFT_CTRL" && option.code === 0x00e0));
  assert.ok(palette.find(category => category.id === "function-navigation").options.some(option => option.key === "KC_F24" && option.code === 0x0073));
  assert.ok(palette.find(category => category.id === "keypad").options.some(option => option.key === "KC_KP_0" && option.code === 0x0062));
});

test("layer controls and macros are bounded by target capabilities", () => {
  const palette = buildQmkPalette({layerCount: 2, macroSlots: 3});
  const layers = palette.find(category => category.id === "layers").options;
  const macros = palette.find(category => category.id === "macros").options;

  assert.ok(layers.some(option => option.key === "MO(1)" && option.code === 0x5221));
  assert.ok(!layers.some(option => option.key.endsWith("(2)")));
  assert.deepEqual(macros.map(option => option.code), [0x7700, 0x7701, 0x7702]);
  assert.throws(() => buildQmkPalette({layerCount: 33, macroSlots: 0}), /layer/i);
  assert.throws(() => buildQmkPalette({layerCount: 1, macroSlots: 129}), /macro/i);
});

test("layer controls follow canonical target indexes without inventing gaps", () => {
  const palette = buildQmkPalette({layerIndexes: [0, 2], macroSlots: 0});
  const layers = palette.find(category => category.id === "layers").options;

  assert.ok(layers.some(option => option.key === "MO(2)" && option.code === 0x5222));
  assert.ok(!layers.some(option => option.key === "MO(1)"));
  assert.throws(() => buildQmkPalette({layerIndexes: [0, 0], macroSlots: 0}), /layer/i);
  assert.throws(() => buildQmkPalette({layerIndexes: [32], macroSlots: 0}), /layer/i);
});

test("a reported keycode spec filters entries introduced later", () => {
  const oldPalette = buildQmkPalette({layerCount: 1, macroSlots: 0, keycodeSpec: "0.0.2"});
  const currentPalette = buildQmkPalette({layerCount: 1, macroSlots: 0, keycodeSpec: "0.0.8"});
  const oldKeys = new Set(oldPalette.flatMap(category => category.options.map(option => option.key)));
  const currentKeys = new Set(currentPalette.flatMap(category => category.options.map(option => option.key)));

  assert.equal(oldKeys.has("QK_REPEAT_KEY"), false);
  assert.equal(oldKeys.has("QK_LAYER_LOCK"), false);
  assert.equal(currentKeys.has("QK_REPEAT_KEY"), true);
  assert.equal(currentKeys.has("QK_LAYER_LOCK"), true);
  assert.throws(() => buildQmkPalette({layerCount: 1, macroSlots: 0, keycodeSpec: "banana"}), /spec/i);
});

test("palette filtering searches friendly, technical, and raw labels", () => {
  const palette = buildQmkPalette({layerCount: 2, macroSlots: 1});

  assert.deepEqual(filterQmkPalette(palette, "left control").flatMap(category => category.options).map(option => option.key), ["KC_LEFT_CTRL"]);
  assert.deepEqual(filterQmkPalette(palette, "MO(1)").flatMap(category => category.options).map(option => option.key), ["MO(1)"]);
  assert.deepEqual(filterQmkPalette(palette, "0x7700").flatMap(category => category.options).map(option => option.key), ["QK_MACRO_0"]);
});

test("unknown and per-board 16-bit codes remain explicit and raw-editable", () => {
  const unknown = describeQmkKeycode(0x1234, {keycodeSpec: "0.0.8"});
  const keyboard = describeQmkKeycode(0x7e12, {keycodeSpec: "0.0.8"});
  const user = describeQmkKeycode(0x7f34, {keycodeSpec: "0.0.8"});

  assert.deepEqual(unknown, {label: "Unknown QMK keycode", technical: "0x1234", warning: null});
  assert.match(keyboard.warning, /keyboard-specific/i);
  assert.match(user.warning, /user-specific/i);
  assert.equal(parseRawQmkCode("0xABCD"), 0xabcd);
  assert.equal(parseRawQmkCode("0xffff"), 0xffff);
  assert.throws(() => parseRawQmkCode("ABCD"), /0x/i);
  assert.throws(() => parseRawQmkCode("0x10000"), /16-bit/i);
});
