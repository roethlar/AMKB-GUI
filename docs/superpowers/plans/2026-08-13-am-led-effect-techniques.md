# Procedural Effect Expansion from AM LED Builder Techniques

**Status:** Draft. Ruling (1) landed 2026-08-13: adopt seven kinds —
breathe, chase, ripple, matrix_rain, heartbeat, fire, twinkle; strobe is
excluded ("Seven, no strobe"). Rulings pending, in order: (2) whether to
add the reactive panel-coupled key track and where its switch lives,
(3) confirmation of the rejections recorded below. No implementation is
authorized until the remaining rulings land and this status line records
them.

## Source analysis

<https://am-led.nanakumi.net> ("AM LED JSON Builder") is a community,
browser-only editor that exports LED profile JSON byte-compatible with
`diy.angrymiao.com` for the Cyberboard and AM RGB-65. Its bundle is minified,
carries no license, and has no discoverable public repository, so **no code
from it may be transcribed or ported. Implement only from the behavioral
descriptions in this plan**; the descriptions below were derived by observing
the tool's behavior and output format.

Engine characteristics observed:

- Every effect is a pure sampler `(ledIndex, frameIndex) -> hex color`,
  baked at export into `frame_data` arrays. No runtime animation system.
- Per-key physical geometry (`xCenterEm`, `row`, per-product radial distance
  table) drives positional effects (wave, sweep, comet, chase, ripple).
- Loop length is the least common multiple of the motion period and the
  color-cycle length, clamped to the device frame cap, then tiled.
- Color source (solid, A→B gradient along a chosen axis, rainbow, or
  panel-synced) is a separate sampler multiplied by the motion's intensity
  envelope.
- Panel-coupled key effects: `mirrorPanel` copies the display pixel above
  each key; `reactiveScroll` lights a key when its display column's mean
  luma crosses a threshold, adopting the column's brightest color.
- Noise effects use a deterministic integer hash of
  `(ledIndex, frameBucket, salt)`, so re-export is byte-identical.

## Fit against this codebase

- `am_configurator/procedural.py` renders recipes on rectangular rasters
  with `phase = frame_index / frame_count` and validated **integer** layer
  speeds, so every layer completes whole cycles and loops are seamless by
  construction (`validate_quality` additionally gates the seam). Frame
  count is pinned to `device_mapping.MODEL_FRAME_CAPS` per family.
- Effect kinds are LLM-facing only: `procedural.recipe_schema()` is handed
  to providers by `recipe_provider.py`; there is no user-facing effect
  picker. `lighting_composer.js` has an independent media-compositing
  vocabulary that this plan does not touch.
- `device_mapping.frames_to_led_tracks` already resamples one source raster
  into every target track, which is the `mirrorPanel` behavior for boards
  with both a display and a key track.
- True per-key x/y geometry exists only for NEON dynamic layouts read from
  the device; the three fixed families are raster-placement only.

## Adopt 1 — new raster-domain layer kinds (ruled: seven, no strobe)

Add `breathe`, `chase`, `ripple`, `matrix_rain`, `heartbeat`, `fire`, and
`twinkle` to `procedural._KINDS`, implemented in `_sample_layer` in the
existing raster/phase domain. `strobe` is excluded by the 2026-08-13
ruling; its sketch below is retained only as the record of what was
declined. Hard constraints for every new kind:

- Reuse only existing `_LAYER_KEYS` parameters; no schema key additions.
- Periodic in `local_phase` so loop-by-construction is preserved.
- Deterministic: any randomness comes from `layer["seed"]` via
  `random.Random(seed)` precomputation or a small integer hash of
  `(cell, frame_bucket, seed)` implemented from the standard xorshift
  construction — never global RNG state.
- Must pass `validate_quality` unmodified. The quality gates are
  load-bearing; if a kind cannot pass without weakening thresholds, bound
  its parameters until it passes or drop the kind. Strobe and heartbeat
  are the known risks (adjacent-frame difference spikes).

Candidate kinds, each returning `(amount, mix)` like existing kinds:

- `breathe` — global envelope, no spatial term:
  `amount = (0.5 - 0.5*cos(2π*local_phase))^gamma`, `gamma` from `width`
  (smaller width → sharper); `mix` = the oscillation value. Distinct from
  `pulse`, which is an expanding radial ring.
- `strobe` (**declined 2026-08-13, do not implement**) — global square
  wave: on when `frac(local_phase) < duty`, `duty = 0.1 + 0.4*width`;
  `amount` 1/0, `mix` fixed 0. Declined for its adjacent-frame-difference
  conflict with the quality gates.
- `chase` — `count` runners with exponential tails traversing lit raster
  cells in serpentine row-major order; runner head position =
  `frac(local_phase + i/count) * n_cells`; tail length from `trail`;
  sign of `speed` (already ±) sets direction.
- `ripple` — concentric wave train from `(center_x, center_y)`:
  `amount = (0.5 + 0.5*sin(2π*(distance/(scale*min_dim) - local_phase)))^k`,
  `k` from `width`; `mix = 1 - wave`. Distinct from `pulse` (single ring)
  and `wave` (planar).
- `matrix_rain` — per-column drops falling along the axis chosen by
  `direction_degrees`; column start offset from hash(column, seed); head at
  full `amount` with `mix = 1` (secondary color highlights the head),
  exponential tail over `trail` cells; wraps periodically.
- `heartbeat` — global double-beat envelope: two gaussian lobes per cycle
  centered at phase 0.0 and ~0.18, widths from `width`; `mix` = envelope.
- `fire` — vertical intensity ramp (bottom row hottest) times hash noise
  per cell per frame bucket (bucket count derived from `speed` so the
  bucket sequence completes whole cycles per loop); `mix` rises toward the
  secondary color near the base.
- `twinkle` — every lit cell fades in/out on its own hash-derived phase
  offset and rate; contrast with `sparkle`, which places `count` discrete
  points from the seed.

Companion work required by the adopted kinds:

- Extend semantic validation and `recipe_schema()` enums.
- Extend `recipe_system_prompt()` with one-line guidance per kind
  (when to choose it, what parameters matter).
- Extend the committed qualification corpus so
  `test_committed_corpus_covers_devices_densities_effects_and_adversarial_prompts`
  again proves coverage of every kind; corpus tests stay offline.
- One manual local qualification run (`build_tools/qualify_recipe_model.py`,
  local Ollama, no cloud, no device writes) after implementation; record
  the result in `.agents/state.md`.

## Adopt 2 — reactive panel-coupled key derivation

New derivation mode for families with two tracks driven by one source:
CB (`frames` 40×5 → `keyframes` 15×6) and NEON (`head` 46×5 → `axial`
19×6). Today both destinations get the same resampled source raster
("mirror"). Add "reactive":

For each destination raster cell, map its x-extent onto the source track's
column band. Compute the band's mean Rec.709 luma
(`0.2126R + 0.7152G + 0.0722B`, normalized). If it exceeds threshold
`t = 0.18`, the cell takes the band's brightest pixel color; otherwise
black. Deterministic, per-frame, no state.

Wiring:

- New pure helper in `device_mapping.py` taking the already-mapped source
  track frames plus the destination layout; unit-tested byte-exact.
- Recipe root field `key_track` with values `"mirror"` (default, exactly
  today's behavior) and `"reactive"`, honored only for CB and NEON;
  validation rejects it elsewhere. Schema and system prompt updated so
  providers may choose it. Default keeps every existing recipe and banked
  asset byte-identical.
- `procedural_generation.py` render path applies the derivation after
  rendering, before `validate_mapped_result` (mapped shape unchanged).
- The imported-media path is untouched in this plan.

## Rejected

- **Per-key `xCenterEm` geometry sampling.** Contradicts the raster
  contract that `device_mapping._LAYOUTS`, the media mappers, and their
  byte-exact tests lock down; fixed families have no authored physical
  geometry; the gain is sub-column precision on staggered rows only.
  Revisit only if adopted effects visibly misalign on hardware.
- **Minimal LCM frame counts.** Loops here are already seamless by
  integer-speed construction, and firmware plays at fixed speed, so
  shrinking frame counts would shorten loop duration, not improve quality.
  Frame caps remain the canvas.
- **Deterministic hash noise as a standalone change.** Existing seeded
  `random.Random` rendering is already reproducible; the hash construction
  enters only as an implementation detail of new kinds that need per-cell,
  per-bucket noise.
- **`word_page` text authoring** (5×5 font scrolling text). The app
  currently passes `word_page` through untouched (`writer.py` replays it;
  `server.py` emits an empty stub; `profile_import.py` does not validate
  it). A text-page composer is a separate feature with its own UI, font,
  and wire-format surface — its own plan if ever wanted.

## Verification

1. Per adopted kind: new tests in `tests/test_procedural.py` for
   determinism, loop-boundary continuity, and quality-gate acceptance of a
   committed reference recipe. Prove each new test bites: revert the
   implementation, watch it fail, restore.
2. Reactive derivation: byte-exact unit test in
   `tests/test_device_mapping.py`; a `test_procedural_generation.py` case
   proving `key_track: "mirror"` output is unchanged from today and
   `"reactive"` changes only the derived track.
3. Corpus coverage test green with the extended corpus.
4. Full repository verification entry point from
   `.agents/repo-guidance.md`.
5. Manual local model qualification run as above. No hardware writes
   anywhere in this plan.
