# AI Removal Blast-Radius Scope (2026-08-14)

Decision context: `.agents/decisions.md` (2026-08-14) — AI generation is removed
from the core app; the core consumes pixel art and recipes only. This file scopes
the removal so the work can be planned and sliced. Scope only — no code changes
are authorized by this document.

## Removed (AI-only modules)

| File | Lines | Role |
| --- | --- | --- |
| `am_configurator/llm.py` | 499 | Provider abstraction (xAI/Grok et al.) |
| `am_configurator/recipe_provider.py` | 1346 | LLM recipe generation (Xai/Ollama providers) |
| `am_configurator/ollama_client.py` | 520 | Local Ollama HTTP client |
| `am_configurator/ai_catalog.py` | 424 | Provider/model catalog, env vars |
| `am_configurator/ai_capability.py` | — | AI capability service wiring |
| `am_configurator/procedural_generation.py` | 1025 | AI generation job pipeline (imports `llm`, `recipe_provider`) |
| `am_configurator/generation_admission.py` | 208 | Admission/gating for AI generation jobs |
| `am_configurator/credentials.py` | — | AI provider key storage (verified 2026-08-14: AI-only, all call sites are AI settings paths) |
| `am_configurator/recipe_inference.py` | 81 | Ollama request contract, imported only by `recipe_provider.py` (verified 2026-08-14: AI-only) |

## Stays (deterministic core)

- `am_configurator/procedural.py` — deterministic recipe/effect renderer. The
  recipe schema (seven kinds) and its validation stay; recipes become a
  user-authored/imported format, not an LLM output format.
- ~~`am_configurator/recipe_inference.py`~~ — resolved 2026-08-14: AI-only
  (Ollama request contract), moved to the Removed table above.
- `am_configurator/library.py` — generated-asset library becomes the imported
  pixel-art/recipe library.
- `am_configurator/device_mapping.py`, `media_framing_audit.py` — core; strip
  their AI imports (`PROVIDER_ENVIRONMENT_VARIABLES` ref at
  `media_framing_audit.py:2445`).

## Edited (mixed files — AI surface stripped, rest untouched)

- `am_configurator/server.py` — remove `/api/ai/*` routes and AI imports
  (~lines 1960–2823 region).
- `am_configurator/store.py` — remove Ollama/provider settings persistence
  (~7 import sites); keep all non-AI profile/library store logic.
- `am_configurator/desktop.py` — remove AI service wiring (~lines 695–856).
- `am_configurator/web/app.js` — remove AI generation UI (master switch,
  provider settings, generation panel). Lighting studio, library, and
  composer UI untouched.

## Tests

- Removed with their modules: `test_ai_capability.py`, `test_ai_routes.py`,
  `test_credentials.py` (if module goes), `test_generation_admission.py`,
  `test_ollama_client.py`, `test_recipe_provider.py`,
  `test_procedural_generation.py`.
- Kept and possibly trimmed: `test_procedural.py`, `test_recipe_inference.py`,
  `test_library.py`, `test_app.py`, `test_desktop.py`, `test_device_mapping.py`,
  web tests (drop AI-flow assertions only).
- `test_legacy_inline_generator_removed.py` — precedent guard; extend the same
  pattern to assert the AI surface stays gone.

## Follow-ups captured elsewhere

- Plugin/external-provider path (pixel-art generators, OpenKeeb v2 plugin
  surface): open question in `.agents/decisions.md`, not part of removal.
- Packaging/docs sweep: README, packaging metadata, and CI env-var references
  to provider keys must be cleaned in the same slice set.

## Verification for the removal slices

Full entry point from `.agents/repo-guidance.md` (Verification), plus a grep
gate: no hits for `ollama|recipe_provider|ai_catalog|/api/ai/|llm\.` outside
tests that assert absence.
