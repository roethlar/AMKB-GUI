# Optional AI Backends and Procedural Lighting Generation

**Status:** Product decisions approved on 2026-07-21. Tasks 1–5 landed in
`d7eedc2`, `9780945`, `d748898`, `8721681`, and `07260ea`. The owner amended and authorized the
remaining direction on 2026-07-21: local inference is primary, the application
never downloads model weights, users select their own local GGUF model, and
model qualification evidence does not gate the feature.

## Objective

Replace the visible xAI still/video proof flow with one optional prompt-to-procedural-animation capability. AI is off by default and absent from the normal application UI unless the user has explicitly enabled it and the selected backend has passed setup. The two supported backend classes are:

1. The primary app-managed local GPU runtime using a GGUF model selected by the
   user from local storage.
2. A secondary curated API model, initially xAI, with its key stored in the
   operating-system credential store.

Both backends return the same strict animation-recipe object. All animation rendering, exact device-frame generation, previewing, mapping, banking, review, and Apply behavior remains local and backend-independent.

## Approved Product Decisions

- Manual lighting editing is the complete default product. No Generate control, AI copy, AI route, model control, setup warning, or AI empty-state action appears outside Settings while AI is disabled or invalid.
- Settings always exposes one collapsed **Optional AI features** setup section. The user explicitly chooses Local model or API model.
- Local AI requires a supported GPU and enough usable GPU or unified memory. There is no supported CPU fallback.
- Ollama is not a release dependency. The application owns the local runtime lifecycle. The existing Ollama CLI proof remains developer tooling until deliberately removed.
- The local model is neither bundled nor downloaded by the application. The
  user selects an existing local GGUF file through a native file picker and may
  replace that selection at any time.
- Corpus qualification is developer evidence, not a release catalog gate. A
  selected model becomes usable after the production runtime proves it can
  return one schema-valid recipe; later recipe or quality failures are normal
  per-generation failures and do not disable local AI globally.
- API mode does not require local GPU support. It requires a curated provider and model, an OS-stored credential, and an explicit privacy/cost acknowledgment and setup test.
- A backend is configured only after it produces a valid recipe through the production schema. Merely finding a binary, model file, or API key is not enough.
- If a previously configured backend becomes invalid, AI entry points disappear from the main UI and Settings shows a repair state. A transient API network outage is an operational error, not automatic configuration loss; authentication or removed-model failures invalidate setup.
- Generated animations and historical still/video assets remain normal Library content when AI is disabled. Disabling AI never deletes or hides saved work.
- Generation always creates a preview for explicit user review. It never mutates a document or writes to a device automatically.

## Existing Evidence and Constraints

- `am_configurator/local_animation.py` proves that a model-generated strict recipe can drive a deterministic periodic Pillow renderer and the existing `frames_to_led_tracks` mapping core.
- `ornith:latest` under Ollama produced a valid six-layer dense aurora recipe. Its rendered result kept more than 91% of Relic raster positions visibly active in every frame.
- `gemma4:12b-mlx` ignored Ollama's requested JSON schema. Model presence therefore cannot be treated as model qualification.
- The current browser always contains a Generate button and AI dialog. Current eligibility is inferred from an xAI key and Library folder, which does not satisfy the new capability boundary.
- Settings schema v2 stores xAI keys in `settings.json`. The new decision requires migration to the OS credential store with no plaintext fallback.
- The current durable Library schema is tied to concept candidates and video attempts. It must remain able to read historical jobs while adding procedural jobs.
- Supported distribution targets remain macOS, Windows, and Linux. The local backend may be unavailable on a machine while API mode and the rest of the application remain fully supported.

## Release Architecture

```text
Settings only while disabled
        |
        +-- Local setup ----------------------------+
        |   GPU probe -> choose local GGUF -> test  |
        |                                            v
        +-- API setup -----------------------> RecipeProvider
            key vault -> acknowledgment -> test     |
                                                     v
manual workspace <--- hidden unless ready --- Generate prompt
                                                     |
                                                     v
                                    strict AnimationRecipe validation
                                                     |
                                                     v
                                      periodic local Pillow renderer
                                                     |
                                                     v
                             exact device frames + preview + LED mapping
                                                     |
                                                     v
                                  durable Library -> Review -> Apply
```

### Capability Contract

Add `am_configurator/ai_capability.py`. It owns the only computation of whether AI may be exposed or invoked. The public status shape is exact and pathless:

```json
{
  "schema_version": 1,
  "enabled": false,
  "backend": null,
  "ready": false,
  "reason": "disabled",
  "local": {
    "supported": false,
    "gpu_backend": null,
    "runtime_verified": false,
    "model_selected": false,
    "model_filename": null,
    "model_verified": false,
    "setup_tested": false
  },
  "api": {
    "provider": "xai",
    "model_id": "grok-4.5",
    "credential_set": false,
    "disclosure_current": false,
    "setup_tested": false
  }
}
```

Allowed top-level reasons are `disabled`, `backend_unselected`, `gpu_unsupported`, `runtime_unavailable`, `model_missing`, `model_invalid`, `credential_store_unavailable`, `credential_missing`, `disclosure_required`, `setup_required`, `auth_invalid`, `model_unavailable`, and `ready`. Unknown internal errors map to `setup_required`; paths, subprocess output, credentials, and provider response bodies never cross the loopback API.

The browser uses only `enabled && ready` to reveal AI entry points. Every generation endpoint independently recomputes and enforces the same gate; the browser is never the authority.

### Settings Schema v3

Replace active `llm` settings with an `ai` section:

```json
{
  "schema_version": 3,
  "ai": {
    "enabled": false,
    "backend": null,
    "local": {
      "setup_fingerprint": null
    },
    "api": {
      "provider": "xai",
      "model_id": "grok-4.5",
      "setup_fingerprint": null,
      "disclosure_version": null,
      "disclosure_at": null
    }
  },
  "library": {
    "current_root": null,
    "roots": []
  },
  "generation": {
    "loop_mode": "smooth"
  }
}
```

`enabled` records user intent. Saving `enabled: true` is rejected unless the selected backend is currently ready. A later runtime, model, credential, or provider-auth failure leaves intent enabled but makes public `ready` false, thereby hiding the main-UI entry and exposing repair status only in Settings.

Migrate v1/v2 settings without losing Library roots or loop mode. Obsolete still-count and concept/video model preferences do not enter the active v3 shape. Historical manifests already own the exact models used for their work.

### Credential Storage and Migration

Add `am_configurator/credentials.py` behind a narrow injected protocol:

```python
class CredentialStore(Protocol):
    def available(self) -> bool: ...
    def get(self, provider: str) -> str | None: ...
    def set(self, provider: str, value: str) -> None: ...
    def delete(self, provider: str) -> None: ...
```

Use the maintained Python `keyring` package for macOS Keychain, Windows Credential Locker, and Linux Secret Service. Pin it in `pyproject.toml` and frozen requirements. The adapter must reject null, plaintext, alternate-file, or otherwise non-secure backends; there is no fallback to `settings.json`. Tests inject an in-memory fake and never touch the developer's real credential store.

Use one fixed application service identifier and one provider username. Raw credentials may exist only in the credential adapter and provider instance. They never enter browser state, settings JSON, manifests, logs, errors, subprocess arguments, or crash chains. Preserve `XAI_API_KEY` as an explicit environment override for development and automation; report only that an external credential exists.

For an existing v2 plaintext key:

1. Attempt migration under the settings lock.
2. Write the key to the secure credential store and read it back for exact verification.
3. Only after successful verification, atomically write schema v3 without the key.
4. If secure storage is unavailable or verification fails, leave the original v2 file untouched, return AI disabled with `credential_store_unavailable`, and let Settings offer a retry. Never delete or silently copy the only credential.

### Shared Recipe Contract and Quality Gate

Move the backend-neutral schema, semantic validator, periodic renderer, GIF writer, and exact mapping adapter from `local_animation.py` into `am_configurator/procedural.py`. Keep `local_animation.py` as a thin developer CLI adapter.

Version the recipe schema and add explicit output intent:

```json
{
  "schema_version": 1,
  "name": "Aurora energy field",
  "density": "dense",
  "background": "#080810",
  "palette": ["#00E5C9", "#3D7AFF", "#8B4FFF", "#FF00CC"],
  "layers": []
}
```

`density` is `sparse`, `balanced`, or `dense`. System guidance defaults to `balanced`; it uses `sparse` only when the prompt explicitly asks for isolated points or darkness, and `dense` for whole-board, field, wash, aurora, fire, ocean, or similarly continuous effects. Keep the bounded primitive vocabulary, exact keys, color-index bounds, and periodic phase rules from the proof. Increase the layer ceiling only if the qualification corpus proves the renderer remains within its CPU and output-size budgets.

After rendering but before banking a ready result, compute deterministic quality metrics:

- exact dimensions and device frame cap;
- final-to-first seam no greater than `1.25 * maximum ordinary adjacent difference + 0.01`;
- non-zero ordinary motion;
- peak brightness greater than 180;
- sparse: no frame has more than 60% of pixels above RGB channel 32;
- balanced: every frame has at least 35% and no frame more than 95% above 32;
- dense: every frame has at least 70% above 32.

Local inference may retry semantic or quality-invalid recipes at most twice after the initial attempt, with the validation reason and a new deterministic seed. API inference is exactly one paid request per user action and is never automatically replayed; a schema or quality failure is banked as a typed failed job and requires another explicit Generate.

### Backend-Neutral Provider

Add `am_configurator/recipe_provider.py`:

```python
@dataclass(frozen=True)
class RecipeRequest:
    prompt: str
    width: int
    height: int
    frame_count: int
    density_default: str

@dataclass(frozen=True)
class RecipeResult:
    recipe: dict
    backend: str
    provider: str
    model_id: str
    usage: dict | None

class RecipeProvider(Protocol):
    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult: ...
```

Both concrete providers send the same system instructions and validate through `procedural.validate_recipe`; provider output never selects file paths, device identifiers, costs, or Apply destinations.

#### API provider

Implement `XaiRecipeProvider` by reusing the bounded/redacted xAI transport in `llm.py` and the current Responses endpoint. The initial curated model is the existing `grok-4.5`; retain the catalog seam for later API recipe models. Use `store: false`, strict JSON schema, one request, one monotonic deadline, exact usage retention when reported, and existing typed auth/rate-limit/timeout/offline/bad-response mapping.

API setup uses an explicit **Test and enable** action. It performs one minimal structured-recipe request through the real production adapter after Settings shows its estimated maximum cost and current privacy disclosure. Tests and builds always inject a fake transport and never make this call. A successful setup stores a fingerprint of provider, model, credential identity hash, recipe-schema version, disclosure version, and test timestamp; never the credential. Changing any component invalidates the fingerprint.

#### Local provider

Implement `ManagedLocalRecipeProvider` against the app-owned runtime. It
performs no external network access. The provider accepts only the current
model selection resolved from the model manager's private attestation; HTTP
callers cannot supply paths, endpoints, or model identifiers.

Use grammar-constrained JSON output in addition to semantic validation. Bound context, output tokens, response bytes, wall time, GPU layers, and concurrent requests. Cancellation terminates and then kills the child process using argument arrays, never a shell. Keep a verified runtime warm only while the app is open and only after AI use; stop it after a short idle interval and always during application exit.

### Managed Local Runtime

Use `llama.cpp` release candidate `b9637` at commit `aedb2a5` because its official runtime supports Metal, CUDA/Vulkan, an OpenAI-compatible local server, and grammar-constrained output. Task 2 exercised that exact runtime; implementation may not silently track `main` or a newer release. Before promoting it, check the official security-advisory record; a vulnerable pin requires a documented plan amendment and runtime requalification. Mirror the existing FFmpeg supply-chain pattern:

- `packaging/llama_runtime_manifest.json` owns source URL, immutable revision, archive SHA-256, MIT license metadata, build flags, runtime capabilities, and per-platform artifact names.
- `build_tools/build_llama_runtime.py` verifies the source archive before extraction, rejects unsafe members, builds offline from the verified source, and writes a runtime attestation.
- `am_configurator/local_ai_runtime.py` resolves only the frozen bundled runtime or an explicit attested developer override. It never searches `PATH` and never discovers Ollama.
- macOS arm64 builds enable Metal; Windows x64 and Linux x64 builds enable Vulkan. Additional CUDA-specific artifacts are deferred until measured need justifies their packaging cost.
- Runtime launch binds only to `127.0.0.1`, uses an app-generated per-process bearer token, disables the bundled web UI, allows one slot, uses a small fixed context, and requests full GPU offload. A CPU-only or partial-offload setup test fails local eligibility.
- Runtime stdout/stderr is bounded and sanitized. The random port, token, model path, and raw diagnostics never enter the browser or Library.

The installer contains the runtime and its notices but no model weights. Native
CI builds and frozen smoke tests verify runtime location, attestation, launch
arguments, native model selection, and fake inference without downloading a
model.

### User-Selected Local Models

The Qwen3 4B Q4_K_M qualification in
`docs/verification/2026-07-21-qwen3-4b-q4-k-m/` remains useful evidence about
the corpus, renderer, and runtime, but its failed cases do not select or reject
models for users. There is no release model catalog.

Settings exposes **Choose model file** through a native picker restricted to
regular `.gguf` files. Browser requests never contain a path. The model manager
stores a private local attestation containing the canonical selected path,
basename, size, file identity, modification time, and SHA-256. It re-hashes
after identity or metadata changes and rejects missing files, symlinks,
non-regular files, and files outside conservative size bounds.

Selecting a file makes it available for testing but does not enable AI. **Test
and enable** launches only the pinned app runtime, requests full GPU offload,
and asks the selected model for one minimal recipe through the production JSON
grammar and semantic validator. Success stores a fingerprint of runtime
attestation, model SHA-256, recipe-schema version, and setup-test version.
Changing the file invalidates the fingerprint. Failure keeps the selection and
shows a pathless reason so the user can select another model.

The committed qualification corpus remains a repeatable developer comparison
tool for any locally available model. It never triggers a download, never
changes the user's selection, and is not required for local UI availability or
release packaging.

**Clear selection** removes only the private attestation and setup fingerprint.
The application never copies, moves, modifies, downloads, or deletes the
user's model file.

### Durable Procedural Generation

Add a procedural job mode to `GeneratedAssetLibrary` rather than bypassing the Library. Bump the manifest schema with a read-compatible v1 normalizer:

- existing manifests normalize to `pipeline: "legacy_video"` and remain browsable;
- new jobs use `pipeline: "procedural"`;
- add `procedural_attempts` while retaining old concept/video arrays for v1 compatibility;
- add asset kinds for `recipe` (`application/json`) and exact `raster_animation` (`image/gif`); reuse `preview_animation` and `mapped_result`;
- every asset is banked through the existing intent, hash, fsync, and atomic-publication boundary;
- no model output, secret, local path, runtime diagnostic, or provider response body enters a manifest.

Add `ProceduralGenerationCoordinator` with the shared process-wide generation admission gate. Its ordered phases are:

1. Validate prompt, selected destination snapshot, configured Library, and current AI capability before any model or provider call.
2. Create and fsync the durable job manifest.
3. Record the selected backend/model and estimated API cost, if any.
4. Mark the recipe operation about to start before the external API request or local inference.
5. Generate and validate one recipe.
6. Bank `recipe.json`.
7. Render exactly the active device family's maximum frame count at its fastest legal firmware duration.
8. Run the deterministic quality gate.
9. Bank exact-raster GIF, enlarged preview GIF, mapped LED JSON, and summary metadata.
10. Publish `ready` for review without applying anything.

Local cancellation stops inference or rendering and publishes `cancelled`. API cancellation before the request prevents spend; after submission it only hides foreground progress and must not cause an automatic retry. A startup reconciliation pass adopts completely banked procedural artifacts or marks an interrupted local operation retryable. It never repeats an API request automatically.

### Authenticated HTTP API

Keep all routes behind the existing loopback token and strict exact-body validation:

- `GET /api/ai/status` — public capability view above.
- `POST /api/settings/ai` — save selected backend/configuration or disable AI; cannot force readiness.
- `POST /api/settings/credential` — set/clear one curated provider credential in the OS store.
- `POST /api/ai/test` — explicit selected-backend production health test; API mode may spend only after the Settings disclosure confirmation.
- `POST /api/ai/local/select` — open the native GGUF picker and attest the
  selected local file; no caller-supplied path is accepted.
- `POST /api/ai/local/clear` — clear only the app's selection and attestation;
  never delete or modify the model file.
- `POST /api/lighting/effects` — create one durable procedural job.
- Existing job, Library, asset, cancel, and Apply/read endpoints remain the polling and review surfaces.

Generation rejects `disabled`, unready, backend-mismatch, missing-Library, incompatible-target, and concurrent-operation states before inference. The server chooses frame count, duration, raster dimensions, mapping targets, and active model from canonical device/capability data; the browser cannot override them.

Stop accepting new `/api/lighting/concepts`, `/animate`, `/process`, and legacy `/api/led/generate` operations once the procedural route passes acceptance. Keep authenticated reads and startup recovery required to preserve already-banked legacy jobs. Return a stable local `410` for retired mutation routes rather than silently redirecting to a different paid behavior.

### Browser and Settings Behavior

`index.html` ships the Generate trigger and AI dialog hidden, preventing first-paint flicker and accessibility exposure. After settings/status load, `app.js` reveals them only for `enabled && ready`.

When AI is not ready:

- manual Workspace and playback/paint/import controls are unchanged;
- Library remains fully visible;
- Library empty states do not offer Generate;
- no Create hash route opens the AI dialog;
- no persistent AI job strip appears unless an already-running durable job must finish banking;
- no key/model/provider/cost warnings appear outside Settings.

Settings begins with one disabled **Optional AI features** switch and presents
Local model first. Turning it on reveals backend choice but does not expose
main-UI generation. Local setup shows GPU/runtime status, selected GGUF
filename/size, Choose model file, Test and enable, and Clear selection. API
setup remains secondary and shows provider, curated recipe model, password
input, credential-store status, privacy/cost disclosure, Test and enable, and
Remove credential. Setup failures stay on this route with one actionable repair
reason.

The generation dialog becomes a single flow:

1. Prompt and destination summary.
2. Generate one animation.
3. Progress while recipe and frames are banked.
4. Animated exact-raster preview plus recipe summary.
5. Apply or close; Apply remains one undoable document-only mutation.

There are no concept stills, video controls, provider-call counts, model controls, setup links, or auto-Apply behavior in this dialog. Backend identity and API cost history belong in Settings and Library metadata, not the working canvas.

## Implementation Tasks and Commit Boundaries

Every task begins with a focused test observed failing, then the implementation, then focused green verification. Commit each task before beginning the next.

### Task 1 — Shared procedural contract and quality corpus

Files: `am_configurator/procedural.py`, `am_configurator/local_animation.py`, `tests/test_procedural.py`, `tests/fixtures/procedural_prompt_cases.json`, `build_tools/qualify_recipe_model.py`.

- Extract backend-neutral proof code without changing current CLI output.
- Add schema version/density and deterministic quality metrics.
- Add dense/balanced/sparse, exact-frame, seam, motion, brightness, determinism, mapper-parity, malformed-recipe, and resource-budget tests.
- Run the current Ornith proof through the new contract to prove no regression, but do not make Ollama an app dependency.

Commit: `feat: establish procedural animation contract`.

### Task 2 — Benchmark the first local model candidate

Files: qualification corpus/results under `docs/verification/` and qualification tooling.

- Evaluate the pinned Qwen candidate through the production grammar/schema and committed corpus.
- Record machine, runtime revision, per-case result, latency, density/motion metrics, and gallery paths without committing model weights.
- Preserve the result as comparative evidence without weakening schema or
  metrics. Do not create a release model catalog or make the result a gate on
  user-selected local inference.

Commit: `docs: reject local recipe model`.

### Task 3 — Pinned local runtime and user-selected model

Files: runtime manifest/license, build helper, `am_configurator/local_ai_runtime.py`, `am_configurator/local_model.py`, packaging and focused tests.

- Mirror verified FFmpeg source/build/runtime resolution.
- Implement GPU/full-offload probe, bounded subprocess lifecycle, private native
  GGUF selection/verification/attestation/clear, and pathless public status.
- Add malicious archive, caller-path, symlink, non-regular file, wrong-extension,
  size-bound, tamper, no-GPU, partial-offload, and process-timeout tests. Prove
  selection and clearing never copy, modify, download, or delete model weights.

Commit: `feat: manage local GPU recipe runtime`.

### Task 4 — Secure credential store and settings v3

Files: `pyproject.toml`, lockfile, frozen spec, `am_configurator/credentials.py`, `am_configurator/store.py`, settings tests.

- Add fail-closed keyring adapter and in-memory test double.
- Implement v1/v2 to v3 migration, verified plaintext-key transfer, retry state, environment override, strict section updates, and secret redaction.
- Prove secure-backend absence never writes a key to disk and never loses the only v2 copy.

Commit: `feat: move AI credentials to OS storage`.

### Task 5 — Recipe providers and capability service

Files: `am_configurator/recipe_provider.py`, `am_configurator/ai_capability.py`, `am_configurator/ai_catalog.py`, provider/capability tests.

- Implement the primary managed-local provider and secondary xAI provider behind
  the shared protocol.
- Implement setup fingerprints, exact readiness reasons, local retry policy, one-call API policy, typed errors, usage/cost accounting, and invalidation rules.
- Prove disabled/unready states perform no subprocess launch, file mutation,
  network request, or credential lookup beyond the capability check required.

Commit: `feat: add interchangeable recipe backends`.

### Task 6 — Durable procedural jobs

Files: `am_configurator/library.py`, `am_configurator/procedural_generation.py`, `am_configurator/generation.py` only for shared admission/recovery seams, Library/coordinator tests.

- Add read-compatible manifest v2 and procedural asset kinds.
- Implement durable ordered phases, exact max-frame/fastest-duration rendering, quality gate, atomic banking, cancellation, reconciliation, and no automatic API replay.
- Prove old manifests remain byte-preserved unless a required recovery update occurs and old assets remain browseable with AI disabled.

Commit: `feat: bank procedural lighting jobs`.

### Task 7 — Capability and generation routes

Files: `am_configurator/server.py`, `am_configurator/desktop.py`, server endpoint tests.

- Add strict authenticated setup/status/model/credential/effect routes.
- Enforce server-side exposure gate and canonical device generation parameters.
- Retire new mutations through old xAI still/video routes only after the new route passes full offline lifecycle tests.
- Keep fake-transport frozen smoke; add fake-local-runtime smoke.

Commit: `feat: expose optional procedural generation API`.

### Task 8 — Hidden-by-default Settings and generation UI

Files: `am_configurator/web/index.html`, `app.js`, `lighting_state.js`, `style.css`, browser tests.

- Make disabled first paint contain no exposed AI controls.
- Implement local/API setup panels and repair states.
- Replace Concepts/Animate/Video UI with prompt/progress/review/apply.
- Preserve manual layout, keyboard operation, zoom/narrow-window behavior, Library browsing, and explicit Apply.
- Test all capability-state transitions and assert no AI text/control is accessible outside Settings while disabled or invalid.

Commit: `feat: gate optional AI setup and generation`.

### Task 9 — Packaging, release checks, and legacy compatibility

Files: build scripts, native workflows, frozen spec, notices, smoke tests, docs/state.

- Bundle and attest the platform runtime without model weights.
- Add installer checks that AI-disabled launch never starts the runtime or contacts model/provider hosts.
- Run frozen fake local/API generation smokes, a real user-selected local-model
  setup/generation smoke on each platform claimed as local-capable, historical
  Library acceptance, and manual visual checks.
- Build through `python build.py --skip-sync` so the native build version advances; never invoke PyInstaller directly.
- Update state with exact passed platforms and leave unsupported local platforms API-only.

Commit: `build: package optional local AI runtime`, followed by a docs-only verification record.

## Verification

For every new regression test, temporarily restore the pre-fix behavior, observe the test fail, restore the implementation, and observe it pass.

Run the repository verification entry point after every code task and before completion:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/app.js
uv build
```

Native release verification additionally requires:

- versioned build through `python build.py --skip-sync`;
- frozen smoke with network disabled and AI disabled;
- frozen fake local and fake API setup/generation paths;
- runtime attestation and license presence;
- proof that the installer contains no model weights or credential values;
- real user-selected local-model setup/generation smoke on every platform
  claimed as local-AI supported;
- manual checks at wide, narrow, and zoomed layouts for both disabled and ready states;
- no provider call or hardware write without a separate explicit owner go.

## Non-Goals

- No CPU local inference fallback.
- No browser-supplied model paths, model downloads, arbitrary Hugging Face
  repositories, custom API base URLs, or arbitrary provider model IDs. Local
  model paths enter only through the native GGUF picker.
- No bundled model weights in installers.
- No image-generation, image-to-video, or direct frame-by-frame generative GIF path in the new flow.
- No multiple generated variations in one action until the single procedural result proves useful across the qualification corpus.
- No automatic Apply, keyboard write, paid retry, API setup probe, model
  download, model copy, or model deletion.
- No deletion or conversion of historical Library jobs.

## Rollback and Failure Behavior

- If a selected local model fails setup or generation, retain the selection,
  show a pathless actionable error, and allow immediate reselection. One model's
  failure never disables the local feature or changes release scope.
- If the secure credential backend is unavailable, local AI remains usable; API setup is unavailable and no plaintext fallback appears.
- If the selected backend loses readiness, hide only AI entry points. Manual editing and Library access continue.
- If runtime packaging fails on one platform, that platform remains API-only
  rather than blocking the application release; model weights are never a
  packaging input.
- If the new procedural flow fails acceptance, keep it disabled by default and retain the isolated CLI proof; do not restore the rejected still/video UI as a fallback.
