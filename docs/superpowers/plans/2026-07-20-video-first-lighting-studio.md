# Video-First Lighting Studio — Implementation Plan

- **Date**: 2026-07-20
- **Status**: approved by the owner on 2026-07-20; implementation authorized.
  The owner approved an editor-first UI reset on 2026-07-21 before Task 11.
  Product decisions are recorded in `.agents/decisions.md`.
- **Branch**: `llm-led-generator`
- **Starting commit**: `137dbc85d2f731aeef1ce4b93c512c21792c42d5`
- **Goal**: keep the manual Lighting editor as the primary product workspace
  while adding an optional durable image/video generation workflow. Users can
  generate and select still concepts, animate one with a minimum-duration xAI
  video, convert the complete video locally into the active device's maximum
  firmware frame count, browse every retained artifact, and explicitly apply a
  compatible result to the open document.
- **Execution**: tests first, one commit per numbered task, full repository
  verification after every task. When a task adds a test, prove the guard by
  observing the test fail before the implementation and pass afterward.
  Parallel agents may inspect or implement disjoint tasks, but only one agent
  may edit a shared file at a time and each finished slice is committed before
  the next overlapping slice begins.

## Authority and supersession

The approved decisions in `.agents/decisions.md` are the product authority for
this plan. This plan supersedes these parts of
`docs/design/llm-led-generator.md`:

- video/MP4/FFmpeg as a non-goal;
- zero new runtime dependencies;
- the 16-render keyframe/tween path as the primary generation experience;
- discarding successful artifacts after a partial failure;
- a single ephemeral in-memory job and browser-only pending result;
- the narrow inline AI panel and modal Settings UI.

The 2026-07-21 editor-first decision supersedes the Create-first shell described
by the original Task 10. It does not supersede the generation, library,
durability, compatibility, or explicit-Apply contracts.

Keep the implemented GIF import and `frames_to_led_tracks()` mapping core. The
parked `previous_plan` forwarding defect belongs only to the superseded inline
generator and is closed by removing that endpoint after the replacement is
operational; do not spend a separate slice repairing dead behavior.

The premium direct frame-by-frame GIF generator is not part of this plan. It is
the last follow-up and requires a separate owner-approved plan covering its
frame range, one-output limit, chained image-edit contract, and one-time cost
confirmation. The manual local GIF importer remains supported.

## Verified starting point

- `am_configurator/llm.py` contains typed provider errors, a bounded xAI JSON
  transport, strict structured-output parsing, validated PNG/JPEG decoding,
  current model/frame constants, and the old interpreter/renderer pipeline.
- `am_configurator/server.py` contains authenticated loopback routes,
  `_GIF_LAYOUTS`, `_generation_spec()`, `frames_to_led_tracks()`, typed provider
  HTTP mapping, and an ephemeral `_State` generation worker.
- `am_configurator/store.py` contains cross-platform locks, atomic JSON writes,
  app settings, and masked xAI-key resolution.
- `am_configurator/web/app.js` is a framework-free single application store.
  Reuse `api()`, the LED canvas and playback mechanics,
  `applyLedResultToPage()`, and undo handling. Replace the inline AI panel,
  pending-result takeover, whole-screen polling rerenders, and settings modal.
- `am_configurator/desktop.py` owns the pywebview window and frozen smoke test.
  It has no native JavaScript bridge yet.
- The repository verification entry point is the four-command sequence in
  `.agents/repo-guidance.md`. Native-distribution changes also require a local
  bundle and frozen `--smoke-test`.
- Automated tests must never call a provider or write to a keyboard. Provider,
  downloader, job, media, and native-bridge collaborators must be injectable.

## Provider contracts and dated catalog

Create `am_configurator/ai_catalog.py` as the canonical curated catalog. Its
schema version and `pricing_as_of = "2026-07-20"` make stale estimates visible.
It contains only these selectable roles:

- interpreter: `grok-4.5` default, `grok-4.3` lower-cost option;
- concept image: `grok-imagine-image` default,
  `grok-imagine-image-quality` quality option;
- video: `grok-imagine-video-1.5` default,
  `grok-imagine-video` lower-cost option.

Record per-million input/output text prices, per-image input/output prices, and
per-second 480p video prices as integer USD ticks, where 10^10 ticks is one US
dollar. Do not use binary floating point for aggregation. The catalog is an
estimate, not billing truth. Every provider response is independently parsed
for `usage.cost_in_usd_ticks`. Store usage under a stable charged-operation key
(`concept_plan`, candidate asset ID, `video_plan`, or video request ID) and
replace rather than append repeated status observations, so polling can never
double-count one charge. Manifests sum unique exact integer values and mark the
total incomplete if a charged operation never reports usage.

The catalog values as of the plan date are:

- `grok-4.5`: 20,000,000,000 ticks per million short-context input tokens and
  60,000,000,000 per million output tokens;
- `grok-4.3`: 12,500,000,000 ticks per million short-context input tokens and
  25,000,000,000 per million output tokens;
- `grok-imagine-image`: 20,000,000 ticks per image input and 200,000,000 per
  1K output image;
- `grok-imagine-image-quality`: 100,000,000 ticks per image input and
  500,000,000 per 1K output image;
- `grok-imagine-video-1.5`: 100,000,000 ticks per image input and 800,000,000
  per second of 480p output;
- `grok-imagine-video`: 20,000,000 ticks per image input and 500,000,000 per
  second of 480p output.

Use the documented xAI REST contracts:

- structured planning: `POST https://api.x.ai/v1/responses`, `store: false`;
- stills: `POST https://api.x.ai/v1/images/generations`, `n: 1`,
  `aspect_ratio: "20:9"`, `resolution: "1k"`, and inline `b64_json` only;
- image-to-video submit: `POST https://api.x.ai/v1/videos/generations` with
  the selected still as a validated base64 data URI in `image.url`,
  `duration: 1`, `resolution: "480p"`, and no aspect-ratio override;
- video status: `GET https://api.x.ai/v1/videos/{request_id}` until `done`,
  `failed`, or `expired`.

Paid POSTs are called once and never automatically retried. A transport failure
after a video POST may mean the provider accepted a charge without returning a
request ID; record `submission_unknown` and require an explicit human retry.
Status GETs and media downloads may retry within fixed attempt and time bounds.
Persist a returned `request_id` before the first poll. Ten minutes is only the
foreground wait budget: after that, move the operation to background retrieval
instead of abandoning it. Poll at five-second intervals while foregrounded,
use per-request network timeouts no greater than 30 seconds, and persist bounded
backoff after network failures. Relaunch keeps resuming safe status/download
checks until xAI reports `done`, `failed`, or `expired`; elapsed wall time alone
never discards an accepted paid request or triggers another POST.

Implement against these primary references, rechecking them before provider or
pricing code lands because they are external, versioned contracts:

- xAI pricing: <https://docs.x.ai/developers/pricing>
- xAI exact cost tracking: <https://docs.x.ai/developers/cost-tracking>
- xAI image generation/editing:
  <https://docs.x.ai/developers/rest-api-reference/inference/images>
- xAI asynchronous video REST API:
  <https://docs.x.ai/developers/rest-api-reference/inference/videos>
- xAI image-to-video inputs:
  <https://docs.x.ai/developers/model-capabilities/video/image-to-video>
- FFmpeg release/source verification: <https://ffmpeg.org/download.html>
- FFmpeg licensing checklist: <https://ffmpeg.org/legal.html>

## Settings contract

Migrate the current settings file without quarantining it or losing a saved
key. The normalized v2 settings shape is:

```json
{
  "schema_version": 2,
  "llm": {
    "models": {
      "interpreter": "grok-4.5",
      "concept": "grok-imagine-image",
      "video": "grok-imagine-video-1.5"
    },
    "keys": {"xai": "stored-secret"}
  },
  "library": {
    "current_root": null,
    "roots": []
  },
  "generation": {
    "candidate_count": 4,
    "loop_mode": "smooth",
    "privacy_ack_version": null,
    "privacy_ack_at": null
  }
}
```

The server accepts concept counts only in `1..8` regardless of client state.
Loop modes are exactly `smooth`, `none`, and `ping_pong`. Changing
`current_root` appends the previous non-null root to `roots`, deduplicated by
canonical path; it never moves files. Secrets and preferences have independent
mutation routes so changing a model or folder cannot erase a key:

- `GET /api/settings` returns preferences and masked key state only;
- `POST /api/settings/key` accepts `{provider, key}`; an empty key clears;
- `POST /api/settings/preferences` accepts only curated models, candidate-count
  default, and loop-mode default;
- `POST /api/settings/library` accepts only `{current_root}` and updates the
  server-owned root history;
- `POST /api/settings/privacy` records acknowledgment of only the current
  disclosure version.

The Settings page has Provider, Models, Storage, and Costs sections. Costs
shows dated estimates for concept batches and the video workflow plus exact
historical totals from manifests. No call count, token count, or price appears
in the Create workflow.

Before the first provider call for the current disclosure version, require one
explicit acknowledgment explaining that the user's prompt, derived prompts,
target geometry, and—during animation—the selected still are sent to xAI; that
xAI's current retention policy applies; and that prompts, generated media,
usage, and costs are retained in the chosen local folder. This is privacy copy,
not an API-call/cost dashboard. Persist only the disclosure version and
timestamp, and require acknowledgment again when the disclosed data flow
changes.

## Library and manifest contract

The configured library root contains `jobs/<job-id>/`. A job ID is a generated
UUID and never contains prompt text. Each job directory contains:

```text
manifest.json
concepts/
video/
frames/
preview/
result/
.work/
```

`manifest.json` is schema-versioned and atomically replaced under a per-job
lock. It stores the job ID, timestamps, prompt, device-family/raster/target
snapshot, concept batches, candidates, selected candidate, animation attempts,
loop mode, model IDs, sanitized provider request IDs, operation status/phase,
asset records, estimated and actual cost ticks, cancellation timestamps, and
sanitized errors. It never stores API keys, Authorization headers, base64 data
URIs, or temporary signed URLs.

Each asset record has an opaque ID, kind, relative path, MIME type, byte size,
SHA-256, origin, created timestamp, and status. Provider image bytes are
validated and atomically committed before a candidate is reported complete.
Retain every completed provider still, the selected still, the original MP4,
individual final target-raster PNG frames, a preview poster/animation, and the
mapped LED JSON. Full-resolution temporary interpolation frames live only under
`.work/` and are removed after every success, failure, cancellation, or
interrupted-state reconciliation. A local retry recreates them from the banked
MP4.

Before any paid request, require a configured root, canonicalize it, create a
private write probe, verify sufficient free space, and create the job manifest.
Never silently fall back to the app data directory. A changed current root is
used only for new jobs; scan every recorded root for older jobs. A corrupt
manifest is isolated and reported without hiding other jobs. Rebuild any
in-memory index from manifests on startup.

At startup:

- an in-progress concept request becomes `interrupted` or `partial` according
  to already committed candidates;
- an accepted video request with a stored request ID resumes polling;
- a video submission with unknown acceptance remains `submission_unknown`;
- a banked MP4 with unfinished local work becomes `ready_to_process`;
- no paid POST is automatically repeated.

## Durable workflow

A job is a reusable lineage rather than a disposable request. It may contain
multiple concept batches and animation attempts, but only one operation is
active. A process-wide coordinator allows one paid/local generation operation
at a time; `awaiting_selection` and terminal jobs do not hold the lock.

Concept operation:

1. Validate prompt, product/targets, count, models, API key, and library root.
2. Create the manifest before spending.
3. Ask the interpreter for a strict `ConceptPlan` containing a shared visual
   brief and exactly N closely related candidate prompts. Request 1K `20:9`
   stills and bind every candidate prompt to the exact device raster. Concepts
   are flat, high-contrast emissive textures with raster-cell-scale forms, not
   cinematic scenes, landscapes, photographed keyboards, or fine-detail art.
   Keep all essential subjects/action inside the target-raster safe band; the
   Create gallery overlays the actual device crop so users judge what survives.
4. Generate candidates sequentially. Atomically bank and publish each valid
   image and its exact usage before starting the next call.
5. End as `awaiting_selection`, `partial`, `cancelled`, or `failed`. Successful
   candidates remain selectable in every outcome.
6. “More like this” appends another explicit batch under the same lineage and
   repeats the same preflight. It never starts automatically.

Animation operation:

1. Validate that the candidate asset belongs to the job and commit the
   selection; this does not mutate the open document.
2. Pixel-reduce the selected still to the target raster's information budget,
   nearest-upscale it back to provider dimensions, and bank that exact PNG as a
   `selected_still`. Send it with the original prompt, optional user motion text,
   device geometry, fixed one-second duration, locked coordinates, and selected
   loop mode to the interpreter. Validate a strict `VideoAnimationPlan` with
   subject/style locks and one concrete prompt, then deterministically append
   the non-optional LED-texture, no-scene, closed-cycle constraints so planner
   drift cannot turn the request back into conventional video.
3. Submit exactly one image-to-video POST and persist `request_id` before poll.
4. Poll durably. On visible cancellation after acceptance, stop foreground
   progress but continue background poll/download; bank the MP4, mark
   `cancelled_saved`, and do not start local processing.
5. Download a completed MP4 promptly, validate it, hash it, fsync it, and
   atomically publish it before local processing.
6. Process the complete one-second video to exactly the existing
   `MODEL_FRAME_CAPS[family]` count at 34 ms per frame. Publish only after exact
   count and image validation.
7. Call the existing `frames_to_led_tracks()` with constant 34 ms durations and
   the captured targets/product family. Require `timing_resampled == false` and
   exact frame-count parity. Atomically bank the mapped JSON and preview.
8. End as `ready`; do not apply automatically. A local processing failure keeps
   the MP4 and exposes a no-provider-cost retry.

## Loop algorithms

Let F be the existing maximum frame cap for the selected device family. Every
mode outputs exactly F frames and therefore plays for `F * 34 ms`:

- `smooth`: reserve `S = ceil(F / 8)` frames. FFmpeg motion-interpolates and
  samples the complete source video into `F - S` content frames. At compact
  target resolution, append S deterministic blends from the last content frame
  toward the first, excluding duplicate endpoints. This is the default.
- `none`: FFmpeg motion-interpolates and samples the complete source video into
  F content frames. Playback may jump from the final frame to the first.
- `ping_pong`: all current caps are even. Sample `F / 2 + 1` frames across the
  complete source, then append the interior frames in reverse order. The two
  endpoints appear once and the result has exactly F frames.

Interpolate before crop/scale. Use a cover crop that preserves the source
aspect ratio and emits the exact raster dimensions from `_generation_spec()`.
The original provider still and MP4 remain untouched regardless of loop mode.

## Media boundary and bundled FFmpeg

Create `am_configurator/media.py`. The provider MP4 downloader:

- accepts HTTPS only, no user information, and the documented `vidgen.x.ai`
  host; every redirect is revalidated against the same allowlist;
- never forwards the xAI Authorization header to the media host;
- streams to `source.mp4.part` with a 100 MB cap and request timeout;
- verifies non-empty MP4-like content, hashes during download, fsyncs, and uses
  atomic rename;
- never passes a provider URL or provider-controlled filesystem path to FFmpeg.

Bundle FFmpeg 8.1.2 from the signed official source release. Add
`packaging/ffmpeg/manifest.json`, `README.md`, the LGPL license, exact source
URL/signature/fingerprint, computed source SHA-256, configure arguments, and
runtime-attestation schema. The build must remain LGPL-only: never enable GPL
or nonfree components. Build only the `ffmpeg` program and required static
libraries/protocols, the MOV/MP4 demuxer, H.264/MPEG-4/HEVC decoders and parsers,
PNG encoder/image2 muxer, file protocol, and the trim/setpts/minterpolate/
scale/crop/format/fps filters. Disable network protocols in the executable. Set
`SOURCE_DATE_EPOCH` from the release and use prefix-map/strip flags so build
paths and timestamps do not leak into the runtime.

`build_tools/ffmpeg_bundle.py` verifies the signed source, builds the minimal
binary for the current platform/architecture, records/verifies hashes, and
checks `ffmpeg -version`, configure flags, required decoders, and required
filters. Built binaries live under ignored `build/ffmpeg/`, not Git. CI caches
the source/build by version, platform, architecture, and recipe hash. Native
installer jobs build or restore the verified binary before PyInstaller.

The static manifest pins the official source SHA-256 and recipe, not a guessed
cross-toolchain binary hash. Each build emits `ffmpeg-runtime.json` beside its
binary with the platform, architecture, compiler identity, recipe hash,
configure output, capability results, and actual binary SHA-256; PyInstaller
packages both and runtime discovery verifies the pair.

Use these supported build environments:

- macOS: the runner's Xcode Command Line Tools (`clang`, `make`, SDK zlib);
- Linux x86-64: Ubuntu `build-essential`, `pkg-config`, and `zlib1g-dev`;
- Windows x86-64: MSYS2 MinGW64 with `mingw-w64-x86_64-gcc`, `make`,
  `pkgconf`, and `zlib`; run configure/build wholly inside the MSYS2 shell.

Use `--disable-everything --disable-autodetect --enable-ffmpeg
--disable-ffplay --disable-ffprobe --disable-doc --disable-debug
--disable-network --enable-static --disable-shared` plus only the listed
libraries/components. Use `--disable-x86asm` on x86 targets to avoid an
unpinned assembler dependency; accept the small performance cost for a
one-second 480p input. The build helper translates platform path syntax and
adds the target/architecture flags. Increase the native workflow timeout from
35 to 75 minutes. Cache key:
`ffmpeg-8.1.2-<os>-<arch>-<source-sha>-<recipe-sha>`. CI verifies the committed
source hash; the README records the one-time PGP verification against FFmpeg's
published release key fingerprint.

At runtime resolve only: an injected test path, a validated developer override
`AM_CONFIGURATOR_FFMPEG`, the prepared development cache, or the PyInstaller
bundle. Do not silently pick an arbitrary system executable. Run with a fixed
absolute binary path, argument array, `-nostdin`, no shell, bounded timeout,
captured bounded diagnostics, and `CREATE_NO_WINDOW` on Windows. Cancellation
terminates then kills after a short grace period. Validate every output name,
count, format, and dimension before publication.

Add FFmpeg to `THIRD_PARTY_NOTICES`. Ship the LGPL text, source/build offer, and
matching recipe beside every native distribution. The wheel remains
platform-neutral and does not contain all native binaries.

## Authenticated local API

All routes require the existing `X-AM-Token`. JSON endpoints never return an
absolute library path except the explicit Settings storage view. Binary assets
are addressed only by job/asset IDs and resolved through manifest-owned
relative paths:

- `POST /api/lighting/concepts` → create job and return `{job_id}`;
- `POST /api/lighting/jobs/{job_id}/concepts` → explicit additional batch;
- `POST /api/lighting/jobs/{job_id}/animate` → select owned candidate and start
  one video attempt;
- `POST /api/lighting/jobs/{job_id}/process` → retry banked local work only;
- `POST /api/lighting/jobs/{job_id}/cancel` → phase-aware visible cancellation;
- `GET /api/lighting/jobs/{job_id}` → durable status, progress, assets, costs,
  and mapped result metadata;
- `GET /api/lighting/library` → paginated/filterable manifest summaries;
- `GET /api/lighting/library/{job_id}` → complete sanitized lineage;
- `GET /api/lighting/assets/{job_id}/{asset_id}` → whitelisted image/video
  bytes with bounded single-range support for MP4 playback.

Reject symlink escapes, `..`, unknown asset IDs, wrong ownership, unsupported
MIME types, oversized ranges, malformed IDs, and assets outside every recorded
canonical root. Add `media-src 'self' blob:` to CSP. The browser fetches assets
through authenticated `api`/fetch calls and creates short-lived blob URLs so
the token never appears in an asset URL.

## Desktop and browser folder behavior

Add a narrow `DesktopBridge` to `desktop.py` and pass it as pywebview `js_api`.
It exposes a native folder chooser and Reveal action only; persistence remains
through authenticated HTTP settings routes. The bridge validates returned
paths and Reveal targets against recorded library roots. Browser-only launches
show an editable absolute-path fallback and the same server-side validation.
No provider call may begin until the configured path is writable.

## Lighting Studio experience

The global Lighting screen opens directly into the manual editor. A compact
toolbar exposes Workspace and Library, the current product/slot/target, and a
secondary `Generate…` action. It reuses the single global Open and Devices
controls; routed content must not duplicate either action. Library and Settings
work without an open configuration. Workspace, Generate, and Apply explain
when a compatible document is required using copy only.

Generate opens a labelled dialog or drawer over the editor and uses `Concepts →
Animate → Review & Apply`:

- Concepts: large prompt, quantity default four/max eight, stable media grid,
  explicit single selection, saved indicators, partial tiles, “More like this,”
  actual device-crop overlay/preview, and “Animate selected.” No cost/call
  details.
- Animate: selected still anchor, optional “How should it move?” field, Video
  visibly selected and recommended, loop selector with Smooth/No
  transition/Ping-pong, and one Create animation action. The premium GIF entry
  is a collapsed disabled/coming-later disclosure until its separate plan.
- Review: device-mapped preview is primary; Source video and Frames are
  secondary tabs. The result starts paused. The action is destination-specific,
  for example “Apply 80 frames to Slot 1,” with “Changes the open document
  only. It does not write to the keyboard.” Applying revalidates compatibility,
  creates one undo checkpoint, and calls the existing mapping application
  boundary. Closing or navigating leaves the result in Library.

Closing the generation surface never cancels, discards, applies, or triggers a
provider call. A completed result appears in the existing explicit pending
review surface; it is not applied automatically. Opening or selecting within
Generate makes no paid call.

Library groups cards by lineage and shows concepts, selected still, source MP4,
device animation, status, and poster. Filters include All, Concepts, Videos,
Partial, and Applied. Detail actions include preview, animate a banked still,
retry local processing, explicitly retry a paid step, apply a compatible result,
and Reveal. Never call a paid endpoint from a filter, selection, navigation,
resume-local, or Apply action.

Keep the manual editor as the default Lighting renderer and place Library in a
secondary routed view. The generation surface owns the Concepts/Animate/Review
state without replacing the editor shell. Keep stable shell/media nodes while
polling; update only progress and affected cards so focus and scroll survive.
Keep the persistent compact job strip outside the routed screen.

Accessibility and responsive requirements:

- Workspace/Library tabs use `aria-selected`, roving focus, and arrow keys;
- concept cards are a single-select radiogroup with arrow/Space operation;
- selection, errors, and status include text/icons and never rely on color;
- phase changes use a polite live region once; measurable work uses a
  progressbar; polling itself is silent;
- images have useful alt text; videos start paused and muted with named
  play/pause controls; no autoplay;
- Escape closes the generation drawer/dialog and returns focus to Generate,
  but never cancels, applies, discards, or starts a provider call;
- respect `prefers-reduced-motion`;
- the LED canvas and its entry state remain in the first viewport at wide and
  narrow sizes; frames become a horizontal strip before controls stack;
- at 880 px and 200% zoom there is no page-level horizontal scrolling, and the
  editor remains usable at 720 px and 200% zoom equivalent. At wide widths the
  context panel is 230–260 px; below its fit threshold it moves beneath the
  canvas or into a named drawer.

## Task 1 — Curated catalog and lossless settings migration

**Files**: add `am_configurator/ai_catalog.py`; modify
`am_configurator/store.py`, `am_configurator/server.py`, and
`tests/test_app.py`.

1. Add failing settings/catalog tests for exact curated choices/defaults,
   integer price ticks/date, v1→v2 migration preserving an existing key,
   strict unknown-field/model/loop/count rejection, root history semantics,
   independent key/preference updates, versioned privacy acknowledgment, key
   masking, and no secret in errors.
2. Implement the catalog and v2 schema. Keep `XAI_API_KEY` as a non-persisted
   effective override. Do not quarantine a valid v1 file.
3. Add the split settings routes and expose the catalog through capabilities.
4. Prove the focused tests red→green, run the full verification entry point,
   then commit `feat: add curated ai catalog and migrate settings`.

## Task 2 — Secure manifest-backed library

**Files**: add `am_configurator/library.py` and `tests/test_library.py`; modify
`am_configurator/store.py` only for shared helpers if unavoidable.

1. Add failing tests for root preflight, private job creation, atomic manifest
   updates, immediate asset banking, hashes, partial retention, multi-root scan,
   corrupt-manifest isolation, restart reconciliation, permissions, traversal,
   symlink escapes, and opaque asset lookup.
2. Implement the schema, per-job locks, atomic byte/JSON helpers, scan/index,
   reconciliation, free-space check, and sanitized public views.
3. Prove each new guard, run full verification, and commit
   `feat: add durable generated asset library`.

## Task 3 — Concept planning, still generation, and exact usage

**Files**: modify `am_configurator/llm.py`; add focused provider tests in
`tests/test_app.py`.

1. Add failing tests for strict `ConceptPlan`, exactly N varied prompts,
   prompt/count bounds, selected models, `store: false`, one image per POST,
   validated original PNG/JPEG bytes, per-response cost ticks, missing-usage
   marking, partial callback ordering, cancellation between calls, refusal,
   typed errors, and secret redaction.
2. Refactor the existing validated image decoder to return original bytes and
   metadata as well as a Pillow image. Expose a single-image generation seam so
   orchestration can bank before the next paid call.
3. Keep the old generator operational until Task 15. Run full verification and
   commit `feat: add bankable concept generation providers`.

## Task 4 — Structured video planning and asynchronous xAI video provider

**Files**: modify `am_configurator/llm.py`; add provider tests.

1. Add failing tests for selected-still multimodal planning, strict
   `VideoAnimationPlan`, subject/style locks, motion/loop/device context, one
   concrete prompt, one-second/480p/default-model payload, base64 data URI,
   request-ID validation, status validation, cost ticks, terminal states,
   per-call timeouts, and no paid POST retry.
2. Implement separate `submit()` and `poll()` seams. Keep signed media URLs only
   in memory long enough to hand to the downloader; never serialize them.
3. Run full verification and commit
   `feat: add xai image-to-video provider contract`.

## Task 5 — Hardened temporary-video downloader

**Files**: add `am_configurator/media.py` and `tests/test_media.py`.

1. Add failing fake-opener tests for exact-host HTTPS acceptance, scheme/host/
   userinfo/port rejection, redirect revalidation, auth stripping, streamed
   size bound, timeouts, `.part` cleanup, fsync/atomic publication, SHA-256,
   cancellation, and preserved destination on failure.
2. Implement the downloader without invoking FFmpeg. Run full verification and
   commit `feat: add hardened xai video downloader`.

## Task 6 — Reproducible LGPL FFmpeg runtime and exact-frame processor

**Files**: add `build_tools/ffmpeg_bundle.py`, `packaging/ffmpeg/*`, a tiny MP4
fixture, and media tests; modify `am_configurator/media.py`, `.gitignore`, and
`THIRD_PARTY_NOTICES`.

1. Add failing tests for manifest/schema/hash checks, runtime resolution,
   required capability parsing, argument-array construction, no shell/network,
   timeout/cancellation behavior, Windows no-console flags, crop dimensions,
   loop formulas, and exact 80/200/186 output validation.
2. Implement the signed-source build/verify helper and minimal recipe. Build the
   current-host binary into ignored `build/ffmpeg/` and run it against the
   fixture. Unit tests may inject a fake runner; at least one current-host
   integration test must exercise the real binary.
3. Implement processing into `.work/`, compact-frame validation, deterministic
   loop assembly, and atomic publication.
4. Run full verification and commit
   `feat: add reproducible ffmpeg animation processing`.

## Task 7 — Durable concept orchestration

**Files**: add `am_configurator/generation.py` and
`tests/test_generation.py`.

1. Add failing tests for validation-before-spend, manifest-before-spend,
   single-flight, sequential candidates, immediate banking, partial/error/
   cancellation status, More-like-this batches, exact/estimated cost totals,
   restart interruption, no automatic retry, and no device writer calls.
2. Implement an injected coordinator using the library and provider seams.
3. Run full verification and commit
   `feat: add durable concept generation jobs`.

## Task 8 — Durable video, recovery, and mapping orchestration

**Files**: modify `am_configurator/generation.py`; extend generation tests.

1. Add failing tests for candidate ownership, persisted selection, request ID
   persistence before poll, restart polling resume, submission unknown, bounded
   safe poll/download retry, foreground timeout without abandonment, visible
   cancellation with background banking,
   cancelled-saved no-auto-process, MP4 retention on local failure, local-only
   retry, exact frame caps/34 ms, all loop modes, mapping parity, exact cost
   accumulation, and never applying/writing hardware.
2. Implement the full state machine and startup reconciliation.
3. Run full verification and commit
   `feat: add durable video animation pipeline`.

## Task 9 — Authenticated Lighting and Library endpoints

**Files**: modify `am_configurator/server.py`; add endpoint tests in
`tests/test_app.py`.

1. Add failing loopback tests for every route, authentication, strict bodies,
   preflight errors, 409 single-flight, durable snapshots, pagination/filters,
   asset ownership/path safety, MIME/Range behavior, provider error mapping,
   phase-aware cancellation, and zero device writes.
2. Inject coordinator/provider/downloader/media dependencies through
   `create_server()` for offline tests. Preserve manual GIF and legacy generator
   routes until Task 15.
3. Run full verification and commit
   `feat: expose durable lighting generation api`.

## Task 10 — Lighting shell and testable browser state

**Files**: modify `am_configurator/web/index.html`, `app.js`, and `style.css`;
add `am_configurator/web/lighting_state.js` and Node tests under `tests/web/`;
modify server static assets and the recorded verification entry point.

1. Add failing pure-state tests for stage transitions, selection-without-
   mutation, route/job persistence, compatibility gating, and Apply as the only
   document-mutation intent. Add static assertions for semantic tabs and the
   persistent job strip.
2. Make Settings and Library routable without a document. Add the Lighting
   Create/Library/Edit shell and extract the current LED editor unchanged into
   Edit. Keep job progress outside routed content.
3. Add `node --test tests/web/*.test.js` to repository verification. Run full
   verification and commit `feat: add lighting studio shell`.

## Task 10R — Editor-first responsive shell reset

**Status**: approved by the owner on 2026-07-21; execute before Task 11.

**Files**: modify `am_configurator/web/index.html`, `app.js`, `style.css`, and
`lighting_state.js`; modify browser tests under `tests/web/`.

1. Add failing state/static tests proving Lighting defaults and links to Edit,
   the shell contains one global Open control and one global Devices control,
   routed requirements contain neither duplicate, Workspace precedes Library,
   Generate is secondary and closed by default, and opening/closing it cannot
   call a provider, cancel, discard, apply, or mutate the document.
2. Replace the Task 10 hero, destination card, equal-weight Create tab, staged
   landing artwork, and oversized empty requirement with a compact two-row
   Workspace toolbar. Keep route/job/stage/apply APIs, Library and Settings
   routes, the persistent job strip, and all manual editor behavior. Move the
   legacy prompt controls into the labelled generation dialog as a temporary
   adapter until Tasks 12–13 replace its contents. Keep pending review in the
   editor and lock its captured slot/target while generation or review is live.
   Prove the focused tests red before implementation and green after; commit
   `feat: restore editor-first lighting workspace`.
3. Add failing interaction/static tests for named playback/frame/paint controls,
   keyboard painting, retained focus, canvas-first narrow ordering, a horizontal
   frame strip, no page-level overflow, visible device access, and sufficient
   small-text contrast. Implement the responsive/accessibility pass without
   changing device/provider behavior. Manually inspect 1600×900, 1280×800,
   980×720, 720×600, and the 720px/200%-zoom equivalent. Run full verification,
   rebuild the native app through `python build.py --skip-sync`, run frozen
   smoke, and commit `fix: make lighting workspace compact and accessible`.

## Task 11 — Native folder bridge and full Settings page

**Files**: modify `am_configurator/desktop.py`, web assets, packaging tests, and
browser-state/static tests.

1. Add failing tests for the injected bridge, cancel/no-selection behavior,
   canonical chosen paths, Reveal root restrictions, and settings UI contracts.
2. Pass `DesktopBridge` as pywebview `js_api`; keep manual-path browser
   fallback. Replace the settings dialog with Provider/Models/Storage/Costs and
   preserve key Save/Test/Clear without coupling it to preferences.
3. Verify keyboard behavior and an unwritable-folder provider preflight. Run
   full verification, rebuild the current-OS native app, pass frozen smoke, and
   commit
   `feat: add full settings and native library chooser`.

## Task 12 — Concepts Create stage

**Files**: modify web assets and browser tests.

1. Add failing state/static tests for default four/max eight, stable candidate
   slots, partial retention, explicit More-like-this, radiogroup selection,
   device-crop overlays, no selection side effects, no cost/call copy,
   first-use privacy acknowledgment, and accessible phase updates.
2. Implement Concepts against the durable endpoints with authenticated asset
   blobs and object-URL cleanup. Poll without replacing the workspace DOM.
3. Manual-check keyboard-only selection, cancellation, partial results, 880 px,
   200% zoom, and reduced motion. Run full verification and commit
   `feat: add concept creation workspace`.

## Task 13 — Video Animate and explicit Review & Apply

**Files**: modify web assets and browser tests.

1. Add failing state/static tests for Video default, three loop choices,
   collapsed premium disclosure, selected-still anchor, phase labels,
   cancelled-saved behavior, paused/muted previews, source/device/frame tabs,
   destination-specific Apply copy, compatibility revalidation, and one undo
   mutation only after Apply.
2. Implement animation start/status/local retry and review. Reuse
   `applyLedResultToPage()`; no endpoint or completion callback applies.
3. Manual-check all three loops and navigation with the persistent job strip.
   Run full verification and commit
   `feat: add video animation review and apply`.

## Task 14 — Manifest-backed Library browser

**Files**: modify web assets and browser tests.

1. Add failing tests for filters, lineage grouping, partial/cancelled visibility,
   asset detail actions, no-cost local resume, paid-retry explicitness,
   compatible Apply gating, and document-independent access.
2. Implement grid/detail views, authenticated image/video blobs, preview,
   animate-from-still, local retry, Apply, and Reveal.
3. Manual-check a multi-root library and app relaunch. Run full verification and
   commit `feat: add generated lighting library browser`.

## Task 15 — Native packaging and frozen media smoke

**Files**: modify `packaging/am_configurator.spec`, native build scripts,
`.github/workflows/desktop.yml`, `am_configurator/desktop.py`, and packaging
tests.

1. Add failing packaging tests for correct platform/architecture binary,
   executable mode, manifest/hash/version/capabilities, license/source offer,
   PyInstaller placement, and offline frozen smoke coverage.
2. Prepare/cache the minimal binary before PyInstaller and bundle only the
   current platform artifact. Extend `--smoke-test` to locate the bundled binary,
   process the committed MP4 fixture through the real interpolation/crop path,
   and assert exact output offline.
3. Build the current macOS `.app`, run frozen smoke with network disabled, and
   run the full verification entry point. Commit
   `build: bundle verified ffmpeg media runtime`.

## Task 16 — Remove the superseded inline generator

**Files**: modify `llm.py`, `server.py`, web assets, desktop smoke, and tests;
update the old design's implementation status.

1. Add/adjust guards proving manual GIF import, shared mapping, settings key
   test, new generation, and frozen smoke remain intact without the legacy
   `/api/led/generate*`, `EffectPlan` tween pipeline, 16-keyframe cap, pending UI,
   or stale `previous_plan` state.
2. Remove only now-unreferenced code and tests. Do not remove shared transport,
   image validation, mapping, manual GIF import, or provider errors.
3. Run full verification, rebuild the current-OS native app, pass frozen smoke,
   and commit
   `refactor: remove legacy inline ai generator`.

## Task 17 — Native visual acceptance and durable completion record

**Files**: update this plan status, `docs/design/llm-led-generator.md`, and
`.agents/state.md`; add screenshots only if the repository documentation uses
them as maintained evidence.

1. Run the full verification entry point, build the macOS app, and pass frozen
   smoke with network disabled.
2. Launch the app for owner visual review at wide and 880 px-equivalent sizes.
   Exercise Concepts with fake providers, all loop previews with a fixture,
   Library across relaunch, Settings folder selection, keyboard navigation,
   reduced motion, and explicit Apply/undo. No hardware write.
3. A credentialed live xAI video call is optional and requires a separate
   explicit owner go because it incurs cost. Windows/Linux installer evidence
   comes from CI; report it as pending until observed.
4. Record exact verification evidence, remaining platform/live-provider risks,
   and the separate premium-GIF follow-up. Commit
   `docs: mark video-first lighting studio implemented`.

## Completion criteria

- The primary generation path produces exactly the device-family frame cap from
  the complete one-second source video at 34 ms/frame.
- Every provider-created asset is durably banked before it is shown complete;
  partial/cancelled/interrupted jobs survive restart.
- No paid POST is automatic, retried automatically, or triggered by selection,
  navigation, local resume, preview, Apply, or library browsing.
- Video 1.5 is the default; all curated alternatives and cost estimates live in
  Settings; exact available provider cost is retained in integer ticks.
- Smooth, None, and Ping-pong produce exact frame counts; originals are intact.
- Create never auto-applies. Apply is destination-aware, undoable, document-
  only, and never writes hardware.
- The Library and Settings are useful without a connected keyboard or open
  document.
- The packaged app contains a verified LGPL-only FFmpeg runtime with license,
  source, recipe, and offline frozen smoke proof.
- The UI passes the responsive, keyboard, focus, reduced-motion, and no-autoplay
  acceptance criteria and receives owner visual approval.
- The premium frame-by-frame GIF route remains explicitly parked for its final,
  separate approved plan.
