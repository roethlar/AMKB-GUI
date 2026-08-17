# Repository State

## Now

- **v1 is done and locked; all new work is OpenKeeb v2 (2026-08-14):** owner
  ruling, recorded in `.agents/decisions.md`. The v1 default branch is frozen
  (no new feature work or releases; owner-directed fixes only). All new work
  lands on `v2/openkeeb`.

- **Release-lane assets carry no build attestation.** As of `2a80cf0`,
  `.github/workflows/release.yml` contains no attestation step while
  `.github/workflows/desktop.yml` attests candidate builds; README and install
  guidance accurately distinguish the two lanes. Adding release-lane
  attestation remains an open option, not a decision.

- **H7 OpenKeeb branding/UI overhaul is active under full owner delegation:**
  complete element-level repositioning, not a rename, restyle, or pilot.
  Page order, prototype form, visual arrangements, implementation slicing, and
  technical details belong to the working agent; there are no phase-by-phase
  owner check-ins. The cold implementation plan is
  `docs/superpowers/plans/2026-08-17-openkeeb-branding-overhaul.md`. Public/deep
  identifiers, spending, release/publication, destructive history changes, and
  physical keyboard writes remain separately owner-gated.

## Next

- **OpenKeeb v2 implementation is active under the approved hub-configurator
  plan:** H0 through H4 are complete. H3 (the VIA spoke) has bounded
  user-imported definition resolution and generic read-only raw-HID transport.
  It handles active layout options without guessing, VIA 7's per-key fallback,
  VIA 8+ keymap/macro buffers, VIA 11's macro-delay dialect, and VIA 13's stated
  keycode spec behind a mutation-refusing command surface and authenticated
  local API. The owner's Mode Eighty M80H V2 passed that production path live:
  exact public `m80v2h.json` identity, active option 0/87 physical keys, four
  layers/816 keymap bytes, and 16 macro slots/169 bytes with three populated
  macros decoded into a complete hub profile. H3a pure buffer/transfer-report
  planning is complete: it preserves
  omitted target sections, reports unsupported mappings, gates keycode-spec
  mismatch, and encodes both VIA macro dialects within device budgets without
  opening HID. H3b fake-HID write transport is complete: exact
  `VIA <definition> <VID>:<PID>` confirmation, endpoint/USB/definition/protocol/
  layout/capacity binding, same-handle reproof, three-command setter allowlist,
  protocol-correct writes, accepted-byte accounting, exact read-back, and
  authenticated preflight/write API. H3c then passed the separately authorized
  live M80H proof: exact `VIA M80V2 H 00DE:0083` confirmation; only protocol-9
  `0x13` keymap-buffer and `0x0F` macro-buffer setters; 816 keymap and 169 macro
  bytes accepted with exact immediate read-back; both buffers persisted with
  exact SHA-256 hashes after unplug/replug through a fresh read-only endpoint.
  Future hardware writes remain separately owner-gated. H2's
  generic Vial
  transport and local API are wired to the hub codec with read-only command
  enforcement, endpoint/firmware/definition reproof, exact typed confirmation,
  physical unlock, and exact read-back. The owner's Neon 80 qualified the full
  path on hardware: its live profile was planned back byte-identically, 720
  keymap and 6,677 macro bytes were written and read back exactly, unplug/replug
  invalidated the old endpoint, both buffers persisted, and the board returned
  locked. H4's pure keymap-first overlay engine now returns a validated
  target-shaped profile, carried/adapted/dropped report, and structured
  worklist through the authenticated local API without opening transport. Its
  108-key-to-40% fixture carries 40 keys, adapts 10 digits to the target's
  established layer, and surfaces 58 homeless keys with deterministic
  suggestions where target conventions exist; matrix coordinates, ambiguous
  homes, collisions, and per-board custom codes are never guessed. H5 now has
  a bounded keymap-editor/worklist contract: preserve the AM-native workspace,
  add an in-memory generic hub document with same-snapshot geometry, extend the
  existing board/layer/palette UI, make H4 review and resolution first-class,
  then wire the already-landed exact Vial/VIA write gates. Generic macro
  authoring, lighting, definition fetching, and visual rebranding stay out.
  H5a is complete: the pure immutable generic-document reducer owns profile,
  endpoint/definition binding, geometry, selection, dirty/history, report, and
  worklist state; the existing Keymap screen now adapts AM and generic documents.
  The Devices dialog lists AM, Vial, and VIA interfaces without cross-ecosystem
  deduplication, requires a user-imported definition before VIA read, and adopts
  same-snapshot geometry. Canonical authenticated hub open/save uses the Python
 loader/dumper; every new H5a hardware route is read-only. H5b is also complete:
 its separately tested portable QMK palette is curated from the pinned H0 survey,
 filters by reported keycode spec and exact target layer/macro capabilities, and
 applies generic palette/raw assignments through one document undo checkpoint.
 Unknown and per-board 16-bit codes remain exact through Advanced; generic save
 stays canonical `.hub.json`; AM assignment/history behavior is unchanged. H5b
 adds no hardware route, preflight, or setter. Full landing verification passed
 725 Python and 204 web tests, compile/JavaScript checks, and package build. A live
 in-app browser smoke covered palette/raw assignment, filtering, focus restoration,
 custom-code warning/undo, layer selection bounds, and the disabled Write action.
  H5c is complete: hub import overlays every open target through H4; key
  worklist items carry structured source data; profile/report/worklist history
  resolves server suggestions, board choices, and explicit omissions one
  checkpoint at a time. AM resolutions rebase on the current exported config
  before `/api/hub/apply`, while generic documents apply the target-shaped
  profile directly. Keymap owns the counts-first review rail and disclosed
  technical data; no H5c hardware route or setter exists. Verification passed
  727 Python and 212 web tests, compile/JavaScript checks, and package build.
  The rendered smoke was unavailable because the in-app browser runtime exposed
  no browser instance. H5d is complete: generic Write requires an exact freshly
  read live binding and every rescan invalidates it; Vial/VIA preflight shows
  endpoint/USB identity, byte and transfer counts, fresh target-match proof,
  exact case-sensitive confirmation, and canonical backup. Vial adds read-only
  unlock state with named/marked layout keys without starting its handshake.
  Possible accepted-byte failures can only run a fresh read-only verification
  and never resend; AM behavior is unchanged. Verification passed 727 Python
  and 216 web tests, compile/JavaScript checks, and package build. Rendered
  fake-Vial smoke covered edit/preflight/unlock marking, confirmation casing,
  dialog fit, rescan invalidation, and zero console errors; it never submitted a
  write request or touched a physical keyboard.
 H7 is the queued branding overhaul,
  which the owner ruled is a
  repositioning rather than a rename. The canonical scope and sequence live in
  `docs/superpowers/plans/2026-08-15-openkeeb-v2-hub-configurator.md`. Public
  identifiers, releases, money, and future hardware writes remain owner-gated.

- **Text banner authoring remains in v2 scope for NEON and Cyberboard.** The
  durable boundary, including its text effects, lives in `.agents/decisions.md`
  under "2026-08-14 — Text banner authoring is in v2 scope"; it needs its own
  approved plan before implementation.

- **The next release notes must carry the retired AI-vault cleanup steps or
  point to README's upgrade section.** The product version remains `0.1.68` as
  of `2a80cf0`, so no later release record yet owns that obligation.

- **The generic lighting job/progress scaffold remains an owner choice:** it
  can be removed as dead production code or reused by future deterministic
  tooling. The original finding and bounds live in
  `docs/superpowers/plans/2026-08-14-ai-removal.md`.

- **Whether OpenKeeb v2 exposes a plugin/external-provider surface remains an
  owner question.** It is not required by the approved hub-configurator lane.

- **Package-manager publication is paused:** AUR remains parked by the Arch
  lock; Flatpak preparation exists but must not publish under
  `io.github.roethlar.AMConfigurator`. Retarget both only after OpenKeeb public
  identifiers are approved. Canonical plan:
  `docs/superpowers/plans/2026-08-08-package-manager-distribution.md`.

## Blockers

- Whether the published 0.1.67 listing should carry a known-issue note about
  its unreachable AI providers, now that 0.1.68 supersedes it, is the owner's
  call. The live GitHub Release body still carries no such note as verified
  2026-08-16.
- Whether unobserved first-launch trust behaviour on a signed package gates a
  future publication remains an owner ruling; automated signature,
  notarization-ticket, and Gatekeeper primary-signature checks do not settle
  the visible launch path.
- Whether `.github/workflows/release.yml` should attest its assets remains an
  owner ruling; as of `2a80cf0`, it does not, and the docs say so.
- The stopped Reddit announcement was never posted. Its fate remains an owner
  decision; do not post it.
