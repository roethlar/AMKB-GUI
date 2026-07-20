# Repository State

## Now

- The owner approved the product decisions for a video-first Lighting Studio,
  recorded in `.agents/decisions.md`. The proposed implementation plan is
  `docs/superpowers/plans/2026-07-20-video-first-lighting-studio.md`; code
  execution awaits final plan approval.
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

- Obtain final owner approval for the video-first Lighting Studio plan, then
  execute its tasks in order with tests-first commits. Do not separately repair
  the legacy `previous_plan` path.
- A paid live xAI video acceptance check remains optional and needs a separate
  explicit go after the offline video pipeline is implemented.
- Carried over: address any failures surfaced by the committed CI and
  desktop-installer workflows; continue hardware verification across
  CyberBoard, Relic 80, and AFA firmware variants using portable JSON
  backups.

## Blockers

- Code implementation is intentionally blocked until the owner gives final
  approval to the proposed video-first Lighting Studio plan.
- Hardware checks require corresponding owner-supplied devices; they are not
  required for the offline suite.
