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
- Backend Slice B1 is implemented on `codex/ollama-backend-correctness`: schema
  v7 migrates the fixed-loopback v6 record, Ollama accepts one normalized
  HTTP(S) origin, endpoint persistence makes no request, clients are cached by
  origin, and runtime/routes/status/frontend use the atomic `ollama` contract.
  The full automated verification entry point passed after guard proofs showed
  the origin, migration, client-cache, no-request endpoint, and no-alias tests
  fail when their production behavior is removed. No live Ollama request,
  credentialed provider request, or keyboard write was used.
- Backend Slice B2 is implemented on `codex/ollama-backend-correctness`.
  Completion-capable server and Ollama Cloud inventory is selectable with an
  explicit execution location; inventory metadata cannot redirect transport;
  model selection, status polling, and generation do not rediscover inventory;
  non-loopback and cloud data flow requires an explicit disclosure; and setup
  identity binds the normalized endpoint, model identity, execution location,
  and required disclosure. The full automated verification entry point passed.
  Guard proofs showed the cloud-classification, non-probing status/generation,
  non-network selection, location persistence, disclosure, and explicit-only
  browser Refresh tests fail when their production behavior is removed. No
  live Ollama request, credentialed provider request, or keyboard write was
  used.
- Backend Slice B3 is implemented in `a7daff3`. Ollama recipe generation,
  local-animation generation, schema failures, quality failures, and
  cancellation now make at most one model request per explicit action. Retry
  prompts, retry seeds, retry limits, and the `generate_attempt` protocol were
  removed while historical multi-attempt manifests remain supported. The
  focused B3 suite passed 58 tests and the full automated verification entry
  point passed.

## Next

- Close backend Slice B4 after a Windows native build and executable smoke
  test. `python build.py --skip-sync` currently stops before packaging because
  the pinned FFmpeg source archive and detached signature are not staged under
  `build/ffmpeg/sources`; no executable was produced.
- The owner assigned the product-experience plan to Claude for parallel work.
  The backend contracts are now committed, so its AI language and Settings
  integration no longer need to wait for B1-B3.

## Blockers

- Backend implementation has no unresolved product decision or approval
  blocker. Native smoke remains blocked only on the missing staged FFmpeg
  sources described above.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat the check on another machine; the next release
  plan must record an unverified gate or use an independently available host.
