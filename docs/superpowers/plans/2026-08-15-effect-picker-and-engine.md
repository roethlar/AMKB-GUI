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
3. **Picker UI.** The Effects tool panel (app.js + workspace wiring):
   kind list, bounded controls, seed shuffle, live raster preview,
   save-to-Library. Composer vocabulary and job scaffolding untouched.
   Web tests for state, bounds, and determinism of preview requests;
   plain-language sweep for user-facing copy.
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