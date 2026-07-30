# FFmpeg Removal and Dependency Ownership Audit

**Status:** Approved and in progress. The owner approved implementation on
2026-07-30. AI is procedural-only, FFmpeg must be removed entirely, and
dependencies without a live supported responsibility must not remain.
Installing Inno Setup 6 on the Windows verification host is a separate host
mutation and remains owner-gated.

## Authority and supersession

The canonical decision is
`.agents/decisions.md#2026-07-30--ai-is-procedural-only-and-ffmpeg-is-prohibited`.
Apply it literally:

- AI produces a strict JSON procedural LED recipe.
- Python/Pillow validates and renders the recipe locally into exact-target LED
  frames.
- No new or historical product path requests, downloads, processes, resumes, or
  displays generated video.
- FFmpeg is absent from runtime code, source/build tooling, CI, native
  packaging, tests, recovery, active documentation, and current-state
  guidance.
- Existing user files are never deleted automatically while legacy execution
  support is removed.
- A dependency remains only when it owns a live supported product or artifact
  responsibility.

This plan supersedes:

- the video-generation, historical video recovery, and FFmpeg clauses of
  `.agents/decisions.md`'s 2026-07-20 Video-first Lighting Studio decision;
- Slice B4 of
  `docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md`, whose only
  remaining work was a native smoke blocked by the obsolete FFmpeg build;
- every active release-plan instruction that requires an FFmpeg runtime,
  source archive, signature, attestation, or native media smoke.

The 2026-07-27 Imported media and AI generation decision remains authoritative:
GIF/PNG/BMP composition is separate from AI, and AI renders a procedural recipe
locally.

## Baseline evidence

### Reachability

- `am_configurator/web/app.js::startProceduralGeneration` posts only to
  `/api/lighting/effects`.
- `am_configurator/server.py::_start_procedural_effect` delegates only to
  `ProceduralGenerationCoordinator.start_effect`.
- `ProceduralGenerationCoordinator._run` sends a `RecipeRequest`, receives
  `RecipeResult.recipe`, renders it through
  `render_recipe_frames_to_exact_target`, writes GIF previews with Pillow, and
  maps the frames to the target. It has no FFmpeg call.
- `/api/lighting/concepts`, `/api/led/generate`, and job actions
  `concepts`/`animate`/`process` already return the retired-AI response.
- `GenerationCoordinator` describes itself as historical recovery without paid
  mutation entry points. It is the only production owner of
  `XaiVideoProvider`, video download, MP4 banking, and `process_video_frames`.
- `get_ffmpeg_runtime` has only two production consumers: the historical
  coordinator and the native FFmpeg smoke.

### Current direct dependency inventory

| Dependency | Scope | Live responsibility | Disposition |
| --- | --- | --- | --- |
| `hidapi` | runtime | HID discovery and transport for supported HID keyboards in `hid_transport.py` | keep |
| `pyserial` | runtime | serial discovery, read, write, and macro transport in `device.py`, `reader.py`, `writer.py`, and `macros.py` | keep |
| `pillow` | runtime | procedural rendering, GIF/image composition, validation, preview generation, and LED mapping | keep |
| `keyring` | runtime | platform secure credential stores; plaintext fallback is prohibited | keep |
| `pywebview` | desktop extra | native desktop window and platform webview backend | keep |
| `pyinstaller` | build extra | native application bundle creation | keep |
| `hatchling` | PEP 517 build backend | wheel and sdist creation exercised by `uv build` | keep |

The runtime import audit finds no undeclared third-party Python import. The
production third-party import roots are `hid`, `serial`, `PIL`, `keyring`, and
`webview`; `AppKit` is a macOS platform dependency supplied by pywebview's
PyObjC stack.

There is no `package.json` or JavaScript package lock. Browser tests use Node's
built-in test runner, and application JavaScript has no third-party package
dependency. Provider HTTP clients and the loopback server use the Python
standard library rather than vendor SDKs or a web framework.

### Current external build-tool inventory

| Tool or package | Current owner | Disposition |
| --- | --- | --- |
| FFmpeg source/runtime | retired historical video path | remove |
| GnuPG | FFmpeg source-signature verification only | remove |
| MSYS2, MinGW, GNU Make, diffutils | Windows FFmpeg build only | remove |
| `build-essential`, `zlib1g-dev` in desktop CI | Linux FFmpeg build only | remove after proving desktop sync/build still succeeds |
| Visual Studio Build Tools | no repository command or package path | do not require or invoke |
| Inno Setup 6 | Windows installer compiler | keep, build-only |
| `codesign`, `hdiutil`, `ditto` | macOS app/DMG packaging | keep, operating-system tools |
| pinned `appimagetool` | Linux AppImage packaging | keep, build-only |
| Linux X11/Qt runtime libraries | headless pywebview/Qt native smoke | keep |

After FFmpeg removal, a normal Windows installer build requires Python 3.12,
uv, the locked desktop/build extras, PyInstaller, and Inno Setup. It does not
compile C/C++ project code and does not require Visual Studio Build Tools.

### Misplaced package code

`am_configurator/local_animation.py` has no product importer. It is a
developer-only Ollama qualification adapter imported dynamically by
`build_tools/qualify_recipe_model.py` and tested by
`tests/test_local_animation.py`. Production already owns
`recipe_provider.OllamaRecipeProvider`; retaining a second invocation adapter
inside the shipped package is duplicate responsibility.

## Scope

In scope:

1. Remove the retired AI-video runtime and historical execution/recovery path.
2. Remove FFmpeg and every FFmpeg-only source, binary, license, attestation,
   cache, workflow, test, and build prerequisite.
3. Refactor the model-qualification tool to use the production Ollama recipe
   provider, then remove the developer-only shipped adapter.
4. Add a no-new-dependency audit guard implemented with the standard library.
5. Prove every retained direct dependency and external build tool owns the live
   responsibility listed above.
6. Rebuild and inspect native artifacts to prove removed dependencies do not
   survive transitively or as stale bundled data.
7. Synchronize current plans, decisions, state, machine notes, release guidance,
   notices, and developer documentation.

Out of scope:

- changing procedural recipe semantics, rendering, quality validation, or LED
  mapping;
- removing GIF/PNG/BMP import or composition;
- replacing justified libraries with custom security, image, HID, serial,
  desktop-window, or packaging implementations merely to reduce a count;
- deleting or rewriting user library files;
- changing device read/write safety gates;
- publishing a release or announcement;
- installing host software without a separate owner go.

## Commit and verification discipline

- Land one finding per commit. Do not combine the runtime retirement, FFmpeg
  packaging removal, developer-adapter removal, dependency guard, or record
  closure.
- Before each commit, run the focused suites named by that slice.
- After every new regression test, prove the guard by temporarily reverting the
  production change, confirming the test fails, restoring the change, and
  confirming the test passes.
- Run the repository's complete verification entry point after each production
  slice and once more at final closure.
- Do not amend, squash, reorder, or otherwise rewrite landed commits.

## Slice R1 — Remove the retired AI-video runtime

### Production changes

1. Delete `am_configurator/generation.py`.
2. In `am_configurator/server.py`:
   - remove `GenerationCoordinator`, `_lighting_coordinator`, its dependency
     injection surface, and its reconciliation signature;
   - make lighting startup reconciliation procedural-only;
   - remove xAI-key resolution that exists only to resume accepted video
     requests;
   - retain procedural cancellation;
   - return the existing retired/`410 Gone` response for every legacy
     concept/video mutation or non-procedural resume attempt;
   - drop `video/mp4` from `_LIGHTING_ASSET_MIMES` if no live non-video feature
     consumes it.
3. In `am_configurator/llm.py`, remove `XaiVideoProvider`, `VideoStatus`, and
   video polling/request helpers and constants. Preserve shared provider error,
   usage, redaction, bounded HTTP, and recipe-provider behavior.
4. In `am_configurator/library.py`:
   - remove `source_video` as an accepted asset kind;
   - remove `video/mp4` from generated preview types;
   - remove video-request and source-video resume/reconcile branches;
   - keep generic file integrity and ownership checks;
   - when an old video manifest is scanned, fail it closed as unsupported
     without modifying or deleting its directory or assets.
5. In `am_configurator/web/app.js`, remove source-video labels, generated-MP4
   display branches, and legacy asset selection. Preserve procedural
   `preview_animation` GIF behavior.

### Tests

- Delete `tests/test_generation.py`.
- Remove historical video-resume cases from `tests/test_app.py`,
  `tests/test_library.py`, `tests/test_ai_routes.py`, and browser source guards.
- Retain or add behavior tests proving:
  - `/api/lighting/effects` starts only the procedural pipeline;
  - all retired AI-video endpoints return `410 Gone` and start no provider or
    worker;
  - startup reconciliation never requests an xAI key for video;
  - an old video-job directory is left byte-for-byte untouched and is not
    resumed;
  - procedural generation still produces a recipe, GIF preview, mapped result,
    and exact target frames.

### Focused verification

```text
uv run --frozen python -m unittest \
  tests.test_ai_routes \
  tests.test_app \
  tests.test_library \
  tests.test_media \
  tests.test_procedural_generation -v
node --test tests/web/lighting_shell.test.js
```

Commit as one retired-subsystem finding.

### Implementation sequencing record

R1 completed on 2026-07-30 in the commit containing this record. The complete
verification entry point passed: 702 Python tests (8 skipped), 125 browser
tests, every JavaScript syntax check, Python byte-compilation, and wheel/sdist
build. The new retirement guards were also proved red by temporarily restoring
their production seams, then green after restoration.

R1 makes the retained low-level video implementation unreachable from every
production API, coordinator, startup-recovery, library, and UI path. Deleting
the video-only portion of `am_configurator/media.py` and its
`tests/test_media.py` cases is sequenced into R2 so the FFmpeg implementation,
runtime resolver, package data, build tooling, native smoke, and tests disappear
as one atomic finding rather than leaving an untestable split subsystem between
commits.

## Slice R2 — Remove FFmpeg from runtime, builds, and artifacts

### Delete

- The video-only subsystem in `am_configurator/media.py`:
  `DownloadedVideo`, `ProcessedAnimation`, video URL/download helpers, FFmpeg
  command construction/execution, local MP4 frame processing, and video-only
  cancellation/publication helpers. Preserve image/GIF validation and every
  function called by media composition or procedural generation.
- The corresponding video-only cases in `tests/test_media.py`.
- `am_configurator/ffmpeg_runtime.py`
- `build_tools/ffmpeg_bundle.py`
- `build_tools/prepare_ffmpeg.py`
- `build_tools/finalize_ffmpeg_bundle.py`
- `packaging/ffmpeg/`
- `tests/test_ffmpeg_bundle.py`
- `tests/fixtures/tiny-motion.mp4`

Remove ignored `build/ffmpeg/` material only after resolving its absolute path
inside the workspace and treating it as disposable generated data. Do not
delete any broader `build/` or user-library directory.

### Build and packaging changes

1. Remove the `build_tools.prepare_ffmpeg` step from `build.py`.
2. In `packaging/am_configurator.spec`:
   - remove the runtime resolver import;
   - remove the FFmpeg binary;
   - remove FFmpeg metadata, attestation, license, and source-offer data;
   - remove the MP4 smoke fixture;
   - preserve platform keyring/webview hidden imports and project notices.
3. Remove `_run_ffmpeg_media_smoke` from `am_configurator/desktop.py` and stop
   calling it from `run_smoke_test`. Keep disabled-AI, API-recipe,
   Ollama-recipe, native-webview, loopback, and asset smokes.
4. Remove FFmpeg finalization from `packaging/macos/build_dmg.sh`; retain outer
   app ad-hoc signing and DMG verification.
5. In `.github/workflows/desktop.yml`, remove:
   - macOS GnuPG installation;
   - Windows MSYS2/MinGW setup;
   - FFmpeg source staging, cache, preparation, and tool-path wiring;
   - Linux `build-essential`, `gnupg`, and `zlib1g-dev` unless a fresh desktop
     sync/build proves a remaining owner. Keep the Qt/X11 packages.
6. Remove the FFmpeg paragraph from `THIRD_PARTY_NOTICES`.
7. Remove the FFmpeg manifest rule from `.gitattributes`.
8. Remove obsolete FFmpeg comments or allowlist rationale from
   `pyproject.toml`, tests, README, and active plans. Historical plans and review
   reports retain their original evidence but receive a short supersession
   pointer where they could otherwise be mistaken for current instructions.

### Regression guards

Update `tests/test_packaging.py` to assert all of the following:

- `build.py` invokes dependency sync, PyInstaller, and the platform packager
  without an FFmpeg preparation command;
- the PyInstaller spec has no FFmpeg binary/data or MP4 fixture;
- desktop CI contains no FFmpeg, GnuPG, MSYS2, MinGW, GNU Make, diffutils,
  `build-essential`, or `zlib1g-dev` setup;
- macOS packaging contains no FFmpeg finalizer;
- `THIRD_PARTY_NOTICES` contains no FFmpeg source offer;
- the deleted FFmpeg paths do not exist.

Add an absence guard over current product/build surfaces, excluding historical
plans, archived state, and historical review reports. It must fail if the token
`ffmpeg` is reintroduced under `am_configurator/`, `build_tools/`,
`packaging/`, `.github/workflows/`, `tests/`, `build.py`, `pyproject.toml`,
`.gitattributes`, `README.md`, or `THIRD_PARTY_NOTICES`.

### Focused verification

```text
uv run --frozen python -m unittest \
  tests.test_desktop \
  tests.test_packaging -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
uv build
```

Inspect the rebuilt wheel and sdist and assert that neither contains an FFmpeg
module, manifest, license, GPG key, MP4 fixture, source helper, or generated
runtime.

Commit as one bundled-dependency finding.

### Implementation sequencing record

R2 completed on 2026-07-30 in the commit containing this record. The retired
media module, FFmpeg runtime and build helpers, package metadata, native smoke,
CI toolchains, fixtures, and tests are gone. GIF/PNG/BMP composition and
procedural Pillow rendering remain supported.

The focused R2 suite passed 74 tests (2 skipped). The complete verification
entry point passed 638 Python tests (5 skipped), 125 browser tests, every
JavaScript syntax check, Python byte-compilation, and wheel/sdist builds. The
rebuilt wheel (50 files) and sdist (114 files) contained none of the retired
runtime, source, license, fixture, or identifying token. New absence guards were
proved red by temporarily restoring the retired media module, workflow
toolchain references, and third-party notice, then green after restoration.

## Slice R3 — Remove the developer-only shipped adapter

1. Refactor `build_tools/qualify_recipe_model.py` to construct the production
   `OllamaRecipeProvider` with an `OllamaClient` configured for the requested
   endpoint and a validated `OllamaModel`.
2. Build a production `RecipeRequest` from each qualification case and call the
   provider's normal one-request `generate` path. Do not retain independent
   sampling parameters, retry wording, retry counts, or response parsing.
3. Delete `am_configurator/local_animation.py` and
   `tests/test_local_animation.py`.
4. Update `tests/test_recipe_inference.py` and qualification tests so they prove
   the tool delegates to the production provider contract.
5. Confirm no developer-only module remains as an unreferenced top-level module
   inside the shipped `am_configurator` package.

Guard proof: temporarily restore the dynamic import of
`am_configurator.local_animation` and confirm the new delegation/absence guard
fails.

Commit as one misplaced-code finding.

### Implementation sequencing record

R3 completed on 2026-07-30 in the commit containing this record. The
qualification CLI now discovers the requested model through the production
Ollama client, constructs the production provider with that exact inventory
record, and submits one production `RecipeRequest` per corpus case. It no longer
owns payload construction, sampling defaults, parsing, or retry behavior. The
duplicate shipped adapter and its isolated tests are gone.

The focused provider/qualification suite passed 46 tests. The complete entry
point passed 633 Python tests (5 skipped), 125 browser tests, every JavaScript
syntax check, Python byte-compilation, and wheel/sdist builds. The rebuilt wheel
(49 files) and sdist (112 files) contain neither the retired adapter nor its
client type. The absence/delegation guard was proved red by temporarily
restoring the dynamic import, then green after restoration.

## Slice R4 — Enforce dependency ownership without adding an audit dependency

Add `tests/test_dependencies.py` using only `ast`, `importlib.metadata`,
`pathlib`, `sys`, and `tomllib`.

The test must:

1. Parse `[project.dependencies]`, `[project.optional-dependencies]`, and
   `[build-system].requires` from `pyproject.toml`.
2. Build a production import graph for `am_configurator`, `build_tools`,
   `build.py`, and `packaging/launcher.py`.
3. Use installed distribution metadata to map runtime distribution names to
   import roots and fail when a direct runtime dependency owns no production
   import.
4. Check optional/build dependencies against their executable owners:
   `pywebview` → desktop imports, `pyinstaller` → build/spec/workflow,
   `hatchling` → configured build backend and successful `uv build`.
5. Fail when an `am_configurator` top-level module has no production importer
   and is not an actual entry point such as `__main__`.
6. Fail when a new JavaScript package manifest or lock appears without an
   approved dependency decision.
7. Emit the package/import/path that failed so removal or approval is
   actionable.

Do not add `deptry`, `pipdeptree`, `pip-audit`, a JavaScript package manager, or
another scanner merely to enforce this repository-local invariant.

Run `uv tree --locked` for Windows, Linux, and macOS target markers and inspect
each transitive dependency. A transitive package is retained only through the
justified direct owner in the baseline table; do not promote transitive
packages to direct requirements.

Commit as one dependency-policy guard.

### Implementation sequencing record

R4 completed on 2026-07-30 in the commit containing this record.
`tests/test_dependencies.py` uses only the standard library to derive runtime
distribution-to-import ownership, enforce the optional/build owner table,
reject orphaned top-level application modules, reject JavaScript package
metadata, and ensure the locked graph covers direct requirements without a
retired media package.

The five focused guards pass. Each was proved red with an isolated temporary
sentinel: an unused runtime requirement, a removed PyInstaller command owner, an
orphan package module, a JavaScript package manifest, and a forbidden locked
package. The complete entry point passed 638 Python tests (5 skipped), 125
browser tests, every JavaScript syntax check, Python byte-compilation, and
wheel/sdist builds.

Python 3.12 locked trees for Windows, Linux, and macOS each resolved from the
same 43-package lock. Every active transitive package belongs to the retained
`keyring`, `pywebview`, or `pyinstaller` responsibility; `hidapi`, Pillow, and
pyserial have no active transitive children. No independent, undeclared,
JavaScript, model-runtime, or retired media dependency remains.

## Slice R5 — Native artifact and clean-environment proof

### Automated verification

Run the complete entry point from `.agents/repo-guidance.md`:

```text
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/app.js
uv build
```

Run once in the existing environment and once in a fresh Python 3.12
`UV_PROJECT_ENVIRONMENT` created with `uv sync --locked` and no extras. The base
suite must not gain desktop/build dependencies.

### Windows native proof

After a separate owner go installs Inno Setup 6 on `netwatch-01`:

1. Create a fresh Python 3.12 environment with
   `uv sync --locked --extra desktop --extra build`.
2. Run `python build.py --skip-sync`.
3. Confirm no compiler, Visual Studio, FFmpeg, GnuPG, MSYS2, MinGW, or GNU Make
   process is invoked.
4. Run the installed executable smoke through the normal installer script.
5. Recursively inspect the PyInstaller tree and installed tree; reject any
   FFmpeg executable, manifest, license/source offer, MP4 fixture, or video
   provider module.
6. Record installer size before and after removal as evidence, not as a fixed
   invariant.

### Cross-platform proof

Push only after local automated verification is green. Require all macOS,
Windows, and Linux CI and Desktop installer jobs to pass. Download each native
artifact, inspect its contents, and run the platform smoke where a qualified
host is available. Absence of a qualified host is recorded explicitly and does
not become an invented pass.

## Slice R6 — Close records and obsolete blockers

After all production slices pass:

1. Mark this plan implemented with commit IDs and exact verification evidence.
2. Update
   `docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md` so B4 is
   superseded and closed by removal, not described as an unperformed FFmpeg
   build.
3. Update the historical public-release plan and current product plan pointers;
   do not resume the rejected candidate.
4. Update `.agents/state.md` so no current blocker or next action mentions
   FFmpeg, MinGW, MSYS2, GnuPG, Visual Studio, staged source archives, or native
   media smoke.
5. Prune obsolete FFmpeg/toolchain facts from `.agents/machines.md`. Retain only
   current machine capabilities that still affect supported builds, including
   the Inno Setup and SmartScreen facts.
6. Update README developer prerequisites: Windows local packaging requires
   Inno Setup, not Visual Studio or an FFmpeg toolchain.
7. Close any tracker item whose entire scope was the retired FFmpeg/B4 path.
8. Commit the closure records with the final implementation slice; do not leave
   landed work and stale paperwork separated.

## Completion criteria

The effort is complete only when:

- fresh AI generation is procedural-only and unchanged in behavior;
- legacy AI-video mutations and recovery cannot execute;
- no current source/build/test/package/workflow surface contains FFmpeg;
- no native artifact contains FFmpeg or its metadata;
- FFmpeg-only toolchains and system packages are gone from CI;
- `am_configurator/local_animation.py` is gone and qualification uses the
  production provider;
- every remaining direct dependency has a live owner and the audit guard passes;
- clean base and desktop/build environments resolve from `uv.lock`;
- the complete automated verification entry point passes;
- a Windows installer is built and smoke-tested locally after the Inno Setup
  gate, and cross-platform Desktop installer CI passes;
- decisions, active plans, current state, machine notes, notices, and README all
  describe the same dependency contract.
