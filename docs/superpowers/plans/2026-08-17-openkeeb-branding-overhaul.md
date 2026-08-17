# OpenKeeb branding and product-interface overhaul (H7)

Status: **approved for continuous execution** by the owner on 2026-08-17. The
owner delegated all H7 sequencing, visual, copy, prototype, and implementation
choices and explicitly rejected phase-by-phase approval. This plan is the code
gate required by `AGENTS.md`; implement it through completion without treating
intermediate slices as owner gates. The only stops are the reserved boundaries
listed below.

## Objective

Turn the current Angry-Miao-centered AM Configurator product into OpenKeeb: a
local, open keyboard configurator whose identity, information architecture, UI,
documentation, native display names, and capability language match the hub and
AM/Vial/VIA implementation already present on `v2/openkeeb`.

This is not a textual rename and not a CSS color pass. The whole shipped product
must read and feel like one broader keyboard workbench while preserving every
existing device-safety and data-integrity boundary.

## Authoritative rulings

- `.agents/decisions.md`, 2026-08-16: this repository builds OpenKeeb; the work
  is a branding overhaul and repositioning, not a rename.
- `.agents/decisions.md`, 2026-08-17: H7 is all user-facing surfaces and is not
  complete until the whole scope is complete; implementation details are
  delegated and do not return to the owner at each phase.
- `.agents/repo-guidance.md`: full automated verification and native packaging
  verification apply; automated and rendered tests never write a keyboard.
- The H0-H5 hub plan remains authoritative for capability claims and hardware
  safety. H7 changes presentation, not transport or profile semantics.

## Reserved boundaries

H7 must not change or publish any of these without a new explicit owner action:

- macOS bundle identifier and Windows AppId;
- settings/data-directory names or migration behavior;
- PyPI distribution name, the installed `am-configurator` command, environment
  variables, session-storage keys, or other compatibility identifiers;
- AUR package id, Flatpak application id, repository slug/URL, sponsor URLs;
- canonical product version or the `2.0.0` cut;
- release tags, GitHub Releases, package-manager publication, announcements;
- physical keyboard writes, paid services, or destructive Git history changes.

These retained identifiers are implementation compatibility, not visible
product positioning. Current/historical release records continue to use the
name under which they shipped.

## Product language contract

### Positioning

OpenKeeb is a local, open keyboard configurator built around one portable hub
profile. The default language is keyboard-first and ecosystem-neutral.

Use this capability hierarchy everywhere:

1. **OpenKeeb core:** discover a board, read what its firmware exposes, edit a
   portable document, transfer compatible keymaps, and write only after exact
   target proof and confirmation.
2. **Angry Miao spoke:** full current keymap, macro, and model-specific lighting
   workflow for supported CyberBoard, Relic, AFA, and Neon hardware.
3. **Vial spoke:** keymap and macro discovery/read/edit/write with embedded
   layout and physical-unlock handling; generic lighting remains H6 work.
4. **VIA spoke:** definition-bound keymap and macro read/edit/write; the user
   supplies the matching definition; generic lighting and definition fetching
   remain H6/later work.

Never claim universal keyboard support, firmware flashing, automatic VIA
definition fetching, generic Vial/VIA lighting, or lighting read-back where the
firmware does not provide it. Retain explicit document-only versus keyboard
mutation language.

### Naming

- Visible current-product name: `OpenKeeb`.
- Generic document: `OpenKeeb profile` or `hub profile`, depending on context.
- AM-specific wire/profile facts may say `Angry Miao` when that distinction is
  load-bearing. They must not call the whole product AM Configurator.
- Historical release notes, announcements, archived plans, third-party notices,
  and compatibility identifiers keep their historically correct names.

## Visual system

Build one reproducible identity without network fonts or opaque source assets.

### Brand mark and native icon

Add a checked-in deterministic asset generator under `build_tools/` as the
single source for:

- `assets/openkeeb-mark.svg` — simplified vector brand mark for docs and UI;
- `assets/openkeeb.png`, `assets/openkeeb-512.png`,
  `assets/openkeeb.ico`, `assets/openkeeb.icns` — native/package assets;
- `am_configurator/web/icon.png` — web/native-window page icon.

The mark is an open keycap/workbench symbol, not letters `AM`, a copied keyboard
brand, or a photorealistic keyboard. It must remain legible at 16, 32, 128, and
512 px, use no text, and have a transparent-safe silhouette. Generation must be
offline and deterministic from repository code. Remove the old generated AM
identity assets only after every consumer and packaging test points to the new
ones.

### Tokens and composition

Keep the existing accessibility floors but replace the current undifferentiated
purple-card treatment with a structural workbench system:

- near-black canvas, elevated graphite work surfaces, restrained violet as the
  document/edit signal, cyan as live/connected signal, amber for caution, red
  only for destructive/write risk;
- a compact brand rail and document/device command bar with visibly separate
  document actions and hardware actions;
- page headers that explain the current task and target instead of repeating
  route names in decorative cards;
- board/work surface as the visual center, with inspectors and review rails
  visibly subordinate;
- consistent card, control, tab, disclosure, status, empty-state, and dialog
  primitives across Keymap, Macros, Lighting, Library, Settings, and overlays;
- system font stack only; technical values retain monospace;
- no decorative animation required for comprehension; honor reduced motion.

The native minimum window and 1000×680, 1280×800, and 1600×1000 browser sizes
must remain usable without clipped primary actions or page-level horizontal
scroll.

## Surface inventory

H7 is incomplete until every item below uses the new identity and language.

### Global shell and empty state

- Add the OpenKeeb mark/name to the persistent shell.
- Recompose navigation, document identity, connection status, and write action
  so a user can distinguish local file state from connected keyboard state.
- Replace the generic empty illustration and AM-oriented setup copy with two
  clear starts: connect/read a keyboard or open an OpenKeeb/compatible profile.
- Preserve all existing IDs and event bindings unless a planned test is updated
  in the same slice.

### Keymap and overlay review

- Use the cross-ecosystem Keymap workspace as the reference implementation of
  the new workbench hierarchy.
- Preserve physical geometry, layer controls, immediate assignment, Advanced
  raw codes, undo/redo, generic dirty state, and H4 review worklist semantics.
- Make target ecosystem/capability visible without making AM the product frame.
- Keep `keyboard unchanged until Write` and exact generic-write readiness clear.

### Macros

- Apply the same workbench hierarchy to macro list, Text/Flow/Repeat editor,
  capacity meter, recording, and technical event rows.
- Preserve every existing compiler, recording, capacity, and AM-only capability
  rule. Explain unavailable generic macro authoring as a capability boundary,
  not an application failure.

### Lighting Studio and Library

- Recompose the dense toolbar/context/stage/timeline/inspector arrangement using
  the same shell and tokens; do not regress destination locking, preview/apply,
  reduced motion, or source/board distinction.
- Keep AM-specific lighting controls accurately scoped to the connected/profile
  target. Do not imply H6 generic lighting already exists.
- Align Library filters, cards, empty/error states, pagination, dialogs, and
  Settings storage language with OpenKeeb.

### Settings, About, device, hub, compatibility, and write dialogs

- Replace current-product naming and AM-centered explanations.
- Devices must present AM, Vial, and VIA as explicit ecosystem capabilities.
- Hub/profile terminology must be understandable without internal architecture
  vocabulary.
- Write dialogs retain exact target identity, backup action, accepted/read-back
  counts, Vial unlock guidance, cancel behavior, and typed confirmation.
- About must say OpenKeeb is an independent open-source community project and
  distinguish protocol compatibility from vendor affiliation.

### Toasts, errors, and backend-visible messages

- Sweep all current user-visible Python and browser strings for the old product
  name or whole-product Angry Miao framing.
- Keep AM-specific protocol errors technically accurate.
- Do not rename internal compatibility keys, storage paths, executable command,
  test fixture products, or historical artifacts merely to satisfy a text grep.

## Native packaging and repository-facing product surfaces

Change current display/output names while preserving reserved ids:

- native window title and smoke-test title checks;
- PyInstaller executable/collection/app bundle display names and icon paths;
- local build directory expectations and installer artifact filenames;
- macOS DMG volume/application display names, Windows installer display names,
  Linux desktop display/comment/icon names;
- CI/release workflow display names, paths, artifact labels, and smoke commands;
- package-manager generated **display names and descriptions only**; retain AUR
  package name, Flatpak id, wrapper command, repository URL, and publication
  pause;
- active README, installation guide, Linux device guide, issue templates, and
  current screenshots/captions.

Do not rewrite old release notes or announcements. README and installation docs
must distinguish the OpenKeeb development product from already-published AM
Configurator releases until the owner authorizes an OpenKeeb release/version.

## Test-first implementation slices

Each slice gets its own local commit with records closed in the same commit.
None is an owner gate.

### H7a — identity contract and deterministic assets

1. Add failing branding-contract tests covering the visible product name,
   reserved-identifier allowlist, icon consumers, and historical exclusions.
2. Add the deterministic asset generator and new identity assets.
3. Switch web/native/package icon consumers and the visible product constants.
4. Prove the new tests bite by temporarily restoring one old visible identity,
   observing failure, then restoring the fix.

### H7b — complete application shell and surface overhaul

1. Add failing DOM/design-token contracts for shell composition, brand rail,
   document/hardware action separation, every route, dialogs, narrow windows,
   focus, contrast, and reduced motion.
2. Rework `index.html`, `style.css`, and browser render functions without
   changing device/profile behavior.
3. Sweep current user-visible server/desktop errors and labels.
4. Render and inspect empty, Keymap AM, Keymap Vial/VIA, Macros, Lighting,
   Library, Settings, Devices, Hub, About, compatibility, and write states.

### H7c — packaging, docs, workflow display names, and screenshots

1. Add failing packaging/release-info tests for OpenKeeb display and artifact
   names while asserting all reserved identifiers remain byte-for-byte stable.
2. Update spec/build/install scripts and workflow display/path references.
3. Reposition README/current docs with the capability matrix and compatibility
   disclaimer; retain historical release truth.
4. Capture fresh synthetic screenshots from the actual app at the canonical
   viewport and replace current-product README screenshots.

### H7d — closure

1. Run the full repository verification entry point.
2. Because native packaging changes, build on macOS with
   `python build.py --skip-sync` in the prepared environment and run the frozen
   executable's `--smoke-test`/native-policy smoke through the supported build
   path. Do not publish the artifact.
3. Run the rendered matrix through the in-app browser with fake/no hardware;
   verify zero console errors and no write route invocation.
4. Run a repository-wide old-name/user-facing copy audit against the allowlist.
5. Update this plan with exact landing evidence and `.agents/state.md` with the
   final commit/test/build/smoke results.

## Automated verification

Run the exact entry point from `.agents/repo-guidance.md` after every behavior
slice and once on the final committed tree:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_workspace.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/hub_keymap_state.js
node --check am_configurator/web/hub_keycode_palette.js
node --check am_configurator/web/app.js
uv build
```

Docs-only/record commits require `git diff --check`. No automated test, browser
smoke, screenshot capture, or native smoke may send a setter to a physical
keyboard.

## Acceptance criteria

H7 is complete only when:

- every current user-facing product surface says OpenKeeb and uses the new
  identity; no screen remains an AM-branded island;
- the interface is structurally reworked across all routes and dialogs, not
  merely recolored;
- capability language accurately distinguishes AM, Vial, and VIA support;
- new icon assets are deterministic, legible, and consumed by web/native/
  packaging surfaces;
- current README/install/current guides and generated packaging display names
  are repositioned, while historical releases and reserved identifiers remain
  intact;
- all new tests have demonstrated red proofs, full verification is green, the
  native build/smoke is green, and rendered checks cover every surface group;
- no release/publication, deep-id migration, physical write, or other reserved
  action occurred;
- the worktree is clean and every implementation slice plus final records is
  committed locally.
