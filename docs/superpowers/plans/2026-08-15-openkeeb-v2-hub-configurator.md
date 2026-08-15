# OpenKeeb v2 — full configurator through one hub format

Status: DRAFT, awaiting owner approval (2026-08-15). No slice in this plan is
authorized until the owner approves the plan, and each slice then needs its
own go. Supersedes `docs/superpowers/plans/2026-08-08-openkeeb-v2.md` in part:
the companion-firmware lane and the OpenRGB lane are dead (owner ruling
2026-08-15, `.agents/decisions.md`); everything that plan settled about
identity, migration, naming, licensing, and device safety still stands and is
not restated here.

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
