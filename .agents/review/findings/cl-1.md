# cl-1: Malformed retired-video manifests escape Library fault isolation

**Severity**: HIGH — one malformed historical manifest can abort Library scans and startup reconciliation, hiding healthy jobs and preventing the application from launching.
**Status**: Open
**Branch**: —
**Commit**: —

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
The draft implementation plan is
`docs/superpowers/plans/2026-07-30-cl-1-malformed-retired-video-manifest-isolation.md`.
Implementation approval remains pending.

## Files changed
—

## Guard proof
Prospective guard: add a malformed retired manifest beside a healthy job,
assert `scan()` and `reconcile()` return a pathless per-item error while
preserving the healthy job, and assert the retired directory remains
byte-identical. The eventual fix must be red-proven by reverting it.

## Coder dispute (if any)

## Known gaps
The intake reproduction exercised `scan()` and `reconcile()` directly. The
startup consequence is established by the unguarded caller chain but has not
yet been exercised through `create_server`.

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
