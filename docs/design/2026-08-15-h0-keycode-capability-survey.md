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

- [ ] QMK keycode table: ranges, categories, and version deltas 0.0.1→0.0.8
      recorded; per-version table extracted from pinned commit.
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

Nothing below this line is authored yet; tables land as they are extracted,
each with its source commit/URL.
