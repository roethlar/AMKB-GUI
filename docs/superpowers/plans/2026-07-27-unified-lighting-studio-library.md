# Unified Lighting Studio and Asset Library

**Status:** Revised draft, ready for owner approval on 2026-07-27. The owner
approved the integrated Studio, mixed Library, imported-media/AI separation,
local still animation, and six API recipe providers recorded in
`.agents/decisions.md`. No implementation work is approved until this revised
plan receives an explicit go.

## Goal

Replace the split manual editor, direct GIF conversion, detached generation
dialog, and generation-job-only Library with one cohesive Lighting section:

- a simple per-key, per-frame editor;
- deterministic “Animate this” helpers;
- a visual media compositor with pan, zoom, crop, and optional non-uniform
  stretch over the exact destination layout;
- GIF animation plus PNG and BMP still-image import;
- separate optional AI procedural-lighting generation through Ollama, xAI,
  Anthropic, OpenAI, Gemini, Kimi/Moonshot, or DeepSeek;
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
  coordinates;
- **Shimmer** — seeded, repeatable per-LED intensity variation;
- **Move & zoom** — start/end pan and scale keyframes for an imported still,
  including simple drift and Ken Burns-style presets.

Controls are preset, frame count, direction where applicable, and duration.
The result is previewed before replacement, stays within the destination frame
ceiling, creates one undo checkpoint when accepted, and is implemented locally
without AI. Move & zoom is available only while a still-source composition is
active; the colour/intensity effects work on manual frames and imported media.
Dependent Relic and Neon tracks follow their existing authored or derived
relationship; a preset must not silently erase an independent track.

### Media source compositor

The Source inspector imports GIF, PNG, and BMP files without using AI. GIF
retains its decoded animation and timing. PNG and BMP begin as one still frame;
animated PNG is outside version 1 and is rejected rather than silently reduced
to one frame. Every validated import is immutable and banked before the
compositor opens.

The compositor provides:

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

### AI procedural generation

AI generation is a separate Studio tool, not a media source and not an Animate
this option. It accepts a text description, obtains the existing strict
procedural recipe from the selected Local or API backend, renders directly at
the exact destination raster and frame ceiling, banks the recipe, raster
preview, and mapped result, and offers document-only Review and Apply.

The generated result never enters the media compositor: it has no pan, zoom,
stretch, crop, image upload, or imported-still input. AI never analyzes or
animates imported media.

When persisted AI intent is off, no generation prompt, provider status, AI job
strip, setup copy, or AI-specific action exists anywhere in Lighting. Existing
generated Library items remain visible. When intent is on but the selected
backend is not ready, generation remains absent from Lighting and the complete
repair/setup surface stays in Settings. Only intent-on plus current readiness
reveals the **Generate lighting** Studio tool, and generation still requires an
explicit user action.

### AI provider registry

Ollama remains the single Local backend. The API backend gains these fixed
provider IDs and labels:

| ID | Label | Native request contract |
|---|---|---|
| `xai` | xAI | Preserve the existing Responses adapter and strict JSON Schema output. |
| `anthropic` | Anthropic | `POST https://api.anthropic.com/v1/messages`; use `output_config.format` with `type: json_schema`. |
| `openai` | OpenAI | `POST https://api.openai.com/v1/responses`; use strict `text.format` JSON Schema output and `store: false`. |
| `gemini` | Gemini | `POST https://generativelanguage.googleapis.com/v1beta/interactions`; use JSON `response_format` with the recipe schema. |
| `moonshot` | Kimi / Moonshot | Use the OpenAI-compatible Moonshot Chat Completions endpoint with `response_format: {type: json_object}`. |
| `deepseek` | DeepSeek | Use the OpenAI-compatible DeepSeek Chat Completions endpoint with `response_format: {type: json_object}`. |

Provider endpoints are compiled allowlist constants. The product accepts no
custom base URL, proxy URL, organization URL, or arbitrary provider ID. Use the
existing bounded standard-library transport rather than adding vendor SDKs.
Refactor the xAI-only transport into a provider-spec-driven JSON POST transport
that still verifies TLS, ignores environment proxies, refuses every redirect,
pins the expected HTTPS origin before opening the request, bounds request and
response bytes, observes the shared deadline, performs no automatic retry, and
maps errors without retaining a credential or provider response in exception
context. Provider specs own only constant endpoint, authentication headers, and
required version headers. In particular, use `x-api-key` plus
`anthropic-version` for Anthropic, `x-goog-api-key` for Gemini, and bearer
authorization for xAI, OpenAI, Moonshot, and DeepSeek; never place credentials
in a URL.

OpenAI's current resolver names `gpt-5.6-sol` as the flagship model and
`gpt-5.6-terra` as its balanced-cost sibling. Add both as curated OpenAI
choices, defaulting to `gpt-5.6-sol`; record and send an explicit per-model
reasoning effort rather than inheriting a provider default. Before each provider
adapter lands, recheck that provider's official model catalog and endpoint,
then record the exact accepted model IDs, labels, default, structured-output
mode, output limit, reasoning setting where applicable, and pricing source/date
in `ai_catalog.py`. This is a current-data verification step, not an owner
choice: choose at least one generally available current model that supports the
required output contract, and fail the slice if the official documentation does
not establish one. Model IDs remain curated; the UI never sends an arbitrary
model string.

Bump the public AI catalog to schema version 2. It is keyed by provider ID and
projects only bounded public metadata: label, default model, model choices,
structured-output mode, disclosure version, output ceiling, optional dated
price fields, and any fixed reasoning setting. Endpoint URLs, authentication
header names, and transport details remain server constants rather than browser
capabilities.

Native structured-output adapters still run the existing complete local
`procedural.validate_recipe()` check. Kimi/Moonshot and DeepSeek currently
document JSON-object mode rather than strict schema output; give them the same
bounded system prompt plus one compact schema-shaped example, parse exactly one
JSON object, and apply the full local validator. Empty, truncated, refused,
non-JSON, or schema-invalid output is a typed failed attempt. A paid request is
never automatically retried.

Normalize all adapters to `RecipeProvider.generate()` and `RecipeResult`.
Provider-specific code owns request and response shapes, authentication
headers, usage extraction, refusal/stop handling, and sanitized error mapping.
It never owns recipe semantics, rendering, Library publication, cancellation,
or Apply.

Migrate credential-free settings from schema version 5 to version 6 with this
provider-scoped API shape:

```json
{
  "schema_version": 6,
  "ai": {
    "enabled": false,
    "backend": null,
    "local": {
      "model_id": null,
      "model_digest": null,
      "setup_fingerprint": null
    },
    "api": {
      "selected_provider": "xai",
      "providers": {
        "xai": {
          "model_id": "grok-4.5",
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        },
        "anthropic": {
          "model_id": null,
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        },
        "openai": {
          "model_id": null,
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        },
        "gemini": {
          "model_id": null,
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        },
        "moonshot": {
          "model_id": null,
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        },
        "deepseek": {
          "model_id": null,
          "setup_fingerprint": null,
          "disclosure_version": null,
          "disclosure_at": null
        }
      }
    }
  }
}
```

The strict v6 validator requires exactly the six provider records and the exact
four fields shown for each. `model_id` is either null or one curated model for
that provider. Existing xAI keeps its configured model; newly introduced
providers start null. On first selection the UI presents the catalog default
but submits that exact model with the provider-selection mutation, so an
unconfigured provider is never treated as ready merely because the catalog has
a default.

The v5→v6 migration wraps the complete existing xAI record under
`ai.api.providers.xai`, preserves its selected model, setup fingerprint,
disclosure version, and disclosure timestamp byte-for-byte, selects `xai`, and
initializes the other provider records with null model/setup/disclosure fields.
It is credential-free: it must neither read nor mutate the OS vault. Older
schemas continue through their existing validated projections and then through
v6; the v1/v2 plaintext xAI credential migration retains its current verified
write/rollback behavior. A future-schema file still fails closed and is never
rewritten.

Keep one separate OS-vault credential per provider under the existing service
identifier, using the exact usernames `xai`, `anthropic`, `openai`, `gemini`,
`moonshot`, and `deepseek`. Generalize credential status, resolution, update,
rollback, and deletion to require one allowlisted provider ID. The only
environment overrides are `XAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, `MOONSHOT_API_KEY`, and `DEEPSEEK_API_KEY`; each overrides only
its matching vault entry. Settings and capability status inspect credential
presence only for the selected provider while AI is on and API is selected.
They must not enumerate six vault entries, access Keychain while AI is off or
Local is selected, or trigger a sequence of OS credential prompts.

Selecting a provider reveals only its curated model picker, credential
status/actions, disclosure, and setup test. Switching providers preserves every
provider's prior model, credential, disclosure, and setup fingerprint, clears
no unrelated record, and makes readiness reflect only the selected provider.
Generalize the existing `/api/settings/ai`, `/api/settings/credential`,
`/api/settings/privacy`, and `/api/ai/test` contracts rather than adding
provider-specific routes. Credential and disclosure mutations require an exact
provider ID; setup test still accepts only `{backend: "api"}` and resolves the
selected provider server-side so a stale client cannot test an unselected
configuration.

Disclosure acknowledgment is provider-specific because the recipient changes.
It states that only the lighting prompt and target raster/frame requirements
leave the computer; imported GIF/PNG/BMP bytes, keymaps, macros, device paths,
and Library files are never sent. Setup fingerprints include provider, model,
credential identity hash, disclosure version/time, and the production recipe
schema version. Store disclosure versions in the provider catalog and require
`/api/settings/privacy` to match both the selected provider and that provider's
current version.

`AICapabilityService` must resolve the selected provider through the registry,
key cached API providers and remembered failures by the full provider setup
fingerprint, and write setup readiness only to that provider's record. Changing
provider, model, credential, or disclosure invalidates readiness for that
provider without changing the master AI intent. The existing single-operation
admission gate prevents a setup test from racing those settings mutations.

Cost metadata is optional per curated model and dated. An unavailable estimate
is represented as unavailable, never zero. Provider-reported usage is retained
when present, but missing usage does not invalidate an otherwise valid recipe.
Change `recipe_max_cost_usd_ticks()` to return `int | None` and update the
generation-manifest validator compatibly for a nullable estimate if required;
old manifests continue to load without rewrite.

Implementation must recheck these official contracts:

- Anthropic structured outputs:
  <https://platform.claude.com/docs/en/build-with-claude/structured-outputs>
- OpenAI Structured Outputs:
  <https://developers.openai.com/api/docs/guides/structured-outputs>
- OpenAI current-model resolver guidance:
  <https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol.md>
- Gemini structured outputs:
  <https://ai.google.dev/gemini-api/docs/structured-output>
- Kimi/Moonshot JSON mode:
  <https://platform.kimi.ai/docs/guide/use-json-mode-feature-of-kimi-api>
- DeepSeek JSON output:
  <https://api-docs.deepseek.com/guides/json_mode/>

### Automatic Library banking

- A validated GIF, PNG, or BMP is banked before the compositor opens. Cancelling
  composition leaves the source available in Library.
- A completed AI-generated lighting result is banked before review, preserving the
  current durable-generation rule.
- Re-importing identical media bytes reopens the existing source item by
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

- imported GIF/PNG/BMP source;
- generated lighting result and historical generation job;
- saved lighting composition;
- saved keyboard profile/mapping file.

Sources open in the media compositor. Generated and saved Lighting items preview
and offer compatible Apply. Keyboard profiles open a compatibility sheet. Historical
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
  "kind": "media_source",
  "origin": "media_import",
  "name": "user-visible name",
  "created_at": "UTC ISO-8601",
  "updated_at": "UTC ISO-8601",
  "status": "ready",
  "tags": [],
  "device": null,
  "source": {
    "asset_id": "uuid",
    "mime_type": "image/png",
    "sha256": "server-computed",
    "width": 1,
    "height": 1,
    "frame_count": 1,
    "duration_ms": 0
  },
  "composition": null,
  "profile": null,
  "assets": []
}
```

The manifest is discriminated by `kind`. A `media_source` requires
`origin: media_import`, a non-null `source`, and null `composition`/`profile`.
A `lighting_composition` requires a non-null `composition` and null `profile`;
its `source` field is null because any immutable media is referenced by opaque
catalog/asset ID inside the composition. A `keyboard_profile` requires a
non-null `profile`, null `source`/`composition`, and an immutable
`application/json` asset. GIF source metadata has one or more frames and a
positive bounded aggregate duration. PNG and BMP metadata has exactly one frame
and `duration_ms: 0`.

Allowed `kind` values are `media_source`, `lighting_composition`, and
`keyboard_profile`; allowed origins are `media_import`, `manual`, `json_import`,
and `verified_export`, constrained by kind. Allowed media MIME values are
`image/gif`, `image/png`, and `image/bmp`. `device` is null for target-independent
media and otherwise contains only validated product/family identity plus
keymap/lighting signatures.

`composition` stores versioned target-independent media references where
available, the normalized transform, deterministic local-effect specifications,
manual LED overrides, destination snapshot, authored/dependent track
relationship, and a validated rendered-result asset. AI results continue to
use the existing generation-job manifest: their validated procedural recipe is
their target-independent representation and is never reclassified as
`media_source`. `profile` stores only metadata and section presence; the exact
configuration remains an immutable JSON asset.

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

Create a versioned `SourceTransform` shared only by GIF, PNG, and BMP import:

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

AI procedural generation does not construct or accept `SourceTransform` and
does not call the media composition function. It asks the procedural renderer
for the exact selected destination width, height, and frame ceiling, then maps
those exact frames through the existing target rules. Reapplying an AI result
to another compatible destination reruns its validated recipe at that
destination; it never resizes the prior raster preview or frames.

The server owns final rendering and returns the existing validated
`mapped_result` shape so `applyLedResultToPage()` remains the single
document-application seam. Browser CSS/canvas transforms provide responsive
interaction, but acceptance preview and saved output always come from the
server renderer.

Import accepts larger source dimensions than the destination. Replace base64
JSON upload with one bounded authenticated raw-binary media route so encoding
overhead does not consume the generic JSON-body ceiling. A bounded
percent-encoded `name` query preserves the original filename for display, while
the body contains only source bytes and `Content-Type` is a non-authoritative
hint. Reject a missing/invalid length, chunked input, unknown query fields,
oversized names, control characters, and bodies over the media ceiling before
decode.

Sniff and then decoder-verify the authoritative format:

- GIF requires `GIF87a` or `GIF89a`, normalized `image/gif`, bounded dimensions,
  frame count, per-frame timing, aggregate duration, and aggregate decoded-pixel
  work;
- PNG requires the PNG signature, normalized `image/png`, one decoded frame,
  and no animation control/chunk state; APNG is rejected rather than flattened;
- BMP requires the BMP signature, normalized `image/bmp`, one decoded frame,
  bounded dimensions, and bounded decoded-pixel work.

For every format, reject truncated input, trailing decoder failure,
decompression warnings, unsupported frame mode, zero dimensions, and metadata
that disagrees with the decoded asset. Normalize decoded frames to RGBA and
composite alpha onto black only while rendering; retain the exact original
bytes. Publish the immutable source only after the complete validation pass.
File-size, dimension, frame, duration, and decoded-pixel constants live in one
server media module and have exact boundary tests; no decoder warning is
bypassed.

Store local animation as a versioned deterministic effect specification. Pulse,
Hue cycle, Sweep, and Shimmer accept bounded frame count/duration plus
effect-specific bounded parameters; Shimmer also stores its integer seed. Move
& zoom stores start/end normalized offsets and scales and is valid only for a
still media source. Preview and committed render use the same pure reducer and
server renderer, so reopening a composition reproduces byte-identical LED
frames. No local effect invokes `AICapabilityService`, a recipe provider, or a
network transport.

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
| GIF/PNG/BMP media source | Convertible to any destination target supported by the media renderer. Open it in the compositor without mutating the source item. |
| AI-generated result with validated recipe | Convertible by rerendering the recipe directly at the destination raster/frame ceiling. Never pass the old raster through the media compositor or resize it. |
| Lighting composition with original media source and transform/effects | Re-render through the destination media mapping; preserve the original item. |
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
- `POST /api/library/import/media?name=<encoded-name>` — authenticated bounded
  raw-binary GIF/PNG/BMP import with server-sniffed format;
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
3. route GIF/PNG/BMP import through bank → compose → server preview → Apply;
4. move ready-only AI prompt/progress/review into its own Studio tool while
   retaining the exact procedural job → local render → Review → Apply seam;
5. generalize API-provider Settings controls from xAI to the selected catalog
   provider without adding provider controls to Lighting;
6. replace job-specific Library renderers with catalog cards/details/actions;
7. add profile save/import and the compatibility sheet;
8. remove dead dialog state, asset URL maps, and route branches only after
   equivalent catalog flows pass.

Use semantic buttons, radio groups, sliders, dialog focus trapping for
compatibility/removal confirmation, keyboard-operable transform handles,
visible focus, reduced-motion behavior, and live regions for import/render/job
progress. The Studio must not autoplay animated sources or trigger inference on
navigation. There is no GIF/Generated radio group: Source is imported media,
Animate is local deterministic effects, and the AI tool appears separately only
when the master switch is on and the selected backend is ready.

## Implementation slices

Each slice lands as a separate commit. Tests are added first and red-proven
before implementation. Do not start the next slice before the current slice is
green and committed.

### 1. Record decision and approve this plan

Files: `.agents/decisions.md`, this plan, `.agents/state.md`.

Record the imported-media/AI separation and provider rulings, change the plan
status to approved, and establish the exact implementation baseline. No product
code changes belong in this slice.

### 2. Provider registry, settings v6, and credential foundation

Files: `ai_catalog.py`, `credentials.py`, `store.py`, `llm.py`,
`ai_capability.py`, `server.py`, `desktop.py`, and focused app, AI-route,
credential, desktop-smoke, and packaging tests.

Add AI catalog schema 2, the six fixed provider records, the provider-safe JSON
transport, settings v6 and its credential-free v5 migration, generic
provider-scoped vault operations/environment overrides, provider-specific
disclosures/fingerprints, and selected-provider-only capability resolution.
Route existing xAI behavior through the registry without changing its request
or durable-generation semantics. Red-prove v5 preservation, older migrations,
future-schema refusal, credential rollback per provider, no non-selected vault
lookup, no vault lookup while AI is off/Local, and no credential or provider
body in any error.

### 3. Anthropic recipe adapter

Files: `ai_catalog.py`, `recipe_provider.py`, `ai_capability.py`, and focused
provider/capability/route tests.

After rechecking the official catalog and endpoint, add curated Anthropic
model(s), Messages request construction with `output_config.format`, text,
refusal/stop, and usage parsing, setup-test/generation registry wiring, and
sanitized typed failures. Red-prove exact origin/headers/schema, one paid
request, deadline/cancellation behavior, complete local recipe validation, and
no retry.

### 4. OpenAI recipe adapter

Files: `ai_catalog.py`, `recipe_provider.py`, `ai_capability.py`, and focused
provider/capability/route tests.

Add curated `gpt-5.6-sol` and `gpt-5.6-terra` choices after rerunning the
official resolver, Responses request construction with `store: false`, strict
`text.format`, and explicit reasoning, plus output/refusal/usage parsing and
registry wiring. Red-prove the same transport, local-validation, cancellation,
and no-retry properties as Anthropic.

### 5. Gemini recipe adapter

Files: `ai_catalog.py`, `recipe_provider.py`, `ai_capability.py`, and focused
provider/capability/route tests.

After rechecking the official catalog and Interactions contract, add curated
Gemini model(s), schema response-format request construction, output/safety/
stop/usage parsing, and registry wiring. Red-prove that the API key is a header,
never a query parameter or logged URL, and prove the shared provider invariants.

### 6. Kimi/Moonshot recipe adapter

Files: `ai_catalog.py`, `recipe_provider.py`, `ai_capability.py`, and focused
provider/capability/route tests.

After rechecking the official catalog and endpoint, add curated Moonshot
model(s), one OpenAI-compatible Chat Completions JSON-object request with the
bounded schema-shaped example, exact-one-object parsing, full local validation,
typed stop/refusal/usage handling, and registry wiring. Red-prove malformed and
schema-invalid JSON fails without a paid retry.

### 7. DeepSeek recipe adapter

Files: `ai_catalog.py`, `recipe_provider.py`, `ai_capability.py`, and focused
provider/capability/route tests.

After rechecking the official catalog and endpoint, add curated DeepSeek
model(s) using the same JSON-object/local-validation boundary but a distinct
compiled endpoint and response adapter. Red-prove provider isolation, no
cross-provider credential lookup, malformed output refusal, and no paid retry.

### 8. Provider Settings and exact-target AI Studio integration

Files: `web/index.html`, `web/style.css`, `web/app.js`, `server.py`,
`procedural_generation.py`, `tests/test_ai_routes.py`,
`tests/test_procedural_generation.py`, and focused web tests.

Render the selected provider and only its model, credential, disclosure, and
setup controls while the master AI switch is on. Preserve every provider's
stored setup when switching. Move prompt/progress/review from the detached
dialog into a separate ready-only Studio tool, retain procedural job → exact
destination render → Review → document-only Apply, and remove the detached
Generate dialog/Create route. Red-prove AI is absent from Lighting unless both
intent and readiness are true, a generated job never invokes media import,
`SourceTransform`, or the media renderer, and rerendering a recipe targets the
new destination directly rather than resizing old frames.

### 9. Generic saved-item storage and mixed catalog

Files: `library.py`, `server.py`, `tests/test_library.py`,
`tests/test_app.py`.

Implement strict saved-item manifests, private item directories, atomic assets,
mixed job/item scan, catalog IDs, pagination/search/filtering, legacy job
projection, and corruption isolation. Prove existing generation reconciliation
is unchanged.

### 10. Reversible removal

Files: `library.py`, `server.py`, `tests/test_library.py`,
`tests/test_app.py`.

Implement trash, restore, permanent deletion, active-operation refusal,
cross-root behavior, link/path escape protection, and no effect on device-store
history. Red-prove deletion targets only the exact owned UUID directory.

### 11. Device signatures and section compatibility

Files: `device_mapping.py`, `hid_transport.py`, `server.py`,
`tests/test_device_mapping.py`, `tests/test_hid_transport.py`,
`tests/test_app.py`.

Build canonical keymap/lighting signatures, target limits, the section matrix,
and complete candidate-config projection. Cover exact, convertible, macro-only,
unknown-layout, capacity failure, unsupported usage, and identity-preservation
cases.

### 12. Profile banking

Files: `library.py`, `server.py`, `web/app.js`, `web/index.html`,
`tests/test_library.py`, `tests/test_app.py`,
`tests/web/lighting_shell.test.js`.

Implement JSON Add files, Save mapping to Library, exact-source retention,
metadata projection, Library cards/detail, and compatibility-sheet preview.
Saving or browsing must not mutate the document or device store.

### 13. Transform-aware media renderer and media banking

Files: `device_mapping.py`, a focused media/composition module, `library.py`,
`server.py`, `tests/test_device_mapping.py`, `tests/test_media.py`,
`tests/test_library.py`, `tests/test_app.py`.

Implement strict transforms; bounded binary GIF, PNG, and BMP validation;
APNG refusal; normalized metadata; hash deduplication; transient render epochs;
asymmetric golden mappings; source preservation; and mapped-result publication.
Preserve the old GIF center-crop result when the default transform is used.

### 14. Unified Studio shell and local animation helpers

Files: `web/index.html`, `web/style.css`, `web/app.js`,
`web/lighting_composer.js`, `tests/web/lighting_shell.test.js`, new focused web
unit tests.

Move Paint into the stable Studio layout, add transform canvas/overlay and
inspector, implement Pulse/Hue cycle/Sweep/Shimmer plus still-only Move & zoom
drafts, and preserve manual painting, frame navigation, playback, undo, target
relationships, and responsive behavior. Prove every effect is deterministic,
bounded, local-only, and reproduced by the server render contract.

### 15. Media composition and saved lighting

Files: `web/app.js`, `web/lighting_composer.js`, `web/library_state.js`,
`web/index.html`, `web/style.css`, focused Python and web tests.

Replace direct GIF track replacement with GIF/PNG/BMP bank → compose → preview
→ Apply. Add Save lighting to Library and Lighting item review/reapply. Prove
cancelling composition keeps the banked source but leaves the document
unchanged.

### 16. Mixed Library UI, Apply, and removal

Files: `web/app.js`, `web/library_state.js`, `web/index.html`, `web/style.css`,
focused web and endpoint tests.

Complete filters, search, compatibility badges, details, Open in Studio,
section Apply, remove/undo/restore/delete-forever, stale request handling,
keyboard navigation, and narrow layouts. Remove job-only visible UI after
historical jobs are available through the catalog.

### 17. Migration, packaging, and acceptance

Files: migration code/tests as required, native smoke assertions, this plan,
`.agents/state.md`.

Run the complete gate, build the native package through `build.py`, run bundled
and mounted-installer frozen smoke checks, and inspect Studio/Library at wide
and narrow widths with AI off, on-but-unready, and ready. Use local fixtures and
fake adapters for all six API providers plus Ollama. No real provider request,
real credential mutation, model download, hardware write, remote push, or
release publication is authorized.

## Verification

Every new behavioral test must be guard-proven: temporarily restore the
pre-fix behavior, observe the focused test fail, restore the implementation,
and observe it pass.

Required focused proof includes:

1. settings v5→v6 preserves every xAI field without vault access; every older
   migration still lands in valid v6; future schemas remain untouched;
2. credential save/delete rollback is provider-specific, each environment
   override affects only its provider, only the selected API provider is read,
   and AI-off/Local status performs no vault lookup;
3. all six API adapters pin the exact approved origin, authentication/version
   headers, bounded payload, output ceiling, and documented structured-output
   mode; redirects, proxies, oversized bodies, and automatic retries remain
   impossible;
4. every provider response undergoes complete local recipe validation;
   provider refusals/stops and missing usage are handled explicitly, and
   malformed Moonshot/DeepSeek JSON fails after exactly one paid request;
5. provider/model/credential/disclosure changes invalidate only that
   provider's setup fingerprint, while switching back restores still-current
   readiness and never changes the master AI switch;
6. imported GIF, PNG, and BMP bytes are format-sniffed, fully validated, and
   banked before success; malformed, oversized, decompression-heavy,
   interrupted, and APNG imports publish no item;
7. identical media imports deduplicate by the server hash;
8. pan, zoom, locked aspect, stretch, Fit, Fill, and reset transform every GIF
   frame and each still deterministically, with an asymmetric fixture catching
   mirror/transpose;
9. exact physical overlays and server output use the same target map;
10. Pulse, Hue cycle, Sweep, Shimmer, and still Move & zoom are bounded,
    deterministic, stay within each family frame limit, survive Library
    reopen, and never call an AI service;
11. AI-off and AI-on-but-unready Lighting contain no AI-specific control or
    copy; ready AI exposes one separate Generate lighting tool with no
    GIF/Generated radio and still requires an explicit action;
12. AI generation and cross-target recipe reapplication render directly at the
    requested destination and never call media import, `SourceTransform`, or
    the media resize/composition function;
13. imported sources remain in Library after compositor cancel and completed
    generated results remain after Review cancel;
14. saved manual lighting round-trips exact colours, timing, brightness, local
    effect specs, and dependent-track semantics;
15. exact-layout profiles import keymaps; incompatible layouts cannot; portable
    macros import only when the complete destination validation passes;
16. a partial profile import preserves destination identity and every
    unselected section and creates one undo checkpoint;
17. remove/restore is reversible, permanent deletion is trash-only, and no
    Library action touches exported files or device-store current/history;
18. legacy generation jobs remain browseable and recoverable;
19. Studio and Library survive relaunch, stale async results cannot replace a
    newer selection, and opening/previewing never persists `current.json`;
20. no automated test reaches a real provider, OS credential prompt, Ollama
    model mutation, or physical keyboard.

Run the repository verification entry point from `.agents/repo-guidance.md`.
When the new web modules land, update CI and that canonical entry point in the
same slice so their syntax checks cannot drift from the shipped source set.

Native acceptance uses `python build.py --skip-sync`, the frozen
`--smoke-test`, mounted-installer smoke, and visual inspection of:

- manual frame editing and all five Animate this effects;
- large GIF plus PNG/BMP import, APNG refusal, pan, zoom, locked scaling,
  stretch, still Move & zoom, preview, Apply, undo, and Library reopening;
- AI-off and unready absence plus ready Generate lighting flow with fake Ollama
  and each of the six API adapters;
- direct exact-target AI rendering and cross-target recipe rerender with no
  compositor or resize controls;
- source, lighting, keymap, legacy job, and Removed Library filters;
- exact-compatible, partially portable, and fully blocked profile sheets;
- remove, Undo, restore, and delete forever;
- desktop, narrow, 150%-equivalent zoom, keyboard-only, and reduced-motion
  layouts with no console errors or page-level horizontal overflow.

## Completion criteria

- Lighting feels like one Studio and Library, with no detached Create product or
  generation dialog.
- Manual per-key frame editing remains complete without AI.
- AI-off and unready AI mean no AI-specific Lighting UI; ready AI exposes one
  separate procedural Generate lighting tool, and there is no media-source
  radio.
- Ollama and xAI, Anthropic, OpenAI, Gemini, Kimi/Moonshot, and DeepSeek all
  produce the same locally validated procedural recipe through one readiness
  boundary.
- Imported GIF/PNG/BMP and generated results are durable before review; manual
  lighting and keyboard profiles can be saved explicitly.
- Pan, zoom, crop, and stretch operate only on imported media against the exact
  target overlay and map every frame deterministically.
- Pulse, Hue cycle, Sweep, Shimmer, and still Move & zoom animate locally
  without AI.
- AI never analyzes or animates imported media and never resizes a generated
  raster; recipe results render directly for the selected destination.
- Library can browse, search, open, compatibly apply, reversibly remove, restore,
  and explicitly destroy each supported item kind.
- Compatibility imports every safe section and no unsafe section, never changes
  destination identity, never silently truncates, and never writes hardware.
- Existing generation jobs and device-store safety snapshots remain intact.
- The full automated gate, native frozen smoke, and visual acceptance pass with
  no real provider call or keyboard write.
