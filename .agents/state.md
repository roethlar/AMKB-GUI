# Repository State

## Now

- The standalone AM Configurator app, protocol implementation, browser assets,
  native desktop wrapper, tests, and cross-platform workflows are present as of
  `c8a722c`.
- The local macOS arm64 PyInstaller bundle builds and its frozen `--smoke-test`
  passes.
- The nested `cyberboard-cli/` checkout remains ignored reference material and
  is not part of the application.

## Next

- Run the committed CI and desktop-bundle workflows after this repository is
  connected to its intended GitHub remote.
- Continue hardware verification across CyberBoard, Relic 80, and AFA firmware
  variants using portable JSON backups.

## Blockers

- None for local development or macOS packaging.
