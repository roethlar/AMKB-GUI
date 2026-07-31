# Product Experience and User Documentation Remediation

**Status:** Complete. Slices P1-P6 and their follow-up fixes landed on `main`
by 2026-07-31. Slice P6 established and locally qualified the distinct
`0.1.65` candidate without the retired AI-video/FFmpeg path. Push-time CI,
cross-platform exact-artifact qualification, hardware checks, and publication
remain separate gates; the historical `0.1.64` release plan is not executable.

## Objective

Replace the current implementation-led interface and README with a
gamer-facing keyboard application whose normal path explains user tasks rather
than storage, rendering, firmware, or provider internals.

The completed product must:

- give a new user two obvious starting actions: connect a keyboard or open a
  profile;
- keep Keymap, Macros, Lighting, Library, Settings, and AI workflows task-led;
- use Ollama and Direct API names consistently;
- explain failures in plain language and offer one clear next action;
- hide low-level controls behind explicit Advanced disclosures without losing
  capability or round-trip fidelity;
- preserve device-write safety, lossless raw keycodes, macro event editing,
  complete lighting controls, Library durability, and preview/apply boundaries;
- present a readable, accessible hierarchy at the native minimum window and
  common desktop viewports; and
- give a new user a direct download and five-minute README path.

The rejected unpublished `0.1.64` candidate remains unpublishable. This plan
does not authorize release, a live cloud prompt, provider credential use,
keyboard writes during implementation, tag creation, publication, or
announcement.

## Dependency on Backend Correctness

`docs/superpowers/plans/2026-07-29-ollama-backend-correctness.md` owns:

- settings schema and migration;
- Ollama origin validation and transport;
- inventory eligibility and location;
- setup identity and disclosure triggers;
- status payload names and loopback API routes;
- exactly-one-request generation behavior.

This plan consumes those contracts and does not redefine them. Backend Slices
B1-B3 landed before the product work consumed them. Backend Slice B4 was
superseded by the 2026-07-30 procedural-only/FFmpeg-prohibited decision and
must not be executed.

## Current Baseline

The implementation at the plan base has these user-facing problems:

- `am_configurator/web/index.html`, `app.js`, `lighting_state.js`, and
  `lighting_review.js` expose terms including Local, API backend, durable job,
  banked/banking, procedural recipe, exact LED frames, raster dimensions,
  deterministic seed, model identity, and mapped/stored counts.
- The empty state is paragraph-led and makes merge behavior visible before a
  user has opened a document.
- The normal Keymap inspector exposes matrix positions and raw eight-digit
  keycodes.
- The normal Macro view exposes key-down/key-up events and per-event timing.
- The normal Lighting view exposes sampling, stretch algorithms, deterministic
  seeds, raw frame counts, and draft/render terminology.
- Settings describes provider implementation instead of the chosen service,
  endpoint, model destination, and explicit actions.
- Sidebar counts and dense helper text lack a clear hierarchy at ordinary
  window sizes.
- `README.md` places provenance and implementation detail before a direct
  supported-device, download, and first-use path.

## Non-Goals

- Do not redesign device protocols, profile schemas, rendering algorithms,
  Library storage, or the hardware-write confirmation boundary.
- Do not remove raw keycode editing, matrix labels, macro event editing,
  firmware timing, sampling, stretch, seed, diagnostic counts, or other expert
  capability; move it behind Advanced disclosure.
- Do not make Lighting/profile Apply and Save to Library the same action.
- Do not expose credentials, serials, filesystem paths, raw exceptions, or
  diagnostic payloads in normal UI or screenshots.
- Do not add a live cloud prompt, provider qualification, or keyboard write to
  automated or manual implementation verification.
- Do not duplicate backend correctness rules from the backend plan.

## Product Language Contract

Normal UI, surfaced API errors, README instructions, installation guidance, and
screenshots use these replacements:

| Internal term | User-facing replacement |
|---|---|
| local backend | Ollama |
| API backend | Direct API |
| local model | model on this Ollama server |
| bank / banked / banking | save / saved / saving to Library |
| durable job | generation continues in the background |
| procedural recipe | lighting effect or lighting pattern |
| exact LED frames | lighting frames |
| raster dimensions | keyboard or display size |
| model identity changed | the model was updated; test it again |
| source | imported media |
| deterministic draft | preview |
| accept draft | apply preview |
| catalog identity / asset identity | saved Library item |
| mapped / stored counts | hidden normally; shown under Technical details |

Internal names, manifest fields, developer tests, and diagnostic logs may keep
precise engineering terms when they are not user-visible.

Every surfaced failure answers:

1. what failed in user terms;
2. whether anything was saved or changed;
3. the next available action.

Typed errors are mapped at the API/UI boundary. Raw exception text stays in
local diagnostics and test assertions.

## Interaction Design

### First Run and Empty State

Show two primary task cards:

- **Connect a keyboard** — opens Devices and states that reading never writes;
- **Open a JSON profile** — opens a complete portable profile.

Keep one concise lighting safety note: keyboards whose firmware cannot read
lighting require a complete JSON profile or the application's last verified
local snapshot to preserve existing lighting.

Do not introduce merge concepts before a document is open. Show **Merge another
JSON** only for an open document or when a key-only export needs its matching
lighting file.

### Application Chrome

Group actions by task:

- file: Open, Save JSON, contextual Merge;
- application: Settings;
- device: Devices, Write to keyboard.

Keep quiet chrome and Keymap-first launch. Do not add a nested product title or
version to ordinary chrome.

Give sidebar counts visible or accessible labels such as `7 layers`, `4
macros`, and `3 lighting slots`; unexplained numbers are not acceptable.

### Keymap

The normal inspector contains:

- selected physical key;
- current assignment in plain language;
- searchable assignment groups; and
- a clear explanation that choosing from the palette changes the selected key
  immediately.

Move raw keycode editing and firmware passthrough explanation into collapsed
**Advanced keycode**. Hide matrix/LED numbers by default and expose them through
**Show technical labels**. Preserve lossless raw-code round trips. The Advanced
raw-code field keeps its explicit **Apply** action; do not reintroduce a staged
palette Apply action, which owner testing found unreachable in single-column
layouts.

### Macros

The default workflow contains:

- **Type text** to convert text to keystrokes;
- **Record keys** to capture a sequence;
- one simple delay control with a timing explanation.

Move the key-down/key-up table, per-event delay editing, track counts, and
capacity diagnostics into **Edit individual events**. Capacity errors remain
pre-mutation and use task language.

### Lighting Studio and Library

Normal tools are:

- Paint;
- Import media;
- Effects;
- AI.

Use a consistent two-step boundary: **Preview**, then **Apply to lighting
slot**.

Move sampling method, independent-axis stretch, pattern seed, raw frame counts,
mapped/stored counts, and firmware timing into contextual **Advanced** or
**Technical details** sections. Normal controls use friendly presets constrained
to firmware-safe values.

Use **Save to Library** consistently for manual lighting, imported media,
keymaps, macros, and generated effects. Apply changes only the open document;
Library persistence is always a separate labelled action.

AI progress uses:

- Creating lighting;
- Checking the result;
- Saving to Library.

The progress explanation is:

> You can open Library while this finishes. Closing the progress view does not
> cancel generation.

The panel shows destination, selected Ollama or Direct API model, one prompt,
one Generate/Try again action, and Cancel. It never claims a job/result is
durable, banked, exact, or procedural.

### Settings

Backend choices are **Ollama** and **Direct API**. Remove Primary computer,
Secondary provider, Installed model, and eligible local model wording.

The Ollama panel contains:

- Server URL with loopback default and a LAN example;
- configured-host connection status without credentials;
- Refresh models;
- a picker labelled On this Ollama server or Ollama Cloud;
- the disclosure supplied by the backend contract;
- Use model;
- Test setup;
- Clear selection.

Saving a changed URL performs no request. Refresh and Test setup are the only
actions that initiate inventory and setup generation.

### Visual Hierarchy and Accessibility

Retain the dark visual identity while enforcing:

- body text at least 14 px at 100% scale;
- helper text at least 13 px;
- WCAG AA 4.5:1 contrast for normal text;
- 3:1 contrast for large text and control boundaries;
- visible focus on every interactive element;
- readable, distinguishable disabled controls;
- consistent primary, secondary, destructive, and Advanced hierarchy;
- no clipped primary action, horizontal clipping, or overlapping panel at the
  native minimum window or 1280×800;
- no regression at 1600×1000.

Automated DOM tests own structural, vocabulary, keyboard-navigation, and stable
token assertions. Manual visual verification owns perceptual hierarchy.

## README and Screenshots

Restructure `README.md`:

1. one-sentence product purpose;
2. **Download the latest release**;
3. supported keyboards and operating systems;
4. five-minute quick start;
5. three current screenshots;
6. Keymap, Macros, Lighting, Library, and optional AI capabilities;
7. concise device-write and lighting-backup safety;
8. installation-verification link;
9. collapsed developer/build instructions.

README labels and actions must match the application. Move maintainer-only
reproducibility and provenance detail out of the normal download path while
retaining it in installation/release documentation.

Capture screenshots only after final UI verification. They contain no
credential, device serial, personal path, live cloud prompt, or result.

## Implementation Slices

Every slice is guard-proven, fully verified, and committed before the next.
Normal and Advanced paths must both remain functional at every boundary.

### Slice P1 — Replace implementation vocabulary and error presentation

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/lighting_review.js`
- surfaced Python error mappings
- affected Python and web tests

Required guards:

- normal UI contains none of the banned language in the contract;
- phases and failures state the task, saved/changed state, and next action;
- Ollama and Direct API labels match backend status;
- generated-result review uses lighting-effect language;
- raw exception text is not surfaced;
- internal manifest compatibility is unchanged.

Commit:

```text
fix: use plain language throughout the app
```

### Slice P2 — Simplify onboarding, Keymap, and Macros

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/style.css`
- relevant web tests

Required guards:

- empty state exposes Connect a keyboard and Open a JSON profile;
- Merge is contextual;
- raw keycodes and technical labels are hidden until requested;
- palette choices apply to the selected key immediately;
- lossless raw assignment still round-trips;
- Type text and Record keys remain normal Macro actions;
- event-level editing remains complete under Advanced;
- keyboard navigation and focus restoration pass.

Commit:

```text
feat: simplify keymap and macro workflows
```

### Slice P3 — Simplify Lighting, Library, and Settings

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/lighting_review.js`
- `am_configurator/web/style.css`
- relevant web and route tests

Required guards:

- tool names and Preview/Apply actions match this plan;
- technical controls retain values and behavior under Advanced;
- every Library save is explicit and separate from Apply;
- Settings URL save makes no request;
- Refresh and Test setup remain distinct explicit actions;
- non-loopback HTTP and Ollama Cloud disclosures are correct;
- generation failure exposes one Try again action and makes no automatic call;
- AI-off mode hides AI-only controls while all manual tools remain available.

Commit:

```text
feat: simplify lighting and AI setup
```

### Slice P4 — Correct hierarchy, accessibility, and responsive behavior

Files:

- `am_configurator/web/style.css`
- minimal semantic markup required for accessibility
- web structure/navigation tests

Required checks:

- stable token/contrast assertions;
- keyboard-only traversal of every primary task;
- visible focus and readable disabled controls;
- no clipped primary action at 1280×800 or native minimum;
- no regression at 1600×1000;
- no hidden modal action at minimum size;
- manual inspection of Keymap, Macros, Lighting, Library, Settings, empty
  state, errors, and dialogs at both target viewports.

Commit:

```text
fix: improve application legibility and hierarchy
```

### Slice P5 — Rewrite user entry documentation

Files:

- `README.md`
- user installation documentation whose labels changed
- `docs/images/*.png`
- link and copy tests

Required checks:

- README order matches this plan;
- latest-release installation links resolve;
- README and application action labels agree;
- three screenshots match the verified UI and contain no sensitive data;
- developer/build instructions remain accurate.

Commit:

```text
docs: add a clear user quick start
```

### Slice P6 — Close remediation and prepare a distinct candidate

The rejected unpublished `0.1.64` identifier is not reused. After the
FFmpeg-removal plan is complete, set the canonical version in
`am_configurator/_version.py` to `0.1.65`. This version change and its
propagation are part of the new candidate, not a revision of the rejected
candidate.

Files:

- `am_configurator/_version.py`
- generated/version consumers updated by the repository's normal build flow
- `.agents/state.md`
- this plan
- the backend plan status/pointer
- the release plan status/pointers

Required checks:

- full automated verification entry point passes;
- `python build.py --skip-sync` and executable `--smoke-test` pass;
- every screen/error state passes the two-viewport manual matrix;
- version assertions and artifact names resolve to `0.1.65`;
- no live cloud prompt, provider credential, or keyboard write was used;
- exact implementation commits and remaining platform gates are recorded.

Commit:

```text
docs: close product experience remediation
```

The local candidate build and qualification close this slice. Tagging,
publication, announcements, live cloud qualification, macOS Open Anyway, and
hardware writes retain separate action-time gates.

Completion record (2026-07-31):

- The canonical version and active packaging, installation, issue-template,
  and product-identity pointers resolve to `0.1.65`. The rejected unpublished
  `0.1.64` release and announcement drafts are explicitly historical and are
  no longer linked as current release notes.
- The new active-pointer, historical-packet, and compact-key-label guards each
  passed, failed for the predicted reason with its behavior temporarily
  reverted, and passed again after restoration.
- The full repository gate passed: 646 Python tests with 5 expected skips,
  127 web tests, Python compilation, JavaScript syntax checks, and the
  `0.1.65` source distribution and wheel build.
- From a Visual Studio Build Tools 2026 Developer PowerShell,
  `python build.py --skip-sync` completed in about 14 seconds. PyInstaller,
  Inno Setup, silent install, installed smoke, and uninstall all passed. The
  direct frozen bundle also passed `--smoke-test`.
- The local Windows installer is
  `AM-Configurator-0.1.65-Windows-x64-Setup.exe`, 17,442,806 bytes, SHA-256
  `02B88C45D9CD52A5D080F29EC9275BBE6D1DFE40BA2CDFAF740BC67F3C334FC9`.
- The native WebView2 matrix covered 18 states at both 1000×680 and 1280×800
  with device scale factor 1: Keymap normal/technical, Macros
  normal/Advanced, all Switch LED and top-display editor modes, Library
  empty/error, Settings model-missing, About, device-empty,
  incompatible-profile, write-confirmation, and empty-document states. All
  36 captures were inspected; automated DOM layout audits reported zero
  failures, no horizontal overflow, and no clipped toolbar controls. The
  CyberBoard switch LEDs match the canonical physical key geometry while its
  40×5 top display remains rectangular.
- Supporting CyberBoard geometry landed at `c01357e`, its target-split guard
  at `0b6778f`, and the owner-waiver review closure at `86e378d`. The P6
  version, pointer, compact-key-label, guard, and completion changes landed at
  exact commit `4a3c6ebadcc5d0fc1730c06b853af8e28c686ca5`.
- That commit was pushed to canonical `origin/main`. Exact-head
  [CI run 30666353202](https://github.com/roethlar/AMKB-GUI/actions/runs/30666353202)
  (run 57, attempt 1) passed Windows, Linux, the Python 3.11 floor, and macOS.
  Exact-head
  [Desktop run 30666353162](https://github.com/roethlar/AMKB-GUI/actions/runs/30666353162)
  (run 68, attempt 1) passed native installer smoke on all three platforms,
  candidate metadata, and release provenance.
- The downloaded manifest names source commit `4a3c6eb`, repository
  `roethlar/AMKB-GUI`, and exactly these three `0.1.65` artifacts:
  - Linux AppImage: 211,671,544 bytes, SHA-256
    `f5b8d028e45c5f04a5d1f7e82ed174846cdbc4eed7c56dd6ca106d7a6a698398`;
  - Windows installer: 17,890,591 bytes, SHA-256
    `5a0e09f992505a0ea83adb03b21f76edc7a1492382b90f94fcbeb160beb6670a`;
  - macOS DMG: 22,484,503 bytes, SHA-256
    `5d32825bf205de1e208259a35e3be796c0e1596ef4246064bc3a2e824d60790c`.
- Regenerating `release-manifest.json` and `SHA256SUMS.txt` from the downloaded
  installers with the repository tool produced byte-identical files. File
  format magic is PE, ELF, and UDIF; GitHub attestation verification
  passed for all three installers and both metadata files. The Windows
  installer reports product version `0.1.65` and is unsigned as required.
- A controlled install of that exact downloaded Windows artifact contained
  223 files totaling 49,483,978 bytes, included the required third-party
  notice, and had zero retired-runtime path or content hits. Installed frozen
  smoke and silent uninstall returned zero, and no install directory remained.
- No FFmpeg path, live cloud prompt, provider request or credential, keyboard
  write, tag, Release, or announcement was used. The ordinary `main` push was
  the only outward action. This host still cannot supply SmartScreen evidence;
  macOS Open Anyway, hardware checks, publication, and announcement retain
  their separate gates.

## Guard-Proof and Verification Procedure

For each new behavioral guard:

1. run the focused test and confirm PASS;
2. temporarily revert only the production behavior it guards;
3. rerun and confirm FAIL for the predicted reason;
4. restore the behavior;
5. rerun and confirm PASS;
6. run the full automated verification entry point before commit.

Do not duplicate verification commands here. The authoritative entry point is
`.agents/repo-guidance.md` under **Verification**.

Manual visual checks record viewport, view/dialog, normal/Advanced state,
keyboard traversal, and result. They do not use a live cloud prompt or keyboard
write.

## Acceptance Criteria

This plan is complete only when:

- first run has two obvious primary tasks;
- ordinary UI contains none of the banned implementation vocabulary;
- Keymap, Macros, Lighting, Library, and Settings expose a clear normal path;
- all expert controls remain complete under labelled disclosure;
- errors explain failure, saved/changed state, and next action;
- Ollama/Direct API setup and execution labels are unambiguous;
- Lighting/profile Apply and Save to Library remain distinct;
- keyboard navigation, focus, contrast, minimum-size, and viewport checks pass;
- README supplies a direct download and five-minute start;
- screenshots match the verified interface and contain no sensitive data;
- automated verification and native smoke pass;
- this plan and the FFmpeg-removal plan are complete and independently
  committed;
- `0.1.64` remains rejected and the next candidate is `0.1.65`;
- release qualification resumes only for that new exact candidate.
