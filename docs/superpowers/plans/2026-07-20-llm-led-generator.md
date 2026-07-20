# LLM-Backed LED Effect Generator — Implementation Plan

- **Date**: 2026-07-20
- **Design (source of truth)**: `docs/design/llm-led-generator.md` (draft v3,
  approved). Where this plan and the design disagree, the design wins; stop
  and flag the conflict instead of guessing.
- **Branch**: `llm-led-generator`
- **Execution model**: subagent-driven development — one fresh Opus subagent
  per task, in order. Gate between tasks: full `python3 -m unittest` (use
  `.venv/bin/python` if present) must pass, then commit, then review before
  the next task starts.
- **Goal**: users describe an LED effect in natural language; a two-phase
  xAI provider (Grok interpreter → Grok Imagine keyframe renderer) plus
  local tween expansion produces firmware-ready LED tracks through the
  existing GIF mapping pipeline, previewed as a pending result and applied
  only on explicit user action.

## Context for implementers (verified 2026-07-20)

- App: stdlib-only local HTTP server + browser UI. `am_configurator/server.py`
  (1380 lines) holds the pipeline and `_Handler(BaseHTTPRequestHandler)`;
  `am_configurator/store.py` holds persistence; UI in `am_configurator/web/`
  (`index.html`, `app.js`, `style.css`). Tests in `tests/test_app.py` (738
  lines; classes `DesktopServerTests`, `MergeTests`, `GifImportTests`,
  `MacroProtocolTests`, `SpotlightProtocolTests`), `tests/test_packaging.py`,
  `tests/test_protocol.py`. **No network in any test.**
- Key existing symbols (line numbers at plan time):
  - `server.py:40` `_MAX_GIF_BYTES = 12_000_000`; `:41` `_MAX_GIF_FRAMES = 256`
  - `server.py:43` `_LED_SPEEDS_MS = (255, 240, 224, 208, 192, 176, 160, 146,
    132, 118, 100, 90, 76, 62, 48, 34)` — the firmware speed steps
  - `server.py:122` `_GIF_LAYOUTS: dict[str, dict[str, dict[str, Any]]]` —
    models `"CB"`, `"ALICE"`, `"80"`; per-target `size`, `map`, `pixels`,
    optional `copies`
  - `server.py:242` `_led_model(product_id)`; `:259`
    `_gif_timeline_indices(durations)`
  - `server.py:294` `gif_to_led_tracks(payload, targets, resample="box",
    product_id="CB_XX") -> dict` — decode loop + per-frame crop/resize/hex
    mapping + timeline resample; returns `{"tracks", "source_frames",
    "decoded_frames", "duration_ms", "source_duration_ms",
    "timing_resampled", "model"}`
  - `server.py:996` `class _State` (holds `config`, `token`, `device_lock`);
    `:1009` `_Handler` with `_headers`, `_json`, `_authorized` (X-AM-Token),
    `_body` (25 MB cap); `do_GET :1056`, `do_POST :1099` are plain
    `elif`-chains on `urlparse(self.path).path`; `_convert_gif :1141`
    services `POST /api/led/gif`
  - `server.py:1338` `create_server(...)` returns `(server, url)`;
    tests already call it directly (`tests/test_app.py:246`)
  - `store.py`: `store_root()`, `device_lock(product_id)` (advisory lock
    file + `_lock_windows_byte` fallback), `_atomic_write_json(path, obj)`,
    `_read_json(path)`; store root honors `AM_CONFIGURATOR_DATA_DIR`
  - `web/app.js:41` `api(path, options)` fetch helper (adds `X-AM-Token`);
    `:947` `importGif(input)` posts to `/api/led/gif`
- Design constants (fixed by design v3 — do not re-derive):
  `MAX_RENDERED_KEYFRAMES = 16`; `MODEL_FRAME_CAPS = {"CB": 80, "80": 200,
  "ALICE": 186}`; `MAX_PROVIDER_RESPONSE = 25_000_000`;
  `MAX_IMAGE_BYTES = 12_000_000`; decoded pixel cap 4 MP;
  `LLM_TOTAL_BUDGET = 120.0` seconds (monotonic deadline across both
  phases); endpoints `POST https://api.x.ai/v1/responses` (`store: false`,
  strict JSON schema) and `POST https://api.x.ai/v1/images/generations`
  (`response_format: "b64_json"`, `n: 1`); no URL fetching ever; paid image
  POSTs never auto-retried.
- Pinned model IDs (verified against docs.x.ai 2026-07-20; bumping is a
  one-line change): `XAI_MODELS = {"interpreter":
  "grok-4.20-0309-non-reasoning", "renderer": "grok-imagine-image"}`.
- TDD is mandatory: every task writes its failing test first, watches it
  fail for the right reason, implements, watches it pass, runs the full
  suite, commits.

---

## Task 1 — App settings store

**Files**: modify `am_configurator/store.py`; add `SettingsStoreTests` to
`tests/test_app.py`.

1. Write failing tests (`SettingsStoreTests`, using a temp
   `AM_CONFIGURATOR_DATA_DIR` in `setUp`/`tearDown`):
   - `test_defaults_when_missing` — `load_settings()` with no file returns
     `{"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}}}`.
   - `test_round_trip` — `save_settings` then `load_settings` preserves
     `{"llm": {..., "keys": {"xai": "sk-test"}}}`.
   - `test_unknown_fields_rejected` — unknown top-level or `llm` keys, and
     unknown provider names, raise `ValueError` (strict, not merged).
   - `test_mask_sentinel_rejected` — saving a key equal to the mask
     sentinel (`"••••••••"`, exported as `store.KEY_MASK`) raises
     `ValueError`.
   - `test_corrupt_file_recovers` — corrupt JSON on disk: `load_settings()`
     returns defaults and the file is renamed to `settings.json.bad`.
   - `test_env_override` — with `XAI_API_KEY` set, `resolve_xai_key()`
     returns the env value and disk content is unchanged.
   - `test_file_permissions` — after save, mode is `0o600`
     (skip assertion on Windows via `sys.platform`).
2. Run: `.venv/bin/python -m unittest tests.test_app.SettingsStoreTests` —
   confirm all fail (functions don't exist).
3. Implement in `store.py`, reusing existing helpers:
   `settings_path() -> store_root()/"settings.json"`; `_settings_lock()`
   modeled on `device_lock`; `load_settings()` via `_read_json` with
   corrupt→`.bad` rename; `save_settings(values)` strict-validating then
   `_atomic_write_json` + `os.chmod(path, 0o600)` (guarded for Windows);
   `KEY_MASK = "••••••••"`; `resolve_xai_key() -> str | None` (env
   `XAI_API_KEY` wins, never persisted). Empty-string key deletes the entry.
4. Run task tests, then full suite. 5. Commit:
   `feat: add app-level settings store with strict llm settings`

## Task 2 — Extract `frames_to_led_tracks` mapping core

**Files**: modify `am_configurator/server.py`; add `FramesToLedTracksTests`
to `tests/test_app.py`.

1. Failing tests:
   - `test_parity_with_gif_import` — build a small in-memory GIF (Pillow,
     ~4 frames, per-frame durations) for each model/target combo already
     exercised by `GifImportTests` (CB `display`+`keys`, Relic pair with
     `spotlight_frames`, ALICE incl. `copies`); assert
     `frames_to_led_tracks(images, durations_ms, targets, resample,
     product_id)` equals `gif_to_led_tracks(gif_bytes, ...)` output
     field-for-field.
   - `test_frame_limit_and_timing` — >256 synthetic frames hits the same
     `_MAX_GIF_FRAMES` resample behavior (`timing_resampled` true).
   - `test_rejects_empty_and_bad_target` — `ValueError` on empty frame
     list and unsupported target (same messages as today).
2. Run; confirm failure (`frames_to_led_tracks` missing).
3. Implement: move the per-frame body of `gif_to_led_tracks` (alpha
   flatten → aspect-fit crop → resize → hex list → per-target index remap →
   `_gif_timeline_indices` resample) into
   `frames_to_led_tracks(images: Sequence[Image.Image], durations_ms:
   Sequence[int], targets, resample="box", product_id="CB_XX") -> dict`.
   `gif_to_led_tracks` keeps decode/validation (`_MAX_GIF_BYTES`, GIF
   format check) and delegates; return shape unchanged, except the core
   sets `source_frames`/`decoded_frames` from its inputs and
   `gif_to_led_tracks` overrides them with GIF decode counts exactly as
   today. **Existing `GifImportTests` must pass unmodified** — that is the
   refactor's parity guard.
4. Run `FramesToLedTracksTests` + `GifImportTests`, then full suite.
5. Commit: `refactor: extract frames_to_led_tracks mapping core`

## Task 3 — `llm.py` types, constants, plan validation

**Files**: add `am_configurator/llm.py`; add `GrokTransportTests` (validation
subset) to `tests/test_app.py`.

1. Failing tests (in `GrokTransportTests`):
   - `test_speed_steps_match_server` — `llm.LED_SPEEDS_MS ==
     server._LED_SPEEDS_MS` (single source drift guard).
   - `test_plan_validation_accepts_good_plan` — canonical dict →
     `EffectPlan` via `llm.plan_from_json(data, spec)`.
   - Rejection cases (each raises `llm.ProviderError` with
     `code == "bad_response"`): missing field, wrong type, `frame_ms` not
     in `LED_SPEEDS_MS`, `frame_count < 1` or `> spec.max_frames`,
     `len(keyframe_prompts)` outside `1..min(frame_count,
     MAX_RENDERED_KEYFRAMES)`, `tween` not in `{"crossfade", "step"}`,
     empty prompt string, oversized strings (cap 2000 chars).
2. Run; confirm import failure.
3. Implement `llm.py` (stdlib only): frozen dataclasses `RasterSpec`,
   `EffectPlan`, `RenderedFrames` exactly as design §Data model;
   `class ProviderError(Exception)` with `code`, `message`,
   `retry_after=None` and codes `config/auth/rate_limited/timeout/offline/
   moderation/bad_response/unavailable`; constants `MAX_RENDERED_KEYFRAMES`,
   `MODEL_FRAME_CAPS`, `MAX_PROVIDER_RESPONSE`, `MAX_IMAGE_BYTES`,
   `LLM_TOTAL_BUDGET`, `LED_SPEEDS_MS` (tuple literal equal to server's),
   `XAI_MODELS` (pinned IDs above), `INTERPRETERS`/`RENDERERS` registries
   (populated in Tasks 5–6); `plan_from_json` independent validator.
4. Run; full suite. 5. Commit:
   `feat: add llm provider types, constants, and plan validation`

## Task 4 — xAI transport with typed errors

**Files**: `am_configurator/llm.py`; `tests/test_app.py`
(`GrokTransportTests`).

1. Failing tests, driving `llm._xai_request(url, payload, api_key,
   deadline, opener=None) -> dict` with a fake `opener` callable
   (request → canned response object / raised `urllib.error.*`):
   - success returns parsed JSON dict; `Authorization: Bearer <key>` and
     `Content-Type: application/json` headers set.
   - HTTP 401/403 → `ProviderError("auth")`; 429 with `Retry-After: 7` →
     `("rate_limited", retry_after=7)`; 500/502/503 → `("unavailable")`;
     other 4xx → `("bad_response")`.
   - `URLError`/socket/SSL failure → `("offline")`; expired deadline (pass
     `deadline` in the past) → `("timeout")` **without** calling the opener.
   - body larger than `MAX_PROVIDER_RESPONSE` (bounded `read(n+1)`) and
     non-JSON body → `("bad_response")`.
   - no auto-retry: opener called exactly once per invocation.
   - secret redaction: error `str()` never contains the api key.
2. Run; confirm fail. 3. Implement using `urllib.request` with per-call
   timeout `min(remaining, 30.0)`, bounded read, and the mapping above;
   `opener=None` builds the real urllib opener (never exercised in tests).
4. Run; full suite. 5. Commit: `feat: add xai transport with typed errors`

## Task 5 — `GrokInterpreter`

**Files**: `am_configurator/llm.py`; `tests/test_app.py`.

1. Failing tests (fake transport injected via
   `GrokInterpreter(api_key, transport=...)`):
   - `test_interpret_happy_path` — canned `/v1/responses` structured-output
     payload → validated `EffectPlan`; request body asserts `store: false`,
     model `XAI_MODELS["interpreter"]`, strict schema with
     `additionalProperties: false`, and that the system prompt contains the
     raster size, `spec.max_frames` as a ceiling ("limit, not a goal"
     phrasing), the speed steps, and the sparse-position mask when
     `spec.mapped_positions` is set.
   - `test_schema_valid_but_inconsistent_fails` — plan violating
     `plan_from_json` rules → `bad_response` **before** any render call.
   - `test_moderation_refusal` — refusal payload → `("moderation")`.
   - `test_previous_plan_included` — `interpret(..., previous_plan=...)`
     embeds the prior plan summary (Refine flow).
2. Run; fail. 3. Implement `GrokInterpreter.interpret(prompt, spec,
   deadline, previous_plan=None)`; register in `INTERPRETERS["grok"]`.
4. Run; full suite. 5. Commit: `feat: add Grok interpreter provider`

## Task 6 — `GrokImagineRenderer`

**Files**: `am_configurator/llm.py`; `tests/test_app.py`.

1. Failing tests (fake transport; tiny in-memory PNGs base64-encoded):
   - `test_render_happy_path` — K prompts → K transport calls (sequential,
     `n: 1`, `response_format: "b64_json"`, model
     `XAI_MODELS["renderer"]`) → `RenderedFrames` with K RGB images.
   - `test_url_fields_ignored` — response containing only a `url` field →
     `bad_response` (URL mode never fetched).
   - `test_invalid_base64`, `test_oversized_decoded_image`
     (> `MAX_IMAGE_BYTES`), `test_pixel_cap` (> 4 MP),
     `test_format_whitelist` (GIF payload rejected; PNG/JPEG allowed) →
     `bad_response`.
   - `test_partial_failure_discards` — failure at keyframe 2 of 3 raises;
     no result leaks; exactly 2 calls made.
   - `test_cancel_between_calls` — cancel flag checked between keyframes.
2. Run; fail. 3. Implement `GrokImagineRenderer.render(plan, spec,
   deadline, cancelled=None)` with the design's validation chain (shape →
   b64 → size cap → Pillow open with format whitelist → pixel cap →
   `load()`); register in `RENDERERS["grok"]`. 4. Run; full suite.
5. Commit: `feat: add Grok Imagine keyframe renderer`

## Task 7 — Tween expansion + generation orchestrator

**Files**: `am_configurator/llm.py`; `tests/test_app.py`.

1. Failing tests:
   - `test_expand_step_and_crossfade` — `llm.expand_keyframes(images,
     frame_count, tween)`: K=1 repeats; K==frame_count is identity;
     `step` holds nearest-left keyframe; `crossfade` blends with
     `Image.blend` at evenly spaced positions (assert exact pixel values
     on 2 keyframes → 4 frames).
   - `test_generate_effect_pipeline` — fake interpreter+renderer through
     `llm.generate_effect(prompt, spec, targets, product_id, api_key,
     factories, progress, cancelled)` returns the `/api/led/gif`-shaped
     dict via `server.frames_to_led_tracks`, plus `"plan"` and `"usage"`;
     generated-path fields per design: `source_frames == decoded_frames ==
     frame_count`, `source_duration_ms == frame_count * frame_ms`,
     `timing_resampled is False`, `duration_ms == frame_count * frame_ms`.
   - `test_progress_phases` — progress callback sees `"interpreting"`,
     `"rendering 1/K"`…, `"tweening"`, `"mapping"` in order.
   - `test_deadline_spans_phases` — deadline created once
     (`LLM_TOTAL_BUDGET`) and passed to both providers.
2. Run; fail. 3. Implement (import `frames_to_led_tracks` lazily inside the
   function to avoid a server↔llm import cycle). 4. Run; full suite.
5. Commit: `feat: add tween expansion and generation orchestrator`

## Task 8 — Settings + capabilities endpoints

**Files**: `am_configurator/server.py`; `tests/test_app.py`
(`LedGenerateEndpointTests`, loopback server via `create_server`, requests
carry `X-AM-Token`).

1. Failing tests:
   - `test_settings_round_trip_masks_key` — `POST /api/settings` saves;
     `GET /api/settings` returns `{"set": true, "last4": ...}`, never the
     raw key; posting the mask sentinel → 400.
   - `test_settings_strict_validation` — unknown field/provider → 400.
   - `test_capabilities` — `GET /api/led/capabilities` lists providers,
     `XAI_MODELS`, `MODEL_FRAME_CAPS`, `MAX_RENDERED_KEYFRAMES`, per-model
     target rules (single-CB-target, extra_targets pairs).
   - `test_settings_test_endpoint` — `POST /api/settings/test` with an
     injected fake transport returns `{"ok": true}` / typed error JSON;
     no key configured → 400 with settings hint.
   - `test_requires_auth` — all new routes 403 without token.
2. Run; fail. 3. Implement in the `do_GET`/`do_POST` elif chains using
   `store.load_settings`/`save_settings`/`resolve_xai_key`; key test issues
   one models-list request through the transport (injectable via `_State`).
4. Run; full suite. 5. Commit:
   `feat: add settings and led capabilities endpoints`

## Task 9 — Generation job endpoints (single-flight worker)

**Files**: `am_configurator/server.py` (`_State`, `_Handler`,
`create_server(..., llm_factories=None)`); `tests/test_app.py`.

1. Failing tests (fake interpreter/renderer via `llm_factories`):
   - `test_generate_lifecycle` — `POST /api/led/generate` with
     `{"prompt", "product_id", "targets"}` → `{"job_id"}`; poll
     `GET /api/led/generate/status?job=…` until result; result shape parity
     with `/api/led/gif` plus `plan`/`usage`.
   - `test_single_flight` — second POST while busy (fake provider blocks on
     an event) → 409.
   - `test_cancel` — `POST /api/led/generate/cancel` → job ends cancelled;
     status reports it; page-affecting state untouched.
   - `test_validation_first` — mixed CB targets → 400 before any provider
     call; unknown target → 400; `frame_count` clamped to
     `MODEL_FRAME_CAPS[model]`.
   - `test_missing_key_hint` — no key → 400 mentioning Settings.
   - `test_provider_error_mapping` — fake raising
     `ProviderError("rate_limited", retry_after=7)` → status carries 429 +
     retry-after; `timeout` → 504; `offline` → 503; `bad_response` → 502.
   - `test_no_device_writes` — assert no device module calls during any
     endpoint test (fake/spy on `server` device functions).
2. Run; fail. 3. Implement: `_State` gains `llm_factories`, one worker
   thread, job dict (id, phase, cancel `threading.Event`, result/error kept
   until read or replaced); `RasterSpec` built from `_GIF_LAYOUTS` +
   `MODEL_FRAME_CAPS` (incl. `mapped_positions` for sparse targets,
   `extra_targets` for Relic pair / ALICE copies); routes per design §3.
4. Run; full suite. 5. Commit:
   `feat: add background led generation job endpoints`

## Task 10 — Frontend: Settings panel + Generate-with-AI panel

**Files**: `am_configurator/web/index.html`, `app.js`, `style.css`. No JS
test harness exists — verification is manual (steps below) plus the full
Python suite staying green.

1. Settings panel: provider picker fed by `/api/led/capabilities`; masked
   key `<input type="password">` with Save/Clear; **Test key** button →
   `/api/settings/test`; never renders the raw key (uses `set`/`last4`).
2. LED tab "Generate with AI" panel beside GIF import: prompt textarea,
   target selector reusing GIF target UI with the single-CB-target rule,
   optional frame-count selector, up-front call-count label
   ("1 + K API calls"), Generate → poll status (phase in busy label),
   Cancel; persistent inline error region (typed messages, retry-after on
   429) — not the toast.
3. Pending preview: result lands in `pendingGeneration` state; preview via
   the existing `renderLeds`/`startPlayback` from that state; **Apply to
   page** (mutate + undo checkpoint + dirty mark), **Discard**, **Refine**
   (reopens prompt with previous prompt + plan summary; sends
   `previous_plan`). Failures/cancel leave page + prompt untouched.
4. Privacy disclosure shown before first use, per design §5 copy points;
   scope the existing "without uploading anything" promise to manual/GIF
   tools.
5. Manual check: `uv run am-configurator` (or `python -m am_configurator`)
   → Settings → key masked → Test key; Generate for CB display with fake
   key → inline typed error; layout sane in light/dark.
6. Run full suite. Commit: `feat: add AI generation and settings UI`

## Task 11 — Packaging + frozen smoke test

**Files**: `packaging/am_configurator.spec`, `tests/test_packaging.py`, and
the `--smoke-test` implementation (locate via `grep -rn "smoke-test"
am_configurator/`).

1. Failing test in `tests/test_packaging.py`: spec text includes
   `"am_configurator.llm"` in `hidden_imports`; smoke-test source includes a
   fake-transport generation step.
2. Implement: add hidden import; extend `--smoke-test` to run one
   fake-transport `generate_effect` end-to-end in-process (exercises `ssl`
   context creation, JSON, base64, Pillow decode); add opt-in flag
   (`AM_SMOKE_NET=1`) for the real-TLS HEAD check. No new third-party deps,
   so `THIRD_PARTY_NOTICES` is unchanged.
3. Run full suite. If on the packaged machine: rebuild PyInstaller bundle
   and run the frozen smoke test. Commit:
   `build: bundle llm module and extend frozen smoke test`

## Task 12 — Final verification + docs

1. Full suite green; `git log --oneline` shows one commit per task.
2. Follow design §Verification: manual happy path (with a real key if
   available — otherwise fake-transport path), negative paths (no key, bad
   key, 429, timeout, concurrent 409, cancel).
3. Update `docs/design/llm-led-generator.md` status from draft to
   implemented (note any deviations); update `.agents/state.md` Now/Next.
4. Commit: `docs: mark llm led generator design implemented`

---

**Worst-case spend guard (recap)**: ≤ 1 + `MAX_RENDERED_KEYFRAMES` = 17
provider calls per user action; single-flight; no auto-retry of paid calls;
`LLM_TOTAL_BUDGET` monotonic deadline across phases.
