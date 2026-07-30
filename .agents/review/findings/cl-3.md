# cl-3: Node 24 plan names a nonexistent retired workflow ref

**Severity**: LOW — one planned regression assertion is vacuous and the cold-implementation record misstates the current provenance-action ref, although the surrounding exact-multiset guard would still fail before the upgrade.
**Status**: Open
**Branch**: —
**Commit**: —

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
Not started. Correcting the pending plan requires owner approval of the
finding-specific documentation change or inclusion in the plan-approval pass.

## Files changed
—

## Guard proof
Prospective proof: after correcting the plan, implement the exact retired-commit
assertion first and show it fails against the current workflow, then update the
workflow and show it passes. Keep the existing no-floating-ref assertion as the
single owner of that separate rule.

## Coder dispute (if any)

## Known gaps
The plan is unapproved and changes no runtime behavior. Its exact target
multiset would still make the overall new test fail on the old workflow, so the
defect is limited to one dead assertion and inaccurate implementation guidance.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-30T23:54:36Z.
