# Qwen3 4B Q4_K_M qualification — rejected

> **Historical evidence only.** This rejected direct-GGUF experiment is not a
> supported product, setup, build, verification, or release path. The shipped
> application is Ollama or curated API only. The recorded JSON and gallery
> remain unchanged for comparison; normal repo tooling can no longer execute or
> regenerate the llama/GGUF experiment. Current authority is the
> [Ollama/API-only decision](../../../.agents/decisions.md#2026-07-22--ollamaapi-only-ai-backends)
> and its [holistic remediation plan](../../superpowers/plans/2026-07-22-holistic-branch-remediation.md).

## Decision

The pinned Qwen3 4B Q4_K_M candidate is **not qualified as a release local
recipe model**. Six of twelve committed corpus cases passed the unchanged
procedural quality gate within the initial attempt plus two retries. Because
the gate requires every case to pass, no local model catalog entry was added.

The complete machine-readable result, including every attempt and its final
quality metrics, is [qualification.json](qualification.json).

## Immutable inputs

- Model: `Qwen/Qwen3-4B-GGUF`, `Qwen3-4B-Q4_K_M.gguf`, revision
  `bc640142c66e1fdd12af0bd68f40445458f3869b`, 2,497,280,256 bytes, SHA-256
  `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
  The upstream model card declares Apache-2.0.
- Runtime: official llama.cpp release `b9637`, commit
  `aedb2a5e9ca3d4064148bbb919e0ddc0c1b70ab3`, built locally with Metal.
- Corpus: `tests/fixtures/procedural_prompt_cases.json` at repository commit
  `a14c7f3`.
- Recipe contract and thresholds: `am_configurator/procedural.py` at repository
  commit `a14c7f3`.

The official llama.cpp security advisories were checked on 2026-07-21. The
published affected ranges ended before `b9637`; the critical RPC advisory is
also outside the qualification path because RPC was not built or enabled.

## Qualification host

- MacBook Pro `Mac16,5`
- Apple M4 Max: 16 CPU cores (12 performance, 4 efficiency), 40 GPU cores
- 48 GiB unified memory
- macOS 26.5.2 (`25F84`), arm64, Metal 4
- AppleClang 21.0.0.21000101

The runtime reported the Apple M4 Max Metal device with 38,338 MiB free and
confirmed that all 37 of 37 model layers were offloaded to the GPU. Inference
used a local verified model file with `--offline`, a 4,096-token context,
1,536-token output cap, fixed seeds 7319–7321, flash attention, full GPU layer
offload, auto-fit disabled, and the production JSON schema. The b9637 Jinja
path failed while prefilling the non-thinking marker into the JSON grammar, so
qualification used b9637's built-in non-Jinja model template; grammar
constraining and semantic validation remained enabled.

## Per-case result

`Gen s` is cumulative model-process time across the recorded attempts. Lit
ratios, brightness, adjacent-frame difference, and loop-seam difference are
from the final attempt. Every rendered attempt was rendered twice and compared
byte-for-byte before quality assessment.

| Case | Result | Attempts | Gen s | Lit ratio min–max | Peak | Motion | Seam | Final reason | Gallery |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| relic-sparse-comets | pass | 1 | 4.191 | 0.016–0.040 | 221 | 0.392 | 0.384 | — | [GIF](gallery/relic-sparse-comets.gif) |
| relic-dense-aurora | pass | 1 | 5.441 | 1.000–1.000 | 252 | 4.690 | 4.471 | — | [GIF](gallery/relic-dense-aurora.gif) |
| cyberboard-keys-balanced-fire | fail | 3 | 17.643 | 0.533–1.000 | 252 | 6.889 | 5.244 | balanced density exceeded the 0.95 maximum | none; rejected output |
| cyberboard-display-sweep | fail | 3 | 14.223 | 1.000–1.000 | 255 | 12.300 | 12.300 | balanced density exceeded the 0.95 maximum | none; rejected output |
| afa-pulse-orbit | fail | 3 | 11.604 | 1.000–1.000 | 184 | 1.300 | 0.104 | balanced density exceeded the 0.95 maximum | none; rejected output |
| relic-sparse-sparkles | fail | 3 | 6.384 | 0.000–0.008 | 47 | 0.071 | 0.032 | peak brightness did not exceed 180 | none; rejected output |
| relic-ambiguous | pass | 3 | 15.960 | 0.405–0.794 | 215 | 5.892 | 4.362 | — | [GIF](gallery/relic-ambiguous.gif) |
| afa-multilingual-ocean | fail | 3 | 14.391 | 0.438–1.000 | 246 | 2.396 | 1.854 | dense density fell below the 0.70 minimum | none; rejected output |
| cyberboard-adversarial-video | pass | 2 | 12.050 | 0.400–0.850 | 231 | 3.917 | 3.478 | — | [GIF](gallery/cyberboard-adversarial-video.gif) |
| relic-adversarial-primitives | fail | 3 | 20.881 | — | — | — | — | recipe selected the wrong density class | none; rejected before render |
| cyberboard-long-layered | pass | 1 | 4.493 | 0.778–0.944 | 246 | 10.089 | 7.941 | — | [GIF](gallery/cyberboard-long-layered.gif) |
| afa-fast-comets | pass | 1 | 3.242 | 0.075–0.100 | 203 | 1.842 | 1.725 | — | [GIF](gallery/afa-fast-comets.gif) |

The successful GIFs are exact device-resolution raster evidence; Markdown or a
browser may enlarge them with nearest-neighbor scaling. Failed attempts have no
gallery artifact because the qualification writer publishes artifacts only
after the unchanged quality gate accepts them.

## Outcome

Local AI remains unreleased and has no catalog selection. API-mode work and
manual lighting are unaffected. A different local candidate requires a new
approved qualification task; these failures are not grounds to alter the
committed schema, density classes, brightness, motion, or seam thresholds.

## Sources

- Model revision and artifact: <https://huggingface.co/Qwen/Qwen3-4B-GGUF/blob/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf>
- Model card and Apache-2.0 declaration: <https://huggingface.co/Qwen/Qwen3-4B-GGUF>
- llama.cpp release record: <https://github.com/ggml-org/llama.cpp/releases/tag/b9637>
- llama.cpp security advisories: <https://github.com/ggml-org/llama.cpp/security/advisories>
