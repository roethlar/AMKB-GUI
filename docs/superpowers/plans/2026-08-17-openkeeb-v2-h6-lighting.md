# OpenKeeb v2 H6 — capability-honest Vial/VIA lighting through the hub

Status: **APPROVED for continuous fixture-backed H6a–H6e implementation** by
the owner on 2026-08-17 (`go`). Product code, tests, records, rendered fake-HID
verification, native verification, and local commits may proceed without
per-slice approval under the standing technical delegation in
`.agents/decisions.md`. H6f physical hardware activity, push, release, public
identifiers, and spending remain separately owner-gated.

H6a fixture-backed landing, 2026-08-17: hub profiles now validate exact
schema-v1 input, migrate deterministically, and serialize canonical schema v2.
The pure lighting model owns bounded independent surfaces, native channel
ranges, stable per-key identities, animations, and explicit
carried/adapted/dropped transfer findings. Pure Vial/VialRGB and VIA codecs
extract only definition/device-proved capabilities and produce closed
persistent command plans without opening HID; target lighting survives omitted
or incompatible source data, and VialRGB direct effect 1 remains excluded from
persistent plans. The pinned survey records protocol evidence and a conservative
30-report/second application ceiling. The schema test first failed while the
module was absent, then the 128-test focused suite passed; final verification
passed 751 Python tests, 223 web tests, Python compilation, every JavaScript
syntax gate, package build, and `git diff --check`. No transport setter or
hardware access landed. H6b read-only fake-HID snapshots are next.

H6b fixture-backed landing, 2026-08-17: Vial keyboard-ID feature flags now
survive discovery and same-handle identity reproof. Mutation-refusing raw-HID
sessions admit top-level lighting GET only for definition/protocol-proved legacy
value IDs, VialRGB subcommands, or VIA channel/command pairs; arbitrary GET,
SET `0x07`, SAVE `0x09`, setters, and unlock-start/poll remain refused. One
snapshot now carries keymap, macros, current native lighting state, active
layout, and ephemeral `lighting_geometry`. VialRGB additionally gates on
protocol, feature flag, embedded definition, and GET_INFO version; effect pages
and LED counts are bounded before allocation, while GET_LED_INFO supplies
device-proved pixel identities and geometry. VIA per-key reads use only unique
active-layout `li` indexes from the imported definition; hostile, duplicate, or
oversized indexes stop before any lighting GET. Unknown lighting definitions
return an explicit empty capability and no lighting command. The VialRGB and
VIA snapshot tests first failed on absent feature/state transport, then focused
and full verification passed 760 Python tests, 223 web tests, compilation,
every JavaScript syntax gate, package build, and `git diff --check`. No hardware
was opened outside injected fake HID and no mutation occurred. H6c persistent
fake-HID writes are next.

H6c fixture-backed landing, 2026-08-17: endpoint-approved Vial/VIA sessions now
admit only the exact planned lighting GET/SET/SAVE prefixes while refusing raw
`0x07`, `0x08`, and `0x09` calls without an explicit prefix. Prepared writes
carry the pure lighting plan, current-lighting backup, canonical target
fingerprint, combined transfer report, and setter/save counts. Execution
re-proves feature flags, definition/protocol/layout/capability/state/geometry on
the transmitting handle, sends only planned global or declared-index per-key
changes, reads back exactly before SAVE, and reports possibly accepted lighting
changes/saves across setter timeout, partial write, read-back mismatch/error,
and SAVE failure. Server preflight, success, and HTTP 409 responses expose the
same evidence. Fake HID proves lighting-only VIA writes do not depend on a
keymap write, per-key writes use only channel 0 and the declared LED index, and
wrong confirmation/stale evidence/unplanned commands transmit no setter. The
lighting-only regression test failed when the old keymap dependency was
temporarily restored, then passed with the fix. Full verification passed 768
Python tests, 223 web tests, Python compilation, every JavaScript syntax gate,
package build, and `git diff --check`. No physical keyboard was opened and no
hardware mutation occurred.

H6d fixture-backed landing, 2026-08-17: the generic Lighting Studio projects
only proved surface controls and current-target geometry, preserves exact pixel
identities through the existing composer, keeps edits in shared document
undo/redo, supports lighting-only schema-v2 documents, and extends persistent
write review with lighting change/save counts, target-lighting backup, target
fingerprint, unlock suppression for lighting-only writes, and possible-acceptance
copy. Rendered testing additionally made read-success counts optional, replaced
AM-only and shallow-discovery capability copy, made read/verify mismatch copy
profile-wide, and cleared stale identity/target controls for unsupported
lighting. Chrome rendered the supported editor, persistent preflight,
possibly-accepted write/read-verify recovery, and unsupported-capability state
at 1000×680, 1280×800, and 1600×1000. All states had exact target/confirmation
copy, no page-level horizontal overflow, and no console warnings/errors; the
isolated fake server recorded 6 reads, 4 preflights, and 2 confirmed write
attempts. The H6d bite proof fails under the old required-keymap assumption and
passes with the fix. Full verification passes 768 Python tests, 234 web tests,
Python compilation, every JavaScript syntax gate, package build, and
`git diff --check`. No physical keyboard was opened and no hardware mutation
occurred. H6e volatile VialRGB streaming is next.

## Objective

Make Vial and VIA lighting first-class OpenKeeb hub data without weakening the
existing document/write boundary:

- read only the lighting capabilities and state the selected firmware proves;
- preserve exact effect, color, brightness, speed, and per-key state in the hub;
- edit only controls the target actually exposes;
- write persistent lighting through the existing endpoint-bound confirmation
  gate, narrow command allowlist, accepted-change accounting, and exact
  read-back;
- play hub animations on VialRGB as an explicitly started, volatile host stream
  that never claims persistence;
- keep current Angry Miao lighting behavior byte-for-byte unchanged.

H6 does not add firmware flashing, automatic definition downloads, bare-QMK or
XAP support, arbitrary VIA custom-menu execution, generic macro authoring,
panel/text authoring, or a physical hardware write.

## Authoritative boundaries

- `AGENTS.md` and `.agents/repo-guidance.md` govern verification and device
  safety. Automated tests and rendered smokes must use fake HID and must never
  write a physical keyboard.
- `.agents/decisions.md`, 2026-08-15 and 2026-08-16, defines the AM/Vial/VIA
  hub, capability honesty, continuous technical delegation, and separately
  gated hardware writes.
- `docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md` defines
  H6 as effect/color/speed for Vial/VIA, VialRGB per-LED streaming, and
  definition-backed geometry.
- `docs/design/2026-08-15-h0-keycode-capability-survey.md` and
  `docs/design/2026-08-15-hub-schema-draft.md` are background evidence. Their
  lighting section is provisional and is superseded by this plan where the
  current implementation or refreshed upstream evidence is more specific.
- Vial/VIA/QMK GPL sources are protocol evidence only. Do not copy source code
  or tables into this MIT repository without a separate license decision and
  required notices. Protocol constants, packet shapes, ranges, and
  device-returned/definition-returned values are implemented independently.

## Pinned protocol evidence

H6a records these exact pins in a technical survey before product code lands:

- `vial-kb/vial-gui` `aef8222a2d0429a183b2ed692d5f9efcfd383f08`;
- `vial-kb/vial-qmk` `dd43959ae5c08d8a28d38a1acf7b04e86b14a344`;
- MIT reference `Vil4/vial_rgb_direct_control`
  `b139cb2ef06f7cb0dd9ef0cc466d22405ef55799`;
- `the-via/app` `38da806d9fce44940e33ce7f796226089f815953`;
- `the-via/reader` `c26009992a7a2e9776720ebf5644a50f8e92c7a5`;
- `the-via/keyboards` `cc2d06a238661caa005125e0d6248b54781721ab`;
- `qmk/qmk_firmware` `96c3e85e59b1acfa0d43c32a224ba2b26123fe3d`.

The survey must cite file paths and the facts consumed; it must not depend on a
developer's out-of-repo checkout after the survey is committed.

## Current repository seams

- `am_configurator/hub_profile.py` schema version 1 can validate one static
  value, one hardware effect, and AM animations, but cannot losslessly express
  multiple addressable lighting surfaces or their control ranges.
- `am_configurator/hub_vial.py` and `am_configurator/hub_via.py` currently emit
  keymap/macro capabilities only. Their write plans ignore lighting.
- `am_configurator/hub_via.py` validates layout alternatives but intentionally
  ignores definition `lighting`, `menus`, and KLE LED index (`li`) metadata.
- `am_configurator/hid_transport.py` read-only sessions do not permit top-level
  lighting GET `0x08`; approved VIA writes permit only keymap/macro setters.
- `am_configurator/vial_transport.py` and `via_transport.py` already bind an
  exact endpoint, definition/firmware evidence, target snapshot, pure write
  plan, typed confirmation, same-handle reproof, accepted-byte accounting, and
  exact read-back. H6 extends these boundaries; it does not create a bypass.
- `am_configurator/web/app.js` preserves generic hub documents but explicitly
  disables generic Lighting. The existing Angry Miao Lighting Studio remains
  the shipped composition/rendering surface and must not be forked into a
  second visual language.

## Canonical lighting model

### Schema migration

H6a advances the hub to `schema_version: 2` because version 1 cannot represent
two independent surfaces such as key backlight plus underglow.

`loads_hub_profile` and `validate_hub_profile` accept the exact known version-1
shape and normalize it to version 2. `dumps_hub_profile` and every spoke builder
emit version 2 only. Unknown version-1 fields remain errors; migration is not a
permissive compatibility path.

Version-1 migration rules are deterministic:

- `hardware_effect` becomes one surface state, keyed by its generation;
- global/per-key static state attaches to the one compatible generated surface;
- AM animations become `am_frames` surface animations;
- version-1 animation pixel order is preserved with opaque `LED_I<n>` pixel
  identities when no key identity exists;
- ambiguous version-1 combinations fail with a plain error instead of choosing
  a target surface.

Round-trip fixtures prove all H1-H5 hub examples still load and canonicalize.

### Capability surfaces

`capabilities.lighting.surfaces` is the only version-2 capability truth. Each
bounded item contains:

- `id`: profile-local stable identifier, unique in the profile;
- `role`: `keys`, `underglow`, `backlight`, `panel`, or `accent`;
- `generation`: `am_frames`, `qmk_backlight`, `qmk_rgblight`,
  `qmk_rgb_matrix`, or `vialrgb`;
- supported effects as device/definition-returned integer IDs plus an optional
  OpenKeeb semantic key (`off`, `solid`, `breathing`, and other separately
  surveyed unambiguous values);
- independently optional `brightness`, `speed`, and `color` controls, including
  native integer bounds and color space;
- independently optional `per_key` support with mapped pixel count;
- independently optional `stream` descriptor containing protocol, pixel count,
  maximum chunk size, and `volatile: true`.

The schema rejects duplicate surface IDs, duplicate effect IDs, invalid ranges,
unsupported semantic keys, unbounded pixel counts, and a stream descriptor on
anything except VialRGB.

`lighting.surfaces` carries current/authored state by surface ID. Values remain
in the surface's declared native ranges so a read/write round trip is exact.
Cross-target normalization is derived from the source and target capability
ranges; no second normalized value is stored.

`lighting.animations` keeps RGB frames but adds:

- `surface_id`;
- `pixel_ids`, exactly one stable identity per frame entry;
- existing `frame_ms`, `brightness`, and `geometry_seam` placement.

Key-associated pixels use the hub key identity; other LEDs use `LED_I<n>`.
Coordinates and raw-HID addresses remain ephemeral target evidence and never
enter the hub file.

### Transfer rules

Persistent lighting planning is pure and target-shaped:

1. Match source and target surface by role, then generation.
2. Carry the native effect ID only when the generation and supported ID match.
3. Otherwise adapt only an unambiguous surveyed semantic effect present on the
   target. At minimum `off` and `solid` are cross-generation mappings.
4. Normalize brightness and speed across declared ranges; report `adapted` when
   the native target value differs. Never guess a range absent from evidence.
5. Carry HSV color only when the target declares it.
6. Map per-key colors by canonical key identity. Opaque or missing pixel IDs,
   duplicate targets, auxiliary LEDs, and unsupported per-key controls become
   explicit dropped report items.
7. Animations stream only to an exact compatible VialRGB target. H6 does not
   resample an animation across different pixel identity sets; it reports the
   mismatch and leaves the keyboard unchanged.

The generic H4 overlay continues to preserve target lighting when the imported
profile omits lighting. When lighting is present, H6 extends its transfer report
with the rules above; it never silently replaces an incompatible target.

## Protocol contracts

### Vial and VialRGB

Vial lighting capability requires embedded-definition evidence. Supported
definition values are the surveyed `qmk_backlight`, `qmk_rgblight`,
`qmk_backlight_rgblight`, and `vialrgb` values. Unknown values produce no
lighting capability and no lighting command.

Legacy QMK lighting uses top-level raw-HID GET `0x08`, SET `0x07`, and SAVE
`0x09`, with only the surveyed brightness/effect/speed/color value IDs. H6 never
sends a definition-derived arbitrary value ID.

VialRGB additionally requires all of:

- Vial protocol at least 4;
- the keyboard-ID feature flag indicating VialRGB;
- embedded definition `lighting: vialrgb`;
- VialRGB GET_INFO protocol version exactly 1.

Read-only discovery then obtains maximum brightness, current mode/speed/HSV,
the paginated supported-effect IDs, and—only when direct mode is supported—the
LED count and one GET_LED_INFO record per index. Counts are bounded before
allocation.

VialRGB direct reports contain at most nine sequential HSV pixels in one
32-byte report. Direct effect ID 1 is volatile stream ownership: the persistent
writer must refuse to save it as an ordinary effect.

### VIA

VIA capability is definition-derived and protocol-gated:

- Version-2 definitions support only the surveyed built-in lighting values and
  their declared effect lists.
- Protocol 11+ version-3 definitions support only recognized QMK lighting
  common menus or inline controls that structurally match the same closed
  channel/command/type/range contracts.
- H6 recognizes `qmk_backlight`, `qmk_rgblight`, `qmk_rgb_matrix`, and the
  combined built-in menu. Unknown common-menu names, vendor channels, labels,
  condition expressions, or controls remain preserved in the imported
  definition but are not executable by OpenKeeb.
- GET uses top-level `0x08`; SET uses `0x07`; SAVE uses `0x09`. Version-3 save
  carries the exact recognized channel. Version-2 save carries no channel.
- Per-key RGB is allowed only for protocol 11+, a validated selected-layout
  `li` mapping, and the surveyed channel 0/command 1 packet. Reads and writes use
  declared LED indexes only, one index per request in H6; SAVE carries channel
  0. Missing indexes are not inferred.

The canonical imported-definition hash and active layout options bind all VIA
lighting evidence and plans exactly as they bind keymaps and macros.

## Geometry ownership

Every read response returns a separate ephemeral `lighting_geometry` list.
Each item contains pixel ID, device LED index, normalized x/y, raw flags where
available, and optional canonical key identity. It is never serialized by
`dumps_hub_profile`.

- VialRGB x/y, flags, and row/column come from firmware GET_LED_INFO and are
  device-proven. A valid row/column links the LED to a matrix key; other LEDs
  remain auxiliary. The embedded Vial layout is not treated as an LED map.
- VIA uses only the active KLE key geometry plus its validated `li` value. This
  is `user_import` definition evidence, not device-proven geometry. Duplicate,
  negative, oversized, or option-inactive LED indexes fail before HID open or
  produce no per-key capability as appropriate.
- A VIA definition without `li` may still expose global effect controls, but it
  cannot expose a per-key painter.
- AM geometry and its current target adapters are unchanged.

## Write-safety contract

Persistent lighting extends the existing generic Vial/VIA preflight and Write
flow rather than adding a hidden mutation route.

Preflight is read-only and returns:

- exact endpoint, USB, firmware/definition, protocol, layout, and capability
  fingerprint;
- canonical backup profile containing the current lighting state;
- field/pixel transfer verdicts and exact planned setter/save counts;
- the existing exact case-sensitive confirmation phrase;
- zero transmitted setters and zero unlock-start commands.

Execution re-enumerates the same endpoint and keeps one handle through identity,
capability, current-state, plan, write, save, and read-back. It sends only
planned `0x07` values and, after exact volatile read-back, one required `0x09`
save per affected channel. Omitted or unchanged surfaces send nothing.

Approved sessions gain a closed lighting command surface; do not return the
unrestricted raw session to a new caller. Keymap/macro setters, reset,
bootloader, keyboard-value setters, arbitrary custom menu commands, and unknown
lighting IDs remain locally refused when the operation is lighting-only.

Receipts and failures count accepted lighting fields and accepted pixel values
separately from keymap/macro bytes. A timeout after a setter is a possible
accepted change. The UI offers only a fresh read/verify; it never blindly
retries or claims rollback.

### Volatile VialRGB streaming

Streaming has separate authenticated preflight/start/status/stop routes and a
server-owned worker that alone holds the HID handle. It is never reachable from
ordinary Save or Write.

Start requires the exact Vial target confirmation, a fresh endpoint/capability
reproof, a compatible hub animation, and a current mode other than direct. The
worker captures current mode/speed/HSV, switches to direct without SAVE, sends
the first complete frame, then delta-skips unchanged nine-pixel chunks.

Scheduling has no backlog: frame deadlines use a monotonic clock, late frames
are skipped, and the report-rate ceiling plus animation `frame_ms` determine the
effective rate. H6a records one conservative application ceiling; it is not
presented as a firmware guarantee.

Any timeout, endpoint change, app shutdown, explicit stop, or maximum-duration
expiry stops new frames and attempts exactly one same-handle restoration of the
captured non-direct mode without SAVE. A failed restoration is reported plainly
as possibly still in direct mode; no reconnect/retry loop is allowed. Starting
while the keyboard already reports direct mode is refused because exact prior
per-pixel colors cannot be read back.

The UI states that streaming is a live preview, runs only while OpenKeeb remains
connected, is not stored in keyboard EEPROM, and must be stopped before a
persistent lighting write.

## Implementation slices

### H6a — refreshed survey, schema v2, pure capability codecs

Files:

- add `docs/design/2026-08-17-h6-lighting-capability-survey.md`;
- modify `am_configurator/hub_profile.py`;
- add `am_configurator/hub_lighting.py`;
- add `am_configurator/vial_lighting.py` and
  `am_configurator/via_lighting.py`;
- modify `am_configurator/hub_vial.py`, `hub_via.py`, and `hub_overlay.py`;
- add/modify `tests/test_hub_profile.py`, `test_hub_lighting.py`,
  `test_hub_vial.py`, `test_hub_via.py`, and `test_hub_overlay.py` plus bounded
  fixtures.

Work:

1. Commit the pinned survey and independent protocol facts.
2. Land deterministic version-1-to-version-2 migration and canonical version-2
   serialization.
3. Implement bounded surface validators, effect semantics, geometry records,
   Vial/VIA capability extraction, and pure transfer/write plans with no HID
   dependency.
4. Cover hostile definitions, counts, duplicate controls/indexes, ambiguous
   effects, range adaptation, omitted lighting preservation, and exact
   round-trip.

Acceptance: a new schema/capability test first fails without H6a; all focused
tests pass; no transport setter exists in the slice.

### H6b — read-only snapshots, capability truth, and geometry

Files:

- modify `am_configurator/hid_transport.py`, `vial_keymap.py`,
  `vial_transport.py`, `via_transport.py`, and `server.py`;
- modify `tests/test_vial_keymap.py`, `test_vial_transport.py`,
  `test_via_transport.py`, and server API tests.

Work:

1. Preserve the Vial keyboard-ID feature flags instead of discarding byte 12.
2. Add top-level lighting GET to mutation-refusing sessions; add no setter.
3. Extend live snapshots and `/api/hub/vial/read` and `/api/hub/via/read` with
   capability-derived hub lighting plus ephemeral `lighting_geometry`.
4. Keep one-snapshot consistency: keymap, macros, lighting, active layout, and
   geometry come from the same connection and definition hash.
5. Return explicit no-lighting capability for unsupported/unknown definitions,
   never a guessed default.

Acceptance: fake HID proves read paths transmit only allowlisted GETs and no
`0x07`, `0x09`, unlock-start, keymap setter, or other mutation.

### H6c — persistent fake-HID write transport

Files:

- modify `am_configurator/hid_transport.py`, `vial_transport.py`,
  `via_transport.py`, and `server.py`;
- modify write/preflight tests and accepted-write API assertions.

Work:

1. Extend existing prepared plans and receipts with lighting state, backup,
   setter/save counts, and target-match fingerprint.
2. Add closed approved lighting session facades and exact command/value/channel
   allowlists.
3. Reprove target capability on the transmitting handle, send only changed
   fields/pixels, read back before and after SAVE, and count possible accepted
   changes on every failure edge.
4. Extend authenticated generic preflight/write responses and H5d failure
   semantics without changing AM writes.

Acceptance: fake HID covers wrong confirmation, forged approval, stale endpoint,
definition hash, layout option, Vial flag/protocol, effect list, control range,
LED mapping, partial acceptance, save failure, read-back mismatch, and dangerous
command refusal. No physical backend is opened.

### H6d — generic Lighting Studio and persistent Write UX

Files:

- add `am_configurator/web/hub_lighting_state.js`;
- modify `hub_keymap_state.js`, `lighting_targets.js`, `lighting_workspace.js`,
  `lighting_composer.js`, `app.js`, `index.html`, and `styles.css`;
- add `tests/web/hub_lighting_state.test.js` and extend lighting, hub-editor, and
  generic-write shell tests.

Work:

1. Make lighting mutations part of the immutable generic document history and
   canonical `.hub.json` save; preserve unrelated keymap/macro/profile fields.
2. Enable the Lighting route only when the profile has proved surfaces. Render
   effect/color/brightness/speed controls independently by capability.
3. Render per-key painting only from ephemeral lighting geometry; disclose
   whether evidence is device-proven VialRGB or user-imported VIA definition.
4. Adapt the existing local media/pattern composer to a dynamic target
   descriptor and produce hub animations with exact pixel identities. Do not
   create a second composer or route.
5. Extend the existing generic Write dialog with lighting field/pixel/save
   counts, backup, transfer verdicts, exact confirmation, and fresh verify after
   possible acceptance.

Acceptance: Node tests cover capability-gated controls, immutable undo/redo,
unknown control refusal, pixel identity preservation, target rescan
invalidation, document-only edits, canonical save, and zero setter before
confirmed Write. Existing AM lighting tests remain unchanged and green.

### H6e — VialRGB volatile streaming worker and UX

Files:

- add `am_configurator/vial_rgb_stream.py`;
- modify `hid_transport.py`, `vial_transport.py`, `server.py`, `app.js`, and
  generic lighting state/UI files;
- add focused Python worker/API tests and browser shell/state tests.

Work:

1. Implement authenticated preflight/start/status/stop with one opaque token,
   one worker, one endpoint-bound handle, fake clock injection, maximum duration,
   and app-shutdown cancellation.
2. Implement nine-pixel chunking, deterministic RGB-to-HSV8 conversion,
   delta-skip, rate ceiling, deadline skipping, no setter retry, and exact
   restoration rules.
3. Add explicit Preview on keyboard / Stop preview UX, confirmation dialog,
   volatile-state disclosure, progress/status, and persistent-Write exclusion.

Acceptance: fake HID proves no SAVE during stream, no start from direct mode,
all first-frame pixels transmitted, unchanged chunks skipped, late frames not
queued, stop/error/shutdown restore once, endpoint change invalidates token,
failed restore is reported, and no physical keyboard is accessed.

### H6f — separately authorized live evidence

H6a through H6e can close as fixture-backed. A live proof needs a new owner
authorization naming the exact Vial/VIA keyboard and exact write/stream actions.

If authorized:

1. Save a complete read-only backup and record endpoint, firmware/definition,
   capability, geometry, mode, and hashes/counts.
2. First persist a byte-identical current lighting plan, type the exact phrase,
   send only listed lighting setters/SAVE, and prove exact immediate and
   unplug/replug read-back.
3. For VialRGB, run one short bounded animation without SAVE, stop it, and prove
   the captured mode/speed/HSV was restored.
4. Record every transmitted command class, accepted count, read-back, and
   persistence result. Stop on any mismatch; do not retry.

No live proof is a prerequisite for claiming fixture-backed H6a-H6e complete.

## Verification

Every implementation slice runs focused tests and proves at least one new test
bites by reverting the fix, observing failure, and restoring it. Final closure
runs the complete entry point in `.agents/repo-guidance.md`:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_workspace.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/hub_keymap_state.js
node --check am_configurator/web/hub_keycode_palette.js
node --check am_configurator/web/app.js
uv build
```

Add `node --check am_configurator/web/hub_lighting_state.js` after that file
lands. Run the supported macOS frozen build, `--smoke-test`, and
`--native-policy-smoke` before H6 closure because the slice changes native HID
policy. Render fake-device Lighting, persistent preflight, possible-accepted
failure, streaming start/stop, and unsupported-capability states at 1000×680,
1280×800, and 1600×1000. Record console errors, hardware request counts, page
overflow, and confirmation behavior. All rendered checks use injected fake HID.

## Completion criteria

H6a through H6e are complete only when:

- version-1 hub files migrate deterministically and version-2 files round-trip;
- Vial/VIA reads expose only proved lighting state and geometry;
- unsupported controls are absent, not cosmetic-disabled guesses;
- generic document edits and animation authoring never mutate hardware;
- persistent writes are endpoint/capability-bound, confirmed, narrowly
  allowlisted, saved, and exactly read back with possible-acceptance accounting;
- VialRGB streaming is explicit, volatile, rate-bounded, cancellable, and
  restoration-aware;
- AM lighting behavior and all pre-H6 tests remain green;
- the full and native verification contracts pass;
- records and this plan identify fixture-backed versus separately authorized
  live evidence without implying a physical write occurred.
