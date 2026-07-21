# Machine Notes

Per-machine facts that do not belong in the portable `state.md`.

## michael-mac (macOS arm64)

_Last verified: 2026-07-20_

- Repo checkout: `/Users/michael/Dev/am`, shell `zsh`, Darwin 25.5.0
  (macOS 26.5.2).
- Project venv at `.venv/` with Python 3.13.14; run tests via
  `.venv/bin/python -m unittest` (system `python3` also 3.13).
- Local macOS arm64 PyInstaller bundle builds here and its frozen
  `--smoke-test` passes.
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
