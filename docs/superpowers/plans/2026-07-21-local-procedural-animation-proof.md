# Local Procedural Animation Proof

**Status:** Approved by the owner on 2026-07-21: build only an isolated proof using the already-installed Ollama model, a validated recipe, and a local renderer; do not change the application UI or call xAI.

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
