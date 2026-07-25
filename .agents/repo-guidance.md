# Repository Guidance

## Scope

`/Users/michael/Dev/am` is the standalone AM Configurator application. The
ignored `cyberboard-cli/` directory is reference material only: do not edit it,
commit from it, or introduce a runtime/build dependency on it.

The supported application scope is the native/local GUI, its device protocol,
profile store, tests, packaging, and CI for macOS, Windows, and Linux.

## Verification

Run the automated verification entry point from the repository root:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/app.js
uv build
```

This is the same command set `.github/workflows/ci.yml` enforces. CI is the
authoritative source; if the two ever disagree, fix this file.

Build the environment the way CI does when checking a change that could depend
on optional dependencies. `uv sync --locked` installs no extras, so a test that
reaches the real `webview` import passes locally under `--extra desktop` and
fails in CI.

For native distribution changes, build on the current operating system with
`python build.py --skip-sync` (or `python build.py` when dependencies need
synchronization) so the local build number is reserved and stamped. Then run
the frozen executable with `--smoke-test`. Do not invoke PyInstaller directly;
GitHub Actions owns equivalent native builds for the other operating systems.

## Device Safety

Automated tests and smoke tests must not write to a keyboard. Hardware writes
are manual actions initiated from the GUI and require device/model matching plus
typed confirmation.
