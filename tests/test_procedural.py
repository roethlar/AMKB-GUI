from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from am_configurator.procedural import (
    QualityError,
    RecipeError,
    WorkBudget,
    WorkCancelled,
    WorkDeadlineExceeded,
    assess_quality,
    gif_durations,
    map_frames_to_led_tracks,
    recipe_schema,
    render_recipe,
    validate_quality,
    validate_recipe,
    write_gif,
    write_animation_artifacts,
)
from am_configurator.server import frames_to_led_tracks
from build_tools import qualify_recipe_model as qualification_tool
from build_tools.qualify_recipe_model import (
    load_prompt_corpus,
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


def _worst_case_recipe() -> dict:
    return _recipe(
        "dense",
        layers=[
            _layer(
                "comet",
                phase=index / 6,
                count=12,
                trail=1.0,
                seed=index,
            )
            for index in range(6)
        ],
    )


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

    def test_worst_case_render_obeys_the_shared_monotonic_budget(self) -> None:
        elapsed = 0.0

        def monotonic() -> float:
            nonlocal elapsed
            elapsed += 0.01
            return elapsed

        work = WorkBudget(
            deadline=0.05,
            cancelled=lambda: False,
            monotonic=monotonic,
        )

        with self.assertRaises(WorkDeadlineExceeded):
            render_recipe(
                _worst_case_recipe(),
                width=18,
                height=7,
                frame_count=200,
                work=work,
            )

        self.assertLessEqual(elapsed, 0.06)

    def test_each_local_frame_stage_honors_mid_stage_cancellation(self) -> None:
        frames = render_recipe(_recipe(), width=18, height=7, frame_count=6)
        durations = gif_durations(len(frames), 34)

        def cancelled_work(cancel_after: int):
            cancelled = False

            def progress(completed: int, total: int) -> None:
                nonlocal cancelled
                self.assertLessEqual(completed, total)
                if completed >= cancel_after:
                    cancelled = True

            return (
                WorkBudget(
                    deadline=100.0,
                    cancelled=lambda: cancelled,
                    monotonic=lambda: 0.0,
                ),
                progress,
            )

        stages = {
            "render": lambda work, progress: render_recipe(
                _recipe(),
                width=18,
                height=7,
                frame_count=6,
                work=work,
                progress=progress,
            ),
            "quality": lambda work, progress: validate_quality(
                _recipe(),
                frames,
                width=18,
                height=7,
                frame_count=6,
                work=work,
                progress=progress,
            ),
            "gif encoding": lambda work, progress: write_gif(
                frames,
                io.BytesIO(),
                durations,
                work=work,
                progress=progress,
            ),
            "mapping": lambda work, progress: map_frames_to_led_tracks(
                frames,
                duration_ms=34,
                product_id="AM21",
                targets=("keyframes", "spotlight_frames"),
                work=work,
                progress=progress,
            ),
        }
        for name, stage in stages.items():
            with self.subTest(stage=name):
                cancel_after = len(frames) + 1 if name == "gif encoding" else 1
                work, progress = cancelled_work(cancel_after)
                with self.assertRaises(WorkCancelled):
                    stage(work, progress)


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
    def test_banked_gifs_preserve_exact_raster_preview_and_mapping_colors(self) -> None:
        cases = (
            (40, 5, "CB04", ("frames",)),
            (15, 6, "CB04", ("keyframes",)),
            (18, 7, "AM21", ("keyframes", "spotlight_frames")),
            (16, 5, "ALICE", ("keyframes",)),
        )
        for width, height, product_id, targets in cases:
            with self.subTest(size=(width, height), product_id=product_id):
                frames = []
                for offset in (0, 53):
                    frame = Image.new("RGB", (width, height))
                    frame.putdata(
                        [
                            (
                                (index + offset) % 256,
                                (index * 37 + offset * 3) % 256,
                                (index * 73 + offset * 5) % 256,
                            )
                            for index in range(width * height)
                        ]
                    )
                    frames.append(frame)

                raster_output = io.BytesIO()
                write_gif(frames, raster_output, [40] * len(frames))
                with Image.open(io.BytesIO(raster_output.getvalue())) as raster:
                    decoded_raster = []
                    for frame_index in range(raster.n_frames):
                        raster.seek(frame_index)
                        decoded_raster.append(raster.convert("RGB"))
                self.assertEqual(
                    [frame.tobytes() for frame in frames],
                    [frame.tobytes() for frame in decoded_raster],
                )

                preview_frames = [
                    frame.resize((width * 40, height * 40), Image.Resampling.NEAREST)
                    for frame in frames
                ]
                preview_output = io.BytesIO()
                write_gif(preview_frames, preview_output, [40] * len(frames))
                with Image.open(io.BytesIO(preview_output.getvalue())) as preview:
                    decoded_preview = []
                    for frame_index in range(preview.n_frames):
                        preview.seek(frame_index)
                        decoded_preview.append(preview.convert("RGB"))
                self.assertEqual(
                    [frame.tobytes() for frame in preview_frames],
                    [frame.tobytes() for frame in decoded_preview],
                )

                mapped = map_frames_to_led_tracks(
                    frames,
                    duration_ms=40,
                    product_id=product_id,
                    targets=targets,
                )
                self.assertEqual(
                    mapped,
                    map_frames_to_led_tracks(
                        decoded_raster,
                        duration_ms=40,
                        product_id=product_id,
                        targets=targets,
                    ),
                )
                self.assertEqual(
                    mapped,
                    map_frames_to_led_tracks(
                        decoded_preview,
                        duration_ms=40,
                        product_id=product_id,
                        targets=targets,
                    ),
                )

    def test_gif_banking_rejects_frames_with_more_than_256_colors(self) -> None:
        frame = Image.new("RGB", (257, 1))
        frame.putdata([(index % 256, index // 256, 0) for index in range(257)])
        output = io.BytesIO()

        with self.assertRaisesRegex(RecipeError, "more than 256 colors"):
            write_gif([frame], output, [40])

        self.assertEqual(b"", output.getvalue())

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
                self.assertEqual(0, image.info["loop"])
                encoded_durations = []
                for frame_index in range(image.n_frames):
                    image.seek(frame_index)
                    encoded_durations.append(image.info["duration"])
                self.assertEqual(gif_durations(40, 34), encoded_durations)
            summary = json.loads(paths["summary"].read_text())
            self.assertEqual("sparse", summary["quality"]["density"])
            self.assertEqual(40, summary["quality"]["frame_count"])
            mapped = json.loads(paths["led_json"].read_text())
            self.assertEqual(40, mapped["source_frames"])
            self.assertEqual(40, mapped["tracks"]["keyframes"]["frame_count"])


class QualificationCorpusTests(unittest.TestCase):
    def test_developer_qualification_tool_has_no_direct_model_entry_point(self) -> None:
        option_names = {action.dest for action in qualification_tool._parser()._actions}
        self.assertTrue(
            {
                "llama_cli",
                "model_file",
                "runtime_revision",
                "model_revision",
                "model_sha256",
            }.isdisjoint(option_names)
        )
        self.assertFalse(hasattr(qualification_tool, "LlamaCliRecipeClient"))
        self.assertFalse(hasattr(qualification_tool, "qualify_local_case"))
        source = Path(qualification_tool.__file__).read_text("utf-8")
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("--llama-cli", source)
        self.assertNotIn("--model-file", source)

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

if __name__ == "__main__":
    unittest.main()
