"""Qualify strict procedural recipes against the committed prompt corpus.

The reusable functions are provider-neutral.  The command-line adapter may use
the isolated Ollama developer client, but tests and release builds never invoke
it or perform network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from am_configurator.procedural import (
    DENSITIES,
    QualityError,
    RecipeError,
    map_frames_to_led_tracks,
    recipe_schema,
    recipe_system_prompt,
    render_recipe,
    validate_quality,
    validate_recipe,
    write_animation_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "tests" / "fixtures" / "procedural_prompt_cases.json"
MAX_CORPUS_BYTES = 1_000_000
MAX_MODEL_OUTPUT_BYTES = 1_000_000
LOCAL_MODEL_ATTEMPTS = 3
LOCAL_MODEL_SEED = 7319
_CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROOT_KEYS = {"schema_version", "cases"}
_CASE_KEYS = {
    "id",
    "prompt",
    "density",
    "product_id",
    "targets",
    "width",
    "height",
    "frame_count",
    "tags",
}


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    density: str
    product_id: str
    targets: tuple[str, ...]
    width: int
    height: int
    frame_count: int
    tags: tuple[str, ...]


class LlamaCliRecipeClient:
    """Bounded offline llama.cpp adapter for release-model qualification."""

    def __init__(
        self,
        runtime: Path | str,
        model: Path | str,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout_seconds: float = 180,
    ) -> None:
        runtime_path = Path(runtime).resolve()
        model_path = Path(model).resolve()
        if not runtime_path.is_file():
            raise ValueError("llama.cpp runtime must be an existing regular file.")
        if not model_path.is_file():
            raise ValueError("Local model must be an existing regular file.")
        if timeout_seconds <= 0 or timeout_seconds > 600:
            raise ValueError("llama.cpp timeout must be between 0 and 600 seconds.")
        self.runtime = runtime_path
        self.model = model_path
        self.runner = runner
        self.timeout_seconds = float(timeout_seconds)

    def generate(
        self,
        case: PromptCase,
        attempt: int = 0,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Generate one schema-constrained recipe from local immutable inputs."""

        if isinstance(attempt, bool) or not 0 <= attempt < LOCAL_MODEL_ATTEMPTS:
            raise ValueError("Local model attempt must be 0, 1, or 2.")
        user_prompt = case.prompt
        if feedback:
            user_prompt += (
                "\n\nThe previous recipe failed validation: "
                f"{feedback} Return a corrected complete recipe."
            )
        user_prompt += "\n/no_think"
        arguments = (
            str(self.runtime),
            "--model",
            str(self.model),
            "--offline",
            "--ctx-size",
            "4096",
            "--batch-size",
            "512",
            "--ubatch-size",
            "512",
            "--predict",
            "1536",
            "--gpu-layers",
            "all",
            "--fit",
            "off",
            "--flash-attn",
            "on",
            "--temp",
            "0.7",
            "--top-k",
            "20",
            "--top-p",
            "0.8",
            "--min-p",
            "0",
            "--presence-penalty",
            "1.5",
            "--seed",
            str(LOCAL_MODEL_SEED + attempt),
            "--json-schema",
            json.dumps(recipe_schema(), separators=(",", ":")),
            "--system-prompt",
            recipe_system_prompt(
                case.width,
                case.height,
                case.frame_count,
                density_default=case.density,
            ),
            "--prompt",
            user_prompt,
            "--reasoning",
            "off",
            "--reasoning-budget",
            "0",
            # b9637's Jinja path prefills Qwen's closed thinking block into the
            # JSON grammar and aborts sampler initialization. Its built-in
            # model template keeps the same chat contract without that prefill.
            "--no-jinja",
            "--single-turn",
            "--simple-io",
            "--no-display-prompt",
            "--no-show-timings",
            "--log-disable",
        )
        try:
            completed = self.runner(
                arguments,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise RecipeError("Local model inference timed out.") from None
        except OSError:
            raise RecipeError("Local model runtime could not be executed.") from None
        stdout = completed.stdout
        stderr = completed.stderr
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise RecipeError("Local model runtime returned invalid process output.")
        if (
            len(stdout.encode("utf-8")) > MAX_MODEL_OUTPUT_BYTES
            or len(stderr.encode("utf-8")) > MAX_MODEL_OUTPUT_BYTES
        ):
            raise RecipeError("Local model output exceeded the size limit.")
        if completed.returncode != 0:
            raise RecipeError(
                f"Local model runtime exited with status {completed.returncode}."
            )
        recipe_text = stdout.strip()
        prompt_marker = f"\n> {user_prompt}\n\n"
        exit_marker = "\n\n\nExiting..."
        if prompt_marker in stdout:
            recipe_text = stdout.rpartition(prompt_marker)[2]
            if exit_marker not in recipe_text:
                raise RecipeError("Local model output framing was invalid.")
            recipe_text = recipe_text.rpartition(exit_marker)[0].strip()
        try:
            recipe = json.loads(recipe_text)
        except json.JSONDecodeError:
            raise RecipeError("Local model output was not valid JSON.") from None
        return validate_recipe(recipe)


def _exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} does not match the qualification schema.")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def load_prompt_corpus(path: Path | str = DEFAULT_CORPUS) -> tuple[PromptCase, ...]:
    """Load and strictly validate the bounded committed qualification corpus."""

    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise ValueError("Qualification corpus could not be read.") from None
    if len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("Qualification corpus exceeds the size limit.")
    try:
        root = _exact_dict(json.loads(raw), _ROOT_KEYS, "Qualification corpus")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Qualification corpus is not valid UTF-8 JSON.") from None
    if (
        isinstance(root["schema_version"], bool)
        or not isinstance(root["schema_version"], int)
        or root["schema_version"] != 1
    ):
        raise ValueError("Qualification corpus schema version is unsupported.")
    if not isinstance(root["cases"], list) or not root["cases"]:
        raise ValueError("Qualification corpus must contain at least one case.")

    cases: list[PromptCase] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(root["cases"]):
        value = _exact_dict(raw_case, _CASE_KEYS, f"Qualification case {index + 1}")
        case_id = value["id"]
        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise ValueError(f"Qualification case {index + 1} has an invalid id.")
        if case_id in seen_ids:
            raise ValueError("Qualification case ids must be unique.")
        seen_ids.add(case_id)
        prompt = value["prompt"]
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise ValueError(f"Qualification case {case_id} has an invalid prompt.")
        density = value["density"]
        if density not in DENSITIES:
            raise ValueError(f"Qualification case {case_id} has an invalid density.")
        product_id = value["product_id"]
        targets_value = value["targets"]
        if (
            not isinstance(product_id, str)
            or not isinstance(targets_value, list)
            or not targets_value
            or any(not isinstance(target, str) for target in targets_value)
            or len(set(targets_value)) != len(targets_value)
        ):
            raise ValueError(f"Qualification case {case_id} has invalid targets.")
        width = _positive_int(value["width"], f"Qualification case {case_id} width")
        height = _positive_int(value["height"], f"Qualification case {case_id} height")
        frame_count = _positive_int(
            value["frame_count"], f"Qualification case {case_id} frame count"
        )
        targets = tuple(targets_value)
        try:
            from am_configurator.server import generation_spec

            spec, canonical_targets = generation_spec(product_id, targets, None)
        except ValueError:
            raise ValueError(
                f"Qualification case {case_id} does not match a supported device target."
            ) from None
        if (
            tuple(canonical_targets) != targets
            or (spec.width, spec.height, spec.max_frames)
            != (width, height, frame_count)
        ):
            raise ValueError(
                f"Qualification case {case_id} does not match a supported device target."
            )
        tags_value = value["tags"]
        if (
            not isinstance(tags_value, list)
            or not tags_value
            or any(not isinstance(tag, str) or not tag for tag in tags_value)
            or len(set(tags_value)) != len(tags_value)
        ):
            raise ValueError(f"Qualification case {case_id} has invalid tags.")
        cases.append(
            PromptCase(
                case_id=case_id,
                prompt=prompt.strip(),
                density=density,
                product_id=product_id,
                targets=targets,
                width=width,
                height=height,
                frame_count=frame_count,
                tags=tuple(tags_value),
            )
        )
    return tuple(cases)


def qualify_recipe(
    case: PromptCase,
    recipe: dict[str, Any],
    *,
    output_directory: Path | None = None,
) -> dict[str, Any]:
    """Render and assess one model recipe, returning deterministic evidence."""

    started = time.monotonic()
    try:
        normalized = validate_recipe(recipe)
        if normalized["density"] != case.density:
            raise RecipeError("Recipe density does not match the qualification case.")
        frames = render_recipe(
            normalized,
            width=case.width,
            height=case.height,
            frame_count=case.frame_count,
        )
        repeated = render_recipe(
            normalized,
            width=case.width,
            height=case.height,
            frame_count=case.frame_count,
        )
        if [frame.tobytes() for frame in frames] != [frame.tobytes() for frame in repeated]:
            raise RecipeError("Procedural rendering is not deterministic.")
        quality = validate_quality(
            normalized,
            frames,
            width=case.width,
            height=case.height,
            frame_count=case.frame_count,
        )
        mapped = map_frames_to_led_tracks(
            frames,
            duration_ms=34,
            product_id=case.product_id,
            targets=case.targets,
        )
        artifacts: dict[str, str] = {}
        if output_directory is not None:
            paths = write_animation_artifacts(
                normalized,
                output_directory,
                width=case.width,
                height=case.height,
                frame_count=case.frame_count,
                duration_ms=34,
                product_id=case.product_id,
                targets=case.targets,
            )
            artifacts = {key: path.name for key, path in paths.items()}
        return {
            "case_id": case.case_id,
            "passed": True,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "quality": quality.to_dict(),
            "mapped_tracks": {
                name: track["frame_count"] for name, track in mapped["tracks"].items()
            },
            "artifacts": artifacts,
        }
    except RecipeError as exc:
        result: dict[str, Any] = {
            "case_id": case.case_id,
            "passed": False,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "error": str(exc),
        }
        if isinstance(exc, QualityError) and exc.metrics is not None:
            result["quality"] = exc.metrics.to_dict()
        return result


RecipeGenerator = Callable[[PromptCase], dict[str, Any]]
RetryRecipeGenerator = Callable[[PromptCase, int, str | None], dict[str, Any]]


def qualify_local_case(
    case: PromptCase,
    generate: RetryRecipeGenerator,
    *,
    output_directory: Path | None = None,
) -> dict[str, Any]:
    """Generate and qualify one case with at most two corrective retries."""

    attempts: list[dict[str, Any]] = []
    feedback: str | None = None
    total_generation_seconds = 0.0
    result: dict[str, Any] = {
        "case_id": case.case_id,
        "passed": False,
        "error": "Local model did not return a usable recipe.",
    }
    for attempt in range(LOCAL_MODEL_ATTEMPTS):
        generation_started = time.monotonic()
        try:
            recipe = generate(case, attempt, feedback)
        except RecipeError as exc:
            generation_seconds = round(
                time.monotonic() - generation_started, 6
            )
            total_generation_seconds += generation_seconds
            result = {
                "case_id": case.case_id,
                "passed": False,
                "error": str(exc),
            }
        else:
            generation_seconds = round(
                time.monotonic() - generation_started, 6
            )
            total_generation_seconds += generation_seconds
            result = qualify_recipe(
                case,
                recipe,
                output_directory=output_directory,
            )
        attempt_result: dict[str, Any] = {
            "attempt": attempt + 1,
            "seed": LOCAL_MODEL_SEED + attempt,
            "generation_seconds": generation_seconds,
            "passed": result["passed"],
        }
        if not result["passed"]:
            attempt_result["error"] = result["error"]
            if "quality" in result:
                attempt_result["quality"] = result["quality"]
        attempts.append(attempt_result)
        if result["passed"]:
            break
        feedback = result["error"]

    result["attempt_count"] = len(attempts)
    result["generation_seconds"] = round(total_generation_seconds, 6)
    result["attempts"] = attempts
    return result


def qualify_local_model(
    cases: Sequence[PromptCase],
    generate: RetryRecipeGenerator,
    *,
    output_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Qualify a local model sequentially with the production retry policy."""

    results = []
    for case in cases:
        case_output = output_directory / case.case_id if output_directory else None
        results.append(
            qualify_local_case(case, generate, output_directory=case_output)
        )
    return results


def qualify_model(
    cases: Sequence[PromptCase],
    generate: RecipeGenerator,
    *,
    output_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Generate and qualify cases sequentially through an injected provider."""

    results = []
    for case in cases:
        case_output = output_directory / case.case_id if output_directory else None
        generation_started = time.monotonic()
        try:
            recipe = generate(case)
        except RecipeError as exc:
            results.append(
                {
                    "case_id": case.case_id,
                    "passed": False,
                    "generation_seconds": round(
                        time.monotonic() - generation_started, 6
                    ),
                    "error": str(exc),
                }
            )
            continue
        generation_seconds = round(time.monotonic() - generation_started, 6)
        result = qualify_recipe(case, recipe, output_directory=case_output)
        result["generation_seconds"] = generation_seconds
        results.append(result)
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="ornith:latest")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--llama-cli", type=Path)
    parser.add_argument("--model-file", type=Path)
    parser.add_argument("--runtime-revision")
    parser.add_argument("--model-revision")
    parser.add_argument("--model-sha256")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--case", action="append", dest="case_ids")
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = load_prompt_corpus(args.corpus)
        if args.case_ids:
            selected = set(args.case_ids)
            cases = tuple(case for case in cases if case.case_id in selected)
            if {case.case_id for case in cases} != selected:
                raise ValueError("One or more requested qualification cases do not exist.")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        local_requested = args.llama_cli is not None or args.model_file is not None
        if local_requested:
            if args.llama_cli is None or args.model_file is None:
                raise ValueError("--llama-cli and --model-file must be used together.")
            if not args.runtime_revision or not args.model_revision:
                raise ValueError(
                    "Local qualification requires runtime and model revisions."
                )
            if not args.model_sha256 or not _SHA256.fullmatch(args.model_sha256):
                raise ValueError(
                    "Local qualification requires a lowercase expected model SHA-256."
                )
            model_path = args.model_file.resolve()
            if not model_path.is_file():
                raise ValueError("Local model must be an existing regular file.")
            actual_sha256 = _sha256(model_path)
            if actual_sha256 != args.model_sha256:
                raise ValueError("Local model SHA-256 does not match the expected value.")
            client = LlamaCliRecipeClient(
                args.llama_cli,
                model_path,
                timeout_seconds=args.timeout,
            )
            results = qualify_local_model(
                cases,
                client.generate,
                output_directory=output,
            )
            provider = {
                "kind": "llama.cpp",
                "runtime_revision": args.runtime_revision,
                "model_filename": model_path.name,
                "model_revision": args.model_revision,
                "model_sha256": actual_sha256,
                "model_size_bytes": model_path.stat().st_size,
                "retry_limit": LOCAL_MODEL_ATTEMPTS - 1,
            }
        else:
            from am_configurator.local_animation import OllamaRecipeClient

            client = OllamaRecipeClient(endpoint=args.endpoint)

            def generate(case: PromptCase) -> dict[str, Any]:
                return client.generate(
                    case.prompt,
                    model=args.model,
                    width=case.width,
                    height=case.height,
                    frame_count=case.frame_count,
                    density_default=case.density,
                )

            results = qualify_model(cases, generate, output_directory=output)
            provider = {
                "kind": "ollama-development",
                "model": args.model,
                "endpoint": args.endpoint,
            }
        report = {
            "schema_version": 1,
            "provider": provider,
            "passed": all(result["passed"] for result in results),
            "results": results,
        }
        (output / "qualification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, RecipeError) as exc:
        print(f"Qualification failed: {exc}")
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
