# AM Neon 80 Support

Status: draft, awaiting owner approval. No implementation may begin until the
owner approves this plan and the approved wording is recorded in this line.

Governing decisions: `.agents/decisions.md`, both 2026-07-25 entries
("AM Neon 80 supported at full parity or not at all" and "AM Neon 80 protocol
sources and GPL relicensing"). Those decisions are authoritative; this plan
implements them and must not restate scope they settle differently.

## Problem

The application supports three Angry Miao families — CyberBoard (`CB`),
Relic 80 (`AM21`, LED model `80`), and AFA (`ALICE`) — all reached through one
proprietary transport: 64-byte CDC-serial frames with a trailing CRC-8
(`am_configurator/protocol.py`), discovered by opening candidate serial ports
and asking each device for its product-ID string (`am_configurator/device.py`).

The AM Neon 80 shares none of that. It is a QMK/Vial device reached over raw
HID. Adding it means a second transport and a second protocol dialect beneath
the existing lighting, keymap, macro, and profile-store surfaces, not a fourth
entry in the current tables.

## Established facts

These were established by reading published Angry Miao sources and by read-only
USB enumeration of the owner's device. Nothing was written to the keyboard. A
cold agent should treat this section as given and need not re-derive it, but
must confirm the geometry against hardware before Task N8 is called complete.

### Device identity

- USB `0x05AC:0x024F` (vendor ID is Apple's, borrowed so macOS treats the board
  as a native keyboard; it is not an Apple device).
- Serial-number string carries a `vial:` prefix; the owner's unit reports
  `vial:f64c2b3c`. The suffix is a per-board UID and must not be matched on.
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

## Non-goals

- No LED frame read-back. No supported family has it; `am_configurator/reader.py`
  records that the AM serial families expose no LED-frame read path either.
  Neon 80 lacking one is parity, not a gap.
- No custom or modified firmware, and no flashing. The stock board already
  exposes everything needed.
- No Vial feature beyond keymap and macros. Combos, tap dance, key overrides,
  and QMK settings are outside parity because no existing family has them.
- No change to the AM serial transport, its device families, or their behavior.
- No automated hardware writes. Device writes stay manual, GUI-initiated, and
  gated on device/model matching plus typed confirmation.

## Tasks

Land each task as its own commit, in order. Each task states its own red-proof
obligation; a test that passes with its change reverted is vacuous and must be
replaced.

### N1. Raw HID transport and discovery

New module `am_configurator/hid_transport.py`. Do not extend `protocol.py` or
`device.py`; those own the serial dialect and must stay unchanged.

- Add `hidapi` to `pyproject.toml` runtime dependencies and regenerate the lock.
- Enumerate HID devices, selecting the interface whose usage page is `0xFF60`
  and usage is `0x61`. Match on VID/PID `0x05AC:0x024F` **and** a serial string
  beginning with `vial:`. VID/PID alone is insufficient — that pair is widely
  reused by unrelated keyboards, so a board without the `vial:` prefix must be
  rejected rather than probed.
- Provide open, write, read-with-timeout, and close, with exclusive access where
  the platform supports it, mirroring `protocol.exclusive_serial_kwargs()` in
  spirit.
- Surface a typed, pathless error when the device is absent, busy, or refuses
  permission. Linux permission failure is the common case and its message must
  name the udev remedy.
- Ship the udev rule as packaging data and document it. Without it, Linux
  requires root and discovery fails for ordinary users.

Red-proof: a discovery test with a stand-in HID backend offering a decoy device
at the same VID/PID but no `vial:` serial. The test must fail if the serial
check is removed.

### N2. Device family registration

Extend `am_configurator/device_mapping.py`.

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

### N3. Lighting push over `0xF0`

New module `am_configurator/neon_lighting.py`.

- Build 32-byte packets per the table above, including the checksum.
- Walk frames and packets, setting `packIndex` to `255` on the final packet of
  the final frame and to the packet index otherwise.
- Honour the existing operation deadline and cancellation predicate the way
  `procedural_generation.py` does, and publish throttled progress.
- Verify each reply: `0x01` continues, `0xFF` aborts with a typed error naming
  the zone and frame. A partial upload must not be reported as success.
- Reject frame counts above 256 and per-frame LED counts that do not match the
  zone before any packet is sent.

Red-proof: a transport-level test capturing every emitted packet for a
three-frame axial animation, asserting exact bytes including checksums and the
`255` terminator. Removing the terminator rule must make it fail.

### N4. Vial keymap read and write

New module `am_configurator/vial_keymap.py`.

- Read the layer count, then the keymap buffer, and write it back through the
  buffer commands. Prefer buffer over per-keycode calls for whole-keymap work,
  matching how `reader.py`/`writer.py` already chunk.
- Fetch and decompress the Vial keyboard definition from the board to obtain the
  physical layout. Do not hand-author a layout table for this device.
- Translate between QMK 16-bit keycodes and the application's existing
  `#MMPPUUUU` 4-byte representation used by `reader.py` and `macros.py`. This
  translation is the largest source of correctness risk in the plan; it needs
  round-trip tests over the full keycode range the UI can produce, not samples.
- Handle Vial's physical unlock requirement: writes may be refused until the
  board is unlocked. Surface that as a distinct, actionable status rather than a
  generic write failure.

Red-proof: a round-trip test over every keycode the UI can emit, asserting
byte-identical recovery. Corrupting one translation entry must make it fail.

### N5. Macros

Extend `am_configurator/macros.py` with a Vial path alongside the existing
`[6,10]` serial path, sharing the existing macro data model so the UI is
unchanged.

Red-proof: a round-trip test through the Vial macro buffer for a macro
containing press, release, and a delay, proven red with the encoder reverted.

### N6. Profile store integration

Register Neon 80 in `am_configurator/store.py` as a device family so profiles,
current-state files, locks, and JSON backup/restore work as they do for the
existing families. No new store schema.

Red-proof: a store test covering save, reload, and backup round-trip for a Neon
profile.

### N7. Relicensing and packaging

Implements the second 2026-07-25 decision.

Ordering constraint: N2 introduces GPL-derived tables into the tree, so this
task must land before any native build, release, or artifact publication that
carries them. It may be pulled forward to run before N2 and doing so is
preferred; what is not permitted is shipping anything built from N2's output
while `LICENSE` and `pyproject.toml` still claim MIT.

- `LICENSE` becomes GPL-2.0-or-later. Retain the existing MIT text (Copyright
  2026 GeneralD, covering the `cyberboard-cli`-derived protocol layer) as a
  third-party notice; it must not be deleted or altered.
- `pyproject.toml` line 11: `license = "MIT"` becomes `GPL-2.0-or-later`.
- `THIRD_PARTY_NOTICES` gains entries for `AngryMiao/neon_80_embedded`
  (GPL-2.0) and `AngryMiao/neon80_driver` (Apache-2.0).
- Update `tests/test_packaging.py`, which guards license files in every artifact
  under release-hygiene R1, plus the sdist allowlist if the udev rule adds a new
  top-level path.
- `README.md` states where corresponding source lives, satisfying the GPL
  source-offer obligation for distributed binaries.
- FFmpeg's LGPL bundling and its attestation system are unaffected; do not touch
  them.

Red-proof: extend the existing packaging guards so a build missing either new
attribution fails.

### N8. Hardware verification

Manual, and last. Automated tests must never reach the physical keyboard.

- Confirm the enumerated identity matches this document.
- Push a known pattern to one axial slot, one head slot, and one side slot;
  photograph each and confirm LED positions match the transcribed maps. This is
  the only check that can catch a transcription error in N2.
- Round-trip a keymap and a macro through the GUI.
- Record results in this document's verification section, including anything
  that did not match.

## Verification

Run the repository entry point from `.agents/repo-guidance.md` (Verification)
before claiming any task complete. Note that `uv sync --locked` installs no
extras: a test that reaches a real `hidapi` import will pass locally and fail in
CI unless the dependency is a genuine runtime dependency, which N1 makes it.

Every task above carries an explicit red-proof obligation. Follow the repo rule:
temporarily revert the change, confirm the test fails, restore, confirm green.

## Risks

- **Transcription error in N2** is the highest-likelihood defect and is invisible
  to every automated test, because the tests would encode the same wrong table.
  Only N8's photographic check catches it.
- **Keycode translation in N4** is the largest logic surface and the most likely
  source of subtle, user-visible wrongness.
- **`hidapi` packaging** reopens the native installer work stabilized in
  release-hygiene R1-R4 and the Windows suite repair. Expect all three platforms
  to need attention, and Linux to need the udev rule shipped and documented.
- **Read-back of lighting is unavailable**, so a failed or partial push cannot be
  detected by reading the board. N3's per-packet reply checking is the only
  signal.
