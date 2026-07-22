# Local Procedural Animation Proof

**Status:** Implemented in `c6d46cc` and corrected in `2078a0b`. The proof remains isolated from the application UI.

## Goal

Prove that a local language model can translate a natural-language lighting prompt into a constrained animation recipe whose deterministic local rendering is visibly useful on a Relic 80 LED raster. The proof must emit the exact device frames and a directly inspectable looping GIF from the same pixels.

## Scope

- Add an isolated Python module and command-line entry point; do not wire it into the desktop application or settings.
- Call the local Ollama HTTP API at loopback only, defaulting to the already-installed `gemma4:12b-mlx` model.
- Require Ollama structured output against a strict JSON schema. Validate all semantic bounds and reject unknown data before rendering.
- Support a small composable primitive set designed for low-resolution LEDs: comets, waves, radial pulses, sparkles, orbits, sweeps, and periodic noise.
- Render every primitive as a periodic function of normalized loop phase so the final-to-first transition is one ordinary frame step.
- Default the proof to the Relic 80 target: `18x7`, 200 frames, 34 ms firmware timing, `keyframes` plus `spotlight_frames`.
- Write `recipe.json`, an exact-raster GIF, a nearest-neighbor enlarged preview GIF, and the existing shared mapper's LED JSON into a caller-selected output directory.
- Add deterministic offline tests for schema rejection, exact frame count and dimensions, loop-boundary continuity, reproducibility, GIF output, shared mapping parity, and the Ollama request/response boundary.
- Run one local generation for `shooting stars on a black background`; no cloud provider call or device write is permitted.

## Verification

1. Prove each new regression test fails before its implementation and passes afterward.
2. Run the repository verification entry point from `.agents/repo-guidance.md`.
3. Run the local proof with `gemma4:12b-mlx` and inspect the emitted artifact metadata and GIF dimensions/frame counts.
4. Commit the implementation as one isolated proof slice, then record its result in `.agents/state.md`.

## Outcome

- `gemma4:12b-mlx` ignored Ollama's requested JSON schema and did not produce a usable recipe after correction attempts.
- `ornith:latest` produced a semantically valid recipe after the bounded retry path and is therefore the proof's default model.
- The saved shooting-stars recipe rendered as an exact 18×7, 200-frame, 6.8-second loop and mapped through the existing Relic 80 frame conversion without a cloud provider call or device write.
- Visual inspection exposed and then closed an unsafe width interpretation that originally turned the effect into a full-board wash. The guarded rerender is a dark, sparse sequence of bright comet trails with an ordinary final-to-first frame step.
