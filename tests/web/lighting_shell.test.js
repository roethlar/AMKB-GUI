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
  const appScript=html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript>=0&&stateScript<reviewScript&&reviewScript<appScript);
  assert.match(server,/"\/lighting_state\.js":\s*"lighting_state\.js"/);
  assert.match(server,/"\/lighting_review\.js":\s*"lighting_review\.js"/);
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
  assert.match(effect,/JSON\.stringify\(\{prompt,backend:state\.aiStatus\.backend,loop_mode:state\.animationLoopMode\}\)/);
  assert.doesNotMatch(effect,/model_path|model_id|frame_count|product_id:/);
});

test("API setup stays secondary, explicit, and confined to Settings", () => {
  assert.match(js,/api\("\/api\/settings\/credential"/);
  assert.match(js,/api\("\/api\/settings\/privacy"/);
  assert.match(html,/prompt and the selected keyboard raster dimensions go to xAI/i);
  assert.match(html,/API use may cost money/);
  const generation=js.slice(js.indexOf("async function startProceduralGeneration"),js.indexOf("function applyReviewedLighting",js.indexOf("async function startProceduralGeneration")));
  assert.doesNotMatch(generation,/settings-api|credential|privacy|disclosure|provider|model_id/);
});

test("generation is one prompt, durable progress, animated review, and explicit Apply", () => {
  const generationSurface=`${js}\n${review}`;
  for(const id of ["effect-prompt","generate-effect","cancel-effect","apply-procedural-effect"]){
    assert.match(generationSurface,new RegExp(`id="${id}"`));
  }
  assert.match(js,/api\("\/api\/lighting\/effects"/);
  assert.match(js,/backend:state\.aiStatus\.backend/);
  assert.match(js,/scheduleLightingJobPoll\(started\.job_id\)/);
  assert.match(js,/procedural_attempts/);
  assert.match(js,/preview_asset_id/);
  assert.match(js,/recipe_asset_id/);
  assert.match(js,/mapped_result_asset_id/);
  assert.match(review,/Animated exact-raster lighting preview/);
  assert.match(js,/createReviewView\(\{assetUrls:state\.conceptAssetUrls/);
  assert.match(js,/renderReview\(\$\("#lighting-generate-content"\),view,applyReviewedLighting\)/);
  assert.match(js,/saved failure does not disable this backend/);
  assert.match(js,/syncLightingJob\(null,\{renderPage:false\}\)/);
  assert.match(js,/type:"APPLY_REQUESTED"/);
  const applyStart=js.lastIndexOf("function applyReviewedLighting");
  const applyEnd=js.indexOf("async function loadAiConfig",applyStart);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  assert.match(apply,/keyboard has not been written/);
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

test("Settings remains a saveable route with Library and loop preferences", () => {
  assert.match(html,/id="settings-save"[^>]*>Save changes</);
  assert.match(html,/id="settings-done"[^>]*>Done</);
  for(const id of ["settings-library-root","settings-choose-library","settings-reveal-library","settings-loop-mode"]){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  assert.match(js,/api\("\/api\/settings\/ai"/);
  assert.match(js,/api\("\/api\/settings\/preferences"/);
  assert.match(js,/api\("\/api\/settings\/library"/);
  assert.match(js,/api\("\/api\/native\/choose-library"/);
  assert.match(js,/api\("\/api\/native\/reveal-library"/);
  assert.match(js,/function finishSettings[\s\S]*navigateTo\(route/);
});

test("manual Lighting layout, keyboard controls, narrow windows, and reduced motion remain", () => {
  assert.match(html,/role="tablist"[^>]*aria-label="Lighting views"/);
  assert.match(js,/role="grid"[^>]*aria-label="LED paint grid"/);
  assert.match(js,/nextGridIndex\(/);
  assert.match(js,/event\.key===['"] ['"]\|\|event\.key===['"]Enter['"]/);
  assert.match(js,/focusSelectedFrame\(/);
  assert.match(js,/focusSelectedTarget\(/);
  assert.doesNotMatch(css,/min-width:\s*880px/);
  assert.match(css,/@media\s*\(max-width:\s*720px\)/);
  assert.match(css,/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  const medium=css.match(/@media\s*\(max-width:\s*1240px\)\s*\{[\s\S]*?\n\}/)?.[0]||"";
  assert.match(medium,/grid-template-areas:\s*"canvas controls"\s*"frames frames"/);
  assert.match(medium,/overflow-x:\s*auto/);
});
