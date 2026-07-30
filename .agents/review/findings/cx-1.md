# cx-1: Credential-save responses falsely report that no API credential exists

**Severity**: MEDIUM — a successful save immediately renders "No credential is configured" and disables Remove, misrepresenting security-sensitive persisted state until a full status refresh.
**Status**: Verified
**Branch**: —
**Commit**: `1bb4a21`

## Evidence
`am_configurator/server.py:2714` returns `status(probe=False)` after `/api/settings/credential` stores the key; that path uses `_unprobed_api_components` (`am_configurator/ai_capability.py:437`) which hardcodes `configured` false (line 449), surfaced as `api.credential_set` (line 550) and reasons `credential_store_unavailable`/`credential_missing` (lines 505-508). UI renders the false state and disables Remove at `am_configurator/web/app.js:4286-4287`. Trigger: save a valid Direct API key.

## Predicted observable failure
Right after a successful key save, Settings shows the credential as absent and disables its removal control; recovers only on a later full refresh/reload.

## What
The unprobed status projection suppresses local credential-vault inspection along with network probing, so the response to a credential mutation contradicts the mutation it acknowledges.

## Approach
`_save_ai_credential` now returns `capability.status(probe=True)`. The probed API projection (`_api_components`) reads only the injected local credential store and computes a fingerprint — it never contacts a provider — so the response to a vault write may read the vault it just wrote. Other `probe=False` sites (status polls, non-credential settings saves) are unchanged.

## Files changed
- `am_configurator/server.py:2714` — credential-save response probes the vault
- `tests/test_ai_routes.py` — fake capability records probe arguments; new guard test

## Guard proof
- `tests/test_ai_routes.py::OptionalAIRouteTests::test_credential_save_returns_a_vault_probed_status` — asserts the credential-save route requests a probed status. Reverting `probe=True` back to `probe=False` at the save site makes it FAIL ("credential-save must return a vault-probed status"); restoring makes it PASS. Full suite green (703 tests at commit time).

## Coder dispute (if any)

## Known gaps
The general `/api/settings/ai` save (server.py:2697) still returns an unprobed status; it does not mutate the vault, so its `credential_set` may lag until the next status poll. Reviewer may grade whether that adjacent site needs the same treatment.

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

Reviewer: codex / gpt-5.6-sol / high / standard
codex-cli 0.146.0; reviewed 1bb4a212a874dbf2d2436077072cb5a9048d1733 base 3a4e5f0f95b3589f790de37ba9375ca469dd970c; guard_confirmed=true; verdict=accepted; 2026-07-30T05:32:12Z; comments: none.
