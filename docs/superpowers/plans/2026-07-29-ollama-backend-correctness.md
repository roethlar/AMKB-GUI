# Ollama Backend Correctness Remediation

**Status:** Approved for implementation by the owner on 2026-07-29. This plan
is independently approvable from the product-experience plan, but it must be
implemented first because the product plan consumes the backend names, routes,
status projection, and disclosure behavior defined here.

## Objective

Replace the loopback-only, local-only, retrying Ollama integration with one
coherent backend contract:

- users configure one Ollama HTTP(S) server origin;
- loopback remains the default and LAN Ollama servers are first-class;
- every structurally valid completion-capable model returned by that server is
  selectable, including Ollama Cloud entries;
- the application contacts only the configured origin and fixed Ollama API
  paths, never inventory `remote_host` metadata;
- endpoint and execution location are part of setup identity and disclosure;
- one explicit Generate action makes exactly one model request; and
- the application never manages Ollama models.

The rejected unpublished `0.1.64` candidate remains unpublishable. Completing
this plan does not resume release qualification or authorize a live cloud
prompt, provider credential use, keyboard write, tag, Release, publication, or
announcement.

## Current Baseline

The implementation at the plan base has these relevant behaviors:

- `am_configurator/ollama_client.py` hardcodes
  `http://127.0.0.1:11434`.
- `am_configurator/ollama_client.py::_model_from_tag` rejects entries marked by
  `remote_model`, `remote_host`, or a `:cloud` suffix even when they are valid
  completion-capable Ollama inventory.
- `am_configurator/store.py` schema v6 stores the backend as `local` and the
  selection under `ai.local`.
- `am_configurator/ai_capability.py` fingerprints the model as
  `ollama-loopback-v1`, uses `local` as the status and provider-cache key, and
  exposes `discover_local_models`.
- `am_configurator/server.py` and the bundled frontend use
  `/api/ai/local/*` routes.
- `am_configurator/procedural_generation.py::_run` gives the Ollama path
  `LOCAL_MAX_RETRIES`, so one Generate action may make an initial request plus
  two corrected requests after schema or quality failures.
- `am_configurator/local_animation.py` independently uses the same retry
  constant and correction payload.
- `am_configurator/recipe_inference.py` builds retry-only prompts and corrected
  seeds.
- `am_configurator/recipe_provider.py::OllamaRecipeProvider.generate` delegates
  to `generate_attempt`; no backend needs that second protocol method once the
  retry loop is removed.

## Locked Backend Contract

### Settings Schema v7

Raise `SETTINGS_SCHEMA_VERSION` from 6 to 7. The canonical shape is:

```json
{
  "ai": {
    "enabled": false,
    "backend": "ollama",
    "ollama": {
      "base_url": "http://127.0.0.1:11434",
      "model_id": null,
      "model_digest": null,
      "model_location": null,
      "setup_fingerprint": null,
      "disclosure_version": null,
      "disclosure_at": null
    }
  }
}
```

`ai.backend` accepts `null`, `ollama`, or `api`. The existing Direct API
provider object is unchanged.

Migrate v6 deterministically:

- `ai.backend == "local"` becomes `"ollama"`;
- `ai.local.model_id` and `model_digest` move into `ai.ollama`;
- `base_url` becomes normalized `http://127.0.0.1:11434`;
- model location, disclosure fields, and setup fingerprint become `null`;
- API, Library, generation, and non-AI settings are preserved exactly; and
- the original file is not replaced unless the projected v7 value passes the
  strict v7 validator and can be atomically written.

The setup fingerprint reset is mandatory. The v6 fingerprint did not bind an
endpoint or local/cloud execution location and cannot prove the v7 setup.

### Ollama Origin

Implement one canonical parser and normalizer in
`am_configurator/ollama_client.py`. Every settings mutation, client
construction, public status projection, and setup fingerprint uses the
normalized origin.

Accepted:

- absolute `http://` or `https://`;
- DNS hostname, IPv4 literal, or bracketed IPv6 literal;
- explicit port or the scheme default; and
- empty path or `/`.

Rejected:

- any other scheme;
- missing host;
- username or password;
- query, fragment, or non-root path;
- wildcard/unspecified `0.0.0.0` or `[::]`;
- control characters, over-bound values, malformed ports, or ambiguous
  normalization.

Normalization lowercases scheme and DNS hostname, preserves bracketed IPv6,
removes a trailing root slash and default port, and emits an ASCII origin with
no credentials.

HTTP remains supported for ordinary LAN Ollama installations. The frontend
warns that prompts sent to a non-loopback HTTP endpoint are not encrypted.
HTTPS uses platform/Python certificate and hostname validation. No UI or API
may disable TLS verification.

The only requests are:

- `GET <origin>/api/tags`;
- `POST <origin>/api/chat`.

Redirects and environment proxies remain disabled. Inventory and response
bounds remain enforced. Cancellation closes only the active connection.
Errors exposed outside diagnostic logs remain pathless and credential-free.

### Inventory and Location

`OllamaModel` exposes bounded `location`:

- `on_device` when no cloud marker exists;
- `ollama_cloud` when the model name ends in `:cloud` or inventory contains a
  non-empty `remote_model` or `remote_host`.

An entry is eligible when it is an object whose:

- `name` and `model` are the same valid bounded model ID;
- digest is valid;
- size is a positive integer;
- capabilities are a string list containing `completion`; and
- optional details and remote metadata pass bounded type validation.

Cloud markers classify; they never reject. `remote_host` is never included in
the public model projection and never reaches a transport constructor.

The public projection contains `model_id`, `digest`, `location`,
`parameter_size`, and `quantization`. Labels are:

- `<model> — On this Ollama server`;
- `<model> — Ollama Cloud`.

### Capability, Disclosure, and Setup Identity

Rename the contract atomically:

- `discover_local_models` → `discover_ollama_models`;
- `_local_components` → `_ollama_components`;
- `status.local` → `status.ollama`;
- backend and provider-cache key `local` → `ollama`;
- `/api/ai/local/*` → `/api/ai/ollama/*`.

There is no compatibility alias for the token-authenticated loopback web API;
the native shell and bundled frontend update atomically. Historical Library and
generation manifests remain read-compatible.

Cache `OllamaClient` by normalized origin. Changing the endpoint:

- clears model ID, digest, location, setup fingerprint, and disclosure;
- discards the provider/client cached for the prior origin;
- makes no request until explicit Refresh or Test setup; and
- never changes the old server or its models.

The v2 setup fingerprint contains normalized base URL, model ID, digest,
location, recipe schema version, setup-test version, and the current
disclosure version/timestamp when disclosure is required.

Disclosure acknowledgement is required before Test setup when the endpoint is
not loopback or the model location is `ollama_cloud`. It states:

- a non-loopback endpoint receives the lighting prompt and keyboard dimensions;
- an Ollama Cloud model may be forwarded by the configured server to Ollama
  Cloud; and
- imported media, profiles, keymaps, macros, device paths, and Library files
  are not sent.

Endpoint, model, location, or disclosure-version changes invalidate setup.

### One Request Per User Action

Every generation job creates one attempt and calls `provider.generate` once.
Schema, semantic, quality, transport, and cancellation failures stop the job.
No failure path calls a model again.

Remove, rather than gate:

- `LOCAL_MAX_RETRIES`;
- retry-only prompt and payload fields;
- corrected retry seed selection;
- `generate_attempt` from `OllamaRecipeProvider`, its protocol surface, exports,
  fakes, and tests.

Historical manifests containing multiple attempts remain readable. A visible
Try again action creates a new job and one new request. Test setup remains one
separately explicit request.

## Implementation Slices

Every slice must pass the repository's full automated verification entry point
before commit. A slice boundary that leaves old and new settings keys, backend
values, routes, or status fields split across consumers is invalid.

### Slice B1 — Land schema v7, configurable origin, and the atomic Ollama rename

Files:

- `am_configurator/store.py`
- `am_configurator/ollama_client.py`
- `am_configurator/ai_capability.py`
- `am_configurator/server.py`
- `am_configurator/desktop.py`
- `am_configurator/procedural_generation.py`
- `am_configurator/recipe_provider.py`
- `am_configurator/local_animation.py`
- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `tests/test_app.py` (`SettingsStoreTests`)
- `tests/test_ollama_client.py`
- `tests/test_ai_capability.py`
- `tests/test_ai_routes.py`
- `tests/test_credentials.py`
- `tests/test_library.py`
- `tests/test_procedural_generation.py`
- `tests/test_recipe_provider.py`
- `tests/test_local_animation.py`
- affected `tests/web/*.test.js`

Required guards:

- v6 settings migrate to the exact v7 shape without losing unrelated data;
- every runtime/frontend consumer uses `ollama`, `ai.ollama`,
  `status.ollama`, and `/api/ai/ollama/*` in the same commit;
- no normal runtime path reads `ai.local` or compares backend to `local`;
- accepted and rejected URL cases cover the complete origin contract;
- HTTP and HTTPS choose the correct connection class;
- inventory and chat use only normalized origin plus fixed paths;
- proxies, redirects, TLS bypass, and URL credentials remain unavailable;
- saving a changed endpoint performs no network request;
- endpoint changes clear selection/setup and evict the prior cached client;
- the developer local-animation adapter uses the configured normalized origin;
- Direct API and historical manifest behavior are unchanged.

Commit:

```text
feat: configure the Ollama backend origin
```

### Slice B2 — Accept complete inventory and bind setup to execution location

Files:

- `am_configurator/ollama_client.py`
- `am_configurator/store.py`
- `am_configurator/ai_capability.py`
- `am_configurator/server.py`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- corresponding Python and web tests

Required guards:

- on-device and cloud entries with `completion` are returned;
- malformed entries are independently filtered;
- `remote_host` is classification-only and never a request target;
- public inventory never exposes `remote_host`;
- location survives selection and enters the setup fingerprint;
- endpoint/model/location/disclosure changes invalidate setup;
- disclosure is required for non-loopback or cloud execution and not otherwise;
- model labels unambiguously state server-local or Ollama Cloud execution;
- Refresh and Test setup remain the only inventory/setup request actions.

Commit:

```text
feat: support Ollama server and cloud models
```

### Slice B3 — Remove automatic model regeneration

Files:

- `am_configurator/local_animation.py`
- `am_configurator/procedural_generation.py`
- `am_configurator/recipe_inference.py`
- `am_configurator/recipe_provider.py`
- `tests/test_local_animation.py`
- `tests/test_procedural_generation.py`
- `tests/test_recipe_inference.py`
- `tests/test_recipe_provider.py`
- affected historical documentation assertions

Required guards:

- schema, semantic, quality, and transport failures each make exactly one
  provider call;
- Direct API still makes exactly one call;
- local-animation generation makes exactly one call;
- cancellation never creates another attempt;
- Try again creates one new job and one new call;
- new jobs never append an automatic second attempt;
- historical multi-attempt manifests remain readable;
- retry correction prompts, fields, and seeds are absent;
- `generate_attempt` and `LOCAL_MAX_RETRIES` have no definitions, exports,
  fakes, tests, or call sites.

Commit:

```text
fix: stop automatic Ollama regeneration
```

### Slice B4 — Close backend remediation

Files:

- `.agents/state.md`
- this plan
- affected durable verification records

Required checks:

- run the current automated verification entry point in
  `.agents/repo-guidance.md`;
- run `python build.py --skip-sync` and the built executable's `--smoke-test`;
- exercise endpoint and inventory behavior only with bounded fake loopback/LAN
  servers;
- prove exact one-call behavior with automated counters;
- record implementation commits and any remaining platform gates;
- record that no live cloud prompt, provider credential, or keyboard write was
  used.

Commit:

```text
docs: close Ollama backend remediation
```

## Guard-Proof Procedure

For each new behavioral guard:

1. run the focused test against the change and confirm PASS;
2. temporarily revert only the production behavior it guards;
3. rerun and confirm FAIL for the predicted reason;
4. restore the behavior;
5. rerun and confirm PASS;
6. run the full automated verification entry point before commit.

Do not duplicate the verification command list here; the canonical entry point
is `.agents/repo-guidance.md` under **Verification**.

## Acceptance Criteria

This plan is complete only when:

- users can configure loopback or LAN Ollama HTTP(S) origins;
- endpoint validation/persistence makes no implicit request;
- all valid completion-capable server inventory is selectable and labelled;
- inventory metadata can never redirect application transport;
- endpoint/model/location/disclosure changes require a new setup test;
- each Generate/Try again/Test setup action makes exactly one model request;
- no retry protocol or correction machinery remains;
- Direct API, Library, and historical manifest behavior still pass;
- automated verification, native smoke, and fake-server checks pass;
- every slice is committed independently with guard proof;
- no live cloud prompt, credentialed provider request, or keyboard write occurs.

The product-experience plan remains separately pending after this plan closes.
No release candidate is built until both plans are complete.
