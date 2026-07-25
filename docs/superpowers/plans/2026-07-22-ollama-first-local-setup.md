# Ollama-First Local Model Setup

**Status:** The original implementation landed on 2026-07-22 in `57fb05a`,
`440c5ac`, `6815337`, `8021ecf`, and `9f2174a`. The surviving Ollama/API-only
behavior was independently hardened and red-proven in `7ded2dc`, `ed53fa2`,
`3eec04c`, `37a7449`, `2186a62`, `d42f01e`, `267dc56`, and `9ae2306`; the exact
reproducible evidence is recorded below. This plan implements the 2026-07-22
Ollama-first local model decision and supersedes the direct-GGUF onboarding
portions of the 2026-07-21 Optional AI plan.

**Current scope correction:** A later owner decision on 2026-07-22 removes the
advanced direct-GGUF fallback and every bundled or application-managed
llama.cpp path. The shipped backends are fixed-loopback Ollama and the curated
API only. Direct-GGUF language below is retained solely as historical
implementation context; the holistic remediation plan owns its deletion.

## Regression Guard Evidence

All commands below were rerun from the repository root after `9ae2306` and
passed. During each named remediation slice, the stated production behavior
was temporarily removed or weakened, the same focused command failed for the
intended assertion, the behavior was restored, and the command passed. The
temporary mutations were not committed.

1. **F08 — proxy immunity (`7ded2dc`)**

   ```sh
   uv run --frozen python -m unittest tests.test_ollama_client.OllamaClientTests.test_actual_discovery_request_ignores_environment_proxy tests.test_app.GrokTransportTests.test_actual_xai_request_ignores_environment_proxy -v
   ```

   Removing either transport's explicit empty `ProxyHandler` made its real
   request path target the configured sentinel proxy and fail.

2. **F09 — model-picker behavior (`ed53fa2`)**

   ```sh
   node --test tests/web/lighting_state.test.js tests/web/lighting_shell.test.js
   ```

   Removing the unavailable/removed/digest-changed/transient projection
   branches made the executable picker-state regressions fail.

3. **F36 — offline desktop smoke execution (`3eec04c`)**

   ```sh
   uv run --frozen python -m unittest tests.test_desktop.DesktopSmokeTests.test_every_offline_ai_smoke_executes_without_external_side_effects -v
   ```

   Replacing `_run_ollama_recipe_smoke` with a no-op made the provider/render/
   mapping counters fail.

4. **F37 — failure-sensitive smoke guards (`37a7449`)**

   ```sh
   uv run --frozen python -m unittest tests.test_desktop.DesktopSmokeTests.test_recipe_smokes_construct_real_adapters_and_propagate_stage_failures -v
   ```

   Swallowing the injected API rendering failure made its propagation subtest
   fail.

5. **F38 — route/discovery integration (`2186a62`)**

   ```sh
   uv run --frozen python -m unittest tests.test_ai_routes.OptionalAIRouteTests.test_real_ollama_discovery_and_selection_cross_the_server_contract -v
   ```

   Corrupting `OllamaModel.public()` to publish a zero digest made the exact
   route contract fail before selection could persist it.

6. **F39 — eligibility defenses (`d42f01e`)**

   ```sh
   uv run --frozen python -m unittest tests.test_ollama_client.OllamaClientTests.test_discovery_is_fixed_and_returns_sorted_public_models tests.test_ollama_client.OllamaClientTests.test_each_ineligible_inventory_entry_is_filtered_independently tests.test_ollama_client.OllamaClientTests.test_inventory_accepts_512_entries_rejects_513_and_maps_404 -v
   ```

   Removing the bare `:cloud` suffix exclusion admitted that model and failed
   its independent subtest.

7. **F40 — same-name digest replacement (`267dc56`)**

   ```sh
   uv run --frozen python -m unittest tests.test_ai_capability.CapabilityTests.test_same_name_digest_replacement_requires_selection_and_new_setup -v
   ```

   Weakening selected-model identity matching to the name alone changed the
   replacement from `model_unavailable` to `setup_required` and failed the
   guard.

8. **F41 — retry ceiling (`9ae2306`)**

   ```sh
   uv run --frozen python -m unittest tests.test_procedural_generation.ProceduralGenerationTests.test_real_ollama_provider_stops_after_two_corrected_retries tests.test_procedural_generation.ProceduralGenerationTests.test_api_quality_failure_is_one_charged_call_and_never_retried -v
   ```

   Permitting a fourth local attempt triggered the fake client's fourth-call
   trap and changed the durable terminal error, making the guard fail. The API
   companion remained exactly one request.

## Objective

Restore the proven Ollama recipe path as the normal Local AI experience. When
the user opens Optional AI Settings, the application discovers models already
installed in the fixed local Ollama service, presents those models by name, and
lets the user test and enable one. The application has no model-download path.
The private GGUF picker and pinned llama.cpp runtime described by the original
plan are superseded historical implementation and are not release scope.

## Product and Safety Boundaries

- Local Ollama is fixed to `http://127.0.0.1:11434`. There is no endpoint field,
  environment override, host discovery, or redirect following.
- Discovery uses only `GET /api/tags`. Recipe inference uses only
  `POST /api/chat`. Production application code contains no Ollama pull, create,
  copy, delete, or weight-management operation.
- Entries with `remote_model` or `remote_host` metadata are excluded. Invalid
  names, invalid digests, non-positive sizes, or models without completion
  capability are excluded. This keeps Local AI local even when Ollama exposes
  cloud aliases.
- The app disables environment proxies, rejects redirects, bounds response
  bytes and time, validates every response shape, and never exposes raw service
  output through the browser API.
- Model selection is server-authoritative. A submitted name is accepted only
  when the same discovery response supplies a valid local digest for it.
- Setup and generation use the same strict `AnimationRecipe` schema and
  validator. Local semantic or quality retries remain bounded at two retries;
  the API backend remains one paid request per user action.
- Manual lighting, hidden-until-ready AI entry points, durable banking,
  explicit Review/Apply, and device-write safety do not change.

## Settings Schema v4

Bump the active settings schema from v3 to v4. The local section becomes:

```json
{
  "source": "ollama",
  "model_id": null,
  "model_digest": null,
  "setup_fingerprint": null
}
```

`source` is exactly `ollama` or `gguf`. Ollama requires `model_id` and
`model_digest` to be both set or both null. GGUF requires both to be null and
continues to keep its path and attestation exclusively in the existing private
model manager.

Migration from v3 is lossless for Library roots, loop mode, API disclosure,
API readiness, and Local readiness. A v3 Local setup fingerprint selects the
`gguf` advanced source and preserves the fingerprint because it represents an
existing tested managed model. Otherwise migration defaults to `ollama` with
no selected model. As before, credentials never enter settings JSON.

Changing local source or Ollama model atomically clears the Local setup
fingerprint. Selecting a model records the exact name and digest returned by
the current fixed-loopback discovery call. No model bytes or filesystem path
are stored.

## Ollama Transport and Provider

Add one production Ollama client seam used by both setup discovery and recipe
generation. It returns bounded immutable model records and maps local service
failures to stable pathless errors. Dependency injection must keep the complete
automated suite offline.

Add `OllamaRecipeProvider` alongside `ManagedLocalRecipeProvider`. It accepts a
server-selected model record and sends the shared system prompt, user prompt,
JSON schema, deterministic per-attempt seed, non-streaming flag, and bounded
generation options to `/api/chat`. It validates `message.content` through the
same backend-neutral validator and returns:

```json
{
  "backend": "local",
  "provider": "ollama",
  "model_id": "the-selected-name"
}
```

The provider implements the existing `generate_attempt` retry contract so the
procedural coordinator remains backend-neutral. The developer CLI delegates to
this production client instead of maintaining a divergent Ollama transport.

## Capability Contract

Keep `backend: "local"` as the public backend class and add a local `source`.
For Ollama, status reports only stable non-secret data: service availability,
selected model name, whether it remains installed with the recorded digest,
and setup-tested state. It must not enumerate all installed models in the
general capability response.

The Ollama setup fingerprint binds:

- fixed provider identity `ollama-loopback-v1`;
- selected model name and SHA-256 digest;
- recipe schema version; and
- setup test version.

Ollama Local readiness does not depend on the packaged llama.cpp runtime, the
GGUF model manager, or a host GPU probe. GGUF advanced readiness retains all
three existing requirements and its existing runtime/model fingerprint.

Generation resolves the provider from the currently ready local source.
Durable manifests record `provider: "ollama"` and the selected Ollama name, or
the existing `provider: "llama.cpp"` and GGUF filename for advanced mode.

## Authenticated Loopback API

Add `GET /api/ai/local/models` with no query fields. It performs fixed-loopback
discovery and returns an exact bounded view:

```json
{
  "available": true,
  "models": [
    {
      "model_id": "ornith:latest",
      "digest": "...",
      "size_bytes": 5629110568,
      "parameter_size": "9.0B",
      "quantization": "Q4_K_M"
    }
  ]
}
```

Unavailable service returns `available: false` and an empty list without
turning expected absence into a server error. Raw Ollama errors never cross the
route.

Change `POST /api/ai/local/select` to require exactly `model_id`; the server
rediscovers models and persists the matching name/digest. Add
`POST /api/ai/local/gguf/select` with an empty body for the native advanced
picker. `POST /api/ai/local/clear` clears the current source's selection and
fingerprint without deleting a model or file. All three mutations share the
existing generation admission gate.

## Settings UI

The primary Local panel says Ollama, not GGUF. It includes:

- current service state;
- a select control populated with installed local model names;
- Refresh models;
- Select model; and
- Test & enable.

If Ollama is unavailable, explain that Ollama must be installed and running. If
it has no eligible installed models, explain that the user installs models in
Ollama; do not offer an application download. Preserve selection if refresh
temporarily fails and clearly show when a previously selected model is no
longer available.

Put the current GGUF chooser, selected filename, Test & enable, clear action,
and GPU/runtime diagnostics under a collapsed `Advanced: direct GGUF` section.
Selecting that fallback explicitly changes the local source to `gguf`.

Browser calls are limited to authenticated local routes. Playwright may be used
as an external acceptance tool but is not an application or packaged runtime
dependency.

## Implementation Slices

1. Record the superseding decision and this approved plan.
2. Add the hardened Ollama discovery/generation client and provider, refactor
   the developer adapter to reuse it, and cover valid, malformed, remote-model,
   timeout, redirect, proxy, strict-schema, retry, and cancellation behavior.
3. Add schema-v4 migration, source-aware capability/fingerprints, provider
   resolution, model discovery/selection routes, durable manifest identity,
   and offline route/capability tests.
4. Replace direct-GGUF onboarding with Ollama discovery and selection, demote
   GGUF to the advanced section, and add browser regressions for disabled,
   unavailable, empty, selected, ready, and advanced states.
5. Prove the new regressions fail without their implementation, run the full
   repository verification entry point, exercise discovery and one strict
   recipe through an already-installed real Ollama model without downloading
   anything, then build and frozen-smoke the native application.

Each finished slice is committed before the next begins. No push, provider
request, model download, model mutation, or hardware write is authorized by
this plan.

## Verification

Run focused Python and browser tests after each slice. For every newly added
behavioral regression, temporarily remove or revert the implementation, prove
the test fails, restore it, and prove it passes.

Run the repository entry point:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/app.js
uv build
```

Run a real local acceptance check against an already-installed eligible Ollama
model. Capture the model name/digest before and after and prove the installed
model list is unchanged. The check must produce one validated recipe and local
render; it must not access a cloud alias or call a model-management endpoint.

Because the native setup and packaged behavior change, run:

```sh
uv run --frozen python build.py --skip-sync
```

Then run the produced frozen executable with `--smoke-test` and verify the
versioned macOS application/DMG using the builder's normal checks. Use external
Playwright against the local application if visual or responsive acceptance
needs browser automation; do not add it to runtime dependencies.
