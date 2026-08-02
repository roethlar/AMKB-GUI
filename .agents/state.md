# Repository State

## Now
- LSR-1 is closed. Implementation `1ee73a81182c8f401b1942776d3df7c005541f33` and admitted review repair `95795845b6eeabd1c572b82244fef26a975183dd` are fully guard-proven, pass the 677-Python/144-browser/compile/syntax/build gate, and are pushed. The required `claude-opus-5` generation review and T2 per-finding verification used exact ranges once each; `cl-10` returned accepted with guard and capability confirmed. Canonical evidence is in the redesign plan and `.agents/review/findings/cl-10.md`.
- LSR-2 implementation `65c9fbfc22c2b24c3b868218512b00039756e6e1` is committed, pushed, and passed the 685-Python/144-browser/compile/syntax/build gate plus selected/full parity and Library-removal mutation proofs. Its single required `claude-opus-5` generation review over exact parent `4bdb75f802dec338821ea827d397a7ebc091d8bd` returned two independently reproduced findings: `cl-11` MEDIUM (sessionless renders consume and depend on the explicit preview-session LRU) and `cl-12` LOW (supersession begins only after complete decode). Both are admitted; repair `cl-11` first, then `cl-12`, one commit and one per-finding verdict each.

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
- The active release objective requires every landed LSR implementation slice
  to be committed, pushed, and reviewed once through codereview harness
  `claude` / job `fable-review` with explicit model `claude-opus-5` and effort
  `high` over the exact landed range. The first substantive result is used as
  returned; no discard, rerun, resubmission, or model substitution is allowed
  without explicit owner approval.
- The Macro page finding that existing macro contents are not shown directly
  enough is recorded as separate queued UX work. It is not part of the
  Lighting redesign and has no approved implementation scope.
- The proposed Neon write gate was canceled before invocation because the
  loaded portable profile did not contain the owner's current saved lighting.
  No Write action, typed confirmation, physical unlock, hardware write,
  provider request, credential lookup, tag/Release, or announcement occurred.
  Candidate-attempt-3 artifacts are rejected bytes and must not be published or
  reused.
- The owner approved the Windows-first imported-media correction recorded in
  `docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md` on
  2026-08-01. IMF-1 is implemented, locally verified, and clean-reviewed:
  Python
  and the browser share exact canonical geometry vectors, normal and Move &
  zoom renders intersect every requested target's limits, the backend returns
  the exact canonical state it used, and the browser adopts it atomically. The
  rejected same-size 40x5 pan now clamps to zero and retains the complete
  source raster. Its focused and complete CI-equivalent gates pass; canonical
  evidence is in the repair plan. Its single required `fable-review` run used
  `claude-fable-5` at `xhigh` over exact implementation commit `4a9e6b8` and
  returned clean with no findings. No dependency or prohibited path changed.
- IMF-2 is implemented, locally verified, and clean-reviewed. The
  source overlay remains mounted for an active media draft and now uses the
  primary destination's exact resolved raster box; only that viewport clips,
  leaving the LED grid and destination border intact. Pointer, wheel, keyboard,
  preset, zoom, stretch, and sampling changes reveal source view before one
  canonical commit path invalidates Preview and updates controls/status
  synchronously. Primary-pointer sessions are ID-scoped and stage-scoped,
  release on up/cancel/lost capture, and continue without error when synthetic
  capture raises `NotFoundError`. Its focused 134-web/181-Python gate and red
  proofs pass. Its single required `fable-review` run used `claude-fable-5` at
  `xhigh` over exact implementation commit `041c26f` and returned clean with
  no findings. No dependency or prohibited path changed.
- IMF-3 is implemented, locally verified, and clean-reviewed. Pathless
  asymmetric GIF/PNG/BMP fixtures now drive one isolated native PyWebView audit
  through import,
  framing, exact Preview pixels, Apply/Undo, the complete Library ownership
  workflow, and Cancel. Source and exact rebuilt frozen WebView2 audits pass at
  1000x680 and 1280x800 with no console or layout findings; the Windows build,
  native-tree audit, installer build, and frozen smoke pass. The visual audit
  activates its real native window before asserting focus; a deliberately
  hidden launch fails the explicit focus precondition and is not valid evidence.
  The canonical full command chain reached and produced both valid `uv build`
  archives after every guarded test/compile/syntax stage returned zero, but PTK
  lost its outer transport immediately after artifact creation and no duplicate
  run was submitted. Its single required `fable-review` used `claude-fable-5`
  at `xhigh` over exact implementation commit `25c58d5` and returned clean with
  no findings. Post-repair qualification then passed: the controlled current
  Windows package install, recursive prohibited-native-code audit, frozen
  smoke, and uninstall were clean, with no install directory left; exact-head
  CI run `30699525122` and Desktop run `30699525134` attempt 1 passed every
  required job at `875437ab432462d0c88ee73733d1d84e65261cfe`. No dependency or
  prohibited path changed.
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

- Repair `cl-11` without expanding LSR-2: keep explicit prepared sessions in
  the bounded LRU while sessionless full renders use transient decoded state and
  destination-scoped epochs independent of cache residency. Guard, mutation-
  prove, fully verify, commit, push, and obtain its one per-finding verdict;
  then repair `cl-12` the same way before closing LSR-2 and starting LSR-3. Do
  not restart R65-2 until LSR-1 through LSR-10 are implemented,
  guarded, verified, accepted, and pushed. A replacement candidate must repeat
  every release gate and cannot mix evidence from any rejected attempt with new
  bytes.
- The approved `0.1.65` release plan remains recorded at
  `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md`; it records all
  three rejected candidates and is paused behind the redesign.
- `.agents/machines.md` owns all host details, including the current connection
  information for `nagatha`. `win-arm-vm` remains SmartScreen observation only
  and Windows ARM64 remains outside the `0.1.65` public asset set.
- Tagging, release publication, hardware writes, live provider use, macOS Open
  Anyway, and announcement remain separately gated actions.
- Separately, the accepted `cl-2` review recorded a pre-existing read-only
  `get()` / `resolve_asset()` retired-job exposure as a candidate requiring an
  owner scope decision; it is not approved implementation work.

## Blockers

- No blocker prevents the LSR-2 finding repairs. R65-2 is blocked on completion
  and owner acceptance of the complete redesign. Live provider requests,
  keyboard writes, macOS Open Anyway, tag creation, release publication, and
  announcements remain separately gated actions for their later slices.
