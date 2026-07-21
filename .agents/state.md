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
- The full repository verification entry point passed at `2e4d474` with 262
  Python tests and 29 browser-state/static tests. Versioned macOS build
  `0.1.18` passed frozen smoke and DMG verification and was launched with the
  Relic profile. A one-output live xAI Concepts acceptance check completed with
  one still banked locally, visible/selectable in Concepts, browsable in
  Library detail, and retained across Settings → Done. Provider-reported cost
  was $0.0227244. No key was persisted and no video or hardware call was made.
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

- Finish Task 12's explicit selected-concept handoff into Animate, implement
  Task 13's video/review/apply workflow, then expand the landed read-only
  Library browser to Task 14's remaining resume/retry/animate/apply actions. Do
  not separately repair the legacy `previous_plan` path.
- A paid live xAI video acceptance check remains optional and needs a separate
  explicit go after the offline video pipeline is implemented.
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
