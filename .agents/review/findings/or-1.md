# or-1: The write seam sits above the protocol encoding, not below it

**Severity**: HIGH — the transport abstraction N2 introduced cannot carry a
non-serial device, so the seam must be rebuilt before N5/N6 rather than
extended.
**Status**: Open
**Branch**: (not started)
**Commit**: (not started)

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

Not started. See "Owner decision required" below — the correction is an
architecture change, not a repair.

## Files changed

Not started.

## Guard proof

Not started. A guard must show a non-serial transport receiving a logical
configuration rather than AM frames; a synthetic transport in
`tests/test_transport.py` can assert this without hardware.

## Coder dispute (if any)

None. The citations were verified line by line and are exact. The defect is
mine: I made the transport a byte pipe when the operations it must abstract
differ by protocol, not merely by link.

## Known gaps

The macro path is already closer to correct — `link.write_macros(address,
entries)` passes macro dicts, not encoded bytes — so the seam is inconsistent
as well as misplaced. Any fix should settle both.

## Owner decision required

The plan's N2 says "dispatch discovery, read, write, and verify on the handle",
which this implements literally. Correcting it means dispatching a *domain-level*
write to a device driver, keeping AM frame planning inside the serial driver,
and returning a typed write receipt instead of serial `JSON_END` status. That is
a larger N2 than the approved plan describes.

## Reviewer comments

`Reviewer: codex / gpt-5.6-sol / (codex-configured default) / n/a — see
outcomes.md routing deviation`. Raised in the 2026-07-25 openreview pass over
`65a70c9..94a847a`. Verdict `findings`. Admitted at intake after independent
verification of every citation.
