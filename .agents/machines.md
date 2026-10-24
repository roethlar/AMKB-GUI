# Machine Notes

Per-machine facts that do not belong in the portable `state.md`.

## netwatch-01 (Windows 11, x86-64)

_Last verified locally: 2026-07-31. SSH reachability recheck as `4cf4d13`
on 2026-08-22 timed out; the host may simply be off._

- **Observed locally on 2026-10-24 (as `b699548`), superseding the tool and
  path bullets below until rechecked:** the host named `NETWATCH-01` now
  reports Microsoft Windows Server 2025 Standard (build 26100).
  `C:\Users\michael\dev` is a plain directory, not a reparse point, and `F:\dev`
  does not exist. `uv` is not installed (no `C:\Users\michael\.local\bin\uv.exe`,
  none on `PATH`) and Node is not on `PATH`, so the recorded verification entry
  point cannot run here; GitHub Actions CI stood in for it. Python 3.14.7 exists
  at `C:\Users\michael\AppData\Local\Programs\Python\Python314\python.exe` but
  is not on `PATH`, where `python` is the Microsoft Store alias. `gh` and
  `tea` are on `PATH`, and a non-interactive push to `github` worked.
- Reachable as `michael@netwatch-01` over SSH with key auth from `nagatha`.
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

_Key auth last verified 2026-08-03. SSH recheck as `4cf4d13` on
2026-08-22 reported “Host is down”; no machine facts were revalidated._

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

_Last verified locally as `4cf4d13` on 2026-08-22._

- This is the owner’s Mac, formerly recorded as `michael-mac`; older records
  and plans using that name mean this host.
- Current hostname is `q.lan`; the machine is macOS 27.0, Darwin 27.0.0,
  arm64. Gatekeeper assessments are enabled.
- Exact-artifact qualification tools are available: `hdiutil`, `codesign`,
  `spctl`, `xattr`, `shasum`, `curl`, `file`, `open`, and `ditto`.
  The writable data volume had about 23 GiB free.
- GitHub CLI 2.98.0, `uv` 0.12.5, and Node 26.7.0 are on `PATH`.
  `/usr/local/bin/ollama` is installed. Neither `flatpak` nor
  `flatpak-builder` is installed.
- The active checkout is `/Users/michael/Dev/AMKB-GUI`; `origin` is the
  local Gitea remote and `github` is the public GitHub remote. The checkout
  currently has no `.venv`; exact downloaded-artifact checks do not depend on
  a project environment.
- The owner may operate the GUI directly or permit SSH-driven command checks.
  Availability never authorizes an Open Anyway interaction or hardware write.

## gabrielle (Linux x86-64)

_Last verified over SSH as `4cf4d13` on 2026-08-22._

- Reachable as `michael@gabrielle`; Arch Linux, kernel 7.1.8-arch1-3,
  x86-64. The home filesystem had about 1.7 TiB free.
- Qualification tools include Git 2.55.0, Python 3.14.7, Node 26.7.0, GitHub
  CLI 2.98.0, `uv` 0.12.5, `curl`, `file`, `sha256sum`, FUSE,
  `flatpak`, and `flatpak-builder`.
- The Flatpak `io.github.roethlar.AMConfigurator` is installed from the
  checkout at `d5c7f4e`; `flatpak run io.github.roethlar.AMConfigurator
  --smoke-test` passed again on 2026-08-22.
- An ordinary SSH shell has no `DISPLAY` or `WAYLAND_DISPLAY`. Unprivileged
  user namespaces, subordinate IDs, `unshare`, and `bwrap` are available;
  a disposable Ubuntu 24.04 rootfs can run Xvfb for exact AppImage inspection
  without changing host packages.
- Qualification checkouts and Ubuntu-rootfs paths are transient, not durable
  machine facts. Exact downloaded-artifact checks must create their own
  isolated working root; no physical-keyboard test is needed.
