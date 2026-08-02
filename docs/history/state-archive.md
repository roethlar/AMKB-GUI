# State Archive

## Archived 2026-07-26 by catchup

- Product remediation and its required cross-platform release evidence are
  complete. Manually dispatched Desktop installers run
  `30050985418` passed at head
  `06cb811c2953a64b40b97767ec63aed5e33d8d37` on macOS, Windows x64,
  and Linux x86-64. The generated Windows installer and Linux AppImage both
  passed their installed/frozen smoke and native renderer policy checks; those
  checks found an Ollama/API-only Settings surface and rejected direct-model
  runtimes, manifests, and weights from the bundles. The canonical evidence is
  in `docs/superpowers/plans/2026-07-22-holistic-branch-remediation.md`. Native
  Windows acceptance also proved production preflight repairs a pre-existing
  Library `jobs` directory from broad inherited access to a protected DACL
  containing only current-user, SYSTEM, and Administrators full control.
- The owner corrected the holistic remediation boundary on 2026-07-23:
  governance is a separate product and is updated only in a fresh one-off
  session. P10 and P11 are excluded from the product-remediation plan. The
  governance refresh, bootstrap preparation, bootstrap blocker, and later
  governance-state reconciliation attempted during this remediation were
  reversed; none remains queued under the product plan.
- Product implementation is complete on the current tree; the canonical
  closure ledger is
  `docs/superpowers/plans/2026-07-22-holistic-branch-remediation.md`. The
  2026-07-23 no-provider/no-hardware UI pass covered normal file-open target
  synchronization, every device-family Target control, disabled and ready
  Ollama Settings, independent paint-stroke undo, Library retry, narrow and
  zoom-equivalent layouts, and procedural Review/Apply. It found and closed one
  F01 regression: Generate now opens its modal before the first render instead
  of displaying an empty dialog. The full repository gate, versioned macOS
  `0.1.34` build, frozen offline desktop smoke, signed-bundle verification, and
  built-artifact inspection passed afterward, and the final goal-first
  self-review found no material implementation issue. Shipped AI remains
  fixed-loopback Ollama or curated API only; no application-managed runtime or
  model-management path remains.
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
  P03 is complete on the current tree: the generation dialog shows only the
  destination slot and keyboard target, with no Local/API identity; Settings
  retains backend selection and Library retains cost metadata. The browser
  regression was proven red against the former identity prefix. P04 is complete
  on the current tree: Library asset fetches hold epoch-owned leases, stale
  completions revoke newly created Blob URLs before publication, and an old
  lease cannot clear a refreshed request's ownership. Behavioral and adapter
  regressions were proven red against the prior bare in-flight set. P05 is
  complete on the current tree: new procedural UI, HTTP requests, coordinator
  calls, and manifests contain no ignored loop-mode control. The strict route
  rejects stale clients that send it; older procedural manifests containing the
  field still load; stored settings and legacy-video processing retain their
  compatibility value. Route, Library, and browser guards were proven red. P06
  is complete on the current tree: one device-mapping validator now enforces
  exact source/decoded counts, duration, target set, and per-track frame counts
  for both procedural publication and legacy recovery. Invalid procedural
  mapping is rejected before raster, preview, or mapped assets are banked; its
  regression was proven red. P07 is complete on the current tree: CI runs the
  browser tests and each JavaScript syntax check as independent single-command
  steps, so a Windows native-command failure cannot be overwritten by a later
  success; the regression was proven red against the multiline block. P08 is
  complete on the current tree: PyInstaller disables UPX at both packaging
  stages, the remaining FFmpeg manifest and attestation resolve only through
  validated in-bundle macOS links, and the frozen smoke uses a temporary data
  root, in-memory credentials, and an offline Ollama inventory. Its regressions
  were proven red, and the versioned current-host build plus frozen smoke passed.
  No llama or GGUF runtime is present. P09 is complete on the current tree:
  disabled first paint performs only static capability, settings, and status
  reads; Ollama inventory discovery is deferred until Settings is open or the
  enabled backend is local. The pure browser decision and adapter wiring were
  proven red, while the server regression confirms disabled status touches
  neither Ollama nor the credential store. P12 is complete on the current tree:
  developer artifacts and production banking share one nearest-neighbor preview
  GIF writer with unchanged exact pixels, durations, cancellation, and progress;
  the production wiring regression was proven red. P13 is complete:
  the neutral generation-admission module owns shared errors, target snapshots,
  and the operation gate; procedural generation and server admission no longer
  depend on recovery generation, while recovery keeps compatible re-exports.
  Fresh-process import-order and identity regressions were proven red. P14 is
  closed with evidence: Phase 0 removed the reported duplicate managed-runtime
  transport, the surviving recipe provider delegates to the one hardened
  fixed-loopback Ollama client, and source search plus its proxy, redirect,
  cancellation, and selected-model tests pass. No mismatched abstraction was
  introduced. P15 is complete: the media opener now disables environment
  proxies while retaining explicit same-host redirect validation, and its
  sentinel regression was proven red by an attempted proxy connection before
  the fix. P16 is complete: the shared media budget is enforced after FFmpeg,
  throughout image validation and loop assembly, and across every reversible
  publication boundary. Four regressions were proven red, including atomic
  restoration after cancellation observed the newly swapped directory. P17 is
  closed with executable evidence: historical runtime process/probe symbols are
  absent from shipping source, the deleted modules remain unimportable, and the
  existing architecture guards prohibit managed llama processes, runtime
  attestations, and their setup artifacts. P18 is closed with executable
  evidence: no GPU-offload probe or diagnostic parser survives in shipping
  source, capability polling prohibits model/runtime paths, and readiness
  probes only the selected Ollama or curated API backend. P19 is complete: both
  direct FFmpeg bundle CLI paths force a private temporary `GNUPGHOME`, import
  only the supplied pinned release-key file, verify/build through that runner,
  and remove the keyring afterward. Ambient keyrings cannot override it; both
  regressions were proven red. P20 is complete: atomic store publication now
  fsyncs its containing directory where supported, ignores only explicit
  unsupported-filesystem errors, and remains a no-op on Windows. The parent
  publication and Windows regressions were proven red. P21 is closed with
  executable evidence: no local-model temp, chmod, publication, cleanup, or
  attestation writer survives; its deleted modules remain unimportable; the
  only bundle-artifact reference is a rejection guard; and v4 migration opens
  neither the user's GGUF nor its bytes. P22 is complete: the rejected Qwen
  qualification now links forward to the authoritative Ollama/API-only
  decision and this remediation plan while retaining its immutable comparative
  evidence. R01 is complete: file imports normalize key-layer and macro
  assignment codes before browser-state publication, malformed macro markup is
  rejected, both code-bearing attributes escape their complete value, and the
  CSP regression confirms inline script and external image/connect channels
  remain closed. Both browser safety regressions were proven red. R02 is
  complete: imported static and animated lighting colors normalize to uppercase
  six-digit RGB or fail with a content-free error, and every CSS/property
  boundary repairs noncanonical values to black. Declaration and remote-URL
  payload regressions were proven red. All local implementation findings are
  closed. The separate governance findings are excluded by the current first
  `## Now` entry and the remediation plan's owner-corrected scope.
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
- A 2026-07-24 release-readiness review opened a second approved plan,
  `docs/superpowers/plans/2026-07-24-release-hygiene.md`, covering five
  release-artifact defects (R0-R4) that do not affect application runtime
  behavior. Code signing and notarization are excluded: both require paid
  developer accounts, and `README.md` already discloses the unsigned state.
  R0 is complete on the current tree (`4105552`): two folder-chooser tests
  reached the real lazy `import webview`, which is supplied only by the
  `desktop` optional extra, so they failed under CI's extras-free
  `uv sync --locked` while passing on a developer machine. The failure was
  latent since `2797312` because `ci.yml` triggers only on `pull_request` and
  pushes to `main` and this branch has never opened one, so CI has never run
  against it. Both tests now supply a stand-in `webview` module like every
  other webview-dependent test in that file; no production code changed. The
  full entry point passes in both a CI-equivalent environment (Python 3.12,
  `uv sync --locked`, no extras, `webview` absent) and the developer
  environment, at 376 Python tests with one skip and 43 browser tests. The
  same two errors were the only failures in a CPython 3.11.15 probe, so the
  declared `>=3.11` floor has no known incompatibility.
- The release-hygiene plan is complete at `2d50393`; its canonical closure
  ledger is `docs/superpowers/plans/2026-07-24-release-hygiene.md`. R1 puts
  `LICENSE` and `THIRD_PARTY_NOTICES` into every native artifact, closing the
  MIT notice obligation for the `cyberboard-cli`-derived protocol layer; macOS
  build `0.1.45` passed DMG verification and frozen smoke with both files in
  `Contents/Resources/` and FFmpeg's LGPL material intact. R2 restricts the
  sdist to a root-anchored allowlist, so `uv build` no longer publishes
  `.agents/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, or the internal plan and
  verification documents; the wheel and native bundles were already clean. Two
  guards hold it, one asserting the allowlist and one requiring every tracked
  top-level entry to be classified, so a new directory cannot ship
  unclassified. R3 makes `ci.yml`, `.agents/repo-guidance.md`, and `README.md`
  name an identical four-target `node --check` set. R4 parameterizes the CI
  matrix and adds a Linux Python 3.11 entry. Code signing and notarization
  remain out of scope and unaddressed: both require paid developer accounts.

- The release-hygiene plan is complete; R1-R4 landed in `c4403e3`, `a72e31f`,
  `42b4b92`, and `2d50393`. Opening pull request #1 then ran CI against this
  branch for the first time, because `ci.yml` triggers only on `pull_request`
  and pushes to `main`. `Test · Windows` failed with 23 tests; every other
  check passed, including all three installers.
- The Windows suite repair plan is complete;
  `docs/superpowers/plans/2026-07-24-windows-suite-repair.md` is its canonical
  ledger. Every failure was reproduced on a real Windows 11 host and
  classified: one product defect and ten test defects. The product defect was
  user-facing: `_file_stat_identity` compared `st_ctime_ns`, which a path query
  and an open handle report at different resolutions on Windows for a recently
  written file, so `resolve_asset` and `open_verified` rejected every freshly
  banked asset and no Library media loaded on that platform. `ffmpeg_runtime`
  had the identical defect and was fixed in `3f550a1`; `library.py` was the
  last instance, because the suite had never run on Windows. A diagnostic
  experiment applying that fix alone cleared 11 tests and broke none. The
  Windows suite now reaches `OK (skipped=6)` at 381 tests with identical counts
  across two consecutive runs.

- Two macOS CI flakes were diagnosed after the Windows repair. The DMG one was
  a real race and is fixed in `ad4c035`: `build_dmg.sh` detached the mounted
  image immediately after the smoke-test process exited, with no retry, under
  `set -e`, so a busy volume made the exit trap run `rm -rf` across a still
  mounted read-only image. It now retries with backoff, then forces, and never
  removes an attached mount point; a stubborn mount warns instead of failing
  the build. Verified by a real versioned macOS `0.1.46` build with a clean
  detach. All seven checks then passed on the first attempt at `ad4c035`.
- Asset read cost is addressed;
  `docs/superpowers/plans/2026-07-24-asset-read-cost.md` is its ledger. Serving
  one Library asset hashed the whole file twice, measured at 2.0x the asset
  size, and Range requests paid it on every seek. `resolve_asset` and
  `open_verified` now take `verify_content`; the serving route resolves without
  hashing because `open_verified` re-checks the descriptor actually served
  from, and Range reads additionally skip the digest. Full-file reads per
  request fall from 2 to 1 for a normal view and from 2 to 0 for a Range read.
  Every path, descriptor, identity, and size check is retained, and the
  `owned.path` callers in `generation.py` and `procedural_generation.py` keep
  the verifying default. Accepted risk, agreed by the owner on 2026-07-24: a
  Range read no longer proves the served bytes match the recorded digest, while
  a non-Range read still does. The CPU cost was never the justification and
  must not be cited as one; hashing runs about 2.9 GB/s on the development
  machine. The I/O cost on the Range path is the reason.
- The AI-route timeout flake is fixed. Every `urlopen` in the suite was timed
  against its own timeout: the 2-second and 5-second ones run at 460x headroom
  or better, and only `tests/test_ai_routes.py` was thin at 3.4x, because
  `POST /api/lighting/effects` renders 200 frames, encodes two GIFs, and maps
  them to device tracks before replying, measuring about 4.4 seconds locally.
  It is now a named 60-second constant documented as a hung-server backstop
  rather than a latency assertion. No other timeout needed changing.

- Pull request #1 (`llm-led-generator` into `main`) was green on the first
  attempt at `d74048d` — all seven checks, covering macOS, Windows, and Linux
  tests, the Python 3.11 floor, and all three native installers — and merged on
  2026-07-25. Pull request #2 (`flake-fix`) merged the same day. Work is now on
  `main` at `65a70c9`.
- Do not perform governance work under this product-remediation plan. Any
  governance update requires a separate fresh one-off session.
- The keyboard **stopped enumerating partway through the last session** (zero
  endpoints at `05AC:024F`). Everything after that point was verified against
  stand-ins only. Replug and re-confirm identity before N10.

- Known open work recorded during the review, not yet scheduled:
  `validate_config` (`server.py:537`) still calls `writer.plan` to check that a
  configuration encodes, which is the AM serial wire encoder. It runs with no
  device attached, so it is validation rather than transmission, but a Neon
  configuration would be rejected by it. Needs a per-family answer at N4. See
  `.agents/review/findings/or-1.md` (Known gaps).

## Archived 2026-07-29 by catchup

- The canonical release-version correction landed as `39b5507`. The owner
  approved `0.1.64` after identifying that `0.1.34` would regress below native
  builds that had already displayed `0.1.63`. Runtime/package metadata,
  installer names, tests, install/release copy, README, the issue form, durable
  decisions, and the release plan now agree on `0.1.64`; the `0.1.34` preflight
  is invalidated historical evidence only. Focused red/green proof, both Python
  floors, the cumulative gate, live wide/narrow browser acceptance, and a fresh
  native candidate all pass. `main` was later pushed through `97ed7a2`; no tag,
  release, hardware write, provider request, credential or Keychain access, or
  Reddit post has occurred.
- The AI master-switch and visible-version work is complete on `main`. AI
  enablement now persists as user intent before backend setup is ready; backend
  selection and setup tests cannot change that intent, while generation still
  requires both enabled and ready. Settings shows exactly one styled AI switch
  while off and performs no automatic Ollama discovery; switching on
  immediately reveals Local/API setup and switching off hides it without
  deleting configuration or Library content. The global header displays the
  server-injected runtime version as a distinct `Version <version>` badge.
  Focused persistence, route, setup-ownership, hidden-settings, discovery,
  version, and switch-style regressions were red-proven. The full repository
  gate passes 579 Python tests, 57 web tests, compile/syntax checks, and package
  builds. Native build 59 passes frozen smoke from the signed app and mounted
  DMG; its checksum-verified artifact is
  `dist/AM-Configurator-0.1.59-macOS-arm64.dmg`. An isolated native-window check
  confirms the `Version 0.1.59` badge, the styled off/on states, immediate
  persisted enablement, revealed setup while on, and hidden setup after
  restoring off. No provider request, credential access, model
  mutation/download, or hardware write was performed. The approved and
  completed plan is
  `docs/superpowers/plans/2026-07-27-ai-master-switch.md`; the governing ruling
  is the 2026-07-27 AI master-switch entry in `.agents/decisions.md`.
- AM Neon 80 support is complete on `main`. Merge commit `f3ed88c` integrates
  the former `neon-80-support` branch, which was deleted locally and from
  `origin` after a direct content comparison proved that deleting it would lose
  nothing. Plan tasks N1-N9 are implemented, and `.agents/review/index.md` owns
  the closed, red-proven review scoreboard. N10's physical identity and
  real-GUI enumeration checks pass.
  The GUI read exposed and red-proved fixes for a macOS hidapi thread-affinity
  crash, Vial's empty macro-capacity slots entering the portable document, and
  literal Vial text being misread as HID usage numbers. Commit `25f225c`
  red-proves the literal/tap decoder repair. A GET-only physical read through
  the exact UI API now returns four 90-key layers and four populated macros as
  real press/release transitions, while retaining the separately reported
  16-slot/6677-byte capacity. Native build 53's rendered UI confirms the
  corrected event counts. N10 then exposed that Vial `GET_UNLOCK_STATUS` byte 1
  had been misread as a held-key count even though it is the
  unlock-in-progress flag, and that the app never started or polled the physical
  handshake. The repair decodes the reported matrix combo `(0,0)` + `(0,2)`,
  starts and polls the standard handshake before the first configuration SET,
  names the Neon's physical Esc + F2 positions in the GUI, and prevents Esc
  from dismissing the write dialog. Its red/green repository gate passes 576
  Python tests, 54 web tests, compile/syntax checks, and package build. Native
  build 54 passes its bundled launcher smoke; the artifact is
  `dist/AM-Configurator-0.1.54-macOS-arm64.dmg`. The Neon's per-key lighting
  canvas now projects all 89 axial LEDs onto the 87-key live Vial geometry:
  real row offsets and key widths replace the 19x6 matrix cells, and LEDs
  80–82 form one 7-unit spacebar. A GET-only read through the source-served GUI
  confirmed the rendered rows `17/17/17/13/13/12`, correct modifiers and
  inverted-T arrows. The red/green repository gate passes 576 Python tests and
  55 web tests; native build 55 and its bundled smoke pass, with artifact
  `dist/AM-Configurator-0.1.55-macOS-arm64.dmg`. A build-55 full-write attempt
  passed the typed confirmation and physical Esc + F2 unlock, and the owner
  visually confirmed that it changed the axial/QWERTY lighting. The app then
  stopped during the lighting transfer, before the head/side lighting or any
  keymap or macro SET. Firmware source and hardware behavior proved that the
  Neon echoes accepted lighting packets: response byte 7 is RGB payload, not
  an ACK status, and the terminal packet echo mutates the packet index and
  checksum. Commit `7dc9399` validates that firmware-shaped echo. Its gate
  passes 577 Python tests, 55 web tests, compile/syntax checks, and package
  builds; native build 56 and its bundled smoke pass, with artifact
  `dist/AM-Configurator-0.1.56-macOS-arm64.dmg`. Build 56 accepted the complete
  full write, and the owner reports that the LEDs now match the application. A
  subsequent GET-only diagnostic proved all four keymap layers match exactly
  and isolated the first verification failure to macros: the prepared artifact
  still contained the pre-fix legacy-literal representation, so its
  `10/14/18/17` tap entries read back as `20/28/36/34` transitions instead of
  the previously verified `22/34/38/40`. The original profile's deterministic
  literal/tap distinction has been recovered into
  `/Users/michael/Downloads/AM-NEON80-N10-asymmetric-macro-recovered-2026-07-26.json`
  (SHA-256 `74a92c53c6f341f9d41942236cce76ba2ab67484afb0c0158d20e693cf4aadc5`);
  it passes complete configuration validation and an exact offline Vial macro
  encode/decode round trip at the target event counts. A second build-56 full
  write with that recovery profile completed and verified. The persisted
  `current.json` and newest history snapshot match the recovery document
  exactly: four 90-key layers, eight lighting pages, and macro event counts
  `22/34/38/40`. The deliberate GUI keymap round trip then changed only layer 4
  matrix index 89 from End (`#0007004D`) to F12 (`#00070045`), read back exactly
  that one difference, restored End, and confirmed
  `/Users/michael/Downloads/AM-NEON80-final-readback-2026-07-27.json` is
  semantically identical to the recovery profile. The N6 refusal check selected
  layer 1 matrix key 0 and applied `#000C00E9`; build 56 rejected usage page
  `0x0C` as non-QMK-representable, retained Esc (`#00070029`), and opened no
  write confirmation. The macro-capacity check built a local 17-macro profile
  and invoked the GUI full-write action; validation refused more than 16 macros
  before confirmation or any device SET. After the four-macro local state was
  restored, a fresh device read again rendered event counts `22/34/38/40`. No
  macro plaintext was exposed. The owner's 2026-07-27 photograph closes the
  remaining lighting check: the QWERTY and perforated top display both show the
  asymmetric red/blue/green/yellow corners in the expected orientation, and the
  white center appears only in the authored head matrix. The protocol's “side”
  channel is not underglow; the official driver labels it “side screen lights”
  (`side_screen_lights` / `侧屏幕灯`), and the owner confirms that the physical
  keyboard has no underglow LEDs. It contributes to the same perforated top
  display. N10 is complete. Angry Miao Master, Vial, VIA, and QMK Toolbox are
  not running; UTM offers
  **Connect…** for AM Neon 80, confirming the board is not forwarded to the VM.
  Optional xAI credential access remains deferred; no Keychain prompt occurred.
  The exported device-read JSON is **not an LED backup**: the Neon has no LED
  read-back, and its three custom LED slots in that file are synthetic black
  placeholders. On 2026-07-26 the owner found the original GIF used for the
  current lighting, accepted it as the recovery source, and explicitly
  authorized overwriting the connected Neon's LED setup for N10. A later
  build-59 write exposed a false-success path: the driver incorrectly required
  equal axial/head timeline lengths and silently omitted the populated slot. It
  sent only unchanged empty slots, then keymap/macro verification passed because
  Neon firmware cannot read LEDs back. The official
  `AngryMiao/neon80_driver` behavior confirms that the channel timelines are
  independent. Commit `8eeb684` gives axial, head, and derived side-screen
  channels their own final terminators; commit `bc659a1` makes malformed
  populated slots fail before any SET. Both regressions were red-proven, and
  the full gate passes 581 Python tests, 57 web tests, compile/syntax checks,
  and source/wheel builds. Native build 60 passes bundled and mounted-DMG
  frozen smoke tests; its checksum-verified artifact is
  `dist/AM-Configurator-0.1.60-macOS-arm64.dmg` (SHA-256
  `724e68cfcfda993b904ae393373596b4f14f370a8a4d2a61b430bd3451ebe8d9`).
  A real build-60 write of the unequal-timeline document completed through the
  normal GUI after typed confirmation and physical Esc + F2 unlock, then
  verified keymaps and macros. Persisted current state and history match the
  source byte-for-byte, and the owner visually confirmed that the keyboard
  lighting changed. The exact packet count, document hash, and snapshot are in
  `docs/neon-80-hardware-verification.md`.
  The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and the live hardware
  record is `docs/neon-80-hardware-verification.md`. The proposed scoped-write
  follow-up in
  `docs/superpowers/plans/2026-07-26-neon-led-preserving-writes.md` is withdrawn
  as unnecessary for N10.
- The Desktop installers workflow skips pinned FFmpeg source downloads when the
  exact current-platform runtime cache is restored; the preparation helper still
  verifies the cached runtime before the native build. This closes the Windows
  x64 failures caused by contacting `ffmpeg.org` despite a cache hit. The guard
  was red-proven, and the repository gate passes 578 Python tests, 55 web tests,
  compile/syntax checks, and package builds.
- The owner-approved unified Lighting implementation in
  `docs/superpowers/plans/2026-07-27-unified-lighting-studio-library.md` is
  complete and accepted through slice 17. Catalog schema 2 names the six fixed API
  providers; settings schema 6 preserves the complete xAI record through a
  credential-free v5 migration; provider-scoped vault operations, environment
  overrides, disclosure records, setup fingerprints, capability caches, and
  the bounded JSON transport are in place. Capability polling and setup resolve
  only the selected provider, never access the vault while AI is off or Local
  is selected, and retain the existing xAI request and durable-generation
  behavior. Unknown cost estimates are represented by `null`, while old numeric
  manifests remain valid. Anthropic now has curated Sonnet 5 and Opus 5
  choices, one pinned Messages request with documented structured output and
  fixed effort, complete local recipe validation, refusal/stop handling, dated
  usage-cost estimation, and shared setup/generation registry wiring.
  Provider-specific save/delete rollback, migrations and future-schema refusal,
  selected-provider access, error redaction, transport bounds, Anthropic
  schema/usage/output handling, cancellation, one-paid-request behavior, and
  no-retry behavior were red-proven. OpenAI now has curated GPT-5.6 Sol and
  GPT-5.6 Terra choices, one pinned Responses request with strict structured
  output, disabled storage and streaming, explicit reasoning effort, complete
  local recipe validation, refusal/completion handling, dated usage-cost
  estimation, and shared setup/generation registry wiring. Its request,
  transport, usage, output, cancellation, one-paid-request, and no-retry guards
  were red-proven. Gemini now has curated stable Gemini 3.6 Flash and 3.5
  Flash-Lite choices, one pinned Interactions request with a header-only API
  key, documented JSON Schema projection, disabled storage/streaming/background
  execution, explicit documented thinking levels, complete local recipe
  validation, terminal-status and step handling, thought-inclusive dated
  usage-cost estimation, and shared setup/generation registry wiring. Its
  schema, request, transport, usage, completion, cancellation, one-paid-request,
  and no-retry guards were red-proven. Kimi/Moonshot now has a curated Kimi K3
  choice, one pinned Chat Completions request with JSON-object mode and a compact
  schema-shaped example, the current output-token field, explicit documented
  reasoning effort, exact-one-choice and terminal-stop enforcement, complete
  local recipe validation, cache-aware dated usage-cost estimation, and shared
  setup/generation registry wiring. Its request, transport, cached usage,
  completion, ambiguity, cancellation, one-paid-request, and no-retry guards
  were red-proven. DeepSeek now has curated V4 Pro and V4 Flash choices, one
  pinned Chat Completions request with JSON-object mode and the shared compact
  schema-shaped example, explicit disabled thinking, exact-one-choice handling,
  complete local recipe validation, typed content-filter/resource/stop
  outcomes, cache-hit/miss dated usage-cost estimation, and shared
  setup/generation registry wiring. Its provider isolation, request, transport,
  cache-split usage, finish states, ambiguity, cancellation, one-paid-request,
  and no-retry guards were red-proven. Settings now derives all six providers,
  their model choices, and provider-scoped setup actions from catalog metadata,
  preserving each provider's saved model and using the catalog default on first
  selection. Lighting Studio exposes one inline Generate tool only while the
  selected provider is ready; AI-off and unready states remove that tool and
  the job strip. Procedural generation requires exactly one selected target,
  rejects media/compositor fields, and renders recipes directly at the
  destination raster and frame ceiling before mapping. The detached generation
  dialog and `lighting/create` route are gone. Exact-target, Settings, and
  hidden-tool/job-strip guards were red-proven. Saved-item schema 1 now
  discriminates media sources, lighting compositions, and keyboard profiles;
  publishes their private item directories, asset intents, hashes, and
  manifest atomically; scans current and historical roots with corruption and
  duplicate isolation; and resolves assets only through manifest ownership.
  `LibraryCatalog` projects saved items plus unchanged generation jobs through
  namespaced catalog IDs, pathless detail, pagination, status/kind/
  compatibility filters, and bounded search. Authenticated
  `/api/library/items` and `/api/library/assets/...` reads are additive; legacy
  generation and job-Library routes remain unchanged. Storage, catalog,
  pagination, root, discriminator, duplicate/corruption, asset, API, and
  regression guards were red-proven. A deterministic worker-first guard now
  forces the procedural cancellation race in which the worker persists
  `cancelled` before the cancel-request manifest update. Cancellation accepts
  that terminal state, records `cancel_requested_at`, releases admission, and
  still refuses ready or interrupted jobs; the old behavior was red-proven.
  Library removal now moves exactly one owned job/item UUID directory into the
  same root's private `.trash`, keeps removed detail/assets browseable, restores
  by the inverse rename, and deletes forever only an exact link-free trashed
  directory. Normal and Removed catalog pages are disjoint; live/trash
  collisions, cross-root ambiguity, active operations, nonterminal jobs,
  unsafe ownership directories, links/path escapes, mutation query/body
  fields, and deletion of live content all fail closed. Historical jobs remain
  in their original root, manifest bytes survive remove/restore unchanged, and
  device-history/sibling sentinels are untouched. All removal, restore,
  permanent-delete, active-state, cross-root, link, pathless API, and exact
  deletion guards were red-proven. Canonical device descriptors now expose
  fixed and dynamic keymap signatures, per-target lighting signatures and
  routing roles, and destination limits. Section compatibility independently
  classifies keymaps, macros, and lighting with stable reasons; selected
  exact/portable sections project into one fully revalidated candidate while
  preserving destination identity and unselected content. Unknown Neon layout
  evidence, layer/macro capacity overflow, unsupported Vial assignments,
  lighting mismatches, and invalid candidate documents fail closed. The six
  focused signature/compatibility/projection guards fail against pre-slice
  production code and pass with the implementation restored. Keymap now offers
  explicit profile banking, while Library accepts one or more configuration
  JSON files without changing the open document, device store, or hardware.
  Imported profiles retain the exact source bytes; current mappings retain a
  complete normalized snapshot. Both carry section presence plus device/layout
  signatures, render as mixed-catalog cards/details, and obtain a read-only
  server compatibility preview for the open document. The profile helper,
  import/save endpoints, exact-byte retention, side-effect isolation, and web
  shell guards fail against pre-slice production code and pass with the
  implementation restored. Imported GIF, PNG, and BMP sources now cross one
  authenticated bounded raw-binary route, are signature-sniffed and fully
  decoded before publication, reject APNG, truncation, trailing data, decoder
  warnings, and resource-bound violations, retain their exact original bytes,
  and deduplicate only against a live hash- and byte-verified source. Exact
  version-1 transforms support normalized pan, locked or independent scale,
  black alpha composition, and three sampling modes while preserving the old
  default center-crop result. Pathless transient renders use monotonic editor
  epochs, reverify the owned source and metadata, publish only the existing
  mapped-result shape, leave `.work` empty after completion or supersession,
  and block Library removal/root switching while active. Mapping now transforms
  every validated source frame before resampling the complete timeline under
  the destination family's frame ceiling, so a long GIF cannot silently lose
  its tail. The media validation, transform, asymmetric orientation, complete
  timeline, deduplication, concurrency, source-preservation, epoch, binary
  envelope, route, and no-publication guards were red-proven. The Studio keeps
  its timeline, exact LED canvas, and one right-hand
  Paint/Source/Animate inspector stable while tools change; ready-only
  procedural generation is a fourth inspector tool and remains absent when AI
  is unavailable. The canvas exposes the destination overlay and normalized
  pan/zoom/stretch controls. Pulse, Hue cycle, Sweep, and seeded Shimmer produce
  bounded deterministic local drafts; still-only Move & zoom produces
  normalized transform keyframes. Preview is document-neutral, stale drafts
  fail closed, and Accept replaces the selected track through exactly one undo
  checkpoint while preserving the existing Relic dependent-track retiming
  rule. Manual paint, keyboard frame/pixel navigation, playback, target
  geometry, and responsive layout remain available. The focused compositor and
  Studio-shell guards were red-proven before implementation and pass restored.
  The direct GIF replacement path is now gone: GIF, PNG, and BMP imports bank
  the immutable source first, open one transform draft, render a
  server-authoritative preview, expose the complete mapped timeline for
  selection/playback, and mutate the open slot only through explicit Apply.
  Cancelling retains the source and changes no document data. Render epochs are
  strictly increasing across reopened drafts and equal/stale server epochs fail
  closed. Manual, locally animated, and imported lighting can be saved as exact
  composition assets with preview, timing, brightness, target relationships,
  and source/effect provenance; provenance is retained only while the exact
  applied page is unchanged. Saved lighting reapplication verifies family and
  target signatures, restores brightness, and creates one undo checkpoint.
  Media sources reopen in Studio from the mixed Library. The new browser state
  module is syntax-gated in both CI and the canonical repository gate. All
  slice-15 behavioral guards were red-proven. The heavy procedural recovery
  fixture uses the production 180-second operation deadline instead of a flaky
  test-only override. The mixed Library now exposes All, Sources, Lighting,
  Keymaps, and Removed; generated results and historical jobs share Lighting,
  compatible profile sections apply through one revalidated candidate and one
  undo checkpoint, removal is reversible, pagination and stale-request
  ownership are explicit, and keyboard navigation is retained.
  Frozen smoke now fetches the mixed-Library shell plus its composer, state,
  application, and stylesheet assets. Native policy verifies Local/API, all six
  provider IDs, and hidden AI details while AI is off. The policy server injects
  empty device discovery so browser startup never reaches attached keyboards or
  initializes macOS hidapi; this closes the prior post-success `hid_exit`
  SIGTRAP without bypassing WKWebView. The focused guards were red-proven.
  Browser inspection found and red-proved a 760px header overflow; the header
  now enters its internally scrollable two-row layout at 820px. Follow-up
  browser acceptance also red-proved and fixed independent media-height
  controls, stale async Library-confirmation targets, and the Relic per-key
  canvas. Relic Lighting now uses the exact normalized Keymap geometry: all 87
  physical keys align, and the spacebar is one correctly sized key with three
  independently editable, persistently labelled LED segments (78, 79, and
  80). The interactive pass covered manual paint and keyboard navigation; all
  five local effects; media reopen, pan, locked zoom, stretch, preview, Apply,
  and undo; deterministic fake-provider generation through saved review,
  Apply, undo, and Library banking; partial and fully blocked profile sheets;
  remove, Undo, restore, and delete forever; wide, narrow, 150%-equivalent, and
  reduced-motion layouts. No browser console error or page-level horizontal
  overflow remained.
  The clean full gate passes 666 Python tests, 78 web tests, compile/syntax
  checks, and source/wheel builds. Native build 63 passes bundled and mounted
  DMG frozen smoke, the real WKWebView policy smoke, deep code-signature
  verification, and DMG verification. The artifact is
  `dist/AM-Configurator-0.1.63-macOS-arm64.dmg` (SHA-256
  `f240d3c511e91e51080965a64293b5cd5173d635ffbcf88662da97622384fd8b`).
  No real provider request, credential access or mutation, Keychain prompt,
  model mutation/download, real Library mutation/deletion, hardware write, or
  release occurred during the final acceptance. `main` and tag `v0.1.11` were
  subsequently pushed to `origin`; GitHub CI and all three Desktop installer
  jobs passed at `8b50fb9`.

- The approved 2026-07-28 public-release plan is at
  `docs/superpowers/plans/2026-07-28-public-release.md`. The owner settled that
  installers remain permanently platform-unsigned, the release is normal
  rather than beta/prerelease, and `0.1.64` is the one canonical version.
  Build counters and workflow runs remain provenance only. The plan also
  removes duplicate in-app branding, moves version into an unobtrusive About
  dialog, opens Keymap unconditionally on every launch, adds free hashes/keyless
  provenance, exact-artifact platform and Neon acceptance, corrected public
  documentation, release notes, and a Reddit-safe claim boundary. Release
  identity and the plan landed in `0f18963`; canonical source/package/local/CI
  versioning landed in `4ce7003` with its metadata-test repair in `6a9e1f1`.
  Native-build guidance now agrees that counters are provenance only. The
  duplicate in-content brand/version block is removed, a quiet About dialog is
  the sole normal UI version surface, and launch state now forces Keymap despite
  saved routes or startup hashes while preserving active lighting-job identity.
  The focused server, state, and syntax checks pass. The strict release-metadata helper
  now accepts only the exact three canonical installers, streams deterministic
  SHA-256 metadata, rejects unsafe/ambiguous candidates and conflicting output,
  and keeps workflow run identity as provenance only. The Desktop workflow
  collects metadata only after all installers succeed on `main` push or manual
  dispatch, using immutable `actions/download-artifact` source. Its ten focused
  guards were red-proven and the complete packaging module passes. A separate
  downstream provenance job now owns the only OIDC/attestation write
  permissions, runs solely for `main` pushes, and creates four records for the
  three exact installers plus the manifest/checksum pair with the official
  action pinned to commit `e8998f9`. Pull requests and manual candidates remain
  unable to request an OIDC token. The focused provenance guard was red-proven,
  and public install guidance now includes the `gh attestation verify` command
  without presenting provenance as platform signing. Public documentation now
  sends users only to GitHub Releases, names Neon 80's actual layout, lighting,
  layer, and macro limits, describes the unified Studio/Library and off-by-
  default AI behavior, explains complete writes and absent Neon LED read-back,
  and gives hash/attestation plus narrow macOS, Windows, and Linux launch
  instructions without security-bypass commands. The public-doc guard was
  red-proven and the complete packaging module passes. Screenshot acceptance
  found that the desktop Keymap canvas retained a `260px` minimum height after
  its inspector stacked, forcing an internal page-width clip in narrow windows.
  The responsive grid and keyboard canvas now release that desktop minimum; its
  focused guard was red-proven, and live 720px inspection shows zero document or
  main-workspace horizontal overflow. The README's Keymap, macro, and Lighting
  images are now fresh 1600×1000 captures from isolated public fixtures; the
  macro image uses a generated `Hello, world!` example and the Lighting image
  visibly labels all three Relic spacebar LEDs. Metadata was stripped, its guard
  was red-proven, and full-resolution inspection found no private state. Live
  wide/narrow acceptance also confirmed unconditional Keymap reload, the quiet
  About dialog with `0.1.64`, zero document/main overflow, and no console
  warnings or exceptions. The `0.1.64` release notes and Reddit draft now state
  the exact hardware/OS/provider qualification boundary, installer integrity
  workflow, full-write/LED-readback limitations, and non-affiliation without
  promotional overclaiming. A structured GitHub bug form collects keyboard,
  firmware, OS, version, operation, write, installer, reproduction, and
  sanitized-log context. Both release-packet guards were red-proven and the
  issue-form YAML parses successfully. The cumulative local pre-publication
  gate now passes 685 Python tests on Python 3.13, 81 web tests,
  compile/syntax checks, and source/wheel builds. The Python 3.11 floor
  separately passes all 685 Python tests, compilation, and package builds.
  The first post-push GitHub candidate from Desktop run `30388161235` at
  `97ed7a2` reproduced its manifest/checksums exactly, verified all
  attestations, and passed macOS native checks, but it is rejected: live
  inspection exposed macOS's automatic one-tab strip beneath the normal
  native title bar. No tag or Release was created. Commit `3496bbe` disables
  automatic macOS window tabbing before pywebview creates a window. Its
  regression was red-proven, and exact-path inspection of the rebuilt bundle
  confirms one native window, no accessibility tab-bar role, unconditional
  `#/keymap` startup, and About-only version `0.1.64`. Owner review then exposed
  that globally selectable page text could trap subsequent clicks. Commit
  `621adef` disables native page-text selection and limits CSS selection to
  text inputs, textareas, and editable content. Both native and stylesheet
  regressions were red-proven. Exact-bundle inspection confirms that dragging
  across the Keymap heading creates no highlight and the next Settings click
  works, while text inside the Library path field remains selectable. The
  fresh local artifact is
  `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (25,507,199 bytes,
  SHA-256
  `0aa59150b2821ef48292ae1fc094ee8d3a1e54c997691eb0cd17587304dea557`);
  bundle and mounted-DMG smoke, the real WKWebView policy smoke,
  `hdiutil verify`, and deep strict ad-hoc signature verification pass with
  `Signature=adhoc`, no team identity, and bundle version `0.1.64`. No keyboard
  SET occurred during the rejected candidate's hardware preflight. Its
  GET-only snapshot is
  `~/Downloads/AM-NEON80-release-0.1.64-prewrite-2026-07-28.json` (SHA-256
  `fc1d7a76d8d4dda84077dcc30c4811a22eb4e84f640e7bd7b50f45e7e1d11076`);
  the known LED-bearing restore document remains
  `~/Downloads/AM-NEON80-config.json` (SHA-256
  `745b107a4ae0a6cfd239ff95a9162382cab89cfde426f815b137dc70f55ebb90`).
  The tracked/untracked privacy audit previously redacted one historical
  device serial in `c774cac`; `95f222c` additionally removes the physical
  firmware UID from historical docs and replaces its test fixture with a
  synthetic value. The current tree has no untracked files, `.env` files,
  non-test credential signatures, physical firmware UID values, public
  machine-local paths, or oversized tracked files.
  `actionlint` is not installed, so that optional local check remains for
  GitHub workflow validation. No provider request, credential or Keychain
  access, model mutation/download, hardware write, release publication, or
  Reddit post occurred during the correction preflight. Replacement push,
  final GitHub candidate qualification, exact-artifact hardware acceptance,
  release publication, and Reddit posting retain their explicit gates.
- Three owner-reported Neon regressions are fixed on local `main`. Commit
  `537e570` makes keymap macro triggers protocol-aware: the Neon reports Vial
  protocol 5 and therefore needs the legacy `0x5F12` macro range rather than
  protocol 6's inert-on-Neon `0x7700` range. Commit `7305e0a` adds the Neon's
  separate under-key and top-display lighting controls to the assignment
  palette. Commit `1bd850c` preserves the canonical Neon geometry selected
  during startup so Lighting cannot fall back to a matrix of square cells.
  Focused regressions were added for all three fixes. A GET-only read through
  the exact rebuilt bundle shows the old `0x7700` trigger values as raw
  keycodes on layer 2, while the known LED-bearing restore JSON renders the
  same four positions as semantic Macro 1–4 assignments. The native UI opens
  unconditionally on Keymap, renders the 87-key Neon layout, exposes both
  lighting-control groups, and renders Lighting as the same keyboard-shaped
  geometry with individually labelled LEDs. No write dialog or keyboard SET
  was opened, so corrected macro execution on physical hardware remains an
  exact-candidate acceptance item rather than a completed claim. The clean
  gate passes 687 Python tests (one skipped), 83 web tests, compile/syntax
  checks, and source/wheel builds. Frozen bundle and mounted-DMG smoke, the
  real WKWebView policy smoke, `hdiutil verify`, and deep strict ad-hoc
  signature verification pass. The current local artifact is
  `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (25,629,920 bytes, SHA-256
  `364df91494702bd3945da09a83bbe8a98936112cc250564b6ae207e1700dee89`).
- Desktop run `30414278566` (run 36) and CI run `30414278607` both passed at
  exact commit `6cffe0196e3a778ecb2ac41025cccab6d8d7b948`. Candidate metadata reproduced
  byte-for-byte, all four attestations verified, and the exact macOS and Linux
  packages passed their available native and content checks. The Windows
  install/smoke/uninstall workflow passed and its exact installer has no
  Authenticode Security Directory, but `netwatch-01` remains unreachable for
  the real-host hash, SmartScreen, and About inspection. Exact macOS UI
  acceptance confirmed the corrected window/version/startup/privacy/Neon
  geometry and GET-only read paths. Its temporary Library banked GIF, PNG, BMP,
  manual lighting, and a Neon mapping; exercised transforms, all local effects,
  Apply/undo, source reopen, and exact-compatible lighting apply. Importing a
  valid cross-keyboard profile then exposed that the client still selected the
  removed `profiles` filter rather than the canonical `keymaps` filter. The
  item banked safely, but the Library refresh failed, so run 36 is rejected and
  no keyboard SET, tag, Release, or announcement occurred. A focused guard was
  red-proven against that failure; the local repair now passes 687 Python tests
  (one skipped), 83 web tests, compilation/syntax checks, and source/wheel
  builds.
- Desktop run `30416604544` (run 37) and CI run `30416604729` both passed at
  exact commit `dd891e3ab69101e368a2cb2a57295f9b29765d16`, but exact packaged
  macOS inspection exposed that the media picker's concrete GIF/PNG/BMP MIME
  and extension list disabled valid source images. Run 37 is rejected. The
  repair uses pywebview's Cocoa-compatible `image/*` supertype; its focused
  regression was red-proven against the concrete list. The clean repository
  gate passes 687 Python tests (one skipped), 83 web tests, compilation/syntax
  checks, and source/wheel builds. A clean native build passes frozen smoke and
  DMG verification. Its exact-byte `/Applications` qualification matched the
  build by `rsync -acn`, matched ad-hoc CDHash
  `bbdb6617f28511c047ee69f4ad8329250564394b`, passed deep strict signature
  verification, launched on Keymap, reported `0.1.64` only in About, and banked
  fresh GIF, PNG, and BMP sources with hashes identical to the selected files.
  The owner's installed app was restored after qualification. The current
  local artifact is `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (24,505,055
  bytes, SHA-256
  `d7cfb5e0ae7233396ed990dff4ebd7c5a9667a9dd27920df5b438b76b24bea07`).
  No provider request, credential or Keychain access, model mutation/download,
  keyboard SET, tag, Release, or announcement occurred.
- Desktop run `30419761672` (run 38) and CI run `30419761680` both passed at
  exact commit `f64aa974a047d680c8d04722d3f3fb66293eb79a`. Deterministic metadata,
  all five attestations, exact macOS native checks, available Linux checks, and
  unsigned-Windows package inspection passed. Run 38 is rejected: the packaged
  `accept="image/*"` input still showed valid GIF, PNG, and BMP files with
  **Open** disabled. WKWebView owns HTML file inputs, so pywebview's Python
  wildcard-UTI mapping does not apply. The replacement removes the media
  input's `accept` attribute and retains server-side bounded signature/decode
  validation. Its focused guard was red-proven against `image/*`; the full gate
  passes 687 Python tests (one skipped), 83 web tests, compilation/syntax
  checks, and source/wheel builds. The clean local DMG passes frozen and native
  policy smoke, DMG verification, and deep strict ad-hoc signature
  verification; it reports `0.1.64`, CDHash
  `991ccb95cb09f3d53391dc7ed04a35046b8e36f8`, and SHA-256
  `74090c617f37e1f0eddcea985f0587c120949b81275e9c23d15b1f56e634cc4b`.
  Exact packaged UI acceptance enabled and banked GIF, PNG, and BMP with asset
  bytes matching each selected file. A selected plain-text file was rejected
  by the import endpoint and created no Library item. The temporary app used
  isolated data and Library roots; no provider request, credential or Keychain
  access, model mutation/download, keyboard SET, tag, Release, or announcement
  occurred.
- As of `36f105e`, Desktop run `30421303254` (run 39) and CI run
  `30421303257` passed on `main`. Candidate metadata regenerated byte-for-byte
  and all five attested subjects verified. The exact installer SHA-256 values
  are recorded in the candidate manifest; the Windows installer hash is
  `4966cf1a3fed94822e11fdbf4dca498a7e617beef995ee2435dec8cb2b131622`.
  The exact macOS artifact passed DMG verification, frozen and real-WKWebView
  policy smoke, deep strict ad-hoc signature verification, version `0.1.64`,
  expected unsigned-policy rejection, and packaged-markup inspection. Its
  isolated native UI opened on Keymap, reported `0.1.64` only in About, kept
  AI controls hidden while off with no outbound connection, enabled the native
  picker for GIF, PNG, BMP, and plain text, rendered each supported format in
  Studio, banked exact source bytes, and rejected the text file without
  creating a fourth Library item. The Linux AppImage contains the exact
  repository license, notices, and udev rule, has only expected runtime-sized
  binaries, and exposes no release credential or machine-local-path finding.
  On `netwatch-01`, the exact Windows bytes independently match the expected
  hash and `Get-AuthenticodeSignature` reports `NotSigned` with no signer.
  Windows SmartScreen, normal install, visible About, native-policy smoke, and
  uninstall remain for a Codex session running locally on that host. During
  this qualification the owner requires an immediate stop and report on any
  failed tool, test, gate, or required-host check; do not recover or retry
  before the owner responds. No keyboard SET, macOS Open Anyway action, tag,
  Release, provider credential access, or announcement has occurred. This
  handoff bookkeeping push will move `origin/main` beyond `36f105e` and trigger
  replacement CI/Desktop workflows, so run 39 becomes qualified precursor
  evidence rather than the final release candidate after that push.

## Archived 2026-07-30 by catchup

- The owner approved a two-plan structure on 2026-07-29. Backend correctness is
  `docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md`; product
  experience and user documentation are
  `docs/superpowers/plans/2026-07-29-product-experience-remediation.md`.
  The plans are independently approvable, and backend implementation completes
  before product-experience implementation begins.
- Three admitted plan-review findings were fixed in commits `52261fe`,
  `e596823`, and `ffd7644`: local-animation scope, explicit supersession of old
  Ollama constraints, and a pointer to the canonical verification entry point.
- An approach-first openreview completed through Claude Code MCP with
  `claude-fable-5` at `xhigh` over
  `d77106491edc8d76118bc04ab98ad8b0d3760bb2..ffd76446c4c3e9cf689d11d5c3ac4a0b260e84d3`.
  Capability proof passed and the assessment was `acceptable_with_changes`.
  Its slice-boundary, plan-split, protocol-removal, supersession-style, and
  version-policy recommendations are incorporated in the two plans.
- AgentGovernanceBootstrap issue
  `https://github.com/roethlar/AgentGovernanceBootstrap/issues/11` tracks the
  toolkit bug that made the original openreview contract produce a
  defect-shaped audit instead of an independent approach.
- Slice P4 landed on the product branch: 13px helper-text floor (one
  documented exception: the opt-in keycap matrix overlay), WCAG-checked
  `--control-line` token on interactive borders, readable disabled states,
  top-bar actions moved to a scrollable full-width row at ≤1120px, keymap
  editor single-column at ≤1240px, and a shorter visible Merge label. Guards
  live in `tests/web/design_tokens.test.js` with computed WCAG contrast
  assertions. Two viewports were manually verified live at 1000×680 and
  1280×800 (empty state, chrome, top bar); the full per-screen manual matrix
  with an open document still rides Slice P6. A resize defect initially
  reported from screenshots was disproved: an in-page probe on the same
  pywebview 6.2.1/WebView2 stack reflows correctly on shrink, grow, and
  maximize. The screenshots were cropped by DPI-unaware capture tooling —
  window automation from a DPI-unaware shell process uses virtualized
  coordinates at 125% scale, so captures must multiply sizes by the scale
  factor or the right/bottom ~20% of the window silently disappears.
- The owner then caught a real pre-existing board overflow with an open
  document: `.keyboard-stage` combined `aspect-ratio: 2.95/1` with
  `min-height: 260px`, and CSS transfers that min-height through the ratio
  into an implicit ~767px min-width, so the keymap board spilled out of its
  card and under the inspector whenever the keymap column was narrower
  (roughly 1121-1427px viewports before the P4 breakpoints). Fixed by capping
  the stage at `max-width: 100%`, which clamps the transferred minimum;
  guarded in `tests/web/design_tokens.test.js`. Lesson recorded: per-screen
  manual checks must use an open document — the empty-state pass cannot catch
  document-dependent layout.
- The owner then asked for a holistic fix and connected three keyboards.
  `build_tools/layout_audit.py` now drives the real app read-only (it never
  references the write path), reads each connected keyboard, runs the app's
  own validation, and numerically reports every element that escapes the
  viewport, escapes a non-scrolling container, or is cut by an
  overflow-hidden ancestor, across all routes, Studio tools, lighting
  targets, and four window sizes. First run: CB04, AM21, and ALICE all read
  and validate clean (7 layers, 4 macros, 8 pages each). The audit found one
  systemic layout class — grid rows with `min-width:auto` children blowing
  out of fixed tool columns (`.button-row` 1fr/1fr, `.gif-import-row` 92px
  select track) — fixed with auto-fit wrapping rows and `min-width: 0`
  children, guarded in `tests/web/design_tokens.test.js`. Re-run is clean;
  remaining audit rows are known-benign (`.sr-only` by design; 3-9px keycap
  and Relic-stage border clipping from layout data ending at 100.6%).
- Owner testing on live hardware caught a P2 regression and two
  board-geometry defects. The staged palette Apply was reverted to immediate
  assignment: its confirmation lived in the key inspector, which
  single-column layouts place below the entire palette, so assignments could
  not be changed in practice. The plan's Keymap wording lists "Apply" among
  normal inspector contents; immediate assignment is a deliberate deviation
  after this usability failure — reconcile the plan wording at P6 or by
  owner ruling. RELIC_LAYOUT's right column ended at 100.6% of the stage, so
  the P4 stage clamp cut the PrtSc/PgUp/arrow column; the data now ends at
  exactly 100% with a computed guard. Known gap queued next: CyberBoard
  keymaps render the uniform generic matrix fallback because the app has no
  CB physical layout. Planned approach: dump CB04 matrix occupancy through
  the layout-audit bridge, author CB layout data from standard 75% row
  templates, and have the owner verify against the physical board (the
  cyberboard-cli reference checkout does not exist on this Windows host).
- CB04_LAYOUT is authored in `am_configurator/web/app.js` from the 81 matrix
  cells read off the connected CB04, with geometry measured from the owner's
  board photo after two rejected guesses: 16u wide, clustered F-row (Esc at
  0u; clusters at 1.25u/5.5u/9.75u; Delete+Home at 14u/15u), up arrow at 14u
  leaving the case notch empty at 15u, and 1.25u bottom-row modifiers with a
  6.25u space. `.keyboard-stage.cyber` uses a 2.46:1 aspect because the shared
  2.95:1 stage is sized for the wider Relic and stretches 75% keycaps.
  Verified by extracting every rendered keycap's position from the live app
  rather than by screenshot. Lesson recorded: geometry claims are verified
  numerically from the DOM; screenshots on this host are unreliable because
  the capture process is DPI-unaware and PrintWindow crops rather than scales
  when the window is on a 200%-scaled display — capture at rect*2 and
  downscale.
- Product-experience implementation runs in parallel on
  `claude/product-experience-remediation`, a worktree branch based at the
  shared docs tip `0271213`. Slice P2 is implemented and guard-proven:
  onboarding task cards (Connect a keyboard / Open a JSON profile), contextual
  Merge, Advanced keycode and Show technical labels disclosures with lossless
  raw round-trip, Type text / Record keys as the normal macro path with
  complete event editing under Edit individual events, labelled sidebar
  counts, and focus restoration. Guards live in
  `tests/web/app_shell.test.js` plus the updated empty-state test in
  `tests/test_app.py`.
- Backend Slice B1 is implemented on `codex/ollama-backend-correctness`: schema
  v7 migrates the fixed-loopback v6 record, Ollama accepts one normalized
  HTTP(S) origin, endpoint persistence makes no request, clients are cached by
  origin, and runtime/routes/status/frontend use the atomic `ollama` contract.
  The full automated verification entry point passed after guard proofs showed
  the origin, migration, client-cache, no-request endpoint, and no-alias tests
  fail when their production behavior is removed. No live Ollama request,
  credentialed provider request, or keyboard write was used.
- Backend Slice B2 is implemented on `codex/ollama-backend-correctness`.
  Completion-capable server and Ollama Cloud inventory is selectable with an
  explicit execution location; inventory metadata cannot redirect transport;
  model selection, status polling, and generation do not rediscover inventory;
  non-loopback and cloud data flow requires an explicit disclosure; and setup
  identity binds the normalized endpoint, model identity, execution location,
  and required disclosure. The full automated verification entry point passed.
  Guard proofs showed the cloud-classification, non-probing status/generation,
  non-network selection, location persistence, disclosure, and explicit-only
  browser Refresh tests fail when their production behavior is removed. No
  live Ollama request, credentialed provider request, or keyboard write was
  used.
- Backend Slice B3 is implemented in `a7daff3`. Ollama recipe generation,
  local-animation generation, schema failures, quality failures, and
  cancellation now make at most one model request per explicit action. Retry
  prompts, retry seeds, retry limits, and the `generate_attempt` protocol were
  removed while historical multi-attempt manifests remain supported. The
  focused B3 suite passed 58 tests and the full automated verification entry
  point passed.
- Owner UX finding for Slice P3 (2026-07-29): the lighting saving flow is
  incomprehensible — "render, apply, then save?" with no indication whether
  anything reached the keyboard. P3 must make the Preview → Apply to lighting
  slot boundary uniform, follow every Apply with explicit feedback naming the
  destination slot and document plus the next action (Write to <device> puts
  it on the keyboard), and keep Save to Library visibly distinct as optional
  archival. The hardware-write gate itself is correct and stays; the failure
  was that nothing tells the user where their work went.
- On 2026-07-29 the owner directed merging the backend branch and the product
  branch to `main`. The backend contract (B1-B3) and product Slices P2/P4 with
  their hardware-verified follow-up fixes land together; backend Slice B4's
  native build and executable smoke remain open, blocked only on the missing
  staged FFmpeg sources noted under Next.
- In flight at handoff (2026-07-30, `main` at `31f5700`, working tree clean,
  CI and Desktop installers both green): the owner asked for a GitHub release
  and an r/AngryMiao announcement, and ruled that publishing a release in
  order to test it is backwards — a testable build must come first. Slices
  P1-P5 are landed and verified; P6 (bump to `0.1.65`, closing matrix,
  reconcile the two recorded plan deviations) is the only plan slice left and
  has not been started. The Reddit announcement is drafted but deliberately
  uncommitted, held outside the repo in the session scratchpad as
  `reddit_draft.md`; it needs a resolving download link before posting and
  should be re-drafted from this record if lost. No tag, Release, or
  announcement has been created.

## Archived 2026-07-30 by catchup

- Backend Slices B1-B3 and product Slices P1-P5, including their follow-up
  fixes, are landed on `main`. Backend Slice B4 and product Slice P6 remain
  open. P6 has not started: `am_configurator/_version.py` still reports
  `0.1.64`, and `0.1.65` appears only in the product plan.

## Archived 2026-08-02 by drift

- LSR-1 is closed. Implementation `1ee73a81182c8f401b1942776d3df7c005541f33` and admitted review repair `95795845b6eeabd1c572b82244fef26a975183dd` are fully guard-proven, pass the 677-Python/144-browser/compile/syntax/build gate, and are pushed. The required `claude-opus-5` generation review and T2 per-finding verification used exact ranges once each; `cl-10` returned accepted with guard and capability confirmed. Canonical evidence is in the redesign plan and `.agents/review/findings/cl-10.md`.
- LSR-2 is closed. Implementation `65c9fbfc22c2b24c3b868218512b00039756e6e1` and admitted repairs `9015d422d97d3be0ba9aa04a0ebeeec81c934335` (`cl-11`) and `3865c1008a9798f4d882b2f81c445e7fc2e3261f` (`cl-12`) are committed, pushed, mutation-proven, and pass the complete 688-Python/144-browser/compile/syntax/build gate. The single generation review and both per-finding verifications used `fable-review`, explicit `claude-opus-5` at `high`, exact ranges, and the first substantive result once; both findings returned accepted with guard and capability confirmed.
- LSR-3 is closed. Implementation `92949d92ca6751073ce47fa2b5182c01ed247009` is pushed, mutation-proven, and passes the complete 690-Python/149-browser/compile/syntax/build gate plus the isolated two-viewport native WebView2 destination-transition audit. Exact-head CI run `30735969449` and Desktop installers run `30735969440` passed every platform, metadata, and provenance job. Its one required `fable-review` used explicit `claude-opus-5` at `high` over `b5d46d9402df4d47429b17aaf50326d1307024d8..92949d92ca6751073ce47fa2b5182c01ed247009`; the first substantive result returned clean with exact pins, `capability_ok=true`, no findings, exit 0, and no stderr.
- LSR-4 is closed. Implementation `78bcdcf47ff3a5dcacce555ad31ac14bef95993b` and admitted review repair `abc6826b346420de257d1679879ef84e483c3a81` are committed, pushed, non-vacuously mutation-proven, and pass the complete 691-Python/153-browser/compile/syntax/build gate plus deliberate two-viewport GIF/PNG/BMP native eviction/recovery. The required generation review used `fable-review`, explicit `claude-opus-5` at `high`, and exact pins once; `cl-13` then returned `accepted` in one T2 verification using `claude-opus-5` at `xhigh`, with guard and capability confirmed. Exact repair-head CI run `30738460515` and Desktop installers run `30738460507` passed all nine jobs. Canonical evidence is in the redesign plan and `.agents/review/findings/cl-13.md`.
- LSR-5 is closed. Implementation `7052212445c269752a094217b1ab4813741b2ef7`
  and admitted repairs `1a8632b6b1b2dc4926f848235d10dadd4066e6e5`
  (`cl-14`), `027f2eb18cedd88974ae5a965de2176c0690f801` (`cl-15`), and
  `1b09a2a7d6da087187efbf125c9480cb457e7f46` (`cl-16`) are committed,
  pushed, independently mutation-proven, and pass the complete 694-Python/
  161-browser/compile/syntax/build gate plus all six native GIF/PNG/BMP cases.
  The generation review and all three per-finding verifications used job
  `fable-review`, explicit `claude-opus-5` at `high`, exact pins, and each
  first substantive result once; all returned accepted with guard and
  capability confirmed. Exact final CI run `30743864174` and Desktop
  installers run `30743864148` passed every job. Canonical evidence is in the
  redesign plan and `.agents/review/findings/cl-14.md` through `cl-16.md`.
- LSR-6 is closed. Implementation
  `246da643e95dbc2fc390507264e228cc75051292` and admitted review repair
  `07a1cbe8cf2c7eea56ea4aa27b43dada8a861c1a` (`cl-17`) are committed,
  pushed, and independently mutation-proven. The final complete gate passes
  694 Python tests with 5 skips, 171 browser tests, compile/syntax checks, and
  both package builds; exact repair-head CI run `30746538330` and Desktop
  installers run `30746538320` passed all nine jobs. The isolated native
  WebView2 Effects audit confirmed the five cards, exact Hue-cycle output,
  accessibility floor, reduced-motion representative frame, Apply/Cancel
  boundaries, and document-preserving Cancel; its occluded screenshot is not
  accepted as visual evidence. The generation review and `cl-17` verification
  each used job `fable-review`, explicit `claude-opus-5` at `high`, exact pins,
  and the first substantive result once; `cl-17` returned `accepted` with
  guard and capability confirmed. Canonical evidence is in the redesign plan
  and `.agents/review/findings/cl-17.md`.
- LSR-7 implementation `e7bd1f35110e82e40be2fac27bf0f88aa1c388f7`
  is committed, pushed, and non-vacuously mutation-proven. Its complete local
  gate passes 705 Python tests with 5 skips, 173 browser tests, compile/syntax
  checks, and both package builds; exact-head CI run `30748121792` and Desktop
  installers run `30748121791` passed every platform, metadata, and provenance
  job. Its one required `fable-review` used explicit `claude-opus-5` at `high`
  over the exact landed range once and returned three independently confirmed
  MEDIUM findings: `cl-18` (corrupt remembered evidence cannot self-heal),
  `cl-19` (device rescan drops the trusted deep signature), and `cl-20`
  (connected geometry can overwrite conflicting embedded evidence). All three
  repairs are now independently guard-proven, accepted, and closed; LSR-7 is
  closed.
- `cl-18` is closed in repair commit
  `8e059292411b85a3387d348c8a4ee36ef8137f25`. Its two guards failed against
  the reviewed exception/raw-retention paths and pass after restoration; the
  complete 707-Python/173-browser/compile/syntax/build gate, exact-head CI run
  `30749340460`, and Desktop installers run `30749340465` pass. The one
  per-finding `fable-review` used explicit `claude-opus-5` at `high` once and
  returned accepted with guard and capability confirmed. Canonical evidence is
  in `.agents/review/findings/cl-18.md`.
- `cl-19` is closed in repair commit
  `9ad77c2f6070982250b1a9cd6fb2d555e90daaa4`. The isolated repair keeps a
  validated Neon key layout and its deep
  descriptor/signature paired across shallow device scans; contradictory
  signatures and replacement identities inherit no stale geometry. Its
  descriptor-drop and application-linkage guards fail against the reviewed
  behaviors and pass after restoration. The authoritative stable
  707-Python/175-browser/compile/syntax/build gate, exact-head CI run
  `30750225695`, and Desktop installers run `30750225702` pass. Its one
  per-finding `fable-review` used explicit `claude-opus-5` at `high` once and
  returned accepted with guard and capability confirmed. Canonical evidence is
  in `.agents/review/findings/cl-19.md`.
- `cl-20` is closed in repair commit
  `1d6f101f953d190afeaff72be3b25df34ca140f9`. The isolated repair makes valid
  embedded dynamic-layout evidence own portable export and Library save. A
  matching connected layout retains that
  evidence; a conflicting canonical signature returns one clear error before
  remembered-layout or Library mutation. Its three guards fail against the
  reviewed overwrite behavior and pass after restoration. The complete
  710-Python/175-browser/compile/syntax/build gate, exact-head CI run
  `30751005214`, and Desktop installers run `30751005186` pass. Its one
  per-finding `fable-review` used explicit `claude-opus-5` at `high` once and
  returned accepted with guard and capability confirmed. Canonical evidence is
  in `.agents/review/findings/cl-20.md`. LSR-7 is closed; LSR-8 is next.
- LSR-8 implementation `845f716fdc80741f38ec2161e49e7b775114fe3c` is
  committed and pushed. The
  strict server classifier accepts app-native profiles, recognized AM Master
  full profiles, and AM Master AM 80 lighting-only JSON without using the
  filename; exports remain app-native. Lighting-only imports review both exact
  Head and Per-key tracks offline, can use validated remembered Neon geometry,
  save explicitly to Library without a document, and apply only to an exact
  compatible open Neon slot through one Undo checkpoint. Placeholder, track
  mapping, Apply-signature, whole-selection, shared-playhead, and remembered-
  layout guards are independently mutation-proven. The complete local gate
  passes 720 Python tests with 5 skips, 178 browser tests, compile/syntax
  checks, source and wheel builds, Windows native-tree audit, installer,
  frozen smoke, silent uninstall, and cleanup. Read-only acceptance against all
  seven machine-local originals classified four ALICE profiles (writer plan
  1542 each) and three paired Neon compositions (1/50/75 frames at 90/90/100
  ms); no original filename or LED payload entered the repository. The native
  WebView2 behavior audit confirmed 230 Head LEDs, 89 physical Per-key LEDs,
  exact frame-position preservation, no image-bearing Board descendant,
  offline Save, disabled Apply without a document, and mutation-free Close.
  GPU screen capture was black and is not accepted as visual styling evidence.
  No dependency, FFmpeg/libav path, provider request, credential use, hardware
  write, or release action was introduced. Exact-head CI run `30754260384`
  and Desktop installers run `30754260409` pass every job. The one required
  `fable-review` used job `fable-review`, explicit `claude-opus-5` at `high`,
  and exact pins once; its first substantive result admitted `cl-21` (frozen
  imported arrays make an applied slot uneditable) and `cl-22` (a source-text
  guard pins the associated dead clone block). Both findings are closed below;
  LSR-8 is closed.
- `cl-21` is closed in repair commit
  `864bd28636be781a84d1dfc259a9e0622890d111`. The live document owns mutable
  copies of both imported track arrays while the transient report stays frozen.
  Its executable production-function guard fails against the reviewed shared
  reference and passes after restoration; the complete 720-Python/179-browser/
  compile/syntax/build gate passes with 5 Python skips. Exact-head CI run
  `30755504354` and Desktop installers run `30755504317` pass. Its one
  T2-routed `fable-review` used explicit `claude-opus-5` at `xhigh`, returned
  accepted, and independently confirmed the guard and full gate.
- Owner ruling 2026-08-02: external/cross-harness reviews are exceptional, not
  automatic for every minor change. Use them only on explicit request or a
  concrete material risk that local guards and CI cannot resolve; explain need
  and expected cost before dispatch. `cl-22` receives no Claude review.
- The isolated `cl-22` repair removes the unused imported-lighting candidate
  clone/apply block and reverses its source guard so reintroducing only those
  three lines makes exactly one focused test fail. Restoration passes 42
  focused shell tests and the complete 720-Python/179-browser/compile/syntax/
  build gate with 5 Python skips. Repair commit
  `3b2d26fb48094bf8b804a0449cb968edc2b4b7d9` is pushed; exact-head CI run
  `30756144641` and Desktop installers run `30756144701` pass every job. No
  external review was run under the owner-approved review-economy rule.
  `cl-22` and LSR-8 are closed.
- LSR-9 implementation is landed in the commit containing this state record.
  Media, local effects, imported JSON, procedural results, and saved Library
  lighting now Apply only the exact accepted `BoardFrameSet` through one common
  writer. Relic dependent tracks are derived before Board acceptance. Library
  lighting and generated results first open a read-only physical Board preview,
  while procedural review uses that Board instead of the obsolete raster
  preview asset. The initial focused guard run failed the predicted 12 of 101
  tests; the final focused set passes 102 of 102, including independent
  mutations for exact preview identity and the full-render model capture. The
  complete local gate passes 720 Python tests with 5 skips, 185 browser tests,
  compile/syntax checks, both package builds, the Windows native-tree audit,
  installer build, and frozen smoke. The current source native workflow audit
  reached the saved-lighting Library workflow and then stopped at its obsolete
  direct-Apply selector; updating that audit for Preview on board is approved
  LSR-10 work, so the run is not accepted as native evidence. No dependency,
  FFmpeg/libav path, provider request, credential use, hardware write, or
  external review was introduced. Exact implementation head
  `e4f3d26134dd3926dcc9a559ff62d32877882e91` passes CI run `30762071502` and
  Desktop installers run `30762071501`; all nine platform, metadata, and
  provenance jobs passed. LSR-9 is closed; LSR-10 is next.
- LSR-10 is in progress. Commits `5a6952e` and `b0a1a23` repair two defects
  exposed by the native Library workflow: a saved CyberBoard display no longer
  absorbs the independent per-key timeline, while Relic per-key saves retain
  their required edge companion; Library preview failures remain observable
  until the physical Board has opened. Commit `ed1f454` replaces the obsolete
  direct Library Apply audit with read-only Board Preview, exact DOM-to-frame
  equality, mutation-free Cancel, separate one-call Apply, and one-checkpoint
  Undo. Both production guards were independently red under mutation and green
  after restoration. The simplified source WebView2 audit passes GIF, PNG, and
  BMP at 1000×680 and 1280×800 with no console or layout findings. The full
  Python gate advanced through compile and completed both fresh package builds;
  PTK then lost only the outer transport, so it was not resubmitted. All 185
  browser tests and syntax checks pass. No external review was launched.
- LSR-10 commits `4162f19` and `98a163d` extend that evidence. Closing an
  imported-lighting review no longer calls a shadowed renderer or renders an
  imported-only target against the underlying document; both executable guards
  were red before the repair and green after it. Audit schema v2 adds minimized
  pathless app-native, portable Neon, AM Master full-profile, and AM 80
  lighting fixtures. The passing Windows source WebView2 audit now covers all
  six GIF/PNG/BMP viewport cases plus live Pulse output and parameter changes,
  one Apply/Undo, reduced motion, captured-Blob app-native save/reopen,
  missing-layout Head/Per-key behavior, embedded 89-key Neon geometry, exact
  Head/Per-key re-import, Library save, one Apply/Undo, normalized ALICE open,
  and CyberBoard restoration at 1000×680 and 1280×800. It reports no console or
  layout findings; canonical machine-local evidence is
  `.agents/review/lsr10-source-audit-11.local.json`. All 18 focused Python tests,
  187 browser tests, compile/syntax checks, and both package builds pass. PTK
  lost the full Python suite transport and reported its outcome unknown, so
  that command was not silently resubmitted and is not claimed as evidence.
  No external review was launched.
- LSR-10 automated cross-platform qualification is complete for the current
  shipped-product tree. Windows source and frozen schema-v2 audits pass both
  viewports, all six GIF/PNG/BMP cases, and all ten profile checks; the native
  tree audit, installer build, and frozen smoke pass. The first diagnostic
  frozen run stopped before a viewport at `raw_import_rejected:unknown`; one
  logged run against the identical frozen bytes then passed the complete audit,
  ruling out the suspected Pillow/PyInstaller packaging defect without a code
  change. macOS source WKWebView and mounted-DMG audits pass the same schema,
  strict signature/native-tree/smoke checks pass, and the mounted app matches
  the built 157-entry bundle manifest. Linux exact-head `b9b481a` source and
  frozen WebKitGTK audits pass, as do frozen smoke and both the PyInstaller-tree
  and extracted-AppImage native audits; the 108,919,288-byte AppImage has
  SHA-256 `efcfdeaa9b65ab60eb4a0a28ebc6fa2c059fcc1506fe34ce1cfa182086594c16`.
  Commit `b9b481a` also classifies the governance-owned `.codex` directory as
  deliberately excluded from packages after the existing top-level classifier
  caught the refresh omission. Its focused guard moved red to green, and the
  complete current-head gate passes 727 Python tests with 5 skips, 187 browser
  tests, compile/syntax checks, and both package builds. The only diff from the
  Windows/macOS qualification head `a53d0e3` is that packaging test; shipped
  inputs and dependency files are identical. No dependency, FFmpeg/libav path,
  provider call, credential use, hardware write, or external review was added.
  Exact shipped-product head `f5cc91c` passes CI run `30766621303` on Windows,
  macOS, Linux Python 3.11, and Linux, while Desktop installers run
  `30766621302` passes Windows, macOS, Linux, candidate metadata, and release
  provenance. Only the owner's final visible Windows acceptance pass remains
  before LSR-10 can close.
- The one final LSR-10 material `fable-review` used literal `claude-opus-5` at
  `high` over pinned range `ca8d7b8..b9b481a`, returned two findings, and was
  preserved and used unchanged with no retry or re-review. Both independently
  reproduce and are admitted: `cl-23` (MEDIUM) finds the app-native round-trip
  native check can pass before reopen; `cl-24` (LOW) finds Close retains the
  review destination instead of the user's pre-review destination. The prior
  platform qualification and visible Windows build are reopened until both
  repairs are mutation-proven and the affected gates are repeated. Canonical
  records are `.agents/review/findings/cl-23.md` and `cl-24.md`.
- `cl-23` repair `2d450b6` makes the app-native reopen check load-bearing: the
  focused contract moved red to green and a deliberate import short-circuit
  makes the real native audit fail exactly at `app_native_reopen_timeout`.
  `cl-24` repair `e738bb6` captures and restores the pre-review destination;
  its executable open/switch/close guard moved red to green and all 43 Lighting
  shell tests pass. The complete repaired-head gate passes 727 Python tests
  with 5 skips, 187 browser tests, compile/syntax checks, and both package
  builds. Repaired-head Windows source/frozen schema-v2 audits, native-tree
  audit, installer, and smoke pass; the installer is 17,545,528 bytes with
  SHA-256 `95321e1cb56e8bb22fb552c724c9f1598c68753e8c405b45539aa46f775fed23`.
  Linux source/frozen schema-v2 audits, native-tree and extracted-AppImage
  audits, and smoke pass; its 108,919,288-byte AppImage has SHA-256
  `c0cb7214cd2a3f9d9e5aa6a09d8ceae26fcd7173044e0484779e432ac1b568b5`.
  macOS exact-head build, DMG checksum verification, strict signature,
  native-tree audit, smoke, and 157-entry manifest equality pass; the
  22,612,851-byte DMG has SHA-256
  `2e41fff767668765706734466470e95f4bd04b4d5a41232309873195a328aac4`.
  Its schema-v2 audit is the sole remaining platform gap: SSH activation and
  Accessibility click both leave WKWebView without document focus, so one real
  owner click in the rebuilt DMG window is required. No further Claude review
  is authorized.
  Exact shipped-product head `dbf1b2b` passes CI run `30768142979` on all four
  test jobs and Desktop installers run `30768142977` on Windows, macOS, Linux,
  candidate metadata, and release provenance.
- The owner approved the Windows-first imported-media correction recorded in
  `docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md` on
  2026-08-01. IMF-1 is implemented, locally verified, and clean-reviewed:
  Python
  and the browser share exact canonical geometry vectors, normal and Move &
  zoom renders intersect every requested target's limits, the backend returns
  the exact canonical state it used, and the browser adopts it atomically. The
  rejected same-size 40x5 pan now clamps to zero and retains the complete
  source raster. Its focused and complete CI-equivalent gates pass; canonical
  evidence is in the repair plan. Its single required `fable-review` run used
  `claude-fable-5` at `xhigh` over exact implementation commit `4a9e6b8` and
  returned clean with no findings. No dependency or prohibited path changed.
- IMF-2 is implemented, locally verified, and clean-reviewed. The
  source overlay remains mounted for an active media draft and now uses the
  primary destination's exact resolved raster box; only that viewport clips,
  leaving the LED grid and destination border intact. Pointer, wheel, keyboard,
  preset, zoom, stretch, and sampling changes reveal source view before one
  canonical commit path invalidates Preview and updates controls/status
  synchronously. Primary-pointer sessions are ID-scoped and stage-scoped,
  release on up/cancel/lost capture, and continue without error when synthetic
  capture raises `NotFoundError`. Its focused 134-web/181-Python gate and red
  proofs pass. Its single required `fable-review` run used `claude-fable-5` at
  `xhigh` over exact implementation commit `041c26f` and returned clean with
  no findings. No dependency or prohibited path changed.
- IMF-3 is implemented, locally verified, and clean-reviewed. Pathless
  asymmetric GIF/PNG/BMP fixtures now drive one isolated native PyWebView audit
  through import,
  framing, exact Preview pixels, Apply/Undo, the complete Library ownership
  workflow, and Cancel. Source and exact rebuilt frozen WebView2 audits pass at
  1000x680 and 1280x800 with no console or layout findings; the Windows build,
  native-tree audit, installer build, and frozen smoke pass. The visual audit
  activates its real native window before asserting focus; a deliberately
  hidden launch fails the explicit focus precondition and is not valid evidence.
  The canonical full command chain reached and produced both valid `uv build`
  archives after every guarded test/compile/syntax stage returned zero, but PTK
  lost its outer transport immediately after artifact creation and no duplicate
  run was submitted. Its single required `fable-review` used `claude-fable-5`
  at `xhigh` over exact implementation commit `25c58d5` and returned clean with
  no findings. Post-repair qualification then passed: the controlled current
  Windows package install, recursive prohibited-native-code audit, frozen
  smoke, and uninstall were clean, with no install directory left; exact-head
  CI run `30699525122` and Desktop run `30699525134` attempt 1 passed every
  required job at `875437ab432462d0c88ee73733d1d84e65261cfe`. No dependency or
  prohibited path changed.
- Review finding `cl-2` is verified at
  `d77ca6e61a84c4bc01deb5fc3f3367ab8325022b`: live and removed retired-video
  jobs share one unsupported classification, and remove, restore, and
  permanent deletion reject them both before and after lock acquisition
  without changing stored bytes. A pinned `claude-opus-5` review independently
  reproduced both red/green guards and accepted the slice.
- Review finding `cl-3` is verified at
  `72a1e41889243819f4c27036693f150b15b95859`: the Node 24 plan now names
  the exact retired provenance-action commit, making its future absence guard
  non-vacuous. A pinned `claude-opus-5` review independently reproduced the
  manual base/head proof and accepted the slice. The original `cl-1` through
  `cl-3` review set is closed; the two record-drift findings raised by the A1
  implementation review are also closed below.
- CyberBoard switch lighting now projects the canonical 81-key CB04 Keymap
  geometry through the firmware LED map instead of rendering a uniform 15×6
  raster. The function-row gaps, wide keys, three-segment spacebar, and arrow
  notch share the Keymap footprint and 2.46:1 stage; the 40×5 top display stays
  rectangular. The geometry guard was red before the repair and green after;
  the owner accepted the corrected native view, and the full gate passes with
  646 Python tests, 127 web tests, compile/syntax checks, and the `0.1.65`
  source/wheel build.
- CyberBoard review finding `cl-6` closed at `0b6778f28482a664047df4ee0d830f9da1524a6f`:
  the target-split guard fails when the 83-LED switch layout replaces the
  200-cell display and passes with the repair. The owner explicitly waived a
  second paid Claude call after the full gate passed.
- Windows CI on `791ca06d9012235f9f6af842275e568004bbe418` exposed a pre-existing
  manifest-lookup race: lookup read a manifest before taking the per-object
  lock, so Windows sharing contention could be misreported as a missing job.
  Repair `2e92b62ac0736376a37045b88c8ba043dab8b9dc` locks generated-job and
  saved-item manifest validation. Both deterministic guards were red before
  the repair and green after it; all 645 Python tests, 125 web tests, package
  checks, and 300 Windows stress iterations pass. Its one required
  `claude-opus-5` review completed but the verdict envelope was lost after the
  outer MCP caller timed out; `.agents/review/outcomes.md` records the failed
  pass, and the owner ruled out a paid rerun.
- The GitHub Actions Node 24 upgrade is complete. Slice A1 landed at
  `7586bf7daab187a158a5c929cafcb80f9af97d10`; its exact dependency guard,
  full local verification, and required `claude-opus-5` review passed. Exact
  implementation-commit CI and Desktop runs then passed without Node 20 or
  action-runtime warnings, and artifact, SLSA provenance, and qualified Windows
  install/smoke/uninstall acceptance all passed. Exact evidence lives in
  `docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md`.
- Review finding `cl-4` is verified at
  `c443f03605e93e0f288a6d9e0f8ff5d5d1b4d487`: the canonical state now names
  the exact landed A1 commit and A2 acceptance instead of retired refs and a
  settled approval gate. A pinned `claude-opus-5` review independently
  reproduced the manual base/head proof and focused dependency guard.
- Review finding `cl-5` is verified at
  `227019705bacfe89862a24bbbe4349176b487818`: the Node 24 plan now names exact
  A1 commit `7586bf7daab187a158a5c929cafcb80f9af97d10` and the A1/A2 qualification
  sequence instead of a settled approval gate. A pinned `claude-opus-5` review
  independently reproduced the manual base/head proof and passed all 51
  packaging tests. The A1 review loop is closed, and A2 has since completed.
