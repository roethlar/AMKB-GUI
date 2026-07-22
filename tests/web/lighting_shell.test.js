"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("pure lighting state loads before the application adapter", () => {
  const stateScript = html.indexOf('<script src="/lighting_state.js"></script>');
  const appScript = html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript >= 0, "lighting_state.js script is missing");
  assert.ok(stateScript < appScript, "lighting_state.js must load before app.js");
  assert.match(server, /"\/lighting_state\.js":\s*"lighting_state\.js"/);
});

test("persistent job strip is a stable sibling outside routed content", () => {
  const strip = html.indexOf('id="lighting-job-strip"');
  const routeContent = html.indexOf('id="route-content"');
  const routeEnd = html.indexOf("</main>", routeContent);
  assert.ok(strip >= 0 && strip < routeContent, "job strip must precede routed content");
  assert.ok(routeContent >= 0 && routeEnd > routeContent, "routed content must be inside main");
  assert.match(html, /id="lighting-job-phase-live"[^>]*aria-live="polite"/);
  const openingTag = html.slice(html.lastIndexOf("<", strip), html.indexOf(">", strip) + 1);
  assert.doesNotMatch(openingTag, /aria-live|role="status"/);
});

test("Lighting opens in a compact Workspace with Library secondary", () => {
  assert.match(html, /data-route="lighting\/edit"/);
  assert.match(html, /role="tablist"[^>]*aria-label="Lighting views"/);
  for (const name of ["edit", "library"]) {
    assert.match(html, new RegExp(`id="lighting-${name}-tab"[^>]*role="tab"[^>]*aria-controls="lighting-${name}-panel"`));
    assert.match(html, new RegExp(`id="lighting-${name}-tab"[^>]*aria-selected="(?:true|false)"[^>]*tabindex="(?:0|-1)"`));
    assert.match(html, new RegExp(`id="lighting-${name}-panel"[^>]*role="tabpanel"[^>]*aria-labelledby="lighting-${name}-tab"`));
  }
  assert.ok(html.indexOf('id="lighting-edit-tab"') < html.indexOf('id="lighting-library-tab"'));
  assert.doesNotMatch(html, /id="lighting-create-tab"|class="lighting-hero"|class="studio-welcome|class="concept-skeleton/);
  for (const key of ["ArrowLeft", "ArrowRight", "Home", "End"]) assert.match(js, new RegExp(key));
});

test("Lighting tab activation keeps focus within the roving tablist", () => {
  const start = js.indexOf("$$('[data-lighting-route]')");
  const end = js.indexOf("$$('[data-lighting-slot]')", start);
  const wiring = js.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.doesNotMatch(wiring, /focusHeading/);
});

test("destination selectors expose their selected value and lock during review", () => {
  assert.match(html, /class="segmented compact" role="group" aria-label="Custom slot"/);
  assert.match(html, /data-lighting-slot="5"[^>]*aria-pressed="true"[^>]*aria-label="Custom slot 1"/);
  assert.match(html, /id="lighting-target-controls"[^>]*role="group"/);
  assert.match(js, /setAttribute\("aria-pressed"/);
  assert.match(js, /data-lighting-target=.*aria-pressed=/);
  assert.match(js, /destinationLocked\s*=\s*Boolean\(state\.generation\s*\|\|\s*state\.pendingGeneration\s*\|\|\s*state\.lighting\.activeJob\)/);
  assert.match(js, /slot:\s*state\.ledSlot/);
  assert.match(js, /productFamily:\s*productFamily\(productId\(\)\)/);
  assert.match(js, /getPage\(pending\.slot\)/);
});

test("global Open and Devices controls are not duplicated in routed content", () => {
  assert.equal((html.match(/id="open-button"/g) || []).length, 1);
  assert.equal((html.match(/id="device-button"/g) || []).length, 1);
  assert.doesNotMatch(html, /id="empty-open"|data-requirement-open|data-requirement-devices/);
  assert.doesNotMatch(js, /empty-open|data-requirement-open|data-requirement-devices/);
  assert.match(js, /\$\("#device-button"\)\.addEventListener\("click",showDeviceDialog\)/);
});

test("AI generation is contained in a closed secondary dialog", () => {
  const trigger = html.indexOf('id="lighting-generate-open"');
  const routeContent = html.indexOf('id="route-content"');
  const routeEnd = html.indexOf("</main>", routeContent);
  const dialog = html.indexOf('id="lighting-generate-dialog"');
  assert.ok(trigger >= 0, "secondary Generate trigger is missing");
  assert.ok(dialog > routeEnd, "generation dialog must live outside routed content");
  assert.match(html, /id="lighting-generate-dialog"[^>]*aria-labelledby="lighting-generate-title"/);
  assert.doesNotMatch(html.slice(dialog, html.indexOf(">", dialog) + 1), /\sopen(?:\s|=|>)/);

  const open = js.match(/function openGenerationDialog\s*\([^)]*\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(open, /showModal\(\)/);
  assert.doesNotMatch(open, /api\(|startGeneration|cancelGeneration|applyGeneration|mutate\(/);
  const close = js.match(/function handleGenerationDialogClose\s*\([^)]*\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.doesNotMatch(close, /api\(|cancelGeneration|discardGeneration|applyGeneration|mutate\(/);

  const editorBody = js.slice(js.indexOf("const editorBody="), js.indexOf('$("#lighting-edit-content").innerHTML', js.indexOf("const editorBody=")));
  assert.doesNotMatch(editorBody, /ai-prompt|generate-ai|\$\{aiPanel\}/);
  assert.match(js, /function renderGenerationDialog\s*\(/);
  assert.match(js, /id="concept-prompt"/);
  assert.match(js, /id="generate-concepts"/);
  assert.doesNotMatch(html, /class="create-steps"/);
});

test("the proof flow generates one banked still with no quantity or wizard controls", () => {
  const start = js.indexOf("function renderConceptStage");
  const end = js.indexOf("function animationPhaseLabel", start);
  const dialog = js.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(dialog, /Generate one still/);
  assert.doesNotMatch(dialog, /concept-output-count|Additional outputs|More like this/);
  assert.doesNotMatch(dialog, /ai-frame-count|ai-calls|API calls|>Frames</);
  assert.match(dialog, /role="radiogroup"/);
  assert.match(dialog, /id="concept-progress"[^>]*aria-label="Concept generation progress"/);
  assert.match(js, /name="lighting-concept"/);
  assert.match(js, /dataset\.candidateSlot=/);
  assert.match(js, /candidate_count:\s*1/);
  assert.match(js, /api\("\/api\/lighting\/concepts"/);
  assert.match(js, /\/api\/lighting\/jobs\/\$\{encodeURIComponent\(jobId\)\}/);
  assert.match(js, /\/api\/lighting\/assets\/\$\{encodeURIComponent\(jobId\)\}\/\$\{encodeURIComponent\(assetId\)\}/);
  assert.match(js, /type:\s*"SELECT_CANDIDATE"/);
  assert.doesNotMatch(js, /fewer frames/);
  assert.match(js, /conceptAssetLoads\.has\(key\)/);
  assert.match(js, /conceptAssetLoads\.add\(key\)/);
  assert.match(js, /acceptConceptJob\(response\.job_id/);
  assert.match(js, /scheduleLightingJobPoll\(jobId,Math\.min\(5000/);
});

test("clicking a concept opens Animate directly without an API call", () => {
  assert.doesNotMatch(js, /id="animate-selected"/);
  assert.match(js, /type:\s*"SHOW_ANIMATE"/);
  const selection = js.slice(js.indexOf("function appendConceptSlot"), js.indexOf("function updateConceptStage"));
  assert.match(selection, /type:\s*"SELECT_CANDIDATE"/);
  assert.match(selection, /showAnimateStage\(\)/);
  assert.doesNotMatch(selection, /\/animate|startLightingAnimation|api\(/);

  for (const id of [
    "animation-selected-still",
    "animation-motion",
    "animation-loop-mode",
    "start-animation",
    "retry-local-processing",
  ]) assert.match(js, new RegExp(`id="${id}"`));
  assert.match(js, /\["smooth","Smooth loop"/);
  assert.match(js, /\["none","Hard loop"/);
  assert.match(js, /\["ping_pong","Ping-pong"/);
  assert.match(js, /\/api\/lighting\/jobs\/\$\{encodeURIComponent\(jobId\)\}\/animate/);
  assert.match(js, /candidate_id:\s*selectedCandidateId/);
  assert.match(js, /motion:\s*motion\s*\|\|\s*null/);
  assert.match(js, /loop_mode:\s*state\.animationLoopMode/);
  assert.match(js, /\/api\/lighting\/jobs\/\$\{encodeURIComponent\(job\.id\)\}\/process/);

  assert.match(js, /\[\["device","LED result"\],\["source","Source video"\],\["frames","Frames"\]\]/);
  assert.match(js, /data-review-tab="\$\{value\}"/);
  assert.match(js, /<video[^>]*controls[^>]*muted[^>]*preload="metadata"/);
  assert.doesNotMatch(js, /<video[^>]*autoplay/);
  assert.match(js, /mappedLightingResults/);
  assert.match(js, /type:\s*"APPLY_REQUESTED"/);
  assert.match(js, /applyLedResultToPage\(getPage\(destination\.slot\),result,destination\.target,pairsRelicGif\)/);
  const apply = js.slice(js.indexOf("function applyReviewedLighting"), js.indexOf("\n}", js.indexOf("function applyReviewedLighting")) + 2);
  assert.match(apply, /mutate\(\(\)=>\{/);
  assert.equal((apply.match(/mutate\(/g) || []).length, 1);
});

test("Library and Settings have document-independent routed surfaces", () => {
  assert.match(html, /id="lighting-library-panel"/);
  assert.match(html, /id="settings-screen"/);
  assert.match(js, /ROUTES\.LIBRARY/);
  assert.match(js, /ROUTES\.SETTINGS/);
  assert.match(js, /function renderRoute\s*\(/);
});

test("Library browses banked manifests and authenticated local assets", () => {
  for (const id of [
    "lighting-library-toolbar",
    "library-search",
    "library-refresh",
    "library-reveal",
    "library-status",
    "library-content",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /data-library-filter="all"/);
  assert.match(html, /data-library-filter="concept"/);
  assert.match(html, /data-library-filter="video"/);
  assert.match(html, /data-library-filter="partial"/);
  assert.match(js, /api\(`\/api\/lighting\/library\?/);
  assert.match(js, /api\(`\/api\/lighting\/library\/\$\{encodeURIComponent\(jobId\)\}`/);
  assert.match(js, /fetch\(`\/api\/lighting\/assets\/\$\{encodeURIComponent\(jobId\)\}\/\$\{encodeURIComponent\(assetId\)\}`[\s\S]*"X-AM-Token":token/);
  assert.match(js, /URL\.createObjectURL/);
  assert.match(js, /clearLibraryAssetUrls/);
  assert.match(js, /URL\.revokeObjectURL/);
  assert.match(js, /function renderLibrary/);
  assert.match(js, /function openLibraryJob/);
  assert.doesNotMatch(js, /src=["'`]\/api\/lighting\/assets/);
});

test("a banked Library concept can resume directly in Animate without a provider call", () => {
  assert.match(js, /data-library-animate-job=/);
  assert.match(js, /data-library-animate-candidate=/);
  assert.match(js, /function continueLibraryConcept\s*\(/);
  const resume = js.slice(js.indexOf("function continueLibraryConcept"), js.indexOf("function renderLibrary", js.indexOf("function continueLibraryConcept")));
  assert.match(resume, /type:\s*"SELECT_CANDIDATE"/);
  assert.match(resume, /type:\s*"SHOW_ANIMATE"/);
  assert.match(resume, /openGenerationDialog\(\)/);
  assert.doesNotMatch(resume, /\/animate|method:\s*"POST"|startLightingAnimation/);
  const availability = js.slice(js.indexOf("function libraryConceptAvailability"), js.indexOf("function libraryMediaMarkup"));
  assert.doesNotMatch(availability, /if\(!document\)return/);
  assert.match(availability, /if\(document/);
  const dialog = js.slice(js.indexOf("function renderGenerationDialog"), js.indexOf("function openGenerationDialog"));
  assert.match(dialog, /STAGES\.CONCEPTS/);
  assert.doesNotMatch(dialog, /if \(!state\.config \|\| !pageData\(\)\.length\)/);
});

test("Library media failures retry once and become actionable instead of loading forever", () => {
  assert.match(js, /assetErrors:\s*new Map\(\)/);
  assert.match(js, /data-library-asset-retry=/);
  assert.match(js, /loadLibraryAsset\(jobId,assetId,\{retry:true\}\)/);
  assert.match(js, /assetErrors\.set\(key/);
  assert.match(js, /assetErrors\.delete\(key\)/);
});

test("Settings is a complete saveable route with storage and an explicit exit", () => {
  assert.match(html, /id="settings-save"[^>]*>Save changes</);
  assert.match(html, /id="settings-done"[^>]*>Done</);
  for (const id of [
    "settings-xai-key",
    "settings-interpreter",
    "settings-concept-model",
    "settings-video-model",
    "settings-library-root",
    "settings-choose-library",
    "settings-reveal-library",
    "settings-candidate-count",
    "settings-loop-mode",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(js, /api\("\/api\/settings\/preferences"/);
  assert.match(js, /api\("\/api\/settings\/library"/);
  assert.match(js, /api\("\/api\/settings\/key"/);
  assert.match(js, /choose_library_folder/);
  assert.match(js, /reveal_library_path/);
  assert.match(js, /api\("\/api\/native\/choose-library"/);
  assert.match(js, /api\("\/api\/native\/reveal-library"/);
  assert.match(js, /settingsReturnRoute/);
  assert.match(js, /\$\("#settings-done"\).*saveSettings\(\{exit:true\}\)/);
  assert.match(js, /function finishSettings[\s\S]*navigateTo\(route/);
  assert.doesNotMatch(html, /id="settings-renderer"/);
});

test("a restored Settings route refreshes after persisted settings load", () => {
  const refresh = js.match(/function refreshAiGate\s*\(\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(refresh, /ROUTES\.SETTINGS/);
  assert.match(refresh, /populateSettings\(\)/);
});

test("shell supports narrow windows, zoom, focus, and reduced motion", () => {
  assert.doesNotMatch(css, /min-width:\s*880px/);
  assert.match(css, /textarea:focus-visible/);
  assert.match(css, /@media\s*\(max-width:\s*720px\)/);
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.doesNotMatch(css, /\.create-steps/);
});

test("the Lighting editor exposes named keyboard-operable controls", () => {
  assert.match(js, /id="play-led"[^>]*aria-label="\$\{state\.playing\?'Stop animation':'Play animation'\}"/);
  assert.match(js, /class="frame-item[^`]*aria-pressed="\$\{i===state\.ledFrame\}"/);
  assert.match(js, /class="pixel[^`]*tabindex="\$\{/);
  assert.match(js, /aria-label="[^"`]*LED \$\{/);
  assert.match(js, /role="grid"[^>]*aria-label="LED paint grid"/);
  assert.match(js, /for="led-color"/);
  assert.match(js, /for="brightness"/);
  assert.match(js, /for="speed"/);
  assert.match(js, /nextGridIndex\(/);
  assert.match(js, /event\.key===['"] ['"]\|\|event\.key===['"]Enter['"]/);
  assert.match(js, /focusSelectedFrame\(/);
  assert.match(js, /focusSelectedTarget\(/);
});

test("responsive Lighting layout keeps canvas first and turns frames into a filmstrip", () => {
  const medium = css.match(/@media\s*\(max-width:\s*1240px\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(medium, /grid-template-areas:\s*"canvas controls"\s*"frames frames"/);
  assert.match(medium, /grid-auto-flow:\s*column/);
  assert.match(medium, /overflow-x:\s*auto/);
  const narrow = css.match(/@media\s*\(max-width:\s*980px\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(narrow, /grid-template-areas:\s*"canvas"\s*"frames"\s*"controls"/);
  const mobile = css.match(/@media\s*\(max-width:\s*720px\)\s*\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(mobile, /#device-button\s*\{\s*order:\s*-2/);
  assert.doesNotMatch(css, /--muted-2:\s*#6f6f78/);
});
