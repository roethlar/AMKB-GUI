from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from PIL import Image, ImageChops, ImageStat

from am_configurator.local_animation import (
    OllamaRecipeClient,
    RecipeError,
    render_recipe,
    validate_recipe,
    write_proof_artifacts,
)


def _recipe() -> dict:
    return {
        "name": "Blue shooting stars",
        "background": "#000000",
        "palette": ["#BDEBFF", "#3A8DFF", "#FFFFFF"],
        "layers": [
            {
                "kind": "comet",
                "color_index": 0,
                "secondary_color_index": 2,
                "speed": 1,
                "phase": 0.12,
                "direction_degrees": 25.0,
                "center_x": 0.1,
                "center_y": 0.32,
                "scale": 0.55,
                "width": 0.11,
                "trail": 0.48,
                "count": 3,
                "intensity": 0.92,
                "seed": 17,
            }
        ],
    }


class RecipeValidationTests(unittest.TestCase):
    def test_recipe_is_exact_and_semantically_bounded(self) -> None:
        validated = validate_recipe(_recipe())
        self.assertEqual("comet", validated["layers"][0]["kind"])

        for mutate in (
            lambda value: value.update(extra=True),
            lambda value: value.update(background="black"),
            lambda value: value["layers"][0].update(speed=0),
            lambda value: value["layers"][0].update(color_index=9),
            lambda value: value.update(layers=[]),
        ):
            candidate = json.loads(json.dumps(_recipe()))
            mutate(candidate)
            with self.subTest(candidate=candidate):
                with self.assertRaises(RecipeError):
                    validate_recipe(candidate)


class ProceduralRendererTests(unittest.TestCase):
    @staticmethod
    def _difference(left: Image.Image, right: Image.Image) -> float:
        return sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3

    def test_render_is_deterministic_exact_and_loop_continuous(self) -> None:
        frames = render_recipe(_recipe(), width=18, height=7, frame_count=200)
        again = render_recipe(_recipe(), width=18, height=7, frame_count=200)
        self.assertEqual(200, len(frames))
        self.assertTrue(all(frame.size == (18, 7) and frame.mode == "RGB" for frame in frames))
        self.assertEqual([frame.tobytes() for frame in frames], [frame.tobytes() for frame in again])

        ordinary = [self._difference(frames[index - 1], frames[index]) for index in range(1, len(frames))]
        seam = self._difference(frames[-1], frames[0])
        self.assertLessEqual(seam, max(ordinary) * 1.25 + 0.01)
        self.assertGreater(max(ordinary), 0.0)

    def test_comets_remain_sparse_and_bright_even_at_maximum_model_width(self) -> None:
        recipe = _recipe()
        recipe["layers"][0]["width"] = 1.0
        frames = render_recipe(recipe, width=18, height=7, frame_count=40)
        lit_ratios = []
        brightness = []
        peaks = []
        for frame in frames:
            pixels = list(frame.get_flattened_data())
            lit_ratios.append(sum(max(pixel) > 32 for pixel in pixels) / len(pixels))
            brightness.append(sum(sum(pixel) / 3 for pixel in pixels) / len(pixels))
            peaks.append(max(max(pixel) for pixel in pixels))
        self.assertLess(max(lit_ratios), 0.55)
        self.assertLess(max(brightness), 35)
        self.assertGreater(max(peaks), 220)

    def test_artifacts_share_the_exact_frames_and_existing_device_mapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_proof_artifacts(
                _recipe(),
                Path(directory),
                width=18,
                height=7,
                frame_count=200,
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
                self.assertEqual(200, image.n_frames)
            with Image.open(paths["preview_gif"]) as image:
                self.assertEqual((720, 280), image.size)
                self.assertEqual(200, image.n_frames)
            led = json.loads(paths["led_json"].read_text())
            self.assertEqual(200, led["source_frames"])
            self.assertEqual(34, led["duration_ms"])
            self.assertEqual(200, led["tracks"]["keyframes"]["frame_count"])
            self.assertEqual(200, led["tracks"]["spotlight_frames"]["frame_count"])


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class OllamaRecipeClientTests(unittest.TestCase):
    def test_request_is_loopback_schema_constrained_and_validated(self) -> None:
        observed = {}

        def opener(request, timeout):
            observed["url"] = request.full_url
            observed["body"] = json.loads(request.data)
            observed["timeout"] = timeout
            return FakeResponse({"message": {"content": json.dumps(_recipe())}})

        result = OllamaRecipeClient(opener=opener).generate(
            "shooting stars on a black background",
            width=18,
            height=7,
            frame_count=200,
        )
        self.assertEqual("Blue shooting stars", result["name"])
        self.assertEqual("http://127.0.0.1:11434/api/chat", observed["url"])
        self.assertFalse(observed["body"]["stream"])
        self.assertEqual("object", observed["body"]["format"]["type"])
        self.assertEqual("ornith:latest", observed["body"]["model"])
        self.assertGreater(observed["timeout"], 0)

    def test_semantic_retry_changes_seed_and_includes_the_validation_error(self) -> None:
        calls = []

        def opener(request, timeout):
            del timeout
            body = json.loads(request.data)
            calls.append(body)
            recipe = _recipe()
            if len(calls) == 1:
                recipe["layers"][0]["phase"] = 2
            return FakeResponse({"message": {"content": json.dumps(recipe)}})

        result = OllamaRecipeClient(opener=opener).generate("blue stars", model="ornith:latest")
        self.assertEqual("Blue shooting stars", result["name"])
        self.assertEqual(2, len(calls))
        self.assertNotEqual(calls[0]["options"]["seed"], calls[1]["options"]["seed"])
        self.assertIn("failed validation", calls[1]["messages"][-1]["content"])
        self.assertIn("phase", calls[1]["messages"][-1]["content"])

    def test_transport_failure_is_typed_and_endpoint_is_fixed_to_loopback(self) -> None:
        with self.assertRaises(ValueError):
            OllamaRecipeClient(endpoint="https://example.com")

        def offline(_request, timeout):
            del timeout
            raise URLError("offline")

        with self.assertRaises(RecipeError):
            OllamaRecipeClient(opener=offline).generate("blue pulse", model="gemma4:12b-mlx")


if __name__ == "__main__":
    unittest.main()
