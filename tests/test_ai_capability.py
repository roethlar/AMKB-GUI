from __future__ import annotations

import copy
import inspect
import threading
import time
import unittest
from unittest.mock import patch

from am_configurator import ai_capability, ai_catalog, llm, store
from am_configurator.ai_capability import (
    AICapabilityError,
    AICapabilityService,
    api_setup_fingerprint,
    ollama_setup_fingerprint,
)
from am_configurator.ollama_client import OllamaError, OllamaModel
from am_configurator.recipe_provider import RecipeResult


DEFAULTS = {
    "schema_version": 7,
    "ai": {
        "enabled": False,
        "backend": None,
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "model_id": None,
            "model_digest": None,
            "model_location": None,
            "setup_fingerprint": None,
            "disclosure_version": None,
            "disclosure_at": None,
        },
        "api": {
            "selected_provider": "xai",
            "providers": {
                provider: {
                    "model_id": "grok-4.5" if provider == "xai" else None,
                    "setup_fingerprint": None,
                    "disclosure_version": None,
                    "disclosure_at": None,
                }
                for provider in ai_catalog.API_PROVIDER_IDS
            },
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
            backend="ollama",
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
    def __init__(
        self,
        models: list[OllamaModel],
        *,
        available: bool = True,
        error_code: str | None = None,
    ) -> None:
        self.models = models
        self.available = available
        self.error_code = error_code
        self.calls = 0

    def list_models(self, *, deadline):
        del deadline
        self.calls += 1
        if self.error_code is not None:
            raise OllamaError(self.error_code, "Stable local discovery failure.")
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
        self.last_ollama_client: _OllamaClient | None = None
        self.credential = None
        self.writes: list[tuple] = []

    def _selected_api(self) -> dict:
        api = self.settings["ai"]["api"]
        return api["providers"][api["selected_provider"]]

    def _service(
        self,
        *,
        provider=None,
        credential_available=True,
        credential_invalid=False,
        ollama_available=True,
        ollama_error=None,
    ):
        def write_fingerprint(backend, fingerprint, *, provider=None):
            self.writes.append(("fingerprint", backend, provider, fingerprint))
            if backend == "api":
                selected = self.settings["ai"]["api"]["selected_provider"]
                self.assertEqual(selected, provider)
                self.settings["ai"]["api"]["providers"][selected][
                    "setup_fingerprint"
                ] = fingerprint
            else:
                self.settings["ai"][backend]["setup_fingerprint"] = fingerprint
            return copy.deepcopy(self.settings)

        credential_status = lambda _provider: {
            "available": credential_available,
            "configured": self.credential is not None,
            "external": False,
            "invalid": credential_invalid,
        }
        self.last_ollama_client = _OllamaClient(
            self.ollama_models,
            available=ollama_available,
            error_code=ollama_error,
        )
        return AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=credential_status,
            credential_resolver=lambda _provider: self.credential,
            fingerprint_writer=write_fingerprint,
            api_provider_factory=lambda _provider, key, model: provider or _Provider(),
            ollama_client=self.last_ollama_client,
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
                "ollama": {
                    "base_url": "http://127.0.0.1:11434",
                    "service_available": False,
                    "model_selected": False,
                    "model_id": None,
                    "model_digest": None,
                    "model_location": None,
                    "model_verified": False,
                    "setup_tested": False,
                    "disclosure_required": False,
                    "disclosure_current": True,
                    "disclosure_version": "ollama-data-disclosure-v1",
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

    def test_disabled_or_unselected_status_performs_no_backend_probe(self) -> None:
        ollama = _OllamaClient([self.ollama_model])
        credential_calls = 0

        def credential_status(_provider):
            nonlocal credential_calls
            credential_calls += 1
            raise AssertionError("disabled status probed the credential store")

        service = AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=credential_status,
            credential_resolver=lambda _provider: (_ for _ in ()).throw(
                AssertionError("disabled status resolved a credential")
            ),
            ollama_client=ollama,
        )

        self.assertEqual("disabled", service.status()["reason"])
        self.settings["ai"]["enabled"] = True
        self.assertEqual("backend_unselected", service.status()["reason"])
        self.assertEqual(0, ollama.calls)
        self.assertEqual(0, credential_calls)

    def test_ollama_client_is_cached_by_normalized_origin_and_replaced_on_change(self) -> None:
        created: list[tuple[str, _OllamaClient]] = []

        def client_factory(*, base_url):
            client = _OllamaClient([])
            created.append((base_url, client))
            return client

        with patch.object(ai_capability, "OllamaClient", side_effect=client_factory):
            service = AICapabilityService(
                settings_loader=lambda: copy.deepcopy(self.settings),
            )
            service.discover_ollama_models()
            service.discover_ollama_models()
            self.settings["ai"]["ollama"]["base_url"] = "https://ollama.lan"
            service.discover_ollama_models()

        self.assertEqual(
            [
                "http://127.0.0.1:11434",
                "https://ollama.lan",
            ],
            [base_url for base_url, _client in created],
        )
        self.assertEqual([2, 1], [client.calls for _base_url, client in created])

    def test_enabled_status_never_probes_ollama_inventory(self) -> None:
        ollama = self.settings["ai"]["ollama"]
        ollama.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
            "setup_fingerprint": ollama_setup_fingerprint(
                ollama["base_url"],
                self.ollama_model.model_id,
                self.ollama_model.digest,
                self.ollama_model.location,
                None,
                None,
            ),
        })
        self.settings["ai"].update({"enabled": True, "backend": "ollama"})
        ollama = _OllamaClient([self.ollama_model])
        credential_calls = 0

        def credential_status(_provider):
            nonlocal credential_calls
            credential_calls += 1
            return {
                "available": True,
                "configured": True,
                "external": False,
                "invalid": False,
            }

        service = AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=credential_status,
            credential_resolver=lambda _provider: "sk-selected-backend-only",
            ollama_client=ollama,
        )
        self.assertTrue(service.status()["ready"])
        self.assertEqual(0, ollama.calls)
        self.assertEqual(0, credential_calls)

        self.credential = "sk-selected-backend-only"
        api = self._selected_api()
        api["disclosure_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        api["disclosure_at"] = "2026-07-22T00:00:00+00:00"
        api["setup_fingerprint"] = api_setup_fingerprint(
            self.settings["ai"]["api"]["selected_provider"],
            api["model_id"],
            self.credential,
            api["disclosure_version"],
            api["disclosure_at"],
        )
        self.settings["ai"]["backend"] = "api"
        self.assertTrue(service.status()["ready"])
        self.assertEqual(0, ollama.calls)
        self.assertEqual(1, credential_calls)

    def test_api_status_reads_only_the_selected_provider(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "deepseek"
        status_calls: list[str] = []
        resolve_calls: list[str] = []

        service = AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=lambda provider: (
                status_calls.append(provider)
                or {
                    "available": True,
                    "configured": False,
                    "external": False,
                    "invalid": False,
                }
            ),
            credential_resolver=lambda provider: (
                resolve_calls.append(provider) or None
            ),
            ollama_client=_OllamaClient([]),
        )

        status = service.status()

        self.assertEqual("model_missing", status["reason"])
        self.assertEqual("deepseek", status["api"]["provider"])
        self.assertEqual(["deepseek"], status_calls)
        self.assertEqual([], resolve_calls)

    def test_anthropic_setup_and_generation_share_one_registry_identity(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "anthropic"
        api = self._selected_api()
        api.update(
            {
                "model_id": "claude-sonnet-5",
                "disclosure_version": ai_catalog.provider_disclosure_version(
                    "anthropic"
                ),
                "disclosure_at": "2026-07-27T12:00:00+00:00",
            }
        )
        self.credential = "anthropic-private"
        provider = _Provider()
        service = self._service(provider=provider)

        self.assertEqual("setup_required", service.status()["reason"])
        status = service.test_backend(
            "api",
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )

        self.assertTrue(status["ready"])
        self.assertEqual("anthropic", status["api"]["provider"])
        self.assertEqual("claude-sonnet-5", status["api"]["model_id"])
        self.assertEqual(1, provider.calls)
        self.assertIs(provider, service.provider_for_generation())
        self.assertEqual(
            ("fingerprint", "api", "anthropic", api["setup_fingerprint"]),
            self.writes[-1],
        )

    def test_default_registry_constructs_the_anthropic_adapter(self) -> None:
        from am_configurator.recipe_provider import AnthropicRecipeProvider

        provider = AICapabilityService._default_api_provider(
            "anthropic",
            "anthropic-private",
            "claude-sonnet-5",
        )

        self.assertIsInstance(provider, AnthropicRecipeProvider)

    def test_openai_setup_and_generation_share_one_registry_identity(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "openai"
        api = self._selected_api()
        api.update(
            {
                "model_id": "gpt-5.6-sol",
                "disclosure_version": ai_catalog.provider_disclosure_version(
                    "openai"
                ),
                "disclosure_at": "2026-07-27T12:00:00+00:00",
            }
        )
        self.credential = "openai-private"
        provider = _Provider()
        service = self._service(provider=provider)

        self.assertEqual("setup_required", service.status()["reason"])
        status = service.test_backend(
            "api",
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )

        self.assertTrue(status["ready"])
        self.assertEqual("openai", status["api"]["provider"])
        self.assertEqual("gpt-5.6-sol", status["api"]["model_id"])
        self.assertEqual(1, provider.calls)
        self.assertIs(provider, service.provider_for_generation())
        self.assertEqual(
            ("fingerprint", "api", "openai", api["setup_fingerprint"]),
            self.writes[-1],
        )

    def test_default_registry_constructs_the_openai_adapter(self) -> None:
        from am_configurator.recipe_provider import OpenAIRecipeProvider

        provider = AICapabilityService._default_api_provider(
            "openai",
            "openai-private",
            "gpt-5.6-sol",
        )

        self.assertIsInstance(provider, OpenAIRecipeProvider)

    def test_gemini_setup_and_generation_share_one_registry_identity(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "gemini"
        api = self._selected_api()
        api.update(
            {
                "model_id": "gemini-3.6-flash",
                "disclosure_version": ai_catalog.provider_disclosure_version(
                    "gemini"
                ),
                "disclosure_at": "2026-07-27T12:00:00+00:00",
            }
        )
        self.credential = "gemini-private"
        provider = _Provider()
        service = self._service(provider=provider)

        self.assertEqual("setup_required", service.status()["reason"])
        status = service.test_backend(
            "api",
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )

        self.assertTrue(status["ready"])
        self.assertEqual("gemini", status["api"]["provider"])
        self.assertEqual("gemini-3.6-flash", status["api"]["model_id"])
        self.assertEqual(1, provider.calls)
        self.assertIs(provider, service.provider_for_generation())
        self.assertEqual(
            ("fingerprint", "api", "gemini", api["setup_fingerprint"]),
            self.writes[-1],
        )

    def test_default_registry_constructs_the_gemini_adapter(self) -> None:
        from am_configurator.recipe_provider import GeminiRecipeProvider

        provider = AICapabilityService._default_api_provider(
            "gemini",
            "gemini-private",
            "gemini-3.6-flash",
        )

        self.assertIsInstance(provider, GeminiRecipeProvider)

    def test_kimi_setup_and_generation_share_one_registry_identity(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "moonshot"
        api = self._selected_api()
        api.update(
            {
                "model_id": "kimi-k3",
                "disclosure_version": ai_catalog.provider_disclosure_version(
                    "moonshot"
                ),
                "disclosure_at": "2026-07-27T12:00:00+00:00",
            }
        )
        self.credential = "moonshot-private"
        provider = _Provider()
        service = self._service(provider=provider)

        self.assertEqual("setup_required", service.status()["reason"])
        status = service.test_backend(
            "api",
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )

        self.assertTrue(status["ready"])
        self.assertEqual("moonshot", status["api"]["provider"])
        self.assertEqual("kimi-k3", status["api"]["model_id"])
        self.assertEqual(1, provider.calls)
        self.assertIs(provider, service.provider_for_generation())
        self.assertEqual(
            ("fingerprint", "api", "moonshot", api["setup_fingerprint"]),
            self.writes[-1],
        )

    def test_default_registry_constructs_the_kimi_adapter(self) -> None:
        from am_configurator.recipe_provider import KimiRecipeProvider

        provider = AICapabilityService._default_api_provider(
            "moonshot",
            "moonshot-private",
            "kimi-k3",
        )

        self.assertIsInstance(provider, KimiRecipeProvider)

    def test_deepseek_setup_and_generation_share_one_registry_identity(self) -> None:
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        self.settings["ai"]["api"]["selected_provider"] = "deepseek"
        api = self._selected_api()
        api.update(
            {
                "model_id": "deepseek-v4-pro",
                "disclosure_version": ai_catalog.provider_disclosure_version(
                    "deepseek"
                ),
                "disclosure_at": "2026-07-27T12:00:00+00:00",
            }
        )
        self.credential = "deepseek-private"
        provider = _Provider()
        service = self._service(provider=provider)

        self.assertEqual("setup_required", service.status()["reason"])
        status = service.test_backend(
            "api",
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )

        self.assertTrue(status["ready"])
        self.assertEqual("deepseek", status["api"]["provider"])
        self.assertEqual("deepseek-v4-pro", status["api"]["model_id"])
        self.assertEqual(1, provider.calls)
        self.assertIs(provider, service.provider_for_generation())
        self.assertEqual(
            ("fingerprint", "api", "deepseek", api["setup_fingerprint"]),
            self.writes[-1],
        )

    def test_default_registry_constructs_the_deepseek_adapter(self) -> None:
        from am_configurator.recipe_provider import DeepSeekRecipeProvider

        provider = AICapabilityService._default_api_provider(
            "deepseek",
            "deepseek-private",
            "deepseek-v4-pro",
        )

        self.assertIsInstance(provider, DeepSeekRecipeProvider)

    def test_capability_polling_has_no_managed_model_or_runtime_path(self) -> None:
        source = inspect.getsource(ai_capability)
        for forbidden in (
            ".gguf",
            "local_ai_runtime",
            "from .local_model",
            "import local_model",
            "runtime_resolver",
            "verify_runtime_attestation",
            "model_path",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())

    def test_readiness_reasons_are_exact_and_invocation_fails_closed(self) -> None:
        self.settings["ai"]["enabled"] = True
        self.settings["ai"]["backend"] = None
        service = self._service()
        self.assertEqual("backend_unselected", service.status()["reason"])

        self.settings["ai"]["backend"] = "ollama"
        self.assertEqual(
            "model_missing",
            self._service(ollama_available=False).status()["reason"],
        )
        self.assertEqual("model_missing", service.status()["reason"])
        with self.assertRaises(AICapabilityError) as captured:
            service.require_ready()
        self.assertEqual("model_missing", captured.exception.reason)

        upgrade = self._service(ollama_error="upgrade_required")
        upgrade_status = upgrade.status()
        self.assertEqual("model_missing", upgrade_status["reason"])
        self.assertFalse(upgrade_status["ollama"]["service_available"])
        self.assertFalse(upgrade_status["ready"])
        with self.assertRaises(AICapabilityError) as captured:
            upgrade.require_ready()
        self.assertEqual("model_missing", captured.exception.reason)
        self.assertEqual(
            {
                "available": True,
                "models": [],
                "reason": "upgrade_required",
            },
            upgrade.discover_ollama_models(),
        )
        self.assertEqual(
            {"available": True, "models": []},
            service.discover_ollama_models(),
        )

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
        api = self._selected_api()
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

    def test_ollama_disclosure_binds_non_loopback_and_cloud_execution(self) -> None:
        disclosure_at = "2026-07-29T20:00:00+00:00"
        local = ollama_setup_fingerprint(
            "http://127.0.0.1:11434",
            self.ollama_model.model_id,
            self.ollama_model.digest,
            "ollama_server",
            None,
            None,
        )
        remote = ollama_setup_fingerprint(
            "http://ollama.lan:11434",
            self.ollama_model.model_id,
            self.ollama_model.digest,
            "ollama_server",
            store.OLLAMA_DISCLOSURE_VERSION,
            disclosure_at,
        )
        cloud = ollama_setup_fingerprint(
            "http://127.0.0.1:11434",
            self.ollama_model.model_id,
            self.ollama_model.digest,
            "ollama_cloud",
            store.OLLAMA_DISCLOSURE_VERSION,
            disclosure_at,
        )
        self.assertEqual(3, len({local, remote, cloud}))
        with self.assertRaisesRegex(ValueError, "disclosure"):
            ollama_setup_fingerprint(
                "http://ollama.lan:11434",
                self.ollama_model.model_id,
                self.ollama_model.digest,
                "ollama_server",
                None,
                None,
            )

        ollama = self.settings["ai"]["ollama"]
        ollama.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": "ollama_cloud",
        })
        self.settings["ai"].update({"enabled": True, "backend": "ollama"})
        service = self._service()
        blocked = service.status()
        self.assertEqual("disclosure_required", blocked["reason"])
        self.assertTrue(blocked["ollama"]["disclosure_required"])
        self.assertFalse(blocked["ollama"]["disclosure_current"])
        self.assertEqual(0, self.last_ollama_client.calls)

        ollama.update({
            "disclosure_version": store.OLLAMA_DISCLOSURE_VERSION,
            "disclosure_at": disclosure_at,
            "setup_fingerprint": cloud,
        })
        ready = service.status()
        self.assertTrue(ready["ready"])
        self.assertTrue(ready["ollama"]["disclosure_current"])
        self.assertEqual("ollama_cloud", ready["ollama"]["model_location"])
        self.assertEqual(0, self.last_ollama_client.calls)

    def test_ollama_setup_uses_installed_name_and_digest(self) -> None:
        provider = _Provider()
        self.ollama_models = [self.ollama_model]
        self.settings["ai"]["backend"] = "ollama"
        self.settings["ai"]["ollama"].update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
        })
        self.settings["ai"]["enabled"] = True
        service = self._service(provider=provider)

        status = service.test_backend(
            "ollama", deadline=time.monotonic() + 10, cancelled=lambda: False
        )

        self.assertEqual(1, provider.calls)
        self.assertEqual(1, self.last_ollama_client.calls)
        self.assertTrue(status["ready"])
        self.assertEqual("ollama", status["ollama"]["provider"])
        self.assertEqual("ornith:latest", status["ollama"]["model_id"])
        self.assertEqual(
            ollama_setup_fingerprint(
                self.settings["ai"]["ollama"]["base_url"],
                "ornith:latest",
                "c" * 64,
                "ollama_server",
                None,
                None,
            ),
            self.settings["ai"]["ollama"]["setup_fingerprint"],
        )

        self.ollama_models.clear()
        self.assertEqual("ready", service.status()["reason"])
        with self.assertRaises(llm.ProviderError) as missing:
            service.test_backend(
                "ollama",
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("config", missing.exception.code)

    def test_inventory_identity_change_is_detected_only_by_explicit_setup_test(self) -> None:
        provider = _Provider()
        self.ollama_models = [self.ollama_model]
        old_fingerprint = ollama_setup_fingerprint(
            self.settings["ai"]["ollama"]["base_url"],
            self.ollama_model.model_id,
            self.ollama_model.digest,
            self.ollama_model.location,
            None,
            None,
        )
        ollama = self.settings["ai"]["ollama"]
        ollama.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
            "setup_fingerprint": old_fingerprint,
        })
        self.settings["ai"].update({"enabled": True, "backend": "ollama"})
        service = self._service(provider=provider)
        self.assertTrue(service.status()["ready"])

        replacement = OllamaModel(
            model_id=self.ollama_model.model_id,
            digest="d" * 64,
            size_bytes=self.ollama_model.size_bytes,
            parameter_size=self.ollama_model.parameter_size,
            quantization=self.ollama_model.quantization,
        )
        self.ollama_models[:] = [replacement]
        replaced = service.status()
        self.assertTrue(replaced["ready"])
        self.assertEqual("ready", replaced["reason"])
        self.assertTrue(replaced["ollama"]["model_verified"])
        self.assertTrue(replaced["ollama"]["setup_tested"])
        with self.assertRaises(llm.ProviderError) as changed:
            service.test_backend(
                "ollama",
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("config", changed.exception.code)

        ollama.update({
            "model_digest": replacement.digest,
            "setup_fingerprint": None,
        })
        selected = service.status()
        self.assertFalse(selected["ready"])
        self.assertEqual("setup_required", selected["reason"])
        self.assertTrue(selected["ollama"]["model_verified"])
        self.assertFalse(selected["ollama"]["setup_tested"])
        with self.assertRaises(AICapabilityError) as blocked:
            service.require_ready()
        self.assertEqual("setup_required", blocked.exception.reason)

        tested = service.test_backend(
            "ollama", deadline=time.monotonic() + 10, cancelled=lambda: False
        )
        new_fingerprint = ollama_setup_fingerprint(
            self.settings["ai"]["ollama"]["base_url"],
            replacement.model_id,
            replacement.digest,
            replacement.location,
            None,
            None,
        )
        self.assertEqual(1, provider.calls)
        self.assertNotEqual(old_fingerprint, new_fingerprint)
        self.assertEqual(new_fingerprint, ollama["setup_fingerprint"])
        self.assertTrue(tested["ready"])
        self.assertEqual("ready", tested["reason"])
        self.assertTrue(tested["ollama"]["setup_tested"])

    def test_setup_requires_master_switch_and_never_changes_its_intent(self) -> None:
        self.ollama_models = [self.ollama_model]
        ollama = self.settings["ai"]["ollama"]
        ollama.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
        })
        self.settings["ai"]["backend"] = "ollama"
        provider = _Provider()
        service = self._service(provider=provider)

        with self.assertRaises(AICapabilityError) as blocked:
            service.test_backend(
                "ollama", deadline=time.monotonic() + 10, cancelled=lambda: False
            )
        self.assertEqual("disabled", blocked.exception.reason)
        self.assertEqual(0, provider.calls)
        self.assertIsNone(ollama["setup_fingerprint"])

        self.settings["ai"]["enabled"] = True
        status = service.test_backend(
            "ollama", deadline=time.monotonic() + 10, cancelled=lambda: False
        )
        self.assertTrue(status["enabled"])
        self.assertTrue(status["ready"])
        self.assertEqual(1, provider.calls)

    def test_generation_failure_does_not_invalidate_a_ready_ollama_model(self) -> None:
        failure = _FailingProvider("bad_response")
        self.ollama_models = [self.ollama_model]
        self.settings["ai"].update({"enabled": True, "backend": "ollama"})
        self.settings["ai"]["ollama"].update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
            "setup_fingerprint": ollama_setup_fingerprint(
                self.settings["ai"]["ollama"]["base_url"],
                self.ollama_model.model_id,
                self.ollama_model.digest,
                self.ollama_model.location,
                None,
                None,
            ),
        })
        service = self._service(provider=failure)

        provider = service.provider_for_generation()
        self.assertEqual(0, self.last_ollama_client.calls)
        with self.assertRaises(llm.ProviderError):
            provider.generate(None, time.monotonic() + 10, lambda: False)

        self.assertEqual(1, failure.calls)
        self.assertEqual(0, self.last_ollama_client.calls)
        self.assertTrue(service.status()["ready"])
        self.assertEqual("ready", service.status()["reason"])

    def test_api_auth_failure_invalidates_setup_without_exposing_the_key(self) -> None:
        failure = _FailingProvider("auth")
        self.credential = "sk-private-auth"
        self.settings["ai"].update({"enabled": True, "backend": "api"})
        api = self._selected_api()
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
            service.test_backend(
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
        api = self._selected_api()
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
            service.test_backend(
                "api", deadline=time.monotonic() + 10, cancelled=lambda: False
            )

        self.assertEqual(fingerprint, api["setup_fingerprint"])
        self.assertTrue(service.status()["ready"])
        self.assertEqual("api", self.settings["ai"]["backend"])

    def test_provider_construction_is_singleton_per_backend_identity(self) -> None:
        self.ollama_models = [self.ollama_model]
        self.settings["ai"].update({"enabled": True, "backend": "ollama"})
        ollama = self.settings["ai"]["ollama"]
        ollama.update({
            "model_id": self.ollama_model.model_id,
            "model_digest": self.ollama_model.digest,
            "model_location": self.ollama_model.location,
            "setup_fingerprint": ollama_setup_fingerprint(
                ollama["base_url"],
                self.ollama_model.model_id,
                self.ollama_model.digest,
                self.ollama_model.location,
                None,
                None,
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

        def api_factory(_provider, _credential, _model_id):
            provider = object()
            api_created.append(provider)
            return provider

        service = AICapabilityService(
            settings_loader=lambda: copy.deepcopy(self.settings),
            credential_status_loader=lambda _provider: {
                "available": True,
                "configured": self.credential is not None,
                "external": False,
                "invalid": False,
            },
            credential_resolver=lambda _provider: self.credential,
            fingerprint_writer=lambda *_args, **_kwargs: None,
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
        api = self._selected_api()
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
