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
- [x] VIA v3 definition schema: schema authority identified and the field
      set via-app actually consumes extracted (see "VIA spoke" below);
      full per-field bounds live in `@the-via/reader` and are deferred to
      the H3 importer slice, per the untrusted-input ruling.
- [x] VIA dynamic-keymap command set: keymap/macro read-write commands,
      per-protocol-version gates, and the protocol-to-keycode-spec
      mapping extracted (see "VIA spoke" below).
- [x] AM spoke inventory: what `FamilySpec` + `_LAYOUTS` + existing codecs
      already express, in the same vocabulary as the above (see "AM spoke"
      below).
- [x] Capability surface comparison: lighting, macros, layers per family
      (see "Capability surface comparison" below) — the raw material for
      the hub's capability descriptor.
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

## AM spoke (extracted 2026-08-15)

Source: this repository, `am_configurator/` — `device_mapping.py`
(`FamilySpec`, `_LAYOUTS`), `vial_keymap.py`, `vial_macros.py`,
`macros.py`, `macro_text.py`. Line references are current as of this
survey's commit.

### Families and limits (`FamilySpec`, one row per family)

| Family | Transport | Frame cap | Macro model | Keys/layer |
|---|---|---|---|---|
| CB (Cyberboard) | serial | 80 | 32 tracks, 200 events total | 200 |
| ALICE | serial | 186 | 32 tracks, 200 events total | 200 |
| 80 (Relic; probes as `AM21`) | serial | 200 | 32 tracks, 200 events total | 200 |
| NEON | HID (Vial) | 256 | 16 slots, 6677-**byte** buffer | 90 (6×15) |

- The two macro capacity models are *incommensurable* and `FamilySpec`
  already records both (`macro_events` vs `macro_buffer_bytes`, 0 = "not
  expressed that way") — the module comment states there is no correct
  events↔bytes conversion. The hub's macro budget metadata must carry
  both vocabularies, exactly as the plan's "per-ecosystem byte-budget
  metadata" line says.
- NEON numbers are measured on the owner's board (read-only VIA reads,
  2026-07-25), not vendor claims.

### LED geometry (`_LAYOUTS` — separate from `FamilySpec`, as the plan
notes)

Per-family authored tracks, each `{size (w,h), placement map, pixels}`:
CB `keyframes` 15×6/90 + `frames` 40×5/200; ALICE `keyframes` 16×5/90
(with copied pixels); NEON `axial` 19×6/89 + `head` 46×5/230 (row-major,
no map needed); 80 `keyframes` 18×7/90 + `spotlight_frames` 18×7/24.
Shared fallback colour counts for unauthored tracks: frames 200,
keyframes 90, spotlight_frames 24. Identity quirks the hub must keep:
`AM21`→family `80` (wire format stores `80`), `CB*`→`CB`,
`NEON`/`NEON80`/`AM NEON 80`→`NEON`.

### Keycode representation (`vial_keymap.py`)

- The app's own key identity is `#` + 8 hex digits = HID **page +
  usage** (page `0x07` basic keyboard usages; `#00000000` = no key =
  QMK `KC_NO`).
- Translation to/from QMK is explicitly **not symmetric**; the proven
  fix is a passthrough page `0xFF` carrying an untranslatable 16-bit QMK
  keycode verbatim (owner's board ships `0x5101`). One representation
  per keycode, read-back stable. This is a working in-repo prototype of
  the hub's "carried vs adapted" contract at single-key granularity.
- `to_qmk`/`from_qmk` already take a `vial_protocol` parameter (macro
  keycode base shifts by protocol version) — confirming the QMK-section
  finding that spec-version mapping is load-bearing.
- Keymap I/O implemented: layer count read, buffer read/write,
  encode/decode layers, and the Vial unlock flow
  (`unlock_status`/`ensure_unlocked`, typed-confirmation gated upstream).

### Macro codecs (two, matching the two capacity models)

- `vial_macros.py`: Vial v2 event-stream codec — same wire format the
  Vial section documents (SS_QMK_PREFIX events, offset-by-one delay
  encoding, NUL separation), plus slot tables and byte-capacity
  enforcement (`MacroCapacity`, `MacroCapacityError`).
- `macros.py` + `macro_text.py`: AM serial frame codec — event-count
  model, text compiled to US-layout key events with natural delays.
- Consequence: the hub's normalized macro event vocabulary already has
  two independent in-repo consumers/producers; their shared event kinds
  (tap/down/up/text/delay) are the intersection to normalize, budgets
  stay per-spoke.

## VIA spoke (extracted 2026-08-15)

Source: `the-via/app` commit `e21976de7348dad918e85d1a7903457d91c9ec0b`
(2026-08-15), shallow clone at `~/Dev/reference/via-app/` (reference
material, outside this repo; ~16M). Protocol facts only, no code reuse.

### Transport and command set (`src/utils/keyboard-api.ts`)

- Raw HID, 32-byte reports; `COMMAND_START = 0x00` is the HID report ID.
- `enum APICommand` `0x01`-`0x16`: `GET_PROTOCOL_VERSION 0x01`,
  `GET/SET_KEYBOARD_VALUE 0x02/0x03`,
  `DYNAMIC_KEYMAP_GET/SET_KEYCODE 0x04/0x05`,
  custom-menu channel `0x06`-`0x09` (which re-carve the deprecated
  `BACKLIGHT_CONFIG_*` command IDs `0x07`-`0x09` from the v2 lighting
  era), `EEPROM_RESET 0x0a`, `BOOTLOADER_JUMP 0x0b`,
  `DYNAMIC_KEYMAP_MACRO_*` `0x0c`-`0x10` (count, buffer size, get/set
  buffer, reset), `GET_LAYER_COUNT 0x11`, keymap
  `GET/SET_BUFFER 0x12/0x13`, encoders `0x14/0x15`,
  `UI_SYNC_REQUEST 0x16`.
- Keymap/macro buffers move in max-28-byte chunks
  (`DYNAMIC_KEYMAP_GET_BUFFER` caps data length at 28) — the same
  28-byte ceiling as Vial's `BUFFER_FETCH_CHUNK`.

### Protocol-version gates (load-bearing for the hub)

Constants: `PROTOCOL_ALPHA = 7`, `PROTOCOL_BETA = 8`,
`PROTOCOL_GAMMA = 9`; live gates in the app go higher:

- `protocol < 8`: no macros at all (`macrosSlice` returns early).
- `>= 8`: fast raw-matrix read via keymap buffer commands (alpha-7
  boards fall back to per-key `getKey` reads).
- `< 11`: v2 definition required, legacy lighting path
  (`updateLightingData`, deprecated `BACKLIGHT_CONFIG_*` values).
- `>= 11`: v3 definition required (`requiredDefinitionVersion` flips at
  exactly 11), custom-menu/`UI_SYNC` data path, macro delays supported
  (`isDelaySupported = protocol >= 11`), v11 macro codec.
- `>= 13`: board reports its keycode spec version
  (`GET_KEYBOARD_VALUE` sub-command `KEYCODES_VERSION = 0x06`,
  4-byte BCD; app pins `SUPPORTED_KEYCODES_VERSION = 0x00000008`).
  This closes the QMK-section open item "VIA-protocol-version to
  keycode-spec-version mapping": pre-13 boards imply the spec by
  protocol version, 13+ boards state it, and 0.0.8 is exactly the
  latest delta table already extracted above. Keycode lookup is
  `getBasicKeyDict(protocol, keycodesVersion)` — two-axis, confirming
  the hub must carry both numbers per VIA endpoint.

### Macro codec (v11, `src/utils/macro-api/`)

- Byte format is the same SS_ family as QMK/Vial: prefix `0x01`, then
  `Tap=1 / Down=2 / Up=3 / Delay=4`; macro terminator `0x00`.
- Delay wire encoding differs from Vial: ASCII decimal digits
  terminated by `'|'` (`DelayTerminator = 124`), not Vial's
  offset-by-one two-byte pair. Same event vocabulary, third distinct
  wire dialect — reinforces the plan's "hub stores clean events,
  spokes own the escaping" rule.

### Definition schema (v2/v3)

- Schema authority is the `@the-via/reader` package (`^1.14.4`), not
  vendored here; the definitions database is the `the-via/keyboards`
  repo behind usevia.app (settled: user-imported definitions first,
  catalog download deferred).
- Fields via-app actually consumes from a definition (usage-derived):
  `vendorProductId`, `name`, `matrix.rows/cols`, `layouts.labels` +
  KLE `keymap`, `menus`, `keycodes`, `customKeycodes`. These are the
  fields the hub's VIA reader must validate as untrusted input;
  per-field bounds come from `@the-via/reader` at the H3 importer
  slice, not invented here.

## Capability surface comparison (assembled 2026-08-15)

The raw material for the hub's capability descriptor. Every cell is
sourced from a section above; nothing here is aspirational.

### Keymap

| Family | Keymap surface | Layer model |
|---|---|---|
| AM (CB/80/ALICE/NEON) | Vial keymap I/O already in-repo (`vial_keymap.py`: layer-count read, buffer read/write, unlock flow) | device-reported layer count; keys/layer 200 (serial), 90 (NEON) |
| Vial | full dynamic keymap, VIA cmds + `0xFE` Vial subcommands | device-reported; QMK ≤32-layer keycode space |
| VIA | full dynamic keymap (`0x04/0x05`, buffers `0x12/0x13`), encoders `0x14/0x15` | `GET_LAYER_COUNT 0x11`; QMK ≤32-layer keycode space |
| QMK bare (no VIA) | none at runtime — keymap compiled into firmware; out per the no-flash rule | n/a |

Keycode space is QMK's versioned 16-bit composed space for Vial, VIA,
and (via the in-repo `0xFF` passthrough page) AM. The hub must carry
the spec version per endpoint: Vial implies it via protocol; VIA ≥13
states it, pre-13 implies it; AM uses the passthrough identity.

### Macros

| Family | Budget model | Wire dialect | Event kinds |
|---|---|---|---|
| AM serial | event counts (32 tracks / 200 events) | AM serial frames | tap/down/up/text/delay (text → US-layout events) |
| AM NEON | byte buffer (16 slots / 6677 B) | Vial v2 | same |
| Vial | byte buffer, device-reported; NUL-separated, 28 B chunks | v1 (no delays) / v2 (offset-by-one delay bytes) | tap/down/up/text/delay |
| VIA | byte buffer via `DYNAMIC_KEYMAP_MACRO_*`, 28 B chunks; macros ≥8, delays ≥11 | SS_ prefix + ASCII delay terminated `'\|'` | tap/down/up/text/delay |

One shared event vocabulary, three wire dialects, two incommensurable
budget models (events vs bytes) — the hub stores clean events and
carries both budget vocabularies per endpoint, as already recorded.

### Lighting

| Family | Static/effects | Per-key | Streaming/animation |
|---|---|---|---|
| AM | app-driven | full pixel art | full custom animation, frame caps 80/200/186/256 |
| Vial + VialRGB | effect/color/speed | per-key direct | VialRGB raw-HID per-LED streaming (host script model) |
| VIA <11 | legacy `BACKLIGHT_CONFIG_*` values (brightness/effect/speed/color) | no | no |
| VIA ≥11 | whatever the definition's `menus` declare (custom-value channels) | menu-dependent | no |
| QMK bare | keycode-level toggles only (three lighting keycode generations); no host protocol | no | no |

Lighting capability is therefore *not* a family constant for VIA — it
is definition-derived, which the capability-honesty rule already
anticipates: the descriptor is filled per endpoint at read time, never
assumed per family.
