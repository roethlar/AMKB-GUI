# Repository State

## Now

- AM Neon 80 support is in progress on `neon-80-support`. Plan tasks N1-N9 are
  implemented, and `.agents/review/index.md` owns the closed, red-proven review
  scoreboard. N10's physical identity and real-GUI enumeration checks pass.
  The GUI read exposed and red-proved fixes for a macOS hidapi thread-affinity
  crash, Vial's empty macro-capacity slots entering the portable document, and
  literal Vial text being misread as HID usage numbers. Commit `25f225c`
  red-proves the literal/tap decoder repair. A GET-only physical read through
  the exact UI API now returns four 90-key layers and four populated macros as
  real press/release transitions, while retaining the separately reported
  16-slot/6677-byte capacity. The complete repository gate passes, and native
  build 53 passes its bundled smoke. Optional xAI credential access remains
  deferred; no Keychain prompt occurred. Nothing has ever been written to the
  keyboard.
  The exported device-read JSON is **not an LED backup**: the Neon has no LED
  read-back, and its three custom LED slots in that file are synthetic black
  placeholders. The owner has prohibited overwriting the current LED setup, so
  neither the full-write action nor N10's asymmetric lighting push may be used.
  The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and the live hardware
  record is `docs/neon-80-hardware-verification.md`. The proposed safe follow-up
  is `docs/superpowers/plans/2026-07-26-neon-led-preserving-writes.md`.
- Next action: obtain the owner's approval for the proposed Neon-only,
  keymap-only/macro-only write plan, then implement it before any remaining N10
  hardware check.

## Blockers

- N10's current full-write route would replace the owner's unrecoverable LED
  setup with synthetic black frames. It is prohibited. The safe scoped-write
  follow-up is drafted but unapproved, so keymap and macro hardware round trips
  remain blocked on that one owner ruling. Lighting geometry verification
  remains blocked unless a complete trusted LED source becomes available and
  the owner separately authorizes replacing the current setup. Broader
  device-family checks require their corresponding keyboards; they do not block
  the offline suite.
- Code signing and notarization are blocked on paid developer accounts, an
  Apple Developer Program membership and an Authenticode certificate. The owner
  declined both on 2026-07-24 as not ready. `README.md` discloses the unsigned
  state; note that on macOS 15+ an ad-hoc-signed download is not merely a
  warning, the user must approve it through System Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
