# Imported Media Framing Repair

**Status:** Owner-approved on 2026-08-01 after release candidate attempt 2
failed R65-5. IMF-1 is implemented, locally verified, and clean-reviewed at
`4a9e6b89233e9549a4b9b05ca14613a2f2115eb6`. IMF-2 is implemented, locally
verified, and clean-reviewed at `041c26fe2c069b1a237464aedd8fb150c1cb89c1`.
IMF-3 remains the sequential follow-up.

## Objective

Make GIF, PNG, and BMP framing visibly responsive, geometrically bounded, and
deterministic from the native UI through the authoritative backend render.
Pointer, keyboard, wheel, preset, zoom, stretch, Preview, Apply, Undo, and
Library flows must never hide a transform change or allow ordinary framing to
move the source effectively off canvas.

The repaired behavior must be proved on Windows WebView2 first at the two
release-blocking viewports, then repeated against the final exact macOS
WKWebView artifact as a platform regression check. The repair adds no runtime,
build, test, browser-automation, or media dependency.

## Authority and release consequence

- `AGENTS.md` and `.agents/repo-guidance.md` own process, verification, and
  device safety.
- `.agents/decisions.md` owns the imported-media/AI separation, the
  procedural-only AI contract, and the unconditional FFmpeg prohibition.
- `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md` owns release
  qualification and permanently records candidate attempt 2 as rejected.
- This plan owns only the imported-media framing correction and its proof.
- Candidate attempt 2 may not be reused. A completed repair moves `main` and
  requires a fresh R65-2 freeze plus the complete release qualification.
- No provider request, credential use, hardware write, tag, Release, macOS
  Open Anyway action, security-setting change, or announcement is authorized
  by this plan.

## Reproduced defect

Candidate attempt 2 froze
`c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7`. Exact CI run `30687960889`
and Desktop run `30687960898` attempt 1 passed. R65-3 and R65-4 passed for the
exact three-platform artifact set. During R65-5, a 40x5 imported animation was
framed for the CyberBoard 40x5 display in the exact macOS application:

1. dragging on the LED canvas produced no visible source movement or other
   framing feedback;
2. the drag nevertheless changed the normalized pan state;
3. later keyboard panning changed that hidden state again; and
4. Preview rendered the animation almost entirely black because the source was
   nearly off canvas.

The owner explicitly rejected the result. Apply was not used. No document,
Library lighting item, keyboard, provider, tag, Release, or announcement was
changed by the failed check.

## Confirmed causes

1. `am_configurator/web/lighting_composer.js` constrains offsets only to the
   schema-wide `-8..8` range. It does not receive source or destination
   geometry, so a valid transform can move an image several complete canvases
   away.
2. `am_configurator/media_composition.py` enforces the same schema-wide range
   and pastes the resulting raster without a geometry constraint. The backend
   therefore treats an effectively blank off-canvas result as valid.
3. `am_configurator/web/app.js` mutates framing state in LED-result mode, while
   the movable source overlay exists only in imported-media mode. A pointer,
   keyboard, wheel, slider, or preset action can therefore change hidden state.
4. `am_configurator/web/style.css` approximates the backend with a full-stage
   `object-fit: cover` image and CSS translation/scale. It does not use the
   backend raster box, so it cannot be a faithful framing preview.
5. Existing tests prove schema limits, pure reducers, orientation, decoding,
   and endpoint availability. They do not prove real source/destination
   constraints, browser/backend geometry parity, event wiring, immediate
   visual feedback, or the complete imported-media workflow in a native
   webview.

## Framing contract

### Exact geometry

For source size `(Sw, Sh)`, destination size `(Dw, Dh)`, and transform scales
`(sx, sy)`, both runtimes use the same positive half-up rounding rule and these
values:

```text
MAX_OFFSET = 8  # unchanged version-1 transform-schema bound
base = max(Dw / Sw, Dh / Sh)
Rw = max(1, floor(Sw * base * sx + 0.5))
Rh = max(1, floor(Sh * base * sy + 0.5))
max_x = min(MAX_OFFSET, abs(Rw - Dw) / (2 * Dw))
max_y = min(MAX_OFFSET, abs(Rh - Dh) / (2 * Dh))
offset_x = clamp(offset_x, -max_x, max_x)
offset_y = clamp(offset_y, -max_y, max_y)
left = floor((Dw - Rw) / 2 + offset_x * Dw + 0.5)
top = floor((Dh - Rh) / 2 + offset_y * Dh + 0.5)
```

This keeps the maximum possible source overlap for the selected scale on each
axis without producing a transform outside the unchanged version-1 schema: a
smaller rendered source remains fully inside the destination, while a larger
rendered source continues to cover the destination. A same-size 40x5 source
therefore has zero legal pan and cannot be dragged off its 40x5 target.

When one composition targets more than one raster, compute the per-target
limits and use their intersection: the smallest `max_x` and `max_y`. The
primary target owns the visible source overlay, but the canonical transform is
safe for every requested target.

The version-1 transform schema and its broad persistence validation remain
unchanged. A new geometry-aware canonicalization step applies only when source
and destination sizes are known. Presets, pointer/keyboard pan, wheel/slider
zoom, independent-axis stretch, destination changes, and every Move & zoom
keyframe pass through that step. Scale changes immediately re-constrain the
existing offsets.

The backend is the final safety boundary. It canonicalizes before rendering
and returns the exact transform it used. For Move & zoom, interpolate first,
canonicalize every frame against that frame's scale, and return the resolved
transform array alongside the validated effect. The browser computes the same
array and adopts the backend-returned canonical state. Stale or externally
supplied in-range offsets may be corrected safely, but the correction must
never remain hidden from the UI.

### Visible interaction

- A destination-sized, overflow-clipped source viewport is present whenever an
  imported source is active in the Import media tool. The source image lives
  inside that viewport, while the LED grid and destination border remain
  outside it so their geometry is not clipped. LED result and imported-media
  modes may hide or reveal the viewport, but do not destroy the only element
  capable of showing a transform.
- Starting any framing operation activates the imported-media view before the
  state changes. The same operation updates the overlay box and the numeric
  controls synchronously; no network render is needed for drag feedback.
- The overlay uses the calculated `left`, `top`, `Rw`, and `Rh` relative to the
  primary destination. It does not use `object-fit: cover` as a transform
  substitute. Preview remains the authoritative resampled LED result.
- A primary-pointer session is tied to one pointer ID and uses stage-scoped
  move/up/cancel/lost-capture listeners installed at pointer down. Attempt
  pointer capture for a real active pointer, but treat only
  `DOMException: NotFoundError` as a non-fatal no-capture result: a synthetic
  native-audit event has no UA-tracked pointer ID. The same stage-scoped
  session must still complete and clean itself up; do not add a document-global
  mouse fallback. Unrelated pointer moves do not mutate framing.
- Do not gate framing on `event.isTrusted`. The native audit intentionally
  dispatches untrusted PointerEvents through the same shipped handlers; real
  pointer capture remains the ordinary user path.
- Pointer down prevents native image/text drag, focuses the stage, and exposes
  a visible dragging state. Arrow keys and `+`/`-` retain equivalent accessible
  operation. Non-framing keys and inactive tools do nothing.
- Every transform change invalidates an accepted Preview. Apply remains
  disabled until the backend has returned a Preview for the exact current
  transform and effects.

## Scope

Expected implementation surfaces:

- `am_configurator/web/lighting_composer.js` for shared browser geometry;
- a small repository-owned, dependency-free browser interaction module if
  needed to make real event wiring directly testable;
- `am_configurator/web/app.js`, `am_configurator/web/index.html`, and
  `am_configurator/web/style.css` for visible interaction and exact overlay
  placement;
- `am_configurator/media_composition.py` and
  `am_configurator/device_mapping.py` for backend canonicalization;
- media, mapping, endpoint, browser, desktop, and packaging tests;
- one shared geometry-vector fixture consumed by Python and Node; and
- a native, no-hardware imported-media audit path that is runnable from source
  and the frozen application.

No dependency or lockfile change is expected. If implementation appears to
require Playwright, Selenium, FFmpeg/libav, another decoder, another webview,
or any new direct dependency, stop and request a separate owner decision.

Out of scope:

- changing the imported-media version-1 persistence schema;
- changing AI generation or routing imported media through AI;
- changing device maps, LED orientation, firmware protocol, or write gates;
- adding video formats beyond GIF, PNG, and BMP;
- redesigning unrelated Lighting Studio controls; and
- release publication or any separately gated action.

## Implementation slices

Each slice receives one independent commit after its red/green proof and
relevant automated verification pass. Run exactly one `fable-review` job with
model `claude-fable-5` at `xhigh` over that committed slice, use its substantive
result regardless of envelope formatting, and do not rerun or resubmit it
without explicit owner approval. Push verified work normally to canonical `origin`.
A review finding fixed under this approved scope lands as a new commit; never
amend or rewrite the reviewed commit.

### Slice IMF-1 - Canonical geometry in browser and backend

Implement one geometry contract on both sides and guard it with a shared vector
corpus.

Requirements:

1. Add pure browser helpers that validate sizes, compute the exact raster box,
   intersect multi-target offset limits, and return a canonical version-1
   transform without mutating inputs.
2. Add equivalent Python helpers. Use one explicit rounding rule; do not rely
   on the Python/JavaScript default-rounding difference.
3. Keep `validate_source_transform` as schema/persistence validation. Invoke
   geometry canonicalization defensively in `render_source_frame`, normal
   multi-target composition, and Move & zoom rendering.
4. Resolve all requested target sizes before normal or Move & zoom rendering.
   Return the canonical base transform and the exact resolved Move & zoom
   transform array used by the backend.
5. Route presets, pan, zoom, stretch, destination refresh, and Move & zoom
   construction through the browser helper. Re-constrain offsets after every
   scale or target change.
6. Preserve the exact legacy center-crop fast path for the canonical default
   transform.
7. Cover same-size 40x5, extreme aspect ratios, independent axes, minimum and
   maximum supported scales, odd raster dimensions, multi-target intersection,
   and Move & zoom frames in the shared vectors. Include a same-size source and
   destination at scale 32: its raw per-axis overlap limit is 15.5, but both
   runtimes must cap the canonical limit at exactly 8 and keep every returned
   offset within the version-1 schema range of ±8.
8. Prove that every canonical box has maximum possible overlap and that the
   rejected 40x5 pan becomes zero rather than an almost-black output.

Implementation record, 2026-08-01:

- The shared JSON corpus covers the required 40x5, extreme-ratio,
  independent-axis, minimum/maximum-scale, odd-raster, multi-target, scale-32,
  and Move & zoom cases. Before the implementation, Python and Node both
  lacked the shared resolver and the rejected 40x5 transform rendered all 200
  output pixels black. After the implementation, both runtimes match every
  vector exactly and the same render retains all 200 red source pixels.
- The endpoint non-vacuity check failed when its response was temporarily put
  back on the old unchecked-transform behavior, then passed after restoring
  the backend canonical transform and resolved Move & zoom array.
- Focused verification passed 171 Python tests with one expected platform
  skip, six compositor tests, and both required JavaScript syntax checks.
- The complete CI-equivalent local gate passed 664 Python tests with five
  expected platform skips, 129 web tests, all compile/syntax checks, and both
  `0.1.65` source and wheel builds. No dependency, lockfile, FFmpeg/libav,
  provider, hardware, tag, Release, security-setting, or announcement path
  changed or ran.
- The required one-time `fable-review` change review used
  `claude-fable-5` at `xhigh` over exact range
  `6bf41b9a0a04b03e84cfbc5ea16794d7eb5fe4b3..4a9e6b89233e9549a4b9b05ca14613a2f2115eb6`.
  It returned schema-valid `clean`, `capability_ok=true`, exact pinned SHAs,
  no findings, exit 0, and no stderr. The first result was persisted and used;
  no retry, reformat, replacement, or resubmission occurred.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_media tests.test_device_mapping tests.test_app -v
node --test tests/web/lighting_composer.test.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/app.js
```

Landed implementation commit:

```text
4a9e6b89233e9549a4b9b05ca14613a2f2115eb6 — fix: bound imported media framing geometry
```

### Slice IMF-2 - Faithful live preview and robust input wiring

Make every ordinary input visibly operate the canonical transform without a
backend round trip.

Requirements:

1. Keep the source overlay available for the life of an active media draft and
   switch it visibly on before any transform mutation.
2. Replace the fixed cover approximation with an overflow-clipped source
   viewport and the exact primary-target raster box returned by the browser
   geometry helper. Do not clip the LED grid or destination border.
3. Centralize pointer, wheel, keyboard, preset, zoom, and stretch mutations so
   they all activate source view, canonicalize, invalidate Preview, update
   controls, update overlay geometry, and update status through one path.
4. Implement the stage-scoped primary-pointer session and all release cases
   from the framing contract. Wrap `setPointerCapture` narrowly: continue only
   for `NotFoundError`, and do not hide other capture failures. Do not depend on
   a document-global mouse fallback.
5. Keep LED-result mode useful for inspecting the last accepted backend
   Preview, but never let a framing action mutate state invisibly in that mode.
6. Add dependency-free Node tests with fake event targets that dispatch the
   actual event sequence and assert capture, pointer-ID isolation, release,
   keyboard/wheel equivalence, visible-mode activation, canonical state, and
   synchronous view updates. One fake target must throw `NotFoundError` from
   `setPointerCapture`; the same untrusted drag must still update framing,
   release its listeners, and produce no console error.
7. Add markup/style guards for the overlay box, focus visibility, dragging
   cursor/state, reduced motion, and the two release-blocking viewports.

Implementation record, 2026-08-01:

- One dependency-free stage controller now owns primary-pointer identity,
  stage-scoped move/up/cancel/lost-capture listeners, wheel and keyboard
  equivalence, focus, dragging state, and teardown. A synthetic
  `NotFoundError` from pointer capture continues the same session; every other
  capture error cleans up and remains visible to the caller.
- Every framing input uses one source-transform commit path that reveals the
  imported-media view before mutation, canonicalizes and invalidates the
  accepted Preview, then synchronously updates the exact overlay box, numeric
  controls, status, and Apply availability. Only an accepted current render
  switches back to LED-result mode; a stale render cannot hide newer framing.
- The imported source viewport remains mounted for an active media draft. It
  is destination-sized and is the only clipping boundary; its image uses the
  primary target's resolved `left`, `top`, rendered width, and rendered height.
  The LED grid and destination border remain sibling layers outside that
  viewport.
- Before implementation, five new Node guards failed because the stage
  controller, live overlay markup, exact CSS geometry, and release-viewport
  constraints were absent. After implementation all pass. Separately removing
  the stale-render acceptance check made the shell guard fail; restoring it
  returned the guard to green.
- Focused verification passed 134 web tests, 181 Python app/packaging tests
  with three expected platform skips, and both required JavaScript syntax
  checks. No dependency, lockfile, FFmpeg/libav, provider, hardware, tag,
  Release, security-setting, or announcement path changed or ran.
- The required one-time `fable-review` change review used
  `claude-fable-5` at `xhigh` over exact range
  `042f55003c9e56e14ce023cc201bb0d62fd89c98..041c26fe2c069b1a237464aedd8fb150c1cb89c1`.
  It returned schema-valid `clean`, `capability_ok=true`, exact pinned SHAs,
  no findings, exit 0, and no stderr. The first result was persisted and used;
  no retry, reformat, replacement, or resubmission occurred.

Focused verification:

```text
node --test tests/web/*.test.js
node --check am_configurator/web/lighting_composer.js
node --check am_configurator/web/app.js
uv run --frozen python -m unittest tests.test_app tests.test_packaging -v
```

Landed implementation commit:

```text
041c26fe2c069b1a237464aedd8fb150c1cb89c1 — fix: show imported media framing as it changes
```

### Slice IMF-3 - End-to-end pixel and native-webview proof

Close the coverage gap that allowed the rejected candidate to pass.

Requirements:

1. Generate asymmetric, anonymous GIF, PNG, and BMP fixtures in tests. Each
   contains sentinel colors whose expected destination pixels and non-black
   count are asserted directly; frame count alone is not evidence.
2. Exercise raw import, saved source retrieval, constrained transform, Preview,
   stale-Preview invalidation, Apply to the open slot, Undo, Save to Library,
   Library apply/remove/undo/restore/permanent-delete confirmation, and Cancel.
3. Prove Apply occurs exactly once and only after an accepted current Preview.
   Prove Undo restores the document and dirty indicator together.
4. Add a dependency-free native audit mode using the existing PyWebView and
   local server. It must use isolated temporary application-data and Library
   roots, synthetic CB04 data, disabled device discovery, and cleared provider
   credential variables. It must never scan or write a physical keyboard.
5. Drive the real DOM in the platform renderer: inject each anonymous media
   fixture, dispatch an untrusted primary-pointer sequence whose capture call
   takes the specified `NotFoundError` path, then dispatch keyboard and slider
   operations. Inspect the live overlay box before Preview, invoke Preview, and
   assert the exact mapped sentinel pixels and workflow state.
6. Run the native audit at 1000x680 and 1280x800. Assert no viewport/container
   escape, no console error, visible focus, immediate drag feedback, and
   browser/backend canonical-transform equality.
7. Add the explicit CLI form
   `--media-framing-audit <sanitized-result.json>` to the normal desktop entry
   point and frozen executable. The exact Windows candidate must therefore be
   able to prove the shipped WebView2 path without Computer Use, Playwright, or
   manual drag timing. Reject combinations with ordinary config paths or other
   smoke modes instead of silently choosing one.
8. Emit only a bounded sanitized JSON result. Verify exact temporary roots
   before recursive cleanup and leave provider keys, user Library roots,
   profiles, firmware identifiers, and screenshots out of the result.

Implementation record, 2026-08-01:

- One pathless fixture builder now emits asymmetric 20x5 GIF, PNG, and BMP
  bytes with exact expected sentinel pixels and non-black counts. Python proves
  the decoded frames before the same expectations are injected into the native
  workflow; the GIF proof covers its complete normalized output sequence.
- The normal desktop entry point accepts only the explicit
  `--media-framing-audit RESULT.json` form and rejects configuration paths and
  every other smoke/probe mode. The audit uses a private temporary data root,
  private Library root, synthetic blank CB04 document, in-memory credentials,
  offline device discovery, cleared provider variables, verified exact-root
  cleanup, and one bounded pathless JSON result.
- The real DOM workflow now covers raw import, saved-source byte retrieval,
  pointer capture's `NotFoundError` path, immediate pointer/keyboard/slider
  geometry, stale Preview rejection, browser/backend transform equality, exact
  mapped pixels, single Apply, Undo/dirty state, Save to Library, Library
  apply/remove/undo/restore/permanent-delete confirmation, and Cancel.
- Audit-driven support fixes keep a Library ownership mutation busy through its
  forced refresh, keep Undo disabled until that refresh is ready, retry bounded
  Windows sharing contention around directory moves and tree deletion, make a
  keyboard pan move by at least one primary-destination raster cell, and remove
  reduced-motion transitions without creating zero-duration geometry updates.
- Before implementation the native audit module, CLI dispatch, and end-to-end
  workflow did not exist. The native-window activation guard separately failed
  with the helper absent and passed after the audit began activating the real
  PyWebView window and waiting for `document.hasFocus()` before visual focus
  assertions.
- Focused verification passed 319 Python tests with five expected platform
  skips, the complete web test suite, and both changed JavaScript syntax checks.
  `python build.py --skip-sync` passed the native-tree audit and built the
  Windows installer; frozen `--smoke-test` passed.
- Source and exact rebuilt frozen WebView2 audits each passed GIF, PNG, and BMP
  at 1000x680 and 1280x800 with no console errors or layout findings. A visual
  focus audit must run as a normal visible native window; an explicitly hidden
  Windows launch cannot own top-level focus and now fails the explicit
  `webview_focus_timeout` precondition instead of mislabeling product focus CSS.
- The canonical full command chain reached its final `uv build`, which emitted
  valid `0.1.65` source and wheel archives containing the audit module; every
  earlier guarded test, compile, and syntax command had exited zero. PTK lost
  its worker transport immediately after the two archives were written, so the
  outer wrapper did not return its final exit envelope and the completed run
  was not resubmitted. No dependency, lockfile, FFmpeg/libav, provider,
  hardware, tag, Release, security-setting, or announcement path changed or ran.

Focused verification:

```text
uv run --frozen python -m unittest tests.test_media tests.test_device_mapping tests.test_app tests.test_desktop tests.test_library tests.test_packaging -v
node --test tests/web/*.test.js
```

Then run the new native audit directly on `netwatch-01` in Windows WebView2 at
both required sizes. Build through `python build.py --skip-sync`, run frozen
`--smoke-test`, and repeat the native audit from the frozen executable. Do not
use PyInstaller directly. Launch each visual audit as a normal visible native
window and wait for its process; `-WindowStyle Hidden` invalidates the focus
precondition and is not a valid audit invocation.

Proposed commit:

```text
test: prove imported media framing end to end
```

## Red/green proof

Every new guard must fail against the pre-slice behavior for the behavior it
claims to protect, then pass after restoration of the fix.

At minimum, preserve these red proofs in the slice completion records:

- the rejected 40x5 transform is accepted/off-canvas before IMF-1 and clamps
  to the maximum-overlap box after it;
- browser and backend vector results disagree or are unavailable before IMF-1
  and match exactly after it;
- a pointer sequence mutates state without a visible overlay update before
  IMF-2 and updates synchronously after it;
- the old fixed-cover overlay disagrees with the exact raster box before IMF-2
  and matches after it; and
- the native GIF/PNG/BMP workflow test is absent or fails on the old wiring and
  passes on Windows WebView2 after IMF-3.

Do not weaken a failing assertion, substitute a frame-count check for pixels,
or accept screenshot timing as automated input proof.

## Full verification and qualification sequence

After all approved repair slices and any admitted review findings land:

1. run the complete canonical verification entry point from
   `.agents/repo-guidance.md` in the CI-shaped no-extra environment;
2. run the source and frozen Windows WebView2 native audits at 1000x680 and
   1280x800 on `netwatch-01`;
3. build, smoke, install/audit, and uninstall the current Windows package as
   required for a native distribution change;
4. require exact-head CI and Desktop installer workflows to pass after every
   final implementation commit;
5. record sanitized slice evidence in this plan and current state;
6. restart public-release R65-2 on a clean, reconciled `main` and freeze a new
   candidate SHA;
7. rerun R65-3 and R65-4 for the complete new artifact set;
8. run R65-5 functional UI qualification on the exact Windows artifact first,
   using the native audit plus direct visual inspection; and
9. use the exact macOS DMG only for the final WKWebView/Gatekeeper and
   cross-platform UI regression pass. A macOS pass cannot replace the Windows
   proof, and a Windows pass cannot replace final exact-DMG qualification.

R65-6 hardware authorization remains pending until the new candidate has
passed R65-5. Publication and announcement gates remain later and separate.

## Completion criteria

This repair is complete only when:

- all three slices and every admitted finding are independently committed,
  verified, reviewed once with `claude-fable-5` at `xhigh`, and pushed;
- browser and Python share passing exact geometry vectors;
- the backend cannot produce an off-canvas result from an ordinary canonical
  framing operation;
- pointer, keyboard, wheel, slider, preset, zoom, and stretch changes are
  immediately visible and invalidate stale Preview state;
- exact GIF, PNG, and BMP pixels pass through Preview, Apply, Undo, and Library
  workflows;
- source and frozen Windows WebView2 audits pass at both required viewports;
- the canonical full gate and exact-head CI/Desktop workflows pass; and
- no dependency, FFmpeg/libav path, AI-media behavior, provider use, hardware
  write, security-setting change, tag, Release, or announcement was added or
  performed.

## Failure policy

- If maximum-overlap constraints cannot preserve an existing supported
  composition contract, stop and present the concrete conflicting case before
  changing the schema or behavior.
- If native automation would require a new dependency or a production security
  exception, stop. Do not add the dependency or bypass the platform boundary.
- If Windows WebView2 still cannot show immediate real drag feedback, the
  repair is not complete even when reducers and backend pixels pass.
- If a code or documentation correction moves `main` after a new candidate is
  frozen, reject that candidate and restart R65-2. Never patch candidate bytes.
