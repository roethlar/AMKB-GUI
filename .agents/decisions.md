# Repository Decisions

## 2026-07-25 — AM Neon 80 protocol sources and GPL relicensing

Status: approved by the owner on 2026-07-25, after the owner was shown the
licensing consequence and chose it explicitly.

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
