# Neon 80 LED-Preserving Writes

**Status:** Withdrawn on 2026-07-26 without implementation. The owner found the
original GIF used for the current lighting, accepted it as the recovery source,
and explicitly authorized overwriting the connected Neon's LEDs for N10. The
existing full-write route can therefore complete the approved N10 workflow.
This document remains only as the record of the considered alternative and
does not authorize a scoped-write implementation.

## Problem

The Neon exposes its keymap and Vial macro buffer for read-back, but exposes no
command for reading stored lighting frames. A document created by **Read keymap
& macros** therefore contains synthetic black LED frames, not a backup of the
keyboard's current LEDs.

The only shipped write path is `/api/device/write`. For the Neon it calls
`NeonTransport.write_config`, which sends `0xF0` lighting packets before writing
the keymap and macros. Using that path with a device-read document replaces the
current LED setup with the synthetic frames. The owner initially prohibited
that replacement, then withdrew the prohibition after finding the original
source GIF and explicitly authorized it for N10.

N10 still needs a real-GUI keymap round trip, macro safety checks, and asymmetric
lighting geometry verification. They will use the already-approved full-write
workflow; this scoped-write proposal is not required for that work.

## Safety contract

- Every scoped write remains a manual GUI action with the existing resolved
  device/model check and typed `NEON80` confirmation.
- The only accepted scopes are exactly `keymap` and `macros`.
- A keymap-scoped write sends no macro-buffer command and no lighting command.
- A macro-scoped write sends no keymap command and no lighting command.
- Neither scoped path imports, calls, or can reach `neon_lighting.push`; no
  packet beginning with vendor command `0xF0` may be sent.
- Scope-specific encoding, capacity checks, and Vial unlock status complete
  before the first SET command. A refusal sends no SET command.
- Verification reads only the section just written. A failed verification
  offers a verify-only retry and never resends the accepted write.
- A scoped success does not call `store.save_current`, create a full-device
  snapshot, clear the whole document's dirty state, or claim the synthetic LED
  frames are verified. The response and UI state explicitly say that LEDs were
  untouched.
- Serial families do not gain partial-write behavior in this change.
- The existing full-write path remains separately labeled as replacing LEDs,
  keymaps, and macros. N10 must not invoke it while the current LED setup is to
  be preserved.

## Change

### 1. Transport capability

Extend `transport.DeviceTransport` with a section-write operation taking the
logical configuration and one exact section name. `SerialTransport` rejects
both partial scopes before I/O. `NeonTransport` implements both scopes inside
one identity-approved raw-HID session.

For `keymap`, `NeonTransport`:

1. extracts and encodes all device layers;
2. reads Vial unlock status;
3. refuses while locked, before any SET;
4. writes the encoded dynamic-keymap buffer; and
5. returns a receipt labeled `keymap bytes`.

For `macros`, `NeonTransport`:

1. reads the device-reported count and byte capacity;
2. compiles and sizes the complete positional macro buffer;
3. reads Vial unlock status;
4. refuses while locked, before any SET;
5. writes that preflighted complete macro buffer; and
6. returns a receipt labeled `macro bytes`.

The preflighted bytes are the bytes transmitted; neither path re-encodes a
mutable configuration after validation.

### 2. Authenticated local routes

Add `/api/device/write-section` and `/api/device/verify-section`.

Both routes:

- accept the existing transport/address handle, complete configuration, exact
  `scope`, and exact product confirmation;
- run the existing configuration, device-family, resolved-identity, and typed
  confirmation gates;
- reject non-Neon transports and any scope other than `keymap` or `macros`
  before calling a driver;
- execute through the one device-I/O worker used by all HID calls.

The write route delegates to the driver's section-write operation, then performs
scope-specific read-back. The verify route performs only that read-back. Their
success payloads include the scope, native write count and unit label,
verification result, and `leds_untouched: true`; they contain no full-device
snapshot.

### 3. GUI

For a selected writable Neon, add two explicit actions to the existing
confirmation dialog:

- **Write keymap only** — `LEDs and macros stay untouched.`
- **Write macros only** — `LEDs and keymap stay untouched.`

The chosen scope is shown in the dialog title, warning, summary, progress copy,
button label, and result toast. The full-write action retains its current red
warning and never becomes the default partial action.

A scoped success keeps the document dirty because its other sections were not
applied. An accepted write whose verification fails changes the same action to
**Retry verification** and calls `/api/device/verify-section`.

## Non-goals

- Reading, reconstructing, exporting, or claiming to back up the current Neon
  LED frames.
- Writing any Neon lighting packet during the keymap or macro N10 checks.
- Adding partial writes to the serial Angry Miao families.
- Combining keymap and macro writes into one action; keeping them separate
  avoids rewriting an unchanged section.
- Automatically initiating any hardware write during tests or application
  startup.

## Verification

1. Driver tests record every HID request and prove keymap scope contains
   keymap SET commands but no macro SET and no `0xF0`; macro scope contains
   macro SET commands but no keymap SET and no `0xF0`.
2. Driver refusal tests prove locked, unsupported-keycode, count-overflow, and
   byte-overflow cases send zero SET commands.
3. Route tests prove exact scope parsing, Neon-only dispatch, typed
   confirmation, section-specific verification, accepted-write retry without
   resend, and no profile-store or snapshot call.
4. Web tests prove the two explicit labels and untouched-section warnings,
   full-write separation, scoped endpoint selection, retry-only behavior, and
   that scoped success does not clear the full document's dirty state.
5. Red-prove each new regression by temporarily restoring the unsafe behavior,
   then restore the implementation and run the complete repository verification
   entry point.
6. Build and smoke-test the native package on the current operating system.
7. Hardware work remains manual. First run the keymap-only N10 change and
   read-back while visually confirming the LED setup did not change. Run a
   macro-only check only after the corrected macro display is confirmed. Never
   select the full-write action in this workflow.
