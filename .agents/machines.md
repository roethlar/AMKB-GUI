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
- A fresh Python 3.12 base environment passed 639 tests (5 skipped) in 97.061
  seconds on 2026-07-30. A separate fresh desktop/build environment resolved all
  locked Windows packages and passed the canonical installer build.
- Winget-installed Inno Setup 6.7.3 is at
  `C:\Users\michael\AppData\Local\Programs\Inno Setup 6\ISCC.exe`; its
  Authenticode signature is valid. The Windows packager accepts both official
  machine-wide and current-user locations. The canonical installer,
  installed-executable smoke, recursive installed-tree audit, and uninstall all
  passed on 2026-07-30; exact artifact evidence is canonical in the active
  dependency-removal plan.
- The supported Windows build does not require a compiler or Visual Studio
  Build Tools.
- SmartScreen is disabled: the machine-level `SmartScreenEnabled` value is
  `Off`, and the current-user `EnableWebContentEvaluation` value is `0`. This
  host cannot supply SmartScreen release evidence.

## michael-mac additions

_Last verified: 2026-07-28_

- `build.py` no longer reserves or stamps local build numbers. Native artifacts
  use the canonical application version unchanged; existing older DMGs in
  `dist/` do not affect it. <!-- lint: allow (owner ruled leave-it, 2026-07-29: dist/ is gitignored build output, exists only after native builds) -->
- Use `python build.py --skip-sync` for an end-to-end DMG check against an
  already prepared environment.

## michael-mac (macOS arm64)

_Last verified: 2026-07-21_

- Repo checkout: `/Users/michael/Dev/am`, shell `zsh`, Darwin 25.5.0
  (macOS 26.5.2).
- Project venv at `.venv/` with Python 3.13.14; run tests via
  `.venv/bin/python -m unittest` (system `python3` also 3.13).
- Local macOS arm64 PyInstaller bundle builds here and its frozen
  `--smoke-test` passes.
- Ollama is installed locally. On 2026-07-21, `ornith:latest` produced a strict
  procedural-animation recipe while `gemma4:12b-mlx` ignored the requested JSON
  schema. Current production generation makes one request without automatic
  correction retries, so model availability and conformance must be rechecked
  rather than inferred from that historical run.
