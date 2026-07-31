# cl-1: Malformed retired-video manifests escape Library fault isolation

**Severity**: HIGH — one malformed historical manifest can abort Library scans and startup reconciliation, hiding healthy jobs and preventing the application from launching.
**Status**: Verified
**Branch**: —
**Commit**: `36338cbc91520436bbc97fabf3761106bd538f0a`

## Evidence
`am_configurator/library.py:1866` canonicalizes a retired manifest's `job_id`.
The surrounding handler at `am_configurator/library.py:1884` catches only
`ManifestError`, while `_canonical_uuid` raises the sibling
`InvalidIdentifierError` (`am_configurator/library.py:318-323`,
`am_configurator/library.py:425-434`). Trigger: a manifest marked by
`schema_version == 1` or `pipeline == "legacy_video"` with a missing,
non-string, or noncanonical `job_id`.

Independent intake reproduction created one healthy temporary job and one
retired manifest containing only `{"schema_version": 1}`. Both `scan()` and
`reconcile()` raised `InvalidIdentifierError` instead of isolating the damaged
directory. The existing retired-manifest test at `tests/test_library.py:205`
uses a valid canonical `job_id` and cannot reach this path.

## Predicted observable failure
`GeneratedAssetLibrary.scan()` fails the entire Library listing rather than
returning a `corrupt_manifest` error beside healthy jobs. Startup also fails:
`create_server` calls `state.reconcile_lighting(force=True)` at
`am_configurator/server.py:3916`; that reaches
`ProceduralServices.reconcile_startup` and the unguarded `library.reconcile()`
call at `am_configurator/procedural_generation.py:1007`.

## What
The retired-video check introduced by the reviewed range raises an exception
outside the exception type handled by the per-directory fault-isolation path.

## Approach
`GeneratedAssetLibrary._scan_internal` now isolates
`InvalidIdentifierError` beside `ManifestError` at the existing per-directory
corrupt-manifest boundary. This preserves direct caller ID validation while
projecting malformed manifest-owned IDs through the established pathless
`corrupt_manifest` response. A focused regression test exercises scan,
reconciliation, application startup, healthy-job visibility, and byte
preservation.

## Files changed
- `am_configurator/library.py:1884` — isolate invalid manifest-owned UUIDs at
  the generated-job scan boundary.
- `tests/test_library.py:233` — guard malformed retired manifests across scan,
  reconcile, and startup without touching their bytes.
- `docs/superpowers/plans/2026-07-30-cl-1-malformed-retired-video-manifest-isolation.md`
  — record the approved implementation and verification contract.
- `.agents/review/findings/cl-1.md`, `.agents/review/index.md`, and
  `.agents/state.md` — record the active finding slice.

## Guard proof
- `tests.test_library.GeneratedAssetLibraryTests.test_malformed_retired_video_manifest_is_isolated_during_scan_reconcile_and_startup`
  passes with the tuple handler.
- Replacing that handler temporarily with `except ManifestError:` makes the
  focused test fail at `scan()` with uncaught `InvalidIdentifierError`.
- Restoring the tuple handler makes the same focused test pass.
- `tests.test_library`: 58 passed, 2 expected platform skips.
- Complete gate: 640 Python tests passed with 5 expected platform skips; 125
  web tests passed; compile, JavaScript syntax, and `uv build` passed.

## Coder dispute (if any)

## Known gaps
`cl-2` remains deliberately out of scope: trash scanning, restore, and
permanent deletion behavior is unchanged.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-30T23:54:36Z.

Intake correction: the review described the canonicalization call as preceding
the `try`; it is inside that `try`, but the handler catches only
`ManifestError`. The sibling exception still escapes, so the finding is
admitted on the reproduced failure.

Reviewer: claude / claude-opus-5 / xhigh / frontier
escalated: T2

claude-cli 2.1.220; reviewed
`36338cbc91520436bbc97fabf3761106bd538f0a` against
`6f7865e8bc9cf6f8b77d2b7f0eb1c1a9b530c67b`;
`guard_confirmed=true`; `capability_ok=true`; verdict `accepted`;
2026-07-31T00:39:43Z.

- The root correction is the precise generated-job per-directory boundary at
  `am_configurator/library.py:1884`; direct caller ID validation remains
  unchanged.
- In a disposable detached worktree, restoring only `library.py` from the base
  made the focused test fail with the predicted escaping
  `InvalidIdentifierError`; restoring the reviewed file made it pass.
- The reviewer confirmed the malformed directory never enters reconciliation's
  scanned set, so the pathless error projection and byte-preservation claim
  hold.
- The reviewer independently reran the full Python gate: 640 tests passed with
  5 expected platform skips.
- Non-blocking test-quality notes: the `create_server` return-value assertion is
  redundant because the load-bearing coverage is that construction does not
  raise, and the explicit absolute-path assertion supplements an already
  fixed-shape error-dict assertion.
- Environment note: repository hooks rewrote one git command through `rtk`,
  and one Grep invocation was denied. The reviewer recovered through allowed
  git and Read operations, completed both capability and guard proofs, removed
  `F:/dev/_cl1-verify-wt`, and left the coder tree clean.
