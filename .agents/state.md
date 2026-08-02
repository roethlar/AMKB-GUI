# Repository State

## Now

- The final LSR-10 owner-acceptance repair is implemented in `a4d3793`.
  Imported-media framing and exact mapped LED output
  now survive Studio -> Library -> Studio before and after Apply; an interrupted
  render is discarded on exit and resumes on return; Undo makes the retained
  accepted result applicable again. Source and Board update automatically with
  no separate Preview action, Apply uses compact state-specific slot copy, the
  action row no longer clips, and applied compositions remain saveable to
  Library. The native audit now proves navigation persistence before and after
  Apply plus interrupted-render recovery, and uses a Zoom nudge for its pointer
  proof so Fit cannot make vertical pan mathematically impossible. The complete
  local gate passes 727 Python tests with 5 skips, 188 browser tests,
  compile/syntax checks, and both package builds. Windows source and frozen
  schema-v2 audits pass both viewports, all six GIF/PNG/BMP cases, all ten
  profile checks, and all six navigation-persistence checks with no console or
  layout finding; native-tree audit, frozen smoke, and the Windows build pass.
  Canonical machine-local evidence is
  `.agents/review/lsr10-media-navigation-source-5.local.json` and
  `.agents/review/lsr10-media-navigation-frozen-3.local.json`. The accepted
  executable has SHA-256
  `CC130573A8E33512962ABF75821BD51C65098CF8B1AB4584A6FC35FFB0C5B042`, and
  the owner passed its visible Windows acceptance on 2026-08-02. Two uncaptured
  launches stopped at the already-recorded packaged-startup race
  `raw_import_rejected:unknown`; they were not resubmitted, while the proven
  captured-process invocation passed against identical executable bytes. PTK
  also lost one aggregate full-gate transport; Python and the remaining gate
  components were recovered separately without repeating successful work. No
  external review was launched. Exact repair head `a4d3793` passes CI run
  `30770842393` on all four test jobs and Desktop installers run `30770842381`
  on Windows, macOS, Linux, candidate metadata, and release provenance. LSR-10
  remains open only for affected Windows, Linux, and macOS native qualification.
- Public-release candidate attempt 3 at
  `09232fb695a1a8b1ebc470ac470509ebbace3eb2` is rejected. Exact CI run
  `30699706921` and Desktop run `30699706913` attempt 1 passed, and the owner
  accepted exact-candidate macOS qualification including the substantive
  native WKWebView media workflow. R65-6 then failed before a write: starting
  preview playback on Per-key and switching to Head matrix while it remained
  active rendered incorrect Head matrix lighting instead of its saved
  animation. No candidate is active. Canonical sanitized evidence is in the
  current public-release plan; screenshots and the native audit remain
  controlled machine-local evidence.
- A holistic Lighting Studio redesign is drafted at
  `docs/superpowers/plans/2026-08-01-lighting-studio-human-first-redesign.md`.
  It preserves the canonical renderer, device maps, Library, document-only
  Apply/Undo, and write safety while replacing the frontend state and
  interaction model. Imported media keeps an actual Source pane beside a
  separate physical Board pane whose LEDs come only from the exact canonical
  arrays used by Apply and Write; one transform and playhead own both. The plan
  also covers destination-bound playback, live Effects, supported-format
  selection, honest errors, and offline profile editing. The owner approved the
  complete plan on 2026-08-01. Normal Save JSON is self-contained app-native
  output through strict namespaced `_am_configurator` dynamic-layout metadata;
  protocol encoders exclude that metadata, while no sidecar, vendor-clean
  export, or third-party output compatibility promise is required. Import
  remains intentionally broader: strict server adapters
  must accept recognized Angry Miao AM Master full-profile and AM 80
  lighting-only JSON.
- Seven owner-supplied machine-local AM Master examples established two import
  dialects without becoming repository fixtures: four full `ALICE` profiles
  need only recognized disabled zero-frame placeholder normalization to pass
  existing validation/writer planning; three AM 80 lighting-only objects carry
  paired 230-pixel Head and 89-pixel Per-key tracks with 1, 50, or 75 frames.
  The approved plan requires minimized synthetic fixtures and a final read-only
  acceptance pass against the supplied files; original payloads are not copied
  into the repository, logs, or packages.
- Remaining LSR work follows `.agents/repo-guidance.md` (Review Economy); the
  former per-slice codereview requirement is superseded. Any review already
  launched is allowed to finish and its first substantive result is used under
  that canonical rule.
- The Macro page finding that existing macro contents are not shown directly
  enough is recorded as separate queued UX work. It is not part of the
  Lighting redesign and has no approved implementation scope.
- The proposed Neon write gate was canceled before invocation because the
  loaded portable profile did not contain the owner's current saved lighting.
  No Write action, typed confirmation, physical unlock, hardware write,
  provider request, credential lookup, tag/Release, or announcement occurred.
  Candidate-attempt-3 artifacts are rejected bytes and must not be published or
  reused.
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
  and all three unpublished `0.1.65` candidate attempts remain permanently
  rejected; none may be reused or published.
- Approved release work remains historical context in
  `docs/superpowers/plans/2026-07-28-public-release.md`; it must not resume
  against the existing candidate. No tag, Release, announcement, macOS Open
  Anyway action, live cloud prompt, provider credential use, or
  release-candidate hardware write followed the rejection.
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

- Repeat affected native qualification at exact head `a4d3793` on Windows x64,
  Linux x86-64, and macOS arm64. Close LSR-10 and R65-2 only when all three pass.
  No further external review is authorized;
  use one only on explicit owner request or a concrete material risk that local
  guards and CI cannot resolve. A replacement release candidate must repeat
  every release gate and cannot mix evidence from any rejected attempt with new
  bytes.
- The approved `0.1.65` release plan remains recorded at
  `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md`; it records all
  three rejected candidates and is paused behind the redesign.
- `.agents/machines.md` owns all host details, including each host's
  qualification role and connection information.
- Tagging, release publication, hardware writes, live provider use, macOS Open
  Anyway, and announcement remain separately gated actions.
- Separately, the accepted `cl-2` review recorded a pre-existing read-only
  `get()` / `resolve_asset()` retired-job exposure as a candidate requiring an
  owner scope decision; it is not approved implementation work.

## Blockers

- Owner acceptance of the complete redesign is passed. R65-2 remains blocked
  only on affected Windows, Linux, and macOS native qualification for the final
  LSR-10 repair at exact head `a4d3793`. Live provider requests,
  keyboard writes, macOS Open Anyway, tag creation, release publication, and
  announcements remain separately gated actions for their later slices.
