"use strict";

const queryToken = new URLSearchParams(location.search).get("token") || "";
if (queryToken) sessionStorage.setItem("am-configurator-token", queryToken);
const token = queryToken || sessionStorage.getItem("am-configurator-token") || "";
if (queryToken) history.replaceState({}, "", `${location.pathname}${location.hash}`);

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clone = value => JSON.parse(JSON.stringify(value));
const esc = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
const {ROUTES, STAGES, createLightingState, createPaintStrokeController, formatLightingHash, nextGridIndex, parseLightingHash, projectLightingJob, reduceLightingState, routeAvailability} = LightingState;
const {createReviewView, renderReview, reviewBlockedMessage} = LightingReview;
const {DEVICE_TARGETS, renderTargetControls} = LightingTargets;
const LIGHTING_SESSION_KEY = "am-lighting-session";
let activePaintStrokeController = null;

function restoredLightingState() {
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem(LIGHTING_SESSION_KEY) || "{}"); } catch (error) {}
  const parsed = parseLightingHash(location.hash);
  const hasRoute = /^#\//.test(location.hash);
  return {
    lighting: createLightingState({...saved, route: hasRoute ? parsed.route : saved.route}),
    jobId: parsed.jobId || saved.activeJob?.id || null,
  };
}

const restoredLighting = restoredLightingState();

const state = {
  config: null,
  documentRevision: null,
  documentSyncEpoch: 0,
  documentSyncing: false,
  documentSyncError: "",
  fileName: "AM-config.json",
  dirty: false,
  lighting: restoredLighting.lighting,
  lightingJobId: restoredLighting.jobId,
  layer: 0,
  selected: null,
  macro: 0,
  recording: false,
  recordLast: 0,
  ledSlot: 5,
  ledTarget: "keyframes",
  ledFrame: 0,
  ledPixel: 0,
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
  capabilities: null,
  settings: null,
  aiStatus: null,
  localModels: {available:null,models:[],loading:false},
  settingsReturnRoute: null,
  settingsReturnDialog: false,
  settingsSaveBusy: false,
  aiPrompt: "",
  conceptQuantity: 1,
  conceptManifest: null,
  conceptExpectedCount: 0,
  conceptSubmitting: false,
  conceptError: "",
  conceptPollTimer: null,
  conceptPollEpoch: 0,
  conceptPollFailures: 0,
  conceptAssetUrls: new Map(),
  conceptAssetLoads: new Set(),
  conceptDestination: null,
  animationMotion: "",
  animationLoopMode: "smooth",
  animationSubmitting: false,
  animationError: "",
  reviewTab: "device",
  reviewFrameIndex: 0,
  mappedLightingResults: new Map(),
  mappedLightingResultLoads: new Set(),
  proceduralRecipes: new Map(),
  proceduralRecipeLoads: new Set(),
  library: {
    jobs: [],
    details: new Map(),
    detailLoads: new Set(),
    assetUrls: new Map(),
    assetLoads: new Set(),
    assetErrors: new Map(),
    filter: "all",
    query: "",
    selectedJobId: null,
    loaded: false,
    loading: false,
    error: "",
    warnings: [],
    epoch: 0,
    searchTimer: null,
  },
};
let incompatibleResolver = null;

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

function documentSynchronized() {
  return Boolean(state.config&&state.documentRevision&&!state.documentSyncing);
}

async function synchronizeOpenDocument() {
  const config=state.config;
  const epoch=++state.documentSyncEpoch;
  state.documentRevision=null;
  state.documentSyncError="";
  state.documentSyncing=Boolean(config);
  if(!config)return null;
  try{
    const result=await api("/api/document/sync",{method:"POST",body:JSON.stringify({config})});
    if(epoch!==state.documentSyncEpoch||state.config!==config)return null;
    state.documentRevision=result.revision;
    return result.revision;
  }catch(error){
    if(epoch===state.documentSyncEpoch){state.documentSyncError=error.message||"The open document could not be synchronized.";}
    return null;
  }finally{
    if(epoch===state.documentSyncEpoch)state.documentSyncing=false;
  }
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

function productLabel(value) {
  const family=productFamily(value);
  if(family==="80")return "Relic 80";
  if(family==="ALICE")return "AFA / AFA 2";
  if(family==="CB")return "CyberBoard";
  return String(value||"Unknown keyboard");
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
  $("#dirty-dot").classList.toggle("visible",state.dirty);
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

function chooseIncompatibleProfile(config,fileName,target,compatibility,canImport) {
  const sourceId=config?.product_info?.product_id||compatibility.source_product_id||"?";
  const targetId=target.product_id||compatibility.target_product_id||"?";
  const sourceName=`${productLabel(sourceId)} (${sourceId})`;
  const targetName=target.label||`${productLabel(targetId)} (${targetId})`;
  $("#incompatible-source").textContent=sourceName;
  $("#incompatible-target").textContent=targetName;
  $("#incompatible-message").textContent=target.kind==="document"
    ? `${fileName} is for ${sourceName}; the open document is ${targetName}. These profiles cannot be merged.`
    : `${fileName} is for ${sourceName}; the connected keyboard is ${targetName}. This profile cannot be written to that keyboard.`;
  const importButton=$("#import-incompatible-macros");
  importButton.hidden=!canImport;
  importButton.textContent=compatibility.macro_count===1?"Import 1 macro only":`Import ${compatibility.macro_count} macros only`;
  $("#incompatible-macro-note").textContent=canImport
    ? `The ${compatibility.macro_count} validated macro definition${compatibility.macro_count===1?' is':'s are'} portable. Importing replaces the macros in the current ${productLabel(targetId)} workspace without opening this profile.`
    : compatibility.macro_error||"This profile has no portable modern macros.";
  const dialog=$("#incompatible-dialog");
  dialog.returnValue="";
  if(dialog.open)dialog.close();
  return new Promise(resolve=>{
    incompatibleResolver=resolve;
    dialog.showModal();
  });
}

function resolveIncompatibleProfile(choice) {
  const resolve=incompatibleResolver;
  incompatibleResolver=null;
  const dialog=$("#incompatible-dialog");
  if(dialog.open)dialog.close();
  if(resolve)resolve(choice);
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
    const families=new Set(configs.map(config=>productFamily(config?.product_info?.product_id)).filter(Boolean));
    if(families.size>1)throw new Error("The selected JSON files belong to different keyboard families and cannot be combined.");
    const incoming=mergeConfigs(configs);
    if(!incoming?.key_layer)throw new Error("No key_layer was found in the selected JSON.");

    const activeDevice=state.devices.find(device=>device.port===state.loadedPort)||selectedDevice();
    const target=merge&&state.config
      ? {product_id:productId(),label:`${productLabel(productId())} (${productId()})`,kind:"document"}
      : !merge&&activeDevice?activeDevice:null;
    let effectiveMerge=merge;
    if(target){
      const compatibility=await api("/api/config/compatibility",{method:"POST",body:JSON.stringify({config:incoming,target_product_id:target.product_id})});
      if(!compatibility.compatible){
        const canImport=Boolean(state.config)&&sameProductFamily(productId(),target.product_id)&&compatibility.can_import_macros;
        const choice=await chooseIncompatibleProfile(incoming,files[0].name,target,compatibility,canImport);
        if(choice==="cancel")return;
        if(choice==="macros"){
          await importMacrosFromConfig(incoming,files[0].name);
          return;
        }
        effectiveMerge=false;
      }
    }

    const combined=effectiveMerge&&state.config?mergeConfigs([state.config,...configs]):incoming;
    if (!combined?.key_layer) throw new Error("No key_layer was found in the selected JSON.");
    if (!effectiveMerge) {
      stashDeviceDocument();
      state.loadedPort = null;
    }
    if (effectiveMerge && state.config) pushUndo();
    state.config = combined;
    state.documentRevision=null;
    state.fileName = cleanFileName(files[0].name);
    if (!effectiveMerge) resetDocumentView();
    else state.ledFrame = 0;
    state.undo = [];
    state.redo = [];
    if(!await synchronizeOpenDocument())throw new Error(state.documentSyncError||"The opened document could not be synchronized.");
    markDirty(effectiveMerge);
    updateMeta();
    render();
    toast(effectiveMerge ? "Configurations merged" : "Configuration opened", `${productId()} · ${layers().length} layers · ${(state.config.macro_key || []).length} macros`, "success");
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
// CyberBoard profile JSON stores its 40×5 display row-first: index=y*40+x.
// Keep the editor grid in that same order so its preview matches the keyboard.
const CB_DISPLAY_MAP = Array.from({length:200},(_,index)=>index);
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
    targets:DEVICE_TARGETS.CB,
  },
  ALICE: {
    name:"AFA", keyMap:AFA_LED_MAP, keyColumns:16, keyRaster:"16×5", physicalLayout:AFA_LED_LAYOUT,
    targets:DEVICE_TARGETS.ALICE,
  },
  "80": {
    name:"Relic 80", keyMap:RELIC_LED_MAP, keyColumns:17, keyRaster:"18×7",
    targets:DEVICE_TARGETS["80"],
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
  renderRoute();
  renderLightingJobStrip();
  updateMeta();
}

function renderScreen() {
  renderRoute();
}

function persistLightingState() {
  try { sessionStorage.setItem(LIGHTING_SESSION_KEY, JSON.stringify(state.lighting)); } catch (error) {}
}

function navigateTo(route, {replace = false, focusHeading = false} = {}) {
  state.recording = false;
  state.lighting = reduceLightingState(state.lighting, {type: "NAVIGATE", route}).state;
  persistLightingState();
  const jobId = state.lighting.activeJob?.id || state.lightingJobId;
  const hash = formatLightingHash(state.lighting.route, jobId);
  const nextUrl = `${location.pathname}${location.search}${hash}`;
  history[replace ? "replaceState" : "pushState"]({}, "", nextUrl);
  render();
  if (focusHeading) {
    const heading = state.lighting.route === ROUTES.SETTINGS ? $("#settings-title") : $("#lighting-title");
    heading?.focus({preventScroll: true});
  }
}

function documentDescriptor() {
  if (!state.config) return null;
  const targets = activeLedModel().targets.map(target => target.key);
  return {
    family: productFamily(productId()),
    productId: productId(),
    slots: [5, 6, 7],
    supportedTargets: targets,
  };
}

function renderRoute() {
  stopPlayback(false);
  let route = state.lighting.route;
  if (route === ROUTES.CREATE && !aiReady() && !state.lighting.activeJob) {
    state.lighting = reduceLightingState(state.lighting, {type: "NAVIGATE", route: ROUTES.EDIT}).state;
    route = ROUTES.EDIT;
    persistLightingState();
    history.replaceState({}, "", `${location.pathname}${location.search}${formatLightingHash(route)}`);
  }
  $("#empty-state").hidden = true;
  $("#screen").hidden = true;
  $("#lighting-shell").hidden = true;
  $("#settings-screen").hidden = true;

  $$(".nav-item").forEach(item => {
    const active = item.dataset.route === route
      || (item.dataset.route === ROUTES.EDIT && route.startsWith("lighting/"));
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  const settingsActive = route === ROUTES.SETTINGS;
  $("#settings-button").classList.toggle("active", settingsActive);
  if (settingsActive) $("#settings-button").setAttribute("aria-current", "page");
  else $("#settings-button").removeAttribute("aria-current");

  if (route === ROUTES.SETTINGS) {
    $("#settings-screen").hidden = false;
    populateSettings();
    return;
  }
  if (route === ROUTES.CREATE || route === ROUTES.LIBRARY || route === ROUTES.EDIT) {
    $("#lighting-shell").hidden = false;
    renderLightingShell();
    return;
  }
  if (!state.config) {
    const label = route === ROUTES.MACROS ? "edit macros" : "edit a keymap";
    $("#empty-title").textContent = `Open a configuration to ${label}.`;
    $("#empty-state").hidden = false;
    return;
  }
  $("#screen").hidden = false;
  if (route === ROUTES.KEYMAP) renderKeymap();
  else if (route === ROUTES.MACROS) renderMacros();
}

function renderLightingJobStrip() {
  const strip = $("#lighting-job-strip");
  const job = state.lighting.activeJob;
  strip.hidden = !job;
  if (!job) return;
  const phase = job.phase ? job.phase.replaceAll("_", " ") : "Ready";
  const phaseLabel = phase.charAt(0).toUpperCase() + phase.slice(1);
  if ($("#lighting-job-phase").textContent !== phaseLabel) {
    $("#lighting-job-phase").textContent = phaseLabel;
    $("#lighting-job-phase-live").textContent = `Lighting job: ${phaseLabel}`;
  }
  const progress = job.progress;
  $("#lighting-job-detail").textContent = progress
    ? `${progress.completed} of ${progress.total} saved`
    : "Your work is saved locally as it completes.";
  const progressNode = $("#lighting-job-progress");
  progressNode.hidden = !progress || progress.total <= 0;
  if (!progressNode.hidden) {
    progressNode.max = progress.total;
    progressNode.value = Math.min(progress.total, progress.completed);
  }
  $("#lighting-job-cancel").disabled = !["in_progress", "accepted", "processing"].includes(job.status);
}

function clearConceptAssetUrls() {
  for(const url of state.conceptAssetUrls.values())URL.revokeObjectURL(url);
  state.conceptAssetUrls.clear();
  state.mappedLightingResults.clear();
  state.mappedLightingResultLoads.clear();
}

function clearLibraryAssetUrls() {
  for(const url of state.library.assetUrls.values())URL.revokeObjectURL(url);
  state.library.assetUrls.clear();
  state.library.assetErrors.clear();
}

function libraryFilterQuery() {
  const params=new URLSearchParams({page:"1",limit:"24"});
  if(state.library.filter==="animation")params.set("kind","preview_animation");
  else if(state.library.filter==="partial")params.set("status","partial");
  if(state.library.query.trim())params.set("query",state.library.query.trim());
  return params.toString();
}

function libraryDate(value) {
  const date=new Date(value);
  return Number.isNaN(date.valueOf())?"Unknown date":date.toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"});
}

function libraryStatusLabel(value) {
  const label=String(value||"saved").replaceAll("_"," ");
  return label.charAt(0).toUpperCase()+label.slice(1);
}

function libraryCoverAsset(detail) {
  const procedural=detail?.assets?.find(asset=>asset.kind==="preview_animation")
    || detail?.assets?.find(asset=>asset.kind==="raster_animation");
  if(procedural)return procedural;
  const selected=detail?.candidates?.find(candidate=>candidate.candidate_id===detail.selected_candidate_id);
  const first=selected||detail?.candidates?.[0];
  if(first?.asset_id)return {asset_id:first.asset_id,mime_type:first.mime_type||"image/png"};
  return detail?.assets?.find(asset=>asset.kind==="preview_poster")
    || detail?.assets?.find(asset=>["preview_animation","source_video"].includes(asset.kind))
    || null;
}

async function loadLibraryAsset(jobId,assetId,{retry=false}={}) {
  const key=`${jobId}:${assetId}`;
  if(state.library.assetUrls.has(key)||state.library.assetLoads.has(key))return;
  state.library.assetLoads.add(key);
  state.library.assetErrors.delete(key);
  try{
    const response=await fetch(`/api/lighting/assets/${encodeURIComponent(jobId)}/${encodeURIComponent(assetId)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load asset (${response.status})`);}
    const url=URL.createObjectURL(await response.blob());
    const previous=state.library.assetUrls.get(key);
    if(previous&&previous!==url)URL.revokeObjectURL(previous);
    state.library.assetUrls.set(key,url);
    if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }catch(error){
    if(retry)state.library.assetErrors.set(key,error.message);
    else{
      state.library.assetErrors.set(key,"Retrying…");
      setTimeout(()=>loadLibraryAsset(jobId,assetId,{retry:true}),250);
    }
  }finally{
    state.library.assetLoads.delete(key);
    if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }
}

async function ensureLibraryJobDetail(jobId) {
  if(state.library.details.has(jobId)||state.library.detailLoads.has(jobId))return;
  const epoch=state.library.epoch;
  state.library.detailLoads.add(jobId);
  try{
    const detail=await api(`/api/lighting/library/${encodeURIComponent(jobId)}`);
    if(epoch!==state.library.epoch)return;
    state.library.details.set(jobId,detail);
    const cover=libraryCoverAsset(detail);
    if(cover)void loadLibraryAsset(jobId,cover.asset_id);
    if(state.library.selectedJobId===jobId){
      for(const asset of detail.assets||[]){
        if(["concept","selected_still","preview_poster","preview_animation","source_video"].includes(asset.kind))void loadLibraryAsset(jobId,asset.asset_id);
      }
    }
    if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }catch(error){
    if(epoch===state.library.epoch){state.library.error=error.message;if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();}
  }finally{state.library.detailLoads.delete(jobId);}
}

async function loadLibrary({force=false}={}) {
  if(state.library.loading||(!force&&state.library.loaded))return;
  state.library.loading=true;
  state.library.error="";
  const epoch=++state.library.epoch;
  if(force){clearLibraryAssetUrls();state.library.details.clear();state.library.selectedJobId=null;}
  renderLibrary();
  try{
    const result=await api(`/api/lighting/library?${libraryFilterQuery()}`);
    if(epoch!==state.library.epoch)return;
    state.library.jobs=result.jobs||[];
    state.library.warnings=result.errors||[];
    state.library.loaded=true;
    for(const job of state.library.jobs)void ensureLibraryJobDetail(job.job_id);
  }catch(error){
    if(epoch===state.library.epoch){state.library.jobs=[];state.library.error=error.message;state.library.loaded=true;}
  }finally{
    if(epoch===state.library.epoch){state.library.loading=false;renderLibrary();}
  }
}

function libraryEmptyMarkup() {
  if(state.library.loading)return '<div class="library-empty"><div class="loader"></div><strong>Loading your Library…</strong></div>';
  if(state.library.error)return `<div class="library-empty"><strong>Library could not be loaded.</strong><p>${esc(state.library.error)}</p><button type="button" class="button ghost" data-library-retry>Try again</button></div>`;
  if(!state.settings?.library?.current_root)return '<div class="library-empty"><strong>Choose a Library folder to save generated media.</strong><p>Settings controls where generated assets are banked.</p><button type="button" class="button primary" data-library-settings>Open Settings</button></div>';
  return '<div class="library-empty"><strong>Nothing here yet.</strong><p>Generated animations and historical media will appear here as they are saved.</p></div>';
}

function libraryCardMarkup(job) {
  const detail=state.library.details.get(job.job_id);
  const cover=libraryCoverAsset(detail);
  const url=cover&&state.library.assetUrls.get(`${job.job_id}:${cover.asset_id}`);
  const kind=detail?.assets?.some(asset=>["preview_animation","raster_animation"].includes(asset.kind))?"Animation":detail?.assets?.some(asset=>asset.kind==="source_video")?"Video":"Stills";
  return `<button type="button" class="library-card" data-library-job="${esc(job.job_id)}">
    <span class="library-card-poster">${url?`<img src="${esc(url)}" alt="">`:'<span class="library-card-placeholder" aria-hidden="true">✦</span>'}</span>
    <span class="library-card-copy"><strong>${esc(job.prompt)}</strong><span>${kind} · ${libraryStatusLabel(job.status)} · ${libraryDate(job.updated_at)}</span><small>${job.asset_count} saved asset${job.asset_count===1?"":"s"}</small></span>
  </button>`;
}

function libraryMediaMarkup(jobId,asset,index,detail) {
  const url=state.library.assetUrls.get(`${jobId}:${asset.asset_id}`);
  const label=asset.kind.replaceAll("_"," ");
  const loadError=state.library.assetErrors.get(`${jobId}:${asset.asset_id}`);
  if(!url&&loadError&&loadError!=="Retrying…")return `<div class="library-media-card failed"><strong>Could not load this ${esc(label)}.</strong><small>${esc(loadError)}</small><button type="button" class="button ghost" data-library-asset-retry="${esc(asset.asset_id)}" data-library-asset-job="${esc(jobId)}">Retry</button></div>`;
  if(!url)return `<div class="library-media-card loading"><span class="library-card-placeholder">${loadError||"Loading…"}</span><small>${esc(label)}</small></div>`;
  if(asset.mime_type==="video/mp4")return `<figure class="library-media-card"><video src="${esc(url)}" controls muted playsinline preload="metadata"></video><figcaption>${esc(label)}</figcaption></figure>`;
  return `<figure class="library-media-card"><img src="${esc(url)}" alt="Saved lighting asset ${index+1}"><figcaption><span>${esc(label)}</span></figcaption></figure>`;
}

function libraryDetailMarkup(jobId) {
  const summary=state.library.jobs.find(job=>job.job_id===jobId);
  const detail=state.library.details.get(jobId);
  if(!detail)return '<div class="library-empty"><div class="loader"></div><strong>Loading saved media…</strong></div>';
  const media=(detail.assets||[]).filter(asset=>["concept","selected_still","preview_poster","preview_animation","raster_animation","source_video"].includes(asset.kind));
  return `<section class="library-detail" aria-labelledby="library-detail-title">
    <button type="button" class="library-back" data-library-back>← Library</button>
    <header><div><p class="eyebrow">${esc(libraryStatusLabel(detail.status))}</p><h2 id="library-detail-title">${esc(detail.prompt)}</h2><p>${libraryDate(detail.created_at)} · ${media.length} saved media item${media.length===1?"":"s"}</p></div><span class="pill ${detail.status==="partial"?"muted":""}">${esc(libraryStatusLabel(detail.phase||detail.status))}</span></header>
    <div class="library-media-grid">${media.length?media.map((asset,index)=>libraryMediaMarkup(jobId,asset,index,detail)).join(""):'<p class="library-no-media">This job has no viewable media yet.</p>'}</div>
    ${summary?.costs?.actual_incomplete?'<p class="library-warning">Provider cost reporting is incomplete for this item.</p>':""}
  </section>`;
}

function wireLibraryContent() {
  $$("[data-library-job]",$("#library-content")).forEach(card=>card.addEventListener("click",()=>openLibraryJob(card.dataset.libraryJob)));
  $$("[data-library-asset-retry]",$("#library-content")).forEach(button=>button.addEventListener("click",()=>loadLibraryAsset(button.dataset.libraryAssetJob,button.dataset.libraryAssetRetry,{retry:true})));
  $("[data-library-back]",$("#library-content"))?.addEventListener("click",()=>{state.library.selectedJobId=null;renderLibrary();});
  $("[data-library-retry]",$("#library-content"))?.addEventListener("click",()=>loadLibrary({force:true}));
  $("[data-library-settings]",$("#library-content"))?.addEventListener("click",openSettings);
}

function openLibraryJob(jobId) {
  state.library.selectedJobId=jobId;
  renderLibrary();
  void ensureLibraryJobDetail(jobId);
}

function renderLibrary() {
  const content=$("#library-content");
  if(!content)return;
  const selected=state.library.selectedJobId;
  if(selected)content.innerHTML=libraryDetailMarkup(selected);
  else if(state.library.jobs.length)content.innerHTML=`<div class="library-grid">${state.library.jobs.map(libraryCardMarkup).join("")}</div>`;
  else content.innerHTML=libraryEmptyMarkup();
  const status=$("#library-status");
  status.textContent=state.library.loading?"Refreshing Library…":state.library.warnings.length?"Some previously recorded Library items could not be read.":state.library.jobs.length?`${state.library.jobs.length} saved job${state.library.jobs.length===1?"":"s"}`:"";
  status.classList.toggle("warning",Boolean(state.library.warnings.length));
  $("#library-reveal").disabled=!state.settings?.library?.current_root;
  $$("[data-library-filter]").forEach(button=>{const active=button.dataset.libraryFilter===state.library.filter;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
  wireLibraryContent();
  if(!state.library.loaded&&!state.library.loading)void loadLibrary();
}

async function loadConceptAsset(jobId,assetId) {
  const key=`${jobId}:${assetId}`;
  if(state.conceptAssetUrls.has(key)||state.conceptAssetLoads.has(key))return;
  state.conceptAssetLoads.add(key);
  try{
    const response=await fetch(`/api/lighting/assets/${encodeURIComponent(jobId)}/${encodeURIComponent(assetId)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load concept (${response.status})`);}
    const url=URL.createObjectURL(await response.blob());
    if(state.conceptManifest?.job_id!==jobId){URL.revokeObjectURL(url);return;}
    const previous=state.conceptAssetUrls.get(key);
    if(previous&&previous!==url)URL.revokeObjectURL(previous);
    state.conceptAssetUrls.set(key,url);
    refreshGenerationDialog();
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.conceptError=error.message;refreshGenerationDialog();}
  }finally{state.conceptAssetLoads.delete(key);}
}

async function loadMappedLightingResult(jobId,assetId) {
  const key=`${jobId}:${assetId}`;
  if(state.mappedLightingResults.has(key)||state.mappedLightingResultLoads.has(key))return;
  state.mappedLightingResultLoads.add(key);
  try{
    const response=await fetch(`/api/lighting/assets/${encodeURIComponent(jobId)}/${encodeURIComponent(assetId)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load LED result (${response.status})`);}
    const result=await response.json();
    if(!result||typeof result!=="object"||!result.tracks)throw new Error("The saved LED result is invalid.");
    if(state.conceptManifest?.job_id!==jobId)return;
    state.mappedLightingResults.set(key,result);
    refreshGenerationDialog();
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.animationError=error.message;refreshGenerationDialog();}
  }finally{state.mappedLightingResultLoads.delete(key);}
}

function scheduleLightingJobPoll(jobId,delay=800) {
  if(state.conceptPollTimer)clearTimeout(state.conceptPollTimer);
  const epoch=state.conceptPollEpoch;
  state.conceptPollTimer=setTimeout(()=>pollLightingJob(jobId,epoch),delay);
}

async function pollLightingJob(jobId,epoch=state.conceptPollEpoch) {
  if(epoch!==state.conceptPollEpoch||state.lighting.activeJob?.id!==jobId)return;
  try{
    const manifest=await api(`/api/lighting/jobs/${encodeURIComponent(jobId)}`);
    if(epoch===state.conceptPollEpoch&&state.lighting.activeJob?.id===jobId)syncLightingJob(manifest,{renderPage:false});
  }catch(error){
    if(epoch!==state.conceptPollEpoch||state.lighting.activeJob?.id!==jobId)return;
    if(error.status===400||error.status===404){syncLightingJob(null,{renderPage:false});return;}
    state.conceptError=error.message;
    state.conceptPollFailures++;
    refreshGenerationDialog();
    scheduleLightingJobPoll(jobId,Math.min(5000,800*(2**Math.min(3,state.conceptPollFailures))));
  }
}

async function restoreLightingJob() {
  if (!state.lightingJobId) return;
  const jobId=state.lightingJobId;
  const epoch=++state.conceptPollEpoch;
  if(state.conceptPollTimer)clearTimeout(state.conceptPollTimer);
  try {
    const manifest=await api(`/api/lighting/jobs/${encodeURIComponent(jobId)}`);
    if(epoch===state.conceptPollEpoch&&state.lightingJobId===jobId)syncLightingJob(manifest);
  } catch (error) {
    if (epoch===state.conceptPollEpoch&&state.lightingJobId===jobId&&(error.status === 404 || error.status === 400)) syncLightingJob(null);
    else if(epoch===state.conceptPollEpoch&&state.lightingJobId===jobId)scheduleLightingJobPoll(jobId);
  }
}

async function cancelLightingJob() {
  const job = state.lighting.activeJob;
  if (!job || $("#lighting-job-cancel").disabled) return;
  state.conceptPollEpoch++;
  if(state.conceptPollTimer)clearTimeout(state.conceptPollTimer);
  $("#lighting-job-cancel").disabled = true;
  try {
    await api(`/api/lighting/jobs/${encodeURIComponent(job.id)}/cancel`, {method: "POST", body: "{}"});
    await restoreLightingJob();
  } catch (error) {
    toast("Could not cancel lighting job", error.message, "error");
    renderLightingJobStrip();
  }
}

function documentRequirementMarkup(message) {
  return `<div class="route-requirement"><span class="route-requirement-icon" aria-hidden="true">⌨</span><div><strong>Open a keyboard configuration first.</strong><p>${esc(message)} Use Open or Devices in the toolbar above.</p></div></div>`;
}

function renderLightingShell() {
  const route = state.lighting.route;
  const available = routeAvailability(route, documentDescriptor(), {aiReady: aiReady(), hasActiveJob: Boolean(state.lighting.activeJob)});
  const routes = [ROUTES.EDIT, ROUTES.LIBRARY];
  const names = ["edit", "library"];
  routes.forEach((candidate, index) => {
    const selected = route === candidate || (candidate === ROUTES.EDIT && route === ROUTES.CREATE);
    const tab = $(`#lighting-${names[index]}-tab`);
    const panel = $(`#lighting-${names[index]}-panel`);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    panel.hidden = !selected;
  });

  $("#lighting-destination-product").textContent = state.config
    ? `${productLabel(productId())} · ${productId()}`
    : "No document open";
  const destinationLocked = Boolean(state.lighting.activeJob);
  $$('[data-lighting-slot]').forEach(button => {
    const selected = Number(button.dataset.lightingSlot) === state.ledSlot;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.disabled = !state.config || destinationLocked;
  });

  const targetHost = $("#lighting-target-controls");
  const targets = state.config ? activeLedModel().targets : [];
  if (targets.length && !targets.some(target => target.key === state.ledTarget)) state.ledTarget = targets[0].key;
  renderTargetControls(targetHost,targets,state.ledTarget,destinationLocked,target=>{
    state.ledTarget = target;
    state.ledFrame = 0;
    state.ledPixel = 0;
    renderLightingShell();
    focusSelectedTarget(target);
  });

  $$("[data-lighting-stage]").forEach(step => {
    if (step.dataset.lightingStage === state.lighting.create.stage) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });

  if (route === ROUTES.EDIT || route === ROUTES.CREATE) {
    if (!available.available) {
      $("#lighting-edit-content").innerHTML = documentRequirementMarkup("Edit works directly on the custom lighting slots in an open document.");
    } else renderLightingEdit();
  }
  if (route === ROUTES.LIBRARY) renderLibrary();
  const generateOpen=$("#lighting-generate-open");
  generateOpen.hidden=!aiReady();
  generateOpen.disabled = !state.config || !pageData().length || !aiReady() || !documentSynchronized();
  renderGenerationDialog();
  if (route === ROUTES.CREATE && (aiReady() || state.lighting.activeJob)) setTimeout(openGenerationDialog, 0);
}

function focusSelectedTarget(target = state.ledTarget) {
  $$('[data-lighting-target]').find(button => button.dataset.lightingTarget === String(target))?.focus();
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

async function loadImportableMacros(config) {
  return api("/api/macros/import",{method:"POST",body:JSON.stringify({config})});
}

function confirmMacroReplacement(existingCount,incomingCount,fileName) {
  return !existingCount||confirm(`Replace the ${existingCount} macros in this workspace with ${incomingCount} from ${fileName}?`);
}

function applyImportedMacros(result) {
  const incoming=result.macros||[];
  mutate(()=>{state.config.macro_key=clone(incoming);state.macro=0;});
  const events=incoming.reduce((sum,macro)=>sum+(macro.layer_key||[]).length,0);
  const connected=incoming.filter(macro=>layers().some(layer=>(layer.layer||[]).some(code=>String(code).toUpperCase()===macro.original_key))).map(macro=>decodeCode(macro.original_key));
  toast("Macros imported",`${incoming.length} macros · ${events} events from ${result.product_id}${connected.length?` · ${connected.join(', ')} connected to this keymap`:''}`,"success");
}

async function importMacrosFromConfig(config,fileName) {
  if(!state.config)return false;
  try{
    const result=await loadImportableMacros(config);
    const incoming=result.macros||[];
    if(!confirmMacroReplacement(macros().length,incoming.length,fileName))return false;
    applyImportedMacros(result);
    return true;
  }catch(error){toast("Could not import macros",error.message,"error");return false;}
}

async function importMacros(input) {
  const file=input.files?.[0];
  input.value="";
  if(!file||!state.config)return;
  try{
    const parsed=JSON.parse(await file.text());
    await importMacrosFromConfig(parsed,file.name);
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
  if (!state.recording || state.lighting.route !== ROUTES.MACROS || event.repeat) return;
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

function renderLightingEdit() {
  if (!pageData().length) {
    $("#lighting-edit-content").innerHTML=`<div class="empty-state lighting-edit-empty"><p class="eyebrow">Key-only export</p><h1>No LED pages loaded.</h1><p>Merge the matching lighting JSON to preserve your existing effects, or create three blank custom slots.</p><div class="header-controls"><button id="merge-led" class="button ghost large">Merge lighting JSON</button><button id="create-led" class="button primary large">Create blank slots</button></div></div>`;
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
  const focusablePixelCount=physicalLayout?.length||pixelMap.filter(index=>index>=0).length;
  state.ledPixel=Math.min(state.ledPixel,Math.max(0,focusablePixelCount-1));
  const keyLabels=layers()[0]?.layer||[];
  let pixelOrder=0;
  const rasterCells=pixelMap.map(index=>{
    if(index<0)return `<span class="pixel-spacer"></span>`;
    const position=pixelOrder++;
    const color=frame?.frame_RGB[index]||'#000000';
    return `<button class="pixel" role="gridcell" tabindex="${position===state.ledPixel?0:-1}" data-pixel="${index}" style="background:${esc(color)};--pixel-color:${esc(color)}" aria-label="LED ${index}, ${esc(color)}" title="LED ${index} · ${esc(color)}"></button>`;
  }).join("");
  const pixelCanvas=!frame?`<div class="event-empty"><button id="first-frame" class="button primary">Create first frame</button></div>`:physicalLayout?`<div class="pixel-grid physical afa-led-board" role="grid" aria-label="LED paint grid">${physicalLayout.map((item,position)=>{
    const color=frame.frame_RGB[item.index]||"#000000";
    const body=item.keyIndex===null;
    const label=body?item.label:decodeCode(keyLabels[item.keyIndex]||"#00000000");
    const description=body?'Center light':`Key ${label}, matrix ${item.keyIndex}`;
    return `<button class="pixel physical-pixel ${body?'body-led':''}" role="gridcell" tabindex="${position===state.ledPixel?0:-1}" data-pixel="${item.index}" style="left:${item.x}%;top:${item.y}%;width:${item.w}%;--rotation:${item.rotation}deg;background:${esc(color)};--pixel-color:${esc(color)}" aria-label="${esc(description)}, LED ${item.index}, ${esc(color)}" title="${esc(description)} · LED ${item.index} · ${esc(color)}"><span>${esc(label)}</span><small>LED ${item.index}</small></button>`;
  }).join("")}</div>`:`<div class="pixel-grid ${gridClass}" role="grid" aria-label="LED paint grid" style="grid-template-columns:repeat(${columns},1fr)">${rasterCells}</div>`;
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
  const targetLabel=targets.find(t=>t.key===state.ledTarget)?.label||state.ledTarget;
  const editorBody=`<div class="card-body">
        <div class="control-group" role="group" aria-labelledby="animation-source-label"><h3 id="animation-source-label" class="control-label">Animation source</h3><input id="gif-input" type="file" accept="image/gif,.gif" hidden><div class="gif-import-row"><button id="import-gif" class="button ghost">${gifButtonLabel}</button><select id="gif-resample" class="select-field" aria-label="GIF resize method"><option value="nearest" ${state.gifResample==='nearest'?'selected':''}>Crisp</option><option value="box" ${state.gifResample==='box'?'selected':''}>Balanced</option><option value="lanczos" ${state.gifResample==='lanczos'?'selected':''}>Smooth</option></select></div>${relicGifOption}<small class="control-help">${gifHelp}</small></div>
        ${edgeTools}
        <div class="control-group"><label class="control-label" for="led-color">Paint color</label><input id="led-color" class="color-picker" type="color" value="${state.ledColor}"><input id="led-color-text" class="text-field" aria-label="Paint color hex value" value="${state.ledColor}"></div>
        <div class="control-group"><label class="control-label">Brush</label><div class="button-row"><button id="fill-led" class="button ghost">Fill all</button><button id="clear-led" class="button ghost">Clear</button></div></div>
        <div class="control-group"><label class="control-label" for="brightness">Brightness</label><div class="range-row"><input id="brightness" type="range" min="0" max="100" value="${Number(page?.lightness??100)}" aria-describedby="brightness-value"><span id="brightness-value" class="range-value">${Number(page?.lightness??100)}%</span></div></div>
        <div class="control-group"><label class="control-label" for="speed">Frame duration</label><select id="speed" class="select-field">${LED_SPEEDS.map(speed=>`<option value="${speed}" ${speed===encodedSpeed?'selected':''}>${speed} ms · ${(1000/speed).toFixed(1)} fps</option>`).join("")}</select><small class="control-help">These are the timing steps exposed by Angry Miao firmware.</small></div>
      </div>`;
  $("#lighting-edit-content").innerHTML=`<div class="lighting-edit-shell"><div class="led-layout">
      <aside class="card frame-list" aria-label="Animation frames"><div class="card-header"><strong>Frames</strong><small>${frames.length}</small></div><div class="frame-items">${frames.map((item,i)=>`<button class="frame-item ${i===state.ledFrame?'active':''}" data-frame="${i}" aria-pressed="${i===state.ledFrame}" aria-label="Frame ${i+1}${i===state.ledFrame?', selected':''}"><span class="frame-thumb">${(item.frame_RGB||[]).slice(0,12).map(color=>`<i style="background:${esc(color)}"></i>`).join("")}</span><span><strong>Frame ${String(i+1).padStart(2,"0")}</strong><small>${i===state.ledFrame?'Editing':'Select'}</small></span></button>`).join("")||`<div class="event-empty">No frames</div>`}</div><div class="card-body button-row"><button id="add-frame" class="button ghost">+ Duplicate</button><button id="remove-frame" class="button ghost" ${frames.length<=1?'disabled':''}>Delete</button></div></aside>
      <section class="card led-canvas-card" aria-label="LED canvas"><div class="card-header"><strong>${esc(model.name)} · ${esc(targetLabel)}</strong><small>${mappedCount}${mappedCount===length?'':' mapped'} / ${length} stored${physicalLayout?' · Layer 1 labels':''}</small></div><div id="led-canvas" class="led-canvas ${physicalLayout?'physical-canvas':''}" role="region" aria-label="Paint the selected animation frame">${pixelCanvas}</div></section>
      <aside class="card led-controls" aria-label="Lighting controls"><div class="card-header"><strong>Frame controls</strong><button id="play-led" class="icon-button" aria-label="${state.playing?'Stop animation':'Play animation'}">${state.playing?'■':'▶'}</button></div>${editorBody}</aside>
    </div></div>`;
  wireLedEditor(columns);
}

function focusSelectedFrame() {
  $$('[data-frame]').find(button=>Number(button.dataset.frame)===state.ledFrame)?.focus();
}

function selectLightingFrame(index) {
  state.ledFrame=Number(index);
  renderLightingEdit();
  focusSelectedFrame();
}

function wireLedEditor(gridColumns) {
  activePaintStrokeController?.teardown();
  activePaintStrokeController=null;
  $$('[data-frame]').forEach(button=>button.addEventListener('click',()=>selectLightingFrame(button.dataset.frame)));
  $("#first-frame")?.addEventListener("click",()=>mutate(ensureTrack));
  $("#import-gif").addEventListener("click",()=>$("#gif-input").click());
  $("#gif-resample").addEventListener("change",event=>{state.gifResample=event.target.value;});
  $("#relic-gif-edges")?.addEventListener("change",event=>{state.relicGifEdges=event.target.checked;renderLightingEdit();});
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
  const paint = pixel => {
    const frame=currentFrame();if(!frame)return;const i=Number(pixel.dataset.pixel);frame.frame_RGB[i]=state.ledColor;pixel.style.background=state.ledColor;pixel.style.setProperty('--pixel-color',state.ledColor);pixel.title=`LED ${i} · ${state.ledColor}`;pixel.setAttribute('aria-label',`LED ${i}, ${state.ledColor}`);
  };
  const strokeController=createPaintStrokeController({releaseTarget:window,checkpoint:pushUndo,paint});
  activePaintStrokeController=strokeController;
  const pixels=$$('.pixel');
  const focusPixel=index=>{
    const next=Math.min(pixels.length-1,Math.max(0,index));
    pixels.forEach((pixel,pixelIndex)=>{pixel.tabIndex=pixelIndex===next?0:-1;});
    state.ledPixel=next;
    pixels[next]?.focus();
  };
  pixels.forEach((pixel,index)=>{
    pixel.addEventListener('focus',()=>{state.ledPixel=index;pixels.forEach((item,itemIndex)=>{item.tabIndex=itemIndex===index?0:-1;});});
    pixel.addEventListener('keydown',event=>{
      if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key)){
        event.preventDefault();
        focusPixel(nextGridIndex(index,event.key,pixels.length,gridColumns));
      }else if(event.key===' '||event.key==='Enter'){
        event.preventDefault();
        pushUndo();
        paint(pixel);
        markDirty();
      }
    });
    pixel.addEventListener('pointerdown',event=>{event.preventDefault();focusPixel(index);strokeController.pointerDown(pixel);markDirty();});
    pixel.addEventListener('pointerenter',event=>{strokeController.pointerEnter(pixel,event.buttons);});
  });
  $("#led-color").addEventListener("input",event=>{state.ledColor=event.target.value.toUpperCase();$("#led-color-text").value=state.ledColor;});
  $("#led-color-text").addEventListener("change",event=>{if(/^#[0-9a-f]{6}$/i.test(event.target.value)){state.ledColor=event.target.value.toUpperCase();renderLightingEdit();}else toast("Invalid color","Use a six-digit hex color such as #8358FF.","error");});
  $("#fill-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill(state.ledColor);}));
  $("#clear-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill("#000000");}));
  $("#brightness").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).lightness=Number(event.target.value);}));
  $("#speed").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).speed_ms=Number(event.target.value);}));
  $("#play-led").addEventListener("click",toggleLightingPlayback);
}

// Write a GIF/procedural mapping result (the shared `/api/led/gif` shape)
// into a page object in place: replace each returned track, retime a paired or
// existing Relic edge animation to the key track, and adopt the per-frame speed.
// Manual import and generated Apply therefore stay identical.
function applyLedResultToPage(page,result,primaryTarget,pairsRelicGif) {
  page.valid=1;
  for(const [trackName,trackResult] of Object.entries(result.tracks)){
    if(trackName==="spotlight_frames"){
      const count=Math.max(1,result.tracks.keyframes?.frame_count||page.keyframes?.frame_data?.length||trackResult.frame_count);
      page[trackName]={valid:1,frame_num:count,frame_data:resampleEdgeAnimation(trackResult.frames,count)};
    }else{
      page[trackName]={valid:1,frame_num:trackResult.frame_count,frame_data:trackResult.frames.map((colors,index)=>({frame_index:index,frame_RGB:colors}))};
    }
  }
  if(primaryTarget==="keyframes"&&!pairsRelicGif&&page.spotlight_frames?.frame_data?.length){
    const count=page.keyframes.frame_data.length;
    page.spotlight_frames={...page.spotlight_frames,valid:1,frame_num:count,frame_data:resampleEdgeAnimation(page.spotlight_frames.frame_data,count)};
  }
  if(result.duration_ms&&primaryTarget!=="spotlight_frames")page.speed_ms=Number(result.duration_ms);
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
    mutate(()=>{applyLedResultToPage(getPage(state.ledSlot),result,target,pairsRelicGif);state.ledFrame=0;});
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
  state.playing=true;renderLightingEdit();
  const tick=()=>{
    if(!state.playing)return;
    state.ledFrame=(state.ledFrame+1)%track.frame_data.length;
    const frame=track.frame_data[state.ledFrame];
    $$('.pixel').forEach(pixel=>{const color=frame.frame_RGB[Number(pixel.dataset.pixel)]||'#000000';pixel.style.background=color;pixel.style.setProperty('--pixel-color',color);});
    $$('.frame-item').forEach((node,i)=>{const selected=i===state.ledFrame;node.classList.toggle('active',selected);node.setAttribute('aria-pressed',String(selected));node.setAttribute('aria-label',`Frame ${i+1}${selected?', selected':''}`);});
  };
  state.playTimer=setInterval(tick,Math.max(12,Number(getPage(state.ledSlot)?.speed_ms||90)));
}

function toggleLightingPlayback() {
  if(state.playing)stopPlayback();
  else startPlayback();
  $("#play-led")?.focus();
}

function stopPlayback(rerender=true) {
  if(state.playTimer)clearInterval(state.playTimer);
  const was=state.playing;state.playTimer=null;state.playing=false;
  if(was&&rerender&&state.lighting.route===ROUTES.EDIT)renderLightingEdit();
}

// ---- AI LED generation -----------------------------------------------------

// Typed provider-error codes → actionable, user-facing copy (design §error map).
const AI_ERROR_MESSAGES = {
  config: "Generation isn’t ready. Repair the selected backend in Settings.",
  auth: "The API provider rejected the credential. Check it in Settings.",
  rate_limited: "The API provider is rate-limiting requests. Try again shortly.",
  timeout: "Generation timed out. Try a simpler prompt and try again.",
  offline: "The selected backend could not be reached.",
  moderation: "The API provider declined this prompt. Try describing the effect differently.",
  bad_response: "The selected model returned an invalid recipe. Try another prompt or model.",
  unavailable: "The selected backend is temporarily unavailable.",
};

function aiErrorMessage(error) {
  if (error?.status === 404) return "The generation job expired. Try again.";
  const code = error?.code;
  let message = AI_ERROR_MESSAGES[code] || error?.message || "Generation failed. Try again.";
  if (code === "rate_limited" && error?.retry_after) message += ` Retry after ${error.retry_after}s.`;
  return message;
}

// ---- Settings route --------------------------------------------------------

function setSettingsStatus(message, kind = "") {
  const status = $("#settings-status");
  status.className = `write-status settings-route-status ${kind}`.trim();
  status.textContent = message;
}

function finishSettings() {
  const route=state.settingsReturnRoute&&state.settingsReturnRoute!==ROUTES.SETTINGS?state.settingsReturnRoute:ROUTES.EDIT;
  const reopen=state.settingsReturnDialog;
  state.settingsReturnRoute=null;
  state.settingsReturnDialog=false;
  navigateTo(route,{focusHeading:!reopen});
  if(reopen)setTimeout(openGenerationDialog,0);
}

async function chooseLibraryFolder() {
  const button=$("#settings-choose-library");
  button.disabled=true;
  setSettingsStatus("Opening folder chooser…","working");
  try{
    let path=null;
    try{
      const result=await api("/api/native/choose-library",{method:"POST",body:"{}"});
      path=result.path;
    }catch(error){
      const bridge=window.pywebview?.api;
      if(error.status!==404||!bridge?.choose_library_folder)throw error;
      path=await bridge.choose_library_folder();
    }
    if(path){$("#settings-library-root").value=path;setSettingsStatus("Folder selected. Save changes to use it.");}
    else setSettingsStatus("No folder selected.");
  }catch(error){
    $("#settings-library-root").focus();
    setSettingsStatus(error.status===404?"Enter an absolute folder path, then save changes.":`Could not choose folder: ${error.message||error}`,"error");
  }finally{button.disabled=false;}
}

async function invokeRevealLibraryPath(path) {
  try{
    const result=await api("/api/native/reveal-library",{method:"POST",body:JSON.stringify({path})});
    return Boolean(result.revealed);
  }catch(error){
    const bridge=window.pywebview?.api;
    if(error.status!==404||!bridge?.reveal_library_path)throw error;
    return Boolean(await bridge.reveal_library_path(path));
  }
}

async function revealLibraryFolder() {
  const path=state.settings?.library?.current_root;
  if(!path)return;
  try{if(!await invokeRevealLibraryPath(path))throw new Error("The folder is unavailable.");}
  catch(error){setSettingsStatus(`Could not reveal folder: ${error.message||error}`,"error");}
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

function mismatchedDevice() {
  const device=selectedDevice();
  return state.config&&device&&!sameProductFamily(productId(),device.product_id)?device:null;
}

function updateCompatibilityBanner() {
  const banner=$("#compatibility-banner");
  if(!banner)return;
  const device=mismatchedDevice();
  banner.hidden=!device;
  if(!device)return;
  const sourceId=productId();
  const sourceName=`${productLabel(sourceId)} (${sourceId})`;
  const targetName=`${productLabel(device.product_id)} (${device.product_id})`;
  $("#compatibility-title").textContent=`${sourceName} profile · ${targetName} connected`;
  $("#compatibility-detail").textContent=`This JSON cannot be written to ${device.product_id}. Save JSON still works; keymaps and LED tracks cannot cross layouts.`;
  const saved=state.deviceDocuments.get(device.port);
  const hasMacros=Array.isArray(state.config.macro_key)&&state.config.macro_key.length>0;
  $("#import-banner-macros").hidden=!(saved&&hasMacros);
  const returnButton=$("#return-connected-workspace");
  returnButton.textContent=saved?`Return to ${device.product_id}`:`Load ${device.product_id}`;
}

async function importDetachedMacros() {
  const device=mismatchedDevice();
  if(!device||!state.config)return;
  const saved=state.deviceDocuments.get(device.port);
  if(!saved)return toast("No keyboard workspace to restore",`Load ${device.product_id} before importing macros into it.`,"error");
  const source=clone(state.config),sourceName=state.fileName;
  try{
    const result=await loadImportableMacros(source);
    const incoming=result.macros||[];
    const existing=(saved.config?.macro_key||[]).length;
    if(!confirmMacroReplacement(existing,incoming.length,sourceName))return;
    if(!restoreDeviceDocument(device.port,device.product_id))throw new Error(`The saved ${device.product_id} workspace is no longer compatible.`);
    state.loadedPort=device.port;
    state.selectedPort=device.port;
    applyImportedMacros(result);
    await synchronizeOpenDocument();
  }catch(error){toast("Could not import macros",error.message,"error");}
}

async function returnToConnectedWorkspace() {
  const device=mismatchedDevice();
  if(!device)return;
  if(state.dirty&&!confirm(`Discard unsaved changes to ${state.fileName} and return to ${device.product_id}?`))return;
  if(restoreDeviceDocument(device.port,device.product_id)){
    state.loadedPort=device.port;
    state.selectedPort=device.port;
    await synchronizeOpenDocument();
    render();
    toast("Keyboard workspace restored",`${device.product_id} · ${state.fileName}`,"success");
    return;
  }
  state.selectedPort=device.port;
  await readDevice();
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
    dirty:state.dirty,
    undo:state.undo,
    redo:state.redo,
    view:{layer:state.layer,selected:state.selected,macro:state.macro,ledSlot:state.ledSlot,ledTarget:state.ledTarget,ledFrame:state.ledFrame},
  });
}

function restoreDeviceDocument(port,deviceId) {
  const saved=state.deviceDocuments.get(port);
  if(!saved||!sameProductFamily(saved.config?.product_info?.product_id,deviceId))return false;
  state.config=saved.config;
  state.documentRevision=null;
  state.fileName=saved.fileName;
  state.dirty=Boolean(saved.dirty);
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
  updateCompatibilityBanner();
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
    if(!await synchronizeOpenDocument())throw new Error(state.documentSyncError||"The device document could not be synchronized.");
    markDirty();render();
    $("#device-dialog").close();
    const ledDetail=restored?'Its in-memory LED workspace was restored.':preserved?'Open LED data was preserved.':restoredFromDisk?'LEDs were restored from this machine’s last verified full write—not read from the keyboard.':'No portable LED source was available; blank local LED slots were created.';
    const macroDetail=result.macro_restored_from_snapshot?`${result.macros.length} macros restored from the complete local snapshot; the readable device prefix matched.`:keptLocalMacros?`Keyboard reported no macro definitions; kept ${keptLocalMacros} from this local workspace.`:result.macros.length?`${result.macros.length} macros read from the keyboard.`:result.macro_references?.length?`The keymap assigns ${result.macro_references.map(code=>decodeCode(code)).join(', ')}, but the keyboard returned no macro actions.`:'No macros reported by the keyboard.';
    const macroReadWarning=result.macro_read_warning?`\n${result.macro_read_warning}`:'';
    const storedWarning=result.stored_warning?`\n${result.stored_warning}`:'';
    toast(switching?`Switched to ${result.device.product_id}`:'Device data loaded',`${result.layers.length} layers\n${macroDetail}\n${ledDetail}${macroReadWarning}${storedWarning}`,keptLocalMacros||result.macro_references?.length||result.macro_read_warning||result.stored_warning?'':'success');
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
    if(result.document_revision){state.documentRevision=result.document_revision;state.documentSyncError="";}
    markDirty(false);$("#write-dialog").close();state.pendingWrite=null;
    const partialMacros=result.macro_verification==='partial';
    const macroWarning=result.macro_warning?`\n${result.macro_warning}`:'';
    toast(partialMacros?'Write accepted; macro tail unreadable':'Write verified',`${result.device.product_id} · ${result.frames} configuration frames · ${result.macros} macros\nSnapshot ${result.snapshot}${macroWarning}`,partialMacros?'':'success');
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

// ---- Optional procedural generation ---------------------------------------

function aiReady() {
  return Boolean(state.aiStatus?.enabled && state.aiStatus?.ready);
}

function selectedAiBackend() {
  return $("input[name='settings-ai-backend']:checked")?.value || state.aiStatus?.backend || "local";
}

function proceduralTargetSnapshot() {
  const family=productFamily(productId());
  if(family==="CB")return {family,productId:productId(),targets:["frames"],frameCap:80};
  if(family==="80")return {family,productId:productId(),targets:["keyframes","spotlight_frames"],frameCap:200};
  return {family,productId:productId(),targets:["keyframes"],frameCap:186};
}

function latestProceduralAttempt(manifest=state.conceptManifest) {
  const attempts=manifest?.procedural_attempts||[];
  return attempts.length?attempts[attempts.length-1]:null;
}

async function loadProceduralRecipe(jobId,assetId) {
  const key=`${jobId}:${assetId}`;
  if(state.proceduralRecipes.has(key)||state.proceduralRecipeLoads.has(key))return;
  state.proceduralRecipeLoads.add(key);
  try{
    const response=await fetch(`/api/lighting/assets/${encodeURIComponent(jobId)}/${encodeURIComponent(assetId)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load recipe (${response.status})`);}
    const recipe=await response.json();
    if(!recipe||typeof recipe!=="object"||!Array.isArray(recipe.layers))throw new Error("The saved recipe is invalid.");
    if(state.conceptManifest?.job_id===jobId){state.proceduralRecipes.set(key,recipe);refreshGenerationDialog();}
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.animationError=error.message;refreshGenerationDialog();}
  }finally{state.proceduralRecipeLoads.delete(key);}
}

function hydrateProceduralAssets(manifest) {
  const attempt=latestProceduralAttempt(manifest);
  if(!attempt)return;
  if(attempt.preview_asset_id)void loadConceptAsset(manifest.job_id,attempt.preview_asset_id);
  if(attempt.recipe_asset_id)void loadProceduralRecipe(manifest.job_id,attempt.recipe_asset_id);
  if(attempt.mapped_result_asset_id)void loadMappedLightingResult(manifest.job_id,attempt.mapped_result_asset_id);
}

function refreshGenerationDialog() {
  const dialog=$("#lighting-generate-dialog");
  if(dialog?.open)renderGenerationDialog();
}

function syncLightingJob(manifest,{renderPage=true}={}) {
  const previousId=state.conceptManifest?.job_id;
  if(previousId&&previousId!==manifest?.job_id){
    clearConceptAssetUrls();
    state.proceduralRecipes.clear();
    state.animationError="";
  }
  state.conceptManifest=manifest||null;
  if(manifest){
    state.conceptPollFailures=0;
    state.aiPrompt=manifest.prompt||state.aiPrompt;
    state.conceptDestination={slot:state.conceptDestination?.slot||state.ledSlot,target:manifest.target?.targets?.[0]||state.ledTarget};
    if(manifest.loop_mode)state.animationLoopMode=manifest.loop_mode;
  }else state.conceptDestination=null;
  state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:manifest?projectLightingJob(manifest):null}).state;
  state.lightingJobId=state.lighting.activeJob?.id||null;
  persistLightingState();
  history.replaceState({},"",`${location.pathname}${location.search}${formatLightingHash(state.lighting.route,state.lightingJobId)}`);
  hydrateProceduralAssets(manifest);
  if(renderPage)render();
  else{renderLightingJobStrip();refreshGenerationDialog();}
  if(manifest&&["in_progress","accepted","processing"].includes(manifest.status))scheduleLightingJobPoll(manifest.job_id);
}

function proceduralPhaseLabel(phase) {
  return ({
    accepted:"Queued locally",
    recipe_about_to_start:"Preparing recipe generation",
    recipe_generating:"Creating a procedural recipe",
    quality_check:"Checking exact LED frames",
    rendering:"Rendering exact LED frames",
    banking:"Saving the result locally",
    ready_for_review:"Ready for review",
    cancelled_saved:"Cancelled; completed assets remain saved",
  })[phase]||String(phase||"Working").replaceAll("_"," ");
}

function generationDialogContext() {
  const manifest=state.conceptManifest?.job_id===state.lighting.activeJob?.id?state.conceptManifest:null;
  const target=manifest?.target||proceduralTargetSnapshot();
  const targetKey=target.targets?.[0]||state.ledTarget;
  const model=LED_MODELS[productFamily(target.family||target.product_id)]||activeLedModel();
  const targetLabel=model.targets.find(item=>item.key===targetKey)?.label||targetKey;
  const destinationSlot=state.conceptDestination?.slot||state.ledSlot;
  return {manifest,target,targetKey,targetLabel,destinationSlot,busy:state.conceptSubmitting||["in_progress","accepted","processing"].includes(state.lighting.activeJob?.status)};
}

function renderPromptStage(context) {
  const {manifest,targetLabel,destinationSlot,busy}=context;
  const backend=state.aiStatus?.backend==="api"?"API":"Local";
  const stopped=latestProceduralAttempt(manifest)?.error_code;
  $("#lighting-generate-content").innerHTML=`<div class="concept-stage">
    <div class="concept-prompt"><label class="control-label" for="effect-prompt">Describe the lighting</label><textarea id="effect-prompt" class="text-field" rows="5" maxlength="4000" placeholder="Dense violet aurora moving across the whole keyboard…" ${busy?'disabled':''}>${esc(state.aiPrompt)}</textarea></div>
    <p class="concept-destination">${backend} · Custom ${destinationSlot-4} · ${esc(targetLabel)}</p>
    <div class="concept-actions"><button id="generate-effect" type="button" class="button primary" ${busy||!state.aiPrompt.trim()||!aiReady()||!documentSynchronized()?'disabled':''}>Generate animation</button></div>
    ${state.conceptError||state.animationError||state.documentSyncError||stopped?`<p class="ai-error" role="alert">${esc(state.conceptError||state.animationError||state.documentSyncError||(String(stopped).replaceAll("_"," ")+". The saved failure does not disable this backend; adjust the prompt or model and try again."))}</p>`:""}
  </div>`;
  $("#effect-prompt")?.addEventListener("input",event=>{state.aiPrompt=event.target.value;$("#generate-effect").disabled=!event.target.value.trim()||!aiReady()||!documentSynchronized();});
  $("#generate-effect")?.addEventListener("click",startProceduralGeneration);
}

function renderProgressStage(context) {
  const manifest=context.manifest;
  const progress=manifest?.progress||state.lighting.activeJob?.progress;
  const completed=Number(progress?.completed||0),total=Number(progress?.total||0);
  $("#lighting-generate-content").innerHTML=`<div class="concept-stage generation-progress">
    <div class="loader" aria-hidden="true"></div><h3>${esc(proceduralPhaseLabel(manifest?.phase||state.lighting.activeJob?.phase))}</h3>
    <p>Your job is durable. You can close this window while the result continues banking locally.</p>
    ${total?`<progress max="${total}" value="${Math.min(completed,total)}" aria-label="Generation progress"></progress><p>${completed} of ${total} frames saved</p>`:""}
    <div class="button-row"><button id="cancel-effect" type="button" class="button ghost">Cancel</button></div>
    ${state.conceptError?`<p class="ai-error" role="alert">${esc(state.conceptError)}</p>`:""}
  </div>`;
  $("#cancel-effect")?.addEventListener("click",cancelLightingJob);
}

function renderProceduralReview(context) {
  const manifest=context.manifest;
  const attempt=latestProceduralAttempt(manifest);
  const recipe=attempt?.recipe_asset_id?state.proceduralRecipes.get(`${manifest.job_id}:${attempt.recipe_asset_id}`):null;
  const quality=attempt?.quality||{};
  const decision=reduceLightingState(state.lighting,{type:"APPLY_REQUESTED"},{document:documentDescriptor(),destination:state.conceptDestination});
  const mappedResultLoaded=Boolean(attempt?.mapped_result_asset_id&&state.mappedLightingResults.has(`${manifest.job_id}:${attempt.mapped_result_asset_id}`));
  const view=createReviewView({assetUrls:state.conceptAssetUrls,jobId:manifest.job_id,attempt,recipe,quality,frameCap:manifest?.target?.frame_cap,targetLabel:context.targetLabel,destinationSlot:context.destinationSlot,blockedReason:decision.blocked,mappedResultLoaded,errorMessage:state.animationError});
  renderReview($("#lighting-generate-content"),view,applyReviewedLighting);
}

function renderGenerationDialog() {
  const dialog=$("#lighting-generate-dialog");
  if(!dialog)return;
  const active=Boolean(state.lighting.activeJob);
  dialog.hidden=!aiReady()&&!active;
  if(!dialog.open)return;
  const context=generationDialogContext();
  if(state.lighting.create.stage===STAGES.REVIEW&&context.manifest)renderProceduralReview(context);
  else if(state.lighting.create.stage===STAGES.PROGRESS&&active)renderProgressStage(context);
  else renderPromptStage(context);
}

function openGenerationDialog() {
  const dialog=$("#lighting-generate-dialog");
  if((!aiReady()&&!state.lighting.activeJob)||!state.config||!pageData().length||(!state.lighting.activeJob&&!documentSynchronized()))return;
  dialog.hidden=false;
  renderGenerationDialog();
  if(!dialog.open)dialog.showModal();
  setTimeout(()=>$("#effect-prompt")?.focus(),30);
}

function handleGenerationDialogClose() {
  const job=state.lighting.activeJob;
  if(job&&!["in_progress","accepted","processing"].includes(job.status)){
    clearConceptAssetUrls();
    state.proceduralRecipes.clear();
    state.conceptManifest=null;
    state.conceptDestination=null;
    state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:null}).state;
    state.lightingJobId=null;
    state.library.loaded=false;
    persistLightingState();
    history.replaceState({},"",`${location.pathname}${location.search}${formatLightingHash(state.lighting.route)}`);
    render();
  }
  $("#lighting-generate-open")?.focus();
}

async function startProceduralGeneration() {
  if(state.conceptSubmitting||!aiReady()||!documentSynchronized())return;
  if(state.lighting.activeJob){
    if(["in_progress","accepted","processing"].includes(state.lighting.activeJob.status))return;
    syncLightingJob(null,{renderPage:false});
  }
  const prompt=state.aiPrompt.trim();
  if(!prompt)return;
  state.conceptSubmitting=true;
  state.conceptError="";
  state.animationError="";
  const target=proceduralTargetSnapshot();
  state.conceptDestination={slot:state.ledSlot,target:target.targets[0]};
  renderGenerationDialog();
  try{
    const started=await api("/api/lighting/effects",{method:"POST",body:JSON.stringify({prompt,backend:state.aiStatus.backend,loop_mode:state.animationLoopMode,document_revision:state.documentRevision})});
    state.conceptPollEpoch++;
    state.conceptDestination={slot:state.ledSlot,target:started.target.targets[0]};
    state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:{id:started.job_id,status:"in_progress",phase:"accepted",progress:null,resultAssetId:null,previewAssetId:null,recipeAssetId:null,target:started.target}}).state;
    state.lightingJobId=started.job_id;
    persistLightingState();
    renderLightingJobStrip();
    renderGenerationDialog();
    scheduleLightingJobPoll(started.job_id);
  }catch(error){state.conceptError=aiErrorMessage(error);}
  finally{state.conceptSubmitting=false;refreshGenerationDialog();}
}

function applyReviewedLighting() {
  const manifest=state.conceptManifest;
  const attempt=latestProceduralAttempt(manifest);
  const destination=state.conceptDestination;
  if(!manifest||!attempt?.mapped_result_asset_id||!destination)return;
  const decision=reduceLightingState(state.lighting,{type:"APPLY_REQUESTED"},{document:documentDescriptor(),destination});
  if(decision.blocked){state.animationError=reviewBlockedMessage(decision.blocked);renderGenerationDialog();return;}
  const result=state.mappedLightingResults.get(`${manifest.job_id}:${attempt.mapped_result_asset_id}`);
  if(!result){state.animationError="The saved LED result is still loading.";renderGenerationDialog();return;}
  const pairsRelicGif=(manifest.target?.targets||[]).includes("spotlight_frames");
  mutate(()=>{
    state.ledSlot=destination.slot;
    state.ledTarget=destination.target;
    applyLedResultToPage(getPage(destination.slot),result,destination.target,pairsRelicGif);
    state.ledFrame=0;
  },false);
  state.conceptPollEpoch++;
  if(state.conceptPollTimer)clearTimeout(state.conceptPollTimer);
  clearConceptAssetUrls();
  state.proceduralRecipes.clear();
  state.conceptManifest=null;
  state.conceptDestination=null;
  state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:null}).state;
  state.lightingJobId=null;
  state.library.loaded=false;
  persistLightingState();
  history.replaceState({},"",`${location.pathname}${location.search}${formatLightingHash(state.lighting.route)}`);
  $("#lighting-generate-dialog").close();
  render();
  toast("Lighting applied",`${Number(result.source_frames||0)} frames added to Custom ${destination.slot-4}. The keyboard has not been written.`,"success");
}

async function loadAiConfig() {
  const requests=await Promise.allSettled([api("/api/led/capabilities"),api("/api/settings"),api("/api/ai/status"),api("/api/ai/local/models")]);
  if(requests[0].status==="fulfilled")state.capabilities=requests[0].value;
  if(requests[1].status==="fulfilled")state.settings=requests[1].value;
  if(requests[2].status==="fulfilled")state.aiStatus=requests[2].value;
  if(requests[3].status==="fulfilled")state.localModels=normalizeLocalModels(requests[3].value);
  else state.localModels={available:false,models:[],loading:false};
  if(["smooth","none","ping_pong"].includes(state.settings?.generation?.loop_mode))state.animationLoopMode=state.settings.generation.loop_mode;
  refreshAiGate();
}

function refreshAiGate() {
  const button=$("#lighting-generate-open");
  if(button){button.hidden=!aiReady();button.disabled=!state.config||!pageData().length||!aiReady();}
  const dialog=$("#lighting-generate-dialog");
  if(dialog){
    const keep=Boolean(state.lighting.activeJob);
    dialog.hidden=!aiReady()&&!keep;
    if(dialog.open&&!aiReady()&&!keep)dialog.close();
  }
  if(state.lighting.route===ROUTES.CREATE&&!aiReady()&&!state.lighting.activeJob)navigateTo(ROUTES.EDIT,{replace:true});
  else if(state.lighting.route===ROUTES.SETTINGS)populateSettings();
  else if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  else renderScreen();
}

function aiReasonText(reason,status=state.aiStatus) {
  return ({
    disabled:"Optional generation is off.",backend_unselected:"Choose a backend.",ollama_unavailable:"Start Ollama on this computer, then refresh the installed models.",model_missing:"Choose one of the models already installed in Ollama.",model_unavailable:"The selected Ollama model is no longer installed with the same identity. Refresh and choose it again.",setup_required:"Run the setup test to enable this backend.",credential_store_unavailable:"Secure credential storage is unavailable.",credential_missing:"Save an API credential.",disclosure_required:"Accept the API data disclosure.",auth_invalid:"The API credential was rejected.",ready:"Ready.",
  })[reason]||"Setup needs attention.";
}

function normalizeLocalModels(value) {
  const models=Array.isArray(value?.models)?value.models.filter(model=>model&&typeof model.model_id==="string"&&typeof model.digest==="string"):[];
  return {available:value?.available===true,models,loading:false};
}

function populateLocalModelSelect(local) {
  const select=$("#settings-local-model-select");
  const previous=select.value;
  const selected=local.model_id;
  const models=state.localModels.models;
  select.replaceChildren();
  const placeholder=document.createElement("option");
  placeholder.value="";
  placeholder.textContent=state.localModels.loading?"Checking installed models…":state.localModels.available?(models.length?"Choose an installed model":"No eligible local models found"):"Ollama is not available";
  select.append(placeholder);
  models.forEach(model=>{
    const option=document.createElement("option");
    option.value=model.model_id;
    const details=[model.parameter_size,model.quantization].filter(Boolean).join(" · ");
    option.textContent=details?`${model.model_id} — ${details}`:model.model_id;
    select.append(option);
  });
  if(selected&&!models.some(model=>model.model_id===selected)){
    const missing=document.createElement("option");
    missing.value=selected;
    missing.textContent=`${selected} — not currently available`;
    missing.disabled=true;
    select.append(missing);
  }
  const preferred=[previous,selected].find(value=>value&&[...select.options].some(option=>option.value===value))||"";
  select.value=preferred;
  select.disabled=state.localModels.loading||!state.localModels.available||models.length===0;
}

async function openSettings({returnToGeneration=false}={}) {
  if(state.lighting.route!==ROUTES.SETTINGS)state.settingsReturnRoute=state.lighting.route;
  state.settingsReturnDialog=returnToGeneration||$("#lighting-generate-dialog").open;
  if($("#lighting-generate-dialog").open)$("#lighting-generate-dialog").close();
  navigateTo(ROUTES.SETTINGS,{focusHeading:true});
  setSettingsStatus("");
  await loadAiConfig();
}

function populateSettings() {
  const status=state.aiStatus;
  const backend=status?.backend||"local";
  const migration=state.settings?.migration||{};
  const migrationBlocked=migration.required===true;
  const canDiscardLegacyCredential=migrationBlocked&&migration.reason==="credential_store_unavailable";
  const repair=$("#settings-migration-repair");
  const confirm=$("#settings-migration-confirm");
  repair.hidden=!migrationBlocked;
  $("#settings-migration-message").textContent=migration.reason==="settings_migration_write_failed"
    ?"The older settings were read, but the upgraded settings file could not be saved. Restore write access, then reopen Settings."
    :"The legacy API credential could not be moved into secure storage. Retry after credential storage is available, or explicitly continue without that legacy credential.";
  $("#settings-migration-confirm-row").hidden=!canDiscardLegacyCredential;
  $("#settings-migration-discard").hidden=!canDiscardLegacyCredential;
  if(!migrationBlocked)confirm.checked=false;
  $("#settings-migration-discard").disabled=!canDiscardLegacyCredential||!confirm.checked;
  $("#settings-mutable").inert=migrationBlocked;
  $("#settings-save").disabled=migrationBlocked||state.settingsSaveBusy;
  $("#settings-ai-enabled").checked=Boolean(status?.enabled);
  $("#settings-ai-local").checked=backend==="local";
  $("#settings-ai-api").checked=backend==="api";
  $("#settings-ai-state").textContent=aiReady()?"Ready":status?.enabled?"Needs repair":"Off";
  $("#settings-ai-state").className=`pill ${aiReady()?"":"muted"}`;
  $("#settings-local-panel").hidden=backend!=="local";
  $("#settings-api-panel").hidden=backend!=="api";
  const local=status?.local||{};
  const ollamaAvailable=state.localModels.available===true;
  $("#settings-local-runtime").textContent=state.localModels.loading?"Checking":ollamaAvailable?"Ollama ready":"Not running";
  $("#settings-local-runtime").className=`pill ${ollamaAvailable?"":"muted"}`;
  let localGuidance="Choose an installed Ollama model for local generation.";
  if(backend==="local"){
    if(!ollamaAvailable)localGuidance="Start Ollama on this computer, then refresh the installed models.";
    else if(!local.model_selected)localGuidance="Choose one of the models already installed in Ollama.";
    else if(!local.model_verified)localGuidance="The selected model is no longer available. Refresh and choose it again.";
    else if(!local.setup_tested)localGuidance="Run Test & enable to verify this model can create lighting recipes.";
    else localGuidance=status?.enabled?"Ready.":"This model passed setup. Turn on Optional AI features to use it.";
  }
  $("#settings-local-state").textContent=localGuidance;
  populateLocalModelSelect(local);
  $("#settings-local-model").textContent=local.model_selected?`Selected in Ollama: ${local.model_id}${local.model_verified?" · installed":" · no longer available"}`:"No Ollama model selected.";
  const picker=$("#settings-local-model-select");
  $("#settings-local-refresh").disabled=state.localModels.loading;
  $("#settings-local-select").disabled=picker.disabled||!picker.value||!state.localModels.models.some(model=>model.model_id===picker.value);
  $("#settings-local-clear").disabled=!local.model_selected;
  $("#settings-local-test").disabled=!local.model_verified;
  const apiState=status?.api||{};
  $("#settings-api-credential-state").textContent=apiState.credential_set?"A credential is stored securely.":"No credential is configured.";
  $("#settings-api-remove").disabled=!apiState.credential_set;
  $("#settings-api-disclosure-ack").checked=Boolean(apiState.disclosure_current);
  $("#settings-api-provider").value=apiState.provider||"xai";
  $("#settings-api-model").value=apiState.model_id||"grok-4.5";
  $("#settings-library-root").value=state.settings?.library?.current_root||"";
  $("#settings-reveal-library").disabled=!state.settings?.library?.current_root;
  $("#settings-loop-mode").value=state.settings?.generation?.loop_mode||"smooth";
}

async function refreshSettingsData() {
  const [settings,status]=await Promise.all([api("/api/settings"),api("/api/ai/status")]);
  state.settings=settings;
  state.aiStatus=status;
  populateSettings();
  refreshAiGate();
}

async function selectAiBackend(backend) {
  setSettingsStatus("Updating backend…","working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({enabled:false,backend})});
    populateSettings();
    refreshAiGate();
    setSettingsStatus(backend==="local"?"Local backend selected. Choose an installed Ollama model, then test it.":"API backend selected. Save a credential, accept the disclosure, and test.");
  }catch(error){setSettingsStatus(error.message,"error");}
}

async function refreshLocalModels({quiet=false}={}) {
  state.localModels={...state.localModels,loading:true};
  populateSettings();
  if(!quiet)setSettingsStatus("Checking models already installed in Ollama…","working");
  try{
    state.localModels=normalizeLocalModels(await api("/api/ai/local/models"));
    populateSettings();
    if(!quiet)setSettingsStatus(state.localModels.available?(state.localModels.models.length?`${state.localModels.models.length} local Ollama model${state.localModels.models.length===1?"":"s"} available.`:"Ollama is running, but it has no eligible local models installed."):"Ollama is not running. Start Ollama, then refresh models.",state.localModels.available?"":"error");
  }catch(error){state.localModels={available:false,models:[],loading:false};populateSettings();if(!quiet)setSettingsStatus("Ollama could not be reached on this computer.","error");}
}

async function selectOllamaModel() {
  const modelId=$("#settings-local-model-select").value;
  if(!modelId){setSettingsStatus("Choose an installed Ollama model first.","error");return;}
  setSettingsStatus(`Selecting ${modelId}…`,"working");
  try{state.aiStatus=await api("/api/ai/local/select",{method:"POST",body:JSON.stringify({model_id:modelId})});populateSettings();refreshAiGate();setSettingsStatus(`${modelId} selected. Run Test & enable.`);}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function clearLocalModel() {
  setSettingsStatus("Clearing selection…","working");
  try{state.aiStatus=await api("/api/ai/local/clear",{method:"POST",body:"{}"});populateSettings();refreshAiGate();setSettingsStatus("Ollama model selection cleared. No installed model was changed or removed.");}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function testAiBackend(backend) {
  setSettingsStatus(backend==="local"?"Testing the selected model through local Ollama…":"Testing the API backend…","working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({enabled:false,backend,provider:"xai",model_id:"grok-4.5"})});
    if(backend==="api"){
      const key=$("#settings-api-key").value.trim();
      if(key){state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:"xai",key})});$("#settings-api-key").value="";}
      if(!state.aiStatus.api.disclosure_current){
        if(!$("#settings-api-disclosure-ack").checked)throw new Error("Accept the API data disclosure before testing.");
        const version=state.capabilities?.privacy_disclosure_version;
        if(!version)throw new Error("The current API disclosure is unavailable.");
        state.settings=await api("/api/settings/privacy",{method:"POST",body:JSON.stringify({version})});
      }
    }
    state.aiStatus=await api("/api/ai/test",{method:"POST",body:JSON.stringify({backend})});
    await refreshSettingsData();
    setSettingsStatus(backend==="local"?"Local generation is enabled with the selected Ollama model.":"API generation is enabled.");
  }catch(error){
    try{state.aiStatus=await api("/api/ai/status");populateSettings();refreshAiGate();}catch(refreshError){}
    setSettingsStatus(aiErrorMessage(error),"error");
  }
}

async function saveApiCredential() {
  const key=$("#settings-api-key").value.trim();
  if(!key){setSettingsStatus("Enter an API key to save.","error");return;}
  setSettingsStatus("Saving credential securely…","working");
  try{state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:"xai",key})});$("#settings-api-key").value="";populateSettings();setSettingsStatus("Credential saved. Run Test & enable API.");}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function clearSettingsKey() {
  setSettingsStatus("Removing credential…","working");
  try{state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:"xai",key:""})});populateSettings();refreshAiGate();setSettingsStatus("API credential removed.");}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function discardLegacyApiCredential() {
  if(!$("#settings-migration-confirm").checked){
    setSettingsStatus("Confirm that the legacy API credential may be discarded.","error");
    return;
  }
  const button=$("#settings-migration-discard");
  button.disabled=true;
  setSettingsStatus("Repairing older settings…","working");
  try{
    state.settings=await api("/api/settings/migration/discard-credential",{method:"POST",body:JSON.stringify({confirm:true})});
    await loadAiConfig();
    populateSettings();
    setSettingsStatus("Settings repaired. The legacy file credential was discarded; the OS credential vault was not changed.");
  }catch(error){setSettingsStatus(error.message,"error");populateSettings();}
}

async function saveSettings({exit=false}={}) {
  if(state.settingsSaveBusy)return false;
  state.settingsSaveBusy=true;
  $("#settings-save").disabled=true;
  $("#settings-done").disabled=true;
  setSettingsStatus("Saving…","working");
  try{
    const backend=selectedAiBackend();
    const enabled=$("#settings-ai-enabled").checked;
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({enabled,backend,provider:"xai",model_id:"grok-4.5"})});
    state.settings=await api("/api/settings/preferences",{method:"POST",body:JSON.stringify({loop_mode:$("#settings-loop-mode").value})});
    const requestedRoot=$("#settings-library-root").value.trim()||null;
    if(requestedRoot!==state.settings.library?.current_root)state.settings=await api("/api/settings/library",{method:"POST",body:JSON.stringify({current_root:requestedRoot})});
    state.animationLoopMode=state.settings.generation?.loop_mode||"smooth";
    state.library.loaded=false;
    populateSettings();
    refreshAiGate();
    setSettingsStatus("Settings saved.");
    if(exit)finishSettings();
    return true;
  }catch(error){setSettingsStatus(error.message,"error");return false;}
  finally{state.settingsSaveBusy=false;$("#settings-save").disabled=false;$("#settings-done").disabled=false;}
}

function showDeviceDialog(){const dialog=$("#device-dialog");if(!dialog.open)dialog.showModal();scanDevices();}

$("#open-button").addEventListener("click",()=>$("#open-input").click());
$("#merge-button").addEventListener("click",()=>$("#merge-input").click());
$("#open-input").addEventListener("change",event=>readFiles(event.currentTarget,false));
$("#merge-input").addEventListener("change",event=>readFiles(event.currentTarget,true));
$("#macro-import-input").addEventListener("change",event=>importMacros(event.currentTarget));
$("#save-button").addEventListener("click",saveConfig);
$("#backup-before-write").addEventListener("click",saveConfig);
$("#write-button").addEventListener("click",writeDevice);
$("#device-button").addEventListener("click",showDeviceDialog);
$("#read-device").addEventListener("click",readDevice);
$("#open-incompatible").addEventListener("click",()=>resolveIncompatibleProfile("open"));
$("#import-incompatible-macros").addEventListener("click",()=>resolveIncompatibleProfile("macros"));
$("#incompatible-dialog").addEventListener("close",()=>{if(incompatibleResolver)resolveIncompatibleProfile("cancel");});
$("#import-banner-macros").addEventListener("click",importDetachedMacros);
$("#return-connected-workspace").addEventListener("click",returnToConnectedWorkspace);
$("#confirm-write").addEventListener("click",confirmDeviceWrite);
$("#write-confirmation").addEventListener("input",event=>{$("#confirm-write").disabled=!state.pendingWrite||event.target.value.trim().toUpperCase()!==state.pendingWrite.device.product_id.toUpperCase();});
$("#write-confirmation").addEventListener("keydown",event=>{if(event.key==='Enter'){event.preventDefault();if(!$("#confirm-write").disabled)confirmDeviceWrite();}});
$("#write-dialog").addEventListener("close",()=>{if($("#write-dialog").returnValue==='cancel')state.pendingWrite=null;});
$("#undo-button").addEventListener("click",undo);
$("#redo-button").addEventListener("click",redo);
$("#validate-button").addEventListener("click",()=>validateCurrent());
$("#settings-button").addEventListener("click",openSettings);
$("#settings-save").addEventListener("click",()=>saveSettings());
$("#settings-done").addEventListener("click",()=>state.settings?.migration?.required?finishSettings():saveSettings({exit:true}));
$("#settings-migration-confirm").addEventListener("change",populateSettings);
$("#settings-migration-discard").addEventListener("click",discardLegacyApiCredential);
$("#settings-ai-enabled").addEventListener("change",event=>{if(!event.target.checked)void selectAiBackend(selectedAiBackend());});
$("#settings-ai-local").addEventListener("change",()=>selectAiBackend("local"));
$("#settings-ai-api").addEventListener("change",()=>selectAiBackend("api"));
$("#settings-local-refresh").addEventListener("click",()=>refreshLocalModels());
$("#settings-local-model-select").addEventListener("change",populateSettings);
$("#settings-local-select").addEventListener("click",selectOllamaModel);
$("#settings-local-test").addEventListener("click",()=>testAiBackend("local"));
$("#settings-local-clear").addEventListener("click",clearLocalModel);
$("#settings-api-key").addEventListener("keydown",event=>{if(event.key==='Enter'){event.preventDefault();saveApiCredential();}});
$("#settings-api-save-key").addEventListener("click",saveApiCredential);
$("#settings-api-test").addEventListener("click",()=>testAiBackend("api"));
$("#settings-api-remove").addEventListener("click",clearSettingsKey);
$("#settings-choose-library").addEventListener("click",chooseLibraryFolder);
$("#settings-reveal-library").addEventListener("click",revealLibraryFolder);
$("#library-refresh").addEventListener("click",()=>loadLibrary({force:true}));
$("#library-reveal").addEventListener("click",async()=>{
  const path=state.settings?.library?.current_root;
  if(!path){openSettings();return;}
  try{if(!await invokeRevealLibraryPath(path))throw new Error("The folder is unavailable.");}
  catch(error){toast("Could not reveal Library",error.message||String(error),"error");}
});
$$("[data-library-filter]").forEach(button=>button.addEventListener("click",()=>{
  if(state.library.filter===button.dataset.libraryFilter)return;
  state.library.filter=button.dataset.libraryFilter;
  state.library.loaded=false;
  void loadLibrary({force:true});
}));
$("#library-search").addEventListener("input",event=>{
  state.library.query=event.target.value;
  if(state.library.searchTimer)clearTimeout(state.library.searchTimer);
  state.library.searchTimer=setTimeout(()=>{state.library.loaded=false;void loadLibrary({force:true});},280);
});
$("#lighting-generate-open").addEventListener("click",openGenerationDialog);
$("#lighting-generate-dialog").addEventListener("close",handleGenerationDialogClose);
$$('.nav-item').forEach(item=>item.addEventListener('click',()=>navigateTo(item.dataset.route, {focusHeading: true})));
$$('[data-lighting-route]').forEach(tab => {
  tab.addEventListener('click', () => navigateTo(tab.dataset.lightingRoute));
  tab.addEventListener('keydown', event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = $$('[data-lighting-route]');
    const current = tabs.indexOf(event.currentTarget);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? tabs.length - 1
      : event.key === "ArrowLeft" ? (current - 1 + tabs.length) % tabs.length
      : (current + 1) % tabs.length;
    tabs[next].focus();
    navigateTo(tabs[next].dataset.lightingRoute);
  });
});
$$('[data-lighting-slot]').forEach(button=>button.addEventListener('click',()=>{
  state.ledSlot=Number(button.dataset.lightingSlot);
  state.ledFrame=0;
  state.ledPixel=0;
  renderLightingShell();
}));
$("#lighting-job-view").addEventListener("click",openGenerationDialog);
$("#lighting-job-cancel").addEventListener("click", cancelLightingJob);
window.addEventListener("popstate", () => {
  const parsed = parseLightingHash(location.hash);
  state.lightingJobId = parsed.jobId;
  state.lighting = reduceLightingState(state.lighting, {type: "NAVIGATE", route: parsed.route}).state;
  persistLightingState();
  render();
  if (parsed.jobId && parsed.jobId !== state.lighting.activeJob?.id) restoreLightingJob();
});
document.addEventListener('keydown',event=>{
  if(state.recording){recordEvent(event,true);return;}
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='z'){event.preventDefault();event.shiftKey?redo():undo();}
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveConfig();}
});
document.addEventListener('keyup',event=>{if(state.recording)recordEvent(event,false);});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',clearConceptAssetUrls);
window.addEventListener('pagehide',clearLibraryAssetUrls);

(async function boot(){
  updateMeta();
  if(!token){toast('Missing local session token','Launch this page with AM Configurator.','error');return;}
  try{
    const result=await api('/api/config');
    if(result.config){state.config=result.config;state.documentRevision=result.document_revision||null;state.fileName=`AM-${productId()}-config.json`;}
    render();
    restoreLightingJob();
    scanDevices();
    loadAiConfig();
  }catch(error){toast('Could not start configurator',error.message,'error');}
})();
