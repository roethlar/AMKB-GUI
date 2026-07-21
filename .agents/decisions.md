# Repository Decisions

## 2026-07-21 — Editor-first Lighting workspace

Status: approved by the owner on 2026-07-21.

- Lighting opens directly into the manual device workspace. AI generation is
  an optional secondary action contained in a dialog or drawer; it is not the
  default route, a landing page, or the product's visual emphasis. Library is
  a secondary view alongside the workspace.
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

Status: approved by the owner on 2026-07-20.

- Replace the narrow inline AI controls with a durable Concepts → Animate →
  Review & Apply workflow and a full Library. The 2026-07-21 editor-first
  decision supersedes this decision's original full-width, Create-first UI
  hierarchy; provider-call and price details still stay out of generation.
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
