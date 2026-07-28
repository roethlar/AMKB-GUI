# Repository State

## Now

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
  active. Slices 2-7 are complete. Catalog schema 2 names the six fixed API
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
  and no-retry guards were red-proven. The full gate passes 619 Python tests, 57
  web tests, compile/syntax checks, and source/wheel builds. The heavy
  procedural recovery fixture uses the production 180-second operation
  deadline instead of a flaky 30-second test-only override. No real provider
  request, credential mutation, Keychain prompt, model mutation, or hardware
  write occurred. Next action is slice 8, provider Settings and exact-target AI
  Studio integration. Local
  `main` remains unpublished; the push policy requires a fresh explicit owner
  go.

## Blockers

- N10 has no remaining blocker. Broader device-family checks require their
  corresponding keyboards; they do not block the completed Neon scope.
- Code signing and notarization are blocked on paid developer accounts, an
  Apple Developer Program membership and an Authenticode certificate. The owner
  declined both on 2026-07-24 as not ready. `README.md` discloses the unsigned
  state; note that on macOS 15+ an ad-hoc-signed download is not merely a
  warning, the user must approve it through System Settings.
- One decision is waiting on the owner: whether to remove the Windows
  verification leftovers on `netwatch-01`, recorded in `.agents/machines.md`.
  They are harmless and useful for further Windows work.
