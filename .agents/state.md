# Repository State

## Now

- The approved public-release plan at
  `docs/superpowers/plans/2026-07-28-public-release.md` remains in flight.
  Implementation and local preflight are complete. As of `3d89351`, CI run
  `30450040146` and Desktop installers run `30450040069` (run 40) completed
  successfully for that exact `main` commit, including the required test,
  installer, candidate-metadata, and release-provenance jobs. The run-40
  artifacts have not yet received exact-artifact qualification. No tag,
  Release, announcement, macOS Open Anyway action, provider credential
  access, or release-candidate hardware write has occurred. Candidate
  qualification must stop and report on the first failed tool, test, gate,
  or required-host check rather than retrying.

## Next

- On `netwatch-01`, resolve the successful Desktop run whose `headSha` matches
  the live canonical `main`, then download its Windows installer and candidate
  metadata through the browser, require the manifest hash, verify SHA-256 and
  Authenticode state, observe SmartScreen, run the normal per-user install,
  launch and inspect About version `0.1.64`, run
  `--native-policy-smoke`, and uninstall without disabling or bypassing
  Defender or SmartScreen. Stop immediately and report the first failure.
  Once Windows passes, continue the same candidate's remaining macOS/Linux,
  UI, Open Anyway, and freshly authorized Neon gates before requesting
  publication approval.

## Blockers

- No external blocker prevents starting the Windows gate on this host once the
  final candidate SHA is selected by the required live git/workflow checks.
- One cleanup decision is waiting on the owner: whether to remove the
  Windows verification leftovers on `netwatch-01`, recorded in
  `.agents/machines.md`. They remain harmless and useful for this release
  qualification.
- The later macOS Open Anyway check and Neon full write require action-time
  authorization. Tag creation, release publication, and announcement remain
  separately gated outward actions.
