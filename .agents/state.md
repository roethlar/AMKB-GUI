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

## Next

- Surface the completed two-plan design and request implementation approval for
  the backend correctness plan first. It has no unresolved product decisions.
- After backend Slice B4 closes, begin the product-experience plan only if its
  implementation has also been approved.

## Blockers

- Backend implementation is blocked on owner approval of the backend plan.
  Product-experience implementation additionally depends on backend completion
  and its own implementation approval.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat the check on another machine; the next release
  plan must record an unverified gate or use an independently available host.
