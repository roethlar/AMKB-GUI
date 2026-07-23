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
from am_configurator.ai_capability import AICapabilityError, AICapabilityService
from am_configurator.credentials import MemoryCredentialStore
from am_configurator.generation_admission import OperationGate
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.llm import ProviderError
from am_configurator.ollama_client import OLLAMA_MODELS_URL, OllamaClient
from am_configurator.procedural_generation import ProceduralGenerationCoordinator
from am_configurator.recipe_provider import RecipeResult
from am_configurator.server import create_server


_RECIPE = Path(__file__).parent / "fixtures" / "ornith_dense_aurora_recipe.json"


def _ready_status() -> dict:
    return {
        "schema_version": 1,
        "enabled": True,
        "backend": "local",
        "ready": True,
        "reason": "ready",
        "local": {
            "service_available": True,
            "model_selected": True,
            "model_id": "ornith:latest",
            "model_verified": True,
            "setup_tested": True,
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
            backend="local",
            provider="ollama",
            model_id="ornith:latest",
            usage=None,
        )


class _OllamaResponse:
    def __init__(self, value: object) -> None:
        self._payload = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self._payload[:limit]


class _Capability:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.test_calls: list[str] = []
        self.validation_calls: list[str] = []
        self.closed = False
        self.status_value = _ready_status()

    def status(self):
        return copy.deepcopy(self.status_value)

    def backend_setup_valid(self, backend):
        self.validation_calls.append(backend)
        current = self.status()
        if backend == "local":
            local = current["local"]
            return all(
                local[field] is True
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

    def test_and_enable(self, backend, *, deadline, cancelled):
        self.test_calls.append(backend)
        return self.status()

    def discover_local_models(self):
        return {
            "available": True,
            "models": [
                {
                    "model_id": "ornith:latest",
                    "digest": "a" * 64,
                    "size_bytes": 5_629_110_568,
                    "parameter_size": "9.0B",
                    "quantization": "Q4_K_M",
                }
            ],
        }

    def close(self):
        self.closed = True


class _LegacyCoordinator:
    active_job_id = None

    def reconcile_startup(self, *, api_key=None, _admission_token=None):
        del _admission_token
        return []


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
            operation_timeout_seconds=30,
        )
        config_path = Path(self.temporary.name) / "config.json"
        config_path.write_text(
            json.dumps(_valid_config("AM21")),
            encoding="utf-8",
        )
        self.server, url = create_server(
            [str(config_path)],
            lighting_library=self.library,
            lighting_coordinator=_LegacyCoordinator(),
            lighting_dependencies={"operation_gate": self.gate},
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
            with urlopen(request, timeout=15) as response:
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
            ("GET", "/api/ai/status", None),
            ("GET", "/api/ai/local/models", None),
            ("POST", "/api/settings/ai", {"enabled": False, "backend": "local"}),
            ("POST", "/api/settings/credential", {"provider": "xai", "key": "secret"}),
            ("POST", "/api/settings/migration/discard-credential", {"confirm": True}),
            ("POST", "/api/ai/test", {"backend": "local"}),
            ("POST", "/api/ai/local/select", {"model_id": "ornith:latest"}),
            ("POST", "/api/ai/local/gguf/select", {}),
            ("POST", "/api/ai/local/clear", {}),
            ("POST", "/api/document/sync", {"config": _valid_config("AM21")}),
            ("POST", "/api/lighting/effects", {"prompt": "aurora", "backend": "local"}),
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
        self.assertEqual({"revision"}, set(response))
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

    def test_setup_routes_are_strict_pathless_and_never_echo_credentials(self) -> None:
        status, capability = self._request("GET", "/api/ai/status")
        self.assertEqual(200, status)
        self.assertEqual(_ready_status(), capability)
        status, _response = self._request("GET", "/api/ai/status?extra=true")
        self.assertEqual(400, status)

        status, models = self._request("GET", "/api/ai/local/models")
        self.assertEqual(200, status)
        self.assertEqual(["ornith:latest"], [item["model_id"] for item in models["models"]])
        status, _response = self._request("GET", "/api/ai/local/models?host=other")
        self.assertEqual(400, status)

        secret = "sk-route-secret-12345678"
        status, response = self._request(
            "POST",
            "/api/settings/credential",
            {"provider": "xai", "key": secret},
        )
        self.assertEqual(200, status)
        self.assertNotIn(secret, json.dumps(response))
        self.assertEqual(secret, self.credentials.get("xai"))

        status, _response = self._request(
            "POST", "/api/settings/ai", {"enabled": False, "backend": "local"}
        )
        self.assertEqual(200, status)
        self.assertEqual("local", store.load_settings(credential_store=self.credentials)["ai"]["backend"])

        status, _response = self._request(
            "POST", "/api/ai/test", {"backend": "local"}
        )
        self.assertEqual(200, status)
        self.assertEqual(["local"], self.capability.test_calls)

        status, _response = self._request(
            "POST", "/api/ai/local/select", {"path": "/tmp/injected.gguf"}
        )
        self.assertEqual(400, status)
        status, response = self._request(
            "POST", "/api/ai/local/select", {"model_id": "ornith:latest"}
        )
        self.assertEqual(200, status)
        local = store.load_settings(credential_store=self.credentials)["ai"]["local"]
        self.assertEqual("ornith:latest", local["model_id"])

        status, response = self._request("POST", "/api/ai/local/gguf/select", {})
        self.assertEqual(404, status)
        self.assertNotIn("private", json.dumps(response))

        status, _response = self._request("POST", "/api/ai/local/clear", {})
        self.assertEqual(200, status)
        self.assertIsNone(
            store.load_settings(credential_store=self.credentials)["ai"]["local"]["model_id"]
        )

    def test_real_ollama_discovery_and_selection_cross_the_server_contract(self) -> None:
        digest = "d" * 64
        model = {
            "name": "ornith:latest",
            "model": "ornith:latest",
            "digest": digest,
            "size": 5_629_110_568,
            "capabilities": ["completion"],
            "details": {
                "parameter_size": "9.0B",
                "quantization_level": "Q4_K_M",
            },
        }
        transport = {"outcome": OSError("offline")}
        calls: list[tuple[str, str, float]] = []

        def opener(request, timeout):
            calls.append((request.full_url, request.get_method(), timeout))
            outcome = transport["outcome"]
            if isinstance(outcome, BaseException):
                raise outcome
            return _OllamaResponse(outcome)

        self.server.state._ai_capability = None
        self.server.state._ollama_client = OllamaClient(opener=opener)

        status, response = self._request("GET", "/api/ai/local/models")
        self.assertEqual(200, status)
        self.assertEqual({"available": False, "models": []}, response)
        self.assertIsInstance(self.server.state.ai_services(), AICapabilityService)

        transport["outcome"] = {"models": [model]}
        status, response = self._request("GET", "/api/ai/local/models")
        self.assertEqual(200, status)
        self.assertEqual(
            {
                "available": True,
                "models": [
                    {
                        "model_id": "ornith:latest",
                        "digest": digest,
                        "size_bytes": 5_629_110_568,
                        "parameter_size": "9.0B",
                        "quantization": "Q4_K_M",
                    }
                ],
            },
            response,
        )

        status, _response = self._request(
            "POST", "/api/ai/local/select", {"model_id": "missing:latest"}
        )
        self.assertEqual(400, status)
        local = store.load_settings(credential_store=self.credentials)["ai"]["local"]
        self.assertEqual(
            {
                "model_id": None,
                "model_digest": None,
                "setup_fingerprint": None,
            },
            local,
        )

        status, _response = self._request(
            "POST", "/api/ai/local/select", {"model_id": "ornith:latest"}
        )
        self.assertEqual(200, status)
        local = store.load_settings(credential_store=self.credentials)["ai"]["local"]
        self.assertEqual(
            {
                "model_id": "ornith:latest",
                "model_digest": digest,
                "setup_fingerprint": None,
            },
            local,
        )

        transport["outcome"] = {"models": {"not": "a list"}}
        status, response = self._request("GET", "/api/ai/local/models")
        self.assertEqual(200, status)
        self.assertEqual({"available": False, "models": []}, response)
        self.assertEqual(5, len(calls))
        for url, method, timeout in calls:
            self.assertEqual(OLLAMA_MODELS_URL, url)
            self.assertEqual("GET", method)
            self.assertGreater(timeout, 0)

    def test_invalid_credential_input_is_a_stable_non_secret_client_error(self) -> None:
        secret = "sk-route\nsecret"

        status, response = self._request(
            "POST",
            "/api/settings/credential",
            {"provider": "xai", "key": secret},
        )

        self.assertEqual(400, status)
        self.assertEqual("credential_invalid", response["code"])
        self.assertEqual("API credential is invalid.", response["error"])
        self.assertNotIn(secret, json.dumps(response))
        self.assertIsNone(self.credentials.get("xai"))

    def test_unchanged_tested_backend_can_be_reenabled_without_another_test(self) -> None:
        store.update_ai_settings(
            {"enabled": True, "backend": "local"},
            ready=True,
            credential_store=self.credentials,
        )
        status, _response = self._request(
            "POST", "/api/settings/ai", {"enabled": False, "backend": "local"}
        )
        self.assertEqual(200, status)
        self.assertFalse(
            store.load_settings(credential_store=self.credentials)["ai"]["enabled"]
        )

        self.capability.status_value.update({
            "enabled": False,
            "ready": False,
            "reason": "disabled",
        })

        status, _response = self._request(
            "POST",
            "/api/settings/ai",
            {
                "enabled": True,
                "backend": "local",
                "provider": "xai",
                "model_id": "grok-4.5",
            },
        )

        self.assertEqual(200, status)
        self.assertTrue(
            store.load_settings(credential_store=self.credentials)["ai"]["enabled"]
        )
        self.assertEqual(["local"], self.capability.validation_calls)
        self.assertEqual([], self.capability.test_calls)

    def test_blocked_legacy_migration_requires_confirmed_credential_discard(self) -> None:
        secret = "sk-only-legacy-route-copy"
        library_root = Path(self.temporary.name) / "legacy-library"
        legacy = {
            "schema_version": 2,
            "llm": {
                "models": {
                    "interpreter": "grok-4.3",
                    "concept": "grok-imagine-image-quality",
                    "video": "grok-imagine-video",
                },
                "keys": {"xai": secret},
            },
            "library": {"current_root": str(library_root), "roots": []},
            "generation": {
                "candidate_count": 4,
                "loop_mode": "ping_pong",
                "privacy_ack_version": "2026-07-20-xai-v1",
                "privacy_ack_at": "2026-07-20T12:00:00+00:00",
            },
        }
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        original = (json.dumps(legacy, indent=2) + "\n").encode("utf-8")
        path.write_bytes(original)
        self.credentials.set("xai", "vault-value-must-remain")
        self.credentials._available = False

        status, settings = self._request("GET", "/api/settings")
        self.assertEqual(200, status)
        self.assertEqual(
            {"required": True, "reason": "credential_store_unavailable"},
            settings["migration"],
        )
        self.assertNotIn(secret, json.dumps(settings))
        self.assertEqual(original, path.read_bytes())

        status, response = self._request(
            "POST", "/api/settings/ai", {"enabled": False, "backend": "local"}
        )
        self.assertEqual(400, status)
        self.assertNotIn(secret, json.dumps(response))
        self.assertEqual(original, path.read_bytes())
        for body in ({"confirm": False}, {"confirm": True, "extra": True}):
            with self.subTest(body=body):
                status, _response = self._request(
                    "POST", "/api/settings/migration/discard-credential", body
                )
                self.assertEqual(400, status)
                self.assertEqual(original, path.read_bytes())

        status, repaired = self._request(
            "POST",
            "/api/settings/migration/discard-credential",
            {"confirm": True},
        )

        self.assertEqual(200, status)
        self.assertEqual({"required": False, "reason": None}, repaired["migration"])
        self.assertEqual("ping_pong", repaired["generation"]["loop_mode"])
        self.assertEqual(str(library_root.resolve()), repaired["library"]["current_root"])
        self.assertNotIn(secret, path.read_text("utf-8"))
        self.credentials._available = True
        self.assertEqual("vault-value-must-remain", self.credentials.get("xai"))

    def test_effect_route_owns_target_model_frames_and_banks_offline_result(self) -> None:
        status, started = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "Dense violet aurora",
                "backend": "local",
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
                "targets": ["keyframes", "spotlight_frames"],
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
                "backend": "local",
                "document_revision": self.document_revision,
                "product_id": "CB04",
                "model_path": "/tmp/model.gguf",
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
                "document_revision": self.document_revision,
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("backend_mismatch", response["code"])
        self.assertEqual(1, len(self.provider.calls))

    def test_effect_route_derives_each_device_family_target_server_side(self) -> None:
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
                {
                    "family": "ALICE",
                    "product_id": "ALICE",
                    "raster": {"width": 16, "height": 5},
                    "targets": ["keyframes"],
                    "frame_cap": 186,
                },
            ),
        )
        for product_id, expected in cases:
            with self.subTest(product_id=product_id):
                stale_revision = self.document_revision
                revision = self._sync_document(product_id)
                before = len(calls)
                status, response = self._request(
                    "POST",
                    "/api/lighting/effects",
                    {
                        "prompt": "stale target",
                        "backend": "local",
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
                        "backend": "local",
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
                "backend": "local",
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
                "backend": "local",
                "provider": "ollama",
                "model_id": "ornith:latest",
            },
            pipeline="procedural",
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

    def test_unready_missing_target_and_busy_states_stop_before_inference(self) -> None:
        original_require_ready = self.capability.require_ready
        self.capability.require_ready = lambda: (_ for _ in ()).throw(
            AICapabilityError("disabled")
        )
        status, response = self._request(
            "POST",
            "/api/lighting/effects",
            {
                "prompt": "blocked",
                "backend": "local",
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
                "backend": "local",
                "document_revision": stale_revision,
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("document_required", response["code"])
        self.assertEqual([], self.provider.calls)
        self.assertEqual([], self.library.scan()["jobs"])

        token, _cancelled = self.gate.begin("already-running")
        try:
            status, _response = self._request(
                "POST", "/api/ai/test", {"backend": "local"}
            )
            self.assertEqual(409, status)
            status, _response = self._request(
                "POST", "/api/ai/local/select", {"model_id": "ornith:latest"}
            )
            self.assertEqual(409, status)
            status, _response = self._request(
                "POST", "/api/ai/local/gguf/select", {}
            )
            self.assertEqual(404, status)
        finally:
            self.gate.finish(token)
        self.assertEqual([], self.capability.test_calls)

    def test_setup_provider_errors_are_typed_and_unexpected_paths_are_redacted(self) -> None:
        def rate_limited(*_args, **_kwargs):
            raise ProviderError("rate_limited", "slow down", retry_after=7)

        self.capability.test_and_enable = rate_limited
        status, response = self._request(
            "POST", "/api/ai/test", {"backend": "local"}
        )
        self.assertEqual(429, status)
        self.assertEqual("rate_limited", response["code"])
        self.assertEqual(7, response["retry_after"])
        self.assertFalse(self.gate.is_active)

        status, response = self._request("POST", "/api/ai/local/gguf/select", {})
        self.assertEqual(404, status)
        self.assertEqual({"error": "Not found."}, response)


if __name__ == "__main__":
    unittest.main()
