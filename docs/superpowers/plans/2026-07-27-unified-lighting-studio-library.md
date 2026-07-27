# Unified Lighting Studio and Asset Library

**Status:** Drafted 2026-07-27. The owner approved the integrated studio and
mixed-Library direction recorded in `.agents/decisions.md`. Implementation is
blocked on the Generated-source representation decision in **Open decision
D1**. No implementation work is approved until that ruling is recorded and the
resulting plan is explicitly approved.

## Goal

Replace the split manual editor, direct GIF conversion, detached generation
dialog, and generation-job-only Library with one cohesive Lighting section:

- a simple per-key, per-frame editor;
- deterministic “Animate this” helpers;
- a visual source compositor with pan, zoom, crop, and optional non-uniform
  stretch over the exact destination layout;
- GIF import and optional AI generation as two source paths through the same
  compositor;
- a mixed durable Library containing sources, lighting compositions,
  generated results, and keyboard profile/mapping files;
- server-authoritative compatibility analysis that applies only safe portions
  of a saved item to the current document.

Every Studio operation mutates only the open in-memory document until the
existing explicit hardware-write action is invoked. No Library, preview,
generation, compatibility, or Apply route writes a keyboard.

## Authority and supersession

The 2026-07-27 integrated-studio decision in `.agents/decisions.md` governs this
plan.

This plan supersedes:

- the separate `Generate…` dialog and Create route retained by
  `2026-07-20-video-first-lighting-studio.md`;
- the job-only visible Library taxonomy from that plan;
- the 2026-07-21 editor-first requirement that optional generation live in a
  separate dialog or drawer.

It preserves:

- the 2026-07-27 AI master-switch contract: the switch records intent,
  readiness independently gates inference, and disabling AI does not delete
  Library content;
- the Ollama/API-only backend decision and strict recipe/provider boundary;
- local deterministic rendering, durable banking before success is exposed,
  explicit review and document-only Apply, undo, and no automatic hardware
  writes;
- existing device-specific LED mappings, frame ceilings, dependent-track
  rules, and typed write confirmation.

## Open decision D1 — Generated source representation

The current Local and API AI backends return the same strict procedural recipe,
which is rendered locally at the destination raster. They do not synthesize
provider images. A true image-synthesis path would require a new provider
contract and would have no equivalent in the current Ollama text-model backend.

Choose one before implementation:

1. **Locally rendered procedural source — recommended.** Both AI backends keep
   producing a strict recipe. The local renderer creates a target-independent
   raster animation source, and the compositor then pans, scales, stretches,
   and maps it like an imported GIF. This preserves Local/API parity, existing
   privacy/cost boundaries, deterministic rendering, and offline testing.
2. **Provider-synthesized raster source.** Generated invokes an image or
   animation model and banks its returned media before composition. This
   requires a new API catalog, cost and disclosure contract, paid-call retry
   rules, and an explicit policy for Local AI, which cannot currently provide
   equivalent raster generation.

Only the source-generation adapter depends on this decision. The Studio,
transform, Library, compatibility, removal, and profile work below is common to
both.

## Verified current implementation

- `am_configurator/web/index.html` provides Lighting `Workspace` and `Library`
  tabs plus a separate `Generate…` dialog.
- `am_configurator/web/app.js::renderLightingEdit()` owns the manual frame list,
  LED canvas, painting, playback, direct GIF input, resize-filter selection,
  frame duplication/deletion, brightness, and duration controls.
- `am_configurator/web/app.js::importGif()` sends a base64 GIF directly to
  `/api/led/gif`, immediately replaces a document track, and does not bank the
  original source.
- `am_configurator/device_mapping.py::frames_to_led_tracks()` center-crops every
  frame to the target aspect ratio and exposes no caller-supplied transform.
- `am_configurator/web/app.js` renders AI generation in
  `lighting-generate-dialog`; the resulting procedural job is reviewed and
  applied through the shared mapped-result shape.
- `am_configurator/library.py::GeneratedAssetLibrary` stores durable
  generation jobs under `jobs/<uuid>/`. Its manifest validation, private path
  handling, atomic writes, asset hashing, reconciliation, historical-root scan,
  and safe asset resolution are reusable, but it has no generic saved-item
  model or removal operation.
- `/api/lighting/library` projects generation jobs only. Its filters and UI do
  not cover imported media, manual lighting, or keyboard profiles.
- `server.py::config_transfer_options()` returns family-wide compatibility
  booleans and permits validated macro-only transfer across incompatible
  profiles. It does not return a section-by-section import plan or layout
  signatures.
- `store.py` keeps verified-write `current.json` and bounded device history
  separate from the user-selected Library. Studio and Library operations must
  never call `store.save_current()` or `store.snapshot()`; those remain
  post-write responsibilities only.

## Product behavior

### One Lighting section

Lighting keeps two subordinate views, **Studio** and **Library**, under the same
route shell. There is no Create route and no generation dialog.

Studio uses one stable layout:

- a frame timeline on the left or as a horizontal strip at narrow widths;
- the exact destination canvas in the center;
- a right inspector containing Paint, Source, and Animate controls;
- compact slot and target controls above the workspace;
- playback and a final-output/source-overlay toggle on the canvas.

Changing Studio tools never discards frames. Switching target or Library view
preserves the current frame, transform draft, and undo history for the open
document.

### Manual editing

Paint remains the default tool and requires no AI or Library configuration.
Users can select a frame, click or drag across individual LEDs, fill, clear,
choose a color, set brightness and duration, duplicate, insert, reorder, or
delete frames, and play the exact result.

Add **Save lighting to Library**. It saves the selected custom slot's authored
tracks, timing, brightness, dependent-track relationship, target metadata, and
preview without saving keymap or macro data. Saving is explicit; editing never
auto-creates a new item.

### Animate this

The Animate inspector generates a deterministic draft from the selected frame
or selected range. Version 1 includes:

- **Pulse** — brightness down and back to the source frame;
- **Hue cycle** — periodic hue rotation while preserving per-LED relative
  brightness;
- **Sweep** — a directional brightness mask traversing the physical LED
  coordinates.

Controls are preset, frame count, direction where applicable, and duration.
The result is previewed before replacement, stays within the destination frame
ceiling, creates one undo checkpoint when accepted, and is implemented locally
without AI. Dependent Relic and Neon tracks follow their existing authored or
derived relationship; a preset must not silently erase an independent track.

### Media source compositor

The Source inspector is always available for GIF import. When persisted AI
intent is off, no Generated radio, prompt, AI badge, AI status, repair link, or
AI job strip exists anywhere in Lighting. Existing generated Library items
remain visible.

When AI intent is on, Source shows one radio group:

- **GIF import**
- **Generated**

If the selected backend is not ready, Generated remains visible but disabled
with one direct Settings repair action; no provider or Ollama request starts.
This later, more specific behavior supersedes the older hidden-until-ready UI
rule while preserving the server readiness gate.

Both choices produce an immutable banked source before it is shown as ready.
The same compositor then provides:

- the exact per-key physical outline or rectangular display matrix as an
  overlay;
- dimmed content outside the destination bounds;
- drag-to-pan;
- wheel, trackpad, keyboard, and slider zoom;
- locked aspect ratio by default;
- an explicit **Stretch** toggle enabling independent horizontal and vertical
  handles;
- Fit, Fill, Center, and Reset;
- Crisp, Balanced, and Smooth sampling;
- play/pause for animated sources;
- Source and LED-result preview modes.

One normalized transform applies to every source frame. Applying the draft
creates one undo checkpoint and replaces only the selected destination tracks.
It never auto-saves the open JSON or writes hardware.

### Automatic Library banking

- A validated GIF is banked before the compositor opens. Cancelling composition
  leaves the source available in Library.
- A completed Generated result is already banked before review, preserving the
  current durable-generation rule.
- Re-importing identical GIF bytes reopens the existing source item by
  server-computed SHA-256 instead of creating a duplicate.
- The original media is immutable. Transform recipes and rendered LED results
  are separate versioned assets; re-framing never rewrites the original.
- Import requires a configured, private, writable Library root. There is no
  silent fallback to application data.

### Mixed Library

Library filters are:

- **All**
- **Sources**
- **Lighting**
- **Keymaps**
- **Removed**

Search covers item name, original filename, prompt, product label/ID, tags, and
creation date. Cards show kind, origin, compatibility with the open document,
target/layout, frame count where applicable, and last update.

Supported visible item kinds are:

- imported GIF source;
- generated source/result and historical generation job;
- saved lighting composition;
- saved keyboard profile/mapping file.

Source and generated items open in Studio. Lighting items preview and offer
compatible Apply. Keyboard profiles open a compatibility sheet. Historical
generation jobs remain browsable without destructive migration.

### Keyboard profile banking

Add **Save mapping to Library** to Keymap. It banks a complete portable profile
snapshot, not a raw layer array: original configuration identity, key layers,
macros and references, any present lighting sections, device/layout metadata,
and the exact JSON asset. The Library detail view identifies which sections are
present.

Library also provides **Add files…** for existing AM configuration JSON. The
server validates and banks the exact original plus a normalized metadata
projection. Opening a JSON through the global Open action continues to open it;
it does not silently bank it.

Saving or importing a profile does not change the open document, verified-write
store, or connected device.

## Storage architecture

Keep generation jobs in their existing `jobs/<uuid>/` layout. Add generic saved
items under:

```text
<library-root>/
  jobs/<job-id>/                 # existing generation lineage
  items/<item-id>/
    manifest.json
    source/
    preview/
    result/
  .trash/
    jobs/<job-id>/
    items/<item-id>/
```

Introduce a `SavedItemLibrary` beside `GeneratedAssetLibrary` and a
`LibraryCatalog` that projects both into one discriminated public list. Reuse
the existing root preflight, owner-private permissions, path and link guards,
atomic replacement, per-item locking, asset intents, hashing, historical-root
scan, and sanitized public projection. Do not weaken generation-manifest
validation or rewrite old jobs in place.

### Saved item manifest

Use schema version 1 with an exact allowed-field validator:

```json
{
  "schema_version": 1,
  "item_id": "uuid",
  "kind": "gif_source | lighting_composition | keyboard_profile",
  "origin": "gif_import | manual | json_import | verified_export",
  "name": "user-visible name",
  "created_at": "UTC ISO-8601",
  "updated_at": "UTC ISO-8601",
  "status": "ready",
  "tags": [],
  "device": {
    "product_id": "NEON80",
    "family": "NEON",
    "keymap_signature": "sha256-or-null",
    "lighting_signatures": {"keyframes": "sha256"}
  },
  "source": {
    "asset_id": "uuid-or-null",
    "mime_type": "image/gif-or-application/json",
    "sha256": "server-computed",
    "width": 0,
    "height": 0,
    "frame_count": 0,
    "duration_ms": 0
  },
  "composition": null,
  "profile": null,
  "assets": []
}
```

`composition` stores versioned target-independent source references where
available, the normalized transform, deterministic modifiers, manual LED
overrides, destination snapshot, authored/dependent track relationship, and a
validated rendered-result asset. `profile` stores only metadata and section
presence; the exact configuration remains an immutable JSON asset.

All names and tags are bounded sanitized display text. IDs, paths, MIME types,
hashes, dimensions, counts, timestamps, transform values, section names, and
status are server validated. Manifests never contain credentials, signed URLs,
raw device paths, or provider authorization data.

### Removal

**Remove from Library** atomically moves the owned item/job directory to the
same root's `.trash` under the library lock. The UI immediately offers Undo.
Removed items remain in the Removed filter and can be restored or explicitly
deleted forever. There is no timed automatic purge.

Removal is refused while a generation job is active or while an editor commit
for that item is in progress. Permanent deletion resolves the exact trashed
UUID directory, rejects links and path escapes, and removes only that directory.
Removing any Library item never deletes device-store snapshots, an open
document, exported user files, credentials, or model files.

## Composition and rendering contract

Create a versioned `SourceTransform` shared by GIF and Generated adapters:

```json
{
  "version": 1,
  "offset_x": 0.0,
  "offset_y": 0.0,
  "scale_x": 1.0,
  "scale_y": 1.0,
  "aspect_locked": true,
  "sampling": "nearest | box | lanczos",
  "background": "#000000"
}
```

Offsets and scales use normalized source/destination coordinates, not browser
pixels. Values must be finite and bounded; the server rejects NaN, infinity,
zero/negative scales, unbounded canvases, unknown fields, and unsupported
sampling. Fit, Fill, Center, and Reset reduce to exact transforms in a pure
shared web module.

Extend `device_mapping.frames_to_led_tracks()` through a new transform-aware
composition function rather than changing its existing default behavior.
Decode the immutable source, composite alpha onto black, apply the transform to
every frame, resize through the selected filter, then run the existing
device-map and timing logic. Dependent targets are derived only through the
current family rules.

The server owns final rendering and returns the existing validated
`mapped_result` shape so `applyLedResultToPage()` remains the single
document-application seam. Browser CSS/canvas transforms provide responsive
interaction, but acceptance preview and saved output always come from the
server renderer.

Import accepts larger source dimensions than the destination. Replace base64
JSON upload with a bounded authenticated binary GIF route so encoding overhead
does not consume the generic JSON-body ceiling. Validate GIF magic, MIME,
dimensions, frame count, aggregate decoded-pixel budget, decompression
warnings, duration, and file size before publication. Store the original only
after validation succeeds. Constants live in one server module and have
boundary tests; no decoder warning is bypassed.

Transient render previews live below an owned `.work` directory and are
cancelled/replaced by editor epoch. They are never catalog items. Committing a
composition atomically banks its transform, preview, and mapped result, then
cleans transient work.

## Compatibility contract

Compatibility is server-authoritative and section based. Add canonical
signatures:

- `keymap_signature`: normalized physical layout, matrix coordinates, and
  supported assignment encoding;
- one `lighting_signature` per target: semantic target, raster dimensions,
  output LED count/order, copies/derivations, and track role;
- target limits: frame ceiling, layer count, macro count/event/buffer limits,
  and supported HID/QMK usage encoding.

Dynamic Neon/Vial layouts include the connected definition projection in the
keymap signature. Unknown or absent layout evidence never falls back to another
keyboard.

The compatibility response lists each section as `exact`, `convertible`,
`portable`, or `blocked`, with a stable reason code and user-facing detail:

| Saved content | Import rule |
|---|---|
| GIF or target-independent Generated source | Convertible to any destination target supported by the server renderer. |
| Lighting composition with original source/recipe | Re-render through the destination mapping; preserve the original item. |
| Lighting composition with rendered frames only | Exact matching lighting signature only. |
| Keymap layers | Exact keymap signature and sufficient destination layer capacity only. Never match by array index, visual guess, or product-name similarity. |
| Macros | Portable only when every imported macro validates for destination encoding and complete capacity; never silently truncate or renumber references. |
| Full profile | Import the independently allowed sections into the current destination document. Never copy source `product_info` over destination identity. |

The compatibility sheet shows checked compatible sections and disabled blocked
sections with reasons. The user confirms one import. The mutation uses one undo
checkpoint, preserves all unselected destination data, revalidates the complete
result, and reports exactly what changed. If no section is compatible, the item
remains browseable/exportable but Apply is disabled.

Compatibility and import operate on an open document. A connected keyboard may
provide the target descriptor, but importing never writes it. The existing
write dialog must still independently revalidate device identity and require
typed confirmation plus any physical unlock.

## Local API

Replace the visible job-only Library API with a catalog while retaining old job
status routes for active generation:

- `GET /api/library/items` — paginated mixed catalog with kind, status,
  compatibility, and search filters;
- `GET /api/library/items/<catalog-id>` — sanitized detail;
- `GET /api/library/assets/<catalog-id>/<asset-id>` — verified bounded asset
  serving;
- `POST /api/library/import/gif` — authenticated bounded binary GIF import;
- `POST /api/library/import/profile` — strict configuration JSON import;
- `POST /api/library/save/lighting` — validated selected-slot composition;
- `POST /api/library/save/profile` — validated current profile snapshot;
- `POST /api/library/items/<catalog-id>/render` — bounded transient transform
  preview for a destination descriptor;
- `POST /api/library/items/<catalog-id>/compatibility` — section import plan;
- `POST /api/library/items/<catalog-id>/apply` — validated document-only
  section projection returning a complete candidate configuration;
- `POST /api/library/items/<catalog-id>/remove` — move to internal trash;
- `POST /api/library/items/<catalog-id>/restore` — restore from trash;
- `DELETE /api/library/items/<catalog-id>` — permanent deletion, accepted only
  for an exact trashed item.

Catalog IDs are opaque and include a server-owned namespace discriminator so a
client cannot confuse a job UUID with an item UUID. Mutation bodies reject
unknown fields. Routes re-resolve ownership and content hashes; they never
accept arbitrary filesystem paths or client-supplied compatibility claims.

Keep `/api/lighting/jobs/<id>` for active/recoverable generation operations and
provide compatibility redirects or tombstones for the old
`/api/lighting/library` reads only after the new UI no longer uses them.

## Web implementation

Add pure modules:

- `web/lighting_composer.js` — transform math, fit/fill/reset, normalized pointer
  conversion, frame-range and animation-preset reducers;
- `web/library_state.js` — catalog filters, selection, removal/restore state,
  compatibility projection, and stale-request epochs.

Keep device target definitions in `lighting_targets.js`; do not create a second
family/limit table in `app.js`. Add server-projected layout signatures and
physical overlay data to the document/device descriptor.

Refactor `app.js` in this order:

1. replace the Generate dialog/Create route with Studio inspector state;
2. preserve existing manual canvas behavior through the new Paint inspector;
3. route GIF import through bank → compose → server preview → Apply;
4. route Generated through the same source-item/composition seam after D1;
5. replace job-specific Library renderers with catalog cards/details/actions;
6. add profile save/import and the compatibility sheet;
7. remove dead dialog state, asset URL maps, and route branches only after
   equivalent catalog flows pass.

Use semantic buttons, radio groups, sliders, dialog focus trapping for
compatibility/removal confirmation, keyboard-operable transform handles,
visible focus, reduced-motion behavior, and live regions for import/render/job
progress. The Studio must not autoplay animated sources or trigger inference on
navigation.

## Implementation slices

Each slice lands as a separate commit. Tests are added first and red-proven
before implementation. Do not start the next slice before the current slice is
green and committed.

### 1. Record decision and approve this plan

Files: `.agents/decisions.md`, this plan, `.agents/state.md`.

Record D1, change the status to approved, and establish the exact implementation
baseline. No product code changes belong in this slice.

### 2. Generic saved-item storage and mixed catalog

Files: `library.py`, `server.py`, `tests/test_library.py`,
`tests/test_app.py`.

Implement strict saved-item manifests, private item directories, atomic assets,
mixed job/item scan, catalog IDs, pagination/search/filtering, legacy job
projection, and corruption isolation. Prove existing generation reconciliation
is unchanged.

### 3. Reversible removal

Files: `library.py`, `server.py`, `tests/test_library.py`,
`tests/test_app.py`.

Implement trash, restore, permanent deletion, active-operation refusal,
cross-root behavior, link/path escape protection, and no effect on device-store
history. Red-prove deletion targets only the exact owned UUID directory.

### 4. Device signatures and section compatibility

Files: `device_mapping.py`, `hid_transport.py`, `server.py`,
`tests/test_device_mapping.py`, `tests/test_hid_transport.py`,
`tests/test_app.py`.

Build canonical keymap/lighting signatures, target limits, the section matrix,
and complete candidate-config projection. Cover exact, convertible, macro-only,
unknown-layout, capacity failure, unsupported usage, and identity-preservation
cases.

### 5. Profile banking

Files: `library.py`, `server.py`, `web/app.js`, `web/index.html`,
`tests/test_library.py`, `tests/test_app.py`,
`tests/web/lighting_shell.test.js`.

Implement JSON Add files, Save mapping to Library, exact-source retention,
metadata projection, Library cards/detail, and compatibility-sheet preview.
Saving or browsing must not mutate the document or device store.

### 6. Transform-aware renderer and GIF banking

Files: `device_mapping.py`, a focused media/composition module, `library.py`,
`server.py`, `tests/test_device_mapping.py`, `tests/test_media.py`,
`tests/test_library.py`, `tests/test_app.py`.

Implement strict transforms, bounded binary GIF validation, hash deduplication,
transient render epochs, asymmetric golden mappings, source preservation, and
mapped-result publication. Preserve the old center-crop result when the default
transform is used.

### 7. Unified Studio shell and manual animation helpers

Files: `web/index.html`, `web/style.css`, `web/app.js`,
`web/lighting_composer.js`, `tests/web/lighting_shell.test.js`, new focused web
unit tests.

Move Paint into the stable Studio layout, add transform canvas/overlay and
inspector, implement Pulse/Hue cycle/Sweep drafts, and preserve manual
painting, frame navigation, playback, undo, target relationships, and
responsive behavior.

### 8. GIF compose and saved lighting

Files: `web/app.js`, `web/lighting_composer.js`, `web/library_state.js`,
`web/index.html`, `web/style.css`, focused Python and web tests.

Replace direct GIF track replacement with bank → compose → preview → Apply.
Add Save lighting to Library and Lighting item review/reapply. Prove cancelling
composition keeps the banked source but leaves the document unchanged.

### 9. Generated source integration

Files depend on D1; expected areas are `procedural_generation.py`,
`procedural.py`, `library.py`, `server.py`, `web/app.js`, and generation tests.

Move prompt/progress/review into Source → Generated, produce the D1-approved
banked source representation, open it in the same compositor, and remove the
separate Generate dialog/Create route. Preserve single-operation admission,
cancel/recovery, readiness enforcement, provider-call safety, and durable
partial results.

### 10. Mixed Library UI, Apply, and removal

Files: `web/app.js`, `web/library_state.js`, `web/index.html`, `web/style.css`,
focused web and endpoint tests.

Complete filters, search, compatibility badges, details, Open in Studio,
section Apply, remove/undo/restore/delete-forever, stale request handling,
keyboard navigation, and narrow layouts. Remove job-only visible UI after
historical jobs are available through the catalog.

### 11. Migration, packaging, and acceptance

Files: migration code/tests as required, native smoke assertions, this plan,
`.agents/state.md`.

Run the complete gate, build the native package through `build.py`, run bundled
and mounted-installer frozen smoke checks, and inspect Studio/Library at wide
and narrow widths with AI off, on-but-unready, and ready. Use local fixtures and
fake generation providers. No provider request, credential mutation, model
download, hardware write, remote push, or release publication is authorized.

## Verification

Every new behavioral test must be guard-proven: temporarily restore the
pre-fix behavior, observe the focused test fail, restore the implementation,
and observe it pass.

Required focused proof includes:

1. imported GIF bytes are validated and banked before success; malformed,
   oversized, decompression-heavy, and interrupted imports publish no item;
2. identical imports deduplicate by server hash;
3. pan, zoom, locked aspect, stretch, Fit, Fill, and reset transform every frame
   deterministically, with an asymmetric fixture catching mirror/transpose;
4. exact physical overlays and server output use the same target map;
5. Pulse, Hue cycle, and Sweep are periodic, bounded, deterministic, and stay
   within each family frame limit;
6. AI-off Lighting contains no AI-specific control or copy; AI-on exposes the
   source radio; unready Generated cannot invoke a backend; ready Generated
   still requires an explicit action;
7. imported/generated sources remain in Library after compositor cancel;
8. saved manual lighting round-trips exact colours, timing, brightness, and
   dependent-track semantics;
9. exact-layout profiles import keymaps; incompatible layouts cannot; portable
   macros import only when the complete destination validation passes;
10. a partial profile import preserves destination identity and every
    unselected section and creates one undo checkpoint;
11. remove/restore is reversible, permanent deletion is trash-only, and no
    Library action touches exported files or device-store current/history;
12. legacy generation jobs remain browseable and recoverable;
13. Studio and Library survive relaunch, stale async results cannot replace a
    newer selection, and opening/previewing never persists `current.json`;
14. no automated test reaches a provider, OS credential prompt, Ollama model
    mutation, or physical keyboard.

Run the repository verification entry point from `.agents/repo-guidance.md`.
When the new web modules land, update CI and that canonical entry point in the
same slice so their syntax checks cannot drift from the shipped source set.

Native acceptance uses `python build.py --skip-sync`, the frozen
`--smoke-test`, mounted-installer smoke, and visual inspection of:

- manual frame editing and all three Animate this presets;
- large GIF import, pan, zoom, locked scaling, stretch, preview, Apply, undo,
  and Library reopening;
- AI-off absence and AI-on Generated flow with fake Local and API adapters;
- source, lighting, keymap, legacy job, and Removed Library filters;
- exact-compatible, partially portable, and fully blocked profile sheets;
- remove, Undo, restore, and delete forever;
- desktop, narrow, 150%-equivalent zoom, keyboard-only, and reduced-motion
  layouts with no console errors or page-level horizontal overflow.

## Completion criteria

- Lighting feels like one Studio and Library, with no detached Create product or
  generation dialog.
- Manual per-key frame editing remains complete without AI.
- AI-off means no AI-specific Lighting UI; AI-on exposes GIF/Generated source
  selection, and readiness still gates invocation.
- Imported GIF and Generated results are durable before review; manual lighting
  and keyboard profiles can be saved explicitly.
- Pan, zoom, crop, and stretch operate against the exact target overlay and map
  every frame deterministically.
- Library can browse, search, open, compatibly apply, reversibly remove, restore,
  and explicitly destroy each supported item kind.
- Compatibility imports every safe section and no unsafe section, never changes
  destination identity, never silently truncates, and never writes hardware.
- Existing generation jobs and device-store safety snapshots remain intact.
- The full automated gate, native frozen smoke, and visual acceptance pass with
  no real provider call or keyboard write.
