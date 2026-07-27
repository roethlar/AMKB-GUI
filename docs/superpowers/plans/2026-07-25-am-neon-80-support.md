# AM Neon 80 Support

Status: **approved by the owner on 2026-07-25** ("approve"), after two
`openreview codex` passes and two revisions. Implementation may proceed through
the tasks below in order. Scope changes still require a new owner decision.

Governing decisions: `.agents/decisions.md` — "AM Neon 80 supported at full
parity or not at all" and "License follows capability; Neon 80 stays MIT for
now", both 2026-07-25. The latter supersedes an earlier relicensing decision.
Those decisions are authoritative; this plan implements them.

Revision history: revised twice on 2026-07-25 against `openreview codex` passes
recorded in `.agents/review/outcomes.md`. Eight findings, all admitted. The
recurring defect in both drafts was the same: the device protocol was planned
well and the application integration was not. This revision restructures around
an authoritative per-family device specification (N1) rather than patching
individual gaps, and removes the firmware-table transcription that pass two
proved was the wrong data entirely.

## Problem

The application supports three Angry Miao families — CyberBoard (`CB`),
Relic 80 (`AM21`, LED model `80`), and AFA (`ALICE`) — all reached through one
proprietary transport: 64-byte CDC-serial frames with a trailing CRC-8
(`am_configurator/protocol.py`), discovered by opening candidate serial ports
and asking each device for its product-ID string (`am_configurator/device.py`).

The AM Neon 80 shares none of that. It is a QMK/Vial device reached over raw
HID. But the transport is the smaller half of the problem: **the application is
not polymorphic over device families in either data shape or transport.**

Data shape is hardcoded in at least four places:

| Location | Hardcoded assumption |
|---|---|
| `server.py:490` | `validate_config` requires `frames`=200, `keyframes`=90, `spotlight_frames`=24 |
| `web/app.js:1311` | editor track lengths `{frames:200, keyframes:90, spotlight_frames:24}` |
| `web/app.js:489` | any unrecognized model falls back to `LED_MODELS.CB` |
| `web/app.js:1121`, `:1215` | macro limits of 32 tracks and 200 events |

Transport is hardcoded in every device route: `/api/devices` (`server.py:1356`)
calls `device.list_devices()`; `/api/device/read`, `/api/device/write`, and
`/api/device/verify` (lines 1478-1482) reach `_read_device` (1995) and
`_write_device` (2032); and `_write_request` (2063) raises `"A serial port is
required."` when none is supplied.

A Neon 80 needs authored tracks of 89 and 230 values and Vial-reported macro
limits. Registering it in `device_mapping.py` alone would produce a device the
browser renders as a CyberBoard, the validator rejects, and no route can reach.

## Established facts

These were established by reading published Angry Miao sources and by read-only
USB enumeration of the owner's device. Nothing was written to the keyboard. A
cold agent should treat this section as given and need not re-derive it, but
must confirm the geometry against hardware before N10 is called complete.

### Do not transcribe the firmware LED maps

**This is the single most important fact in this document.** The firmware's
`real_map[89]`, `h_map[5][46]`, and `s_map[70]` in `led.c` are **not** host-side
position maps. `rgb_map_t` is `{chip_index, x, y}` — coordinates on the AW20216
LED driver ICs — and the firmware applies them *after* receiving a frame, to
route buffer positions to physical driver pins. The firmware's own comment on
`h_map` reads "需要根据原理图和位号图修改，贼坑" ("must be modified per the
schematic and designator diagram, very tricky") and annotates rows by driver
chip.

The host transmits a **linear payload**: 89 axial values in payload order, and
230 head values in row-major 46x5 order. Transcribing the firmware tables into
`device_mapping.py` would apply the mapping a second time and scramble every
LED. Take axial ordering and positions from the Apache-2.0 driver's
`axialDefinitionsData.ts` instead, whose array index *is* payload index.

### Device identity

- USB `0x05AC:0x024F` (vendor ID is Apple's, borrowed so macOS treats the board
  as a native keyboard; it is not an Apple device).
- Serial-number string carries a `vial:` prefix; the owner's unit reports
  `vial:f64c2b3c`.
- **Correction, 2026-07-25.** An earlier revision of this plan recorded the
  suffix as "a per-board UID". That is wrong, and the error mattered: it makes
  the USB serial look like a unique device identifier when it is not.
  `vial:f64c2b3c` is a fixed magic string every Vial keyboard reports. Two
  independent lines of evidence:
  - Vial publishes a single udev rule, for all Vial keyboards, that matches
    `ATTRS{serial}=="*vial:f64c2b3c*"` literally. A per-board value could not
    serve as a general rule.
  - The genuine per-board UID is the 8 bytes returned by `FE 00`, measured on
    the owner's unit as `d47af38a35b8ed73` — a different value from the serial
    suffix, as recorded under "Vial definition fetch" below.

  Consequence for implementation: **a device address must not be derived from
  the USB serial**, because two different Vial boards on the same VID/PID share
  it exactly. Use the `FE 00` keyboard UID.
- **This pair identifies far less than it appears to.** `0x05AC:0x024F` is
  reused by many unrelated keyboards, and a `vial:` prefix marks any Vial board
  whatsoever. Neither, alone or together, establishes that the connected device
  is a Neon 80. N3 defines the identity check that does.
- Interfaces: keyboard (usage page `0x01`, usage `0x06`), mouse (`0x01`/`0x02`),
  and raw HID (usage page `0xFF60`, usage `0x61`).
- No CDC-serial port is exposed. `device.candidate_ports()` can never enumerate
  this board, and `probe()` can never identify it.
- **Verified on the owner's board, 2026-07-25**, by read-only `hid.enumerate()`
  with no bytes sent to the device. The interface table above is confirmed
  exactly: raw HID is usage page `0xFF60` / usage `0x61` on interface 1, and the
  serial number reads `vial:f64c2b3c`. Two facts the plan did not previously
  record:
  - `manufacturer_string` is `AngryMiao` and `product_string` is `AM Neon 80`.
    These are evidence, not proof — USB string descriptors are firmware-authored
    and a clone or a reflashed board can report anything — so they narrow
    candidates like VID/PID does and do **not** replace the definition gate.
  - macOS reports `path` as `DevSrvsID:<n>` (an IOKit registry entry ID), which
    is **not** stable across replug. That is correct for the confirmation
    binding, whose purpose is to invalidate when the device changes, but the
    plan's word "immutable" is wrong: read it as stable for the lifetime of one
    connection, and treat any change as invalidating.

### Vial definition fetch (verified on hardware, 2026-07-25)

Read-only probe of the owner's board, using an allowlist that refused any
non-read subcommand. Nothing was written. These are the constants N3's identity
gate needs; they were previously unrecorded and must not be re-derived.

Raw HID packets are 32 bytes. `hidapi` requires a leading report-ID byte, so a
request is `b"\x00" + payload.ljust(32, b"\x00")`.

| Request | Bytes | Response |
|---|---|---|
| Keyboard ID | `FE 00` | `u32` LE Vial protocol version, then 8-byte keyboard UID |
| Definition size | `FE 01` | `u32` LE compressed byte count |
| Definition block *n* | `FE 02 <n LE16>` | 32 bytes of the compressed payload |

Only `0x00`, `0x01`, and `0x02` are reads. `0x04` (set encoder), `0x06`-`0x08`
(unlock start / poll / lock) and the settings-set subcommands mutate the board;
an implementation must never issue them during discovery or identity checking.

Observed on the owner's unit:

- Vial protocol version **5**; keyboard UID `d47af38a35b8ed73`. Note this UID is
  **not** the `vial:f64c2b3c` serial suffix — they are different values from
  different sources, and neither is a model identity.
- Compressed definition is **404 bytes**, magic `fd 37 7a 58` — that is **XZ**,
  not LZMA-alone. Plain `lzma.decompress` handles it; do not force
  `FORMAT_ALONE`.
- Decompressed payload is 1061 bytes of JSON with exactly these top-level keys:
  `layouts`, `matrix`, `name`, `productId`, `vendorId`.
- `name` is **`"AM Neon 80"`** — this is the field the identity gate matches on.
  `vendorId` `05AC`, `productId` `024F`, `matrix` `{rows: 6, cols: 15}`, and
  `lighting` is absent.

The definition is firmware-authored like the USB strings, so this gate is not
cryptographic proof of hardware. It is materially stronger than VID/PID or the
`vial:` prefix — it is the board declaring its own model — and it is the gate
the approved plan specifies.

### VIA capacity, measured on hardware 2026-07-25

Read-only VIA reads against the owner's board, behind an allowlist that refused
every mutating command. Nothing was written.

| Value | Command | Measured |
|---|---|---|
| VIA protocol version | `0x01` | 9 |
| Layer count | `0x11` | **4** |
| Macro count | `0x0C` | **16** |
| Macro buffer | `0x0D` | **6677 bytes** |

Three of these contradict assumptions carried from the serial families and must
not be defaulted:

- **4 layers, not 7.** `_read_device` requests 7 layers by default and the
  browser asks for `layers().length || 7`. A Neon has four.
- **16 macros, not 32.** The serial ceiling is double the real one here.
- **Capacity is 6677 bytes**, with no event-count limit at all — which is why
  or-3 required the byte budget to be a separate field rather than a different
  value for `macro_events`.

`macro_events` for this family should be recorded as a *proven upper bound*
derived from the buffer (no event encodes in fewer than one byte, so the count
can never exceed the byte budget), never as an invented ceiling. The
authoritative check is exact byte sizing before a write, which is N7.

### Upstream sources

`AngryMiao/neon80_driver` — reference web configurator, **Apache-2.0**. This is
the implementation source:

| File | Contents needed |
|---|---|
| `src/804/utils/keyboard-api.ts` | `setRGB` packet construction, VIA command enum, `calculateSumCheck` |
| `src/804/light-library/device-push.ts` | Channel walk, packetization, side-zone derivation |
| `src/804/light-library/payload.ts` | Frame-length validation: matrix 230, axial 89 |
| `src/804/axialDefinitionsData.ts` | Axial LED order and positions; array index is payload index |

`AngryMiao/neon_80_embedded` — keyboard firmware, **GPL-2.0**. Read to establish
facts (geometry constants, slot layout, frame ceiling in `led_drv.h` and
`app_flash.h`). Its LED tables must not be transcribed — see above. Establishing
an interface fact is not copying expression; the application stays MIT.

### Zones, slots, and capacity

Firmware `app_flash.h` and the driver's `setRGB` docstring agree exactly.

| `cmd` byte | Firmware enum | Zone | LEDs per frame | Flash bytes per frame |
|---|---|---|---|---|
| `0x01`–`0x03` | `CMD_KEY_LED1..3` | axial (per-switch) | 89 | 512 |
| `0x04`–`0x06` | `CMD_HEAD_LED1..3` | head matrix, 46x5 | 230 | 1024 |
| `0x07`–`0x09` | `CMD_SIDE_LED1..3` | side | 70 | 256 |
| `0x0A`–`0x0D` | `CMD_DEFAT_HEAD1/2`, `CMD_DEFAT_SIDE1/2` | factory defaults | | |
| `0x0E` | `CMD_OTHER_CMD` | control; driver sends `F0 0E 01` | | |

Three user slots per zone. `USER_FRAME_MAX` is **256 frames per slot**.

**Two authored tracks, three channels.** The driver pushes one authored light
effect to slot *N* as channels *N*, *N+3*, and *N+6* — axial, head, and side —
deriving side from the head frames at transmit time. Side is therefore **never
independently authored** and must not become a selectable track. This matters
concretely: `device_mapping.py:427` `target_capabilities()` publishes every
`_LAYOUTS` entry as a selectable target, so adding side there would offer users
a track that the next head upload silently overwrites.

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
`[0]` is the command selector and bytes `[1..31]` are the payload.

**N10 hardware correction (2026-07-26):** the firmware echoes an accepted
packet; it does not return a separate status byte. Response byte `[7]` is the
first echoed RGB byte, so `0xFF` is valid colour data rather than failure. On
the terminal packet, firmware replaces pack index `0xFF` with the packet's real
index and recomputes the checksum before echoing it. The application validates
that firmware-shaped echo. The earlier status-byte interpretation partially
wrote the axial zone before mistaking its red corner byte for rejection.

Packetization: 8 LEDs per packet, so 89 axial LEDs produce 12 packets (the last
carrying 1 LED) and 230 head LEDs produce 29 packets (the last carrying 6).

### Side-zone derivation

Derived from head frames at transmit time. Reproduce exactly:

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

`0x0E` is both a top-level VIA command and the second byte of the vendor control
packet `F0 0E 01`. They do not collide because the vendor byte is nested under
`0xF0`; keep the namespaces separate in code.

Macro capacity is **device-reported**, via `GET_COUNT` and `GET_BUFFER_SIZE`. It
is not the application's hardcoded 32 tracks / 200 events, which are AM serial
firmware limits.

### Keycode width mismatch

QMK keycodes are **16-bit**. The application's keymap surface is **32-bit**:
`web/app.js:1091` accepts any `#` followed by eight hexadecimal digits,
`app.js:1085` exposes that raw field, and `app.js:1084` advertises "Raw codes
remain available for lossless passthrough". The Angry Miao palette includes
vendor usage pages with no QMK equivalent.

A lossless round-trip of every code the UI can emit is therefore **impossible**
on a Vial device. N6 defines the policy that replaces it.

## Non-goals

- No LED frame read-back. No supported family has it; `am_configurator/reader.py`
  records the AM serial families expose no LED-frame read path either.
- No custom or modified firmware, and no flashing.
- No Vial feature beyond keymap and macros. Combos, tap dance, key overrides,
  and QMK settings are outside parity.
- No selection of the firmware's built-in lighting effects. No existing family
  offers it; it is a plausible later capability, not part of parity.
- No behavioral change to the AM serial families. N1 and N2 refactor the seams
  they sit behind; their observable behavior must be identical before and after.
- No relicensing. The superseding decision keeps the application MIT.
- No automated hardware writes. Device writes stay manual, GUI-initiated, and
  gated on device/model matching plus typed confirmation.

## Tasks

Land each task as its own commit, in the order given. Each states its own
red-proof obligation; a test that passes with its change reverted is vacuous.

N1 and N2 are pure refactors that must land before any Neon code exists. Both
are built with the three existing families as their only entries, so each is
provable in isolation against the current suite.

### N1. Authoritative device-family specification

One module owning, per family: authored track names and lengths, LED counts,
frame cap, macro track and byte limits, and transport kind. Every consumer reads
it instead of a literal.

Consumers to convert:

- `validate_config` (`server.py:490`) — replace the `(("frames", 200),
  ("keyframes", 90), ("spotlight_frames", 24))` tuple with a spec lookup.
- Blank-profile creation and any generation path that sizes tracks.
- `web/app.js:1311` `trackInfo()` — replace the hardcoded lengths object.
- `web/app.js:489` — replace the CyberBoard fallback with an explicit
  unknown-family error. A silent fallback is what would render a Neon as a
  CyberBoard.
- `web/app.js:1121` and `:1215` — macro limits read from the spec, not `32`
  and `200` literals.
- Target controls and profile summaries.

Red-proof: the existing suite passes unchanged, plus a test proving an unknown
family raises rather than falling back to CyberBoard. Restoring the fallback
must make it fail.

### N2. Transport-neutral device handle and route dispatch

**Revised 2026-07-25 after openreview finding or-1** (`.agents/review/findings/
or-1.md`), owner-approved. The first implementation (commit `94a847a`) dispatched
on the handle but left the AM serial encoding *above* the seam: the route called
`writer.plan(config)` and passed 64-byte frames to `write_config(address,
frames)`. A raw-HID driver cannot construct `0xF0` or Vial writes from those
bytes, so the seam had to move below the encoding. The corrected design is
below; N2 is complete only when it holds.

- Introduce a device handle carrying transport kind plus transport-specific
  address, replacing the bare `port` string in the device routes. Existing
  devices produce a serial-kind handle wrapping the same port. **Done in
  `94a847a`; unchanged by the revision.**
- Dispatch discovery, read, write, and verify on the handle: `/api/devices`,
  and `/api/device/read|write|verify` reaching `_read_device` and
  `_write_device`. **Done in `94a847a`; unchanged.**
- `_write_request` generalizes `"A serial port is required."` to a handle.
  **Done in `94a847a`; unchanged.**
- `_validated_write_target` keeps its exact contract: probe, confirm a
  supported keyboard, match the config's `product_id`, require typed
  confirmation equal to the product ID. Only the probe becomes dispatched. **The
  gate does not weaken here**; N3 strengthens it for HID. **Done in `94a847a`;
  unchanged.**
- Update the browser device surface to carry handles rather than port strings.
  **Done in `94a847a`**: a device's identity key is `transport:address`.
- **Move the seam below the protocol encoding.** The driver interface takes the
  logical configuration, not encoded bytes:
  - `write_config(address, config) -> WriteReceipt` plans *and* transmits. AM
    frame planning (`writer.plan`) moves inside the serial driver, which owns
    `SETTLE_SECONDS` and raises a typed `DeviceWriteError` carrying the
    protocol's own rejection detail. `server.py` stops importing `writer`.
  - `describe_write(config) -> WriteReceipt` reports what a write *would*
    transmit without performing I/O. The verify route needs this because it
    reports a transmitted-unit count without resending; today it calls
    `writer.plan(config)` purely to read `.total`.
  - `WriteReceipt` carries a protocol-native unit count and its label
    (serial: configuration frames), so the response payload stops naming
    `frames` unconditionally. The browser write toast renders the label rather
    than hardcoding "configuration frames".
  - `"Device rejected JSON_END: …"` moves out of the route into the serial
    driver: it is a serial protocol message and must not be raised by
    transport-neutral code.
- `write_macros`/`read_macros` already pass macro dictionaries rather than
  encoded bytes and need no change; the revision makes the whole interface
  consistently domain-level.

Red-proof: existing device-route tests pass unchanged, plus (a) a dispatch test
proving an unknown transport kind is rejected with a typed error rather than
silently treated as serial, and (b) a test registering a synthetic non-serial
driver and proving a write reaches it as the logical configuration — reverting
to a frames-shaped interface must make it fail.

### N3. Raw HID transport and Neon 80 identity

New module `am_configurator/hid_transport.py`. Do not extend `protocol.py` or
`device.py`.

- Add `hidapi` to `pyproject.toml` runtime dependencies; regenerate the lock.
- Enumerate HID devices, selecting usage page `0xFF60`, usage `0x61`.
- **Identity is a three-stage gate; only the last authorizes a write.** VID/PID
  narrows candidates; a `vial:` serial prefix confirms Vial firmware; neither
  establishes the model. Before exposing a device as write-capable, fetch and
  validate the Vial keyboard definition and confirm it identifies a Neon 80. A
  Vial board that is not a Neon 80 enumerates as unsupported, never writable.
- Bind the typed confirmation to the validated identity and to an immutable HID
  path identity captured at validation time, so a device swapped between
  confirmation and write cannot inherit the approval.
- Provide open, write, read-with-timeout, close, with exclusive access where the
  platform supports it.
- Typed pathless errors for absent, busy, or permission-denied devices. Linux
  permission failure is the common case; its message must name the udev remedy.
- Ship the udev rule as packaging data and document it.

Red-proof: a decoy test with a stand-in HID backend offering a device at the
same VID/PID **and** a valid `vial:` prefix, but a definition that is not a
Neon 80 — it must be rejected as a write target, and removing the definition
check must make the test fail. A second test proves a changed HID path identity
invalidates a prior confirmation.

### N4. Neon 80 family registration

Register Neon 80 in the N1 spec and in `am_configurator/device_mapping.py`.

- **Two authored tracks only**: axial (89 values) and head (230 values, 46x5
  row-major). Frame cap 256.
- **Head needs no position map at all** — payload order is row-major.
- **Axial ordering comes from the Apache-2.0 driver's `axialDefinitionsData.ts`**,
  whose array index is the payload index; derive grid positions from its
  coordinates. Do not transcribe firmware `real_map`.
- **Side is not a registered track.** It is derived privately at transmit time
  (N5). It must not appear in `_LAYOUTS`, because
  `device_mapping.py:427` publishes every entry as independently selectable.
- Extend `led_model()` to return `NEON` for the Neon 80 identity.

Red-proof: a test asserting the published target list for Neon contains exactly
the two authored tracks and not side; adding side must make it fail. A second
test asserts axial payload order round-trips to the expected grid positions.

### N5. Lighting push over `0xF0`

New module `am_configurator/neon_lighting.py`, reached through the N2 handle.

- One authored effect pushes to slot *N* as channels *N*, *N+3*, *N+6*: axial,
  head, and side derived from the head frames per the algorithm above.
- Build 32-byte packets per the table, including checksum; `packIndex` is `255`
  on the final packet of the final frame, else the packet index.
- Honour the existing operation deadline and cancellation predicate as
  `procedural_generation.py` does; publish throttled progress.
- Verify each reply: `0x01` continues, `0xFF` aborts with a typed error naming
  zone and frame. A partial upload must never report success.
- Reject frame counts above 256 and per-track lengths that do not match the spec
  before sending any packet.
- Wire the Lighting Apply path so a Neon target applies through this module.

Red-proof: a golden-packet test capturing every emitted byte for a three-frame
effect across all three channels, asserting checksums, the `255` terminator, and
that the side channel matches the derivation. Removing the derivation or the
terminator rule must fail it.

### N6. Vial keymap and the unsupported-code policy

New module `am_configurator/vial_keymap.py`, reached through the N2 handle.

Policy replacing the impossible lossless round-trip:

- QMK-to-application translation must be **injective**, so read-back is stable.
- A UI-emittable code with **no** QMK representation is **rejected at assignment
  time** for a Neon target with a typed, actionable error — never silently
  coerced, truncated, or written.
- The Angry Miao palette and raw-code field are filtered to the representable
  subset when the active device is a Neon, preventing the failure at the UI.
- A stored profile containing non-representable codes loads and displays, but
  applying it to a Neon reports precisely which keys are unsupported.

Implementation: read layer count then the keymap buffer, write back through the
buffer commands, chunking as `reader.py`/`writer.py` do. Reuse the definition
fetched in N3 for the layout. Handle Vial's physical unlock requirement as a
distinct, actionable status, not a generic write failure.

Red-proof: round-trip over the representable subset asserting byte-identical
recovery, plus a test proving a non-representable code is rejected and never
reaches the transport. Corrupting a translation entry fails the first; removing
the rejection fails the second.

### N7. Macros with device-reported capacity

Extend `am_configurator/macros.py` with a Vial path alongside the existing
`[6,10]` serial path, sharing the existing macro data model.

- Query `GET_COUNT` and `GET_BUFFER_SIZE` during discovery or read; publish both
  into the N1 spec for the connected device.
- **Capacity is bytes, not events** (openreview finding or-3,
  `.agents/review/findings/or-3.md`). `GET_BUFFER_SIZE` is a total buffer size;
  how many events fit depends on each event's encoding, and no conversion to an
  event count is correct — too many bytes per event rejects valid macro sets,
  too few accepts a buffer that overruns the device. Add a byte-budget field
  *alongside* `macro_tracks`/`macro_events` rather than reusing them, and never
  express "device-reported" as `None`: `validate_config` would silently stop
  enforcing, and the editor would render an empty limit and a permanently
  tripped meter. Discovered per-device capacity overlays the family spec.
- Compile and size the **complete** macro buffer before the first reset or HID
  write. Reject overflow with a typed error **before sending anything** — a Vial
  macro write rewrites the whole buffer, so a mid-write failure can clear macros
  the user already had.
- Surface the device limits in the UI in place of the `32`/`200` literals.
- The N6 unsupported-code policy applies to macro key events too.

Red-proof: tests at exact-count, exact-byte, and one-over boundaries, proving
the one-over case sends zero packets. A single-macro round-trip is explicitly
insufficient and must not be the only coverage.

### N8. Profile store integration

Register Neon 80 in `am_configurator/store.py` so profiles, current-state files,
locks, and JSON backup/restore work as for existing families. No new schema.

Red-proof: save, reload, and backup round-trip for a Neon profile, including one
carrying a non-representable keycode and one at the macro capacity boundary.

### N9. Notices and packaging

- `THIRD_PARTY_NOTICES` gains an Apache-2.0 attribution for
  `AngryMiao/neon80_driver`, used as the reference client.
- Extend the sdist allowlist if the udev rule adds a top-level path.
- `tests/test_packaging.py` guards license files in every artifact under
  release-hygiene R1; update it to cover the new attribution.

No license change. The application remains MIT per the superseding decision.

Red-proof: extend the packaging guard so a build missing the attribution fails.

### N10. Hardware verification

Manual, and last. Automated tests must never reach the physical keyboard.

- Confirm enumerated identity matches this document, including that the
  definition-based model check accepts the real board.
- Confirm Neon 80 appears in Devices through the real GUI — the check that
  proves N1 and N2 actually connected it.
- Push a known **asymmetric** pattern to one slot; photograph axial, head, and
  side and confirm LED positions and orientation. An asymmetric pattern is
  required: a symmetric one cannot reveal a transposed or mirrored map.
- Round-trip a keymap and a macro through the GUI, including confirming a
  non-representable code is refused with the N6 error and an oversized macro set
  is refused before any write.
- Record results here, including anything that did not match.

Current hardware results as of 2026-07-27; the detailed live record is
`docs/neon-80-hardware-verification.md`.

| Check | Outcome | Evidence |
|---|---|---|
| Identity and real GUI | Pass | The physical board passed the definition gate as `NEON80`; native build 56 reads and targets it through Devices. |
| Asymmetric lighting orientation | Partial | Build 56 completed the axial, head, and derived-side upload, and the owner reports that the LEDs match the application. Explicit axial/head/side orientation inspection or photographs remain open. |
| Keymap and macro round trip | Pass | A recovered four-macro profile completed a full write and read-back at event counts `22, 34, 38, 40`. A deliberate layer 4 matrix-index-89 End→F12 change read back as the only keymap difference; End was restored and the final GUI read-back is semantically identical to the recovery profile. |
| N6 unsupported assignment | Pass | Layer 1 matrix key 0 refused `#000C00E9` as a non-QMK-representable usage-page-`0x0C` code, retained Esc, and opened no write confirmation. |
| N7 macro overflow | Pass | The GUI full-write action refused a local 17-macro profile before confirmation. A fresh device read still returned the original four macros at `22, 34, 38, 40` events. |

## Verification

Run the repository entry point from `.agents/repo-guidance.md` (Verification)
before claiming any task complete. Note that `uv sync --locked` installs no
extras: a test reaching a real `hidapi` import passes locally and fails in CI
unless the dependency is a genuine runtime dependency, which N3 makes it.

Every task carries an explicit red-proof obligation. Follow the repo rule:
revert the change, confirm the test fails, restore, confirm green.

## Risks

- **N1 and N2 touch every existing device path.** They are the tasks that could
  break working support for three shipped boards. Their safeguard is landing
  before any Neon code exists and leaving the existing suite green with no
  behavioral change.
- **Axial ordering** is now the highest-likelihood silent defect, since the
  firmware tables are unusable and the order is inferred from the driver's
  positional data. Only N10's asymmetric-pattern photograph catches an error.
- **Writing to the wrong keyboard** is the worst outcome here. `0x05AC:0x024F`
  is widely reused and a `vial:` prefix is not a model. N3's definition gate is
  what stands between a user and a mis-targeted write.
- **Macro buffer rewrites are destructive on failure**, which is why N7 sizes
  the whole buffer before touching the device.
- **`hidapi` packaging** reopens the native installer work stabilized in
  release-hygiene R1-R4 and the Windows suite repair. Expect all three platforms
  to need attention, and Linux to need the udev rule shipped and documented.
- **Lighting read-back is unavailable**, so a partial push cannot be detected by
  reading the board. N5's per-packet reply checking is the only signal.
