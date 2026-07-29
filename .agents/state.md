# Repository State

## Now

- The canonical release-version correction landed as `39b5507`. The owner
  approved `0.1.64` after identifying that `0.1.34` would regress below native
  builds that had already displayed `0.1.63`. Runtime/package metadata,
  installer names, tests, install/release copy, README, the issue form, durable
  decisions, and the release plan now agree on `0.1.64`; the `0.1.34` preflight
  is invalidated historical evidence only. Focused red/green proof, both Python
  floors, the cumulative gate, live wide/narrow browser acceptance, and a fresh
  native candidate all pass. `main` was later pushed through `97ed7a2`; no tag,
  release, hardware write, provider request, credential or Keychain access, or
  Reddit post has occurred.
- The AI master-switch and visible-version work is complete on `main`. AI
  enablement now persists as user intent before backend setup is ready; backend
  selection and setup tests cannot change that intent, while generation still
  requires both enabled and ready. Settings shows exactly one styled AI switch
  while off and performs no automatic Ollama discovery; switching on
  immediately reveals Local/API setup and switching off hides it without
  deleting configuration or Library content. The global header displays the
  server-injected runtime version as a distinct `Version <version>` badge.
  Focused persistence, route, setup-ownership, hidden-settings, discovery,
  version, and switch-style regressions were red-proven. The full repository
  gate passes 579 Python tests, 57 web tests, compile/syntax checks, and package
  builds. Native build 59 passes frozen smoke from the signed app and mounted
  DMG; its checksum-verified artifact is
  `dist/AM-Configurator-0.1.59-macOS-arm64.dmg`. An isolated native-window check
  confirms the `Version 0.1.59` badge, the styled off/on states, immediate
  persisted enablement, revealed setup while on, and hidden setup after
  restoring off. No provider request, credential access, model
  mutation/download, or hardware write was performed. The approved and
  completed plan is
  `docs/superpowers/plans/2026-07-27-ai-master-switch.md`; the governing ruling
  is the 2026-07-27 AI master-switch entry in `.agents/decisions.md`.
- AM Neon 80 support is complete on `main`. Merge commit `f3ed88c` integrates
  the former `neon-80-support` branch, which was deleted locally and from
  `origin` after a direct content comparison proved that deleting it would lose
  nothing. Plan tasks N1-N9 are implemented, and `.agents/review/index.md` owns
  the closed, red-proven review scoreboard. N10's physical identity and
  real-GUI enumeration checks pass.
  The GUI read exposed and red-proved fixes for a macOS hidapi thread-affinity
  crash, Vial's empty macro-capacity slots entering the portable document, and
  literal Vial text being misread as HID usage numbers. Commit `25f225c`
  red-proves the literal/tap decoder repair. A GET-only physical read through
  the exact UI API now returns four 90-key layers and four populated macros as
  real press/release transitions, while retaining the separately reported
  16-slot/6677-byte capacity. Native build 53's rendered UI confirms the
  corrected event counts. N10 then exposed that Vial `GET_UNLOCK_STATUS` byte 1
  had been misread as a held-key count even though it is the
  unlock-in-progress flag, and that the app never started or polled the physical
  handshake. The repair decodes the reported matrix combo `(0,0)` + `(0,2)`,
  starts and polls the standard handshake before the first configuration SET,
  names the Neon's physical Esc + F2 positions in the GUI, and prevents Esc
  from dismissing the write dialog. Its red/green repository gate passes 576
  Python tests, 54 web tests, compile/syntax checks, and package build. Native
  build 54 passes its bundled launcher smoke; the artifact is
  `dist/AM-Configurator-0.1.54-macOS-arm64.dmg`. The Neon's per-key lighting
  canvas now projects all 89 axial LEDs onto the 87-key live Vial geometry:
  real row offsets and key widths replace the 19x6 matrix cells, and LEDs
  80–82 form one 7-unit spacebar. A GET-only read through the source-served GUI
  confirmed the rendered rows `17/17/17/13/13/12`, correct modifiers and
  inverted-T arrows. The red/green repository gate passes 576 Python tests and
  55 web tests; native build 55 and its bundled smoke pass, with artifact
  `dist/AM-Configurator-0.1.55-macOS-arm64.dmg`. A build-55 full-write attempt
  passed the typed confirmation and physical Esc + F2 unlock, and the owner
  visually confirmed that it changed the axial/QWERTY lighting. The app then
  stopped during the lighting transfer, before the head/side lighting or any
  keymap or macro SET. Firmware source and hardware behavior proved that the
  Neon echoes accepted lighting packets: response byte 7 is RGB payload, not
  an ACK status, and the terminal packet echo mutates the packet index and
  checksum. Commit `7dc9399` validates that firmware-shaped echo. Its gate
  passes 577 Python tests, 55 web tests, compile/syntax checks, and package
  builds; native build 56 and its bundled smoke pass, with artifact
  `dist/AM-Configurator-0.1.56-macOS-arm64.dmg`. Build 56 accepted the complete
  full write, and the owner reports that the LEDs now match the application. A
  subsequent GET-only diagnostic proved all four keymap layers match exactly
  and isolated the first verification failure to macros: the prepared artifact
  still contained the pre-fix legacy-literal representation, so its
  `10/14/18/17` tap entries read back as `20/28/36/34` transitions instead of
  the previously verified `22/34/38/40`. The original profile's deterministic
  literal/tap distinction has been recovered into
  `/Users/michael/Downloads/AM-NEON80-N10-asymmetric-macro-recovered-2026-07-26.json`
  (SHA-256 `74a92c53c6f341f9d41942236cce76ba2ab67484afb0c0158d20e693cf4aadc5`);
  it passes complete configuration validation and an exact offline Vial macro
  encode/decode round trip at the target event counts. A second build-56 full
  write with that recovery profile completed and verified. The persisted
  `current.json` and newest history snapshot match the recovery document
  exactly: four 90-key layers, eight lighting pages, and macro event counts
  `22/34/38/40`. The deliberate GUI keymap round trip then changed only layer 4
  matrix index 89 from End (`#0007004D`) to F12 (`#00070045`), read back exactly
  that one difference, restored End, and confirmed
  `/Users/michael/Downloads/AM-NEON80-final-readback-2026-07-27.json` is
  semantically identical to the recovery profile. The N6 refusal check selected
  layer 1 matrix key 0 and applied `#000C00E9`; build 56 rejected usage page
  `0x0C` as non-QMK-representable, retained Esc (`#00070029`), and opened no
  write confirmation. The macro-capacity check built a local 17-macro profile
  and invoked the GUI full-write action; validation refused more than 16 macros
  before confirmation or any device SET. After the four-macro local state was
  restored, a fresh device read again rendered event counts `22/34/38/40`. No
  macro plaintext was exposed. The owner's 2026-07-27 photograph closes the
  remaining lighting check: the QWERTY and perforated top display both show the
  asymmetric red/blue/green/yellow corners in the expected orientation, and the
  white center appears only in the authored head matrix. The protocol's “side”
  channel is not underglow; the official driver labels it “side screen lights”
  (`side_screen_lights` / `侧屏幕灯`), and the owner confirms that the physical
  keyboard has no underglow LEDs. It contributes to the same perforated top
  display. N10 is complete. Angry Miao Master, Vial, VIA, and QMK Toolbox are
  not running; UTM offers
  **Connect…** for AM Neon 80, confirming the board is not forwarded to the VM.
  Optional xAI credential access remains deferred; no Keychain prompt occurred.
  The exported device-read JSON is **not an LED backup**: the Neon has no LED
  read-back, and its three custom LED slots in that file are synthetic black
  placeholders. On 2026-07-26 the owner found the original GIF used for the
  current lighting, accepted it as the recovery source, and explicitly
  authorized overwriting the connected Neon's LED setup for N10. A later
  build-59 write exposed a false-success path: the driver incorrectly required
  equal axial/head timeline lengths and silently omitted the populated slot. It
  sent only unchanged empty slots, then keymap/macro verification passed because
  Neon firmware cannot read LEDs back. The official
  `AngryMiao/neon80_driver` behavior confirms that the channel timelines are
  independent. Commit `8eeb684` gives axial, head, and derived side-screen
  channels their own final terminators; commit `bc659a1` makes malformed
  populated slots fail before any SET. Both regressions were red-proven, and
  the full gate passes 581 Python tests, 57 web tests, compile/syntax checks,
  and source/wheel builds. Native build 60 passes bundled and mounted-DMG
  frozen smoke tests; its checksum-verified artifact is
  `dist/AM-Configurator-0.1.60-macOS-arm64.dmg` (SHA-256
  `724e68cfcfda993b904ae393373596b4f14f370a8a4d2a61b430bd3451ebe8d9`).
  A real build-60 write of the unequal-timeline document completed through the
  normal GUI after typed confirmation and physical Esc + F2 unlock, then
  verified keymaps and macros. Persisted current state and history match the
  source byte-for-byte, and the owner visually confirmed that the keyboard
  lighting changed. The exact packet count, document hash, and snapshot are in
  `docs/neon-80-hardware-verification.md`.
  The approved plan is
  `docs/superpowers/plans/2026-07-25-am-neon-80-support.md`, its governing
  rulings are in `.agents/decisions.md` (2026-07-25), and the live hardware
  record is `docs/neon-80-hardware-verification.md`. The proposed scoped-write
  follow-up in
  `docs/superpowers/plans/2026-07-26-neon-led-preserving-writes.md` is withdrawn
  as unnecessary for N10.
- The Desktop installers workflow skips pinned FFmpeg source downloads when the
  exact current-platform runtime cache is restored; the preparation helper still
  verifies the cached runtime before the native build. This closes the Windows
  x64 failures caused by contacting `ffmpeg.org` despite a cache hit. The guard
  was red-proven, and the repository gate passes 578 Python tests, 55 web tests,
  compile/syntax checks, and package builds.
- The owner-approved unified Lighting implementation in
  `docs/superpowers/plans/2026-07-27-unified-lighting-studio-library.md` is
  complete and accepted through slice 17. Catalog schema 2 names the six fixed API
  providers; settings schema 6 preserves the complete xAI record through a
  credential-free v5 migration; provider-scoped vault operations, environment
  overrides, disclosure records, setup fingerprints, capability caches, and
  the bounded JSON transport are in place. Capability polling and setup resolve
  only the selected provider, never access the vault while AI is off or Local
  is selected, and retain the existing xAI request and durable-generation
  behavior. Unknown cost estimates are represented by `null`, while old numeric
  manifests remain valid. Anthropic now has curated Sonnet 5 and Opus 5
  choices, one pinned Messages request with documented structured output and
  fixed effort, complete local recipe validation, refusal/stop handling, dated
  usage-cost estimation, and shared setup/generation registry wiring.
  Provider-specific save/delete rollback, migrations and future-schema refusal,
  selected-provider access, error redaction, transport bounds, Anthropic
  schema/usage/output handling, cancellation, one-paid-request behavior, and
  no-retry behavior were red-proven. OpenAI now has curated GPT-5.6 Sol and
  GPT-5.6 Terra choices, one pinned Responses request with strict structured
  output, disabled storage and streaming, explicit reasoning effort, complete
  local recipe validation, refusal/completion handling, dated usage-cost
  estimation, and shared setup/generation registry wiring. Its request,
  transport, usage, output, cancellation, one-paid-request, and no-retry guards
  were red-proven. Gemini now has curated stable Gemini 3.6 Flash and 3.5
  Flash-Lite choices, one pinned Interactions request with a header-only API
  key, documented JSON Schema projection, disabled storage/streaming/background
  execution, explicit documented thinking levels, complete local recipe
  validation, terminal-status and step handling, thought-inclusive dated
  usage-cost estimation, and shared setup/generation registry wiring. Its
  schema, request, transport, usage, completion, cancellation, one-paid-request,
  and no-retry guards were red-proven. Kimi/Moonshot now has a curated Kimi K3
  choice, one pinned Chat Completions request with JSON-object mode and a compact
  schema-shaped example, the current output-token field, explicit documented
  reasoning effort, exact-one-choice and terminal-stop enforcement, complete
  local recipe validation, cache-aware dated usage-cost estimation, and shared
  setup/generation registry wiring. Its request, transport, cached usage,
  completion, ambiguity, cancellation, one-paid-request, and no-retry guards
  were red-proven. DeepSeek now has curated V4 Pro and V4 Flash choices, one
  pinned Chat Completions request with JSON-object mode and the shared compact
  schema-shaped example, explicit disabled thinking, exact-one-choice handling,
  complete local recipe validation, typed content-filter/resource/stop
  outcomes, cache-hit/miss dated usage-cost estimation, and shared
  setup/generation registry wiring. Its provider isolation, request, transport,
  cache-split usage, finish states, ambiguity, cancellation, one-paid-request,
  and no-retry guards were red-proven. Settings now derives all six providers,
  their model choices, and provider-scoped setup actions from catalog metadata,
  preserving each provider's saved model and using the catalog default on first
  selection. Lighting Studio exposes one inline Generate tool only while the
  selected provider is ready; AI-off and unready states remove that tool and
  the job strip. Procedural generation requires exactly one selected target,
  rejects media/compositor fields, and renders recipes directly at the
  destination raster and frame ceiling before mapping. The detached generation
  dialog and `lighting/create` route are gone. Exact-target, Settings, and
  hidden-tool/job-strip guards were red-proven. Saved-item schema 1 now
  discriminates media sources, lighting compositions, and keyboard profiles;
  publishes their private item directories, asset intents, hashes, and
  manifest atomically; scans current and historical roots with corruption and
  duplicate isolation; and resolves assets only through manifest ownership.
  `LibraryCatalog` projects saved items plus unchanged generation jobs through
  namespaced catalog IDs, pathless detail, pagination, status/kind/
  compatibility filters, and bounded search. Authenticated
  `/api/library/items` and `/api/library/assets/...` reads are additive; legacy
  generation and job-Library routes remain unchanged. Storage, catalog,
  pagination, root, discriminator, duplicate/corruption, asset, API, and
  regression guards were red-proven. A deterministic worker-first guard now
  forces the procedural cancellation race in which the worker persists
  `cancelled` before the cancel-request manifest update. Cancellation accepts
  that terminal state, records `cancel_requested_at`, releases admission, and
  still refuses ready or interrupted jobs; the old behavior was red-proven.
  Library removal now moves exactly one owned job/item UUID directory into the
  same root's private `.trash`, keeps removed detail/assets browseable, restores
  by the inverse rename, and deletes forever only an exact link-free trashed
  directory. Normal and Removed catalog pages are disjoint; live/trash
  collisions, cross-root ambiguity, active operations, nonterminal jobs,
  unsafe ownership directories, links/path escapes, mutation query/body
  fields, and deletion of live content all fail closed. Historical jobs remain
  in their original root, manifest bytes survive remove/restore unchanged, and
  device-history/sibling sentinels are untouched. All removal, restore,
  permanent-delete, active-state, cross-root, link, pathless API, and exact
  deletion guards were red-proven. Canonical device descriptors now expose
  fixed and dynamic keymap signatures, per-target lighting signatures and
  routing roles, and destination limits. Section compatibility independently
  classifies keymaps, macros, and lighting with stable reasons; selected
  exact/portable sections project into one fully revalidated candidate while
  preserving destination identity and unselected content. Unknown Neon layout
  evidence, layer/macro capacity overflow, unsupported Vial assignments,
  lighting mismatches, and invalid candidate documents fail closed. The six
  focused signature/compatibility/projection guards fail against pre-slice
  production code and pass with the implementation restored. Keymap now offers
  explicit profile banking, while Library accepts one or more configuration
  JSON files without changing the open document, device store, or hardware.
  Imported profiles retain the exact source bytes; current mappings retain a
  complete normalized snapshot. Both carry section presence plus device/layout
  signatures, render as mixed-catalog cards/details, and obtain a read-only
  server compatibility preview for the open document. The profile helper,
  import/save endpoints, exact-byte retention, side-effect isolation, and web
  shell guards fail against pre-slice production code and pass with the
  implementation restored. Imported GIF, PNG, and BMP sources now cross one
  authenticated bounded raw-binary route, are signature-sniffed and fully
  decoded before publication, reject APNG, truncation, trailing data, decoder
  warnings, and resource-bound violations, retain their exact original bytes,
  and deduplicate only against a live hash- and byte-verified source. Exact
  version-1 transforms support normalized pan, locked or independent scale,
  black alpha composition, and three sampling modes while preserving the old
  default center-crop result. Pathless transient renders use monotonic editor
  epochs, reverify the owned source and metadata, publish only the existing
  mapped-result shape, leave `.work` empty after completion or supersession,
  and block Library removal/root switching while active. Mapping now transforms
  every validated source frame before resampling the complete timeline under
  the destination family's frame ceiling, so a long GIF cannot silently lose
  its tail. The media validation, transform, asymmetric orientation, complete
  timeline, deduplication, concurrency, source-preservation, epoch, binary
  envelope, route, and no-publication guards were red-proven. The Studio keeps
  its timeline, exact LED canvas, and one right-hand
  Paint/Source/Animate inspector stable while tools change; ready-only
  procedural generation is a fourth inspector tool and remains absent when AI
  is unavailable. The canvas exposes the destination overlay and normalized
  pan/zoom/stretch controls. Pulse, Hue cycle, Sweep, and seeded Shimmer produce
  bounded deterministic local drafts; still-only Move & zoom produces
  normalized transform keyframes. Preview is document-neutral, stale drafts
  fail closed, and Accept replaces the selected track through exactly one undo
  checkpoint while preserving the existing Relic dependent-track retiming
  rule. Manual paint, keyboard frame/pixel navigation, playback, target
  geometry, and responsive layout remain available. The focused compositor and
  Studio-shell guards were red-proven before implementation and pass restored.
  The direct GIF replacement path is now gone: GIF, PNG, and BMP imports bank
  the immutable source first, open one transform draft, render a
  server-authoritative preview, expose the complete mapped timeline for
  selection/playback, and mutate the open slot only through explicit Apply.
  Cancelling retains the source and changes no document data. Render epochs are
  strictly increasing across reopened drafts and equal/stale server epochs fail
  closed. Manual, locally animated, and imported lighting can be saved as exact
  composition assets with preview, timing, brightness, target relationships,
  and source/effect provenance; provenance is retained only while the exact
  applied page is unchanged. Saved lighting reapplication verifies family and
  target signatures, restores brightness, and creates one undo checkpoint.
  Media sources reopen in Studio from the mixed Library. The new browser state
  module is syntax-gated in both CI and the canonical repository gate. All
  slice-15 behavioral guards were red-proven. The heavy procedural recovery
  fixture uses the production 180-second operation deadline instead of a flaky
  test-only override. The mixed Library now exposes All, Sources, Lighting,
  Keymaps, and Removed; generated results and historical jobs share Lighting,
  compatible profile sections apply through one revalidated candidate and one
  undo checkpoint, removal is reversible, pagination and stale-request
  ownership are explicit, and keyboard navigation is retained.
  Frozen smoke now fetches the mixed-Library shell plus its composer, state,
  application, and stylesheet assets. Native policy verifies Local/API, all six
  provider IDs, and hidden AI details while AI is off. The policy server injects
  empty device discovery so browser startup never reaches attached keyboards or
  initializes macOS hidapi; this closes the prior post-success `hid_exit`
  SIGTRAP without bypassing WKWebView. The focused guards were red-proven.
  Browser inspection found and red-proved a 760px header overflow; the header
  now enters its internally scrollable two-row layout at 820px. Follow-up
  browser acceptance also red-proved and fixed independent media-height
  controls, stale async Library-confirmation targets, and the Relic per-key
  canvas. Relic Lighting now uses the exact normalized Keymap geometry: all 87
  physical keys align, and the spacebar is one correctly sized key with three
  independently editable, persistently labelled LED segments (78, 79, and
  80). The interactive pass covered manual paint and keyboard navigation; all
  five local effects; media reopen, pan, locked zoom, stretch, preview, Apply,
  and undo; deterministic fake-provider generation through saved review,
  Apply, undo, and Library banking; partial and fully blocked profile sheets;
  remove, Undo, restore, and delete forever; wide, narrow, 150%-equivalent, and
  reduced-motion layouts. No browser console error or page-level horizontal
  overflow remained.
  The clean full gate passes 666 Python tests, 78 web tests, compile/syntax
  checks, and source/wheel builds. Native build 63 passes bundled and mounted
  DMG frozen smoke, the real WKWebView policy smoke, deep code-signature
  verification, and DMG verification. The artifact is
  `dist/AM-Configurator-0.1.63-macOS-arm64.dmg` (SHA-256
  `f240d3c511e91e51080965a64293b5cd5173d635ffbcf88662da97622384fd8b`).
  No real provider request, credential access or mutation, Keychain prompt,
  model mutation/download, real Library mutation/deletion, hardware write, or
  release occurred during the final acceptance. `main` and tag `v0.1.11` were
  subsequently pushed to `origin`; GitHub CI and all three Desktop installer
  jobs passed at `8b50fb9`.

- The approved 2026-07-28 public-release plan is at
  `docs/superpowers/plans/2026-07-28-public-release.md`. The owner settled that
  installers remain permanently platform-unsigned, the release is normal
  rather than beta/prerelease, and `0.1.64` is the one canonical version.
  Build counters and workflow runs remain provenance only. The plan also
  removes duplicate in-app branding, moves version into an unobtrusive About
  dialog, opens Keymap unconditionally on every launch, adds free hashes/keyless
  provenance, exact-artifact platform and Neon acceptance, corrected public
  documentation, release notes, and a Reddit-safe claim boundary. Release
  identity and the plan landed in `0f18963`; canonical source/package/local/CI
  versioning landed in `4ce7003` with its metadata-test repair in `6a9e1f1`.
  Native-build guidance now agrees that counters are provenance only. The
  duplicate in-content brand/version block is removed, a quiet About dialog is
  the sole normal UI version surface, and launch state now forces Keymap despite
  saved routes or startup hashes while preserving active lighting-job identity.
  The focused server, state, and syntax checks pass. The strict release-metadata helper
  now accepts only the exact three canonical installers, streams deterministic
  SHA-256 metadata, rejects unsafe/ambiguous candidates and conflicting output,
  and keeps workflow run identity as provenance only. The Desktop workflow
  collects metadata only after all installers succeed on `main` push or manual
  dispatch, using immutable `actions/download-artifact` source. Its ten focused
  guards were red-proven and the complete packaging module passes. A separate
  downstream provenance job now owns the only OIDC/attestation write
  permissions, runs solely for `main` pushes, and creates four records for the
  three exact installers plus the manifest/checksum pair with the official
  action pinned to commit `e8998f9`. Pull requests and manual candidates remain
  unable to request an OIDC token. The focused provenance guard was red-proven,
  and public install guidance now includes the `gh attestation verify` command
  without presenting provenance as platform signing. Public documentation now
  sends users only to GitHub Releases, names Neon 80's actual layout, lighting,
  layer, and macro limits, describes the unified Studio/Library and off-by-
  default AI behavior, explains complete writes and absent Neon LED read-back,
  and gives hash/attestation plus narrow macOS, Windows, and Linux launch
  instructions without security-bypass commands. The public-doc guard was
  red-proven and the complete packaging module passes. Screenshot acceptance
  found that the desktop Keymap canvas retained a `260px` minimum height after
  its inspector stacked, forcing an internal page-width clip in narrow windows.
  The responsive grid and keyboard canvas now release that desktop minimum; its
  focused guard was red-proven, and live 720px inspection shows zero document or
  main-workspace horizontal overflow. The README's Keymap, macro, and Lighting
  images are now fresh 1600×1000 captures from isolated public fixtures; the
  macro image uses a generated `Hello, world!` example and the Lighting image
  visibly labels all three Relic spacebar LEDs. Metadata was stripped, its guard
  was red-proven, and full-resolution inspection found no private state. Live
  wide/narrow acceptance also confirmed unconditional Keymap reload, the quiet
  About dialog with `0.1.64`, zero document/main overflow, and no console
  warnings or exceptions. The `0.1.64` release notes and Reddit draft now state
  the exact hardware/OS/provider qualification boundary, installer integrity
  workflow, full-write/LED-readback limitations, and non-affiliation without
  promotional overclaiming. A structured GitHub bug form collects keyboard,
  firmware, OS, version, operation, write, installer, reproduction, and
  sanitized-log context. Both release-packet guards were red-proven and the
  issue-form YAML parses successfully. The cumulative local pre-publication
  gate now passes 685 Python tests on Python 3.13, 81 web tests,
  compile/syntax checks, and source/wheel builds. The Python 3.11 floor
  separately passes all 685 Python tests, compilation, and package builds.
  The first post-push GitHub candidate from Desktop run `30388161235` at
  `97ed7a2` reproduced its manifest/checksums exactly, verified all
  attestations, and passed macOS native checks, but it is rejected: live
  inspection exposed macOS's automatic one-tab strip beneath the normal
  native title bar. No tag or Release was created. Commit `3496bbe` disables
  automatic macOS window tabbing before pywebview creates a window. Its
  regression was red-proven, and exact-path inspection of the rebuilt bundle
  confirms one native window, no accessibility tab-bar role, unconditional
  `#/keymap` startup, and About-only version `0.1.64`. Owner review then exposed
  that globally selectable page text could trap subsequent clicks. Commit
  `621adef` disables native page-text selection and limits CSS selection to
  text inputs, textareas, and editable content. Both native and stylesheet
  regressions were red-proven. Exact-bundle inspection confirms that dragging
  across the Keymap heading creates no highlight and the next Settings click
  works, while text inside the Library path field remains selectable. The
  fresh local artifact is
  `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (25,507,199 bytes,
  SHA-256
  `0aa59150b2821ef48292ae1fc094ee8d3a1e54c997691eb0cd17587304dea557`);
  bundle and mounted-DMG smoke, the real WKWebView policy smoke,
  `hdiutil verify`, and deep strict ad-hoc signature verification pass with
  `Signature=adhoc`, no team identity, and bundle version `0.1.64`. No keyboard
  SET occurred during the rejected candidate's hardware preflight. Its
  GET-only snapshot is
  `~/Downloads/AM-NEON80-release-0.1.64-prewrite-2026-07-28.json` (SHA-256
  `fc1d7a76d8d4dda84077dcc30c4811a22eb4e84f640e7bd7b50f45e7e1d11076`);
  the known LED-bearing restore document remains
  `~/Downloads/AM-NEON80-config.json` (SHA-256
  `745b107a4ae0a6cfd239ff95a9162382cab89cfde426f815b137dc70f55ebb90`).
  The tracked/untracked privacy audit previously redacted one historical
  device serial in `c774cac`; `95f222c` additionally removes the physical
  firmware UID from historical docs and replaces its test fixture with a
  synthetic value. The current tree has no untracked files, `.env` files,
  non-test credential signatures, physical firmware UID values, public
  machine-local paths, or oversized tracked files.
  `actionlint` is not installed, so that optional local check remains for
  GitHub workflow validation. No provider request, credential or Keychain
  access, model mutation/download, hardware write, release publication, or
  Reddit post occurred during the correction preflight. Replacement push,
  final GitHub candidate qualification, exact-artifact hardware acceptance,
  release publication, and Reddit posting retain their explicit gates.
- Three owner-reported Neon regressions are fixed on local `main`. Commit
  `537e570` makes keymap macro triggers protocol-aware: the Neon reports Vial
  protocol 5 and therefore needs the legacy `0x5F12` macro range rather than
  protocol 6's inert-on-Neon `0x7700` range. Commit `7305e0a` adds the Neon's
  separate under-key and top-display lighting controls to the assignment
  palette. Commit `1bd850c` preserves the canonical Neon geometry selected
  during startup so Lighting cannot fall back to a matrix of square cells.
  Focused regressions were added for all three fixes. A GET-only read through
  the exact rebuilt bundle shows the old `0x7700` trigger values as raw
  keycodes on layer 2, while the known LED-bearing restore JSON renders the
  same four positions as semantic Macro 1–4 assignments. The native UI opens
  unconditionally on Keymap, renders the 87-key Neon layout, exposes both
  lighting-control groups, and renders Lighting as the same keyboard-shaped
  geometry with individually labelled LEDs. No write dialog or keyboard SET
  was opened, so corrected macro execution on physical hardware remains an
  exact-candidate acceptance item rather than a completed claim. The clean
  gate passes 687 Python tests (one skipped), 83 web tests, compile/syntax
  checks, and source/wheel builds. Frozen bundle and mounted-DMG smoke, the
  real WKWebView policy smoke, `hdiutil verify`, and deep strict ad-hoc
  signature verification pass. The current local artifact is
  `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (25,629,920 bytes, SHA-256
  `364df91494702bd3945da09a83bbe8a98936112cc250564b6ae207e1700dee89`).
- Desktop run `30414278566` (run 36) and CI run `30414278607` both passed at
  exact commit `6cffe0196e3a778ecb2ac41025cccab6d8d7b948`. Candidate metadata reproduced
  byte-for-byte, all four attestations verified, and the exact macOS and Linux
  packages passed their available native and content checks. The Windows
  install/smoke/uninstall workflow passed and its exact installer has no
  Authenticode Security Directory, but `netwatch-01` remains unreachable for
  the real-host hash, SmartScreen, and About inspection. Exact macOS UI
  acceptance confirmed the corrected window/version/startup/privacy/Neon
  geometry and GET-only read paths. Its temporary Library banked GIF, PNG, BMP,
  manual lighting, and a Neon mapping; exercised transforms, all local effects,
  Apply/undo, source reopen, and exact-compatible lighting apply. Importing a
  valid cross-keyboard profile then exposed that the client still selected the
  removed `profiles` filter rather than the canonical `keymaps` filter. The
  item banked safely, but the Library refresh failed, so run 36 is rejected and
  no keyboard SET, tag, Release, or announcement occurred. A focused guard was
  red-proven against that failure; the local repair now passes 687 Python tests
  (one skipped), 83 web tests, compilation/syntax checks, and source/wheel
  builds.
- Desktop run `30416604544` (run 37) and CI run `30416604729` both passed at
  exact commit `dd891e3ab69101e368a2cb2a57295f9b29765d16`, but exact packaged
  macOS inspection exposed that the media picker's concrete GIF/PNG/BMP MIME
  and extension list disabled valid source images. Run 37 is rejected. The
  repair uses pywebview's Cocoa-compatible `image/*` supertype; its focused
  regression was red-proven against the concrete list. The clean repository
  gate passes 687 Python tests (one skipped), 83 web tests, compilation/syntax
  checks, and source/wheel builds. A clean native build passes frozen smoke and
  DMG verification. Its exact-byte `/Applications` qualification matched the
  build by `rsync -acn`, matched ad-hoc CDHash
  `bbdb6617f28511c047ee69f4ad8329250564394b`, passed deep strict signature
  verification, launched on Keymap, reported `0.1.64` only in About, and banked
  fresh GIF, PNG, and BMP sources with hashes identical to the selected files.
  The owner's installed app was restored after qualification. The current
  local artifact is `dist/AM-Configurator-0.1.64-macOS-arm64.dmg` (24,505,055
  bytes, SHA-256
  `d7cfb5e0ae7233396ed990dff4ebd7c5a9667a9dd27920df5b438b76b24bea07`).
  No provider request, credential or Keychain access, model mutation/download,
  keyboard SET, tag, Release, or announcement occurred.

## Next

- Commit and push the red-proven native media-picker repair under the
  repository-local push policy, wait for CI and all desktop workflows,
  download the exact replacement artifacts, and restart gates C through F. The
  exact macOS
  candidate's Neon acceptance must load the LED-bearing restore JSON, receive a
  fresh hardware-write authorization immediately before the write, complete
  the physical Esc + F2 unlock, and exercise all four macro trigger keys before
  release publication.

## Blockers

- N10 has no remaining blocker. Broader device-family checks require their
  corresponding keyboards; they do not block the completed Neon scope.
- Platform signing and notarization are permanently excluded by settled owner
  constraint. Releases remain normal public releases: deterministic macOS
  ad-hoc signing only, no notarization, and no Windows Authenticode certificate.
  `README.md` discloses the current unsigned state in ordinary language; on
  macOS 15+ an ad-hoc-signed download requires approval through System
  Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
- `netwatch-01` currently times out over SSH, so the required exact Windows
  host inspection waits for the owner to wake it. The macOS Open Anyway test
  and Neon full write each require action-time authorization; neither blocks
  building and qualifying the next candidate up to those exact gates.
