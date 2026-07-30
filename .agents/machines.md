# Machine Notes

Per-machine facts that do not belong in the portable `state.md`.

## netwatch-01 (Windows 11, x86-64)

_Last verified locally: 2026-07-30; SSH reachability and suite timing were
last verified 2026-07-29._

- Reachable as `michael@netwatch-01` over SSH with key auth from `michael-mac`.
  Resolution is not always available; it failed until the owner brought the host
  up, so treat a name-resolution failure as "ask the owner", not "host is gone".
- Default SSH shell is PowerShell 7.6.3. Quoting through
  macOS PowerShell to bash to SSH to Windows PowerShell is unreliable: write a
  `.ps1`, `scp` it over, and run `pwsh -NoProfile -File`.
- System Python is 3.14 only. `uv` was installed for this work at
  `C:\Users\michael\.local\bin\uv.exe` and is not on the default PATH; prepend
  it per session. `uv` fetches its own CPython 3.12 for the project.
- `C:\Users\michael\dev` is a reparse point to `F:\dev`. Creating directories
  through the junction failed once while `F:` was not ready; the owner asked for
  `F:\dev` directly. This matters for the product too, because `library.py`
  preflight rejects a reparse-bearing Library root.
- Windows verification must build the environment the way CI does,
  `uv sync --locked -p 3.12` with no extras. Adding `--extra desktop` hides the
  optional-dependency failures this host is used to catch.
- The Windows suite is slower than macOS, about 102 s against 84 s, and was
  non-deterministic before the `st_ctime_ns` fix. It should now report identical
  counts across consecutive runs; variance is a signal, not noise.
- The current checkout has the pinned `ffmpeg-8.1.2.tar.xz` and detached
  signature staged under `build/ffmpeg/sources`; the archive SHA-256 is
  `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`,
  matching `build_tools/ffmpeg_bundle.py`.
- No MinGW `cc` or Inno Setup 6 compiler is available. Visual Studio Build
  Tools 2026 is installed, but the attested FFmpeg recipe pins
  `--target-os=mingw32`, so MSVC cannot substitute for MinGW. The owner's
  2026-07-30 rulings prohibit installing a non-Microsoft toolchain on this host
  and prohibit a local FFmpeg source compile.
- SmartScreen is disabled: the machine-level `SmartScreenEnabled` value is
  `Off`, and the current-user `EnableWebContentEvaluation` value is `0`. This
  host cannot supply SmartScreen release evidence.

## michael-mac additions

_Last verified: 2026-07-28_

- `build.py` no longer reserves or stamps local build numbers. Native artifacts
  use the canonical application version unchanged; existing older DMGs in
  `dist/` do not affect it. <!-- lint: allow (owner ruled leave-it, 2026-07-29: dist/ is gitignored build output, exists only after native builds) -->
- `packaging/macos/build_dmg.sh` cannot be re-run against an already finalized
  bundle in `dist/`; FFmpeg finalization refuses the second pass. <!-- lint: allow (owner ruled leave-it, 2026-07-29: dist/ is gitignored build output, exists only after native builds) -->
  Use `python build.py --skip-sync` for an end-to-end DMG check.

## michael-mac (macOS arm64)

_Last verified: 2026-07-21_

- Repo checkout: `/Users/michael/Dev/am`, shell `zsh`, Darwin 25.5.0
  (macOS 26.5.2).
- Project venv at `.venv/` with Python 3.13.14; run tests via
  `.venv/bin/python -m unittest` (system `python3` also 3.13).
- Local macOS arm64 PyInstaller bundle builds here and its frozen
  `--smoke-test` passes.
- Ollama is installed locally. On 2026-07-21, `ornith:latest` successfully
  produced the strict procedural-animation recipe after a bounded semantic
  retry; `gemma4:12b-mlx` ignored the requested JSON schema and failed the same
  task. The proof therefore defaults to `ornith:latest` on this machine.
- `/usr/bin/cc` reports Apple clang 21.0.0. The Task 6 helper produced two
  byte-identical FFmpeg 8.1.2 runtimes with SHA-256
  `18664dd97929bd0e155339150cb4491a8032c5585760270dc028e20ee12b8a3a`;
  the cached attestation reports the same compiler identity, and the runtime
  passed real exact-frame checks for all three device caps.
- GPG is not installed. The official FFmpeg archive's detached signature and
  exact release-key fingerprint were cryptographically checked with isolated
  PGPy during Task 6 preflight, but PGPy's warnings mean this is not a release
  substitute; the production offline build helper requires GPG and disables
  automatic key retrieval.
