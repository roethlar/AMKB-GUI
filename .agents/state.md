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
  16-slot/6677-byte capacity. Native build 53's rendered UI confirms the
  corrected event counts. N10 then exposed that Vial `GET_UNLOCK_STATUS` byte 1
  had been misread as a held-key count even though it is the
  unlock-in-progress flag, and that the app never started or polled the physical
  handshake. The repair decodes the reported matrix combo `(0,0)` + `(0,2)`,
  starts and polls the standard handshake before the first configuration SET,
  names the Neon's physical Esc + F2 positions in the GUI, and prevents Esc
  from dismissing the write dialog. Its red/green repository gate passes 576
  Python tests, 54 web tests, compile/syntax checks, and package build. Native
  build 54 passes its bundled launcher smoke; the artifact is
  `dist/AM-Configurator-0.1.54-macOS-arm64.dmg`. Optional xAI credential access
  remains
  deferred; no Keychain prompt occurred. Nothing has ever been written to the
  keyboard.
  The exported device-read JSON is **not an LED backup**: the Neon has no LED
  read-back, and its three custom LED slots in that file are synthetic black
  placeholders. On 2026-07-26 the owner found the original GIF used for the
  current lighting, accepted it as the recovery source, and explicitly
  authorized overwriting the connected Neon's LED setup for N10. The full-write
  action and asymmetric lighting push may now be used.
  The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and the live hardware
  record is `docs/neon-80-hardware-verification.md`. The proposed scoped-write
  follow-up in
  `docs/superpowers/plans/2026-07-26-neon-led-preserving-writes.md` is withdrawn
  as unnecessary for N10.
- Next action: replace the Neon's misleading matrix-cell LED projection with
  the real Vial key geometry and widths requested by the owner, then build and
  use that corrected GUI for the authorized N10 write and read-back checks.

## Blockers

- N10 has no remaining owner-authorization blocker: the owner explicitly
  authorized replacing the current LED setup after finding the original source
  GIF. The connected board still requires the physical Esc + F2 Vial unlock,
  and Angry Miao Master or VM USB forwarding must not hold the HID endpoint
  during the manual GUI write. The current Neon lighting canvas also needs the
  owner-requested real key sizing before N10 resumes. Broader device-family
  checks require their corresponding keyboards; they do not block the offline
  suite.
- Code signing and notarization are blocked on paid developer accounts, an
  Apple Developer Program membership and an Authenticode certificate. The owner
  declined both on 2026-07-24 as not ready. `README.md` discloses the unsigned
  state; note that on macOS 15+ an ad-hoc-signed download is not merely a
  warning, the user must approve it through System Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
