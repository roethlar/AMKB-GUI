# cl-2: Removed retired-video jobs bypass unsupported classification

**Severity**: MEDIUM — a retired video job in Library trash is exposed as an ordinary item and can be restored or permanently deleted despite the range's unsupported-and-untouched contract.
**Status**: Open
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
The draft implementation plan is
`docs/superpowers/plans/2026-07-30-cl-2-retired-video-catalog-isolation.md`.
Implementation approval remains pending.

## Files changed
—

## Guard proof
Prospective guard: place a valid retired-video job in Library trash, assert the
removed scan reports it as unsupported, and assert restore and permanent
deletion fail while all bytes remain unchanged. The eventual fix must be
red-proven by reverting it.

## Coder dispute (if any)

## Known gaps
The approved decision explicitly prohibits automatic deletion; the approved
removal plan and current module contract additionally require scanned retired
video manifests to be reported as unsupported and left untouched. The eventual
fix plan should state the intended response for explicit user deletion rather
than relying on an implicit catalog omission.

## Reviewer comments
Raised by: Reviewer: claude / claude-opus-5 / high / standard (inline,
session-only) — generation pass over
`1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`;
claude-cli 2.1.220; capability_ok=true; verdict=findings;
2026-07-30T23:54:36Z.
