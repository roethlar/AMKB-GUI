from __future__ import annotations

import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import media_composition
from am_configurator.library import (
    GeneratedAssetLibrary,
    LibraryCatalog,
    SavedItemLibrary,
)


def _still_bytes(format_name: str, *, mode: str = "RGBA") -> bytes:
    from PIL import Image

    image = Image.new(mode, (4, 2))
    colors = (
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (0, 255, 255, 255),
        (255, 0, 255, 255),
        (255, 255, 255, 255),
        (0, 0, 0, 255),
    )
    image.putdata(colors)
    if format_name == "BMP":
        image = image.convert("RGB")
    payload = io.BytesIO()
    image.save(payload, format=format_name)
    return payload.getvalue()


def _gif_bytes(*, durations: tuple[int, ...] = (30, 70)) -> bytes:
    from PIL import Image

    frames = []
    for index, color in enumerate(((255, 0, 0), (0, 0, 255))):
        frame = Image.new("RGB", (4, 2), color)
        frame.putpixel((index, 1), (0, 255, 0))
        frames.append(frame)
    payload = io.BytesIO()
    frames[0].save(
        payload,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=list(durations),
        loop=0,
        optimize=False,
    )
    return payload.getvalue()


class ImportedMediaValidationTests(unittest.TestCase):
    def test_gif_png_and_bmp_are_fully_decoded_with_normalized_metadata(self) -> None:
        cases = (
            ("image/gif", _gif_bytes(), 2, 100),
            ("image/png", _still_bytes("PNG"), 1, 0),
            ("image/bmp", _still_bytes("BMP"), 1, 0),
        )
        for mime_type, payload, frame_count, duration_ms in cases:
            with self.subTest(mime_type=mime_type):
                decoded = media_composition.decode_media(payload)
                self.assertEqual(mime_type, decoded.mime_type)
                self.assertEqual((4, 2), (decoded.width, decoded.height))
                self.assertEqual(frame_count, decoded.frame_count)
                self.assertEqual(duration_ms, decoded.duration_ms)
                self.assertEqual(hashlib.sha256(payload).hexdigest(), decoded.sha256)
                self.assertEqual(frame_count, len(decoded.frames))
                self.assertTrue(all(frame.mode == "RGBA" for frame in decoded.frames))
                if mime_type == "image/gif":
                    self.assertEqual((30, 70), decoded.durations_ms)
                else:
                    self.assertEqual((0,), decoded.durations_ms)

    def test_apng_truncation_trailing_bytes_and_signature_spoofing_are_rejected(
        self,
    ) -> None:
        from PIL import Image

        first = Image.new("RGBA", (2, 1), (255, 0, 0, 255))
        second = Image.new("RGBA", (2, 1), (0, 0, 255, 255))
        apng = io.BytesIO()
        first.save(
            apng,
            format="PNG",
            save_all=True,
            append_images=[second],
            duration=[40, 60],
            loop=0,
        )
        with self.assertRaisesRegex(ValueError, "Animated PNG"):
            media_composition.decode_media(apng.getvalue())

        payloads = {
            "gif": _gif_bytes(),
            "png": _still_bytes("PNG"),
            "bmp": _still_bytes("BMP"),
        }
        for label, payload in payloads.items():
            with self.subTest(label=label, failure="truncated"):
                with self.assertRaises(ValueError):
                    media_composition.decode_media(payload[:-1])
            with self.subTest(label=label, failure="trailing"):
                with self.assertRaises(ValueError):
                    media_composition.decode_media(payload + b"trailing")

        with self.assertRaisesRegex(ValueError, "supported GIF, PNG, or BMP"):
            media_composition.decode_media(b"GIF89x" + b"\0" * 64)

    def test_every_media_limit_is_enforced_before_publication(self) -> None:
        png = _still_bytes("PNG")
        gif = _gif_bytes()
        cases = (
            ("MAX_MEDIA_BYTES", len(png) - 1, png, "size limit"),
            ("MAX_MEDIA_DIMENSION", 3, png, "dimensions"),
            ("MAX_MEDIA_FRAMES", 1, gif, "frame limit"),
            ("MAX_MEDIA_DURATION_MS", 99, gif, "duration limit"),
            ("MAX_DECODED_PIXELS", 15, gif, "decoded-pixel limit"),
        )
        for constant, value, payload, message in cases:
            with self.subTest(constant=constant):
                with (
                    patch.object(media_composition, constant, value),
                    self.assertRaisesRegex(ValueError, message),
                ):
                    media_composition.decode_media(payload)

    def test_decoder_warnings_fail_closed(self) -> None:
        from PIL import Image

        original_open = Image.open

        def warning_open(*args, **kwargs):
            import warnings

            warnings.warn("unsafe image", Image.DecompressionBombWarning)
            return original_open(*args, **kwargs)

        with (
            patch.object(Image, "open", side_effect=warning_open),
            self.assertRaisesRegex(ValueError, "warning"),
        ):
            media_composition.decode_media(_still_bytes("PNG"))


class SourceTransformTests(unittest.TestCase):
    @staticmethod
    def _transform(**changes):
        value = {
            "version": 1,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "aspect_locked": True,
            "sampling": "nearest",
            "background": "#000000",
        }
        value.update(changes)
        return value

    def test_transform_schema_is_exact_finite_and_bounded(self) -> None:
        normalized = media_composition.validate_source_transform(self._transform())
        self.assertEqual(self._transform(), normalized.to_dict())

        invalid = (
            {**self._transform(), "extra": True},
            self._transform(version=2),
            self._transform(offset_x=float("nan")),
            self._transform(offset_y=float("inf")),
            self._transform(scale_x=0),
            self._transform(scale_y=-1),
            self._transform(scale_x=1.0, scale_y=2.0),
            self._transform(aspect_locked="yes"),
            self._transform(sampling="bilinear"),
            self._transform(background="black"),
        )
        for transform in invalid:
            with self.subTest(transform=transform):
                with self.assertRaises(ValueError):
                    media_composition.validate_source_transform(transform)

    def test_pan_and_stretch_keep_asymmetric_orientation(self) -> None:
        from PIL import Image

        source = Image.open(io.BytesIO(_still_bytes("PNG"))).convert("RGBA")
        transform = media_composition.validate_source_transform(
            self._transform(
                offset_x=0.25,
                scale_x=0.5,
                scale_y=1.0,
                aspect_locked=False,
            )
        )
        rendered = media_composition.render_source_frame(source, (4, 2), transform)
        self.assertEqual(
            [
                "#000000",
                "#000000",
                "#00FF00",
                "#FFFF00",
                "#000000",
                "#000000",
                "#FF00FF",
                "#000000",
            ],
            [
                f"#{red:02X}{green:02X}{blue:02X}"
                for red, green, blue in rendered.getdata()
            ],
        )

    def test_shared_geometry_vectors_are_canonical_and_maximally_overlapping(
        self,
    ) -> None:
        vectors = json.loads(
            (Path(__file__).parent / "fixtures" / "media_geometry_vectors.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(1, vectors["version"])
        for vector in vectors["vectors"]:
            with self.subTest(vector=vector["name"]):
                before = json.dumps(vector, sort_keys=True)
                source = (vector["source"]["width"], vector["source"]["height"])
                destinations = [
                    (destination["width"], destination["height"])
                    for destination in vector["destinations"]
                ]
                resolved = media_composition.resolve_source_geometry(
                    source,
                    destinations,
                    vector["transform"],
                )
                self.assertEqual(vector["expected"], resolved.to_dict())
                self.assertEqual(before, json.dumps(vector, sort_keys=True))
                for destination, box in zip(
                    vector["destinations"],
                    resolved.boxes,
                    strict=True,
                ):
                    overlap_x = max(
                        0,
                        min(destination["width"], box.left + box.rendered_width)
                        - max(0, box.left),
                    )
                    overlap_y = max(
                        0,
                        min(destination["height"], box.top + box.rendered_height)
                        - max(0, box.top),
                    )
                    self.assertEqual(
                        min(destination["width"], box.rendered_width),
                        overlap_x,
                    )
                    self.assertEqual(
                        min(destination["height"], box.rendered_height),
                        overlap_y,
                    )

        move_zoom = vectors["move_zoom"]
        self.assertEqual(
            move_zoom["expected_transforms"],
            media_composition.interpolate_move_zoom(
                move_zoom["effect"],
                source_size=(
                    move_zoom["source"]["width"],
                    move_zoom["source"]["height"],
                ),
                destination_sizes=[
                    (destination["width"], destination["height"])
                    for destination in move_zoom["destinations"]
                ],
            ),
        )

    def test_same_size_40x5_pan_cannot_render_off_canvas(self) -> None:
        from PIL import Image

        source = Image.new("RGB", (40, 5), (255, 0, 0))
        rendered = media_composition.render_source_frame(
            source,
            (40, 5),
            self._transform(offset_x=8.0, offset_y=-8.0),
        )
        pixels = (
            rendered.get_flattened_data()
            if hasattr(rendered, "get_flattened_data")
            else rendered.getdata()
        )
        self.assertEqual([(255, 0, 0)] * 200, list(pixels))


class LocalAnimationEffectTests(unittest.TestCase):
    def _effect(
        self,
        effect_type: str,
        parameters: dict,
        *,
        frame_count: int = 5,
    ) -> dict:
        return {
            "version": 1,
            "type": effect_type,
            "frame_count": frame_count,
            "duration_ms": 90,
            "parameters": parameters,
        }

    def test_color_effects_match_the_browser_golden_contract(self) -> None:
        source = [["#FF8040", "#204080", "#FFFFFF"]]
        coordinates = [
            {"x": 0.0, "y": 0.5},
            {"x": 0.5, "y": 0.5},
            {"x": 1.0, "y": 0.5},
        ]
        cases = {
            "pulse": (
                {"minimum_brightness": 0.2},
                [
                    ["#FF8040", "#204080", "#FFFFFF"],
                    ["#994D26", "#13264D", "#999999"],
                    ["#331A0D", "#060D1A", "#333333"],
                    ["#994D26", "#13264D", "#999999"],
                    ["#FF8040", "#204080", "#FFFFFF"],
                ],
            ),
            "hue_cycle": (
                {"turns": 1.0},
                [
                    ["#FF8040", "#204080", "#FFFFFF"],
                    ["#99FF40", "#732080", "#FFFFFF"],
                    ["#40FFCC", "#802620", "#FFFFFF"],
                    ["#404CFF", "#668020", "#FFFFFF"],
                    ["#FF40E5", "#20804D", "#FFFFFF"],
                ],
            ),
            "sweep": (
                {
                    "direction": "left_to_right",
                    "width": 0.35,
                    "minimum_brightness": 0.1,
                },
                [
                    ["#1A0D06", "#03060D", "#1A1A1A"],
                    ["#CE6734", "#03060D", "#1A1A1A"],
                    ["#1A0D06", "#204080", "#1A1A1A"],
                    ["#1A0D06", "#03060D", "#CECECE"],
                    ["#1A0D06", "#03060D", "#1A1A1A"],
                ],
            ),
            "shimmer": (
                {"depth": 0.6, "seed": 824},
                [
                    ["#914924", "#1D3A74", "#BDBDBD"],
                    ["#67341A", "#122448", "#6E6E6E"],
                    ["#A55329", "#0D1A34", "#7D7D7D"],
                    ["#F67B3E", "#152A54", "#D6D6D6"],
                    ["#EA753B", "#1F3E7C", "#FEFEFE"],
                ],
            ),
        }
        for effect_type, (parameters, expected) in cases.items():
            with self.subTest(effect=effect_type):
                effect = media_composition.validate_effect_spec(
                    self._effect(effect_type, parameters),
                    frame_limit=16,
                    still_source=False,
                )
                self.assertEqual(
                    expected,
                    media_composition.render_color_effect(
                        source,
                        effect,
                        coordinates=coordinates,
                    ),
                )

    def test_move_zoom_is_still_only_and_interpolates_exact_transforms(self) -> None:
        start = {
            "version": 1,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "aspect_locked": True,
            "sampling": "box",
            "background": "#000000",
        }
        end = {
            **start,
            "offset_x": 0.5,
            "scale_x": 2.0,
            "scale_y": 2.0,
        }
        effect = self._effect(
            "move_zoom",
            {"start_transform": start, "end_transform": end},
            frame_count=3,
        )
        with self.assertRaisesRegex(ValueError, "still"):
            media_composition.validate_effect_spec(
                effect,
                frame_limit=16,
                still_source=False,
            )
        checked = media_composition.validate_effect_spec(
            effect,
            frame_limit=16,
            still_source=True,
        )
        self.assertEqual(
            [
                start,
                {**start, "offset_x": 0.25, "scale_x": 1.5, "scale_y": 1.5},
                end,
            ],
            media_composition.interpolate_move_zoom(checked),
        )


class MediaRenderCoordinatorTests(unittest.TestCase):
    @staticmethod
    def _transform(**changes):
        value = {
            "version": 1,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "aspect_locked": True,
            "sampling": "nearest",
            "background": "#000000",
        }
        value.update(changes)
        return value

    @staticmethod
    def _effect(
        effect_type: str,
        parameters: dict,
        *,
        frame_count: int,
        duration_ms: int = 90,
    ) -> dict:
        return {
            "version": 1,
            "type": effect_type,
            "frame_count": frame_count,
            "duration_ms": duration_ms,
            "parameters": parameters,
        }

    @staticmethod
    def _bank_source(
        saved: SavedItemLibrary,
        *,
        name: str,
        payload: bytes,
    ) -> str:
        decoded = media_composition.decode_media(payload)
        manifest, _created = saved.bank_media_source(
            name=name,
            payload=payload,
            metadata={
                "mime_type": decoded.mime_type,
                "width": decoded.width,
                "height": decoded.height,
                "frame_count": decoded.frame_count,
                "duration_ms": decoded.duration_ms,
            },
        )
        return f"item:{manifest['item_id']}"

    def test_selected_frames_equal_full_sequences_for_formats_effects_and_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            jobs = GeneratedAssetLibrary(root, minimum_free_bytes=1)
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(jobs, saved)
            renderer = media_composition.MediaRenderCoordinator(catalog)
            start = self._transform()
            cases = (
                (
                    "motion.gif",
                    _gif_bytes(),
                    [
                        self._effect(
                            "hue_cycle",
                            {"turns": 1.25},
                            frame_count=4,
                            duration_ms=76,
                        )
                    ],
                ),
                (
                    "still.png",
                    _still_bytes("PNG"),
                    [
                        self._effect(
                            "move_zoom",
                            {
                                "start_transform": start,
                                "end_transform": self._transform(
                                    offset_x=0.4,
                                    offset_y=-0.25,
                                    scale_x=1.8,
                                    scale_y=1.8,
                                ),
                            },
                            frame_count=3,
                        ),
                        self._effect(
                            "pulse",
                            {"minimum_brightness": 0.2},
                            frame_count=5,
                        ),
                    ],
                ),
                (
                    "still.bmp",
                    _still_bytes("BMP"),
                    [
                        self._effect(
                            "sweep",
                            {
                                "direction": "diagonal",
                                "width": 0.4,
                                "minimum_brightness": 0.15,
                            },
                            frame_count=4,
                        ),
                        self._effect(
                            "shimmer",
                            {"depth": 0.55, "seed": 824},
                            frame_count=3,
                            duration_ms=100,
                        ),
                    ],
                ),
            )
            destinations = (
                ("CB04", ["keyframes", "frames"]),
                ("ALICE", ["keyframes"]),
                ("AM21", ["keyframes", "spotlight_frames"]),
                ("NEON80", ["axial", "head"]),
            )
            for name, payload, effects in cases:
                catalog_id = self._bank_source(saved, name=name, payload=payload)
                session = renderer.prepare_preview_session(catalog_id)
                session_id = session["preview_session_id"]
                for product_id, targets in destinations:
                    with self.subTest(name=name, product_id=product_id):
                        transform = self._transform(
                            offset_x=0.15,
                            offset_y=-0.1,
                            scale_x=1.25,
                            scale_y=0.75,
                            aspect_locked=False,
                        )
                        full = renderer.render(
                            catalog_id,
                            preview_session_id=session_id,
                            product_id=product_id,
                            targets=targets,
                            transform=transform,
                            effects=effects,
                            epoch=1,
                        )
                        self.assertEqual(
                            len(full["preview_timeline"]),
                            next(iter(full["mapped_result"]["tracks"].values()))[
                                "frame_count"
                            ],
                        )
                        for frame_index, timeline_entry in enumerate(
                            full["preview_timeline"]
                        ):
                            selected = renderer.render_frame(
                                catalog_id,
                                preview_session_id=session_id,
                                product_id=product_id,
                                targets=targets,
                                transform=transform,
                                effects=effects,
                                frame_index=frame_index,
                                epoch=frame_index + 2,
                            )
                            self.assertEqual(
                                timeline_entry,
                                selected["timeline_entry"],
                            )
                            self.assertEqual(
                                full["mapped_result"]["model"],
                                selected["mapped_frame"]["model"],
                            )
                            for target in targets:
                                self.assertEqual(
                                    full["mapped_result"]["tracks"][target][
                                        "frames"
                                    ][frame_index],
                                    selected["mapped_frame"]["tracks"][target][
                                        "colors"
                                    ],
                                )
                                for key in ("width", "height", "pixels", "mapped_pixels"):
                                    self.assertEqual(
                                        full["mapped_result"]["tracks"][target][key],
                                        selected["mapped_frame"]["tracks"][target][key],
                                    )
                        self.assertNotIn(str(root), json.dumps(full))

    def test_source_projection_is_complete_static_source_and_uses_byte_lru(
        self,
    ) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(
                GeneratedAssetLibrary(root, minimum_free_bytes=1),
                saved,
            )
            catalog_id = self._bank_source(
                saved,
                name="motion.gif",
                payload=_gif_bytes(),
            )
            renderer = media_composition.MediaRenderCoordinator(catalog)
            session = renderer.prepare_preview_session(catalog_id)
            session_id = session["preview_session_id"]
            expected = media_composition.decode_media(_gif_bytes()).frames[0]

            original_encoder = media_composition._encode_source_preview
            with patch(
                "am_configurator.media_composition.MAX_SOURCE_PREVIEW_CACHE_ENTRIES",
                1,
            ), patch(
                "am_configurator.media_composition._encode_source_preview",
                wraps=original_encoder,
            ) as encode:
                first = renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=session_id,
                    source_frame_index=0,
                )
                again = renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=session_id,
                    source_frame_index=0,
                )
                renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=session_id,
                    source_frame_index=1,
                )
                renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=session_id,
                    source_frame_index=0,
                )
            self.assertEqual(first, again)
            self.assertEqual(3, encode.call_count)
            with Image.open(io.BytesIO(first)) as projected:
                projected.load()
                self.assertEqual(expected.size, projected.size)
                expected_pixels = (
                    expected.get_flattened_data()
                    if hasattr(expected, "get_flattened_data")
                    else expected.getdata()
                )
                projected_rgba = projected.convert("RGBA")
                projected_pixels = (
                    projected_rgba.get_flattened_data()
                    if hasattr(projected_rgba, "get_flattened_data")
                    else projected_rgba.getdata()
                )
                self.assertEqual(list(expected_pixels), list(projected_pixels))
                self.assertNotEqual((40, 5), projected.size)
            self.assertEqual(
                {
                    "mime_type": "image/png",
                    "width": 4,
                    "height": 2,
                    "frame_count": 2,
                    "display_only": True,
                },
                session["source_preview"],
            )

            bounded_renderer = media_composition.MediaRenderCoordinator(catalog)
            bounded_session = bounded_renderer.prepare_preview_session(catalog_id)
            bounded_session_id = bounded_session["preview_session_id"]
            with patch(
                "am_configurator.media_composition.MAX_SOURCE_PREVIEW_PIXELS",
                4,
            ), patch(
                "am_configurator.media_composition.MAX_SOURCE_PREVIEW_CACHE_BYTES",
                1,
            ), patch(
                "am_configurator.media_composition._encode_source_preview",
                wraps=original_encoder,
            ) as bounded_encode:
                bounded_first = bounded_renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=bounded_session_id,
                    source_frame_index=0,
                )
                bounded_renderer.source_frame_png(
                    catalog_id,
                    preview_session_id=bounded_session_id,
                    source_frame_index=0,
                )
            self.assertEqual(2, bounded_encode.call_count)
            with Image.open(io.BytesIO(bounded_first)) as bounded_projection:
                self.assertEqual((2, 1), bounded_projection.size)
                self.assertLessEqual(
                    bounded_projection.width * bounded_projection.height,
                    4,
                )

    def test_sessions_enforce_lru_expiry_pixel_hash_catalog_and_close_bounds(
        self,
    ) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(
                GeneratedAssetLibrary(root, minimum_free_bytes=1),
                saved,
            )
            ids = []
            for index in range(3):
                image = Image.new("RGBA", (4, 2), (index * 40, 20, 80, 255))
                output = io.BytesIO()
                image.save(output, format="PNG")
                ids.append(
                    self._bank_source(
                        saved,
                        name=f"source-{index}.png",
                        payload=output.getvalue(),
                    )
                )
            now = [0.0]
            renderer = media_composition.MediaRenderCoordinator(
                catalog,
                clock=lambda: now[0],
            )
            sessions = []
            for index in range(2):
                now[0] = float(index)
                sessions.append(renderer.prepare_preview_session(ids[index]))
            now[0] = 2.0
            renderer.source_frame_png(
                ids[0],
                preview_session_id=sessions[0]["preview_session_id"],
                source_frame_index=0,
            )
            now[0] = 3.0
            third = renderer.prepare_preview_session(ids[2])
            with self.assertRaisesRegex(ValueError, "no longer available"):
                renderer.source_frame_png(
                    ids[1],
                    preview_session_id=sessions[1]["preview_session_id"],
                    source_frame_index=0,
                )
            renderer.source_frame_png(
                ids[0],
                preview_session_id=sessions[0]["preview_session_id"],
                source_frame_index=0,
            )
            with self.assertRaisesRegex(ValueError, "no longer available"):
                renderer.source_frame_png(
                    ids[1],
                    preview_session_id=sessions[0]["preview_session_id"],
                    source_frame_index=0,
                )

            now[0] = media_composition.PREVIEW_SESSION_TTL_SECONDS + 4.0
            with self.assertRaisesRegex(ValueError, "no longer available"):
                renderer.source_frame_png(
                    ids[2],
                    preview_session_id=third["preview_session_id"],
                    source_frame_index=0,
                )

            now[0] += 1
            fresh = renderer.prepare_preview_session(ids[0])
            real_get = catalog.get

            def mismatched_hash(catalog_id):
                detail = real_get(catalog_id)
                detail["item"]["source"]["sha256"] = "0" * 64
                return detail

            with patch.object(catalog, "get", side_effect=mismatched_hash):
                with self.assertRaisesRegex(ValueError, "metadata"):
                    renderer.source_frame_png(
                        ids[0],
                        preview_session_id=fresh["preview_session_id"],
                        source_frame_index=0,
                    )
            with self.assertRaisesRegex(ValueError, "no longer available"):
                renderer.source_frame_png(
                    ids[0],
                    preview_session_id=fresh["preview_session_id"],
                    source_frame_index=0,
                )

            replacement = renderer.prepare_preview_session(ids[0])
            renderer.close()
            with self.assertRaisesRegex(ValueError, "no longer available"):
                renderer.source_frame_png(
                    ids[0],
                    preview_session_id=replacement["preview_session_id"],
                    source_frame_index=0,
                )

            bounded = media_composition.MediaRenderCoordinator(catalog)
            with patch(
                "am_configurator.media_composition.MAX_PREVIEW_DECODED_PIXELS",
                8,
            ):
                first = bounded.prepare_preview_session(ids[0])
                bounded.prepare_preview_session(ids[1])
                with self.assertRaisesRegex(ValueError, "no longer available"):
                    bounded.source_frame_png(
                        ids[0],
                        preview_session_id=first["preview_session_id"],
                        source_frame_index=0,
                    )

    def test_sessionless_renders_do_not_consume_preview_session_lru(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(
                GeneratedAssetLibrary(root, minimum_free_bytes=1),
                saved,
            )
            ids = [
                self._bank_source(
                    saved,
                    name=f"source-{index}.png",
                    payload=_still_bytes("PNG"),
                )
                for index in range(2)
            ]
            renderer = media_composition.MediaRenderCoordinator(catalog)
            retained_session_id = renderer.prepare_preview_session(ids[0])[
                "preview_session_id"
            ]

            results = [
                renderer.render(
                    ids[1],
                    product_id="CB04",
                    targets=["frames"],
                    transform=self._transform(),
                    epoch=epoch,
                )
                for epoch in (1, 2)
            ]

            source_png = renderer.source_frame_png(
                ids[0],
                preview_session_id=retained_session_id,
                source_frame_index=0,
            )
            self.assertTrue(source_png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(
                [None, None],
                [item["preview_session_id"] for item in results],
            )

    def test_sessionless_render_does_not_depend_on_preview_lru_residency(
        self,
    ) -> None:
        from am_configurator import device_mapping

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(
                GeneratedAssetLibrary(root, minimum_free_bytes=1),
                saved,
            )
            catalog_id = self._bank_source(
                saved,
                name="source.png",
                payload=_still_bytes("PNG"),
            )
            renderer = media_composition.MediaRenderCoordinator(catalog)
            real_compose = device_mapping.compose_media_frames_to_led_tracks
            entered = threading.Event()
            release = threading.Event()
            calls_lock = threading.Lock()
            calls = 0
            failures: list[BaseException] = []

            def delayed_compose(*args, **kwargs):
                nonlocal calls
                with calls_lock:
                    calls += 1
                    should_wait = calls == 1
                if should_wait:
                    entered.set()
                    self.assertTrue(release.wait(5))
                return real_compose(*args, **kwargs)

            def first_render() -> None:
                try:
                    renderer.render(
                        catalog_id,
                        product_id="CB04",
                        targets=["frames"],
                        transform=self._transform(),
                        epoch=1,
                    )
                except BaseException as exc:  # noqa: BLE001 - preserve worker failure
                    failures.append(exc)

            with patch.object(
                device_mapping,
                "compose_media_frames_to_led_tracks",
                side_effect=delayed_compose,
            ):
                worker = threading.Thread(target=first_render)
                worker.start()
                self.assertTrue(entered.wait(5))
                try:
                    renderer.render(
                        catalog_id,
                        product_id="CB04",
                        targets=["keyframes"],
                        transform=self._transform(),
                        epoch=1,
                    )
                    renderer.render(
                        catalog_id,
                        product_id="CB04",
                        targets=["frames", "keyframes"],
                        transform=self._transform(),
                        epoch=1,
                    )
                finally:
                    release.set()
                    worker.join(5)

            self.assertFalse(worker.is_alive())
            self.assertEqual([], failures)

    def test_newer_epoch_supersedes_inflight_work_and_work_is_never_catalogued(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            jobs = GeneratedAssetLibrary(root, minimum_free_bytes=1)
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            manifest, _created = saved.bank_media_source(
                name="source.png",
                payload=_still_bytes("PNG"),
                metadata={
                    "mime_type": "image/png",
                    "width": 4,
                    "height": 2,
                    "frame_count": 1,
                    "duration_ms": 0,
                },
            )
            catalog = LibraryCatalog(jobs, saved)
            renderer = media_composition.MediaRenderCoordinator(catalog)
            catalog_id = f"item:{manifest['item_id']}"
            entered = threading.Event()
            release = threading.Event()
            calls = 0
            calls_lock = threading.Lock()

            def compose(
                images,
                durations_ms,
                targets,
                transform,
                product_id,
                *,
                work_check=None,
                progress=None,
            ):
                nonlocal calls
                with calls_lock:
                    calls += 1
                    call = calls
                if call == 1:
                    entered.set()
                    self.assertTrue(release.wait(5))
                    work_check()
                return {
                    "tracks": {
                        "frames": {
                            "frames": [["#000000"] * 200],
                            "frame_count": 1,
                            "width": 40,
                            "height": 5,
                            "pixels": 200,
                            "mapped_pixels": 200,
                        }
                    },
                    "source_frames": 1,
                    "decoded_frames": 1,
                    "duration_ms": 90,
                    "source_duration_ms": 90,
                    "timing_resampled": False,
                    "model": "CB",
                }

            failures: list[BaseException] = []

            def first_render() -> None:
                try:
                    renderer.render(
                        catalog_id,
                        product_id="CB04",
                        targets=["frames"],
                        transform=self._transform(),
                        epoch=1,
                    )
                except BaseException as exc:  # noqa: BLE001 - preserve worker failure
                    failures.append(exc)

            with patch(
                "am_configurator.device_mapping.compose_media_frames_to_led_tracks",
                side_effect=compose,
            ):
                worker = threading.Thread(target=first_render)
                worker.start()
                self.assertTrue(entered.wait(5))
                newest = renderer.render(
                    catalog_id,
                    product_id="CB04",
                    targets=["frames"],
                    transform=self._transform(),
                    epoch=2,
                )
                release.set()
                worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(2, newest["epoch"])
            self.assertEqual(1, len(failures))
            self.assertIsInstance(
                failures[0],
                media_composition.MediaRenderSuperseded,
            )
            for stale_epoch in (1, 2):
                with self.subTest(epoch=stale_epoch):
                    with self.assertRaises(media_composition.MediaRenderSuperseded):
                        renderer.render(
                            catalog_id,
                            product_id="CB04",
                            targets=["frames"],
                            transform=self._transform(),
                            epoch=stale_epoch,
                        )

            item_dir = root / "items" / manifest["item_id"]
            self.assertEqual([], list((item_dir / ".work").iterdir()))
            self.assertEqual(1, len(saved.load_manifest(manifest["item_id"])["assets"]))
            self.assertEqual(
                1,
                len(
                    [
                        item
                        for item in catalog.scan()["items"]
                        if item["kind"] == "media_source"
                    ]
                ),
            )

    def test_session_epochs_are_destination_scoped_and_selected_work_cannot_publish_stale(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            saved = SavedItemLibrary(root, minimum_free_bytes=1)
            catalog = LibraryCatalog(
                GeneratedAssetLibrary(root, minimum_free_bytes=1),
                saved,
            )
            catalog_id = self._bank_source(
                saved,
                name="source.png",
                payload=_still_bytes("PNG"),
            )
            renderer = media_composition.MediaRenderCoordinator(catalog)
            session_id = renderer.prepare_preview_session(catalog_id)[
                "preview_session_id"
            ]
            transform = self._transform()

            first_destination = renderer.render(
                catalog_id,
                preview_session_id=session_id,
                product_id="CB04",
                targets=["frames"],
                transform=transform,
                epoch=1,
            )
            other_destination = renderer.render(
                catalog_id,
                preview_session_id=session_id,
                product_id="CB04",
                targets=["keyframes"],
                transform=transform,
                epoch=1,
            )
            self.assertEqual(1, first_destination["epoch"])
            self.assertEqual(1, other_destination["epoch"])
            with self.assertRaises(media_composition.MediaRenderSuperseded):
                renderer.render(
                    catalog_id,
                    preview_session_id=session_id,
                    product_id="CB04",
                    targets=["frames"],
                    transform=transform,
                    epoch=1,
                )

            from am_configurator import device_mapping

            real_mapper = device_mapping.map_media_frame_to_led_tracks
            entered = threading.Event()
            release = threading.Event()
            failures: list[BaseException] = []

            def delayed_mapper(*args, **kwargs):
                entered.set()
                self.assertTrue(release.wait(5))
                return real_mapper(*args, **kwargs)

            def selected_render() -> None:
                try:
                    renderer.render_frame(
                        catalog_id,
                        preview_session_id=session_id,
                        product_id="CB04",
                        targets=["frames"],
                        transform=transform,
                        effects=[],
                        frame_index=0,
                        epoch=2,
                    )
                except BaseException as exc:  # noqa: BLE001 - preserve worker failure
                    failures.append(exc)

            with patch.object(
                device_mapping,
                "map_media_frame_to_led_tracks",
                side_effect=delayed_mapper,
            ):
                worker = threading.Thread(target=selected_render)
                worker.start()
                self.assertTrue(entered.wait(5))
                newest = renderer.render(
                    catalog_id,
                    preview_session_id=session_id,
                    product_id="CB04",
                    targets=["frames"],
                    transform=transform,
                    epoch=3,
                )
                release.set()
                worker.join(5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(3, newest["epoch"])
            self.assertEqual(1, len(failures))
            self.assertIsInstance(
                failures[0],
                media_composition.MediaRenderSuperseded,
            )


if __name__ == "__main__":
    unittest.main()
