# Repository State

## Now

- The standalone AM Configurator app, protocol implementation, browser assets,
  native desktop wrapper, tests, and cross-platform workflows are present as of
  `98abb13` on `main`.
- Branch `llm-led-generator` holds `e26be36`, which commits the approved design
  `docs/design/llm-led-generator.md` (v3): an LLM-backed LED effect generator
  using a two-role Grok/xAI provider (interpreter + Grok Imagine renderer),
  reusing the GIF import mapping pipeline, with a pending/preview job UI and
  settings-stored API key.
- The implementation plan for that design is mid-write per
  `superpowers:writing-plans`; `docs/superpowers/plans/` does not exist yet.
  Codebase recon for the plan is complete (GIF mapping core, `_GIF_LAYOUTS`,
  `_LED_SPEEDS_MS`, settings-store lock/atomic-write pattern, `importGif` UI
  flow, `create_server` routing).
- Agreed execution model: this session writes and commits the plan, then Opus
  subagents implement it task-by-task (subagent-driven development) on the
  feature branch with test/review gates between tasks.
- The nested `cyberboard-cli/` checkout remains ignored reference material and
  is not part of the application.

## Next

- Write and commit `docs/superpowers/plans/2026-07-20-llm-led-generator.md`
  covering the TDD task sequence: settings store additions,
  `frames_to_led_tracks` refactor with GIF parity, `llm.py`
  types/validation/budget caps (`MAX_LLM_FRAMES`, `MAX_RENDERED_KEYFRAMES`,
  `MODEL_FRAME_CAPS`), xAI transport, `GrokInterpreter`,
  `GrokImagineRenderer`, tween/orchestrator, settings + generate-job HTTP
  endpoints, UI settings and generate panel, packaging/smoke-test updates.
- Dispatch Opus subagents per plan task; run `python3 -m unittest` between
  tasks before advancing.
- Carried over: address any failures surfaced by the committed CI and
  desktop-installer workflows; continue hardware verification across
  CyberBoard, Relic 80, and AFA firmware variants using portable JSON backups.

## Blockers

- None for local development. A live `XAI_API_KEY` is required only for
  end-to-end generation checks, not for the offline test suite.
