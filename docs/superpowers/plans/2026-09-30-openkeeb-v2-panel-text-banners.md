# OpenKeeb v2 — panel text banners for NEON and Cyberboard

Status: **DRAFT — not approved.** D1 settled 2026-09-30: support both drawn
frames (lane A, both boards) and the Cyberboard firmware's built-in text
(lane B, Cyberboard only) — `.agents/decisions.md` "2026-09-30 — Cyberboard
text supports both drawn frames and built-in text". Pending: D2 (approve this
plan). No implementation, hardware write, push, or release is authorized by
this document. Written 2026-09-30 on `v2/openkeeb` at `1359a9b`.

Governing records: `.agents/decisions.md` "2026-08-14 — Text banner authoring
is in v2 scope; panel display is a capability" (scope, targets, capability
gating); `docs/superpowers/plans/2026-08-08-openkeeb-v2.md` capability list
item 4, `panel_display`; `docs/superpowers/plans/2026-08-13-am-led-effect-techniques.md`
Adopt 3 (clean-room rule; text effects are a text-composer concern);
`docs/superpowers/plans/2026-08-17-openkeeb-branding-overhaul.md` (language and
token contract); `.agents/repo-guidance.md` Device Safety.

## Objective

Let a user type a line of text and put it on the billboard panel of a
Cyberboard (`CB`, track `frames`, 40×5) or NEON 80 (`NEON`, track `head`,
46×5), written through the existing full-config write gate. Boards without a
panel never show the feature. Two lanes:

- **Lane A — drawn text (both boards).** OpenKeeb draws the text into
  panel-track frames: scrolling or static, with color and a small set of text
  effects, previewed exactly on the Board preview, applied to one custom
  slot's panel track, saved to the Library.
- **Lane B — built-in text (Cyberboard only).** OpenKeeb fills the custom
  slot's `word_page` so the Cyberboard firmware draws the text itself (up to
  255 characters). Its on-device behavior is unknown until the live
  experiment (B2); until then the product labels it untested and shows no
  pixel preview for it.

## Non-goals

- No new hardware write path, protocol command, or transport change. Banners
  become ordinary panel-track frames; the existing `/api/device/preflight` →
  `/api/device/write` → `/api/device/verify` flow carries them unchanged.
- No `word_page` authoring for NEON (its firmware reads no text section,
  `neon_driver.py:150-174`), Relic 80, or AFA.
- No claim about built-in text appearance, scrolling, colors, or character
  coverage before B2 evidence exists.
- No text on Relic 80 (`80`), AFA (`ALICE`), Vial, or VIA boards.
- No hub-schema change. `hub_am._capabilities` (`hub_am.py:176-204`) declares
  one `am_frames` surface with role `panel` for every AM family, including
  families with no billboard, and `hub_am` does not map NEON `axial`/`head`
  (`hub_am.py:144`, `:475-479`). Adding a hub `panel_display` descriptor is
  deferred to AM↔hub parity work; the AM Lighting Studio does not read hub
  capabilities, so nothing here depends on it.
- No non-ASCII glyphs, emoji, or CJK in the lane A font: a 5-row panel cannot
  render them legibly. Lane B character coverage beyond printable ASCII is
  decided only from B2 evidence.
- No code, glyph data, or effect math copied or derived from
  am-led.nanakumi.net or any third-party font (clean-room rule, effect-techniques
  plan lines 27-33). Glyphs are authored in this repository.

## Established facts (verified in code on `1359a9b`)

- Panel geometry authority: `_LAYOUTS` in `am_configurator/device_mapping.py:151-188`.
  CB `frames` is 40×5 = 200 pixels with identity map `_CB_DISPLAY_MAP =
  tuple(range(200))` (`:58-59`). NEON `head` is 46×5 = 230 pixels with identity
  map `_NEON_HEAD_MAP` (`:147-149`). Both are row-major, index `y*width+x`,
  origin top-left (NEON origin hardware-verified,
  `docs/neon-80-hardware-verification.md:87,155`; CB origin unverified on
  hardware). `_TARGET_SEMANTICS` (`:356-362`) marks `frames` and `head` as
  `"display"`. Relic 80 and ALICE have no display track.
- Published to the browser by `target_capabilities()` (`device_mapping.py:1448`)
  via `_capabilities()` (`server.py:1960-1968`) at `/api/led/capabilities`.
  The browser mirror of family numbers is `SPEC_SOURCE` in
  `am_configurator/web/lighting_targets.js:69-83`, drift-guarded by
  `tests/test_device_mapping.py:680`.
- Frame caps: `MODEL_FRAME_CAPS = {"CB": 80, "80": 200, "ALICE": 186, "NEON": 256}`
  (`device_mapping.py:14`). NEON enforces 256 at push (`neon_lighting.py:45`,
  `:217-221`). `validate_config` does **not** enforce the CB cap
  (`server.py:1499-1532`); authoring paths must.
- Timing: one `speed_ms` per page from `LED_SPEEDS_MS` (`device_mapping.py:15-32`):
  255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34.
  No per-frame delay. `speed_ms` is page-wide: the same slot's key track plays
  at the same rate. `applyLedResultToPage` (`app.js`, near `:6703`) already sets
  `page.speed_ms` from the applied result's `duration_ms` for every existing
  effect; banners inherit that behavior.
- Color is 24-bit `#RRGGBB` per pixel; page brightness `lightness` 0-100.
- NEON derives its 70-LED side zone from `head` at transmit time
  (`neon_lighting.py:80-111`); any `head` banner is echoed, downsampled, on the
  side LEDs. This is existing device behavior, not something to change.
- Cyberboard built-in text wire section: `word_page_frames`
  (`writer.py:99-113`) sends `[3,1]` frames of up to `WORD_PER_FRAME = 28`
  two-byte codes (`writer.py:41`), payload `[chunk_idx, page_index, valid,
  count] + codes`, each code from a `#XXXX` string big-endian
  (`uni_bytes`, `writer.py:59-61`); the manifest `[2,1]` carries one-byte
  `word_len` per page (`writer.py:71-78`), so at most 255. Page control
  `[2,2]` carries `color.default`, `color.back_rgb`, `color.rgb`, and
  `speed_ms` per page (`writer.py:81-96`). The `word_page` inner loop was
  reconstructed from decompiled sources ("lost" and "repaired",
  `writer.py:15-17`) and has never been exercised on hardware: the encoding
  itself is unverified. `_protocol_config` passes `page_data` through whole
  (`server.py:1636-1657`), so a populated `word_page` reaches the writer.
  `validate_config` (`server.py:1427-1561`) and `profile_import.py` never
  inspect `word_page`. New pages get the stub
  `{"valid": 0, "word_len": 0, "unicode": []}` (`server.py:210`).
- Neither board supports LED read-back (`reader.py:10-12`,
  `neon_driver.py:132-133`). Live banner evidence is visual only.
- Custom slots are pages 5, 6, 7 ("Custom slot 1-3"); NEON maps slot N to page
  N+4 (`neon_driver.py:136-156`).
- Studio tools: `availableStudioTools()` returns
  `["paint","source","animate","pattern"]` (`app.js:3648`); `setStudioTool`
  refuses tools not in that list. Board preview frame sets are built by
  `createBoardFrameSet` (`lighting_workspace.js:174`), whose `PROVENANCE` set
  (`:11-17`) must contain the frame set's `provenance`, which must equal
  `context.source_kind`. Apply path: `acceptedBoardFrameSetForApply` →
  `applyBoardFrameSetToPage` → `applyLedResultToPage` (`app.js:6679-6724`),
  which replaces only the tracks present in the result.
- Grid rendering: `gridClass` in `renderLightingEdit` (`app.js` near `:6410`)
  is `"display"` only for `frames`; NEON `head` falls through to `"key"`, and
  `columns` is hardcoded 40 for `frames`.
- Library: kind `lighting_composition`, `schema_version` 1
  (`library.py:2360-2415`); `effects` is a free JSON list validated only as a
  list. Browser provenance: `createLightingProvenance` /
  `lightingProvenanceForPage` (`library_state.js:297-350`); `validateEffects`
  (`:247`) accepts any array of at most 8 entries. `lighting_composer.validateEffectSpec`
  (`lighting_composer.js:657-735`) validates its own effect types and must not
  be handed a banner entry.
- New browser modules are registered in four places: `server._STATIC`
  (`server.py:43-54`), an `index.html` script tag (`:356-363`), a `node --check`
  line in `.github/workflows/ci.yml` (`:71`), and the Verification block in
  `.agents/repo-guidance.md`.
- Copy guard: `tests/web/plain_language.test.js:43-57` bans words such as
  "raster", "deterministic", "bank", "procedural effect". Tokens:
  `am_configurator/web/style.css:1-23` (`--violet` document/edit, `--cyan`
  live/connected, `--amber` caution, `--red` destructive/write only).

## Design

### Capability: `panel_display`

Python is the authority. `device_mapping.target_capabilities()` gains, per
model, a `panel_display` entry that is present only for models whose layouts
contain a target with semantic `"display"` **and** whose family is `CB` or
`NEON`:

```json
"panel_display": {
  "target": "frames",
  "width": 40,
  "height": 5,
  "max_frames": 80,
  "speeds_ms": [255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34],
  "text": {"font": "openkeeb-panel-5", "charset": "ascii-printable"},
  "builtin_text": {"max_chars": 255, "charset": "ascii-printable", "hardware_verified": false}
}
```

NEON's entry names `head`, width 46, and has **no** `builtin_text` key.
`builtin_text` is present only for `CB`. `max_frames` is
`MODEL_FRAME_CAPS[family]`. Derive every number from `_LAYOUTS`,
`MODEL_FRAME_CAPS`, and `LED_SPEEDS_MS`; hardcode only the family allowlist
and the `text` and `builtin_text` descriptors. `builtin_text.charset` and
`hardware_verified` change only in B3, from B2 evidence. Assert in Python
that the named target's map is the identity `range(width*height)`; if a future
layout breaks that, `panel_display` must be omitted for that model rather than
published with a wrong pixel order.

The browser reads `panel_display` from the served capabilities for the active
family. Absent → no Text tool, no text copy, nothing disabled-looking.

### Font `openkeeb-panel-5`

- Original, authored in this repository, same license as the repository.
- Printable ASCII `0x20`-`0x7E`, 95 glyphs, every glyph exactly 5 rows.
- Proportional: glyph widths 1-5 columns; space is 3 columns. One blank
  column between adjacent glyphs; no trailing spacing after the last glyph.
- Stored in the new module as a frozen table `char → [row0 … row4]`, each row
  a string of `#` (lit) and `.` (unlit) of the glyph's width. No other
  encoding.
- Legibility rules the glyph author must satisfy: digits 0-9 are all distinct;
  `0`/`O`, `1`/`l`/`I`, `5`/`S`, and `8`/`B` are pairwise distinct; lowercase
  letters may use small-cap forms (lit only in rows 1-4 or 2-4) because five
  rows leave no room for ascenders and descenders, but each lowercase glyph
  must differ from its uppercase glyph (T2 asserts this for `a`-`z`).

### Layout and frames (pure function)

New UMD module `am_configurator/web/panel_text.js` exporting:

- `FONT` (frozen), `measureText(text) → width`,
- `validateBannerSpec(spec, panel) → normalized spec` (throws
  `PanelTextError` with a `code` and plain-language message),
- `planBanner(spec, panel) → {frameCount, stepPx, periodPx, durationMs}`,
- `renderBanner(spec, panel) → {frames: string[][], frameCount, durationMs}`
  where each frame is `width*height` `#RRGGBB` uppercase strings, row-major.

`panel` is the served `panel_display` object. The module is pure:
no DOM, no time, no randomness; identical input → identical output.

Banner spec (schema `panel_text/1`):

```jsonc
{
  "schema": "panel_text/1",
  "text": "HELLO",
  "motion": "scroll",          // "scroll" | "static"
  "align": "center",           // static only: "left" | "center" | "right"
  "color": {"mode": "solid", "rgb": "#FFFFFF"},   // mode "solid" | "rainbow"
  "background": "#000000",
  "effect": "none",            // "none" | "pulse" | "blink" (blink: static only)
  "speed_ms": 62               // member of panel.speeds_ms
}
```

Validation: `text` is 1-64 characters, every character in `FONT`; unsupported
characters are reported by name in the error. Unknown keys, wrong types,
`align` with `scroll`, `blink` with `scroll`, and `speed_ms` outside
`panel.speeds_ms` are errors.

Static motion: `measureText(text) ≤ width` or error `too_wide` ("This text is
too wide to stay still on this display. Use Scroll or shorten it."). Text is
placed at x = 0, `floor((width-w)/2)`, or `width-w` for left/center/right,
rows 0-4. Frame count: `effect` none → 1; pulse → `min(32, max_frames)`;
blink → 8 (frames 0-3 text on, 4-7 text off).

Scroll motion, seamless marquee moving right-to-left:

1. `w = measureText(text)`, `W = panel.width`, `C = panel.max_frames`,
   gap `g = 8`.
2. Period `P = max(w + g, W)`.
3. Step `s` = the smallest of 1, 2, 3 with `ceil(P / s) ≤ C`. None → error
   `too_long` whose message names the longest text that fits at `s = 3`
   (computed, not estimated).
4. `P' = s * ceil(P / s)` (pad the gap so the loop closes exactly);
   `frameCount = P' / s`.
5. Strip of length `P'`: text columns at `[0, w)`, background after.
6. Frame `k`, display column `c` shows strip column
   `((c + k*s - W) mod P' + P') mod P'`. Frame 0 therefore has the text's first
   column just past the right edge; frame `frameCount` would equal frame 0.

Worked budget (for tests): CB, `w = 72` → `P = 80`, `s = 1`, 80 frames. CB,
`w = 73` → `P = 81`, `s = 2`, `P' = 82`, 41 frames. NEON, `w = 248` → `P = 256`,
`s = 1`, 256 frames. CB at `s = 3` fits `P' ≤ 240`, so `w ≤ 232`.

Color: solid → every lit pixel is `color.rgb`. Rainbow → lit pixel hue
`h = stripColumn / P'` for scroll, `h = (c / W + k / frameCount) mod 1` for
static; HSV saturation 1, value 1, converted to `#RRGGBB` with rounding
half-up per channel. Unlit pixels are `background`.

Effects: pulse multiplies lit-pixel RGB by
`f(k) = 0.35 + 0.65 * (0.5 - 0.5 * cos(2π k / frameCount))`, rounded half-up;
the background is not scaled. Blink shows background only on frames 4-7.

`durationMs` is `spec.speed_ms`.

### Studio integration

- `availableStudioTools()` appends `"text"` only when the active family's
  `panel_display` exists **and** `state.ledTarget === panel_display.target`.
  If the target changes while the Text tool is active, fall back to `"paint"`
  through the existing `setStudioTool` path.
- Tool label "Text". Panel controls: text field (single line,
  `maxlength=64`), Motion (Scroll/Still), Align (Still only), Color
  (Solid + color input / Rainbow), Background color, Effect
  (None/Pulse/Blink; Blink hidden for Scroll), Speed (the served speeds shown
  as Slow…Fast labels mapped to exact `speed_ms` values, default 62). A
  one-line note states that applying sets this slot's speed for its key
  lighting too. Follow the Patterns panel markup (`app.js:5245-5305`) and
  existing tokens; no new colors.
- Every valid edit re-renders synchronously through `renderBanner` and
  publishes a Board frame set with provenance `"text_banner"` (add to
  `PROVENANCE` in `lighting_workspace.js` and to the accepted provenance list of
  the apply button). `frames_by_target` contains only the panel target;
  `maxFrames` is `panel_display.max_frames`; `allowedDurations` must include
  `speed_ms`. Validation errors replace the preview with the error message and
  disable Apply.
- Apply uses `acceptedBoardFrameSetForApply({provenance: "text_banner"})` and
  `applyBoardFrameSetToPage`, so only the panel track and `speed_ms` change.
- Fix `gridClass` and `columns` in `renderLightingEdit` to use
  `panel_display` (display class and served width) for NEON `head` as well as
  CB `frames`.
- Provenance: on Apply, record the normalized spec as the single entry of the
  provenance `effects` list: `{"type": "text_banner", "spec": <spec>}`. When
  the Text tool opens on a slot whose page fingerprint still matches that
  provenance (`lightingProvenanceForPage`), prefill the controls from the spec;
  otherwise start empty. Every consumer of provenance or composition `effects`
  (find them with `grep -n "effects" am_configurator/web/*.js`) must either
  handle `type: "text_banner"` or skip it explicitly; `validateEffectSpec` must
  never receive it.
- Library: saving a slot with banner provenance stores the entry in the
  composition `effects` list (no library schema change). Reopening that saved
  composition into a slot and opening the Text tool restores the spec.

### Built-in text (lane B, Cyberboard only)

Data written to the chosen custom slot page (5, 6, or 7):

```jsonc
"word_page": {"valid": 1, "word_len": 5, "unicode": ["#0048", "#0045", "#004C", "#004C", "#004F"]},
"color": {"default": 0, "back_rgb": "#000000", "rgb": "#FFFFFF"},   // assumption: back_rgb = background, rgb = text
"speed_ms": 62                                                        // assumption: governs built-in scroll rate
```

- `unicode[i]` is `"#"` + the character's UTF-16 code unit as four uppercase
  hex digits; `word_len == len(unicode)`; `1 ≤ word_len ≤ 255`. Until B3,
  input is limited to printable ASCII `0x20`-`0x7E` (the served
  `builtin_text.charset`).
- The color and speed mappings are **assumptions** carried into B2 as test
  cases. Mark them in code comments as unverified with a pointer to this plan.
- Pure helper in `panel_text.js`: `builtinTextPage(spec, panel) →
  {word_page, color, speed_ms}` with its own validation (`text` 1-255
  characters within the charset; colors `#RRGGBB`; `speed_ms` in
  `panel.speeds_ms`). Spec schema `panel_builtin_text/1`:
  `{"schema", "text", "rgb", "background", "speed_ms"}`.
- Server validation: `validate_config` gains `word_page` checks for every page
  of every family (the writer would otherwise crash or send garbage): object
  with exactly `valid`, `word_len`, `unicode`; `valid` in {0, 1}; `unicode`
  a list of `#XXXX` hex strings; `word_len == len(unicode) ≤ 255`;
  `valid == 1` requires `word_len ≥ 1`. A non-empty `word_page` on a non-`CB`
  family is refused with a plain message, because no other family reads it.
  Before adding the non-`CB` refusal, check `tests/fixtures/am_master_import_cases.json`
  and every test config for a populated `word_page` on another family; if
  one exists, stop and record it instead of refusing.
- Text tool on `CB` `frames` shows a mode switch "Drawn by OpenKeeb" /
  "Keyboard's built-in text". Built-in mode fields: text (`maxlength=255`),
  text color, background, speed. It publishes no Board frame set; the preview
  area shows the typed text as plain text plus the fixed note "Your Cyberboard
  draws this text itself. OpenKeeb has not tested how it looks yet." Apply
  writes only `word_page`, `color`, and `speed_ms` of the slot and leaves the
  panel frames track untouched. A "Remove built-in text" action restores the
  stub `{"valid": 0, "word_len": 0, "unicode": []}`.
- When the slot has both a populated `word_page` and panel frames, the Text
  tool states: "This slot also has display animation. How your Cyberboard
  combines them has not been tested yet." B3 replaces this with the observed
  rule.
- Library: built-in text is not saved to the Library before B3.
- Writer: no change unless B2 proves the encoding wrong. Add to
  `tests/test_protocol.py` (writer frame tests; `tests/test_transport.py`
  already calls `writer.plan`) byte-exact
  assertions for a 5-character and a 29-character `word_page` (two `[3,1]`
  frames) and the manifest `word_len` byte, pinning current behavior so a B2
  correction is a visible diff.

## Slices

Each slice: focused tests, at least one new test proven to bite (revert the
change, observe the failure, restore), full verification entry point from
`.agents/repo-guidance.md`, `git diff --check`, one commit, `.agents/state.md`
updated in the same commit. Order: T1, T2, T3, T4, B1, T5. L and B3 are
outside D2's approval.

### T1 — `panel_display` capability

Files: `am_configurator/device_mapping.py`, `tests/test_device_mapping.py`
(and `tests/test_app.py` if `/api/led/capabilities` is pinned there).
Tests: CB publishes `frames` 40×5, `max_frames` 80; NEON publishes `head`
46×5, `max_frames` 256; `80` and `ALICE` have no `panel_display`; speeds equal
`LED_SPEEDS_MS`; a layout with a non-identity map drops the entry.

### T2 — font and renderer

Files: new `am_configurator/web/panel_text.js`, new
`tests/web/panel_text.test.js`, registration in `server._STATIC`,
`index.html`, `ci.yml`, `.agents/repo-guidance.md`.
Tests: 95 glyphs, 5 rows each, row widths equal per glyph, widths 1-5, space
width 3; distinctness rules; `measureText` examples; every validation error
code; the worked budgets above; seamless loop (frame `k+frameCount` rendered
by the formula equals frame `k`); frame count never exceeds `max_frames` for
every text length 1-64 of `"W"` and `"i"` on both panels; exact pixel
snapshot for `"HI"` static center solid on CB (write the expected 200 values
from the authored glyphs); pulse and rainbow values at two frames; determinism
(two calls deep-equal).

### T3 — Text tool

Files: `am_configurator/web/app.js`, `am_configurator/web/lighting_workspace.js`,
`am_configurator/web/index.html` if markup lives there,
`am_configurator/web/style.css` only if existing classes do not cover the
panel, web tests beside `tests/web/lighting_patterns.test.js`.
Tests: Text tool present only for CB `frames` / NEON `head`; absent for keys
targets and for `80`/`ALICE`; falls back to Paint on target change; valid spec
publishes a `text_banner` frame set with only the panel target; invalid spec
disables Apply and shows the message; Apply replaces only the panel track and
`speed_ms`, leaving the key track byte-identical; NEON grid uses display class
and 46 columns; plain-language guard passes on new copy.

### T4 — provenance and Library round trip

Files: `am_configurator/web/library_state.js`, `am_configurator/web/app.js`,
relevant web tests, `tests/test_library.py`.
Tests: provenance with a `text_banner` entry round-trips; a saved composition
carrying it passes `library.py` validation and restores the spec; composer
effect validation is never called with it; a changed page fingerprint yields
an empty Text tool.

### B1 — built-in text authoring (fixture-backed)

Files: `am_configurator/device_mapping.py` (`builtin_text`),
`am_configurator/server.py` (`validate_config`), `am_configurator/web/panel_text.js`,
`am_configurator/web/app.js`, writer and server tests, web tests.
Tests: `builtin_text` present for `CB` only; `builtinTextPage` encodes
`"HELLO"` exactly as above, rejects 0 and 256 characters and non-ASCII;
`validate_config` accepts the stub and a valid page, rejects each malformed
case and a populated `word_page` on `NEON`; writer byte-exact assertions
above; Text tool mode switch present only on `CB`; built-in Apply changes only
`word_page`, `color`, `speed_ms`; Remove restores the stub; both-present note
renders; no Board frame set is published in built-in mode.

### T5 — closure

Full verification entry point. Rendered checks in Chrome with no device
connected (document-only CB and NEON configs) at 1000×680, 1280×800, and
1600×1000: Text tool empty state, scroll preview playing, static preview,
`too_long` and unsupported-character errors, applied slot, and on CB the
built-in mode with and without the both-present note. Record console
warnings/errors (must be zero), page-level horizontal overflow (must be none),
and that no hardware request was made. Update `.agents/state.md` and this
plan's status with evidence.

### L — live evidence (separately owner-gated; not part of closure)

Requires an owner go naming the exact board(s), slot, and the cases below.
Every write goes through the normal GUI write flow with typed confirmation;
nothing is written by a test or script. Neither board reports its lights back,
so each observation is the owner's visual confirmation or a photo. Before the
first write on each board, record model, revision, firmware, and the current
config as a saved backup; a full write replaces keymaps and macros too, so
every write starts from the board's own current document with only the chosen
slot changed. Stop at the first unexpected result (write failure, verify
mismatch, blank or garbled panel, wrong slot); record it; do not retry.

Lane A (NEON 80 and Cyberboard): one scroll banner and one static banner.
Record direction, origin, color, speed. CB display origin is unverified; a
mirrored or flipped result stops the slice and is recorded before any fix.

Lane B / B2 (Cyberboard), one write per case, each case recorded:

1. `"HELLO"`, panel frames track empty: does text appear; font; static or
   scrolling; direction.
2. Same text at `speed_ms` 34 and 255: does speed govern scrolling.
3. `rgb` red on `back_rgb` blue, `default` 0; then `default` 1: which color is
   text, which background, what `default` does.
4. Same slot with both `word_page` and a panel frames animation: which shows,
   or how they combine.
5. `"é€中"` (non-ASCII, BMP): rendered, replaced, or ignored per character.
6. A 255-character string: complete, truncated, or refused.

If case 1 shows nothing or garbage, stop: the reconstructed encoder is the
first suspect, and the fix is a plan update before any further write.

### B3 — built-in text from evidence

Scope is written into this plan after B2, from its records only: set
`builtin_text.hardware_verified` and `charset`; replace the untested notes
with the observed behavior; add a Board preview for built-in text only if B2
shows the firmware font and scrolling precisely enough to reproduce; decide
the both-present rule; add Library support. B3 needs no new owner decision
unless B2 shows the feature cannot work as the owner expects.

## Open items for the owner

- **D1 — settled 2026-09-30:** support both lanes (drawn frames on both
  boards; Cyberboard built-in text). Lane A's Cyberboard scroll length stays
  bounded by the 80-frame cap (text up to 72 columns at 1 px per frame, about
  14 characters; up to 232 columns at 3 px per frame).
- **D2 — approve this plan** as the implementation gate for T1-T4, B1, T5
  (fixture-backed, no hardware).
- **Live go (later, separate):** L names the boards, slot, and cases; B3
  follows from B2 records.
