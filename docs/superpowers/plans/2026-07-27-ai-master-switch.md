# AI Master Switch and Visible Runtime Version

**Status:** Approved by the owner's explicit implementation request on
2026-07-27. This plan implements the same-day decision that AI enablement is
user intent while backend readiness independently gates generation.

## Problem

The Settings checkbox is labeled **Enable after setup passes**, ignores its
checked transition, and only persists when Settings is later saved. The store
then refuses `enabled: true` unless the selected backend already has a valid
setup fingerprint. Backend selection and setup testing work around that
constraint by forcing AI off and letting the test turn it back on. This creates
a circular setup path: the switch does not reveal or enable setup, and setup
owns the state that the switch claims to own.

The running application version is injected into the global header, but it is
rendered as tiny muted text inside the product name. It does not provide a
useful visual build identifier.

## Behavior Contract

- The global header displays `Version <runtime version>` as a distinct,
  readable badge on every route. The server remains the sole source of the
  runtime version.
- Settings exposes exactly one AI on/off switch when AI is off. All backend,
  model, credential, disclosure, refresh, selection, and setup-test controls are
  contained in one details region and hidden while off.
- Switching on persists `enabled: true` immediately, defaults an unselected
  backend to Local, reveals setup, and loads the Local inventory only when Local
  is selected.
- Switching off persists immediately, hides setup, stops automatic Local
  inventory discovery, and hides generation outside Settings. It does not
  remove models, credentials, setup fingerprints, or Library content.
- `enabled` records user intent and is valid before setup. `ready` remains
  derived from the selected backend's current model/credential/disclosure and
  setup fingerprint.
- Backend selection preserves the master switch. A setup test records only the
  selected backend's current setup fingerprint. A failed test leaves AI on and
  its repair controls visible.
- Generation continues to require both `enabled` and `ready` at the
  server-authoritative invocation boundary.

## Implementation

### 1. Intent persistence and capability setup

Remove the readiness-forgery parameter and precondition from strict settings
persistence. `save_settings` and `update_ai_settings` accept a strict boolean
enable intent without accepting or manufacturing readiness.

Simplify `/api/settings/ai` to persist the strict intent/backend fields and then
return capability status. It must not probe readiness as permission to save the
switch.

Rename the capability setup operation from `test_and_enable` to `test_backend`.
It requires the master switch to be on and the tested backend to be selected,
runs the existing production recipe check, and writes only the setup
fingerprint. Success returns derived ready status; failure preserves enable
intent.

### 2. Settings interaction

Wrap all backend-specific controls in one `settings-ai-details` region. Render
that region from persisted capability `enabled`, not from readiness. Replace
the old enable-after-test and test-and-enable copy with master-switch and setup
language.

Add an immediate `setAiEnabled` action for both checkbox transitions. Preserve
the current enabled state when changing backends, never force the switch off
before a setup test, and refresh installed Ollama models after Local is enabled
or selected. Settings Save continues to persist library changes and may
idempotently persist the current AI selection.

Change Local discovery projection so opening Settings while AI is off does not
contact Ollama. Existing readiness gating continues to hide generation and
redirect an unavailable Create route to the manual editor.

### 3. Version presentation

Change the injected header text to `Version __AM_VERSION__` and style it as a
high-contrast compact badge that remains visible at desktop and narrow
breakpoints. Update the loopback-server assertion to prove the actual runtime
version replaces the placeholder.

## Verification

Add or update regressions proving:

1. strict settings persistence accepts enabled-but-unready intent and still
   rejects malformed fields and types;
2. `/api/settings/ai` stores the on state without a setup fingerprint;
3. setup testing requires the switch, never mutates it, and produces readiness
   only through the existing fingerprint;
4. disabled Settings contains a single visible AI switch and a hidden details
   region, while enabled rendering reveals that region;
5. toggle, backend selection, and setup requests preserve their distinct state
   ownership;
6. disabled Settings does not trigger Ollama discovery;
7. the rendered loopback page contains the prominent runtime version badge.

Red-prove each new behavioral regression by temporarily restoring the old
behavior, confirm the focused test fails, restore the implementation, and
confirm it passes. Then run the complete repository verification entry point
from `.agents/repo-guidance.md`.

Build the native package with `uv run --frozen python build.py --skip-sync`, run
its frozen `--smoke-test`, and inspect the source-served UI at desktop and
narrow widths with AI off and on. No provider request, model mutation/download,
credential entry, hardware write, remote push, or release publication is
authorized by this plan.

## Implementation Slices

1. Commit this decision and approved plan.
2. Land and commit the intent/readiness backend contract with focused Python
   regressions.
3. Land and commit the Settings/version UI with browser regressions.
4. Red-prove the new guards, run the full gate, build/smoke/visually inspect the
   native package, update `.agents/state.md`, and commit the verification
   record.
