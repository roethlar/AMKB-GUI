# Repository State

## Now

- Public-release qualification is stopped. The unpublished `0.1.64` candidate
  is rejected after product inspection found three release-blocking classes:
  Ollama Cloud inventory is deliberately hidden, one Ollama Generate action may
  run three complete model requests before failing, and normal UI/README paths
  expose implementation-led language and controls instead of a clear
  gamer-facing product.
- The approved release work remains historical context in
  `docs/superpowers/plans/2026-07-28-public-release.md`; it must not resume
  against an existing candidate. No tag, Release, announcement, macOS Open
  Anyway action, live cloud prompt, provider credential use, or
  release-candidate hardware write followed the rejection.
- The remediation plan is
  `docs/superpowers/plans/2026-07-29-human-facing-product-remediation.md`.
  It records configurable loopback/LAN Ollama origins, complete
  completion-capable inventory including Ollama Cloud, one model call per
  Generate action, plain-language UI, progressive disclosure, and a user-first
  README. Implementation awaits owner approval after independent openreview.

## Next

- Surface the remediation plan and failed review transport outcome to the
  owner. The requested Claude Fable 5 xhigh openreview was pinned to
  `d77106491edc8d76118bc04ab98ad8b0d3760bb2..013bd403c36838bcf1d70b355607c8a552d81f73`.
  Its one bounded smoke and one actual review attempt both stopped before model
  or tool use because the Claude OAuth session was expired and could not be
  refreshed. No verdict exists, and no retry or alternate reviewer was run.
- Make no product implementation change until the owner approves the plan.
  Another review attempt requires a fresh owner request after Claude
  authentication is restored.

## Blockers

- Product implementation is blocked on owner approval of the remediation plan.
  The requested independent review is unavailable until Claude authentication
  is restored; the failed transport produced no plan findings or clean verdict.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat that check on another machine; the next release
  plan must record the unverified gate or an independently available host.
