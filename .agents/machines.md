# Machine Notes

Per-machine facts that do not belong in the portable `state.md`.

## netwatch-01 (Windows 11, x86-64)

_Last verified locally: 2026-07-31; SSH reachability and suite timing were
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
  passed during dependency removal on 2026-07-30. The exact downloaded
  `0.1.65` artifact repeated install, recursive audit, frozen smoke, and clean
  uninstall on 2026-07-31; its evidence is canonical in the completed
  product-experience plan.
- The supported Windows build does not require a compiler or Visual Studio
  Build Tools.
- GitHub and local Gitea push authentication work on this host. On 2026-07-30,
  Gitea Git authentication was repaired by registering `tea login helper` for
  `http://q:3000`; pushing `main` and tags then succeeded.
- SmartScreen is disabled: the machine-level `SmartScreenEnabled` value is
  `Off`, and the current-user `EnableWebContentEvaluation` value is `0`. This
  host cannot supply SmartScreen release evidence.

## win-arm-vm (Windows 11, ARM64)

_Last verified over SSH: 2026-07-31._

- Reachable as `michael@10.1.10.211`; hostname `WIN-RRRKRP63HA6`, Windows 11
  Pro 24H2 build 26100, ARM64. The clean VM has no SmartScreen-disabling user,
  machine, or policy value. Defender is running with real-time protection and
  PUA protection enabled. Preserve that default protection state for the
  exact-candidate Edge-download observation; do not change security settings.
- Installed build tools are native ARM64 Git 2.55.0 and `uv` 0.11.32, Inno
  Setup 6.7.3, Visual Studio Build Tools 2022 17.14 with the ARM64 C++ tools,
  and Windows 11 SDK 10.0.26100.0. The C++ workload is required because
  `hidapi` 0.15.0 has no Windows ARM64 wheel and must build locally.
- A clean canonical checkout at `C:\Users\michael\dev\AMKB-GUI` matched
  `9f482b3ce949ea013d2f3167bf6072c02f1c8cba` during preflight. An explicitly
  selected native ARM64 CPython 3.14.6 environment produced an ARM64 app,
  Python runtime, HID extension, and Pillow extension. The installer completed
  silent install, frozen smoke, uninstall, and direct frozen smoke with no
  leftover smoke directory.
- The first default `uv` environment selected x64 CPython under emulation.
  Because artifact naming reads the host architecture, that x64 bundle was
  misleadingly named `arm64`. A Windows ARM build must explicitly select the
  aarch64 Python environment and verify PE headers; do not use the first build.
- The exploratory ARM64 installer is not a `0.1.65` release candidate or public
  asset. This VM's approved release role is the independent default-SmartScreen
  observation for the exact x64 candidate downloaded normally through Edge;
  `netwatch-01` remains the x64 install, audit, smoke, and uninstall host.
- The pre-release x64 warning path was observed successfully on 2026-07-31:
  an Edge-downloaded Actions artifact retained Internet-zone metadata,
  SmartScreen first blocked the unknown publisher, **More info** exposed
  **Run anyway**, the installer opened, and the x64 application launched under
  emulation. Repeat the same observation with the final exact candidate; this
  preflight does not substitute for R65-4.

## nagatha (macOS arm64)

_Last verified over SSH: 2026-07-31. The owner was the active console user and
was RDP-connected from this host to the current `netwatch-01` session._

- Reachable as `michael@10.1.10.41`; hostname `nagatha.local`, macOS 26.6,
  Darwin 25.6.0, arm64. Gatekeeper assessments are enabled.
- Exact-artifact qualification tools are available: `hdiutil`, `codesign`,
  `spctl`, `xattr`, `shasum`, `curl`, `file`, `open`, and `ditto`. The temporary
  directory is writable and the data volume had about 273 GB free.
- GitHub CLI, `uv`, and Node are not on `PATH`. Attestation may be verified on
  `netwatch-01` before transfer and bound to the macOS bytes by matching the
  SHA-256 again on `nagatha`; do not install tools merely to duplicate that
  proof.
- A clean checkout exists at `/Users/michael/dev/AMKB-GUI` with canonical
  `origin`, but it was still at cached head `9dc81c5` and had no project venv.
  Do not use it as current-source evidence without a deliberate synchronization
  and environment-preparation step. Exact downloaded-artifact checks do not
  depend on that checkout.
- The owner may either operate the GUI directly or permit SSH-driven command
  checks. Availability does not authorize macOS Open Anyway or a keyboard
  write.

## gabrielle (Linux x86-64)

_Last verified over SSH: 2026-08-01._

- Reachable as `michael@gabrielle`; Arch Linux, kernel 7.1.5-arch1-1, x86-64.
  The home filesystem had about 1.7 TB free and the temporary directory is
  writable.
- Available qualification tools include Git 2.55.0, Python 3.14.6, Node
  26.5.0, GitHub CLI 2.96.0, `curl`, `file`, `sha256sum`, FUSE, and
  `fusermount3` 3.18.2. `uv` is not installed and is not needed for the planned
  exact-AppImage inspection.
- An ordinary SSH shell has no `DISPLAY` or `WAYLAND_DISPLAY`. Unprivileged
  user namespaces, subordinate IDs, `unshare`, and `bwrap` are available; a
  disposable Ubuntu 24.04 rootfs can run Xvfb and the exact AppImage without
  changing host packages. This path passed the real GTK/WebKit native-policy
  smoke and exposed helper executable origins for inspection.
- Qualification checkouts and Ubuntu rootfs paths are transient and are not
  durable machine facts. Exact downloaded-artifact checks must create or
  verify their own isolated working root; no physical-keyboard test is needed.

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
