"use strict";

const queryToken = new URLSearchParams(location.search).get("token") || "";
if (queryToken) sessionStorage.setItem("am-configurator-token", queryToken);
const token = queryToken || sessionStorage.getItem("am-configurator-token") || "";
if (queryToken) history.replaceState({}, "", location.pathname);

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clone = value => JSON.parse(JSON.stringify(value));
const esc = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

const state = {
  config: null,
  fileName: "AM-config.json",
  dirty: false,
  screen: "keymap",
  layer: 0,
  selected: null,
  macro: 0,
  recording: false,
  recordLast: 0,
  ledSlot: 5,
  ledTarget: "keyframes",
  ledFrame: 0,
  ledColor: "#8358ff",
  gifResample: "box",
  relicGifEdges: true,
  playing: false,
  playTimer: null,
  undo: [],
  redo: [],
  devices: [],
  selectedPort: null,
  loadedPort: null,
  deviceDocuments: new Map(),
  pendingWrite: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", "X-AM-Token": token, ...(options.headers || {})},
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    Object.assign(error, data, {status:response.status});
    throw error;
  }
  return data;
}

function toast(title, message = "", type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = message;
  node.append(strong, span);
  $("#toast-region").append(node);
  setTimeout(() => node.remove(), type === "error" ? 6500 : 3800);
}

function productId() {
  return state.config?.product_info?.product_id || "—";
}

function productFamily(value) {
  const id = String(value || "").toUpperCase();
  if (id === "80" || id === "AM21") return "80";
  if (id === "ALICE") return "ALICE";
  if (id.startsWith("CB")) return "CB";
  return id;
}

function sameProductFamily(left, right) {
  return Boolean(left && right && productFamily(left) === productFamily(right));
}

function pageData(config = state.config) {
  return Array.isArray(config?.page_data) ? config.page_data : [];
}

function layers() {
  return state.config?.key_layer?.layer_data || [];
}

function macros() {
  if (!Array.isArray(state.config?.macro_key)) state.config.macro_key = [];
  return state.config.macro_key;
}

function cleanFileName(name) {
  const base = String(name || "AM-config.json").replace(/-KEY(?=\.json$)/i, "");
  return base.toLowerCase().endsWith(".json") ? base : `${base}.json`;
}

function markDirty(value = true) {
  state.dirty = value;
  $("#dirty-dot").classList.toggle("visible", value);
}

function pushUndo() {
  if (!state.config) return;
  state.undo.push(JSON.stringify(state.config));
  if (state.undo.length > 30) state.undo.shift();
  state.redo.length = 0;
  updateHistoryButtons();
}

function mutate(fn, rerender = true) {
  pushUndo();
  fn();
  markDirty();
  updateMeta();
  if (rerender) renderScreen();
}

function undo() {
  if (!state.undo.length || !state.config) return;
  state.redo.push(JSON.stringify(state.config));
  state.config = JSON.parse(state.undo.pop());
  markDirty();
  updateMeta();
  renderScreen();
}

function redo() {
  if (!state.redo.length || !state.config) return;
  state.undo.push(JSON.stringify(state.config));
  state.config = JSON.parse(state.redo.pop());
  markDirty();
  updateMeta();
  renderScreen();
}

function updateHistoryButtons() {
  $("#undo-button").disabled = !state.undo.length;
  $("#redo-button").disabled = !state.redo.length;
}

function updateMeta() {
  $("#file-name").textContent = state.config ? state.fileName : "No configuration open";
  const product = $("#product-pill");
  product.textContent = state.config ? productId() : "—";
  product.classList.toggle("muted", !state.config);
  $("#nav-layers").textContent = state.config ? String(layers().length) : "—";
  $("#nav-macros").textContent = state.config ? String((state.config.macro_key || []).length) : "—";
  $("#nav-leds").textContent = state.config ? (pageData().length ? "3" : "—") : "—";
  $("#save-button").disabled = !state.config;
  $("#merge-button").disabled = !state.config;
  $("#validate-button").disabled = !state.config;
  updateHistoryButtons();
  updateDeviceActions();
}

function mergeConfigs(configs) {
  if (!configs.length) return null;
  const ledSources = configs.filter(config => Array.isArray(config.page_data) && config.page_data.length);
  const keyOnly = configs.filter(config => config.key_layer && (!config.page_data || !config.page_data.length));
  const keySources = keyOnly.length ? keyOnly : configs.filter(config => config.key_layer);
  const base = clone((ledSources.length ? ledSources : keySources.length ? keySources : configs).at(-1));
  for (const config of configs) {
    for (const [key, value] of Object.entries(config)) if (!(key in base)) base[key] = clone(value);
  }
  if (ledSources.length) {
    const led = ledSources.at(-1);
    base.page_data = clone(led.page_data);
    base.page_num = Number(led.page_num ?? led.page_data.length);
  }
  if (keySources.length) {
    const keyConfig = keySources.at(-1);
    const fields = ["key_layer","tab_key","tab_key_num","macro_key","MACRO_key","MACRO_key_num","Fn_key","Fn_key_num","swap_key","swap_key_num","exchange_key","exchange_num"];
    for (const field of fields) if (field in keyConfig) base[field] = clone(keyConfig[field]);
    if (keyConfig.product_info) base.product_info = clone(keyConfig.product_info);
  }
  return base;
}

async function readFiles(input, merge) {
  const files = [...input.files];
  input.value = "";
  if (!files.length) return;
  try {
    const configs = await Promise.all(files.map(async file => {
      const parsed = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${file.name} is not a configuration object.`);
      return parsed;
    }));
    const combined = merge && state.config ? mergeConfigs([state.config, ...configs]) : mergeConfigs(configs);
    if (!combined?.key_layer) throw new Error("No key_layer was found in the selected JSON.");
    if (!merge) {
      stashDeviceDocument();
      state.loadedPort = null;
    }
    if (merge && state.config) pushUndo();
    state.config = combined;
    state.fileName = cleanFileName(files[0].name);
    if (!merge) resetDocumentView();
    else state.ledFrame = 0;
    state.undo = [];
    state.redo = [];
    markDirty(merge);
    updateMeta();
    render();
    toast(merge ? "Configurations merged" : "Configuration opened", `${productId()} · ${layers().length} layers · ${(state.config.macro_key || []).length} macros`, "success");
  } catch (error) {
    toast("Could not open JSON", error.message, "error");
  }
}

function saveConfig() {
  if (!state.config) return;
  const output = clone(state.config);
  output.macro_key = (output.macro_key || []).map(macro => ({
    ...macro,
    original_key: String(macro.original_key).toUpperCase(),
    layer_key: (macro.layer_key || []).map(code => String(code).toUpperCase()),
    intvel_ms: Array.from({length:(macro.layer_key || []).length},(_,index)=>Number(macro.intvel_ms?.[index]??0)),
  }));
  output.page_num = (output.page_data || []).length;
  const blob = new Blob([JSON.stringify(output, null, 2) + "\n"], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = cleanFileName(state.fileName);
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  markDirty(false);
  toast("JSON saved", link.download, "success");
}

// Physical geometry transcribed from Angry Miao's public configurator.
const RELIC_LAYOUT = [
  [0,0,0],[1,7,0],[2,12.5,0],[3,18,0],[4,23.6,0],[5,30.5,0],[6,36.1,0],[7,41.6,0],[8,47.2,0],[9,54.2,0],[10,59.7,0],[11,65.3,0],[12,70.8,0],[13,77.7,0],[14,84.7,0],[89,90.2,0],[88,95.8,0],
  [25,0,20.5],[26,5.6,20.5],[27,11.1,20.5],[28,16.7,20.5],[29,22.2,20.5],[30,27.7,20.5],[31,33.3,20.5],[32,38.8,20.5],[33,44.4,20.5],[34,50,20.5],[35,55.5,20.5],[36,61,20.5],[37,66.6,20.5],[38,72.5,20.5,9],[39,84.7,20.5],[114,90.2,20.5],[113,95.8,20.5],
  [50,0,36.3,6.2],[51,8.3,36.3],[52,14,36.3],[53,19.4,36.3],[54,24.9,36.3],[55,30.5,36.3],[56,36,36.3],[57,41.6,36.3],[58,47.2,36.3],[59,52.7,36.3],[60,58.2,36.3],[61,63.8,36.3],[62,69.4,36.3],[63,75,36.3,6.2],[64,84.7,36.3],[139,90.2,36.3],[112,95.8,36.3],
  [75,0,52.7,8],[76,9.8,52.7],[77,15.3,52.7],[78,20.9,52.7],[79,26.4,52.7],[80,31.9,52.7],[81,37.5,52.7],[82,43,52.7],[83,48.6,52.7],[84,54.1,52.7],[85,59.7,52.7],[86,65.3,52.7],[87,70.8,52.7,10.2],
  [100,0,69,10.5],[101,12.5,69],[102,18.1,69],[103,23.6,69],[104,29.2,69],[105,34.7,69],[106,40.2,69],[107,45.7,69],[108,51.3,69],[109,56.9,69],[110,62.5,69],[111,68.1,69,13.2],[137,90.2,69],
  [125,0,85,6.2],[126,8.3,85],[127,13.8,85,6.2],[128,22.2,85,37],[135,61.1,85,6.2],[136,69.4,85],[138,75,85,6.2],[133,84.7,85],[132,90.2,85],[131,95.8,85],
];

const AFA_LAYOUT = [
  [0,7.1,10.7],[1,12.4,12],[2,16.7,12],[3,21,10.4],[4,25.8,12.8,3.8,12],[5,30.1,15.8,3.8,12],[6,34.4,18.4,3.8,12],[31,38.8,21,3.8,12],[7,59.5,19.4,3.8,-12],[8,63.9,16.8,3.8,-12],[9,68.2,14.1,3.8,-12],[10,72.6,11.2,3.8,-12],[11,77.3,10.2],[12,81.6,11.6],[13,86,11.6,7],
  [25,6.4,23.3],[26,11.7,24.8,5],[27,18.1,24.8],[28,22.8,24.4,3.8,12],[29,27.1,27,3.8,12],[30,31.4,29.6,3.8,12],[56,35.8,32.5,3.8,12],[57,58.2,33.5,3.8,-12],[32,62.5,30.9,3.8,-12],[33,66.8,28.1,3.8,-12],[34,71.2,25.4,3.8,-12],[35,75.9,24],[36,80.2,24.7],[37,84.6,24.7],[38,88.9,24.7,5],
  [50,5.6,36.4],[51,10.8,37.6,6],[52,18.3,37.6],[53,23.1,37.8,3.8,12],[54,27.3,40.5,3.8,12],[55,31.6,43.2,3.8,12],[81,35.9,45.7,3.8,12],[82,60.2,45.8,3.8,-12],[58,64.6,43,3.8,-12],[59,68.9,40.2,3.8,-12],[60,73.1,37.4,3.8,-12],[61,77.8,37.3],[62,82.2,37.7],[63,86.6,37.7,8],
  [75,4.6,48.8],[76,10,50.3,8],[77,19.5,50.3],[78,24.3,51.4,3.8,12],[79,28.5,54.5,3.8,12],[80,32.8,57.2,3.8,12],[106,37.1,59.7,3.8,12],[107,58.9,59.6,3.8,-12],[108,63.4,56.7,3.8,-12],[83,67.7,53.8,3.8,-12],[84,71.9,51,3.8,-12],[85,76.7,50.2],[86,81,50.2],[87,85.4,50.2],[88,89.8,50.2,6],
  [101,9.9,63.3,4],[102,15.3,63.3,4],[103,25.5,65.7,4,12],[105,31,71,8,12],[109,60.1,70.2,10.5,-12],[110,71.8,64,4,-12],[111,81.1,63.2],[112,85.5,63.2],[113,89.8,63.2],
];

// AFA's firmware LED indexes are not its key-matrix indexes.  Pair Angry
// Miao's LED ordering with the already-verified Alice key geometry so the
// lighting editor shows the actual key under each LED.  The final four LEDs
// sit beneath the glass center cover rather than beneath switches.
const AFA_KEY_LED_INDICES = [
  0,1,2,3,4,5,6,20,7,8,9,10,11,12,13,
  14,15,16,17,18,19,34,35,21,22,23,24,25,26,27,
  28,29,30,31,32,33,48,49,36,37,38,39,40,41,
  42,43,44,45,46,47,62,63,64,50,51,52,53,54,55,
  57,58,59,61,65,66,67,68,69,
];
const AFA_LED_LAYOUT = AFA_LAYOUT.map(([keyIndex,x,y,w=4.8,rotation=0], position) => ({
  index:AFA_KEY_LED_INDICES[position], keyIndex, x, y, w, rotation,
})).concat([
  {index:70,keyIndex:null,x:50.7,y:80.2,w:4.2,rotation:0,label:"C1"},
  {index:71,keyIndex:null,x:50.7,y:11.2,w:4.2,rotation:0,label:"C2"},
  {index:72,keyIndex:null,x:45.5,y:11.2,w:4.2,rotation:0,label:"C3"},
  {index:73,keyIndex:null,x:45.5,y:80.2,w:4.2,rotation:0,label:"C4"},
]);

// Angry Miao's image-converter rasters. Values are firmware LED indexes;
// -1 cells are physical gaps. The 90-color storage shape is not interchangeable
// between models even when the wire frame length is the same.
const CB_LED_MAP = [
  0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,
  15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,
  30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,
  45,46,47,48,49,50,51,52,53,54,55,56,-1,58,59,
  60,62,63,64,65,66,67,68,69,70,71,-1,72,73,-1,
  75,76,77,79,-1,80,-1,-1,81,85,86,-1,87,88,89,
];
// CyberBoard's 40×5 display is serialized column-first: index = x*5 + y.
// This maps each visible row-major grid position back to its firmware index.
const CB_DISPLAY_MAP = Array.from({length:200},(_,sourceIndex)=>(sourceIndex%40)*5+Math.floor(sourceIndex/40));
const AFA_LED_MAP = [
  0,1,2,3,4,5,6,20,7,8,9,10,11,12,-1,13,
  14,15,-1,16,17,18,19,34,35,21,22,23,24,25,26,27,
  28,29,-1,30,31,32,33,48,49,36,37,38,39,40,-1,41,
  42,43,-1,44,45,46,47,62,63,64,50,51,52,53,54,55,
  56,57,58,-1,59,60,61,73,70,65,-1,66,-1,67,68,69,
];
const RELIC_LED_MAP = [
  0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,59,58,
  15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,74,73,
  30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,89,72,
  45,46,47,48,49,50,51,52,53,54,55,56,-1,57,-1,-1,-1,
  60,-1,61,62,63,64,65,66,67,68,69,70,-1,71,-1,87,-1,
  75,76,77,78,-1,-1,79,-1,-1,80,-1,85,86,88,83,82,81,
];

const LED_MODELS = {
  CB: {
    name:"CyberBoard", keyMap:CB_LED_MAP, displayMap:CB_DISPLAY_MAP, keyColumns:15, keyRaster:"15×6",
    targets:[{key:"keyframes",label:"Switch LEDs"},{key:"frames",label:"Top display 40×5"}],
  },
  ALICE: {
    name:"AFA", keyMap:AFA_LED_MAP, keyColumns:16, keyRaster:"16×5", physicalLayout:AFA_LED_LAYOUT,
    targets:[{key:"keyframes",label:"Keys + center"}],
  },
  "80": {
    name:"Relic 80", keyMap:RELIC_LED_MAP, keyColumns:17, keyRaster:"18×7",
    targets:[{key:"keyframes",label:"Per-key"},{key:"spotlight_frames",label:"Edge lights"}],
  },
};
const LED_SPEEDS = [255,240,224,208,192,176,160,146,132,118,100,90,76,62,48,34];

function firmwareLedSpeed(value) {
  const duration=Math.max(1,Number(value)||90);
  return LED_SPEEDS.reduce((best,speed)=>Math.abs(speed-duration)<Math.abs(best-duration)?speed:best,LED_SPEEDS[0]);
}

function activeLedModel() {
  const id=productFamily(productId());
  if(id==="80")return LED_MODELS["80"];
  if(id==="ALICE")return LED_MODELS.ALICE;
  return LED_MODELS.CB;
}

const HID_NAMES = {};
for (let i = 0; i < 26; i++) HID_NAMES[0x04 + i] = String.fromCharCode(65 + i);
for (let i = 0; i < 10; i++) HID_NAMES[0x1e + i] = String((i + 1) % 10);
for (let i = 0; i < 12; i++) HID_NAMES[0x3a + i] = `F${i + 1}`;
HID_NAMES[0x68] = "F13";
Object.assign(HID_NAMES, {0x28:"Enter",0x29:"Esc",0x2a:"Backspace",0x2b:"Tab",0x2c:"Space",0x2d:"−",0x2e:"=",0x2f:"[",0x30:"]",0x31:"\\",0x33:";",0x34:"'",0x35:"`",0x36:",",0x37:".",0x38:"/",0x39:"Caps",0x46:"PrtSc",0x47:"ScrLk",0x48:"Pause",0x49:"Insert",0x4a:"Home",0x4b:"PgUp",0x4c:"Delete",0x4d:"End",0x4e:"PgDn",0x4f:"→",0x50:"←",0x51:"↓",0x52:"↑",0x53:"Num",0x65:"Menu",0xe0:"L Ctrl",0xe1:"L Shift",0xe2:"L Alt",0xe3:"L Cmd",0xe4:"R Ctrl",0xe5:"R Shift",0xe6:"R Alt",0xe7:"R Cmd"});
const CONSUMER = {0x00b5:"Next",0x00b6:"Previous",0x00b7:"Stop",0x00cd:"Play / Pause",0x00e2:"Mute",0x00e9:"Volume +",0x00ea:"Volume −",0x0070:"Brightness +",0x006f:"Brightness −"};
// AM usage-page codes. The PCB/nameplate block and layer controls were
// confirmed against a Relic 80 keymap captured from AM's configurator.
// Display-lighting and model-switch controls are retained for other boards.
const VENDOR = {
  0x0c0f:"Layer 1",0x0c10:"Layer 2",0x0c11:"Layer 3",0x0c12:"Layer 4",0x0c13:"Layer 5",0x0c14:"Layer 6",0x0c15:"Layer 7",
  0x0c20:"Fn 1",0x0c0b:"Fn 2",0x0c22:"Fn 3",0x0c23:"Fn 4",0x0c24:"Fn 5",0x0c25:"Fn 6",0x0c26:"Fn 7",0x0c0d:"Previous layer",
  0x0100:"Next LED",0x0101:"LED On / Off",0x0102:"LED Bright +",0x0103:"LED Bright −",0x0104:"LED Speed +",0x0105:"LED Speed −",0x0140:"LED Rotate",
  0x0900:"Next PCB",0x0901:"PCB Bright +",0x0902:"PCB Bright −",0x0903:"PCB On / Off",0x0904:"PCB Speed +",0x0905:"PCB Speed −",
  0x090b:"Nameplate Bright +",0x090c:"Nameplate Bright −",0x090d:"Nameplate On / Off",0x090e:"Nameplate Color",0x090f:"Next Nameplate",
  0x0106:"Bluetooth 1",0x0107:"Bluetooth 2",0x0108:"Bluetooth 3",0x0130:"2.4G",0x0910:"Battery",0x0922:"Win / Mac",0x0a01:"Power",0x0a02:"Reset",
};
const VENDOR_GROUPS = ["Layers & Fn","Display lighting","PCB lighting","Nameplate lighting","Wireless & system"];

function makeCode(page, usage, modifier = 0) {
  return `#${modifier.toString(16).padStart(2,"0")}${page.toString(16).padStart(2,"0")}${usage.toString(16).padStart(4,"0")}`.toUpperCase();
}

function codeParts(code) {
  if (!/^#[0-9A-F]{8}$/i.test(code || "")) return null;
  return {modifier: parseInt(code.slice(1,3),16), page: parseInt(code.slice(3,5),16), usage: parseInt(code.slice(5,9),16)};
}

function decodeCode(code) {
  const parts = codeParts(code);
  if (!parts) return String(code || "Invalid");
  if (!parts.page && !parts.usage) return "None";
  if (parts.page === 0x95 && parts.usage >= 0x1500 && parts.usage <= 0x151f) return `Macro ${parts.usage - 0x1500 + 1}`;
  let label = parts.page === 0x07 ? HID_NAMES[parts.usage] : parts.page === 0x0c ? CONSUMER[parts.usage] : parts.page === 0x92 ? VENDOR[parts.usage] : null;
  label ||= `${parts.page.toString(16).toUpperCase()}:${parts.usage.toString(16).toUpperCase()}`;
  if (parts.modifier === 0x11) return `↓ ${label}`;
  if (parts.modifier === 0x10) return `↑ ${label}`;
  return parts.modifier ? `M${parts.modifier.toString(16)} + ${label}` : label;
}

const KEY_OPTIONS = [{label:"None", code:"#00000000", category:"Basic"}];
for (let usage = 0x04; usage <= 0x1d; usage++) KEY_OPTIONS.push({label:HID_NAMES[usage], code:makeCode(7,usage), category:"Letters"});
for (let usage = 0x1e; usage <= 0x27; usage++) KEY_OPTIONS.push({label:HID_NAMES[usage], code:makeCode(7,usage), category:"Numbers"});
for (const usage of [0x28,0x29,0x2a,0x2b,0x2c,0x2d,0x2e,0x2f,0x30,0x31,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x46,0x47,0x48,0x49,0x4a,0x4b,0x4c,0x4d,0x4e,0x4f,0x50,0x51,0x52,0x65,0xe0,0xe1,0xe2,0xe3,0xe4,0xe5,0xe6,0xe7]) KEY_OPTIONS.push({label:HID_NAMES[usage], code:makeCode(7,usage), category:"Basic"});
for (const usage of [...Array.from({length:12},(_,i)=>0x3a+i),0x68]) KEY_OPTIONS.push({label:HID_NAMES[usage], code:makeCode(7,usage), category:"Function"});
for (const [usage,label] of Object.entries(CONSUMER)) KEY_OPTIONS.push({label, code:makeCode(0x0c,Number(usage)), category:"Media"});
for (const [usage,label] of Object.entries(VENDOR)) KEY_OPTIONS.push({label, code:makeCode(0x92,Number(usage)), category:"Device"});

const QWERTY_ROWS = [
  [[0x29,1.25],null,...Array.from({length:12},(_,index)=>[0x3a+index,1])],
  [[0x35,1],...[0x1e,0x1f,0x20,0x21,0x22,0x23,0x24,0x25,0x26,0x27,0x2d,0x2e].map(usage=>[usage,1]),[0x2a,2]],
  [[0x2b,1.5],...[0x14,0x1a,0x08,0x15,0x17,0x1c,0x18,0x0c,0x12,0x13,0x2f,0x30,0x31].map(usage=>[usage,1])],
  [[0x39,1.8],...[0x04,0x16,0x07,0x09,0x0a,0x0b,0x0d,0x0e,0x0f,0x33,0x34].map(usage=>[usage,1]),[0x28,2.2]],
  [[0xe1,2.3],...[0x1d,0x1b,0x06,0x19,0x05,0x11,0x10,0x36,0x37,0x38].map(usage=>[usage,1]),[0xe5,2.7]],
  [[0xe0,1.35],[0xe3,1.35],[0xe2,1.35],[0x2c,6.2],[0xe6,1.35],[0xe7,1.35],[0x65,1.35],[0xe4,1.35]],
];

function standardOption(usage, category="Keyboard") {
  return {label:HID_NAMES[usage]||`07:${usage.toString(16).toUpperCase()}`,code:makeCode(7,usage),category};
}

function assignmentButton(option,current,width=1) {
  const active=option.code.toUpperCase()===String(current||"").toUpperCase();
  const disabled=state.selected===null?"disabled":"";
  return `<button class="palette-key assignment-key ${active?'active':''}" data-code="${option.code}" data-search="${esc((option.label+' '+option.category).toLowerCase())}" style="--key-units:${width}" title="${esc(option.category)} · ${option.code}" ${disabled}>${esc(option.label)}</button>`;
}

function vendorGroup(usage) {
  if ((usage>=0x0c0b&&usage<=0x0c26)) return "Layers & Fn";
  if ((usage>=0x0100&&usage<=0x0105)||usage===0x0140) return "Display lighting";
  if (usage>=0x0900&&usage<=0x0905) return "PCB lighting";
  if (usage>=0x090b&&usage<=0x090f) return "Nameplate lighting";
  return "Wireless & system";
}

function renderAssignmentPalette(current) {
  const macrosForPalette=(state.config.macro_key||[]).map((macro,index)=>({label:`Macro ${index+1}`,code:macro.original_key,category:"Macros"}));
  const extraUsages=[0x46,0x47,0x48,0x49,0x4a,0x4b,0x4c,0x4d,0x4e,0x4f,0x50,0x51,0x52,0x53,0x68];
  const extras=[{label:"None",code:"#00000000",category:"Navigation & media"},...extraUsages.map(usage=>standardOption(usage,"Navigation & media")),...KEY_OPTIONS.filter(option=>option.category==="Media")];
  const vendorOptions=Object.entries(VENDOR).map(([usage,label])=>({label,code:makeCode(0x92,Number(usage)),category:vendorGroup(Number(usage))}));
  return `<section class="assignment-panel">
    <div class="assignment-heading"><div><strong>Available assignments</strong><small>${state.selected===null?'Select a key on the board first.':`Assigning matrix key ${state.selected}`}</small></div><input id="key-search" class="search-field" type="search" placeholder="Filter keys and controls…"></div>
    <div class="assignment-scroll"><div class="qwerty-board assignment-section"><p class="control-label">Standard QWERTY keyboard</p>${QWERTY_ROWS.map(row=>`<div class="qwerty-row">${row.map(item=>item?assignmentButton(standardOption(item[0]),current,item[1]):`<span class="qwerty-spacer"></span>`).join("")}</div>`).join("")}</div></div>
    <div class="assignment-groups">
      <div class="assignment-section"><p class="control-label">Navigation & media</p><div class="assignment-grid">${extras.map(option=>assignmentButton(option,current)).join("")}</div></div>
      <div class="assignment-section"><p class="control-label">Macros</p>${macrosForPalette.length?`<div class="assignment-grid">${macrosForPalette.map(option=>assignmentButton(option,current)).join("")}</div>`:`<small class="palette-empty">Create a macro on the Macros screen to assign it here.</small>`}</div>
      ${VENDOR_GROUPS.map(group=>`<div class="assignment-section"><p class="control-label">Angry Miao · ${group}</p><div class="assignment-grid">${vendorOptions.filter(option=>option.category===group).map(option=>assignmentButton(option,current)).join("")}</div></div>`).join("")}
    </div>
  </section>`;
}

function activeLayout() {
  if (productFamily(productId()) === "80") return {name:"Relic 80", className:"relic", keys:RELIC_LAYOUT};
  if (productFamily(productId()) === "ALICE") return {name:"AFA", className:"afa", keys:AFA_LAYOUT};
  const layer = layers()[state.layer]?.layer || [];
  const keys = [];
  layer.forEach((code, index) => {
    if (code !== "#00000000") {
      const row = Math.floor(index / 25), col = index % 25;
      keys.push([index, col * 6.25, row * 15 + 3, decodeCode(code) === "Space" ? 24 : 5.6]);
    }
  });
  return {name:"Matrix layout", className:"generic", keys};
}

function keyClass(code) {
  const parts = codeParts(code);
  if (parts?.page === 0x95) return "macro";
  if (parts?.page === 0x92) return "vendor";
  return "";
}

function render() {
  $("#empty-state").hidden = Boolean(state.config);
  $("#screen").hidden = !state.config;
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.screen === state.screen));
  if (state.config) renderScreen();
  updateMeta();
}

function renderScreen() {
  stopPlayback(false);
  if (!state.config) return;
  if (state.screen === "keymap") renderKeymap();
  else if (state.screen === "macros") renderMacros();
  else renderLeds();
}

function renderKeymap() {
  state.layer = Math.min(state.layer, Math.max(0, layers().length - 1));
  const layer = layers()[state.layer]?.layer || [];
  const layout = activeLayout();
  if (state.selected !== null && !layout.keys.some(key => key[0] === state.selected)) state.selected = null;
  const current=state.selected===null?null:(layer[state.selected]||"#00000000");
  $("#screen").innerHTML = `
    <div class="screen-shell">
      <header class="screen-header">
        <div><p class="eyebrow">${esc(layout.name)}</p><h1>Keymap</h1><p class="description">Select a physical key, then choose what it should send.</p></div>
        <div class="segmented layer-tabs">${layers().map((_,i) => `<button class="${i===state.layer?'active':''}" data-layer="${i}">${i+1}</button>`).join("")}</div>
      </header>
      <div class="editor-grid">
        <section class="card"><div class="card-header"><strong>Layer ${state.layer+1}</strong><small>${layout.keys.length} physical keys</small></div><div class="card-body">
          <div class="keyboard-stage ${layout.className}">
            ${layout.keys.map(([index,x,y,w=4.8,rotation=0]) => {
              const code = layer[index] || "#00000000";
              return `<button class="keycap ${keyClass(code)} ${state.selected===index?'selected':''}" data-index="${index}" style="left:${x}%;top:${y}%;width:${w}%;transform:rotate(${rotation}deg)" title="Matrix ${index} · ${esc(code)}">${esc(decodeCode(code))}<span>${index}</span></button>`;
            }).join("")}
          </div>
          ${renderAssignmentPalette(current)}
        </div></section>
        <aside class="card inspector">${renderKeyInspector(layer)}</aside>
      </div>
    </div>`;
  $$("[data-layer]").forEach(button => button.addEventListener("click", () => { state.layer = Number(button.dataset.layer); renderKeymap(); }));
  $$(".keycap").forEach(button => button.addEventListener("click", () => { state.selected = Number(button.dataset.index); renderKeymap(); }));
  wireKeyInspector();
}

function renderKeyInspector(layer) {
  if (state.selected === null) return `<div class="inspector-empty"><div><p class="eyebrow">Nothing selected</p><p>Click a keycap to edit its assignment.</p></div></div>`;
  const current = layer[state.selected] || "#00000000";
  return `<div class="card-header"><strong>Key ${state.selected}</strong><small>Layer ${state.layer+1}</small></div><div class="card-body">
    <div class="selected-code"><div><strong>${esc(decodeCode(current))}</strong><br><code>${esc(current)}</code></div><span class="pill">${keyClass(current)||'key'}</span></div>
    <p class="inspector-help">Choose a key from the QWERTY, macro, or Angry Miao palettes below the keyboard. Raw codes remain available for lossless passthrough.</p>
    <div class="raw-row"><input id="raw-code" class="text-field" value="${esc(current)}" maxlength="9" aria-label="Raw keycode"><button id="apply-raw" class="button ghost">Apply</button></div>
  </div>`;
}

function assignSelected(code) {
  if (state.selected === null || !layers()[state.layer]) return;
  if (!/^#[0-9a-f]{8}$/i.test(code)) return toast("Invalid keycode", "Use # followed by exactly eight hexadecimal digits.", "error");
  mutate(() => { layers()[state.layer].layer[state.selected] = code.toUpperCase(); });
}

function wireKeyInspector() {
  $$(".palette-key").forEach(button => button.addEventListener("click", () => assignSelected(button.dataset.code)));
  $("#key-search")?.addEventListener("input", event => {
    const query = event.target.value.trim().toLowerCase();
    $$(".palette-key").forEach(button => button.hidden = query && !button.dataset.search.includes(query));
    $$(".assignment-section").forEach(section=>{section.hidden=Boolean(query)&&!section.querySelector(".palette-key:not([hidden])");});
  });
  $("#apply-raw")?.addEventListener("click", () => assignSelected($("#raw-code").value.trim()));
  $("#raw-code")?.addEventListener("keydown", event => { if (event.key === "Enter") assignSelected(event.currentTarget.value.trim()); });
}

function totalMacroEvents() {
  return (state.config.macro_key || []).reduce((sum, macro) => sum + (macro.layer_key || []).length, 0);
}

function missingMacroTokens() {
  const defined=new Set(macros().map(macro=>String(macro.original_key||"").toUpperCase()));
  const referenced=new Set();
  for(const layer of layers())for(const code of layer.layer||[]){
    const upper=String(code||"").toUpperCase();
    if(/^#009515(?:0[0-9A-F]|1[0-9A-F])$/.test(upper))referenced.add(upper);
  }
  return [...referenced].filter(code=>!defined.has(code)).sort();
}

function addMacro() {
  if (macros().length >= 32) return toast("Macro limit reached", "This profile supports up to 32 macros.", "error");
  const used = new Set(macros().map(macro => macro.original_key.toUpperCase()));
  let tokenCode = null;
  for (let i=0;i<32;i++) {
    const candidate = makeCode(0x95,0x1500+i);
    if (!used.has(candidate)) { tokenCode = candidate; break; }
  }
  mutate(() => { macros().push({original_key:tokenCode, layer_key:[], intvel_ms:[]}); state.macro=macros().length-1; });
}

async function importMacros(input) {
  const file=input.files?.[0];
  input.value="";
  if(!file||!state.config)return;
  try{
    const parsed=JSON.parse(await file.text());
    const result=await api("/api/macros/import",{method:"POST",body:JSON.stringify({config:parsed})});
    const incoming=result.macros||[];
    if(macros().length&&!confirm(`Replace the ${macros().length} macros in this workspace with ${incoming.length} from ${file.name}?`))return;
    mutate(()=>{state.config.macro_key=clone(incoming);state.macro=0;});
    const events=incoming.reduce((sum,macro)=>sum+(macro.layer_key||[]).length,0);
    const connected=incoming.filter(macro=>layers().some(layer=>(layer.layer||[]).some(code=>String(code).toUpperCase()===macro.original_key))).map(macro=>decodeCode(macro.original_key));
    toast("Macros imported",`${incoming.length} macros · ${events} events from ${result.product_id}${connected.length?` · ${connected.join(', ')} connected to this keymap`:''}`,"success");
  }catch(error){toast("Could not import macros",error.message,"error");}
}

function removeMacro() {
  const macro = macros()[state.macro];
  if (!macro || !confirm(`Delete ${decodeCode(macro.original_key)}? Keys assigned to it will be cleared.`)) return;
  mutate(() => {
    for (const layer of layers()) layer.layer = layer.layer.map(code => code.toUpperCase() === macro.original_key.toUpperCase() ? "#00000000" : code);
    macros().splice(state.macro,1);
    state.macro = Math.max(0,state.macro-1);
  });
}

function macroBaseCode(eventCode) {
  const parts = codeParts(eventCode);
  return parts ? makeCode(parts.page, parts.usage) : "#00070004";
}

function macroEventCode(base, down) {
  const parts = codeParts(base);
  return parts ? makeCode(parts.page, parts.usage, down ? 0x11 : 0x10) : "#11070004";
}

async function applyMacroText(mode) {
  const current=macros()[state.macro];
  if(!current)return;
  const text=$("#macro-text").value;
  const delay=Number($("#macro-text-delay").value);
  try{
    const generated=await api("/api/macros/text",{method:"POST",body:JSON.stringify({text,delay_ms:delay})});
    const oldCount=(current.layer_key||[]).length;
    const projected=mode==="append"?totalMacroEvents()+generated.layer_key.length:totalMacroEvents()-oldCount+generated.layer_key.length;
    if(projected>200)throw new Error(`This would use ${projected}/200 events across the profile.`);
    mutate(()=>{
      current.layer_key=mode==="append"?[...(current.layer_key||[]),...generated.layer_key]:generated.layer_key;
      current.intvel_ms=mode==="append"?[...(current.intvel_ms||[]).slice(0,oldCount),...generated.intvel_ms]:generated.intvel_ms;
    });
    toast("Text converted",`${generated.characters} characters · ${generated.layer_key.length} deterministic events · ${delay}ms between keys`,"success");
  }catch(error){toast("Could not convert text",error.message,"error");}
}

function renderMacros() {
  state.macro = Math.min(state.macro, Math.max(0,macros().length-1));
  const current = macros()[state.macro];
  const total = totalMacroEvents();
  const eventOptions = KEY_OPTIONS.filter(option => ["Letters","Numbers","Basic","Function"].includes(option.category) && option.code !== "#00000000");
  const assigned = current ? layers().reduce((sum, layer) => sum + layer.layer.filter(code => code.toUpperCase()===current.original_key.toUpperCase()).length,0) : 0;
  const missing=missingMacroTokens();
  const missingWarning=missing.length?`<div class="write-warning macro-warning"><strong>Macro assignments have no readable actions</strong><p>${missing.map(code=>esc(decodeCode(code))).join(", ")} ${missing.length===1?'is':'are'} assigned in the keymap, but the keyboard returned no matching macro definition. Loading cannot reconstruct those keystrokes; restore them from a saved JSON or recreate them before writing.</p></div>`:"";
  $("#screen").innerHTML = `<div class="screen-shell">
    <header class="screen-header"><div><p class="eyebrow">Up to 32 tracks · 200 events</p><h1>Macros</h1><p class="description">Record or arrange exact key-down, key-up, and timing events.</p></div><div class="header-controls"><div><small>${total}/200 events</small><div class="limit-meter"><span style="width:${Math.min(100,total/2)}%"></span></div></div><button id="import-macros" class="button ghost">Import macros</button><button id="add-macro" class="button primary">+ New macro</button></div></header>
    ${missingWarning}
    <div class="macro-layout">
      <aside class="card macro-list"><div class="card-header"><strong>Macro library</strong><small>${macros().length}/32</small></div><div class="macro-list-items">
        ${macros().length ? macros().map((macro,i) => `<button class="macro-item ${i===state.macro?'active':''}" data-macro="${i}"><span><strong>${esc(decodeCode(macro.original_key))}</strong><small>${(macro.layer_key||[]).length} events</small></span><span class="macro-token">${esc(macro.original_key.slice(-2))}</span></button>`).join("") : `<div class="event-empty">No macros yet.<br>Create one to begin.</div>`}
      </div></aside>
      <section class="card macro-editor">${current ? `<div class="card-header"><strong>${esc(decodeCode(current.original_key))}</strong><small>Assigned to ${assigned} key${assigned===1?'':'s'}</small></div>
        <div class="card-body"><div class="macro-toolbar">
          <button id="record-macro" class="button ghost ${state.recording?'recording':''}">${state.recording?'■ Stop recording':'● Record'}</button>
          <button id="add-event" class="button ghost">+ Event</button>
          <div class="spacer"></div>
          <button id="assign-macro" class="button ghost" ${state.selected===null?'disabled':''}>Assign to selected key</button>
          <button id="delete-macro" class="button danger">Delete</button>
        </div><div class="text-macro-composer">
          <div><strong>Text → keystrokes</strong><small>Paste text instead of recording it in real time.</small></div>
          <textarea id="macro-text" class="text-field" rows="3" placeholder="Type the exact text this macro should enter…"></textarea>
          <div class="text-macro-actions"><label>Inter-key delay <input id="macro-text-delay" class="text-field" type="number" min="1" max="1000" value="10"> ms</label><div class="spacer"></div><button id="text-append" class="button ghost">Append</button><button id="text-replace" class="button primary">Replace events</button></div>
          <small>US keyboard layout · letters, numbers, punctuation, spaces, Tab, and Enter · Shift is generated automatically.</small>
        </div><div class="event-list">
          ${(current.layer_key||[]).length ? current.layer_key.map((code,i) => {
            const down = codeParts(code)?.modifier !== 0x10;
            const base = macroBaseCode(code);
            return `<div class="event-row" data-event="${i}"><span class="event-number">${i+1}</span><button class="event-action ${down?'':'up'}" data-action="${i}">${down?'Key down':'Key up'}</button><select class="select-field event-key" data-event-key="${i}">${eventOptions.map(option=>`<option value="${option.code}" ${option.code===base?'selected':''}>${esc(option.label)}</option>`).join("")}</select><input class="text-field event-delay" type="number" min="0" max="15000" value="${Number(current.intvel_ms?.[i]??25)}" data-delay="${i}" title="Delay after event in milliseconds"><button class="remove-event" data-remove="${i}" title="Remove">×</button></div>`;
          }).join("") : `<div class="event-empty">${state.recording?'Press keys now. Recording captures both down and up events.':'Record input or add an event manually.'}</div>`}
        </div></div>` : `<div class="event-empty">Create a macro to open the event editor.</div>`}</section>
    </div></div>`;
  $("#add-macro").addEventListener("click", addMacro);
  $("#import-macros").addEventListener("click",()=>$("#macro-import-input").click());
  $$("[data-macro]").forEach(button => button.addEventListener("click",()=>{state.macro=Number(button.dataset.macro);renderMacros();}));
  if (!current) return;
  $("#delete-macro").addEventListener("click", removeMacro);
  $("#add-event").addEventListener("click", () => {
    if (totalMacroEvents() >= 200) return toast("Event limit reached", "Delete an event before adding another.", "error");
    mutate(()=>{current.layer_key.push("#11070004");current.intvel_ms.push(25);});
  });
  $("#record-macro").addEventListener("click", toggleRecording);
  $("#text-append").addEventListener("click",()=>applyMacroText("append"));
  $("#text-replace").addEventListener("click",()=>applyMacroText("replace"));
  $("#assign-macro").addEventListener("click", () => assignSelected(current.original_key));
  $$("[data-action]").forEach(button => button.addEventListener("click",()=>mutate(()=>{
    const i=Number(button.dataset.action); current.layer_key[i]=macroEventCode(macroBaseCode(current.layer_key[i]), codeParts(current.layer_key[i])?.modifier===0x10);
  })));
  $$("[data-event-key]").forEach(select => select.addEventListener("change",()=>mutate(()=>{
    const i=Number(select.dataset.eventKey);current.layer_key[i]=macroEventCode(select.value,codeParts(current.layer_key[i])?.modifier!==0x10);
  })));
  $$("[data-delay]").forEach(input => input.addEventListener("change",()=>mutate(()=>{
    const i=Number(input.dataset.delay);current.intvel_ms[i]=Math.max(0,Math.min(15000,Number(input.value)||0));
  })));
  $$("[data-remove]").forEach(button => button.addEventListener("click",()=>mutate(()=>{
    const i=Number(button.dataset.remove);current.layer_key.splice(i,1);current.intvel_ms.splice(i,1);
  })));
}

const DOM_USAGE = {KeyA:0x04,KeyB:0x05,KeyC:0x06,KeyD:0x07,KeyE:0x08,KeyF:0x09,KeyG:0x0a,KeyH:0x0b,KeyI:0x0c,KeyJ:0x0d,KeyK:0x0e,KeyL:0x0f,KeyM:0x10,KeyN:0x11,KeyO:0x12,KeyP:0x13,KeyQ:0x14,KeyR:0x15,KeyS:0x16,KeyT:0x17,KeyU:0x18,KeyV:0x19,KeyW:0x1a,KeyX:0x1b,KeyY:0x1c,KeyZ:0x1d,Digit1:0x1e,Digit2:0x1f,Digit3:0x20,Digit4:0x21,Digit5:0x22,Digit6:0x23,Digit7:0x24,Digit8:0x25,Digit9:0x26,Digit0:0x27,Enter:0x28,Escape:0x29,Backspace:0x2a,Tab:0x2b,Space:0x2c,Minus:0x2d,Equal:0x2e,BracketLeft:0x2f,BracketRight:0x30,Backslash:0x31,Semicolon:0x33,Quote:0x34,Backquote:0x35,Comma:0x36,Period:0x37,Slash:0x38,CapsLock:0x39,ArrowRight:0x4f,ArrowLeft:0x50,ArrowDown:0x51,ArrowUp:0x52,ControlLeft:0xe0,ShiftLeft:0xe1,AltLeft:0xe2,MetaLeft:0xe3,ControlRight:0xe4,ShiftRight:0xe5,AltRight:0xe6,MetaRight:0xe7};
for(let i=1;i<=12;i++) DOM_USAGE[`F${i}`]=0x39+i;

function toggleRecording() {
  state.recording = !state.recording;
  state.recordLast = performance.now();
  renderMacros();
}

function recordEvent(event, down) {
  if (!state.recording || state.screen !== "macros" || event.repeat) return;
  const usage = DOM_USAGE[event.code];
  if (usage === undefined) return;
  event.preventDefault();
  const current = macros()[state.macro];
  if (!current || totalMacroEvents() >= 200) { state.recording=false; renderMacros(); return toast("Event limit reached","Recording stopped at 200 events.","error"); }
  const now = performance.now();
  current.layer_key.push(makeCode(7,usage,down?0x11:0x10));
  current.intvel_ms.push(Math.max(0,Math.min(15000,Math.round(now-state.recordLast))));
  state.recordLast = now;
  markDirty();
  renderMacros();
}

function getPage(index) {
  return pageData().find(page => Number(page.page_index) === index) || pageData()[index];
}

function createLedPages() {
  mutate(() => {
    state.config.page_data = Array.from({length:8},(_,index)=>({
      valid:index<3?1:(index>=5?1:0),page_index:index,lightness:100,speed_ms:90,
      color:{default:false,back_rgb:"#000000",rgb:"#000000"},word_page:{valid:0,word_len:0,unicode:[]},
      frames:{valid:0,frame_num:0,frame_data:[]},
      keyframes:{valid:index>=5?1:0,frame_num:index>=5?1:0,frame_data:index>=5?[{frame_index:0,frame_RGB:Array(90).fill("#000000")}]:[]},
      ...(productFamily(productId())==="80"&&index>=5?{spotlight_frames:{valid:1,frame_num:1,frame_data:[{frame_index:0,frame_RGB:Array(24).fill("#000000")}]}}:{}),
    }));
    state.config.page_num = 8;
  });
}

function trackInfo() {
  const page = getPage(state.ledSlot);
  const lengths = {frames:200,keyframes:90,spotlight_frames:24};
  return {page, track:page?.[state.ledTarget], length:lengths[state.ledTarget]};
}

function ensureTrack() {
  const page = getPage(state.ledSlot);
  if (!page) return null;
  const length = {frames:200,keyframes:90,spotlight_frames:24}[state.ledTarget];
  if (!page[state.ledTarget]) page[state.ledTarget]={valid:1,frame_num:0,frame_data:[]};
  const track = page[state.ledTarget];
  if (!track.frame_data?.length) {
    track.valid=1;track.frame_num=1;track.frame_data=[{frame_index:0,frame_RGB:Array(length).fill("#000000")}];
  }
  return track;
}

function currentFrame() {
  const track = trackInfo().track;
  if (!track?.frame_data?.length) return null;
  state.ledFrame = Math.min(state.ledFrame,track.frame_data.length-1);
  return track.frame_data[state.ledFrame];
}

function edgeColors(colors) {
  const result=Array(24).fill("#000000");
  for(let index=0;index<7;index++)result[index]=colors[index]||"#000000";
  return result;
}

function resampleEdgeAnimation(sourceFrames, count) {
  const sources=sourceFrames?.length?sourceFrames:[Array(24).fill("#000000")];
  return Array.from({length:count},(_,index)=>{
    const sourceIndex=Math.min(sources.length-1,Math.floor(index*sources.length/count));
    const source=sources[sourceIndex]?.frame_RGB||sources[sourceIndex]||[];
    return {frame_index:index,frame_RGB:edgeColors(source)};
  });
}

function scaledColor(color, amount) {
  const value=parseInt(color.slice(1),16);
  const channel=shift=>Math.round(((value>>shift)&255)*amount).toString(16).padStart(2,"0");
  return `#${channel(16)}${channel(8)}${channel(0)}`.toUpperCase();
}

function replaceEdgeAnimation(mode) {
  const page=getPage(state.ledSlot);if(!page)return;
  const count=Math.max(1,Math.min(256,page.keyframes?.frame_data?.length||1));
  const painted=edgeColors(currentFrame()?.frame_RGB||[]);
  const frames=[];
  for(let index=0;index<count;index++){
    let colors;
    if(mode==="hold")colors=[...painted];
    else if(mode==="static")colors=edgeColors(Array(7).fill(state.ledColor));
    else{
      const amount=count===1?1:(1-Math.cos(2*Math.PI*index/count))/2;
      colors=edgeColors(Array(7).fill(scaledColor(state.ledColor,amount)));
    }
    frames.push({frame_index:index,frame_RGB:colors});
  }
  mutate(()=>{page.spotlight_frames={valid:1,frame_num:count,frame_data:frames};state.ledFrame=0;});
  const label=mode==="hold"?"Painted edge frame held":mode==="static"?"Static edge color created":"Edge pulse created";
  toast(label,`${count} edge frames generated to match the key animation.`,"success");
}

function renderLeds() {
  if (!pageData().length) {
    $("#screen").innerHTML=`<div class="empty-state"><p class="eyebrow">Key-only export</p><h1>No LED pages loaded.</h1><p>Merge the matching lighting JSON to preserve your existing effects, or create three blank custom slots.</p><div class="header-controls"><button id="merge-led" class="button ghost large">Merge lighting JSON</button><button id="create-led" class="button primary large">Create blank slots</button></div></div>`;
    $("#merge-led").addEventListener("click",()=>$("#merge-input").click());
    $("#create-led").addEventListener("click",createLedPages);
    return;
  }
  const page = getPage(state.ledSlot);
  const model=activeLedModel();
  const targets=model.targets;
  if (!targets.some(target=>target.key===state.ledTarget)) state.ledTarget=targets[0].key;
  const {track,length}=trackInfo();
  const frames=track?.frame_data||[];
  state.ledFrame=Math.min(state.ledFrame,Math.max(0,frames.length-1));
  const frame=frames[state.ledFrame];
  const gridClass=state.ledTarget==="frames"?"display":state.ledTarget==="spotlight_frames"?"edge":"key";
  const columns=state.ledTarget==="frames"?40:state.ledTarget==="spotlight_frames"?7:model.keyColumns;
  const physicalLayout=state.ledTarget==="keyframes"?model.physicalLayout:null;
  const pixelMap=physicalLayout?physicalLayout.map(item=>item.index):state.ledTarget==="keyframes"?model.keyMap:state.ledTarget==="spotlight_frames"?[0,1,2,3,4,5,6]:model.displayMap||Array.from({length},(_,index)=>index);
  const mappedCount=new Set(pixelMap.filter(index=>index>=0)).size;
  const keyLabels=layers()[0]?.layer||[];
  const pixelCanvas=!frame?`<div class="event-empty"><button id="first-frame" class="button primary">Create first frame</button></div>`:physicalLayout?`<div class="pixel-grid physical afa-led-board">${physicalLayout.map(item=>{
    const color=frame.frame_RGB[item.index]||"#000000";
    const body=item.keyIndex===null;
    const label=body?item.label:decodeCode(keyLabels[item.keyIndex]||"#00000000");
    return `<button class="pixel physical-pixel ${body?'body-led':''}" data-pixel="${item.index}" style="left:${item.x}%;top:${item.y}%;width:${item.w}%;--rotation:${item.rotation}deg;background:${esc(color)};--pixel-color:${esc(color)}" title="${body?'Center light':`Key ${esc(label)} · matrix ${item.keyIndex}`} · LED ${item.index} · ${esc(color)}"><span>${esc(label)}</span><small>LED ${item.index}</small></button>`;
  }).join("")}</div>`:`<div class="pixel-grid ${gridClass}" style="grid-template-columns:repeat(${columns},1fr)">${pixelMap.map(index=>index<0?`<span class="pixel-spacer"></span>`:`<button class="pixel" data-pixel="${index}" style="background:${esc(frame.frame_RGB[index]||'#000000')};--pixel-color:${esc(frame.frame_RGB[index]||'#000000')}" title="LED ${index} · ${esc(frame.frame_RGB[index]||'#000000')}"></button>`).join("")}</div>`;
  const gifSize=state.ledTarget==="frames"?"40×5":state.ledTarget==="spotlight_frames"?"18×7 → 7 edge LEDs":`${model.keyRaster} → ${mappedCount} mapped LEDs`;
  const relicKeyTarget=model===LED_MODELS["80"]&&state.ledTarget==="keyframes";
  const pairsRelicGif=relicKeyTarget&&state.relicGifEdges;
  const edgeAutomation=model===LED_MODELS["80"]&&state.ledTarget==="spotlight_frames";
  const keyFrameCount=Math.max(1,page?.keyframes?.frame_data?.length||1);
  const encodedSpeed=firmwareLedSpeed(page?.speed_ms??90);
  const gifButtonLabel=pairsRelicGif?"Import GIF to both":relicKeyTarget?"Import key GIF":"Import GIF";
  const gifHelp=pairsRelicGif
    ? "Replaces both tracks from one 18×7 animation: 89 key LEDs plus 7 edge LEDs."
    : relicKeyTarget?"Replaces the 89-key track; your separate edge animation is preserved and retimed to match.":edgeAutomation?`Maps this GIF to the 7 edge LEDs, then retimes it to the key track’s ${keyFrameCount} frames.`:`Replaces this track by resizing every GIF frame to ${gifSize}.`;
  const relicGifOption=relicKeyTarget?`<label class="check-row"><input id="relic-gif-edges" type="checkbox" ${state.relicGifEdges?'checked':''}><span>Also derive edge lights from this GIF</span></label>`:"";
  const edgeTools=edgeAutomation?`<div class="control-group"><label class="control-label">Whole edge animation</label><div class="button-row"><button id="edge-static" class="button ghost">Static color</button><button id="edge-pulse" class="button ghost">Pulse color</button></div><button id="edge-hold" class="button ghost wide-button">Hold painted frame</button><small class="control-help">Generates ${keyFrameCount} edge frames automatically to match the key animation. “Hold” preserves the seven colors painted in the current frame.</small></div>`:"";
  $("#screen").innerHTML=`<div class="screen-shell">
    <header class="screen-header"><div><p class="eyebrow">Custom animation slots</p><h1>LED Studio</h1><p class="description">Paint frames, adjust timing, and preview without uploading anything.</p></div><div class="header-controls"><div class="segmented">${[5,6,7].map(i=>`<button data-slot="${i}" class="${i===state.ledSlot?'active':''}">Slot ${i-4}</button>`).join("")}</div><div class="segmented">${targets.map(target=>`<button data-target="${target.key}" class="${target.key===state.ledTarget?'active':''}">${target.label}</button>`).join("")}</div></div></header>
    <div class="led-layout">
      <aside class="card frame-list"><div class="card-header"><strong>Frames</strong><small>${frames.length}</small></div><div class="frame-items">${frames.map((item,i)=>`<button class="frame-item ${i===state.ledFrame?'active':''}" data-frame="${i}"><span class="frame-thumb">${(item.frame_RGB||[]).slice(0,12).map(color=>`<i style="background:${esc(color)}"></i>`).join("")}</span><span><strong>Frame ${String(i+1).padStart(2,"0")}</strong><small>${i===state.ledFrame?'Editing':'Select'}</small></span></button>`).join("")||`<div class="event-empty">No frames</div>`}</div><div class="card-body button-row"><button id="add-frame" class="button ghost">+ Duplicate</button><button id="remove-frame" class="button ghost" ${frames.length<=1?'disabled':''}>Delete</button></div></aside>
      <section class="card led-canvas-card"><div class="card-header"><strong>${esc(model.name)} · ${esc(targets.find(t=>t.key===state.ledTarget)?.label)}</strong><small>${mappedCount}${mappedCount===length?'':' mapped'} / ${length} stored${physicalLayout?' · Layer 1 labels':''}</small></div><div id="led-canvas" class="led-canvas ${physicalLayout?'physical-canvas':''}">${pixelCanvas}</div></section>
      <aside class="card led-controls"><div class="card-header"><strong>Frame controls</strong><button id="play-led" class="icon-button">${state.playing?'■':'▶'}</button></div><div class="card-body">
        <div class="control-group"><label class="control-label">Animation source</label><input id="gif-input" type="file" accept="image/gif,.gif" hidden><div class="gif-import-row"><button id="import-gif" class="button ghost">${gifButtonLabel}</button><select id="gif-resample" class="select-field" aria-label="GIF resize method"><option value="nearest" ${state.gifResample==='nearest'?'selected':''}>Crisp</option><option value="box" ${state.gifResample==='box'?'selected':''}>Balanced</option><option value="lanczos" ${state.gifResample==='lanczos'?'selected':''}>Smooth</option></select></div>${relicGifOption}<small class="control-help">${gifHelp}</small></div>
        ${edgeTools}
        <div class="control-group"><label class="control-label">Paint color</label><input id="led-color" class="color-picker" type="color" value="${state.ledColor}"><input id="led-color-text" class="text-field" value="${state.ledColor}"></div>
        <div class="control-group"><label class="control-label">Brush</label><div class="button-row"><button id="fill-led" class="button ghost">Fill all</button><button id="clear-led" class="button ghost">Clear</button></div></div>
        <div class="control-group"><label class="control-label">Brightness</label><div class="range-row"><input id="brightness" type="range" min="0" max="100" value="${Number(page?.lightness??100)}"><span class="range-value">${Number(page?.lightness??100)}%</span></div></div>
        <div class="control-group"><label class="control-label">Frame duration</label><select id="speed" class="select-field">${LED_SPEEDS.map(speed=>`<option value="${speed}" ${speed===encodedSpeed?'selected':''}>${speed} ms · ${(1000/speed).toFixed(1)} fps</option>`).join("")}</select><small class="control-help">These are the timing steps exposed by Angry Miao firmware.</small></div>
      </div></aside>
    </div></div>`;
  wireLedEditor();
}

function wireLedEditor() {
  $$('[data-slot]').forEach(button=>button.addEventListener('click',()=>{state.ledSlot=Number(button.dataset.slot);state.ledFrame=0;renderLeds();}));
  $$('[data-target]').forEach(button=>button.addEventListener('click',()=>{state.ledTarget=button.dataset.target;state.ledFrame=0;renderLeds();}));
  $$('[data-frame]').forEach(button=>button.addEventListener('click',()=>{state.ledFrame=Number(button.dataset.frame);renderLeds();}));
  $("#first-frame")?.addEventListener("click",()=>mutate(ensureTrack));
  $("#import-gif").addEventListener("click",()=>$("#gif-input").click());
  $("#gif-resample").addEventListener("change",event=>{state.gifResample=event.target.value;});
  $("#relic-gif-edges")?.addEventListener("change",event=>{state.relicGifEdges=event.target.checked;renderLeds();});
  $("#gif-input").addEventListener("change",event=>importGif(event.currentTarget));
  $("#edge-static")?.addEventListener("click",()=>replaceEdgeAnimation("static"));
  $("#edge-pulse")?.addEventListener("click",()=>replaceEdgeAnimation("pulse"));
  $("#edge-hold")?.addEventListener("click",()=>replaceEdgeAnimation("hold"));
  $("#add-frame").addEventListener("click",()=>mutate(()=>{
    const track=ensureTrack();const source=track.frame_data[state.ledFrame]||track.frame_data[0];track.frame_data.splice(state.ledFrame+1,0,clone(source));track.frame_data.forEach((f,i)=>f.frame_index=i);track.frame_num=track.frame_data.length;state.ledFrame++;
    if(state.ledTarget==="keyframes"&&activeLedModel()===LED_MODELS["80"]){const page=getPage(state.ledSlot);if(page.spotlight_frames?.frame_data?.length){const data=resampleEdgeAnimation(page.spotlight_frames.frame_data,track.frame_data.length);page.spotlight_frames={...page.spotlight_frames,frame_num:data.length,frame_data:data};}}
  }));
  $("#remove-frame").addEventListener("click",()=>mutate(()=>{
    const track=trackInfo().track;track.frame_data.splice(state.ledFrame,1);track.frame_data.forEach((f,i)=>f.frame_index=i);track.frame_num=track.frame_data.length;state.ledFrame=Math.max(0,state.ledFrame-1);
    if(state.ledTarget==="keyframes"&&activeLedModel()===LED_MODELS["80"]){const page=getPage(state.ledSlot);if(page.spotlight_frames?.frame_data?.length){const data=resampleEdgeAnimation(page.spotlight_frames.frame_data,track.frame_data.length);page.spotlight_frames={...page.spotlight_frames,frame_num:data.length,frame_data:data};}}
  }));
  let painting=false, checkpointed=false;
  const paint = pixel => {
    const frame=currentFrame();if(!frame)return;const i=Number(pixel.dataset.pixel);frame.frame_RGB[i]=state.ledColor;pixel.style.background=state.ledColor;pixel.style.setProperty('--pixel-color',state.ledColor);pixel.title=`LED ${i} · ${state.ledColor}`;
  };
  $$('.pixel').forEach(pixel=>{
    pixel.addEventListener('pointerdown',event=>{event.preventDefault();if(!checkpointed){pushUndo();checkpointed=true;}painting=true;paint(pixel);markDirty();});
    pixel.addEventListener('pointerenter',event=>{if(painting&&event.buttons)paint(pixel);});
  });
  window.addEventListener('pointerup',()=>{painting=false;checkpointed=false;},{once:true});
  $("#led-color").addEventListener("input",event=>{state.ledColor=event.target.value.toUpperCase();$("#led-color-text").value=state.ledColor;});
  $("#led-color-text").addEventListener("change",event=>{if(/^#[0-9a-f]{6}$/i.test(event.target.value)){state.ledColor=event.target.value.toUpperCase();renderLeds();}else toast("Invalid color","Use a six-digit hex color such as #8358FF.","error");});
  $("#fill-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill(state.ledColor);}));
  $("#clear-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill("#000000");}));
  $("#brightness").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).lightness=Number(event.target.value);}));
  $("#speed").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).speed_ms=Number(event.target.value);}));
  $("#play-led").addEventListener("click",()=>state.playing?stopPlayback():startPlayback());
}

async function importGif(input) {
  const file=input.files?.[0];
  input.value="";
  if(!file)return;
  if(file.size>12_000_000)return toast("GIF is too large","Choose a GIF smaller than 12 MB.","error");
  const target=state.ledTarget;
  const pairsRelicGif=activeLedModel()===LED_MODELS["80"]&&target==="keyframes"&&state.relicGifEdges;
  const targets=pairsRelicGif?["keyframes","spotlight_frames"]:[target];
  const button=$("#import-gif");button.disabled=true;button.textContent="Converting…";
  try{
    const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error("Could not read the GIF."));reader.readAsDataURL(file);});
    const encoded=String(dataUrl).split(",",2)[1];
    const result=await api("/api/led/gif",{method:"POST",body:JSON.stringify({data:encoded,targets,resample:state.gifResample,product_id:productId()})});
    mutate(()=>{
      const page=getPage(state.ledSlot);
      page.valid=1;
      for(const [trackName,trackResult] of Object.entries(result.tracks)){
        if(trackName==="spotlight_frames"){
          const count=Math.max(1,result.tracks.keyframes?.frame_count||page.keyframes?.frame_data?.length||trackResult.frame_count);
          const frameData=resampleEdgeAnimation(trackResult.frames,count);
          page[trackName]={valid:1,frame_num:count,frame_data:frameData};
        }else{
          page[trackName]={valid:1,frame_num:trackResult.frame_count,frame_data:trackResult.frames.map((colors,index)=>({frame_index:index,frame_RGB:colors}))};
        }
      }
      if(target==="keyframes"&&!pairsRelicGif&&page.spotlight_frames?.frame_data?.length){
        const count=page.keyframes.frame_data.length;
        const frameData=resampleEdgeAnimation(page.spotlight_frames.frame_data,count);
        page.spotlight_frames={...page.spotlight_frames,valid:1,frame_num:count,frame_data:frameData};
      }
      if(result.duration_ms&&target!=="spotlight_frames")page.speed_ms=Number(result.duration_ms);
      state.ledFrame=0;
    });
    const primary=result.tracks[target];
    const mapped=pairsRelicGif?"89 key + 7 edge LEDs":`${primary.mapped_pixels} mapped LEDs`;
    const synchronized=target==="spotlight_frames"&&primary.frame_count!==getPage(state.ledSlot).spotlight_frames.frame_num?` · retimed to ${getPage(state.ledSlot).spotlight_frames.frame_num} key frames`:"";
    const timing=`${result.duration_ms}ms / ${(1000/result.duration_ms).toFixed(1)}fps${result.timing_resampled?' · variable GIF timing resampled':''}`;
    const truncated=result.source_frames>result.decoded_frames?` · ${result.source_frames-result.decoded_frames} source frames beyond the 256-frame limit were omitted`:"";
    toast("GIF imported",`${file.name} · ${primary.frame_count} device frames · ${timing} · ${mapped}${synchronized}${truncated}`,"success");
  }catch(error){toast("Could not import GIF",error.message,"error");}
  finally{if(button.isConnected){button.disabled=false;button.textContent=pairsRelicGif?"Import GIF to both":target==="keyframes"&&activeLedModel()===LED_MODELS["80"]?"Import key GIF":"Import GIF";}}
}

function startPlayback() {
  const track=trackInfo().track;if(!track?.frame_data?.length)return;
  state.playing=true;renderLeds();
  const tick=()=>{
    if(!state.playing)return;
    state.ledFrame=(state.ledFrame+1)%track.frame_data.length;
    const frame=track.frame_data[state.ledFrame];
    $$('.pixel').forEach(pixel=>{const color=frame.frame_RGB[Number(pixel.dataset.pixel)]||'#000000';pixel.style.background=color;pixel.style.setProperty('--pixel-color',color);});
    $$('.frame-item').forEach((node,i)=>node.classList.toggle('active',i===state.ledFrame));
  };
  state.playTimer=setInterval(tick,Math.max(12,Number(getPage(state.ledSlot)?.speed_ms||90)));
}

function stopPlayback(rerender=true) {
  if(state.playTimer)clearInterval(state.playTimer);
  const was=state.playing;state.playTimer=null;state.playing=false;
  if(was&&rerender&&state.screen==='leds')renderLeds();
}

async function validateCurrent(showSuccess = true) {
  if (!state.config) return null;
  try {
    const result = await api("/api/config/validate", {method:"POST", body:JSON.stringify({config:state.config})});
    if (!result.ok) toast("Configuration needs attention", result.errors.join("\n"), "error");
    else if (showSuccess) {
      const plan=result.frame_plan;const detail=`${result.layers} layers · ${result.macros} macros · ${result.pages} pages${plan?` · ${plan.total} wire frames`:''}${result.warnings.length?`\n${result.warnings.join("\n")}`:''}`;
      toast("Configuration is valid",detail,"success");
    }
    return result;
  } catch(error){toast("Validation failed",error.message,"error");return null;}
}

function selectedDevice() {
  return state.devices.find(device=>device.port===state.selectedPort)||null;
}

function deviceSwitchesWorkspace(device) {
  if(!device||!state.config)return false;
  if(state.loadedPort)return state.loadedPort!==device.port;
  return !sameProductFamily(productId(),device.product_id);
}

function stashDeviceDocument() {
  if(!state.loadedPort||!state.config)return;
  state.deviceDocuments.set(state.loadedPort,{
    config:state.config,
    fileName:state.fileName,
    undo:state.undo,
    redo:state.redo,
    view:{layer:state.layer,selected:state.selected,macro:state.macro,ledSlot:state.ledSlot,ledTarget:state.ledTarget,ledFrame:state.ledFrame},
  });
}

function restoreDeviceDocument(port,deviceId) {
  const saved=state.deviceDocuments.get(port);
  if(!saved||!sameProductFamily(saved.config?.product_info?.product_id,deviceId))return false;
  state.config=saved.config;
  state.fileName=saved.fileName;
  state.undo=saved.undo;
  state.redo=saved.redo;
  if(saved.view)Object.assign(state,saved.view);
  else resetDocumentView();
  return true;
}

function resetDocumentView() {
  state.layer=0;
  state.selected=null;
  state.macro=0;
  state.ledSlot=5;
  state.ledTarget=productFamily(productId())==="CB"?"frames":"keyframes";
  state.ledFrame=0;
}

function updateDeviceActions() {
  const read=$("#read-device"),write=$("#write-button");
  if(!read||!write)return;
  const device=selectedDevice();
  if(!device){
    read.disabled=true;
    write.disabled=!state.config;
    write.textContent="Write to keyboard";
    write.title=state.config?"Choose the target keyboard first.":"Open or read a configuration first.";
    return;
  }
  read.disabled=false;
  read.textContent=deviceSwitchesWorkspace(device)?`Switch to ${device.product_id}`:state.loadedPort===device.port?"Refresh keymap & macros":"Read keymap & macros";
  const wrongWorkspace=!sameProductFamily(productId(),device.product_id)||(state.loadedPort&&state.loadedPort!==device.port);
  write.textContent=`Write to ${device.product_id}`;
  write.disabled=!state.config||Boolean(wrongWorkspace);
  write.title=wrongWorkspace?"Load this keyboard before writing its configuration.":"";
}

async function scanDevices() {
  $("#device-list").innerHTML='<div class="loader"></div>';
  $("#device-actions").hidden=true;
  try {
    const result=await api('/api/devices');
    state.devices=result.devices||[];
    const keyboards=state.devices.filter(device=>device.is_keyboard);
    $(".status-light").classList.toggle("online",Boolean(keyboards.length));
    if(!keyboards.length){
      state.selectedPort=null;
      $("#device-list").innerHTML='<div class="event-empty">No supported keyboard found.<br>Connect it by USB, not through the dongle.</div>';
      updateDeviceActions();
      return;
    }
    if(!keyboards.some(device=>device.port===state.selectedPort)){
      state.selectedPort=keyboards.some(device=>device.port===state.loadedPort)?state.loadedPort:null;
    }
    $("#device-list").innerHTML=keyboards.map(device=>{const active=device.port===state.loadedPort;return `<button type="button" class="device-card ${device.port===state.selectedPort?'selected':''} ${active?'active-device':''}" data-port="${esc(device.port)}"><span><strong>${esc(device.product_id)}</strong><small>${esc(device.version||'Firmware version unavailable')} · pages ${device.pages??'?'}</small></span><span class="pill">${active?'Active':'USB'}</span></button>`;}).join('');
    $$('.device-card').forEach(card=>card.addEventListener('click',()=>{state.selectedPort=card.dataset.port;$$('.device-card').forEach(node=>node.classList.toggle('selected',node===card));updateDeviceActions();}));
    $("#device-actions").hidden=false;
    updateDeviceActions();
  }catch(error){$("#device-list").innerHTML=`<div class="event-empty">${esc(error.message)}</div>`;toast('Device scan failed',error.message,'error');}
}

async function readDevice() {
  if(!state.selectedPort)return;
  const port=state.selectedPort;
  const button=$("#read-device");button.disabled=true;button.textContent='Reading…';
  try{
    const requestedLayers=state.config&&sameProductFamily(productId(),selectedDevice()?.product_id)?layers().length||7:7;
    const result=await api('/api/device/read',{method:'POST',body:JSON.stringify({port,layers:requestedLayers})});
    const switching=state.loadedPort?state.loadedPort!==port:Boolean(state.config&&!sameProductFamily(productId(),result.device.product_id));
    if(switching)stashDeviceDocument();
    const restored=switching&&restoreDeviceDocument(port,result.device.product_id);
    const preserved=Boolean(state.config)&&(!switching||restored);
    const restoredFromDisk=!preserved&&Boolean(result.stored_config);
    let keptLocalMacros=0;
    if(preserved){
      pushUndo();
      const localMacros=clone(state.config.macro_key||[]);
      state.config.key_layer={valid:1,layer_num:result.layers.length,layer_data:result.layers.map(layer=>({layer}))};
      // CyberBoard R4 can retain macro-token assignments in its readable keymap
      // while [6,10] returns an empty macro table. Never let a refresh silently
      // destroy definitions that are still present in the local workspace/JSON.
      const preserveCyberboardMacros=productFamily(result.device.product_id)==="CB"&&!result.macros.length&&localMacros.length;
      state.config.macro_key=preserveCyberboardMacros?localMacros:result.macros;
      keptLocalMacros=preserveCyberboardMacros?localMacros.length:0;
    }else{
      state.config=clone(result.stored_config||result.blank_config);
      const localMacros=clone(state.config.macro_key||[]);
      state.config.key_layer={valid:1,layer_num:result.layers.length,layer_data:result.layers.map(layer=>({layer}))};
      const preserveCyberboardMacros=productFamily(result.device.product_id)==="CB"&&!result.macros.length&&localMacros.length;
      state.config.macro_key=preserveCyberboardMacros?localMacros:result.macros;
      keptLocalMacros=preserveCyberboardMacros?localMacros.length:0;
      state.fileName=`AM-${state.config.product_info.product_id}-config.json`;
      state.undo=[];state.redo=[];
      resetDocumentView();
    }
    state.loadedPort=port;
    state.selectedPort=port;
    markDirty();render();
    $("#device-dialog").close();
    const ledDetail=restored?'Its in-memory LED workspace was restored.':preserved?'Open LED data was preserved.':restoredFromDisk?'LEDs were restored from this machine’s last verified full write—not read from the keyboard.':'No portable LED source was available; blank local LED slots were created.';
    const macroDetail=keptLocalMacros?`Keyboard reported no macro definitions; kept ${keptLocalMacros} from this local workspace.`:result.macros.length?`${result.macros.length} macros read from the keyboard.`:result.macro_references?.length?`The keymap assigns ${result.macro_references.map(code=>decodeCode(code)).join(', ')}, but the keyboard returned no macro actions.`:'No macros reported by the keyboard.';
    const storedWarning=result.stored_warning?`\n${result.stored_warning}`:'';
    toast(switching?`Switched to ${result.device.product_id}`:'Device data loaded',`${result.layers.length} layers\n${macroDetail}\n${ledDetail}${storedWarning}`,keptLocalMacros||result.macro_references?.length||result.stored_warning?'':'success');
  }catch(error){toast('Could not read device',error.message,'error');}
  finally{button.disabled=false;updateDeviceActions();}
}

async function writeDevice() {
  if(!state.config)return;
  if(!state.selectedPort){toast('Choose a write target','Select the keyboard you intend to write.','error');showDeviceDialog();return;}
  const device=state.devices.find(item=>item.port===state.selectedPort);
  if(!device)return toast('Write unavailable','Select the connected keyboard again.','error');
  if(!sameProductFamily(productId(),device.product_id)||(state.loadedPort&&state.loadedPort!==device.port))return toast('Write unavailable','Load the selected keyboard before writing its configuration.','error');
  const validation=await validateCurrent(false);if(!validation?.ok)return;
  state.pendingWrite={device,validation};
  $("#write-title").textContent=`Write to ${device.product_id}`;
  $("#write-token").textContent=device.product_id;
  const led=validation.led_frames||{};
  $("#write-summary").innerHTML=`<span><strong>${validation.layers}</strong><small>layers</small></span><span><strong>${validation.macros}</strong><small>macros</small></span><span><strong>${validation.frame_plan?.total||0}</strong><small>USB frames</small></span><span><strong>${led.display||0}</strong><small>display frames</small></span><span><strong>${led.per_key||0}</strong><small>per-key frames</small></span><span><strong>${led.edge||0}</strong><small>edge frames</small></span>`;
  const status=$("#write-status");
  status.className='write-status';
  status.textContent=validation.warnings.length?validation.warnings.join(' '):'Nothing is sent until the button below is enabled and pressed.';
  const input=$("#write-confirmation");input.value='';
  $("#confirm-write").disabled=true;
  $("#device-dialog").close();
  $("#write-dialog").returnValue='';
  $("#write-dialog").showModal();
  setTimeout(()=>input.focus(),50);
}

async function confirmDeviceWrite() {
  const pending=state.pendingWrite;if(!pending)return;
  const verifyOnly=Boolean(pending.verifyOnly);
  const typedConfirmation=$("#write-confirmation").value.trim();
  if(typedConfirmation.toUpperCase()!==pending.device.product_id.toUpperCase())return;
  const confirmation=pending.device.product_id;
  const button=$("#confirm-write"),cancel=$("#cancel-write"),close=$("#cancel-write-x"),input=$("#write-confirmation"),status=$("#write-status");
  button.disabled=true;cancel.disabled=true;close.disabled=true;input.disabled=true;
  button.textContent=verifyOnly?'Verifying accepted write…':`Writing ${pending.validation.frame_plan?.total||''} frames…`;
  status.className='write-status working';status.textContent=verifyOnly?'Reading the keymap again without resending the configuration.':'Writing configuration. Keep the cable connected; verification follows automatically.';
  try{
    const endpoint=verifyOnly?'/api/device/verify':'/api/device/write';
    const result=await api(endpoint,{method:'POST',body:JSON.stringify({port:pending.device.port,config:state.config,confirmation})});
    markDirty(false);$("#write-dialog").close();state.pendingWrite=null;
    toast('Write verified',`${result.device.product_id} · ${result.frames} configuration frames · ${result.macros} macros\nSnapshot ${result.snapshot}`,'success');
  }catch(error){
    if(error.accepted){
      pending.verifyOnly=true;
      status.className='write-status error';status.textContent=error.message;
      toast('Write accepted; verification incomplete','Use Retry verification—the configuration will not be resent.','error');
    }else{
      status.className='write-status error';status.textContent=`Write failed: ${error.message}`;
      toast('Write failed',error.message,'error');
    }
  }finally{
    cancel.disabled=false;close.disabled=false;input.disabled=false;button.textContent=pending.verifyOnly?'Retry verification':'Write full configuration';
    button.disabled=input.value.trim().toUpperCase()!==pending.device.product_id.toUpperCase();
  }
}

function showDeviceDialog(){const dialog=$("#device-dialog");if(!dialog.open)dialog.showModal();scanDevices();}

$("#open-button").addEventListener("click",()=>$("#open-input").click());
$("#empty-open").addEventListener("click",()=>$("#open-input").click());
$("#merge-button").addEventListener("click",()=>$("#merge-input").click());
$("#open-input").addEventListener("change",event=>readFiles(event.currentTarget,false));
$("#merge-input").addEventListener("change",event=>readFiles(event.currentTarget,true));
$("#macro-import-input").addEventListener("change",event=>importMacros(event.currentTarget));
$("#save-button").addEventListener("click",saveConfig);
$("#backup-before-write").addEventListener("click",saveConfig);
$("#write-button").addEventListener("click",writeDevice);
$("#device-button").addEventListener("click",showDeviceDialog);
$("#read-device").addEventListener("click",readDevice);
$("#confirm-write").addEventListener("click",confirmDeviceWrite);
$("#write-confirmation").addEventListener("input",event=>{$("#confirm-write").disabled=!state.pendingWrite||event.target.value.trim().toUpperCase()!==state.pendingWrite.device.product_id.toUpperCase();});
$("#write-confirmation").addEventListener("keydown",event=>{if(event.key==='Enter'){event.preventDefault();if(!$("#confirm-write").disabled)confirmDeviceWrite();}});
$("#write-dialog").addEventListener("close",()=>{if($("#write-dialog").returnValue==='cancel')state.pendingWrite=null;});
$("#undo-button").addEventListener("click",undo);
$("#redo-button").addEventListener("click",redo);
$("#validate-button").addEventListener("click",()=>validateCurrent());
$$('.nav-item').forEach(item=>item.addEventListener('click',()=>{state.recording=false;state.screen=item.dataset.screen;render();}));
document.addEventListener('keydown',event=>{
  if(state.recording){recordEvent(event,true);return;}
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='z'){event.preventDefault();event.shiftKey?redo():undo();}
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveConfig();}
});
document.addEventListener('keyup',event=>{if(state.recording)recordEvent(event,false);});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});

(async function boot(){
  updateMeta();
  if(!token){toast('Missing local session token','Launch this page with AM Configurator.','error');return;}
  try{
    const result=await api('/api/config');
    if(result.config){state.config=result.config;state.fileName=`AM-${productId()}-config.json`;}
    render();
    scanDevices();
  }catch(error){toast('Could not start configurator',error.message,'error');}
})();
