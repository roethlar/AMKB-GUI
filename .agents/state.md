# Repository State

## Now

- `v0.1.65` remains a withdrawn GitHub draft; its tag and assets are retained
  and must not be republished or moved. Its disposition is an R66-5 owner
  decision.
- Macro repair: complete and reviewed in the app by the owner. Three-mode
  editor: `4c1884d` (compiler timing), `92aad3c` (Text entry), `b7f1c39`
  (Flow), `b3b22c3` (Repeat), review fix `b9f226e` (Flow sole event editor,
  recorded-text decode). The owner confirmed his real 0 ms-delay macros work
  fine; no zero-delay warning is wanted.
- README screenshots were recaptured with a synthetic profile at release size
  (`9e714de`); the suite is fully green. The screenshot guard failure is
  resolved.
- Release `0.1.66` preparation is mid-flight: version bumped (`777da50`),
  JPEG import landed (`aa1c263`), experimental ARM64 CI landed and passed on
  both targets (`0558685`, run 30884280304), release notes drafted.
  **Pushes are paused (owner, 2026-08-04): the owner has not yet read or
  approved the packet. Nothing goes to origin until the owner reviews.**
- The Reddit draft is being rewritten with the owner as a first-app
  announcement (what/why/try-it framing). Edits are local and uncommitted.
- A read-only static audit found six redundant labels: the QWERTY-picker
  caption, the Macros eyebrow, and four duplicate dialog/screen eyebrows.
  No audit edits were made.

## Next

- **The 0.1.66 release is frozen (owner, 2026-08-04): an element-level UI
  redesign blocks publication.** R66-4 qualification and R66-5 gates do not
  proceed until the redesign ships. The packet (release notes, plan) is
  superseded in UI terms — it describes the current look.
- The redesign starts from information architecture, not paint: two mockup
  rounds (colorways, then structural reskins) were rejected as "the same
  elements, restyled." The next step is throwaway prototypes with genuinely
  different element arrangements for the owner to judge.
- After `0.1.66`: draft a plan for unsupported-board onboarding (owner
  approved 2026-08-03): "new keyboard model detected" plus a read-only scan
  that packages a sanitized device report (product ID, protocol responses,
  keymap/macro capacities) for GitHub submission, so support can be added
  without buying every board. Known limit: serial-protocol LED geometry is
  not probeable, so lighting for new serial families still needs a physical
  board or vendor source; keymap/macro support may ship from a scan alone.

## Blockers

- Release is frozen on the element-level UI redesign (owner, 2026-08-04).
  Origin pushes stay paused. No external blocker.
