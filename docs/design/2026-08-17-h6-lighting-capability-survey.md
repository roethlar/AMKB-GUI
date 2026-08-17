# H6 lighting capability and protocol survey

Status: pinned implementation evidence for OpenKeeb H6a–H6e, extracted
2026-08-17. This document records protocol facts only. It does not make GPL
source or effect-name tables part of this MIT repository.

## Source pins and license boundary

The evidence set is fixed at these commits:

- `vial-kb/vial-gui` `aef8222a2d0429a183b2ed692d5f9efcfd383f08`
  (GPL-2.0-or-later);
- `vial-kb/vial-qmk` `dd43959ae5c08d8a28d38a1acf7b04e86b14a344`
  (GPL-2.0-or-later);
- `Vil4/vial_rgb_direct_control`
  `b139cb2ef06f7cb0dd9ef0cc466d22405ef55799` (MIT);
- `the-via/app` `38da806d9fce44940e33ce7f796226089f815953`
  (GPL-3.0);
- `the-via/reader` `c26009992a7a2e9776720ebf5644a50f8e92c7a5`
  (GPL-3.0);
- `the-via/keyboards` `cc2d06a238661caa005125e0d6248b54781721ab`
  (definition data under that repository's terms);
- `qmk/qmk_firmware` `96c3e85e59b1acfa0d43c32a224ba2b26123fe3d`
  (GPL-2.0-or-later).

OpenKeeb independently implements packet shapes, bounds, and
device/definition-returned values. It does not copy the Vial/VIA/QMK effect
tables. Consequently, legacy built-in capabilities give semantic names only
to the independently verified unambiguous `off`, `solid`, and `breathing`
cases; other effect IDs remain opaque unless returned by the keyboard or its
definition. A broader copied table requires a separate license decision and
notices.

## Shared VIA raw-HID lighting envelope

Sources:

- Vial GUI `src/main/python/protocol/constants.py` and
  `src/main/python/protocol/keyboard_comm.py`;
- VIA app `src/utils/keyboard-api.ts`;
- QMK `quantum/via.h` and `quantum/via.c`;
- Vial QMK `quantum/via.h` and `quantum/via.c`.

All surveyed lighting routes use the 32-byte raw-HID report envelope. The
top-level command IDs are SET `0x07`, GET `0x08`, and SAVE `0x09`.

Legacy VIA/Vial lighting uses one-byte value IDs:

| Control | Value ID | Native payload |
|---|---:|---|
| QMK backlight brightness | `0x09` | one byte |
| QMK backlight effect | `0x0A` | one byte |
| QMK RGBLIGHT brightness | `0x80` | one byte |
| QMK RGBLIGHT effect | `0x81` | one byte |
| QMK RGBLIGHT speed | `0x82` | one byte |
| QMK RGBLIGHT color | `0x83` | hue, saturation bytes |

Vial's embedded definition recognizes only `qmk_backlight`, `qmk_rgblight`,
`qmk_backlight_rgblight`, and `vialrgb` as lighting generation evidence. See
Vial GUI `src/main/python/protocol/dummy_keyboard.py` and
`src/main/python/protocol/keyboard_comm.py`. Unknown definition values do not
authorize a GET or SET.

## VialRGB discovery and direct mode

Sources:

- Vial QMK `quantum/vial.c`, `quantum/vialrgb.h`,
  `quantum/vialrgb.c`, and `quantum/rgb_matrix/animations/vialrgb_direct_anim.h`;
- Vial GUI `src/main/python/protocol/constants.py` and
  `src/main/python/protocol/keyboard_comm.py`;
- MIT reference `vialrgb_demo.py` in `Vil4/vial_rgb_direct_control`.

VialRGB requires four independent proofs before OpenKeeb exposes a surface:

1. Vial protocol version is at least 4.
2. Byte 12 of `FE 00` keyboard-ID response has bit 0 set. Vial QMK sets that
   byte when `VIALRGB_ENABLE` is built.
3. The embedded definition says `lighting: vialrgb`.
4. GET_INFO reports protocol version exactly 1.

VialRGB value/subcommand IDs are:

| Operation | ID | Response or request after the ID |
|---|---:|---|
| GET_INFO | `0x40` | little-endian protocol version, maximum brightness |
| GET_MODE / SET_MODE | `0x41` | little-endian effect ID, speed, hue, saturation, value |
| GET_SUPPORTED | `0x42` | request: little-endian ID lower bound; response: paged little-endian IDs terminated by `0xFFFF` |
| GET_NUMBER_LEDS | `0x43` | little-endian LED count |
| GET_LED_INFO | `0x44` | request: little-endian LED index; response: x, y, flags, row, column |
| DIRECT_FASTSET | `0x42` under SET | little-endian first LED, count, then HSV triples |

Effect ID 1 is direct mode. It is volatile ownership, not a persistable
hardware effect. Direct mode must be present in the device-returned supported
effect IDs before LED count or LED metadata is requested. LED count is bounded
to 1..1024 before allocation. `0xFF` row or column means an auxiliary LED;
otherwise the row/column may be linked to a canonical hub key. Coordinates,
flags, row/column, and wire LED indexes are ephemeral endpoint evidence and do
not enter a hub file.

DIRECT_FASTSET has three bytes of request metadata after the two-byte
top-level/value prefix, leaving 27 bytes in a 32-byte report: at most nine HSV
pixels per report. H6 uses an application ceiling of **30 HID reports per
second** for volatile streaming. This is a conservative OpenKeeb scheduling
limit, not a firmware guarantee. Frame duration and required chunk count may
lower the effective frame rate. The worker never builds a backlog.

## VIA version-2 definitions

Sources:

- VIA reader `src/types.v2.ts` and `src/lighting-presets.ts`;
- VIA app `src/store/lightingSlice.ts` and
  `src/components/panes/configure-panes/submenus/lighting/`.

Version-2 definitions may select `qmk_backlight`, `qmk_rgblight`, or
`qmk_backlight_rgblight`, or provide a lighting object with explicit
`supportedLightingValues`, `effects`, and `underglowEffects`. OpenKeeb executes
only the value IDs in the shared table above and only effect IDs supplied by
that definition. Vendor-specific lighting values remain preserved definition
data but inert.

The built-in preset tables contain more effect labels than OpenKeeb imports.
For string presets, OpenKeeb exposes the independently established controls
and the minimal unambiguous semantic IDs; a current opaque device effect may
be added so an exact same-device round trip remains possible.

## VIA protocol-11 common menus

Sources:

- VIA reader `src/common-menus/qmk_backlight.ts`,
  `qmk_rgblight.ts`, `qmk_backlight_rgblight.ts`,
  `qmk_rgb_matrix.ts`, `src/common-menus/index.ts`, and `src/validate.ts`;
- VIA reader `src/menu-types.ts` and `src/types.v3.ts`;
- VIA app `src/store/menusSlice.ts` and `src/utils/keyboard-api.ts`;
- QMK `quantum/via.h` and `quantum/via.c`.

For protocol 11 and newer, built-in common menus use the same top-level
SET/GET/SAVE commands as other custom menus, but their channel and command
contracts are fixed:

| Surface | Channel | Brightness | Effect | Speed | Color |
|---|---:|---:|---:|---:|---:|
| QMK backlight | 1 | 1 | 2 | — | — |
| QMK RGBLIGHT | 2 | 1 | 2 | 3 | 4 |
| QMK RGB matrix | 3 | 1 | 2 | 3 | 4 |

Range controls carry definition-supplied integer bounds. Color carries hue
and saturation bytes; brightness/value is a separate native control. Effect
dropdowns carry either positional IDs or explicit `[label, id]` pairs.
OpenKeeb recognizes only `qmk_backlight`, `qmk_rgblight`,
`qmk_backlight_rgblight`, and `qmk_rgb_matrix`, and only inline controls whose
identifier, type, channel, command, and bounds match those closed contracts.
Arbitrary custom menus, conditions, labels, and vendor channels are never an
execution language.

Each changed channel is saved once with SAVE plus that exact channel. Legacy
version-2 lighting uses one channel-less SAVE.

## VIA per-key RGB and geometry

Sources:

- VIA reader `src/kle-parser.ts` and `src/types.common.ts`;
- VIA app `src/utils/keyboard-api.ts`, `src/store/menusSlice.ts`, and
  `src/utils/use-color-painter.tsx`;
- representative pinned definitions under `the-via/keyboards/v3/`.

KLE label metadata `li` is parsed as an LED index. Only keys active under the
selected layout options participate. Negative, duplicate, out-of-range, and
inactive LED indexes are rejected before HID opens.

Protocol 11 per-key RGB uses channel 0, command 1. GET sends LED index and
count; SET sends LED index, count, hue, and saturation; SAVE commits channel
0. The definition-backed mapping is ephemeral. Hub persistent state is keyed
by canonical `K_*` identity and retains two native HSV channels, while the
wire index and KLE coordinates stay outside the hub document. A VIA definition
without valid `li` evidence can still expose global controls but cannot expose
the per-key painter.

## Hub consequences

- Hub schema version 2 stores a bounded list of independent surfaces, native
  control ranges, current/authored state by surface ID, and animation
  `surface_id` plus stable `pixel_ids`.
- Unknown generations, effect IDs, controls, common menus, and stream protocol
  versions do not become capabilities.
- Range transfer uses source and target native bounds and reports adaptation;
  it never stores a second normalized value.
- Cross-generation effect transfer uses only unambiguous semantic evidence.
- Persistent plans are pure closed command records. HID execution remains
  behind endpoint identity, typed confirmation, accepted-change accounting,
  SAVE, and exact read-back.
- Volatile VialRGB streaming has a separate lifecycle and never calls SAVE.
