# AM Neon 80 — hardware verification (plan task N10)

The last task, and the only one that writes to the keyboard. Everything before
it was read-only.

Work through this in order and record the outcome of each step in the Results
table, **including anything that did not match**. A step that fails is a
finding, not a reason to stop: note it, finish the steps that do not depend on
it, and report.

## Before starting

- [x] One AM Neon 80 connected by USB, and no other application holding it —
      close Angry Miao Master, Vial, VIA, QMK Toolbox, and other HID tools. The
      app reports contention separately from a permission problem, so if it
      says the device is busy, that is why.
- [ ] On Linux only: the udev rule installed, per `docs/neon-80-linux.md`.
- [x] The current keymap and macros were read, validated, and exported before
      any write as `~/Downloads/AM-NEON80-pre-N10-2026-07-26.json`.
- [x] The owner found the original GIF used for the current LED setup and
      accepted it as the recovery source. **The device-read export is still not
      an LED backup:** Neon firmware exposes no LED-frame read-back, so its LED
      slots are synthetic black placeholders.
- [x] On 2026-07-26 the owner explicitly authorized overwriting the connected
      Neon's LED setup for N10. The full-write action and asymmetric lighting
      step may now be used.
- [x] No VM or remote-session USB forwarding is active.
- [ ] The keyboard can be power-cycled if recovery is needed.

## 1. Identity

- [x] The board enumerates and the definition-based model check accepts it.

```sh
uv run --frozen python -c "
from am_configurator import hid_transport as h
i = h.find([x.address for x in h.list_devices()][0])
print('model          :', i.model)
print('definition name:', i.definition_name)
print('firmware uid   :', i.firmware_uid)
print('protocol       :', i.protocol_version)
print('writable       :', i.writable)
"
```

Expected: model `NEON80`, definition name `AM Neon 80`, protocol `5`, writable
`True`. The firmware UID is per model, not per unit, so a different value is not
by itself a problem — record it.

## 2. Devices in the real GUI

- [x] Launch the application normally and open Devices. The Neon appears
      alongside any serial boards.
- [x] Select the Neon and run **Read keymap & macros**. The dialog completes,
      the document opens, **Save JSON** is enabled, and validation passes.
- [x] Confirm the rendered macro rows contain 22, 34, 38, and 40 aligned
      press/release events.
- [x] Confirm the per-key lighting canvas uses the real Vial key widths and row
      offsets rather than evenly sized matrix cells.

This is the step that proves N1 and N2 actually connected it. A device that
works from a script but not in the GUI means the route or the browser is wrong,
which is exactly the class of defect the earlier reviews kept finding.

Record what the card shows: product name, and whether it is offered as a write
target.

## 3. Lighting geometry — asymmetric pattern

- [x] Push a **deliberately asymmetric** pattern to slot 1 and photograph the
      axial keys and perforated top display. The firmware's third channel is
      side-screen lighting within that display, not case-edge underglow.

**Authorized:** this step overwrites the current lighting configuration. On
2026-07-26 the owner found the original source GIF, accepted it as the recovery
path, and explicitly authorized the replacement for N10.

**A symmetric pattern is not acceptable here.** A mirrored or transposed map
looks correct under any symmetric image; only an asymmetric one can reveal it.
Use something with a distinguishable corner — a single lit key at one end, a
diagonal, or a colour gradient running one way.

Check, from the photographs:

- [x] Axial: the lit position is where the pattern says it should be, not
      mirrored left-to-right and not rotated.
- [x] Head: the 46x5 matrix runs in the direction expected, row-major.
- [x] Side-screen: the 70 derived LEDs within the perforated top display follow
      the head pattern rather than showing something unrelated. The official
      driver labels this channel “side screen lights” (`side_screen_lights` /
      `侧屏幕灯`); the physical keyboard has no underglow LEDs.

If a zone is mirrored or transposed, record which one and in which direction —
that identifies the defect precisely.

## 4. Keymap round trip

- [x] Read the keymap through the GUI, change one key, write it back, read
      again, and confirm the change persisted and nothing else moved.

Use the existing full-write action. The owner has authorized its replacement of
the lighting configuration; the exact document must still pass every preflight
before the first SET command.

Expect the board to be **locked**. Its `GET_UNLOCK_STATUS` response reports
matrix positions `(0,0)` and `(0,2)`; the served Vial layout and published
firmware map those physical positions to **Esc + F2**. Type `NEON80`, hold Esc +
F2 before pressing **Write full configuration**, and keep holding while the app
starts and polls Vial's physical handshake. Esc must not dismiss the dialog, and
no lighting, keymap, or macro SET may be sent until the combo is accepted. If
the combo is not held long enough, an actionable locked status with no
configuration SET is the passing result.

- [x] A non-representable keycode is refused with the N6 error naming the key,
      and nothing is written.

Assign a consumer-page code (for example `#000C00E9`, volume up) to a key and
apply. Expected: refused, naming the layer and key index.

## 5. Macro capacity

- [x] A macro set larger than the device holds is refused **before any write**.

The oversized configuration must be submitted through the existing GUI
full-write action so its complete preflight is exercised. Expected: refusal
before any lighting, keymap, or macro SET command.

The board reports 16 macros and 6677 bytes. Build 17 macros, or a set that
compiles past the byte budget, and apply. Expected: refused, saying nothing was
sent. Then confirm the device still holds its previous macros — this is the
property that matters, because a Vial macro write replaces the whole buffer.

## 6. Independent lighting timelines

- [x] A populated slot with different axial and head frame counts transmits both
      authored timelines and the head-derived side-screen timeline.
- [x] A malformed populated slot is rejected before any configuration SET
      instead of being silently omitted.

The exact reproduction document is
`~/Downloads/AM-NEON80-config.json` (SHA-256
`745b107a4ae0a6cfd239ff95a9162382cab89cfde426f815b137dc70f55ebb90`).
Slot 1 contains 24 axial frames and 60 head frames; the side-screen channel
derives 60 frames from the head timeline.

## Results

Fill this in as you go. `—` means not attempted.

| Step | Outcome | Notes |
|---|---|---|
| 1. Identity | Pass | Physical board: model `NEON80`, definition `AM Neon 80`, firmware UID `d47af38a35b8ed73`, Vial protocol 5, writable `True`, 87 projected layout keys. Read-only; nothing was written. |
| 2. Devices in GUI | Pass | Native build 52 listed `NEON80` as USB, completed **Read keymap & macros** without crashing or touching Keychain, and opened a valid document with four 90-key layers and four populated macro slots while retaining the separately reported 16-slot capacity. Commit `25f225c` red-proves the macro decoder repair; native build 53's rendered UI confirms event counts 22, 34, 38, and 40 as aligned press/release transitions. A GET-only source-GUI read then rendered all 89 axial LEDs on the connected board's 87-key Vial geometry in rows `17/17/17/13/13/12`, with real modifier widths, row offsets, inverted-T arrows, and LEDs 80–82 grouped into one 7-unit spacebar. The exported JSON remains a keymap/macro profile with synthetic black LED placeholders, not a backup of the current LED setup. The 576-Python/55-web gate, native build 55, and bundled smoke pass. No keyboard write was attempted. |
| 3a. Axial geometry | Pass | Build 55 accepted the physical unlock and changed the axial/QWERTY lighting before the app stopped. Hardware and firmware source proved response byte 7 is echoed RGB data, not an ACK status: the red `0xFF` payload byte was misclassified as rejection after its packet landed. Commit `7dc9399` red-proves and corrects the echo handling. Build 56 then accepted the complete full write. The owner's 2026-07-27 photograph shows red at Esc, blue at left Ctrl, green at Pause, and yellow at right arrow: the asymmetric QWERTY pattern is neither mirrored nor rotated. |
| 3b. Head geometry | Pass | Build 56 transmitted the 46x5 head matrix with four corner markers plus a white center. The owner's photograph shows red upper-left, blue lower-left, green upper-right, yellow lower-right, and white in the center of the perforated top display, matching the application without mirroring, rotation, or transposition. |
| 3c. Side-screen derivation | Pass | Build 56 transmitted the 70-value channel derived from the head pattern. This is not underglow: the official driver calls it “side screen lights,” and the owner confirms that the physical keyboard has no underglow LEDs. It contributes to the same perforated top display, whose photograph shows a coherent continuation of the four corner colours; the white center appearing only in the authored head matrix is expected. UTM shows **Connect…** for AM Neon 80 (not forwarded), and Angry Miao Master, Vial, VIA, and QMK Toolbox are not running. |
| 4a. Keymap round trip | Pass | A GET-only build-56 follow-up proved all four written layers match the prepared profile exactly. Accepted-write verification then isolated a macro-only mismatch: the prepared artifact still carried the pre-fix legacy-literal representation and produced doubled transition counts on read-back. No macro plaintext was exposed. A recovered profile restores the previously verified event counts `22, 34, 38, 40` and round-trips through the Vial encoder exactly offline. Its corrective build-56 full write completed and verified. The deliberate GUI round trip then changed only layer 4 matrix index 89 from End (`#0007004D`) to F12 (`#00070045`); read-back showed exactly that one difference. End was restored, and `AM-NEON80-final-readback-2026-07-27.json` is semantically identical to the recovery profile, including the four macro event counts. The open document retained the recovery LED data because Neon firmware has no LED read-back. |
| 4b. Lock reported | Pass | Hardware returned locked, not-in-progress, with matrix combo `(0,0)` + `(0,2)` (physical Esc + F2). Build 55 accepted the real Esc + F2 handshake and proceeded into the lighting upload; no configuration SET preceded acceptance. |
| 4c. Bad keycode refused | Pass | With layer 1 matrix key 0 selected, applying consumer-page volume-up code `#000C00E9` returned **Assignment unavailable**: usage page `0x0C` has no QMK equivalent and only HID keyboard page `0x07` translates. The selected key remained Esc (`#00070029`), no write confirmation opened, and no device write occurred. |
| 5. Macro overflow refused | Pass | A local 17-macro profile was submitted through **Write to NEON80** without exposing macro plaintext. Full-write validation refused it with `macro_key contains more than 16 macros.` before any confirmation dialog or device SET. After restoring the local four-macro profile, a fresh GUI device read showed the keyboard still held four macros with event counts `22, 34, 38, 40`. |
| 6. Independent lighting timelines | Pass | Build 59 incorrectly required equal axial and head frame counts. It silently omitted populated slot 1, sent only the two unchanged black slots (100 packets), then verified keymap/macros and falsely reported success because Neon firmware has no LED read-back. The official `AngryMiao/neon80_driver` behavior confirms that the channel timelines are independent. Commit `8eeb684` gives axial, head, and derived side-screen channels their own final terminators; commit `bc659a1` makes any malformed populated slot fail before the first SET. Both regressions were red-proven. Build 60 completed the corrected 2,668-packet full write through the normal GUI after typed `NEON80` confirmation and physical Esc + F2 unlock. Keymap/macro verification passed, `current.json` and history snapshot `2026-07-27T19-21-00-288560Z` match the source SHA-256 exactly, and the owner visually confirmed that the keyboard lighting changed. |

Copy the completed table into
`docs/superpowers/plans/2026-07-25-am-neon-80-support.md` under N10 when done.
