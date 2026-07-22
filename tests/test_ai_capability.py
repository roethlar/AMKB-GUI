from __future__ import annotations

import copy
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from am_configurator import ai_catalog, llm
from am_configurator.ai_capability import (
    AICapabilityError,
    AICapabilityService,
    api_setup_fingerprint,
    local_setup_fingerprint,
)
from am_configurator.local_ai_runtime import GpuProbe, RuntimePaths
from am_configurator.local_model import SelectedModel
from am_configurator.recipe_provider import RecipeResult


DEFAULTS = {
    "schema_version": 3,
    "ai": {
        "enabled": False,
        "backend": None,
        "local": {"setup_fingerprint": None},
        "api": {
            "provider": "xai",
            "model_id": "grok-4.5",
            "setup_fingerprint": None,
            "disclosure_version": None,
            "disclosure_at": None,
        },
    },
    "library": {"current_root": None, "roots": []},
    "generation": {"loop_mode": "smooth"},
}


class _ModelManager:
    def __init__(self, model: SelectedModel | None = None, invalid: bool = False) -> None:
        self.model = model
        self.invalid = invalid

    def status(self):
        if self.invalid:
            return {
                "selected": True,
                "filename": None,
                "size_bytes": None,
                "verified": False,
                "reason": "model_invalid",
            }
        if self.model is None:
            return {
                "selected": False,
                "filename": None,
                "size_bytes": None,
                "verified": False,
                "reason": "model_missing",
            }
        return {
            "selected": True,
            "filename": self.model.filename,
            "size_bytes": self.model.size_bytes,
            "verified": True,
            "reason": None,
        }

    def resolve_selected(self):
        if self.model is None:
            raise RuntimeError("missing")
        return self.model


class _Provider:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = 0

    def generate(self, request, deadline, cancelled):
        self.calls += 1
        return RecipeResult(
            recipe={
                "schema_version": 1,
                "name": "Setup",
                "density": "balanced",
                "background": "#000000",
                "palette": ["#FFFFFF"],
                "layers": [
                    {
                        "kind": "pulse",
                        "color_index": 0,
                        "secondary_color_index": 0,
                        "speed": 1,
                        "phase": 0.0,
                        "direction_degrees": 0.0,
                        "center_x": 0.5,
                        "center_y": 0.5,
                        "scale": 1.0,
                        "width": 0.5,
                        "trail": 0.0,
                        "count": 1,
                        "intensity": 1.0,
                        "seed": 1,
                    }
                ],
            },
            backend="local",
            provider="llama.cpp",
            model_id="selected.gguf",
            usage=None,
        )

    def close(self) -> None:
        self.closed += 1


class _FailingProvider:
    def __init__(self, code: str) -> None:
        self.code = code
        self.calls = 0

    def generate(self, request, deadline, cancelled):
        self.calls += 1
        raise llm.ProviderError(self.code, "Pathless provider failure.")


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="am-capability-"))
        self.directory = directory
        self.runtime = RuntimePaths(
            cli=directory / "llama-cli", server=directory / "llama-server"
        )
        self.model = SelectedModel(
            path=directory / "selected.gguf",
            filename="selected.gguf",
            size_bytes=2_000_000,
            sha256="a" * 64,
            device=1,
            inode=2,
            mtime_ns=3,
        )
        self.settings = copy.deepcopy(DEFAULTS)
        self.credential = None
        self.writes: list[tuple] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def _service(
        self,
        *,
        manager=None,
        runtime_available=True,
        provider=None,
        host=(True, "metal"),
        credential_available=True,
    ):
        manager = _ModelManager() if manager is None else manager

        def write_fingerprint(backend, fingerprint):
            self.writes.append(("fingerprint", backend, fingerprint))
            self.settings["ai"][backend]["setup_fingerprint"] = fingerprint
            return copy.deepcopy(self.settings)

        def write_ai(values, ready=False):
            self.writes.append(("ai", copy.deepcopy(values), ready))
            self.settings["ai"]["enabled"] = values["enabled"]
            self.settings["ai"]["backend"] = values["backend"]
            return copy.deepcopy(self.settings)

        def runtime_resolver():
            if not runtime_available:
                raise RuntimeError("private runtime path")
            return self.runtime

        credential_status = lambda: {
            "available": credential_available,
            "configured": self.credential is not None,
            "external": False,
        }
        return AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            model_manager=manager,
            runtime_resolver=runtime_resolver,
            runtime_identity_loader=lambda runtime: "b" * 64,
            host_capability=lambda: host,
            credential_status_loader=credential_status,
            credential_resolver=lambda: self.credential,
            fingerprint_writer=write_fingerprint,
            ai_settings_writer=write_ai,
            gpu_probe=lambda runtime, model, **_kwargs: GpuProbe("metal", 37, 37),
            local_provider_factory=lambda: provider or _Provider(),
            api_provider_factory=lambda key, model: provider or _Provider(),
        )

    def test_default_status_is_exact_pathless_and_disabled(self) -> None:
        provider = _Provider()
        service = self._service(runtime_available=False, provider=provider)
        self.assertEqual(
            {
                "schema_version": 1,
                "enabled": False,
                "backend": None,
                "ready": False,
                "reason": "disabled",
                "local": {
                    "supported": True,
                    "gpu_backend": "metal",
                    "runtime_verified": False,
                    "model_selected": False,
                    "model_filename": None,
                    "model_verified": False,
                    "setup_tested": False,
                },
                "api": {
                    "provider": "xai",
                    "model_id": "grok-4.5",
                    "credential_set": False,
                    "disclosure_current": False,
                    "setup_tested": False,
                },
            },
            service.status(),
        )
        with self.assertRaises(AICapabilityError):
            service.provider_for_generation()
        self.assertEqual(0, provider.calls)

    def test_local_readiness_uses_attested_user_model_not_a_catalog(self) -> None:
        manager = _ModelManager(self.model)
        fingerprint = local_setup_fingerprint("b" * 64, self.model.sha256)
        self.settings["ai"].update({"enabled": True, "backend": "local"})
        self.settings["ai"]["local"]["setup_fingerprint"] = fingerprint

        status = self._service(manager=manager).status()

        self.assertTrue(status["ready"])
        self.assertEqual("ready", status["reason"])
        self.assertEqual("selected.gguf", status["local"]["model_filename"])
        self.assertTrue(status["local"]["setup_tested"])

        manager.invalid = True
        status = self._service(manager=manager).status()
        self.assertFalse(status["ready"])
        self.assertEqual("model_invalid", status["reason"])

    def test_readiness_reasons_are_exact_and_invocation_fails_closed(self) -> None:
        self.settings["ai"]["enabled"] = True
        self.settings["ai"]["backend"] = None
        service = self._service()
        self.assertEqual("backend_unselected", service.status()["reason"])

        self.settings["ai"]["backend"] = "local"
        self.assertEqual(
            "gpu_unsupported",
            self._service(host=(False, None)).status()["reason"],
        )
        self.assertEqual(
            "runtime_unavailable",
            self._service(runtime_available=False).status()["reason"],
        )
        self.assertEqual("model_missing", service.status()["reason"])
        with self.assertRaises(AICapabilityError) as captured:
            service.require_ready()
        self.assertEqual("model_missing", captured.exception.reason)

        self.settings["ai"]["backend"] = "api"
        self.assertEqual(
            "credential_store_unavailable",
            self._service(credential_available=False).status()["reason"],
        )

    def test_api_readiness_requires_credential_disclosure_and_matching_setup(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        service = self._service()
        self.assertEqual("credential_missing", service.status()["reason"])

        self.credential = "sk-private"
        self.assertEqual("disclosure_required", service.status()["reason"])
        api = self.settings["ai"]["api"]
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-21T00:00:00+00:00"
        self.assertEqual("setup_required", service.status()["reason"])
        api["setup_fingerprint"] = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        status = service.status()
        self.assertTrue(status["ready"])
        self.assertEqual("ready", status["reason"])
        self.assertNotIn(self.credential, str(status))

    def test_local_test_probes_full_gpu_then_enables_exact_components(self) -> None:
        manager = _ModelManager(self.model)
        provider = _Provider()
        self.settings["ai"]["backend"] = "local"
        service = self._service(manager=manager, provider=provider)

        status = service.test_and_enable(
            "local", deadline=time.monotonic() + 10, cancelled=lambda: False
        )

        self.assertEqual(1, provider.calls)
        self.assertTrue(status["ready"])
        self.assertEqual("ready", status["reason"])
        self.assertEqual(
            local_setup_fingerprint("b" * 64, self.model.sha256),
            self.settings["ai"]["local"]["setup_fingerprint"],
        )
        self.assertIn(("ai", {"enabled": True, "backend": "local"}, True), self.writes)
        service.close()
        self.assertEqual(1, provider.closed)

    def test_generation_failure_does_not_invalidate_a_ready_local_model(self) -> None:
        manager = _ModelManager(self.model)
        failure = _FailingProvider("bad_response")
        self.settings["ai"].update({"enabled": True, "backend": "local"})
        self.settings["ai"]["local"]["setup_fingerprint"] = (
            local_setup_fingerprint("b" * 64, self.model.sha256)
        )
        service = self._service(manager=manager, provider=failure)

        provider = service.provider_for_generation()
        self.assertIs(provider, service.provider_for_generation())
        with self.assertRaises(llm.ProviderError):
            provider.generate(None, time.monotonic() + 10, lambda: False)

        self.assertEqual(1, failure.calls)
        self.assertTrue(service.status()["ready"])
        self.assertEqual("ready", service.status()["reason"])

    def test_api_auth_failure_invalidates_setup_without_exposing_the_key(self) -> None:
        failure = _FailingProvider("auth")
        self.credential = "sk-private-auth"
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        api = self.settings["ai"]["api"]
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-21T00:00:00+00:00"
        api["setup_fingerprint"] = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        service = self._service(provider=failure)

        with self.assertRaises(llm.ProviderError) as captured:
            service.test_and_enable(
                "api", deadline=time.monotonic() + 10, cancelled=lambda: False
            )

        self.assertEqual("auth", captured.exception.code)
        status = service.status()
        self.assertEqual("auth_invalid", status["reason"])
        self.assertFalse(status["ready"])
        self.assertNotIn(self.credential, str(status))
        self.assertEqual("api", self.settings["ai"]["backend"])
        self.assertTrue(self.settings["ai"]["enabled"])

    def test_transient_api_failure_does_not_invalidate_a_ready_backend(self) -> None:
        failure = _FailingProvider("offline")
        self.credential = "sk-private-transient"
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        api = self.settings["ai"]["api"]
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-21T00:00:00+00:00"
        fingerprint = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        api["setup_fingerprint"] = fingerprint
        service = self._service(provider=failure)

        with self.assertRaises(llm.ProviderError):
            service.test_and_enable(
                "api", deadline=time.monotonic() + 10, cancelled=lambda: False
            )

        self.assertEqual(fingerprint, api["setup_fingerprint"])
        self.assertTrue(service.status()["ready"])
        self.assertEqual("api", self.settings["ai"]["backend"])


if __name__ == "__main__":
    unittest.main()
