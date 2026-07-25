# Asset Read Cost

**Status:** Approved by the owner on 2026-07-24. The owner chose the wider of two
options after being shown the measurements and an explicit concern that the
Range relaxation optimises a cost not yet observed in practice.

## Problem

Serving one Library asset hashes the whole file twice, measured at 2.0x the
asset size through the exact call sequence `server._lighting_asset` uses:

- `resolve_asset` hashes it via `_verify_owned_asset`;
- `OwnedAsset.open_verified` hashes it again on its own descriptor.

The CPU cost is not the problem and must not be used to justify this work:
hashing runs at roughly 2.9 GB/s on the development machine, so a 20 MB video
costs about 15 ms per request. The cost that matters is I/O on the Range path.
A browser playing a video issues many Range requests, and each currently reads
the entire file twice before seeking to the slice it wants; serving an 8 MB
chunk of a 60 MB video reads 120 MB first. A Library on an external or network
drive pays that repeatedly.

## Non-goals

- Removing content verification from the ordinary, non-Range read path.
- Removing the path-safety checks: `S_ISREG`, reparse-point rejection,
  `O_NOFOLLOW`, and the descriptor/path identity comparisons all stay exactly as
  they are on every path. Those defend a real case, because the Library root is
  user-chosen and its bytes are served over the loopback HTTP server.
- Changing `generation.py` or `procedural_generation.py`, which call
  `resolve_asset` and then use `owned.path` directly without ever calling
  `open_verified`. Their verification is load-bearing and must keep hashing.

## Change

### 1. `resolve_asset(..., verify_content=True)`

Add a keyword-only flag. When false, skip the SHA-256 comparison and obtain the
identity tuple for the under-lock recheck from `lstat` instead of from
`_file_integrity`.

Everything else in `resolve_asset` is unchanged: it still takes the job lock
twice, still re-reads the manifest, still requires the record and the file
identity to be unchanged across the two lock windows, and still raises
`ManifestError("The owned asset changed during verification.")` otherwise.

Callers that pass nothing keep today's behaviour. Only
`server._lighting_asset` passes false, because it always follows with
`open_verified`, which verifies on its own descriptor. That descriptor is the
one actually served, so the resolve-time hash protects nothing the open-time
check does not already cover.

### 2. `OwnedAsset.open_verified(*, verify_content=True)`

When false, perform every existing check except the digest: the `lstat`
`S_ISREG` and reparse test, the `O_NOFOLLOW` open, the `fstat` `S_ISREG` and
reparse test, the before/after identity comparisons, and the
`st_size != record["byte_size"]` comparison. Skip only the full-file read and
the `hmac.compare_digest` on its result.

The result still proves the descriptor refers to the same regular, non-reparse
file the manifest describes, at the expected size, unchanged across the call.
It no longer proves the bytes hash to the recorded digest.

### 3. `server._lighting_asset`

- Resolve with `verify_content=False`.
- Non-Range requests keep `open_verified()` with content verification, so an
  ordinary view still verifies bytes end to end.
- Range requests use `open_verified(verify_content=False)`.

Resulting full-file reads per request, excluding the payload read itself:

| Request | Before | After |
| --- | --- | --- |
| non-Range | 2 | 1 |
| Range | 2 | 0 |

## Accepted risk

A Range request no longer proves the served bytes match the recorded digest. A
non-Range request still does, so an asset whose content has been altered is
still caught the first time it is viewed. The residual case is an asset altered
between an initial view and a later seek, inside the user's own owner-only
Library directory, by something already running as that user. The owner accepted
this on 2026-07-24.

## Verification

1. A regression proving the byte count hashed while serving one asset: 2.0x the
   asset size before, 1.0x for a non-Range request and 0x for a Range request
   after. Prove it red by restoring either hash.
2. A regression proving a tampered asset is still rejected on a non-Range read.
3. A regression proving `resolve_asset` without `verify_content=False` still
   hashes and still rejects a tampered asset, so the FFmpeg-facing callers are
   unaffected.
4. Full repository verification entry point.
5. The Windows suite, because `library.py` is the module whose Windows behaviour
   was just repaired.
