# Repository State

## Now

- Public-release qualification is stopped. The unpublished `0.1.64` candidate
  was rejected after product inspection found three release-blocking classes:
  Ollama Cloud inventory was deliberately hidden, one Ollama Generate action
  could run three complete model requests before failing, and normal UI/README
  paths exposed implementation-led language and controls instead of a clear
  gamer-facing product.
- Approved release work remains historical context in
  `docs/superpowers/plans/2026-07-28-public-release.md`; it must not resume
  against the existing candidate. No tag, Release, announcement, macOS Open
  Anyway action, live cloud prompt, provider credential use, or
  release-candidate hardware write followed the rejection.
- The owner approved a two-plan structure on 2026-07-29. Backend correctness is
  `docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md`; product
  experience and user documentation are
  `docs/superpowers/plans/2026-07-29-product-experience-remediation.md`.
  The plans are independently approvable, and backend implementation completes
  before product-experience implementation begins.
- Three admitted plan-review findings were fixed in commits `52261fe`,
  `e596823`, and `ffd7644`: local-animation scope, explicit supersession of old
  Ollama constraints, and a pointer to the canonical verification entry point.
- An approach-first openreview completed through Claude Code MCP with
  `claude-fable-5` at `xhigh` over
  `d77106491edc8d76118bc04ab98ad8b0d3760bb2..ffd76446c4c3e9cf689d11d5c3ac4a0b260e84d3`.
  Capability proof passed and the assessment was `acceptable_with_changes`.
  Its slice-boundary, plan-split, protocol-removal, supersession-style, and
  version-policy recommendations are incorporated in the two plans.
- AgentGovernanceBootstrap issue
  `https://github.com/roethlar/AgentGovernanceBootstrap/issues/11` tracks the
  toolkit bug that made the original openreview contract produce a
  defect-shaped audit instead of an independent approach.
- Slice P4 landed on the product branch: 13px helper-text floor (one
  documented exception: the opt-in keycap matrix overlay), WCAG-checked
  `--control-line` token on interactive borders, readable disabled states,
  top-bar actions moved to a scrollable full-width row at ≤1120px, keymap
  editor single-column at ≤1240px, and a shorter visible Merge label. Guards
  live in `tests/web/design_tokens.test.js` with computed WCAG contrast
  assertions. Two viewports were manually verified live at 1000×680 and
  1280×800 (empty state, chrome, top bar); the full per-screen manual matrix
  with an open document still rides Slice P6. A resize defect initially
  reported from screenshots was disproved: an in-page probe on the same
  pywebview 6.2.1/WebView2 stack reflows correctly on shrink, grow, and
  maximize. The screenshots were cropped by DPI-unaware capture tooling —
  window automation from a DPI-unaware shell process uses virtualized
  coordinates at 125% scale, so captures must multiply sizes by the scale
  factor or the right/bottom ~20% of the window silently disappears.
- Product-experience implementation runs in parallel on
  `claude/product-experience-remediation`, a worktree branch based at the
  shared docs tip `0271213`. Slice P2 is implemented and guard-proven:
  onboarding task cards (Connect a keyboard / Open a JSON profile), contextual
  Merge, Advanced keycode and Show technical labels disclosures with lossless
  raw round-trip, Type text / Record keys as the normal macro path with
  complete event editing under Edit individual events, labelled sidebar
  counts, and focus restoration. Guards live in
  `tests/web/app_shell.test.js` plus the updated empty-state test in
  `tests/test_app.py`.

## Next

- Implement backend Slice B1 on `codex/ollama-backend-correctness`, preserving a
  green full-stack boundary for the schema, endpoint, route, and consumer
  rename.
- The owner assigned the product-experience plan to Claude for parallel work.
  Claude may implement low-conflict visual/documentation work independently;
  AI language and Settings integration wait for the backend contracts to land.
- On `claude/product-experience-remediation`, low-conflict work (P2, P4) is
  committed. Slices P1 and P3 start only after the completed backend branch
  merges into the product branch; P5 screenshots and P6 versioning close out
  after both plans, including the full two-viewport per-screen manual matrix
  with an open document.

## Blockers

- Backend implementation has no unresolved product decision or approval
  blocker. Product AI/Settings integration depends on backend completion.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat the check on another machine; the next release
  plan must record an unverified gate or use an independently available host.
