# Lighting Studio Human-First Redesign

**Status:** Owner-approved on 2026-08-01 after Gate LSR-G1 and the asymmetric
AM Configurator export / AM Master import contract were recorded in
`.agents/decisions.md`. Implementation is authorized beginning with LSR-1.

## Objective

Replace the current Lighting frontend interaction and state model with a
human-first workspace while preserving the parts that already produce correct
results:

- canonical device layouts and LED mappings;
- media decoding, transform geometry, and exact target rendering;
- procedural-only AI generation;
- the unified local Library;
- document-only Apply with one Undo checkpoint;
- explicit Save to Library; and
- the separately authorized, identity-checked hardware-write boundary.

The application also imports recognized Angry Miao AM Master JSON. Its own
saved JSON is an app-native, self-contained format and makes no compatibility
promise to AM Master or another tool.

For imported media, the workspace must show two synchronized views at the same
time:

1. the actual selected source frame, used for pan and zoom; and
2. the physical lighting target, showing exactly what every hardware LED will
   display for that same point in the animation.

One canonical transform and one playhead drive both views. The board view never
contains, blends, masks, or overlays the full-resolution source image. Its
pixels come only from the exact canonical LED arrays later consumed by Apply
and, after a separate write authorization, by the device writer.

This is a redesign, not a patch for the rejected playback transition. The
cross-target playback defect, misleading source overlay, rigid offline layout
requirement, opaque Effects flow, unsupported media selection, invalid preset,
and duplicate low-level errors are symptoms of the same frontend ownership
problem and are corrected through one state and rendering contract.

## Authority and supersession

- `AGENTS.md` and `.agents/repo-guidance.md` own process, verification, device
  safety, and action authorization.
- `.agents/decisions.md` owns the integrated Lighting/Library product, the
  imported-media/AI separation, procedural-only AI, the unconditional FFmpeg
  prohibition, app-native-export/AM-Master-import asymmetry, document-only
  Apply, and the independent hardware-write gate.
- `2026-07-27-unified-lighting-studio-library.md` remains authoritative for
  Library ownership, media banking, compatibility, AI separation, and the
  backend `mapped_result` seam. This plan supersedes its frontend layout and
  interaction model.
- `2026-07-29-product-experience-remediation.md` remains authoritative for
  plain language, normal-versus-Advanced hierarchy, accessibility, and the
  separation of Apply from Save to Library. This plan replaces its Lighting
  presentation where the completed UI proved confusing in owner testing.
- `2026-08-01-imported-media-framing-repair.md` remains authoritative for exact
  transform geometry, maximum-overlap constraints, pointer safety, browser /
  Python vector parity, and the Windows native audit foundation. This plan
  supersedes its source-versus-result preview toggle: source and board are now
  separate simultaneous views.
- `2026-07-31-public-release-0.1.65.md` remains the release plan. All three
  candidates are permanently rejected, no candidate is active, and R65-2 may
  not restart until this redesign is implemented, verified, accepted, and
  pushed.

No provider request, credential use, hardware write, tag, Release, macOS Open
Anyway action, security-setting change, or announcement is authorized by this
plan.

## Rejected UX evidence

The redesign must close all of these observed failures as one product problem:

1. Playback is global rather than destination-bound. A Per-key timer retained
   old frame arrays after the user selected Head matrix and painted those old
   colors into the new target DOM.
2. Imported media is currently mounted behind the LED grid. The full source
   image can appear as a ghost image and visually claim that hardware LEDs will
   reproduce detail that the canonical mapped result has already discarded.
3. Source framing and LED output are mutually exclusive modes. The user must
   crop without continuously seeing how the image reduces to physical LEDs.
4. An opened Neon profile loses its dynamic physical layout when no matching
   device is connected, so the whole per-key editor is withheld even though
   opening and editing a profile must be an offline operation.
5. Effects controls change hidden parameters but do not create obvious output
   until a separate Preview action is discovered and invoked.
6. The media chooser can present files the importer will reject. A previous
   `accept`-attribute experiment is not a valid repair because WKWebView can
   disable supported GIF/PNG/BMP files when that filter is present.
7. Center can calculate a scale above the version-1 maximum of `32`, then show
   duplicate errors containing internal field names such as `scale_x`.
8. The vertical frame list and dense three-column shell push the important
   relationship—source to LEDs—out of the first viewport.

The Macro page complaint (existing macros are not shown directly enough) is a
separate queued product finding. This Lighting plan does not redesign Macros.

## Confirmed AM Master import evidence

Seven owner-supplied AM Master exports were structurally inspected without
copying their lighting payloads into the repository:

- four AFA exports are full `ALICE` profiles with eight pages, seven 200-key
  layers, and canonical 90-pixel per-key custom tracks;
- those full profiles currently fail only because AM Master retains a one-color
  placeholder in built-in tracks explicitly marked `valid: false` with
  `frame_num: 0`; replacing only those semantically disabled placeholders with
  empty `frame_data` makes all four pass the existing validator and serial
  writer plan without another repair;
- three AM 80 exports are lighting-only objects rather than profiles, with
  `speed`, `brightness`, optional `description`, `frames`, and `frames_axial`;
- their `frames` contain 230 six-digit RGB values per frame for Head matrix,
  their `frames_axial` contain 89 for Per-key, and the paired tracks have equal
  frame counts; the supplied files exercise 1, 50, and 75 frames; and
- the observed brightness dialects use normal `0..100` percentage values or
  `255` for full brightness.

The supplied files remain machine-local acceptance evidence. Add minimized,
synthetic fixtures that preserve these schemas and edge cases; do not commit
the owner's original filenames, lighting arrays, or other payload data.

## Non-negotiable product contract

### Exact board truth

Define one validated browser shape, `BoardFrameSet`, for anything shown on the
physical board:

```text
BoardFrameSet
  context: {document_epoch, slot, target, source_kind, revision}
  frames_by_target: {target -> array<array<#RRGGBB>>}
  frame_count: positive integer
  duration_ms: supported firmware duration
  timeline: array<PreviewTimelineEntry>
  provenance: document | local_effect | media_render | procedural_result
```

`BoardFrameSet` is a browser view model, not a new persisted profile or Library
schema. It validates target names, frame counts, color counts, canonical RGB,
and context before the DOM can consume it.

Board data sources are exact and limited to:

- the current document track arrays for Paint;
- the immutable local-effect draft arrays that Apply will clone into the open
  document;
- `MediaRenderCoordinator`'s accepted `mapped_result` arrays for imported
  media; and
- the existing reviewed `mapped_result` arrays for procedural AI and Library
  results.

No board component accepts a URL, `HTMLImageElement`, Canvas image, CSS
background image, source raster, or approximate browser resample. The board
component projects colors through the canonical physical layout and target map
only. A DOM guard must prove there is no `img`, `picture`, `video`, or canvas
image source inside the board preview.

Apply does not rerender an accepted result. It clones the currently accepted
`BoardFrameSet` arrays through the existing `applyLedResultToPage()` seam, then
the open document becomes the source for any later write. Tests compare every
target, frame, LED index, duration, and dependent-track rule at Preview,
Apply, saved composition, and writer-plan boundaries.

### Source and board synchronization

When imported media is active:

- the Source pane and Board pane are both visible;
- Source shows one display-only projection of the actual decoded source frame,
  never the LED reduction;
- Board shows the canonical LED arrays for the same accepted timeline entry;
- one normalized source transform owns pan, zoom, stretch, sampling, presets,
  and Move & zoom;
- one destination-bound playhead owns source-frame selection, board-frame
  selection, scrubber position, Play/Pause, and frame labels; and
- both panes identify the same accepted render revision.

The source projection may be downscaled to the visible preview ceiling, but it
must preserve the complete decoded frame, aspect ratio, and source-coordinate
system. That display-only downscale never enters device rendering.

Pointer input maintains a requested transform for immediate interaction and
requests an exact selected-frame render from the loopback backend. Only a
current response atomically becomes the accepted transform/revision used by
both panes. While a request is pending, Board visibly says `Updating lights…`,
retains the last accepted LEDs, and Apply stays disabled; it never presents old
LEDs as if they belonged to the requested transform. Superseded responses are
discarded without a toast.

Playback advances only when the source projection for the next timeline entry
is ready. The same reducer event then advances Source, Board, scrubber, and
frame label. If source-frame loading falls behind, both panes hold the prior
entry rather than drifting apart.

### Destination and playback isolation

A workspace context key is the tuple:

```text
document_epoch + custom slot + target + accepted preview revision
```

Every render request, response, timer, playhead tick, draft, and Apply intent
carries that key. Changing document, slot, target, media item, or accepted
preview invalidates the prior playback session before any rerender. A stale
timer or response is a no-op and cannot query or mutate the current DOM.

Target and slot changes preserve independent authored document tracks but stop
active playback and set the destination's playhead to its own last valid frame
or frame zero. Playback never migrates old frame arrays to a new target.

### Offline-first profile editing

Opening a valid profile is never conditional on a connected keyboard. Fixed
families use their built-in canonical layouts. A dynamic Vial/Neon layout may
come from validated portable profile metadata, validated local remembered
evidence, or a currently connected exact device; it is never guessed from a
product name.

If a legacy Neon JSON contains no layout evidence and this installation has
never seen the matching layout, the document still opens. Head matrix,
non-geometry-dependent lighting data, Keymap data, Macros, Library, and Save
remain available. Only the physical Per-key surface shows a scoped explanation
of the missing layout and the one action that can obtain it. The application
must not replace the entire Lighting route with a device-required empty state.

Connecting hardware verifies layout identity at write time. A persisted or
remembered dynamic layout whose canonical signature differs from the selected
device blocks the write before typed confirmation and before any transport
mutation. Editing and previewing remain offline and read-only with respect to
hardware.

### Asymmetric JSON interoperability

`Save JSON` writes the canonical app-native profile, including validated
`_am_configurator` metadata where available. Do not add a vendor-clean mode,
sidecar, compatibility toggle, or output-shape promise for AM Master. Hardware
encoders receive only the canonical device sections because protocol preflight
strips app metadata independently of file interoperability.

All global JSON Open/import paths become server-authoritative and classify one
of these forms before mutating the open document:

1. **AM Configurator profile** — supported device configuration plus optional
   valid `_am_configurator` metadata;
2. **AM Master full profile** — supported `product_info.product_id`, key layers,
   pages, and optional macro/legacy sections; or
3. **AM Master AM 80 lighting** — the exact lighting-only dialect confirmed
   above, with no claim that it is a complete keyboard profile.

Never classify by basename. Parse under the existing bounded profile byte
ceiling, reject duplicate JSON object keys, require a JSON object root, and
match a strict structural discriminator. The server returns `source_format`,
canonical normalized content, and a list of every normalization. JavaScript
does not independently reinterpret vendor shapes.

For AM Master full profiles:

- normalize assignment and RGB spelling through the existing lossless helpers;
- ignore comment-only `//` members;
- canonicalize a track to `frame_num: 0, frame_data: []` only when the track is
  explicitly `valid: false`, declares zero frames, and contains the recognized
  single-color placeholder form;
- preserve every valid supported keymap, macro, lighting, timing, brightness,
  page-validity, and destination-identity value; and
- reject mismatches in enabled tracks, capacities, product identity, or any
  unrecognized lossy convention. Do not make `validate_config()` broadly ignore
  malformed disabled data from arbitrary callers; normalization belongs in the
  named AM Master adapter before canonical validation.

For AM Master AM 80 lighting:

- require exactly the known required fields and optional `description`;
- require equal nonzero track frame counts within the Neon frame ceiling;
- require exactly 230 Head and 89 Per-key six-digit hexadecimal colors per
  frame, then normalize them to uppercase `#RRGGBB`;
- map `frames` to canonical `head` and `frames_axial` to canonical `axial`;
- treat `speed` as bounded milliseconds;
- accept brightness `0..100` directly and the observed sentinel `255` as 100%;
  reject unproven values `101..254` rather than guessing a scale; and
- produce a transient, family-bound lighting composition and `BoardFrameSet`,
  not a fabricated full profile or writable device document.

A lighting-only composition opens in Studio review even with no document. Head
matrix preview, timeline, playback, and explicit Save to Library work offline.
Per-key preview uses validated portable/remembered/current layout evidence or
shows the scoped missing-layout state. Applying requires an open compatible AM
80 document, a selected custom slot, explicit Apply, and one Undo checkpoint.
Opening or reviewing never writes hardware and never silently saves to Library.

The import result identifies `AM Master profile` or `AM Master AM 80 lighting`
in task language. Any normalization appears once in a review note; expected
disabled placeholders do not become alarming error toasts.

### Human-first tool behavior

Lighting retains one Studio and one Library. Studio tools remain Paint, Import
media, Effects, and optional AI:

- **Paint:** edits canonical document frames directly and keeps full manual
  capability without AI, media, or a connected device.
- **Import media:** banks GIF/PNG/BMP before editing, opens the synchronized
  Source/Board workspace, renders live output, and exposes Apply and Cancel.
- **Effects:** creates a live non-mutating draft immediately. There is no
  separate Preview button. Selecting an effect is an explicit user action and
  starts an obvious loop; reduced-motion mode instead selects a demonstrative
  changed frame and leaves playback paused. Parameter changes update the draft
  and board immediately. Apply remains explicit.
- **AI:** remains a separate procedural-only action, hidden unless enabled and
  ready. It never receives imported media and keeps the existing Review/Apply
  seam.

Import media and Effects expose friendly presets first. Sampling, independent
axes, exact frame counts, firmware duration, and seed remain under contextual
Advanced controls. Every normal preset must already satisfy the strict backend
validator; a preset may clamp to a legal boundary but may not first author an
invalid value and report an error.

Errors are rendered once in the nearest persistent status region. Toasts are
reserved for cross-workspace outcomes. One request/reducer revision owns one
visible error, duplicate identical errors coalesce, and browser/backend field
names are mapped to task language before display. Raw exception text, paths,
and internal labels such as `scale_x` never reach normal UI.

### Persistence and mutation boundaries

- Import banks immutable source bytes before the editor opens.
- Live selected-frame renders and full sequence renders are transient and do
  not create Library items.
- Apply changes only the current open document and creates one Undo checkpoint.
- Save to Library is a separate explicit action.
- Cancel leaves an already banked source in Library and leaves the document
  unchanged.
- Navigation, import, playback, and Effects never write hardware or call an AI
  provider.
- Hardware write remains the existing separately authorized action with device
  identity checks, dynamic-layout verification, typed confirmation, physical
  unlock where required, and post-write verification.

## Workspace state architecture

Add `am_configurator/web/lighting_workspace.js` as a dependency-free UMD pure
module loaded before `app.js`. Do not expand the existing route/job reducer in
`lighting_state.js` into editor state. `lighting_state.js` continues to own
routes and generation jobs; `lighting_workspace.js` owns destination, draft,
preview, playhead, and playback state.

The reducer state contains serializable values only:

```text
context
  document_epoch, slot, target
tool
playhead
  index, playing, session_id
media
  catalog_id, source metadata, requested_transform, accepted_transform,
  effects, preview_session_id
preview
  status, request_epoch, accepted_epoch, context_key, board_frame_set,
  timeline, error
effect_draft
  specification, board_frame_set, demonstrative_frame, source_frame_index
```

Timers, DOM nodes, object URLs, AbortControllers, decoded frames, and device
handles stay outside reducer state. `app.js` executes reducer intents and sends
their results back as events.

Required events include:

- `DOCUMENT_OPENED`, `DOCUMENT_CLOSED`, `DESTINATION_CHANGED`;
- `TOOL_SELECTED`, `MEDIA_OPENED`, `MEDIA_CANCELLED`;
- `TRANSFORM_REQUESTED`, `EFFECT_REQUESTED`;
- `FRAME_RENDER_STARTED`, `FRAME_RENDER_ACCEPTED`, `FRAME_RENDER_FAILED`;
- `SEQUENCE_RENDER_STARTED`, `SEQUENCE_RENDER_ACCEPTED`,
  `SEQUENCE_RENDER_FAILED`;
- `PLAY_REQUESTED`, `SOURCE_FRAME_READY`, `PLAYBACK_TICK`, `PAUSE_REQUESTED`;
- `PLAYHEAD_SCRUBBED`, `APPLY_REQUESTED`, `APPLY_COMPLETED`; and
- `WORKSPACE_ERROR_DISMISSED`.

Every asynchronous acceptance event includes context key and request epoch.
The reducer ignores a response unless both match the current request. Any
context-changing event returns a `cancel-playback` intent before a render
intent. Tests exercise transitions directly without parsing `app.js` text.

Gradually replace the editor globals in `app.js`—`ledSlot`, `ledTarget`,
`ledFrame`, `playing`, `playTimer`, `studioTool`, `sourcePreviewMode`,
`mediaComposition`, `localAnimationDraft`, and related transform/effect
fields—with reducer selectors and intents. Do not keep two writable authorities
after the migration slice completes.

## Exact media preview architecture

### Prepared media session

Refactor beneath the existing `MediaRenderCoordinator` API so full renders and
selected-frame renders share one prepared representation rather than duplicate
mapping algorithms.

`media_composition.py` owns a bounded `PreparedMediaSession` containing:

- verified catalog ID, asset hash, and decoded immutable RGBA frames;
- exact source sizes and normalized durations;
- destination model, targets, layouts, maps, copies, and frame ceiling;
- canonical transform and validated effects; and
- a `PreviewTimeline` mapping every output frame to source frame, duration,
  resolved Move & zoom transform, and effect phase.

`device_mapping.py` exposes the existing timeline selection as a tested pure
helper and factors one output-frame mapping primitive beneath
`compose_media_frames_to_led_tracks()` and
`compose_media_transform_sequence_to_led_tracks()`. The existing public
functions keep their behavior and result shape. Full sequence render loops the
same primitive used by selected-frame render.

Factor color-effect evaluation so `render_color_effect()` and selected-frame
evaluation call one per-frame implementation. Browser and Python effect parity
remains guarded, but media Board output is always the Python result.

The full render response retains the existing `mapped_result` object and adds
presentation metadata beside it:

```text
preview_session_id
preview_timeline
source_preview descriptor
```

Do not add display-only fields to persisted device tracks. Saved lighting and
Apply continue to consume `mapped_result` unchanged.

### Bounded cache and source-frame projection

The loopback server keeps at most two decoded preview sessions in an LRU owned
by the current Library catalog identity. Each entry remains subject to the
existing media byte, dimension, frame, duration, and aggregate decoded-pixel
ceilings. Total retained decoded pixels may not exceed twice the existing
single-media ceiling. Entries expire after bounded inactivity and are evicted
on source removal, asset hash change, Library-root change, or server shutdown.

Session IDs are cryptographically random opaque values. A session is usable
only through authenticated loopback routes and remains bound to its verified
catalog item and asset hash. Responses contain no filesystem path.

Add strict routes:

- `POST /api/library/items/<catalog-id>/preview-session` prepares verified
  source metadata and returns an opaque session;
- `POST /api/library/items/<catalog-id>/render-frame` accepts exactly session,
  destination, requested transform/effects, output frame, and epoch, then
  returns the canonical transform, timeline entry, and exact per-target LED
  arrays for that frame;
- the existing `POST .../render` accepts an optional matching session and
  returns the full canonical sequence through the same prepared primitives;
  and
- `GET /api/library/items/<catalog-id>/source-frame` accepts an exact session
  and decoded source-frame index and returns a static PNG projection of that
  actual frame.

The source-frame projection is bounded to the visible-preview pixel ceiling,
preserves the complete decoded frame and aspect ratio, and is explicitly
display-only. It does not apply the source transform, LED sampling, target map,
color effect, or firmware timing. Current and next source projections are
prefetched; older encoded projections use a bounded byte LRU.

The current epoch supersession rule expands from catalog-only to preview
session plus workspace context so two destinations cannot cancel or accept one
another's work. Superseded selected-frame work and sequence work return the
existing conflict classification without user-facing error noise.

### Live-render scheduling

On import or `Open in Studio`, prepare a session and render frame zero
automatically. Transform/effect inputs coalesce to one in-flight selected-frame
request and one latest pending request. Pointer-up, keyboard steps, presets,
and scrubber changes request immediately; continuous pointer/wheel input may be
frame-rate coalesced but may not queue unbounded work.

After the latest selected frame is accepted, start or restart a short bounded
idle debounce for full sequence render. Apply stays disabled until that full
sequence response matches the exact current context, canonical transform,
effects, and epoch. Playback uses only the accepted full `BoardFrameSet`.

Selected-frame and full-render equality tests are mandatory. For every
supported family/target fixture and representative transform/effect, the frame
route's LED array must equal the corresponding array in the full
`mapped_result` byte for byte.

## Workspace layout and interaction design

### Stable shell

Keep compact slot and target controls above the workspace. The primary stage
uses these regions:

```text
Media active, wide:
  [ Source frame ] [ Physical LED output ] [ Tool inspector ]
  [ shared horizontal timeline + playback across Source and Board ]

Media active, compact:
  [ Source frame ] [ Physical LED output ]
  [ shared horizontal timeline ]
  [ compact tool inspector ]

Paint/effect without media:
  [ Physical LED output             ] [ Tool inspector ]
  [ shared horizontal timeline      ]
```

At 1000×680 and 1280×800, Source and Board remain simultaneously visible for
media, the timeline is horizontal, primary Apply/Cancel actions remain in the
first viewport, and there is no page-level horizontal overflow. At 1600×1000,
the layout may add breathing room but not move actions or change terminology.

The Source card is labelled `Source`. The Board card uses the friendly target
label, for example `Per-key` or `Head matrix`, and a short `What the keyboard
will show` subtitle. Technical dimensions, mapped/stored counts, frame timing,
and sampling remain under Technical details.

### Source pane

The Source pane contains the actual static source-frame projection inside an
overflow-clipped viewport. Existing exact raster-box math positions it. Pan,
wheel/trackpad, keyboard, sliders, Fit, Fill, Center, Reset, aspect lock, and
Stretch all use `lighting_composer.js` canonical geometry.

There is no Source/LED-result toggle. The old source plane, source overlay
inside `#led-canvas`, `sourcePreviewMode`, and the misleading blended CSS are
deleted only after the new panes pass exact guards.

Center means native source scale relative to the destination, clamped before
validation to the version-1 `0.01..32` scale range. Every preset is passed
through browser and backend canonicalization and is guaranteed valid for the
current source/destination vector.

### Board pane

Use the existing physical CyberBoard, AFA, Relic, and validated Neon layout
projections. Rectangular display/head targets retain exact row-major geometry.
The board component receives only a `BoardFrameSet`, target, and playhead.

Paint buttons remain interactive only for document/manual Paint frames. Media,
Effect, procedural, and Library previews are read-only board projections until
Apply. Their status and action area says where Apply will land and that the
keyboard is unchanged.

### Timeline and playback

Replace the vertical frame list with a horizontal, keyboard-operable strip
beneath the stage. It shows source thumbnails when media is active and canonical
LED miniatures otherwise, but selection always means one shared output
timeline entry. Provide Play/Pause, previous/next, scrubber, frame position,
and loop status in one place.

Timer cadence uses the accepted canonical duration. Do not close over frame
arrays or DOM elements. A timer dispatches `PLAYBACK_TICK(session_id,
context_key)`; selectors read the current `BoardFrameSet` after the reducer
accepts the tick.

Tool, target, slot, route, document, or preview revision changes cancel the
timer and detach it before rerender. The exact rejected Neon transition—Play
Per-key, select Head matrix—must stop the Per-key session, show the saved Head
matrix frame at its own playhead, and leave every Head LED equal to the Head
track.

### Media selection

Do not reintroduce a blanket `accept` attribute inside native WKWebView.
Instead, add a pathless desktop-bridge media chooser backed by PyWebView's
native file dialog with only GIF, PNG, and BMP filters. Follow the existing
server-owned `desktop_bridge` pattern: an authenticated no-body native import
route invokes the dialog, receives the selected path only inside Python, checks
that it is one bounded regular file, reads it once, and passes bytes through the
same media importer. JavaScript receives only the sanitized catalog detail;
neither a path nor base64 file payload crosses into the webview. The backend
still sniffs and decoder-verifies the format.

The ordinary-browser development fallback uses
`accept=".gif,.png,.bmp,image/gif,image/png,image/bmp"` plus immediate
client-side extension/type feedback. Backend validation remains authoritative
in both paths. Unsupported formats are not shown as normal native choices, and
any bypassed/mislabeled file produces one plain-language inline error.

## Resolved Gate LSR-G1 — Self-contained dynamic layout metadata

Neon Per-key geometry comes from a validated Vial definition and is not present
in the vendor configuration JSON. Offline editing therefore needs durable
layout evidence.

`Save JSON` includes one exact namespaced top-level `_am_configurator` object
with a versioned, server-validated dynamic layout projection and canonical
signature. This is the normal portable Save/Open representation and does not
require a sidecar, second file, or local cache to travel with the profile.

App-owned layout metadata is exact-field, versioned, bounded, pathless, contains
no device address, serial, credential, or other machine identity, and is
validated by rebuilding `device_descriptor()` and comparing the canonical
signature. Unknown or malformed metadata never becomes layout evidence. The
protocol encoder extracts only canonical device sections so the object never
reaches transport; app-native files and local snapshots may retain it.

Third-party parser compatibility is not a requirement. Do not add a
vendor-clean export, sidecar workflow, or compatibility mode. AM Master support
exists only at the validated import boundary defined above.

The gate and complete plan are approved.

## Implementation slices

Each slice receives one independent commit after focused red/green proof and
the relevant automated verification pass. Run the complete repository
verification entry point before each code commit. A new behavioral test must
be proven non-vacuous by temporarily reverting its production behavior as
required by `AGENTS.md`. Push verified commits normally to canonical `origin`.

External review follows `.agents/repo-guidance.md` under **Review Economy**. It
is not a per-slice gate: use it only on explicit owner request or when a concrete
material risk remains that local guards and CI cannot settle. An already-launched
review still uses its first substantive result as returned and is never retried,
discarded, replaced, or resubmitted without explicit owner approval.

### Slice LSR-1 — Workspace reducer and board-frame contract

Completed 2026-08-02. Implementation commit
`1ee73a81182c8f401b1942776d3df7c005541f33` passed the full gate and was pushed.
Its single required `fable-review` used `claude-opus-5` at `high` over exact
parent/head and returned one admitted HIGH finding, `cl-10`. Repair commit
`95795845b6eeabd1c572b82244fef26a975183dd` canonicalizes backend-valid RGB
spelling, passed the non-vacuous red/green proof and full 677-Python/144-browser
gate, and was pushed. Its T2 per-finding verification used `claude-opus-5` at
`xhigh` over the exact repair range and returned `accepted` with
`guard_confirmed=true` and `capability_ok=true`. LSR-1 is closed.

Files:

- new `am_configurator/web/lighting_workspace.js`;
- `am_configurator/web/index.html` and static route/packaging maps;
- `am_configurator/web/app.js` adapter wiring;
- new `tests/web/lighting_workspace.test.js`;
- affected shell and packaging tests.

Implement the pure state/events/intents contract, context keys, accepted versus
requested revisions, `BoardFrameSet` validation/projection, stale-response
rejection, and error deduplication. Adapt the existing UI to selectors without
changing the visible layout yet. Move slot, target, frame, and playback
ownership first; remove the corresponding legacy writable globals once the
adapter is live.

Required proof:

- stale context/epoch responses are no-ops;
- every context change emits playback cancellation before render;
- invalid target/color/frame shapes cannot reach Board projection;
- identical reducer errors coalesce and internal labels map to friendly text;
- the existing document, local-effect, media, and procedural sources can each
  construct a valid `BoardFrameSet`; and
- no dependency or lockfile changes.

Commit:

```text
refactor: centralize lighting workspace state
```

### Slice LSR-2 — Exact selected-frame media renderer

Completed 2026-08-02. Implementation commit
`65c9fbfc22c2b24c3b868218512b00039756e6e1` passed the complete
685-Python/144-browser gate, selected/full parity and invalidation mutation
proofs, and was pushed. Its single required `fable-review` used
`claude-opus-5` at `high` over exact parent/head and returned two admitted
findings. `cl-11` repair `9015d422d97d3be0ba9aa04a0ebeeec81c934335`
keeps sessionless renders outside the explicit preview LRU; `cl-12` repair
`3865c1008a9798f4d882b2f81c445e7fc2e3261f` restores decode-time
supersession. Both repairs are non-vacuously mutation-proven, pushed, pass the
complete 688-Python/144-browser gate, and each received one exact-range
`claude-opus-5` high/standard `accepted` verdict with `guard_confirmed=true`
and `capability_ok=true`. LSR-2 is closed; LSR-3 is next.

Files:

- `am_configurator/media_composition.py`;
- `am_configurator/device_mapping.py`;
- `am_configurator/server.py`;
- `tests/test_media.py`, `tests/test_device_mapping.py`, and
  `tests/test_app.py`;
- `tests/fixtures/media_geometry_vectors.json` where additional vectors are
  required.

Implement prepared sessions, bounded decode/source-projection caches,
`PreviewTimeline`, shared per-frame/full-sequence primitives, strict routes,
session-scoped epochs, and static source-frame PNG projection. Preserve the
existing full `mapped_result` shape and every default/legacy renderer result.
Do not change Apply, Library mutation, Effects UI, or hardware paths in this
slice.

Required proof:

- selected-frame arrays equal full sequence arrays byte for byte for GIF, PNG,
  BMP, transforms, Move & zoom, and color effects across all family targets;
- source projection contains the actual complete decoded frame and is never an
  LED raster or transformed device output;
- caches enforce item/hash binding, authentication, LRU/expiry/pixel bounds,
  Library-root invalidation, and pathless responses;
- superseded work publishes nothing current;
- malformed sessions, frame indices, destinations, and unknown body/query
  fields fail before unbounded work; and
- the old media and procedural mapping suites remain unchanged and green.

Commit:

```text
feat: render exact live media frames
```

### Slice LSR-3 — Destination-bound playback isolation

Completed 2026-08-02. Implementation commit
`92949d92ca6751073ce47fa2b5182c01ed247009` is pushed, mutation-proven, and
passes the complete 690-Python/149-browser/compile/syntax/build gate. The
isolated native WebView2 audit passed at 1000×680 and 1280×800 across
GIF/PNG/BMP, including CyberBoard switch-to-display and Neon
Per-key-to-Head transitions, with exact destination colors, unchanged document
data, and no console or layout finding. Exact-head CI run `30735969449` and
Desktop installers run `30735969440` passed on every platform, including
metadata and provenance. The one required `fable-review` used
`claude-opus-5` at `high` over exact range
`b5d46d9402df4d47429b17aaf50326d1307024d8..92949d92ca6751073ce47fa2b5182c01ed247009`;
its first substantive result returned `clean`, `capability_ok=true`, exact
pins, no findings, exit 0, and no stderr. It was not retried, re-emitted,
replaced, reformatted, or resubmitted. LSR-3 is closed; LSR-4 is next.

Files:

- `am_configurator/web/lighting_workspace.js`;
- `am_configurator/web/app.js`;
- focused web tests and `tests/test_media_framing_audit.py`.

Replace the global playback closure/timer with reducer sessions. Make document,
slot, target, tool, media, Library, and route transitions cancel playback and
render through current selectors. Preserve independent destination playheads.

Required proof:

- the rejected Neon Per-key → Head matrix transition cannot paint Per-key
  colors into Head DOM and displays the exact saved Head track;
- CyberBoard switches → 40×5 display and Relic keys → edge transitions are
  equally isolated;
- a stale timer, source-frame load, selected-frame response, or full render is
  inert after a context change;
- starting/stopping repeatedly leaves one timer and no orphan listeners; and
- Apply and document arrays are unchanged by playback.

Commit:

```text
fix: isolate lighting playback by destination
```

### Slice LSR-4 — Human-first shell and synchronized panes

Completed 2026-08-02. Implementation commit
`78bcdcf47ff3a5dcacce555ad31ac14bef95993b` is pushed and passes the complete
691-Python/151-browser/compile/syntax/build gate plus the isolated two-viewport
native GIF/PNG/BMP audit. Its one required `fable-review` used
`claude-opus-5` at `high` over exact parent/head and returned one admitted HIGH
finding, `cl-13`. Repair commit
`abc6826b346420de257d1679879ef84e483c3a81` restores bounded recovery after
preview-session expiry or eviction, is pushed, non-vacuously mutation-proven,
and passes the complete 691-Python/153-browser/compile/syntax/build gate plus
deliberate six-case native eviction/recovery. Its T2 per-finding verification used
`claude-opus-5` at `xhigh` over the exact repair range and returned `accepted`
with `guard_confirmed=true` and `capability_ok=true`; the first substantive
result was used as returned without retry or resubmission. Exact repair-head CI
run `30738460515` and Desktop installers run `30738460507` passed all nine
jobs. LSR-4 is closed; LSR-5 is next.

Files:

- `am_configurator/web/index.html`;
- `am_configurator/web/style.css`;
- `am_configurator/web/app.js`;
- `am_configurator/web/lighting_workspace.js`;
- `tests/web/lighting_shell.test.js`, `tests/web/design_tokens.test.js`, and
  focused DOM tests.

Build the stable shell, separate Source and Board components, horizontal
timeline, shared playback controls, task-led labels, persistent inline status,
and responsive layouts. Keep existing tools functional through the adapter.
Delete the source/result toggle and blended source plane only after the new
structure passes.

Required proof:

- media always shows Source and Board together;
- Board contains no image-bearing element and accepts only canonical arrays;
- Source contains the actual selected source-frame projection;
- both panes, timeline, Apply, and Cancel are visible without page overflow at
  1000×680 and 1280×800, with no regression at 1600×1000;
- physical CyberBoard, AFA, Relic, Neon axial, rectangular display, and Head
  layouts remain exact;
- keyboard navigation, visible focus, reduced motion, readable disabled state,
  and live-region behavior pass; and
- Paint still works without media, AI, Library setup, or hardware.

Commit:

```text
feat: rebuild the lighting workspace around led output
```

### Slice LSR-5 — Live imported-media workflow

Completed 2026-08-02. Implementation commit
`7052212445c269752a094217b1ab4813741b2ef7` and admitted review repairs
`1a8632b6b1b2dc4926f848235d10dadd4066e6e5` (`cl-14`),
`027f2eb18cedd88974ae5a965de2176c0690f801` (`cl-15`), and
`1b09a2a7d6da087187efbf125c9480cb457e7f46` (`cl-16`) are pushed. The one
generation review and all three per-finding verifications used job
`fable-review`, explicit `claude-opus-5` at `high`, exact pins, and each first
substantive result once; every finding returned `accepted` with guard and
capability confirmed. The final head passes 694 Python and 161 browser tests,
compile/syntax/build gates, and deliberate two-viewport GIF/PNG/BMP native
selected-frame, ownership, session-recovery, Source/Board, Apply/Undo, Library,
and layout proof. Exact final CI run `30743864174` and Desktop installers run
`30743864148` passed all jobs. LSR-5 is closed; LSR-6 is next.

Files:

- `am_configurator/desktop.py` and bridge tests;
- `am_configurator/server.py` and native/import route tests;
- `am_configurator/web/app.js`;
- `am_configurator/web/lighting_workspace.js`;
- `am_configurator/web/lighting_composer.js`;
- `am_configurator/web/style.css`;
- media, server, browser, and native-audit tests.

Wire native GIF/PNG/BMP selection, browser fallback, automatic preview-session
creation, requested/accepted transforms, exact selected-frame requests,
coalescing, source projection prefetch, full-render debounce, synchronized
scrubbing/playback, and Apply readiness. Retain bank-before-edit, Cancel, Undo,
and Save to Library boundaries.

Required proof:

- the native picker normally shows only GIF/PNG/BMP while all three remain
  selectable on Windows WebView2, macOS WKWebView, and Linux WebKitGTK;
- bypassed/mislabeled/unsupported input creates one inline error and no item;
- pan, zoom, keyboard, wheel, sliders, sampling, stretch, Fit, Fill, Center,
  Reset, and Move & zoom update requested state immediately and accept one
  exact current Board revision;
- Center and every preset remain within `0.01..32` for extreme vectors;
- no duplicate toast or raw schema field reaches the user;
- source and board playback hold together when a source projection is late;
- Apply is disabled for stale/pending sequence output and makes one Undo
  checkpoint for the exact accepted arrays; and
- Library source ownership and immutable bytes remain unchanged.

Commit:

```text
feat: make media framing live and truthful
```

### Slice LSR-6 — Immediate Effects workflow

Completed 2026-08-02. Implementation commit
`246da643e95dbc2fc390507264e228cc75051292` and admitted review repair
`07a1cbe8cf2c7eea56ea4aa27b43dada8a861c1a` (`cl-17`) are pushed and
non-vacuously mutation-proven. The final complete gate passes 694 Python tests
with 5 skips, 171 browser tests, compile/syntax checks, and both package builds;
exact repair-head CI run `30746538330` and Desktop installers run `30746538320`
passed all nine jobs. The generation review and `cl-17` per-finding verification
used job `fable-review`, explicit `claude-opus-5` at `high`, exact pins, and
each first substantive result once. The repair verification independently
reproduced the stale-thumbnail failure with only the painter reverted, restored
both focused and complete browser suites green, and returned `accepted` with
guard and capability confirmed. LSR-6 is closed; LSR-7 is next.

Files:

- `am_configurator/web/lighting_workspace.js`;
- `am_configurator/web/lighting_composer.js`;
- `am_configurator/web/app.js` and `style.css`;
- effect, shell, server-parity, and accessibility tests.

Replace parameter-only Effects controls and separate Preview with live draft
cards/presets. A deliberate effect selection creates a draft immediately and
starts destination-bound playback unless reduced motion is active. Parameter
changes regenerate or request the exact draft and select an effect-specific
demonstrative changed frame while pending.

Manual/document effects continue to use the deterministic browser reducer and
the exact arrays Apply will clone. Media effects use the prepared backend
session and exact `mapped_result`. Move & zoom remains available only for an
imported still and keeps Source/Board visible.

Required proof:

- Pulse, Hue cycle, Sweep, and Shimmer visibly differ from their source without
  a Preview click;
- changing any normal control changes the Board or clearly explains why it
  cannot;
- parameter changes stay pinned to the originating document frame while the
  effect playhead advances;
- reduced-motion mode never autoplays and selects a changed representative
  frame;
- seeded Shimmer stays repeatable, target bounds/frame ceilings remain exact,
  and dependent tracks are preserved;
- target/tool changes cancel the effect loop and cannot leak frames; and
- Apply/Cancel each produce exactly one documented mutation outcome.

Commit:

```text
feat: preview lighting effects as they change
```

### Slice LSR-7 — Offline layout evidence and write-time verification

The isolated `cl-18` repair
`8e059292411b85a3387d348c8a4ee36ef8137f25` makes a newly validated live
layout atomically replace unreadable private persistence and retains only
strictly revalidated bounded history. Its focused guards fail against both
reviewed failure modes and pass after the repair; the complete 707-Python/
173-browser/compile/syntax/build gate, exact-head CI run `30749340460`, and
Desktop installers run `30749340465` pass. Its one explicit
`claude-opus-5`/`high` per-finding verdict returned accepted with guard and
capability confirmed. `cl-18` is closed; `cl-19` is next.

The isolated `cl-19` repair
`9ad77c2f6070982250b1a9cd6fb2d555e90daaa4` keeps a validated Neon key layout
and its deep descriptor/signature paired across shallow device scans;
contradictory signatures and replacement identities inherit no stale geometry.
Both focused guards fail against their reviewed behaviors and pass after
restoration. The authoritative stable 707-Python/175-browser/compile/syntax/
build gate, exact-head CI run `30750225695`, and Desktop installers run
`30750225702` pass. Its one explicit `claude-opus-5`/`high` per-finding verdict
returned accepted with guard and capability confirmed. `cl-19` is closed;
`cl-20` is next.

The isolated `cl-20` repair
`1d6f101f953d190afeaff72be3b25df34ca140f9` makes valid embedded
dynamic-layout evidence own portable export and Library save. A matching
connected layout retains that evidence and a conflicting canonical signature
returns one clear error before remembered-layout or Library mutation. Its
helper, export, and Library guards all fail against the reviewed overwrite
behavior and pass after restoration; the complete
710-Python/175-browser/compile/syntax/build gate, exact-head CI run
`30751005214`, and Desktop installers run `30751005186` pass. Its one explicit
`claude-opus-5`/`high` per-finding verdict returned accepted with guard and
capability confirmed. `cl-20` and LSR-7 are closed; LSR-8 is next.

Under the resolved Gate LSR-G1 contract, files are expected to include:

- profile load/save helpers in `am_configurator/web/app.js`;
- strict metadata validation in `am_configurator/server.py` or a focused
  profile module;
- `am_configurator/device_mapping.py` signature helpers;
- app-local remembered-layout storage with private bounded persistence;
- write preflight and affected profile/Neon/store tests.

Implement the exact approved portable representation, canonical dynamic-layout
schema/signature, evidence resolution, remembered exact layouts, scoped legacy
fallback, and write-time comparison. Make every protocol encoder extract only
canonical device fields; retain validated app metadata in app-native files and
local snapshots where it preserves offline layout evidence.

Required proof:

- a self-contained saved Neon profile opens Per-key and Head offline on a fresh
  installation under the approved representation;
- malformed, oversized, unknown-field, wrong-product, and wrong-signature
  metadata never becomes layout evidence;
- a legacy layout-less Neon JSON still opens and exposes every surface not
  dependent on physical geometry;
- connecting an exact layout enables verification without changing document
  lighting;
- a different dynamic layout blocks write before confirmation and transmits
  zero bytes;
- fixed-family Save/Open output and layouts do not regress; and
- no serial, path, credential, or device address enters a portable profile.

Commit:

```text
feat: keep dynamic lighting layouts portable
```

### Slice LSR-8 — Import AM Master profiles and lighting

Implementation is landed in the commit containing this status record on
2026-08-02. Its strict app-native/full-profile/lighting-only classifier,
offline imported-lighting review, exact Apply gate, explicit Library save, and
remembered-layout path are mutation-proven. The complete local gate passes 720
Python tests with 5 skips, 178 browser tests, compile/syntax and source/wheel
builds, plus the Windows native-tree/installer/frozen-smoke chain. A read-only
acceptance pass classified all seven machine-local examples without recording
their filenames or payload arrays. Implementation commit `845f716` is pushed;
exact-head CI run `30754260384` and Desktop installers run `30754260409` pass.
The single required `fable-review` used explicit `claude-opus-5` at `high` over
the exact implementation range once and admitted `cl-21` (applied imported
frames remain frozen) and `cl-22` (a source-text guard pins the related dead
clone block). LSR-8 remains open until both findings are independently closed.

The isolated `cl-21` repair
`864bd28636be781a84d1dfc259a9e0622890d111` copies canonical mapped color arrays at the live
document boundary, so applied Head and Per-key frames remain editable while the
transient review report stays recursively frozen. Its executable guard runs the
actual production conversion, performs indexed paint and frame fill, and
confirms the source report is unchanged; reverting only the copy fails that
guard and restoring it passes. The complete 720-Python/179-browser/compile/
syntax/build gate is green. Exact-head CI run `30755504354` and Desktop
installers run `30755504317` pass. Its one T2-routed `fable-review` used
explicit `claude-opus-5` at `xhigh`, returned accepted, and independently
confirmed the guard and complete gate. `cl-21` is closed; `cl-22` remains.
Under the owner's 2026-08-02 review-economy ruling, the minor `cl-22` cleanup
will be locally guard-proven and CI-qualified without external model review.

The isolated `cl-22` repair removes the unused candidate clone/apply/lightness
block from imported-lighting Apply and reverses the brittle positive source
assertion so reintroducing only those three lines makes exactly one focused
test fail. Restoration passes 42 focused shell tests and the complete
720-Python/179-browser/compile/syntax/build gate with 5 Python skips. Repair
commit `3b2d26fb48094bf8b804a0449cb968edc2b4b7d9` is pushed; exact-head CI run
`30756144641` and Desktop installers run `30756144701` pass every job. No
external per-finding review was run under the owner-approved review-economy
rule. `cl-22` and LSR-8 are closed; LSR-9 is next.

Files:

- new focused `am_configurator/profile_import.py`;
- `am_configurator/server.py`;
- `am_configurator/web/app.js` and `lighting_workspace.js`;
- `am_configurator/library.py` only where explicit Save to Library reuses the
  canonical composition contract;
- new minimized synthetic fixtures under `tests/fixtures/`;
- new focused profile-import tests plus affected app, Library, web, desktop,
  and packaging tests.

Add a bounded authenticated raw-JSON import endpoint that accepts a sanitized
display name separately from bytes, rejects duplicate object keys, classifies
the three approved forms, runs the named adapter, then canonical validation.
Route global Open, Merge inputs, and Library profile import through the same
classifier. Global Open remains non-banking; explicit Library import/save owns
persistence.

Implement the exact AM Master full-profile disabled-placeholder normalization
and AM 80 lighting-only conversion defined above. Return one immutable import
report with source format and normalizations. A full profile proceeds through
the normal document-open compatibility flow. A lighting-only file produces a
transient composition review and exact `BoardFrameSet`; it never fabricates
key layers, device identity evidence, or write eligibility.

Required proof:

- minimized versions of all four confirmed AFA full-profile shapes normalize
  only disabled zero-frame placeholders and pass unchanged canonical
  validation/writer planning afterward;
- temporarily leaving one recognized placeholder unnormalized makes the
  focused test fail for the predicted frame-count/color-count reason;
- an enabled malformed track still fails and no generic validator rule is
  weakened;
- minimized 1-, 50-, and 75-frame AM 80 lighting fixtures map `frames` to 230
  Head colors and `frames_axial` to 89 Per-key colors with exact order, timing,
  and paired frame count;
- brightness `0..100` and `255` normalize as specified, while `101..254`
  rejects with one friendly explanation;
- filename changes cannot affect classification, and unknown fields, duplicate
  keys, invalid colors, unequal tracks, oversize input, excess frames, wrong
  pixel counts, and malformed descriptions fail before document/Library
  mutation;
- a lighting-only file can preview/play and be explicitly saved to Library
  without an open document, but Apply remains disabled until an exact AM 80
  document/custom slot exists;
- full-profile Open and Merge remain document-only, preserve every supported
  section, and create no Library item implicitly;
- app-native `_am_configurator` profiles still round-trip exactly, while no
  export path attempts to reproduce an AM Master shape; and
- no original owner-supplied payload is committed, logged, or included in a
  package.

Commit:

```text
feat: import angry miao lighting json
```

### Slice LSR-9 — Preserve Library, AI, Apply, and Undo integration

Implementation is landed in the commit containing this status record on
2026-08-02. Every preview-backed Apply now retrieves the exact accepted
`BoardFrameSet` and passes it through one common copying writer; Relic dependent
tracks are derived before Board acceptance, so Apply cannot invent or retime an
unseen track. Saved Library lighting and generated results open a separate
read-only physical Board preview before one document-only Apply, and procedural
review now points to that same Board instead of displaying the obsolete raster
preview asset. Cancel, navigation, and preview do not create a Library item or
an Undo checkpoint.

The focused guard set first failed 12 of 101 tests against the pre-change paths
and now passes 102 of 102. Additional mutations independently proved the exact
preview-object identity check and the full-render device-model capture. The
complete local gate passes 720 Python tests with 5 skips, 185 browser tests,
compile and syntax checks, and both package builds. The Windows native tree
audit, installer build, and frozen smoke pass. The existing native workflow
audit is intentionally an LSR-10 update surface: a source run reached its saved
lighting Library workflow and then failed at the old direct-Apply selector,
which LSR-9 replaced with Preview on board; that run is not claimed as accepted
native evidence. No dependency, FFmpeg/libav path, provider request, credential
use, or hardware write was introduced. No external review was run under the
owner-approved review-economy rule. Exact-head CI and Desktop installer
qualification remain pending, so LSR-9 remains open.

Files:

- `am_configurator/web/app.js`;
- `am_configurator/web/library_state.js` and focused tests only if its public
  projection needs adaptation;
- Library/server tests and lighting workflow tests.

Route manual, media, local-effect, procedural, saved-lighting, and Library
Apply previews through `BoardFrameSet`. Remove remaining duplicate legacy
editor state and dead markup only after parity tests pass. Keep AI generation
procedural-only and do not change providers, readiness, requests, or recipes.

Required proof:

- each source type shows exact physical Board output and applies only to the
  selected open-document destination;
- Preview/Apply arrays and duration are byte-equivalent, including paired or
  derived tracks;
- Undo restores the complete prior slot once;
- Save to Library remains distinct, saved composition bytes equal the accepted
  render, and Cancel/navigation create no item beyond the already banked media
  source;
- AI never enters the media session or receives source bytes;
- AI-off mode retains complete manual/media/effect/Library behavior; and
- no Studio action reaches hardware or a live provider implicitly.

Commit:

```text
refactor: unify lighting previews on canonical frames
```

### Slice LSR-10 — Native audit and owner acceptance

Files:

- extend `am_configurator/media_framing_audit.py` or add one focused pathless
  Lighting audit module;
- `am_configurator/desktop.py` explicit CLI dispatch;
- native, desktop, packaging, and report-schema tests;
- this plan, `.agents/state.md`, and the release plan when evidence lands.

Extend the current isolated, no-hardware native audit rather than introducing a
browser-automation dependency. Cover GIF/PNG/BMP, two-pane framing, exact Board
pixels, source/board playback, target-switch isolation, live Effects, Apply,
Undo, Library, app-native profile round-trip, both AM Master import dialects,
portable offline Neon layout, missing-layout fallback, Cancel, focus, keyboard
operation, reduced motion, and error hygiene.

Run source and frozen audits at 1000×680 and 1280×800 on:

1. Windows x64 WebView2 for primary iteration;
2. Linux x86-64 WebKitGTK as the highest-priority distribution gap; and
3. macOS arm64 WKWebView as a regression check.

Build only through `python build.py --skip-sync` after the local environment is
prepared, then run frozen `--smoke-test` and the explicit audit mode. Preserve
the current pathless fixtures, isolated data/Library roots, offline device
discovery, in-memory credentials, no provider variables, exact cleanup, and
sanitized bounded report.

Before packaging qualification, run the finished importer read-only against
all seven owner-supplied machine-local examples. Record only source-format,
normalization, validation, and resulting count assertions; never copy filenames
or payload arrays into repository artifacts. Synthetic minimized fixtures own
the repeatable CI guard.

The owner performs one final visible acceptance pass on the current Windows
build. That pass must confirm that source framing, physical LED reduction,
Effects, target changes, offline profile behavior, and action boundaries make
sense without instruction. It authorizes no hardware write.

Required completion evidence:

- all seven supplied AM Master examples pass their intended full-profile or
  lighting-only import path with no unreported normalization;
- full repository verification passes;
- exact-head CI and all three native Desktop artifact jobs pass;
- source and frozen native audits pass on all three platforms with no console,
  focus, layout, mapping, provider, credential, or cleanup finding;
- recursive native/dependency audits retain the FFmpeg prohibition;
- no new direct or transitive dependency appears; and
- owner visual acceptance is recorded before any new R65-2 candidate freeze.

Commit:

```text
test: qualify the redesigned lighting studio
```

## Verification strategy

The authoritative full command set is `.agents/repo-guidance.md` under
**Verification** and is not duplicated here. Focused tests may run first, but
they never replace the full gate for a code slice.

Cross-cutting guard matrix:

| Contract | Required automated proof |
|---|---|
| Board truth | Every displayed LED equals the accepted source array by target/frame/index; no image-bearing descendant exists in Board. |
| Selected/full parity | Selected-frame response equals the same full `mapped_result` frame across all formats, targets, transforms, and effects. |
| Shared playhead | Source timeline entry, Board frame, scrubber, label, and duration advance in one reducer event. |
| Stale isolation | Old timer/session/render/source load cannot alter a new document, slot, target, tool, or revision. |
| Physical layouts | CyberBoard, AFA, Relic, Neon axial, CyberBoard display, and Neon Head use their canonical maps and dimensions. |
| Media selection | Native and fallback flows admit GIF/PNG/BMP and reject unsupported input once, before publication. |
| Offline Neon | Exact portable evidence edits offline; missing evidence scopes the limitation; mismatched live signature blocks write pre-confirmation. |
| AM Master import | Full-profile disabled placeholders normalize only through the named adapter; AM 80 lighting maps exact Head/Per-key arrays; malformed enabled data remains rejected. |
| Effects | Each normal control produces immediate visible draft output; reduced motion remains paused and meaningful. |
| Presets/errors | Every preset validates at extremes; one friendly error per revision; no raw field/path/exception. |
| Mutation equality | Apply, saved composition, open document, and writer input retain exact accepted arrays/duration and dependent-track semantics. |
| Responsive/accessibility | 1000×680, 1280×800, 1600×1000; keyboard-only, focus, contrast, reduced motion, no page overflow. |
| Safety/dependencies | No implicit hardware/provider action, no new dependency, and no FFmpeg/libav path or artifact. |

For every new behavioral guard, temporarily revert only the production behavior
it names, observe the predicted failure, restore it, and observe the pass. Large
structural absence guards—such as no image inside Board—must also fail against
the current pre-redesign markup before the slice is accepted.

## Failure policy

- If exact live selected-frame output cannot reuse the full canonical renderer,
  stop. Do not ship an approximate Board preview.
- If responsive exact frame rendering requires a new dependency, alternate
  media runtime, FFmpeg/libav, browser engine, or external service, stop and
  request an owner decision. None is expected.
- If source and Board cannot remain synchronized without dropping frames, hold
  both on the last accepted entry; never let either silently run ahead.
- If a dynamic layout lacks validated evidence, scope the missing surface and
  explain it; never invent or substitute a plausible grid.
- If a new AM Master export does not match either approved dialect, reject it
  with one useful explanation and capture only a minimized, non-sensitive
  structural case before expanding the adapter. Do not weaken canonical
  validation or guess a conversion.
- If a slice moves `main` after a future release candidate is frozen, reject
  that candidate and restart R65-2. Never patch candidate bytes or reuse earlier
  platform evidence.
- If native behavior differs materially across WebView2, WebKitGTK, and
  WKWebView, the redesign is incomplete even when browser unit tests pass.

## Completion criteria

This plan is complete only when:

- Gate LSR-G1 and complete plan approval are durably recorded;
- LSR-1 through LSR-10 and any admitted findings are independently committed,
  guard-proven, fully verified, and pushed;
- imported media always presents actual Source and exact physical Board output
  together under one transform and playhead;
- Board never contains or approximates the source image and uses the exact
  canonical arrays later consumed by Apply and Write;
- target/slot/tool/document changes cannot leak playback or stale work;
- GIF/PNG/BMP selection, framing, playback, and errors are task-led and
  truthful;
- Effects provide immediate obvious feedback without a Preview discovery step;
- profiles open offline, dynamic layout evidence is portable under the approved
  representation, and live verification occurs at write time;
- recognized AM Master full profiles and AM 80 lighting-only JSON import through
  strict named adapters, while app exports remain self-contained and app-native;
- Paint, Library, procedural AI, Apply, Undo, Save to Library, and write safety
  retain their existing successful behavior;
- full automation, exact-head CI, three native frozen audits, dependency/native
  absence checks, and owner visible acceptance pass; and
- no provider request, credential use, hardware write, tag, Release, macOS Open
  Anyway action, security-setting change, announcement, new dependency, or
  FFmpeg/libav path was introduced or performed.
