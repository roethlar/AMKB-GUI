# OpenKeeb v2 — full configurator through one hub format

Status: approved by the owner on 2026-08-15 ("go"). H0 complete and closed
2026-08-16. Per-slice gates lifted by the 2026-08-16 delegation ruling ("make
it work", `.agents/decisions.md`): H1 onward proceeds continuously; the owner
is stopped only for real forks (pilot hardware, money, public
identifiers/release, hardware writes). Supersedes `docs/superpowers/plans/2026-08-08-openkeeb-v2.md` in part:
the companion-firmware lane and the OpenRGB lane are dead (owner ruling
2026-08-15, `.agents/decisions.md`); everything that plan settled about
identity, migration, naming, licensing, and device safety still stands and is
not restated here.

H3 write planning was approved by the owner on 2026-08-16 ("go"). The
fixture-backed implementation may proceed under the standing technical
delegation above. No physical VIA write, push, release, or public identifier
is authorized by that approval.

H2 first landing, 2026-08-16: the fixture-backed Vial spoke foundation is
complete. `am_configurator/hub_vial.py` validates a read-only discovery
snapshot and embedded definition, projects its KLE layout, translates keymap
and macro buffers into the hub, and produces complete byte buffers plus an
honest transfer report for the inverse direction. The seam owns no HID session
and cannot write hardware; transport wiring remains the next H2 slice. The H0
survey established that a Vial definition does not carry LED positions, so LED
geometry remains H6 work rather than being invented in H2.

H2 transport landing, 2026-08-16: `am_configurator/vial_transport.py` wires
all-Vial raw-HID discovery and complete keymap/macro snapshot reads to the hub
codec, with authenticated local read, preflight, and write routes. Read
sessions carry a command allowlist that refuses unlock and setter commands.
The write path pins the connection-scoped endpoint, USB identity, firmware
UID, and canonical embedded-definition hash; requires an exact typed embedded
board name; re-proves identity on the transmitting handle; validates the
device-reported matrix/layer/macro limits before unlocking; uses Vial's
physical unlock; and verifies exact keymap and macro read-back. Fake-HID tests
prove wrong confirmation, forged approval, endpoint replug, changed identity,
and a still-locked board send no setters. The owner's Neon 80 was selected as
the H2 pilot and passed a live generic snapshot/hub build (VIA 9, Vial 5, 6x15
matrix with 87 physical keys, four layers, 16 macros, 6,677-byte macro buffer).
After a separate hardware-write authorization, exact `AM Neon 80` typed
confirmation, and physical Esc + F2 unlock, the live profile was planned back
byte-identically; 720 keymap bytes and 6,677 macro bytes were written and read
back exactly. Unplug/replug invalidated the old endpoint, both buffers persisted
exactly, and the keyboard returned locked with no unlock in progress. This
closes H2's live evidence boundary; future hardware writes remain separately
owner-gated.

H3 pilot qualification, 2026-08-16: the owner's Mode Eighty hot-swap board
enumerated as `M80H V2`, VID `00DE`, PID `0083`, exactly matching the public
VIA `m80v2h.json` definition (`M80V2 H`, 6x17 matrix). A mutation-refusing
read-only session proved VIA protocol 9, four layers, an 816-byte keymap buffer,
and 16 macro slots in a 169-byte buffer. This settles H3's pilot and exact
definition fork. No setter, firmware, unlock, or configuration write was sent;
generic VIA definition resolution and transport wiring were the next H3 slice,
and live writes remained separately owner-gated.

H3 read-transport landing, 2026-08-16: `am_configurator/hub_via.py` and
`am_configurator/via_transport.py` accept a bounded user-imported definition,
match exact VID/PID, read the active layout-option bitfield, and project one
physical layout rather than flattening alternatives. The mutation-refusing
transport covers VIA 7's per-key keymap fallback, VIA 8+ keymap/macro buffers,
VIA 11's prefixed action/decimal-delay macro dialect, and VIA 13's stated QMK
keycode spec, with authenticated local discovery/read routes. Fake HID proves
two same-model endpoints remain distinct, wrong definitions stop before open,
setters never transmit, protocol gates select the right reads, and snapshots
become complete hub profiles. The live M80H V2 production path matched public
`m80v2h.json`, selected option 0/87 physical keys, read four layers/816 keymap
bytes and 16 macro slots/169 bytes, decoded three populated macros, and built a
complete hub profile. No write path exists in that landed slice. The H3 write
plan below is now durable; live writes remain separately owner-gated.

H3a pure-planner landing, 2026-08-16: `am_configurator/hub_via.py` now plans
complete VIA keymap and macro replacement buffers without opening HID. It
starts from the target snapshot, preserves omitted sections, addresses only
canonical matrix identities, gates stated keycode-spec mismatches rather than
guessing, and emits a validated carried/dropped transfer report. The VIA-owned
macro encoder round-trips protocol 8–10's prefixless actions and protocol 11+
prefixed actions/decimal delays, rejects reserved text, unsupported delays or
keycodes, duplicate/out-of-range slots, and whole-buffer overflow before any
transport exists. Red proof failed on the missing planner API; focused VIA
tests then passed 17/17. Full verification passed 694 Python tests, 185 web
tests, compile and JavaScript syntax gates, and sdist/wheel build. H3b
endpoint-bound fake-HID transport is next. No setter, hardware access, or live
write was added or performed.

### H3 write slice: pure plan, endpoint-bound execution, exact read-back

This section is the cold-implementation contract for completing H3. VIA does
not expose Vial's firmware UID or physical-unlock handshake, so a VIA write
must never inherit Vial's identity assumptions. The replacement safety chain
is: canonical imported-definition hash, exact connection-scoped raw-HID
endpoint, complete enumerated USB metadata, protocol/layout/capacity reproof
on the transmitting handle, exact typed confirmation, narrowly allowlisted
set commands, and complete read-back.

#### H3a — pure planner and codecs

1. Extend `am_configurator/hub_via.py` with an immutable `ViaWritePlan`
   containing optional complete keymap and macro replacement buffers plus a
   validated hub transfer report. `plan_via_write(profile, target=snapshot)`
   must validate the hub profile, open no device, and mutate no input.
2. Begin from the target snapshot's existing complete buffers. Apply only
   profile fields that are present, so omitted keymap or macro sections are
   not erased. Address keys only by canonical `K_R<row>_C<col>` identity.
   Layers, positions, macro slots, and keycodes that the target cannot express
   are reported as dropped or adapted; they are never silently truncated.
3. Keep keymap planning as a complete big-endian 16-bit matrix buffer for all
   VIA versions. The transport decides whether to send it through protocol
   7's per-key command or protocol 8+'s buffer command. Hub keycodes are the
   schema's canonical QMK 16-bit values and normally carry byte-identically.
   If both source and target state a `keycode_spec` and those versions differ,
   use a repository-backed conversion table or report the entry dropped;
   never invent a version conversion. H4 remains responsible for semantic
   cross-layout overlay.
4. Add a VIA-owned macro encoder inverse to the landed decoder. Protocols
   8–10 use prefixless tap/down/up actions and reject delays; protocol 11+
   uses the `0x01` action prefix and decimal ASCII delay terminated by `|`.
   Text and reserved-byte constraints, one-byte keycode limits,
   duplicate/out-of-range slots, delay bounds, and the device-reported byte
   budget are proven before any transport is opened. Reject NUL or action-byte
   text that the target dialect cannot represent; do not invent an escape.
   The result is a complete, capacity-sized replacement buffer. Protocol 7
   exposes no macros and produces no macro write plan.
5. Unit tests must cover preservation of omitted fields, layer/matrix/slot
   reporting, protocol-9 and protocol-11 macro round trips, delay rejection on
   old protocol, capacity overflow, unsupported keycodes, and deterministic
   transfer reports. Prove the first new test fails without the planner, then
   restore the implementation.

#### H3b — typed endpoint gate and fake-HID write transport

1. Add `PreparedViaWrite` and `ViaWriteReceipt` in
   `am_configurator/via_transport.py`. Preflight accepts address, imported
   definition, and hub profile; resolves and reads the target through the
   mutation-refusing path; creates the pure plan; and returns without sending
   a setter. The exact confirmation phrase is
   `VIA <definition name> <VID>:<PID>` with four uppercase hexadecimal digits
   per USB ID. It deliberately makes the user acknowledge both the imported
   definition and the enumerated hardware identity.
2. Bind the prepared write to every fact available at preflight: endpoint
   address and raw path, VID/PID, manufacturer, USB product, serial,
   interface, canonical definition hash and name, VIA protocol, active layout
   options, protocol-13 keycode spec when present, matrix/layer shape, macro
   count, and macro buffer size. A changed or replugged endpoint invalidates
   the preparation even when another same-model board appears.
3. Add an unforgeable VIA approval type and an approved writable session in
   `am_configurator/hid_transport.py`. It must reject a wrong confirmation
   before opening, re-enumerate the exact endpoint, open it once, and keep that
   same handle through protocol identity reproof and transmission. The session
   command surface allowlists only the reads needed for reproof/read-back and
   VIA keymap/macro setters: per-key `0x05`, keymap buffer `0x13`, and macro
   buffer `0x0F`. It must refuse keyboard-value setters, macro reset, EEPROM
   reset, bootloader jump, encoder writes, firmware operations, and unknown
   commands before transmission.
4. On the transmitting handle, re-read and exactly compare VIA protocol,
   layout options, keycode spec, layer count, and macro capacity before the
   first setter. Revalidate the imported definition and its canonical hash
   from the request. VIA firmware cannot attest that definition, so the API
   must continue to label it `user_import`; USB matching alone never upgrades
   it to device-proven identity.
5. Protocol 7 writes the planned keymap with per-key `0x05`; protocol 8+
   writes it in bounded `0x13` chunks. Protocol 8+ writes the planned macro
   buffer in bounded `0x0F` chunks. Send nothing for an absent plan component.
   Track accepted keymap and macro byte counts; if failure occurs after any
   setter, raise a distinct accepted-write error with those counts and do not
   claim rollback.
6. Before returning success, read every written component back through the
   protocol-correct path and require byte equality with the pure plan. Return
   exact accepted byte counts and the planner's validated transfer report.
   Close the session on every exit.
7. Add authenticated strict-body routes parallel to Vial:
   `POST /api/hub/via/preflight` accepts `address`, `definition`, `profile` and
   returns endpoint metadata, the exact confirmation phrase, planned byte
   counts, and report; `POST /api/hub/via/write` additionally requires
   `confirmation`, redoes read-only preparation in the request, then executes
   the endpoint-bound plan. No server-side approval survives a request or
   replug. H5 owns end-user editing UX; H3 only exposes the typed local API.
8. Fake-HID tests must prove: preflight sends no setter; wrong confirmation,
   wrong definition/hash, changed USB metadata, replug, changed protocol,
   layout option, keycode spec, layer count, or macro capacity all stop before
   a setter; same-model endpoints stay distinct; protocol 7 sends only
   per-key setters; protocol 8+ uses buffer setters; dangerous commands are
   refused locally; exact read-back succeeds; mismatched read-back reports a
   partial accepted write; and unauthenticated or malformed API requests fail.

#### H3c — separately gated live evidence and closure

Run the repository verification entry point after H3a and H3b and keep all
automated tests mutation-free outside fake HID. A live M80H V2 proof requires
a new, explicit owner authorization at the moment of the write. If approved,
first save a complete read-only snapshot, preflight the byte-identical current
profile against the same imported `m80v2h.json`, show the exact confirmation
phrase, send only the approved keymap/macro setters, require exact read-back,
then unplug/replug and prove persistence through a fresh endpoint. Record the
command classes and byte hashes/counts. Without that separate authorization,
close H3a/H3b as fixture-backed only and leave H3c open.

## Vision (owner, 2026-08-15)

One app that does all the config: take the configuration from one keyboard and
upload a compatible, equivalent version to a different keyboard. Full keyboard
configuration utility — keymaps, layers, macros, lighting — with the most
user-friendly lighting and macro experience on the market. Out of the box:
OpenKeeb speaks only protocols a board's stock firmware already ships;
nobody writes anything to make their keyboard work with us.

## Product shape

- **The hub:** one OpenKeeb profile format that captures everything a keyboard
  can be told. It is the canonical store; every ecosystem reads into it and
  writes out of it. Adding ecosystem N+1 is one spoke, not N translations.
- **The spokes (initial):**
  - **AM** — full custom protocol, already implemented; becomes a spoke.
  - **Vial** — self-describing boards (layout + LED map over USB), documented
    open protocol, keymaps/layers/macros/lighting, plus the VialRGB raw-HID
    per-LED streaming API for animations.
  - **VIA/QMK dynamic keymap** — public definitions repo supplies layouts;
    keymap/macro protocol; effect/color/speed lighting control.
- **Capability honesty:** a transfer between differing boards is *equivalent
  where possible*, never silently lossy. The app reports what carried and what
  could not, per the existing capability-qualification principle.

## QMK boundary (recorded 2026-08-15)

- **QMK with VIA enabled — in.** That is what the VIA spoke is: VIA is QMK
  compiled with the dynamic-keymap protocol switched on, the largest share of
  runtime-configurable boards shipping today.
- **Bare QMK (no VIA/raw-HID) — out, honestly stated.** Not runtime-
  configurable by anyone: the keymap is compiled in, and QMK's own tooling
  "configures" by generating new firmware to flash. Both the out-of-the-box
  rule and the no-automated-flashing rule forbid that lane.
- **A board the user has flashed to VIA firmware with the vendor's own
  official tool counts as a VIA board.** Example: Drop CTRL/ALT/SHIFT V2 —
  stock is QMK+XAP; Drop's Configurator applies the official VIA firmware in
  one user-performed step, after which it is an ordinary VIA spoke device.
- **XAP — watched, not built on.** Drop ships XAP on stock V2 firmware (V1
  reaches it via Drop's official updater), making Drop the first real XAP
  fleet and the natural first pilot if a XAP spoke is ever opened (the
  surviving V2-5 research spike in the 08-08 plan). No XAP work is authorized
  by this plan.

## The hub format (first thing to settle — everything depends on it)

Must capture, with explicit per-field provenance (read from board vs. authored
by user vs. defaulted):

- Board identity and capability descriptor: which ecosystem, layout/geometry
  (physical key positions, LED positions where the definition supplies them),
  layer count, macro limits, lighting capabilities.
- Keymap: per-layer keycode assignments in a normalized keycode space with
  ecosystem-specific extensions preserved (a QMK-only keycode survives a
  round-trip even if another spoke cannot express it).
- Layers and layer-switching behavior.
- Macros: normalized event streams plus per-ecosystem byte-budget metadata.
- Lighting: effect/color/speed selections, per-key colors, and OpenKeeb
  animations (frames + placement via the existing geometry seam).
- Transfer report schema: carried / adapted / dropped, per item.

Design constraint: the normalized keycode space is the hard, load-bearing
choice. Survey QMK/Vial keycode tables before freezing it; do not invent an
abstraction until at least two spokes' real tables are in front of us.

## First-pass overlay (the owner's acceptance test)

Import a 108-key profile onto a 40%: the first pass must land layer-1
alphanumeric keys on the correct physical keys with zero user effort. Keys
with no physical home (F-row, nav cluster, numpad) are surfaced as a worklist
— not silently discarded — with sane suggestions where the target board's
conventions supply one (e.g. existing lower/raise layers). Matching is by
canonical key identity (position-independent), not by matrix coordinates.

## UX principles (the selling point)

- Simple by default, powerful on demand: a first-run user sees a picture of
  their keyboard and clicks keys; an expert can open layer/macro/keycode
  depth without leaving the app.
- Progressive disclosure over modes: no separate "basic/advanced" builds.
- The transfer report and overlay worklist are first-class UI, not a log.
- Explicitly against branding-heavy oversimplification; the benchmark is
  "more powerful if the user wants it, and simple if not."

## Provisional slices (each needs its own go; order is dependency-driven)

- **H0 — Keycode and capability survey (no product code):** dump QMK/Vial/VIA
  keycode tables, macro encodings, and lighting capability surfaces into a
  reference doc; draft the hub schema against real data. Output: schema draft
  + survey doc for owner review.
- **H1 — Hub format lands:** schema, (de)serialization, provenance fields,
  round-trip tests. AM spoke ported to read/write the hub; existing profile
  store migrates or maps in place.
- **H2 — Vial spoke:** discovery, layout/LED-map self-description, keymap +
  macro read/write behind the existing typed-confirmation write gate.
- **H3 — VIA spoke:** definitions-repo consumption, dynamic keymap + macro
  read/write, same gate.
- **H4 — Overlay engine:** cross-board first-pass mapping + transfer report,
  pure logic with fixture-based tests (108→40% among them).
- **H5 — Keymap editor UX:** the board picture, layer editing, keycode
  palette, overlay worklist UI.
- **H6 — Lighting through the hub:** effect/color/speed on VIA/Vial boards,
  VialRGB per-LED streaming for animations, per-key geometry from board
  definitions per the 2026-08-15 geometry amendment.
- **H7 — OpenKeeb branding overhaul (noted 2026-08-16, deferred by owner):**
  not a rename — a repositioning. Product name everywhere user-facing;
  every AM-centric line of copy rewritten for the broader product,
  capability-honest (AM fully supported today, Vial/VIA in development);
  visual identity/icon; window/app/bundle naming; README; workflow display
  names; and the tests asserting each. Deep identifiers (bundle id, AppId,
  data dir, PyPI/AUR/Flatpak, repo URL, the 2.0.0 cut) stay owner-reserved.
  Ruling: `.agents/decisions.md` (2026-08-16).

H2 onward requires the pilot-hardware decision (below). H4/H5 can proceed on
fixtures alone.

## Required owner decisions (one at a time; none are made by this plan)

1. **Approve this plan** — direction, hub-first ordering, slice shape.
2. **Pilot hardware:** which physical Vial and VIA boards prove H2/H3 (one
   cheap Vial board ~$30–50 covers tier 2; community testers cover the long
   tail). The owner's existing boards list from the 08-08 plan is the start.
3. **Public namespaces** — unchanged from the 08-08 plan, still pending.

## Verification contract

- Every slice: full entry point from `.agents/repo-guidance.md` (Verification);
  new tests proven to bite (revert/fail/restore).
- Codec and overlay logic tested against recorded fixtures; automated tests
  never write to a physical keyboard (standing device-safety rule).
- Hardware writes stay manual, device/model-matched, typed-confirmation-gated.
