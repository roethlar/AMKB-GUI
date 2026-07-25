# Windows Suite Repair

**Status:** Complete on 2026-07-24. Approved by the owner the same day, after a
triage that reproduced every CI Windows failure on a real Windows 11 host and
classified all of them.

Committed as W1 `c40691a`, W3 `53a1309`, W2 `a794a97`, W4 `9c8a491`, W5
`f07395a`. The Windows suite reaches `OK (skipped=6)` at 381 tests, with
identical counts on two consecutive runs; the earlier run-to-run variance was a
symptom of W1 and is gone. macOS passes the full entry point at 381 tests.

Process note for future work of this shape: W2-W5 were split into four commits
to satisfy one-finding-per-commit, and the owner confirmed afterwards that a
single commit would have been appropriate for a batch of closely related
test-only repairs. Reserve per-finding commits for behavioural fixes.

Scope is one product defect and ten test defects. The product defect is
user-facing on Windows; the ten test defects are not, but the merge gate stays
red until they are closed, so all six slices are required to land the branch.

Implementation is authorized under one finding per commit.

## Objective

Make `Test · Windows` green, and fix the one genuine Windows product defect that
the triage uncovered: banked Library assets cannot be resolved or served on
Windows.

No macOS or Linux behavior changes. No device, credential, provider, or
generation path changes.

## Triage Result

The CI job `Test · Windows` reported 25 failing entries across 23 distinct tests.
The full suite was reproduced on a Windows 11 host (PowerShell 7.6.3, CPython
3.12.13, `uv sync --locked`, no extras) at branch head `30b65e2`. Between runs
the count varied (23 and 21 failing), which is itself consistent with the
timing-sensitive root cause in W1.

A diagnostic experiment applied the W1 fix alone on a throwaway clone and re-ran
the suite: **11 tests fixed, 0 newly broken.** The remaining 10 are the test
defects in W2-W6.

Classification:

| Finding | Tests | Kind |
| --- | --- | --- |
| W1 | 11 | product defect |
| W2 | 6 | POSIX-absolute-path fixtures |
| W3 | 1 | patch scope too narrow |
| W4 | 1 | test mechanism is POSIX-only |
| W5 | 2 | asserts a fault that cannot occur on Windows |

W6 is the verification slice; it adds no fix of its own.

## Authoritative Inputs

- `AGENTS.md` and `.agents/repo-guidance.md` govern process, verification, and
  Git rules.
- `am_configurator/ffmpeg_runtime.py` holds the already-reviewed precedent for
  W1: commit `3f550a1` removed exactly the offending fields from the equivalent
  helper in that module.
- Current code, and reproduction on a Windows host, are evidence for behavior.

## Windows Verification Environment

Slices W1-W5 cannot be verified on macOS or Linux; every one of them passes there
already. Each slice must be proven on a Windows host.

The triage environment is a clone at `F:\dev\am-win-triage` on the host reachable
as `michael@netwatch-01`, with `uv` at `~\.local\bin\uv.exe`. If that host is
unavailable, any Windows machine with git and `uv` works:

```powershell
$env:Path = "$HOME\.local\bin;$env:Path"
git clone --branch llm-led-generator https://github.com/roethlar/AMKB-GUI.git
cd AMKB-GUI
uv sync --locked -p 3.12      # no extras, exactly as ci.yml does
uv run --frozen -p 3.12 python -m unittest discover -s tests -v
```

Do not add `--extra desktop`. CI does not, and the extras-free environment is
what exposes these failures.

---

## W1 - Windows asset resolution rejects every banked asset

### Defect

`am_configurator/library.py:210`:

```python
def _file_stat_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
        getattr(details, "st_file_attributes", 0),
    )
```

The helper is used for TOCTOU identity comparison in two places, each comparing a
path-derived `lstat` against a descriptor-derived `fstat`:

- `OwnedAsset.open_verified`, `library.py:256` and `library.py:265-266`;
- `_file_integrity`, `library.py:656` and `library.py:666-667`.

On Windows, `st_ctime_ns` is the file creation time, and the value obtained from
a path query does not agree with the value obtained from an open handle for a
recently created file. The two sources are read at different resolutions, so the
comparison fails and a legitimate, unmodified asset is rejected.

Measured on the Windows host for a freshly banked asset:

```
field                lstat(before)            fstat(opened)            match
st_ctime_ns          1784931670069893300      1784931670070786100      NO
```

Every other field agreed. A file that has been settled for some time compares
equal on all seven fields, which is why the defect is intermittent and why the
Windows failure count varies between runs.

`am_configurator/ffmpeg_runtime.py` had exactly this defect and it was fixed in
commit `3f550a1` by reducing the tuple to content identity. `library.py` is the
last surviving instance; a repository sweep for `st_ctime_ns` and
`st_file_attributes` confirms the only other uses are legitimate reparse-point
checks at `library.py:223` and `library.py:348`.

### User impact

`resolve_asset` and `open_verified` are the authenticated asset-serving path.
On Windows, banked Library assets - thumbnails, previews, generated media -
fail to load. This is the only user-facing defect in this plan.

### Change

Reduce the tuple to content identity, matching `ffmpeg_runtime.py`:

```python
def _file_stat_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_size,
        details.st_mtime_ns,
    )
```

Nothing is weakened. `st_mode` and reparse status are already asserted directly
against both the path and the descriptor, before and after reading, at
`library.py:648`, `library.py:654-655`, `library.py:263`, and `library.py:247-248`.
Those checks must remain exactly as they are.

Do not change `_stat_is_reparse_point`, and do not touch `ffmpeg_runtime.py`.

### Regression guard

A source-substring assertion is not sufficient here; the guard must exercise the
comparison. Add a test that builds a real regular file, takes its `lstat`, opens
it, takes its `fstat`, and asserts the two identities compare equal. On Windows
that test fails against the seven-field tuple and passes against the four-field
tuple. On POSIX it passes either way, so also assert the tuple's exact length and
that `st_ctime_ns` is absent from it, so the guard has teeth on every platform.

### Verification

1. On Windows, confirm the 11 tests listed below fail before the change and pass
   after it:
   - `test_app.LightingStudioEndpointTests.test_asset_streaming_enforces_ownership_mime_and_bounded_single_ranges`
   - `test_generation.HistoricalGenerationRecoveryTests.test_banked_animation_recovery_is_idempotent`
   - `test_generation.HistoricalGenerationRecoveryTests.test_banked_concept_response_is_adopted_without_a_provider`
   - `test_generation.HistoricalGenerationRecoveryTests.test_recovery_retries_safe_reads_without_replaying_a_submission`
   - `test_generation.HistoricalGenerationRecoveryTests.test_startup_resumes_only_the_accepted_request_and_banks_local_artifacts`
   - `test_library.GeneratedAssetLibraryTests.test_manifest_symlink_and_asset_content_tampering_are_rejected`
   - `test_library.GeneratedAssetLibraryTests.test_partial_assets_survive_interrupted_concept_reconciliation`
   - `test_library.GeneratedAssetLibraryTests.test_restart_reconciliation_never_repeats_paid_work`
   - `test_library.GeneratedAssetLibraryTests.test_traversal_symlink_escape_and_wrong_ownership_are_rejected`
   - `test_procedural_generation.ProceduralGenerationTests.test_local_job_banks_exact_recipe_raster_preview_and_mapping`
   - `test_procedural_generation.ProceduralGenerationTests.test_reconcile_adopts_completely_banked_procedural_artifacts`
2. Confirm no test that passed before the change fails after it.
3. Run the full entry point on the development platform.

---

## W2 - POSIX-absolute-path fixtures are not absolute on Windows

### Defect

`Path("/absolute/ffmpeg").is_absolute()` is `False` on Windows, because the path
carries no drive. Production code correctly requires absolute paths, so six tests
supply a fixture that production rejects before reaching the behavior under test.

Production checks, both correct and unchanged by this slice:

- `am_configurator/media.py:803` - `not Path(command[0]).is_absolute()` raises
  `MediaError("config", "FFmpeg command is invalid")`.
- `build_tools/ffmpeg_bundle.py:785` - raises
  `BundleError("FFmpeg build tool {role} must have an absolute path")`.

Affected tests and their fixtures:

| Test | File | Fixture |
| --- | --- | --- |
| `test_cancellation_terminates_then_kills_without_shell` | `tests/test_media.py:1027` | `/absolute/ffmpeg` |
| `test_failed_process_separates_bounded_diagnostics_from_stable_error` | `tests/test_media.py:1069` | `/absolute/ffmpeg` |
| `test_timeout_stops_process_and_windows_uses_no_console_flag` | `tests/test_media.py:1083` | `/absolute/ffmpeg` |
| `test_build_plan_uses_argument_arrays_reproducible_flags_and_no_network` | `tests/test_ffmpeg_bundle.py` | `/opt/am-tools/cc` |
| `test_verified_archive_build_extracts_its_own_fresh_source_then_attests` | `tests/test_ffmpeg_bundle.py` | `/opt/am-tools/cc` |
| `test_windows_gpg_runs_inside_the_profileless_msys2_shell` | `tests/test_ffmpeg_bundle.py:454` | `/msys2/usr/bin/bash.exe` |

The last one fails differently: it asserts `command[0]` equals the literal
`"/msys2/usr/bin/bash.exe"`, but the runner emits `str(Path(...))`, which is
`\msys2\usr\bin\bash.exe` on Windows.

These six are one finding with one root cause and are fixed in one commit.

### Change

Add a single test helper that yields a platform-appropriate absolute path, and
route every fixture above through it. Something equivalent to:

```python
def _absolute_fixture(*parts: str) -> str:
    """An absolute path on this platform, for production absolute-path checks."""
    root = "C:\\" if os.name == "nt" else "/"
    return str(Path(root, *parts))
```

Place it where both test modules can use it, or define it in each module if the
suite has no shared test-support module; do not create a new package for it.

For the gpg test, assert against `str(msys2_bash)` rather than a hardcoded
POSIX literal, so the assertion states "the runner invoked the bash it was
given" instead of restating a path spelling. The remaining assertions in that
test about `--noprofile`, `--norc`, `-lc`, the exported `PATH`, the exported
`GNUPGHOME`, and the `exec` line must keep asserting msys-style forward-slash
values, because `_msys_path` is supposed to produce those regardless of platform.

Do not relax either production absolute-path check.

### Verification

All six tests pass on Windows and continue to pass on the development platform.

---

## W3 - Windows preflight consumes the UUIDs the test allocated

### Defect

`tests/test_library.py:480` `test_uuid_collisions_never_reuse_or_delete_existing_jobs_or_assets`
patches `am_configurator.library.uuid.uuid4` with `side_effect=[collision, fresh]`,
exactly two values, then calls `create_job`.

`create_job` calls `preflight()`, and on Windows only, `preflight()` calls
`_run_windows_path_depth_probe`, which consumes two `uuid.uuid4()` calls of its
own (`library.py`, the probe's `probe_job` and `intent` paths). Both patched
values are consumed by the probe, and the job-ID loop raises `StopIteration`.

The probe is correct production code, added by F58; the test predates it and has
never run on Windows.

### Change

The test already patches `am_configurator.library._run_write_probe` for the same
class of reason. Patch `am_configurator.library._run_windows_path_depth_probe`
alongside it, inside the same `with` block, so the patched UUID sequence is
consumed only by the code under test.

Do not widen the `side_effect` list with extra values; that would silently couple
the test to the probe's current UUID count.

Note that the `self.library.preflight()` call at the top of the test is outside
the patch and must stay outside it; it exercises the real probe.

### Verification

The test passes on Windows and on the development platform, and still proves that
a colliding job ID is skipped and the pre-existing job's sentinel file is
untouched.

---

## W4 - The binary-mode test defeats binary mode on real Windows

### Defect

`tests/test_ffmpeg_bundle.py:340` `test_shared_ffmpeg_reader_opens_windows_files_in_binary_mode`
patches `ffmpeg_runtime.os.O_BINARY` to a synthetic flag `1 << 29` and patches
`os.open` with a wrapper that strips that flag before delegating.

On POSIX this correctly proves the production reader requests a binary flag. On
Windows it is self-defeating: production obtains the flag through
`getattr(os, "O_BINARY", 0)`, which the test has replaced, so production never
sets the real `os.O_BINARY` (`0x8000`). The wrapper then strips the synthetic
flag, and the descriptor is opened in text mode. The payload is written as
`{"ok": true}\r\n`; text mode collapses `\r\n` to `\n`, the read returns fewer
bytes than `st_size`, the `total != opened.st_size` check at
`ffmpeg_runtime.py:170` fails, and `FfmpegRuntimeError` is raised.

The failure confirms rather than contradicts production correctness: removing
binary mode breaks the read exactly as the binary-mode requirement predicts.

### Change

Capture the real `os.O_BINARY` before patching, and have the wrapper restore it
when delegating, so the descriptor is still opened in binary mode on Windows
while the synthetic flag still proves production requested it:

```python
real_binary = getattr(os, "O_BINARY", 0)

def open_without_synthetic_flag(path, flags):
    observed_flags.append(flags)
    return real_open(path, (flags & ~binary_flag) | real_binary)
```

Keep both existing assertions: exactly one `os.open` call, and the synthetic flag
present in the observed flags.

Do not skip this test on Windows. Windows is the platform whose behavior it
describes, and with this change it is a genuine check there.

### Verification

The test passes on Windows and on the development platform, and still fails if
production stops requesting `O_BINARY`.

---

## W5 - Two tests inject a fault Windows cannot produce

### Defect

`tests/test_media.py:523` `test_directory_fsync_failure_rolls_back_existing_destination`
and `tests/test_media.py:551` `test_failed_rollback_preserves_previous_destination_backup`
both assert `MediaError` is raised when a directory fsync fails. Directory fsync
is a deliberate no-op on Windows, settled by P20, so the injected fault never
fires, no error is raised, and both assertions fail with `MediaError not raised`.

### Change

Skip both on Windows with an explicit reason, following the precedent already in
the suite. `tests/test_library.py` already contains
`test_directory_fsync_surfaces_real_io_errors_only`, which skips with
`"directory fsync is not exposed on Windows"`. Use the same phrasing so the two
read as one policy.

A skip is correct here rather than a Windows-specific branch: there is no Windows
behavior to assert, because the platform has no directory fsync to fail. Do not
add a Windows fsync shim to make the tests pass.

### Verification

Both tests skip on Windows with a visible reason and continue to pass on POSIX.
Confirm the Windows skip count rises from 4 to 6.

---

## W6 - Full-matrix verification

No code change. Confirm the whole gate before the plan is closed.

1. On Windows, the full suite reaches `OK` with the expected skips:
   `uv run --frozen -p 3.12 python -m unittest discover -s tests -v`
2. Run it a second time. The count must be identical; run-to-run variance was a
   symptom of W1 and must be gone.
3. On the development platform, run the full entry point from
   `.agents/repo-guidance.md`.
4. Push and confirm all seven CI checks pass, including `Test · Windows` and
   `Installer · Windows x64`.

## Completion

The plan is complete when all five fixes are committed one per commit, CI is
green on every platform, and `.agents/state.md` records the W1 user impact, the
11-test experiment result, and the Windows suite's final pass count.

Code signing and notarization remain out of scope and unaddressed. Hardware
acceptance across CyberBoard, Relic 80, and AFA remains a separate external
release prerequisite.
