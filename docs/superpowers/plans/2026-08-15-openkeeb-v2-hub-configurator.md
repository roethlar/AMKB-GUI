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
is authorized by that approval. H3c's one live VIA write was separately
approved and is recorded below; future hardware writes remain separately
owner-gated.

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
tests, compile and JavaScript syntax gates, and sdist/wheel build. H3b's landed
status follows. No setter, hardware access, or live write was added or
performed in H3a.

H3b fake-HID write-transport landing, 2026-08-16: VIA preflight now binds the
canonical imported-definition hash, complete connection-scoped endpoint/USB
metadata, target protocol, layout options, keycode spec, layer count, and
macro capacity to the pure plan. Exact confirmation is
`VIA <definition name> <VID>:<PID>`. The approved session re-enumerates the
endpoint, keeps one handle through reproof/write/read-back, and allows only the
landed reads plus `0x05` per-key, `0x13` keymap-buffer, and `0x0F` macro-buffer
setters; reset, bootloader, keyboard-value, encoder, firmware, and unknown
commands are refused before transmission. Protocol 7 and 8+ writers use their
correct paths, omitted components send nothing, complete read-back is exact,
and lost replies or mismatches retain possible accepted-byte counts through
the authenticated local API. Fake HID proves confirmation, forged approval,
definition hash, metadata, replug, protocol/layout/keycode-spec/layer/capacity,
same-model endpoint, command allowlist, partial acceptance, and read-back
boundaries. Red proof failed on the missing H3b APIs; focused VIA tests then
passed 31/31. Full verification passed 708 Python tests, 185 web tests, compile
and JavaScript syntax gates, and sdist/wheel build. No real HID backend was
opened and no live hardware write was performed. H3c remains separately
owner-gated.

H3c live qualification, 2026-08-16: the owner authorized the exact confirmation
`VIA M80V2 H 00DE:0083`. Production preflight against the public
`m80v2h.json` definition carried all 411 transfer-report items and planned the
live profile byte-identically. The canonical definition hash was
`sha256-018417e38d10619673b482e205122853ffa9fa010741ea855941b61b7d8afdfa`.
On VIA protocol 9, the endpoint-bound approved session sent only the `0x13`
keymap-buffer and `0x0F` macro-buffer setters: 816 keymap bytes with SHA-256
`e8b4e5d6ec159956733126f6655cd342178fe41f15ac3b2de079bb168e8e0cab` and
169 macro bytes with SHA-256
`1c999937ccb5f76c7b6ac1227545bf28c0df3da161e3738337e8ae5b84a14ad7`.
Immediate complete read-back matched exactly. After physical unplug/replug, a
fresh mutation-refusing enumeration and snapshot reproduced both byte counts
and hashes, including all 16 macro slots and three populated macros. This
closes H3's live evidence boundary; future hardware writes remain separately
owner-gated.

H4 overlay-engine landing, 2026-08-16: `am_configurator/hub_overlay.py`
implements a pure, target-preserving first pass and opens no transport.
Authored semantic key identities match directly; current AM/Vial/VIA
positional identities use unique base-key functions as device-proven semantic
anchors, and matrix coordinates never match across boards. The recorded
108-key-to-40% fixture maps every alphanumeric: 40 source keys carry directly,
10 digits adapt to the target's established non-base layer, and the remaining
58 keys become explicit worklist items. Existing target-layer positions provide
structured suggestions for F-row, navigation, and numpad keys without silently
placing them. Ambiguous homes, assignment collisions, spoke-native entries, and
QMK keyboard/user custom ranges are never guessed; macros, encoders, and
lighting remain explicitly deferred by this keymap-first slice. The validated
target-shaped profile, transfer report, and structured worklist are available
through authenticated `POST /api/hub/overlay`. Red proof failed on the missing
overlay module; focused tests passed 12/12. Full verification passed 720 Python
tests, 185 web tests, compile and JavaScript syntax gates, and sdist/wheel build.
This closes H4's fixture-backed acceptance boundary; H5 owns its editing and
worklist UX.

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

### H5 implementation contract — one editor, honest overlay worklist

Status: bounded planning was authorized by the owner on 2026-08-16. The owner
subsequently authorized H5a implementation, which landed in this commit. H5b
and every later H5 slice still require their own explicit go.

H5 extends the existing Keymap workspace rather than introducing a second
configurator. The board stays the primary surface, the assignment palette stays
immediate, and technical matrix/raw values stay behind disclosure. A generic
Vial/VIA document uses the hub profile in memory; the established AM workspace
continues to keep AM-native `state.config` and `current.json` as settled in H1.
Both feed one editor view model, so H5 does not migrate the AM store or create a
second persistent profile database.

#### H5 invariants and non-goals

1. Loading, editing, overlaying, saving, and preflighting are mutation-free for
   hardware. Only the existing typed Vial/VIA write endpoints may open an
   approved writable session, after their exact confirmation phrase is typed.
2. Geometry is ephemeral endpoint/definition evidence, not hub content.
   Render only the active KLE projection returned from the same snapshot as the
   profile. Never infer physical positions from matrix coordinates and never
   store raw-HID endpoint paths or VIA definitions in a hub file.
3. H5 is keymap-first. It preserves target macros and lighting byte-for-byte,
   exposes macro-slot assignments already present in the target profile, and
   leaves generic macro authoring to a later bounded slice. H6 owns lighting.
4. Existing AM read/edit/write, macro, lighting, Library, undo, and portable
   JSON behavior must remain unchanged. H7 owns visual rebranding; H5 may add
   the controls needed for this workflow but does not redesign the application.
5. VIA remains bounded user-imported definition resolution. H5 adds a definition
   file chooser; it does not fetch definitions, flash firmware, or claim bare
   QMK/XAP support.

#### H5a — editor document, geometry, and read-only connection seam

Landing evidence (2026-08-16): complete. `hub_keymap_state.js` is a pure,
immutable generic document reducer; `app.js` adapts AM-native and hub documents
into the existing Keymap workspace. Vial/VIA reads return endpoint metadata,
profile, and canonical-key geometry from one snapshot. Devices discovery keeps
AM, Vial, and VIA interfaces explicit; VIA waits for a user-imported definition.
Authenticated `/api/hub/open` and `/api/hub/save` use the canonical Python
loader/dumper, so endpoint paths, imported definitions, and geometry stay out of
saved hub profiles. New H5a hardware flow is read-only and sends no setter.
Verification passed 725 Python tests, 195 web tests, compile and JavaScript
checks, and `uv build`. The in-app browser runtime was unavailable, so no extra
interactive smoke pass was recorded.


1. Add a pure browser module `am_configurator/web/hub_keymap_state.js`. Its
   immutable reducer owns a generic document's validated profile, target binding
   (ecosystem/address plus in-memory VIA definition when applicable), active
   layer/key, dirty flag, undo/redo, transfer report, and worklist. No DOM,
   transport, or global application state belongs in the module.
2. Add one adapter in `app.js` that projects either AM `state.config` or the
   generic hub document into the existing Keymap screen contract: layers,
   physical keys, current codes, capabilities, selection, mutation, and save/
   write actions. Do not convert the AM working document into hub form merely
   to edit it.
3. Extend the existing authenticated Vial/VIA read responses, without adding a
   second hardware read, to return `{device, profile, layout}`. `layout` is the
   active projected key list from that exact snapshot; every item carries
   canonical hub key identity plus `x`, `y`, `width`, `height`, and rotation
   fields. Vial uses its embedded definition. VIA validates the user-imported
   definition and retains it only in the browser document target binding.
4. The Devices dialog discovers AM, Vial, and VIA candidates with explicit
   ecosystem/capability labels. It may prefer a proved AM-native endpoint, but
   must not deduplicate interfaces that cannot be proven to be the same physical
   device. Reading a Vial board is direct. Reading VIA first requires choosing
   a JSON definition and stops before open if VID/PID does not match.
5. Add authenticated canonical document boundaries backed by
   `loads_hub_profile`/`dumps_hub_profile`: open an untrusted `.hub.json` into a
   validated profile and save the current generic document as canonical UTF-8.
   Browser `JSON.parse`/`JSON.stringify` is not the on-disk source of truth.
6. Tests cover immutable reducer operations, AM adapter parity, active-layout
   geometry, wrong VIA definition before open, read-only command allowlists,
   canonical open/save, endpoint/definition data staying out of saved profiles,
   and no hardware setter during every H5a route.

#### H5b — board, layers, and keycode palette

1. Reuse the current board-first Keymap layout. Generic keys render from the
   H5a geometry by canonical identity rather than AM flat index. Layer tabs,
   key selection, immediate palette assignment, focus restoration, technical
   labels, and raw-code disclosure retain the existing interaction contract.
2. Add a separately tested portable QMK palette module. It owns labels and
   categories for core basic/HID keys, modifiers, function/navigation/keypad,
   layer controls, and macro slots the target capability exposes. Filter by the
   target's reported keycode spec where present. Build it from in-repo surveyed
   facts; do not copy the GPL VIA/Vial GUI catalogs. Unknown existing 16-bit
   codes remain visible and round-trip through Advanced; the normal palette
   never invents per-board `QK_KB`/`QK_USER` values.
3. One palette click changes the open document immediately through one undo
   checkpoint; it never writes the keyboard. Preserve complete target layers,
   omitted sections, unknown keycodes, profile identity/capabilities, and
   provenance. Generic undo/redo snapshots the hub profile; AM keeps its current
   history implementation.
4. Saving a generic document produces `.hub.json`; Save to Library remains AM
   only until Library gains a hub-profile artifact contract. Say that plainly
   rather than converting or silently omitting generic data.
5. Browser tests cover keyboard navigation, selected-key focus after rerender,
   every palette category, raw 16-bit preservation, per-board warning labels,
   layer bounds, undo/redo, narrow-window stacking, reduced motion, and the
   existing contrast/type/focus floors.

#### H5c — overlay review and worklist resolution

1. Route hub import through H4 whenever a target document is open. For AM,
   export the current target to hub, run `/api/hub/overlay`, then translate the
   accepted target-shaped result back through `/api/hub/apply`. For Vial/VIA,
   apply the returned target-shaped profile directly. The operation creates one
   document undo checkpoint and never writes hardware.
2. Enrich H4's internal worklist view (not the transfer-report schema) so each
   key item carries structured source `{layer, key, code}` plus target
   suggestions. Do not make the browser parse display paths to recover data.
3. Make the report and worklist first-class on Keymap: counts first; adapted and
   unresolved items next to the board; plain reasons; no raw JSON log. A
   worklist item offers `Use suggestion`, `Choose a key`, and `Leave out`.
   Applying a choice edits the target profile and changes that report item to
   `adapted` with a reason; leaving it out remains `dropped`. Every resolution
   is independently undoable.
4. Default arrangement uses the existing editor grid: board/palette primary and
   worklist in the inspector rail, stacking between board and palette at the
   current narrow breakpoint. No Basic/Advanced mode split. Technical source
   path, matrix identity, and raw keycode stay in a disclosure.
5. Acceptance fixture is the landed 108→40% record: all 36 alphanumerics appear
   on the correct target layer/key with zero user effort; counts remain 40
   carried, 10 adapted, 58 unresolved; F-row/navigation/numpad suggestions are
   actionable; coordinates, ambiguous homes, collisions, and custom keycodes
   are never auto-placed.

#### H5d — typed generic write UX and closure

1. A generic file is not writable until it is overlaid onto or freshly read
   from a connected target. Keep the connection-scoped address and VIA
   definition only in the live document binding. A rescan/replug invalidates UI
   readiness; backend endpoint reproof remains authoritative.
2. Preflight through the existing Vial/VIA endpoint every time the user chooses
   Write. Show exact planned keymap/macro byte counts, transfer verdict counts,
   endpoint/model, and the backend-supplied confirmation phrase. Confirmation
   comparison is exact and case-sensitive; do not reuse AM's product-ID
   uppercasing rule.
3. Extend Vial preflight's read-only result with physical unlock matrix keys and
   resolve them through the same layout, so the dialog can name/mark the keys
   before execution. Preflight must not start unlock. After confirmation, the
   write request redoes preparation, then starts the volatile unlock handshake.
   VIA shows no unlock instruction.
4. Disable cancel only after an accepted-write-capable request begins. Success
   reports accepted byte counts and exact read-back. If the backend reports
   possible accepted bytes, never offer blind retry; offer a fresh read/verify
   action and explain that the keyboard may already contain the change.
5. Keep canonical backup available in the dialog. Applying an overlay or
   editing a document always says the keyboard is unchanged until Write.
6. Fake-HID and browser tests prove: no setter on discovery/read/edit/import/
   overlay/preflight/wrong confirmation; exact phrases and target bindings;
   Vial unlock guidance before request; replug and definition change stop before
   setter; accepted-byte failure does not retry; exact success read-back; AM
   write behavior unchanged. Run the repository verification entry point.
   Automated H5 tests never write a physical keyboard; any later live proof is
   a new explicit owner gate.

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
