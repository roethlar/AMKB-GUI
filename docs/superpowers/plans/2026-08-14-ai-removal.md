# AI Removal Plan (2026-08-14) — DRAFT, awaiting owner approval

Decision: `.agents/decisions.md` (2026-08-14). Scope:
`docs/superpowers/plans/2026-08-14-ai-removal-scope.md`. This plan slices the
removal so every slice leaves the tree green and lands as its own commit.
Approval of this plan authorizes the slices below and nothing else.

Two scope items verified since the scope doc was written (2026-08-14):
`credentials.py` is AI-provider key storage only, and `recipe_inference.py` is
an Ollama-only request contract imported solely by `recipe_provider.py`. Both
are removed, not kept.

## Ordering principle

Remove consumers before providers, outermost first: UI → server routes →
desktop wiring → store/settings → core AI modules → guards and docs. Each
slice runs the full verification entry point before commit.

## Slices

1. **Web UI.** Remove the AI generation surface from
   `am_configurator/web/app.js`: master switch, provider settings, generation
   panel/flows. Lighting studio, composer, targets, review, and library UI
   untouched. Trim AI-flow assertions from `tests/web/*.test.js` (including
   `plain_language.test.js` strings that exist only for AI screens).
2. **Server routes.** Remove `/api/ai/*` routes and AI imports from
   `am_configurator/server.py` (imports at ~1960–2823). Delete
   `tests/test_ai_routes.py`; trim AI-route cases from `tests/test_app.py`.
3. **Desktop wiring.** Remove `AICapabilityService` and provider wiring from
   `am_configurator/desktop.py` (~608–856). Trim `tests/test_desktop.py`.
4. **Store/settings.** Remove Ollama/provider/credential settings persistence
   from `am_configurator/store.py` (all `ollama_client`, `ai_catalog`,
   `credentials` import sites). Profile/library store logic untouched. Trim
   store-related tests. Existing on-disk settings with AI keys must still
   load: unknown settings are ignored or dropped on save, never a load error
   (add a test proving a pre-removal settings file loads).
5. **Core AI modules.** Delete `llm.py`, `recipe_provider.py`,
   `recipe_inference.py`, `ollama_client.py`, `ai_catalog.py`,
   `ai_capability.py`, `procedural_generation.py`, `generation_admission.py`,
   `credentials.py` and their tests (`test_recipe_provider.py`,
   `test_recipe_inference.py`, `test_ollama_client.py`, `test_ai_capability.py`,
   `test_procedural_generation.py`, `test_generation_admission.py`,
   `test_credentials.py`). Strip the AI imports from
   `media_framing_audit.py` (`ai_catalog` at ~2445, `credentials` at ~2470).
   `procedural.py`, `recipe_*` schema validation living outside these modules,
   `library.py`, and `device_mapping.py` stay.
6. **Absence guard + sweep.** Add a guard test following the
   `test_legacy_inline_generator_removed.py` precedent: assert no module,
   route, or UI string from the removed surface reappears (grep gate: no hits
   for `ollama|recipe_provider|ai_catalog|/api/ai/|ai_capability` in
   `am_configurator/` outside the guard itself). Sweep README, packaging
   metadata, CI workflow env vars (provider API keys), and `docs/` references.
   Update `.agents/state.md` and close this plan.

## Slice-boundary caveat

Line numbers above are locators from the 2026-08-14 audit, not boundaries;
re-derive at edit time. If a slice turns out to entangle non-AI behavior
(e.g. a store migration), stop and surface it rather than widening the slice.

## Verification

Every slice: full entry point from `.agents/repo-guidance.md` (Verification).
Slice 6 additionally proves the guard test bites (revert one deletion, watch
it fail, restore). Native build + `--smoke-test` once after slice 6, since
packaging metadata changes.

## Out of scope

- Generator plugin surface for OpenKeeb v2 (open question 5 in
  `docs/superpowers/plans/2026-08-08-openkeeb-v2.md`).
- Any v2 work; this lands on the current default branch as v1 cleanup unless
  the owner rules it belongs on `v2/openkeeb` — **open question, ask before
  slice 1.**
