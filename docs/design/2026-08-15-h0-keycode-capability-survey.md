# H0 — Keycode and capability survey (hub-configurator plan)

Status: IN PROGRESS (opened 2026-08-15). H0 is authorized by the approved plan
`docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md`. Output:
this survey doc plus a hub schema draft, both for owner review. No product
code.

Design constraint (from the plan): the normalized keycode space is the hard,
load-bearing choice. Survey the real QMK/Vial keycode tables before freezing
it; do not invent an abstraction until at least two spokes' real tables are in
front of us.

## Pinned sources (verified reachable 2026-08-15)

### QMK (feeds both the VIA and Vial spokes)

- Machine-readable keycode spec: `qmk/qmk_firmware` repo,
  `data/constants/keycodes/` — versioned hjson files, `0.0.1` through
  `0.0.8` (latest observed: `keycodes_0.0.8.hjson` +
  `keycodes_0.0.8_lighting.hjson`; versions are deltas over category files
  such as `_basic`, `_lighting`, `_macro`, `_quantum`, `_midi`). This is the
  canonical numeric-keycode ↔ name table, the same data QMK's own tooling
  generates from. Survey must record which spec version each protocol
  version implies.
- To pin before copying tables: exact commit hash of `qmk_firmware` at
  survey time, and the mapping from VIA/Vial protocol versions to keycode
  spec versions.

### Vial spoke

- Porting docs (device self-description, lighting, encoders):
  `https://get.vial.today/docs/` — notably "Build support 1 - Create JSON"
  (layout JSON), "Build support 2 - Port to Vial" (how a board becomes
  self-describing), "Backlight and RGB lighting", "Custom Keycode".
- No formal wire-protocol spec page exists; the authoritative protocol
  encoding (keymap read/write, macro byte format, tap dance, combos, QMK
  settings) is the `vial-gui` application source plus `vial-qmk` firmware
  source. Survey must extract macro/event encodings from there and cite
  file + commit.
- VialRGB per-LED streaming API: documented in Vial changelog v0.4 with a
  reference host script (`Vil4/vial_rgb_direct_control`) — already recorded
  in planning; lighting capability surface for the Vial spoke.

### VIA spoke

- Per-model definition files: `the-via/keyboards` repo (layout, matrix, LED
  map, features; the database behind usevia.app). Definitions are untrusted
  input with size/shape/key-count bounds (settled ruling).
- Definition spec and protocol constants: the VIA docs (caniusevia.com) and
  the `the-via/app` source for the dynamic-keymap command set. VIA is QMK
  with the dynamic-keymap protocol on, so its keycode space is the QMK spec
  above at the protocol version the firmware reports.

### AM spoke

- In-repo: `am_configurator/` transport, `device_mapping.FamilySpec`,
  `_LAYOUTS` table, and the existing Vial keymap/macro codecs — the already
  implemented protocol, surveyed from our own source, no fetch needed.

## Survey checklist (what "done" looks like)

- [x] QMK keycode table: ranges, categories, and version deltas 0.0.1→0.0.8
      recorded; per-version table extracted from pinned commit (see "QMK
      keycode space" below; raw tables consumed from the pinned checkout,
      not duplicated here).
- [ ] Vial macro encoding: byte format, event kinds, delays, limits — from
      vial-gui/vial-qmk source, cited.
- [ ] Vial self-description payloads: layout JSON shape, matrix, encoder,
      tap-dance/combo/QMK-settings surfaces, VialRGB capability report.
- [ ] VIA v3 definition schema: fields OpenKeeb consumes (layout, matrix,
      LED map, features, menus), bounds to enforce on untrusted input.
- [ ] VIA dynamic-keymap command set: keymap/macro read-write commands and
      per-protocol-version differences.
- [ ] AM spoke inventory: what `FamilySpec` + `_LAYOUTS` + existing codecs
      already express, in the same vocabulary as the above.
- [ ] Capability surface comparison: lighting (static/effects/per-key/
      streaming), macros (event kinds, budgets), layers (counts, switching),
      per family — the raw material for the hub's capability descriptor.
- [ ] Hub schema draft written against the surveyed tables (separate doc,
      second half of H0).

Tables below are extracted from pinned sources; each cites its commit/URL.

## QMK keycode space (extracted 2026-08-15)

Source: `qmk/qmk_firmware` commit `96c3e85e59b1acfa0d43c32a224ba2b26123fe3d`
(2026-08-12), shallow sparse checkout of `data/constants/keycodes/` kept at
`~/Dev/reference/qmk_firmware-keycodes/` (reference material, outside this
repo, like `cyberboard-cli/`). 1.3 MB of hjson; owner-approved download.

### Shape of the spec

- Every keycode is a 16-bit value. Entries map hex value → `{group, key,
  label, aliases}` (e.g. `0x0004 → KC_A`, group `basic`).
- The spec is versioned as deltas: `keycodes_<ver>.hjson` (ranges) plus
  `keycodes_<ver>_<category>.hjson` (tables), merged in version order with
  `!delete!` markers for removals. Category files observed: basic, lighting,
  macro, quantum, magic, midi, audio, joystick, sequencer, steno,
  swap_hands, programmable_button, kb, user, connection.
- `extras/`: 72 international/layout alias files
  (`keycodes_<lang>_0.0.1.hjson`) — display-name aliases over basic codes
  (Belgian, BÉPO, German, …). Relevant to keymap-editor display UX, not the
  wire format.

### The ranges table (0.0.1 base, the load-bearing map)

Composed keycodes carry their parameters in the low bits of the range —
this is exactly what the hub's normalized keycode space must round-trip:

| Range (base/mask) | Define | Meaning |
|---|---|---|
| `0x0000/0x00FF` | `QK_BASIC` | plain HID keycodes (KC_NO, KC_TRNS, KC_A…) |
| `0x0100/0x1EFF` | `QK_MODS` | modifier+key combos |
| `0x2000/0x1FFF` | `QK_MOD_TAP` | hold-mod / tap-key |
| `0x4000/0x0FFF` | `QK_LAYER_TAP` | hold-layer / tap-key |
| `0x5000/0x01FF` | `QK_LAYER_MOD` | layer + modifier |
| `0x5200–0x52DF` (6×32) | `QK_TO`, `QK_MOMENTARY`, `QK_DEF_LAYER`, `QK_TOGGLE_LAYER`, `QK_ONE_SHOT_LAYER`, `QK_ONE_SHOT_MOD` | layer switching (≤32 layers) |
| `0x52C0/0x001F` | `QK_LAYER_TAP_TOGGLE` | TT(layer) |
| `0x5600/0x00FF` | `QK_SWAP_HANDS` | swap-hands actions |
| `0x5700/0x00FF` | `QK_TAP_DANCE` | tap dance slots |
| `0x7000–0x74FF` | `QK_MAGIC`, `QK_MIDI`, `QK_SEQUENCER`, `QK_JOYSTICK`, `QK_PROGRAMMABLE_BUTTON`, `QK_AUDIO`, `QK_STENO` | feature blocks |
| `0x7700/0x007F` | `QK_MACRO` | macro slots (128) |
| `0x7800/0x00FF` | `QK_LIGHTING` | lighting controls |
| `0x7C00/0x01FF` | `QK_QUANTUM` | quantum features |
| `0x7E00/0x00FF` → v0.0.2: `0x7E00/0x003F` | `QK_KB` | vendor keycodes |
| `0x7F00/0x00FF` → v0.0.2: `0x7E40/0x01BF` | `QK_USER` | user keycodes |
| `0x8000/0x7FFF` → v0.0.2: split `0x8000/0x3FFF` + `0xC000/0x3FFF` | `QK_UNICODE` → `QK_UNICODEMAP` + `QK_UNICODEMAP_PAIR` | unicode |

### Version deltas 0.0.1 → 0.0.8 (each is small and additive except 0.0.2)

- 0.0.1 — base space above. Counts: basic 218, quantum 71, macro 32,
  lighting 28 (RGB underglow `RGB_*` group), midi 144, magic, audio,
  joystick, sequencer, steno, swap_hands, programmable_button.
- 0.0.2 — re-carves `QK_KB`/`QK_USER`, splits unicode into
  UNICODEMAP/UNICODEMAP_PAIR; adds `KC_MISSION_CONTROL`/`KC_LAUNCHPAD`,
  magic rework (35), midi additions, sequencer table (34), kb/user slots.
- 0.0.3 — adds `QK_REPEAT_KEY`, `QK_ALT_REPEAT_KEY`.
- 0.0.4 — lighting: adds `led_matrix` (`QK_LED_MATRIX_*`) and `rgb_matrix`
  (`QK_RGB_MATRIX_*`) groups (33 entries) alongside legacy `RGB_*`.
- 0.0.5 — basic: 19 first-class mouse keycodes (`QK_MOUSE_*`, replacing the
  old mousekey block).
- 0.0.6 — adds `QK_PERSISTENT_DEF_LAYER` range, `QK_LAYER_LOCK`, and a
  `connection` category (15: `QK_OUTPUT_USB/2P4GHZ/BLUETOOTH`, BT profile
  keys) — wireless boards.
- 0.0.7 — adds `QK_COMMUNITY_MODULE` range (`0x77C0/0x003F`).
- 0.0.8 — lighting: LED/RGB matrix `FLAG_NEXT`/`FLAG_PREVIOUS` (4).

### Consequences for the hub (recorded, not yet designed)

- The QMK-family keycode is a *composed value*, not an enum: layer numbers,
  mod masks, and tap keycodes ride inside the 16 bits. The hub's normalized
  space must preserve composition (e.g. `LT(3, KC_A)`) rather than flatten
  to opaque numbers, or cross-board transfer of layered maps dies.
- The keycode spec version matters per firmware: a VIA/Vial device speaks
  the table its firmware was built from. The VIA-protocol-version →
  keycode-spec-version mapping is still to be extracted (VIA app source);
  pre-refactor (2022, pre-0.0.1) keycode values are a real legacy concern
  for older VIA protocol versions.
- Lighting keycodes are three distinct generations (`RGB_*` underglow,
  `QK_LED_MATRIX_*`, `QK_RGB_MATRIX_*`) — capability descriptors must not
  conflate them.
- `QK_KB`/`QK_USER` ranges are per-board custom keycodes with no portable
  meaning — exactly the "carried / adapted / dropped" transfer-report case.
