# or-1: The write seam sits above the protocol encoding, not below it

**Severity**: HIGH — the transport abstraction N2 introduced cannot carry a
non-serial device, so the seam must be rebuilt before N5/N6 rather than
extended.
**Status**: Verified
**Branch**: `neon-80-support` (worked in place; see Approach)
**Commit**: see the `or-1:` commit on `neon-80-support`

## Evidence

- `am_configurator/server.py:2049-2050` — the route calls `writer.plan(config)`
  and hands `frame_plan.frames` to `link.write_config(handle.address, frames)`.
  The AM serial encoding therefore happens *above* the transport.
- `am_configurator/transport.py:68` — `write_config(self, address, frames)`
  accepts already-encoded AM 64-byte serial frames as its parameter.
- `am_configurator/server.py:2052` — on failure the route raises
  `"Device rejected JSON_END: …"`, a serial-protocol-specific message, from
  transport-neutral code.
- `am_configurator/server.py:2055` — `frame_plan.total`, a serial frame count,
  is passed into `_finish_accepted_write` and reaches the response payload.

## Predicted observable failure

A raw-HID Neon driver cannot construct `0xF0` lighting packets or Vial keymap
writes from `frame_plan.frames`, because those frames are the AM serial
encoding of the configuration, not the configuration. When N5 lands, either the
seam is replaced or the HID path receives the wrong protocol representation.
The failure is a rebuild of N2's central abstraction, not a runtime error.

## What

N2 introduced `DeviceHandle` and a transport registry to make device I/O
transport-neutral, but placed the seam one layer too high: the route encodes
the configuration into serial frames and the transport only ships bytes.
A transport that shares no encoding with serial has nothing to implement.

## Approach

The seam moved below the encoding. `write_config(address, config)` now takes
the logical configuration and each driver plans its own protocol;
`SerialTransport` owns `writer.plan`, `writer.SETTLE_SECONDS`, and its own
rejection message. `describe_write(config)` reports what a write would transmit
with no I/O, which is what the verify route actually needs. `WriteReceipt`
carries a protocol-native unit count plus its label so the response payload
stops assuming every device writes frames. `DeviceWriteError` carries the
driver's rejection detail, so `"Device rejected JSON_END"` no longer appears in
`server.py`.

Worked on the existing branch rather than a per-finding branch: the finding is
a defect in unmerged work on that branch, and the repo's Git Safety rule
forbids rewriting the commit it corrects. The correction is one commit.

## Files changed

- `am_configurator/transport.py` — `WriteReceipt`, `DeviceWriteError`,
  `describe_write`, and a configuration-taking `write_config`.
- `am_configurator/server.py:2041-2070` — routes dispatch a domain-level write;
  `writer` is no longer imported for the device paths.
- `am_configurator/server.py:2148-2152` — response reports `write_units` and
  `write_unit_label`.
- `am_configurator/web/app.js` — the write toast renders the driver's label.
- `tests/test_transport.py` — the guards below.

## Guard proof

- `tests/test_transport.py::SerialDispatchTests::test_the_driver_receives_the_configuration_and_plans_its_own_protocol`
  — reverting `write_config` to a frames-shaped parameter fails it with
  "Expected 'plan' to be called once. Called 0 times." Restoring passes.
- `tests/test_transport.py::NonSerialDriverTests` — registers a driver sharing
  no encoding with serial and proves a write arrives as the configuration
  object itself, reported in that driver's own unit. This is the property the
  finding identified as missing.
- `tests/test_transport.py::SerialDispatchTests::test_a_refused_write_raises_the_drivers_own_protocol_error`
  — asserts `JSON_END` appears nowhere in `server.py`.

## Coder dispute (if any)

None. The citations were verified line by line and are exact. The defect is
mine: I made the transport a byte pipe when the operations it must abstract
differ by protocol, not merely by link.

## Known gaps

Closed by `8546d54` under `n567-2`: validation now takes exact keymap geometry
from `FamilySpec`, and the AM wire encoder runs only for serial families.
Non-serial drivers retain their own preflight before transmission.

## Owner decision (resolved)

The plan's N2 said "dispatch discovery, read, write, and verify on the handle",
which the first implementation satisfied literally. The correction — dispatching
a domain-level write, keeping AM frame planning inside the serial driver, and
returning a typed receipt — is a larger N2 than the approved plan described, so
it was put to the owner as A (rework now) or B (defer to N5).

**Owner chose A, 2026-07-25: "Rework N2 now under the corrected design."**
Recorded in `.agents/decisions.md` under "The device seam sits below the
protocol encoding"; plan task N2 was revised before implementation.

## Reviewer comments

`Reviewer: codex / gpt-5.6-sol / (codex-configured default) / n/a — see
outcomes.md routing deviation`. Raised in the 2026-07-25 openreview pass over
`65a70c9..94a847a`. Verdict `findings`. Admitted at intake after independent
verification of every citation.
