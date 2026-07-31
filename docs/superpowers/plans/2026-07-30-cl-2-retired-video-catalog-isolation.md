# cl-2 Retired-Video Catalog Isolation Plan

**Status:** Implementation slice C2 completed and locally verified on
2026-07-30. The required per-slice `claude-opus-5` review remains pending.

## Objective

Close review finding `cl-2` without expanding into `cl-3` or changing supported
procedural and saved-item behavior. A retired video job must be classified as
`unsupported_video_job` in both live and removed Library scans. Library
`remove`, `restore`, and `delete_forever` mutations must reject it before any
rename or deletion, including after the operation acquires its ownership lock.
The historical directory and every byte beneath it must remain unchanged.

## Authority and settled interpretation

- `.agents/decisions.md` makes historical video jobs non-resumable and prohibits
  automatic deletion while removing the video execution path.
- The approved FFmpeg-removal plan is more specific for this case:
  - an old video manifest encountered by a scan fails closed as unsupported
    without modifying or deleting its directory or assets;
  - legacy AI-video mutations and recovery cannot execute.
- `.agents/state.md` records the implemented contract: legacy video manifests
  are reported unsupported and left untouched.
- `.agents/review/findings/cl-2.md` records the reproduced removed-namespace
  classification and mutation failures and is the only finding in scope.

`delete_forever` is an explicit Library mutation and therefore falls under the
approved “legacy AI-video mutations cannot execute” rule. The application must
not interpret explicit deletion as permission to erase historical video data.
Users retain normal filesystem ownership outside the application; this plan
adds no relocation, quarantine, migration, or cleanup behavior.

No owner decision remains open inside this plan.

## Diagnosis

`GeneratedAssetLibrary._scan_internal` recognizes raw schema-v1 or
`pipeline == "legacy_video"` manifests before normal validation and reports
`unsupported_video_job`.

`LibraryCatalog._scan_removed_namespace` instead calls
`_read_owned_manifest`. `_validate_manifest` intentionally accepts historical
schema-v1 manifests and normalizes them to schema v2 with
`pipeline == "legacy_video"`, so the removed scanner treats them as ordinary
removed generation jobs and publishes summaries.

Mutation lookup follows the same normal validated-manifest path:

- `LibraryCatalog._move` powers both `remove` and `restore`, ending at
  `os.rename`;
- `LibraryCatalog.delete_forever` ends at `shutil.rmtree`;
- each mutation reads once before locking and once again under `_job_lock`, but
  neither read rejects a retired video manifest.

The root correction is one shared retired-manifest classifier, one
retired-aware job-manifest reader that classifies raw historical markers before
strict current-schema validation, uniform live/removed scan projections, and
retired-aware reads at both the initial and lock-held mutation boundaries.

## Scope

### Production

- `am_configurator/library.py`

### Guard

- `tests/test_library.py`

### Records

- `.agents/review/findings/cl-2.md`
- `.agents/review/index.md`
- `.agents/state.md`
- this plan

No server, web, procedural-generation, dependency, packaging, workflow,
installer, release, provider, credential, or hardware source belongs in this
fix.

`LibraryCatalog.get` and `resolve_asset` are not mutation paths and are not
changed by this finding. Removed scans will no longer advertise retired entries;
the retired video display/MIME paths were removed by the approved FFmpeg slice.

## Implementation slice C2 — unify classification and block mutations

One finding maps to one implementation commit. Build both behavior guards
before changing production code, observe their independent failures, then
implement the shared classifier and mutation boundary. Do not commit the
intermediate red working tree.

### C2.1 Add test-only retired-job fixture support

In `LibraryRemovalTests`, add a private helper that:

1. creates a terminal procedural job through `_job()`;
2. optionally moves it to the same root's trash while it is still procedural;
3. rewrites that live or removed manifest into either:
   - a validator-compatible retired manifest by setting `pipeline` to
     `legacy_video`, adding the valid historical `loop_mode`, and replacing
     `models` with historical video metadata; or
   - a minimal raw schema-v1 manifest containing a canonical owning `job_id`
     but deliberately lacking current required fields;
4. creates `video/historical.mp4` with fixed sentinel bytes; and
5. returns the catalog ID, live/removed directory, manifest path, sentinel path,
   and a recursive relative-file-to-bytes snapshot.

The helper simulates data left by an older application. Production APIs must
never be used to create a fresh retired job.

### C2.2 Guard removed-namespace classification

Add
`test_removed_retired_video_job_is_reported_unsupported_and_untouched`.

Create two retired jobs in trash: one validator-compatible `legacy_video`
manifest and one minimal raw schema-v1 manifest. Assert:

- `LibraryCatalog.scan()` and `page(..., removed=True)` contain no item for
  either catalog ID;
- each response contains exactly two pathless errors, one per retired job:
  - `catalog_id`: the canonical `job:<uuid>`;
  - `namespace`: `job`;
  - `code`: `unsupported_video_job`;
  - `message`: the existing retired-video unsupported/unchanged message;
- no configured root or filesystem path appears in either response;
- both removed directories stay in place; and
- both recursive file inventories and every file's bytes remain identical.

Run this test before production changes. It must fail independently for both
classification paths: the current removed scanner returns the
validator-compatible retired job as a normal item and reports the minimal
schema-v1 manifest as corrupt rather than unsupported.

### C2.3 Guard every catalog mutation

Add
`test_retired_video_catalog_mutations_fail_without_touching_files`.

Use a fresh retired fixture for each subtest:

- live retired job + `catalog.remove`;
- removed retired job + `catalog.restore`;
- removed retired job + `catalog.delete_forever`.

Repeat all three mutation cases with a procedural manifest at the initial
lookup, then rewrite it to a retired manifest immediately before `_job_lock`
acquires the ownership lock. These transition cases prove the lock-held
recheck is load-bearing rather than merely present.

For every operation, assert:

- `LibraryItemStateError` is raised with the fixed retired-video
  unsupported/unchanged message;
- the source directory still exists in its original live or removed namespace;
- the opposite namespace does not contain that job ID;
- the recursive relative-file inventory is unchanged; and
- every captured file remains byte-identical.

Run this test before production changes. All six subtests must fail because
the current code performs the rename or recursive deletion both for initially
retired manifests and for manifests retired after lookup. Destruction in this
red proof is confined to each test's temporary root.

### C2.4 Add one canonical retired-aware job-manifest reader

In `am_configurator/library.py`:

1. Promote the existing unsupported message to one module-private constant.
2. Add a private `_UnsupportedVideoJobError` subclass of
   `LibraryItemStateError`. It carries only the fixed public message and lets
   scans project the canonical error while catalog mutations fail closed
   through the existing HTTP 409 mapping.
3. Add `_is_retired_video_manifest(value: object) -> bool` that returns true
   only for dictionary manifests with raw `schema_version == 1` or
   `pipeline == "legacy_video"`.
4. Extract the job-manifest read/validate logic currently owned by
   `_read_manifest` into one private helper accepting
   `reject_retired_video: bool = False`.
5. The helper must:
   - read the raw JSON value exactly once;
   - when rejection is enabled and the raw predicate is true, canonicalize and
     ownership-check its `job_id` against the expected directory UUID;
   - raise `_UnsupportedVideoJobError` only after ownership succeeds;
   - otherwise preserve the existing `_validate_manifest` and recursion-error
     behavior.
6. Keep `_read_manifest` as the normal non-rejecting wrapper so unrelated
   generated-job operations retain existing behavior.
7. Make the active generated-job scan call the helper with rejection enabled,
   catch `_UnsupportedVideoJobError`, and project the existing
   `unsupported_video_job` error with the shared message. Preserve its
   `InvalidIdentifierError`/`ManifestError` corrupt isolation, `continue`, and
   pathless response shape.

Do not change `_validate_manifest`, schema conversion, exception inheritance,
or supported procedural validation. The retired check must precede strict
validation so a genuine old schema-v1 manifest is unsupported rather than
misclassified as corrupt merely because current required fields differ.

### C2.5 Classify removed retired jobs as unsupported

Extend `LibraryCatalog._read_owned_manifest` with a
`reject_retired_video: bool = False` keyword. For the job namespace, delegate
to the shared job-manifest helper; saved-item behavior remains unchanged.

In `LibraryCatalog._scan_removed_namespace`:

- call `_read_owned_manifest(..., reject_retired_video=True)`;
- catch `_UnsupportedVideoJobError` before the corrupt-manifest handlers;
- append the canonical removed-catalog error from C2.2 and `continue`;
- catch both `ManifestError` and `InvalidIdentifierError` through the existing
  corrupt-manifest projection;
- do not append a retired manifest to the removed item list; and
- do not modify the directory, manifest, or assets.

The raw retired check must occur before `_validate_manifest`. This is what makes
both validator-compatible `legacy_video` manifests and genuinely old,
now-incomplete schema-v1 manifests uniformly unsupported.

### C2.6 Reject move and deletion before filesystem mutation

Add a `reject_retired_video: bool = False` keyword to `_find_locations` and
`_single_location`, forwarding it to `_read_owned_manifest`.

In `LibraryCatalog._move`, pass `reject_retired_video=True` to both the initial
and lock-held `_single_location` calls. A retired manifest therefore raises
`_UnsupportedVideoJobError` before destination creation or `os.rename`, while
the second read closes the manifest-change window between lookup and mutation.

This blocks both live `remove` and removed `restore`, and the lock-held check
closes the manifest-change window between lookup and mutation.

In `LibraryCatalog.delete_forever`:

1. pass `reject_retired_video=True` to the initial removed `_single_location`;
2. pass the same flag to the lock-held `_single_location`; and
3. preserve both reads and all identity/link checks before `shutil.rmtree`.

Do not weaken active-operation, ambiguous-ownership, duplicate-location,
link-safety, fsync, or saved-item mutation behavior.

## Guard proof

Use the repository root for every command.

Focused commands:

```powershell
uv run --frozen python -m unittest tests.test_library.LibraryRemovalTests.test_removed_retired_video_job_is_reported_unsupported_and_untouched -v
uv run --frozen python -m unittest tests.test_library.LibraryRemovalTests.test_retired_video_catalog_mutations_fail_without_touching_files -v
```

Required proof:

1. Add both tests before the production edit.
2. Run each command and record its independent expected failure.
3. Implement C2.4-C2.6.
4. Run each command and require success.
5. Before committing, temporarily restore only `am_configurator/library.py` to
   its pre-fix content while leaving both tests present.
6. Run both commands:
   - the removed-scan test must fail because the job is catalogued;
   - the mutation test must fail for remove, restore, and permanent deletion,
     including every after-lookup/lock-transition case.
7. Restore the final `library.py`.
8. Run both commands and require success.
9. Record all red/green results in `.agents/review/findings/cl-2.md`.

Do not use history rewrite for this proof. Revert and restore the working-tree
production file with the normal edit mechanism.

## Verification

After both focused guards are green, run:

```powershell
uv run --frozen python -m unittest tests.test_library -v
```

Then run the complete repository verification entry point:

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

A failure is a roadblock. Do not mask or retry the known intermittent
cancellation test; report its actual output if it appears.

Native installer verification is not required because this fix changes no
dependency, packaging, native entry point, or platform integration.

## Commit and per-slice codereview

Before the implementation commit:

- update `cl-2` with the implemented approach, exact changed files, and both
  red/green guard proofs;
- keep `cl-3` untouched;
- update `.agents/state.md` to point at the active `cl-2` verification state.

Commit production, tests, and finding-specific records as one `cl-2`
implementation slice. Do not amend, squash, reorder, or combine it with another
finding.

The owner requires a per-slice Claude review using the literal model
`claude-opus-5`. Pin the implementation commit as head and its parent as base.
`cl-2` is MEDIUM, so absent a sensitive-path match it routes standard at high
effort; apply any mechanical escalation trigger exactly as the codereview
playbook requires. The reviewer must independently restore the base
`library.py` in a disposable worktree, confirm both focused guards fail, restore
the head file, confirm both pass, and return the schema-enforced per-finding
verdict.

Only an accepted reviewer verdict closes `cl-2`. Record the exact transcript
model, effort, tier, pins, guard result, verdict, UTC timestamp, comments, and
any environment notes in the finding and index before proceeding to `cl-3`.

## Completion criteria

`cl-2` is implementation-complete only when:

- live and removed scans use one retired-manifest classifier;
- removed retired jobs are excluded from catalog items and reported through the
  canonical pathless `unsupported_video_job` error;
- live `remove`, removed `restore`, and removed `delete_forever` all fail before
  rename or deletion;
- each mutation rechecks the lock-held manifest;
- historical directory location, file inventory, and bytes remain unchanged;
- procedural jobs and saved items retain existing scan and mutation behavior;
- both guards are proven red with production reverted and green when restored;
- focused and complete verification pass;
- the implementation lands as one finding-specific commit; and
- the required `claude-opus-5` per-slice review accepts the fix.
