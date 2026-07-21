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
  fixes through `9751f72`. The full repository verification entry point passed
  at `9751f72` with 256 tests, including the prepared real FFmpeg runtime
  integration check for every supported device frame cap. No provider or
  hardware call was made.
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

- Execute the approved video-first Lighting Studio plan in order with
  tests-first commits, beginning Task 10 with the Lighting shell and testable
  browser state. Do not separately repair the legacy `previous_plan` path.
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
