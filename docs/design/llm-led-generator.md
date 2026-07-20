# Design: LLM-Backed LED Effect Generator

Status: draft v3 (post external design review + user review, pending approval)
Author: Claude Code session, 2026-07-20

## Context

The AM Configurator can already convert animated GIFs into per-model LED
animations (`/api/led/gif` → `gif_to_led_tracks` → LED Studio pages). Users who
want a custom effect still have to *find or author* a GIF first. This feature
lets a user type a description — e.g. *"pac-man chased by a blue ghost"* — and
have an LLM produce the frames, previewed and applied through the exact same
mapping pipeline as GIF import.

Decisions already made with the user:

- **Approach C**: a two-role provider architecture (text *interpreter* +
  pixel *renderer*) behind small interfaces, shipping with **Grok/xAI only**
  (one API key covers both roles). GPT Image 2, Claude, and CLI-passthrough
  interpreters are follow-ups behind the same interfaces.
- **Server-side proxy**: keys live in app config; the backend makes all
  provider calls. This is also *forced* by the CSP — `connect-src 'self'`
  (`server.py` `_headers`) blocks any browser→provider call.
- **Renderer contract is "ordered list of RGB frames"**, not a file format.
  Rationale: the Grok Imagine *video* API outputs MP4 only (undecodable
  without bundling ffmpeg; rejected for PyInstaller size), and image APIs
  output static frame sets. Both fit a frame-list contract; at 40×5 or
  90-LED rasters, video fidelity adds nothing.

## Goals

- Text prompt → previewable LED animation for every supported target
  (`CB` display 40×5 / keyframes; `ALICE` keyframes 160×5; `80` keyframes +
  spotlight edges), reusing the GIF import mapping pipeline unchanged.
- One new key (xAI) configured once in a new Settings UI.
- Zero new runtime dependencies (stdlib `urllib.request` + existing Pillow).
- Providers injectable so tests never touch the network.
- **Bounded spend**: every generation has a hard, server-enforced ceiling on
  provider calls, bytes, and wall-clock time.

## Non-Goals (v1)

- GPT Image 2 / Claude / codex- or claude-CLI providers (follow-ups).
- Grok Imagine video (MP4) path.
- OS keychain storage for keys (plaintext `settings.json`, disclosed in UI).
- Sprite-sheet/grid single-image generation (follow-up experiment; v1 is
  strictly one image request per rendered keyframe — see Renderer below).

> **Terminology**: the device target named `keyframes` (per-key LEDs, as in
> the GIF import UI) is unrelated to this doc's *rendered keyframes* (the
> subset of output frames actually generated via the image API). This doc
> always says "`keyframes` target" for the former.
- Streaming interpreter tokens (job-level progress is in scope, token
  streaming is not).

## Architecture

```
web UI (LED tab)                servers.py                          llm.py
┌───────────────────┐  POST /api/led/generate  ┌──────────────────────────┐
│ prompt textarea   │ ───────────────────────► │ start job (409 if busy)  │
│ [Generate]        │  ◄─ {job_id}             │ 1. load settings + key   │
│ poll status/phase │  GET /api/led/generate/  │ 2. Interpreter.interpret │ ──► api.x.ai /v1/responses
│ pending preview   │      status              │ 3. Renderer.render (×K)  │ ──► api.x.ai /v1/images/generations
│ [Apply][Discard]  │  ◄─ result (same shape   │ 4. frames_to_led_tracks  │
│ [Refine]          │      as /api/led/gif)    └──────────────────────────┘
└───────────────────┘
```

### 1. Provider layer — new module `am_configurator/llm.py`

Stdlib-only (`urllib.request`, `json`, `ssl`, `base64`). Two protocols:

```python
class Interpreter(Protocol):
    def interpret(self, prompt: str, spec: RasterSpec, deadline: float) -> EffectPlan: ...

class Renderer(Protocol):
    def render(self, plan: EffectPlan, spec: RasterSpec, deadline: float) -> RenderedFrames: ...

@dataclass(frozen=True)
class RasterSpec:          # one per generation; built server-side from _GIF_LAYOUTS
    model: str             # "CB" | "ALICE" | "80"
    target: str            # single semantic target for generation
    extra_targets: tuple[str, ...]  # same-raster copies (e.g. Relic pair, AFA body)
    width: int; height: int         # generation raster
    mapped_positions: tuple[tuple[int, int], ...] | None  # sparse mask (80 edges, AFA)
    output_len: int                 # LEDs actually driven
    max_frames: int                 # per-model firmware cap — a ceiling, never a target

@dataclass(frozen=True)
class EffectPlan:
    subject: str; palette: str; motion: str
    frame_count: int                 # OUTPUT frames the effect needs; ≤ spec.max_frames
    frame_ms: int                    # must be one of the firmware speed steps
    keyframe_prompts: tuple[str, ...] # 1..MAX_RENDERED_KEYFRAMES paid renders; ≤ frame_count
    tween: str                       # "crossfade" | "step" — local expansion to frame_count
    notes: str

@dataclass(frozen=True)
class RenderedFrames:
    images: tuple[Image.Image, ...]  # RGB; len == len(plan.keyframe_prompts), enforced
    # durations come from the validated EffectPlan, not the renderer
```

**Per-model frame caps** (`MODEL_FRAME_CAPS`, firmware limits confirmed with
the user): `CB` (R4) → **80**, `80` (Relic) → **200**, `ALICE` (AFA,
160×5 raster) → **186**. These are *ceilings*:
the interpreter prompt says "use the fewest frames that express the effect —
the cap is a limit, not a goal" and never advertises the cap as a target.
(Follow-up alignment: the GIF import path currently uses a single global
256-frame cap; `MODEL_FRAME_CAPS` should become the shared source of truth
for both paths.)

**Rendered keyframes vs output frames.** Paid image renders are decoupled
from output frames: the interpreter plans `frame_count` output frames (what
plays on the keyboard) and up to `MAX_RENDERED_KEYFRAMES = 16` keyframe
prompts (what gets rendered via the API). The server expands K rendered
keyframes to `frame_count` outputs locally — keyframes evenly spaced on the
timeline, gaps filled by Pillow `Image.blend` cross-fade or step-hold per
`plan.tween` — at the generation raster, before mapping. A 200-frame Relic
loop therefore costs ≤ 1 + 16 provider calls, and smoothness at high frame
counts comes from local interpolation rather than 200 independently
generated (and mutually incoherent) images. When `frame_count ≤ K`, every
frame is a rendered keyframe and no tweening occurs.

**Target rules (one raster per generation):**

- Exactly **one CyberBoard target** per generation — `display` (40×5) and
  `keys` (15×6) have incompatible aspect ratios and are never generated from
  one raster. The UI enforces this; the server rejects mixed CB targets.
- The Relic 80 per-key + spotlight-edge pair and the AFA body-light copy are
  expressed as `extra_targets` (same raster, different mapping), matching
  what `gif_to_led_tracks` already does.
- Sparse targets (Relic edges' seven sample positions, AFA underglow) carry
  `mapped_positions` so the interpreter prompt can say *"only these positions
  are visible — put the content there"*.

**V1 implementations (endpoints and models pinned now, not "at
implementation time"; bumping them is a deliberate one-line change to the
`XAI_MODELS` constant):**

- **`GrokInterpreter`** — `POST https://api.x.ai/v1/responses` with
  `store: false` and a **strict JSON schema** (structured outputs;
  `additionalProperties: false` throughout). Chat Completions is deprecated
  upstream and is not used. The system prompt embeds raster geometry, the
  sparse-position mask when present, and the firmware speed steps so
  `frame_ms` snaps to a legal value.
- **`GrokImagineRenderer`** — `POST https://api.x.ai/v1/images/generations`,
  `response_format: "b64_json"`, `n: 1`, **one request per rendered
  keyframe**, issued sequentially under the job deadline. Exact call count
  per generation: `1 + len(keyframe_prompts)` (1 interpret + K keyframe
  images, K ≤ `MAX_RENDERED_KEYFRAMES = 16`) — independent of
  `frame_count`, so a 200-frame Relic loop still costs at most 17 calls.
  Each keyframe prompt is `EffectPlan.keyframe_prompts[i]` behind a shared
  style prefix for coherence. Tween expansion to `frame_count` output
  frames happens locally after all keyframes decode (see Data model).
  **No URL fetching**: the URL response mode is never requested
  and URL fields in responses are ignored (removes the SSRF/redirect/
  oversized-download class entirely).
  - *Partial failure*: if keyframe k of K fails after retries are ruled out
    (see error policy), the job fails with a typed error naming the phase;
    completed images are discarded. Paid image POSTs are **never
    auto-retried** (no idempotency guarantee upstream).
  - *Aspect fit*: the API's widest documented ratio (20:9) is far from CB
    display's 8:1 — and further still from ALICE keyframes' 160×5 (32:1).
    The renderer requests the widest supported ratio and the existing
    pipeline fit (center-crop cover) reduces it to the raster. The
    interpreter prompt compensates ("content in a horizontal band").

**Response validation (defense-in-depth, all before Pillow decode):**

- Upstream body read is capped (`MAX_PROVIDER_RESPONSE = 25_000_000` bytes,
  enforced via bounded `read()`, not trust in Content-Length).
- JSON parse → schema-shape check → base64 validity → decoded size cap
  (`MAX_IMAGE_BYTES = 12_000_000`) → Pillow open with format whitelist
  (PNG/JPEG) → pixel-count cap (≤ 4 MP) → full `load()` before conversion.

**EffectPlan validation (stdlib validator, independent of provider claims):**

- Required fields, types, string length caps, `frame_ms` ∈ firmware speed
  steps, `1 ≤ frame_count ≤ spec.max_frames`,
  `1 ≤ len(keyframe_prompts) ≤ min(frame_count, MAX_RENDERED_KEYFRAMES)`,
  `tween` ∈ {`crossfade`, `step`}, non-empty prompts.
  Schema-valid-but-inconsistent output fails *before* any paid image call.

**Typed errors** — `ProviderError(code, message, retry_after=None)` with
stable codes, replacing the v1-draft "everything is `ValueError` → 400":

| code            | meaning                          | local HTTP |
|-----------------|----------------------------------|------------|
| `config`        | no key / unknown provider        | 400        |
| `auth`          | upstream 401/403                 | 400 (actionable: "check Settings") |
| `rate_limited`  | upstream 429                     | 429 (+ `Retry-After` passthrough) |
| `timeout`       | deadline exceeded (any phase)    | 504        |
| `offline`       | DNS/TLS/socket failure           | 503        |
| `moderation`    | provider refusal                 | 400 (actionable) |
| `bad_response`  | malformed/oversized/invalid JSON, b64, image | 502 |
| `unavailable`   | upstream 5xx                     | 502        |

A single **monotonic deadline** (`time.monotonic() + LLM_TOTAL_BUDGET`,
120 s) is passed through both phases; every `urllib` call gets
`min(remaining, per_call_timeout)`. Secrets are redacted from every error
message and log line.

Registry: `INTERPRETERS = {"grok": GrokInterpreter}`,
`RENDERERS = {"grok": GrokImagineRenderer}`. Follow-up providers register
here. The browser reads names/caps from `GET /api/led/capabilities`
(see endpoints) rather than duplicating the registry in JavaScript.

### 2. Settings storage — `am_configurator/store.py`

New app-level (not device-level) settings file. Reuses existing helpers:

- `settings_path() -> store_root() / "settings.json"`
- `load_settings() -> dict` via `_read_json`; **corrupt file → rename to
  `settings.json.bad` + start fresh** (recoverable, never a 500).
- `save_settings(dict)` via `_atomic_write_json` + `_settings_lock()`
  (advisory lock like `device_lock`); `chmod 0o600` where supported.

Shape: `{"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": "..."}}}`

Strict write contract: unknown fields and unknown provider names are
rejected, not merged. The masked display value can never round-trip into
storage (mask sentinel is rejected as a key value). `XAI_API_KEY` env var
acts as a non-persistent override (never written to disk).

### 3. HTTP endpoints — `am_configurator/server.py`

Added to the existing `do_GET`/`do_POST` elif chains, behind `X-AM-Token`:

- **`GET /api/settings`** → `{"llm": {..., "keys": {"xai": {"set": true, "last4": "…"}}}}`
  — the raw key never returns to the browser.
- **`POST /api/settings`** → strict-validate + save; empty string clears.
- **`POST /api/settings/test`** *(no-cost key check)* — one models-list
  request; returns ok / typed error. Catches bad keys before paid calls.
- **`GET /api/led/capabilities`** → provider names, model IDs,
  `MODEL_FRAME_CAPS`, `MAX_RENDERED_KEYFRAMES`, per-model target rules —
  single source of truth for the UI.
- **`POST /api/led/generate`** — body:
  `{"prompt": str, "product_id": str, "targets": [str], "frame_count"?: int}`.
  Validation first (reuse `_led_model` / target semantics from
  `_convert_gif`; enforce single-CB-target rule; clamp `frame_count` to
  `MODEL_FRAME_CAPS[model]` when supplied; when omitted the interpreter
  chooses it) → **starts a background job** and returns
  `{"job_id": ...}` immediately. **One active generation per app instance**:
  a second POST while busy → 409. This bounds spend (≤ 1 +
  `MAX_RENDERED_KEYFRAMES` = 17 provider calls per user action regardless
  of `frame_count`, no concurrency amplification via tabs or direct calls).
- **`GET /api/led/generate/status?job=…`** → `{"phase": "interpreting" |
  "rendering k/K" | "tweening" | "mapping", ...}` while running; on
  completion the full result: same JSON shape as `/api/led/gif` **plus**
  `"plan"` (subject / frame_count / rendered keyframe count / tween /
  frame_ms) and `"usage"` (provider-reported
  token/image counts when available) for the UI. Generated-path values for
  the GIF-shape fields are defined, not left over: `source_frames` and
  `decoded_frames` = `frame_count`, `source_duration_ms` =
  `frame_count × frame_ms`, `timing_resampled` = `false`.
- **`POST /api/led/generate/cancel`** — sets the job's cancel flag; honored
  between provider calls (no mid-download abort needed given bounded reads).

The job runs on one worker thread owned by `_State` (not per-request);
results are held until read or replaced. `ThreadingHTTPServer` still serves
all other routes during a generation.

Provider injection for tests: `_State` gains `llm_factories: dict | None`;
`create_server(..., llm_factories=...)` lets tests supply fakes; production
resolves from the registry. Additionally the real Grok classes accept an
injected `transport` callable (request-dict → response-bytes) so their
parsing/error paths are testable without network.

### 4. Pipeline refactor — `gif_to_led_tracks` split

Extract the per-frame mapping core (crop → resize → hex → firmware-index
remap → timeline resample, currently inline in `gif_to_led_tracks`) into:

```python
def frames_to_led_tracks(images, durations_ms, targets, resample, product_id) -> dict
```

`gif_to_led_tracks` becomes decode-loop + delegate; behavior identical
(existing `GifImportTests` guard this). The extracted core owns alpha
flattening, fitting, mapping, the ≤ 256 frame limit, and timing
normalization for *both* sources. The LLM path calls it directly with PIL
images — no GIF re-encode, no 256-color quantization of fresh pixels.
Parity tests cover every track type, the paired Relic output, and the AFA
body-light copy.

### 5. Frontend — `am_configurator/web/` (`index.html`, `app.js`, `style.css`)

- **LED tab — "Generate with AI"** panel beside the GIF import control:
  prompt textarea, target selector (reusing the GIF import target UI, with
  the single-CB-target rule), frame-count selector (1–8, default 6) with the
  **call count shown before generating** ("1 + 6 API calls"), Generate
  button → poll status endpoint, phase shown in the busy label
  ("rendering 3/6…"), plus Cancel.
- **Pending preview, not silent edit** (fixes the v1-draft contradiction
  where the result fed `importGif`'s path and immediately mutated the page):
  the generated tracks land in a separate `pendingGeneration` state and
  preview via `renderLeds`/`startPlayback` *from that state*. Explicit
  **[Apply to page]** performs the mutate + one undo checkpoint + dirty
  mark; **[Discard]** drops it; **[Refine]** reopens the prompt *with the
  previous prompt and plan summary preserved* and sends
  `previous_plan` alongside the new prompt text so the interpreter can do a
  delta rather than starting over. Failures/cancel preserve the current page
  and the prompt text.
- **Errors**: persistent inline error region in the panel (not the 6.5 s
  toast), showing the typed-error message; 429 shows the retry-after.
- **Settings panel**: provider picker (from `/api/led/capabilities`), masked
  key field (`<input type="password">`) with Save/Clear and a **Test key**
  button (`/api/settings/test`).
- **Privacy copy (required, not optional)**: the LED tab currently promises
  previews happen "without uploading anything" — that stays true for manual
  and GIF tools and is scoped to say so. The AI panel carries its own
  disclosure shown before first use: the prompt, derived frame prompts, and
  target geometry (model family + raster size only — never the keyboard
  configuration, macros, or device identity) are sent to xAI; xAI retains
  API data per its policy (30-day default); internet and a paid API key are
  required.

### 6. Tests — `tests/test_app.py`

- `FramesToLedTracksTests`: call the new core directly with `Image.new`
  frames; per-model mapping parity vs `gif_to_led_tracks` for every track
  type incl. Relic pair + AFA copy.
- `LedGenerateEndpointTests`: loopback server with fake interpreter/renderer
  via `create_server(llm_factories=...)`; assert job lifecycle (start →
  phases → result), response shape parity with `/api/led/gif`, auth
  required, 409 on concurrent start, cancel honored, missing-key → 400 with
  settings hint, **and that no endpoint test ever invokes device writing**.
- `GrokTransportTests` *(new, addresses "tests bypass the riskiest code")*:
  real `GrokInterpreter`/`GrokImagineRenderer` with injected transport;
  fixtures for malformed JSON, schema-violating plan, prompt-count mismatch,
  401/403/429 (+`Retry-After`)/5xx, timeout, moderation refusal, invalid and
  oversized base64, oversized pixels, partial batch failure, cancellation;
  assert secrets never appear in error strings.
- `SettingsStoreTests`: round-trip, atomicity (tmp store root via
  `AM_CONFIGURATOR_DATA_DIR`), masking, mask-sentinel rejection, unknown
  field rejection, corrupt-file recovery, env-var override, 0600 perms.
- No network in any test.

### 7. Packaging

- Add `am_configurator.llm` to `hidden_imports` in
  `packaging/am_configurator.spec`.
- No new third-party deps → no `THIRD_PARTY_NOTICES` change.
- Extend the frozen `--smoke-test` to run one fake-transport generation
  end-to-end inside the frozen app (exercises `ssl` context creation, JSON,
  base64, Pillow decode — the modules PyInstaller most often mis-bundles),
  plus a real-TLS HEAD to a well-known host guarded behind an opt-in flag
  for CA-trust verification on packaged macOS/Windows/Linux builds.

## Risks / open items

- **Keyframe coherence**: independently generated keyframes may flicker.
  Mitigations ordered: local tweening (crossfade smooths transitions by
  construction) → shared style prefix → (follow-up) sprite-sheet mode
  with fixed rows/columns/ordering contract → (future) image-to-image
  chaining or the MP4 path. At 40×5 the downscale forgives a lot; still the
  top quality risk.
- **Tween quality**: `Image.blend` cross-fades at the generation raster can
  look muddy for high-contrast content on per-key targets; `step` is the
  escape hatch, and the interpreter picks the tween per effect. Judge on
  real hardware during verification.
- **Cost**: 1 + K image calls per generation, K ≤ `MAX_RENDERED_KEYFRAMES`
  = 16 regardless of output `frame_count`, single-flight, no
  auto-retry — worst case is bounded and shown to the user up front.
- **xAI API drift**: endpoints/models are pinned constants with typed
  `bad_response` failures, so drift is a visible error + one-line bump, not
  silent breakage.
- **Key at rest**: plaintext JSON under the data dir; 0600 where supported;
  env-var override for the cautious; keychain integration is future work.

## Verification (end-to-end)

1. `python -m unittest` — new + existing tests green (esp. `GifImportTests`
   parity after the refactor).
2. `uv run am-configurator`, open LED tab: add key in Settings → Test key →
   Generate "pac-man chased by a blue ghost" for CB display → phases tick →
   pending preview animates → Apply → write to device (or `--smoke-test`
   path without hardware).
3. Negative paths: no key, bad key, 429, timeout, moderation, concurrent
   generate (409), cancel — each yields the mapped status + actionable
   inline error, no server crash, page state untouched.
4. `pyinstaller packaging/am_configurator.spec` — frozen smoke test passes
   incl. fake-transport generation.

## Changelog

- **v3**: per-model frame caps replace the global cap 8 — `MODEL_FRAME_CAPS`
  (`CB` 80, `80` 200, `ALICE` 186), caps documented as ceilings the
  interpreter is told not to chase; decoupled paid renders from output
  frames via `keyframe_prompts` (≤ `MAX_RENDERED_KEYFRAMES = 16`) + local
  `tween` expansion (`crossfade`/`step`), keeping worst-case spend at 17
  provider calls even for a 200-frame Relic loop; disambiguated the
  `keyframes` device target from rendered keyframes.
- **v2**: addressed external design review — pinned xAI endpoints/models
  (`/v1/responses` + `store:false`, images `b64_json`, no URL fetching);
  server-owned frame count and single-flight job; strict
  schema + independent validation between phases; typed provider errors
  mapped to 400/429/502/503/504 with monotonic deadline; per-track
  `RasterSpec` with sparse-position masks and single-CB-target rule;
  pending-preview Apply/Discard/Refine instead of silent page mutation;
  background job + polling + cancel instead of one long request; strict
  settings contract (mask sentinel, unknown-field rejection, corrupt-file
  recovery, env override, 0600); privacy disclosure copy; transport-level
  test fixtures; frozen-app generation smoke test; `/api/led/capabilities`
  + no-cost key test.
- **v1**: initial draft.
