# AI-removal review follow-up (2026-08-15)

Context: the whole-diff codex review of `27a01ae..474a9f7` returned four
MEDIUM findings (full record: `.agents/review/outcomes.md`, 2026-08-15).
This plan disposes of them on `v2/openkeeb`. Line/symbol references are
locators from the review, re-derived at edit time.

## Slice 1 — delete `recipe_system_prompt()` (finding 2)

`am_configurator/procedural.py` still contains the LLM system-prompt
generator; its only production caller was the deleted `recipe_provider.py`.
Delete the function (and any now-orphaned helpers/tests it alone used), then
re-run the dependency/absence guards. The `lighting_review.js` empty stub is
NOT touched: keeping it was a deliberate, recorded slice-1b decision (file,
script tag, and static route are load-bearing outside that slice).

## Slice 2 — restore settings-safety coverage (finding 3)

`tests/test_credentials.py` deletion also removed the only tests for two
behaviors that survive in non-AI `store.py`: settings preservation under
transient read errors, and rejecting newer schemas without renaming or
overwriting. Port equivalents against the live `store.py` surface
(originals at `27a01ae:tests/test_credentials.py:450`, `:561`). Prove each
new test bites (revert-behavior/fail/restore or targeted mutation).

## Slice 3 — restore discard-credential behavioral test (finding 4)

`/api/settings/migration/discard-credential` remains live but its
integration test went with `tests/test_ai_routes.py` (original at
`27a01ae:tests/test_ai_routes.py:681`). Restore behavioral coverage:
confirmation gate, plaintext removal, no vault modification. Prove it bites.

## Slice 4 — stranded OS-vault provider keys (finding 1) — OWNER DECISION

Upgrading users keep provider API keys under service
`dev.amconfigurator.ai` with no in-app deletion path (the `keyring`
dependency is gone). Options:

- (a) Re-add `keyring` (optional extra) solely to offer one-time vault
  cleanup from the migration UI.
- (b) Document-only: exact per-OS removal steps (Keychain Access, Windows
  Credential Manager, `secret-tool`) in README migration notes + release
  notes.
- (c) Leave as-is.

Recommendation: (b). Re-adding `keyring` contradicts the removal's intent
for one shrinking cohort; documented manual removal is honest and zero-dep.

## Verification

Every slice: full entry point from `.agents/repo-guidance.md`
(Verification). Slices 2–3 additionally prove new tests bite. No further
external review — the launched review's first substantive result is used
as returned; per-finding re-review is waived per Review Economy.
