# Repository State

## Now

- AM Neon 80 support is in progress on `neon-80-support`. Plan tasks N1-N9 are
  implemented, and `.agents/review/index.md` owns the closed, red-proven review
  scoreboard. N10's physical identity and real-GUI enumeration checks pass.
  The GUI read exposed a macOS hidapi thread-affinity crash; the repair is
  red-proven and build 50 passes the repository gate and bundled native smoke,
  but its physical read retry is waiting at macOS Keychain authorization before
  the app window opens. Nothing has ever been written to the keyboard.
  The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and the live hardware
  record is `docs/neon-80-hardware-verification.md`.
- Next action: after the owner authorizes build 50's Keychain prompt, retry
  **Read keymap & macros** in the exact `dist/AM Configurator.app`. If it passes,
  export the read profile and stop at the first keyboard-write confirmation
  gate in the hardware guide.

## Blockers

- Build 50's live GUI retry is waiting at a protected macOS Keychain prompt;
  only the owner can enter or change a credential. This is a read-only app
  launch boundary, not keyboard-write approval.
- N10's remaining steps require the owner at the keyboard-write confirmation
  gate and the attached Neon. Broader device-family hardware checks require
  their corresponding keyboards; neither blocks the offline suite.
- Code signing and notarization are blocked on paid developer accounts, an
  Apple Developer Program membership and an Authenticode certificate. The owner
  declined both on 2026-07-24 as not ready. `README.md` discloses the unsigned
  state; note that on macOS 15+ an ad-hoc-signed download is not merely a
  warning, the user must approve it through System Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
