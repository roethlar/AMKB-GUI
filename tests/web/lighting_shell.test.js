"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {
  projectVialLedLayout,
} = require("../../am_configurator/web/lighting_targets.js");

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
  const composerScript=html.indexOf('<script src="/lighting_composer.js"></script>');
  const libraryStateScript=html.indexOf('<script src="/library_state.js"></script>');
  const appScript=html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript>=0&&stateScript<reviewScript&&reviewScript<targetsScript&&targetsScript<composerScript&&composerScript<libraryStateScript&&libraryStateScript<appScript);
  assert.match(server,/"\/lighting_state\.js":\s*"lighting_state\.js"/);
  assert.match(server,/"\/lighting_review\.js":\s*"lighting_review\.js"/);
  assert.match(server,/"\/lighting_targets\.js":\s*"lighting_targets\.js"/);
  assert.match(server,/"\/lighting_composer\.js":\s*"lighting_composer\.js"/);
  assert.match(server,/"\/library_state\.js":\s*"library_state\.js"/);
});

test("Studio is one Paint, Source, and Animate shell with local draft acceptance", () => {
  for(const id of [
    "studio-paint-tab","studio-source-tab","studio-animate-tab",
    "studio-paint-panel","studio-source-panel","studio-animate-panel",
    "animate-effect","animate-frame-count","animate-preview",
    "animate-accept","animate-cancel",
  ])assert.match(js,new RegExp(`id="${id}"`));
  assert.match(js,/role="tablist" aria-label="Studio tools"/);
  assert.match(js,/data-studio-tool="paint"/);
  assert.match(js,/data-studio-tool="source"/);
  assert.match(js,/data-studio-tool="animate"/);
  assert.match(js,/function previewLocalAnimation\(\)/);
  assert.match(js,/function applyLocalAnimationDraft\(\)/);
  const applyStart=js.indexOf("function applyLocalAnimationDraft");
  const applyEnd=js.indexOf("function ",applyStart+10);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  assert.match(js,/renderColorEffect\(/);
  assert.match(css,/\.studio-tool-tabs/);
  assert.match(css,/\.media-compositor-stage/);
  assert.match(css,/\.animation-draft-controls/);
});

test("media import banks before composition and applies only an accepted preview", () => {
  // WKWebView owns HTML file inputs and can leave valid GIF/PNG/BMP files
  // disabled when an accept filter is present. The bounded import endpoint
  // remains the authority for supported media after selection.
  const mediaInput=js.match(/<input id="media-input"[^>]*>/)?.[0]||"";
  assert.match(mediaInput,/type="file"/);
  assert.match(mediaInput,/\shidden(?:\s|>)/);
  assert.doesNotMatch(mediaInput,/\saccept=/);
  assert.match(js,/async function importMedia\(input\)/);
  assert.match(js,/\/api\/library\/import\/media\?name=/);
  assert.match(js,/function renderMediaCompositionPreview\(\)/);
  assert.match(js,/\/render`,\{method:"POST"/);
  assert.match(js,/function applyMediaCompositionDraft\(\)/);
  const applyStart=js.indexOf("function applyMediaCompositionDraft");
  const applyEnd=js.indexOf("function ",applyStart+10);
  assert.equal((js.slice(applyStart,applyEnd).match(/mutate\(/g)||[]).length,1);
  assert.match(js,/nextMediaRenderEpoch\(state\.mediaRenderEpoch\)/);
  assert.match(js,/const timelineFrames=mediaPreviewFrames\.length\?mediaPreviewFrames:documentFrames/);
  assert.match(js,/function activeMediaPreviewTrack\(\)/);
  assert.match(js,/function cancelMediaComposition\(\)/);
  assert.match(js,/id="media-compose-apply"/);
  assert.match(js,/id="media-compose-cancel"/);
  assert.match(js,/id="source-height"/);
  assert.match(js,/id="source-height-value"/);
  const heightStart=js.indexOf('$("#source-height")?.addEventListener');
  assert.ok(heightStart>=0);
  const heightEnd=js.indexOf("\n  });",heightStart);
  const heightHandler=js.slice(heightStart,heightEnd);
  assert.match(heightHandler,/scale_y:target/);
  assert.match(heightHandler,/aspect_locked:false/);
  const transformViewStart=js.indexOf("function updateSourceTransformView");
  const transformViewEnd=js.indexOf("\nfunction ",transformViewStart+10);
  const transformView=js.slice(transformViewStart,transformViewEnd);
  assert.match(transformView,/mediaCompositionStatusText/);
  assert.match(transformView,/media-compose-apply/);
  assert.match(transformView,/mediaDraftCanApply/);
  assert.match(js,/id="save-lighting-library"/);
  assert.match(js,/\/api\/library\/save\/lighting/);
  assert.match(js,/lightingProvenanceForPage\(/);
  assert.match(js,/page\.lightness=Number\(destination\.lightness\)/);
  assert.match(js,/data-library-open-source/);
  assert.match(js,/data-library-apply-lighting/);
});

test("lighting color style interpolation uses only canonical RGB", () => {
  assert.match(js,/normalizeImportedLightingColors\(normalizeImportedAssignmentCodes\(parsed\)\)/);
  assert.match(js,/background:\$\{safeRgbColor\(color\)\}/);
  assert.doesNotMatch(js,/background:\$\{esc\(color\)\}/);
  assert.match(js,/pixel\.style\.background=safeRgbColor\(color\)/);
  assert.match(js,/setProperty\('--pixel-color',safeRgbColor\(color\)\)/);
});

test("persistent job strip remains available outside routed content", () => {
  const strip=html.indexOf('id="lighting-job-host"');
  const routeContent=html.indexOf('id="route-content"');
  assert.ok(strip>=0&&strip<routeContent);
  assert.doesNotMatch(html,/id="lighting-job-strip"|Lighting job|lighting-job-view/);
  assert.match(js,/id="lighting-job-phase-live"[^>]*aria-live="polite"/);
  assert.match(js,/\$\("#lighting-job-view",host\)\.addEventListener\("click",revealGenerationStudio\)/);
  assert.match(js,/if \(!job \|\| !aiReady\(\)\) \{\s*host\.replaceChildren\(\)/);
});

test("disabled first paint exposes no generation control outside Settings", () => {
  assert.doesNotMatch(html,/lighting-generate-open|lighting-generate-dialog/);
  const beforeSettings=html.slice(0,html.indexOf('id="settings-screen"'));
  assert.doesNotMatch(beforeSettings,/GGUF|xAI|API key|Optional AI|Generate lighting|Test &amp; enable/);
  assert.doesNotMatch(js,/data-library-create/);
  assert.match(js,/const generationTab=aiReady\(\)\?/);
  assert.match(js,/const generationPanel=aiReady\(\)\?/);
  assert.match(js,/id="lighting-generate-tool"/);
  assert.match(js,/function renderGenerationStudio\(\)/);
  assert.match(js,/return Boolean\(aiStudioAvailable\(state\.aiStatus\)\)/);
  assert.doesNotMatch(js,/ROUTES\.CREATE|openGenerationDialog|renderGenerationDialog/);
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
  assert.match(effect,/JSON\.stringify\(\{prompt,backend:state\.aiStatus\.backend,target:state\.ledTarget,document_revision:state\.documentRevision\}\)/);
  assert.doesNotMatch(effect,/model_path|model_id|frame_count|product_id:|source_transform|media/);
  assert.match(js,/api\("\/api\/document\/sync"/);
  const fileOpen=js.slice(js.indexOf("async function readFiles"),js.indexOf("function saveConfig",js.indexOf("async function readFiles")));
  assert.match(fileOpen,/await synchronizeOpenDocument\(\)/);
  const deviceRead=js.slice(js.indexOf("async function readDevice"),js.indexOf("async function writeDevice"));
  assert.match(deviceRead,/await synchronizeOpenDocument\(\)/);
  const restore=js.slice(js.indexOf("async function returnToConnectedWorkspace"),js.indexOf("function deviceSwitchesWorkspace"));
  assert.match(restore,/await synchronizeOpenDocument\(\)/);
});

test("one master switch owns and hides every AI setup control", () => {
  const toggle=html.match(/<input id="settings-ai-enabled"[^>]*>/)?.[0]||"";
  const details=html.match(/<div id="settings-ai-details"[^>]*>/)?.[0]||"";
  assert.match(toggle,/type="checkbox"/);
  assert.match(toggle,/role="switch"/);
  assert.match(toggle,/aria-controls="settings-ai-details"/);
  assert.match(details,/\shidden(?:\s|>)/);
  assert.ok(
    html.indexOf('id="settings-ai-enabled"')<
    html.indexOf('id="settings-ai-details"') &&
    html.indexOf('id="settings-ai-details"')<
    html.indexOf('id="settings-ai-local"')
  );
  assert.doesNotMatch(html,/Enable after setup passes|Test &amp; enable/);
  assert.match(html,/Test setup/);

  const populate=js.slice(js.indexOf("function populateSettings"),js.indexOf("async function refreshSettingsData"));
  assert.match(populate,/\$\("#settings-ai-details"\)\.hidden=!enabled/);
  const toggleAction=js.slice(js.indexOf("async function setAiEnabled"),js.indexOf("async function selectAiBackend"));
  assert.match(toggleAction,/api\("\/api\/settings\/ai"/);
  assert.match(toggleAction,/JSON\.stringify\(\{enabled,backend\}\)/);
  const backendAction=js.slice(js.indexOf("async function selectAiBackend"),js.indexOf("async function refreshLocalModels"));
  assert.doesNotMatch(backendAction,/enabled\s*:/);
  const setupAction=js.slice(js.indexOf("async function testAiBackend"),js.indexOf("async function saveApiCredential"));
  assert.doesNotMatch(setupAction,/enabled\s*:\s*false/);
  assert.match(js,/\$\("#settings-ai-enabled"\)\.addEventListener\("change",event=>void setAiEnabled\(event\.target\.checked\)\)/);
  assert.match(css,/\.settings-row input\[role="switch"\]\s*\{[^}]*appearance:\s*none[^}]*width:\s*44px[^}]*border-radius:\s*999px/);
  assert.match(css,/\.settings-row input\[role="switch"\]:checked\s*\{[^}]*background:\s*var\(--violet\)/);
  assert.match(css,/\.settings-row input\[role="switch"\]:checked::before\s*\{[^}]*translateX\(20px\)/);
});

test("About is the only normal application-version surface", () => {
  assert.match(html,/id="about-button"[^>]*>About<\/button>/);
  assert.match(html,/id="about-dialog"[\s\S]*Version __AM_VERSION__[\s\S]*<\/dialog>/);
  assert.doesNotMatch(html,/id="app-version"|class="app-version"/);
  assert.match(css,/\.about-link\s*\{[^}]*background:\s*transparent[^}]*font-size:\s*13px/);
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
  assert.match(html,/id="settings-api-disclosure-detail"/);
  assert.match(html,/API use may cost money/);
  assert.match(js,/projectApiProviderPicker\(/);
  assert.match(js,/async function selectApiProvider/);
  assert.match(js,/async function selectApiModel/);
  assert.match(js,/provider:selection\.providerId,model_id:selection\.modelId/);
  assert.doesNotMatch(js,/provider:"xai"|model_id:"grok-4\.5"/);
  const generation=js.slice(js.indexOf("async function startProceduralGeneration"),js.indexOf("function applyReviewedLighting",js.indexOf("async function startProceduralGeneration")));
  assert.doesNotMatch(generation,/settings-api|credential|privacy|disclosure|provider|model_id/);
});

test("saving Settings persists intent without client-side readiness forgery", () => {
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
  assert.match(js,/function renderGenerationStudio\(\)/);
  assert.match(js,/saved failure does not disable this backend/);
  assert.match(js,/syncLightingJob\(null,\{renderPage:false\}\)/);
  assert.match(js,/type:"APPLY_REQUESTED"/);
  const applyStart=js.lastIndexOf("function applyReviewedLighting");
  const applyEnd=js.indexOf("async function loadAiConfig",applyStart);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  assert.match(apply,/keyboard has not been written/);
});

test("inline generation tool omits backend identity and keeps the exact target destination", () => {
  const prompt=js.slice(js.indexOf("function renderPromptStage"),js.indexOf("function renderProgressStage"));
  assert.doesNotMatch(prompt,/state\.aiStatus\?\.backend/);
  assert.doesNotMatch(prompt,/===\s*"api"\s*\?\s*"API"\s*:\s*"Local"/);
  assert.match(prompt,/Custom \$\{destinationSlot-4\} · \$\{esc\(targetLabel\)\}/);
  const settings=html.slice(html.indexOf('id="settings-screen"'));
  assert.match(settings,/settings-ai-local/);
  assert.match(settings,/settings-ai-api/);
  assert.match(js,/manifest\?\.costs\?\.actual_incomplete/);
});

test("generation is inline with no detached dialog or Create route", () => {
  assert.doesNotMatch(html,/lighting-generate-dialog|lighting-generate-open/);
  assert.doesNotMatch(js,/openRenderedDialog|handleGenerationDialogClose|ROUTES\.CREATE/);
  assert.doesNotMatch(review,/openRenderedDialog|generation dialog/i);
  assert.match(js,/You can switch to Library while the result continues banking locally/);
  assert.match(js,/function revealGenerationStudio\(\)/);
  assert.match(js,/navigateTo\(ROUTES\.EDIT/);
  assert.match(js,/scrollIntoView/);
});

test("Library remains document-independent and browses every saved kind", () => {
  for(const id of ["lighting-library-toolbar","library-profile-input","library-add-files","library-search","library-refresh","library-reveal","library-status","library-notice","library-page-previous","library-page-label","library-page-next","library-content"]){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  for(const filter of ["all","sources","lighting","keymaps","removed"]){
    assert.match(html,new RegExp(`data-library-filter="${filter}"`));
  }
  assert.doesNotMatch(html,/data-library-filter="generated"/);
  assert.doesNotMatch(html,/data-library-filter="partial"/);
  assert.match(js,/libraryCatalogQuery/);
  assert.match(js,/"preview_animation","raster_animation","source_video"/);
  assert.match(js,/api\(`\/api\/library\/items\?/);
  assert.match(js,/fetch\(`\/api\/library\/assets\//);
  assert.match(js,/"X-AM-Token":token/);
  assert.match(js,/URL\.createObjectURL/);
  assert.match(js,/URL\.revokeObjectURL/);
  assert.doesNotMatch(js,/data-library-animate-job=/);
});

test("profile banking is explicit, exact-source, and applies selected compatible sections", () => {
  assert.match(html,/id="library-profile-input"[^>]*accept="application\/json,.json"[^>]*multiple/);
  assert.match(html,/id="library-add-files"[^>]*>Add files…</);
  assert.match(js,/async function importLibraryProfiles\(/);
  const importFlow=js.slice(
    js.indexOf("async function importLibraryProfiles"),
    js.indexOf("async function saveMappingToLibrary"),
  );
  assert.match(importFlow,/state\.library\.filter="keymaps"/);
  assert.doesNotMatch(importFlow,/state\.library\.filter="profiles"/);
  assert.match(js,/file\.arrayBuffer\(\)/);
  assert.match(js,/\/api\/library\/import\/profile/);
  assert.match(js,/async function saveMappingToLibrary\(/);
  assert.match(js,/\/api\/library\/save\/profile/);
  assert.match(js,/id="save-mapping-library"/);
  assert.match(js,/\/compatibility`/);
  assert.match(js,/\/apply`/);
  assert.match(js,/async function applyLibraryProfile\(/);
  assert.match(js,/data-library-profile-section/);
  assert.match(js,/mutate\(\(\)=>\{\s*state\.config=clone\(result\.config\)/);
  for(const status of ["exact","convertible","portable","blocked"]){
    assert.match(js,new RegExp(`"${status}"`));
  }
  const openFlow=js.slice(js.indexOf("async function readFiles"),js.indexOf("function saveConfig"));
  assert.doesNotMatch(openFlow,/library\/import\/profile/);
});

test("Library removal is reversible and permanent deletion is confirmed", () => {
  for(const id of ["library-confirm-dialog","library-confirm-title","library-confirm-message","library-confirm-action"]){
    assert.match(html,new RegExp(`id="${id}"`));
  }
  assert.match(js,/async function removeLibraryItem\(/);
  assert.match(js,/async function undoLibraryRemoval\(/);
  assert.match(js,/async function restoreLibraryItem\(/);
  assert.match(js,/async function deleteLibraryItemForever\(/);
  assert.match(js,/suffix:"\/remove"/);
  assert.match(js,/suffix:"\/restore"/);
  assert.match(js,/method:"DELETE"/);
  assert.match(js,/data-library-remove/);
  assert.match(js,/data-library-undo-remove/);
  assert.match(js,/data-library-restore/);
  assert.match(js,/data-library-delete/);
  assert.match(js,/createLibraryRequestEpochs/);
  const confirmStart=js.indexOf('$("#library-confirm-action").addEventListener');
  assert.ok(confirmStart>=0);
  const confirmEnd=js.indexOf('\n$("#library-confirm-dialog")',confirmStart);
  const confirmHandler=js.slice(confirmStart,confirmEnd);
  assert.match(confirmHandler,/const button=event\.currentTarget/);
  assert.doesNotMatch(
    confirmHandler.slice(confirmHandler.indexOf("await action()")),
    /event\.currentTarget/,
  );
});

test("Library cards support arrow-key navigation and narrow pagination", () => {
  assert.match(js,/nextCatalogIndex/);
  assert.match(js,/gridTemplateColumns/);
  assert.match(js,/ArrowDown/);
  assert.match(css,/\.library-pagination/);
  assert.match(css,/@media \(max-width:\s*720px\)/);
  assert.match(css,/\.library-filters[^}]*overflow-x:\s*auto/);
});

test("Library media failures retry once and become actionable", () => {
  assert.match(js,/assetErrors:\s*new Map\(\)/);
  assert.match(js,/data-library-asset-retry=/);
  assert.match(js,/loadLibraryAsset\(catalogId,assetId,\{retry:true\}\)/);
});

test("Library asset loads revoke stale blobs and preserve refreshed ownership", () => {
  const loader=js.slice(js.indexOf("async function loadLibraryAsset"),js.indexOf("function profileTargetLayout"));
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
  const zoomed=css.match(/@media\s*\(max-width:\s*1120px\)\s*\{[\s\S]*?\n\}/)?.[0]||"";
  assert.match(medium,/grid-template-areas:\s*"canvas controls"\s*"frames frames"/);
  assert.match(medium,/overflow-x:\s*auto/);
  assert.match(zoomed,/\.topbar\s*\{[^}]*grid-template-columns:\s*1fr auto/);
  assert.match(zoomed,/\.top-actions\s*\{[^}]*overflow-x:\s*auto/);
});

test("narrow Keymap releases the desktop keyboard minimum without page clipping", () => {
  const mediumStart=css.indexOf("@media (max-width: 1240px)");
  const medium=css.slice(mediumStart,css.indexOf("@media (max-width: 1120px)",mediumStart));
  assert.match(medium,/\.editor-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(medium,/\.editor-grid\s*>\s*\*\s*\{[^}]*min-width:\s*0/);
  const stackedStart=css.indexOf("@media (max-width: 1120px)");
  const stacked=css.slice(stackedStart,css.indexOf("@media (max-width: 980px)",stackedStart));
  assert.match(stacked,/\.keyboard-stage\s*\{[^}]*min-height:\s*0/);
});

test("Relic per-key lighting uses the sized Keymap geometry and segments its spacebar LEDs", () => {
  assert.match(
    js,
    /const RELIC_LED_LAYOUT=projectVialLedLayout\([\s\S]*width:17,height:6,count:89,map:RELIC_LED_MAP/,
  );
  assert.match(
    js,
    /"80":\s*\{[\s\S]*physicalLayout:RELIC_LED_LAYOUT/,
  );
  assert.match(
    js,
    /const segmentDescription=grouped\?`, segment \$\{item\.groupPosition\+1\} of \$\{item\.groupCount\}`:""/,
  );
  assert.match(js,/data-pixel-description="\$\{esc\(description\+segmentDescription\)\}"/);
  const paintHandler=js.slice(
    js.indexOf("const paint = pixel =>"),
    js.indexOf("const strokeController=",js.indexOf("const paint = pixel =>")),
  );
  assert.match(paintHandler,/pixel\.dataset\.pixelDescription/);
  const constants=js.slice(
    js.indexOf("const RELIC_LAYOUT"),
    js.indexOf("const LED_MODELS"),
  );
  const context={projectVialLedLayout};
  vm.runInNewContext(`${constants}\nglobalThis.result=RELIC_LED_LAYOUT;`,context);
  assert.equal(context.result.length,89);
  assert.deepEqual(
    context.result.filter(item=>item.keyIndex===128).map(
      item=>[item.index,item.groupPosition,item.groupCount,item.showLabel],
    ),
    [[78,0,3,false],[79,1,3,true],[80,2,3,false]],
  );
});

test("Neon keymap wiring uses the validated layout and assignment gate", () => {
  const layout = js.slice(js.indexOf("function activeLayout"), js.indexOf("function keyClass"));
  const palette = js.slice(js.indexOf("function renderAssignmentPalette"), js.indexOf("function activeLayout"));
  const assign = js.slice(js.indexOf("async function assignSelected"), js.indexOf("function wireKeyInspector"));
  const scan = js.slice(js.indexOf("async function scanDevices"), js.indexOf("async function readDevice"));
  const read = js.slice(js.indexOf("async function readDevice"), js.indexOf("async function writeDevice"));
  const neonLayout = layout.slice(layout.indexOf('if (family === "NEON")'), layout.indexOf("const layer"));
  assert.match(palette, /NEON_LIGHTING_CONTROLS/);
  assert.match(palette, /neonLightingGroups/);

  assert.match(js, /function displayGeometryDevice\(\)[\s\S]*selectVialLayoutDevice\(productId\(\),state\.devices,state\.loadedDevice\)/);
  assert.match(layout, /family === "NEON"[\s\S]*displayGeometryDevice\(\)[\s\S]*projectVialKeyLayout\(device\)/);
  assert.match(js, /const device=displayGeometryDevice\(\);[\s\S]*state\.ledTarget==="axial"[\s\S]*projectVialLedLayout\(device,servedTarget\)/);
  assert.match(js, /const neonAxial=productFamily\(productId\(\)\)==="NEON"&&state\.ledTarget==="axial"/);
  assert.match(js, /if\(neonAxial&&!physicalLayout\)[\s\S]*geometryUnavailableNotice/);
  assert.match(scan, /const priorDisplayGeometry=projectVialKeyLayout\(displayGeometryDevice\(\)\)/);
  assert.match(scan, /const nextDisplayGeometry=projectVialKeyLayout\(displayGeometryDevice\(\)\)/);
  assert.match(scan, /JSON\.stringify\(priorDisplayGeometry\)!==JSON\.stringify\(nextDisplayGeometry\)[\s\S]*renderScreen\(\)/);
  assert.match(css, /\.physical-pixel\.multi-led[\s\S]*\.group-first[\s\S]*\.group-last/);
  assert.doesNotMatch(neonLayout, /Matrix layout|Math\.floor\(index \/ 25\)/);
  assert.match(palette, /filterAssignmentOptions\(product/);
  assert.match(assign, /api\("\/api\/keymap\/assignment"/);
  assert.match(assign, /catch\(error\)[\s\S]*return;/);
  assert.match(assign, /const assignmentEpoch=\+\+state\.keyAssignmentEpoch/);
  assert.match(assign, /state\.keyAssignmentEpoch!==assignmentEpoch[\s\S]*state\.selected!==selected[\s\S]*state\.layer!==layerIndex[\s\S]*productId\(\)!==product/);
  assert.match(read, /state\.devices=state\.devices\.map[\s\S]*result\.device/);
});

test("connected Neon macro capacity owns the editor meter and mutation gates", () => {
  const active=js.slice(js.indexOf("function activeFamilySpec"),js.indexOf("function sameProductFamily"));
  const macros=js.slice(js.indexOf("function macroCapacity"),js.indexOf("function getPage"));

  assert.match(active,/state\.loadedDevice/);
  assert.match(active,/withDeviceMacroLimits/);
  assert.match(macros,/macroCapacityStatus\(activeFamilySpec\(\),candidate\)/);
  assert.match(macros,/capacity\.used[\s\S]*capacity\.limit[\s\S]*capacity\.unit/);
  assert.match(macros,/applyImportedMacros[\s\S]*macroCapacityError\(incoming\)/);
  assert.match(macros,/applyMacroText[\s\S]*macroCapacityError\(candidate\)/);
  assert.match(macros,/add-event[\s\S]*macroCapacityError\(candidate\)/);
  assert.match(macros,/recordEvent[\s\S]*macroCapacityError\(candidate\)/);
  assert.match(server,/macro_state\.device_macro_count/);
  assert.match(server,/"macro_buffer_bytes": macro_state\.device_macro_buffer_bytes/);
  const scan=js.slice(js.indexOf("async function scanDevices"),js.indexOf("async function readDevice"));
  assert.match(scan,/known\?\.macro_count[\s\S]*known\?\.macro_buffer_bytes[\s\S]*macro_count:known\.macro_count[\s\S]*macro_buffer_bytes:known\.macro_buffer_bytes/);
});
