# Repository State

## Now

- The owner settled the product contract on 2026-07-30: AI produces only a
  procedural LED recipe, the application renders it locally, FFmpeg is
  prohibited in every runtime/build/package path, and dependencies without a
  live supported responsibility are removed. The canonical ruling is in
  `.agents/decisions.md`.
- The audited removal work is specified in
  `docs/superpowers/plans/2026-07-30-ffmpeg-removal-and-dependency-audit.md`.
  The owner approved implementation on 2026-07-30. Slices R1-R3 are
  complete: procedural generation is the only AI generation path; historical
  video execution and recovery are retired; and the obsolete media runtime,
  build/package machinery, native smoke, CI toolchains, fixtures, and tests are
  gone. Model qualification now delegates to the production Ollama recipe
  provider, and the duplicate shipped developer adapter is gone. Legacy video
  manifests are reported as unsupported and left untouched.
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
  owner-tested immediate-assignment behavior. After the dependency-removal plan
  closes, P6 owns the candidate version change and remaining release-plan
  status/pointer synchronization.
- As of `b6874a7`, CI run `30556709461` and Desktop installers run
  `30556709994` both pass. The latter has an unexpired private
  `AM-Configurator-0.1.64-Windows-x64-Installer` artifact for precursor local
  testing; it is not the distinct `0.1.65` candidate required for release.
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

- Execute Slice R4: add the standard-library-only dependency ownership guard,
  inspect each locked transitive dependency for the three target platforms, and
  land the policy finding before clean-environment and native-artifact proof.
- Product Slice P6 and release qualification remain paused until the
  dependency-removal plan closes. Publishing a Release or announcement remains
  later, separately gated work.

## Blockers

- Final local Windows installer proof requires Inno Setup 6. Installing it is a
  separate owner-gated host mutation; it does not block the source-removal and
  automated-audit slices.
- This host cannot supply SmartScreen release evidence; see
  `.agents/machines.md`. Do not ask the owner to repeat the check elsewhere;
  record it as unverified or use an independently available host.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
