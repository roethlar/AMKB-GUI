# Repository State

## Now

- The owner settled the product contract on 2026-07-30: AI produces only a
  procedural LED recipe, the application renders it locally, FFmpeg is
  prohibited in every runtime/build/package path, and dependencies without a
  live supported responsibility are removed. The canonical ruling is in
  `.agents/decisions.md`.
- The audited removal work is specified in
  `docs/superpowers/plans/2026-07-30-ffmpeg-removal-and-dependency-audit.md`.
  The owner approved implementation on 2026-07-30, and Slices R1-R6 are
  complete. Procedural generation is the only AI generation path; historical
  video execution/recovery and the obsolete media runtime, build/package
  machinery, CI toolchains, fixtures, and tests are gone. Model qualification
  uses the production Ollama recipe provider, and guards reject ownerless
  dependencies, undeclared imports, orphan package modules, JavaScript package
  metadata, and retired locked packages. Legacy video manifests are reported
  as unsupported and left untouched.
- Local clean-environment/Windows installer proof and final-head Linux, macOS,
  and Windows CI/installer proof all pass. Downloaded artifacts matched their
  manifest and provenance, and recursive inspection found no retired runtime
  reference. Exact evidence lives in the completed dependency-removal plan.
  Its private `0.1.64` artifacts are verification-only and must not be
  published.
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
- Backend Slices B1-B3 and product Slices P1-P5, including their follow-up
  fixes, are landed on `main`. Backend Slice B4 is superseded by the
  procedural-only/FFmpeg-prohibited ruling and must not be executed. Product
  Slice P6 remains open and has not started: `am_configurator/_version.py`
  still reports `0.1.64`, and `0.1.65` appears only in the product plan.
- P6 must complete the full two-viewport per-screen manual matrix with an open
  document and reconcile the Keymap plan's explicit Apply wording with the
  owner-tested immediate-assignment behavior. P6 now owns the candidate version
  change and remaining release-plan status/pointer synchronization.
- Current GitHub workflows pass but emit deprecation warnings because
  `actions/checkout@v4`, `actions/upload-artifact@v4`, pinned
  `actions/download-artifact@v4.3.0`, and `astral-sh/setup-uv@v6` target Node
  20 and are being forced onto Node 24. These actions each have a live owner;
  their major-version compatibility upgrade is specified in the pending draft
  plan, not an unused-dependency finding.
- Known intermittent (backend, pre-existing): under full-suite load,
  `test_procedural_generation...test_local_cancellation_stops_without_retry_or_ready_artifacts`
  has once reported manifest status `interrupted` instead of `cancelled`.
  Neither the production path nor its test changed after B3; as of `b6874a7`,
  five fresh isolated runs pass. Treat it as an unresolved load-only release
  risk, not as a reason to mask or retry the test.
- The owner requested a GitHub release and an r/AngryMiao announcement, but
  ruled that a testable build comes first. Announcement copy has no durable
  repository copy and must be redrafted from repository records. No tag,
  Release, or announcement exists.

## Next

- Owner approval is pending for
  `docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md`.
  If approved, execute its guarded compatibility upgrade before Product Slice
  P6.
- Product Slice P6 remains the next product implementation slice: resolve the
  Keymap Apply contract, complete the two-viewport manual matrix, set the
  distinct candidate version to `0.1.65`, run full/local native verification,
  and synchronize release pointers. Publishing a Release or announcement
  remains later, separately gated work.

## Blockers

- This host cannot supply SmartScreen release evidence; see
  `.agents/machines.md`. Do not ask the owner to repeat the check elsewhere;
  record it as unverified or use an independently available host.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
