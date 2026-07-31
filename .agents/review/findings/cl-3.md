# cl-3: Node 24 plan names a nonexistent retired workflow ref

**Severity**: LOW — one planned regression assertion is vacuous and the cold-implementation record misstates the current provenance-action ref, although the surrounding exact-multiset guard would still fail before the upgrade.
**Status**: Verified
**Branch**: —
**Commit**: `72a1e41889243819f4c27036693f150b15b95859`

## Evidence
`docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md:32`
names `actions/attest-build-provenance@v2.4.0` as current evidence, and line
55 calls the current ref pinned `v2.4.0`. A1.1 then requires none of those five
retired refs to appear in either workflow at lines 115-117.

The actual four uses in `.github/workflows/desktop.yml:161-173` are
`actions/attest-build-provenance@e8998f949152b193b063cb0ec769d69d929409be`;
`v2.4.0` appears only in comments. The existing assertion at
`tests/test_packaging.py:466` already rejects floating
`actions/attest-build-provenance@v...` refs.

## Predicted observable failure
An implementer following A1.1 literally adds an absence assertion for
`actions/attest-build-provenance@v2.4.0`; it passes before either workflow is
changed and therefore guards nothing. The plan's own red-first requirement at
lines 125-132 is not met by that sub-assertion.

## What
The plan uses a release label where its executable guard requires the exact
immutable ref present in the workflow.

## Approach
The plan now records the exact immutable provenance-action commit currently
used by all four Desktop attest steps, while retaining `v2.4.0` only as release
provenance. That makes the planned retired-ref absence assertion fail against
the old workflow as intended and leaves the existing no-floating-ref assertion
as the sole owner of the separate pinning rule.

## Files changed
- `docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md:3`
  — corrected current evidence and the replacement table to the exact retired
  commit.
- `.agents/review/findings/cl-3.md:1` — implementation and proof record.
- `.agents/review/index.md:1` — active-review status.
- `.agents/state.md:1` — current slice and next-action pointer.

## Guard proof
Manual plan proof: the exact retired commit appears in all four current
Desktop attest steps, so the planned absence assertion will fail before the
workflow upgrade. `v2.4.0` appears only in comments, and
`tests/test_packaging.py:466` independently rejects floating
`actions/attest-build-provenance@v...` workflow refs. The packaging test module
passes unchanged: 50 tests passed with 2 platform skips.

## Coder dispute (if any)

## Known gaps
The A1 workflow implementation remains unapproved and changes no runtime
behavior in this slice.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-30T23:54:36Z.

Verified by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only); claude-cli 2.1.220; reviewed
`72a1e41889243819f4c27036693f150b15b95859`; base
`faf41cfcc926ef494258faeb70a8f83b75790247`; guard_confirmed=true;
capability_ok=true; verdict=accepted; 2026-07-31T03:19:10Z.

- Independently confirmed the current Desktop workflow has four exact
  `e8998f949152b193b063cb0ec769d69d929409be` provenance uses, no floating
  provenance ref, and an existing test that forbids one.
- Restored the base plan in a disposable worktree and confirmed its
  `@v2.4.0` retired-ref instruction matched no workflow use. Restored the head
  plan and confirmed both current-evidence locations name the exact commit
  while A1 remains unapproved.
- The focused packaging module passed 50 tests with 2 platform skips. No
  adjacent documentation regression was found.
- Environment note: one piped git command and one hook-rewritten `rtk git`
  spelling were denied. Permitted repository reads, direct git operations, and
  the focused verification succeeded in the same review; the shared worktree
  remained clean and the disposable worktree was removed.
