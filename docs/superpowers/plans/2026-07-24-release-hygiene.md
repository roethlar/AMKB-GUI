# Release Hygiene

**Status:** Complete on 2026-07-24. Approved by the owner the same day: slices
R1-R4 when the plan was drafted, and R0 separately after it was discovered while
de-risking R4, ahead of the others because the branch could not pass CI until it
landed.

All five slices are committed one item per commit: R0 `4105552`, R1 `c4403e3`,
R2 `a72e31f`, R3 `42b4b92`, R4 `2d50393`. Each guard was proven red before its
fix. Closure evidence is in the per-slice sections below and summarized in
`.agents/state.md`.

Code signing and notarization are explicitly out of scope: both require paid
developer accounts (Apple Developer Program, Authenticode certificate) that are
not available, and the README already discloses the unsigned state. Governance
content is toolkit-owned and is not edited by this plan; slice R2 only stops it
from being published.

Implementation is authorized under one finding per commit.

## Objective

Close four defects that affect what the project publishes, so that a tagged
release distributes correct license notices and no internal or machine-local
material, and so that the documented verification entry point matches what CI
actually enforces.

None of these defects affect application runtime behavior. No device, credential,
provider, or generation path changes.

## Scope

- R0: two tests import the real `webview` module, so the branch fails CI.
- R1: the MIT attribution notice is absent from the macOS and Linux native
  artifacts.
- R2: the Python sdist publishes the entire agent-governance surface, internal
  planning history, and machine-local notes.
- R3: the documented verification entry point lists fewer JavaScript syntax
  checks than CI enforces.
- R4: `requires-python = ">=3.11"` is declared and implemented but never tested.

Out of scope: code signing, notarization, SmartScreen reputation, an in-app
About/licenses surface, and any change to `.agents/**`, `AGENTS.md`, `CLAUDE.md`,
or `.claude/**`.

## Authoritative Inputs

- `AGENTS.md` and `.agents/repo-guidance.md` govern process, verification, and
  Git rules.
- `packaging/am_configurator.spec` owns what enters native bundles.
- `pyproject.toml` owns what enters the sdist and wheel.
- `.github/workflows/ci.yml` is the authoritative verification command set; where
  a document disagrees with it, the document is the lower-authority source.
- Current code and built artifacts are evidence for behavior.

---

## R0 — Stop two tests importing the real webview module

Implement this slice first. Until it lands the branch cannot pass CI, so no
other slice can be validated by the pull request that merges this work.

### Defect

`tests/test_desktop.py::DesktopBridgeTests::test_folder_chooser_returns_none_when_cancelled`
and `::test_folder_chooser_returns_only_a_canonical_absolute_directory` call
`bridge.choose_library_folder()` against the real implementation. That reaches
`am_configurator/desktop.py:102`, which executes `import webview`.

`pywebview` is supplied only by the `desktop` optional dependency group
(`pyproject.toml:18-22`). `.github/workflows/ci.yml:40` installs the environment
with `uv sync --locked` and no extras, so `webview` is absent and both tests
raise `ModuleNotFoundError`.

Every other webview-dependent test in the same file already injects a fake
module — see `mock.patch.dict(sys.modules, {"webview": ...})` at lines 154, 375,
419, 469, 498, and 572. These two are an isolated oversight, not a systemic gap.

The defect has been latent since commit `2797312` because `ci.yml` triggers only
on `pull_request` and pushes to `main`, and this branch has never opened a pull
request. It does not reproduce in a normal local run because a developer
environment created with `--extra desktop` has `pywebview` installed.

### Evidence to reproduce before changing anything

Recreate CI's environment exactly, redirecting the environment so the project
`.venv` is not replaced:

```sh
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --locked -p 3.12
uv run --frozen -p 3.12 python -m unittest discover -s tests
```

Expect `Ran 376 tests ... FAILED (errors=2, skipped=1)`, both errors being
`ModuleNotFoundError: No module named 'webview'` raised from
`desktop.py:102` via `_folder_dialog_type`.

### Change

In `tests/test_desktop.py`, make both tests inject a fake `webview` module the
way their siblings in the same class already do, so the real optional dependency
is never imported. Preserve each test's existing assertions exactly: the
cancelled case must still assert `None`, and the canonical case must still assert
the resolved absolute directory string.

Do not add `--extra desktop` to `ci.yml`. On Linux that extra resolves
`pywebview[qt]`, which pulls a Qt stack and its system libraries into the plain
test job; `desktop.yml` already carries that cost deliberately and `ci.yml`
should stay light.

Do not weaken the tests to `skipTest` when `webview` is missing — that would
silently drop the coverage in exactly the environment CI runs.

Do not change `am_configurator/desktop.py`. The lazy `import webview` inside
`_folder_dialog_type` is correct production behavior for an optional dependency.

### Regression guard

The two repaired tests are themselves the guard. Prove they guard the defect by
running them in an environment without the `desktop` extra:

```sh
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --locked -p 3.12
uv run --frozen -p 3.12 python -m unittest tests.test_desktop -v
```

Confirm this fails before the change and passes after it. A run that passes only
in an environment carrying `--extra desktop` has not proven anything.

### Verification

1. The CI-equivalent run above reaches `OK (skipped=1)` with 376 tests.
2. The ordinary developer run also passes:
   `uv run --frozen python -m unittest discover -s tests -v`

Record both results in the closure note.

---

## R1 — Ship the MIT attribution notice in native artifacts

### Defect

`am_configurator/protocol.py`, `reader.py`, and `writer.py` implement a protocol
derived from the MIT-licensed `GeneralD/cyberboard-cli`. The MIT license requires
its copyright and permission notice to accompany all copies or substantial
portions of the software. `LICENSE` and `THIRD_PARTY_NOTICES` are not in the
PyInstaller `datas` allowlist, so neither reaches the macOS `.app`, the Linux
AppImage, or the installed Windows tree.

`packaging/windows/AMConfigurator.iss:35` sets `LicenseFile=..\..\LICENSE`, which
displays the notice during installation but does not install it; its `[Files]`
glob copies only the PyInstaller output directory.

FFmpeg's LGPL obligation is already satisfied and must not be disturbed:
`packaging/ffmpeg/LGPL-2.1.txt`, `manifest.json`, `README.md` (containing the
written source offer), and `ffmpeg-devel.asc` are already in `datas`.

### Evidence to reproduce before changing anything

Against an existing built bundle, or one produced by `python build.py --skip-sync`:

```sh
find "dist/AM Configurator.app" -maxdepth 3 -name LICENSE -o -maxdepth 3 -name THIRD_PARTY_NOTICES
```

Expect no result under `Contents/Resources` or `Contents/Frameworks`. Any hit
under `Contents/Resources/*.dist-info/licenses/` belongs to a third-party wheel
and does not satisfy this obligation.

### Change

In `packaging/am_configurator.spec`, add two entries to the `datas` list
(currently beginning at line 54), alongside the existing FFmpeg metadata entries:

```python
    (str(project / "LICENSE"), "."),
    (str(project / "THIRD_PARTY_NOTICES"), "."),
```

Destination `"."` places both at `Contents/Resources/` in the macOS bundle and at
`_internal/` in the Windows and Linux one-dir trees.

Do not change `binaries`, `hidden_imports`, the `upx=False` settings, or any
FFmpeg entry.

### Regression guard

Add to `tests/test_packaging.py`, following the existing spec-assertion style in
`test_native_bundle_contains_verified_ffmpeg_and_real_media_smoke`:

```python
def test_native_bundle_ships_project_license_and_attribution(self) -> None:
    spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")

    # The protocol layer is derived from MIT-licensed cyberboard-cli; the notice
    # must travel with every native artifact, not only the Windows installer's
    # click-through LicenseFile.
    self.assertIn('(str(project / "LICENSE"), ".")', spec)
    self.assertIn('(str(project / "THIRD_PARTY_NOTICES"), ".")', spec)
    self.assertTrue((ROOT / "LICENSE").is_file())
    self.assertTrue((ROOT / "THIRD_PARTY_NOTICES").is_file())
    self.assertIn("cyberboard-cli", (ROOT / "THIRD_PARTY_NOTICES").read_text("utf-8"))
```

Prove the guard: remove the two `datas` entries, confirm the new test fails,
restore them, confirm the suite passes.

### Verification

1. `uv run --frozen python -m unittest discover -s tests -v`
2. `python build.py --skip-sync`
3. Confirm both files are present in the rebuilt bundle:
   `ls "dist/AM Configurator.app/Contents/Resources/LICENSE" "dist/AM Configurator.app/Contents/Resources/THIRD_PARTY_NOTICES"`
4. Run the frozen executable with `--smoke-test` and confirm it still passes.

Record the built version number and the smoke result in the closure note.

---

## R2 — Restrict the sdist to an explicit allowlist

### Defect

`pyproject.toml` declares no sdist target configuration, so hatchling defaults to
including every version-controlled file. `uv build` therefore publishes:

- `.agents/**` — including `state.md`, `decisions.md`, `repo-guidance.md`,
  `review/**`, and `machines.md`, which records the owner's checkout path, host
  OS version, local toolchain identity, and installed-software notes;
- `.claude/**` — including `settings.local.json`;
- `AGENTS.md` and `CLAUDE.md`;
- `docs/superpowers/plans/**`, `docs/design/**`, and `docs/verification/**`.

The wheel is already correct (package plus `dist-info`, with `LICENSE` under
`dist-info/licenses/`). Native bundles are already correct because the spec's
`datas` is an explicit allowlist. Only the sdist is affected.

`.claude/hooks/protect-governance.py` cannot be used to derive the exclusion set:
its `PROTECTED` frozenset lists only toolkit-installed files and deliberately
omits the repo-owned `.agents/` files that carry the machine-local and internal
content.

### Design decision (settled; do not reopen)

Use an allowlist, not a denylist. Governance is refreshed from an external
toolkit — four such refresh commits exist on this branch — so a denylist must be
updated whenever the toolkit adds a path, fails open when it is not, and fails
silently. The allowlist's maintenance trigger is a new shippable top-level entry,
which did not occur once across this branch, and it fails closed and loudly.

### Change

Append to `pyproject.toml`, after the existing `[tool.hatch.build.targets.wheel]`
table:

```toml
[tool.hatch.build.targets.sdist]
# Allowlist, not a denylist: governance is refreshed from an external toolkit,
# so anything not named here must stay out of published artifacts by default.
include = [
  "am_configurator/",
  "assets/",
  "build_tools/",
  "docs/images/",
  "packaging/",
  "tests/",
  "build.py",
  "LICENSE",
  "README.md",
  "THIRD_PARTY_NOTICES",
  "pyproject.toml",
  "uv.lock",
]
```

`docs/images/` is retained because `README.md` references those files. Do not add
`docs/design/`, `docs/superpowers/`, or `docs/verification/`.

Do not modify `[tool.hatch.build.targets.wheel]`.

### Regression guards

Add both tests to `tests/test_packaging.py`. The first proves the exclusion; the
second is what removes the need for anyone to remember the allowlist exists.

```python
_SDIST_FORBIDDEN_PREFIXES = (
    ".agents/",
    ".claude/",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/design/",
    "docs/superpowers/",
    "docs/verification/",
)

def test_sdist_allowlist_excludes_governance_and_internal_material(self) -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    include = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    for forbidden in _SDIST_FORBIDDEN_PREFIXES:
        with self.subTest(forbidden=forbidden):
            self.assertNotIn(forbidden, include)
    for required in (
        "am_configurator/",
        "build_tools/",
        "packaging/",
        "tests/",
        "LICENSE",
        "THIRD_PARTY_NOTICES",
    ):
        with self.subTest(required=required):
            self.assertIn(required, include)

def test_every_tracked_top_level_entry_is_allowlisted_or_deliberately_excluded(self) -> None:
    """A new top-level entry must be classified before it can silently ship."""
    listing = subprocess.run(
        ("git", "ls-tree", "--name-only", "HEAD"),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        self.skipTest("git is unavailable")

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    include = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    allowlisted = {entry.rstrip("/") for entry in include}
    # Deliberately excluded: governance, internal history, and repo-only config.
    excluded = {
        ".agents",
        ".claude",
        ".gitattributes",
        ".github",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "docs",
    }

    for entry in listing.stdout.split():
        with self.subTest(entry=entry):
            self.assertIn(entry, allowlisted | excluded)
```

`subprocess` must be imported in the test module. `docs` appears in `excluded`
because only its `images/` subtree is allowlisted.

Prove both guards: remove the `[tool.hatch.build.targets.sdist]` table, confirm
both new tests fail, restore it, confirm the suite passes.

### Verification

1. `uv run --frozen python -m unittest discover -s tests -v`
2. `uv build`
3. Confirm the sdist is clean and complete:

```sh
tar -tzf dist/am_configurator-0.1.0.tar.gz | grep -E '(^|/)(\.agents|\.claude|AGENTS\.md|CLAUDE\.md)|docs/(design|superpowers|verification)/'
```

Expect no output. Then confirm the sdist still carries the package, tests,
packaging, `build_tools`, `uv.lock`, `LICENSE`, and `THIRD_PARTY_NOTICES`.

4. Confirm the wheel is unchanged: `unzip -Z1 dist/am_configurator-0.1.0-py3-none-any.whl`
   still lists only `am_configurator/**` and `am_configurator-0.1.0.dist-info/**`.

Record the exact grep result in the closure note.

---

## R3 — Align the documented verification entry point with CI

### Defect

`.github/workflows/ci.yml:47-54` runs four `node --check` steps
(`lighting_state.js`, `lighting_review.js`, `lighting_targets.js`, `app.js`), and
`tests/test_packaging.py::test_ci_runs_each_node_gate_as_a_failure_sensitive_step`
already asserts all four. Two documents list only two of them:

- `.agents/repo-guidance.md`, section `Verification`;
- `README.md`, the `Development verification` disclosure block.

An agent or contributor following either document runs a strictly weaker gate
than CI enforces. CI is the higher-authority source, so both documents are
corrected to match it.

### Change

In both files, insert the two missing commands so each command block reads:

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

Preserve the surrounding prose in both files, including the native-distribution
paragraph that follows the block in `.agents/repo-guidance.md`.

`.agents/repo-guidance.md` is repo-owned, not toolkit-installed, and is the
correct place for this fix. Do not edit `AGENTS.md`.

### Verification

Docs-only; the repository verification entry point is not required to change
behavior here. Still run it once to confirm nothing regressed, and confirm by
inspection that the two documents and `ci.yml` now name the identical command
set.

---

## R4 — Test the declared Python floor

### Defect

`pyproject.toml:10` declares `requires-python = ">=3.11"`, `README.md` states
"Python 3.11 or newer", and `am_configurator/library.py` carries an explicit
CPython 3.11.10 private-directory version gate — so 3.11 support is intended and
implemented. `.github/workflows/ci.yml:37` pins `python-version: "3.12"` on every
matrix entry, so no job ever exercises the declared floor.

### Known compatibility state

The floor has been probed on the pre-R0 tree and is sound:

- `python3.11 -m compileall -q am_configurator build_tools packaging build.py`
  exits 0.
- A full suite run on CPython 3.11.15 executed all 376 tests with 1 skip and
  exactly 2 errors — both the R0 `webview` defect, which is interpreter
  independent and reproduces identically on 3.12.

No 3.11-specific incompatibility is known. This slice is therefore expected to be
a workflow edit, not a porting exercise. Run the confirmation below anyway, on a
tree that already carries R0.

### Change

Confirm the suite passes on 3.11. Redirect the environment so the project
`.venv` is not replaced with a 3.11 one — plain `uv run -p 3.11` rebuilds
`.venv` in place, which is a destructive side effect on the developer's
environment:

```sh
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --locked -p 3.11
uv run --frozen -p 3.11 python -m unittest discover -s tests -v
```

If this reveals a real 3.11 incompatibility, stop and surface it rather than
adjusting the floor or skipping tests to make the run green. Lowering or raising
`requires-python` is an owner decision, not part of this slice.

If it passes, parameterize the CI matrix in `.github/workflows/ci.yml`: add
`python: "3.12"` to each existing matrix entry, add a fourth entry

```yaml
          - name: Linux · Python 3.11
            os: ubuntu-latest
            python: "3.11"
```

and change the setup step to `python-version: ${{ matrix.python }}`.

### Regression guard

Add to `tests/test_packaging.py`, beside the existing `ci.yml` assertions:

```python
def test_ci_exercises_the_declared_python_floor(self) -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    self.assertEqual(">=3.11", metadata["project"]["requires-python"])
    self.assertIn('python: "3.11"', workflow)
    self.assertIn("python-version: ${{ matrix.python }}", workflow)
```

Prove the guard: revert the workflow edit, confirm the test fails, restore it,
confirm the suite passes.

### Verification

1. The redirected 3.11 run above reaches `OK (skipped=1)` with 376 tests.
2. `uv run --frozen python -m unittest discover -s tests -v`
3. Confirm the workflow remains valid YAML and every matrix entry carries a
   `python` key.

---

## Closure Evidence

Recorded 2026-07-24 at `2d50393`.

- R0 `4105552`. Both folder-chooser tests failed in a CI-equivalent environment
  (Python 3.12, `uv sync --locked`, `webview` absent) and passed after supplying
  a stand-in module. No production change.
- R1 `c4403e3`. Guard red with the two `datas` entries removed. Native macOS
  build `0.1.45` passed DMG verification and frozen smoke; the rebuilt bundle
  carries `Contents/Resources/LICENSE` (1065 bytes) and
  `Contents/Resources/THIRD_PARTY_NOTICES` (539 bytes), and the seven FFmpeg
  LGPL files remain in `Contents/Resources/ffmpeg/`.
- R2 `a72e31f`. Both guards red with the sdist table removed. A real `uv build`
  returns nothing for the governance grep; only `docs/images/` ships from
  `docs/`; `packaging/ffmpeg/` material still arrives through its parent; the
  wheel is unchanged. An unanchored `README.md` pattern was observed matching
  `docs/verification/*/README.md` during this slice, which is why every pattern
  is root-anchored and a guard enforces it.
- R3 `42b4b92`. `ci.yml`, `.agents/repo-guidance.md`, and `README.md` now name
  an identical four-target `node --check` set.
- R4 `2d50393`. Guard red against the unparameterized workflow. The suite passes
  on CPython 3.11.15 with no extras.

Final gate at `2d50393`: 380 Python tests with one skip in the developer
environment, the CI-equivalent 3.12 environment, and the 3.11 floor environment;
43 browser tests; four `node --check` targets; `compileall`; `uv build`.

## Completion

The plan is complete when all five slices are committed, the full verification
entry point from `.agents/repo-guidance.md` passes in an environment built the
way CI builds it (`uv sync --locked`, no extras), and `.agents/state.md` `## Now`
records: the CI-equivalent suite result, the notice files present in a rebuilt
native bundle, the empty governance grep against a rebuilt sdist, the aligned
command set, and the 3.11 suite result.

Hardware acceptance across CyberBoard, Relic 80, and AFA remains a separate
external release prerequisite and is not affected by this plan.
