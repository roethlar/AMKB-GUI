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
const workspace = fs.readFileSync(path.join(root, "am_configurator/web/lighting_workspace.js"), "utf8");
const review = fs.readFileSync(path.join(root, "am_configurator/web/lighting_review.js"), "utf8");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const server = fs.readFileSync(path.join(root, "am_configurator/server.py"), "utf8");

test("pure lighting state loads before the application adapter", () => {
  const stateScript=html.indexOf('<script src="/lighting_state.js"></script>');
  const workspaceScript=html.indexOf('<script src="/lighting_workspace.js"></script>');
  const reviewScript=html.indexOf('<script src="/lighting_review.js"></script>');
  const targetsScript=html.indexOf('<script src="/lighting_targets.js"></script>');
  const composerScript=html.indexOf('<script src="/lighting_composer.js"></script>');
  const libraryStateScript=html.indexOf('<script src="/library_state.js"></script>');
  const appScript=html.indexOf('<script src="/app.js"></script>');
  assert.ok(stateScript>=0&&stateScript<workspaceScript&&workspaceScript<reviewScript&&reviewScript<targetsScript&&targetsScript<composerScript&&composerScript<libraryStateScript&&libraryStateScript<appScript);
  assert.match(server,/"\/lighting_state\.js":\s*"lighting_state\.js"/);
  assert.match(server,/"\/lighting_workspace\.js":\s*"lighting_workspace\.js"/);
  assert.match(server,/"\/lighting_review\.js":\s*"lighting_review\.js"/);
  assert.match(server,/"\/lighting_targets\.js":\s*"lighting_targets\.js"/);
  assert.match(server,/"\/lighting_composer\.js":\s*"lighting_composer\.js"/);
  assert.match(server,/"\/library_state\.js":\s*"library_state\.js"/);
});

test("workspace reducer is the only destination and playback authority", () => {
  const stateStart=js.indexOf("const state = {");
  const stateEnd=js.indexOf("\n};",stateStart);
  const legacyState=js.slice(stateStart,stateEnd);
  for(const field of ["ledSlot","ledTarget","ledFrame","studioTool","playing","playTimer"]){
    assert.doesNotMatch(legacyState,new RegExp(`\\b${field}\\s*:`),`${field} must not remain reducer-adjacent state`);
  }
  assert.match(js,/Object\.defineProperties\(state,/);
  assert.match(js,/type: "DESTINATION_CHANGED"/);
  assert.match(js,/type: "PLAYHEAD_SCRUBBED"/);
  assert.match(js,/type: "TOOL_SELECTED"/);
  assert.doesNotMatch(js,/state\.playTimer/);
  assert.doesNotMatch(js,/lightingPlaybackTimer/);
  assert.match(js,/createLightingPlaybackRuntime/);
  assert.match(js,/paintBoardProjection/);
  assert.match(js,/workspaceDestinationKey/);

  const playbackStart=js.indexOf("function startPlayback");
  const playbackEnd=js.indexOf("function toggleLightingPlayback",playbackStart);
  const playback=js.slice(playbackStart,playbackEnd);
  assert.match(playback,/selectBoardProjection\(lightingWorkspace\)/);
  assert.match(playback,/type: "PLAY_REQUESTED"/);
  assert.doesNotMatch(playback,/trackInfo|activeMediaPreviewTrack|frames\s*=/);

  const executorStart=js.indexOf("function executeLightingWorkspaceIntents");
  const executorEnd=js.indexOf("function dispatchLightingWorkspace",executorStart);
  const executor=js.slice(executorStart,executorEnd);
  assert.match(executor,/lightingPlaybackRuntime\.execute\(intent\)/);
  assert.doesNotMatch(executor,/setInterval|clearInterval|PLAYBACK_TICK/);
  assert.doesNotMatch(executor,/frame_RGB|\.frames/);

  const renderStart=js.indexOf("function renderLightingEdit");
  const renderEnd=js.indexOf("function focusSelectedFrame",renderStart);
  const edit=js.slice(renderStart,renderEnd);
  assert.match(edit,/currentLightingBoardFrameSet/);
  assert.match(edit,/publishLightingBoardFrameSet/);
  assert.match(edit,/boardProjection\.colors/);
  assert.match(js,/type:"BOARD_COLOR_UPDATED"/);
});

test("media and source-projection transitions are bound to the reducer session", () => {
  const openLibraryStart=js.indexOf("function openLibrarySource");
  const openLibraryEnd=js.indexOf("\nfunction ",openLibraryStart+10);
  const openLibrary=js.slice(openLibraryStart,openLibraryEnd);
  assert.match(openLibrary,/type:\s*"MEDIA_OPENED"/);

  const importStart=js.indexOf("async function importMedia");
  const importEnd=js.indexOf("\nasync function ",importStart+10);
  const importMedia=js.slice(importStart,importEnd);
  assert.match(importMedia,/adoptImportedMedia\(/);
  const adoptStart=js.indexOf("async function adoptImportedMedia");
  const adoptEnd=js.indexOf("\nasync function ",adoptStart+10);
  const adopt=js.slice(adoptStart,adoptEnd);
  assert.match(adopt,/type:\s*"MEDIA_OPENED"/);

  const cancelStart=js.indexOf("function cancelMediaComposition");
  const cancelEnd=js.indexOf("\nfunction ",cancelStart+10);
  const cancel=js.slice(cancelStart,cancelEnd);
  assert.match(cancel,/type:\s*"MEDIA_CANCELLED"/);

  const loadStart=js.indexOf("function loadSourceProjection");
  const loadEnd=js.indexOf("\nfunction loadLightingSourceProjection",loadStart+10);
  const load=js.slice(loadStart,loadEnd);
  assert.match(load,/captureWorkspaceAsyncContext\(lightingWorkspace\)/);
  assert.match(js,/workspaceAsyncContextMatches\(lightingWorkspace,load\)/);
  assert.match(load,/sourceProjectionLoadMatchesWorkspace/);
  assert.match(load,/sourceProjectionLoadMatchesWorkspace\(existing\.load\)/);
  assert.match(load,/existing\.controller\.abort\(\)/);
  assert.match(load,/const record=\{controller,load,promise:null\}/);
  assert.ok(
    load.indexOf("sourceProjectionLoadMatchesWorkspace") < load.indexOf("renderLightingSourceProjection()"),
    "a stale source load must be rejected before touching the current DOM",
  );
});

test("expired preview sessions invalidate their exact id and retry one render", () => {
  assert.match(js,/MEDIA_PREVIEW_SESSION_UNAVAILABLE/);
  const invalidationStart=js.indexOf("function invalidateMediaPreviewSession");
  const invalidationEnd=js.indexOf("\nfunction ",invalidationStart+10);
  const invalidation=js.slice(invalidationStart,invalidationEnd);
  assert.match(invalidation,/type:"MEDIA_SESSION_INVALIDATED"/);
  assert.match(invalidation,/preview_session_id:previewSessionId/);

  const renderStart=js.indexOf("async function renderMediaCompositionPreviewAttempt");
  const renderEnd=js.indexOf("\nfunction ",renderStart+10);
  const renderAttempt=js.slice(renderStart,renderEnd);
  assert.match(renderAttempt,/allowSessionRecovery&&mediaPreviewSessionUnavailable\(error\)/);
  assert.match(renderAttempt,/invalidateMediaPreviewSession\(/);
  assert.match(renderAttempt,/return renderMediaCompositionPreviewAttempt\(request,false\)/);

  const sourceStart=js.indexOf("function loadSourceProjection");
  const sourceEnd=js.indexOf("\nfunction loadLightingSourceProjection",sourceStart+10);
  const sourceLoad=js.slice(sourceStart,sourceEnd);
  assert.match(sourceLoad,/mediaPreviewSessionUnavailable\(error\)/);
  assert.match(sourceLoad,/invalidateMediaPreviewSession\(/);
});

test("queued media renders surrender Source ownership before shared preview mutation", () => {
  const dispatchStart=js.indexOf("function dispatchLightingWorkspace");
  const dispatchEnd=js.indexOf("\nfunction ",dispatchStart+10);
  const dispatch=js.slice(dispatchStart,dispatchEnd);
  assert.match(dispatch,/mediaOwnedBefore/);
  assert.match(dispatch,/mediaCompositionRenderScheduler\.cancel\(\)/);
  assert.ok(
    dispatch.indexOf("mediaCompositionRenderScheduler.cancel()")
      < dispatch.indexOf("executeLightingWorkspaceIntents"),
    "pending media work must be cancelled before transition intents execute",
  );

  const scheduleStart=js.indexOf("function scheduleMediaCompositionPreview");
  const scheduleEnd=js.indexOf("\nfunction ",scheduleStart+10);
  const schedule=js.slice(scheduleStart,scheduleEnd);
  assert.match(schedule,/ownership:\s*\{/);
  assert.match(schedule,/captureWorkspaceAsyncContext\(lightingWorkspace\)/);
  assert.match(schedule,/lightingMediaIdentity\(draft\)/);

  const renderStart=js.indexOf("async function renderMediaCompositionPreviewAttempt");
  const renderEnd=js.indexOf("\nfunction ",renderStart+10);
  const render=js.slice(renderStart,renderEnd);
  const ownershipCheck=render.indexOf("mediaLoadMatchesWorkspace(request?.ownership)");
  const renderStarted=render.indexOf('type:"SEQUENCE_RENDER_STARTED"');
  assert.ok(ownershipCheck>=0, "queued render ownership must be checked");
  assert.match(render,/lightingWorkspace\.media\?\.requested_revision!==request\?\.revision/);
  assert.ok(
    ownershipCheck<renderStarted,
    "stale queued work must be rejected before SEQUENCE_RENDER_STARTED",
  );
  assert.match(render,/const requestAsyncContext=request\.ownership/);
});

test("interactive framing publishes one exact selected frame before the full sequence", () => {
  const frameSchedulerStart=js.indexOf("const mediaCompositionFrameScheduler");
  const sequenceSchedulerStart=js.indexOf("const mediaCompositionRenderScheduler");
  assert.ok(frameSchedulerStart>=0, "the selected-frame scheduler must exist");
  assert.ok(sequenceSchedulerStart>=0, "the full-sequence scheduler must remain");
  const frameScheduler=js.slice(frameSchedulerStart,sequenceSchedulerStart);
  assert.match(frameScheduler,/delayMs:0/);
  assert.match(frameScheduler,/renderMediaCompositionFrameAttempt/);

  const dispatchStart=js.indexOf("function dispatchLightingWorkspace");
  const dispatchEnd=js.indexOf("\nfunction ",dispatchStart+10);
  const dispatch=js.slice(dispatchStart,dispatchEnd);
  assert.match(dispatch,/mediaCompositionFrameScheduler\.cancel\(\)/);
  assert.match(dispatch,/mediaCompositionRenderScheduler\.cancel\(\)/);
  assert.ok(
    dispatch.indexOf("mediaCompositionFrameScheduler.cancel()")
      <dispatch.indexOf("executeLightingWorkspaceIntents"),
    "pending selected-frame work must be cancelled before transition intents",
  );

  const requestStart=js.indexOf("function requestMediaCompositionRender");
  const requestEnd=js.indexOf("\nfunction ",requestStart+10);
  const request=js.slice(requestStart,requestEnd);
  assert.match(request,/scheduleMediaCompositionFrame\(\)/);
  assert.doesNotMatch(request,/scheduleMediaCompositionPreview\(\)/);

  const scheduleStart=js.indexOf("function scheduleMediaCompositionFrame");
  const scheduleEnd=js.indexOf("\nfunction ",scheduleStart+10);
  const schedule=js.slice(scheduleStart,scheduleEnd);
  assert.match(schedule,/const frameIndex=mediaCompositionFrameIndex\(draft\)/);
  assert.match(schedule,/type:"PLAYHEAD_SCRUBBED",index:frameIndex/);
  assert.match(schedule,/frameIndex,/);
  assert.match(schedule,/mediaCompositionRenderScheduler\.cancel\(\)/);
  assert.match(schedule,/mediaCompositionFrameScheduler\.request\(request\)/);

  const attemptStart=js.indexOf("async function renderMediaCompositionFrameAttempt");
  const attemptEnd=js.indexOf("\nfunction ",attemptStart+10);
  const attempt=js.slice(attemptStart,attemptEnd);
  assert.match(attempt,/\/render-frame`/);
  assert.match(attempt,/frame_index:request\.frameIndex/);
  assert.match(attempt,/boardFrameSetFromMappedFrame\(/);
  assert.match(attempt,/type:"FRAME_RENDER_STARTED"/);
  assert.match(attempt,/type:"FRAME_RENDER_ACCEPTED"/);
  assert.match(attempt,/type:"FRAME_RENDER_SUCCEEDED"/);
  assert.match(attempt,/scheduleMediaCompositionPreview\(\)/);
  assert.ok(
    attempt.indexOf("mediaLoadMatchesWorkspace(request?.ownership)")
      <attempt.indexOf('type:"FRAME_RENDER_STARTED"'),
    "stale selected-frame work must stop before shared preview mutation",
  );
  assert.ok(
    attempt.indexOf("lightingWorkspace.playhead.index!==request?.frameIndex")
      <attempt.indexOf("/render-frame`"),
    "a stale scrubbed frame must stop before the selected-frame request",
  );
  assert.ok(
    attempt.indexOf("if(accepted.ignored)return")
      <attempt.indexOf("scheduleMediaCompositionPreview()"),
    "only an accepted latest selected frame may schedule the full sequence",
  );

  const flushStart=js.indexOf("async function renderMediaCompositionPreview");
  const flushEnd=js.indexOf("\nasync function renderMediaCompositionFrameAttempt",flushStart+10);
  const flush=js.slice(flushStart,flushEnd);
  assert.ok(
    flush.indexOf("await mediaCompositionFrameScheduler.flush()")
      <flush.indexOf("mediaCompositionRenderScheduler.flush()"),
    "explicit Preview must finish the selected frame before awaiting the sequence",
  );
  const scrubStart=js.indexOf("const scrubTimeline=index=>");
  const scrubEnd=js.indexOf("\n  };",scrubStart+10);
  assert.match(
    js.slice(scrubStart,scrubEnd),
    /!mediaCompositionCanApply\(\)/,
    "an already exact full sequence must not launch a late frame that stops playback",
  );
});

// Slice P3 renamed the visible tool labels to Paint / Import media / Effects /
// AI while the internal tool keys and element ids stayed stable. This guard
// keeps owning the stable keys; the visible labels are owned by
// tests/web/lighting_flow.test.js.
test("Studio is one Paint, Import media, and Effects shell with local draft acceptance", () => {
  for(const id of [
    "studio-paint-tab","studio-source-tab","studio-animate-tab",
    "studio-paint-panel","studio-source-panel","studio-animate-panel",
    "animate-draft-status","animate-frame-count",
    "animate-accept","animate-cancel",
  ])assert.match(js,new RegExp(`id="${id}"`));
  assert.match(js,/role="tablist" aria-label="Studio tools"/);
  assert.match(js,/data-studio-tool="paint"/);
  assert.match(js,/data-studio-tool="source"/);
  assert.match(js,/data-studio-tool="animate"/);
  assert.match(js,/function regenerateLocalAnimationDraft\(/);
  assert.match(js,/function applyLocalAnimationDraft\(\)/);
  assert.doesNotMatch(js,/id="animate-preview"|state\.localAnimationDraft/);
  const cardsStart=js.indexOf("function animationEffectCardsMarkup");
  const cardsEnd=js.indexOf("function ",cardsStart+10);
  const cards=js.slice(cardsStart,cardsEnd);
  for(const effect of ["pulse","hue_cycle","sweep","shimmer","move_zoom"]){
    assert.match(cards,new RegExp(`\\["${effect}"`));
  }
  const applyStart=js.indexOf("function applyLocalEffectFrameSet");
  const applyEnd=js.indexOf("function ",applyStart+10);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  assert.match(apply,/frameSet\.frames_by_target\[context\.target\]/);
  assert.match(apply,/type:"APPLY_COMPLETED"/);
  assert.match(js,/renderColorEffect\(/);
  assert.match(css,/\.studio-tool-tabs/);
  assert.match(css,/\.media-compositor-stage/);
  assert.match(css,/\.effect-card-grid/);
  assert.match(css,/\.animation-draft-status/);
});

test("the stable Lighting shell keeps actual Source and canonical Board separate", () => {
  for(const id of [
    "lighting-edit-message","lighting-workspace-shell","lighting-preview-panes",
    "lighting-timeline","lighting-workspace-status","lighting-studio-inspector",
  ])assert.match(html,new RegExp(`id="${id}"`));
  const shell=html.slice(
    html.indexOf('id="lighting-edit-content"'),
    html.indexOf('id="lighting-library-panel"'),
  );
  assert.ok(shell.indexOf('id="lighting-preview-panes"')<shell.indexOf('id="lighting-timeline"'));
  assert.ok(shell.indexOf('id="lighting-timeline"')<shell.indexOf('id="lighting-studio-inspector"'));

  assert.match(js,/function commitSourceTransform\(reducer\)/);
  const commitStart=js.indexOf("function commitSourceTransform");
  const commitEnd=js.indexOf("function ",commitStart+10);
  const commit=js.slice(commitStart,commitEnd);
  assert.match(commit,/activateSourceTransformView\(\)/);
  assert.match(commit,/updateMediaCompositionTransform/);
  assert.ok(
    commit.indexOf("activateSourceTransformView()")
      <commit.indexOf("updateMediaCompositionTransform"),
    "source mode must become visible before the transform changes",
  );
  assert.match(js,/wireSourceTransformStage\(stage,/);
  const sourceStart=js.indexOf("const sourcePane=");
  const boardStart=js.indexOf("const boardPane=");
  const timelineStart=js.indexOf("const timelineMarkup=");
  assert.ok(sourceStart>=0&&sourceStart<boardStart&&boardStart<timelineStart);
  const sourceMarkup=js.slice(sourceStart,boardStart);
  const boardMarkup=js.slice(boardStart,timelineStart);
  assert.match(sourceMarkup,/id="lighting-source-pane"/);
  assert.match(sourceMarkup,/id="media-compositor-stage"/);
  assert.match(sourceMarkup,/class="media-source-viewport"/);
  assert.match(sourceMarkup,/class="source-frame-image"/);
  assert.match(boardMarkup,/id="lighting-board-pane"/);
  assert.match(boardMarkup,/id="led-canvas"/);
  assert.match(boardMarkup,/\$\{pixelCanvas\}/);
  assert.doesNotMatch(boardMarkup,/<img|source-frame-image|media-source-viewport|media-compositor-stage/);
  assert.match(js,/selectSourceProjection\(lightingWorkspace\)/);
  assert.match(js,/\/preview-session/);
  assert.match(js,/\/source-frame\?/);
  assert.match(js,/preview_session_id/);
  assert.match(js,/source_frame_index/);
  assert.match(js,/resolveSourceGeometry\(/);
  assert.match(js,/box\.left\/primary\.width/);
  assert.match(js,/box\.top\/primary\.height/);
  assert.match(js,/box\.rendered_width\/primary\.width/);
  assert.match(js,/box\.rendered_height\/primary\.height/);
  assert.match(css,/\.media-source-viewport \{[^}]*overflow: hidden/);
  assert.match(css,/\.source-frame-image \{[^}]*left: var\(--source-left\)[^}]*top: var\(--source-top\)[^}]*width: var\(--source-width\)[^}]*height: var\(--source-height\)/);
  assert.doesNotMatch(css,/\.source-frame-image \{[^}]*(?:object-fit: cover|opacity: \.\d+)/);
  assert.match(css,/\.media-compositor-stage\.dragging \{[^}]*cursor: grabbing/);
  assert.match(css,/\.media-compositor-stage:focus-visible/);
  assert.doesNotMatch(js,/sourcePreviewMode|data-source-preview/);
  assert.doesNotMatch(css,/source-preview-toggle|source-visible|\.media-compositor-stage\.source-visible/);
  assert.match(css,/@media \(prefers-reduced-motion: reduce\)/);
  assert.match(
    css,
    /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?transition: none !important;/,
  );
  assert.doesNotMatch(
    css,
    /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?transition-duration:/,
  );
});

test("one horizontal timeline owns playback, position, editing, and status", () => {
  for(const id of [
    "lighting-previous-frame","play-led","lighting-next-frame",
    "lighting-timeline-scrubber","lighting-frame-position","lighting-loop-status",
  ])assert.match(js,new RegExp(`id="${id}"`));
  assert.match(js,/class="lighting-timeline-frames"/);
  assert.match(js,/aria-label="Lighting timeline"/);
  assert.match(js,/aria-live="polite"/);
  assert.match(css,/\.lighting-timeline-frames \{[^}]*grid-auto-flow: column[^}]*overflow-x: auto/);
  assert.match(css,/\.lighting-playback-controls/);
  assert.doesNotMatch(css,/\.frame-list\s*\{/);
  assert.doesNotMatch(css,/\.led-layout\s*\{/);
});

test("media import banks before composition and applies only an accepted preview", () => {
  const mediaInput=js.match(/<input id="media-input"[^>]*>/)?.[0]||"";
  assert.match(mediaInput,/type="file"/);
  assert.match(mediaInput,/\shidden(?:\s|>)/);
  assert.match(mediaInput,/accept="\.gif,\.png,\.bmp,image\/gif,image\/png,image\/bmp"/);
  assert.match(js,/async function chooseMedia\(\)/);
  assert.match(js,/api\("\/api\/native\/choose-media"/);
  assert.match(js,/error\.status===404/);
  assert.match(js,/\$\("#media-input"\)\.click\(\)/);
  assert.match(js,/id="media-import-status"[^>]*aria-live="polite"/);
  assert.match(js,/async function importMedia\(input\)/);
  assert.match(js,/\/api\/library\/import\/media\?name=/);
  assert.match(js,/function renderMediaCompositionPreview\(\)/);
  assert.match(js,/createLatestTaskScheduler\(/);
  assert.match(js,/scheduleMediaCompositionPreview\(/);
  assert.match(js,/\/render`,\{method:"POST"/);
  assert.match(js,/function applyMediaCompositionDraft\(\)/);
  const applyStart=js.indexOf("function applyMediaCompositionDraft");
  const applyEnd=js.indexOf("function ",applyStart+10);
  assert.equal((js.slice(applyStart,applyEnd).match(/mutate\(/g)||[]).length,1);
  assert.match(js,/nextMediaRenderEpoch\(state\.mediaRenderEpoch\)/);
  assert.match(js,/boardFrameSetFromMappedResult\(/);
  assert.match(js,/type:"SEQUENCE_RENDER_ACCEPTED"/);
  const renderPreviewStart=js.indexOf("async function renderMediaCompositionPreview");
  const renderPreviewEnd=js.indexOf("\nfunction ",renderPreviewStart+10);
  const renderPreview=js.slice(renderPreviewStart,renderPreviewEnd);
  assert.match(renderPreview,/await ensureMediaPreviewSession\(draft\)/);
  assert.match(renderPreview,/preview_session_id:previewSessionId/);
  assert.match(renderPreview,/timeline:result\.preview_timeline/);
  assert.match(renderPreview,/type:"RENDER_DISCARDED"/);
  assert.ok(
    renderPreview.indexOf("mediaLoadMatchesWorkspace(requestAsyncContext)")
      < renderPreview.indexOf("/render`"),
    "a stale session acquisition must stop before a full media render",
  );
  assert.match(
    renderPreview,
    /if\(renderAccepted&&requiresWorkspaceRebuild\)renderLightingEdit\(\)/,
    "only the first media frame set may rebuild the workspace",
  );
  assert.equal(
    (renderPreview.match(/renderLightingEdit\(\)/g)||[]).length,
    1,
    "live media revisions must preserve the active transform surface",
  );
  assert.ok(
    renderPreview.indexOf("await ensureMediaPreviewSession(draft)")
      <renderPreview.indexOf("/render`"),
    "the authenticated source session must exist before the full LED render",
  );
  assert.match(js,/boardProjection\?\.frame_set\.frames_by_target/);
  const frameSetStart=js.indexOf("function currentLightingBoardFrameSet");
  const frameSetEnd=js.indexOf("\nfunction ",frameSetStart+10);
  assert.match(js.slice(frameSetStart,frameSetEnd),/timeline:\s*lightingWorkspace\.media\?\.preview_timeline\?\?null/);
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
  assert.match(transformView,/mediaCompositionCanApply/);
  assert.match(js,/type:"TRANSFORM_REQUESTED"/);
  assert.match(js,/intent\.type === "prepare-source-frame"/);
  const importErrorStart=js.indexOf("function reportMediaImportError");
  const importErrorEnd=js.indexOf("\nfunction ",importErrorStart+10);
  const importError=js.slice(importErrorStart,importErrorEnd);
  assert.match(importError,/setMediaImportStatus/);
  assert.doesNotMatch(importError,/toast\(/);
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
  assert.match(workspace,/projection\.colors\[Number\(pixel\?\.dataset\?\.pixel\)\]/);
  assert.match(workspace,/pixel\.style\.background = color/);
  assert.match(workspace,/setProperty\?\.\("--pixel-color", color\)/);
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
  assert.doesNotMatch(loader,/\/api\/ai\/ollama\/models|shouldDiscoverOllamaModels/);
  assert.equal((js.match(/\/api\/ai\/ollama\/models/g)||[]).length,1);
});

test("Settings exposes Ollama server and cloud models plus the curated API", () => {
  const ollama=html.indexOf('id="settings-ai-ollama"');
  const api=html.indexOf('id="settings-ai-api"');
  assert.ok(ollama>=0&&ollama<api);
  for(const id of [
    "settings-ai-enabled","settings-ai-ollama","settings-ai-api","settings-ollama-state",
    "settings-ollama-base-url","settings-ollama-save-url","settings-ollama-model",
    "settings-ollama-model-select","settings-ollama-refresh",
    "settings-ollama-select","settings-ollama-test","settings-ollama-clear",
    "settings-ollama-transport-warning","settings-ollama-disclosure",
    "settings-ollama-disclosure-ack","settings-ollama-disclosure-detail",
    "settings-api-provider","settings-api-model","settings-api-key","settings-api-credential-state",
    "settings-api-disclosure-ack","settings-api-test","settings-api-remove",
  ])assert.match(html,new RegExp(`id="${id}"`));
  assert.match(html,/never downloads, pulls, or removes models/);
  const ollamaPanel=html.slice(html.indexOf('id="settings-ollama-panel"'),html.indexOf('id="settings-api-panel"'));
  assert.match(ollamaPanel,/Ollama/);
  assert.doesNotMatch(ollamaPanel,/GGUF|llama\.cpp|GPU backend|direct model/i);
  assert.doesNotMatch(html,/settings-gguf|settings-local-advanced/);
  assert.match(js,/api\("\/api\/ai\/ollama\/models"/);
  assert.match(js,/api\("\/api\/ai\/ollama\/select"/);
  assert.match(js,/JSON\.stringify\(\{model_id:model\.model_id,model_digest:model\.digest,model_location:model\.location\}\)/);
  assert.match(js,/api\("\/api\/ai\/ollama\/clear"/);
  assert.match(js,/api\("\/api\/ai\/test"/);
  assert.match(js,/api\(\"\/api\/settings\/ollama\/disclosure\"/);
  assert.match(js,/On this Ollama server/);
  assert.match(js,/Ollama Cloud/);
  assert.doesNotMatch(js,/\/api\/ai\/ollama\/gguf|settings-gguf|chooseAdvancedLocalModel/);
  assert.doesNotMatch(server,/\/api\/ai\/ollama\/gguf|_select_advanced_local_model|_choose_local_model/);
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
    html.indexOf('id="settings-ai-ollama"')
  );
  assert.doesNotMatch(html,/Enable after setup passes|Test &amp; enable/);
  assert.match(html,/Test setup/);

  const populate=js.slice(js.indexOf("function populateSettings"),js.indexOf("async function refreshSettingsData"));
  assert.match(populate,/\$\("#settings-ai-details"\)\.hidden=!enabled/);
  const toggleAction=js.slice(js.indexOf("async function setAiEnabled"),js.indexOf("async function selectAiBackend"));
  assert.match(toggleAction,/api\("\/api\/settings\/ai"/);
  assert.match(toggleAction,/JSON\.stringify\(\{enabled,backend\}\)/);
  const backendAction=js.slice(js.indexOf("async function selectAiBackend"),js.indexOf("async function refreshOllamaModels"));
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
  assert.match(js,/normalizeOllamaModels\(await api\("\/api\/ai\/ollama\/models"\)\)/);
  assert.match(js,/configured Ollama server must be upgraded/);
  assert.match(js,/Upgrade the configured Ollama server/);
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
  assert.match(review,/Animated lighting preview/);
  assert.match(js,/createReviewView\(\{assetUrls:state\.conceptAssetUrls/);
  assert.match(js,/renderReview\(\$\("#lighting-generate-content"\),view,applyReviewedLighting\)/);
  assert.match(js,/function renderGenerationStudio\(\)/);
  assert.match(js,/This earlier failure does not turn anything off/);
  assert.match(js,/syncLightingJob\(null,\{renderPage:false\}\)/);
  assert.match(js,/type:"APPLY_REQUESTED"/);
  const applyStart=js.lastIndexOf("function applyReviewedLighting");
  const applyEnd=js.indexOf("async function loadAiConfig",applyStart);
  const apply=js.slice(applyStart,applyEnd);
  assert.equal((apply.match(/mutate\(/g)||[]).length,1);
  // Slice P3 moved this sentence into the shared post-Apply feedback helper so
  // every Apply says the same thing. The intent is unchanged: applying a
  // generated result must state that the keyboard has not been written.
  assert.match(apply,/lightingAppliedDetail\(/);
  const detail=js.slice(js.indexOf("function lightingAppliedDetail"),js.indexOf("\nfunction ",js.indexOf("function lightingAppliedDetail")+10));
  assert.match(detail,/Nothing has been written to the keyboard yet/);
});

test("inline generation tool omits backend identity and keeps the exact target destination", () => {
  const prompt=js.slice(js.indexOf("function renderPromptStage"),js.indexOf("function renderProgressStage"));
  assert.doesNotMatch(prompt,/state\.aiStatus\?\.backend/);
  assert.doesNotMatch(prompt,/===\s*"api"\s*\?\s*"API"\s*:\s*"Local"/);
  assert.match(prompt,/Custom \$\{destinationSlot-4\} · \$\{esc\(targetLabel\)\}/);
  const settings=html.slice(html.indexOf('id="settings-screen"'));
  assert.match(settings,/settings-ai-ollama/);
  assert.match(settings,/settings-ai-api/);
  assert.match(js,/manifest\?\.costs\?\.actual_incomplete/);
});

test("generation is inline with no detached dialog or Create route", () => {
  assert.doesNotMatch(html,/lighting-generate-dialog|lighting-generate-open/);
  assert.doesNotMatch(js,/openRenderedDialog|handleGenerationDialogClose|ROUTES\.CREATE/);
  assert.doesNotMatch(review,/openRenderedDialog|generation dialog/i);
  assert.match(js,/You can open Library while this finishes/);
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
  assert.match(js,/"preview_animation","raster_animation"/);
  assert.doesNotMatch(js,/source_video|video\/mp4/);
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
  const ownershipMutation=js.slice(
    js.indexOf("async function runLibraryOwnershipMutation"),
    js.indexOf("async function removeLibraryItem"),
  );
  assert.ok(
    ownershipMutation.indexOf("await loadLibrary({force:true})")
      <ownershipMutation.indexOf("state.library.mutatingCatalogId=null"),
    "ownership must remain busy until its forced Library refresh completes",
  );
  assert.match(
    js,
    /data-library-undo-remove[^>]*\$\{state\.library\.mutatingCatalogId\|\|state\.library\.loading\?"disabled":""\}/,
  );
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
  assert.match(medium,/\.lighting-workspace-shell\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) 240px/);
  assert.match(css,/\.lighting-timeline-frames\s*\{[^}]*overflow-x:\s*auto/);
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

test("CyberBoard switch lighting shares the photographed Keymap geometry", () => {
  assert.match(
    js,
    /const CB_LED_LAYOUT=projectVialLedLayout\([\s\S]*key_layout:CB04_LAYOUT\.map[\s\S]*width:15,height:6,count:83,map:CB_LED_MAP/,
  );
  assert.match(
    js,
    /CB:\s*\{[^}]*physicalLayout:CB_LED_LAYOUT[^}]*physicalClass:"cyber"/,
  );
  assert.match(
    js,
    /const columns=state\.ledTarget==="frames"\?40:/,
  );
  assert.match(
    js,
    /const physicalLayout=state\.ledTarget==="keyframes"\s*\?model\.physicalLayout\s*:state\.ledTarget==="axial"\s*\?projectVialLedLayout\(device,servedTarget\)\s*:null;/,
  );
  assert.match(
    js,
    /class="pixel-grid physical afa-led-board \$\{esc\(model\.physicalClass\|\|""\)\}"/,
  );
  assert.match(
    css,
    /\.pixel-grid\.physical\.cyber\s*\{[^}]*aspect-ratio:\s*2\.46\s*\/\s*1/,
  );

  const constants=js.slice(
    js.indexOf("const CB04_LAYOUT"),
    js.indexOf("const AFA_LED_MAP",js.indexOf("const CB04_LAYOUT")),
  );
  const context={projectVialLedLayout};
  vm.runInNewContext(
    `${constants}\nglobalThis.result={keymap:CB04_LAYOUT,layout:CB_LED_LAYOUT,display:CB_DISPLAY_MAP};`,
    context,
  );
  const {keymap,layout,display}=context.result;
  const led=index=>layout.find(item=>item.index===index);

  assert.equal(keymap.length,81);
  assert.equal(layout.length,83);
  assert.deepEqual(
    [0,1,5,9,13,14].map(index=>[led(index).x,led(index).w]),
    [[0,6.25],[7.8125,6.25],[34.375,6.25],[60.9375,6.25],[87.5,6.25],[93.75,6.25]],
  );
  assert.deepEqual(
    [28,58,60,72,73].map(index=>[
      led(index).keyIndex,
      led(index).x,
      led(index).w,
    ]),
    [
      [38,81.25,12.5],
      [88,79.6875,14.0625],
      [100,0,14.0625],
      [112,76.5625,10.9375],
      [113,87.5,6.25],
    ],
  );
  assert.deepEqual(
    layout.filter(item=>item.keyIndex===131).map(
      item=>[item.index,item.groupPosition,item.groupCount,item.showLabel],
    ),
    [[79,0,3,false],[80,1,3,true],[81,2,3,false]],
  );
  assert.deepEqual(
    [87,88,89].map(index=>[led(index).keyIndex,led(index).x]),
    [[137,81.25],[138,87.5],[139,93.75]],
  );
  assert.equal(display.length,200);
  assert.equal(display[0],0);
  assert.equal(display[199],199);
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
