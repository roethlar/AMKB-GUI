# Repository State

## Now

- The holistic branch review was committed in `e2ba095`, and its complete
  remediation ledger was committed in `8faa962`. The owner then corrected the
  release direction: shipped AI is fixed-loopback Ollama or curated API only.
  Direct GGUF selection, bundled or application-managed llama.cpp, GPU
  qualification, and every associated build/package/release path are
  superseded and must be removed. The durable decision and remediation plan now
  own that correction. The owner approved the revised plan on 2026-07-22;
  Phase 0 / F49 is complete on the current tree: active settings migrated to
  Ollama/API-only schema v5, GGUF readiness migrates to unselected Ollama
  without opening the model file, and the native picker, route, browser surface,
  capability branch, and product smoke invocation are gone. Phase 0 / F20 and
  F21 are also complete on the current tree: the managed llama server/provider,
  process and GPU-probe lifecycle, executable managed-runtime smoke, and their
  tests are gone; a negative architecture guard now prohibits their process,
  credential, and argv construction paths from returning. Phase 0 / F34 is
  complete on the current tree: the llama builder, source/cache workflow,
  runtime attestation and model-selection modules, package data, macOS
  finalization, and direct-local provider label are gone. Frozen packages retain
  FFmpeg and reject direct-runtime binaries or model weights. Phase 1 / F01 is
  also complete on the current tree: procedural Review uses the authenticated
  Blob URL map, renders every reducer block reason and loading state, and guards
  Apply as a one-shot action under executable reducer/DOM coverage. Phase 1 /
  F05 is complete on the current tree: CyberBoard, Relic, and AFA target controls
  are created as valid DOM buttons with preserved pressed/locked state and
  executable selection coverage. Phase 1 / F10 is complete on the current tree:
  a strict authenticated sync route stores an immutable validated document,
  browser open/read/restore paths hold its opaque revision, and generation
  rejects missing or stale revisions before using the server-derived target. The
  F30 is complete on the current tree: disabling AI preserves a tested
  backend's fingerprint, and re-enabling recomputes current Ollama model or API
  credential validity server-side without another inference; changed or
  missing models and changed credentials remain invalid. The next slice is
  F31 is complete on the current tree: each lighting paint stroke owns fresh
  pointer-up/cancel cleanup, creates its own undo checkpoint, and cannot be
  started by merely entering the grid with a held pointer. The next slice is
  F03 is complete on the current tree: Library reconciliation returns separate
  safe-resume actions and pathless errors, contains recovery/lock/mutation/work
  cleanup failures per job, continues healthy jobs, and permits the loopback
  server to bind despite damaged current or historical jobs. The next slice is
  F04 is complete on the current tree: banked-video recovery projects every
  source/frame/preview/mapping/status/progress field before mutation, skips an
  already-consistent manifest, retains an existing completion timestamp during
  genuine repair, and leaves normalized-in-memory v1 bytes untouched. The next
  F13 is complete on the current tree: transient settings I/O and newer schema
  versions return distinct pathless statuses without renaming or overwriting
  exact bytes, updates fail closed with typed errors, and only confirmed
  encoding/JSON/schema corruption enters quarantine. F17 is complete on the
  current tree: blocked legacy migrations now report credential-vault and
  settings-write failures separately, every ordinary settings mutation remains
  fail-closed, and a strictly confirmed recovery action can atomically publish
  credential-free v5 settings without reading or changing the OS vault. The
  Settings route exposes that recovery only for a vault-blocked legacy
  credential and otherwise keeps mutable controls inert. F18 is complete on the
  current tree: every v1-v4 projection is normalized through the active v5
  validator before migration, invalid projections return a stable pathless
  blocked status, and exact source bytes plus any prior vault value remain
  untouched. F19 is complete on the current tree: one shared credential-shape
  validator rejects controls, surrounding whitespace, and oversized values
  before storage; malformed pasted, environment, legacy, or vault values report
  the stable pathless `credential_invalid` reason without secret content; and
  actual vault outages and settings-write failures retain separate typed errors.
  F23 is complete on the current tree: procedural cancellation proves operation
  ownership before entering the manifest mutation, accepts only an in-progress
  procedural job under its lock, and leaves ready or interrupted manifests
  byte-identical when a cancel loses the completion race or targets an inactive
  job. F24 is complete on the current tree: startup reconciliation treats an
  already-interrupted procedural job as terminal, preserves the first
  interruption or failure completion time, settles a banked failed attempt
  without reclassifying it, emits no unused local retry action, and leaves the
  exact manifest bytes stable on every later startup. F61 is complete on the
  current tree: a failed FFmpeg process exposes only a stable typed/pathless
  exception message while retaining its bounded stderr tail solely on the
  in-memory exception, so decoder prose, relative staging names, URLs, local
  paths, and credentials cannot enter `manifest.json`. F02 is complete on the
  current tree: Ollama chat and setup inference use a direct fixed-host HTTP
  connection with no proxy or redirect layer, poll cancellation and deadline
  every 50 ms, shut down the active socket/connection on either condition, and
  discard any late response. The real provider/coordinator regression proves
  cancellation releases the shared gate without banking late output. F25 is
  complete on the current tree: direct procedural startup reconciliation owns
  the shared operation lease across library recovery, scan, and every manifest
  mutation; a busy caller receives the same typed admission failure as legacy
  recovery; and every exceptional path releases the lease. The next slice is
  F26's removal of the server-level release/reacquire window between the legacy
  and procedural reconciliation passes. F26 is complete on the current tree:
  `_State.reconcile_lighting` acquires one admission lease, passes its validated
  unforgeable token through both coordinators, and releases it only after the
  combined pass; direct coordinator calls still acquire their own lease. A
  concurrent generation can run before or after recovery, never in the
  handoff. F27 is complete on the current tree: the response snapshot is read
  before launch, launcher failure leaves no worker and releases admission, and
  launcher acceptance atomically marks the lease worker-owned before any later
  bookkeeping can fail. A post-launch failure cannot admit a second operation
  or make the live job uncancellable; only worker exit releases the token. The
  next slice is F28's synchronization of lazy AI service and provider
  construction. F28 is complete on the current tree: `_State` publishes one
  capability service under concurrent requests, and that service constructs
  one cached provider per Ollama/API configuration identity, replacing the API
  provider when its credential fingerprint changes. Provider cache clearing is
  synchronized, and the existing architecture guard continues to prohibit any
  managed llama singleton or process path. F33 is complete on the current tree:
  rendering, quality analysis, preview work, frame-wise GIF encoding, LED
  mapping, and mapped JSON encoding all share the operation's monotonic deadline
  and cancellation predicate. Cancellation and timeout release admission from
  inside local frame work, and durable `rendering`, `quality_check`, and
  `banking` phases publish throttled frame-relative progress while provider work
  remains indeterminate. F11 is complete on the current tree: disabled and
  backend-unselected capability status performs no backend probe, while enabled
  status contacts only the selected fixed-loopback Ollama or curated API
  credential backend. Unprobed public fields remain schema-compatible and
  conservatively unverified, and a source guard excludes every managed model or
  runtime path from capability polling. F14 is complete on the current tree:
  local authentication rejects non-ASCII header values before constant-time
  comparison, then compares only explicit ASCII byte representations. Raw GET
  and POST requests with a latin-1 token receive the same JSON 403 as every
  other invalid token without a handler traceback or dropped connection. F15 is
  complete on the current tree: all unexpected loopback GET/POST and nested
  native-bridge failures flow through one generic pathless 500 response, while
  logs retain only the exception type. The accepted-device-write 409 retains
  its accepted/retryable recovery contract but no longer serializes verification
  or device details. F16 is complete on the current tree: the remaining legacy
  credential routes require exact request bodies and an idle shared admission
  gate, use the server's injected credential store for every settings, vault,
  and provider operation, and inherit the generic pathless unexpected-failure
  response. The regression fails against the prior production behavior and
  passes with the hardening restored. F22 is complete on the current tree:
  every curated API POST, status GET, and legacy key probe now shares one
  response-bounded and deadline-bounded transport that pins exact
  `https://api.x.ai` versioned URLs without an explicit port, query,
  credentials, or fragment. Its dedicated verifying opener ignores environment
  proxies and refuses 301/302/303/307/308 redirects, so Authorization cannot be
  forwarded to another origin. The origin/proxy regression fails against the
  prior transport and passes with the hardening restored. F43 is complete on
  the current tree: an otherwise valid local `/api/tags` model entry without
  capability metadata yields the stable `upgrade_required` discovery and
  setup reason, while a genuinely empty inventory or an explicit
  non-completion model remains an ordinary empty eligible list. Settings tells
  the user Ollama must be upgraded. Discovery still uses only `/api/tags`, and
  generation only `/api/chat`; no `/api/show` or model-management operation was
  added. The client, capability, and browser regressions all fail with their
  deciding branches removed and pass after restoration. F08 is complete on the
  current tree: Ollama and curated-API openers are constructed under explicit
  HTTP/HTTPS proxy environments, their real discovery/request paths have socket
  creation intercepted before network I/O, and the tests prove the attempted
  destinations remain fixed-loopback Ollama and `api.x.ai`, never the sentinel
  proxy ports. Removing either empty `ProxyHandler` makes its regression target
  the sentinel and fail. F09 is complete on the current tree: model inventory
  normalization, picker projection, and refresh-failure handling live in the
  executable pure browser-state module. The projection distinguishes available,
  empty, unavailable, upgrade-required, selected, removed, digest-changed, and
  transient-failure states; retains a valid previous choice and cached model
  options across a failed refresh; and disables stale choices until discovery
  succeeds. The adapter renders the projected disabled missing-model option and
  specific recovery guidance. Removing those branches makes both behavioral
  regressions fail. F36 is complete on the current tree: the disabled, curated
  API, and Ollama desktop AI smoke helpers execute in-process under traps for
  real sockets, provider transports, OS credentials, local-model settings,
  subprocesses, and serial hardware. Counters prove the disabled status path,
  both production provider adapters, and both render/mapping passes actually
  execute; a no-op Ollama smoke makes the regression fail. The test also proves
  no advanced direct-model smoke remains. F37 is complete on the current tree:
  the remaining source-substring smoke assertion is gone, and executable guards
  prove both recipe providers are constructed, both render/mapping paths run,
  and disabled status, construction, rendering, and mapping failures propagate.
  F38 is complete on the current tree: the authenticated model discovery and
  selection routes now have an integration regression through the production
  capability service, fixed-loopback client parser, and `OllamaModel.public`
  projection. It covers unavailable and malformed inventories, a missing model,
  exact public metadata, and persistence of the discovered name and digest. F39
  is complete on the current tree: independent regressions reject name/model
  mismatch, bare cloud suffixes, each remote marker, missing completion support,
  malformed size/digest/name, and prove the exact 512-model bound plus discovery
  404 mapping. F40 is complete on the current tree: a selected model replaced
  under the same Ollama name but a new digest becomes unavailable, reselection
  makes the new identity verified but setup-required, and only a successful new
  setup writes its fingerprint and restores readiness. F41 is complete on the
  current tree: the coordinator and real Ollama recipe adapter stop after one
  initial call plus two corrected retries across schema and quality failures,
  use three deterministic distinct seeds and correction prompts, persist the
  terminal failure, and release admission. The curated API path remains exactly
  one request without automatic retry. F44 is complete on the current tree: the
  Ollama plan's status names every F08/F09/F36-F41 remediation commit and owns
  one canonical ledger of the exact focused command, temporary production
  mutation, expected failure, restoration, and passing result for each guard.
  The historical Ollama state entry points to that ledger. F50 is complete on
  the current tree: removed local-model and llama-runtime attestation modules
  are non-importable, shipping sources and package data reject their schemas,
  readers, writers, and capability dependencies, and frozen smoke refuses both
  legacy metadata filenames. FFmpeg's separate attestation system remains
  explicitly allowed. F54 is complete on the current tree: even with a zero GPG
  exit code, the detached-signature verifier accepts exactly one well-formed
  uppercase `VALIDSIG` for the pinned fingerprint and rejects absent, wrong,
  lowercase, short, overlong, duplicate, and mixed records. F32 is complete on
  the current tree: procedural raster and preview GIFs now use deterministic
  exact per-frame palettes, reject a frame above GIF's 256-color limit before
  writing, and decode pixel-identically across all four supported raster
  geometries. Mapping the decoded raster or preview produces the same device
  tracks as mapping the source. F47 is complete on the current tree: FFmpeg's
  image2 output argument escapes every literal percent in the owned staging
  path while retaining exactly one `%04d` filename conversion. End-to-end
  processing now succeeds under Library roots containing `%`, `%%`, `%d`,
  `%04d`, spaces, and Unicode. F48 is complete on the current tree: video
  replacement still prefers a hard-link backup, but unsupported Windows link
  semantics and hard-link-incompatible filesystems fall back to a private,
  cancellation/deadline-aware, fsynced byte copy. Publication failure restores
  that copy and cleans both backup and partial download under the same rollback
  contract. F06 is complete on the current tree: the Windows workflow consumes
  `setup-msys2`'s actual installation output, derives every GPG/Bash/compiler
  path from it, and prepends its native tool directories for the PowerShell
  process. Generated profile-less Bash commands also set
  `/usr/bin:/mingw64/bin` explicitly. F07 is complete on the current tree: the
  obsolete Windows Vulkan SDK installation is gone, and a release-workflow
  guard prohibits any Vulkan setup from returning now that direct GGUF runtime
  builds have been removed. F12 is complete on the current tree: release entry
  points, platform packagers, the desktop workflow/spec, and FFmpeg build tools
  are guarded against any llama, GGUF, or GGML build-command or timeout path.
  F35 is complete on the current tree: Linux packaging downloads immutable
  appimagetool 1.9.1 assets, verifies the official per-architecture digests,
  rejects unsupported architectures explicitly, and caches by version plus
  digest. F52 is complete on the current tree: each frozen platform build runs
  two isolated real-renderer probes against one private loopback origin to
  verify private storage, token-history cleanup, an empty browser bridge,
  downloads, CSP, loopback loading, and Ollama/API-only Settings. Authenticated
  loopback handlers now own native actions without exposing pywebview methods
  to page scope. The actual local WKWebView probe passed. F53 is complete on
  the current tree: the sole remaining runtime source extractor rejects a colon
  in every archive path segment, closing Windows drive-relative and NTFS ADS
  forms before path construction while retaining absolute, UNC, traversal, and
  link rejection; the retired llama extractor is guarded absent. F55 is complete
  on the current tree: macOS finalization verifies the original prepared FFmpeg
  attestation, reproduces PyInstaller's deterministic ad-hoc signature on a
  private copy, requires the bundled bytes to match exactly, verifies the code
  signature, and records both hashes, the signing identity/CDHash, recipe,
  configure arguments, capabilities, manifest, and prepared-attestation hash.
  It no longer re-blesses behavior-compatible replacement bytes. The real local
  signed bundle passed the new relationship check. F57 is complete on the
  current tree: Windows Python 3.11 detects every reparse point through
  `st_file_attributes`, Python 3.12 retains its native junction check, and
  preflight rejects a reparse-bearing raw root before resolution or directory
  creation. F58 is complete on the current tree: Windows preflight now creates
  and removes the deepest real asset-intent atomic temporary path before job
  creation and before further paid work, reports an actionable path-length
  error for Win32 error 206, and is covered at the classic 259/260-character
  boundary plus a long-path-aware case. F60 is complete on the current tree:
  the developer qualification helper no longer imports subprocesses, accepts a
  direct model file or runtime, or exposes the GGUF retry harness; its remaining
  explicit CLI is non-production fixed-loopback Ollama only. The direct-model
  tests are gone, while the rejected Qwen JSON/gallery remain unchanged and
  their README labels them historical evidence that normal tooling cannot
  regenerate. F51 is complete on the current tree: runtime, build, source, and
  macOS-finalization FFmpeg JSON/hash reads now delegate to one regular-file
  verifier with no-follow open, Windows reparse rejection, pre-read size caps,
  and descriptor/path identity checks before and after reading. Runtime
  compiler identity is capped at 1,000 characters, with its regression proven
  red when the limit is removed. F56 is complete on the current tree: Library
  and settings atomic publication use one bounded Windows replacement helper
  that retries sharing/access violations without changing the same-directory
  atomic boundary. Simulated concurrent readers prove a banked asset remains
  attached to its manifest, settings updates settle, and persistent contention
  stops at the configured bound. F59 is complete on the current tree: POSIX and
  Windows job-file locks now share one nonblocking monotonic ten-second budget,
  asset verification checks descriptor and path identity before and after
  hashing, and public resolution performs large-file hashing outside the
  exclusive manifest lock before rechecking ownership and identity under lock.
  F29 is complete on the current tree: unreachable concept, image, and video
  planning/submission entry points and providers are gone; the active catalog
  contains only curated recipe models; and obsolete model/candidate preferences
  are rejected while frozen private v2 migration data preserves old settings.
  Historical accepted-video polling, download, local processing, cancellation,
  and banked-asset recovery remain, while retired mutation routes stay at 410
  without provider access. An architecture guard prevents the removed surface
  from becoming importable or configurable again. F42 is complete on the
  current tree: the obsolete key-save and no-cost key-test routes, their probe
  transport/injection seam, and the raw-key `_lighting_settings` helper are
  gone. Authenticated stale routes return 404 without vault or provider access;
  the current credential route retains strict admission and now triggers
  historical recovery when a key becomes available. F45 is complete on the
  current tree: `device_mapping` now owns canonical device families, raster
  layouts, frame caps, timing, generation specs, and frame-to-LED conversion.
  The HTTP server and lower-level generation, procedural, recovery, media, and
  qualification paths delegate directly to that module, while an architecture
  guard prevents reverse imports from those lower layers into the server. F46
  is complete on the current tree: one pure recipe-inference module now owns
  Ollama temperature, output cap, prompt-derived per-attempt seeds, sanitized
  retry correction, and the fresh two-message request shape. Both the shipped
  provider and retained Ollama developer/qualification client use its exact
  payload, with an anti-drift guard against redeclared parameters. The new
  contract test was proven red before implementation by the missing module;
  no model was invoked or downloaded. P01 is closed as an evidence-only
  duplicate of F42: a repository-wide definition/call search confirms the raw
  `_lighting_settings` helper has no surviving resolver or caller, while the
  current capability's credential resolver remains scoped to the secure store.
  P02 is complete on the current tree: default credential discovery no longer
  caches a failed OS-keyring construction, retries on later resolution, and
  caches only the first adapter that validates as a built-in secure backend.
  The recovery regression was proven red against the process-lifetime cache.
  The next slice is Phase 10 / P03's removal of backend identity from the
  generation dialog.
- The owner approved the product decisions for a video-first Lighting Studio,
  recorded in `.agents/decisions.md`, and authorized implementation of
  `docs/superpowers/plans/2026-07-20-video-first-lighting-studio.md`. Task 1,
  the curated catalog and lossless settings migration, landed in `bec8413`;
  Task 2's durable generated-asset library landed in `352271e`, followed by
  the fail-closed Windows private-directory runtime guard in `4e3c6de`; Task
  3's bankable concept-planning and still-generation providers landed in
  `ae20186` and passed review after focused fixes through `57ec851`; Task 4's
  structured video planner and asynchronous image-to-video contract landed in
  `f9f5cab` and passed review after focused fixes through `88776d0`; Task 5's
  hardened temporary-video downloader landed in `deca3d5` and passed review
  after focused fixes through `8798a68`; Task 6's signed-source, reproducible
  LGPL FFmpeg build/runtime verification and exact-frame animation processor
  landed in `3cbe33c`; Task 7's durable, single-operation concept coordinator
  landed in `0ecf7c8` and passed review after owning-root preflight and canonical
  target-validation fixes through `b243d22`; Task 8's durable video, recovery,
  exact-frame local processing, mapping, and cancellation orchestration landed
  in `9ece907` and passed architecture review after focused durability fixes
  through `bd5f121`; Task 9's authenticated durable Lighting and Library API
  landed in `cf393b5` and passed architecture/security review after startup
  recovery, shared admission, error-redaction, and deferred-reconciliation
  fixes through `9751f72`; Task 10's routable, responsive Lighting
  Create/Library/Edit shell, persistent job surface, extracted manual editor,
  and pure browser state landed in `39cd7ca` and passed state and visual review
  after focused fixes through `14423bd`. The owner subsequently rejected its
  bulky Create-first presentation. The approved Task 10R reset restored the
  manual editor as the default, removed duplicate Open/Devices affordances,
  demoted AI generation to a secondary dialog, and made the canvas-first editor
  responsive and keyboard-operable in `24c7764` and `fbac041`. The full
  repository verification entry point passed at `fbac041` with 256 Python tests
  and 26 browser-state/static tests, including the prepared real FFmpeg runtime
  integration check for every supported device frame cap. The macOS app bundle
  was rebuilt through the versioned builder, passed frozen smoke, and launched
  with the Relic profile for owner visual inspection. No provider or hardware
  call was made.
- The temporary legacy 1–8 animation-frame adapter was removed from Generate in
  `78e236f`. Generate now treats 1–8 as separately banked still-concept outputs
  (saved default four), uses the durable Concepts job and authenticated asset
  routes, keeps candidate slots stable while polling, makes selection local
  only, and never exposes provider-call counts or auto-applies. Accepted paid
  jobs are persisted before status polling; transient/stale polls and concurrent
  asset loads fail safely. The full verification entry point passed at
  `78e236f` with 256 Python tests and 27 browser tests. Versioned macOS build
  `0.1.15` passed frozen smoke and was visually checked at 1440×920 and 520×720
  with the Relic profile; no provider or hardware call was made.
- Task 11's full Provider/Models/Storage/Costs Settings route and restricted
  native folder-chooser/Reveal bridge landed in `2797312`. Settings now saves
  keys, curated models, still-count and loop defaults, and the current Library
  root through independent routes; Done returns to the originating route and
  restores an open Concepts dialog. The first manifest-backed Library browser
  slice landed in `70e01ba`: it lists/filter/searches durable jobs, loads
  authenticated local thumbnails and detail media as Blob URLs, and works
  without a document. A malformed-effective-key redaction hole found during
  live acceptance testing was closed in `2e4d474`.
- The folder picker's packaged-page dependency on the injected JavaScript
  bridge was removed in `7ac492f`; Choose folder and Reveal now dispatch through
  authenticated native loopback routes, retaining the injected bridge only as
  a browser-only fallback. The production page and route opened a real macOS
  folder panel in a source-build probe. The full repository verification entry
  point passed at `7ac492f` with 263 Python tests and 29 browser-state/static
  tests. Versioned macOS build `0.1.19` passed frozen smoke and DMG verification
  and was launched with the Relic profile; host accessibility policy prevented
  an automated click in the frozen GUI. The preceding `0.1.18` live xAI
  Concepts acceptance check completed with one still banked locally,
  visible/selectable in Concepts, browsable in Library detail, and retained
  across Settings → Done. Provider-reported cost was $0.0227244. No key was
  persisted and no video or hardware call was made.
- The owner's saved Relic concept job demonstrated that generic `20:9` safe-band
  steering still produced cinematic landscapes whose detail could not survive
  an `18x7` LED raster. Concept planning now receives exact device geometry and
  binds every paid still prompt to a flat, high-contrast emissive texture in
  `569e244`. Animation now pixel-reduces and banks the exact selected source
  sent upstream, deterministically constrains every video prompt to a fixed
  one-second closed LED cycle, and gives each loop mode explicit endpoint motion
  rules in `e7dd78d`; the offline integration adapter was updated in `a94f86d`.
  The full verification entry point passed at `a94f86d` with 267 Python tests
  and 29 browser-state/static tests. Versioned macOS build `0.1.20` passed frozen
  smoke and DMG verification. No provider or hardware call was made.
- Task 13's missing concept-to-animation handoff and complete Review/Apply flow
  landed in `dc807e2`. Selecting a saved concept now exposes an explicit local
  transition into motion and loop controls; only Generate animation starts the
  paid video operation. Polling carries the same durable job through saved-video
  local retry, exact LED/source/frame review, compatibility revalidation, and a
  single undoable document-only Apply. Task 15's verified current-platform
  FFmpeg preparation, native bundling, signed macOS re-attestation, and offline
  real-MP4 frozen smoke landed in `624cccc`. The full verification entry point
  passed at `624cccc` with 269 Python tests and 30 browser tests. Versioned macOS
  build `0.1.23` passed DMG verification and processed the fixture at all three
  device frame caps from the frozen app. No provider or hardware call was made.
- Task 14's first actionable Library bridge landed in `0792ceb`. Every banked
  concept now exposes `Animate this concept` when the open document is
  compatible; it restores the durable job, selects that exact still, and opens
  Animate without a provider request. The owner's eight-concept Relic job
  `281044bf-b560-456c-85b9-37456c0b60dc` was checked against this path. Full
  verification passed with 269 Python tests and 31 browser tests. Versioned
  macOS build `0.1.24` passed frozen media smoke and DMG verification and was
  launched with the owner's Relic profile. No provider or hardware call was
  made.
- The owner paused broader UI work until the paid AI path is proven end to end.
  Commit `581e058` reduces Generate to one linear proof flow: prompt, exactly
  one banked still, click the still to open Animate, then explicitly start the
  video request. The stage bar, quantity control, selection handoff panel, and
  extra concept-generation action are absent; the saved multi-concept job still
  remains usable. Full verification passed with 269 Python tests and 31 browser
  tests. Versioned macOS build `0.1.25` passed frozen media smoke and DMG
  verification and was launched with the owner's Relic profile. No provider or
  hardware call was made.
- Library acceptance exposed two false UI stalls in `0.1.25`: Animate required
  an open document even though a saved job owns a complete device-target
  snapshot, and a failed media fetch remained visually stuck at Loading.
  Commit `6b9ff3f` permits saved-still animation without a document while
  retaining document compatibility as an Apply-only gate; Library assets now
  retry once and then expose an explicit Retry action. Both JPEGs in job
  `ef25e4ab-c0f3-4791-a11c-e6d209ec61c9` were verified present with matching
  sizes and SHA-256 hashes. Full verification passed with 269 Python tests and
  32 browser tests. Versioned macOS build `0.1.26` passed frozen media smoke and
  DMG verification and was launched without a document to reproduce the
  owner's Library context. No provider or hardware call was made.
- The owner rejected the visual usefulness of the xAI video result and approved
  an isolated local procedural-animation proof, with no application UI work.
  The approved plan landed in `8d33771`; the strict Ollama recipe client,
  deterministic periodic renderer, exact GIF/LED artifacts, and offline guards
  landed in `c6d46cc`, followed by the proven-model default correction in
  `2078a0b`. `gemma4:12b-mlx` ignored the structured-output contract;
  `ornith:latest` produced the validated shooting-stars recipe. Visual
  inspection caught and closed a full-board wash failure: the same recipe now
  renders sparse bright comet trails on black at exactly 18×7, 200 frames, and
  34 ms per frame, with an ordinary loop seam. Full verification passed at
  `2078a0b` with 276 Python tests (one prepared-runtime integration skip) and
  32 browser tests. No xAI call, UI change, app build, or device write was made.
- A second local proof used the unchanged Ornith-to-procedural pipeline for a
  six-layer dense aurora field. The exact 18×7, 200-frame result kept at least
  91.3% of raster positions above the visible threshold in every frame, showing
  that the local recipe path can produce full-board motion rather than leaving
  most keys dark. The owner approved a release direction in which AI is off and
  absent from the main UI by default, then becomes available only after either
  an app-managed local GPU model or a curated API model passes setup. The
  durable implementation plan is
  `docs/superpowers/plans/2026-07-21-optional-ai-backends.md`, committed with
  the approved decision record in `ca13f11`. Task 1's shared versioned recipe
  contract, deterministic renderer, density/brightness/motion/seam quality
  gate, exact GIF/device mapping adapters, qualification corpus, and offline
  qualification helper landed in `d7eedc2`. The extracted renderer produced
  200 byte-identical frames against the prior implementation for the saved
  Ornith aurora, which passed the new dense quality gate and both Relic mapping
  tracks without inference. Full verification passed at `d7eedc2` with 285
  Python tests (one prepared-runtime integration skip) and 32 browser tests.
  Task 2's pinned Qwen3 4B Q4_K_M candidate qualification landed in `9780945`.
  The exact 2,497,280,256-byte model and llama.cpp `b9637` runtime were verified
  and run offline with all 37 model layers on the owner's M4 Max GPU. Only 6 of
  12 corpus cases passed the unchanged schema and quality gate within two
  retries, so the candidate is rejected and no release local-model catalog was
  created. The machine-readable results and exact-raster pass galleries live in
  `docs/verification/2026-07-21-qwen3-4b-q4-k-m/`. Full verification passed at
  `9780945` with 288 Python tests (one prepared-runtime integration skip) and 32
  browser tests. No provider call, UI change, app build, or hardware write was
  made. The owner then clarified that corpus qualification must not gate local
  AI: local inference is the primary backend, the application must never
  download model weights, and users choose their own GGUF file. The amended
  durable plan makes Task 3 the pinned runtime and private user-selected model
  flow. Task 3 landed in `d748898`: the exact llama.cpp `b9637` source recipe,
  static GPU builds, runtime attestation, private user-owned GGUF selection,
  tamper detection, pathless status, bounded process handling, and strict
  full-offload probe are implemented without a model catalog or weight
  lifecycle. The verified-source build produced an attested macOS arm64
  runtime, and the already-present Qwen file was used only as a runtime smoke;
  Metal reported all 37 layers offloaded. The official llama.cpp advisory list
  was checked on 2026-07-21: `b9637` is beyond all published fixed-version
  boundaries, and the remaining unpatched RPC advisory is outside the compiled
  build because `GGML_RPC=OFF`. Full repository verification passed at
  `d748898` with 298 Python tests (one prepared-runtime integration skip) and 32
  browser tests. No model was downloaded, copied, modified, or deleted; no
  provider call or hardware write was made. Task 4's schema-v3 settings and
  secure credential boundary landed in `8721681`: Library roots and loop mode
  survive migration, obsolete model/count preferences are removed, and valid
  v1/v2 plaintext credentials move to a fixed platform OS credential backend
  only after exact read-back. Failed migration or final settings publication
  leaves the original v2 bytes untouched and restores any prior vault value;
  active settings and browser responses contain no key or credential-derived
  substring. Full repository verification passed at `8721681` with 309 Python
  tests (one prepared-runtime integration skip) and 32 browser tests. Tests
  used injected memory storage; no production credential read/write, provider
  call, model download, native app build, or hardware write was made. Task 5's
  local-first recipe providers and sole capability/readiness gate landed in
  `07260ea`. The managed local provider launches only the pinned authenticated
  loopback runtime with the current private model attestation, disables proxies
  and redirects, permits one slot, bounds output/lifetime, terminates on
  cancellation, stays warm only for a short idle, and exposes a coordinator-
  owned maximum of two deterministic retries. The secondary xAI provider makes
  exactly one bounded strict-schema request and retains exact reported cost,
  including after cancellation. Setup fingerprints bind runtime/model or
  provider/model/credential/disclosure identity; a later bad local recipe is a
  per-generation failure and leaves local readiness intact, while transient API
  failures do not invalidate prior setup. Full repository verification passed
  at `07260ea` with 326 Python tests (two prepared-runtime integration skips)
  and 32 browser tests. A separate prepared-runtime smoke used the already-
  present Qwen file only to prove authenticated grammar-constrained server I/O
  and clean shutdown; it did not qualify the model, alter the user's selection,
  or gate the feature. No model was downloaded, copied, modified, or deleted;
  no external provider call, credential-store write, native app build, or
  hardware write was made. Task 6's read-compatible manifest v2 and durable
  procedural coordinator landed in `2c5b6b6`. Historical v1 manifests normalize
  only in memory and remain byte-preserved and browseable until a real update;
  procedural jobs bank the exact recipe, 200-frame fastest-duration raster,
  preview, mapped LED result, quality evidence, and usage record. Local schema
  or quality failures may retry twice within that generation and never revoke
  readiness. API work remains one-call, and startup recovery adopts fully
  banked artifacts without replaying an interrupted API request. Full repository
  verification passed at `2c5b6b6` with 335 Python tests (two prepared-runtime
  integration skips) and 32 browser tests. No model was downloaded or invoked;
  no provider call, credential-store write, native app build, or hardware write
  was made. Task 7's authenticated optional-AI setup and procedural-effect API
  landed in `f45d529`. The native picker accepts an existing regular GGUF but
  its path-returning method is private to the loopback server and cannot enter
  browser JavaScript; setup and generation share one admission gate. The server
  owns backend verification and derives each active device family's raster,
  mapping targets, maximum frame count, fastest duration, and selected model.
  Historical job, Library, asset, and cancellation surfaces remain; obsolete
  xAI still/video mutations return stable local `410` responses without calling
  their providers. The frozen smoke path now exercises the production managed-
  local recipe adapter against a fake runtime. Full repository verification
  passed at `f45d529` with 338 Python tests (two prepared-runtime integration
  skips) and 32 browser tests. No model was downloaded or invoked; no external
  provider call, production credential-store write, native app build, or
  hardware write was made. Task 8's hidden-by-default setup and procedural UI
  landed in `5e6e8c4`. Disabled first paint exposes no generation control
  outside Settings; Local is the primary setup panel and accepts any existing
  user-selected GGUF through the private native chooser, with no model catalog
  or download action. The secondary API panel keeps credential, disclosure,
  provider, and model repair state in Settings. Ready users get one prompt,
  durable progress that can be closed without cancellation, an animated exact-
  raster review with recipe summary, and one explicit undoable document-only
  Apply. A failed selected model remains selected and can be retried or replaced
  without disabling local support. Historical Library media remains browseable,
  while the retired still/video browser calls and continuation UI are removed.
  The full repository verification entry point passed at `5e6e8c4` with 338
  Python tests (two prepared-runtime integration skips) and 22 browser tests.
  New first-paint and procedural-projection regressions were each proven red
  with their implementation temporarily removed. No model was downloaded or
  invoked; no external provider call, production credential-store write,
  native app build, or hardware write was made. Task 9's native llama.cpp
  packaging and offline release checks landed in `8c9017e`. The versioned
  builder produced macOS arm64 `0.1.27`; the signed app and DMG passed frozen
  smoke with AI disabled, fake local and API recipe adapters, deterministic
  render/mapping, real FFmpeg media processing, and loopback UI loading. The
  bundle's final signed `llama-cli` and `llama-server` bytes match their
  attestation, the pinned manifest and MIT notice are present, and direct scans
  found zero GGUF weights, private settings/model-selection files, or credential
  patterns. The already-present Qwen3 4B Q4_K_M file then passed a non-gating
  real local smoke through temporary private selection, 37/37 Metal layer
  offload, strict recipe generation, exact rendering, and Relic mapping; the
  model file was not downloaded, copied, changed, or deleted. Full repository
  verification passed with 341 Python tests (two prepared-runtime integration
  skips) and 22 browser tests. Historical Library acceptance is covered by
  those Python and browser suites. Headless Playwright then rendered disabled
  and ready Settings at 1440×920, 520×720, and a 150%-equivalent zoom viewport,
  plus the Library gate in both states. It found no console errors, horizontal
  overflow, or clipped interactive controls and confirmed Generate is absent
  when disabled and present when ready. Visual inspection found the Local/API
  labels touching their descriptions; `f264f31` separated those label lines and
  added a regression proven red before the fix. The same Playwright matrix and
  full repository gate passed afterward. No external provider call, production
  credential write, model download, or hardware write was made.
- Task 16 removed the superseded inline xAI generator in `a441ecf`. The
  interpreter/image renderer, 16-keyframe tween path, ephemeral worker,
  operational status route, pending/refine browser state, and dead tests are
  gone; authenticated legacy generation routes remain stable local `410`
  tombstones. Shared provider transport/image validation, manual GIF import,
  device mapping, settings key test, procedural generation, and frozen smoke
  remain covered. The full repository gate passed on that tree with 316 Python
  tests (two prepared-runtime integration skips) and 22 browser tests. Versioned
  macOS arm64 build `0.1.28` passed signed-app/runtime checks, DMG verification,
  and frozen offline smoke. The video-first plan is complete through Task 17;
  the later optional-AI plan owns the shipped local-first product direction.
- A Grok whole-change openreview of
  `98abb138406093dacea97df2b49be91aa11fdf10..6c1f7337d162eb59015265690e88a5d02d7be962`
  reported no material issue; provenance is recorded in
  `.agents/review/outcomes.md`.
- Ollama-first Local AI landed in `57fb05a`, `440c5ac`, `6815337`, `8021ecf`,
  and `9f2174a`. Settings now discovers eligible models already installed in
  fixed-loopback Ollama and lets the user select one by name. That landed slice
  kept direct GGUF under a collapsed advanced fallback; the current first
  `## Now` entry supersedes that historical product scope. Cloud aliases are
  excluded, model selection is bound to Ollama's current digest, and production
  code has no model-
  management operation, and Ollama readiness is independent of the bundled
  llama.cpp runtime and GPU probe. A real temporary setup and full procedural
  generation through the already-installed `ornith:latest` model recovered
  from one malformed response with the bounded retry, then banked a dense
  200-frame Relic result with recipe, raster, preview, and mapped assets; the
  seven-model eligible inventory was unchanged before and after. External
  Playwright checks at 1440×920 and 520×720 covered available, selected, and
  unavailable states without console errors, clipping, or horizontal overflow;
  Playwright is not an application dependency. Full verification passed with
  324 Python tests (two prepared-runtime integration skips) and 22 browser
  tests. Versioned macOS arm64 build `0.1.29` passed signed runtime checks, DMG
  verification, and frozen smoke of the offline Ollama, advanced GGUF, API,
  media, and loopback UI paths. No model was downloaded, copied, changed, or
  deleted, and no hardware write was made. The surviving Ollama/API-only
  behavior was later red-proven in `7ded2dc`, `ed53fa2`, `3eec04c`, `37a7449`,
  `2186a62`, `d42f01e`, `267dc56`, and `9ae2306`; the exact commands and
  temporary failing mutations are canonical in the Ollama plan's
  `Regression Guard Evidence` section.
- The nested `cyberboard-cli/` checkout remains ignored reference material
  and is not part of the application.

## Next

- Implement the approved holistic remediation plan one finding per commit,
  continuing with Phase 10 / P03's removal of backend identity from the
  generation dialog.
  Do not push or dispatch workflows before the local remediation and verification
  gates pass.
- After remediation and a separate outward authorization, verify Windows
  x86_64 and Linux x86_64 packages as Ollama/API-only builds and prove they
  contain no llama binary, GGUF execution path, model picker, model-selection
  private state, or model weight.
- Carried over: address any failures surfaced by the committed CI and
  desktop-installer workflows; continue hardware verification across
  CyberBoard, Relic 80, and AFA firmware variants using portable JSON
  backups.

## Blockers

- Hardware checks require corresponding owner-supplied devices; they are not
  required for the offline suite.
- Native Windows ACL verification for a pre-existing library `jobs` directory
  remains required before a Windows release. New directories are private on
  supported patched CPython runtimes, and older runtimes fail preflight before
  touching the configured root.
