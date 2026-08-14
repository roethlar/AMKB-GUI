# Procedural Effect Expansion from AM LED Builder Techniques

**Status:** Draft, and **partly built on premises the code contradicts**. A
2026-08-14 verification pass against the source corrected three of them; the
corrections are marked inline and dated.

- Ruling (1) landed 2026-08-13: adopt seven kinds — breathe, chase, ripple,
  matrix_rain, heartbeat, fire, twinkle. Stands unchanged.
- Strobe is **not** declined. The 2026-08-13 rationale was false, and strobe
  is a text effect rather than a per-key kind; it belongs to text banner
  authoring (Adopt 3).
- Ruling (2) is **withdrawn, not pending.** Its premise — existing panel→key
  mirroring to add a mode to — does not hold. See Adopt 2.
- The open scoping question this plan does not answer: **effect kinds are
  reachable only by an LLM.** There is no user-facing effect picker, so
  adopting kinds does not give users the reference builder's options.
- Ruling (3), confirmation of the rejections below, is still outstanding.

No implementation is authorized.

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
- **Effect kinds are LLM-facing only, and that is a scope problem, not a
  footnote** (verified 2026-08-14). `procedural._KINDS` is
  `{comet, wave, pulse, sparkle, orbit, sweep, noise}`; `recipe_schema()`
  hands those names to providers via `recipe_provider.py`. No effect picker
  exists anywhere in the browser UI — every `kind` in `app.js` refers to
  asset or document kinds, never an effect. Adding kinds to `_KINDS`
  therefore widens only what a model may emit; a user cannot choose one.
  The reference builder is the opposite: the user picks from 14 named
  patterns and no model is involved. **Delivering the builder's lighting
  options to users needs a user-facing effect picker, which does not exist
  and is not in this plan.** `lighting_composer.js` has an independent
  media-compositing vocabulary that this plan does not touch.
- Source-raster fan-out differs by path (verified 2026-08-14), and the
  earlier blanket claim here was wrong:
  - **Imported media:** `frames_to_led_tracks` accepts several targets and
    resamples the source *independently per target size* — crop to each
    track's aspect ratio, then resize (`device_mapping.py:981-995`).
    `validate_gif_targets` imposes no same-raster restriction, so one GIF
    can drive a display track and a key track together.
  - **Procedural generation:** `generation_spec` refuses targets whose
    rasters differ — "generate one target at a time"
    (`device_mapping.py:1302`). CB `frames` 40×5 vs `keyframes` 15×6 and
    NEON `head` 46×5 vs `axial` 19×6 are both refused, so a generated
    animation cannot feed panel and keys at once.
  - Neither path is the builder's `mirrorPanel`. Both resample a shared
    source picture; neither derives a key's color from the panel's rendered
    output above it.
- True per-key x/y geometry exists only for NEON dynamic layouts read from
  the device; the three fixed families are raster-placement only.

## Adopt 1 — new raster-domain layer kinds (ruled: seven)

Add `breathe`, `chase`, `ripple`, `matrix_rain`, `heartbeat`, `fire`, and
`twinkle` to `procedural._KINDS`, implemented in `_sample_layer` in the
existing raster/phase domain. `strobe` is not among them because it is not
a per-key kind — see the corrected note below. Hard constraints for every
new kind:

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
- `strobe` (**not a per-key kind — corrected 2026-08-14**) — on the
  reference builder, strobe is a *text effect* toggle beside Bold, Outline,
  Glow, Motion Blur, Shadow, Pulse, Flicker, Sparkle, and Shake. It applies
  to scrolling panel text, not to key LEDs, so it was never comparable to
  the seven kinds above. It belongs to text banner authoring (Adopt 3) and
  arrives with that feature.
  The 2026-08-13 record declined it "for its adjacent-frame-difference
  conflict with the quality gates." That rationale is false: the only
  adjacent-difference check in `validate_quality` requires motion *greater*
  than zero (`procedural.py:659`), and a square wave maximizes it. The
  interaction that does exist is with the density floor — dark off-frames
  drive `minimum_lit_ratio` to zero, failing `balanced` (≥ 0.35) and
  `dense` (≥ 0.70) while passing `sparse`, which sets no floor. That check
  runs only on the AI generation path, so it never governed whether a
  hand-authored effect may exist. Both facts are recorded so the error is
  not re-derived.
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

**Premise corrected 2026-08-14; this section is not ready to rule on.** It
was written as a new *mode* on existing panel→key mirroring. No such
mirroring exists to add a mode to:

- The panel and key sections are independent surfaces in this app. The UI
  offers them as separate targets ("Top display 40×5" / "Switch LEDs" on CB,
  "Head matrix 46×5" / "Per-key" on NEON, `lighting_targets.js:15-31`), and
  the boards carry separate hardware controls for each — the keycode table
  lists independent power, brightness, speed, and effect keys under "Top
  display lighting" and "Under-key lighting" (`lighting_targets.js:40-53`).
- Procedural generation cannot even produce both at once: `generation_spec`
  refuses targets with differing rasters (`device_mapping.py:1302`), which
  both of these pairs are.
- Imported media can write both from one GIF, but by resampling the shared
  source separately per track — not by deriving key color from panel output.

So panel-coupled key lighting does not exist here in any form. The reference
builder has it as one of its 14 per-key patterns (`mirror panel`), and
`reactiveScroll` is a second, distinct one. Building either is **new
feature work on an independent key surface**, not a switch on existing
behavior, and it lands downstream of the missing user-facing effect picker
noted above. Whether to scope it is an open question, not a pending ruling.

The original sketch is retained below as the technique description, should
that scoping happen. Its "today both destinations get the same resampled
source raster" premise is the false one:

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

## Adopt 3 — text banner authoring (owner-scoped 2026-08-14, own plan)

The owner scoped scrolling-text banner authoring into v2 on 2026-08-14. The
NEON and Cyberboard billboard panels are the reason the feature exists, and
those two families are its only targets. This reverses the `word_page`
rejection this plan recorded on 2026-08-13.

Implementation stays out of *this* plan. A text composer carries its own UI,
bitmap font, per-scene text effects, and wire-format surface, and it is gated
on the v2 capability model rather than on the seven raster kinds. It needs its
own plan before any implementation.

Today the app passes `word_page` through untouched: `writer.py` replays it,
`server.py` emits an empty stub, and `profile_import.py` does not validate it.
That pass-through is the baseline the future plan starts from.

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
- ~~**`word_page` text authoring** (5×5 font scrolling text)~~ — **reversed
  2026-08-14 by owner scoping; see "Adopt 3" above.** Retained here as the
  record of what was declined on 2026-08-13.

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
