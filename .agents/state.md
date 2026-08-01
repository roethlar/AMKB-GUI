# Repository State

## Now

- The owner settled the product contract on 2026-07-30: AI produces only a
  procedural LED recipe, the application renders it locally, FFmpeg is
  prohibited in every runtime/build/package path, and dependencies without a
  live supported responsibility are removed. The canonical ruling is in
  `.agents/decisions.md`.
- The audited removal work is specified in
  `docs/superpowers/plans/2026-07-30-ffmpeg-removal-and-dependency-audit.md`.
  The owner approved implementation on 2026-07-30, and the app-owned R1-R6
  removal is landed. Procedural generation is the only AI generation path;
  historical video execution/recovery and the obsolete app-owned media
  runtime, build/package machinery, CI toolchains, fixtures, and tests are
  gone. The native-artifact criterion was reopened when exact `0.1.65` Linux
  extraction found FFmpeg code in Qt WebEngine/Multimedia, then re-established
  by the completed LXF-1 correction: Linux now uses GTK/WebKitGTK and both the
  PyInstaller tree and extracted AppImage are guarded by structural native
  audits. Canonical completion evidence lives in the LXF-1 plan. Legacy video
  manifests remain unsupported and untouched.
- The historical `0.1.64` clean-environment, CI, manifest, provenance, and
  platform results remain evidence for the app-owned removal, but their Linux
  absence conclusion is superseded because the scan did not inspect extracted
  vendor-library strings. Those private artifacts remain verification-only and
  must not be published.
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
  `cl-3` review set is closed; the two record-drift findings raised by the A1
  implementation review are also closed below.
- Backend Slices B1-B3 and product Slices P1-P6, including their follow-up
  fixes, are landed on `main`. Backend Slice B4 is superseded by the
  procedural-only/FFmpeg-prohibited ruling and must not be executed. Product
  Slice P6 established `0.1.65`, synchronized active packaging and product
  identity pointers, marked the rejected `0.1.64` release packet historical,
  and reconciled the Keymap plan with owner-tested immediate palette
  assignment. Its full gate, two-viewport 36-state native WebView2 matrix, and
  local Windows installer/frozen smoke all pass. Exact P6 commit `4a3c6eb`
  also passed all four CI jobs plus Windows, macOS, and Linux native artifact,
  metadata, and provenance jobs. Downloaded hashes and attestations, regenerated
  metadata, and controlled exact downloaded Windows
  install/audit/smoke/uninstall all pass.
  Detailed evidence and remaining action gates are canonical in the completed
  product-experience plan.
- CyberBoard switch lighting now projects the canonical 81-key CB04 Keymap
  geometry through the firmware LED map instead of rendering a uniform 15×6
  raster. The function-row gaps, wide keys, three-segment spacebar, and arrow
  notch share the Keymap footprint and 2.46:1 stage; the 40×5 top display stays
  rectangular. The geometry guard was red before the repair and green after;
  the owner accepted the corrected native view, and the full gate passes with
  646 Python tests, 127 web tests, compile/syntax checks, and the `0.1.65`
  source/wheel build.
- CyberBoard review finding `cl-6` closed at `0b6778f28482a664047df4ee0d830f9da1524a6f`:
  the target-split guard fails when the 83-LED switch layout replaces the
  200-cell display and passes with the repair. The owner explicitly waived a
  second paid Claude call after the full gate passed.
- Windows CI on `791ca06d9012235f9f6af842275e568004bbe418` exposed a pre-existing
  manifest-lookup race: lookup read a manifest before taking the per-object
  lock, so Windows sharing contention could be misreported as a missing job.
  Repair `2e92b62ac0736376a37045b88c8ba043dab8b9dc` locks generated-job and
  saved-item manifest validation. Both deterministic guards were red before
  the repair and green after it; all 645 Python tests, 125 web tests, package
  checks, and 300 Windows stress iterations pass. Its one required
  `claude-opus-5` review completed but the verdict envelope was lost after the
  outer MCP caller timed out; `.agents/review/outcomes.md` records the failed
  pass, and the owner ruled out a paid rerun.
- The GitHub Actions Node 24 upgrade is complete. Slice A1 landed at
  `7586bf7daab187a158a5c929cafcb80f9af97d10`; its exact dependency guard,
  full local verification, and required `claude-opus-5` review passed. Exact
  implementation-commit CI and Desktop runs then passed without Node 20 or
  action-runtime warnings, and artifact, SLSA provenance, and qualified Windows
  install/smoke/uninstall acceptance all passed. Exact evidence lives in
  `docs/superpowers/plans/2026-07-30-github-actions-node24-upgrade.md`.
- Review finding `cl-4` is verified at
  `c443f03605e93e0f288a6d9e0f8ff5d5d1b4d487`: the canonical state now names
  the exact landed A1 commit and A2 acceptance instead of retired refs and a
  settled approval gate. A pinned `claude-opus-5` review independently
  reproduced the manual base/head proof and focused dependency guard.
- Review finding `cl-5` is verified at
  `227019705bacfe89862a24bbbe4349176b487818`: the Node 24 plan now names exact
  A1 commit `7586bf7daab187a158a5c929cafcb80f9af97d10` and the A1/A2 qualification
  sequence instead of a settled approval gate. A pinned `claude-opus-5` review
  independently reproduced the manual base/head proof and passed all 51
  packaging tests. The A1 review loop is closed, and A2 has since completed.
- Known intermittent (backend, pre-existing): under full-suite load,
  `test_procedural_generation...test_local_cancellation_stops_without_retry_or_ready_artifacts`
  has once reported manifest status `interrupted` instead of `cancelled`.
  Neither the production path nor its test changed after B3; as of `b6874a7`,
  five fresh isolated runs pass. Treat it as an unresolved load-only release
  risk, not as a reason to mask or retry the test.
- The owner requested a GitHub release and an r/AngryMiao announcement and
  ruled that a testable build comes first. Exact P6 CI and three-platform
  artifacts now satisfy that prerequisite. Announcement copy has no durable
  repository copy and must be redrafted from repository records. No tag,
  Release, or announcement exists.

## Next

- The approved `0.1.65` release plan is recorded at
  `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md`. R65-0 and R65-1
  are complete: fresh release notes, an explicitly unposted Reddit draft, and a
  red-proven current-packet guard pass with the full 647-Python/127-web gate.
  R65-G1 host, operator, restore-source, and action-path readiness completed on
  2026-08-01. Use this local `netwatch-01`
  session for Windows x64, `win-arm-vm` for the independent default-SmartScreen
  observation, `nagatha` for macOS, and `gabrielle` for Linux. The pre-release
  x64 SmartScreen warning/More info/Run anyway/install/launch path passed on the
  VM with Internet-zone metadata preserved; the final exact candidate must
  repeat it. A directly connected Neon passed the non-writing production
  identity/read/export path: `NEON80`, definition `AM Neon 80`, Vial protocol 5,
  four 90-key layers, four populated macros within the device-reported 16-slot
  capacity. The valid private export's keymap/macros match the complete desired
  profile on `nagatha`; that profile contains the LED restore tracks and matches
  the documented recovery hash. Private paths, hashes, macros, firmware UID,
  and configuration bytes remain outside the repository. The simultaneously
  connected AFA A2 was not opened, and no keyboard write occurred. Candidate
  attempt 1 froze `2685a9832e0982d8b52ea45a4becd8a75eb48d01`; exact CI run
  `30683516281` and Desktop run `30683516302` attempt 1 passed, and the
  five-file metadata/provenance checks passed. R65-3 then rejected the complete
  candidate because its extracted Linux Qt WebEngine/Multimedia libraries
  contain FFmpeg decoder/demuxer implementation code. No candidate is active.
  Corrective slice LXF-1 is complete: the transitive Qt media runtime is gone,
  the standalone GTK/WebKitGTK AppImage passes exact-head CI, provenance,
  independent extraction/audit, native-policy, bundled-helper, license, and
  udev checks, and no physical keyboard test occurred. Canonical evidence is in
  `docs/superpowers/plans/2026-08-01-linux-transitive-ffmpeg-removal.md`.
  No approved implementation work remains. The next action is public-release
  Slice R65-2: audit the resulting clean `main`, run maintained-host native
  preflights, push normally, and freeze a completely new candidate SHA.
  `.agents/machines.md` owns the Windows ARM exploratory-build evidence and its
  explicit-native-Python requirement; ARM64 is not part of the `0.1.65` public
  asset set.
  One owner-requested `claude-fable-5` openreview judged the exact plan range
  `best_approach` with no findings; `.agents/review/outcomes.md` records the
  returned-envelope deviation and no-resubmission handling.
  Tagging, release publication, hardware writes, live provider use, macOS Open
  Anyway, and announcement remain separately gated actions.
- Separately, the accepted `cl-2` review recorded a pre-existing read-only
  `get()` / `resolve_asset()` retired-job exposure as a candidate requiring an
  owner scope decision; it is not approved implementation work.

## Blockers

- No implementation blocker remains before R65-2. Live Ollama Cloud prompts,
  keyboard writes, macOS Open Anyway, tag creation, release publication, and
  announcements remain separately gated actions for their later slices.
