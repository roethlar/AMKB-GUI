from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from am_configurator.procedural import (
    QualityError,
    RecipeError,
    assess_quality,
    map_frames_to_led_tracks,
    recipe_schema,
    render_recipe,
    validate_quality,
    validate_recipe,
    write_animation_artifacts,
)
from am_configurator.server import frames_to_led_tracks
from build_tools.qualify_recipe_model import (
    LlamaCliRecipeClient,
    PromptCase,
    load_prompt_corpus,
    qualify_local_case,
    qualify_recipe,
)


FIXTURE = Path(__file__).parent / "fixtures" / "procedural_prompt_cases.json"
ORNITH_RECIPE = Path(__file__).parent / "fixtures" / "ornith_dense_aurora_recipe.json"


def _layer(kind: str = "comet", **changes) -> dict:
    value = {
        "kind": kind,
        "color_index": 0,
        "secondary_color_index": 1,
        "speed": 1,
        "phase": 0.12,
        "direction_degrees": 25.0,
        "center_x": 0.1,
        "center_y": 0.32,
        "scale": 0.55,
        "width": 0.8,
        "trail": 0.48,
        "count": 3,
        "intensity": 1.0,
        "seed": 17,
    }
    value.update(changes)
    return value


def _recipe(density: str = "sparse", *, layers: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "name": f"{density.title()} proof",
        "density": density,
        "background": "#000000",
        "palette": ["#FFFFFF", "#3A8DFF", "#00E5C9", "#FF00CC"],
        "layers": layers or [_layer()],
    }


def _balanced_recipe() -> dict:
    return _recipe(
        "balanced",
        layers=[
            _layer(
                "wave",
                speed=2,
                phase=0.2,
                direction_degrees=30,
                scale=0.75,
                width=0.62,
                intensity=1.0,
            )
        ],
    )


def _dense_recipe() -> dict:
    return json.loads(ORNITH_RECIPE.read_text())


class RecipeContractTests(unittest.TestCase):
    def test_schema_and_semantic_validator_require_version_and_density(self) -> None:
        schema = recipe_schema()
        self.assertEqual(
            {"schema_version", "name", "density", "background", "palette", "layers"},
            set(schema["required"]),
        )
        self.assertEqual(["balanced", "dense", "sparse"], schema["properties"]["density"]["enum"])
        self.assertEqual(_recipe(), validate_recipe(_recipe()))

        invalid = (
            {key: value for key, value in _recipe().items() if key != "schema_version"},
            {**_recipe(), "schema_version": 2},
            {**_recipe(), "schema_version": 1.0},
            {**_recipe(), "density": "cinematic"},
            {**_recipe(), "extra": True},
            {**_recipe(), "palette": ["#FFFFFF"], "layers": [_layer(color_index=1)]},
            {**_recipe(), "layers": [_layer(speed=0)]},
            {**_recipe(), "layers": [_layer(kind=[])]},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(RecipeError):
                    validate_recipe(candidate)

    def test_rendering_is_exact_deterministic_and_resource_bounded(self) -> None:
        cases = ((15, 6, 80), (40, 5, 80), (16, 5, 186), (18, 7, 200))
        for width, height, frame_count in cases:
            with self.subTest(size=(width, height), frame_count=frame_count):
                frames = render_recipe(
                    _recipe(), width=width, height=height, frame_count=frame_count
                )
                again = render_recipe(
                    _recipe(), width=width, height=height, frame_count=frame_count
                )
                self.assertEqual(frame_count, len(frames))
                self.assertTrue(
                    all(frame.mode == "RGB" and frame.size == (width, height) for frame in frames)
                )
                self.assertEqual(
                    [frame.tobytes() for frame in frames],
                    [frame.tobytes() for frame in again],
                )

        for dimensions in ((0, 7, 10), (18, 201, 10), (18, 7, 257), (200, 200, 256)):
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(RecipeError):
                    render_recipe(
                        _recipe(),
                        width=dimensions[0],
                        height=dimensions[1],
                        frame_count=dimensions[2],
                    )


class QualityGateTests(unittest.TestCase):
    def test_sparse_balanced_and_dense_recipes_pass_deterministic_metrics(self) -> None:
        for recipe in (_recipe(), _balanced_recipe(), _dense_recipe()):
            with self.subTest(density=recipe["density"]):
                frames = render_recipe(recipe, width=18, height=7, frame_count=80)
                metrics = validate_quality(
                    recipe, frames, width=18, height=7, frame_count=80
                )
                self.assertEqual(recipe["density"], metrics.density)
                self.assertEqual(80, metrics.frame_count)
                self.assertGreater(metrics.maximum_adjacent_difference, 0)
                self.assertLessEqual(
                    metrics.seam_difference,
                    metrics.maximum_adjacent_difference * 1.25 + 0.01,
                )
                self.assertGreater(metrics.peak_brightness, 180)
                self.assertEqual(metrics, assess_quality(recipe, frames))

    def test_quality_gate_reports_static_dim_and_density_failures(self) -> None:
        static = _recipe()
        static["palette"] = ["#000000", "#000000"]
        static["layers"] = [_layer(color_index=0, secondary_color_index=1)]
        frames = render_recipe(static, width=18, height=7, frame_count=20)
        with self.assertRaises(QualityError) as captured:
            validate_quality(static, frames, width=18, height=7, frame_count=20)
        self.assertIn("motion", captured.exception.failures)
        self.assertIn("brightness", captured.exception.failures)

        sparse_frames = render_recipe(_recipe(), width=18, height=7, frame_count=20)
        dense_claim = {**_recipe(), "density": "dense"}
        with self.assertRaises(QualityError) as captured:
            validate_quality(
                dense_claim, sparse_frames, width=18, height=7, frame_count=20
            )
        self.assertIn("density", captured.exception.failures)

        with self.assertRaises(QualityError) as captured:
            validate_quality(_recipe(), sparse_frames[:-1], width=18, height=7, frame_count=20)
        self.assertIn("dimensions", captured.exception.failures)


class ArtifactAndMappingTests(unittest.TestCase):
    def test_mapping_adapter_is_identical_to_existing_shared_mapper(self) -> None:
        frames = render_recipe(_recipe(), width=18, height=7, frame_count=20)
        durations = [34] * len(frames)
        expected = frames_to_led_tracks(
            frames, durations, ["keyframes", "spotlight_frames"], "nearest", "AM21"
        )
        actual = map_frames_to_led_tracks(
            frames,
            duration_ms=34,
            product_id="AM21",
            targets=("keyframes", "spotlight_frames"),
        )
        self.assertEqual(expected, actual)

    def test_artifacts_use_one_exact_quality_checked_frame_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_animation_artifacts(
                _recipe(),
                Path(directory),
                width=18,
                height=7,
                frame_count=40,
                duration_ms=34,
                product_id="80",
                targets=("keyframes", "spotlight_frames"),
            )
            self.assertEqual(
                {"recipe", "raster_gif", "preview_gif", "led_json", "summary"},
                set(paths),
            )
            with Image.open(paths["raster_gif"]) as image:
                self.assertEqual((18, 7), image.size)
                self.assertEqual(40, image.n_frames)
            summary = json.loads(paths["summary"].read_text())
            self.assertEqual("sparse", summary["quality"]["density"])
            self.assertEqual(40, summary["quality"]["frame_count"])
            mapped = json.loads(paths["led_json"].read_text())
            self.assertEqual(40, mapped["source_frames"])
            self.assertEqual(40, mapped["tracks"]["keyframes"]["frame_count"])


class QualificationCorpusTests(unittest.TestCase):
    def test_committed_corpus_covers_devices_densities_effects_and_adversarial_prompts(self) -> None:
        cases = load_prompt_corpus(FIXTURE)
        self.assertEqual(
            {(15, 6, 80), (40, 5, 80), (16, 5, 186), (18, 7, 200)},
            {(case.width, case.height, case.frame_count) for case in cases},
        )
        self.assertEqual({"sparse", "balanced", "dense"}, {case.density for case in cases})
        tags = {tag for case in cases for tag in case.tags}
        self.assertTrue(
            {
                "colors",
                "direction",
                "speed",
                "layering",
                "fire",
                "noise",
                "waves",
                "pulses",
                "sweeps",
                "comets",
                "sparkles",
                "orbits",
                "adversarial",
                "short",
                "long",
                "ambiguous",
                "multilingual",
            }.issubset(tags)
        )

    def test_qualification_result_contains_render_and_quality_evidence(self) -> None:
        case = next(case for case in load_prompt_corpus(FIXTURE) if case.case_id == "relic-sparse-comets")
        result = qualify_recipe(case, _recipe())
        self.assertTrue(result["passed"])
        self.assertEqual("relic-sparse-comets", result["case_id"])
        self.assertEqual(200, result["quality"]["frame_count"])
        self.assertEqual("sparse", result["quality"]["density"])

    def test_saved_ornith_aurora_passes_the_new_contract_without_inference(self) -> None:
        case = next(case for case in load_prompt_corpus(FIXTURE) if case.case_id == "relic-dense-aurora")
        result = qualify_recipe(case, _dense_recipe())
        self.assertTrue(result["passed"], result)
        self.assertGreaterEqual(result["quality"]["minimum_lit_ratio"], 0.70)
        self.assertEqual(
            {"keyframes": 200, "spotlight_frames": 200}, result["mapped_tracks"]
        )


class LocalModelQualificationTests(unittest.TestCase):
    def test_llama_cli_client_uses_pinned_bounded_offline_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "llama-cli"
            model = root / "model.gguf"
            runtime.write_bytes(b"runtime")
            model.write_bytes(b"model")
            calls = []

            def runner(args, **kwargs):
                calls.append((args, kwargs))
                prompt = args[args.index("--prompt") + 1]
                return subprocess.CompletedProcess(
                    args,
                    0,
                    stdout=(
                        "\nLoading model...\n\navailable commands:\n\n"
                        f"> {prompt}\n\n"
                        f"{json.dumps(_recipe())}\n\n\nExiting...\n"
                    ),
                    stderr="",
                )

            case = next(
                case
                for case in load_prompt_corpus(FIXTURE)
                if case.case_id == "relic-sparse-comets"
            )
            client = LlamaCliRecipeClient(runtime, model, runner=runner)
            recipe = client.generate(
                case,
                attempt=1,
                feedback="Animation failed quality checks: density.",
            )

            self.assertEqual(_recipe(), recipe)
            self.assertEqual(1, len(calls))
            args, kwargs = calls[0]
            self.assertEqual(str(runtime.resolve()), args[0])
            self.assertEqual(str(model.resolve()), args[args.index("--model") + 1])
            self.assertIn("--offline", args)
            self.assertEqual("all", args[args.index("--gpu-layers") + 1])
            self.assertEqual("off", args[args.index("--fit") + 1])
            self.assertEqual("on", args[args.index("--flash-attn") + 1])
            self.assertIn("--no-jinja", args)
            self.assertNotIn("--jinja", args)
            self.assertEqual("7320", args[args.index("--seed") + 1])
            self.assertEqual(
                recipe_schema(),
                json.loads(args[args.index("--json-schema") + 1]),
            )
            self.assertIn(
                "Animation failed quality checks: density.",
                args[args.index("--prompt") + 1],
            )
            self.assertTrue(args[args.index("--prompt") + 1].endswith("/no_think"))
            self.assertEqual(
                {
                    "check": False,
                    "capture_output": True,
                    "text": True,
                    "timeout": 180.0,
                },
                kwargs,
            )

    def test_local_qualification_retries_quality_failure_without_weakening_gate(self) -> None:
        source = next(
            case
            for case in load_prompt_corpus(FIXTURE)
            if case.case_id == "relic-sparse-comets"
        )
        case = PromptCase(
            case_id=source.case_id,
            prompt=source.prompt,
            density=source.density,
            product_id=source.product_id,
            targets=source.targets,
            width=source.width,
            height=source.height,
            frame_count=20,
            tags=source.tags,
        )
        calls = []

        def generate(current_case, attempt, feedback):
            calls.append((current_case.case_id, attempt, feedback))
            if attempt == 0:
                invalid = _recipe()
                invalid["palette"] = ["#000000", "#000000"]
                invalid["layers"] = [
                    _layer(color_index=0, secondary_color_index=1)
                ]
                return invalid
            return _recipe()

        result = qualify_local_case(case, generate)

        self.assertTrue(result["passed"], result)
        self.assertEqual(2, result["attempt_count"])
        self.assertEqual([False, True], [attempt["passed"] for attempt in result["attempts"]])
        self.assertEqual((source.case_id, 0, None), calls[0])
        self.assertIn("brightness", calls[1][2])
        self.assertIn("motion", calls[1][2])

    def test_local_qualification_stops_after_two_retries(self) -> None:
        source = next(iter(load_prompt_corpus(FIXTURE)))
        case = PromptCase(
            case_id=source.case_id,
            prompt=source.prompt,
            density=source.density,
            product_id=source.product_id,
            targets=source.targets,
            width=source.width,
            height=source.height,
            frame_count=20,
            tags=source.tags,
        )
        attempts = []

        def generate(_case, attempt, _feedback):
            attempts.append(attempt)
            raise RecipeError("Model output was not valid JSON.")

        result = qualify_local_case(case, generate)

        self.assertFalse(result["passed"])
        self.assertEqual([0, 1, 2], attempts)
        self.assertEqual(3, result["attempt_count"])
        self.assertEqual(3, len(result["attempts"]))


if __name__ == "__main__":
    unittest.main()
