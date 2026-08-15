from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from am_configurator import store
from am_configurator.ai_capability import AICapabilityError
from am_configurator.credentials import MemoryCredentialStore
from am_configurator.generation_admission import OperationGate
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.ollama_client import DEFAULT_OLLAMA_BASE_URL
from am_configurator.procedural_generation import ProceduralGenerationCoordinator
from am_configurator.recipe_provider import RecipeResult
from am_configurator.server import create_server


_RECIPE = Path(__file__).parent / "fixtures" / "ornith_dense_aurora_recipe.json"

# A backstop against a hung server, not an assertion about latency. Every route
# here answers in under 10 ms except POST /api/lighting/effects, which renders
# 200 frames, encodes two GIFs, and maps them to device tracks before replying;
# that measures about 4.4 s on the development machine. The former 15 s left
# only 3.4x headroom, and a macOS CI runner observed at 2.3x slower than local
# timed out. Everything else in the suite runs at 460x headroom or better.
_REQUEST_TIMEOUT_SECONDS = 60


def _ready_status() -> dict:
    return {
        "schema_version": 1,
        "enabled": True,
        "backend": "ollama",
        "ready": True,
        "reason": "ready",
        "ollama": {
            "base_url": DEFAULT_OLLAMA_BASE_URL,
            "service_available": True,
            "model_selected": True,
            "model_id": "ornith:latest",
            "model_digest": "a" * 64,
            "model_location": "ollama_server",
            "model_verified": True,
            "setup_tested": True,
            "disclosure_required": False,
            "disclosure_current": True,
            "disclosure_version": store.OLLAMA_DISCLOSURE_VERSION,
            "provider": "ollama",
        },
        "api": {
            "provider": "xai",
            "model_id": "grok-4.5",
            "credential_set": False,
            "disclosure_current": False,
            "setup_tested": False,
        },
    }


def _valid_config(product_id: str) -> dict:
    layer = {"layer": ["#00000000"] * 200}
    return {
        "product_info": {
            "product_info_addr": "product_info_addr",
            "product_id": product_id,
        },
        "page_num": 0,
        "page_data": [],
        "tab_key": [],
        "tab_key_num": 0,
        "macro_key": [],
        "MACRO_key": [],
        "MACRO_key_num": 0,
        "exchange_key": [],
        "exchange_num": 0,
        "swap_key": [],
        "swap_key_num": 0,
        "Fn_key": [],
        "Fn_key_num": 0,
        "key_layer": {"valid": 1, "layer_num": 2, "layer_data": [layer, copy.deepcopy(layer)]},
    }


class _Provider:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, request, deadline, cancelled):
        self.calls.append(request)
        return RecipeResult(
            recipe=json.loads(_RECIPE.read_text("utf-8")),
            backend="ollama",
            provider="ollama",
            model_id="ornith:latest",
            usage=None,
        )


class _Capability:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.test_calls: list[str] = []
        self.validation_calls: list[str] = []
        self.closed = False
        self.status_value = _ready_status()
        self.status_probes: list[bool] = []

    def status(self, *, probe=True):
        self.status_probes.append(probe)
        return copy.deepcopy(self.status_value)

    def backend_setup_valid(self, backend):
        self.validation_calls.append(backend)
        current = self.status()
        if backend == "ollama":
            ollama = current["ollama"]
            return all(
                ollama[field] is True
                for field in (
                    "service_available",
                    "model_selected",
                    "model_verified",
                    "setup_tested",
                )
            )
        if backend == "api":
            api = current["api"]
            return all(
                api[field] is True
                for field in (
                    "credential_set",
                    "disclosure_current",
                    "setup_tested",
                )
            )
        return False

    def require_ready(self):
        return self.status()

    def provider_for_generation(self):
        return self.provider

    def test_backend(self, backend, *, deadline, cancelled):
        self.test_calls.append(backend)
        return self.status()

    def discover_ollama_models(self):
        return {
            "available": True,
            "models": [
                {
                    "model_id": "ornith:latest",
                    "digest": "a" * 64,
                    "size_bytes": 5_629_110_568,
                    "location": "ollama_server",
                    "parameter_size": "9.0B",
                    "quantization": "Q4_K_M",
                    "label": "ornith:latest — On this Ollama server",
                }
            ],
        }

    def close(self):
        self.closed = True


class OptionalAIRouteTests(unittest.TestCase):
    _DEFAULT = object()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="am-ai-routes-")
        self.saved_data_dir = os.environ.get("AM_CONFIGURATOR_DATA_DIR")
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self.temporary.name
        root = Path(self.temporary.name) / "library"
        self.credentials = MemoryCredentialStore()
        store.update_library_root(
            {"current_root": str(root)}, credential_store=self.credentials
        )
        self.library = GeneratedAssetLibrary(root, minimum_free_bytes=1)
        self.provider = _Provider()
        self.capability = _Capability(self.provider)
        self.gate = OperationGate()
        self.procedural = ProceduralGenerationCoordinator(
            self.library,
            self.capability,
            operation_gate=self.gate,
            launcher=lambda target: target(),
            operation_timeout_seconds=180,
        )
        config_path = Path(self.temporary.name) / "config.json"
        config_path.write_text(
            json.dumps(_valid_config("AM21")),
            encoding="utf-8",
        )
        self.server, url = create_server(
            [str(config_path)],
            lighting_library=self.library,
            operation_gate=self.gate,
            ai_capability=self.capability,
            credential_store=self.credentials,
            procedural_coordinator=self.procedural,
        )
        self.token = parse_qs(urlparse(url).query)["token"][0]
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, initial = self._request("GET", "/api/config")
        self.assertEqual(200, status)
        self.document_revision = initial["document_revision"]
        self.assertIsInstance(self.document_revision, str)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.saved_data_dir is None:
            os.environ.pop("AM_CONFIGURATOR_DATA_DIR", None)
        else:
            os.environ["AM_CONFIGURATOR_DATA_DIR"] = self.saved_data_dir
        self.temporary.cleanup()

    def _request(self, method, path, body=None, token=_DEFAULT):
        headers = {}
        selected = self.token if token is self._DEFAULT else token
        if selected is not None:
            headers["X-AM-Token"] = selected
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.base + path,
            data=payload,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            return error.code, json.loads(raw) if raw else None

    def _sync_document(self, product_id: str) -> str:
        status, response = self._request(
            "POST", "/api/document/sync", {"config": _valid_config(product_id)}
        )
        self.assertEqual(200, status)
        self.document_revision = response["revision"]
        return self.document_revision

    def test_status_and_all_new_mutations_require_authentication(self) -> None:
        cases = (
            ("POST", "/api/document/sync", {"config": _valid_config("AM21")}),
            ("POST", "/api/lighting/effects", {"prompt": "aurora", "backend": "ollama"}),
        )
        for method, path, body in cases:
            with self.subTest(path=path):
                status, _response = self._request(method, path, body, token=None)
                self.assertEqual(403, status)

    def test_document_sync_is_strict_and_returns_an_opaque_revision(self) -> None:
        config = _valid_config("AM21")
        status, response = self._request(
            "POST", "/api/document/sync", {"config": config}
        )

        self.assertEqual(200, status)
        self.assertEqual(
            {"revision", "layout_evidence", "layout_warning"}, set(response)
        )
        self.assertIsNone(response["layout_evidence"])
        self.assertIsNone(response["layout_warning"])
        self.assertIsInstance(response["revision"], str)
        self.assertGreaterEqual(len(response["revision"]), 24)
        self.assertNotIn("AM21", response["revision"])
        config["product_info"]["product_id"] = "CB04"
        status, current = self._request("GET", "/api/config")
        self.assertEqual(200, status)
        self.assertEqual("AM21", current["config"]["product_info"]["product_id"])
        self.assertEqual(response["revision"], current["document_revision"])

        status, _response = self._request(
            "POST",
            "/api/document/sync",
            {"config": _valid_config("AM21"), "product_id": "CB04"},
        )
        self.assertEqual(400, status)
        invalid = _valid_config("AM21")
        invalid["key_layer"]["layer_data"][0]["layer"].pop()
        status, _response = self._request(
            "POST", "/api/document/sync", {"config": invalid}
        )
        self.assertEqual(400, status)

    def test_effect_route_owns_target_model_frames_and_banks_offline_result(self) -> None:
        status, started = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "Dense violet aurora",
                "backend": "ollama",
                "target": "keyframes",
                "document_revision": self.document_revision,
            },
        )
        self.assertEqual(202, status)
        self.assertEqual({"job_id", "target"}, set(started))
        self.assertEqual(1, len(self.provider.calls))
        request = self.provider.calls[0]
        self.assertEqual((18, 7, 200), (request.width, request.height, request.frame_count))

        status, manifest = self._request(
            "GET", f"/api/lighting/jobs/{started['job_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual("ready", manifest["status"])
        self.assertNotIn("loop_mode", manifest)
        self.assertEqual(
            {
                "family": "80",
                "product_id": "AM21",
                "raster": {"width": 18, "height": 7},
                "targets": ["keyframes"],
                "frame_cap": 200,
            },
            manifest["target"],
        )
        self.assertEqual(
            {"recipe", "raster_animation", "preview_animation", "mapped_result"},
            {asset["kind"] for asset in manifest["assets"]},
        )

        status, _response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "attempted override",
                "backend": "ollama",
                "target": "keyframes",
                "document_revision": self.document_revision,
                "product_id": "CB04",
                "model_path": "/tmp/model.gguf",
                "source_transform": {"version": 1},
            },
        )
        self.assertEqual(400, status)
        self.assertEqual(1, len(self.provider.calls))
        status, response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "stale backend",
                "backend": "api",
                "target": "keyframes",
                "document_revision": self.document_revision,
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("backend_mismatch", response["code"])
        self.assertEqual(1, len(self.provider.calls))

        for body in (
            {
                "prompt": "missing exact target",
                "backend": "ollama",
                "document_revision": self.document_revision,
            },
            {
                "prompt": "unsupported exact target",
                "backend": "ollama",
                "target": "frames",
                "document_revision": self.document_revision,
            },
        ):
            with self.subTest(body=body):
                status, _response = self._request(
                    "POST",
                    "/api/lighting/effects",
                    body,
                )
                self.assertEqual(400, status)
        for field, value in (
            ("source_transform", {"version": 1}),
            ("source_item_id", "00000000-0000-4000-8000-000000000000"),
            ("media", "image/gif"),
            ("resample", "lanczos"),
        ):
            with self.subTest(media_field=field):
                status, _response = self._request(
                    "POST",
                    "/api/lighting/effects",
                    {
                        "prompt": "reject media composition",
                        "backend": "ollama",
                        "target": "keyframes",
                        "document_revision": self.document_revision,
                        field: value,
                    },
                )
                self.assertEqual(400, status)
        self.assertEqual(1, len(self.provider.calls))

    def test_effect_route_validates_each_selected_device_target_server_side(self) -> None:
        calls: list[dict] = []

        def start_effect(**kwargs):
            calls.append(kwargs)
            return {
                "job_id": "00000000-0000-4000-8000-000000000000",
                "target": copy.deepcopy(kwargs["target"]),
            }

        self.server.state._procedural_coordinator = SimpleNamespace(
            active_job_id=None,
            start_effect=start_effect,
        )
        self.server.state._procedural_library_identity = id(self.library)
        cases = (
            (
                "CB04",
                "frames",
                {
                    "family": "CB",
                    "product_id": "CB04",
                    "raster": {"width": 40, "height": 5},
                    "targets": ["frames"],
                    "frame_cap": 80,
                },
            ),
            (
                "ALICE",
                "keyframes",
                {
                    "family": "ALICE",
                    "product_id": "ALICE",
                    "raster": {"width": 16, "height": 5},
                    "targets": ["keyframes"],
                    "frame_cap": 186,
                },
            ),
            (
                "AM21",
                "spotlight_frames",
                {
                    "family": "80",
                    "product_id": "AM21",
                    "raster": {"width": 18, "height": 7},
                    "targets": ["spotlight_frames"],
                    "frame_cap": 200,
                },
            ),
        )
        for product_id, selected_target, expected in cases:
            with self.subTest(product_id=product_id, target=selected_target):
                stale_revision = self.document_revision
                revision = self._sync_document(product_id)
                before = len(calls)
                status, response = self._request(
                    "POST",
                    "/api/lighting/effects",
                    {
                        "prompt": "stale target",
                        "backend": "ollama",
                        "target": selected_target,
                        "document_revision": stale_revision,
                    },
                )
                self.assertEqual(409, status)
                self.assertEqual("document_stale", response["code"])
                self.assertEqual(before, len(calls))
                status, response = self._request(
                    "POST",
                    "/api/lighting/effects",
                    {
                        "prompt": "canonical target",
                        "backend": "ollama",
                        "target": selected_target,
                        "document_revision": revision,
                    },
                )
                self.assertEqual(202, status)
                self.assertEqual(expected, calls[-1]["target"])
                self.assertEqual(expected, response["target"])

    def test_effect_route_rejects_the_obsolete_procedural_loop_field(self) -> None:
        calls: list[dict] = []

        def start_effect(**kwargs):
            calls.append(kwargs)
            raise AssertionError("obsolete request reached the coordinator")

        self.server.state._procedural_coordinator = SimpleNamespace(
            active_job_id=None,
            start_effect=start_effect,
        )
        self.server.state._procedural_library_identity = id(self.library)
        status, _response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "ignored loop control",
                "backend": "ollama",
                "target": "keyframes",
                "loop_mode": "ping_pong",
                "document_revision": self.document_revision,
            },
        )

        self.assertEqual(400, status)
        self.assertEqual([], calls)

    def test_legacy_mutations_are_gone_but_procedural_cancel_remains(self) -> None:
        retired = (
            ("/api/lighting/concepts", {"prompt": "old"}),
            ("/api/lighting/jobs/not-a-job/concepts", {}),
            ("/api/lighting/jobs/not-a-job/animate", {}),
            ("/api/lighting/jobs/not-a-job/process", {}),
            ("/api/led/generate", {"prompt": "old"}),
            ("/api/led/generate/cancel", {}),
        )
        for path, body in retired:
            with self.subTest(path=path):
                status, response = self._request("POST", path, body)
                self.assertEqual(410, status)
                self.assertEqual("retired", response["code"])

        manifest = self.library.create_job(
            prompt="cancel me",
            target={
                "family": "80",
                "product_id": "AM21",
                "raster": {"width": 18, "height": 7},
                "targets": ["keyframes", "spotlight_frames"],
                "frame_cap": 200,
            },
            models={
                "backend": "ollama",
                "provider": "ollama",
                "model_id": "ornith:latest",
            },
        )
        cancelled: list[str] = []

        def cancel(job_id):
            cancelled.append(job_id)
            return self.library.update_manifest(
                job_id, {"status": "cancelled", "phase": "cancelled"}
            )

        self.server.state._procedural_coordinator = SimpleNamespace(
            active_job_id=manifest["job_id"],
            cancel=cancel,
        )
        self.server.state._procedural_library_identity = id(self.library)
        status, response = self._request(
            "POST", f"/api/lighting/jobs/{manifest['job_id']}/cancel", {}
        )
        self.assertEqual(200, status)
        self.assertEqual({"job_id": manifest["job_id"]}, response)
        self.assertEqual([manifest["job_id"]], cancelled)

    def test_unready_and_missing_target_stop_before_inference(self) -> None:
        original_require_ready = self.capability.require_ready
        self.capability.require_ready = lambda: (_ for _ in ()).throw(
            AICapabilityError("disabled")
        )
        status, response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "blocked",
                "backend": "ollama",
                "target": "keyframes",
                "document_revision": self.document_revision,
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("disabled", response["code"])
        self.assertEqual([], self.provider.calls)
        self.assertEqual([], self.library.scan()["jobs"])

        self.capability.require_ready = original_require_ready
        stale_revision = self.document_revision
        self.server.state.clear_document()
        status, response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "no device",
                "backend": "ollama",
                "target": "keyframes",
                "document_revision": stale_revision,
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("document_required", response["code"])
        self.assertEqual([], self.provider.calls)
        self.assertEqual([], self.library.scan()["jobs"])


if __name__ == "__main__":
    unittest.main()
