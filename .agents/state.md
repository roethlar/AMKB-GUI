# Repository State

## Now

- The owner-approved holistic remediation plan is the canonical closure ledger:
  `docs/superpowers/plans/2026-07-22-holistic-branch-remediation.md`. Every
  product, code, test, packaging, and residual-hygiene item is closed on the
  current tree except the separately gated governance bootstrap in P10. P11
  archived the former `## Now` journal verbatim to
  `docs/history/state-archive.md` and reconciled the remaining state here.
- The full repository gate passed on the final implementation tree at
  `61d2d65`. The current-host versioned native build produced the signed
  `AM-Configurator-0.1.33-macOS-arm64.dmg`, verified the disk image, and passed
  the frozen offline desktop smoke. Artifact inspection found no GGUF, llama,
  or local-model payload in the application bundle.
- A final goal-first self-review of `origin/main..61d2d65` found no material
  issue. Shipped AI is fixed-loopback Ollama or curated API only: source,
  workflow, packaging, route, and built-artifact scans found no application-
  managed runtime or Ollama model-management path. Review provenance is in
  `.agents/review/outcomes.md`.

## Next

- Resolve P10 only after explicit owner authorization for the legacy bootstrap
  carve-out and the required push-policy and communication-level choices.
- Complete the plan's manual no-provider/no-hardware UI inspection in a
  browser-capable session. This machine's unavailable browser binding is
  recorded in `.agents/machines.md`.
- After separate outward authorization, verify Windows x86_64 and Linux x86_64
  packages as Ollama/API-only builds and inspect their artifacts for prohibited
  runtime or model content.
- Address any failures surfaced by the committed CI and desktop-installer
  workflows; continue hardware verification across CyberBoard, Relic 80, and
  AFA firmware variants using portable JSON backups.

## Blockers

- Phase 10 / P10 cannot be completed by governance refresh alone. Refresh
  `f4fff9b` installed the current shipped updates, restored the reported
  toolkit-owned drift, and retired `GEMINI.md`, but the toolkit deliberately
  never creates repo-owned policy files and flagged this repo's `AGENTS.md` as
  foreign. Restoring `.agents/push-policy.md` requires the bootstrap
  procedure's separately approved two-commit legacy carve-out, including the
  owner's push-policy and communication-level choices. The remediation plan's
  refresh approval did not authorize that broader governance replacement.
- The manual UI acceptance pass remains unverified because the available
  in-app browser had no bound browser instance; see `.agents/machines.md`.
- Hardware checks require corresponding owner-supplied devices; they are not
  required for the offline suite.
- Native Windows ACL verification for a pre-existing library `jobs` directory
  remains required before a Windows release. New directories are private on
  supported patched CPython runtimes, and older runtimes fail preflight before
  touching the configured root.
