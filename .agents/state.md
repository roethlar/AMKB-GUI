# Repository State

## Now

- Active review loop: see `.agents/review/index.md`.
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
- Review finding `cl-2` is verified at
  `d77ca6e61a84c4bc01deb5fc3f3367ab8325022b`: live and removed retired-video
  jobs share one unsupported classification, and remove, restore, and
  permanent deletion reject them both before and after lock acquisition
  without changing stored bytes. A pinned `claude-opus-5` review independently
  reproduced both red/green guards and accepted the slice.
- Review finding `cl-3` is verified at
  `72a1e41889243819f4c27036693f150b15b95859`: the Node 24 plan now names
  the exact retired provenance-action commit, making its future absence guard
  non-vacuous. A pinned `claude-opus-5` review independently reproduced the
  manual base/head proof and accepted the slice. The original `cl-1` through
  `cl-3` review set is closed; the active loop now owns the two record-drift
  findings raised by the A1 implementation review.
- Backend Slices B1-B3 and product Slices P1-P5, including their follow-up
  fixes, are landed on `main`. Backend Slice B4 is superseded by the
  procedural-only/FFmpeg-prohibited ruling and must not be executed. Product
  Slice P6 remains open and has not started: `am_configurator/_version.py`
  still reports `0.1.64`, and `0.1.65` appears only in the product plan.
- P6 must complete the full two-viewport per-screen manual matrix with an open
  document and reconcile the Keymap plan's explicit Apply wording with the
  owner-tested immediate-assignment behavior. P6 now owns the candidate version
  change and remaining release-plan status/pointer synchronization.
- GitHub Actions Node 24 Slice A1 landed at
  `7586bf7daab187a158a5c929cafcb80f9af97d10`: checkout/upload use their
  reviewed v7 major refs, download/provenance/setup-uv use their reviewed
  immutable releases, and `prune-cache: true` preserves the existing cache
  contract. The new exact dependency guard is red/green proven, and full local
  verification passed. Its required `claude-opus-5` implementation review
  reported no workflow or test defect; A2 remote workflow, artifact,
  provenance, and Windows installation acceptance remains outstanding.
- Review finding `cl-4` is verified at
  `c443f03605e93e0f288a6d9e0f8ff5d5d1b4d487`: the canonical state now names
  the exact landed A1 commit and A2 acceptance instead of retired refs and a
  settled approval gate. A pinned `claude-opus-5` review independently
  reproduced the manual base/head proof and focused dependency guard.
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

- Finish the active Node 24 record-drift loop by correcting and verifying
  `cl-5`. After it closes, push the exact A1 and record commits to both remotes
  and execute the plan's A2 remote acceptance against that pinned head.
- The accepted `cl-2` review recorded a separate pre-existing read-only
  `get()` / `resolve_asset()` retired-job exposure as a candidate requiring an
  owner scope decision.
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
