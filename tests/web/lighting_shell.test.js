"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const review = fs.readFileSync(path.join(root, "am_configurator/web/lighting_review.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("pure lighting state loads before the application adapter", () => {
  const stateScript=html.indexOf('<script src="/lighting_state.js"></script>');
  const reviewScript=html.indexOf('<script src="/lighting_review.js"></script>');
  const targetsScript=html.indexOf('<script src="/lighting_targets.js"></script>');
  const appScript=html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript>=0&&stateScript<reviewScript&&reviewScript<targetsScript&&targetsScript<appScript);
  assert.match(server,/"\/lighting_state\.js":\s*"lighting_state\.js"/);
  assert.match(server,/"\/lighting_review\.js":\s*"lighting_review\.js"/);
  assert.match(server,/"\/lighting_targets\.js":\s*"lighting_targets\.js"/);
});

test("lighting color style interpolation uses only canonical RGB", () => {
  assert.match(js,/normalizeImportedLightingColors\(normalizeImportedAssignmentCodes\(parsed\)\)/);
  assert.match(js,/background:\$\{safeRgbColor\(color\)\}/);
  assert.doesNotMatch(js,/background:\$\{esc\(color\)\}/);
  assert.match(js,/pixel\.style\.background=safeRgbColor\(color\)/);
  assert.match(js,/setProperty\('--pixel-color',safeRgbColor\(color\)\)/);
});

test("persistent job strip remains available outside routed content", () => {
  const strip=html.indexOf('id="lighting-job-strip"');
  const routeContent=html.indexOf('id="route-content"');
  assert.ok(strip>=0&&strip<routeContent);
  assert.match(html,/id="lighting-job-phase-live"[^>]*aria-live="polite"/);
  assert.match(js,/\$\("#lighting-job-view"\)\.addEventListener\("click",openGenerationDialog\)/);
});

test("disabled first paint exposes no generation control outside Settings", () => {
  const trigger=html.match(/<button id="lighting-generate-open"[^>]*>/)?.[0]||"";
  const dialog=html.match(/<dialog id="lighting-generate-dialog"[^>]*>/)?.[0]||"";
  assert.match(trigger,/\shidden(?:\s|>)/);
  assert.match(dialog,/\shidden(?:\s|>)/);
  const beforeSettings=html.slice(0,html.indexOf('id="settings-screen"'));
  assert.doesNotMatch(beforeSettings,/GGUF|xAI|API key|Optional AI|Test &amp; enable/);
  assert.doesNotMatch(js,/data-library-create/);
  assert.match(js,/button\.hidden=!aiReady\(\)/);
  assert.match(js,/route===ROUTES\.CREATE&&!aiReady\(\)&&!state\.lighting\.activeJob/);
  const loader=js.slice(js.indexOf("async function loadAiConfig"),js.indexOf("function refreshAiGate"));
  assert.match(loader,/shouldDiscoverLocalModels\(state\.lighting\.route,state\.aiStatus\)/);
  assert.equal((loader.match(/\/api\/ai\/local\/models/g)||[]).length,1);
  assert.doesNotMatch(loader,/Promise\.allSettled\(\[[^\]]*\/api\/ai\/local\/models/);
});

test("Settings exposes only installed Ollama models and the curated API", () => {
  const local=html.indexOf('id="settings-ai-local"');
  const api=html.indexOf('id="settings-ai-api"');
  assert.ok(local>=0&&local<api);
  for(const id of [
    "settings-ai-enabled","settings-ai-local","settings-ai-api","settings-local-state",
    "settings-local-model","settings-local-model-select","settings-local-refresh",
    "settings-local-select","settings-local-test","settings-local-clear",
    "settings-api-provider","settings-api-model","settings-api-key","settings-api-credential-state",
    "settings-api-disclosure-ack","settings-api-test","settings-api-remove",
  ])assert.match(html,new RegExp(`id="${id}"`));
  assert.match(html,/never downloads model weights/);
  const localPanel=html.slice(html.indexOf('id="settings-local-panel"'),html.indexOf('id="settings-api-panel"'));
  assert.match(localPanel,/Ollama/);
  assert.doesNotMatch(localPanel,/GGUF|llama\.cpp|GPU backend|direct model/i);
  assert.doesNotMatch(html,/settings-gguf|settings-local-advanced/);
  assert.match(js,/api\("\/api\/ai\/local\/models"/);
  assert.match(js,/api\("\/api\/ai\/local\/select"/);
  assert.match(js,/JSON\.stringify\(\{model_id/);
  assert.match(js,/api\("\/api\/ai\/local\/clear"/);
  assert.match(js,/api\("\/api\/ai\/test"/);
  assert.doesNotMatch(js,/\/api\/ai\/local\/gguf|settings-gguf|chooseAdvancedLocalModel/);
  assert.doesNotMatch(server,/\/api\/ai\/local\/gguf|_select_advanced_local_model|_choose_local_model/);
  assert.match(js,/model_id/);
  assert.match(css,/\.check-row\s*>\s*span\s*\{[^}]*display:\s*grid[^}]*gap:/);
  const effect=js.slice(js.indexOf("async function startProceduralGeneration"),js.indexOf("function applyReviewedLighting",js.indexOf("async function startProceduralGeneration")));
  assert.match(effect,/JSON\.stringify\(\{prompt,backend:state\.aiStatus\.backend,document_revision:state\.documentRevision\}\)/);
  assert.doesNotMatch(effect,/model_path|model_id|frame_count|product_id:/);
  assert.match(js,/api\("\/api\/document\/sync"/);
  const fileOpen=js.slice(js.indexOf("async function readFiles"),js.indexOf("function saveConfig",js.indexOf("async function readFiles")));
  assert.match(fileOpen,/await synchronizeOpenDocument\(\)/);
  const deviceRead=js.slice(js.indexOf("async function readDevice"),js.indexOf("async function writeDevice"));
  assert.match(deviceRead,/await synchronizeOpenDocument\(\)/);
  const restore=js.slice(js.indexOf("async function returnToConnectedWorkspace"),js.indexOf("function deviceSwitchesWorkspace"));
  assert.match(restore,/await synchronizeOpenDocument\(\)/);
});

test("Settings explains incompatible Ollama discovery without adding show", () => {
  assert.match(js,/normalizeLocalModels\(await api\("\/api\/ai\/local\/models"\)\)/);
  assert.match(js,/Ollama must be upgraded before local AI can discover installed models/);
  assert.match(js,/Upgrade Ollama to use local AI/);
  assert.doesNotMatch(js,/\/api\/show/);
});

test("Settings exposes an explicit blocked-migration credential discard", () => {
  for(const id of [
    "settings-migration-repair","settings-migration-message","settings-migration-confirm",
    "settings-migration-discard","settings-mutable",
  ])assert.match(html,new RegExp(`id="${id}"`));
  assert.match(html,/continue without the legacy API credential/i);
  assert.match(html,/OS credential|credential vault/i);
  assert.match(js,/\/api\/settings\/migration\/discard-credential/);
  assert.match(js,/JSON\.stringify\(\{confirm:true\}\)/);
  assert.match(js,/settings_migration_invalid/);
});

test("API setup stays secondary, explicit, and confined to Settings", () => {
  assert.match(js,/api\("\/api\/settings\/credential"/);
  assert.match(js,/api\("\/api\/settings\/privacy"/);
  assert.match(html,/prompt and the selected keyboard raster dimensions go to xAI/i);
  assert.match(html,/API use may cost money/);
  const generation=js.slice(js.indexOf("async function startProceduralGeneration"),js.indexOf("function applyReviewedLighting",js.indexOf("async function startProceduralGeneration")));
  assert.doesNotMatch(generation,/settings-api|credential|privacy|disclosure|provider|model_id/);
});

test("saving Settings lets the server validate backend re-enablement", () => {
  const save=js.slice(js.indexOf("async function saveSettings"),js.indexOf("function showDeviceDialog"));
  assert.match(save,/api\("\/api\/settings\/ai"/);
  assert.doesNotMatch(save,/enabled\s*&&\s*!aiReady\(\)/);
});

test("the LED editor delegates every pointer stroke to release-safe state", () => {
  const wire=js.slice(js.indexOf("function wireLedEditor"),js.indexOf("function showDeviceDialog"));
  assert.match(wire,/createPaintStrokeController\(/);
  assert.match(wire,/\.pointerDown\(pixel\)/);
  assert.match(wire,/\.pointerEnter\(pixel,event\.buttons\)/);
  assert.doesNotMatch(wire,/pointerup[^\n]*once:true/);
});

test("generation is one prompt, durable progress, animated review, and explicit Apply", () => {
  const generationSurface=`${js}\n${review}`;
  for(const id of ["effect-prompt","generate-effect","cancel-effect","apply-procedural-effect"]){
    assert.match(generationSurface,new RegExp(`id="${id}"`));
  }
  assert.match(js,/api\("\/api\/lighting\/effects"/);
  assert.match(js,/backend:state\.aiStatus\.backend/);
  assert.match(js,/scheduleLightingJobPoll\(started\.job_id\)/);
  for(const phase of ["rendering","quality_check","banking"]){
    assert.match(js,new RegExp(`${phase}:`));
  }
  assert.match(js,/proceduralProgressLabel\(/);
  assert.doesNotMatch(js,/frames saved/);
  assert.match(js,/procedural_attempts/);
  assert.match(js,/preview_asset_id/);
  assert.match(js,/recipe_asset_id/);
  assert.match(js,/mapped_result_asset_id/);
  assert.match(review,/Animated exact-raster lighting preview/);
  assert.match(js,/createReviewView\(\{assetUrls:state\.conceptAssetUrls/);
  assert.match(js,/renderReview\(\$\("#lighting-generate-content"\),view,applyReviewedLighting\)/);
  assert.match(js,/openRenderedDialog\(dialog,renderGenerationDialog\)/);
  assert.match(js,/saved failure does not disable this backend/);
  assert.match(js,/syncLightingJob\(null,\{renderPage:false\}\)/);
  assert.match(js,/type:"APPLY_REQUESTED"/);
  const applyStart=js.lastIndexOf("function applyReviewedLighting");
  const applyEnd=js.indexOf("async function loadAiConfig",applyStart);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  assert.match(apply,/keyboard has not been written/);
});

test("generation dialog omits backend identity and keeps the target destination", () => {
  const prompt=js.slice(js.indexOf("function renderPromptStage"),js.indexOf("function renderProgressStage"));
  assert.doesNotMatch(prompt,/state\.aiStatus\?\.backend/);
  assert.doesNotMatch(prompt,/===\s*"api"\s*\?\s*"API"\s*:\s*"Local"/);
  assert.match(prompt,/Custom \$\{destinationSlot-4\} · \$\{esc\(targetLabel\)\}/);
  const settings=html.slice(html.indexOf('id="settings-screen"'));
  assert.match(settings,/settings-ai-local/);
  assert.match(settings,/settings-ai-api/);
  assert.match(js,/summary\?\.costs\?\.actual_incomplete/);
});

test("closing the dialog never cancels or applies a durable job", () => {
  const start=js.lastIndexOf("function handleGenerationDialogClose");
  const end=js.indexOf("async function startProceduralGeneration",start);
  const close=js.slice(start,end);
  assert.doesNotMatch(close,/api\(|cancel|apply|mutate\(/i);
  assert.match(js,/You can close this window while the result continues banking locally/);
});

test("Library remains document-independent and browses procedural plus historical media", () => {
  for(const id of ["lighting-library-toolbar","library-search","library-refresh","library-reveal","library-status","library-content"]){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  assert.match(html,/data-library-filter="animation"/);
  assert.match(html,/data-library-filter="partial"/);
  assert.match(js,/kind","preview_animation"/);
  assert.match(js,/"preview_animation","raster_animation","source_video"/);
  assert.match(js,/fetch\(`\/api\/lighting\/assets\//);
  assert.match(js,/"X-AM-Token":token/);
  assert.match(js,/URL\.createObjectURL/);
  assert.match(js,/URL\.revokeObjectURL/);
  assert.doesNotMatch(js,/data-library-animate-job=/);
});

test("Library media failures retry once and become actionable", () => {
  assert.match(js,/assetErrors:\s*new Map\(\)/);
  assert.match(js,/data-library-asset-retry=/);
  assert.match(js,/loadLibraryAsset\(jobId,assetId,\{retry:true\}\)/);
});

test("Library asset loads revoke stale blobs and preserve refreshed ownership", () => {
  const loader=js.slice(js.indexOf("async function loadLibraryAsset"),js.indexOf("async function ensureLibraryJobDetail"));
  assert.match(loader,/createObjectURL/);
  assert.match(loader,/if\(!lease\.current\(state\.library\.epoch\)\)\{URL\.revokeObjectURL\(url\);return;\}/);
  assert.match(loader,/const ownsCurrent=lease\.current\(state\.library\.epoch\)/);
  assert.match(loader,/lease\.release\(\)/);
});

test("Settings remains saveable without a procedural loop preference", () => {
  assert.match(html,/id="settings-save"[^>]*>Save changes</);
  assert.match(html,/id="settings-done"[^>]*>Done</);
  for(const id of ["settings-library-root","settings-choose-library","settings-reveal-library"]){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  assert.doesNotMatch(html,/settings-loop-mode|Generation default|Animation loop/);
  assert.match(js,/api\("\/api\/settings\/ai"/);
  assert.match(js,/api\("\/api\/settings\/library"/);
  assert.match(js,/api\("\/api\/native\/choose-library"/);
  assert.match(js,/api\("\/api\/native\/reveal-library"/);
  assert.match(js,/function finishSettings[\s\S]*navigateTo\(route/);
  const save=js.slice(js.indexOf("async function saveSettings"),js.indexOf("function showDeviceDialog"));
  assert.doesNotMatch(save,/settings\/preferences|loop_mode|animationLoopMode/);
});

test("manual Lighting layout, keyboard controls, narrow windows, and reduced motion remain", () => {
  assert.match(html,/role="tablist"[^>]*aria-label="Lighting views"/);
  assert.match(js,/role="grid"[^>]*aria-label="LED paint grid"/);
  assert.match(js,/nextGridIndex\(/);
  assert.match(js,/event\.key===['"] ['"]\|\|event\.key===['"]Enter['"]/);
  assert.match(js,/focusSelectedFrame\(/);
  assert.match(js,/renderTargetControls\(targetHost,targets,state\.ledTarget,destinationLocked/);
  assert.match(js,/focusSelectedTarget\(/);
  assert.doesNotMatch(css,/min-width:\s*880px/);
  assert.match(css,/@media\s*\(max-width:\s*720px\)/);
  assert.match(css,/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  const medium=css.match(/@media\s*\(max-width:\s*1240px\)\s*\{[\s\S]*?\n\}/)?.[0]||"";
  assert.match(medium,/grid-template-areas:\s*"canvas controls"\s*"frames frames"/);
  assert.match(medium,/overflow-x:\s*auto/);
});
