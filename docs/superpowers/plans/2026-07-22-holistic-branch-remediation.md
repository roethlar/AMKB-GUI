# Holistic Branch Remediation

**Status:** Approved by the owner on 2026-07-22. Drafted from the committed holistic review at
`.agents/review/2026-07-22-holistic-branch-review.md`. The owner authorized a
plan covering every actionable item, then corrected the product scope to
Ollama/API-only. This revision contains no pending product decision.
Implementation is authorized under the one-finding-per-commit rules below.

## Objective

Bring `llm-led-generator` from review head `89d194d` to a releasable state by
closing every actionable defect, regression gap, architecture debt, packaging
risk, documentation drift item, and residual hygiene issue recorded by the
2026-07-22 holistic review. Preserve the approved editor-first, hidden-until-
ready product direction and every device, credential, model-weight, durability,
and explicit-Apply safety boundary. The only shipped AI backends are
fixed-loopback Ollama and the curated API.

This plan is the canonical closure ledger. The review report remains immutable
evidence. Each checklist item is updated in the same commit that closes that
item; `.agents/state.md` points here instead of duplicating counts.

## Scope

The complete scope is:

- numbered findings F01–F61 from the review, including F61 even though the
  review labels it a nit;
- polish items P01–P22 from the review;
- residual hygiene items R01–R02 identified inside the refuted findings;
- no implementation for the four refuted failure scenarios themselves.

The two refuted items with no residual defect (`desktop.create_window` cleanup
and the deliberately narrow `js_api` bridge) remain closed by the review's
existing evidence. R01 and R02 address only the real escaping/validation gaps
left after their overstated security outcomes were refuted.

## Authoritative Inputs

- `AGENTS.md` and `.agents/repo-guidance.md` govern process, verification, Git,
  device safety, and toolkit-owned artifacts.
- `.agents/decisions.md` owns approved product behavior.
- `docs/superpowers/plans/2026-07-21-optional-ai-backends.md` and
  `docs/superpowers/plans/2026-07-22-ollama-first-local-setup.md` record the
  implemented optional-AI architecture. The current decision and this plan
  supersede every direct-GGUF or managed-llama release instruction in them.
- `.agents/review/2026-07-22-holistic-branch-review.md` owns the finding text,
  evidence, severity, refutations, and polish inventory.
- Current code and focused reproductions are evidence for behavior. If a
  finding cannot be reproduced or its cited code has changed before its slice,
  stop that slice and record the evidence instead of manufacturing a change.

## Release Backend Correction

The 2026-07-22 Ollama/API-only decision is unconditional:

- Remove direct-GGUF selection, setup, generation, private model state,
  attestation, and model-file handling from the active product.
- Remove the managed llama.cpp provider/server, GPU qualification, bundled
  binaries, builders, manifests, notices, signing rules, workflow setup, frozen
  smokes, and release branches. Retain FFmpeg and its independent provenance
  boundary.
- Keep historical GGUF qualification evidence as explicitly superseded history
  only. No normal test, build, package, or release command may invoke it.
- Keep fixed-loopback Ollama as the primary backend and the curated API as the
  secondary backend. The application never manages Ollama models.
- Disable environment proxies and reject redirects for curated API transport;
  do not add configurable endpoints or proxy settings.
- Remove loop-mode choice from new procedural generation UI and requests
  because the renderer is inherently periodic. Preserve stored legacy values
  and historical video behavior for compatibility.

Every review concern tied to GGUF or managed llama is closed by deletion or by
evidence that the deleted path cannot enter a release artifact, not by adding a
new fallback or hardening that obsolete path.

## Non-Negotiable Execution Rules

1. One finding or polish item per commit. A commit contains its production
   change, focused regression, red-proof evidence update, and this plan's single
   checkbox update. It must not close an unrelated item.
2. Duplicate root causes still receive separate closures. The first commit may
   repair the shared mechanism; a later item closes its distinct caller,
   contract, test, or dead-code consequence without reintroducing redundant
   implementation.
3. Before each slice, re-read the cited finding and inspect current code. Never
   rely only on the report's line numbers after earlier commits move code.
4. Every new behavioral test is proven non-vacuous by temporarily restoring the
   pre-fix behavior, observing the focused test fail, restoring the fix, and
   observing it pass. Record the exact red and green commands in the commit body
   or the plan checkbox note.
5. Run focused tests after every slice and the full repository gate after every
   phase. A failed gate blocks the next phase.
6. No provider call, model download/copy/change/delete, credential-store access,
   native workflow dispatch, push, or hardware write is authorized by this
   plan. Real provider, hardware, or outward CI work requires a separate go.
7. Use temporary roots and injected stores/transports for destructive, fault,
   migration, recovery, and concurrency tests. Tests never touch the owner's
   Library, credentials, model selection, Ollama inventory, or keyboards.
8. Toolkit-owned files are never edited directly. P10 is routed through the
   governance toolkit owner and refresh workflow; P11 is executed through the
   repo's `drift` operator.
9. Do not rewrite existing history. Each item lands as a new commit. Do not push
   until every required local phase is green and the owner separately invokes
   the Git push operator.

## Shared Verification

Run the repository gate from the root after every phase:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/app.js
uv build
```

Native packaging changes additionally require the versioned builder on the
current host and frozen smoke:

```sh
uv run --frozen python build.py --skip-sync
```

The build's normal signed-app/installer verification must pass. Windows and
Linux claims remain unverified until the committed desktop workflow runs on
those hosts after separate outward authorization.

## Phase 0 — Remove the Superseded Direct-GGUF Product

Complete these deletion slices first, keeping the full repository gate green
after each commit. Historical evidence remains readable, but no active product,
build, or release path may depend on it.

- [x] **F49 — Remove direct-GGUF product state and surface.** Delete the native
  GGUF chooser, setup/generation routes, browser controls, capability source,
  local-model selection/attestation writes, and active settings fields. Advance
  the settings schema only if current evidence requires it; migrate an existing
  GGUF selection to an unselected Ollama state with AI not ready while
  preserving Library roots, API configuration/disclosure, loop compatibility,
  and all unrelated settings. Never open, hash, copy, mutate, or delete the
  user's model file during migration. Add migration, API-absence, first-paint,
  and no-file-touch regressions. Commit: `refactor: remove direct gguf product surface`.

- [x] **F20 — Remove the managed llama runtime.** Delete
  `ManagedLlamaServer`, `ManagedLocalRecipeProvider`, runtime/model manager
  production wiring, GPU probe, process lifecycle, and their now-dead tests and
  settings adapters. Ollama remains the sole local provider; curated API remains
  secondary. Prove startup, shutdown, cancellation, and capability status create
  no llama process. Commit: `refactor: remove managed llama runtime`.

- [x] **F21 — Prove no llama credential or process remains.** After F20, search
  executable code and frozen smoke plans for llama bearer-token, child-process,
  and argv construction paths. Add a focused negative architecture test where
  it guards against reintroduction, and close the original argv leak as removed
  rather than relocating the secret. Commit: `test: prohibit managed llama processes`.

- [x] **F34 — Remove llama from every package and workflow.** Delete the llama
  builder, runtime manifest/attestation/notice, package data, signing and
  finalization branches, Vulkan/MSYS setup used only for llama, GGUF feature
  switches, and advanced-local frozen smokes. Every platform package supports
  Ollama/API only. Add artifact and workflow guards proving zero llama binaries,
  GGUF execution code, picker routes, model-selection files, or weights. Keep
  FFmpeg packaging and provenance intact. Commit: `build: remove direct gguf runtime`.

## Phase 1 — Core Product Release Blockers

Complete these before all other code work. Run the full repository gate and a
local no-provider browser acceptance at the end of the phase.

- [x] **F01 — Restore executable procedural Review/Apply.** In
  `am_configurator/web/app.js`, restore or replace the deleted asset lookup and
  blocked-reason formatter through named, pure helpers. Review must use the
  authenticated Blob URL already owned by `state.conceptAssetUrls`, render every
  reducer block reason, survive missing/loading assets, and Apply exactly once.
  Add an executable browser-state/DOM test that reaches review, renders it, and
  exercises blocked and successful Apply paths; source regex is insufficient.
  Commit: `fix: restore procedural review and apply`.

- [x] **F05 — Repair the manual Lighting Target control.** Close the class
  attribute correctly, generate valid buttons for every device target, retain
  disabled/pressed state, and execute the markup in a DOM-capable test that
  proves CyberBoard, Relic, and AFA target buttons exist and can be selected.
  Commit: `fix: render lighting target controls`.

- [x] **F10 — Make the server own the open document target.** Add a strict,
  authenticated document-synchronization route that accepts the browser's
  complete opened/read configuration, validates it with the server's canonical
  config/product rules, stores an immutable server snapshot, and returns an
  opaque revision. Synchronize after file open, device read, document restore,
  and family change. Generation sends only the revision; the server derives
  family, raster, targets, frame cap, and duration from its stored snapshot and
  rejects stale revisions before inference. CLI-provided configs initialize the
  same mechanism. Add no-document, normal double-click/open, device-read,
  stale-revision, and cross-family tests. Commit: `fix: synchronize procedural document targets`.

- [x] **F30 — Permit re-enabling an unchanged tested backend.** Separate
  backend setup validity from the public `enabled && ready` exposure bit.
  Server-side enable validation must recompute the selected backend's current
  fingerprint/readiness without requiring `enabled` already true. The browser
  follows server authority and never requires a repeated setup inference when
  nothing changed. Test disable, re-enable, changed digest, removed model, and
  invalid credential cases. Commit: `fix: re-enable tested ai backends`.

- [x] **F31 — Restore per-stroke paint checkpoints.** Register pointer release
  cleanup for every stroke or keep one persistent listener with explicit
  teardown. Prove three consecutive strokes create three undo boundaries and a
  pointer entering the grid without a grid pointerdown cannot paint. Commit:
  `fix: checkpoint every lighting paint stroke`.

## Phase 2 — Startup, Settings, and Manifest Durability

- [x] **F03 — Isolate damaged jobs during Library reconciliation.** Wrap each
  scanned job's orphan recovery, manifest mutation, lock acquisition, and work
  purge independently. Return pathless reconciliation errors while continuing
  healthy jobs; startup must bind even when `.work` is missing, a historical
  root is read-only, a lock times out, or cleanup gets `PermissionError`.
  Commit: `fix: isolate library reconciliation failures`.

- [x] **F04 — Make banked-video recovery idempotent.** Before updating, compare
  every recovered source/frame/preview/mapping/status/timestamp field and return
  without writing when already consistent. Never persist in-memory v1
  normalization during a read-only startup scan and never advance an existing
  `completed_at`. Cover v1 byte preservation and repeated reconciliation.
  Commit: `fix: preserve completed video manifests on startup`.

- [x] **F13 — Preserve settings on transient or future-version reads.** Split
  corruption (`JSONDecodeError`, invalid encoding/schema content) from I/O
  unavailability and unsupported future schema. Quarantine only confirmed
  corrupt bytes; return pathless typed status for transient I/O and future
  versions without renaming. Prove exact bytes survive `EMFILE`, `EACCES`,
  injected `EIO`, and a newer schema. Commit: `fix: preserve settings on transient read failures`.

- [x] **F17 — Add an explicit migration-repair path.** Preserve the original
  legacy file while secure migration is unavailable, distinguish credential
  failure from settings-write failure, and allow a user-confirmed
  "continue without the legacy API credential" operation that atomically
  publishes v5 without touching the vault. All other settings remain blocked
  until migration succeeds or that explicit discard is confirmed. Commit:
  `fix: recover blocked settings migrations`.

- [x] **F18 — Validate projected settings before migration publication.** Run
  every v1/v2/v3/v4 projection through the active v5 validator before any vault or
  file mutation. Invalid legacy fields leave source bytes and the prior vault
  value unchanged. Add overlong disclosure and malformed projected-field tests.
  Commit: `fix: validate settings migration projections`.

- [x] **F19 — Distinguish invalid credentials from vault outages.** Validate
  credential shape before storage, map invalid pasted/stored values to a stable
  non-secret input error, and reserve `credential_store_unavailable` for the
  backend. Test controls, length, unavailable vault, and malformed stored data.
  Commit: `fix: report invalid api credentials accurately`.

- [x] **F23 — Make cancellation rejection side-effect free.** Verify gate
  ownership and active procedural status before writing `cancel_requested_at`.
  A completion race returns not-active without changing a ready/interrupted
  manifest. Commit: `fix: validate procedural cancellation before mutation`.

- [x] **F24 — Settle interrupted procedural jobs once.** Treat an already
  reconciled interrupted job as stable, preserve its first interruption time,
  and emit each actionable recovery record once. Remove or consume the unused
  retry action. Prove byte-stable repeated startup. Commit:
  `fix: make procedural interruption recovery idempotent`.

- [x] **F61 — Keep FFmpeg diagnostics out of manifests.** Persist only a stable
  typed/pathless media error and retain bounded stderr solely in ephemeral
  process diagnostics. Test that decoder text, relative staging names, URLs,
  paths, and credentials cannot enter `manifest.json`. Commit:
  `fix: keep runtime diagnostics out of manifests`.

## Phase 3 — Admission, Cancellation, and Runtime Lifecycle

- [x] **F02 — Make Ollama requests abortable.** Replace the blocking urllib
  chat path with a fixed-loopback, proxy-free, redirect-free HTTP exchange whose
  socket/connection can be closed from a 50 ms cancellation/deadline poll.
  Cancellation must stop the active request, release the shared gate promptly,
  and prevent a late response from publishing. Give setup tests the same
  cancellation contract. Commit: `fix: abort cancelled ollama requests`.

- [x] **F25 — Admit procedural reconciliation through the shared gate.** Make
  direct `ProceduralGenerationCoordinator.reconcile_startup()` calls acquire
  and release the same `OperationGate`, with busy behavior matching the legacy
  coordinator. Add deterministic race tests. Commit:
  `fix: gate procedural startup reconciliation`.

- [x] **F26 — Remove the server reconciliation handoff race.** Refactor
  `_State.reconcile_lighting` so legacy and procedural passes execute under one
  state-level admission lease or a single deferred callback, with no release/
  reacquire window. A concurrent generation can run before or after the whole
  pass, never during it. Commit: `fix: serialize combined lighting reconciliation`.

- [x] **F27 — Transfer gate ownership atomically to workers.** Complete every
  response read needed by `start_effect` before launching, or mark the token as
  worker-owned so post-launch exceptions cannot release it. Inject failures at
  every boundary and prove no orphan worker or second admission. Commit:
  `fix: preserve admission after procedural launch`.

- [x] **F28 — Synchronize lazy AI service/provider construction.** Protect
  `_State.ai_services` and the remaining Ollama/API provider construction with
  locks or eager immutable construction. Concurrent setup/generation requests
  must observe one capability service and one provider instance per configured
  backend. Prove no managed-local singleton remains after F20. Commit:
  `fix: serialize ai service construction`.

- [x] **F33 — Bound and cancel render, quality, encode, and mapping.** Thread a
  monotonic deadline and cancellation callback through rendering and artifact
  encoding, check at bounded work intervals, publish real phase/progress updates
  compatible with the UI, and release the gate promptly on cancel. Add a
  worst-case recipe budget test and deterministic mid-stage cancellation tests.
  Commit: `fix: bound procedural rendering work`.

## Phase 4 — Capability, Transport, and Security Boundaries

- [x] **F11 — Make capability status backend-aware and cheap.** When AI is
  disabled, return disabled status without filesystem or network probes. With
  AI enabled, inspect only the selected Ollama or curated API backend. Assert
  capability polling contains no GGUF hash, runtime resolution, GPU probe, or
  model-file access after Phase 0. Commit: `fix: avoid disabled ai capability probes`.

- [x] **F14 — Handle non-ASCII auth headers cleanly.** Convert candidate/header
  tokens to a single byte representation with explicit ASCII rejection before
  `compare_digest`. Every malformed token receives 403 without a traceback or
  dropped connection. Test with a raw latin-1 header. Commit:
  `fix: reject malformed local auth headers`.

- [x] **F15 — Redact every internal HTTP error.** Route all unexpected GET/POST
  failures through one stable pathless response function. Keep accepted-write
  recovery semantics, but never serialize raw `OSError`, device output, path,
  provider, or subprocess text. Commit: `fix: redact loopback api failures`.

- [x] **F16 — Harden legacy settings routes while they still exist.** Add exact
  body validation, the injected credential store, shared admission checks, and
  the same redaction taxonomy as active AI routes. This protects intermediate
  history before F42 removes the obsolete surface. Commit:
  `fix: harden legacy credential routes`.

- [x] **F22 — Harden xAI transport.** Use a dedicated opener that disables
  environment proxies, rejects redirects, pins HTTPS host and port, bounds
  responses/deadlines, and never forwards Authorization to another origin. Do
  not add a custom endpoint or proxy setting. Cover redirect codes, proxy
  environment, DNS/timeout, and secret redaction. Commit:
  `fix: pin xai api transport`.

- [x] **F43 — Diagnose unsupported Ollama discovery contracts.** Preserve the
  approved two-endpoint boundary: do not add `/api/show`. Distinguish a service
  returning model entries without required capability metadata from a true
  empty eligible inventory, return a stable `upgrade_required` setup reason,
  and explain that Ollama must be upgraded. Commit:
  `fix: explain incompatible ollama discovery`.

## Phase 5 — Browser Behavior and Executable Coverage

- [x] **F08 — Make proxy-disable tests non-vacuous.** Construct openers under a
  patched proxy environment and assert actual Ollama requests cannot reach a
  sentinel proxy. Include the curated API transport's no-environment-proxy
  policy without permitting a real external request. Commit:
  `test: prove ai transports ignore environment proxies`.

- [x] **F09 — Behavior-test the Ollama model picker.** Extract normalization,
  preferred-selection restoration, missing-model projection, and transient
  refresh handling into `lighting_state.js` or execute them in a DOM harness.
  Test available, empty, unavailable, selected, removed, digest-changed, and
  transient-failure states. Commit: `test: exercise ollama model picker behavior`.

- [x] **F36 — Execute every offline desktop smoke in tests.** Invoke disabled,
  API, and Ollama smoke helpers in-process with injected fakes; assert no
  external network, real credential, model mutation, managed runtime, or
  hardware access. Assert no advanced-GGUF smoke remains. Commit:
  `test: execute offline desktop ai smokes`.

- [x] **F37 — Replace smoke source assertions with failure-sensitive guards.**
  Remove substring-only packaging checks and add tests proving each smoke's
  provider construction, render/mapping, and failure propagation execute.
  Commit: `test: guard primary ollama smoke behavior`.

- [x] **F38 — Integrate real capability discovery with selection routes.** Run
  `AICapabilityService.discover_local_models` through the real server route and
  real `OllamaModel.public` contract using a fake transport. Cover unavailable,
  missing selection, exact persisted digest, and malformed contract. Commit:
  `test: integrate ollama discovery and selection`.

- [x] **F39 — Guard every Ollama eligibility exclusion.** Add independent cases
  for name/model mismatch, cloud suffix without remote metadata, each remote
  field, absent completion capability, malformed size/digest/name, 512-item
  bound, and 404 mapping. Commit: `test: cover ollama eligibility defenses`.

- [x] **F40 — Require setup after same-name digest replacement.** Present the
  selected name with a new digest and prove readiness becomes false until a new
  setup test. Commit: `test: invalidate replaced ollama models`.

- [x] **F41 — Prove the coordinator retry ceiling.** Feed three consecutive
  schema/quality failures through Ollama, assert exactly initial plus two
  retries, terminal failure, distinct deterministic seeds/corrections, and no
  fourth call. Separately assert curated API generation remains exactly one paid
  request with no automatic retry. Commit:
  `test: enforce procedural retry ceiling`.

- [x] **F44 — Record non-vacuous Ollama regression evidence.** After F08, F09,
  and F36–F41 are red-proven, update the Ollama plan status and state pointer
  with exact commands/commits rather than unsupported blanket completion text.
  Commit: `docs: record ollama regression guard proofs`.

- [x] **F50 — Prove local model/runtime attestations are gone.** After Phase 0,
  verify no model/runtime attestation reader, writer, schema, package data, or
  capability dependency remains. Add an artifact/architecture regression that
  fails if those paths return; FFmpeg attestation rejection remains covered by
  F51/F54. Commit: `test: prohibit local model attestations`.

- [x] **F54 — Prove GPG fingerprint pinning rejects bad signatures.** Test wrong,
  absent, malformed, and multiple `VALIDSIG` records even when GPG exits zero;
  retain the exact pinned happy path. Commit:
  `test: reject invalid ffmpeg signing fingerprints`.

## Phase 6 — Rendering, Mapping, and Media Correctness

- [x] **F32 — Make banked GIFs pixel-exact for every device raster.** Use up to
  the GIF format's 256 colors per frame and fail closed if an exact palette
  cannot represent a frame. Prove decoded pixels equal source RGB for 40x5
  CyberBoard, 15x6, 18x7, and 16x5 qualification frames; preview and mapped
  output must represent the same colors. Commit: `fix: preserve exact procedural gif colors`.

- [x] **F47 — Support percent signs in Library roots.** Escape literal `%` in
  directory components for FFmpeg image2 while retaining exactly one `%04d`
  filename conversion, or stage through an owned safe path and atomically bank
  afterward. Test `%`, `%%`, `%d`, spaces, and Unicode roots. Commit:
  `fix: support percent signs in media paths`.

- [x] **F48 — Make media backup portable.** Treat `NotImplementedError` and
  hard-link-incompatible filesystems as a signal to use an owned, fsynced copy
  backup; preserve rollback and cleanup guarantees. Test Windows semantics and
  injected link failures. Commit: `fix: fall back from unsupported media hard links`.

## Phase 7 — Packaging and Cross-Platform Release Gates

- [x] **F06 — Use the MSYS2 action's actual installation path.** Give the setup
  step an id, consume `steps.<id>.outputs.msys2-location`, derive every Windows
  GPG/bash/compiler/bin path from it, and invoke commands with an explicit
  MSYS2 PATH containing `/usr/bin` and `/mingw64/bin` rather than relying on a
  profile that is disabled. Add workflow static/plan tests. Commit:
  `fix: locate msys2 tools in windows builds`.

- [x] **F07 — Remove obsolete Vulkan workflow setup.** After F34 deletes the
  llama build, remove Vulkan SDK installation, environment export, cache, and
  validation from Windows workflows. Add a static workflow guard proving no
  Vulkan dependency remains. Close the finding by deletion rather than making
  the obsolete setup work. Commit: `build: remove llama vulkan setup`.

- [x] **F12 — Remove obsolete llama configure timeouts.** After F34 deletes the
  llama builder, verify no configure/build timeout or command-plan branch for
  llama remains. Add a static architecture guard if needed and close the
  finding as deletion evidence. Commit: `test: prohibit llama build commands`.

- [x] **F35 — Pin appimagetool to immutable release assets.** Replace the
  `continuous` URL with an immutable version/revision and per-architecture hash,
  reject unsupported architectures explicitly, and cache by version+hash.
  Commit: `build: pin appimagetool release assets`.

- [x] **F52 — Exercise actual native webview policy per platform.** Add a frozen
  smoke/acceptance helper that launches the selected renderer and verifies
  private mode, token-history cleanup, hidden underscore bridge methods,
  downloads, CSP, loopback loading, and Ollama/API-only Settings. Run it in each
  desktop matrix leg; keep Playwright external. Commit:
  `test: verify native webview policy`.

- [x] **F53 — Reject Windows drive and ADS archive members.** Reject `:` in every
  tar path segment plus all drive-qualified/UNC/ADS forms in the remaining
  FFmpeg extractor before path construction. Add malicious Windows-path cases
  and prove no llama extractor remains. Commit:
  `fix: reject drive-qualified runtime archives`.

- [ ] **F55 — Preserve provenance through macOS signing.** Before finalization,
  verify the assembled FFmpeg binary against its prepared runtime attestation;
  after signing, record a signed-artifact relationship that includes the
  original verified hash, signed hash, code-signing identity/CDHash, and
  unchanged manifest/build capabilities. Finalization must refuse an
  unrecognized pre-sign binary rather than blessing behavior-only replacements.
  Prove llama finalization is absent. Commit:
  `build: bind signed runtimes to verified provenance`.

- [ ] **F57 — Detect Windows junctions on every supported Python.** Implement a
  reparse-point fallback for Python 3.11 or raise a clear preflight unsupported
  error before touching a root; retain 3.12 `Path.is_junction` where available.
  Test source-supported 3.11 behavior. Commit:
  `fix: reject junctions on supported windows python`.

- [ ] **F58 — Preflight real Windows path depth.** Probe the maximum real job/
  work/asset/temp path shape, or fail with an actionable path-length message
  before job creation. Cover boundary lengths with long-path support on and off.
  Commit: `fix: validate windows library path depth`.

- [ ] **F60 — Retire executable GGUF qualification tooling.** Remove normal
  test/build entry points that invoke llama or a GGUF model. Preserve existing
  result artifacts as historical evidence with an explicit supersession note;
  if a helper remains for archaeology, it must be clearly non-production and
  unreachable from verification and release commands. Commit:
  `docs: retire gguf qualification tooling`.

After local completion and a separate outward authorization, publish the branch
and manually dispatch the desktop workflow. Windows and Linux packages must
pass as unconditional Ollama/API-only builds and the artifact guards must prove
that no llama/GGUF product path was reintroduced. A normal CI failure is fixed
in a new one-finding commit; no gate is weakened.

## Phase 8 — Library and Attestation Hardening

- [ ] **F51 — Consolidate remaining bounded attestation verification.** After
  Phase 0 removes llama and local-model attestations, extract or retain one
  no-follow, regular-file, pre-read-size-bounded, identity-rechecked JSON/hash
  primitive for the remaining FFmpeg readers. Delete obsolete generic branches
  instead of preserving them. Commit: `refactor: unify ffmpeg attestation verification`.

- [ ] **F56 — Prevent Windows read/replace sharing races.** Coordinate manifest
  reads with job locks or add bounded sharing-violation retry around atomic
  replace without weakening integrity. Concurrent Library polling and banking
  must settle old-or-new, never orphan solely due to a reader. Commit:
  `fix: serialize windows manifest replacement`.

- [ ] **F59 — Bound POSIX job-lock waits.** Use nonblocking `flock` with the
  same monotonic ten-second budget and typed timeout as Windows. Do not hold the
  exclusive job lock across avoidable large-file hashing; verify identity before
  and after any hash performed outside it. Commit: `fix: bound posix library locks`.

## Phase 9 — Retired Surface and Architecture Simplification

- [ ] **F29 — Remove unreachable paid mutation code.** Delete concept/image/
  video planning and start methods, obsolete providers/catalog roles/settings,
  and tests with zero production callers. Retain the smallest poll/download/
  process/recovery subset required for already-banked historical jobs and keep
  mutation routes at stable 410 without provider access. Commit:
  `refactor: remove retired paid generation mutations`.

- [ ] **F42 — Remove obsolete settings routes and helper.** After F16 protects
  intermediate history, delete `/api/settings/key`, `/api/settings/test`, and
  `_lighting_settings`; keep only current credential/setup routes. Assert stale
  routes return 404/410 locally and make no vault/provider call. Commit:
  `refactor: remove legacy ai settings routes`.

- [ ] **F45 — Extract device conversion from the HTTP layer.** Move LED model,
  generation spec, raster layout, and `frames_to_led_tracks` into a lower-level
  device-mapping module with no server import. Update server, procedural,
  recovery, qualification, and tests to use it; remove reverse lazy imports.
  Commit: `refactor: extract device lighting mapping core`.

- [ ] **F46 — Use one production recipe sampling contract.** Centralize local
  generation options, deterministic seeds, retry correction, and message shape.
  Production Ollama and any retained developer recipe CLI must either use it
  exactly or label an intentional experiment as non-production evidence. GGUF
  qualification/corpus tools are historical-only under F60. Regenerate only
  metadata affected by the correction; never invoke or download a model without
  separate authorization. Commit:
  `refactor: unify recipe inference parameters`.

## Phase 10 — Polish Items

Each polish item is a separate commit despite its size.

- [ ] **P01 — Remove the raw-key dead helper.** After F42 deletes the helper,
  verify no raw-key resolver or caller remains and close this duplicate as a
  separate evidence-only documentation commit so the one-item commit boundary
  remains intact. Commit: `docs: close dead lighting settings helper`.

- [ ] **P02 — Retry an unavailable keyring backend.** Cache only successfully
  validated secure backends or provide bounded invalidation so a service that
  becomes available can recover without restart. Commit:
  `fix: retry secure credential backend discovery`.

- [ ] **P03 — Remove backend identity from generation UI.** Keep provider/model/
  cost identity in Settings and Library metadata only. Commit:
  `fix: keep backend identity out of generation`.

- [ ] **P04 — Add Library asset epoch ownership.** An asset load finishing after
  refresh must revoke its new Blob URL and may not reinsert stale state. Commit:
  `fix: discard stale library asset loads`.

- [ ] **P05 — Remove loop mode from new procedural generation.** Remove the
  ignored control and request field from new procedural generation while
  preserving stored legacy values and historical video behavior. Add request,
  UI, migration, and manifest compatibility tests. Commit:
  `fix: remove ignored procedural loop mode`.

- [ ] **P06 — Validate mapped procedural results before banking.** Apply the
  canonical timeline/target/track validation used by recovery before asset
  publication. Commit: `fix: validate procedural mapped results`.

- [ ] **P07 — Stop masking Windows Node failures.** Split workflow commands or
  enforce native-command exit handling so any `node --test` failure fails the
  step immediately. Commit: `fix: propagate windows browser test failures`.

- [ ] **P08 — Disable UPX for the remaining attested runtime.** Set `upx=False`
  for FFmpeg and assert its packaged bytes/attestation remain valid. Prove no
  llama binary is present to compress. Commit:
  `build: preserve attested runtime bytes`.

- [ ] **P09 — Avoid disabled-state AI probes.** Make first-paint capability
  status static/pathless while disabled; probe Ollama only when Settings
  explicitly requests setup details or Ollama AI is enabled. Commit:
  `fix: defer optional ai readiness probes`.

- [ ] **P10 — Restore the missing push-policy artifact through governance.** Do
  not edit `AGENTS.md` or install a handwritten file. Route the missing toolkit
  artifact to the AgentGovernanceBootstrap owner, then invoke the approved
  governance-refresh operator and verify the pointer resolves. Commit is the
  refresh's own governed commit.

- [ ] **P11 — Rotate historical state through `drift`.** Invoke the repo's
  `drift` operator after remediation, archive landed `## Now` entries verbatim,
  point current state to this plan, reverify parked items, and remove duplicated
  counts. Commit: `docs: reconcile remediation state`.

- [ ] **P12 — Reuse the procedural preview helper.** Remove duplicated upscale/
  GIF logic and call the canonical artifact writer without changing pixels or
  durations. Commit: `refactor: reuse procedural preview generation`.

- [ ] **P13 — Extract shared admission primitives from retired generation.**
  Move `OperationGate`, shared errors, and target snapshot types into a neutral
  module before the final retired-pipeline deletion, with import-cycle tests.
  Commit: `refactor: extract generation admission primitives`.

- [ ] **P14 — Reuse hardened loopback exchange primitives where applicable.**
  Consolidate only the remaining Ollama and authenticated app-loopback
  proxy/redirect/cancellation mechanics whose contracts genuinely match; if
  Phase 0 removes the reported duplication, close this item with search and
  executable evidence instead of inventing abstraction. Commit:
  `refactor: share hardened loopback transport`.

- [ ] **P15 — Disable proxies for media downloads.** Retain explicit validated
  redirect handling but ensure environment proxies cannot receive temporary
  media URLs. Test under a sentinel proxy. Commit:
  `fix: keep media downloads off environment proxies`.

- [ ] **P16 — Recheck media deadlines after FFmpeg.** Check cancel/deadline
  through validation, assembly, and publication and roll back atomically at
  every late boundary. Commit: `fix: enforce media deadline through publication`.

- [ ] **P17 — Prove local-runtime leak paths are deleted.** After F20, verify the
  reader-thread, descriptor, probe-child, and managed-runtime setup paths no
  longer exist. Add an architecture guard if source search alone would be too
  weak. Commit: `test: prohibit local runtime setup processes`.

- [ ] **P18 — Prove GPU-offload parsing is deleted.** Remove any surviving
  model-path or runtime-diagnostic offload parser after F20 and guard that
  capability readiness depends only on Ollama or curated API state. Commit:
  `test: prohibit local gpu qualification`.

- [ ] **P19 — Isolate GPG for the direct bundle CLI.** Create a private temporary
  GNUPGHOME, import only the pinned key, verify, and remove it for every CLI path
  as the prepare wrapper already does. Commit:
  `fix: isolate ffmpeg signature verification keyring`.

- [ ] **P20 — Fsync settings directories.** After atomic replacement, fsync the
  parent directory on supported platforms while preserving Windows behavior.
  Commit: `fix: durably publish settings files`.

- [ ] **P21 — Remove local-model attestation temp flows.** After F49/F20, prove
  no temporary local-model metadata, chmod/publication, or cleanup path remains
  and no migration touches the user's GGUF file. Commit:
  `test: prohibit local model attestation writes`.

- [ ] **P22 — Add a forward pointer to superseded qualification evidence.** The
  Qwen qualification README must say it is historical comparative evidence,
  not a supported product or release path, and point to the Ollama/API-only
  decision and remediation plan. Commit:
  `docs: contextualize qwen qualification evidence`.

## Phase 11 — Residual Hygiene from Refuted Findings

- [ ] **R01 — Escape macro assignment codes in markup.** Validate canonical
  assignment-code syntax at config import and escape it in every data/title
  attribute. Prove hostile markup becomes inert text under the existing CSP.
  Commit: `fix: escape imported macro assignment codes`.

- [ ] **R02 — Validate imported lighting colors.** Normalize accepted colors to
  canonical six-digit RGB before style interpolation and reject/repair invalid
  profile values pathlessly. Prove CSS declaration injection and remote URL
  attempts cannot enter markup. Commit: `fix: validate imported lighting colors`.

## Completion and Release Evidence

The plan is complete only when:

1. Every actionable checkbox is closed by a traceable one-item commit or an
   explicitly identified evidence-only duplicate closure.
2. Every new regression has recorded red and green proof.
3. The full repository gate passes on the final tree.
4. The current-host versioned native build and frozen smoke pass.
5. The app is manually inspected without provider or hardware calls for the
   manual Target control, normal file-open generation target, disabled AI,
   Ollama Settings states, procedural Review/Apply, paint undo, Library retry,
   and narrow/zoom layouts.
6. After separate outward authorization, Windows and Linux desktop workflows
   pass as Ollama/API-only builds. Artifact inspection proves they contain no
   llama binary, GGUF execution path, model picker, model-selection private
   state, qualification invocation, or model weight. Native failures are fixed
   rather than hidden.
7. A final goal-first whole-change review finds no material issue.
8. `drift` reconciles plan, decisions, state, history archive, machines, and
   governance pointers without duplicating volatile counts or push status.

No provider request, model mutation, credential write, hardware write, push,
workflow dispatch, release, or branch cleanup is implied by plan approval.
