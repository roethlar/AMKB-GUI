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
uv run --frozen python -m compileall -q am_configurator packaging
node --check am_configurator/web/app.js
uv build
```

For native distribution changes, also build on the current operating system and
run the frozen executable with `--smoke-test`. GitHub Actions owns equivalent
native builds for the other operating systems.

## Device Safety

Automated tests and smoke tests must not write to a keyboard. Hardware writes
are manual actions initiated from the GUI and require device/model matching plus
typed confirmation.
