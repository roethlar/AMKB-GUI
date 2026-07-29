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
- The remediation plan is
  `docs/superpowers/plans/2026-07-29-human-facing-product-remediation.md`.
  It covers configurable loopback/LAN Ollama origins, complete
  completion-capable inventory including Ollama Cloud, one model call per
  Generate action, plain-language UI, progressive disclosure, and a user-first
  README.
- Three admitted plan-review findings were fixed in commits `52261fe`,
  `e596823`, and `ffd7644`: local-animation scope, explicit supersession of old
  Ollama constraints, and a pointer to the canonical verification entry point.
- An approach-first openreview completed through Claude Code MCP with
  `claude-fable-5` at `xhigh` over
  `d77106491edc8d76118bc04ab98ad8b0d3760bb2..ffd76446c4c3e9cf689d11d5c3ac4a0b260e84d3`.
  Capability proof passed and the assessment was `acceptable_with_changes`.
- AgentGovernanceBootstrap issue
  `https://github.com/roethlar/AgentGovernanceBootstrap/issues/11` tracks the
  toolkit bug that made the original openreview contract produce a
  defect-shaped audit instead of an independent approach.

## Next

- Surface the approach-first review to the owner. Its recommended changes are:
  repair the Slice 1/Slice 2 rename boundary so every intermediate commit is
  green; split backend correctness from the UX/README overhaul into separately
  approvable plans; resolve `generate_attempt` removal unconditionally; use one
  supersession annotation style in `.agents/decisions.md`; and state the
  canonical version policy for the post-remediation candidate.
- Make no product implementation change until the owner rules on those plan
  changes and approves the resulting implementation plan or plans.

## Blockers

- Product implementation is blocked on the owner's response to the completed
  openreview and subsequent approval of the corrected plan or plans.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat the check on another machine; the next release
  plan must record an unverified gate or use an independently available host.
