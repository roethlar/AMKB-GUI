from __future__ import annotations

import copy
import threading
import time
import unittest

from am_configurator import ai_catalog, llm
from am_configurator.ai_capability import (
    AICapabilityError,
    AICapabilityService,
    api_setup_fingerprint,
    ollama_setup_fingerprint,
)
from am_configurator.ollama_client import OllamaError, OllamaModel
from am_configurator.recipe_provider import RecipeResult


DEFAULTS = {
    "schema_version": 5,
    "ai": {
        "enabled": False,
        "backend": None,
        "local": {
            "model_id": None,
            "model_digest": None,
            "setup_fingerprint": None,
        },
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
            provider="ollama",
            model_id="ornith:latest",
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


class _OllamaClient:
    def __init__(self, models: list[OllamaModel], *, available: bool = True) -> None:
        self.models = models
        self.available = available
        self.calls = 0

    def list_models(self, *, deadline):
        del deadline
        self.calls += 1
        if not self.available:
            raise OllamaError("unavailable", "Local Ollama is unavailable.")
        return tuple(self.models)


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = copy.deepcopy(DEFAULTS)
        self.ollama_model = OllamaModel(
            model_id="ornith:latest",
            digest="c" * 64,
            size_bytes=5_629_110_568,
            parameter_size="9.0B",
            quantization="Q4_K_M",
        )
        self.ollama_models: list[OllamaModel] = []
        self.credential = None
        self.writes: list[tuple] = []

    def _service(
        self,
        *,
        provider=None,
        credential_available=True,
        credential_invalid=False,
        ollama_available=True,
    ):
        def write_fingerprint(backend, fingerprint):
            self.writes.append(("fingerprint", backend, fingerprint))
            self.settings["ai"][backend]["setup_fingerprint"] = fingerprint
            return copy.deepcopy(self.settings)

        def write_ai(values, ready=False):
            self.writes.append(("ai", copy.deepcopy(values), ready))
            self.settings["ai"]["enabled"] = values["enabled"]
            self.settings["ai"]["backend"] = values["backend"]
            return copy.deepcopy(self.settings)

        credential_status = lambda: {
            "available": credential_available,
            "configured": self.credential is not None,
            "external": False,
            "invalid": credential_invalid,
        }
        return AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=credential_status,
            credential_resolver=lambda: self.credential,
            fingerprint_writer=write_fingerprint,
            ai_settings_writer=write_ai,
            api_provider_factory=lambda key, model: provider or _Provider(),
            ollama_client=_OllamaClient(
                self.ollama_models,
                available=ollama_available,
            ),
            ollama_provider_factory=lambda model: provider or _Provider(),
        )

    def test_default_status_is_exact_pathless_and_disabled(self) -> None:
        provider = _Provider()
        service = self._service(provider=provider)
        self.assertEqual(
            {
                "schema_version": 1,
                "enabled": False,
                "backend": None,
                "ready": False,
                "reason": "disabled",
                "local": {
                    "service_available": True,
                    "model_selected": False,
                    "model_id": None,
                    "model_verified": False,
                    "setup_tested": False,
                    "provider": "ollama",
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

    def test_readiness_reasons_are_exact_and_invocation_fails_closed(self) -> None:
        self.settings["ai"]["enabled"] = True
        self.settings["ai"]["backend"] = None
        service = self._service()
        self.assertEqual("backend_unselected", service.status()["reason"])

        self.settings["ai"]["backend"] = "local"
        self.assertEqual(
            "ollama_unavailable",
            self._service(ollama_available=False).status()["reason"],
        )
        self.assertEqual("model_missing", service.status()["reason"])
        with self.assertRaises(AICapabilityError) as captured:
            service.require_ready()
        self.assertEqual("model_missing", captured.exception.reason)

        self.settings["ai"]["backend"] = "api"
        self.assertEqual(
            "credential_invalid",
            self._service(credential_invalid=True).status()["reason"],
        )
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

    def test_ollama_setup_uses_installed_name_and_digest(self) -> None:
        provider = _Provider()
        self.ollama_models = [self.ollama_model]
        self.settings["ai"]["backend"] = "local"
        self.settings["ai"]["local"].update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
        })
        service = self._service(provider=provider)

        status = service.test_and_enable(
            "local", deadline=time.monotonic() + 10, cancelled=lambda: False
        )

        self.assertEqual(1, provider.calls)
        self.assertTrue(status["ready"])
        self.assertEqual("ollama", status["local"]["provider"])
        self.assertEqual("ornith:latest", status["local"]["model_id"])
        self.assertEqual(
            ollama_setup_fingerprint("ornith:latest", "c" * 64),
            self.settings["ai"]["local"]["setup_fingerprint"],
        )

        self.ollama_models.clear()
        self.assertEqual("model_unavailable", service.status()["reason"])

    def test_backend_setup_validity_is_independent_of_enabled_state(self) -> None:
        self.ollama_models = [self.ollama_model]
        local = self.settings["ai"]["local"]
        local.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "setup_fingerprint": ollama_setup_fingerprint(
                self.ollama_model.model_id,
                self.ollama_model.digest,
            ),
        })
        self.settings["ai"]["backend"] = "local"
        service = self._service()

        self.assertFalse(service.status()["enabled"])
        self.assertTrue(service.backend_setup_valid("local"))

        failed_service = self._service(provider=_FailingProvider("bad_response"))
        with self.assertRaises(llm.ProviderError):
            failed_service.test_and_enable(
                "local", deadline=time.monotonic() + 10, cancelled=lambda: False
            )
        self.assertFalse(failed_service.backend_setup_valid("local"))

        self.ollama_models[:] = [
            OllamaModel(
                model_id=self.ollama_model.model_id,
                digest="d" * 64,
                size_bytes=self.ollama_model.size_bytes,
                parameter_size=self.ollama_model.parameter_size,
                quantization=self.ollama_model.quantization,
            )
        ]
        self.assertFalse(service.backend_setup_valid("local"))

        self.ollama_models.clear()
        self.assertFalse(service.backend_setup_valid("local"))

        self.credential = "sk-original"
        api = self.settings["ai"]["api"]
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-22T00:00:00+00:00"
        api["setup_fingerprint"] = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        self.assertTrue(service.backend_setup_valid("api"))

        self.credential = "sk-replaced"
        self.assertFalse(service.backend_setup_valid("api"))

    def test_generation_failure_does_not_invalidate_a_ready_local_model(self) -> None:
        failure = _FailingProvider("bad_response")
        self.ollama_models = [self.ollama_model]
        self.settings["ai"].update({"enabled": True, "backend": "local"})
        self.settings["ai"]["local"].update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "setup_fingerprint": ollama_setup_fingerprint(
                self.ollama_model.model_id,
                self.ollama_model.digest,
            ),
        })
        service = self._service(provider=failure)

        provider = service.provider_for_generation()
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

    def test_provider_construction_is_singleton_per_backend_identity(self) -> None:
        self.ollama_models = [self.ollama_model]
        self.settings["ai"].update({"enabled": True, "backend": "local"})
        local = self.settings["ai"]["local"]
        local.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "setup_fingerprint": ollama_setup_fingerprint(
                self.ollama_model.model_id,
                self.ollama_model.digest,
            ),
        })
        local_created: list[object] = []
        api_created: list[object] = []
        first_factory_entered = threading.Event()
        second_factory_entered = threading.Event()
        release_factory = threading.Event()

        def local_factory(_model):
            provider = object()
            local_created.append(provider)
            first_factory_entered.set()
            if len(local_created) > 1:
                second_factory_entered.set()
            if not release_factory.wait(2):
                raise TimeoutError("test did not release provider construction")
            return provider

        def api_factory(_credential, _model_id):
            provider = object()
            api_created.append(provider)
            return provider

        service = AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=lambda: {
                "available": True,
                "configured": self.credential is not None,
                "external": False,
                "invalid": False,
            },
            credential_resolver=lambda: self.credential,
            fingerprint_writer=lambda *_args: None,
            ai_settings_writer=lambda *_args, **_kwargs: None,
            api_provider_factory=api_factory,
            ollama_client=_OllamaClient(self.ollama_models),
            ollama_provider_factory=local_factory,
        )
        results: list[object] = []
        failures: list[BaseException] = []

        def resolve_provider() -> None:
            try:
                results.append(service.provider_for_generation())
            except BaseException as error:
                failures.append(error)

        first = threading.Thread(target=resolve_provider)
        second = threading.Thread(target=resolve_provider)
        first.start()
        self.assertTrue(first_factory_entered.wait(1))
        second.start()
        second_factory_entered.wait(0.2)
        release_factory.set()
        first.join(2)
        second.join(2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(1, len(local_created))
        self.assertEqual(2, len(results))
        self.assertIs(results[0], results[1])

        self.credential = "sk-provider-cache-one"
        self.settings["ai"]["backend"] = "api"
        api = self.settings["ai"]["api"]
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-22T00:00:00+00:00"
        api["setup_fingerprint"] = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        first_api = service.provider_for_generation()
        self.assertIs(first_api, service.provider_for_generation())
        self.assertEqual(1, len(api_created))

        self.credential = "sk-provider-cache-two"
        api["setup_fingerprint"] = api_setup_fingerprint(
            "xai",
            "grok-4.5",
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        second_api = service.provider_for_generation()
        self.assertIsNot(first_api, second_api)
        self.assertEqual(2, len(api_created))


if __name__ == "__main__":
    unittest.main()
