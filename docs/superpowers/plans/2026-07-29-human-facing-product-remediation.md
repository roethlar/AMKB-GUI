# Human-Facing Product and Configurable Ollama Remediation

**Status:** Drafted on 2026-07-29 from owner-approved product direction.
Implementation is not yet approved. The rejected `0.1.64` candidate remains
unpublishable, release qualification remains stopped, and this plan must receive
an independent openreview before it is presented for implementation approval.
There are no unresolved product decisions in this plan.

## Objective

Replace the current implementation-led experience with a gamer-facing keyboard
application whose first-run path, controls, messages, documentation, and AI
configuration explain user tasks rather than internal architecture.

The completed change must:

- support an Ollama server at a user-configured HTTP(S) origin, with
  `http://127.0.0.1:11434` as the default and LAN-hosted Ollama installations as
  first-class configurations;
- accept every structurally valid, completion-capable model returned by the
  configured Ollama server, including Ollama Cloud entries;
- send Ollama discovery and generation requests only to the configured origin
  and fixed Ollama API paths, never to inventory-provided `remote_host`
  metadata;
- perform exactly one model request for each explicit **Generate** action for
  every backend;
- expose failures immediately and require a new explicit user action before
  another model request;
- replace implementation vocabulary with plain task language throughout the
  shipped UI and README;
- move low-level firmware, matrix, recipe, and rendering controls behind
  clearly labelled advanced disclosure where they remain necessary; and
- preserve all existing device-write safety, lossless profile handling,
  Library durability, explicit preview/apply boundaries, and no-model-
  management guarantees.

## Owner-Settled Product Decisions

These requirements are authoritative for implementation:

1. **Ollama is one backend, not a synonym for local inference.** Its server URL
   is configurable. Loopback is the default; a user may point the application
   at another Ollama installation on the LAN.
2. **Ollama inventory is authoritative after structural validation.** A
   completion-capable model is eligible whether its computation is local to the
   Ollama server or forwarded by that server to Ollama Cloud.
3. **The application never manages Ollama models.** It does not pull, create,
   copy, update, or remove models.
4. **The application never follows model metadata to another host.** It talks
   only to the configured Ollama origin. Ollama itself owns any forwarding
   required by a cloud model.
5. **Generation is one request per explicit user action.** Schema-invalid and
   quality-invalid responses do not trigger automatic corrected generations.
6. **The target audience is keyboard owners and gamers.** User-facing copy and
   control hierarchy must not assume knowledge of manifests, durable jobs,
   banking, procedural recipes, raster identities, deterministic seeds, or
   provider implementation details.

## Current Baseline and Failure Evidence

- `am_configurator/ollama_client.py::_model_from_tag` rejects any entry with
  `remote_model`, `remote_host`, or a `:cloud` suffix even when the configured
  Ollama daemon reports a valid digest, positive size, and `completion`
  capability.
- `am_configurator/ollama_client.py` hardcodes
  `http://127.0.0.1:11434`.
- `am_configurator/store.py` schema v6 stores the backend as `local` and the
  selected model under `ai.local`.
- `am_configurator/ai_capability.py` fingerprints the selected model as
  `ollama-loopback-v1`, constructs one fixed client, and uses `local` as the
  readiness and provider-cache key.
- `am_configurator/procedural_generation.py::_run` gives the `local` backend
  `LOCAL_MAX_RETRIES`, so one user action can make an initial request plus two
  complete corrected requests after schema or quality failures.
- `am_configurator/recipe_inference.py` builds retry-only prompts and seeds.
- `am_configurator/web/index.html`, `app.js`, `lighting_state.js`, and
  `lighting_review.js` expose implementation terms including `Local`,
  `banked`, `banking`, `durable`, `procedural recipe`, `exact LED frames`,
  `model identity`, and raw stored/mapped counts.
- The normal Keymap view exposes matrix positions and a raw keycode editor; the
  normal Macro view exposes event-level key-down/key-up rows; the normal
  Lighting view exposes sampling algorithms, deterministic pattern seeds, and
  draft/rendering terminology without progressive disclosure.
- `README.md` makes a new user pass release provenance and implementation
  descriptions before reaching a clear supported-device and first-use path.
- The current `0.1.64` release candidate was rejected during product
  qualification. No tag, Release, publication, provider credential use, cloud
  prompt, or release-candidate hardware write followed that rejection.

## Non-Goals

- Do not add Ollama model download, pull, delete, or update controls.
- Do not accept inventory `remote_host` as a connection target.
- Do not add authentication headers, URL-embedded credentials, custom CA
  installation, or an “ignore TLS errors” option.
- Do not disable TLS certificate verification.
- Do not add automatic provider retries, hidden failover, fallback models, or
  automatic prompt rewriting.
- Do not redesign the device protocol, profile schema, Library storage model,
  lighting renderer, or hardware-write confirmation boundary.
- Do not send a live prompt to an Ollama Cloud model as part of implementation
  or automated verification.
- Do not write a keyboard during implementation or automated verification.
- Do not resume exact-artifact release qualification until every implementation
  and usability slice below is complete and a new candidate exists.

## Architecture

### 1. Settings Schema v7

Raise `SETTINGS_SCHEMA_VERSION` from 6 to 7 and replace the misleading local
shape:

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

`backend` accepts `null`, `ollama`, or `api`. The existing API provider object
is unchanged.

Migrate v6 deterministically:

- `ai.backend == "local"` becomes `"ollama"`;
- `ai.local.model_id` and `model_digest` move into `ai.ollama`;
- `base_url` becomes the normalized default
  `http://127.0.0.1:11434`;
- `model_location`, disclosure fields, and `setup_fingerprint` become `null`;
- all API, Library, and generation settings are preserved exactly; and
- the original settings file remains untouched if the projected v7 value does
  not pass the strict v7 validator or cannot be atomically written.

Resetting the Ollama setup fingerprint is intentional. The old fingerprint did
not bind readiness to an endpoint or local/cloud execution, so it cannot prove
the new configuration.

### 2. Ollama Base URL Contract

Add one canonical parser and normalizer in `am_configurator/ollama_client.py`.
Every settings mutation, client construction, public status projection, and
setup fingerprint uses its normalized result.

Accepted values:

- an absolute `http://` or `https://` URL;
- a DNS hostname, IPv4 literal, or bracketed IPv6 literal;
- an explicit port or the scheme default; and
- an empty path or `/`.

Rejected values:

- a scheme other than HTTP(S);
- a missing host;
- username or password information;
- a query, fragment, or non-root path;
- wildcard/unspecified hosts such as `0.0.0.0` and `[::]`;
- control characters or a value beyond the bounded settings length; and
- a URL whose normalized representation is ambiguous.

Normalization lowercases the scheme and DNS hostname, preserves a bracketed
IPv6 host, removes a trailing root slash, removes the default scheme port, and
emits an ASCII origin. The persisted URL contains no credential.

HTTP remains supported because an ordinary Ollama LAN installation commonly
serves plaintext HTTP. The UI must say that prompts sent to a non-loopback HTTP
endpoint are not encrypted. HTTPS uses normal platform/Python certificate and
hostname validation. No UI or API may suppress TLS verification.

The connection boundary remains narrow:

- inventory is `GET <origin>/api/tags`;
- generation is `POST <origin>/api/chat`;
- redirects are rejected;
- environment proxies are bypassed;
- response and inventory bounds remain enforced;
- cancellation closes only the active connection;
- the client never requests an inventory-supplied URL; and
- error text remains pathless and does not expose local filesystem details.

Refactor `OllamaClient` to be constructed from the normalized origin. Select
`http.client.HTTPConnection` or `HTTPSConnection` by scheme while retaining
injectable openers and connection factories for tests.

### 3. Ollama Model Contract

`OllamaModel` gains a bounded public `location` value:

- `on_device` when the tag has no cloud marker; or
- `ollama_cloud` when the name ends in `:cloud` or the tag contains non-empty
  `remote_model` or `remote_host` metadata.

A tag is eligible when:

- it is an object;
- `name` and `model` are the same valid bounded model ID;
- `digest` is a valid digest;
- `size` is a positive integer;
- `capabilities` is a list of strings containing `completion`; and
- optional details and remote metadata satisfy bounded type checks.

Cloud markers classify; they do not reject. `remote_host` is never included in
the public model projection and is never passed to a transport constructor.

Public model inventory includes `model_id`, `digest`, `location`,
`parameter_size`, and `quantization`. The UI label is:

- `<model> — On this Ollama server`; or
- `<model> — Ollama Cloud`.

Parameter size and quantization may follow the label when present, but they must
not replace the location label.

### 4. Capability and Setup Identity

Rename local-facing capability functions and payload fields to Ollama-facing
names:

- `discover_local_models` → `discover_ollama_models`;
- `_local_components` → `_ollama_components`;
- `status.local` → `status.ollama`;
- provider cache key `local` → `ollama`; and
- browser/API routes under `/api/ai/local/*` → `/api/ai/ollama/*`.

There is no compatibility requirement for the token-authenticated loopback web
API because the native shell and bundled frontend update atomically. Historical
Library manifests remain read-compatible.

Construct or cache an `OllamaClient` by normalized endpoint identity. Changing
the endpoint must:

- clear selected model ID, digest, location, and setup fingerprint;
- discard a cached provider for the prior endpoint;
- refresh inventory only after an explicit Refresh action; and
- leave the old Ollama server and all its models untouched.

The v2 Ollama setup fingerprint includes:

- normalized base URL;
- model ID;
- model digest;
- model location;
- recipe schema version;
- setup-test version; and
- the current Ollama disclosure version and acceptance timestamp when
  disclosure is required.

Require disclosure acknowledgement before **Test setup** when either:

- the normalized endpoint is not loopback; or
- the selected model location is `ollama_cloud`.

The disclosure states the exact destination category:

- non-loopback endpoint: the lighting prompt and keyboard dimensions are sent
  to the configured Ollama server;
- cloud model: that Ollama server may forward the prompt to Ollama Cloud; and
- imported media, profiles, keymaps, macros, device paths, and Library files
  are not part of the request.

Changing endpoint, model, location, or disclosure version invalidates setup.

### 5. One Request Per Generate

Remove the local-only correction loop from
`ProceduralGenerationCoordinator._run`. Every job creates one procedural
attempt and calls `provider.generate` once.

Remove or retire:

- `LOCAL_MAX_RETRIES`;
- retry-only payload validation and prompt text;
- corrected retry seed selection;
- `generate_attempt` from the provider protocol when no remaining backend uses
  it; and
- tests and documentation that claim local semantic or quality retries.

Preserve historical manifest reading for jobs that already contain multiple
attempts. New jobs never append an automatic second attempt.

Failure behavior:

- transport/provider failure records the first typed error and stops;
- schema/semantic failure records `bad_response` and stops;
- rendered quality failure records `quality_failed` and stops;
- cancellation records cancellation and stops;
- no failure path calls a model again; and
- the prompt stage reappears with an actionable plain-language explanation and
  a **Try again** button. Clicking it creates a new job and is the next explicit
  user action.

Setup testing remains one separately explicit request initiated by **Test
setup**. It is never triggered by saving Settings, changing endpoint, refreshing
inventory, or selecting a model.

## Product Language Contract

User-facing copy in HTML, JavaScript, Python API errors surfaced by the UI,
README, installation guidance, and screenshots follows this vocabulary:

| Internal term | User-facing replacement |
|---|---|
| local backend | Ollama |
| API backend | Direct API |
| local model | model on this Ollama server |
| bank / banked / banking | save / saved / saving to Library |
| durable job | generation continues in the background |
| procedural recipe | lighting effect or lighting pattern |
| exact LED frames | lighting frames |
| raster dimensions | keyboard or display size |
| model identity changed | the model was updated; test it again |
| source | imported media |
| deterministic draft | preview |
| accept draft | apply preview |
| catalog identity / asset identity | saved Library item |
| mapped / stored counts | hide normally; show under technical details |

Internal variable names, manifest fields, diagnostic logs, and developer tests
may retain precise engineering terms when they are not exposed to users.

Every surfaced error must answer:

1. what failed in user terms;
2. whether anything was saved or changed; and
3. the next available action.

Do not expose raw exception text when it violates this contract. Map typed
errors at the API/UI boundary and retain diagnostic detail only in local logs or
test assertions.

## Interface Remediation

### 1. First-Run and Empty State

Replace the paragraph-only empty state with two primary task cards:

- **Connect a keyboard** — opens Devices and explains that reading never writes
  the keyboard; and
- **Open a JSON profile** — opens a complete portable profile.

Keep one concise safety note: keyboard lighting cannot be read back on models
whose firmware does not expose it, so preserving existing lighting requires a
complete JSON profile or the application's last verified local snapshot.

Do not require users to understand merging before they have opened a document.
Present **Merge another JSON** only after a document is open or when a key-only
export specifically needs its matching lighting file.

### 2. Application Chrome

Group toolbar actions by user task:

- file: Open, Save JSON, and contextual Merge;
- application: Settings; and
- device: Devices and Write to keyboard.

Keep the existing quiet chrome and Keymap-first launch decision. Do not restore
a nested product logo/title or put the version in ordinary chrome.

Sidebar numbers receive visible or accessible labels such as `7 layers`,
`4 macros`, and `3 lighting slots`; unexplained counts are not acceptable.

### 3. Keymap

The normal inspector shows:

- selected physical key;
- current assignment in plain language;
- searchable assignment groups; and
- Apply.

Move raw eight-digit keycode editing, matrix indexes, and firmware passthrough
explanation into a collapsed **Advanced keycode** section. Hide matrix/LED
numbers on the normal keycaps and expose them through an optional **Show
technical labels** toggle. Lossless raw-code support remains available.

### 4. Macros

Make the default macro workflow task-oriented:

- **Type text** converts text to keystrokes;
- **Record keys** captures a physical sequence; and
- a simple delay control explains timing.

Move the key-down/key-up event table, per-event delay editing, track counts, and
capacity diagnostics into an expanded **Edit individual events** section.
Capacity errors remain enforced before mutation and are explained in user
terms.

### 5. Lighting Studio

Rename the normal tools:

- Paint;
- Import media;
- Effects; and
- AI.

Replace draft/render terminology with a consistent two-step boundary:
**Preview** then **Apply to lighting slot**.

Move sampling method, independent-axis stretch, pattern seed, raw frame counts,
mapped/stored counts, and firmware timing detail into contextual **Advanced**
sections. Keep friendly presets and firmware-safe values in the normal path.

Use **Save to Library** consistently for manual lighting, imported media,
keymaps, macros, and generated effects. A successful Apply changes the open
document only; saving to Library is a separate clearly labelled action.

The AI panel shows:

- selected destination in plain language;
- selected Ollama or Direct API model;
- one prompt field;
- one Generate/Try again action;
- progress using `Creating lighting`, `Checking the result`, and
  `Saving to Library`; and
- explicit Cancel.

The progress explanation becomes:

> You can open Library while this finishes. Closing the progress view does not
> cancel generation.

Do not claim that a job or result is durable, banked, exact, or procedural.

### 6. Settings

Use **Ollama** and **Direct API** as backend choices. Remove `Primary computer`,
`Secondary provider`, `Installed model`, and `eligible local model` wording.

The Ollama panel contains:

- **Server URL** with the loopback default and an example LAN URL;
- connection status naming the configured host without credentials;
- Refresh models;
- model picker with `On this Ollama server` or `Ollama Cloud` labels;
- the conditional disclosure described above;
- Use model;
- Test setup; and
- Clear selection.

Saving a changed URL does not contact it. Refresh and Test are the only actions
that initiate discovery and setup generation respectively.

### 7. Visual Hierarchy and Accessibility

Retain the dark visual identity while correcting density and legibility:

- normal body text is at least 14 px at 100% scale;
- helper text is at least 13 px;
- normal text meets WCAG AA 4.5:1 contrast and large text/control boundaries
  meet 3:1;
- focus rings remain visible on every interactive element;
- disabled state is distinguishable without making labels unreadable;
- primary, secondary, destructive, and advanced actions have consistent visual
  hierarchy; and
- the existing native minimum window and a 1280×800 viewport have no hidden
  primary actions, horizontal clipping, or overlapping panels.

Automated DOM tests assert the structural and vocabulary contracts. Manual
visual verification covers Keymap, Macros, Lighting, Library, Settings, empty
state, errors, and dialogs at 1280×800 and 1600×1000.

## README and User Documentation

Restructure `README.md` in this order:

1. one-sentence product purpose;
2. **Download the latest release** link;
3. supported keyboards and operating systems;
4. a five-minute quick start;
5. three current screenshots;
6. keymap, macro, lighting, Library, and optional AI capabilities;
7. concise device-write and lighting-backup safety;
8. installation verification link; and
9. collapsed developer/build instructions.

The quick start uses the same terms and action labels as the application.
Remove maintainer-only workflow artifact detail from the normal download path;
retain reproducibility and provenance material in installation/release
documentation where it is useful.

Update screenshots only after the final UI is implemented and manually checked.
Screenshots must not display credentials, device serials, personal paths, or a
live cloud prompt/result.

## Implementation Slices and Commits

Each slice is completed, red-proven where it adds a guard, fully verified for
its scope, and committed before the next slice begins.

### Slice 0 — Record the rejected candidate and approved product direction

Files:

- `.agents/decisions.md`
- `.agents/state.md`
- this plan

Commit:

```text
docs: plan human-facing Ollama remediation
```

### Slice 1 — Add schema v7 and configurable Ollama origin

Files:

- `am_configurator/store.py`
- `am_configurator/ollama_client.py`
- `tests/test_ai_capability.py`
- `tests/test_ollama_client.py`
- `tests/test_store.py` or the existing settings test module

Required guards:

- v6 local settings migrate to v7 Ollama settings without losing API, Library,
  or generation data;
- setup is invalidated during migration;
- accepted URL normalization covers loopback, LAN DNS, IPv4, bracketed IPv6,
  HTTP, and HTTPS;
- userinfo, query, fragment, non-root path, invalid scheme, wildcard host, and
  malformed ports are rejected;
- HTTP and HTTPS select the correct connection class;
- inventory/chat use only the normalized origin plus fixed API paths;
- proxies and redirects remain disabled; and
- changing the origin clears model/setup state without contacting a server.

Commit:

```text
feat: configure the Ollama server origin
```

### Slice 2 — Accept and label the complete Ollama inventory

Files:

- `am_configurator/ollama_client.py`
- `am_configurator/ai_capability.py`
- `am_configurator/server.py`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/app.js`
- corresponding Python and web tests

Required guards:

- local and cloud entries with `completion` capability are returned;
- malformed inventory entries remain independently filtered;
- `remote_host` is classification-only and never becomes a request target;
- model location survives selection and is included in setup identity;
- endpoint/model/location changes invalidate setup;
- Direct API behavior is unchanged; and
- web model options visibly distinguish server-local and cloud execution.

Commit:

```text
feat: support Ollama server and cloud models
```

### Slice 3 — Enforce one model request per Generate action

Files:

- `am_configurator/procedural_generation.py`
- `am_configurator/recipe_inference.py`
- `am_configurator/recipe_provider.py`
- `tests/test_procedural_generation.py`
- `tests/test_recipe_inference.py`
- `tests/test_recipe_provider.py`
- affected historical plan/verification claims

Required guards:

- Ollama schema failure makes exactly one provider call;
- Ollama quality failure makes exactly one provider call;
- Direct API failure continues to make exactly one provider call;
- cancellation never creates another attempt;
- a new explicit Try again creates one new job and one new call;
- historical manifests with multiple attempts remain readable; and
- no retry-correction prompt or retry seed is emitted.

Commit:

```text
fix: stop automatic Ollama regeneration
```

### Slice 4 — Replace implementation language

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/lighting_review.js`
- surfaced Python error mappings
- all affected web/Python tests

Required guards:

- normal UI output contains none of the banned vocabulary in the Product
  Language Contract;
- phase and failure messages state the user-visible action and next step;
- Ollama/Direct API labels match the stored backend;
- generated result review uses lighting-effect language; and
- internal manifest compatibility remains unchanged.

Commit:

```text
fix: use plain language throughout the app
```

### Slice 5 — Simplify onboarding, Keymap, and Macros

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/style.css`
- relevant web tests

Required guards:

- empty state exposes Connect keyboard and Open JSON as the two primary paths;
- Merge is contextual;
- raw keycodes and matrix labels are hidden until Advanced is opened;
- lossless raw assignment remains functional;
- macro text/record actions remain available in the normal view;
- event-level editing remains functional under Advanced; and
- keyboard navigation and focus restoration continue to pass.

Commit:

```text
feat: simplify keymap and macro workflows
```

### Slice 6 — Simplify Lighting, Library, and Settings

Files:

- `am_configurator/web/index.html`
- `am_configurator/web/app.js`
- `am_configurator/web/lighting_state.js`
- `am_configurator/web/lighting_review.js`
- `am_configurator/web/style.css`
- relevant web and route tests

Required guards:

- tool names and preview/apply actions follow this plan;
- technical controls are under Advanced without losing their values;
- every Library save action is explicit;
- Settings URL save performs no network request;
- Refresh and Test are separately explicit;
- non-loopback HTTP and Ollama Cloud disclosures are correct and bound to setup;
- failed generation exposes one Try again action and no automatic request; and
- AI-off mode leaves all manual tools available and hides AI-only controls.

Commit:

```text
feat: simplify lighting and AI setup
```

### Slice 7 — Correct visual hierarchy and responsive behavior

Files:

- `am_configurator/web/style.css`
- minimal semantic markup changes required for accessibility
- web structure tests

Required checks:

- automated contrast/token checks where stable;
- keyboard-only traversal of all primary tasks;
- visible focus and readable disabled controls;
- no clipped primary actions at 1280×800;
- no regression at 1600×1000; and
- no hidden modal action at native minimum size.

Commit:

```text
fix: improve application legibility and hierarchy
```

### Slice 8 — Rewrite the user entry documentation

Files:

- `README.md`
- user-facing installation documentation where labels changed
- `docs/images/*.png`
- link/copy tests

Required checks:

- README order matches this plan;
- latest-release and installation links resolve;
- app action labels and README instructions agree;
- screenshots match the implemented UI and contain no sensitive data; and
- developer commands remain accurate.

Commit:

```text
docs: add a clear user quick start
```

### Slice 9 — Close product remediation and prepare a new candidate

Files:

- `.agents/decisions.md`
- `.agents/state.md`
- this plan status
- release plan status/pointers without duplicating this plan

Required checks:

- run the complete repository verification entry point;
- run native build and `--smoke-test` on the current OS;
- exercise Ollama endpoint discovery against bounded fake loopback and LAN
  servers without a live model prompt;
- manually inspect all screens and error states at the two target viewports;
- confirm no keyboard write and no live cloud prompt occurred;
- confirm exact one-call behavior from automated counters; and
- record the exact implementation commits and remaining platform gates.

Commit:

```text
docs: close product remediation
```

Building or selecting a new public-release candidate follows only after this
slice. Tagging, publication, announcements, live cloud qualification, macOS
Open Anyway, and hardware writes retain their separate action-time gates.

## Verification and Guard-Proof Procedure

For every new behavioral test:

1. run the focused test against the implemented change and confirm PASS;
2. temporarily revert only the production behavior the test claims to guard;
3. rerun the focused test and confirm FAIL for the predicted reason;
4. restore the production behavior;
5. rerun the focused test and confirm PASS; and
6. run the slice's adjacent suite before committing.

After all slices, run from the repository root:

```sh
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q am_configurator packaging build_tools
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_state.js
node --check am_configurator/web/lighting_review.js
node --check am_configurator/web/lighting_targets.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/library_state.js
node --check am_configurator/web/app.js
uv build
```

Then run the current-OS native build through `python build.py --skip-sync` and
the finished executable's `--smoke-test`. Do not invoke PyInstaller directly.

## Acceptance Criteria

The plan is complete only when:

- a user can configure loopback or another Ollama HTTP(S) origin;
- URL changes are validated, persisted, and do not cause implicit requests;
- local and cloud completion models from that server are selectable and
  unmistakably labelled;
- the application never contacts inventory `remote_host`;
- endpoint/model/location changes require a new explicit setup test;
- one Generate click makes exactly one model request on every failure path;
- retry requires another explicit click and creates a new job;
- the ordinary UI contains no implementation vocabulary listed by this plan;
- first-run, Keymap, Macros, Lighting, Library, and Settings expose clear normal
  paths with advanced details progressively disclosed;
- README gives a new user a direct download and five-minute start path;
- automated verification, native smoke, and manual visual checks pass;
- every slice is committed independently with its guard proof recorded;
- no live Ollama Cloud prompt or keyboard write was used for verification; and
- the rejected candidate remains unpublished and release qualification resumes
  only with a new exact candidate.
