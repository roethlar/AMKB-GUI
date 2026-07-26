# Repository State

## Now

- AM Neon 80 support is in progress on `neon-80-support`. Plan tasks N1-N9 are
  implemented but are not finished while `n567-9` remains open; `n567-10` is
  repaired, red-proven, and verified but has not been re-reviewed. Nothing has
  ever been written to the keyboard; all device interaction so far has been
  read-only. The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and
  `.agents/review/index.md` owns the finding scoreboard.
- Next action: finish and red-prove `n567-9`. After it closes, perform manual,
  owner-present N10 hardware verification using
  `docs/neon-80-hardware-verification.md`; this is the first authorized point
  at which anything writes to the keyboard.

## Blockers

- N10 and the broader device-family hardware checks require the owner and the
  corresponding keyboards; they are not required for the offline suite.
- Code signing and notarization are blocked on paid developer accounts, an
  Apple Developer Program membership and an Authenticode certificate. The owner
  declined both on 2026-07-24 as not ready. `README.md` discloses the unsigned
  state; note that on macOS 15+ an ad-hoc-signed download is not merely a
  warning, the user must approve it through System Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
