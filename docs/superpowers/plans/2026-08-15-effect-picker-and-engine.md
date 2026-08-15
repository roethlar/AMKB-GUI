# Deterministic Effect Picker and Engine

**Status:** Draft, awaiting owner approval. No implementation is authorized
by this document. Premises below were verified against the working tree at
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