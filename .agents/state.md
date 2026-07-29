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

- Run the requested unprimed openreview over the remediation-plan commit using
  the owner-named Claude Fable 5 reviewer at xhigh effort. Permit one bounded
  Claude transport smoke and one actual review attempt only; do not retry a
  failed attempt.
- Surface the plan and review outcome to the owner. Make no implementation
  change until the owner approves the reviewed plan.

## Blockers

- Product implementation is blocked only on approval of the reviewed
  remediation plan.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat that check on another machine; the next release
  plan must record the unverified gate or an independently available host.
