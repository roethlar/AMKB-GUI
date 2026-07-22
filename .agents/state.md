# Repository State

## Now

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
  provider call or hardware write was made.
- A Grok whole-change openreview of
  `98abb138406093dacea97df2b49be91aa11fdf10..6c1f7337d162eb59015265690e88a5d02d7be962`
  reported no material issue; provenance is recorded in
  `.agents/review/outcomes.md`.
- Branch `llm-led-generator`: the approved plan
  `docs/superpowers/plans/2026-07-20-llm-led-generator.md` is complete through
  Task 12. The design's implementation status and final offline verification
  record live in `docs/design/llm-led-generator.md`.
- The generator now includes app settings, the shared frame-mapping core,
  bounded Grok interpreter and renderer providers, local tweening, a
  single-flight generation API, pending-preview UI, packaging support, and an
  offline frozen-app generation smoke test.
- A separate owner-authorized live xAI check completed successfully through
  Grok 4.5 interpretation, Imagine still generation, image decode, and mapping;
  no key was persisted and no video or hardware request was made.
- The legacy implementation's `previous_plan` forwarding gap is superseded by
  the proposed replacement plan, which removes the legacy inline generator
  after the durable video workflow is operational.
- The nested `cyberboard-cli/` checkout remains ignored reference material
  and is not part of the application.

## Next

- Implement Task 4 of
  `docs/superpowers/plans/2026-07-21-optional-ai-backends.md`: migrate settings
  to schema v3 and move API credentials to the operating-system credential
  store without plaintext fallback. Preserve Library roots and loop mode, keep
  local AI primary, and do not initiate a paid API call or write hardware.
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
