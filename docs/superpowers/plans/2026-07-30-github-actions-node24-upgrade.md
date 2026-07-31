# GitHub Actions Node 24 Compatibility Upgrade Plan

**Status:** Implemented. A1 landed as
`7586bf7daab187a158a5c929cafcb80f9af97d10` on 2026-07-31 after the
prerequisite provenance-ref correction at
`72a1e41889243819f4c27036693f150b15b95859`. Full local verification and the
required `claude-opus-5` implementation review completed with no workflow or
test defect, both record-drift follow-ups closed, and A2 qualified the exact A1
commit across remote workflows, artifacts, provenance, and Windows
installation acceptance.

## Objective

Replace every GitHub Actions dependency that currently targets deprecated
Node 20 with a reviewed Node 24-compatible release while preserving the
repository's existing CI, artifact, cache, and provenance contracts.

This is workflow-maintenance work only. It changes no application source,
Python or JavaScript dependency, application version, installer policy,
release candidate, tag, Release, announcement, hardware state, or live
provider state.

## Authority and current evidence

The completed dependency-removal audit recorded this as separate follow-up
work after successful final-head runs:

- CI run `30587012578`;
- Desktop installer run `30587012588`.

GitHub check annotations on the Desktop run identify these Node 20 targets:

- `actions/checkout@v4`;
- `actions/upload-artifact@v4`;
- `astral-sh/setup-uv@v6`;
- `actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093`
  (`v4.3.0`);
- `actions/attest-build-provenance@e8998f949152b193b063cb0ec769d69d929409be`
  (`v2.4.0`), whose composite uses pinned `predicate` and
  `actions/attest@v2.4.0` children.

GitHub currently forces those actions onto Node 24, so the workflows pass but
depend on a compatibility bridge that GitHub may remove.

The public-release trust model already requires
`actions/download-artifact` and `actions/attest-build-provenance` to use
reviewed immutable commits. Preserve that rule. Preserve the existing major-ref
convention for ordinary official checkout/upload actions. `setup-uv` stopped
publishing moving major tags at v8, so use its reviewed immutable release
commit.

## Reviewed target set

Use exactly these replacements:

| Action | Current ref | Target ref | Reviewed release |
|---|---|---|---|
| `actions/checkout` | `v4` | `v7` | `v7.0.1`, commit `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/upload-artifact` | `v4` | `v7` | `v7.0.1`, commit `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `actions/download-artifact` | pinned `v4.3.0` | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | `v8.0.1` |
| `astral-sh/setup-uv` | `v6` | `c771a70e6277c0a99b617c7a806ffedaca235ff9` | `v9.0.0` |
| `actions/attest-build-provenance` | `e8998f949152b193b063cb0ec769d69d929409be` | `0f67c3f4856b2e3261c31976d6725780e5e4c373` | `v4.1.1` |

At implementation time, re-resolve each release tag through the GitHub API and
confirm it still maps to the reviewed commit above. A mismatch is a roadblock:
do not silently substitute a newer ref.

## Compatibility constraints

- GitHub-hosted runners satisfy the Node 24 actions' minimum runner version
  (`2.327.1`). Do not add or claim self-hosted-runner support.
- `setup-uv@v9` changes `prune-cache` from `true` to `false`. Add
  `prune-cache: true` to both existing setup steps so cache behavior and cost
  remain unchanged.
- `setup-uv@v8+` removed moving major/minor tags. Use the immutable v9.0.0
  commit above, with a `# v9.0.0` comment.
- `download-artifact@v5` changed only single-artifact-ID path behavior. This
  repository uses `pattern` plus `merge-multiple: true`; preserve those inputs.
- `download-artifact@v8` fails on digest mismatch instead of warning. Keep that
  secure default. Never weaken it to make a workflow pass.
- `upload-artifact@v7` retains zipped upload behavior unless
  `archive: false` is supplied. Do not add that input.
- `attest-build-provenance@v4` is a compatibility wrapper over
  `actions/attest@v4`. Keep the wrapper and the existing subject paths and
  job-level permissions; changing provenance API shape is outside this plan.
- Do not alter checkout credential persistence, fetch depth, artifact names,
  retention, job dependencies, trigger conditions, permissions, timeouts, or
  candidate/release semantics.

## Files

- `.github/workflows/ci.yml`
- `.github/workflows/desktop.yml`
- `tests/test_packaging.py`
- `.agents/state.md`
- this plan

## Slice A1: guard and upgrade the workflow dependencies

Land A1 as one finding and one implementation commit.

### A1.1 Add the regression guard first

Extend `tests/test_packaging.py` with one workflow dependency-contract test.
The test must read both workflow files and extract every external `uses:` ref.
It must compare the resulting multiset against this exact contract:

- four `actions/checkout@v7` uses: one in CI and three in Desktop;
- two
  `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9`
  uses;
- two `actions/upload-artifact@v7` uses;
- two
  `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`
  uses;
- four
  `actions/attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373`
  uses.

The test must also assert:

- both `setup-uv` steps contain `prune-cache: true`;
- none of the five retired refs listed under current evidence appears in either
  workflow;
- no new external action can enter either workflow without an explicit test
  update and owner-visible review.

Update the existing exact-ref assertions in `tests/test_packaging.py` for the
new download and provenance commits rather than retaining a second source of
truth.

Before changing either workflow, run:

```powershell
uv run --frozen python -m unittest discover -s tests -p "test_packaging.py" -v
```

The new guard must fail specifically on the old action contract. If it passes,
the test is vacuous and must be fixed before proceeding.

### A1.2 Update CI and Desktop workflows

In both workflow files:

- replace `actions/checkout@v4` with `actions/checkout@v7`;
- replace `astral-sh/setup-uv@v6` with
  `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9`
  (`v9.0.0`);
- add `prune-cache: true` beside each existing `enable-cache: true`.

In `.github/workflows/desktop.yml`:

- replace both upload uses with `actions/upload-artifact@v7`;
- replace both download uses with
  `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`
  (`v8.0.1`);
- replace all four provenance uses with
  `actions/attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373`
  (`v4.1.1`).

Make no other workflow edit.

Run the focused test again; it must pass. Prove the new test guards the
implementation by temporarily reverting only the workflow ref/input changes,
confirming the focused test fails, restoring them, and confirming it passes.

### A1.3 Local verification

Run the repository verification entry point:

```powershell
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

Run `git diff --check`. Commit A1 with:

```text
ci: upgrade workflow actions to Node 24
```

## Slice A2: native remote acceptance and closure

Push A1 under `.agents/push-policy.md`, then verify the exact A1 commit. Do not
use a later documentation-only commit as the implementation proof.

Required remote evidence:

1. CI passes on Linux Python 3.11, default Linux, macOS, and Windows.
2. Desktop installers passes native macOS, Windows, and Linux builds plus
   candidate metadata and provenance.
3. Query every check-run annotation for both workflows. There must be no
   Node 20 deprecation warning and no new action warning.
4. Download all private Desktop artifacts into a controlled temporary
   directory.
5. Confirm the wrapper contains exactly the three platform installers,
   `release-manifest.json`, and `SHA256SUMS.txt`.
6. Recompute all bytes/hashes and match the source-bound manifest.
7. Run `gh attestation verify --repo roethlar/AMKB-GUI` on all five subjects.
8. On this qualified Windows host, silently install the exact downloaded
   Windows artifact, run `--smoke-test`, confirm required notices, and uninstall.
9. Remove the temporary audit/install directories after validating that each
   resolved path remains under the system temporary root.

Any artifact layout, digest, provenance, permission, cache, or action-runtime
failure blocks closure. Do not disable digest enforcement, provenance, cache,
or tests and do not downgrade only the failing job. Diagnose the action
compatibility problem; if the fix exceeds this plan, stop for an owner ruling.

After all evidence passes:

- mark this plan implemented with run IDs, immutable refs, manifest/provenance
  results, and the A1 commit;
- update `.agents/state.md` to remove the Node 20 finding and restore Product
  Slice P6 as the sole next implementation slice;
- commit those records as:

```text
docs: close GitHub Actions runtime upgrade
```

The closure commit is documentation-only and does not require a second native
artifact qualification.

## A2 acceptance evidence (completed 2026-07-31)

- Exact implementation commit:
  `7586bf7daab187a158a5c929cafcb80f9af97d10`.
- CI run
  [`30603622836`](https://github.com/roethlar/AMKB-GUI/actions/runs/30603622836)
  passed Linux Python 3.11, default Linux, macOS, and Windows.
- Desktop installers run
  [`30603622828`](https://github.com/roethlar/AMKB-GUI/actions/runs/30603622828)
  passed native Linux, Windows, and macOS builds, candidate metadata, and
  release provenance.
- Both runs were push-triggered against the exact implementation commit. All
  nine check-runs were queried directly and contained no Node 20,
  deprecated-action, or other action-runtime warning. The three CI annotations
  were duplicate cache-key reservation warnings; the corresponding Desktop
  jobs successfully saved the same Linux, Windows, and macOS Python 3.12 cache
  keys, and the CI-only Linux Python 3.11 cache also saved successfully.
- The exercised dependency contract was exactly `actions/checkout@v7`,
  `actions/upload-artifact@v7`,
  `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`,
  `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9`,
  and
  `actions/attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373`;
  no reviewed ref was substituted.
- The downloaded wrapper contained exactly the three installers,
  `release-manifest.json`, and `SHA256SUMS.txt`. The manifest bound them to
  source commit `7586bf7daab187a158a5c929cafcb80f9af97d10` and Desktop
  run `30603622828`. Recomputed SHA-256 digests matched both metadata files:
  Linux
  `6142ec0a14b9cb47ad56c6bff6ff651f64760c2438bacde5fa9e74adb578c7f4`,
  Windows
  `f8c1a5925c9783f849038284d9784a7cca86497a4d15a4b4744e8aa636490ffe`,
  macOS
  `d20a13acac87af6c7fbcc78f0f4f3421431f22406d86903506a7d36084daff54`,
  manifest
  `4edb115df665f87533a411a59e635de83ea9f3be591c998195ef4fa15ca7595b`,
  and checksums
  `99a750edad2edfa7a45bd3ad849de47c2ce75dcbbdb469e791df80685e9a4f6d`.
- Structured `gh attestation verify --repo roethlar/AMKB-GUI` passed for all
  five subjects. Each result carried SLSA provenance v1, the exact source and
  workflow SHA, Desktop invocation
  `https://github.com/roethlar/AMKB-GUI/actions/runs/30603622828/attempts/1`,
  and matching subject digests.
- On the qualified Windows host, the exact downloaded installer registered
  product version `0.1.64` in a custom directory beneath the controlled audit
  root. Its bundled `LICENSE` and `THIRD_PARTY_NOTICES` matched the repository
  files after normalizing Windows and Unix line endings.
  `AM Configurator.exe --smoke-test` exited zero with
  `Desktop smoke test passed (Windows).` The silent uninstaller exited zero,
  removed the custom directory and uninstall-registry entry, and left the
  pre-existing default installation path untouched.
- The controlled audit directory was validated as an immediate child of the
  system temporary directory and removed. No tag, Release, announcement,
  application version, dependency, hardware, or provider state changed.

## Completion criteria

- No workflow action targets Node 20.
- Every external workflow action has a tested, reviewed owner/ref.
- Existing cache pruning, artifact structure, digest enforcement, provenance,
  permissions, and triggers are preserved.
- The new dependency guard is proven red then green.
- Full local verification passes.
- Exact-implementation-commit CI and Desktop workflows pass without action
  deprecation warnings.
- Downloaded artifacts match manifest and provenance.
- No application, dependency lock, version, release, tag, announcement,
  hardware, or provider state changes.
