# Repository Decisions

## 2026-08-03 — The current product/release version is 0.1.66

Status: approved by the owner on 2026-08-03 while authorizing the version
bump after the macro editor rework and README screenshot recapture.

- The current product/release version is `0.1.66`. It succeeds the `0.1.65`
  line: the `v0.1.65` GitHub Release stays a withdrawn draft, its content is
  frozen at `ebd0d043e70c31c0342a73b088f84d28357196e4`, and neither its tag
  nor its assets may be republished or moved.
- The 2026-07-28 canonical-version decision otherwise stands unchanged:
  `am_configurator/_version.py` is the canonical source, every artifact
  reports that exact version, and a version changes only through a deliberate
  source edit for a new public product release.
- Publication of `0.1.66` — tag, builds, qualification, release notes,
  announcement — is separately gated and has not happened.
- Announcement and release-note copy stays flat: changes are listed evenly
  and no feature is framed as a headline (owner ruling while correcting the
  `0.1.66` Reddit draft, 2026-08-03).

## 2026-08-03 — Trust-warning qualification is change-triggered; 0.1.65 is public

Status: approved by the owner on 2026-08-03 while closing release
qualification and explicitly authorizing publication of `0.1.65`.

- Gatekeeper and SmartScreen warning behavior is an established baseline for
  the permanently unsigned distributions. Do not reenact those warning flows
  for every new build while the signing, notarization, installer format,
  application identity, download/quarantine path, supported OS generation, and
  security mechanism remain unchanged. Continue the automated per-build
  signature-state, integrity, provenance, package, install, and launch checks.
- Re-run visible trust-warning qualification only when one of those inputs
  changes or when a concrete regression makes the baseline uncertain. A
  periodic spot check may inform maintenance but is not a release gate.
- A separate visible Windows About check was non-blocking for `0.1.65` because
  the exact version was already proven across source, package metadata,
  installer identity, and visible About evidence on the shipped application.
- Existing Neon 80 physical validation and the owner's sustained use were
  sufficient for `0.1.65`; another exact-candidate hardware write was not a
  publication prerequisite. No final-candidate hardware write was performed.
- Release `v0.1.65` is a normal/latest public release fixed at
  `ebd0d043e70c31c0342a73b088f84d28357196e4`. The Reddit announcement remains
  a separate outward-message gate.

## 2026-08-02 — Keep 0.1.65 unchanged; defer JPEG and experimental ARM CI

Status: approved by the owner on 2026-08-02 while authorizing the current
release to continue.

- Release `0.1.65` keeps its existing public asset and support contract:
  macOS arm64, Windows x64, and Linux x86-64. Do not add native Windows ARM64
  or Linux ARM64 assets, JPEG import, or related claims to this release.
- The next release plan must include JPEG media import and best-effort native
  Windows ARM64 and Linux ARM64 CI builds with quick architecture, native-tree,
  policy, frozen-smoke, and package-smoke verification.
- ARM CI remains experimental and non-blocking unless a later owner decision
  promotes either architecture. Keep its artifacts separate from candidate
  metadata, provenance, supported-platform documentation, and public release
  assets.

## 2026-08-01 — App-native exports and AM Master imports are asymmetric

Status: approved by the owner on 2026-08-01 as Lighting redesign Gate LSR-G1,
then clarified while approving the complete redesign plan.

- `docs/superpowers/plans/2026-08-01-lighting-studio-human-first-redesign.md`
  is the approved implementation plan. It authorizes LSR-1 through LSR-10 code,
  test, documentation, per-slice commits, and ordinary canonical pushes. It does
  not authorize any separately gated provider, hardware, security-setting,
  tag, release, or announcement action.
- External review follows `.agents/repo-guidance.md` under **Review Economy**;
  it is not a per-slice ritual. Run one only on explicit owner request or when
  a concrete material risk remains that local guards and CI cannot adequately
  resolve, after stating that risk and the expected cost. A review already
  launched is allowed to finish, and its first substantive result is used
  regardless of presentation; never discard, rerun, resubmit, replace, or
  substitute it without explicit owner approval. Admitted findings retain
  their actual review provenance.
- The normal `Save JSON` path includes one exact, namespaced top-level
  `_am_configurator` object when portable dynamic-layout evidence is available.
  It carries a versioned, bounded, server-validated layout projection and its
  canonical signature so the saved profile opens and renders physical Per-key
  lighting offline on another installation.
- The metadata is pathless and contains no serial, device address, credential,
  or other machine identity. Reopening accepts it only after strict validation,
  rebuilding the canonical `device_descriptor()`, and matching the signature.
- Protocol encoders extract only canonical device sections; app metadata never
  reaches transport. App-native files and local snapshots may retain it. A
  different connected dynamic-layout signature blocks write before confirmation
  or transport.
- AM Configurator exports are app-native. They do not promise compatibility
  with AM Master or another tool, and no vendor-clean export or sidecar is
  required. Strip app metadata at the hardware protocol boundary for device
  safety, not to manufacture a third-party-compatible file.
- Import compatibility is intentionally broader than export compatibility.
  Support server-validated Angry Miao AM Master full-profile JSON and AM 80
  lighting-only JSON, normalize only explicitly recognized vendor conventions,
  and report every normalization. Never infer compatibility from a filename or
  silently accept a malformed enabled section.
- A legacy dynamic-layout profile without metadata still opens. Only the
  physical surface whose geometry cannot be established is scoped unavailable;
  the application never guesses a plausible layout or blocks unrelated editing.

## 2026-07-31 — The 0.1.65 public-release plan governs release work

Status: approved by the owner on 2026-07-31 after one owner-requested
`claude-fable-5` approach review judged it `best_approach` with no findings.

- `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md` is the governing
  plan for preparing, qualifying, and publishing the `0.1.65` public release.
- Approval authorizes release-packet work, read-only qualification, and ordinary
  canonical-`origin` pushes after the plan's prerequisites pass. Gate R65-G1
  must pass before an exact candidate is frozen.
- Every action-time authorization named by the plan remains pending. Plan
  approval is not authority for those actions.

## 2026-07-30 — Review data is substantive and reruns are owner-gated

Status: approved by the owner on 2026-07-30.

- Use a completed review's substantive data regardless of presentation or
  envelope formatting; formatting alone never justifies discarding a review.
- Do not re-prompt, resubmit, or rerun a review without explicit owner
  approval. If required result data is genuinely unavailable, stop and ask.
- An approval to retry authorizes only the specifically approved retry count.

## 2026-07-30 — AI is procedural-only and FFmpeg is prohibited

Status: approved by the owner on 2026-07-30 and clarified by the owner on
2026-08-01. This supersedes every earlier decision or plan statement that
retains AI video generation, AI-video recovery, an FFmpeg runtime, or an
FFmpeg build path.

- AI produces only a strict procedural LED recipe. The application validates
  and renders that recipe locally into exact-target LED frames.
- The product does not request, download, process, resume, display as a
  generated result, or otherwise consume AI video.
- FFmpeg is not a runtime, build, test, CI, packaging, recovery, or optional
  dependency. The project never builds FFmpeg from source and never substitutes
  a prebuilt FFmpeg binary.
- An incidental textual reference to the FFmpeg name inside a required,
  non-FFmpeg native library is not itself an FFmpeg dependency or
  implementation. Native qualification distinguishes those references from
  FFmpeg/libav libraries, packages, plugins, paths, linked symbols, embedded
  decoder/demuxer implementations, and source fingerprints, all of which
  remain prohibited. This distinction is structural, never a per-file
  allowlist.
- Historical video-generation jobs are not resumable. Removing their execution
  path must not delete user files automatically.
- Every direct dependency and bundled build tool must own a live supported
  product or artifact responsibility. Dead, duplicate, historical-only, or
  speculative dependencies are removed rather than retained for compatibility
  with retired behavior.

## 2026-07-29 — Ollama is a configurable backend and generation never auto-retries

Status: approved by the owner on 2026-07-29 while rejecting the current release
candidate's AI and human-facing product behavior. This supersedes every earlier
decision or plan statement that makes Ollama loopback-only, excludes Ollama
Cloud inventory, or permits automatic local-model correction retries.

- Ollama is one backend whose server URL is user-configurable.
  `http://127.0.0.1:11434` remains the default, and users may configure another
  HTTP(S) Ollama installation on the LAN.
- Every structurally valid completion-capable model returned by that Ollama
  server is eligible, including Ollama Cloud entries. Cloud execution is
  clearly labelled and its prompt-routing implications are disclosed.
- The application sends requests only to the configured Ollama origin and
  fixed Ollama API paths. Inventory `remote_host` metadata never becomes an
  application connection target.
- The application never pulls, creates, updates, copies, removes, or otherwise
  manages Ollama models.
- One explicit Generate action makes exactly one model request. A schema,
  semantic, quality, transport, timeout, or cancellation failure stops that job
  without an automatic corrected generation. Another request requires another
  explicit user action.
- Shipped UI and README language is written for keyboard owners and gamers.
  Internal terms such as durable jobs, banking, procedural recipes, raster
  identities, and deterministic seeds do not appear in the normal user path.

## 2026-07-28 — The application has one canonical product version

Status: approved by the owner on 2026-07-28 while correcting the public-release
plan; updated by owner-approved Product Slice P6 on 2026-07-31 after the
unpublished `0.1.64` candidate was rejected.

- The current product/release version is `0.1.65`.
- The rejected unpublished `0.1.64` candidate is historical and must not be
  reused or published.
- `0.1.64` was the first non-regressive canonical identifier after native
  builds had already displayed `0.1.63`. Its rejection does not revive the
  workflow-derived `0.1.34` identifier, which remains historical build evidence
  and must not become a later public release.
- `am_configurator/_version.py` is the canonical source. Source metadata, UI,
  local and CI builds, package metadata, native bundles/installers, filenames,
  manifests, tags, releases, and announcement copy must all report that exact
  version.
- Local build counters, GitHub workflow run numbers, dates, commit counts, and
  packaging attempts are diagnostic provenance only. They never become
  application versions.
- Failed or repeated unpublished build attempts retain the canonical version.
  A version changes only through a deliberate source edit for a new public
  product release.

## 2026-07-28 — Application chrome is quiet and launch always opens Keymap

Status: approved by the owner on 2026-07-28 while reviewing the native
application.

- Native/browser chrome owns the product title. The application content does
  not repeat the logo and `AM Configurator` title as a nested header.
- The version is absent from normal application chrome. One unobtrusive About
  link opens a small dialog that reports the canonical version and ordinary
  project information; it is not styled as a primary action or badge.
- Every launch opens Keymap unconditionally. Saved/session routes, the prior
  section, Settings, automatic workflow navigation, and a startup URL hash do
  not change the initial route. Normal navigation and history remain available
  after startup, and active lighting-job recovery remains independent.

## 2026-07-28 — Installers are permanently platform-unsigned

Status: approved by the owner on 2026-07-28 as a permanent product constraint.

- Releases never depend on or pursue an Apple Developer Program membership,
  Authenticode certificate, paid developer/signing account, or borrowed signing
  identity.
- macOS may retain deterministic ad-hoc signing for bundle integrity, but the
  app remains not notarized and must never be represented as Developer
  ID-signed. Windows remains Authenticode-unsigned.
- Platform signing does not determine product maturity or release channel.
  Releases are normal public releases when their functional gates pass.
- Missing platform signing receives one ordinary factual sentence where users
  download/install, followed by the narrow per-application OS approval flow. It
  is not product branding, a beta label, an all-caps warning, a banner, or
  “unsigned by design” copy. Documentation never directs users to disable
  Gatekeeper, SmartScreen, Defender, or equivalent protections globally.
- Free hashes and keyless GitHub build provenance may strengthen artifact
  integrity, but must not be described as substitutes for platform publisher
  trust.
- The unsigned constraint waives no build, test, packaging, provenance,
  hardware-safety, release-identity, or public-claim gate.

## 2026-07-27 — Imported media and AI generation stay separate

Status: approved by the owner on 2026-07-27 while resolving the unified
Lighting Studio plan.

- The compositor imports GIF animations plus PNG and BMP still images. Imported
  media may be panned, zoomed, stretched, and mapped to a lighting target.
- PNG and BMP begin as one still frame. Pulse, hue cycle, sweep, pan, zoom, and
  related deterministic effects can animate imported stills entirely locally.
- AI never animates, interprets, resizes, pans, or otherwise edits imported
  media. There is no AI media-source radio and no AI motion-planning path.
- Existing AI generation remains a separate exact-target procedural-lighting
  operation inside the cohesive Lighting Studio. Its validated recipe renders
  directly to destination LED frames and does not pass through the media
  compositor.
- API recipe generation supports xAI plus Anthropic, OpenAI, Gemini,
  Kimi/Moonshot, and DeepSeek. Ollama remains the Local backend. Every provider
  produces the same strict locally validated recipe and every final animation
  is rendered locally.

This supersedes the same-day integrated-Studio decision only where that
decision described GIF import and Generated as two media-source choices. The AI
master switch, hidden-when-off UI, backend readiness gate, local banking,
document-only Apply, and hardware-write boundary remain unchanged.

## 2026-07-27 — Lighting is one integrated studio with a unified Library

Status: approved by the owner on 2026-07-27 by selecting the full image-studio
direction and specifying the unified Lighting and Library workflow.

- Lighting is one cohesive section. Manual per-key, per-frame painting, basic
  deterministic animation, media composition, optional AI generation, and
  Library review are parts of that section rather than separate products or a
  detached generation dialog.
- Manual editing remains available without AI. When the master AI switch is
  off, Lighting exposes no AI-specific source choice, prompt, status, or setup
  copy. When it is on, the source chooser presents GIF import and Generated as
  the two media-source choices; backend readiness still prevents an actual
  generation request until setup is valid.
- Every successfully imported GIF and every completed generated result is
  retained in Library. Manually authored per-key lighting can also be saved to
  Library.
- Library is a mixed local collection, not only a generation-job browser. It
  includes media sources, saved lighting compositions, and saved keyboard
  profile/mapping files, and it provides a remove action.
- Loading from Library is compatibility-gated against the open or connected
  keyboard. The application imports only server-validated compatible sections,
  explains blocked sections, never changes the destination identity, and never
  treats a partial import as permission to write hardware.

This supersedes the editor-first decision only where it prescribed a separate
generation dialog or drawer, and supersedes the video-first Library only where
it modeled the visible collection solely as generation jobs. It preserves the
manual-first default, the AI master switch, durable local banking, explicit
document-only Apply, and the separately confirmed hardware-write boundary.

## 2026-07-27 — One AI switch owns intent; readiness only gates use

Status: approved by the owner on 2026-07-27 through the explicit request to
replace the broken AI enable/setup interaction.

- Settings has one master AI on/off switch. It is the only control that changes
  whether optional AI is enabled.
- When the switch is off, Settings hides every AI backend and setup control and
  the application performs no automatic Ollama discovery. Manual lighting and
  previously generated Library content remain available.
- Turning the switch on persists that intent immediately and reveals backend
  setup even when no backend is ready. Setup failures leave the switch on and
  the repair controls visible.
- Backend selection and setup tests never turn AI on or off. A successful setup
  test records readiness for the selected backend; it does not own enablement.
- Outside Settings, generation remains hidden and unavailable until the master
  switch is on and the selected backend's current setup is valid. Changing a
  model, credential, disclosure, or backend can therefore remove readiness
  without changing the owner's on/off choice.

This supersedes the 2026-07-21 Optional AI decision only where that decision
coupled enablement to a successful setup test. Its manual-first default,
hidden-until-ready generation boundary, local/API backend constraints, privacy
requirements, and Library preservation remain authoritative.

## 2026-07-25 — The device seam sits below the protocol encoding

The device driver interface takes the logical configuration, never
protocol-encoded bytes. A driver plans and transmits its own protocol; the
routes stay ignorant of frames, reports, and packet formats.

Owner ruling on openreview finding or-1
(`.agents/review/findings/or-1.md`), which found that N2's first
implementation (commit `94a847a`) dispatched on a device handle but left
`writer.plan(config)` in the route and passed AM 64-byte frames through
`write_config(address, frames)`. A raw-HID driver cannot construct `0xF0`
lighting packets or Vial keymap writes from that representation, so the
abstraction would have had to be rebuilt at plan task N5.

The owner chose to rework N2 immediately rather than defer the cost to N5,
where more code would depend on the wrong seam. Recorded wording: option **A**,
"Rework N2 now under the corrected design".

Consequences that outlive this task:

- Protocol-specific error text (`"Device rejected JSON_END"`) belongs to the
  driver that speaks that protocol, never to transport-neutral code.
- A write result reports a protocol-native unit count plus its label, rather
  than assuming every device writes "frames".
- `server.py` does not import `writer`; frame planning is serial-driver-internal.
- The existing commit is not rewritten. The rework lands as a new commit, per
  the Git Safety rule against restructuring history without an explicit go.

## 2026-07-25 — License follows capability; Neon 80 stays MIT for now

Status: approved by the owner on 2026-07-25. This supersedes the relicensing
decision below, which was made on a premise that later proved false.

- The owner's standing instruction is that the licensing choice is an **output**
  of building the most capable application, never a constraint on it. The owner
  is indifferent between MIT, GPL, and other open-source licensing, and is
  building to fill a community gap rather than for profit.
- The premise of the superseded decision was that finished LED coordinate tables
  in the GPL-2.0 firmware would save transcription work. That premise is false:
  `real_map`, `h_map`, and `s_map` are `{chip_index, x, y}` AW20216 driver
  coordinates that the firmware applies **after** receiving a frame. The host
  transmits a linear payload, so copying those tables would map twice and
  scramble every LED. They are the wrong data, not a shortcut.
- Everything the host actually needs is available under permissive terms or is
  uncopyrightable fact: axial ordering and positions from the Apache-2.0
  `axialDefinitionsData.ts`, the side-derivation algorithm from Apache-2.0
  `device-push.ts`, and geometry constants, packet layout, channel numbering,
  and frame ceilings as interface facts.
- Therefore the application **remains MIT**. `LICENSE` and the `pyproject.toml`
  license field are unchanged, and no relicensing task exists.
- `THIRD_PARTY_NOTICES` still gains an Apache-2.0 attribution for
  `AngryMiao/neon80_driver`, which is genuinely used as a reference client.
- This is deferred, not foreclosed. If implementation later needs substantial
  expressive material from the GPL-2.0 firmware — a ported effect algorithm
  rather than an interface fact — relicensing is reconsidered **at that point**,
  under the same rule: whichever choice builds the more capable application
  wins, and the license follows.
- Reading the GPL-2.0 firmware to establish facts remains permitted and is how
  the protocol was derived; establishing a fact is not copying expression.

## 2026-07-25 — AM Neon 80 protocol sources and GPL relicensing

Status: **superseded** on 2026-07-25 by the decision above, after an
`openreview codex` pass established that the GPL firmware tables this decision
was built to permit copying are firmware-internal chip coordinates and must not
be copied at all. Retained as the record of a decision made and reversed on
evidence. Its original wording follows.

Status when approved: approved by the owner on 2026-07-25, after the owner was
shown the licensing consequence and chose it explicitly.

- Neon 80 support may derive from both published Angry Miao sources:
  `AngryMiao/neon_80_embedded` (keyboard firmware, GPL-2.0) and
  `AngryMiao/neon80_driver` (reference web configurator, Apache-2.0). This
  includes transcribing LED coordinate tables directly from the GPL firmware
  rather than re-deriving equivalent data from the permissive source.
- Because GPL-2.0 material enters the distributed application, the project
  relicenses to GPL-2.0-or-later. `LICENSE` and the `pyproject.toml` license
  field state that license.
- The pre-existing MIT notice covering the `cyberboard-cli`-derived protocol
  layer (Copyright 2026 GeneralD) is retained as a third-party notice and is
  not removed or altered; MIT material combines into the GPL work unchanged.
- `THIRD_PARTY_NOTICES` gains attributions for the GPL-2.0 firmware and the
  Apache-2.0 driver. The existing packaging guards that require license files
  in every native artifact continue to apply and are updated to match.
- GPL binary distribution carries a corresponding-source obligation; the
  public repository satisfies it and `README.md` states where source lives.
- This change is one-way in practice: returning to MIT requires removing all
  GPL-derived material from the tree.
- FFmpeg's separate LGPL bundling and its attestation system are unaffected.

## 2026-07-25 — AM Neon 80 supported at full parity or not at all

Status: approved by the owner on 2026-07-25.

- The AM Neon 80 is shipped as a supported device family only at full parity
  with the existing CyberBoard, Relic 80, and AFA families. A lighting-only or
  otherwise partial Neon 80 device family is not shipped.
- Parity means lighting animation upload, keymap read and write, macro read and
  write, layer handling, and profile store/backup participation, reached through
  the application's existing surfaces rather than a device-specific UI.
- LED frame read-back is outside parity because no supported family has it; the
  AM serial families expose no LED-frame read path either.
- The Neon 80 does not speak the Angry Miao CDC-serial protocol. It is a
  QMK/Vial device reached over raw HID (usage page `0xFF60`, usage `0x61`),
  identified by USB `0x05AC:0x024F` with a `vial:`-prefixed serial number, so it
  shares no transport with the existing serial device and protocol modules.
- Lighting uses the vendor raw-HID command `0xF0`: three zones (per-switch
  axial, head matrix, side), three user slots per zone, and a firmware ceiling
  of 256 frames per slot. Keymap and macro work use the standard Vial dynamic
  keymap and macro buffers.
- Hardware write safety is unchanged: device writes remain manual, initiated
  from the GUI, and gated on device/model matching plus typed confirmation.

## 2026-07-22 — Ollama/API-only AI backends

Supersession: the fixed-loopback and server-local-only eligibility implications
are superseded on 2026-07-29 by the configurable Ollama backend decision above.
The API-only and no-model-management portions remain current.

Status: approved by the owner on 2026-07-22. This supersedes every product,
plan, packaging, and release statement that retains direct GGUF selection or an
application-managed llama.cpp runtime, including the advanced-fallback portion
of the earlier Ollama-first decision below.

- The only shipped AI backends are the fixed-loopback Ollama integration and
  the curated API integration. Ollama remains primary and uses eligible models
  that the user has already installed through Ollama; the application never
  downloads, creates, copies, modifies, deletes, or otherwise manages models.
- The product has no GGUF picker, direct-GGUF setup or generation path,
  application-managed llama.cpp process, bundled llama runtime, local-model
  attestation store, GPU qualification gate, or llama-specific package,
  signing, licensing, build, smoke, or release path.
- Existing GGUF/runtime qualification artifacts remain historical evidence
  only. They do not describe a supported product path and must not be invoked
  by normal verification, packaging, or release workflows.
- The manual editor, hidden-until-ready AI boundary, strict recipe contract,
  local deterministic rendering, durable Library, and explicit Review/Apply
  boundary remain unchanged.

## 2026-07-22 — Ollama-first local model setup

Supersession: the fixed-loopback and cloud-exclusion requirements were
superseded on 2026-07-29 by the configurable Ollama backend decision above.
Their wording below is historical; hidden-by-default AI, no model management,
and explicit setup testing remain current.

Status: approved by the owner on 2026-07-22. This supersedes the direct-GGUF
onboarding and Ollama release-exclusion portions of the 2026-07-21 Optional AI
decision; its hidden-by-default capability boundary, strict recipe contract,
local rendering, explicit review/Apply boundary, and secondary API backend
remain authoritative.

- Local AI normally connects only to Ollama's fixed unauthenticated loopback
  service, discovers models already installed there, and lets the user select
  one by its Ollama name. The application never pulls, creates, downloads,
  copies, modifies, or deletes model weights.
- Remote and cloud-backed Ollama entries are not eligible for Local AI. The app
  does not accept a configurable Ollama endpoint, so Local setup cannot redirect
  prompts to another host.
- A selected Ollama model must pass the same production schema-valid setup test
  as every other recipe backend. Readiness is bound to the selected model name
  and digest; removal or replacement requires another explicit setup test.
- This decision originally retained direct GGUF and app-managed llama.cpp as an
  advanced fallback. The Ollama/API-only decision above supersedes and removes
  that fallback; it is historical implementation context, not current scope.

## 2026-07-21 — Optional AI capability and recipe backends

Status: approved by the owner on 2026-07-21; amended the same day to make local
inference primary with user-selected models and no application model downloads.
The 2026-07-22 Ollama-first decision supersedes this decision's direct-GGUF
onboarding and Ollama release-exclusion details.

- Manual lighting is the complete default product. Outside Settings, every AI
  control, route, setup warning, and AI-specific empty-state action is hidden
  unless the user explicitly enabled AI and the selected backend passed its
  production setup check. A later invalid setup hides those entry points again
  and exposes repair only in Settings.
- Settings presents Local model as the primary setup and API model as a
  secondary option. Local AI requires a supported GPU, sufficient usable
  memory, an app-managed runtime, and a GGUF file chosen through a native file
  picker; Ollama is not a release requirement and there is no supported CPU
  fallback. The application never downloads, copies, modifies, or deletes model
  weights. API AI requires no local GPU, but does require a curated
  provider/model, an OS-stored credential, explicit privacy/cost acknowledgment,
  and a successful structured-output test.
- A user-selected local model needs one production schema-valid setup result;
  corpus qualification remains developer evidence and never gates the local
  feature. A model-specific setup or generation failure preserves local release
  scope and lets the user select another model.
- Both backends produce the same strict procedural animation recipe. Rendering,
  exact device-frame generation, preview, mapping, banking, review, and Apply
  remain local and backend-independent. Nothing is applied automatically.
- Disabling AI never hides or deletes previously generated Library content.
  Historical still/video jobs remain browseable even though the new generation
  flow does not use image generation or image-to-video.

## 2026-07-21 — Editor-first Lighting workspace

Status: approved by the owner on 2026-07-21.

- Lighting opens directly into the manual device workspace. AI generation is
  an optional secondary action contained in a dialog or drawer; it is not the
  default route, a landing page, or the product's visual emphasis. Library is
  a secondary view alongside the workspace. The later Optional AI capability
  decision further requires that action to be absent until setup is enabled
  and valid.
- The global Open and Devices controls are the only file/device entry
  affordances. Routed empty states and document requirements explain what is
  needed without duplicating those buttons.
- The working viewport prioritizes the LED canvas, frame navigation, playback,
  and paint controls beneath compact slot/target context. At narrower widths,
  frames become a horizontal strip and controls reflow without pushing the
  canvas out of the first viewport or creating page-level horizontal scroll.
- The durable generation/library pipeline, persistent job status, pending
  review, explicit Apply boundary, manual GIF import, painting, playback, and
  device safety behavior remain intact.

## 2026-07-20 — Video-first Lighting Studio generation

Supersession: closed by deletion under the 2026-07-30 procedural-only decision
at the top of this file. Every video-generation, video-recovery, media-runtime,
and associated build instruction below is historical and must not be executed.
Only foundations independently retained by later decisions—such as the durable
Library and explicit Apply boundary—remain current.

Status: approved by the owner on 2026-07-20.

- Replace the narrow inline AI controls with a durable Concepts → Animate →
  Review & Apply workflow and a full Library. The 2026-07-21 editor-first
  decision supersedes this decision's original full-width, Create-first UI
  hierarchy; provider-call and price details still stay out of generation.
  The later 2026-07-21 Optional AI capability decision supersedes Concepts,
  image generation, and image-to-video as the path for new work; the durable
  Library, historical recovery, explicit Apply boundary, and retained assets
  remain authoritative.
- Concept generation defaults to four candidates and has a server-enforced
  maximum of eight per batch. Every completed candidate is banked immediately.
  “More like this” is a separate explicit paid batch. Selection never applies
  or animates automatically.
- Video is the primary animation path. The selected concept and a structured
  motion brief drive one one-second, 480p xAI image-to-video request. The
  default is `grok-imagine-video-1.5`; the less expensive
  `grok-imagine-video` remains selectable in Settings.
- The complete provider video is locally motion-interpolated and converted to
  the existing maximum frame count for the active device family at the fastest
  legal firmware duration. A pinned, minimal, LGPL-only FFmpeg executable is
  bundled as a subprocess dependency with corresponding license, source, and
  build provenance.
- Loop treatment is selectable per animation: Smooth is the default and uses
  one eighth of the device frame budget for an end-to-start blend; No
  transition spends the full budget on source motion; Ping-pong plays the full
  motion forward and backward. Total output frame count always remains the
  device maximum.
- All provider-created stills and MP4 files, final compact device-raster frames,
  previews, mapped results, and metadata are retained in the user-selected
  local library. Full-resolution temporary interpolation frames are not
  retained. Partial, failed, interrupted, and visibly cancelled work remains
  browsable and resumable without automatically repeating paid calls.
- Changing the library folder affects future jobs. Previously indexed roots
  remain browsable in place; moving old assets is a separate explicit action.
- Once a paid video submission is accepted, visible cancellation stops the
  foreground workflow, but background polling and download continue so the
  already-paid MP4 can be banked. It is not processed or applied automatically.
- Settings uses a curated model catalog: Grok 4.5 is the default interpreter
  with Grok 4.3 as the cheaper option; Imagine standard is the default concept
  model with Imagine Quality as the quality option. Settings shows dated price
  estimates and provider-reported actual cost; manifests store integer cost
  ticks and never secrets.
- The direct frame-by-frame GIF route is a premium advanced mode and must be
  implemented last under a separate approved plan. It does not block the
  video-first Lighting Studio.
