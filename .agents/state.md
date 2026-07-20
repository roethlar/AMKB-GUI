# Repository State

## Now

- Branch `llm-led-generator`: the plan
  `docs/superpowers/plans/2026-07-20-llm-led-generator.md` is committed and
  Tasks 1–10 are implemented, test-gated, and committed via subagent-driven
  TDD (settings store, `frames_to_led_tracks` refactor, `llm.py`
  types/caps, xAI transport, `GrokInterpreter`, `GrokImagineRenderer`,
  tween + `generate_effect` orchestrator, settings/generate-job HTTP
  endpoints, frontend AI panel + settings UI) — head `a688914` as of this
  handoff.
- Task 11 (packaging + frozen smoke test) is mid-flight: the subagent was
  interrupted and its prompt lost. Its partial tests-first work sits
  UNCOMMITTED in the worktree: `packaging/am_configurator.spec` adds the
  `"am_configurator.llm"` hidden import; `tests/test_packaging.py` adds
  `test_spec_bundles_the_llm_module` (passes) and
  `test_frozen_smoke_test_runs_a_fake_transport_generation` (FAILS — the
  implementation half was never written).
- The failing test pins the intended design: `am_configurator/desktop.py`
  `run_smoke_test()` must exercise the LLM generation pipeline offline —
  a fake transport feeding the real Grok providers so the
  `b64_json`/Pillow decode chain and `frames_to_led_tracks` mapping run
  inside the frozen bundle; ssl verified via `create_default_context`
  without a socket; real-TLS reach opt-in behind `AM_SMOKE_NET`.
- The nested `cyberboard-cli/` checkout remains ignored reference material
  and is not part of the application.

## Next

- Implement the frozen smoke-test extension in
  `am_configurator/desktop.py` to satisfy the two uncommitted tests, run
  the full `python3 -m unittest` suite, and commit as Task 11
  (packaging + frozen smoke test).
- Then Task 12: final verification + docs.
- Parked follow-up from review: thread `previous_plan` through
  `/api/led/generate` and `generate_effect` so the interpreter sees the
  prior plan on refinement requests.
- Carried over: address any failures surfaced by the committed CI and
  desktop-installer workflows; continue hardware verification across
  CyberBoard, Relic 80, and AFA firmware variants using portable JSON
  backups.

## Blockers

- None for local development. A live `XAI_API_KEY` is required only for
  end-to-end generation checks, not for the offline test suite.
