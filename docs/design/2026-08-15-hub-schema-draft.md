# OpenKeeb hub profile format — schema draft (H0, second half)

Status: DRAFT for owner review (2026-08-15). No product code. Written
against the real tables in
`docs/design/2026-08-15-h0-keycode-capability-survey.md`; every design
choice below cites the survey fact that forces it. Approving this draft
is part of closing H0; H1 (making it real: serialization, round-trip
tests, AM spoke ported) still needs its own go.

## What this is, in one paragraph

One OpenKeeb profile file captures everything a keyboard can be told —
identity, capabilities, keymap, layers, macros, lighting — with
per-field provenance. Every ecosystem (AM, Vial, VIA, whatever comes
later) gets a reader and a writer against this one format. A transfer
between boards is read → adapt → write, and produces a transfer report
saying what carried, what was adapted, and what was dropped.

## Top-level shape

```yaml
openkeeb_profile:
  format_version: 0            # draft; 1 at H1 freeze
  identity:      {...}         # who this profile was read from / built for
  capabilities:  {...}         # what the endpoint proved it can do
  keymap:        {...}         # layers of keys in canonical key identity
  macros:        [...]         # normalized event streams
  lighting:      {...}         # static / effects / per-key / animations
  provenance:    per-field     # see Provenance
```

## Provenance (plan requirement: explicit per-field)

Every leaf value carries one of three origins:

- `device` — read from the board (a VIA `GET_KEYBOARD_VALUE`, a Vial
  definition fetch, an AM probe);
- `user` — authored or edited in OpenKeeb;
- `default` — filled by OpenKeeb because nothing supplied it.

Draft mechanism: a parallel `provenance` map keyed by JSON pointer, not
inline tags — keeps the data readable and diffs small. Open to the
alternative (inline `{value, origin}` pairs) if round-trip tests at H1
prove the map awkward.

## Identity

```yaml
identity:
  ecosystem: am | vial | via          # spoke that produced the profile
  family: "NEON"                       # spoke-local family/model name
  wire_identity: "80"                  # exact quirks preserved (AM21 -> 80)
  endpoint: {vid: 0x..., pid: 0x..., transport: hid | serial}
  protocol:                            # all version axes, per survey
    via_protocol: 12                   # 7..13+ observed gates
    vial_protocol: 6                   # 0..6, when Vial
    keycode_spec: "0.0.8"              # stated (VIA >=13) or implied
  definition:                          # when definition-backed (Vial/VIA)
    source: device | user_import
    hash: sha256-...
```

Forced by: VIA's two-axis lookup (`protocol`, `keycodesVersion`), the
survey's "hub must carry both numbers per VIA endpoint", the
`AM21`→`80` wire-format quirk, and the settled untrusted-definition
ruling (hash pins what was validated).

## Capabilities (the descriptor the comparison tables feed)

```yaml
capabilities:
  keymap:   {layers: N, keys_per_layer: N, encoders: N}
  macros:
    budget: {model: events | bytes,        # incommensurable; carry native
             tracks: N, events_total: N,   # when model=events (AM serial)
             slots: N, buffer_bytes: N}    # when model=bytes (Vial/VIA/NEON)
    delays: true | false                   # VIA <11: false
  lighting:
    static_color: none | global | zone | per_key
    hardware_effects: [{generation: rgblight | led_matrix | rgb_matrix,
                        ids: [...]}]       # three keycode generations,
                                           # never conflated (survey rule)
    per_key_direct: true | false           # VialRGB / AM
    custom_animation: {frames_max: N, streaming: true|false}
```

Filled per endpoint at read time, never assumed per family — the
capability-honesty rule; VIA lighting is definition-derived.

## Keycode representation

- Canonical form: the QMK 16-bit composed value **verbatim** (`0x5203`
  style), plus its spec version via `identity.protocol.keycode_spec`.
  Composition is preserved, never flattened: `LT(3, KC_A)` stays a
  layer-tap of layer 3 over `KC_A` (survey: flattening kills
  cross-board transfer of layered maps).
- A decoded view `{range, args}` is derived at read/display time from
  the pinned ranges table, not stored — one truth, no drift.
- Untranslatable codes ride verbatim with `carried: false` candidates
  flagged for the transfer report — the in-repo `0xFF` passthrough page
  already proved read-back-stable identity is what preflight needs.
- `QK_KB`/`QK_USER` ranges are per-board custom codes: always
  `adapted/dropped` on transfer, never silently carried.

## Keymap

```yaml
keymap:
  layers:
    - index: 0
      keys:
        - key: "K_ENTER"          # canonical key identity,
          code: 0x0028            #   position-independent (plan: matching
        - key: "K_F13"            #   is by identity, not matrix coords)
          code: 0x5203
  spoke_addressing:               # spoke-local, never load-bearing for
    matrix: {rows: R, cols: C,    #   cross-board matching
             map: {K_ENTER: [3, 12], ...}}
  encoders: [{key: "E0", cw: 0x..., ccw: 0x...}]   # Vial label-encoded
```

Canonical key identity is the geometry seam already landed (per-key
LED positions feed the same way). The 108→40% first-pass contract
lives here: layer-1 alphanumerics match by key identity, homeless keys
become the worklist.

## Macros

```yaml
macros:
  - slot: 0
    events:                        # clean events; spokes own escaping
      - {tap: 0x0004}
      - {down: 0x00E0}
      - {up: 0x00E0}
      - {text: "hello"}            # text kept as text; spokes compile
      - {delay_ms: 250}            #   (AM compiles to US-layout events)
```

The shared vocabulary (tap/down/up/text/delay) is exactly the
intersection the survey proved across all three dialects. Wire quirks
(NUL separation, `0xFF00` avoidance, offset-by-one delays, ASCII-`|`
delays) belong to spoke codecs, never the hub. Budgets are metadata in
`capabilities.macros.budget`; preflight checks the target's budget in
the target's own vocabulary.

## Lighting

```yaml
lighting:
  static: {mode: global | per_key, color: [h, s, v],
           per_key: {K_ESC: [h, s, v], ...}}
  hardware_effect: {generation: rgb_matrix, id: N,
                    speed: N, color: [h, s]}
  animations:
    - {name: "...", frames: [...],        # existing AM frame model
       placement: geometry_seam}          # per-key positions when the
                                          #   definition supplies them,
                                          #   grid fallback (settled)
```

Only surfaces the endpoint's capability descriptor declares are
writable; everything else renders as absent, not disabled-looking —
the settled capability-gating rule.

## Transfer report (first-class, per plan)

```yaml
transfer_report:
  source: {identity...}
  target: {identity...}
  items:
    - {path: keymap.layers[0].keys[K_F13], verdict: carried}
    - {path: macros[2].events[4], verdict: adapted,
       reason: "delays unsupported on VIA protocol 9; delay dropped"}
    - {path: lighting.animations[0], verdict: dropped,
       reason: "target has no custom_animation capability"}
```

Three verdicts only: carried / adapted / dropped, each with a
plain-words reason. This is UI input, not a log.

## Open questions for H1 (none block approving the draft)

1. Provenance as pointer-map vs inline pairs (above).
2. File encoding: JSON vs TOML/YAML for the on-disk profile — decide
   with the existing `store.py` settings conventions at H1.
3. Whether `spoke_addressing` is stored or re-derived from the pinned
   definition at write time.
