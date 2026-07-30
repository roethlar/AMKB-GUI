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
- Backend Slices B1-B3 and product Slices P1-P5, including their follow-up
  fixes, are landed on `main`. Backend Slice B4 and product Slice P6 remain
  open. P6 has not started: `am_configurator/_version.py` still reports
  `0.1.64`, and `0.1.65` appears only in the product plan.
- P6 must complete the full two-viewport per-screen manual matrix with an open
  document and reconcile the Keymap plan's explicit Apply wording with the
  owner-tested immediate-assignment behavior. It also owns synchronizing the
  stale status text in the backend, product, and historical release plans: the
  backend plan still names missing sources after they were staged, while the
  product plan still says implementation was not approved before P1-P5 landed.
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

- Proposed first action: download the current private Windows precursor with
  `gh run download 30556709994 -n
  AM-Configurator-0.1.64-Windows-x64-Installer`, then let the owner install and
  test it locally. This compiles nothing and publishes nothing.
- If precursor testing is accepted, execute product Slice P6: bump the
  canonical version to `0.1.65`, close the manual matrix and recorded plan
  deviations, synchronize plan status/pointers, run the full verification and
  native checks, and commit the slice. A newly rebuilt exact candidate follows
  before any separately gated Release or announcement.
- Backend Slice B4 remains open for its required native build and executable
  smoke. Its current host evidence and toolchain constraints are recorded
  canonically in `.agents/machines.md`.

## Blockers

- Backend Slice B4's required native build cannot be performed on this host
  under the owner-approved toolchain constraints and current attested recipe;
  see `.agents/machines.md`. Closing it requires an independently capable host
  or an owner-approved change to the recipe or acceptance path.
- This host cannot supply SmartScreen release evidence; see
  `.agents/machines.md`. Do not ask the owner to repeat the check elsewhere;
  record it as unverified or use an independently available host.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
