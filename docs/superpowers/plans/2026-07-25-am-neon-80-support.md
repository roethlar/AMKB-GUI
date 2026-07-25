# AM Neon 80 Support

Status: draft, awaiting owner approval. No implementation may begin until the
owner approves this plan and the approved wording is recorded in this line.

Governing decisions: `.agents/decisions.md`, both 2026-07-25 entries
("AM Neon 80 supported at full parity or not at all" and "AM Neon 80 protocol
sources and GPL relicensing"). Those decisions are authoritative; this plan
implements them and must not restate scope they settle differently.

Revision history: revised 2026-07-25 to close five findings from the
`openreview codex` pass recorded in `.agents/review/outcomes.md`. The material
changes were adding the integration spine (N2), replacing an impossible lossless
keycode requirement with an explicit unsupported-code policy (N6), binding the
hardware-write gate to validated model identity rather than VID/PID (N3), and
making relicensing an unconditional first task with a guard (N1).

## Problem

The application supports three Angry Miao families — CyberBoard (`CB`),
Relic 80 (`AM21`, LED model `80`), and AFA (`ALICE`) — all reached through one
proprietary transport: 64-byte CDC-serial frames with a trailing CRC-8
(`am_configurator/protocol.py`), discovered by opening candidate serial ports
and asking each device for its product-ID string (`am_configurator/device.py`).

The AM Neon 80 shares none of that. It is a QMK/Vial device reached over raw
HID. Adding it means a second transport and a second protocol dialect beneath
the existing lighting, keymap, macro, and profile-store surfaces.

Critically, the application is not transport-neutral today. Every device route
in `am_configurator/server.py` is keyed on a serial port string:
`/api/devices` (line 1356) calls `device.list_devices()`; `/api/device/read`,
`/api/device/write`, and `/api/device/verify` (lines 1478-1482) reach
`_read_device` (1995) and `_write_device` (2032), and `_write_request` (2063)
raises `"A serial port is required."` when none is supplied. A new transport
therefore cannot be added beside the old one — the seam has to be built first,
or the new modules are unreachable from the GUI.

## Established facts

These were established by reading published Angry Miao sources and by read-only
USB enumeration of the owner's device. Nothing was written to the keyboard. A
cold agent should treat this section as given and need not re-derive it, but
must confirm the geometry against hardware before N9 is called complete.

### Device identity

- USB `0x05AC:0x024F` (vendor ID is Apple's, borrowed so macOS treats the board
  as a native keyboard; it is not an Apple device).
- Serial-number string carries a `vial:` prefix; the owner's unit reports
  `vial:f64c2b3c`. The suffix is a per-board UID and must not be matched on.
- **This pair identifies far less than it appears to.** `0x05AC:0x024F` is
  reused by many unrelated keyboards, and a `vial:` prefix marks any Vial board
  whatsoever. Neither, alone or together, establishes that the connected device
  is a Neon 80. N3 defines the identity check that does.
- Interfaces: keyboard (usage page `0x01`, usage `0x06`), mouse (`0x01`/`0x02`),
  and raw HID (usage page `0xFF60`, usage `0x61`).
- No CDC-serial port is exposed. `device.candidate_ports()` can never enumerate
  this board, and `probe()` can never identify it.

### Upstream sources

Both are public. The 2026-07-25 relicensing decision permits deriving from
either, including transcribing tables from the GPL firmware.

`AngryMiao/neon_80_embedded` — keyboard firmware, **GPL-2.0**:

| File | Contents needed |
|---|---|
| `led_drv.h` | Zone geometry constants |
| `app_flash.h` | Slot layout, frame ceiling, channel enum |
| `led.c` | LED index maps: `map[6][15]` (~line 111), `real_map[89]` (~140), `h_map[5][46]` (~565), `s_map[70]` (~656); `gamma_brightness` (~707); `key_led_lightness_code` (~733) |
| `info.json` | QMK matrix and physical layout. Contains a trailing comma and is not strict JSON — do not feed it to `json.loads` without repair |

`AngryMiao/neon80_driver` — reference web configurator, **Apache-2.0**:

| File | Contents needed |
|---|---|
| `src/804/utils/keyboard-api.ts` | `setRGB` packet construction, VIA command enum, `calculateSumCheck` |
| `src/804/light-library/device-push.ts` | Channel walk, packetization, side-zone derivation |
| `src/804/light-library/payload.ts` | Frame-length validation: matrix 230, axial 89 |

### Zones, slots, and capacity

Firmware `app_flash.h` and the driver's `setRGB` docstring agree exactly; that
agreement is the basis for trusting both.

| `cmd` byte | Firmware enum | Zone | LEDs per frame | Flash bytes per frame |
|---|---|---|---|---|
| `0x01`–`0x03` | `CMD_KEY_LED1..3` | axial (per-switch) | 89 | 512 |
| `0x04`–`0x06` | `CMD_HEAD_LED1..3` | head matrix, 46x5 | 230 | 1024 |
| `0x07`–`0x09` | `CMD_SIDE_LED1..3` | side | 70 | 256 |
| `0x0A`–`0x0D` | `CMD_DEFAT_HEAD1/2`, `CMD_DEFAT_SIDE1/2` | factory defaults | | |
| `0x0E` | `CMD_OTHER_CMD` | control; driver sends `F0 0E 01` | | |

Three user slots per zone. `USER_FRAME_MAX` is **256 frames per slot**.

Axial LEDs sit on a 15x6 grid (`KEY_RGB_LED_X_NUM` 15, `KEY_RGB_LED_Y_NUM` 6 =
90 cells) with `AM_LED_NUM` 89 populated, so exactly one cell is unpopulated —
directly analogous to the `-1` holes in `_CB_KEY_MAP` and `_RELIC_KEY_MAP` in
`am_configurator/device_mapping.py`.

### Vendor lighting command `0xF0`

32-byte packet:

| Byte | Field | Notes |
|---|---|---|
| `[0]` | `0xF0` | command |
| `[1]` | `cmd` | channel from the table above |
| `[2]` | `frameIndex` | 0-255 |
| `[3]` | `packIndex` | packet within frame; **`255` marks the final packet of the final frame** |
| `[4]` | `lightness` | brightness |
| `[5]` | `timeInterval` | playback interval |
| `[6]` | `length` | RGB bytes in this packet, at most 24 |
| `[7]`–`[30]` | RGB data | up to 8 LEDs, 3 bytes each |
| `[31]` | checksum | `sum(bytes[0..30]) & 0xFF` |

The driver transmits `sendPacket.slice(1)` under HID command `0xF0`, so byte
`[0]` is the command selector and bytes `[1..31]` are the payload. Reply is
`0x01` for success and `0xFF` for failure, read from index 7 of the response.

Packetization: 8 LEDs per packet, so 89 axial LEDs produce 12 packets (the last
carrying 1 LED) and 230 head LEDs produce 29 packets (the last carrying 6).

### Side-zone derivation

The driver never authors side frames directly; it derives them from head matrix
frames. Reproduce exactly:

1. Treat the head frame as 5 rows x 46 columns, row-major.
2. Nearest-neighbour downsample to 4 rows x 21 columns using
   `srcX = floor(x * 46 / 21)` and `srcY = floor(y * 5 / 4)`.
3. Walking `y` outer, `x` inner, **skip** positions where
   `y == 0 and 4 < x < 16`, or `y == 1 and x in {6, 7}`, or `y == 3 and x == 6`.

84 candidates minus 14 skipped yields exactly 70, matching `SIDE_LED_NUM`. Any
implementation producing a different count is wrong.

### Vial keymap and macro commands

Standard VIA/Vial raw-HID commands, distinct from the `0xF0` vendor channel:

| Command | ID |
|---|---|
| `GET_PROTOCOL_VERSION` | `0x01` |
| `DYNAMIC_KEYMAP_GET_KEYCODE` / `SET_KEYCODE` | `0x04` / `0x05` |
| `DYNAMIC_KEYMAP_MACRO_GET_COUNT` | `0x0C` |
| `DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE` | `0x0D` |
| `DYNAMIC_KEYMAP_MACRO_GET_BUFFER` / `SET_BUFFER` | `0x0E` / `0x0F` |
| `DYNAMIC_KEYMAP_GET_LAYER_COUNT` | `0x11` |
| `DYNAMIC_KEYMAP_GET_BUFFER` / `SET_BUFFER` | `0x12` / `0x13` |

Note that `0x0E` is both a top-level VIA command (macro buffer read) and the
second byte of the vendor control packet `F0 0E 01`. They do not collide because
the vendor byte is nested under `0xF0`; keep the two namespaces separate in code
so a future reader does not conflate them.

### Keycode width mismatch

QMK keycodes are **16-bit**. The application's keymap surface is **32-bit**:
`am_configurator/web/app.js:1091` accepts any `#` followed by exactly eight
hexadecimal digits, `app.js:1085` exposes that raw field directly, and
`app.js:1084` advertises "Raw codes remain available for lossless passthrough".
The Angry Miao palette includes vendor usage pages with no QMK equivalent.

A lossless round-trip of every code the UI can emit is therefore **impossible**
on a Vial device, and any plan requiring one cannot be satisfied. N6 defines the
policy that replaces it.

## Non-goals

- No LED frame read-back. No supported family has it; `am_configurator/reader.py`
  records that the AM serial families expose no LED-frame read path either.
  Neon 80 lacking one is parity, not a gap.
- No custom or modified firmware, and no flashing.
- No Vial feature beyond keymap and macros. Combos, tap dance, key overrides,
  and QMK settings are outside parity because no existing family has them.
- No behavioral change to the AM serial families. N2 refactors the seam they sit
  behind; their observable behavior must be identical before and after.
- No automated hardware writes. Device writes stay manual, GUI-initiated, and
  gated on device/model matching plus typed confirmation.

## Tasks

Land each task as its own commit, in the order given. Each task states its own
red-proof obligation; a test that passes with its change reverted is vacuous and
must be replaced.

### N1. License and notices prerequisite

Unconditionally first. N4 commits tables transcribed from GPL-2.0 firmware, and
every commit from that point carries GPL-derived material. Because this branch
is intended to be published, an intermediate commit that advertises GPL-derived
tables under MIT metadata is materially incorrect licensing on a public commit —
so the relicensing lands **before** the material does, not merely before a build.

- `LICENSE` becomes GPL-2.0-or-later. Retain the existing MIT text (Copyright
  2026 GeneralD, covering the `cyberboard-cli`-derived protocol layer) as a
  third-party notice; it must not be deleted or altered.
- `pyproject.toml` line 11: `license = "MIT"` becomes `GPL-2.0-or-later`.
- `THIRD_PARTY_NOTICES` gains entries for `AngryMiao/neon_80_embedded`
  (GPL-2.0) and `AngryMiao/neon80_driver` (Apache-2.0).
- Update `tests/test_packaging.py`, which guards license files in every artifact
  under release-hygiene R1, plus the sdist allowlist if later tasks add a new
  top-level path.
- `README.md` states where corresponding source lives, satisfying the GPL
  source-offer obligation for distributed binaries.
- FFmpeg's LGPL bundling and its attestation system are unaffected; do not touch
  them.

Red-proof: a guard test that fails whenever GPL-derived material is present in
the tree while `LICENSE` or the `pyproject.toml` license field still claims MIT.
It must fail if the license field is reverted to MIT with N4's tables present.

### N2. Transport-neutral device handle and route dispatch

The integration spine. Built **before** any HID code exists, with the serial
transport as its only implementation, so the refactor is provable in isolation:
the existing suite must pass unchanged, and no observable behavior may move.

- Introduce a device handle carrying transport kind plus transport-specific
  address, replacing the bare `port` string threaded through the device routes.
  Existing serial devices produce a serial-kind handle wrapping the same port.
- Dispatch discovery, read, write, and verify on the handle's transport:
  `/api/devices` (`server.py:1356`), `/api/device/read`, `/api/device/write`,
  and `/api/device/verify` (`server.py:1478-1482`), reaching `_read_device`
  (1995) and `_write_device` (2032).
- `_write_request` (2063) currently raises `"A serial port is required."` —
  generalize the requirement and its message to a device handle.
- `_validated_write_target` (2074) keeps its exact contract: probe, confirm the
  device is a supported keyboard, match the config's `product_id` against the
  device, and require typed confirmation equal to the product ID. Only the
  probe becomes transport-dispatched. **The gate does not weaken here**; N3
  strengthens it for HID.
- Update the browser device surface to carry handles rather than port strings.

Red-proof: the existing device-route tests pass unchanged against the refactor,
plus a dispatch test proving an unknown transport kind is rejected with a typed
error rather than silently treated as serial.

### N3. Raw HID transport and Neon 80 identity

New module `am_configurator/hid_transport.py`. Do not extend `protocol.py` or
`device.py`; those own the serial dialect and stay unchanged.

- Add `hidapi` to `pyproject.toml` runtime dependencies and regenerate the lock.
- Enumerate HID devices, selecting the interface whose usage page is `0xFF60`
  and usage is `0x61`.
- **Identity is a three-stage gate, and only the last one authorizes a write.**
  VID/PID `0x05AC:0x024F` narrows the candidate set; a `vial:` serial prefix
  confirms Vial firmware; neither establishes the model. Before a device is
  exposed as write-capable, fetch and validate the Vial keyboard definition and
  confirm it identifies a Neon 80. A Vial board that is not a Neon 80 is
  enumerated as unsupported, never as a writable target.
- Bind the typed confirmation from `_validated_write_target` to the validated
  identity and to an immutable HID path identity captured at validation time, so
  a device swapped between confirmation and write cannot inherit the approval.
- Provide open, write, read-with-timeout, and close, with exclusive access where
  the platform supports it.
- Surface typed, pathless errors for absent, busy, or permission-denied devices.
  Linux permission failure is the common case and its message must name the udev
  remedy.
- Ship the udev rule as packaging data and document it. Without it, Linux
  requires root and discovery fails for ordinary users.

Red-proof: a decoy test with a stand-in HID backend offering a device at the
same VID/PID **and** a valid `vial:` serial prefix, but a keyboard definition
that is not a Neon 80. The decoy must be rejected as a write target. Removing
the definition check must make the test fail. A second test must prove a changed
HID path identity invalidates a prior confirmation.

### N4. Device family registration

Extend `am_configurator/device_mapping.py`. **This is the first commit carrying
GPL-derived material; N1 must already have landed.**

- Add LED model `NEON` with `MODEL_FRAME_CAPS["NEON"] = 256`.
- Add three `_LAYOUTS["NEON"]` entries: `keyframes` (15x6 source grid, 89
  outputs), `frames` (46x5, 230 outputs), and the derived side zone (70).
- Transcribe `real_map[89]`, `h_map[5][46]`, and `s_map[70]` from firmware
  `led.c` into the module's existing tuple-of-int convention, using `-1` for the
  single unpopulated axial cell. Record the source file and line in a comment,
  as the existing maps do.
- Extend `led_model()` to return `NEON` for the Neon 80 product identity.

Red-proof: a mapping test asserting exact output counts per zone (89 / 230 / 70)
and that the derived side zone matches the driver's downsample-and-skip rule for
a known head frame. Removing the skip rule must make it fail.

### N5. Lighting push over `0xF0`

New module `am_configurator/neon_lighting.py`, reached through the N2 handle.

- Build 32-byte packets per the table above, including the checksum.
- Walk frames and packets, setting `packIndex` to `255` on the final packet of
  the final frame and to the packet index otherwise.
- Honour the existing operation deadline and cancellation predicate the way
  `procedural_generation.py` does, and publish throttled progress.
- Verify each reply: `0x01` continues, `0xFF` aborts with a typed error naming
  the zone and frame. A partial upload must not be reported as success.
- Reject frame counts above 256 and per-frame LED counts that do not match the
  zone before any packet is sent.
- Wire the Lighting Apply path so a Neon target is selectable and applies
  through this module.

Red-proof: a transport-level test capturing every emitted packet for a
three-frame axial animation, asserting exact bytes including checksums and the
`255` terminator. Removing the terminator rule must make it fail.

### N6. Vial keymap and the unsupported-code policy

New module `am_configurator/vial_keymap.py`, reached through the N2 handle.

The keycode width mismatch above makes a universal lossless round-trip
impossible. The policy that replaces it:

- Translation between QMK 16-bit keycodes and the application's `#MMPPUUUU`
  representation must be **injective in the QMK-to-application direction**, so
  read-back from a board is stable and repeatable.
- A code the UI can emit that has **no** QMK representation is **rejected at
  assignment time** for a Neon target, with a typed, actionable error. It is
  never silently coerced, truncated, or written.
- The Angry Miao palette and the raw-code field are disabled or filtered to the
  representable subset when the active device is a Neon, so the failure is
  prevented at the UI rather than reported after the fact.
- A stored profile containing non-representable codes loads and displays, but
  applying it to a Neon target reports precisely which keys are unsupported.

Implementation:

- Read the layer count, then the keymap buffer, and write it back through the
  buffer commands, matching how `reader.py`/`writer.py` already chunk.
- Fetch and decompress the Vial keyboard definition to obtain the layout. Do not
  hand-author a layout table; N3 already fetches this for identity validation, so
  share that path.
- Handle Vial's physical unlock requirement: writes may be refused until the
  board is unlocked. Surface that as a distinct, actionable status rather than a
  generic write failure.

Red-proof: a round-trip test over the **QMK-representable subset** asserting
byte-identical recovery, plus a test proving a non-representable code is
rejected with the typed error and never reaches the transport. Corrupting one
translation entry must fail the first; removing the rejection must fail the
second.

### N7. Macros

Extend `am_configurator/macros.py` with a Vial path alongside the existing
`[6,10]` serial path, sharing the existing macro data model so the UI is
unchanged. The N6 unsupported-code policy applies to macro key events too.

Red-proof: a round-trip test through the Vial macro buffer for a macro
containing press, release, and a delay, proven red with the encoder reverted.

### N8. Profile store integration

Register Neon 80 in `am_configurator/store.py` as a device family so profiles,
current-state files, locks, and JSON backup/restore work as they do for the
existing families. No new store schema.

Red-proof: a store test covering save, reload, and backup round-trip for a Neon
profile, including one carrying a non-representable keycode.

### N9. Hardware verification

Manual, and last. Automated tests must never reach the physical keyboard.

- Confirm the enumerated identity matches this document, including that the
  definition-based model check accepts the real board.
- Confirm Neon 80 appears in Devices through the real GUI — the check that
  proves N2 actually connected the transport.
- Push a known pattern to one axial slot, one head slot, and one side slot;
  photograph each and confirm LED positions match the transcribed maps. This is
  the only check that can catch a transcription error in N4.
- Round-trip a keymap and a macro through the GUI, including confirming that a
  non-representable code is refused with the N6 error.
- Record results in this document, including anything that did not match.

## Verification

Run the repository entry point from `.agents/repo-guidance.md` (Verification)
before claiming any task complete. Note that `uv sync --locked` installs no
extras: a test that reaches a real `hidapi` import will pass locally and fail in
CI unless the dependency is a genuine runtime dependency, which N3 makes it.

Every task carries an explicit red-proof obligation. Follow the repo rule:
temporarily revert the change, confirm the test fails, restore, confirm green.

## Risks

- **Transcription error in N4** is the highest-likelihood defect and is invisible
  to every automated test, because the tests would encode the same wrong table.
  Only N9's photographic check catches it.
- **The N2 refactor touches every existing device path.** It is the one task that
  can break working support for three shipped boards. Its safeguard is that it
  lands before any HID code exists and must leave the existing suite green with
  no behavioral change.
- **Writing to the wrong keyboard** is the worst outcome in this plan. `0x05AC:0x024F`
  is widely reused and a `vial:` prefix is not a model. N3's definition-based
  gate is what stands between a user and a mis-targeted write.
- **`hidapi` packaging** reopens the native installer work stabilized in
  release-hygiene R1-R4 and the Windows suite repair. Expect all three platforms
  to need attention, and Linux to need the udev rule shipped and documented.
- **Read-back of lighting is unavailable**, so a failed or partial push cannot be
  detected by reading the board. N5's per-packet reply checking is the only
  signal.
