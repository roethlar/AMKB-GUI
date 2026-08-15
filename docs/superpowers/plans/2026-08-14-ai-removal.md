# AI Removal Plan (2026-08-14) — APPROVED by owner 2026-08-14; slices land as work proceeds

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
1b. **Web UI leftovers** (added 2026-08-14 after slice 1 landed; authorized by
   owner blanket go for remaining slices). Slice 1 revealed `index.html`,
   `style.css`, and `lighting_review.js` still ship orphaned AI settings
   markup, selectors, and rules with no live handlers. Remove them; trim any
   tests asserting that markup exists.
2. **Server routes.** Remove `/api/ai/*` routes and AI imports from
   `am_configurator/server.py` (imports at ~1960–2823). Delete
   `tests/test_ai_routes.py`; trim AI-route cases from `tests/test_app.py`.
   DONE 2026-08-14: removed the `/api/ai/*` routes, the AI-only
   `/api/settings/{ai,ollama,ollama/disclosure,credential}` routes, and their
   nine handler methods plus `_is_ai_path` from `server.py`; trimmed (not
   deleted) `tests/test_ai_routes.py` since it is the only coverage for the
   surviving `/api/lighting/effects` procedural route, and trimmed
   `tests/test_app.py`. Kept `/api/settings/migration/discard-credential` and
   its handler `_discard_legacy_ai_credential`: `tests/web/lighting_shell.test.js`
   proves this legacy-credential-migration-repair route is still a live,
   tested UI feature independent of the AI generation surface slices 1/1b
   removed, so removing it here would have widened this slice into web UI
   territory. Full verification entry point green (756 Python tests, 171 JS
   tests).
3. **Desktop wiring.** Remove `AICapabilityService` and provider wiring from
   `am_configurator/desktop.py` (~608–856). Trim `tests/test_desktop.py`.
   DONE 2026-08-14: removed the offline-AI-recipe smoke machinery
   (`_run_disabled_ai_smoke`, `_run_api_recipe_smoke`, `_run_ollama_recipe_smoke`,
   `_smoke_recipe`) and their invocations from `run_smoke_test`, and dropped the
   now-vestigial `credential_store`/`ollama_client` kwargs from desktop.py's own
   `create_server()` calls in `run_smoke_test` and `run_native_policy_smoke`
   (neither smoke path exercises a credential- or Ollama-touching route, so the
   in-memory fakes had nothing left to guard). Kept `_OfflineOllamaInventory` and
   `_assert_ollama_api_only_bundle`: `media_framing_audit.py` (slice 5 territory)
   still imports `_OfflineOllamaInventory` from `desktop.py` for its own
   `create_server()` wiring, and `_assert_ollama_api_only_bundle` is a packaging
   bundle-content guard (no shipped `.gguf`/`llama-cli`/`llama-server`) with its
   own independent coverage in `tests/test_packaging.py`, not an AI-recipe-only
   check — removing either would have widened this slice into slice 5/6
   territory. Trimmed `tests/test_desktop.py`: deleted the two AI-recipe-smoke
   tests, renamed and simplified the full-smoke test to assert no AI kwargs
   reach `create_server()`, and dropped the now-unused
   `credentials`/`device`/`llm`/`ollama_client`/`procedural`/`recipe_provider`/
   `store`/`AICapabilityService`/`socket` imports. Full verification entry point
   green (754 Python tests, 171 JS tests).
4. **Store/settings.** Remove Ollama/provider/credential settings persistence
   from `am_configurator/store.py` (all `ollama_client`, `ai_catalog`,
   `credentials` import sites). Profile/library store logic untouched. Trim
   store-related tests. Existing on-disk settings with AI keys must still
   load: unknown settings are ignored or dropped on save, never a load error
   (add a test proving a pre-removal settings file loads).
   STOPPED 2026-08-14 (no code changed; tree left exactly as found): every
   AI-facing symbol in `store.py` still has a live, in-scope-forbidden
   dependent, so none of them can be removed without either editing
   `server.py` (out of scope for this slice) or editing `tests/test_credentials.py`
   / `tests/test_packaging.py` (slice 5's files — the former is scheduled for
   wholesale deletion there, the latter holds an unrelated "local backend
   absence" guard anchored on `store.py` source text). Evidence, gathered by
   grepping live (non-test) callers before touching anything:
   - `server.py`'s `_settings_view()` (backs the still-live `GET /api/settings`
     route, `server.py:2575`) reads `settings["ai"]["api"]` and
     `settings["ai"]["ollama"]` directly — dropping the top-level `ai` key
     from what `store.load_settings`/`load_settings_with_status` returns
     raises `KeyError` there.
   - `server.py`'s `_State.ai_services()` (`server.py:2140`, reached from
     `procedural_services()` which backs the surviving `/api/lighting/effects`
     AI-recipe-generation route slice 2 kept coverage for) builds an
     `AICapabilityService` wired straight to `store.load_settings`,
     `store.credential_status`, `store.resolve_api_key`, and
     `store.set_ai_setup_fingerprint` as its defaults.
   - `server.py:3896`'s `_save_settings_privacy` handler (routed from
     `POST /api/settings/privacy`, still live) calls `store.acknowledge_privacy`
     directly.
   - `store.discard_legacy_api_credential` is slice 2's deliberately kept
     migration-repair route backing, per its own DONE note above — unchanged.
   - `tests/test_credentials.py` calls `store.save_settings`,
     `store.update_api_key`, `store.resolve_xai_key`, `store.update_ai_settings`,
     `store.update_ollama_ai_settings`, and `store.acknowledge_ollama_disclosure`
     directly; that whole file is slice 5's to delete alongside `credentials.py`,
     not slice 4's to edit piecemeal.
   - `tests/test_packaging.py`'s local-backend-absence guard does
     `store_source[store_source.index("def update_ai_settings(") :]` to slice
     the file text — an unrelated guard that would break if that function
     were renamed or removed here.
   Net: `save_settings` and `update_api_key` (and, transitively,
   `resolve_xai_key`) are otherwise dead in production — no `server.py` or
   `desktop.py` caller remains — but all three are still exercised by
   `test_credentials.py`, so even that "free" trim is blocked by the
   don't-touch-other-files boundary, not by any real behavioral need. No test
   was added for the pre-removal-settings-file-loads contract: writing it now
   would only re-prove today's existing (and already covered, in
   `SettingsStoreTests.test_v1_file_migrates_in_place_without_losing_key` /
   `test_v6_migrates_exactly_to_v7...` / `test_v2_model_preferences_are_discarded...`
   / `test_corrupt_file_recovers`) tolerant-migration behavior, not the
   drop-the-now-unknown-`ai`-key behavior the plan text describes — that
   behavior does not exist yet because `_reject_unknown` at the top level
   still requires `ai` as a mandatory field, and it cannot be made optional
   without breaking the live `server.py` reads above. Full verification
   entry point not re-run (no code changed; tree is identical to slice 3's
   green state). Recommends either widening this slice to include the
   residual `server.py` AI wiring above (folding it into, or ordering it
   immediately before, slice 5's deletion of `ai_capability.py` /
   `procedural_generation.py` / `credentials.py`, since `ai_services()` only
   makes sense together with those modules) or an owner decision to accept a
   larger slice 4.
   RESOLVED 2026-08-14 (in-session, under the owner blanket go for remaining
   slices; no scope added): slices 4 and 5 are re-sequenced — slice 5 runs
   first, then slice 4. Code inspection confirmed the "surviving procedural
   route" characterization from slice 2 was wrong: `/api/lighting/effects` is
   provider-driven AI generation (`ProceduralGenerationCoordinator.start_effect`
   calls `capability.require_ready()`/`provider_for_generation()`;
   `procedural_generation.py` imports `llm`, `recipe_provider`, `ai_catalog`,
   `generation_admission` — all slice 5 deletion targets), so the route
   cannot outlive slice 5's already-approved deletions; removing it is the
   inherent consequence of deleting those modules, not a widening. Likewise
   `store.acknowledge_privacy` (backing `POST /api/settings/privacy`) is
   AI-provider disclosure machinery through `ai_catalog` and goes with it.
   `store.discard_legacy_api_credential` and its migration-repair route stay,
   per slice 2's DONE note.
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
   Runs BEFORE slice 4 (re-sequenced per the slice 4 resolution above) and
   also removes the server-side consumers these deletions orphan — the
   inherent consequence of the approved module deletions, no new scope:
   `/api/lighting/effects` and `/api/lighting/jobs/*` routes,
   `_start_procedural_effect`, the `ai_services()`/`procedural_services()`
   coordinator arm in `server.py`; `POST /api/settings/privacy` and
   `store.acknowledge_privacy` (AI-provider disclosure ack via `ai_catalog`);
   the `/api/led/generate*` dead stubs flagged in slice 2's out-of-scope
   findings; and the corresponding tests in `tests/test_ai_routes.py` /
   `tests/test_credentials.py`-adjacent server tests. `store.py` settings
   persistence itself remains for slice 4.
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

Per-slice external codereview (codex) declined 2026-08-14 (owner delegated
the call via session goal): slices are mechanical deletions, each gated by
the full verification entry point, and slice 6 adds a bite-proven absence
guard — no residual material risk per Review Economy.

Every slice: full entry point from `.agents/repo-guidance.md` (Verification).
Slice 6 additionally proves the guard test bites (revert one deletion, watch
it fail, restore). Native build + `--smoke-test` once after slice 6, since
packaging metadata changes.

## Out of scope

- Generator plugin surface for OpenKeeb v2 (open question 5 in
  `docs/superpowers/plans/2026-08-08-openkeeb-v2.md`).
- Other v2 work. Branch question settled by the owner on 2026-08-14 ("AMKB-GUI
  is done and locked. all new work is openkeep," recorded in
  `.agents/decisions.md`): this removal lands on `v2/openkeeb`, not the v1
  default branch, which is frozen.
