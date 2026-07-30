"use strict";

const queryToken = new URLSearchParams(location.search).get("token") || "";
if (queryToken) sessionStorage.setItem("am-configurator-token", queryToken);
const token = queryToken || sessionStorage.getItem("am-configurator-token") || "";
if (queryToken) history.replaceState({}, "", `${location.pathname}${location.hash}`);

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clone = value => JSON.parse(JSON.stringify(value));
const {ROUTES, STAGES, aiStudioAvailable, createEpochLoadRegistry, createLaunchState, createPaintStrokeController, escapeMarkup:esc, formatLightingHash, nextGridIndex, normalizeImportedAssignmentCodes, normalizeImportedLightingColors, normalizeOllamaModels, ollamaEndpointDataFlow, ollamaModelRefreshFailed, parseLightingHash, projectApiProviderPicker, projectLightingJob, projectOllamaModelPicker, reduceLightingState, routeAvailability, safeRgbColor} = LightingState;
const {createReviewView, renderReview, reviewBlockedMessage} = LightingReview;
const {DEVICE_TARGETS, NEON_LIGHTING_CONTROLS, filterAssignmentOptions, macroCapacityStatus, productFamily, projectVialKeyLayout, projectVialLedLayout, renderTargetControls, selectVialLayoutDevice, specForProduct, supportedFamily, trackColorCount, withDeviceMacroLimits} = LightingTargets;
const {defaultSourceTransform, interpolateMoveZoom, normalizedPointer, panSourceTransform, presetSourceTransform, renderColorEffect, scaleSourceTransform, validateEffectSpec, validateSourceTransform} = LightingComposer;
const {
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
} = LibraryState;
const LIGHTING_SESSION_KEY = "am-lighting-session";
let activePaintStrokeController = null;

function restoredLightingState() {
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem(LIGHTING_SESSION_KEY) || "{}"); } catch (error) {}
  return createLaunchState(saved, location.hash);
}

const restoredLighting = restoredLightingState();
history.replaceState({}, "", `${location.pathname}${restoredLighting.hash}`);

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
  showTechnicalLabels: false,
  advancedKeycodeOpen: false,
  keyAssignmentEpoch: 0,
  macro: 0,
  macroAdvancedOpen: false,
  recording: false,
  recordLast: 0,
  ledSlot: 5,
  ledTarget: "keyframes",
  ledFrame: 0,
  ledPixel: 0,
  ledColor: "#8358ff",
  gifResample: "box",
  relicGifEdges: true,
  studioTool: "paint",
  sourceTransform: defaultSourceTransform("box"),
  sourcePreviewMode: "result",
  mediaComposition: null,
  mediaRenderEpoch: 0,
  appliedLightingProvenance: null,
  localAnimationEffect: "pulse",
  localAnimationFrameCount: 8,
  localAnimationDuration: 90,
  localAnimationMinimum: 0.2,
  localAnimationTurns: 1,
  localAnimationSweepWidth: 0.35,
  localAnimationDirection: "left_to_right",
  localAnimationShimmerDepth: 0.6,
  localAnimationSeed: 824,
  localAnimationCoordinates: [],
  localAnimationDraft: null,
  localAnimationPreviewFrame: 0,
  playing: false,
  playTimer: null,
  undo: [],
  redo: [],
  devices: [],
  selectedDevice: null,
  loadedDevice: null,
  deviceDocuments: new Map(),
  pendingWrite: null,
  capabilities: null,
  settings: null,
  aiStatus: null,
  ollamaModels: {available:null,models:[],reason:null,loading:false},
  settingsReturnRoute: null,
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
  animationSubmitting: false,
  animationError: "",
  reviewTab: "device",
  reviewFrameIndex: 0,
  mappedLightingResults: new Map(),
  mappedLightingResultLoads: new Set(),
  proceduralRecipes: new Map(),
  proceduralRecipeLoads: new Set(),
  library: {
    items: [],
    details: new Map(),
    detailLoads: new Set(),
    compatibilities: new Map(),
    compatibilityLoads: new Set(),
    assetUrls: new Map(),
    assetLoads: createEpochLoadRegistry(),
    assetErrors: new Map(),
    requests: createLibraryRequestEpochs(),
    filter: "all",
    query: "",
    page: 1,
    limit: 12,
    total: 0,
    hasMore: false,
    selectedCatalogId: null,
    lastFocusedCatalogId: null,
    profileSelections: new Map(),
    compatibilityRevisionPromise: null,
    mutatingCatalogId: null,
    undoRemoval: null,
    loaded: false,
    loading: false,
    importing: false,
    error: "",
    warnings: [],
    epoch: 0,
    searchTimer: null,
  },
};
let incompatibleResolver = null;
let libraryConfirmAction = null;

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

function activeFamilySpec() {
  const spec=specForProduct(productId());
  const device=state.devices.find(item=>deviceKey(item)===state.loadedDevice);
  return withDeviceMacroLimits(
    spec,
    device&&sameProductFamily(productId(),device.product_id)?device:null,
  );
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
  const navCounts = [
    ["#nav-layers", state.config ? layers().length : null, "layer", "layers"],
    ["#nav-macros", state.config ? (state.config.macro_key || []).length : null, "macro", "macros"],
    ["#nav-leds", state.config && pageData().length ? 3 : null, "lighting slot", "lighting slots"],
  ];
  for (const [selector, count, singular, plural] of navCounts) {
    const node = $(selector);
    node.textContent = count === null ? "—" : String(count);
    const label = count === null ? "none loaded" : `${count} ${count === 1 ? singular : plural}`;
    node.setAttribute("aria-label", label);
    node.title = label;
  }
  $("#save-button").disabled = !state.config;
  $("#merge-button").disabled = !state.config;
  $("#merge-button").hidden = !state.config;
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
      return normalizeImportedLightingColors(normalizeImportedAssignmentCodes(parsed));
    }));
    const families=new Set(configs.map(config=>productFamily(config?.product_info?.product_id)).filter(Boolean));
    if(families.size>1)throw new Error("The selected JSON files belong to different keyboard families and cannot be combined.");
    const incoming=mergeConfigs(configs);
    if(!incoming?.key_layer)throw new Error("No key_layer was found in the selected JSON.");

    const activeDevice=state.devices.find(device=>deviceKey(device)===state.loadedDevice)||selectedDevice();
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
      state.loadedDevice = null;
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
  [0,0,0],[1,7,0],[2,12.5,0],[3,18,0],[4,23.6,0],[5,30.5,0],[6,36.1,0],[7,41.6,0],[8,47.2,0],[9,54.2,0],[10,59.7,0],[11,65.3,0],[12,70.8,0],[13,77.7,0],[14,84.7,0],[89,90.2,0],[88,95.2,0],
  [25,0,20.5],[26,5.6,20.5],[27,11.1,20.5],[28,16.7,20.5],[29,22.2,20.5],[30,27.7,20.5],[31,33.3,20.5],[32,38.8,20.5],[33,44.4,20.5],[34,50,20.5],[35,55.5,20.5],[36,61,20.5],[37,66.6,20.5],[38,72.5,20.5,9],[39,84.7,20.5],[114,90.2,20.5],[113,95.2,20.5],
  [50,0,36.3,6.2],[51,8.3,36.3],[52,14,36.3],[53,19.4,36.3],[54,24.9,36.3],[55,30.5,36.3],[56,36,36.3],[57,41.6,36.3],[58,47.2,36.3],[59,52.7,36.3],[60,58.2,36.3],[61,63.8,36.3],[62,69.4,36.3],[63,75,36.3,6.2],[64,84.7,36.3],[139,90.2,36.3],[112,95.2,36.3],
  [75,0,52.7,8],[76,9.8,52.7],[77,15.3,52.7],[78,20.9,52.7],[79,26.4,52.7],[80,31.9,52.7],[81,37.5,52.7],[82,43,52.7],[83,48.6,52.7],[84,54.1,52.7],[85,59.7,52.7],[86,65.3,52.7],[87,70.8,52.7,10.2],
  [100,0,69,10.5],[101,12.5,69],[102,18.1,69],[103,23.6,69],[104,29.2,69],[105,34.7,69],[106,40.2,69],[107,45.7,69],[108,51.3,69],[109,56.9,69],[110,62.5,69],[111,68.1,69,13.2],[137,90.2,69],
  [125,0,85,6.2],[126,8.3,85],[127,13.8,85,6.2],[128,22.2,85,37],[135,61.1,85,6.2],[136,69.4,85],[138,75,85,6.2],[133,84.7,85],[132,90.2,85],[131,95.2,85],
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
const RELIC_LED_LAYOUT=projectVialLedLayout(
  {
    key_layout:RELIC_LAYOUT.map(([index,x,y,width=4.8,rotation=0])=>({
      index,x,y,width:Math.min(width,100-x),height:12.2,rotation,
    })),
  },
  {width:17,height:6,count:89,map:RELIC_LED_MAP},
);

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
    name:"Relic 80", keyMap:RELIC_LED_MAP, keyColumns:17, keyRaster:"17×6", physicalLayout:RELIC_LED_LAYOUT,
    targets:DEVICE_TARGETS["80"],
  },
  // No keyMap, keyColumns, or keyRaster: the Neon's axial and head geometry is
  // served from device_mapping rather than copied here. Python owns those
  // tables and a second copy is the drift the spec mirror already guards
  // against; there is no reason to introduce one for the maps.
  NEON: {
    name:"AM Neon 80",
    targets:DEVICE_TARGETS.NEON,
  },
};

// Per-target geometry the server publishes from device_mapping.
function servedGeometry(family, target) {
  const entries=state.capabilities?.targets?.[family]?.targets;
  return entries?.find(entry=>entry.name===target) || null;
}

function geometryUnavailableNotice() {
  const loading=state.capabilities===null;
  return `<div class="empty-state"><p class="eyebrow">${loading?"Loading device layout":"Device layout unavailable"}</p><h1>${loading?"Fetching the LED layout for this keyboard…":"The LED layout for this keyboard could not be loaded."}</h1><p>${loading?"The editor opens once the layout arrives.":"Connect the keyboard by USB and scan Devices, or read it again. Editing is held back deliberately: painting against a guessed square grid would author LED positions that do not exist on the device."}</p></div>`;
}
const LED_SPEEDS = [255,240,224,208,192,176,160,146,132,118,100,90,76,62,48,34];

function firmwareLedSpeed(value) {
  const duration=Math.max(1,Number(value)||90);
  return LED_SPEEDS.reduce((best,speed)=>Math.abs(speed-duration)<Math.abs(best-duration)?speed:best,LED_SPEEDS[0]);
}

// Null when this build has no LED geometry for the loaded product. Callers must
// handle that rather than substituting a default family: editing an unknown
// device with CyberBoard maps is how wrong pixel data reaches a keyboard.
function activeLedModel() {
  const family=supportedFamily(productId());
  return family===null?null:LED_MODELS[family];
}

function unsupportedDeviceNotice(action) {
  return `<div class="empty-state"><p class="eyebrow">Unsupported device</p><h1>No lighting profile for ${esc(productId())}.</h1><p>This build has no LED layout for that product, so ${action} would use another keyboard's geometry. Load a profile for a supported device.</p></div>`;
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
const NEON_QMK_NAMES = Object.fromEntries(
  NEON_LIGHTING_CONTROLS.map(option => [option.code, option.label]),
);

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
  let label = parts.page === 0x07
    ? HID_NAMES[parts.usage]
    : parts.page === 0x0c
      ? CONSUMER[parts.usage]
      : parts.page === 0x92
        ? VENDOR[parts.usage]
        : parts.page === 0xFF
          ? NEON_QMK_NAMES[String(code).toUpperCase()]
          : null;
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
  return `<button class="palette-key assignment-key ${active?'active':''}" data-code="${esc(option.code)}" data-search="${esc((option.label+' '+option.category).toLowerCase())}" style="--key-units:${width}" title="${esc(`${option.category} · ${option.code}`)}" ${disabled}>${esc(option.label)}</button>`;
}

function vendorGroup(usage) {
  if ((usage>=0x0c0b&&usage<=0x0c26)) return "Layers & Fn";
  if ((usage>=0x0100&&usage<=0x0105)||usage===0x0140) return "Display lighting";
  if (usage>=0x0900&&usage<=0x0905) return "PCB lighting";
  if (usage>=0x090b&&usage<=0x090f) return "Nameplate lighting";
  return "Wireless & system";
}

function renderAssignmentPalette(current) {
  const product=productId();
  const macroTracks=activeFamilySpec().macroTracks;
  const macrosForPalette=filterAssignmentOptions(product,(state.config.macro_key||[]).map((macro,index)=>({label:`Macro ${index+1}`,code:macro.original_key,category:"Macros"})),macroTracks);
  const extraUsages=[0x46,0x47,0x48,0x49,0x4a,0x4b,0x4c,0x4d,0x4e,0x4f,0x50,0x51,0x52,0x53,0x68];
  const extras=filterAssignmentOptions(product,[{label:"None",code:"#00000000",category:"Navigation & media"},...extraUsages.map(usage=>standardOption(usage,"Navigation & media")),...KEY_OPTIONS.filter(option=>option.category==="Media")],macroTracks);
  const vendorOptions=filterAssignmentOptions(product,Object.entries(VENDOR).map(([usage,label])=>({label,code:makeCode(0x92,Number(usage)),category:vendorGroup(Number(usage))})),macroTracks);
  const vendorGroups=VENDOR_GROUPS.map(group=>({group,options:vendorOptions.filter(option=>option.category===group)})).filter(entry=>entry.options.length);
  const neonLightingOptions=filterAssignmentOptions(product,NEON_LIGHTING_CONTROLS,macroTracks);
  const neonLightingGroups=[...new Set(neonLightingOptions.map(option=>option.category))].map(group=>({
    group,
    options:neonLightingOptions.filter(option=>option.category===group),
  }));
  return `<section class="assignment-panel">
    <div class="assignment-heading"><div><strong>Available assignments</strong><small>${state.selected===null?'Select a key on the board first.':state.showTechnicalLabels?`Assigning matrix key ${state.selected}`:'Pick what the selected key should send.'}</small></div><input id="key-search" class="search-field" type="search" placeholder="Filter keys and controls…"></div>
    <div class="assignment-scroll"><div class="qwerty-board assignment-section"><p class="control-label">Standard QWERTY keyboard</p>${QWERTY_ROWS.map(row=>`<div class="qwerty-row">${row.map(item=>item?assignmentButton(standardOption(item[0]),current,item[1]):`<span class="qwerty-spacer"></span>`).join("")}</div>`).join("")}</div></div>
    <div class="assignment-groups">
      <div class="assignment-section"><p class="control-label">Navigation & media</p><div class="assignment-grid">${extras.map(option=>assignmentButton(option,current)).join("")}</div></div>
      <div class="assignment-section"><p class="control-label">Macros</p>${macrosForPalette.length?`<div class="assignment-grid">${macrosForPalette.map(option=>assignmentButton(option,current)).join("")}</div>`:`<small class="palette-empty">Create a macro on the Macros screen to assign it here.</small>`}</div>
      ${neonLightingGroups.map(({group,options})=>`<div class="assignment-section"><p class="control-label">AM Neon 80 · ${esc(group)}</p><div class="assignment-grid">${options.map(option=>assignmentButton(option,current)).join("")}</div></div>`).join("")}
      ${vendorGroups.map(({group,options})=>`<div class="assignment-section"><p class="control-label">Angry Miao · ${group}</p><div class="assignment-grid">${options.map(option=>assignmentButton(option,current)).join("")}</div></div>`).join("")}
    </div>
  </section>`;
}

// CyberBoard 75% geometry authored from the CB04 matrix occupancy read off
// the device (81 keys); 1u = 6.1% of the stage, right column at 93.9%.
const CB04_LAYOUT = [
  [0,0,0,6.1],[1,6.1,0,6.1],[2,12.2,0,6.1],[3,18.3,0,6.1],[4,24.4,0,6.1],[5,30.5,0,6.1],[6,36.6,0,6.1],[7,42.7,0,6.1],[8,48.8,0,6.1],[9,54.9,0,6.1],[10,61,0,6.1],[11,67.1,0,6.1],[12,73.2,0,6.1],[13,79.3,0,6.1],[14,93.9,0,6.1],
  [25,0,18,6.1],[26,6.1,18,6.1],[27,12.2,18,6.1],[28,18.3,18,6.1],[29,24.4,18,6.1],[30,30.5,18,6.1],[31,36.6,18,6.1],[32,42.7,18,6.1],[33,48.8,18,6.1],[34,54.9,18,6.1],[35,61,18,6.1],[36,67.1,18,6.1],[37,73.2,18,6.1],[38,79.3,18,12.2],[39,93.9,18,6.1],
  [50,0,34,9.15],[51,9.15,34,6.1],[52,15.25,34,6.1],[53,21.35,34,6.1],[54,27.45,34,6.1],[55,33.55,34,6.1],[56,39.65,34,6.1],[57,45.75,34,6.1],[58,51.85,34,6.1],[59,57.95,34,6.1],[60,64.05,34,6.1],[61,70.15,34,6.1],[62,76.25,34,6.1],[63,82.35,34,9.15],[64,93.9,34,6.1],
  [75,0,50,10.7],[76,10.7,50,6.1],[77,16.8,50,6.1],[78,22.9,50,6.1],[79,29,50,6.1],[80,35.1,50,6.1],[81,41.2,50,6.1],[82,47.3,50,6.1],[83,53.4,50,6.1],[84,59.5,50,6.1],[85,65.6,50,6.1],[86,71.7,50,6.1],[88,77.8,50,13.7],[89,93.9,50,6.1],
  [100,0,66,13.7],[102,13.7,66,6.1],[103,19.8,66,6.1],[104,25.9,66,6.1],[105,32,66,6.1],[106,38.1,66,6.1],[107,44.2,66,6.1],[108,50.3,66,6.1],[109,56.4,66,6.1],[110,62.5,66,6.1],[111,68.6,66,6.1],[112,74.7,66,10.7],[113,87.8,66,6.1],
  [125,0,82,7.6],[126,7.6,82,7.6],[127,15.2,82,7.6],[131,22.8,82,38.2],[135,61,82,6.1],[136,67.1,82,6.1],[137,81.7,82,6.1],[138,87.8,82,6.1],[139,93.9,82,6.1],
];

function activeLayout() {
  const family=productFamily(productId());
  if (family === "80") return {name:"Relic 80", className:"relic", keys:RELIC_LAYOUT};
  if (family === "CB" && productId() === "CB04") return {name:"CyberBoard", className:"cyber", keys:CB04_LAYOUT};
  if (family === "ALICE") return {name:"AFA", className:"afa", keys:AFA_LAYOUT};
  if (family === "NEON") {
    const device=displayGeometryDevice();
    const keys=projectVialKeyLayout(device);
    return keys
      ? {name:"AM Neon 80",className:"neon",keys}
      : {name:"AM Neon 80",className:"neon",keys:[],unavailable:true};
  }
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

function restoreFocus(selector) {
  requestAnimationFrame(() => document.querySelector(selector)?.focus({preventScroll: true}));
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
  const model = activeLedModel();
  if (!model) return null;
  const targets = model.targets.map(target => target.key);
  return {
    family: productFamily(productId()),
    productId: productId(),
    slots: [5, 6, 7],
    supportedTargets: targets,
  };
}

function renderRoute() {
  stopPlayback(false);
  const route = state.lighting.route;
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
  if (route === ROUTES.LIBRARY || route === ROUTES.EDIT) {
    $("#lighting-shell").hidden = false;
    renderLightingShell();
    return;
  }
  if (!state.config) {
    $("#empty-state").hidden = false;
    return;
  }
  $("#screen").hidden = false;
  if (route === ROUTES.KEYMAP) renderKeymap();
  else if (route === ROUTES.MACROS) renderMacros();
}

function renderLightingJobStrip() {
  const host = $("#lighting-job-host");
  const job = state.lighting.activeJob;
  if (!job || !aiReady()) {
    host.replaceChildren();
    return;
  }
  let strip = $("#lighting-job-strip",host);
  if (!strip) {
    host.innerHTML=`<section id="lighting-job-strip" class="lighting-job-strip">
      <span class="job-state-mark" aria-hidden="true"></span>
      <div class="job-strip-copy"><strong id="lighting-job-phase">Lighting job</strong><span id="lighting-job-detail">Preparing local workspace…</span></div>
      <progress id="lighting-job-progress" max="1" value="0" hidden></progress>
      <div class="job-strip-actions"><button id="lighting-job-view" type="button" class="button ghost">View</button><button id="lighting-job-cancel" type="button" class="button ghost">Cancel</button></div>
      <span id="lighting-job-phase-live" class="sr-only" aria-live="polite"></span>
    </section>`;
    strip=$("#lighting-job-strip",host);
    $("#lighting-job-view",host).addEventListener("click",revealGenerationStudio);
    $("#lighting-job-cancel",host).addEventListener("click",cancelLightingJob);
  }
  const phase = job.phase ? job.phase.replaceAll("_", " ") : "Ready";
  const phaseLabel = phase.charAt(0).toUpperCase() + phase.slice(1);
  if ($("#lighting-job-phase").textContent !== phaseLabel) {
    $("#lighting-job-phase").textContent = phaseLabel;
    $("#lighting-job-phase-live").textContent = `Lighting job: ${phaseLabel}`;
  }
  const progress = job.progress;
  const hasProgress = progress && Number(progress.total) > 0;
  $("#lighting-job-detail").textContent = hasProgress
    ? `${progress.completed} of ${progress.total} complete`
    : "Your work is saved locally as it completes.";
  const progressNode = $("#lighting-job-progress");
  progressNode.hidden = !hasProgress;
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

function arrayBufferToBase64(buffer) {
  const bytes=new Uint8Array(buffer);
  let binary="";
  for(let index=0;index<bytes.length;index+=0x8000){
    binary+=String.fromCharCode(...bytes.subarray(index,index+0x8000));
  }
  return btoa(binary);
}

async function importLibraryProfiles(input) {
  const files=[...input.files];
  input.value="";
  if(!files.length||state.library.importing)return;
  state.library.importing=true;
  renderLibrary();
  let imported=0;
  const failures=[];
  try{
    for(const file of files){
      try{
        const data=arrayBufferToBase64(await file.arrayBuffer());
        await api("/api/library/import/profile",{
          method:"POST",
          body:JSON.stringify({name:file.name,data}),
        });
        imported++;
      }catch(error){
        failures.push(`${file.name}: ${error.message}`);
      }
    }
    if(imported){
      state.library.filter="keymaps";
      state.library.loaded=false;
      await loadLibrary({force:true});
    }
    if(failures.length){
      toast(
        imported?"Some profiles were not added":"Profiles were not added",
        failures.slice(0,3).join("\n"),
        "error",
      );
    }else{
      toast(
        imported===1?"Profile added to Library":"Profiles added to Library",
        `${imported} exact JSON file${imported===1?" was":"s were"} banked.`,
        "success",
      );
    }
  }finally{
    state.library.importing=false;
    if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }
}

async function saveMappingToLibrary() {
  if(!state.config)return;
  const button=$("#save-mapping-library");
  if(button)button.disabled=true;
  try{
    const revision=await synchronizeOpenDocument();
    if(!revision)throw new Error(state.documentSyncError||"The open document could not be synchronized.");
    const targetKeyLayout=profileTargetLayout();
    const detail=await api("/api/library/save/profile",{
      method:"POST",
      body:JSON.stringify({
        name:state.fileName||`${productLabel(productId())} mapping`,
        document_revision:revision,
        ...(targetKeyLayout?{key_layout:targetKeyLayout}:{}),
      }),
    });
    state.library.loaded=false;
    toast("Mapping saved to Library",`${detail.name} · ${detail.item.profile.sections.length} sections`,"success");
  }catch(error){
    toast("Could not save mapping",error.message,"error");
  }finally{
    if(button&&button.isConnected)button.disabled=false;
  }
}

function clearLibraryAssetUrls() {
  for(const url of state.library.assetUrls.values())URL.revokeObjectURL(url);
  state.library.assetUrls.clear();
  state.library.assetErrors.clear();
}

const profileCompatibilityStatuses=["exact","convertible","portable","blocked"];

function libraryManifest(detail) {
  return detail?.job||detail?.item||null;
}

function libraryCatalogPath(catalogId) {
  return String(catalogId||"").split(":").map(encodeURIComponent).join(":");
}

function libraryFilterQuery() {
  return libraryCatalogQuery({
    filter:state.library.filter,
    page:state.library.page,
    limit:state.library.limit,
    query:state.library.query,
  });
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
  const manifest=libraryManifest(detail);
  const procedural=manifest?.assets?.find(asset=>asset.kind==="preview_animation")
    || manifest?.assets?.find(asset=>asset.kind==="raster_animation");
  if(procedural)return procedural;
  const selected=manifest?.candidates?.find(candidate=>candidate.candidate_id===manifest.selected_candidate_id);
  const first=selected||manifest?.candidates?.[0];
  if(first?.asset_id)return {asset_id:first.asset_id,mime_type:first.mime_type||"image/png"};
  return manifest?.assets?.find(asset=>asset.kind==="preview_poster")
    || manifest?.assets?.find(asset=>["preview_animation","source_video","preview"].includes(asset.kind))
    || manifest?.assets?.find(asset=>asset.kind==="source")
    || null;
}

async function loadLibraryAsset(catalogId,assetId,{retry=false}={}) {
  const key=`${catalogId}:${assetId}`;
  const epoch=state.library.epoch;
  if(state.library.assetUrls.has(key))return;
  const lease=state.library.assetLoads.begin(key,epoch);
  if(!lease)return;
  state.library.assetErrors.delete(key);
  try{
    const response=await fetch(`/api/library/assets/${libraryCatalogPath(catalogId)}/${encodeURIComponent(assetId)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load asset (${response.status})`);}
    const url=URL.createObjectURL(await response.blob());
    if(!lease.current(state.library.epoch)){URL.revokeObjectURL(url);return;}
    const previous=state.library.assetUrls.get(key);
    if(previous&&previous!==url)URL.revokeObjectURL(previous);
    state.library.assetUrls.set(key,url);
  }catch(error){
    if(!lease.current(state.library.epoch))return;
    if(retry)state.library.assetErrors.set(key,error.message);
    else{
      state.library.assetErrors.set(key,"Retrying…");
      setTimeout(()=>loadLibraryAsset(catalogId,assetId,{retry:true}),250);
    }
  }finally{
    const ownsCurrent=lease.current(state.library.epoch);
    lease.release();
    if(ownsCurrent&&state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }
}

function profileTargetLayout() {
  if(!state.config||!state.loadedDevice)return null;
  const device=state.devices.find(item=>deviceKey(item)===state.loadedDevice);
  return device&&sameProductFamily(productId(),device.product_id)&&Array.isArray(device.key_layout)&&device.key_layout.length
    ? device.key_layout
    : null;
}

async function libraryCompatibilityRevision() {
  if(!state.config)return null;
  if(state.library.compatibilityRevisionPromise){
    return state.library.compatibilityRevisionPromise;
  }
  const request=synchronizeOpenDocument();
  state.library.compatibilityRevisionPromise=request;
  try{
    return await request;
  }finally{
    if(state.library.compatibilityRevisionPromise===request){
      state.library.compatibilityRevisionPromise=null;
    }
  }
}

async function ensureLibraryProfileCompatibility(catalogId,{force=false}={}) {
  const detail=state.library.details.get(catalogId);
  if(detail?.kind!=="keyboard_profile"||state.library.compatibilityLoads.has(catalogId))return;
  if(!state.config){
    state.library.compatibilities.set(catalogId,{revision:null,result:null,error:"Open or read a keyboard configuration to preview what can be imported."});
    renderLibrary();
    return;
  }
  if(!force&&state.library.compatibilities.get(catalogId)?.revision===state.documentRevision)return;
  const epoch=state.library.epoch;
  state.library.compatibilityLoads.add(catalogId);
  state.library.compatibilities.delete(catalogId);
  renderLibrary();
  try{
    const revision=await libraryCompatibilityRevision();
    if(!revision)throw new Error(state.documentSyncError||"The open document could not be synchronized.");
    const targetKeyLayout=profileTargetLayout();
    const result=await api(`/api/library/items/${libraryCatalogPath(catalogId)}/compatibility`,{
      method:"POST",
      body:JSON.stringify({
        document_revision:revision,
        ...(targetKeyLayout?{target_key_layout:targetKeyLayout}:{}),
      }),
    });
    if(epoch!==state.library.epoch)return;
    state.library.compatibilities.set(catalogId,{revision,result,error:""});
    const allowed=compatibleProfileSections(result);
    if(state.library.profileSelections.has(catalogId)){
      const current=state.library.profileSelections.get(catalogId);
      state.library.profileSelections.set(
        catalogId,
        current.filter(section=>allowed.includes(section)),
      );
    }else{
      state.library.profileSelections.set(catalogId,allowed);
    }
  }catch(error){
    if(epoch===state.library.epoch){
      state.library.compatibilities.set(catalogId,{revision:state.documentRevision,result:null,error:error.message});
    }
  }finally{
    state.library.compatibilityLoads.delete(catalogId);
    if(epoch===state.library.epoch&&state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  }
}

async function ensureLibraryItemDetail(catalogId) {
  if(state.library.details.has(catalogId)||state.library.detailLoads.has(catalogId))return;
  const epoch=state.library.epoch;
  state.library.detailLoads.add(catalogId);
  try{
    const detail=await api(`/api/library/items/${libraryCatalogPath(catalogId)}`);
    if(epoch!==state.library.epoch)return;
    state.library.details.set(catalogId,detail);
    const cover=libraryCoverAsset(detail);
    if(cover)void loadLibraryAsset(catalogId,cover.asset_id);
    if(state.library.selectedCatalogId===catalogId){
      for(const asset of libraryManifest(detail)?.assets||[]){
        if(["concept","selected_still","preview_poster","preview_animation","source_video","preview","source"].includes(asset.kind))void loadLibraryAsset(catalogId,asset.asset_id);
      }
    }
    if(detail.kind==="keyboard_profile")void ensureLibraryProfileCompatibility(catalogId);
    if(state.lighting.route===ROUTES.LIBRARY){
      renderLibrary();
      if(state.library.selectedCatalogId===catalogId){
        requestAnimationFrame(()=>$("#library-detail-title")?.focus());
      }
    }
  }catch(error){
    if(epoch===state.library.epoch){state.library.error=error.message;if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();}
  }finally{state.library.detailLoads.delete(catalogId);}
}

async function loadLibrary({force=false}={}) {
  if(!force&&(state.library.loading||state.library.loaded))return;
  state.library.loading=true;
  state.library.error="";
  const epoch=++state.library.epoch;
  if(force){
    clearLibraryAssetUrls();
    state.library.items=[];
    state.library.details.clear();
    state.library.detailLoads.clear();
    state.library.compatibilities.clear();
    state.library.compatibilityLoads.clear();
    state.library.profileSelections.clear();
    state.library.selectedCatalogId=null;
  }
  renderLibrary();
  let reloadLastPage=false;
  try{
    const result=await api(`/api/library/items?${libraryFilterQuery()}`);
    if(epoch!==state.library.epoch)return;
    state.library.items=result.items||[];
    state.library.warnings=result.errors||[];
    state.library.page=Number(result.page||state.library.page);
    state.library.total=Number(result.total||0);
    state.library.hasMore=Boolean(result.has_more);
    state.library.loaded=true;
    if(!state.library.items.length&&state.library.total&&state.library.page>1){
      state.library.page=Math.max(1,Math.ceil(state.library.total/state.library.limit));
      state.library.loaded=false;
      reloadLastPage=true;
      return;
    }
    for(const item of state.library.items)void ensureLibraryItemDetail(item.catalog_id);
  }catch(error){
    if(epoch===state.library.epoch){
      state.library.items=[];
      state.library.total=0;
      state.library.hasMore=false;
      state.library.error=error.message;
      state.library.loaded=true;
    }
  }finally{
    if(epoch===state.library.epoch){
      state.library.loading=false;
      renderLibrary();
      if(reloadLastPage)void loadLibrary({force:true});
    }
  }
}

function libraryEmptyMarkup() {
  if(state.library.loading)return '<div class="library-empty"><div class="loader"></div><strong>Loading your Library…</strong></div>';
  if(state.library.error)return `<div class="library-empty"><strong>Library could not be loaded.</strong><p>${esc(state.library.error)}</p><button type="button" class="button ghost" data-library-retry>Try again</button></div>`;
  if(!state.settings?.library?.current_root)return '<div class="library-empty"><strong>Choose a Library folder to bank profiles and lighting.</strong><p>Settings controls where imported files and generated assets are stored.</p><button type="button" class="button primary" data-library-settings>Open Settings</button></div>';
  return '<div class="library-empty"><strong>Nothing here yet.</strong><p>Add a keyboard JSON file, save a mapping, or create lighting to bank it here.</p></div>';
}

function libraryKindLabel(kind) {
  return {
    generation_job:"Generated",
    keyboard_profile:"Keyboard profile",
    media_source:"Media source",
    lighting_composition:"Lighting",
  }[kind]||libraryStatusLabel(kind);
}

function latestLibraryGeneratedAttempt(detail) {
  const attempts=detail?.job?.procedural_attempts||[];
  return attempts.length?attempts[attempts.length-1]:null;
}

function libraryDetailCompatibility(catalogId,detail) {
  if(!state.config)return {status:"unknown",label:"Open a keyboard"};
  if(detail?.kind==="media_source"){
    return {status:"convertible",label:"Fits this keyboard"};
  }
  if(detail?.kind==="keyboard_profile"){
    const compatibility=state.library.compatibilities.get(catalogId);
    if(compatibility?.result){
      const status=compatibility.result.summary||"unknown";
      return {
        status,
        label:status==="blocked"?"Incompatible":libraryStatusLabel(status),
      };
    }
    if(compatibility?.error)return {status:"blocked",label:"Check failed"};
    return {status:"unknown",label:"Checking…"};
  }
  if(detail?.kind==="lighting_composition"){
    const composition=detail.item?.composition;
    const family=detail.item?.device?.family;
    if(!composition||family!==productFamily(productId())){
      return {status:"blocked",label:"Incompatible"};
    }
    const target=composition.destination?.target;
    if(!activeLedModel()?.targets.some(candidate=>candidate.key===target)){
      return {status:"blocked",label:"Incompatible"};
    }
    const exact=Object.entries(composition.tracks||{}).every(
      ([track,metadata])=>servedGeometry(productFamily(productId()),track)?.signature===metadata.signature,
    );
    return exact
      ?{status:"exact",label:"Exact match"}
      :{status:"blocked",label:"Incompatible"};
  }
  if(detail?.kind==="generation_job"){
    const attempt=latestLibraryGeneratedAttempt(detail);
    const target=detail.job?.target;
    const targetKey=target?.targets?.[0];
    const exact=Boolean(
      attempt?.mapped_result_asset_id
      &&productFamily(target?.family||target?.product_id)===productFamily(productId())
      &&activeLedModel()?.targets.some(candidate=>candidate.key===targetKey),
    );
    return exact
      ?{status:"exact",label:"Exact match"}
      :{status:"blocked",label:"Browse only"};
  }
  return {status:"unknown",label:"Saved"};
}

function libraryCardMarkup(item) {
  const detail=state.library.details.get(item.catalog_id);
  const cover=libraryCoverAsset(detail);
  const url=cover&&state.library.assetUrls.get(`${item.catalog_id}:${cover.asset_id}`);
  const icon=item.kind==="keyboard_profile"?"⌨":"✦";
  const compatibility=libraryDetailCompatibility(item.catalog_id,detail);
  const deviceLabel=item.device?.product_label||item.device?.product_id||item.target?.product_id||"Any keyboard";
  const frameLabel=Number.isSafeInteger(item.frame_count)?`${item.frame_count} frame${item.frame_count===1?"":"s"}`:`${item.asset_count} asset${item.asset_count===1?"":"s"}`;
  return `<button type="button" class="library-card" data-library-item="${esc(item.catalog_id)}" aria-label="Open ${esc(item.name)}">
    <span class="library-card-poster">${url?`<img src="${esc(url)}" alt="">`:`<span class="library-card-placeholder" aria-hidden="true">${icon}</span>`}</span>
    <span class="library-card-copy"><strong>${esc(item.name)}</strong><span>${esc(libraryKindLabel(item.kind))} · ${esc(libraryStatusLabel(item.origin))} · ${libraryDate(item.updated_at)}</span><small>${esc(deviceLabel)} · ${frameLabel}</small><span class="library-card-badges"><span class="pill ${item.status==="partial"?"muted":""}">${esc(libraryStatusLabel(item.status))}</span><span class="pill ${compatibility.status==="blocked"||compatibility.status==="unknown"?"muted":""}">${esc(compatibility.label)}</span></span></span>
  </button>`;
}

function libraryMediaMarkup(catalogId,asset,index) {
  const url=state.library.assetUrls.get(`${catalogId}:${asset.asset_id}`);
  const label=asset.kind.replaceAll("_"," ");
  const loadError=state.library.assetErrors.get(`${catalogId}:${asset.asset_id}`);
  if(!url&&loadError&&loadError!=="Retrying…")return `<div class="library-media-card failed"><strong>Could not load this ${esc(label)}.</strong><small>${esc(loadError)}</small><button type="button" class="button ghost" data-library-asset-retry="${esc(asset.asset_id)}" data-library-asset-item="${esc(catalogId)}">Retry</button></div>`;
  if(!url)return `<div class="library-media-card loading"><span class="library-card-placeholder">${loadError||"Loading…"}</span><small>${esc(label)}</small></div>`;
  if(asset.mime_type==="video/mp4")return `<figure class="library-media-card"><video src="${esc(url)}" controls muted playsinline preload="metadata"></video><figcaption>${esc(label)}</figcaption></figure>`;
  return `<figure class="library-media-card"><img src="${esc(url)}" alt="Saved lighting asset ${index+1}"><figcaption><span>${esc(label)}</span></figcaption></figure>`;
}

function libraryProfileCompatibilityMarkup(catalogId,detail) {
  const compatibility=state.library.compatibilities.get(catalogId);
  if(!state.config)return '<section class="profile-compatibility-sheet"><h3>Compatibility</h3><p>Open or read a keyboard configuration to preview what can be imported.</p></section>';
  if(state.library.compatibilityLoads.has(catalogId)||!compatibility)return '<section class="profile-compatibility-sheet"><h3>Compatibility</h3><div class="loader"></div><p>Comparing this profile with the open document…</p></section>';
  if(compatibility.error)return `<section class="profile-compatibility-sheet"><h3>Compatibility</h3><p class="library-warning">${esc(compatibility.error)}</p><button type="button" class="button ghost" data-library-compatibility-retry>Try again</button></section>`;
  const plan=compatibility.result;
  const allowed=compatibleProfileSections(plan);
  const selected=new Set(state.library.profileSelections.get(catalogId)||allowed);
  const rows=["keymap","macros","lighting"].map(section=>{
    const verdict=plan.sections?.[section]||{status:"blocked",detail:"This section is unavailable."};
    const status=profileCompatibilityStatuses.includes(verdict.status)?verdict.status:"blocked";
    const available=allowed.includes(section);
    return `<li class="${available?"compatible":"blocked"}"><input type="checkbox" data-library-profile-section="${esc(section)}" aria-label="Import ${esc(section)}" ${available&&selected.has(section)?"checked":""} ${available&&!detail.removed?"":"disabled"}><span><strong>${esc(libraryStatusLabel(section))}</strong><small>${esc(verdict.detail)}</small></span><span class="pill ${available?"":"muted"}">${esc(libraryStatusLabel(status))}</span></li>`;
  }).join("");
  const canApply=!detail.removed&&selected.size>0&&!state.library.mutatingCatalogId;
  return `<section class="profile-compatibility-sheet"><div><h3>Compatibility</h3><span class="pill">${esc(libraryStatusLabel(plan.summary))}</span></div><p>Choose the safe sections to import. Apply changes only the open document through one undo checkpoint; it never writes the keyboard.</p><ul>${rows}</ul>${detail.removed?"":`<div class="profile-compatibility-actions"><button type="button" class="button primary" data-library-apply-profile ${canApply?"":"disabled"}>Apply selected sections</button></div>`}</section>`;
}

function libraryDetailMarkup(catalogId) {
  const detail=state.library.details.get(catalogId);
  if(!detail)return '<div class="library-empty"><div class="loader"></div><strong>Loading saved media…</strong></div>';
  const manifest=libraryManifest(detail);
  const media=(manifest?.assets||[]).filter(asset=>["concept","selected_still","preview","preview_poster","preview_animation","raster_animation","source_video","source"].includes(asset.kind));
  const profile=detail.kind==="keyboard_profile"?detail.item?.profile:null;
  const sectionList=(profile?.sections||[]).map(section=>`<span class="pill muted">${esc(libraryStatusLabel(section))}</span>`).join("");
  const compatibility=libraryDetailCompatibility(catalogId,detail);
  const busy=state.library.mutatingCatalogId===catalogId;
  let primaryAction="";
  if(!detail.removed&&detail.kind==="media_source"){
    primaryAction=`<button type="button" class="button primary" data-library-open-source ${state.config?"":"disabled"}>Open in Studio</button>`;
  }else if(!detail.removed&&detail.kind==="lighting_composition"){
    primaryAction=`<button type="button" class="button primary" data-library-apply-lighting ${compatibility.status==="exact"&&!busy?"":"disabled"}>Apply to Custom ${state.ledSlot-4}</button>`;
  }else if(!detail.removed&&detail.kind==="generation_job"){
    primaryAction=`<button type="button" class="button primary" data-library-apply-generated ${compatibility.status==="exact"&&!busy?"":"disabled"}>Apply saved result to Custom ${state.ledSlot-4}</button>`;
  }
  const ownershipActions=detail.removed
    ?`<button type="button" class="button ghost" data-library-restore ${busy?"disabled":""}>Restore</button><button type="button" class="button danger" data-library-delete ${busy?"disabled":""}>Delete forever…</button>`
    :`<button type="button" class="button ghost" data-library-remove ${busy?"disabled":""}>Remove from Library</button>`;
  const actions=`${primaryAction}${ownershipActions}`;
  const deviceLabel=detail.device?.product_label||detail.device?.product_id||detail.target?.product_id||"Any supported keyboard";
  return `<section class="library-detail" aria-labelledby="library-detail-title">
    <button type="button" class="library-back" data-library-back>← Library</button>
    <header><div><p class="eyebrow">${esc(libraryKindLabel(detail.kind))}</p><h2 id="library-detail-title" tabindex="-1">${esc(detail.name)}</h2><p>${libraryDate(detail.created_at)} · ${esc(libraryStatusLabel(detail.origin))} · ${esc(deviceLabel)} · ${detail.asset_count} saved asset${detail.asset_count===1?"":"s"}</p></div><div class="library-card-badges"><span class="pill ${detail.status==="partial"?"muted":""}">${esc(libraryStatusLabel(detail.status))}</span><span class="pill ${compatibility.status==="blocked"||compatibility.status==="unknown"?"muted":""}">${esc(compatibility.label)}</span>${detail.removed?'<span class="pill muted">Removed</span>':""}</div></header>
    ${profile?`<div class="profile-section-list" aria-label="Saved profile sections">${sectionList}</div>${libraryProfileCompatibilityMarkup(catalogId,detail)}`:""}
    ${media.length?`<div class="library-media-grid">${media.map((asset,index)=>libraryMediaMarkup(catalogId,asset,index)).join("")}</div>`:profile?"":'<p class="library-no-media">This item has no viewable media yet.</p>'}
    <div class="library-detail-actions">${actions}</div>
    ${manifest?.costs?.actual_incomplete?'<p class="library-warning">Provider cost reporting is incomplete for this item.</p>':""}
  </section>`;
}

function closeLibraryDetail() {
  const catalogId=state.library.selectedCatalogId;
  state.library.selectedCatalogId=null;
  renderLibrary();
  requestAnimationFrame(()=>{
    const target=$$("[data-library-item]",$("#library-content")).find(
      card=>card.dataset.libraryItem===catalogId,
    );
    target?.focus();
  });
}

function wireLibraryGridNavigation() {
  const grid=$(".library-grid",$("#library-content"));
  if(!grid)return;
  const cards=$$("[data-library-item]",grid);
  for(const card of cards){
    card.addEventListener("keydown",event=>{
      if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key))return;
      const index=cards.indexOf(event.currentTarget);
      const columns=Math.max(
        1,
        getComputedStyle(grid).gridTemplateColumns.split(/\s+/).filter(Boolean).length,
      );
      const next=nextCatalogIndex({index,count:cards.length,columns,key:event.key});
      if(next===index)return;
      event.preventDefault();
      cards[next].focus();
    });
  }
}

function updateLibraryProfileSelection(catalogId,section,checked) {
  const plan=state.library.compatibilities.get(catalogId)?.result;
  const allowed=compatibleProfileSections(plan);
  if(!allowed.includes(section))return;
  const selected=new Set(state.library.profileSelections.get(catalogId)||allowed);
  if(checked)selected.add(section);
  else selected.delete(section);
  state.library.profileSelections.set(
    catalogId,
    allowed.filter(candidate=>selected.has(candidate)),
  );
  renderLibrary();
}

function showLibraryConfirmation({title,message,label,danger=false,action}) {
  const dialog=$("#library-confirm-dialog");
  const button=$("#library-confirm-action");
  libraryConfirmAction=action;
  $("#library-confirm-title").textContent=title;
  $("#library-confirm-message").textContent=message;
  button.textContent=label;
  button.className=`button ${danger?"danger":"primary"}`;
  button.disabled=false;
  dialog.showModal();
}

function requestLibraryProfileApply(catalogId) {
  const detail=state.library.details.get(catalogId);
  const plan=state.library.compatibilities.get(catalogId)?.result;
  let sections;
  try{
    sections=normalizeProfileSections(
      plan,
      state.library.profileSelections.get(catalogId)||[],
    );
  }catch(error){
    return toast("Choose profile sections",error.message,"error");
  }
  showLibraryConfirmation({
    title:"Apply profile sections?",
    message:`${detail?.name||"This profile"} will replace only ${sections.map(libraryStatusLabel).join(", ")} in the open document. Destination identity and every unselected section stay unchanged. This creates one undo checkpoint and does not write the keyboard.`,
    label:"Apply sections",
    action:()=>applyLibraryProfile(catalogId),
  });
}

async function applyLibraryProfile(catalogId) {
  if(state.library.mutatingCatalogId||!state.config)return;
  const compatibility=state.library.compatibilities.get(catalogId)?.result;
  const sections=normalizeProfileSections(
    compatibility,
    state.library.profileSelections.get(catalogId)||[],
  );
  const catalogEpoch=state.library.epoch;
  const lease=state.library.requests.begin("mutation",catalogEpoch);
  const config=state.config;
  const configFingerprint=JSON.stringify(config);
  state.library.mutatingCatalogId=catalogId;
  renderLibrary();
  try{
    const revision=await synchronizeOpenDocument();
    if(
      !revision
      ||!lease.current(state.library.epoch)
      ||state.config!==config
      ||JSON.stringify(config)!==configFingerprint
    ){
      if(lease.current(state.library.epoch)){
        throw new Error("The open document changed before Apply. Review the profile again.");
      }
      return;
    }
    const targetKeyLayout=profileTargetLayout();
    const result=await api(`/api/library/items/${libraryCatalogPath(catalogId)}/apply`,{
      method:"POST",
      body:JSON.stringify({
        document_revision:revision,
        sections,
        ...(targetKeyLayout?{target_key_layout:targetKeyLayout}:{}),
      }),
    });
    if(
      !lease.current(state.library.epoch)
      ||state.config!==config
      ||JSON.stringify(config)!==configFingerprint
    )return;
    lease.release();
    state.library.mutatingCatalogId=null;
    mutate(()=>{
      state.config=clone(result.config);
      state.documentRevision=null;
      state.documentSyncEpoch++;
      state.appliedLightingProvenance=null;
      state.layer=Math.min(state.layer,Math.max(0,layers().length-1));
      state.macro=Math.min(state.macro,Math.max(0,macros().length-1));
      state.ledFrame=0;
    });
    state.library.compatibilities.clear();
    state.library.profileSelections.clear();
    await synchronizeOpenDocument();
    toast(
      "Profile sections applied",
      `${result.applied_sections.map(libraryStatusLabel).join(", ")} changed through one undo checkpoint. Nothing was written to the keyboard.`,
      "success",
    );
  }catch(error){
    if(lease.current(state.library.epoch)){
      toast("Could not apply profile",error.message,"error");
    }
  }finally{
    lease.release();
    if(state.library.mutatingCatalogId===catalogId){
      state.library.mutatingCatalogId=null;
      renderLibrary();
    }
  }
}

async function applyLibraryGenerated(catalogId) {
  if(state.library.mutatingCatalogId||!state.config)return;
  const detail=state.library.details.get(catalogId);
  const attempt=latestLibraryGeneratedAttempt(detail);
  const target=detail?.job?.target;
  const targetKey=target?.targets?.[0];
  if(
    detail?.kind!=="generation_job"
    ||!attempt?.mapped_result_asset_id
    ||libraryDetailCompatibility(catalogId,detail).status!=="exact"
  ){
    return toast("Could not apply generated lighting","This saved result does not exactly match the open keyboard.","error");
  }
  const catalogEpoch=state.library.epoch;
  const lease=state.library.requests.begin("mutation",catalogEpoch);
  const config=state.config;
  const configFingerprint=JSON.stringify(config);
  state.library.mutatingCatalogId=catalogId;
  renderLibrary();
  try{
    const response=await fetch(
      `/api/library/assets/${libraryCatalogPath(catalogId)}/${encodeURIComponent(attempt.mapped_result_asset_id)}`,
      {headers:{"X-AM-Token":token}},
    );
    if(!response.ok){
      const data=await response.json().catch(()=>({}));
      throw new Error(data.error||`Could not load generated lighting (${response.status})`);
    }
    const result=await response.json();
    if(
      !lease.current(state.library.epoch)
      ||state.config!==config
      ||JSON.stringify(config)!==configFingerprint
    )return;
    if(!result?.tracks)throw new Error("The saved generated result is invalid.");
    const pairsRelic=(target.targets||[]).includes("spotlight_frames");
    lease.release();
    state.library.mutatingCatalogId=null;
    mutate(()=>{
      state.ledTarget=targetKey;
      applyLedResultToPage(getPage(state.ledSlot),result,targetKey,pairsRelic);
      state.ledFrame=0;
      state.documentRevision=null;
      state.documentSyncEpoch++;
      state.appliedLightingProvenance=null;
    },false);
    state.studioTool="paint";
    navigateTo(ROUTES.EDIT);
    toast(
      "Generated lighting applied",
      `The saved result changed Custom ${state.ledSlot-4} through one undo checkpoint. Nothing was written to the keyboard.`,
      "success",
    );
  }catch(error){
    if(lease.current(state.library.epoch)){
      toast("Could not apply generated lighting",error.message,"error");
    }
  }finally{
    lease.release();
    if(state.library.mutatingCatalogId===catalogId){
      state.library.mutatingCatalogId=null;
      renderLibrary();
    }
  }
}

async function runLibraryOwnershipMutation(catalogId,{method="POST",suffix="",success}) {
  if(state.library.mutatingCatalogId)return null;
  const catalogEpoch=state.library.epoch;
  const lease=state.library.requests.begin("mutation",catalogEpoch);
  state.library.mutatingCatalogId=catalogId;
  renderLibrary();
  try{
    const result=await api(
      `/api/library/items/${libraryCatalogPath(catalogId)}${suffix}`,
      {method,body:method==="DELETE"?undefined:JSON.stringify({})},
    );
    if(!lease.current(state.library.epoch)){
      state.library.loaded=false;
      void loadLibrary({force:true});
      return null;
    }
    success(result);
    lease.release();
    state.library.mutatingCatalogId=null;
    state.library.selectedCatalogId=null;
    state.library.loaded=false;
    await loadLibrary({force:true});
    return result;
  }catch(error){
    if(lease.current(state.library.epoch)){
      toast("Library action failed",error.message,"error");
    }
    return null;
  }finally{
    lease.release();
    if(state.library.mutatingCatalogId===catalogId){
      state.library.mutatingCatalogId=null;
      renderLibrary();
    }
  }
}

async function removeLibraryItem(catalogId) {
  const detail=state.library.details.get(catalogId);
  await runLibraryOwnershipMutation(catalogId,{
    suffix:"/remove",
    success:result=>{
      state.library.undoRemoval={
        catalogId,
        name:result.name||detail?.name||"Library item",
      };
      toast("Removed from Library","Use Undo to restore it, or manage it from Removed.","success");
    },
  });
}

async function undoLibraryRemoval() {
  const removal=state.library.undoRemoval;
  if(!removal)return;
  await runLibraryOwnershipMutation(removal.catalogId,{
    suffix:"/restore",
    success:()=>{
      state.library.undoRemoval=null;
      toast("Library item restored",`${removal.name} is back in the Library.`,"success");
    },
  });
}

async function restoreLibraryItem(catalogId) {
  const detail=state.library.details.get(catalogId);
  await runLibraryOwnershipMutation(catalogId,{
    suffix:"/restore",
    success:()=>{
      if(state.library.undoRemoval?.catalogId===catalogId)state.library.undoRemoval=null;
      toast("Library item restored",`${detail?.name||"The item"} is back in the Library.`,"success");
    },
  });
}

async function deleteLibraryItemForever(catalogId) {
  const detail=state.library.details.get(catalogId);
  await runLibraryOwnershipMutation(catalogId,{
    method:"DELETE",
    success:()=>{
      if(state.library.undoRemoval?.catalogId===catalogId)state.library.undoRemoval=null;
      toast("Library item deleted",`${detail?.name||"The removed item"} was permanently deleted.`,"success");
    },
  });
}

function requestLibraryDelete(catalogId) {
  const detail=state.library.details.get(catalogId);
  showLibraryConfirmation({
    title:"Delete this item forever?",
    message:`${detail?.name||"This removed item"} and its Library-owned assets will be permanently deleted. Exported files, open documents, and keyboard history are not touched.`,
    label:"Delete forever",
    danger:true,
    action:()=>deleteLibraryItemForever(catalogId),
  });
}

function wireLibraryContent() {
  $$("[data-library-item]",$("#library-content")).forEach(card=>card.addEventListener("click",()=>openLibraryItem(card.dataset.libraryItem)));
  wireLibraryGridNavigation();
  $$("[data-library-asset-retry]",$("#library-content")).forEach(button=>button.addEventListener("click",()=>loadLibraryAsset(button.dataset.libraryAssetItem,button.dataset.libraryAssetRetry,{retry:true})));
  $$("[data-library-profile-section]",$("#library-content")).forEach(input=>input.addEventListener("change",event=>updateLibraryProfileSelection(state.library.selectedCatalogId,event.currentTarget.dataset.libraryProfileSection,event.currentTarget.checked)));
  $("[data-library-back]",$("#library-content"))?.addEventListener("click",closeLibraryDetail);
  $("[data-library-compatibility-retry]",$("#library-content"))?.addEventListener("click",()=>ensureLibraryProfileCompatibility(state.library.selectedCatalogId,{force:true}));
  $("[data-library-open-source]",$("#library-content"))?.addEventListener("click",()=>openLibrarySource(state.library.selectedCatalogId));
  $("[data-library-apply-lighting]",$("#library-content"))?.addEventListener("click",()=>applyLibraryLighting(state.library.selectedCatalogId));
  $("[data-library-apply-generated]",$("#library-content"))?.addEventListener("click",()=>applyLibraryGenerated(state.library.selectedCatalogId));
  $("[data-library-apply-profile]",$("#library-content"))?.addEventListener("click",()=>requestLibraryProfileApply(state.library.selectedCatalogId));
  $("[data-library-remove]",$("#library-content"))?.addEventListener("click",()=>removeLibraryItem(state.library.selectedCatalogId));
  $("[data-library-restore]",$("#library-content"))?.addEventListener("click",()=>restoreLibraryItem(state.library.selectedCatalogId));
  $("[data-library-delete]",$("#library-content"))?.addEventListener("click",()=>requestLibraryDelete(state.library.selectedCatalogId));
  $("[data-library-retry]",$("#library-content"))?.addEventListener("click",()=>loadLibrary({force:true}));
  $("[data-library-settings]",$("#library-content"))?.addEventListener("click",openSettings);
}

function openLibrarySource(catalogId) {
  const detail=state.library.details.get(catalogId);
  const source=detail?.item?.source;
  const destination=currentMediaDestination();
  if(detail?.kind!=="media_source"||!source||!destination){
    return toast(
      "Could not open source",
      "Open a supported keyboard configuration and try again.",
      "error",
    );
  }
  state.sourceTransform=defaultSourceTransform(state.gifResample);
  state.mediaComposition=createMediaDraft({
    catalogId,
    source:{
      asset_id:source.asset_id,
      mime_type:source.mime_type,
      width:source.width,
      height:source.height,
      frame_count:source.frame_count,
      duration_ms:source.duration_ms,
    },
    destination,
    transform:state.sourceTransform,
  });
  state.studioTool="source";
  navigateTo(ROUTES.EDIT);
  void loadMediaCompositionSourceAsset();
  void renderMediaCompositionPreview();
}

async function applyLibraryLighting(catalogId) {
  const detail=state.library.details.get(catalogId);
  const composition=detail?.item?.composition;
  if(detail?.kind!=="lighting_composition"||!composition){
    return toast("Could not apply lighting","This saved lighting item is unavailable.","error");
  }
  try{
    const destination=composition.destination;
    if(
      detail.item.device?.family!==productFamily(productId())
      ||!activeLedModel()?.targets.some(candidate=>candidate.key===destination.target)
    ){
      throw new Error("This rendered lighting does not match the open keyboard.");
    }
    for(const [track,metadata] of Object.entries(composition.tracks||{})){
      if(servedGeometry(productFamily(productId()),track)?.signature!==metadata.signature){
        throw new Error(`The saved ${track} track does not match this keyboard.`);
      }
    }
    const response=await fetch(`/api/library/assets/${libraryCatalogPath(catalogId)}/${encodeURIComponent(composition.rendered_asset_id)}`,{headers:{"X-AM-Token":token}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||`Could not load lighting (${response.status})`);}
    const result=await response.json();
    if(!result?.tracks)throw new Error("The saved LED result is invalid.");
    const pairsRelic=destination.target==="keyframes"&&Boolean(result.tracks.spotlight_frames);
    if(
      !Number.isSafeInteger(destination.lightness)
      ||destination.lightness<0
      ||destination.lightness>100
    ){
      throw new Error("The saved lighting brightness is invalid.");
    }
    const candidate=clone(getPage(state.ledSlot));
    applyLedResultToPage(candidate,result,destination.target,pairsRelic);
    candidate.lightness=Number(destination.lightness);
    const provenance=createLightingProvenance({
      slot:state.ledSlot,
      target:destination.target,
      sourceCatalogId:composition.source_catalog_id,
      transform:composition.transform,
      effects:composition.effects,
      page:candidate,
    });
    mutate(()=>{
      const page=getPage(state.ledSlot);
      applyLedResultToPage(page,result,destination.target,pairsRelic);
      page.lightness=Number(destination.lightness);
      state.appliedLightingProvenance=provenance;
      state.ledTarget=destination.target;
      state.ledFrame=0;
    });
    state.studioTool="paint";
    navigateTo(ROUTES.EDIT);
    toast(
      "Saved lighting applied",
      "The open document changed through one undo checkpoint. Nothing was written to the keyboard.",
      "success",
    );
  }catch(error){
    toast("Could not apply lighting",error.message,"error");
  }
}

function openLibraryItem(catalogId) {
  state.library.lastFocusedCatalogId=catalogId;
  state.library.selectedCatalogId=catalogId;
  state.library.compatibilities.delete(catalogId);
  renderLibrary();
  if(state.library.details.has(catalogId))void ensureLibraryProfileCompatibility(catalogId,{force:true});
  else void ensureLibraryItemDetail(catalogId);
  requestAnimationFrame(()=>$("#library-detail-title")?.focus());
}

function renderLibrary() {
  const content=$("#library-content");
  if(!content)return;
  const selected=state.library.selectedCatalogId;
  if(selected)content.innerHTML=libraryDetailMarkup(selected);
  else if(state.library.items.length)content.innerHTML=`<div class="library-grid">${state.library.items.map(libraryCardMarkup).join("")}</div>`;
  else content.innerHTML=libraryEmptyMarkup();
  const status=$("#library-status");
  status.textContent=state.library.loading
    ?"Refreshing Library…"
    :state.library.warnings.length
      ?"Some previously recorded Library items could not be read."
      :state.library.total
        ?`Showing ${state.library.items.length} of ${state.library.total} saved item${state.library.total===1?"":"s"}`
        :"";
  status.classList.toggle("warning",Boolean(state.library.warnings.length));
  const pages=Math.max(1,Math.ceil(state.library.total/state.library.limit));
  $("#library-page-label").textContent=`Page ${state.library.page} of ${pages}`;
  $("#library-page-previous").disabled=state.library.loading||state.library.page<=1;
  $("#library-page-next").disabled=state.library.loading||!state.library.hasMore;
  const notice=$("#library-notice");
  if(state.library.undoRemoval){
    notice.hidden=false;
    notice.innerHTML=`<span><strong>${esc(state.library.undoRemoval.name)}</strong> was removed.</span><button type="button" class="button ghost" data-library-undo-remove>Undo</button>`;
    $("[data-library-undo-remove]",notice).addEventListener("click",undoLibraryRemoval);
  }else{
    notice.hidden=true;
    notice.replaceChildren();
  }
  $("#library-reveal").disabled=!state.settings?.library?.current_root;
  $("#library-add-files").disabled=state.library.importing;
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
    refreshGenerationStudio();
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.conceptError=error.message;refreshGenerationStudio();}
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
    refreshGenerationStudio();
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.animationError=error.message;refreshGenerationStudio();}
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
    refreshGenerationStudio();
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
  const available = routeAvailability(route, documentDescriptor());
  const routes = [ROUTES.EDIT, ROUTES.LIBRARY];
  const names = ["edit", "library"];
  routes.forEach((candidate, index) => {
    const selected = route === candidate;
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
  const targets = (state.config && activeLedModel()?.targets) || [];
  if (targets.length && !targets.some(target => target.key === state.ledTarget)) state.ledTarget = targets[0].key;
  renderTargetControls(targetHost,targets,state.ledTarget,destinationLocked,target=>{
    cancelLocalAnimationDraft({render:false});
    state.ledTarget = target;
    refreshMediaCompositionDestination();
    state.ledFrame = 0;
    state.ledPixel = 0;
    renderLightingShell();
    focusSelectedTarget(target);
  });

  $$("[data-lighting-stage]").forEach(step => {
    if (step.dataset.lightingStage === state.lighting.create.stage) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });

  if (route === ROUTES.EDIT) {
    if (!available.available) {
      $("#lighting-edit-content").innerHTML = documentRequirementMarkup("Edit works directly on the custom lighting slots in an open document.");
    } else renderLightingEdit();
  }
  if (route === ROUTES.LIBRARY) renderLibrary();
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
  const technical=state.showTechnicalLabels;
  $("#screen").innerHTML = `
    <div class="screen-shell">
      <header class="screen-header">
        <div><p class="eyebrow">${esc(layout.name)}</p><h1>Keymap</h1><p class="description">Select a physical key, then choose what it should send.</p></div>
        <div class="keymap-header-actions"><button id="toggle-technical-labels" type="button" class="button ghost" aria-pressed="${technical}">${technical?'Hide technical labels':'Show technical labels'}</button><button id="save-mapping-library" type="button" class="button ghost">Save mapping to Library</button><div class="segmented layer-tabs">${layers().map((_,i) => `<button class="${i===state.layer?'active':''}" data-layer="${i}" aria-label="Layer ${i+1}">${i+1}</button>`).join("")}</div></div>
      </header>
      <div class="editor-grid">
        <section class="card"><div class="card-header"><strong>Layer ${state.layer+1}</strong><small>${layout.keys.length} physical keys</small></div><div class="card-body">
          <div class="keyboard-stage ${layout.className}">
            ${layout.unavailable?'<div class="inspector-empty"><div><strong>Physical layout unavailable</strong><p>Read this Neon keyboard again to load its validated Vial layout.</p></div></div>':layout.keys.map(([index,x,y,w=4.8,rotation=0,height=null]) => {
              const code = layer[index] || "#00000000";
              return `<button class="keycap ${keyClass(code)} ${state.selected===index?'selected':''}" data-index="${index}" style="left:${x}%;top:${y}%;width:${w}%;${height===null?'':`height:${height}%;`}transform:rotate(${rotation}deg)" title="${technical?`Matrix ${index} · ${esc(code)}`:esc(decodeCode(code))}">${esc(decodeCode(code))}${technical?`<span>${index}</span>`:''}</button>`;
            }).join("")}
          </div>
          ${renderAssignmentPalette(current)}
        </div></section>
        <aside class="card inspector">${renderKeyInspector(layer)}</aside>
      </div>
    </div>`;
  $$("[data-layer]").forEach(button => button.addEventListener("click", () => { state.layer = Number(button.dataset.layer); renderKeymap(); restoreFocus(`[data-layer="${button.dataset.layer}"]`); }));
  $$(".keycap").forEach(button => button.addEventListener("click", () => { state.selected = Number(button.dataset.index); renderKeymap(); restoreFocus(`.keycap[data-index="${button.dataset.index}"]`); }));
  $("#toggle-technical-labels").addEventListener("click", () => { state.showTechnicalLabels = !state.showTechnicalLabels; renderKeymap(); restoreFocus("#toggle-technical-labels"); });
  $("#save-mapping-library")?.addEventListener("click",saveMappingToLibrary);
  wireKeyInspector();
}

function renderKeyInspector(layer) {
  if (state.selected === null) return `<div class="inspector-empty"><div><p class="eyebrow">Nothing selected</p><p>Click a key to see and change what it sends.</p></div></div>`;
  const current = layer[state.selected] || "#00000000";
  const technical = state.showTechnicalLabels;
  return `<div class="card-header"><strong>Selected key</strong><small>Layer ${state.layer+1}${technical?` · Matrix ${state.selected}`:""}</small></div><div class="card-body">
    <div class="selected-code"><div><small class="control-caption">Currently sends</small><br><strong>${esc(decodeCode(current))}</strong>${technical?`<br><code>${esc(current)}</code>`:""}</div><span class="pill">${keyClass(current)||'key'}</span></div>
    <p class="inspector-help">Pick a new assignment from the groups below the keyboard. It is applied to this key immediately.</p>
    <details id="advanced-keycode" class="advanced-disclosure" ${state.advancedKeycodeOpen?"open":""}><summary>Advanced keycode</summary>
      <p class="inspector-help">${productFamily(productId())==="NEON"?"Choose a QMK-representable keyboard or macro assignment. Unsupported media, vendor, and raw codes are refused before they change this profile.":"Raw codes pass through to the keyboard firmware unchanged, so unusual assignments survive saving and reloading exactly."}</p>
      <div class="raw-row"><input id="raw-code" class="text-field" value="${esc(current)}" maxlength="9" aria-label="Raw keycode"><button id="apply-raw" class="button ghost">Apply</button></div>
    </details>
  </div>`;
}

async function assignSelected(code) {
  if (state.selected === null || !layers()[state.layer]) return;
  if (!/^#[0-9a-f]{8}$/i.test(code)) return toast("Invalid keycode", "Use # followed by exactly eight hexadecimal digits.", "error");
  const selected=state.selected,layerIndex=state.layer,product=productId();
  const assignmentEpoch=++state.keyAssignmentEpoch;
  let normalized=code.toUpperCase();
  if(productFamily(product)==="NEON"){
    try{
      const validation=await api("/api/keymap/assignment",{method:"POST",body:JSON.stringify({product_id:product,code:normalized})});
      normalized=validation.code;
    }catch(error){
      toast("Assignment unavailable",error.message,"error");
      return;
    }
  }
  if(state.keyAssignmentEpoch!==assignmentEpoch||state.selected!==selected||state.layer!==layerIndex||productId()!==product)return;
  mutate(() => { layers()[layerIndex].layer[selected] = normalized; });
}

function wireKeyInspector() {
  $$(".palette-key").forEach(button => button.addEventListener("click", () => {
    assignSelected(button.dataset.code);
    restoreFocus(`.palette-key[data-code="${button.dataset.code}"]`);
  }));
  $("#key-search")?.addEventListener("input", event => {
    const query = event.target.value.trim().toLowerCase();
    $$(".palette-key").forEach(button => button.hidden = query && !button.dataset.search.includes(query));
    $$(".assignment-section").forEach(section=>{section.hidden=Boolean(query)&&!section.querySelector(".palette-key:not([hidden])");});
  });
  $("#advanced-keycode")?.addEventListener("toggle", event => { state.advancedKeycodeOpen = event.currentTarget.open; });
  $("#apply-raw")?.addEventListener("click", () => assignSelected($("#raw-code").value.trim()));
  $("#raw-code")?.addEventListener("keydown", event => { if (event.key === "Enter") assignSelected(event.currentTarget.value.trim()); });
}

function macroCapacity(candidate=macros()) {
  return macroCapacityStatus(activeFamilySpec(),candidate);
}

function macroCapacityError(candidate) {
  const capacity=macroCapacity(candidate);
  if(candidate.length>capacity.tracks)return `This keyboard stores ${capacity.tracks} macros; the profile has ${candidate.length}.`;
  if(capacity.used>capacity.limit)return `These macros use ${capacity.used}/${capacity.limit} ${capacity.unit}. Shorten or remove some macros.`;
  return "";
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
  const {macroTracks} = activeFamilySpec();
  if (macros().length >= macroTracks) return toast("Macro limit reached", `This profile supports up to ${macroTracks} macros.`, "error");
  const used = new Set(macros().map(macro => macro.original_key.toUpperCase()));
  let tokenCode = null;
  for (let i=0;i<macroTracks;i++) {
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
  const capacityError=macroCapacityError(incoming);
  if(capacityError)throw new Error(capacityError);
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
    const candidate=clone(macros());
    const next=candidate[state.macro];
    next.layer_key=mode==="append"?[...(next.layer_key||[]),...generated.layer_key]:generated.layer_key;
    next.intvel_ms=mode==="append"?[...(next.intvel_ms||[]).slice(0,oldCount),...generated.intvel_ms]:generated.intvel_ms;
    const capacityError=macroCapacityError(candidate);
    if(capacityError)throw new Error(capacityError);
    mutate(()=>{
      current.layer_key=mode==="append"?[...(current.layer_key||[]),...generated.layer_key]:generated.layer_key;
      current.intvel_ms=next.intvel_ms;
    });
    toast("Text converted",`${generated.characters} characters · ${generated.layer_key.length} deterministic events · ${delay}ms between keys`,"success");
  }catch(error){toast("Could not convert text",error.message,"error");}
}

function renderMacros() {
  state.macro = Math.min(state.macro, Math.max(0,macros().length-1));
  const current = macros()[state.macro];
  const capacity=macroCapacity();
  const macroTracks=capacity.tracks;
  const eventOptions = KEY_OPTIONS.filter(option => ["Letters","Numbers","Basic","Function"].includes(option.category) && option.code !== "#00000000");
  const assigned = current ? layers().reduce((sum, layer) => sum + layer.layer.filter(code => code.toUpperCase()===current.original_key.toUpperCase()).length,0) : 0;
  const missing=missingMacroTokens();
  const missingWarning=missing.length?`<div class="write-warning macro-warning"><strong>Macro assignments have no readable actions</strong><p>${missing.map(code=>esc(decodeCode(code))).join(", ")} ${missing.length===1?'is':'are'} assigned in the keymap, but the keyboard returned no matching macro definition. Loading cannot reconstruct those keystrokes; restore them from a saved JSON or recreate them before writing.</p></div>`:"";
  $("#screen").innerHTML = `<div class="screen-shell">
    <header class="screen-header"><div><p class="eyebrow">Reusable key sequences</p><h1>Macros</h1><p class="description">Type text or record keys, then assign the macro to any key on the Keymap screen.</p></div><div class="header-controls"><button id="import-macros" class="button ghost">Import macros</button><button id="add-macro" class="button primary">+ New macro</button></div></header>
    ${missingWarning}
    <div class="macro-layout">
      <aside class="card macro-list"><div class="card-header"><strong>Macros in this profile</strong><small>${macros().length} ${macros().length===1?'macro':'macros'}</small></div><div class="macro-list-items">
        ${macros().length ? macros().map((macro,i) => `<button class="macro-item ${i===state.macro?'active':''}" data-macro="${i}"><span><strong>${esc(decodeCode(macro.original_key))}</strong><small>${(macro.layer_key||[]).length} events</small></span><span class="macro-token">${esc(macro.original_key.slice(-2))}</span></button>`).join("") : `<div class="event-empty">No macros yet.<br>Create one to begin.</div>`}
      </div></aside>
      <section class="card macro-editor">${current ? `<div class="card-header"><strong>${esc(decodeCode(current.original_key))}</strong><small>Assigned to ${assigned} key${assigned===1?'':'s'}</small></div>
        <div class="card-body"><div class="macro-toolbar">
          <button id="record-macro" class="button ghost ${state.recording?'recording':''}">${state.recording?'■ Stop recording':'● Record keys'}</button>
          <div class="spacer"></div>
          <button id="assign-macro" class="button ghost" ${state.selected===null?'disabled':''}>Assign to selected key</button>
          <button id="delete-macro" class="button danger">Delete</button>
        </div><div class="text-macro-composer">
          <div><strong>Type text</strong><small>Typed text is converted into the exact keystrokes the keyboard will replay.</small></div>
          <textarea id="macro-text" class="text-field" rows="3" placeholder="Type the exact text this macro should enter…"></textarea>
          <div class="text-macro-actions"><label>Delay between keys <input id="macro-text-delay" class="text-field" type="number" min="1" max="1000" value="10"> ms</label><div class="spacer"></div><button id="text-append" class="button ghost">Append</button><button id="text-replace" class="button primary">Replace keystrokes</button></div>
          <small>The delay is how long the keyboard waits between keystrokes — raise it if an app drops characters. US layout · letters, numbers, punctuation, spaces, Tab, and Enter · Shift is added automatically.</small>
        </div><details id="macro-advanced" class="advanced-disclosure" ${state.macroAdvancedOpen?"open":""}><summary>Edit individual events</summary>
          <div class="macro-capacity"><small>${capacity.used}/${capacity.limit} ${capacity.unit} · up to ${macroTracks} tracks</small><div class="limit-meter"><span style="width:${capacity.limit?Math.min(100,capacity.used*100/capacity.limit):0}%"></span></div></div>
          <p class="inspector-help">Each row is one key-down or key-up event and the delay that follows it, exactly as the keyboard replays them.</p>
          <div class="macro-toolbar"><button id="add-event" class="button ghost">+ Event</button></div>
          <div class="event-list">
          ${(current.layer_key||[]).length ? current.layer_key.map((code,i) => {
            const down = codeParts(code)?.modifier !== 0x10;
            const base = macroBaseCode(code);
            return `<div class="event-row" data-event="${i}"><span class="event-number">${i+1}</span><button class="event-action ${down?'':'up'}" data-action="${i}">${down?'Key down':'Key up'}</button><select class="select-field event-key" data-event-key="${i}">${eventOptions.map(option=>`<option value="${option.code}" ${option.code===base?'selected':''}>${esc(option.label)}</option>`).join("")}</select><input class="text-field event-delay" type="number" min="0" max="15000" value="${Number(current.intvel_ms?.[i]??25)}" data-delay="${i}" title="Delay after event in milliseconds"><button class="remove-event" data-remove="${i}" title="Remove">×</button></div>`;
          }).join("") : `<div class="event-empty">${state.recording?'Press keys now. Recording captures both down and up events.':'Record keys or type text above, or add an event here.'}</div>`}
        </div></details></div>` : `<div class="event-empty">Create a macro to open the editor.</div>`}</section>
    </div></div>`;
  $("#add-macro").addEventListener("click", addMacro);
  $("#import-macros").addEventListener("click",()=>$("#macro-import-input").click());
  $$("[data-macro]").forEach(button => button.addEventListener("click",()=>{state.macro=Number(button.dataset.macro);renderMacros();restoreFocus(`[data-macro="${button.dataset.macro}"]`);}));
  if (!current) return;
  $("#macro-advanced").addEventListener("toggle",event=>{state.macroAdvancedOpen=event.currentTarget.open;});
  $("#delete-macro").addEventListener("click", removeMacro);
  $("#add-event").addEventListener("click", () => {
    const candidate=clone(macros());
    candidate[state.macro].layer_key.push("#11070004");
    candidate[state.macro].intvel_ms.push(25);
    const capacityError=macroCapacityError(candidate);
    if(capacityError)return toast("Macro capacity reached",capacityError,"error");
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
  $$("[data-delay]").forEach(input => input.addEventListener("change",()=>{
    const i=Number(input.dataset.delay);
    const value=Math.max(0,Math.min(15000,Number(input.value)||0));
    const candidate=clone(macros());candidate[state.macro].intvel_ms[i]=value;
    const capacityError=macroCapacityError(candidate);
    if(capacityError){toast("Macro capacity reached",capacityError,"error");renderMacros();return;}
    mutate(()=>{current.intvel_ms[i]=value;});
  }));
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
  restoreFocus("#record-macro");
}

function recordEvent(event, down) {
  if (!state.recording || state.lighting.route !== ROUTES.MACROS || event.repeat) return;
  const usage = DOM_USAGE[event.code];
  if (usage === undefined) return;
  event.preventDefault();
  const current = macros()[state.macro];
  const now = performance.now();
  if(!current)return;
  const delay=Math.max(0,Math.min(15000,Math.round(now-state.recordLast)));
  const candidate=clone(macros());
  candidate[state.macro].layer_key.push(makeCode(7,usage,down?0x11:0x10));
  candidate[state.macro].intvel_ms.push(delay);
  const capacityError=macroCapacityError(candidate);
  if(capacityError){state.recording=false;renderMacros();return toast("Macro capacity reached",capacityError,"error");}
  current.layer_key.push(makeCode(7,usage,down?0x11:0x10));
  current.intvel_ms.push(delay);
  state.recordLast = now;
  markDirty();
  renderMacros();
}

function getPage(index) {
  return pageData().find(page => Number(page.page_index) === index) || pageData()[index];
}

function createLedPages() {
  const spec = activeFamilySpec();
  const keyColors = trackColorCount(spec, "keyframes");
  const edgeColorCount = spec.authoredTracks.includes("spotlight_frames")
    ? trackColorCount(spec, "spotlight_frames")
    : null;
  mutate(() => {
    state.config.page_data = Array.from({length:8},(_,index)=>({
      valid:index<3?1:(index>=5?1:0),page_index:index,lightness:100,speed_ms:90,
      color:{default:false,back_rgb:"#000000",rgb:"#000000"},word_page:{valid:0,word_len:0,unicode:[]},
      frames:{valid:0,frame_num:0,frame_data:[]},
      keyframes:{valid:index>=5?1:0,frame_num:index>=5?1:0,frame_data:index>=5?[{frame_index:0,frame_RGB:Array(keyColors).fill("#000000")}]:[]},
      ...(edgeColorCount!==null&&index>=5?{spotlight_frames:{valid:1,frame_num:1,frame_data:[{frame_index:0,frame_RGB:Array(edgeColorCount).fill("#000000")}]}}:{}),
    }));
    state.config.page_num = 8;
  });
}

function trackInfo() {
  const page = getPage(state.ledSlot);
  const length = trackColorCount(activeFamilySpec(), state.ledTarget);
  return {page, track:page?.[state.ledTarget], length};
}

function ensureTrack() {
  const page = getPage(state.ledSlot);
  if (!page) return null;
  const length = trackColorCount(activeFamilySpec(), state.ledTarget);
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

// The track length comes from the spec; the seven authored edge zones padded
// into it remain Relic-specific geometry, which belongs with the LED maps.
function edgeColors(colors) {
  const result=Array(trackColorCount(activeFamilySpec(),"spotlight_frames")).fill("#000000");
  for(let index=0;index<7;index++)result[index]=colors[index]||"#000000";
  return result;
}

function resampleEdgeAnimation(sourceFrames, count) {
  const sources=sourceFrames?.length?sourceFrames:[edgeColors([])];
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

function availableStudioTools() {
  return ["paint","source","animate",...(aiReady()?["generate"]:[])];
}

function setStudioTool(tool,{focus=true}={}) {
  if(!availableStudioTools().includes(tool))return;
  state.studioTool=tool;
  stopPlayback(false);
  renderLightingEdit();
  if(focus)requestAnimationFrame(()=>$(`[data-studio-tool="${tool}"]`)?.focus({preventScroll:true}));
}

function mediaSourceSize() {
  const source=["cancelled"].includes(state.mediaComposition?.status)
    ?null
    :state.mediaComposition?.source;
  const width=Number(source?.width);
  const height=Number(source?.height);
  return Number.isSafeInteger(width)&&width>0&&Number.isSafeInteger(height)&&height>0
    ?{width,height}
    :null;
}

function mediaDestinationSize() {
  const destination=state.mediaComposition?.destination;
  const width=Number(destination?.width);
  const height=Number(destination?.height);
  return Number.isSafeInteger(width)&&width>0&&Number.isSafeInteger(height)&&height>0
    ?{width,height}
    :null;
}

function stillMediaCompositionActive() {
  const source=state.mediaComposition?.status==="cancelled"
    ?null
    :state.mediaComposition?.source;
  return Boolean(source&&Number(source.frame_count)===1);
}

function mediaCompositionTargets() {
  const target=state.ledTarget;
  const paired=activeLedModel()===LED_MODELS["80"]
    &&target==="keyframes"
    &&state.relicGifEdges;
  return paired?["keyframes","spotlight_frames"]:[target];
}

function currentMediaDestination() {
  const target=state.ledTarget;
  const geometry=servedGeometry(productFamily(productId()),target);
  if(!geometry)return null;
  return {
    productId:productId(),
    target,
    targets:mediaCompositionTargets(),
    width:Number(geometry.width),
    height:Number(geometry.height),
  };
}

function refreshMediaCompositionDestination() {
  const destination=currentMediaDestination();
  if(
    destination
    &&state.mediaComposition
    &&state.mediaComposition.status!=="cancelled"
  ){
    state.mediaComposition=reduceMediaDraft(state.mediaComposition,{
      type:"DESTINATION_CHANGED",
      destination,
    });
  }
}

function updateMediaCompositionTransform(transform) {
  const checked=validateSourceTransform(transform);
  state.sourceTransform=checked;
  if(state.mediaComposition&&state.mediaComposition.status!=="cancelled"){
    let draft=state.mediaComposition;
    if(draft.effects.some(effect=>effect.type==="move_zoom")){
      draft=reduceMediaDraft(draft,{type:"EFFECTS_CHANGED",effects:[]});
    }
    state.mediaComposition=reduceMediaDraft(draft,{
      type:"TRANSFORM_CHANGED",
      transform:checked,
    });
  }
  return checked;
}

function mediaCompositionSourceUrl() {
  const draft=state.mediaComposition;
  if(!draft||draft.status==="cancelled")return "";
  return state.library.assetUrls.get(`${draft.catalogId}:${draft.source.asset_id}`)||"";
}

function activeMediaPreviewTrack() {
  if(state.studioTool!=="source"||state.mediaComposition?.status!=="ready")return null;
  const track=state.mediaComposition.mappedResult?.tracks?.[state.ledTarget];
  return track&&Array.isArray(track.frames)&&track.frames.length
    ?track
    :null;
}

async function loadMediaCompositionSourceAsset() {
  const draft=state.mediaComposition;
  if(!draft||draft.status==="cancelled")return;
  await loadLibraryAsset(draft.catalogId,draft.source.asset_id);
  if(state.mediaComposition?.catalogId===draft.catalogId&&state.lighting.route===ROUTES.EDIT){
    renderLightingEdit();
  }
}

function mediaCompositionStatusText(draft) {
  return draft?.status==="rendering"
    ?"Rendering the server-authoritative LED preview…"
    :draft?.status==="ready"
      ?"Preview ready. Apply changes only this open document."
      :draft?.status==="failed"
        ?draft.error
        :draft?.status==="applied"
          ?"Applied to this slot. The banked source remains available for reframing."
          :draft
            ?"Adjust framing, then render a preview."
            :"Choose media to bank it in Library before composition opens.";
}

function updateSourceTransformView() {
  const stage=$("#media-compositor-stage");
  if(!stage)return;
  const transform=state.sourceTransform;
  stage.style.setProperty("--source-offset-x",String(transform.offset_x));
  stage.style.setProperty("--source-offset-y",String(transform.offset_y));
  stage.style.setProperty("--source-scale-x",String(transform.scale_x));
  stage.style.setProperty("--source-scale-y",String(transform.scale_y));
  const zoom=$("#source-zoom");
  if(zoom)zoom.value=String(Math.round(transform.scale_x*100));
  const zoomLabel=$("#source-zoom-label");
  if(zoomLabel)zoomLabel.textContent=transform.aspect_locked?"Zoom":"Width";
  const value=$("#source-zoom-value");
  if(value)value.textContent=`${Math.round(transform.scale_x*100)}%`;
  const heightControl=$("#source-height-control");
  if(heightControl)heightControl.hidden=transform.aspect_locked;
  const height=$("#source-height");
  if(height)height.value=String(Math.round(transform.scale_y*100));
  const heightValue=$("#source-height-value");
  if(heightValue)heightValue.textContent=`${Math.round(transform.scale_y*100)}%`;
  const stretch=$("#source-stretch");
  if(stretch)stretch.checked=!transform.aspect_locked;
  const draft=state.mediaComposition?.status==="cancelled"?null:state.mediaComposition;
  const status=$(".media-composition-status");
  if(status){
    status.textContent=mediaCompositionStatusText(draft);
    status.classList.toggle("failed",draft?.status==="failed");
  }
  const preview=$("#media-compose-preview");
  if(preview)preview.disabled=!draft||draft.status==="rendering";
  const apply=$("#media-compose-apply");
  if(apply)apply.disabled=!mediaDraftCanApply(draft);
  const cancel=$("#media-compose-cancel");
  if(cancel)cancel.disabled=!draft;
}

function applySourceTransformPreset(mode) {
  const source=mediaSourceSize();
  const destination=mediaDestinationSize();
  if(!source||!destination)return;
  try{
    updateMediaCompositionTransform(
      presetSourceTransform(mode,source,destination,state.sourceTransform),
    );
    updateSourceTransformView();
  }catch(error){
    toast("Could not change source framing",error.message,"error");
  }
}

async function importMedia(input) {
  const file=input.files?.[0];
  input.value="";
  if(!file)return;
  if(file.size>12_000_000){
    return toast(
      "Image is too large",
      "Choose a GIF, PNG, or BMP smaller than 12 MB.",
      "error",
    );
  }
  const destination=currentMediaDestination();
  if(!destination){
    return toast(
      "Destination unavailable",
      "The selected keyboard target has no render geometry.",
      "error",
    );
  }
  const button=$("#import-media");
  if(button){button.disabled=true;button.textContent="Banking…";}
  try{
    const response=await fetch(`/api/library/import/media?name=${encodeURIComponent(file.name)}`,{
      method:"POST",
      headers:{
        "X-AM-Token":token,
        "Content-Type":file.type||"application/octet-stream",
      },
      body:file,
    });
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(payload.error||`Could not import media (${response.status})`);
    const detail=payload.item;
    const source=detail?.item?.source;
    if(!detail?.catalog_id||!source)throw new Error("The banked media response is invalid.");
    state.sourceTransform=validateSourceTransform({
      ...state.sourceTransform,
      sampling:state.gifResample,
    });
    state.mediaComposition=createMediaDraft({
      catalogId:detail.catalog_id,
      source:{
        asset_id:source.asset_id,
        mime_type:source.mime_type,
        width:source.width,
        height:source.height,
        frame_count:source.frame_count,
        duration_ms:source.duration_ms,
      },
      destination,
      transform:state.sourceTransform,
    });
    state.library.loaded=false;
    state.studioTool="source";
    renderLightingEdit();
    void loadMediaCompositionSourceAsset();
    await renderMediaCompositionPreview();
    toast(
      payload.deduplicated?"Source reopened":"Source added to Library",
      `${file.name} · ${source.frame_count} frame${source.frame_count===1?"":"s"}`,
      "success",
    );
  }catch(error){
    toast("Could not import media",error.message,"error");
  }finally{
    if(button?.isConnected){
      button.disabled=false;
      button.textContent="Add GIF, PNG, or BMP";
    }
  }
}

async function renderMediaCompositionPreview() {
  const draft=state.mediaComposition;
  if(!draft||draft.status==="cancelled")return;
  const epoch=nextMediaRenderEpoch(state.mediaRenderEpoch);
  state.mediaRenderEpoch=epoch;
  state.mediaComposition=reduceMediaDraft(draft,{
    type:"RENDER_REQUESTED",
    epoch,
  });
  renderLightingEdit();
  try{
    const result=await api(`/api/library/items/${libraryCatalogPath(draft.catalogId)}/render`,{method:"POST",body:JSON.stringify({
      product_id:draft.destination.productId,
      targets:draft.destination.targets,
      transform:draft.transform,
      effects:draft.effects,
      epoch,
    })});
    if(state.mediaComposition?.catalogId!==draft.catalogId)return;
    state.mediaComposition=reduceMediaDraft(state.mediaComposition,{
      type:"RENDER_SUCCEEDED",
      epoch,
      mappedResult:result.mapped_result,
    });
  }catch(error){
    if(state.mediaComposition?.catalogId!==draft.catalogId)return;
    state.mediaComposition=reduceMediaDraft(state.mediaComposition,{
      type:"RENDER_FAILED",
      epoch,
      error:error.message,
    });
  }
  if(state.lighting.route===ROUTES.EDIT)renderLightingEdit();
}

function applyMediaCompositionDraft() {
  const draft=state.mediaComposition;
  if(!mediaDraftCanApply(draft)){
    return toast("Preview required","Render this framing before applying it.","error");
  }
  const pairsRelic=draft.destination.targets.includes("spotlight_frames")
    &&draft.destination.target==="keyframes";
  mutate(()=>{
    const page=getPage(state.ledSlot);
    applyLedResultToPage(
      page,
      draft.mappedResult,
      draft.destination.target,
      pairsRelic,
    );
    state.ledTarget=draft.destination.target;
    state.ledFrame=0;
    state.mediaComposition=reduceMediaDraft(draft,{type:"APPLIED"});
    state.appliedLightingProvenance=createLightingProvenance({
      slot:state.ledSlot,
      target:draft.destination.target,
      sourceCatalogId:draft.catalogId,
      transform:draft.transform,
      effects:draft.effects,
      page,
    });
  });
  toast(
    "Media applied",
    "The selected slot changed through one undo checkpoint. Nothing was written to the keyboard.",
    "success",
  );
}

function cancelMediaComposition() {
  if(!state.mediaComposition)return;
  state.mediaComposition=reduceMediaDraft(state.mediaComposition,{type:"CANCELLED"});
  renderLightingEdit();
  toast(
    "Composition cancelled",
    "The open document was not changed. The imported source remains in Library.",
    "success",
  );
}

async function saveLightingToLibrary() {
  if(!state.config)return;
  const button=$("#save-lighting-library");
  if(button)button.disabled=true;
  try{
    const revision=await synchronizeOpenDocument();
    if(!revision)throw new Error(state.documentSyncError||"The open document could not be synchronized.");
    const provenance=lightingProvenanceForPage(
      state.appliedLightingProvenance,
      {
        slot:state.ledSlot,
        target:state.ledTarget,
        page:getPage(state.ledSlot),
      },
    );
    const detail=await api("/api/library/save/lighting",{
      method:"POST",
      body:JSON.stringify({
        name:`${productLabel(productId())} · slot ${state.ledSlot-4} lighting`,
        document_revision:revision,
        slot:state.ledSlot,
        target:state.ledTarget,
        source_catalog_id:provenance?.source_catalog_id??null,
        transform:provenance?.transform??null,
        effects:provenance?.effects??[],
      }),
    });
    state.library.loaded=false;
    toast(
      "Lighting saved to Library",
      `${detail.name} · ${Object.keys(detail.item.composition.tracks).length} track${Object.keys(detail.item.composition.tracks).length===1?"":"s"}`,
      "success",
    );
  }catch(error){
    toast("Could not save lighting",error.message,"error");
  }finally{
    if(button?.isConnected)button.disabled=false;
  }
}

function localAnimationCoordinatesForGeometry(length,pixelMap,physicalLayout,columns) {
  const coordinates=Array.from({length},()=>({x:0.5,y:0.5}));
  if(physicalLayout?.length){
    for(const item of physicalLayout){
      const index=Number(item.index);
      if(!Number.isSafeInteger(index)||index<0||index>=length)continue;
      const width=Number(item.w)||0;
      const height=Number(item.h)||10.7;
      coordinates[index]={
        x:Math.max(0,Math.min(1,(Number(item.x)+width/2)/100)),
        y:Math.max(0,Math.min(1,(Number(item.y)+height/2)/100)),
      };
    }
    return coordinates;
  }
  const rows=Math.max(1,Math.ceil(pixelMap.length/Math.max(1,columns)));
  pixelMap.forEach((index,position)=>{
    if(!Number.isSafeInteger(index)||index<0||index>=length)return;
    coordinates[index]={
      x:((position%columns)+0.5)/columns,
      y:(Math.floor(position/columns)+0.5)/rows,
    };
  });
  return coordinates;
}

function localAnimationFrameCount() {
  if(state.ledTarget==="spotlight_frames"&&activeLedModel()===LED_MODELS["80"]){
    return Math.max(2,getPage(state.ledSlot)?.keyframes?.frame_data?.length||2);
  }
  return state.localAnimationFrameCount;
}

function currentLocalAnimationSpec() {
  const type=state.localAnimationEffect;
  let parameters;
  if(type==="pulse")parameters={minimum_brightness:state.localAnimationMinimum};
  else if(type==="hue_cycle")parameters={turns:state.localAnimationTurns};
  else if(type==="sweep")parameters={
    direction:state.localAnimationDirection,
    width:state.localAnimationSweepWidth,
    minimum_brightness:state.localAnimationMinimum,
  };
  else if(type==="shimmer")parameters={
    depth:state.localAnimationShimmerDepth,
    seed:state.localAnimationSeed,
  };
  else{
    const start=validateSourceTransform(state.sourceTransform);
    const nextScale=Math.min(32,start.scale_x*1.18);
    parameters={
      start_transform:start,
      end_transform:validateSourceTransform({
        ...start,
        offset_x:Math.min(8,start.offset_x+0.08),
        offset_y:Math.min(8,start.offset_y+0.05),
        scale_x:nextScale,
        scale_y:start.aspect_locked?nextScale:Math.min(32,start.scale_y*1.18),
      }),
    };
  }
  return validateEffectSpec({
    version:1,
    type,
    frame_count:localAnimationFrameCount(),
    duration_ms:state.localAnimationDuration,
    parameters,
  },{
    frameLimit:Math.min(256,activeFamilySpec().frameCap||256),
    stillSource:stillMediaCompositionActive(),
  });
}

function localAnimationDraftMatches() {
  const draft=state.localAnimationDraft;
  return Boolean(
    draft
    &&draft.slot===state.ledSlot
    &&draft.target===state.ledTarget
  );
}

function previewLocalAnimation() {
  const source=currentFrame();
  if(!source)return toast("Nothing to animate","Create or select a frame first.","error");
  if(state.ledTarget==="spotlight_frames"&&activeLedModel()===LED_MODELS["80"]&&(getPage(state.ledSlot)?.keyframes?.frame_data?.length||0)<2){
    return toast("Add a key frame first","Edge animation stays synchronized to the key animation, which currently has only one frame.","error");
  }
  try{
    const effect=currentLocalAnimationSpec();
    const sourceColors=clone(source.frame_RGB);
    const draft={
      slot:state.ledSlot,
      target:state.ledTarget,
      sourceFingerprint:JSON.stringify(sourceColors),
      effect,
      frames:[],
      transforms:[],
    };
    if(effect.type==="move_zoom"){
      if(!state.mediaComposition||state.mediaComposition.status==="cancelled"){
        throw new Error("Move & zoom requires one active imported still.");
      }
      draft.transforms=interpolateMoveZoom(effect);
      state.mediaComposition=reduceMediaDraft(state.mediaComposition,{
        type:"EFFECTS_CHANGED",
        effects:[effect],
      });
      state.localAnimationDraft=null;
      state.studioTool="source";
      renderLightingEdit();
      void renderMediaCompositionPreview();
      return;
    }else{
      draft.frames=renderColorEffect(
        [sourceColors],
        effect,
        state.localAnimationCoordinates,
      );
    }
    state.localAnimationDraft=draft;
    state.localAnimationPreviewFrame=0;
    renderLightingEdit();
    requestAnimationFrame(()=>$("#animate-accept")?.focus({preventScroll:true}));
  }catch(error){
    state.localAnimationDraft=null;
    toast("Could not preview animation",error.message,"error");
  }
}

function cancelLocalAnimationDraft({render=true}={}) {
  state.localAnimationDraft=null;
  state.localAnimationPreviewFrame=0;
  if(render)renderLightingEdit();
}

function applyLocalAnimationDraft() {
  const draft=state.localAnimationDraft;
  const source=currentFrame();
  if(!localAnimationDraftMatches()||!source){
    cancelLocalAnimationDraft();
    return toast("Animation draft expired","Preview the effect again for this destination.","error");
  }
  if(JSON.stringify(source.frame_RGB)!==draft.sourceFingerprint){
    cancelLocalAnimationDraft();
    return toast("Animation draft changed","The source frame changed. Preview the effect again.","error");
  }
  if(!draft.frames.length){
    return toast("Source composition required","Move & zoom is applied with an imported still in Source.","error");
  }
  const frames=clone(draft.frames);
  const duration=draft.effect.duration_ms;
  mutate(()=>{
    const page=getPage(state.ledSlot);
    const track=ensureTrack();
    track.valid=1;
    track.frame_num=frames.length;
    track.frame_data=frames.map((colors,index)=>({frame_index:index,frame_RGB:colors}));
    page.speed_ms=duration;
    if(state.ledTarget==="keyframes"&&activeLedModel()===LED_MODELS["80"]&&page.spotlight_frames?.frame_data?.length){
      const edgeFrames=resampleEdgeAnimation(page.spotlight_frames.frame_data,frames.length);
      page.spotlight_frames={...page.spotlight_frames,valid:1,frame_num:edgeFrames.length,frame_data:edgeFrames};
    }
    state.ledFrame=0;
    state.localAnimationDraft=null;
    state.localAnimationPreviewFrame=0;
    state.appliedLightingProvenance=createLightingProvenance({
      slot:draft.slot,
      target:draft.target,
      sourceCatalogId:null,
      transform:null,
      effects:[draft.effect],
      page,
    });
  });
  toast("Animation applied",`${frames.length} deterministic frames replaced the selected track.`,"success");
}

function animationParameterMarkup() {
  const type=state.localAnimationEffect;
  if(type==="pulse")return `<div class="control-group"><label class="control-label" for="animate-minimum">Minimum brightness</label><div class="range-row"><input id="animate-minimum" type="range" min="0" max="100" value="${Math.round(state.localAnimationMinimum*100)}"><span class="range-value">${Math.round(state.localAnimationMinimum*100)}%</span></div></div>`;
  if(type==="hue_cycle")return `<div class="control-group"><label class="control-label" for="animate-turns">Color rotations</label><div class="range-row"><input id="animate-turns" type="range" min="0.125" max="4" step="0.125" value="${state.localAnimationTurns}"><span class="range-value">${state.localAnimationTurns}×</span></div></div>`;
  if(type==="sweep")return `<div class="control-group"><label class="control-label" for="animate-direction">Direction</label><select id="animate-direction" class="select-field"><option value="left_to_right" ${state.localAnimationDirection==="left_to_right"?"selected":""}>Left to right</option><option value="right_to_left" ${state.localAnimationDirection==="right_to_left"?"selected":""}>Right to left</option><option value="top_to_bottom" ${state.localAnimationDirection==="top_to_bottom"?"selected":""}>Top to bottom</option><option value="bottom_to_top" ${state.localAnimationDirection==="bottom_to_top"?"selected":""}>Bottom to top</option><option value="diagonal" ${state.localAnimationDirection==="diagonal"?"selected":""}>Diagonal</option></select><label class="control-label secondary-label" for="animate-width">Band width</label><div class="range-row"><input id="animate-width" type="range" min="0.05" max="2" step="0.05" value="${state.localAnimationSweepWidth}"><span class="range-value">${state.localAnimationSweepWidth.toFixed(2)}</span></div></div>`;
  if(type==="shimmer")return `<div class="control-group"><label class="control-label" for="animate-depth">Shimmer depth</label><div class="range-row"><input id="animate-depth" type="range" min="0" max="100" value="${Math.round(state.localAnimationShimmerDepth*100)}"><span class="range-value">${Math.round(state.localAnimationShimmerDepth*100)}%</span></div><label class="control-label secondary-label" for="animate-seed">Pattern seed</label><input id="animate-seed" class="text-field" type="number" min="0" max="4294967295" step="1" value="${state.localAnimationSeed}"></div>`;
  return `<div class="control-group"><span class="control-label">Move &amp; zoom</span><p class="control-help">Uses the current Source framing as the start and creates a gentle pan-and-zoom endpoint. Available only for an imported PNG or BMP.</p></div>`;
}

function animationDraftMarkup() {
  const draft=localAnimationDraftMatches()?state.localAnimationDraft:null;
  const count=draft?.frames.length||draft?.transforms.length||0;
  if(!draft)return `<div class="animation-draft-empty">Preview builds a local draft. The document is not changed until you accept it.</div>`;
  return `<div class="animation-draft-controls" aria-live="polite"><strong>Draft ready · ${count} frames</strong><input id="animate-draft-frame" type="range" min="0" max="${Math.max(0,count-1)}" value="${Math.min(state.localAnimationPreviewFrame,Math.max(0,count-1))}" aria-label="Preview draft frame"><small>Frame ${Math.min(state.localAnimationPreviewFrame+1,Math.max(1,count))} of ${count}</small></div>`;
}

function showLocalAnimationDraftFrame(index) {
  const draft=localAnimationDraftMatches()?state.localAnimationDraft:null;
  const count=draft?.frames.length||draft?.transforms.length||0;
  if(!count)return;
  state.localAnimationPreviewFrame=Math.max(0,Math.min(count-1,Number(index)));
  const colors=draft.frames[state.localAnimationPreviewFrame];
  if(colors){
    $$(".pixel").forEach(pixel=>{
      const color=safeRgbColor(colors[Number(pixel.dataset.pixel)]);
      pixel.style.background=color;
      pixel.style.setProperty("--pixel-color",color);
    });
  }
  const label=$(".animation-draft-controls small");
  if(label)label.textContent=`Frame ${state.localAnimationPreviewFrame+1} of ${count}`;
}

function wireStudioInspector() {
  const tabs=$$("[data-studio-tool]");
  tabs.forEach((tab,index)=>{
    tab.addEventListener("click",()=>setStudioTool(tab.dataset.studioTool));
    tab.addEventListener("keydown",event=>{
      if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
      event.preventDefault();
      const next=event.key==="Home"?0:event.key==="End"?tabs.length-1:(index+(event.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;
      setStudioTool(tabs[next].dataset.studioTool);
    });
  });
  $("#animate-effect")?.addEventListener("change",event=>{state.localAnimationEffect=event.target.value;cancelLocalAnimationDraft();});
  $("#animate-frame-count")?.addEventListener("change",event=>{state.localAnimationFrameCount=Number(event.target.value);cancelLocalAnimationDraft();});
  $("#animate-duration")?.addEventListener("change",event=>{state.localAnimationDuration=Number(event.target.value);cancelLocalAnimationDraft();});
  $("#animate-minimum")?.addEventListener("change",event=>{state.localAnimationMinimum=Number(event.target.value)/100;cancelLocalAnimationDraft();});
  $("#animate-turns")?.addEventListener("change",event=>{state.localAnimationTurns=Number(event.target.value);cancelLocalAnimationDraft();});
  $("#animate-direction")?.addEventListener("change",event=>{state.localAnimationDirection=event.target.value;cancelLocalAnimationDraft();});
  $("#animate-width")?.addEventListener("change",event=>{state.localAnimationSweepWidth=Number(event.target.value);cancelLocalAnimationDraft();});
  $("#animate-depth")?.addEventListener("change",event=>{state.localAnimationShimmerDepth=Number(event.target.value)/100;cancelLocalAnimationDraft();});
  $("#animate-seed")?.addEventListener("change",event=>{state.localAnimationSeed=Number(event.target.value);cancelLocalAnimationDraft();});
  $("#animate-preview")?.addEventListener("click",previewLocalAnimation);
  $("#animate-accept")?.addEventListener("click",applyLocalAnimationDraft);
  $("#animate-cancel")?.addEventListener("click",()=>cancelLocalAnimationDraft());
  $("#animate-draft-frame")?.addEventListener("input",event=>showLocalAnimationDraftFrame(event.target.value));
  $("#media-compose-preview")?.addEventListener("click",renderMediaCompositionPreview);
  $("#media-compose-apply")?.addEventListener("click",applyMediaCompositionDraft);
  $("#media-compose-cancel")?.addEventListener("click",cancelMediaComposition);

  $$("[data-source-preview]").forEach(button=>button.addEventListener("click",()=>{
    if(button.disabled)return;
    state.sourcePreviewMode=button.dataset.sourcePreview;
    renderLightingEdit();
  }));
  $$("[data-source-preset]").forEach(button=>button.addEventListener("click",()=>applySourceTransformPreset(button.dataset.sourcePreset)));
  $("#source-stretch")?.addEventListener("change",event=>{
    const locked=!event.target.checked;
    try{
      updateMediaCompositionTransform({
        ...state.sourceTransform,
        aspect_locked:locked,
        scale_y:locked?state.sourceTransform.scale_x:state.sourceTransform.scale_y,
      });
      updateSourceTransformView();
    }catch(error){toast("Could not change stretch mode",error.message,"error");}
  });
  $("#source-zoom")?.addEventListener("input",event=>{
    const target=Number(event.target.value)/100;
    const factor=target/state.sourceTransform.scale_x;
    try{
      updateMediaCompositionTransform({
        ...state.sourceTransform,
        scale_x:target,
        scale_y:state.sourceTransform.aspect_locked
          ?target
          :Math.max(0.01,Math.min(32,state.sourceTransform.scale_y*factor)),
      });
      updateSourceTransformView();
    }catch(error){toast("Could not zoom source",error.message,"error");}
  });
  $("#source-height")?.addEventListener("input",event=>{
    const target=Number(event.target.value)/100;
    try{
      updateMediaCompositionTransform({
        ...state.sourceTransform,
        aspect_locked:false,
        scale_y:target,
      });
      updateSourceTransformView();
    }catch(error){toast("Could not stretch source",error.message,"error");}
  });
  const stage=$("#media-compositor-stage");
  if(stage&&mediaSourceSize()&&mediaDestinationSize()){
    let pointer=null;
    stage.addEventListener("pointerdown",event=>{
      if(state.studioTool!=="source")return;
      pointer=normalizedPointer(event,stage.getBoundingClientRect());
      stage.setPointerCapture?.(event.pointerId);
    });
    stage.addEventListener("pointermove",event=>{
      if(!pointer||state.studioTool!=="source")return;
      const next=normalizedPointer(event,stage.getBoundingClientRect());
      updateMediaCompositionTransform(
        panSourceTransform(state.sourceTransform,next.x-pointer.x,next.y-pointer.y),
      );
      pointer=next;
      updateSourceTransformView();
    });
    const release=()=>{pointer=null;};
    stage.addEventListener("pointerup",release);
    stage.addEventListener("pointercancel",release);
    stage.addEventListener("wheel",event=>{
      if(state.studioTool!=="source")return;
      event.preventDefault();
      updateMediaCompositionTransform(
        scaleSourceTransform(state.sourceTransform,event.deltaY<0?1.08:1/1.08,"both"),
      );
      updateSourceTransformView();
    },{passive:false});
    stage.addEventListener("keydown",event=>{
      if(state.studioTool!=="source")return;
      const step=event.shiftKey?0.1:0.025;
      const pan={
        ArrowLeft:[-step,0],
        ArrowRight:[step,0],
        ArrowUp:[0,-step],
        ArrowDown:[0,step],
      }[event.key];
      if(pan){
        event.preventDefault();
        updateMediaCompositionTransform(
          panSourceTransform(state.sourceTransform,pan[0],pan[1]),
        );
        updateSourceTransformView();
      }else if(["+","=","-","_"].includes(event.key)){
        event.preventDefault();
        updateMediaCompositionTransform(
          scaleSourceTransform(state.sourceTransform,["-","_"].includes(event.key)?1/1.08:1.08,"both"),
        );
        updateSourceTransformView();
      }
    });
  }
  updateSourceTransformView();
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
  if (!model) {
    $("#lighting-edit-content").innerHTML=unsupportedDeviceNotice("painting these pages");
    return;
  }
  const targets=model.targets;
  if (!targets.some(target=>target.key===state.ledTarget)) state.ledTarget=targets[0].key;
  if(!availableStudioTools().includes(state.studioTool))state.studioTool="paint";
  const {track,length}=trackInfo();
  const documentFrames=track?.frame_data||[];
  const mediaPreviewTrack=activeMediaPreviewTrack();
  const mediaPreviewFrames=(mediaPreviewTrack?.frames||[]).map(
    (colors,index)=>({frame_index:index,frame_RGB:colors}),
  );
  const timelineFrames=mediaPreviewFrames.length?mediaPreviewFrames:documentFrames;
  state.ledFrame=Math.min(state.ledFrame,Math.max(0,timelineFrames.length-1));
  const frame=documentFrames[Math.min(
    state.ledFrame,
    Math.max(0,documentFrames.length-1),
  )];
  const gridClass=state.ledTarget==="frames"?"display":state.ledTarget==="spotlight_frames"?"edge":"key";
  // Geometry the server publishes from device_mapping, which is the authority
  // for these tables. A family whose maps are not hardcoded below — the Neon,
  // and anything added later — is laid out entirely from this.
  const servedTarget=servedGeometry(productFamily(productId()),state.ledTarget);
  // A family with no embedded maps depends entirely on served geometry. Until
  // that arrives, refuse to render an editor rather than invent one: an
  // identity map is a plausible-looking but wrong layout, and a user painting
  // against it would be authoring positions that do not exist on the device.
  if(!model.keyMap&&!model.displayMap&&!model.physicalLayout&&!servedTarget){
    $("#lighting-edit-content").innerHTML=geometryUnavailableNotice();
    return;
  }
  const columns=state.ledTarget==="frames"?40:state.ledTarget==="spotlight_frames"?7:(model.keyColumns||servedTarget?.width);
  const device=displayGeometryDevice();
  const physicalLayout=state.ledTarget==="keyframes"
    ?model.physicalLayout
    :state.ledTarget==="axial"
      ?projectVialLedLayout(device,servedTarget)
      :null;
  const neonAxial=productFamily(productId())==="NEON"&&state.ledTarget==="axial";
  if(neonAxial&&!physicalLayout){
    $("#lighting-edit-content").innerHTML=geometryUnavailableNotice();
    return;
  }
  const pixelMap=physicalLayout?physicalLayout.map(item=>item.index):state.ledTarget==="keyframes"?(model.keyMap||servedTarget?.map):state.ledTarget==="spotlight_frames"?[0,1,2,3,4,5,6]:(model.displayMap||servedTarget?.map||Array.from({length},(_,index)=>index));
  const mappedCount=new Set(pixelMap.filter(index=>index>=0)).size;
  const focusablePixelCount=physicalLayout?.length||pixelMap.filter(index=>index>=0).length;
  state.ledPixel=Math.min(state.ledPixel,Math.max(0,focusablePixelCount-1));
  state.localAnimationCoordinates=localAnimationCoordinatesForGeometry(
    length,
    pixelMap,
    physicalLayout,
    columns,
  );
  const activeDraft=state.studioTool==="animate"&&localAnimationDraftMatches()
    ?state.localAnimationDraft
    :null;
  const draftColors=activeDraft?.frames[
    Math.min(
      state.localAnimationPreviewFrame,
      Math.max(0,activeDraft.frames.length-1),
    )
  ];
  const mediaPreviewColors=mediaPreviewTrack?.frames?.[
    Math.min(state.ledFrame,Math.max(0,mediaPreviewTrack.frame_count-1))
  ];
  const displayFrame=draftColors
    ?{frame_index:state.localAnimationPreviewFrame,frame_RGB:draftColors}
    :mediaPreviewColors
      ?{frame_index:state.ledFrame,frame_RGB:mediaPreviewColors}
      :frame;
  const keyLabels=layers()[0]?.layer||[];
  let pixelOrder=0;
  const rasterCells=pixelMap.map(index=>{
    if(index<0)return `<span class="pixel-spacer"></span>`;
    const position=pixelOrder++;
    const color=safeRgbColor(displayFrame?.frame_RGB[index]);
    return `<button class="pixel" role="gridcell" tabindex="${position===state.ledPixel?0:-1}" data-pixel="${index}" style="background:${safeRgbColor(color)};--pixel-color:${safeRgbColor(color)}" aria-label="LED ${index}, ${esc(color)}" title="LED ${index} · ${esc(color)}"></button>`;
  }).join("");
  const pixelCanvas=!displayFrame?`<div class="event-empty"><button id="first-frame" class="button primary">Create first frame</button></div>`:physicalLayout?`<div class="pixel-grid physical afa-led-board" role="grid" aria-label="LED paint grid">${physicalLayout.map((item,position)=>{
    const color=safeRgbColor(displayFrame.frame_RGB[item.index]);
    const body=item.keyIndex===null;
    const keyLabel=body?item.label:decodeCode(keyLabels[item.keyIndex]||"#00000000");
    const label=item.showLabel===false?"":keyLabel;
    const description=body?'Center light':`Key ${keyLabel}, matrix ${item.keyIndex}`;
    const grouped=item.groupCount>1;
    const groupClass=grouped?`multi-led ${item.groupPosition===0?'group-first':''} ${item.groupPosition===item.groupCount-1?'group-last':''}`:"";
    const segmentDescription=grouped?`, segment ${item.groupPosition+1} of ${item.groupCount}`:"";
    return `<button class="pixel physical-pixel ${body?'body-led':''} ${groupClass}" role="gridcell" tabindex="${position===state.ledPixel?0:-1}" data-pixel="${item.index}" data-pixel-description="${esc(description+segmentDescription)}" style="left:${item.x}%;top:${item.y}%;width:${item.w}%;height:${item.h??10.7}%;--rotation:${item.rotation}deg;background:${safeRgbColor(color)};--pixel-color:${safeRgbColor(color)}" aria-label="${esc(description+segmentDescription)}, LED ${item.index}, ${esc(color)}" title="${esc(description+segmentDescription)} · LED ${item.index} · ${esc(color)}"><span>${esc(label)}</span><small>LED ${item.index}</small></button>`;
  }).join("")}</div>`:`<div class="pixel-grid ${gridClass}" role="grid" aria-label="LED paint grid" style="grid-template-columns:repeat(${columns},1fr)">${rasterCells}</div>`;
  const raster=model.keyRaster||(servedTarget?`${servedTarget.width}×${servedTarget.height}`:"");
  const gifSize=state.ledTarget==="frames"?"40×5":state.ledTarget==="spotlight_frames"?"18×7 → 7 edge LEDs":`${raster} → ${mappedCount} mapped LEDs`;
  const relicKeyTarget=model===LED_MODELS["80"]&&state.ledTarget==="keyframes";
  const pairsRelicGif=relicKeyTarget&&state.relicGifEdges;
  const edgeAutomation=model===LED_MODELS["80"]&&state.ledTarget==="spotlight_frames";
  const keyFrameCount=Math.max(1,page?.keyframes?.frame_data?.length||1);
  const encodedSpeed=firmwareLedSpeed(page?.speed_ms??90);
  const gifButtonLabel="Add GIF, PNG, or BMP";
  const gifHelp=pairsRelicGif
    ? "Banks the source, previews one framing across both Relic tracks, then applies only after confirmation."
    : relicKeyTarget?"Banks the source and previews the key track while preserving and retiming the separate edge animation.":edgeAutomation?`Banks the source and previews it on the 7 edge LEDs at the key track’s ${keyFrameCount}-frame timing.`:`Banks the source, then previews every frame at ${gifSize} before Apply.`;
  const relicGifOption=relicKeyTarget?`<label class="check-row"><input id="relic-gif-edges" type="checkbox" ${state.relicGifEdges?'checked':''}><span>Also derive edge lights from this GIF</span></label>`:"";
  const edgeTools=edgeAutomation?`<div class="control-group"><label class="control-label">Whole edge animation</label><div class="button-row"><button id="edge-static" class="button ghost">Static color</button><button id="edge-pulse" class="button ghost">Pulse color</button></div><button id="edge-hold" class="button ghost wide-button">Hold painted frame</button><small class="control-help">Generates ${keyFrameCount} edge frames automatically to match the key animation. “Hold” preserves the seven colors painted in the current frame.</small></div>`:"";
  const targetLabel=targets.find(t=>t.key===state.ledTarget)?.label||state.ledTarget;
  const sourceReady=Boolean(mediaSourceSize()&&mediaDestinationSize());
  const sourceDisabled=sourceReady?"":"disabled";
  const mediaDraft=state.mediaComposition?.status==="cancelled"?null:state.mediaComposition;
  const mediaSourceUrl=mediaCompositionSourceUrl();
  const mediaStatus=mediaCompositionStatusText(mediaDraft);
  const familyFrameCap=Math.min(256,activeFamilySpec().frameCap||256);
  const fixedEdgeFrameCount=edgeAutomation&&keyFrameCount>=2;
  const edgeAnimationUnavailable=edgeAutomation&&keyFrameCount<2;
  const animationFrameCount=fixedEdgeFrameCount?keyFrameCount:state.localAnimationFrameCount;
  const moveZoomReady=stillMediaCompositionActive();
  const animationDraft=localAnimationDraftMatches()?state.localAnimationDraft:null;
  const paintBody=`<div id="studio-paint-panel" class="studio-tool-panel" role="tabpanel" aria-labelledby="studio-paint-tab" ${state.studioTool==="paint"?"":"hidden"}>
        ${edgeTools}
        <div class="control-group"><label class="control-label" for="led-color">Paint color</label><input id="led-color" class="color-picker" type="color" value="${state.ledColor}"><input id="led-color-text" class="text-field" aria-label="Paint color hex value" value="${state.ledColor}"></div>
        <div class="control-group"><label class="control-label">Brush</label><div class="button-row"><button id="fill-led" class="button ghost">Fill all</button><button id="clear-led" class="button ghost">Clear</button></div></div>
        <div class="control-group"><label class="control-label" for="brightness">Brightness</label><div class="range-row"><input id="brightness" type="range" min="0" max="100" value="${Number(page?.lightness??100)}" aria-describedby="brightness-value"><span id="brightness-value" class="range-value">${Number(page?.lightness??100)}%</span></div></div>
        <div class="control-group"><label class="control-label" for="speed">Frame duration</label><select id="speed" class="select-field">${LED_SPEEDS.map(speed=>`<option value="${speed}" ${speed===encodedSpeed?'selected':''}>${speed} ms · ${(1000/speed).toFixed(1)} fps</option>`).join("")}</select><small class="control-help">These are the timing steps exposed by Angry Miao firmware.</small></div>
      </div>`;
  const sourceBody=`<div id="studio-source-panel" class="studio-tool-panel" role="tabpanel" aria-labelledby="studio-source-tab" ${state.studioTool==="source"?"":"hidden"}>
        <div class="control-group" role="group" aria-labelledby="animation-source-label"><h3 id="animation-source-label" class="control-label">Imported media</h3><input id="media-input" type="file" hidden><div class="gif-import-row"><button id="import-media" class="button ghost">${gifButtonLabel}</button><select id="gif-resample" class="select-field" aria-label="Media sampling method"><option value="nearest" ${state.gifResample==='nearest'?'selected':''}>Crisp</option><option value="box" ${state.gifResample==='box'?'selected':''}>Balanced</option><option value="lanczos" ${state.gifResample==='lanczos'?'selected':''}>Smooth</option></select></div>${relicGifOption}<small class="control-help">${gifHelp}</small></div>
        <div class="control-group source-transform-controls" aria-disabled="${String(!sourceReady)}"><span class="control-label">Framing</span><div class="source-preset-grid"><button class="button ghost" data-source-preset="fit" ${sourceDisabled}>Fit</button><button class="button ghost" data-source-preset="fill" ${sourceDisabled}>Fill</button><button class="button ghost" data-source-preset="center" ${sourceDisabled}>Center</button><button class="button ghost" data-source-preset="reset" ${sourceDisabled}>Reset</button></div><label id="source-zoom-label" class="control-label secondary-label" for="source-zoom">${state.sourceTransform.aspect_locked?"Zoom":"Width"}</label><div class="range-row"><input id="source-zoom" type="range" min="1" max="3200" value="${Math.round(state.sourceTransform.scale_x*100)}" ${sourceDisabled}><span id="source-zoom-value" class="range-value">${Math.round(state.sourceTransform.scale_x*100)}%</span></div><div id="source-height-control" ${state.sourceTransform.aspect_locked?"hidden":""}><label class="control-label secondary-label" for="source-height">Height</label><div class="range-row"><input id="source-height" type="range" min="1" max="3200" value="${Math.round(state.sourceTransform.scale_y*100)}" ${sourceDisabled}><span id="source-height-value" class="range-value">${Math.round(state.sourceTransform.scale_y*100)}%</span></div></div><label class="check-row"><input id="source-stretch" type="checkbox" ${state.sourceTransform.aspect_locked?"":"checked"} ${sourceDisabled}><span>Stretch width and height independently</span></label><small class="control-help">${sourceReady?"Drag on the canvas to pan; use the wheel or sliders to resize.":"Import media to bank the source and open framing controls."}</small></div>
        <div class="control-group"><span class="control-label">Canvas preview</span><div class="segmented source-preview-toggle" role="group" aria-label="Canvas preview"><button type="button" data-source-preview="result" aria-pressed="${String(state.sourcePreviewMode==="result")}" class="${state.sourcePreviewMode==="result"?"active":""}">LED result</button><button type="button" data-source-preview="source" aria-pressed="${String(state.sourcePreviewMode==="source")}" class="${state.sourcePreviewMode==="source"?"active":""}" ${sourceDisabled}>Source overlay</button></div></div>
        <div class="media-composition-status ${mediaDraft?.status==="failed"?"failed":""}" aria-live="polite">${esc(mediaStatus)}</div>
        <div class="media-composition-actions"><button id="media-compose-preview" class="button ghost" ${sourceReady&&mediaDraft?.status!=="rendering"?"":"disabled"}>Render preview</button><button id="media-compose-apply" class="button primary" ${mediaDraftCanApply(mediaDraft)?"":"disabled"}>Apply</button><button id="media-compose-cancel" class="button ghost" ${mediaDraft?"":"disabled"}>Cancel</button></div>
      </div>`;
  const animateBody=`<div id="studio-animate-panel" class="studio-tool-panel" role="tabpanel" aria-labelledby="studio-animate-tab" ${state.studioTool==="animate"?"":"hidden"}>
        <div class="control-group"><label class="control-label" for="animate-effect">Animate this</label><select id="animate-effect" class="select-field"><option value="pulse" ${state.localAnimationEffect==="pulse"?"selected":""}>Pulse</option><option value="hue_cycle" ${state.localAnimationEffect==="hue_cycle"?"selected":""}>Hue cycle</option><option value="sweep" ${state.localAnimationEffect==="sweep"?"selected":""}>Sweep</option><option value="shimmer" ${state.localAnimationEffect==="shimmer"?"selected":""}>Shimmer</option><option value="move_zoom" ${state.localAnimationEffect==="move_zoom"?"selected":""} ${moveZoomReady?"":"disabled"}>Move &amp; zoom${moveZoomReady?"":" · still only"}</option></select><small class="control-help">Builds a deterministic local draft from the selected frame. No AI or network request is used.</small></div>
        <div class="control-group"><label class="control-label" for="animate-frame-count">Frames</label><input id="animate-frame-count" class="text-field" type="number" min="2" max="${familyFrameCap}" step="1" value="${animationFrameCount}" ${fixedEdgeFrameCount?"disabled":""}><small class="control-help">${fixedEdgeFrameCount?`Locked to the key animation’s ${keyFrameCount} frames.`:`Destination limit: ${familyFrameCap} frames.`}</small><label class="control-label secondary-label" for="animate-duration">Frame duration</label><select id="animate-duration" class="select-field">${LED_SPEEDS.map(speed=>`<option value="${speed}" ${speed===firmwareLedSpeed(state.localAnimationDuration)?'selected':''}>${speed} ms · ${(1000/speed).toFixed(1)} fps</option>`).join("")}</select></div>
        ${animationParameterMarkup()}
        ${animationDraftMarkup()}
        <div class="animation-draft-actions"><button id="animate-preview" class="button ghost" ${frame&&!edgeAnimationUnavailable?"":"disabled"}>Preview draft</button><button id="animate-accept" class="button primary" ${animationDraft?.frames.length?"":"disabled"}>Accept</button><button id="animate-cancel" class="button ghost" ${animationDraft?"":"disabled"}>Cancel</button></div>
      </div>`;
  const generationTab=aiReady()?`<button id="studio-generate-tab" role="tab" aria-controls="studio-generate-panel" aria-selected="${String(state.studioTool==="generate")}" tabindex="${state.studioTool==="generate"?0:-1}" data-studio-tool="generate">Generate</button>`:"";
  const generationPanel=aiReady()?`<section id="studio-generate-panel" class="studio-tool-panel lighting-generate-tool" role="tabpanel" aria-labelledby="studio-generate-tab" ${state.studioTool==="generate"?"":"hidden"}><div id="lighting-generate-tool" tabindex="-1"><div class="studio-panel-heading"><strong id="lighting-generate-title">Generate lighting</strong><small>Procedural recipe · exact ${esc(targetLabel)} destination</small></div><div id="lighting-generate-content" aria-live="polite"></div></div></section>`:"";
  $("#lighting-edit-content").innerHTML=`<div class="lighting-edit-shell"><div class="led-layout">
      <aside class="card frame-list" aria-label="${mediaPreviewFrames.length?'Media preview':'Animation'} frames"><div class="card-header"><strong>${mediaPreviewFrames.length?'Preview frames':'Frames'}</strong><small>${timelineFrames.length}</small></div><div class="frame-items">${timelineFrames.map((item,i)=>`<button class="frame-item ${i===state.ledFrame?'active':''}" data-frame="${i}" aria-pressed="${i===state.ledFrame}" aria-label="Frame ${i+1}${i===state.ledFrame?', selected':''}"><span class="frame-thumb">${(item.frame_RGB||[]).slice(0,12).map(color=>`<i style="background:${safeRgbColor(color)}"></i>`).join("")}</span><span><strong>Frame ${String(i+1).padStart(2,"0")}</strong><small>${i===state.ledFrame?(mediaPreviewFrames.length?'Previewing':'Editing'):'Select'}</small></span></button>`).join("")||`<div class="event-empty">No frames</div>`}</div><div class="card-body button-row"><button id="add-frame" class="button ghost" ${mediaPreviewFrames.length?'disabled':''}>+ Duplicate</button><button id="remove-frame" class="button ghost" ${timelineFrames.length<=1||mediaPreviewFrames.length?'disabled':''}>Delete</button></div></aside>
      <section class="card led-canvas-card" aria-label="LED canvas"><div class="card-header led-canvas-heading"><div><strong>${esc(model.name)} · ${esc(targetLabel)}</strong><small>${mappedCount}${mappedCount===length?'':' mapped'} / ${length} stored${physicalLayout?' · Layer 1 labels':''}${activeDraft||mediaPreviewColors?' · Draft preview':''}</small></div><div class="led-canvas-actions"><button id="save-lighting-library" class="button ghost">Save lighting</button><button id="play-led" class="icon-button" aria-label="${state.playing?'Stop animation':'Play animation'}">${state.playing?'■':'▶'}</button></div></div><div id="led-canvas" class="led-canvas ${physicalLayout?'physical-canvas':''} ${activeDraft||mediaPreviewColors?'draft-preview':''}" role="region" aria-label="${activeDraft||mediaPreviewColors?'Preview the lighting draft':'Paint the selected animation frame'}"><div id="media-compositor-stage" class="media-compositor-stage" tabindex="${sourceReady&&state.studioTool==="source"?'0':'-1'}" style="--source-offset-x:${state.sourceTransform.offset_x};--source-offset-y:${state.sourceTransform.offset_y};--source-scale-x:${state.sourceTransform.scale_x};--source-scale-y:${state.sourceTransform.scale_y}">${state.studioTool==="source"&&mediaSourceUrl&&state.sourcePreviewMode==="source"?`<img class="media-source-overlay" src="${esc(mediaSourceUrl)}" alt="">`:""}${pixelCanvas}<div class="destination-overlay" aria-hidden="true"></div></div></div></section>
      <aside class="card led-controls studio-inspector" aria-label="Lighting controls"><div class="studio-tool-tabs ${aiReady()?'with-generate':''}" role="tablist" aria-label="Studio tools"><button id="studio-paint-tab" role="tab" aria-controls="studio-paint-panel" aria-selected="${String(state.studioTool==="paint")}" tabindex="${state.studioTool==="paint"?0:-1}" data-studio-tool="paint">Paint</button><button id="studio-source-tab" role="tab" aria-controls="studio-source-panel" aria-selected="${String(state.studioTool==="source")}" tabindex="${state.studioTool==="source"?0:-1}" data-studio-tool="source">Source</button><button id="studio-animate-tab" role="tab" aria-controls="studio-animate-panel" aria-selected="${String(state.studioTool==="animate")}" tabindex="${state.studioTool==="animate"?0:-1}" data-studio-tool="animate">Animate</button>${generationTab}</div><div class="studio-inspector-body">${paintBody}${sourceBody}${animateBody}${generationPanel}</div></aside>
    </div></div>`;
  wireLedEditor(columns);
  wireStudioInspector();
  renderGenerationStudio();
}

function focusSelectedFrame() {
  $$('[data-frame]').find(button=>Number(button.dataset.frame)===state.ledFrame)?.focus();
}

function selectLightingFrame(index) {
  cancelLocalAnimationDraft({render:false});
  state.ledFrame=Number(index);
  renderLightingEdit();
  focusSelectedFrame();
}

function wireLedEditor(gridColumns) {
  activePaintStrokeController?.teardown();
  activePaintStrokeController=null;
  $$('[data-frame]').forEach(button=>button.addEventListener('click',()=>selectLightingFrame(button.dataset.frame)));
  $("#first-frame")?.addEventListener("click",()=>mutate(ensureTrack));
  $("#import-media").addEventListener("click",()=>$("#media-input").click());
  $("#gif-resample").addEventListener("change",event=>{
    state.gifResample=event.target.value;
    updateMediaCompositionTransform({...state.sourceTransform,sampling:state.gifResample});
  });
  $("#relic-gif-edges")?.addEventListener("change",event=>{
    state.relicGifEdges=event.target.checked;
    refreshMediaCompositionDestination();
    renderLightingEdit();
  });
  $("#media-input").addEventListener("change",event=>importMedia(event.currentTarget));
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
  const paintEnabled=state.studioTool==="paint"&&!localAnimationDraftMatches();
  const paint = pixel => {
    if(!paintEnabled)return;
    const frame=currentFrame();if(!frame)return;const i=Number(pixel.dataset.pixel);frame.frame_RGB[i]=state.ledColor;pixel.style.background=state.ledColor;pixel.style.setProperty('--pixel-color',state.ledColor);
    const description=pixel.dataset.pixelDescription;
    pixel.title=description?`${description} · LED ${i} · ${state.ledColor}`:`LED ${i} · ${state.ledColor}`;
    pixel.setAttribute('aria-label',description?`${description}, LED ${i}, ${state.ledColor}`:`LED ${i}, ${state.ledColor}`);
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
    if(!paintEnabled)pixel.setAttribute("aria-disabled","true");
    pixel.addEventListener('focus',()=>{state.ledPixel=index;pixels.forEach((item,itemIndex)=>{item.tabIndex=itemIndex===index?0:-1;});});
    pixel.addEventListener('keydown',event=>{
      if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key)){
        event.preventDefault();
        focusPixel(nextGridIndex(index,event.key,pixels.length,gridColumns));
      }else if(event.key===' '||event.key==='Enter'){
        if(!paintEnabled)return;
        event.preventDefault();
        pushUndo();
        paint(pixel);
        markDirty();
      }
    });
    pixel.addEventListener('pointerdown',event=>{if(!paintEnabled)return;event.preventDefault();focusPixel(index);strokeController.pointerDown(pixel);markDirty();});
    pixel.addEventListener('pointerenter',event=>{if(paintEnabled)strokeController.pointerEnter(pixel,event.buttons);});
  });
  $("#led-color").addEventListener("input",event=>{state.ledColor=event.target.value.toUpperCase();$("#led-color-text").value=state.ledColor;});
  $("#led-color-text").addEventListener("change",event=>{if(/^#[0-9a-f]{6}$/i.test(event.target.value)){state.ledColor=event.target.value.toUpperCase();renderLightingEdit();}else toast("Invalid color","Use a six-digit hex color such as #8358FF.","error");});
  $("#fill-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill(state.ledColor);}));
  $("#clear-led").addEventListener("click",()=>mutate(()=>{const track=ensureTrack();track.frame_data[state.ledFrame].frame_RGB.fill("#000000");}));
  $("#brightness").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).lightness=Number(event.target.value);}));
  $("#speed").addEventListener("change",event=>mutate(()=>{getPage(state.ledSlot).speed_ms=Number(event.target.value);}));
  $("#save-lighting-library").addEventListener("click",saveLightingToLibrary);
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

function startPlayback() {
  const preview=activeMediaPreviewTrack();
  const track=trackInfo().track;
  const frames=preview?.frames?.map(
    (colors,index)=>({frame_index:index,frame_RGB:colors}),
  )||track?.frame_data;
  if(!frames?.length)return;
  state.playing=true;renderLightingEdit();
  const tick=()=>{
    if(!state.playing)return;
    state.ledFrame=(state.ledFrame+1)%frames.length;
    const frame=frames[state.ledFrame];
    $$('.pixel').forEach(pixel=>{const color=frame.frame_RGB[Number(pixel.dataset.pixel)]||'#000000';pixel.style.background=safeRgbColor(color);pixel.style.setProperty('--pixel-color',safeRgbColor(color));});
    $$('.frame-item').forEach((node,i)=>{const selected=i===state.ledFrame;node.classList.toggle('active',selected);node.setAttribute('aria-pressed',String(selected));node.setAttribute('aria-label',`Frame ${i+1}${selected?', selected':''}`);});
  };
  const duration=preview
    ?state.mediaComposition?.mappedResult?.duration_ms
    :getPage(state.ledSlot)?.speed_ms;
  state.playTimer=setInterval(tick,Math.max(12,Number(duration||90)));
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
  state.settingsReturnRoute=null;
  navigateTo(route,{focusHeading:true});
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

// A device's identity is its transport plus its address on that transport, not
// a bare port: a raw-HID keyboard has no serial port, and two transports can
// hand out addresses that collide as plain strings.
function deviceKey(device) {
  return device?`${device.transport}:${device.address}`:null;
}

function displayGeometryDevice() {
  return selectVialLayoutDevice(productId(),state.devices,state.loadedDevice);
}

// The handle fields a device request body carries.
function deviceAddress(device) {
  return {transport:device.transport,address:device.address};
}

function selectedDevice() {
  return state.devices.find(device=>deviceKey(device)===state.selectedDevice)||null;
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
  const saved=state.deviceDocuments.get(deviceKey(device));
  const hasMacros=Array.isArray(state.config.macro_key)&&state.config.macro_key.length>0;
  $("#import-banner-macros").hidden=!(saved&&hasMacros);
  const returnButton=$("#return-connected-workspace");
  returnButton.textContent=saved?`Return to ${device.product_id}`:`Load ${device.product_id}`;
}

async function importDetachedMacros() {
  const device=mismatchedDevice();
  if(!device||!state.config)return;
  const saved=state.deviceDocuments.get(deviceKey(device));
  if(!saved)return toast("No keyboard workspace to restore",`Load ${device.product_id} before importing macros into it.`,"error");
  const source=clone(state.config),sourceName=state.fileName;
  try{
    const result=await loadImportableMacros(source);
    const incoming=result.macros||[];
    const existing=(saved.config?.macro_key||[]).length;
    if(!confirmMacroReplacement(existing,incoming.length,sourceName))return;
    if(!restoreDeviceDocument(deviceKey(device),device.product_id))throw new Error(`The saved ${device.product_id} workspace is no longer compatible.`);
    state.loadedDevice=deviceKey(device);
    state.selectedDevice=deviceKey(device);
    applyImportedMacros(result);
    await synchronizeOpenDocument();
  }catch(error){toast("Could not import macros",error.message,"error");}
}

async function returnToConnectedWorkspace() {
  const device=mismatchedDevice();
  if(!device)return;
  if(state.dirty&&!confirm(`Discard unsaved changes to ${state.fileName} and return to ${device.product_id}?`))return;
  if(restoreDeviceDocument(deviceKey(device),device.product_id)){
    state.loadedDevice=deviceKey(device);
    state.selectedDevice=deviceKey(device);
    await synchronizeOpenDocument();
    render();
    toast("Keyboard workspace restored",`${device.product_id} · ${state.fileName}`,"success");
    return;
  }
  state.selectedDevice=deviceKey(device);
  await readDevice();
}

function deviceSwitchesWorkspace(device) {
  if(!device||!state.config)return false;
  if(state.loadedDevice)return state.loadedDevice!==deviceKey(device);
  return !sameProductFamily(productId(),device.product_id);
}

function stashDeviceDocument() {
  if(!state.loadedDevice||!state.config)return;
  state.deviceDocuments.set(state.loadedDevice,{
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
  read.textContent=deviceSwitchesWorkspace(device)?`Switch to ${device.product_id}`:state.loadedDevice===deviceKey(device)?"Refresh keymap & macros":"Read keymap & macros";
  const wrongWorkspace=!sameProductFamily(productId(),device.product_id)||(state.loadedDevice&&state.loadedDevice!==deviceKey(device));
  write.textContent=`Write to ${device.product_id}`;
  write.disabled=!state.config||Boolean(wrongWorkspace);
  write.title=wrongWorkspace?"Load this keyboard before writing its configuration.":"";
}

async function scanDevices() {
  const priorDisplayGeometry=projectVialKeyLayout(displayGeometryDevice());
  const refreshDisplayGeometry=()=>{
    const nextDisplayGeometry=projectVialKeyLayout(displayGeometryDevice());
    if(JSON.stringify(priorDisplayGeometry)!==JSON.stringify(nextDisplayGeometry))renderScreen();
  };
  $("#device-list").innerHTML='<div class="loader"></div>';
  $("#device-actions").hidden=true;
  try {
    const result=await api('/api/devices');
    const previous=new Map(state.devices.map(device=>[deviceKey(device),device]));
    state.devices=(result.devices||[]).map(device=>{
      const known=previous.get(deviceKey(device));
      const deep={
        ...(known?.key_layout?.length&&!device.key_layout?.length?{key_layout:known.key_layout}:{}),
        ...(Number.isInteger(Number(known?.macro_count))&&Number.isInteger(Number(known?.macro_buffer_bytes))?{
          macro_count:known.macro_count,
          macro_buffer_bytes:known.macro_buffer_bytes,
        }:{}),
      };
      return {...device,...deep};
    });
    const keyboards=state.devices.filter(device=>device.is_keyboard);
    $(".status-light").classList.toggle("online",Boolean(keyboards.length));
    if(!keyboards.length){
      state.selectedDevice=null;
      $("#device-list").innerHTML='<div class="event-empty">No supported keyboard found.<br>Connect it by USB, not through the dongle.</div>';
      updateDeviceActions();
      refreshDisplayGeometry();
      return;
    }
    if(!keyboards.some(device=>deviceKey(device)===state.selectedDevice)){
      state.selectedDevice=keyboards.some(device=>deviceKey(device)===state.loadedDevice)?state.loadedDevice:null;
    }
    $("#device-list").innerHTML=keyboards.map(device=>{const active=deviceKey(device)===state.loadedDevice;return `<button type="button" class="device-card ${deviceKey(device)===state.selectedDevice?'selected':''} ${active?'active-device':''}" data-device="${esc(deviceKey(device))}"><span><strong>${esc(device.product_id)}</strong><small>${esc(device.version||'Firmware version unavailable')} · pages ${device.pages??'?'}</small></span><span class="pill">${active?'Active':'USB'}</span></button>`;}).join('');
    $$('.device-card').forEach(card=>card.addEventListener('click',()=>{state.selectedDevice=card.dataset.device;$$('.device-card').forEach(node=>node.classList.toggle('selected',node===card));updateDeviceActions();}));
    $("#device-actions").hidden=false;
    updateDeviceActions();
    refreshDisplayGeometry();
  }catch(error){$("#device-list").innerHTML=`<div class="event-empty">${esc(error.message)}</div>`;toast('Device scan failed',error.message,'error');}
}

async function readDevice() {
  const target=selectedDevice();
  if(!target)return;
  const port=deviceKey(target);
  const button=$("#read-device");button.disabled=true;button.textContent='Reading…';
  try{
    const requestedLayers=state.config&&sameProductFamily(productId(),target.product_id)?layers().length||7:7;
    const result=await api('/api/device/read',{method:'POST',body:JSON.stringify({...deviceAddress(target),layers:requestedLayers})});
    state.devices=state.devices.map(device=>deviceKey(device)===port?{...device,...result.device}:device);
    const switching=state.loadedDevice?state.loadedDevice!==port:Boolean(state.config&&!sameProductFamily(productId(),result.device.product_id));
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
    state.loadedDevice=port;
    state.selectedDevice=port;
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
  if(!state.selectedDevice){toast('Choose a write target','Select the keyboard you intend to write.','error');showDeviceDialog();return;}
  const device=state.devices.find(item=>deviceKey(item)===state.selectedDevice);
  if(!device)return toast('Write unavailable','Select the connected keyboard again.','error');
  if(!sameProductFamily(productId(),device.product_id)||(state.loadedDevice&&state.loadedDevice!==deviceKey(device)))return toast('Write unavailable','Load the selected keyboard before writing its configuration.','error');
  const validation=await validateCurrent(false);if(!validation?.ok)return;
  state.pendingWrite={device,validation};
  $("#write-title").textContent=`Write to ${device.product_id}`;
  $("#write-token").textContent=device.product_id;
  const neonWrite=productFamily(device.product_id)==="NEON";
  const unlockNote=$("#write-unlock-note");
  unlockNote.hidden=!neonWrite;
  unlockNote.textContent=neonWrite
    ?"Physical unlock required: hold Esc and F2 together before pressing Write, then keep holding until the write begins. The app completes validation before starting this unlock handshake."
    :"";
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
  const neonWrite=productFamily(pending.device.product_id)==="NEON";
  button.disabled=true;cancel.disabled=true;close.disabled=true;input.disabled=true;
  button.textContent=verifyOnly?'Verifying accepted write…':neonWrite?'Unlocking, then writing…':`Writing ${pending.validation.frame_plan?.total||''} frames…`;
  status.className='write-status working';status.textContent=verifyOnly?'Reading the keymap again without resending the configuration.':neonWrite?'Hold Esc and F2 together. Keep holding until the write begins; no lighting, keymap, or macro SET is sent until the combo is accepted.':'Writing configuration. Keep the cable connected; verification follows automatically.';
  try{
    const endpoint=verifyOnly?'/api/device/verify':'/api/device/write';
    const result=await api(endpoint,{method:'POST',body:JSON.stringify({...deviceAddress(pending.device),config:state.config,confirmation})});
    if(result.document_revision){state.documentRevision=result.document_revision;state.documentSyncError="";}
    markDirty(false);$("#write-dialog").close();state.pendingWrite=null;
    const partialMacros=result.macro_verification==='partial';
    const macroWarning=result.macro_warning?`\n${result.macro_warning}`:'';
    toast(partialMacros?'Write accepted; macro tail unreadable':'Write verified',`${result.device.product_id} · ${result.write_units} ${result.write_unit_label} · ${result.macros} macros\nSnapshot ${result.snapshot}${macroWarning}`,partialMacros?'':'success');
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
  return Boolean(aiStudioAvailable(state.aiStatus));
}

function selectedAiBackend() {
  return $("input[name='settings-ai-backend']:checked")?.value || state.aiStatus?.backend || "ollama";
}

function proceduralTargetSnapshot() {
  const family=productFamily(productId());
  return {
    family,
    productId:productId(),
    targets:[state.ledTarget],
    frameCap:Number(activeFamilySpec().frameCap||0),
  };
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
    if(state.conceptManifest?.job_id===jobId){state.proceduralRecipes.set(key,recipe);refreshGenerationStudio();}
  }catch(error){
    if(state.conceptManifest?.job_id===jobId){state.animationError=error.message;refreshGenerationStudio();}
  }finally{state.proceduralRecipeLoads.delete(key);}
}

function hydrateProceduralAssets(manifest) {
  const attempt=latestProceduralAttempt(manifest);
  if(!attempt)return;
  if(attempt.preview_asset_id)void loadConceptAsset(manifest.job_id,attempt.preview_asset_id);
  if(attempt.recipe_asset_id)void loadProceduralRecipe(manifest.job_id,attempt.recipe_asset_id);
  if(attempt.mapped_result_asset_id)void loadMappedLightingResult(manifest.job_id,attempt.mapped_result_asset_id);
}

function refreshGenerationStudio() {
  if($("#lighting-generate-tool"))renderGenerationStudio();
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
  }else state.conceptDestination=null;
  state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:manifest?projectLightingJob(manifest):null}).state;
  state.lightingJobId=state.lighting.activeJob?.id||null;
  persistLightingState();
  history.replaceState({},"",`${location.pathname}${location.search}${formatLightingHash(state.lighting.route,state.lightingJobId)}`);
  hydrateProceduralAssets(manifest);
  if(renderPage)render();
  else{renderLightingJobStrip();refreshGenerationStudio();}
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

function proceduralProgressLabel(phase, completed, total) {
  const verb = ({rendering:"rendered",quality_check:"checked",banking:"prepared"})[phase]||"processed";
  return `${completed} of ${total} frames ${verb}`;
}

function generationStudioContext() {
  const manifest=state.conceptManifest?.job_id===state.lighting.activeJob?.id?state.conceptManifest:null;
  const target=manifest?.target||proceduralTargetSnapshot();
  const targetKey=target.targets?.[0]||state.ledTarget;
  const model=LED_MODELS[productFamily(target.family||target.product_id)]||activeLedModel();
  const targetLabel=model?.targets.find(item=>item.key===targetKey)?.label||targetKey;
  const destinationSlot=state.conceptDestination?.slot||state.ledSlot;
  return {manifest,target,targetKey,targetLabel,destinationSlot,busy:state.conceptSubmitting||["in_progress","accepted","processing"].includes(state.lighting.activeJob?.status)};
}

function renderPromptStage(context) {
  const {manifest,targetLabel,destinationSlot,busy}=context;
  const stopped=latestProceduralAttempt(manifest)?.error_code;
  $("#lighting-generate-content").innerHTML=`<div class="concept-stage">
    <div class="concept-prompt"><label class="control-label" for="effect-prompt">Describe the lighting</label><textarea id="effect-prompt" class="text-field" rows="5" maxlength="4000" placeholder="Dense violet aurora moving across the whole keyboard…" ${busy?'disabled':''}>${esc(state.aiPrompt)}</textarea></div>
    <p class="concept-destination">Custom ${destinationSlot-4} · ${esc(targetLabel)}</p>
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
    <p>Your job is durable. You can switch to Library while the result continues banking locally.</p>
    ${total?`<progress max="${total}" value="${Math.min(completed,total)}" aria-label="Generation progress"></progress><p>${proceduralProgressLabel(manifest?.phase||state.lighting.activeJob?.phase,completed,total)}</p>`:""}
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

function renderGenerationStudio() {
  const container=$("#lighting-generate-content");
  if(!container||!aiReady())return;
  const active=Boolean(state.lighting.activeJob);
  const context=generationStudioContext();
  if(state.lighting.create.stage===STAGES.REVIEW&&context.manifest)renderProceduralReview(context);
  else if(state.lighting.create.stage===STAGES.PROGRESS&&active)renderProgressStage(context);
  else renderPromptStage(context);
}

function revealGenerationStudio() {
  if(!aiReady()||!state.config||!pageData().length)return;
  if(state.lighting.route!==ROUTES.EDIT)navigateTo(ROUTES.EDIT);
  state.studioTool="generate";
  renderLightingEdit();
  requestAnimationFrame(()=>{
    const tool=$("#lighting-generate-tool");
    tool?.scrollIntoView({behavior:"smooth",block:"start"});
    (tool?.querySelector("#effect-prompt")||tool)?.focus({preventScroll:true});
  });
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
  renderGenerationStudio();
  try{
    const started=await api("/api/lighting/effects",{method:"POST",body:JSON.stringify({prompt,backend:state.aiStatus.backend,target:state.ledTarget,document_revision:state.documentRevision})});
    state.conceptPollEpoch++;
    state.conceptDestination={slot:state.ledSlot,target:started.target.targets[0]};
    state.lighting=reduceLightingState(state.lighting,{type:"JOB_SYNCED",job:{id:started.job_id,status:"in_progress",phase:"accepted",progress:null,resultAssetId:null,previewAssetId:null,recipeAssetId:null,target:started.target}}).state;
    state.lightingJobId=started.job_id;
    persistLightingState();
    renderLightingJobStrip();
    renderGenerationStudio();
    scheduleLightingJobPoll(started.job_id);
  }catch(error){state.conceptError=aiErrorMessage(error);}
  finally{state.conceptSubmitting=false;refreshGenerationStudio();}
}

function applyReviewedLighting() {
  const manifest=state.conceptManifest;
  const attempt=latestProceduralAttempt(manifest);
  const destination=state.conceptDestination;
  if(!manifest||!attempt?.mapped_result_asset_id||!destination)return;
  const decision=reduceLightingState(state.lighting,{type:"APPLY_REQUESTED"},{document:documentDescriptor(),destination});
  if(decision.blocked){state.animationError=reviewBlockedMessage(decision.blocked);renderGenerationStudio();return;}
  const result=state.mappedLightingResults.get(`${manifest.job_id}:${attempt.mapped_result_asset_id}`);
  if(!result){state.animationError="The saved LED result is still loading.";renderGenerationStudio();return;}
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
  render();
  toast("Lighting applied",`${Number(result.source_frames||0)} frames added to Custom ${destination.slot-4}. The keyboard has not been written.`,"success");
}

// Device geometry is not an AI concern and must not wait on one. It decides
// whether the editor can render at all, so it is fetched on its own before the
// first render; bundling it with the optional AI calls meant a slow or failing
// AI status could leave the editor with no layout.
async function loadDeviceGeometry() {
  try{state.capabilities=await api("/api/led/capabilities");}
  catch(error){state.capabilities=undefined;}
}

async function loadAiConfig() {
  const requests=await Promise.allSettled([api("/api/settings"),api("/api/ai/status")]);
  if(requests[0].status==="fulfilled")state.settings=requests[0].value;
  if(requests[1].status==="fulfilled")state.aiStatus=requests[1].value;
  state.ollamaModels={available:null,models:[],reason:null,loading:false};
  refreshAiGate();
}

function refreshAiGate() {
  renderLightingJobStrip();
  if(state.lighting.route===ROUTES.SETTINGS)populateSettings();
  else if(state.lighting.route===ROUTES.LIBRARY)renderLibrary();
  else renderScreen();
}

function aiReasonText(reason,status=state.aiStatus) {
  return ({
    disabled:"AI features are off.",backend_unselected:"Choose a backend.",ollama_unavailable:"The configured Ollama server is unavailable.",upgrade_required:"Upgrade the configured Ollama server, then refresh its models.",model_missing:"Refresh and choose a model from the configured Ollama server.",model_unavailable:"The selected Ollama model is no longer available with the same identity. Refresh and choose it again.",setup_required:"Run the setup test for this backend.",credential_store_unavailable:"Secure credential storage is unavailable.",credential_invalid:"The API credential is invalid.",credential_missing:"Save an API credential.",disclosure_required:status?.backend==="ollama"?"Accept the Ollama data disclosure.":"Accept the API data disclosure.",auth_invalid:"The API credential was rejected.",ready:"Ready.",
  })[reason]||"Setup needs attention.";
}

function populateOllamaModelSelect(ollama) {
  const select=$("#settings-ollama-model-select");
  const projection=projectOllamaModelPicker(state.ollamaModels,ollama,select.value);
  select.replaceChildren();
  const placeholder=document.createElement("option");
  placeholder.value="";
  placeholder.textContent=projection.placeholder;
  select.append(placeholder);
  projection.options.forEach(projected=>{
    const option=document.createElement("option");
    option.value=projected.value;
    option.textContent=projected.label;
    option.disabled=projected.disabled;
    select.append(option);
  });
  select.value=projection.value;
  select.disabled=projection.disabled;
  select.dataset.inventoryState=projection.inventoryState;
  select.dataset.selectionState=projection.selectionState;
  return projection;
}

function apiProviderSelection(
  provider=state.aiStatus?.api?.provider,
  model=state.aiStatus?.api?.model_id,
) {
  return projectApiProviderPicker(
    state.capabilities?.ai_catalog,
    state.settings?.ai?.api,
    provider,
    model,
  );
}

function populateApiProviderControls(apiState) {
  const projection=apiProviderSelection(apiState.provider,apiState.model_id);
  const providerSelect=$("#settings-api-provider");
  providerSelect.replaceChildren();
  projection.providers.forEach(provider=>{
    const option=document.createElement("option");
    option.value=provider.id;
    option.textContent=provider.label;
    providerSelect.append(option);
  });
  if(!projection.providers.length){
    const option=document.createElement("option");
    option.value="";
    option.textContent="Provider catalog unavailable";
    providerSelect.append(option);
  }
  providerSelect.value=projection.providerId||"";
  providerSelect.disabled=!projection.providerId;

  const modelSelect=$("#settings-api-model");
  modelSelect.replaceChildren();
  projection.models.forEach(model=>{
    const option=document.createElement("option");
    option.value=model.id;
    option.textContent=model.label;
    modelSelect.append(option);
  });
  if(!projection.models.length){
    const option=document.createElement("option");
    option.value="";
    option.textContent="No curated models available";
    modelSelect.append(option);
  }
  modelSelect.value=projection.modelId||"";
  modelSelect.disabled=!projection.modelId;

  const label=projection.providerLabel;
  $("#settings-api-key-label").textContent=`${label} API key`;
  $("#settings-api-key").placeholder=`Enter ${label} key`;
  $("#settings-api-disclosure-detail").textContent=`Your lighting prompt and the selected keyboard raster dimensions go to ${label}. Imported GIF, PNG, and BMP bytes, keymaps, macros, device paths, and Library files never leave this computer. API use may cost money under your provider account.`;
  $("#settings-api-test").textContent=`Test ${label} setup`;
  return projection;
}

async function openSettings() {
  if(state.lighting.route!==ROUTES.SETTINGS)state.settingsReturnRoute=state.lighting.route;
  navigateTo(ROUTES.SETTINGS,{focusHeading:true});
  setSettingsStatus("");
  await loadAiConfig();
}

function populateSettings() {
  const status=state.aiStatus;
  const enabled=Boolean(status?.enabled);
  const backend=status?.backend||"ollama";
  const migration=state.settings?.migration||{};
  const migrationBlocked=migration.required===true;
  const canDiscardLegacyCredential=migrationBlocked&&["credential_store_unavailable","credential_invalid"].includes(migration.reason);
  const repair=$("#settings-migration-repair");
  const confirm=$("#settings-migration-confirm");
  repair.hidden=!migrationBlocked;
  $("#settings-migration-message").textContent=({
    settings_migration_write_failed:"The older settings were read, but the upgraded settings file could not be saved. Restore write access, then reopen Settings.",
    settings_migration_invalid:"The older settings contain data that cannot be safely upgraded. The original file was left unchanged; correct or replace it before saving settings.",
    credential_invalid:"The legacy API credential is invalid and cannot be moved into secure storage. Explicitly continue without that legacy credential to repair the remaining settings.",
  })[migration.reason]||"The legacy API credential could not be moved into secure storage. Retry after credential storage is available, or explicitly continue without that legacy credential.";
  $("#settings-migration-confirm-row").hidden=!canDiscardLegacyCredential;
  $("#settings-migration-discard").hidden=!canDiscardLegacyCredential;
  if(!migrationBlocked)confirm.checked=false;
  $("#settings-migration-discard").disabled=!canDiscardLegacyCredential||!confirm.checked;
  $("#settings-mutable").inert=migrationBlocked;
  $("#settings-save").disabled=migrationBlocked||state.settingsSaveBusy;
  $("#settings-ai-enabled").checked=enabled;
  $("#settings-ai-details").hidden=!enabled;
  $("#settings-ai-ollama").checked=backend==="ollama";
  $("#settings-ai-api").checked=backend==="api";
  $("#settings-ai-state").textContent=aiReady()?"Ready":enabled?"Setup needed":"Off";
  $("#settings-ai-state").className=`pill ${aiReady()?"":"muted"}`;
  $("#settings-ollama-panel").hidden=backend!=="ollama";
  $("#settings-api-panel").hidden=backend!=="api";
  const ollama=status?.ollama||{};
  const pickerProjection=populateOllamaModelSelect(ollama);
  const ollamaAvailable=state.ollamaModels.available===true;
  const upgradeRequired=state.ollamaModels.reason==="upgrade_required"||status?.reason==="upgrade_required";
  const ollamaBaseUrl=ollama.base_url||state.settings?.ai?.ollama?.base_url||"";
  const ollamaFlow=ollamaEndpointDataFlow(ollamaBaseUrl,ollama.model_location);
  $("#settings-ollama-base-url").value=ollamaBaseUrl;
  $("#settings-ollama-runtime").textContent=state.ollamaModels.loading?"Checking":upgradeRequired?"Upgrade needed":ollamaAvailable?"Server reached":state.ollamaModels.available===false?"Unavailable":"Not checked";
  $("#settings-ollama-runtime").className=`pill ${ollamaAvailable&&!upgradeRequired?"":"muted"}`;
  $("#settings-ollama-transport-warning").hidden=!ollamaFlow.insecureRemote;
  const ollamaDisclosureRequired=Boolean(ollama.disclosure_required);
  $("#settings-ollama-disclosure").hidden=!ollamaDisclosureRequired;
  $("#settings-ollama-disclosure-detail").textContent=[
    !ollamaFlow.loopback?"The configured Ollama server receives your lighting prompt and the selected keyboard dimensions.":null,
    ollama.model_location==="ollama_cloud"?"The configured Ollama server may forward the request to Ollama Cloud.":null,
    "Imported media, profiles, keymaps, macros, device paths, and Library files are not sent.",
  ].filter(Boolean).join(" ");
  $("#settings-ollama-disclosure-ack").checked=Boolean(ollama.disclosure_current);
  let ollamaGuidance="Refresh models from the configured Ollama server.";
  if(backend==="ollama"){
    if(upgradeRequired)ollamaGuidance="Upgrade the configured Ollama server, then refresh models.";
    else if(pickerProjection.inventoryState==="transient_failure")ollamaGuidance="Ollama could not be refreshed. The previous model choice is preserved; try Refresh again.";
    else if(pickerProjection.inventoryState==="not_refreshed")ollamaGuidance=ollama.model_selected?"Run Test setup, or Refresh to update the model list.":"Refresh models from the configured Ollama server.";
    else if(!ollamaAvailable)ollamaGuidance="Check the Ollama server URL, then refresh models.";
    else if(pickerProjection.selectionState==="none")ollamaGuidance="Choose one of the models reported by this Ollama server.";
    else if(pickerProjection.selectionState==="removed")ollamaGuidance="The selected model is no longer available. Refresh and choose another model.";
    else if(pickerProjection.selectionState==="digest_changed")ollamaGuidance="The selected model name now has a different identity. Select it again, then rerun setup.";
    else if(ollamaDisclosureRequired&&!ollama.disclosure_current)ollamaGuidance="Review and accept the Ollama data disclosure, then run Test setup.";
    else if(!ollama.setup_tested)ollamaGuidance="Run Test setup to verify this model can create lighting recipes.";
    else ollamaGuidance="Ready.";
  }
  $("#settings-ollama-state").textContent=ollamaGuidance;
  const selectedLocation=ollama.model_location==="ollama_cloud"?"Ollama Cloud":"On this Ollama server";
  const selectedSuffix=pickerProjection.selectionState==="removed"?" · no longer available":pickerProjection.selectionState==="digest_changed"?" · identity changed":pickerProjection.selectionState==="transient_failure"?" · refresh to check":"";
  $("#settings-ollama-model").textContent=ollama.model_selected?`Selected: ${ollama.model_id} — ${selectedLocation}${selectedSuffix}`:"No Ollama model selected.";
  const picker=$("#settings-ollama-model-select");
  $("#settings-ollama-refresh").disabled=state.ollamaModels.loading;
  $("#settings-ollama-select").disabled=picker.disabled||!picker.value||!state.ollamaModels.models.some(model=>model.model_id===picker.value);
  $("#settings-ollama-clear").disabled=!ollama.model_selected;
  $("#settings-ollama-test").disabled=!ollama.model_selected;
  const apiState=status?.api||{};
  const apiProjection=populateApiProviderControls(apiState);
  $("#settings-api-credential-state").textContent=apiState.credential_set?`A ${apiProjection.providerLabel} credential is stored securely.`:`No ${apiProjection.providerLabel} credential is configured.`;
  $("#settings-api-remove").disabled=!apiState.credential_set;
  $("#settings-api-disclosure-ack").checked=Boolean(apiState.disclosure_current);
  $("#settings-library-root").value=state.settings?.library?.current_root||"";
  $("#settings-reveal-library").disabled=!state.settings?.library?.current_root;
}

async function refreshSettingsData() {
  const [settings,status]=await Promise.all([api("/api/settings"),api("/api/ai/status")]);
  state.settings=settings;
  state.aiStatus=status;
  populateSettings();
  refreshAiGate();
}

async function setAiEnabled(enabled) {
  const toggle=$("#settings-ai-enabled");
  const backend=selectedAiBackend();
  toggle.disabled=true;
  $("#settings-ai-details").hidden=!enabled;
  setSettingsStatus(enabled?"Turning on AI features…":"Turning off AI features…","working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({enabled,backend})});
    if(!enabled)state.ollamaModels={available:null,models:[],reason:null,loading:false};
    populateSettings();
    refreshAiGate();
    setSettingsStatus(enabled?(aiReady()?"AI features are on and ready.":`${aiReasonText(state.aiStatus.reason)} Configure the selected backend below.`):"AI features are off. All AI setup and generation controls are hidden.");
  }catch(error){
    populateSettings();
    refreshAiGate();
    setSettingsStatus(error.message,"error");
  }finally{toggle.disabled=false;}
}

async function selectAiBackend(backend) {
  setSettingsStatus("Updating backend…","working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({backend})});
    populateSettings();
    refreshAiGate();
    setSettingsStatus(backend==="ollama"?"Ollama selected. Refresh models, choose one, then test its setup.":"API backend selected. Save a credential, accept the disclosure, and test its setup.");
  }catch(error){setSettingsStatus(error.message,"error");}
}

async function selectApiProvider() {
  const selection=apiProviderSelection($("#settings-api-provider").value,null);
  if(!selection.providerId||!selection.modelId){
    setSettingsStatus("The API provider catalog is unavailable.","error");
    return;
  }
  setSettingsStatus(`Selecting ${selection.providerLabel}…`,"working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({backend:"api",provider:selection.providerId,model_id:selection.modelId})});
    state.settings=await api("/api/settings");
    populateSettings();
    refreshAiGate();
    setSettingsStatus(`${selection.providerLabel} selected. Save its credential, accept its disclosure, and run Test setup.`);
  }catch(error){populateSettings();setSettingsStatus(error.message,"error");}
}

async function selectApiModel() {
  const selection=apiProviderSelection(
    $("#settings-api-provider").value,
    $("#settings-api-model").value,
  );
  if(!selection.providerId||!selection.modelId){
    setSettingsStatus("Choose a curated API model first.","error");
    return;
  }
  setSettingsStatus(`Selecting ${selection.models.find(model=>model.id===selection.modelId)?.label||selection.modelId}…`,"working");
  try{
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({backend:"api",provider:selection.providerId,model_id:selection.modelId})});
    state.settings=await api("/api/settings");
    populateSettings();
    refreshAiGate();
    setSettingsStatus("Model selected. Run Test setup.");
  }catch(error){populateSettings();setSettingsStatus(error.message,"error");}
}

async function saveOllamaBaseUrl({quiet=false}={}) {
  const input=$("#settings-ollama-base-url");
  const baseUrl=input.value.trim();
  if(!baseUrl){
    if(!quiet)setSettingsStatus("Enter an Ollama server URL.","error");
    return false;
  }
  const current=state.settings?.ai?.ollama?.base_url||state.aiStatus?.ollama?.base_url||"";
  if(baseUrl===current)return true;
  if(!quiet)setSettingsStatus("Saving Ollama server…","working");
  try{
    const result=await api("/api/settings/ollama",{method:"POST",body:JSON.stringify({base_url:baseUrl})});
    state.settings={...state.settings,ai:{...state.settings?.ai,ollama:result.ollama}};
    state.ollamaModels={available:null,models:[],reason:null,loading:false};
    state.aiStatus={
      ...state.aiStatus,
      ready:false,
      reason:state.aiStatus?.enabled?"model_missing":"disabled",
      ollama:{
        ...state.aiStatus?.ollama,
        base_url:result.ollama.base_url,
        model_selected:false,
        model_id:null,
        model_digest:null,
        model_location:null,
        model_verified:false,
        setup_tested:false,
        disclosure_required:!ollamaEndpointDataFlow(result.ollama.base_url).loopback,
        disclosure_current:ollamaEndpointDataFlow(result.ollama.base_url).loopback,
        provider:"ollama",
      },
    };
    populateSettings();
    refreshAiGate();
    if(!quiet)setSettingsStatus("Ollama server saved. Refresh models when you are ready.");
    return true;
  }catch(error){
    populateSettings();
    if(!quiet)setSettingsStatus(error.message,"error");
    return false;
  }
}

async function refreshOllamaModels({quiet=false}={}) {
  state.ollamaModels={...state.ollamaModels,loading:true};
  populateSettings();
  if(!quiet)setSettingsStatus("Refreshing models from the configured Ollama server…","working");
  try{
    state.ollamaModels=normalizeOllamaModels(await api("/api/ai/ollama/models"));
    populateSettings();
    if(!quiet)setSettingsStatus(state.ollamaModels.reason==="upgrade_required"?"The configured Ollama server must be upgraded before models can be discovered.":state.ollamaModels.available?(state.ollamaModels.models.length?`${state.ollamaModels.models.length} completion model${state.ollamaModels.models.length===1?"":"s"} reported.`:"The configured Ollama server reported no completion models."):"The configured Ollama server is unavailable.",state.ollamaModels.reason==="upgrade_required"||!state.ollamaModels.available?"error":"");
  }catch(error){state.ollamaModels=ollamaModelRefreshFailed(state.ollamaModels);populateSettings();if(!quiet)setSettingsStatus("The configured Ollama server could not be reached. The previous model choice is preserved; try Refresh again.","error");}
}

async function selectOllamaModel() {
  const modelId=$("#settings-ollama-model-select").value;
  const model=state.ollamaModels.models.find(candidate=>candidate.model_id===modelId);
  if(!model){setSettingsStatus("Refresh and choose an Ollama model first.","error");return;}
  setSettingsStatus(`Selecting ${modelId}…`,"working");
  try{state.aiStatus=await api("/api/ai/ollama/select",{method:"POST",body:JSON.stringify({model_id:model.model_id,model_digest:model.digest,model_location:model.location})});populateSettings();refreshAiGate();setSettingsStatus(`${model.label} selected. Run Test setup.`);}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function clearOllamaModel() {
  setSettingsStatus("Clearing selection…","working");
  try{state.aiStatus=await api("/api/ai/ollama/clear",{method:"POST",body:"{}"});populateSettings();refreshAiGate();setSettingsStatus("Ollama model selection cleared. No model was changed or removed.");}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function testAiBackend(backend) {
  setSettingsStatus(backend==="ollama"?"Testing the selected model through Ollama…":"Testing the API setup…","working");
  try{
    if(state.aiStatus?.backend!==backend)state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({backend})});
    if(backend==="ollama"){
      if(state.aiStatus?.ollama?.disclosure_required&&!state.aiStatus.ollama.disclosure_current){
        if(!$("#settings-ollama-disclosure-ack").checked)throw new Error("Accept the Ollama data disclosure before testing.");
        state.aiStatus=await api("/api/settings/ollama/disclosure",{method:"POST",body:JSON.stringify({version:state.aiStatus.ollama.disclosure_version})});
      }
    }else{
      const selection=apiProviderSelection();
      if(!selection.providerId||!selection.modelId||!selection.disclosureVersion)throw new Error("The selected API provider is unavailable.");
      if(state.aiStatus?.api?.provider!==selection.providerId||state.aiStatus?.api?.model_id!==selection.modelId){
        state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({provider:selection.providerId,model_id:selection.modelId})});
        state.settings=await api("/api/settings");
      }
      const key=$("#settings-api-key").value.trim();
      if(key){state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:selection.providerId,key})});$("#settings-api-key").value="";}
      if(!state.aiStatus.api.disclosure_current){
        if(!$("#settings-api-disclosure-ack").checked)throw new Error("Accept the API data disclosure before testing.");
        state.settings=await api("/api/settings/privacy",{method:"POST",body:JSON.stringify({provider:selection.providerId,version:selection.disclosureVersion})});
      }
    }
    state.aiStatus=await api("/api/ai/test",{method:"POST",body:JSON.stringify({backend})});
    await refreshSettingsData();
    setSettingsStatus(backend==="ollama"?"Ollama setup passed. AI generation is ready.":"API setup passed. AI generation is ready.");
  }catch(error){
    try{state.aiStatus=await api("/api/ai/status");populateSettings();refreshAiGate();}catch(refreshError){}
    setSettingsStatus(aiErrorMessage(error),"error");
  }
}

async function saveApiCredential() {
  const key=$("#settings-api-key").value.trim();
  if(!key){setSettingsStatus("Enter an API key to save.","error");return;}
  const selection=apiProviderSelection();
  if(!selection.providerId){setSettingsStatus("Choose an API provider first.","error");return;}
  setSettingsStatus("Saving credential securely…","working");
  try{state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:selection.providerId,key})});$("#settings-api-key").value="";populateSettings();setSettingsStatus(`${selection.providerLabel} credential saved. Run Test setup.`);}
  catch(error){setSettingsStatus(error.message,"error");}
}

async function clearSettingsKey() {
  const selection=apiProviderSelection();
  if(!selection.providerId){setSettingsStatus("Choose an API provider first.","error");return;}
  setSettingsStatus("Removing credential…","working");
  try{state.aiStatus=await api("/api/settings/credential",{method:"POST",body:JSON.stringify({provider:selection.providerId,key:""})});populateSettings();refreshAiGate();setSettingsStatus(`${selection.providerLabel} credential removed.`);}
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
    if(backend==="ollama"&&!await saveOllamaBaseUrl({quiet:true}))throw new Error("The Ollama server URL could not be saved.");
    state.aiStatus=await api("/api/settings/ai",{method:"POST",body:JSON.stringify({enabled,backend})});
    const requestedRoot=$("#settings-library-root").value.trim()||null;
    if(requestedRoot!==state.settings.library?.current_root)state.settings=await api("/api/settings/library",{method:"POST",body:JSON.stringify({current_root:requestedRoot})});
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
$("#empty-open").addEventListener("click",()=>$("#open-input").click());
$("#empty-connect").addEventListener("click",showDeviceDialog);
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
$("#write-dialog").addEventListener("cancel",event=>{if(state.pendingWrite&&productFamily(state.pendingWrite.device.product_id)==="NEON")event.preventDefault();});
$("#write-dialog").addEventListener("close",()=>{if($("#write-dialog").returnValue==='cancel')state.pendingWrite=null;});
$("#undo-button").addEventListener("click",undo);
$("#redo-button").addEventListener("click",redo);
$("#validate-button").addEventListener("click",()=>validateCurrent());
$("#settings-button").addEventListener("click",openSettings);
$("#settings-save").addEventListener("click",()=>saveSettings());
$("#settings-done").addEventListener("click",()=>state.settings?.migration?.required?finishSettings():saveSettings({exit:true}));
$("#settings-migration-confirm").addEventListener("change",populateSettings);
$("#settings-migration-discard").addEventListener("click",discardLegacyApiCredential);
$("#settings-ai-enabled").addEventListener("change",event=>void setAiEnabled(event.target.checked));
$("#settings-ai-ollama").addEventListener("change",()=>selectAiBackend("ollama"));
$("#settings-ai-api").addEventListener("change",()=>selectAiBackend("api"));
$("#settings-ollama-save-url").addEventListener("click",saveOllamaBaseUrl);
$("#settings-ollama-refresh").addEventListener("click",()=>refreshOllamaModels());
$("#settings-ollama-model-select").addEventListener("change",populateSettings);
$("#settings-ollama-select").addEventListener("click",selectOllamaModel);
$("#settings-ollama-test").addEventListener("click",()=>testAiBackend("ollama"));
$("#settings-ollama-clear").addEventListener("click",clearOllamaModel);
$("#settings-api-provider").addEventListener("change",selectApiProvider);
$("#settings-api-model").addEventListener("change",selectApiModel);
$("#settings-api-key").addEventListener("keydown",event=>{if(event.key==='Enter'){event.preventDefault();saveApiCredential();}});
$("#settings-api-save-key").addEventListener("click",saveApiCredential);
$("#settings-api-test").addEventListener("click",()=>testAiBackend("api"));
$("#settings-api-remove").addEventListener("click",clearSettingsKey);
$("#settings-choose-library").addEventListener("click",chooseLibraryFolder);
$("#settings-reveal-library").addEventListener("click",revealLibraryFolder);
$("#library-add-files").addEventListener("click",()=>$("#library-profile-input").click());
$("#library-profile-input").addEventListener("change",event=>void importLibraryProfiles(event.currentTarget));
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
  state.library.page=1;
  state.library.loaded=false;
  void loadLibrary({force:true});
}));
$("#library-search").addEventListener("input",event=>{
  state.library.query=event.target.value;
  if(state.library.searchTimer)clearTimeout(state.library.searchTimer);
  state.library.searchTimer=setTimeout(()=>{
    state.library.page=1;
    state.library.loaded=false;
    void loadLibrary({force:true});
  },280);
});
$("#library-page-previous").addEventListener("click",()=>{
  if(state.library.loading||state.library.page<=1)return;
  state.library.page--;
  state.library.loaded=false;
  void loadLibrary({force:true});
});
$("#library-page-next").addEventListener("click",()=>{
  if(state.library.loading||!state.library.hasMore)return;
  state.library.page++;
  state.library.loaded=false;
  void loadLibrary({force:true});
});
$("#library-confirm-action").addEventListener("click",async event=>{
  const action=libraryConfirmAction;
  if(!action)return;
  const button=event.currentTarget;
  button.disabled=true;
  try{
    await action();
    if($("#library-confirm-dialog").open)$("#library-confirm-dialog").close();
  }finally{
    if(button.isConnected)button.disabled=false;
  }
});
$("#library-confirm-dialog").addEventListener("close",()=>{
  libraryConfirmAction=null;
});
$("#about-button").addEventListener("click",()=>{
  const dialog=$("#about-dialog");
  if(!dialog.open)dialog.showModal();
});
$("#about-dialog").addEventListener("click",event=>{
  if(event.target===event.currentTarget)event.currentTarget.close();
});
$("#about-dialog").addEventListener("close",()=>{
  $("#about-button").focus({preventScroll:true});
});
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
  cancelLocalAnimationDraft({render:false});
  state.ledSlot=Number(button.dataset.lightingSlot);
  state.ledFrame=0;
  state.ledPixel=0;
  renderLightingShell();
}));
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
    await loadDeviceGeometry();
    render();
    restoreLightingJob();
    scanDevices();
    loadAiConfig();
  }catch(error){toast('Could not start configurator',error.message,'error');}
})();
