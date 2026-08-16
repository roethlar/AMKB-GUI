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
- [x] Vial macro encoding: byte format, event kinds, delays, limits —
      extracted from vial-gui source (see "Vial spoke" below).
- [x] Vial self-description payloads: layout JSON shape, matrix, encoder,
      handshake, protocol/version constants — extracted (see "Vial spoke"
      below); tap-dance/combo/key-override/QMK-settings and VialRGB
      surfaces recorded as command IDs, per-field detail deferred to H2.
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

## Vial spoke (extracted 2026-08-15)

Source: `vial-kb/vial-gui` commit `aef8222a2d0429a183b2ed692d5f9efcfd383f08`
(2026-05-25), shallow clone at `~/Dev/reference/vial-gui/` (reference
material, outside this repo; GPL-2.0-or-later — read for protocol facts,
no code reuse without a license decision). Files cited below are under
`src/main/python/`.

### Handshake and self-description (`protocol/keyboard_comm.py`,
`protocol/constants.py`)

- Transport: raw HID, 32-byte messages (`MSG_LEN = 32`, `util.py`).
- VIA protocol version: cmd `0x01` → big-endian u16. vial-gui supports VIA
  protocol **9** only (`SUPPORTED_VIA_PROTOCOL = [-1, 9]`).
- Vial commands ride VIA cmd `0xFE` (`CMD_VIA_VIAL_PREFIX`) + subcommand:
  - `0x00 GET_KEYBOARD_ID` → little-endian `<IQ`: u32 vial protocol
    version + u64 keyboard uid. Supported vial protocols **0–6**.
  - `0x01 GET_SIZE` → u32 LE payload size; `0x02 GET_DEFINITION` per
    32-byte block → concatenated payload is **XZ/LZMA-compressed JSON**.
  - Other subcommands (recorded, detail deferred): encoders `0x03/0x04`,
    unlock/lock `0x05–0x08`, QMK settings `0x09–0x0C`, dynamic entries
    `0x0D` (tap dance, combo, key override, alt-repeat-key get/set).
- Definition JSON fields vial-gui consumes: `matrix.rows/cols`,
  `layouts.keymap` (KLE-serialized layout), `layouts.labels`,
  `customKeycodes`, `vial.vibl`, `vial.midi`. Encoders are encoded inside
  the KLE keymap: a key whose `labels[4] == "e"` is an encoder,
  `labels[0] == "idx,direction"`. Layout options select alternate key
  geometry per the labels. This is the shape our Vial reader must parse —
  and validate as untrusted input per the settled ruling.
- Sideload path exists (user-supplied JSON instead of device fetch) —
  matches our planned definition-import lane.
- Version gates (protocol/constants.py): advanced macros ≥2, matrix
  tester ≥3, dynamic entries + QMK settings ≥4, 2-byte-keycode macros +
  key override ≥5.

### Macro encoding (`protocol/macro.py`, `macro/macro_action.py`)

- Buffer model (VIA cmds): `0x0C` macro count, `0x0D` buffer size,
  `0x0E/0x0F` read/write buffer in **28-byte chunks**
  (`BUFFER_FETCH_CHUNK`). One flat buffer holds all macros,
  **NUL-separated** (`b"\x00".join(macros) + b"\x00"`), so `0x00` can
  never appear inside an encoded macro.
- Macro body is a byte stream: plain bytes are UTF-8 text to type;
  escape sequences encode key events.
- v1 encoding (vial protocol < 2): `[code, keycode]` pairs with code
  tap=1 / down=2 / up=3; single-byte keycodes only; no delays.
- v2 encoding (vial protocol ≥ 2): every event starts with
  `SS_QMK_PREFIX = 0x01`, then:
  - `0x01/0x02/0x03` + u8 keycode — tap/down/up, basic keycodes.
  - `0x04` + 2 bytes — delay in ms, encoded `(b1 - 1) + (b2 - 1) * 255`
    (offset-by-one so neither byte is NUL; max ≈ 65 s).
  - `0x05/0x06/0x07` + u16 LE keycode (vial protocol ≥ 5) — tap/down/up
    for full 16-bit keycodes, with a NUL-avoidance quirk: a keycode
    `kc % 256 == 0` is stored as `0xFF00 | (kc >> 8)` and reversed on
    decode (`decode_keycode()` in qmk).
- Limits: total buffer size is device-reported; macro count is
  device-reported; a macro slot is `QK_MACRO` range (128 max in keycode
  space).

### Consequences for the hub (recorded, not yet designed)

- Vial macros are an *event stream* (text runs, key events, millisecond
  delays) — this matches the plan's "macros: normalized event streams"
  choice and gives the exact event vocabulary and byte budgets the hub's
  macro schema must round-trip for this spoke.
- The NUL-separator constraint and the `0xFF00` keycode quirk are
  wire-level details that belong in the Vial codec, not in the hub
  format; the hub stores clean events, the spoke owns the escaping.
- Self-description gives layout + matrix + encoders but **not** an LED
  position map; per-LED geometry for VialRGB comes from the lighting
  protocol surface (H6 territory), consistent with the plan's geometry
  seam.
- vial-gui pins VIA protocol 9 — our VIA spoke must confirm which
  protocol versions the VIA app itself accepts (older boards speak
  pre-9 protocols with different keycode tables; see QMK section note).
