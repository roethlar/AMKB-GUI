# cl-2: Removed retired-video jobs bypass unsupported classification

**Severity**: MEDIUM — a retired video job in Library trash is exposed as an ordinary item and can be restored or permanently deleted despite the range's unsupported-and-untouched contract.
**Status**: In progress
**Branch**: —
**Commit**: —

## Evidence
`am_configurator/library.py:3229-3326` scans removed jobs through
`_read_owned_manifest` with no retired-video check. `_validate_manifest` still
accepts schema-v1 and `legacy_video` manifests
(`am_configurator/library.py:1025-1049`), so the removed scan returns them as
normal catalog items. `restore` reaches `os.rename` at
`am_configurator/library.py:3707`; `delete_forever` reaches
`shutil.rmtree` at `am_configurator/library.py:3808`.

Independent intake reproduction created a valid retired-video job with a
sentinel MP4 in a temporary Library. After removal, `LibraryCatalog.scan()`
returned the job as an ordinary removed item with no error. Restore succeeded.
After removing it again, `delete_forever` succeeded and the sentinel no longer
existed.

## Predicted observable failure
A historical video job already in trash is presented as supported rather than
as `unsupported_video_job`. A user or direct API caller can restore it into the
active namespace, where the active scan then rejects it, or permanently delete
its directory and assets. This makes classification depend on storage location
and leaves generic mutation paths open for the retired data.

## What
The reviewed range added retired-video classification only to the active job
scan. The removed-job scan and its mutation boundaries still use the normal
manifest path.

## Approach
`_is_retired_video_manifest` and `_read_job_manifest` now provide one raw,
ownership-aware retired-job boundary before current-schema validation. Live
and removed scans project `_UnsupportedVideoJobError` as the same pathless
`unsupported_video_job` result. Catalog lookup forwards an explicit rejection
flag, and both the initial and lock-held reads for remove, restore, and
permanent deletion enable it, preventing either rename or deletion even when a
manifest becomes retired after lookup.

## Files changed
- `am_configurator/library.py:297` — central retired-video classification,
  scan projection, and mutation rejection.
- `tests/test_library.py:2223` — retired-job fixtures plus removed-scan and
  six-case mutation guards.
- `docs/superpowers/plans/2026-07-30-cl-2-retired-video-catalog-isolation.md:1`
  — approved scope, transition cases, and implementation status.
- `.agents/review/findings/cl-2.md:1` — implementation and guard evidence.
- `.agents/review/index.md:33` — active-review status.
- `.agents/state.md:1` — current implementation and next-action pointer.

## Guard proof
- `tests.test_library.LibraryRemovalTests.test_removed_retired_video_job_is_reported_unsupported_and_untouched`
  — failed before the fix because a validator-compatible retired job was
  catalogued and a minimal schema-v1 job was reported corrupt. It passed after
  implementation, failed again with only `library.py` restored to the parent
  content, and passed again after restoring the fix.
- `tests.test_library.LibraryRemovalTests.test_retired_video_catalog_mutations_fail_without_touching_files`
  — failed before the fix because remove, restore, and permanent deletion all
  executed, both for initially retired jobs and for jobs changed to retired
  between lookup and lock acquisition. It passed after implementation, failed
  again with only `library.py` restored to the parent content, and passed again
  after restoring the fix.
- Focused guards: 2/2 pass. `tests.test_library`: 60 pass, 2 platform skips.
  Full Python suite: 642 pass, 5 platform skips. Compileall, 125 web tests,
  every recorded JavaScript syntax check, and `uv build` pass.

## Coder dispute (if any)

## Known gaps
None within `cl-2`; `cl-3` and product Slice P6 remain outside this finding.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-30T23:54:36Z.
