# AM Configurator 0.1.65 Public Release

**Status:** Owner-approved on 2026-07-31. Candidate attempts 1 at `2685a98`, 2
at `c2f6fce`, and 3 at `09232fb` were rejected during exact-candidate
qualification. Attempt 3 was rejected during R65-6 on 2026-08-01 because
switching from Per-key to Head matrix while preview playback remained active
rendered incorrect Head matrix lighting. No candidate is active. A correction
now requires completion and owner acceptance of the approved
`2026-08-01-lighting-studio-human-first-redesign.md` before R65-2 can restart.
Live
provider requests, macOS Open Anyway, hardware writes, tag or GitHub Release
creation, and announcement posting remain separate action-time gates.

## Objective

Publish one normal, reproducible AM Configurator `0.1.65` GitHub Release for:

- macOS arm64;
- Windows x64; and
- Linux x86-64.

The release must expose exactly one product version, bind every public byte to
one final `main` commit and GitHub workflow run, state the permanent unsigned
platform status accurately, preserve the device-write safety boundary, and
support a later r/AngryMiao announcement without overstating hardware or AI
qualification.

## Authority and supersession

- `AGENTS.md` and `.agents/repo-guidance.md` own process, verification, device
  safety, and action authorization.
- `.agents/decisions.md` owns canonical version `0.1.65`, permanent unsigned
  installers, procedural-only AI, the FFmpeg prohibition, one-request AI
  behavior, product claims, and application identity.
- `docs/superpowers/plans/2026-07-29-product-experience-remediation.md` owns the
  P6 implementation and exact-artifact prerequisite evidence at `4a3c6eb`.
- `docs/superpowers/plans/2026-07-30-ffmpeg-removal-and-dependency-audit.md`
  owns dependency and retired-runtime absence proof.
- `docs/superpowers/plans/2026-08-01-imported-media-framing-repair.md` records
  the candidate-attempt-2 defect and proposed correction. Its status controls
  whether repair implementation is authorized.
- `docs/neon-80-hardware-verification.md` owns historical physical Neon 80
  evidence. A new exact-candidate result appends to it; it never rewrites the
  historical N10 record.
- `.agents/machines.md` owns host capabilities and limitations.
- `.agents/push-policy.md` owns ordinary canonical-`origin` pushes. It does not
  authorize tags, noncanonical remotes, Releases, or announcements.
- `docs/superpowers/plans/2026-07-28-public-release.md` remains historical
  evidence for the rejected unpublished `0.1.64` candidate. This plan
  supersedes it for every `0.1.65` preparation, qualification, publication,
  rollback, and announcement action.

## Current baseline

Re-verify these facts at execution time.

- Canonical source version is `0.1.65` in
  `am_configurator/_version.py`.
- Canonical `origin/main` is
  `09232fb695a1a8b1ebc470ac470509ebbace3eb2`; local `main` matched it when
  candidate attempt 3 was rejected. Reconcile the exact refs again at
  execution time.
- CI run `30699706921` and Desktop installers run `30699706913` attempt 1
  passed for `09232fb`. Their artifacts belong to rejected candidate attempt 3
  and must not be published.
- P6 implementation commit `4a3c6ebadcc5d0fc1730c06b853af8e28c686ca5`
  passed exact-head CI and three-platform artifact qualification. That proves
  the release pipeline and product implementation, but it is not the final
  release candidate because this plan and the `0.1.65` release packet must land
  first.
- GitHub's current normal/latest Release is `v0.1.11`. Tag and Release
  `v0.1.65` do not exist.
- `docs/releases/0.1.64.md` and
  `docs/announcements/reddit-0.1.64.md` are rejected historical drafts and must
  not be copied mechanically or republished.
- `docs/installing.md`, issue intake, package metadata, native artifact naming,
  and About already resolve to `0.1.65`.
- `netwatch-01` can build, install, audit, smoke, and uninstall Windows
  packages, but SmartScreen is disabled and that host cannot prove the normal
  SmartScreen path.
- `michael-mac` is the known macOS arm64 packaging and Neon 80 host. Its exact
  current availability and tool state must be rechecked before use.
- No live provider credential, paid request, fresh hardware write, tag,
  Release, or announcement has been used for `0.1.65`.

## Fixed constraints

1. `0.1.65` is the only release identity. Workflow numbers, dates, attempts,
   and commit counts are provenance, never versions.
2. The rejected `0.1.64` packet is never revived, retagged, uploaded, or used
   as current copy.
3. Windows remains Authenticode-unsigned. macOS remains ad-hoc signed and not
   notarized. Do not obtain, borrow, simulate, or imply platform publisher
   trust.
4. Never tell users to disable Gatekeeper, SmartScreen, Defender, antivirus,
   quarantine, or browser protections globally. Do not add security-bypass
   commands to code or documentation.
5. FFmpeg and AI video remain prohibited in runtime, build, package, CI,
   recovery, optional extras, and release claims.
6. AI generates only a validated procedural LED recipe rendered locally. Live
   Ollama or remote-provider requests are not release prerequisites and are
   skipped unless separately authorized at action time.
7. Manual configuration works without AI or an account and is the release
   headline path. Any AI path not live-qualified on the exact candidate remains
   explicitly experimental and out of the headline.
8. A hardware read is not permission to write. Every exact-candidate keyboard
   write requires a fresh owner authorization immediately before the write,
   typed device identity, normal UI confirmation, and the device's physical
   unlock when applicable.
9. Plan approval is not tag, Release, publication, Reddit, provider-cost,
   credential-use, macOS Open Anyway, or hardware-write approval.
10. Do not upload candidates to third-party scanners, mirrors, or services
    without separate outward-action approval.
11. Do not weaken tests, package audits, identity checks, confirmation, or
    verification because installers are unsigned.
12. No paid external review is required for release-packet-only documentation.
    A discovered code defect rejects the candidate and returns to a separately
    approved fix slice; do not launch or rerun a paid reviewer implicitly.

## Release identity contract

The final release must satisfy all of the following simultaneously:

- source, About, Python metadata, native bundles, filenames, manifest, tag,
  Release title, release notes, installation docs, and announcement say
  `0.1.65`;
- tag is `v0.1.65`;
- Release title is `AM Configurator 0.1.65`;
- Release is normal/latest: draft false and prerelease false;
- workflow event is `push`, branch is `main`, and every required job concludes
  `success`;
- candidate `headSha`, tag target, remote canonical `main`, and the source
  commit in `release-manifest.json` are identical at publication time;
- the public asset set is exactly:
  - `AM-Configurator-0.1.65-macOS-arm64.dmg`;
  - `AM-Configurator-0.1.65-Windows-x64-Setup.exe`;
  - `AM-Configurator-0.1.65-Linux-x86_64.AppImage`;
  - `SHA256SUMS.txt`;
  - `release-manifest.json`;
- the three installer hashes and byte sizes agree in the manifest, checksum
  file, downloaded files, attestations, owner publication gate, and Release
  read-back; and
- no tag, published asset, or Release record is moved, overwritten, or reused
  after publication.

## Evidence inheritance rule

P6 evidence may reduce repeated exploratory work, but never replace an
exact-candidate check named below.

- Record a `git diff --name-status 4a3c6eb..<candidate>` before qualification.
- P6's 36-state native WebView2 visual matrix may be cited only when the diff
  proves no application web asset, desktop host, model geometry, package input,
  or relevant test changed.
- Even when inherited, the exact candidate still runs native smoke, About
  version, first-launch, platform trust, privacy, and representative UI checks.
- Any change to application source, package inputs, workflow, device code,
  release tooling, or installer scripts invalidates the relevant inherited
  evidence and requires that gate in full.
- Documentation-only changes do not excuse source/package metadata, secret,
  link, or public-claim verification.

## Implementation slices

Every slice ends with the smallest relevant automated checks, `git diff
--check`, a clean status audit, and an independent commit. Do not begin code
changes or release preparation until the owner approves this plan.

### Slice R65-0 — Approve and activate this plan

**Status:** Complete on 2026-07-31.

Files:

- this plan;
- `.agents/decisions.md`;
- `.agents/state.md`;
- historical release-plan successor pointer.

Completion record:

1. Change this plan's status to owner-approved with the date.
2. Record the approved `0.1.65` release scope and action boundaries in
   `.agents/decisions.md` without duplicating detailed gates.
3. Point `.agents/state.md` here as the current release work.
4. Keep every action-time authorization pending.

Commit:

```text
docs: approve 0.1.65 release plan
```

### Slice R65-1 — Build the current release packet

**Status:** Complete on 2026-07-31.

Files:

- new `docs/releases/0.1.65.md`;
- new `docs/announcements/reddit-0.1.65.md`;
- `README.md` only if a current release-note link is required;
- `docs/installing.md` only for evidence-backed corrections;
- `.github/ISSUE_TEMPLATE/bug_report.yml` only for identity corrections;
- `tests/test_packaging.py` for current-packet and stale-link guards;
- this plan and `.agents/state.md` for slice evidence.

Requirements:

1. Write `0.1.65` copy from current code, tests, decisions, and completed
   qualification records. Do not search-and-replace the rejected draft.
2. Describe manual Keymap, Macros, Lighting, Library, and device workflows
   before optional AI.
3. State that AI is optional/off by default, produces procedural LED settings,
   and renders locally. Do not mention AI video or FFmpeg in public marketing
   copy.
4. Name only supported device families and qualification actually proved.
5. State Neon's no-LED-read-back limitation and full-write replacement boundary
   accurately.
6. State permanent unsigned platform facts once in ordinary language and link
   to the narrow installation guide.
7. Use the five exact asset names from the release identity contract.
8. Keep remote provider paths experimental unless exact-candidate live smokes
   are separately authorized and pass.
9. Create the Reddit file as an unposted draft. Its predictable release URL may
   name `v0.1.65`, but the draft must say nothing was posted and must never be
   submitted during this slice.
10. Add regression guards proving the active packet uses `0.1.65`, the README
    does not target the historical `0.1.64` notes, the historical files retain
    their rejection banner, and all three current installer names agree.
11. Guard-prove each new test with the repository's red/green procedure.
12. Run the full canonical verification entry point because packaging tests and
    public setup instructions are release inputs.

Commit:

```text
docs: prepare 0.1.65 release packet
```

Completion record (2026-07-31):

- Fresh `docs/releases/0.1.65.md` and unposted
  `docs/announcements/reddit-0.1.65.md` were written from current product,
  qualification, and decision records rather than copied from the rejected
  packet. The copy leads with manual configuration, keeps optional AI within
  the experimental claim boundary, and names exactly the five release assets.
- `README.md`, `docs/installing.md`, and the bug-report template already carried
  the current identity and required public guidance, so no correction was
  needed on those surfaces.
- The focused current-packet guard failed first because the `0.1.65` release
  notes were absent, then passed with the new packet. It also proves the three
  installer names agree with the installation guide, the README does not point
  at historical notes, the rejected packet retains its banner, and prohibited
  retired-generation terms do not enter current marketing copy.
- The complete automated gate passed: 647 Python tests with 5 expected skips,
  127 web tests, Python compilation, all required JavaScript syntax checks, and
  `0.1.65` source-distribution and wheel builds.
- No provider request, credential use, hardware interaction, macOS Open Anyway,
  tag, Release, or announcement action occurred. The Reddit copy remains a
  repository draft only.

### Gate R65-G1 — Prove post-freeze checks are runnable

**Status:** Complete on 2026-08-01. Every required post-freeze execution path
has a verified host, tool, operator, restore source, and action boundary. This
readiness result permits R65-2; it authorizes no hardware write, macOS Open
Anyway action, live provider request, tag, Release, or announcement.

Do not begin R65-2 merely because the release packet and automated gate pass.
A frozen SHA is useful only when every release-blocking exact-candidate check
has a verified execution path. Do not create a candidate that must wait for a
known-missing host, operator, restore source, owner ruling, or action authority.

Resolve and record all of the following before candidate freeze:

1. Revalidate `michael-mac`, `netwatch-01`, and the required Linux environment.
   Confirm the tools, download paths, isolated test roots, and human operators
   needed by R65-3 through R65-6 are available for one scheduled qualification
   window.
2. Identify and verify an independent normal Windows host whose SmartScreen is
   already enabled. If none is available, obtain the cold owner ruling required
   by R65-4 before freeze; `netwatch-01` is not evidence and changing its
   security settings is not a fallback.
3. Confirm `michael-mac` can preserve normal quarantine/Gatekeeper state and
   execute the download, hash, attestation, DMG, native-smoke, and UI paths.
   Confirm the owner will be reachable for the separate exact-artifact Open
   Anyway gate. Do not treat this readiness check as that authorization.
4. Non-destructively preflight the Neon 80 path: the intended keyboard and
   direct connection are available, competing HID owners can be closed, the
   current keymap/macros can be read and exported, and the complete desired
   configuration plus LED restore source exists with private hashes. Confirm
   the owner will be reachable for the fresh single-write gate immediately
   before R65-6. That fresh authorization cannot be granted by this gate.
5. Confirm an operator can run the exact-artifact UI/privacy matrix with
   isolated application-data and Library roots and without touching a real
   user Library.
6. Record that live provider requests remain skipped and are not a release
   prerequisite. Do not create a provider-authorization blocker when the
   release claims remain within the fixed experimental boundary.
7. Present unresolved owner rulings one at a time. Silence, plan approval, a
   readiness statement, or a historical authorization never satisfies an
   action-time gate.
8. Record the sanitized readiness result in this plan and `.agents/state.md`,
   update `.agents/machines.md` only when a capability fact changed, and commit
   it before R65-2. Keep device identities, private paths, configuration bytes,
   and credentials out of the repository.

Commit:

```text
docs: record 0.1.65 candidate readiness
```

If any required execution path is absent or any pre-freeze ruling is declined,
stop before R65-2. If a recorded readiness fact becomes false after freeze,
reject the candidate instead of leaving `main` indefinitely frozen.

Readiness record (2026-07-31 through 2026-08-01):

- The current session is local on `netwatch-01`; local Windows tooling and the
  disabled SmartScreen state were reverified without SSHing back into the same
  host.
- `nagatha` is reachable over SSH as an owner-operated arm64 macOS 26.6 host.
  Gatekeeper is enabled, exact-artifact hash/DMG/signature tools and a writable
  temporary path are available, and the owner can perform later GUI steps.
- `gabrielle` is reachable over SSH as an x86-64 Arch Linux host with GitHub
  CLI, SHA-256, file inspection, FUSE, and writable temporary storage available
  for the exact AppImage path.
- `win-arm-vm` is reachable over SSH as a clean Windows 11 24H2 ARM64 VM with
  no SmartScreen-disabling override or policy and active Defender protection.
  It is ready to observe the exact x64 candidate's normal Edge-download warning
  path under Windows x64 emulation without changing security settings.
- The same VM proved an exploratory native ARM64 installer can be built when
  ARM64 CPython is selected explicitly and `hidapi` is compiled with Visual C++.
  Its install/smoke/uninstall path passed, but ARM64 is not a `0.1.65` public
  asset and the exploratory bytes are not release evidence.
- The owner downloaded x64 artifact `8810968202` from successful Desktop run
  `30677373584` at `5867fa8` normally through Edge. The ZIP retained Internet
  zone 3 metadata. SmartScreen displayed **Windows protected your PC**, named
  an unrecognized app, exposed the expected unknown-publisher and **Run anyway**
  path under **More info**, then allowed the installer and x64 application to
  launch. The installed x64 binary remained `NotSigned` and its frozen smoke
  passed under Windows ARM emulation. This is preflight evidence only; R65-4
  repeats the observation on the final exact candidate.
- On 2026-08-01 the production shallow scan found one unambiguous Vial/raw-HID
  candidate while the Neon 80 and AFA A2 were both connected. Only that
  candidate was opened. The deep gate identified `NEON80`, definition
  `AM Neon 80`, Vial protocol 5, and the validated 87-key projected layout.
  Windows PnP evidence bound it to a healthy local USB bus with no RDP, VM, or
  virtual-device marker. No competing HID application was running.
- The Neon read returned four 90-key layers, four populated macros, the
  device-reported 16-slot/6677-byte macro capacity, and no identity error. An
  importable keymap/macro profile was exported and validated with zero errors
  or warnings. Its lighting fields are synthetic placeholders because Neon
  exposes no LED read-back; it is not represented as a lighting backup.
- The current device keymap and macros exactly match the known complete desired
  profile on `nagatha`. That profile matches the previously documented recovery
  hash and contains nonempty authored LED tracks. The readback export and
  restore-profile hashes are recorded in a private machine-local manifest;
  paths, hash values, macro content, serial, firmware UID, and configuration
  bytes remain outside the repository.
- The AFA A2 was not opened. No keyboard write, macOS Open Anyway action,
  security-setting change, provider request, or credential use occurred. The
  owner remains reachable for the separate fresh single-write and Open Anyway
  gates when R65-4 and R65-6 reach those action points.

### Slice R65-2 — Freeze the final source candidate

Preconditions:

- R65-0, R65-1, and the R65-G1 readiness record are committed;
- every R65-G1 readiness fact remains true;
- no approved implementation work remains;
- `main` and canonical `origin/main` are reconciled;
- worktree and index are clean;
- no untracked credential, `.env`, profile, firmware identity, captured user
  data, reviewer cache, or oversized binary is eligible for commit;
- `0.1.65` is unchanged; and
- the canonical automated gate passes from the repository-guidance entry
  point.

Procedure:

1. Run `actionlint` when already available; do not install an unplanned tool.
2. Audit source and wheel/sdist contents, dependency ownership, notices,
   version consumers, release packet links, and workflow action pins.
3. Run the current native preflight available on each maintained host. Local
   artifacts are preflight evidence, never substituted for GitHub bytes.
4. Push ordinary verified `main` to canonical `origin` under the push policy.
5. Record the resulting remote SHA as the candidate. From this point until the
   candidate is accepted or rejected, do not make an evidence/bookkeeping
   commit that moves `main`.
6. Keep transient downloaded bytes and machine-local evidence only in explicit
   ignored `.local` paths. GitHub run/manifest identity is the recoverable
   pre-publication record. Durable completion bookkeeping lands after
   publication or candidate rejection.

Any source or documentation correction after step 4 rejects this candidate and
starts R65-2 again on a new commit.

### Slice R65-3 — Qualify the final GitHub candidate

Use the frozen SHA only.

1. Wait for CI and Desktop installers for that exact push.
2. Require success from Windows, primary Linux, Python 3.11 Linux, macOS, all
   three installer jobs, candidate metadata, and release provenance.
3. Require event `push`, branch `main`, attempt identity recorded, and
   `headSha` equal to remote `main`.
4. Download all four Actions artifacts into a new explicit temporary
   directory: three platform artifacts plus candidate metadata.
5. Require exactly the five public files and no unexpected installer-like
   file.
6. Regenerate manifest and checksum files with
   `build_tools.release_manifest` using the run's version, SHA, run ID, run
   number, and repository. Require byte-identical outputs.
7. Verify size and SHA-256 for every installer.
8. Run `gh attestation verify --repo roethlar/AMKB-GUI` for all three
   installers, `SHA256SUMS.txt`, and `release-manifest.json`. Require SLSA
   provenance to resolve the same workflow, repository, branch, push trigger,
   and source SHA.
9. Require PE, ELF, and UDIF file-format magic and canonical filenames.
10. Inspect candidate package/install trees for required license/notices, Linux
    udev data, unexpected local paths or credentials, and retired FFmpeg/video
    runtime, helper, fixture, or metadata markers.
11. Record artifact expiry and complete publication before expiry; never treat
    temporary Actions URLs as public downloads.
12. Remove controlled temporary downloads after their evidence is captured.
    Verify the exact owned path before recursive deletion; the GitHub run is the
    recovery source.

Any mismatch rejects the candidate. Do not create a tag or Release.

#### Candidate attempt 1 — rejected 2026-08-01

- R65-2 froze `2685a9832e0982d8b52ea45a4becd8a75eb48d01` after the
  clean-environment gate, dependency/package audit, and Windows x64, macOS
  arm64, and Linux x86-64 native preflights passed. `actionlint` was not
  installed and was skipped as required.
- Exact push runs `30683516281` (CI) and `30683516302` attempt 1 (Desktop)
  passed every required job. The five-file set, sizes and hashes, byte-identical
  regenerated metadata, PE/ELF/UDIF magic, and source-bound SLSA attestations
  all passed; the Desktop artifacts expire on 2026-08-31.
- Recursive extraction of the exact Linux AppImage found FFmpeg decoder,
  demuxer, source-path, and stub strings in bundled
  `libQt6WebEngineCore.so.6` and `libQt6Multimedia.so.6`, including
  `FFmpegAudioDecoder`, `FFmpegDemuxer`, and `QT_INSTANT_LOAD_FFMPEG_STUBS`.
  This violates the unconditional runtime/build/package prohibition in
  `.agents/decisions.md`, so the complete candidate is rejected.
- R65-4 through R65-9 did not complete. Structural checks of the exact macOS
  DMG passed before rejection; the partial controlled Windows install was
  successfully uninstalled and left no directory. No normal-browser
  Gatekeeper or SmartScreen observation, Open Anyway action, UI/privacy gate,
  hardware write, live provider request, tag, Release, or announcement
  occurred.

#### Candidate attempt 2 — rejected 2026-08-01

- R65-2 froze `c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7` after the
  Linux GTK/WebKitGTK correction and exact-head preflights passed. Exact push
  runs `30687960889` (CI) and `30687960898` attempt 1 (Desktop) passed every
  required job.
- R65-3 passed. The exact Linux, Windows, and macOS installer SHA-256 values
  were respectively
  `a70dd68f59dcbdf528af4cb773cfbba22b9bc4e051be64af76b541d4ad5ff11b`,
  `49d8a5c503addf996c23cea8a49036327f9d86a9c8e13fdc16e486e3f59843a1`,
  and `60eb58fc3bc321fa66ad163e600bf5c2febd21ff10c2219ebc8625c49661c773`.
  The five-file set, regenerated metadata, sizes, hashes, file magic,
  attestations, structural native audits, notices/licenses, and Linux udev
  checks passed. The artifacts expire on 2026-08-31.
- R65-4 passed for the exact Windows x64, macOS arm64, and Linux x86-64
  artifacts, including the required native smoke and platform trust-state
  observations. Those results remain evidence for the rejected bytes only and
  must be repeated for a replacement candidate.
- R65-5 failed while framing a 40x5 imported animation for the CyberBoard 40x5
  display. Pointer dragging showed no source movement but changed hidden pan
  state; later keyboard panning and Preview rendered the source almost entirely
  black/off canvas. The owner explicitly rejected the behavior.
- R65-6 through R65-9 did not begin. Apply was not used, no keyboard write or
  provider request occurred, and no tag, Release, or announcement was created.
  The macOS application was closed, its DMG was ejected, and the controlled
  downloaded/test data was removed. GitHub Actions remains the recovery source
  until artifact expiry.
- The proposed correction is isolated in
  `2026-08-01-imported-media-framing-repair.md`. Candidate qualification may
  restart only after that plan is owner-approved, implemented, verified,
  reviewed, and pushed.

#### Candidate attempt 3 — rejected 2026-08-01

- R65-2 froze `09232fb695a1a8b1ebc470ac470509ebbace3eb2` after the
  imported-media framing correction was implemented, verified, reviewed, and
  qualified. Exact push runs `30699706921` (CI) and `30699706913` (Desktop
  installers) attempt 1 passed.
- R65-5 passed for the exact macOS candidate. The owner accepted the macOS
  qualification, including the substantive native WKWebView media workflow;
  its controlled machine-local audit found no console, provider, credential,
  hardware-write, or layout failure.
- R65-6 failed before the write. With preview playback started on Per-key,
  switching to Head matrix while playback remained active rendered an
  incorrect sparse/dark Head matrix pattern instead of its saved animation.
  Owner-provided normal and failing screenshots are retained as controlled
  machine-local evidence. This is a reproducible target-transition visual
  mapping failure and rejects the complete candidate under the R65-6 failure
  rule.
- The initially loaded portable profile also did not contain the owner's
  current saved lighting, so it was not a valid restoration source and its
  proposed write gate was canceled.
- No Write action, typed device confirmation, physical unlock, hardware write,
  live provider request, tag, Release, or announcement occurred. Attempt 3 is
  permanently rejected and its artifacts must not be published or reused.
- Candidate qualification may restart only after the separately approved
  Lighting Studio redesign corrects the complete rejected interaction model,
  including cross-target preview behavior, and is implemented, guarded,
  verified, accepted, and pushed.

### Slice R65-4 — Exact-artifact platform qualification

Use only bytes downloaded in R65-3.

#### macOS arm64

On `michael-mac`:

1. Obtain the candidate through the normal browser/GitHub download path.
2. Match SHA-256 and attestation.
3. Run `hdiutil verify`, mount read-only, verify deep/strict ad-hoc signature,
   and require no Developer ID authority or notarization ticket.
4. Run frozen and real WKWebView native-policy smoke.
5. Observe the normal first-launch Gatekeeper behavior without removing
   quarantine metadata.
6. Stop for a separate macOS Open Anyway authorization before using the
   per-application System Settings flow.
7. After authorization, require launch and About `0.1.65`.

#### Windows 11 x64

On `netwatch-01`:

1. Download the candidate, match SHA-256 and attestation, and require
   `Get-AuthenticodeSignature` status `NotSigned`.
2. Perform a per-user controlled install into an explicit owned temporary
   directory.
3. Require About `0.1.65`, frozen/native smoke, one third-party notice, zero
   retired-runtime path/content hits, successful uninstall, and no remaining
   install directory.
4. Do not change SmartScreen, Defender, or antivirus settings. Because this
   host has SmartScreen disabled, it cannot prove the documented warning flow.
   Obtain that observation on `win-arm-vm`, preserving its default protection
   state and downloading the exact x64 candidate normally through Edge so the
   file receives Mark-of-the-Web. Do not substitute the local exploratory ARM64
   build or an SCP transfer.
5. If no such host is available, Windows publication remains blocked pending a
   cold owner ruling. Do not infer, simulate, or silently waive SmartScreen
   evidence.

#### Linux x86-64

1. Require the exact GitHub AppImage job's native smoke result, matching hash,
   and attestation.
2. Extract or inspect the AppImage without installing new dependencies. Require
   notices/licenses and the shipped Neon 80 udev rule.
3. Require `--print-udev-rule` to emit the documented rule in a suitable Linux
   environment.
4. Record that no physical Linux keyboard test occurred unless one actually
   runs under a separate hardware authorization.

Any corruption, malware classification, unexpected trust state, launch
failure, or behavior outside the documented narrow approval flow blocks that
platform and therefore the complete three-platform release.

### Slice R65-5 — Exact-artifact UI, privacy, and claim qualification

Use the exact macOS candidate with isolated temporary application-data and
Library roots. Do not point at a real user Library.

Required checks:

- every launch opens Keymap;
- About reports `0.1.65`;
- first-run, Keymap normal/technical, Macros normal/Advanced, Switch LED and
  display Lighting targets, Library empty/error, Settings setup-required, and
  device/write/incompatible dialogs remain usable at 1000×680 and 1280×800;
- representative CyberBoard geometry matches the canonical physical layout and
  its display remains 40×5;
- AI defaults off; AI controls are hidden; no Ollama inventory, remote API,
  credential lookup, or Keychain prompt occurs in that state;
- enabling AI reveals repair/setup controls without reporting false readiness;
- GIF, PNG, and BMP import, pan/zoom/stretch, local effects, preview, Apply,
  undo, Library save/apply/remove/undo/restore/permanent-delete confirmation,
  and compatible/blocked explanations stay inside the temporary Library;
- manual Keymap, Macros, and Lighting remain complete without AI;
- focus visibility, keyboard traversal, reduced motion, editable text
  selection, and noneditable-text behavior remain usable;
- no console error, path, credential, profile content, firmware UID, or private
  prompt appears in screenshots or evidence; and
- no hardware write is initiated.

Provider policy:

- Default action is **skip live AI requests**. Automated/fake-server coverage
  and prior implementation qualification are sufficient for release when copy
  says exact-candidate live providers were not tested.
- An already-installed Ollama model may be tested only after a separate live
  prompt authorization. Do not pull, update, copy, or delete a model.
- A remote API provider may be tested only after separate credential and spend
  authorization for that named provider and one request. Never batch providers
  under one approval.
- Every explicit Generate action makes one request with no automatic retry.
- Record provider, model/digest, date, result, and redacted error category only;
  never record credentials or private prompt content.

### Slice R65-6 — Exact-candidate Neon 80 hardware gate

This release-blocking gate requires a fresh hardware-write authorization
immediately before the write. Historical N10 authorization does not carry.

Preconditions:

- exact GitHub macOS candidate and its verified hash are identified;
- one physical `NEON80` is connected directly;
- AM Master, Vial, VIA, QMK Toolbox, and other HID owners are closed;
- a complete portable JSON and the LED source needed to restore the owner's
  desired state are available and hash-recorded privately;
- current keymap/macros are read and exported before the write;
- the no-LED-read-back limitation is understood; and
- the owner is presented a cold gate naming the exact artifact, keyboard,
  replacement scope, restore source, and proposed single write.

After explicit go:

1. Identify `NEON80`, firmware protocol, writeability, four layers, macro
   capacity, 87-key layout, 89 axial labels, three-segment spacebar, 46×5 head,
   and side-screen derivation without publishing firmware UID.
2. Exercise one GIF and one still image through transforms/local effects in a
   temporary Library and Apply to a nonempty slot.
3. Make one reversible keymap edit while preserving the known macro set.
4. Use the normal full-write UI, type `NEON80`, perform Esc+F2 physical unlock,
   and wait for completion and verification.
5. Require exact keymap/macro read-back, persisted snapshot/source hashes, and
   visual confirmation of asymmetric axial/head orientation and independent
   timelines. Never claim LED read-back.
6. Restore the owner's desired configuration through the same guarded path if
   the acceptance pattern was temporary.
7. Append a sanitized `0.1.65` exact-candidate result to
   `docs/neon-80-hardware-verification.md` after publication or candidate
   rejection. Do not record firmware UID, serial, private macros, or private
   paths in public copy.

False success, wrong identity, partial upload, read-back mismatch, loss of a
known-restorable configuration, or visual mapping failure rejects the
candidate. No other keyboard family receives a physical write under this gate.
If fresh authorization is declined, stop for an owner ruling; do not silently
downgrade the gate or the release claim.

### Slice R65-7 — Freeze release copy and request publication approval

After R65-G1 and R65-2 through R65-6 pass without moving `main`:

1. Render the final Release body from committed
   `docs/releases/0.1.65.md`. Do not edit source merely to inject hashes already
   carried by the five assets and owner gate.
2. Verify the Reddit draft against actual qualification and keep it unposted.
3. Confirm remote `main` still equals the qualified candidate SHA.
4. Present one cold publication gate containing:
   - exact tag, title, target SHA, workflow run IDs/attempts;
   - all five asset names, sizes, and installer hashes;
   - CI, native installer, platform, UI/privacy, and Neon outcomes;
   - Windows unsigned and macOS ad-hoc/not-notarized state;
   - SmartScreen and Gatekeeper observations;
   - every AI path not live-qualified;
   - exact Release classification: normal/latest, not draft, not prerelease;
   - the proposed action: create `v0.1.65` and publish the five assets.
5. Silence or general plan approval does not authorize publication.

### Slice R65-8 — Publish and verify the GitHub Release

Only after the explicit R65-7 publication go:

1. Run `gh release create v0.1.65` with:
   - `--target <exact-qualified-SHA>`;
   - title `AM Configurator 0.1.65`;
   - committed release-notes body;
   - `--latest`;
   - exactly the five qualified files.
2. Do not pass `--prerelease`; do not create or push the tag separately. Let
   GitHub create the tag at the explicit target so tag creation cannot trigger
   another installer build.
3. Read back tag target, Release flags/title/body, asset names, byte sizes, and
   public URLs through the GitHub API.
4. From an unauthenticated context, download all five public assets and match
   hashes again. Verify installer and metadata attestations against the public
   downloads.
5. Require GitHub to report this normal Release as latest.
6. If any read-back differs, do not overwrite assets or move the tag. Apply the
   failure policy.
7. After successful publication, update this plan, `.agents/state.md`, and any
   tracker with immutable URL, tag target, hashes, and outcomes; commit and push
   that bookkeeping normally. The published tag remains fixed at the release
   target even though later bookkeeping advances `main`.

### Slice R65-9 — Finalize and gate the announcement

1. Confirm the predictable `v0.1.65` Release URL and release-notes URL work
   logged out.
2. Re-read the Reddit draft against the published assets and claim boundary.
3. Ensure the headline leads with manual keyboard configuration, not AI.
4. Name physical Neon testing only if R65-6 passed; name other families as
   implementation/automated coverage unless physically tested.
5. State exact unsigned platform facts and no-LED-read-back limitation without
   alarm branding.
6. Present a separate cold outward-message gate with the exact title, body,
   destination, and link set.
7. The owner may post it. An agent may submit, edit, comment, or cross-post only
   after explicit authorization for that exact outward message.
8. After posting, record the URL and begin the post-release watch.

## Public claim boundary

Allowed when the corresponding gate passes:

- independent open-source community application, not affiliated with or
  endorsed by Angry Miao;
- normal public release `0.1.65`;
- manual Keymap, Macros, Lighting, Library, and device configuration without an
  AI account;
- supported operating systems, architectures, and listed keyboard families;
- Neon 80 exact-candidate physical testing only after R65-6;
- other keyboard families have explicit implementation and automated fixture,
  protocol, geometry, and regression coverage;
- optional AI is hidden/off by default and produces locally rendered
  procedural LED settings;
- SHA-256 and GitHub keyless build provenance are available; and
- full writes are identity-gated, explicitly confirmed, and followed by the
  verification the device protocol supports.

Disallowed:

- official, endorsed, or supported by Angry Miao;
- signed, notarized, trusted publisher, SmartScreen-approved, warning-free, or
  malware-free;
- safe for every firmware revision or every keyboard;
- “backup from keyboard” for LED state the firmware cannot read;
- lighting verified by device read-back when only visual confirmation exists;
- all AI providers live-qualified when they are not;
- AI-generated video, bundled FFmpeg, or video recovery;
- zero network activity after a user explicitly enables/configures a remote
  provider;
- zero risk of configuration loss;
- beta/prerelease merely because packages are permanently unsigned; or
- hashes/attestations as a substitute for platform publisher identity.

## Failure and rollback policy

- Before publication, any failed required gate rejects the candidate. Preserve
  the failed run identity and evidence, fix only under an approved slice, push
  a new commit, and restart R65-2. Unpublished attempts do not consume
  `0.1.65`.
- Do not “fix” a candidate by modifying downloaded bytes, editing metadata,
  replacing one platform asset, moving a tag, or hiding a failed job.
- A documentation or claim defect found before publication still moves source
  and therefore requires a new exact GitHub candidate.
- After publication, never replace an asset or move/recreate `v0.1.65`. A code,
  package, or material documentation fix uses a deliberate new canonical
  version and complete three-platform release.
- A release-critical configuration-loss, wrong-device, partial-write, false
  verification, or malware-classification defect stops download
  recommendations. Prepare a public warning and request explicit approval for
  Release/Reddit edits.
- An expected unsigned warning is not a rollback trigger. A warning materially
  different from documented behavior or inability to launch through the narrow
  per-application flow blocks that platform before publication.
- If GitHub attestation is unavailable, do not silently omit promised
  provenance. Stop and amend this plan and release copy with owner approval.
- If one platform artifact fails, reject the complete candidate; never publish
  a mixed-run or partial three-platform set.

## Post-release watch

For the first 72 hours after the announcement:

- monitor GitHub issues and the Reddit thread for install failures, unexpected
  security warnings, configuration loss, wrong-device reports, false verified
  writes, and firmware incompatibility;
- classify reports by app version, platform, keyboard, firmware, and operation
  without requesting secrets, serials, private macros, or unsanitized profiles;
- reproduce before changing claims or code;
- treat a reproducible device-safety defect as release-critical;
- request outward-edit approval before adding a Release warning or Reddit
  comment; and
- use a new canonical patch version for fixes rather than changing published
  bytes.

Do not promise future platform signing.

## Completion criteria

This plan is complete only when:

- owner approval is recorded in this plan and `.agents/decisions.md`;
- R65-G1 proves and records that every required post-freeze qualification path
  is runnable before the candidate is frozen;
- every preparation slice is independently committed and final source is
  frozen at one canonical `main` SHA;
- canonical local verification and exact-head CI pass;
- source, About, package metadata, native artifacts, filenames, manifest, tag,
  Release, release notes, installation docs, and announcement agree on
  `0.1.65`;
- one successful Desktop run owns all three installers, metadata, and
  provenance for the exact release SHA;
- downloaded sizes/hashes, regenerated metadata, five attestations, platform
  checks, notices/licenses, udev data, and retired-runtime audits pass;
- exact-candidate platform, UI/privacy, and freshly authorized Neon 80 gates
  pass;
- SmartScreen and Gatekeeper claims match observed behavior or an explicit
  owner ruling changes the blocked scope before publication;
- unqualified AI paths are experimental and excluded from the headline;
- the owner explicitly authorizes and the agent verifies the normal/latest
  `v0.1.65` GitHub Release with exactly five public assets;
- the separately gated Reddit copy links to the verified Release and stays
  within the claim boundary;
- immutable publication evidence and announcement outcome are committed; and
- no paid signing account, self-signed certificate, security bypass, FFmpeg,
  unapproved provider request, unapproved hardware write, asset overwrite, tag
  move, or unapproved outward message occurred.
