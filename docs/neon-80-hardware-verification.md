# AM Neon 80 — hardware verification (plan task N10)

The last task, and the only one that writes to the keyboard. Everything before
it was read-only.

Work through this in order and record the outcome of each step in the Results
table, **including anything that did not match**. A step that fails is a
finding, not a reason to stop: note it, finish the steps that do not depend on
it, and report.

## Before starting

- [ ] One AM Neon 80 connected by USB, and no other application holding it —
      close Vial, VIA, and QMK Toolbox. The app reports contention separately
      from a permission problem, so if it says the device is busy, that is why.
- [ ] On Linux only: the udev rule installed, per `docs/neon-80-linux.md`.
- [ ] A profile you are willing to overwrite. **This overwrites lighting slot 1,
      the keymap, and all macros on the device.** Read the current state first
      (step 2) so you have it recorded.

## 1. Identity

- [ ] The board enumerates and the definition-based model check accepts it.

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

- [ ] Launch the application normally and open Devices. The Neon appears
      alongside any serial boards.

This is the step that proves N1 and N2 actually connected it. A device that
works from a script but not in the GUI means the route or the browser is wrong,
which is exactly the class of defect the earlier reviews kept finding.

Record what the card shows: product name, and whether it is offered as a write
target.

## 3. Lighting geometry — asymmetric pattern

- [ ] Push a **deliberately asymmetric** pattern to slot 1 and photograph the
      axial, head, and side zones.

**A symmetric pattern is not acceptable here.** A mirrored or transposed map
looks correct under any symmetric image; only an asymmetric one can reveal it.
Use something with a distinguishable corner — a single lit key at one end, a
diagonal, or a colour gradient running one way.

Check, from the photographs:

- [ ] Axial: the lit position is where the pattern says it should be, not
      mirrored left-to-right and not rotated.
- [ ] Head: the 46x5 matrix runs in the direction expected, row-major.
- [ ] Side: derived from the head frames, so it should follow the head pattern
      rather than showing something unrelated. This is the zone most likely to
      be wrong, because it is the only one computed rather than authored.

If a zone is mirrored or transposed, record which one and in which direction —
that identifies the defect precisely.

## 4. Keymap round trip

- [ ] Read the keymap through the GUI, change one key, write it back, read
      again, and confirm the change persisted and nothing else moved.

Expect the board to be **locked**. Vial requires a physical unlock — hold the
designated keys — and the application reports that as its own state rather than
a generic failure. That message appearing is itself a passing result for the
lock handling; unlock and continue.

- [ ] A non-representable keycode is refused with the N6 error naming the key,
      and nothing is written.

Assign a consumer-page code (for example `#000C00E9`, volume up) to a key and
apply. Expected: refused, naming the layer and key index.

## 5. Macro capacity

- [ ] A macro set larger than the device holds is refused **before any write**.

The board reports 16 macros and 6677 bytes. Build 17 macros, or a set that
compiles past the byte budget, and apply. Expected: refused, saying nothing was
sent. Then confirm the device still holds its previous macros — this is the
property that matters, because a Vial macro write replaces the whole buffer.

## Results

Fill this in as you go. `—` means not attempted.

| Step | Outcome | Notes |
|---|---|---|
| 1. Identity | | |
| 2. Devices in GUI | | |
| 3a. Axial geometry | | |
| 3b. Head geometry | | |
| 3c. Side derivation | | |
| 4a. Keymap round trip | | |
| 4b. Lock reported | | |
| 4c. Bad keycode refused | | |
| 5. Macro overflow refused | | |

Copy the completed table into
`docs/superpowers/plans/2026-07-25-am-neon-80-support.md` under N10 when done.
