# cl-1 Malformed Retired-Video Manifest Isolation Plan

**Status:** Drafted on 2026-07-30. The owner authorized plan preparation;
implementation approval remains pending.

## Objective

Close review finding `cl-1` without expanding into `cl-2` or changing the
retired-video product contract. A malformed historical video manifest must be
isolated as one pathless `corrupt_manifest` entry. It must not abort Library
scan, reconciliation, or application startup; hide healthy jobs; or modify the
historical directory or its assets.

## Authority and fixed contract

- `.agents/decisions.md` rules that historical video jobs are not resumable and
  their files are not deleted automatically.
- The implemented FFmpeg-removal plan requires old video manifests to fail
  closed as unsupported without modifying or deleting their directories or
  assets.
- `.agents/review/findings/cl-1.md` records the reproduced regression and is the
  only finding in scope.
- `GeneratedAssetLibrary.scan()` promises to isolate corrupt manifests.
- Automated work must not write to a keyboard. This plan requires no hardware,
  provider, credential, release, tag, announcement, or native-installer action.

## Diagnosis

`GeneratedAssetLibrary._scan_internal` first validates the canonical UUID used
as the directory name. Inside its per-directory `try`, the retired-video
pre-check then canonicalizes `value.get("job_id")`. Missing, non-string, or
noncanonical values raise `InvalidIdentifierError`.

The per-directory handler catches only `ManifestError`. Those exception classes
are siblings under `LibraryError`, so `InvalidIdentifierError` escapes
`_scan_internal`. `scan()` and `reconcile()` propagate it; startup propagates it
through `ProceduralServices.reconcile_startup()` and `create_server()`.

The correction belongs at the generated-job scan's per-directory isolation
boundary:

- catch exactly `(ManifestError, InvalidIdentifierError)`;
- retain the existing pathless `corrupt_manifest` projection;
- do not change the exception hierarchy, because direct caller-supplied invalid
  IDs must remain distinguishable as `InvalidIdentifierError`;
- do not catch broad `LibraryError` or `Exception`;
- do not add a second retired-video classifier or alter valid
  `unsupported_video_job` handling.

This boundary also safely isolates an invalid manifest-owned UUID reached
through `_validate_manifest`, while leaving public lookup/mutation validation
unchanged.

## Scope

### Production

- `am_configurator/library.py`

### Guard

- `tests/test_library.py`

### Records

- `.agents/review/findings/cl-1.md`
- `.agents/review/index.md`
- `.agents/state.md`
- this plan

No server, procedural-generation, web, dependency, packaging, workflow, or
installer source belongs in this fix.

## Implementation slice C1 — isolate invalid manifest-owned IDs

One finding maps to one implementation commit. Build the guard before changing
production code, observe it fail, then implement the one-boundary correction.
Do not commit the intermediate red working tree.

### C1.1 Add the failing behavior guard

In `GeneratedAssetLibraryTests`, add
`test_malformed_retired_video_manifest_is_isolated_during_scan_reconcile_and_startup`.

The test must:

1. Create one healthy job through `_create_job()`.
2. Create a second canonical UUID job directory manually.
3. Write a manifest containing only `{"schema_version": 1}` so the retired
   predicate is true while `job_id` is missing.
4. Add a `video/historical.mp4` sentinel with fixed bytes and snapshot both the
   manifest and sentinel bytes.
5. Call `self.library.scan()` and assert:
   - the healthy job remains visible;
   - the malformed directory contributes exactly one pathless
     `corrupt_manifest` error keyed by its directory UUID;
   - neither filesystem paths nor sentinel content leak into the response.
6. Call `self.library.reconcile()` and assert the same malformed job is isolated
   as `corrupt_manifest` rather than raising.
7. Call `create_server` with the same injected Library and a
   `MemoryCredentialStore`, assert the server is created, and close it in a
   `finally` block.
8. Assert the malformed manifest and sentinel still exist with byte-identical
   contents after scan, reconciliation, and startup.

Run the named test before the production edit. The expected failure is an
uncaught `InvalidIdentifierError`; any other failure means the guard is not
isolating `cl-1` and must be corrected before proceeding.

### C1.2 Correct the generated-job scan boundary

In the `GeneratedAssetLibrary._scan_internal` handler that currently catches
`ManifestError` and emits `corrupt_manifest`, catch
`(ManifestError, InvalidIdentifierError)` instead.

There are two `_scan_internal` methods in `library.py`; modify only the
generated-job implementation around the retired-video pre-check. Do not change
the saved-item scanner.

Make no other production change. In particular:

- do not modify `_canonical_uuid`;
- do not make `InvalidIdentifierError` inherit from `ManifestError`;
- do not wrap or rewrite every validation call;
- do not change valid legacy manifests from `unsupported_video_job`;
- do not touch trash scanning, restore, or permanent deletion, which belong to
  `cl-2`.

Run the named test again and require it to pass.

## Guard proof

Use the repository root for every command.

Focused red/green command:

```powershell
uv run --frozen python -m unittest tests.test_library.GeneratedAssetLibraryTests.test_malformed_retired_video_manifest_is_isolated_during_scan_reconcile_and_startup -v
```

Before committing, prove the guard is load-bearing even if the initial
test-first failure was already observed:

1. Temporarily restore the production handler to `except ManifestError:`.
2. Run the focused command and require failure by uncaught
   `InvalidIdentifierError`.
3. Restore the tuple handler.
4. Run the focused command and require success.
5. Record both results in `.agents/review/findings/cl-1.md`.

Do not use history rewrite for this proof. Revert and restore the working-tree
line with the normal edit mechanism, then verify `git diff` contains the
intended final change.

## Verification

After the focused guard is green, run:

```powershell
uv run --frozen python -m unittest tests.test_library -v
```

Then run the complete repository verification entry point:

```powershell
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/app.js
uv build
```

A failure is a roadblock. Do not mask or retry the known intermittent
cancellation test; report it with its actual output if it appears.

Native installer verification is not required because the fix changes no
dependency, packaging, native entry point, or platform integration.

## Commit and review closure

Before the implementation commit:

- update `cl-1` with the implemented approach, exact changed files, and
  red/green guard evidence;
- keep `cl-2` and `cl-3` untouched;
- update `.agents/state.md` to point at the active `cl-1` verification state.

Commit the production change, test, and finding-specific records as one
`cl-1` implementation slice. Do not amend, squash, reorder, or combine it with
another finding.

After the commit, continue the codereview per-finding flow. Because `cl-1` is
HIGH, T2 routes verification to the frontier tier. No frontier pair may be
guessed or inherited from the generation pass; if the machine-local cache still
has no owner-recorded frontier pair, ask the owner for that separate reviewer
decision when the verified implementation commit is ready.

Only an accepted reviewer verdict closes `cl-1`. Record that verdict in the
finding and index before moving to `cl-2`.

## Completion criteria

`cl-1` is implementation-complete only when:

- malformed retired manifests cannot escape generated-job scan isolation;
- healthy jobs remain visible;
- scan and reconciliation report the malformed directory as pathless
  `corrupt_manifest`;
- application server creation succeeds with the malformed directory present;
- the historical manifest and sentinel remain byte-identical;
- the guard is proven red with the fix removed and green with it restored;
- focused and complete verification pass;
- the implementation is committed as one finding-specific slice; and
- frontier codereview accepts the fix and the review records are synchronized.
