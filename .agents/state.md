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
- The owner approved a two-plan structure on 2026-07-29. Backend correctness is
  `docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md`; product
  experience and user documentation are
  `docs/superpowers/plans/2026-07-29-product-experience-remediation.md`.
  The plans are independently approvable, and backend implementation completes
  before product-experience implementation begins.
- Three admitted plan-review findings were fixed in commits `52261fe`,
  `e596823`, and `ffd7644`: local-animation scope, explicit supersession of old
  Ollama constraints, and a pointer to the canonical verification entry point.
- An approach-first openreview completed through Claude Code MCP with
  `claude-fable-5` at `xhigh` over
  `d77106491edc8d76118bc04ab98ad8b0d3760bb2..ffd76446c4c3e9cf689d11d5c3ac4a0b260e84d3`.
  Capability proof passed and the assessment was `acceptable_with_changes`.
  Its slice-boundary, plan-split, protocol-removal, supersession-style, and
  version-policy recommendations are incorporated in the two plans.
- AgentGovernanceBootstrap issue
  `https://github.com/roethlar/AgentGovernanceBootstrap/issues/11` tracks the
  toolkit bug that made the original openreview contract produce a
  defect-shaped audit instead of an independent approach.
- Slice P4 landed on the product branch: 13px helper-text floor (one
  documented exception: the opt-in keycap matrix overlay), WCAG-checked
  `--control-line` token on interactive borders, readable disabled states,
  top-bar actions moved to a scrollable full-width row at ≤1120px, keymap
  editor single-column at ≤1240px, and a shorter visible Merge label. Guards
  live in `tests/web/design_tokens.test.js` with computed WCAG contrast
  assertions. Two viewports were manually verified live at 1000×680 and
  1280×800 (empty state, chrome, top bar); the full per-screen manual matrix
  with an open document still rides Slice P6. A resize defect initially
  reported from screenshots was disproved: an in-page probe on the same
  pywebview 6.2.1/WebView2 stack reflows correctly on shrink, grow, and
  maximize. The screenshots were cropped by DPI-unaware capture tooling —
  window automation from a DPI-unaware shell process uses virtualized
  coordinates at 125% scale, so captures must multiply sizes by the scale
  factor or the right/bottom ~20% of the window silently disappears.
- The owner then caught a real pre-existing board overflow with an open
  document: `.keyboard-stage` combined `aspect-ratio: 2.95/1` with
  `min-height: 260px`, and CSS transfers that min-height through the ratio
  into an implicit ~767px min-width, so the keymap board spilled out of its
  card and under the inspector whenever the keymap column was narrower
  (roughly 1121-1427px viewports before the P4 breakpoints). Fixed by capping
  the stage at `max-width: 100%`, which clamps the transferred minimum;
  guarded in `tests/web/design_tokens.test.js`. Lesson recorded: per-screen
  manual checks must use an open document — the empty-state pass cannot catch
  document-dependent layout.
- The owner then asked for a holistic fix and connected three keyboards.
  `build_tools/layout_audit.py` now drives the real app read-only (it never
  references the write path), reads each connected keyboard, runs the app's
  own validation, and numerically reports every element that escapes the
  viewport, escapes a non-scrolling container, or is cut by an
  overflow-hidden ancestor, across all routes, Studio tools, lighting
  targets, and four window sizes. First run: CB04, AM21, and ALICE all read
  and validate clean (7 layers, 4 macros, 8 pages each). The audit found one
  systemic layout class — grid rows with `min-width:auto` children blowing
  out of fixed tool columns (`.button-row` 1fr/1fr, `.gif-import-row` 92px
  select track) — fixed with auto-fit wrapping rows and `min-width: 0`
  children, guarded in `tests/web/design_tokens.test.js`. Re-run is clean;
  remaining audit rows are known-benign (`.sr-only` by design; 3-9px keycap
  and Relic-stage border clipping from layout data ending at 100.6%).
- Owner testing on live hardware caught a P2 regression and two
  board-geometry defects. The staged palette Apply was reverted to immediate
  assignment: its confirmation lived in the key inspector, which
  single-column layouts place below the entire palette, so assignments could
  not be changed in practice. The plan's Keymap wording lists "Apply" among
  normal inspector contents; immediate assignment is a deliberate deviation
  after this usability failure — reconcile the plan wording at P6 or by
  owner ruling. RELIC_LAYOUT's right column ended at 100.6% of the stage, so
  the P4 stage clamp cut the PrtSc/PgUp/arrow column; the data now ends at
  exactly 100% with a computed guard. Known gap queued next: CyberBoard
  keymaps render the uniform generic matrix fallback because the app has no
  CB physical layout. Planned approach: dump CB04 matrix occupancy through
  the layout-audit bridge, author CB layout data from standard 75% row
  templates, and have the owner verify against the physical board (the
  cyberboard-cli reference checkout does not exist on this Windows host).
- CB04_LAYOUT is now authored in `am_configurator/web/app.js` from the 81
  matrix cells read off the connected CB04 (75% template, 1u = 6.1% of the
  stage, right column at 93.9%), selected by `activeLayout` for family CB and
  product CB04 only; other CyberBoard models keep the generic fallback. A
  computed guard asserts both authored layouts keep every key on the board
  with no duplicate matrix indices. The geometry awaits the owner's visual
  confirmation against the physical keyboard.
- Product-experience implementation runs in parallel on
  `claude/product-experience-remediation`, a worktree branch based at the
  shared docs tip `0271213`. Slice P2 is implemented and guard-proven:
  onboarding task cards (Connect a keyboard / Open a JSON profile), contextual
  Merge, Advanced keycode and Show technical labels disclosures with lossless
  raw round-trip, Type text / Record keys as the normal macro path with
  complete event editing under Edit individual events, labelled sidebar
  counts, and focus restoration. Guards live in
  `tests/web/app_shell.test.js` plus the updated empty-state test in
  `tests/test_app.py`.
- Backend Slice B1 is implemented on `codex/ollama-backend-correctness`: schema
  v7 migrates the fixed-loopback v6 record, Ollama accepts one normalized
  HTTP(S) origin, endpoint persistence makes no request, clients are cached by
  origin, and runtime/routes/status/frontend use the atomic `ollama` contract.
  The full automated verification entry point passed after guard proofs showed
  the origin, migration, client-cache, no-request endpoint, and no-alias tests
  fail when their production behavior is removed. No live Ollama request,
  credentialed provider request, or keyboard write was used.
- Backend Slice B2 is implemented on `codex/ollama-backend-correctness`.
  Completion-capable server and Ollama Cloud inventory is selectable with an
  explicit execution location; inventory metadata cannot redirect transport;
  model selection, status polling, and generation do not rediscover inventory;
  non-loopback and cloud data flow requires an explicit disclosure; and setup
  identity binds the normalized endpoint, model identity, execution location,
  and required disclosure. The full automated verification entry point passed.
  Guard proofs showed the cloud-classification, non-probing status/generation,
  non-network selection, location persistence, disclosure, and explicit-only
  browser Refresh tests fail when their production behavior is removed. No
  live Ollama request, credentialed provider request, or keyboard write was
  used.
- Backend Slice B3 is implemented in `a7daff3`. Ollama recipe generation,
  local-animation generation, schema failures, quality failures, and
  cancellation now make at most one model request per explicit action. Retry
  prompts, retry seeds, retry limits, and the `generate_attempt` protocol were
  removed while historical multi-attempt manifests remain supported. The
  focused B3 suite passed 58 tests and the full automated verification entry
  point passed.
- Owner UX finding for Slice P3 (2026-07-29): the lighting saving flow is
  incomprehensible — "render, apply, then save?" with no indication whether
  anything reached the keyboard. P3 must make the Preview → Apply to lighting
  slot boundary uniform, follow every Apply with explicit feedback naming the
  destination slot and document plus the next action (Write to <device> puts
  it on the keyboard), and keep Save to Library visibly distinct as optional
  archival. The hardware-write gate itself is correct and stays; the failure
  was that nothing tells the user where their work went.
- On 2026-07-29 the owner directed merging the backend branch and the product
  branch to `main`. The backend contract (B1-B3) and product Slices P2/P4 with
  their hardware-verified follow-up fixes land together; backend Slice B4's
  native build and executable smoke remain open, blocked only on the missing
  staged FFmpeg sources noted under Next.

## Next

- Close backend Slice B4 after a Windows native build and executable smoke
  test. The staged-sources cause is resolved: `ffmpeg-8.1.2.tar.xz` and its
  `.asc` are staged under `build/ffmpeg/sources`, the sha256 matches the pin,
  and the signature verifies against the pinned release fingerprint using this
  host's Git-for-Windows gpg (usable only through the `--msys2-bash` routing;
  bare invocation mishandles `GNUPGHOME` as a POSIX path). B4 is now blocked
  on two independent host gaps: no MinGW C toolchain (`cc` unavailable — the
  FFmpeg runtime must compile from source by design) and no Inno Setup 6
  (hard-required by `packaging/windows/build_installer.ps1`). The 0.1.64
  Windows candidate was never built locally: `.github/workflows/desktop.yml`
  provisions MSYS2 MINGW64 on GitHub-hosted runners and `docs/releases/
  0.1.64.md` records Windows/Linux installers as CI-smoke-tested only.
  Discovered tooling gap to fix or document: `build.py` passes no toolchain
  arguments to `prepare_ffmpeg`, so the documented local
  `python build.py --skip-sync` entry point can only succeed against a
  pre-populated attested FFmpeg cache on Windows, never from a cold start.
  Owner decision pending between: dispatching the Desktop installers workflow
  and taking its Windows smoke as B4 evidence (outward-facing; needs a go);
  provisioning this host (MSYS2 toolchain + Inno Setup, ~75 min compile); or
  recording B4 as verified-in-CI-only with an explicit local-Windows gap.
- The owner assigned the product-experience plan to Claude for parallel work.
  The backend contracts are now committed and merged into the product branch,
  so Slices P1 and P3 (AI language, Settings integration) are unblocked; P5
  screenshots and P6 versioning close out after both plans, including the
  full two-viewport per-screen manual matrix with an open document.

## Blockers

- Backend implementation has no unresolved product decision or approval
  blocker. Native smoke remains blocked only on the missing staged FFmpeg
  sources described above.
- Live Ollama Cloud prompts, keyboard writes, macOS Open Anyway, tag creation,
  release publication, and announcements remain separately gated actions.
- This Windows host cannot validate SmartScreen because SmartScreen is disabled.
  Do not ask the owner to repeat the check on another machine; the next release
  plan must record an unverified gate or use an independently available host.
