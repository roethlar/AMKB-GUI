# Deterministic Effect Picker and Engine

**Status:** APPROVED by owner 2026-08-15 ("go"); slices land as work
proceeds, each behind the full verification entry point. Premises below were verified against the working tree at
`13d1c4b` (v2/openkeeb) on 2026-08-15; line references are locators, not
boundaries — re-derive at edit time.

## Why

The 2026-08-14 decision ("AI generation leaves the core; the core consumes
pixel art") names three creation paths: import, manual painting, and **a
deterministic procedural effect engine with a user-facing picker**. The
first two exist. This plan is the third — it makes the engine reachable by
people instead of the deleted LLM path, and implements the seven kinds
ruled in on 2026-08-13.

## Verified premises

- `am_configurator/procedural.py` is fully dormant: zero importers in
  `am_configurator/` (allowlisted as intentionally dormant in
  `tests/test_dependencies.py`). Its engine surface is complete and tested
  (`tests/test_procedural.py`): `recipe_schema()`, `validate_recipe()`,
  `render_recipe()`, `assess_quality()`/`validate_quality()`,
  `write_gif()`/`write_preview_gif()`, `map_frames_to_led_tracks()`,
  `write_animation_artifacts()` — the last one is the full
  render→quality→GIF→LED-track pipeline in one call.
- `_KINDS` today: comet, wave, pulse, sparkle, orbit, sweep, noise. Ruled
  additions (effect-techniques plan, Ruling 1): breathe, chase, ripple,
  matrix_rain, heartbeat, fire, twinkle — specified there, unimplemented.
- No generation route survives; `/api/lighting/` serves only
  `/api/lighting/library`. Library save/import routes exist
  (`/api/library/save/lighting`, `/api/library/import/media`), and the
  apply path still understands `provenance: "procedural_result"`.
- `web/lighting_state.js` retains dormant job/progress scaffolding
  (`STAGES` PROMPT/PROGRESS/REVIEW, `activeJob`, `JOB_SYNCED`,
  `SHOW_REVIEW`, `APPLY_REQUESTED`), earmarked for possible reuse;
  `app.js` reads `state.lighting.activeJob` for `destinationLocked`.
- `web/lighting_composer.js` has its own imported-media effect vocabulary
  (`EFFECT_FIELDS`: type/frame_count/duration_ms/parameters). It is a
  different feature and stays untouched, per the effect-techniques plan.
- Binding rulings: LCM-frame-count and hash-noise rejections confirmed;
  per-key geometry rejection amended 2026-08-15 — engine must grow a seam
  for real key/LED positions when board definitions supply them
  (QMK/VIA/Vial), grid placement as fallback; AM families keep byte-exact
  current mapping.

## Product shape

A new **Effects** tool in the Lighting studio beside Paint and Import
media. The user picks an effect from a list (the fourteen kinds), adjusts
plain controls — two colors, speed, size, direction, count, trail,
density feel, and a "shuffle" (seed) button — sees a live preview on the
board raster, and saves the result to Library. Apply to hardware stays the
existing manual, typed-confirmation flow. Everything renders locally and
deterministically: same settings + same seed = identical file, every time.

Recipes (schema v1) remain the persisted format. The picker builds a
recipe; V1 exposes a single effect layer plus background (the format
supports up to 3 layers — UI for stacking can come later without a format
change). Density is chosen by the app per kind and bounded parameters so
every picker output passes `validate_quality` unchanged; the gates are not
weakened.

No background job system at V1: rendering a full frame budget is a
seconds-scale local operation, so the render endpoint is synchronous
(WorkBudget-bounded). The dormant job scaffolding in `lighting_state.js`
stays untouched as the designated fallback if real-world render times ever
demand async progress UI. This settles the slice-6 earmark without
deleting or reviving anything.

## Slices

1. **Engine kinds.** Implement the seven adopted kinds in `_sample_layer`
   under the effect-techniques plan's hard constraints (existing
   `_LAYER_KEYS` only; loop-by-construction periodicity; seeded
   determinism; `validate_quality` passes unmodified — bound parameters
   until it does or drop the kind, per that plan). New tests in
   `tests/test_procedural.py` per kind: determinism, loop-boundary
   continuity, quality acceptance of a committed reference recipe; every
   new test bite-proven (revert implementation, watch fail, restore).
   `procedural.py` stays dormant in this slice.

   DONE 2026-08-15: all seven kinds landed in `am_configurator/procedural.py`
   (+146 lines) — `breathe` and `heartbeat` as global envelopes before the
   directional block, `ripple`, `chase`, `matrix_rain`, `fire`, `twinkle`
   after `sweep`, plus two helpers: `_hash_unit()` (32-bit xorshift over
   small integers) and `_cell()` (sub-pixel sample to raster cell). No
   `_LAYER_KEYS` additions; `recipe_schema()` and `validate_recipe()` both
   read `_KINDS`, so the enum and semantic validator widened without an edit.
   Every kind is periodic with period 1 in `local_phase`, and integer speeds
   plus integer per-cell rates (`matrix_rain` 1-2, `twinkle` 1-3) and integer
   bucket counts (`fire`, `16 * abs(speed)`) keep whole cycles per loop, so
   frame N is byte-identical to frame 0 by construction. Randomness is
   `_hash_unit(cell_or_lane, sub_stream, seed)` only; global `random` is
   never touched. No importer added — the module stays dormant and
   `tests/test_dependencies.py` was not edited.

   Reference recipes (committed in `tests/test_procedural.py`, rendered
   18x7 x 80 frames, `validate_quality` thresholds untouched): breathe
   dense lit[1.000,1.000] peak 255 seam 0.000/10.427; chase sparse
   lit[0.238,0.254] peak 255 seam 12.974/16.227; ripple balanced
   lit[0.476,0.667] peak 238 seam 5.762/8.072; matrix_rain sparse
   lit[0.294,0.349] peak 255 seam 19.881/36.379; heartbeat dense
   lit[1.000,1.000] peak 255 seam 4.000/25.843; fire balanced
   lit[0.659,0.706] peak 234 seam 1.915/9.210; twinkle balanced
   lit[0.516,0.651] peak 255 seam 12.180/17.937.

   Parameter bounding, and why. `breathe` and `heartbeat` have no spatial
   term, so they light every cell at the peak and none at the trough: no
   density band accepts them over a black background (`sparse` fails the
   0.60 ceiling at the peak, `balanced`/`dense` fail their floors at the
   trough). Both reference recipes therefore use `dense` over a dim
   always-lit background (`#141428`, max channel 40, above the 32 lit
   threshold) — the "background layer" escape this plan anticipated,
   spelled as a background colour rather than an extra layer.
   `heartbeat`'s adjacent-difference spike never threatened the gate: the
   only adjacent-difference check requires motion greater than zero, and the
   seam is one step of an exactly periodic sequence, so it can never exceed
   the maximum interior step. Its lobe width is still bounded at 0.6 because
   narrower lobes buy nothing visible at 80 frames. `chase` bounds count and
   trail together (2 runners, 0.3) for the sparse ceiling; `matrix_rain`
   bounds trail to 0.1 because a seven-cell lane only fits a head plus a
   short tail before crossing the same ceiling; `fire` bounds flame height
   to 0.9 because above 1.0 the whole raster lights. No kind was dropped and
   no threshold was weakened.

   Two reference recipes were retuned after bite-proofing showed the loop
   test had no power at the first choice — a finding worth recording. With
   `count` evenly spaced runners, `chase` repeats every `1/count` of the
   cycle, so at three runners a broken loop lands within a third of a cycle
   and the seam metric cannot see it; the reference uses two runners, where
   it can. `fire` at speed 2 resamples noise faster than one frame, so its
   adjacent-frame difference saturates and a broken seam is indistinguishable
   from an ordinary step; the reference uses speed 1 (16 buckets per cycle).

   Tests: `AdoptedEffectKindTests` in `tests/test_procedural.py` (+299
   lines, 5 test methods over 7 subtested kinds) — schema/validator
   registration, sampler distinctness, determinism, loop-boundary
   continuity, and quality-gate acceptance. Verification: 590 Python tests
   OK (up from 585), `compileall` clean, 166 node tests OK, all seven
   `node --check` targets clean, `uv build` OK (0.1.68 sdist + wheel),
   `git diff --check` clean.

   Bite proof — each mutation applied to `am_configurator/procedural.py`,
   the five tests run, then the file restored and confirmed byte-identical
   (26 mutations, matrix captured; `restored: True` after every pass):
   - Remove one kind from `_KINDS` — the registration test fails for that
     kind (and the other four with it, since `validate_recipe` rejects the
     recipe). Proven for all seven.
   - Delete a kind's `_sample_layer` branch so it falls through to `noise` —
     the sampler-distinctness test fails for that kind (its render becomes
     byte-identical to `noise`). Proven for all seven; it also failed the
     quality test for `chase` and `matrix_rain`.
   - Scale a kind's `local_phase` by 1.37 (aperiodic) — the loop test fails
     for that kind. Proven for all seven, and it failed the quality test for
     all seven as well.
   - Replace a kind's branch body with `return 1.0, 0.0` — the quality test
     fails for that kind on the motion gate. Proven for all seven.
   - Multiply a kind's amount by `0.5 + random.random()` — the determinism
     test fails for that kind. Proven for `breathe`, `heartbeat`, `ripple`,
     `chase` (the four kinds that use no noise). For `matrix_rain`, `fire`,
     and `twinkle` the equivalent revert is replacing `_hash_unit()`'s
     xorshift body with `return random.random()`, which failed the
     determinism test for exactly those three.

   The bite-proof pass also caught a real defect in the first draft of the
   determinism test: it reseeded the global RNG to one fixed value *between*
   the two renders, which restored the exact state the first render had
   started from and made the test blind to global-RNG use for every kind
   after the first. It now seeds two different known values, one before each
   render.
2. **Render-and-bank endpoint.** One synchronous POST under
   `/api/lighting/` (exact name at implementation) taking a recipe plus
   target family/targets, rendering via `write_animation_artifacts`-style
   flow into the Library with `provenance: "procedural_result"`, returning
   the library entry. Remove the `procedural` dormancy allowlist entry in
   `tests/test_dependencies.py` in this slice — the module regains a
   production importer. Route tests including validation-rejection and
   WorkBudget-cancellation paths.

   DONE 2026-08-15: `POST /api/lighting/render` (+231 lines in
   `am_configurator/server.py`). The name follows the two conventions already
   in the file: `/api/lighting/` is the jobs namespace (`_lighting_get` serves
   `/api/lighting/library` and `/api/lighting/assets/…` from
   `GeneratedAssetLibrary`), and POST routes end in a verb
   (`/api/config/validate`, `/api/document/sync`, `/api/device/write`).

   Request: `{"recipe": <schema v1>, "product_id": "CB04", "targets":
   ["keyframes"]}` — an exact key set, rejected otherwise, matching
   `_library_save_lighting`'s strict-body style. The body never names a family
   or a raster: `device_mapping.generation_spec()` resolves both, exactly as
   `/api/led/gif` addresses a destination by `product_id` plus `targets`.
   Frame count is the family cap and frame duration is
   `min(device_mapping.LED_SPEEDS_MS)` (34 ms), so the mapper never resamples
   — the same two choices the deleted pipeline made
   (`FASTEST_FRAME_DURATION_MS`, `snapshot["frame_cap"]`). Response: `201` with
   `catalog.get("job:<id>")`, the same detail shape
   `/api/library/save/lighting` returns for `item:<id>`.

   Banking. The result is one `generation_job` manifest with
   `pipeline: "procedural"`, four assets (`recipe`, `raster_animation`,
   `preview_animation`, `mapped_result`), and one completed entry in
   `procedural_attempts` carrying the quality metrics — the containers
   `library.py` already defines for exactly this and the shapes `app.js`
   already reads (`libraryCoverAsset` prefers `preview_animation`;
   `latestLibraryGeneratedAttempt` plus the generated-preview path need
   `mapped_result_asset_id` and `job.target.targets[0]`; `applyLibraryPreview`
   then applies it under the client-side provenance token
   `procedural_result`). Nothing deleted by the AI removal was revived:
   `create_job`/`bank_asset`/`update_manifest` are live, tested
   `GeneratedAssetLibrary` methods; the coordinator, gate, threads, and
   provider are not reintroduced, and no Library schema changed. The saved-item
   namespace was considered and rejected: `_validate_saved_manifest`
   (`am_configurator/library.py:2409`) allows a `lighting_composition` exactly
   two assets — its rendered result and one preview — so the recipe and the
   raster GIF could not be banked without widening
   `_SAVED_COMPOSITION_FIELDS`, i.e. a manifest schema change.

   Budget: `_EFFECT_RENDER_DEADLINE_SECONDS = 60.0`. The deleted coordinator
   gave a whole operation 180 s (`DEFAULT_OPERATION_TIMEOUT_SECONDS` in
   `27a01ae:am_configurator/procedural_generation.py`), but that budget also
   covered a network call to a model provider; this route runs only the local
   half. Measured worst case end to end on the largest supported raster (NEON
   head, 46x5, 256 frames) is 13.2 s — 60 s leaves roughly four times that
   headroom on slower machines without letting one synchronous request hang for
   minutes. The budget is built behind `_effect_work_budget()` so a test can
   expire it at an exact stage, the way the coordinator's injected `monotonic`
   allowed. Every rendering stage is budget-checked; one final `work.check()`
   sits immediately before `create_job`, the last moment at which nothing has
   been written. Banking itself is deliberately unbounded: it only commits
   bytes that already exist.

   Errors. `RecipeError` is a `ValueError`, so an unusable recipe or target
   already lands on `do_POST`'s `400` branch with the engine's own message.
   `QualityError` is re-raised as a `ValueError` carrying
   `code: "quality_failed"` and the failure names ("This effect did not pass
   the lighting checks: density. Nothing was saved. …") — `code` uses the same
   optional-attribute channel `DocumentRevisionError` uses. `WorkCancelled` and
   `WorkDeadlineExceeded` are `RuntimeError`s, so they were added to
   `_lighting_error` and map to `409`, the status this route family already
   uses for `MediaRenderSuperseded` — transient, retryable, nothing saved. The
   server has no 5xx vocabulary other than the generic 500.

   Files changed: `am_configurator/server.py` (+231), `tests/test_app.py`
   (+202/-2: five new tests, one new row in
   `test_routes_require_authentication`, and a `timeout` argument on the shared
   `_request` helper), `tests/test_dependencies.py` (+4/-8 — the `procedural`
   dormancy entry removed; the set is now empty and the guard passes on its own
   because `server.py` imports the module in three production places).

   Verification: 595 Python tests OK (up from 590), `compileall` clean, 166
   node tests OK, all seven `node --check` targets clean, `uv build` OK
   (0.1.68 sdist + wheel), `git diff --check` clean.

   Bite proof — each mutation applied to `am_configurator/server.py`, the named
   test run, then the file restored and confirmed byte-identical (15
   mutations; `restored: True` after every pass):

   | # | Mutation | Test | Result |
   | --- | --- | --- | --- |
   | M1 | Bank the preview as `preview_poster`/`image/png` | banks_one_openable_procedural_result | fails |
   | M2 | Never append the `procedural_attempts` entry | banks | fails |
   | M3 | Transpose the raster in the banked target | banks | fails |
   | M4 | Drop `product_label` from the banked target | banks | fails |
   | M5 | Bank the caller's recipe instead of the validated one | banks | fails |
   | M6 | Accept extra request fields | rejects_unusable_requests | fails |
   | M7 | Accept an empty LED-area list | rejects_unusable_requests | fails |
   | M8 | `assess_quality` instead of `validate_quality` | rejects_failed_quality | fails |
   | M9 | Give every render an hour instead of the chosen deadline | deadline_leaves_no_partial_entry | fails |
   | M10 | Move the pre-banking `work.check()` after `create_job` | checks_the_budget_before_it_writes | fails |
   | M10b | Delete the pre-banking `work.check()` | checks_the_budget_before_it_writes | fails |
   | M11 | Unwire the route from the POST dispatch | banks | fails |
   | M12 | Map an expired budget to the generic internal error | deadline_leaves_no_partial_entry | fails |
   | M13 | Remove every production import of `procedural` | dependencies: every_top_level_module_is_imported | fails |
   | M14 | Make `_authorized()` return True | routes_require_authentication | fails |

   One honest negative worth recording: M5 does **not** bite the
   validation-rejection test, because `procedural.render_recipe` re-validates
   its recipe internally, so bad input is still rejected without the route's
   own `validate_recipe` call. That call is load-bearing for *normalization*
   instead — the banked recipe asset must be the normalized one — so the
   happy-path recipe now arrives untidy (padded name, lowercase hex) and the
   test asserts the banked palette comes back uppercased. M5 fails there. Two
   other first-draft mutations also failed to bite and forced real fixes:
   removing `work=work` from `render_recipe` alone left the later stages
   budgeted, so the deadline mutation became "extend the deadline to an hour";
   and with a zero deadline the render always raises before banking, so the
   pre-banking boundary needed its own test that expires the clock the instant
   `map_frames_to_led_tracks` returns.

   Not done, deliberately: no UI (slice 3), no cancel channel (the budget's
   `cancelled` predicate is a constant `False`; the `WorkCancelled` mapping is
   there for when one lands), no hardware write, and
   `LibraryCatalog._job_summary` (`am_configurator/library.py:3114`) still
   hardcodes `"origin": "ai_generation"` for every job, so a procedurally
   rendered entry would label itself "Ai generation" on the Library card.
   Correcting that is a Library projection change with user-visible copy
   consequences, so it belongs with slice 3's plain-language sweep; nothing
   calls this route until then.
3. **Picker UI.** The Effects tool panel (app.js + workspace wiring):
   kind list, bounded controls, seed shuffle, live raster preview,
   save-to-Library. Composer vocabulary and job scaffolding untouched.
   Web tests for state, bounds, and determinism of preview requests;
   plain-language sweep for user-facing copy.

   DONE 2026-08-15: the tool ships as **Patterns**, a fourth studio tool.

   **Name correction to this plan's Product shape.** The plan said "a new
   Effects tool beside Paint and Import media"; the studio already has three
   tools and the third is already labelled **Effects** (`data-studio-tool=
   "animate"`, `am_configurator/web/app.js`) — the client-side colour effects
   (Pulse, Hue cycle, Sweep, Shimmer, Move & zoom) that transform an already
   painted frame. That tool is live, tested, and out of this plan's scope, so
   the picker could not take its name. The new tool is `pattern`, labelled
   **Patterns**, and the four tabs now read Paint · Import media · Effects ·
   Patterns. The plan's own premise ("no effect picker exists in the browser
   UI") remains true of the *engine kinds*; it was never true that only two
   tools existed. No existing tool was renamed or altered.

   **Preview architecture: the server render, opened the way a generated
   Library entry already opens.** Of the two options this plan allowed, the
   studio supports the second natively and the first not at all. Create posts
   to `/api/lighting/render`, and on `201` the panel fetches the banked
   `mapped_result` and calls `openLibraryBoardPreview({kind:
   "library_generated", …})` — the exact function `previewLibraryGenerated`
   uses for a Library entry made this way, which feeds
   `boardFrameSetFromMappedResult` under provenance `procedural_result` and
   drives the existing playback runtime. The Board therefore animates the real
   mapped LED result, not an approximation, and Apply is the already-tested
   `applyLibraryPreview` path. A client-side approximation was rejected: it
   would mean a second copy of `_sample_layer` in the browser that can drift
   from the engine, and a preview that lies is worse than no preview when the
   next step is a gate the server owns. No background job system was added and
   `lighting_state.js`'s dormant job scaffolding was not touched.

   **Bounded space, and the two structural choices that made it provable.**
   Density and the background are chosen by the app, never by the user:
   **every** pattern uses `density: "dense"` over a wash that is the main
   colour at 40/255. Every offered colour has a 255 channel, so the wash's
   brightest channel is exactly 40 — above the engine's lit threshold of 32 —
   which makes `minimum_lit_ratio` 1.0 on every frame and the dense band
   unconditional for all fourteen kinds. That subsumes slice 1's
   breathe/heartbeat requirement rather than special-casing it. Loop seam and
   motion are structural: every kind is periodic with period 1 in
   `local_phase` and speeds are whole numbers, so the seam is one ordinary
   step of an exactly periodic sequence and can never exceed the largest
   interior step. **Brightness (`peak_brightness > 180`) is the only gate that
   ever failed**, and it failed on geometry, not colour: the metric reads the
   4-subsample average of a pixel, so a bright region narrower than one light
   never clears the threshold however saturated it is.

   Controls are short lists of allowed steps, not free ranges — five steps per
   continuous control, the whole integer range for small counts, eight compass
   points for direction (four for Rainfall), three speeds, nine colours. Each
   control is offered only where `_sample_layer` reads it; everything else is
   written at a fixed value the panel never shows (`phase` 0, centre 0.5/0.5,
   `intensity` 1). Per kind: Comet head size/how many/tail/direction; Wave
   band width/spacing/direction; Pulse ring width/reach; Sparkle how
   many + shuffle; Orbit dot size/circle size/how many; Sweep band
   width/direction; Drift (`noise`) cloud fullness + shuffle; Breathe glow
   fullness; Chase how many/tail; Ripple ring width/spacing; Rainfall
   (`matrix_rain`) streak length/direction + shuffle; Heartbeat beat length;
   Fire flame softness/height + shuffle; Twinkle fade fullness + shuffle.

   Slice 1's recorded caps are all honoured and asserted: chase ≤ 2 runners,
   `matrix_rain` trail ≤ 0.1, fire height ≤ 0.9, heartbeat width ≤ 0.6.
   Seven kinds needed a tighter floor than first drafted, every one of them
   for brightness and every one found by sweep, not by argument: comet head
   size ≥ 0.75, orbit dot size ≥ 0.45, Drift cloud fullness ≥ 0.45, wave band
   spacing ≥ 0.6, ripple ring spacing ≥ 0.5, fire flame height ≥ 0.75.

   **Sparkle is the one kind bounding alone could not fix**, and the fix
   changed the shuffle contract for every seeded kind. Its points sit at
   seeded random positions, so on a coarse board a whole arrangement can miss
   every light centre — at point size 0.9 and 12 points, 20 of 288
   (seed, speed, board) combinations were still too dim. Sparkle's point size
   is therefore pinned at the checked constant 1.0 (not offered as a step) and
   **Shuffle now steps through a recorded list of sixteen checked arrangement
   numbers** (`PATTERN_ARRANGEMENTS`) instead of any whole number 0–9999. That
   applies to all five seeded kinds and has a second benefit that matters more
   than sparkle: it makes the entire reachable space **finite**, so "every
   combination the interface can reach" is something a sweep can actually
   enumerate rather than sample. The list was searched by checking candidates
   against every seeded kind, every control step, every speed and every board;
   roughly half of all candidates fail and are excluded.

   **Evidence.** The reachable space is 6,585 recipes. Verified with the worst
   colour pair the palette can offer — Orange + Blue, whose blend can dim a
   channel to 140.2 of 255, established by searching all 81 offered pairs for
   the one minimising the brightest channel of any blend.
   - Every reachable recipe × all six board sizes and frame budgets
     (CB keys 15×6×80, ALICE 16×5×186, CB display 40×5×80, Relic 18×7×200,
     NEON axial 19×6×256, NEON head 46×5×256): **39,510 brightness checks,
     0 dim**.
   - Every reachable recipe through the real `render_recipe` +
     `validate_quality` on CB keys: **6,585 renders, 0 failing**.
   - A stratified sample (40 per kind) through the real checks on the other
     five boards: **2,500 renders, 0 failing**.
   No threshold was weakened and no kind was dropped. This is empirical
   evidence against today's six board geometries; slice 4's per-key placement
   seam changes the sampled geometry, so the sweep and the arrangement list
   must be re-run when it lands.

   **Library origin fixed (the slice-2 finding).**
   `LibraryCatalog._job_summary` now reads `_JOB_ORIGINS[manifest["pipeline"]]`
   — `procedural` → `lighting_effect`, `legacy_video` → `ai_generation` (only
   manifests migrated from schema version 1 can carry that). The browser
   renders it through `libraryStatusLabel(item.origin)` on the Library card and
   the detail header, so a locally rendered effect now reads "Lighting effect"
   where it would have read "Ai generation". No test asserted the old constant,
   so none needed trimming.

   Files changed: `am_configurator/web/lighting_state.js` (+306: the pattern
   tables, step snapping, arrangement list, recipe builder — the dormant job
   scaffolding untouched), `am_configurator/web/app.js` (+227/-3: the Patterns
   panel, its wiring, and the create/preview flow), `am_configurator/web/
   style.css` (+6: swatch grid and the panel's action row),
   `am_configurator/library.py` (+9/-1: `_JOB_ORIGINS`),
   `tests/web/lighting_patterns.test.js` (new, 376 lines, 13 tests),
   `tests/web/plain_language.test.js` (+4: `lighting_state.js` added to the
   swept surfaces, two rules added), `tests/web/lighting_flow.test.js` (+1/-1:
   the studio-tool list), `tests/test_app.py` (+43),
   `tests/test_library.py` (+21). No change to `index.html`, no new web file,
   and `lighting_composer.js` untouched.

   Verification: 597 Python tests OK (up from 595), `compileall` clean, 179
   node tests OK (up from 166), all seven `node --check` targets clean,
   `uv build` OK (0.1.68 sdist + wheel), `git diff --check` clean. Native
   build + frozen smoke test run once for this plan on macOS:
   `Native tree audit passed.` … `Desktop smoke test passed (Darwin).`, and
   the frozen binary run directly with `--smoke-test` printed
   `Desktop smoke test passed (Darwin).` and exited 0.

   Bite proof — each mutation applied, the named test run, then the file
   restored and confirmed byte-identical (22 mutations; `restored: True`
   after every pass):

   | # | Mutation | Test | Result |
   | --- | --- | --- | --- |
   | M1 | Rename a pattern to an id the engine does not publish | fourteen offered patterns | fails |
   | M2 | Widen chase to 6 runners | reachable space inside the bounds | fails |
   | M3 | Widen Rainfall streak length to 0.4 | reachable space inside the bounds | fails |
   | M4 | Widen flame height to 1.2 | reachable space inside the bounds | fails |
   | M5 | Widen heartbeat beat length to 0.9 | reachable space inside the bounds | fails |
   | M6 | Build recipes at `balanced` instead of `dense` | reachable space inside the bounds | fails |
   | M7 | Drop the wash (background `#000000`) | the always-on wash keeps the fullness band | fails |
   | M8 | Shuffle returns a free number again | the same arrangement builds the same lighting | fails |
   | M9 | Clamp lets a stored arrangement through unsnapped | arrangements come from the checked list | fails |
   | M10 | Clamp returns control values unsnapped | settings snap onto an allowed step | fails |
   | M11 | Remove sparkle's pinned point size | arrangements come from the checked list | fails |
   | M12 | Offer wave a tail control it never reads | only the consumed controls are offered | fails |
   | M13 | Post to `/api/lighting/generate` | Create sends exactly the accepted body | fails |
   | M14 | Add a fourth key to the request body | Create sends exactly the accepted body | fails |
   | M15 | Drop `pattern` from the studio tools | Patterns is a studio tool | fails |
   | M15b | Same mutation | every manual studio tool stays reachable | fails |
   | M16 | Surface the engine's failure names in the panel | a rejected effect is explained plainly | fails |
   | M17 | Put "Ai generation" in a toast | banned vocabulary sweep | fails |
   | M18 | Restore the hardcoded `ai_generation` origin | catalog origin test | fails |
   | M18b | Same mutation | render route labels the entry | fails |
   | M19 | Show Shuffle only where it does nothing | the panel renders one complete control set | fails |
   | M20 | Drop the per-pattern controls from the panel | the panel renders one complete control set | fails |
   | M21 | Replace the Create copy with engine words | the panel says plainly what Create does | fails |

   One honest negative worth recording: M8 does **not** bite the
   "arrangements come from the checked list" test, because
   `clampPatternSettings` snaps whatever Shuffle returns back onto the list —
   the two guards are independent, and the shuffle contract is held by the
   determinism test instead. Two earlier drafts also had to be strengthened
   before they bit: the request-shape test originally only matched the three
   keys it wanted, so adding a fourth key passed until it asserted the exact
   key set; and the Patterns action row first reused `animation-draft-actions`,
   which silently broke an existing Effects test that slices the file at the
   first occurrence of that class — the row now has its own `pattern-actions`
   class.

   Not done, deliberately: no per-control live preview (each Create is a full
   local render, so the Board updates on Create rather than on drag); no
   multi-layer stacking (the format allows three, this plan's V1 is one layer
   plus background); no render-without-saving path, because the route always
   banks and adding one is backend work this slice does not own; the existing
   Effects tool, `lighting_composer.js`, and the dormant job scaffolding are
   unchanged.
4. **Geometry seam.** Optional per-key/per-LED placement table accepted at
   the mapping seam (`device_mapping`), default preserves today's
   byte-exact behavior — proven by the existing byte-exact tests running
   unchanged — plus one unit test showing a synthetic placement table is
   honored. No QMK/VIA/Vial integration here; that lands with the v2
   multi-firmware lanes and consumes this seam.

## Verification

Every slice: the full entry point from `.agents/repo-guidance.md`
(Verification). New tests bite-proven as described. Native build +
`--smoke-test` once after slice 3 (UI enters the frozen bundle). No
hardware writes anywhere in this plan (Device Safety rule). This plan's
verification supersedes the effect-techniques plan's items 2/3/5, which
still reference AI-era files deleted by the AI removal
(`test_procedural_generation.py`, model qualification runs); a dated
correction is recorded there.

## Out of scope

- Text banner authoring (own plan per Adopt 3 ruling).
- Reactive panel→key derivation (explicitly an unscoped open question in
  the effect-techniques plan).
- QMK/VIA/Vial support and the OpenKeeb v2 plugin surface (v2 plan).
- Removing the dormant job scaffolding (kept as async fallback).