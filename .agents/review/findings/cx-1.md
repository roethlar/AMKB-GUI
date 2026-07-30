# cx-1: Credential-save responses falsely report that no API credential exists

**Severity**: MEDIUM — a successful save immediately renders "No credential is configured" and disables Remove, misrepresenting security-sensitive persisted state until a full status refresh.
**Status**: Open
**Branch**: —
**Commit**: (pending)

## Evidence
`am_configurator/server.py:2714` returns `status(probe=False)` after `/api/settings/credential` stores the key; that path uses `_unprobed_api_components` (`am_configurator/ai_capability.py:437`) which hardcodes `configured` false (line 449), surfaced as `api.credential_set` (line 550) and reasons `credential_store_unavailable`/`credential_missing` (lines 505-508). UI renders the false state and disables Remove at `am_configurator/web/app.js:4286-4287`. Trigger: save a valid Direct API key.

## Predicted observable failure
Right after a successful key save, Settings shows the credential as absent and disables its removal control; recovers only on a later full refresh/reload.

## What
The unprobed status projection suppresses local credential-vault inspection along with network probing, so the response to a credential mutation contradicts the mutation it acknowledges.

## Approach
(pending)

## Files changed
(pending)

## Guard proof
(pending)

## Coder dispute (if any)

## Known gaps

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.
