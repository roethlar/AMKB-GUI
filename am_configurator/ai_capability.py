"""The single pathless readiness gate for every optional AI entry point."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Callable

from . import ai_catalog, credentials, llm, procedural, store
from .ollama_client import (
    DEFAULT_OLLAMA_BASE_URL,
    OllamaClient,
    OllamaError,
    OllamaModel,
    normalize_ollama_base_url,
    ollama_origin_is_loopback,
    valid_model_digest,
    valid_model_id,
)
from .recipe_provider import (
    AnthropicRecipeProvider,
    DeepSeekRecipeProvider,
    GeminiRecipeProvider,
    KimiRecipeProvider,
    OllamaRecipeProvider,
    OpenAIRecipeProvider,
    RecipeRequest,
    XaiRecipeProvider,
)


CAPABILITY_SCHEMA_VERSION = 1
SETUP_TEST_VERSION = 1
_SETUP_PROMPT = "A balanced blue pulse that loops cleanly across the whole board."
_ALLOWED_REASONS = {
    "disabled",
    "backend_unselected",
    "ollama_unavailable",
    "upgrade_required",
    "model_missing",
    "credential_store_unavailable",
    "credential_invalid",
    "credential_missing",
    "disclosure_required",
    "setup_required",
    "auth_invalid",
    "model_unavailable",
    "ready",
}


class AICapabilityError(RuntimeError):
    """AI is unavailable for one stable, pathless capability reason."""

    def __init__(self, reason: str) -> None:
        normalized = reason if reason in _ALLOWED_REASONS else "setup_required"
        super().__init__(normalized)
        self.reason = normalized


def _sha256_object(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def ollama_setup_fingerprint(
    base_url: str,
    model_id: str,
    model_digest: str,
    model_location: str,
    disclosure_version: str | None,
    disclosure_at: str | None,
) -> str:
    """Bind readiness to one Ollama origin, execution location, and disclosure."""

    if not valid_model_id(model_id) or not valid_model_digest(model_digest):
        raise ValueError("Ollama model identity is invalid")
    try:
        base_url = normalize_ollama_base_url(base_url)
    except ValueError:
        raise ValueError("Ollama server URL is invalid") from None
    if model_location not in {"ollama_server", "ollama_cloud"}:
        raise ValueError("Ollama model location is invalid")
    disclosure_required = (
        not ollama_origin_is_loopback(base_url)
        or model_location == "ollama_cloud"
    )
    if disclosure_required and (
        disclosure_version != store.OLLAMA_DISCLOSURE_VERSION
        or not isinstance(disclosure_at, str)
        or not disclosure_at
    ):
        raise ValueError("Ollama disclosure is not current")
    payload = {
        "kind": "ollama-origin-v2",
        "base_url": base_url,
        "model_id": model_id,
        "model_digest": model_digest,
        "model_location": model_location,
        "recipe_schema_version": procedural.SCHEMA_VERSION,
        "setup_test_version": SETUP_TEST_VERSION,
    }
    if disclosure_required:
        payload["disclosure_version"] = disclosure_version
        payload["disclosure_at"] = disclosure_at
    return _sha256_object(payload)


def api_setup_fingerprint(
    provider: str,
    model_id: str,
    credential: str,
    disclosure_version: str,
    disclosure_at: str,
) -> str:
    """Bind readiness to the API configuration without retaining the key."""

    try:
        provider = ai_catalog.validate_api_provider(provider)
        normalized_model = ai_catalog.validate_provider_model(provider, model_id)
    except ValueError:
        raise ValueError("API provider or model is invalid")
    try:
        credential = credentials.validate_credential(credential)
    except credentials.InvalidCredentialError:
        raise ValueError("API credential is invalid")
    if not isinstance(disclosure_version, str) or not disclosure_version:
        raise ValueError("API disclosure is invalid")
    if not isinstance(disclosure_at, str) or not disclosure_at:
        raise ValueError("API disclosure timestamp is invalid")
    credential_identity = hashlib.sha256(
        b"am-configurator-api-credential-v1\0" + credential.encode("utf-8")
    ).hexdigest()
    return _sha256_object({
        "kind": "api",
        "provider": provider,
        "model_id": normalized_model,
        "credential_identity_sha256": credential_identity,
        "recipe_schema_version": procedural.SCHEMA_VERSION,
        "disclosure_version": disclosure_version,
        "disclosure_at": disclosure_at,
        "setup_test_version": SETUP_TEST_VERSION,
    })


class AICapabilityService:
    """Compute and enforce the sole AI readiness decision."""

    def __init__(
        self,
        *,
        settings_loader=None,
        credential_status_loader=None,
        credential_resolver=None,
        fingerprint_writer=None,
        api_provider_factory=None,
        ollama_client: OllamaClient | None = None,
        ollama_provider_factory=None,
    ) -> None:
        self._settings_loader = store.load_settings if settings_loader is None else settings_loader
        self._credential_status_loader = (
            store.credential_status
            if credential_status_loader is None
            else credential_status_loader
        )
        self._credential_resolver = (
            store.resolve_api_key if credential_resolver is None else credential_resolver
        )
        self._fingerprint_writer = (
            store.set_ai_setup_fingerprint
            if fingerprint_writer is None
            else fingerprint_writer
        )
        self._api_provider_factory = (
            self._default_api_provider
            if api_provider_factory is None
            else api_provider_factory
        )
        self._injected_ollama_client = ollama_client
        self._ollama_clients: dict[str, OllamaClient] = {}
        self._ollama_provider_factory = ollama_provider_factory
        self._provider_lock = threading.Lock()
        self._providers: dict[str, tuple[str, object]] = {}
        self._failure_reasons: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _default_api_provider(provider: str, key: str, model_id: str):
        if provider == "xai":
            return XaiRecipeProvider(key, model_id=model_id)
        if provider == "anthropic":
            return AnthropicRecipeProvider(key, model_id=model_id)
        if provider == "openai":
            return OpenAIRecipeProvider(key, model_id=model_id)
        if provider == "gemini":
            return GeminiRecipeProvider(key, model_id=model_id)
        if provider == "moonshot":
            return KimiRecipeProvider(key, model_id=model_id)
        if provider == "deepseek":
            return DeepSeekRecipeProvider(key, model_id=model_id)
        raise ValueError("API provider adapter is unavailable")

    def _ollama_client_for(self, settings: dict[str, Any]) -> OllamaClient:
        if self._injected_ollama_client is not None:
            return self._injected_ollama_client
        base_url = normalize_ollama_base_url(
            settings["ai"]["ollama"]["base_url"]
        )
        with self._provider_lock:
            client = self._ollama_clients.get(base_url)
            if client is None:
                client = OllamaClient(base_url=base_url)
                self._ollama_clients = {base_url: client}
            return client

    def _new_ollama_provider(self, model: OllamaModel, client: object):
        if self._ollama_provider_factory is not None:
            return self._ollama_provider_factory(model)
        return OllamaRecipeProvider(model, client=client)

    def _provider_for_identity(
        self,
        backend: str,
        identity: str,
        factory: Callable[[], object],
    ) -> object:
        with self._provider_lock:
            existing = self._providers.get(backend)
            if existing is not None and existing[0] == identity:
                return existing[1]
            provider = factory()
            self._providers[backend] = (identity, provider)
            return provider


    def discover_ollama_models(self) -> dict[str, Any]:
        """Return a bounded public list from the configured Ollama origin."""

        try:
            settings = self._settings_loader()
            client = self._ollama_client_for(settings)
            models = client.list_models(deadline=time.monotonic() + 5.0)
        except OllamaError as exc:
            if exc.code == "upgrade_required":
                return {
                    "available": True,
                    "models": [],
                    "reason": "upgrade_required",
                }
            return {"available": False, "models": []}
        except (OSError, RuntimeError):
            return {"available": False, "models": []}
        if not isinstance(models, tuple) or any(
            not isinstance(model, OllamaModel) for model in models
        ):
            return {"available": False, "models": []}
        return {
            "available": True,
            "models": [model.public() for model in models],
        }

    def _ollama_components(
        self,
        settings: dict[str, Any],
        *,
        runtime: bool = False,
    ) -> dict[str, Any]:
        """Project stored Ollama readiness without probing the configured server."""

        ollama = settings["ai"]["ollama"]
        base_url = normalize_ollama_base_url(ollama["base_url"])
        selected_id = ollama["model_id"]
        selected_digest = ollama["model_digest"]
        selected_location = ollama["model_location"]
        selected = (
            valid_model_id(selected_id)
            and valid_model_digest(selected_digest)
            and selected_location in {"ollama_server", "ollama_cloud"}
        )
        disclosure_required = (
            not ollama_origin_is_loopback(base_url)
            or selected_location == "ollama_cloud"
        )
        disclosure_current = (
            not disclosure_required
            or (
                ollama["disclosure_version"] == store.OLLAMA_DISCLOSURE_VERSION
                and isinstance(ollama["disclosure_at"], str)
                and bool(ollama["disclosure_at"])
            )
        )
        expected = None
        model = None
        if selected and disclosure_current:
            expected = ollama_setup_fingerprint(
                base_url,
                selected_id,
                selected_digest,
                selected_location,
                ollama["disclosure_version"],
                ollama["disclosure_at"],
            )
            model = OllamaModel(
                model_id=selected_id,
                digest=selected_digest,
                size_bytes=0,
                parameter_size=None,
                quantization=None,
                location=selected_location,
            )
        setup_tested = (
            isinstance(expected, str)
            and ollama["setup_fingerprint"] == expected
        )
        return {
            "base_url": base_url,
            "service_available": setup_tested,
            "upgrade_required": False,
            "selected": selected,
            "model_id": selected_id,
            "model_digest": selected_digest,
            "model_location": selected_location,
            "verified": selected,
            "model": model,
            "client": self._ollama_client_for(settings) if runtime and selected else None,
            "expected": expected,
            "setup_tested": setup_tested,
            "disclosure_required": disclosure_required,
            "disclosure_current": disclosure_current,
            "disclosure_version": store.OLLAMA_DISCLOSURE_VERSION,
            "provider": "ollama",
        }

    def _ollama_inventory_components(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify the stored identity against one explicit inventory request."""

        stored = self._ollama_components(settings, runtime=True)
        client = stored["client"]
        if client is None:
            return {
                **stored,
                "service_available": False,
                "verified": False,
                "model": None,
            }
        try:
            models = client.list_models(deadline=time.monotonic() + 5.0)
            if not isinstance(models, tuple) or any(
                not isinstance(model, OllamaModel) for model in models
            ):
                raise OllamaError("bad_response", "Invalid Ollama model list.")
            available = True
            upgrade_required = False
        except OllamaError as exc:
            models = ()
            upgrade_required = exc.code == "upgrade_required"
            available = upgrade_required
        except (OSError, RuntimeError):
            models = ()
            available = False
            upgrade_required = False
        model = next(
            (
                candidate
                for candidate in models
                if candidate.model_id == stored["model_id"]
                and candidate.digest == stored["model_digest"]
                and candidate.location == stored["model_location"]
            ),
            None,
        )
        return {
            **stored,
            "available": available,
            "service_available": available,
            "upgrade_required": upgrade_required,
            "model": model,
            "verified": model is not None,
        }

    def _api_components(self, settings: dict[str, Any]) -> dict[str, Any]:
        api_settings = settings["ai"]["api"]
        provider = api_settings["selected_provider"]
        api = api_settings["providers"][provider]
        try:
            status = self._credential_status_loader(provider)
        except Exception:
            status = {}
        available = status.get("available") is True
        configured = status.get("configured") is True
        external = status.get("external") is True
        invalid = status.get("invalid") is True
        disclosure_current = (
            api["disclosure_version"]
            == ai_catalog.provider_disclosure_version(provider)
            and isinstance(api["disclosure_at"], str)
            and bool(api["disclosure_at"])
        )
        credential = None
        if configured and not invalid and (available or external):
            try:
                credential = self._credential_resolver(provider)
            except Exception:
                credential = None
        expected = None
        if credential and disclosure_current:
            try:
                expected = api_setup_fingerprint(
                    provider,
                    api["model_id"],
                    credential,
                    api["disclosure_version"],
                    api["disclosure_at"],
                )
            except ValueError:
                expected = None
        return {
            "available": available,
            "configured": configured and credential is not None,
            "external": external,
            "invalid": invalid,
            "credential": credential,
            "disclosure_current": disclosure_current,
            "expected": expected,
            "provider": provider,
            "model_id": api["model_id"],
            "setup_fingerprint": api["setup_fingerprint"],
        }

    @staticmethod
    def _unprobed_api_components(settings: dict[str, Any]) -> dict[str, Any]:
        api_settings = settings["ai"]["api"]
        provider = api_settings["selected_provider"]
        api = api_settings["providers"][provider]
        disclosure_current = (
            api["disclosure_version"]
            == ai_catalog.provider_disclosure_version(provider)
            and isinstance(api["disclosure_at"], str)
            and bool(api["disclosure_at"])
        )
        return {
            "available": False,
            "configured": False,
            "external": False,
            "invalid": False,
            "credential": None,
            "disclosure_current": disclosure_current,
            "expected": None,
            "provider": provider,
            "model_id": api["model_id"],
            "setup_fingerprint": api["setup_fingerprint"],
        }

    def _remembered_reason(self, backend: str, component: str | None) -> str | None:
        remembered = self._failure_reasons.get(backend)
        if remembered is None or component is None or remembered[1] != component:
            return None
        return remembered[0]

    def status(self, *, probe: bool = True) -> dict[str, Any]:
        try:
            settings = self._settings_loader()
            enabled = settings["ai"]["enabled"] is True
            backend = settings["ai"]["backend"]
            ollama = self._ollama_components(settings)
            api = self._unprobed_api_components(settings)
            ollama_tested = ollama["setup_tested"]
            api_tested = False

            if probe and enabled and backend == "api":
                api = self._api_components(settings)
                api_tested = (
                    api["expected"] is not None
                    and api["setup_fingerprint"] == api["expected"]
                )

            ready = False
            if not enabled:
                reason = "disabled"
            elif backend is None:
                reason = "backend_unselected"
            elif backend == "ollama":
                if not ollama["selected"]:
                    reason = "model_missing"
                elif not ollama["disclosure_current"]:
                    reason = "disclosure_required"
                else:
                    reason = self._remembered_reason("ollama", ollama["expected"])
                    if reason is None and not ollama_tested:
                        reason = "setup_required"
                    elif reason is None:
                        reason = "ready"
                        ready = True
            elif backend == "api":
                if api["model_id"] is None:
                    reason = "model_missing"
                elif api["invalid"]:
                    reason = "credential_invalid"
                elif not api["available"] and not api["external"]:
                    reason = "credential_store_unavailable"
                elif not api["configured"]:
                    reason = "credential_missing"
                elif not api["disclosure_current"]:
                    reason = "disclosure_required"
                else:
                    reason = self._remembered_reason(
                        f"api:{api['provider']}",
                        api["expected"],
                    )
                    if reason is None and not api_tested:
                        reason = "setup_required"
                    elif reason is None:
                        reason = "ready"
                        ready = True
            else:
                reason = "setup_required"

            if reason not in _ALLOWED_REASONS:
                reason = "setup_required"
                ready = False
            return {
                "schema_version": CAPABILITY_SCHEMA_VERSION,
                "enabled": enabled,
                "backend": backend if backend in {None, "ollama", "api"} else None,
                "ready": ready,
                "reason": reason,
                "ollama": {
                    "base_url": ollama["base_url"],
                    "service_available": ollama["service_available"],
                    "model_selected": ollama["selected"],
                    "model_id": ollama["model_id"],
                    "model_digest": ollama["model_digest"],
                    "model_location": ollama["model_location"],
                    "model_verified": ollama["verified"],
                    "setup_tested": ollama_tested,
                    "disclosure_required": ollama["disclosure_required"],
                    "disclosure_current": ollama["disclosure_current"],
                    "disclosure_version": ollama["disclosure_version"],
                    "provider": ollama["provider"],
                },
                "api": {
                    "provider": api["provider"],
                    "model_id": api["model_id"],
                    "credential_set": api["configured"],
                    "disclosure_current": api["disclosure_current"],
                    "setup_tested": api_tested,
                },
            }

        except Exception:
            # The boundary stays exact and pathless even if an injected or
            # platform component violates its contract.
            return {
                "schema_version": CAPABILITY_SCHEMA_VERSION,
                "enabled": False,
                "backend": None,
                "ready": False,
                "reason": "setup_required",
                "ollama": {
                    "base_url": DEFAULT_OLLAMA_BASE_URL,
                    "service_available": False,
                    "model_selected": False,
                    "model_id": None,
                    "model_digest": None,
                    "model_location": None,
                    "model_verified": False,
                    "setup_tested": False,
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

    def require_ready(self) -> dict[str, Any]:
        """Recompute readiness at the invocation boundary and fail closed."""

        status = self.status()
        if not (status["enabled"] and status["ready"]):
            raise AICapabilityError(status["reason"])
        return status

    def provider_for_generation(self):
        """Resolve only the currently ready backend; callers supply no model."""

        status = self.require_ready()
        if status["backend"] == "ollama":
            settings = self._settings_loader()
            components = self._ollama_components(settings, runtime=True)
            model = components["model"]
            client = components["client"]
            identity = components["expected"]
            if (
                not isinstance(model, OllamaModel)
                or client is None
                or not isinstance(identity, str)
            ):
                raise AICapabilityError("model_unavailable")
            return self._provider_for_identity(
                "ollama",
                identity,
                lambda: self._new_ollama_provider(model, client),
            )
        settings = self._settings_loader()
        components = self._api_components(settings)
        credential = components["credential"]
        identity = components["expected"]
        provider_id = components["provider"]
        if credential is None or not isinstance(identity, str):
            raise AICapabilityError("credential_missing")
        return self._provider_for_identity(
            f"api:{provider_id}",
            identity,
            lambda: self._api_provider_factory(
                provider_id,
                credential,
                components["model_id"],
            ),
        )

    def test_backend(
        self,
        backend: str,
        *,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        if backend not in {"ollama", "api"}:
            raise ValueError("AI backend must be ollama or api")
        settings = self._settings_loader()
        if settings["ai"]["enabled"] is not True:
            raise AICapabilityError("disabled")
        if settings["ai"]["backend"] != backend:
            raise ValueError("Tested AI backend must match the selected backend")
        if cancelled() or deadline <= time.monotonic():
            raise llm.ProviderError("timeout", "AI setup test did not start.")
        request = RecipeRequest(
            prompt=_SETUP_PROMPT,
            width=18,
            height=7,
            frame_count=32,
            density_default="balanced",
        )

        if backend == "ollama":
            stored = self._ollama_components(settings, runtime=True)
            if not stored["selected"]:
                raise llm.ProviderError("config", "Choose an Ollama model first.")
            if not stored["disclosure_current"]:
                raise llm.ProviderError(
                    "config",
                    "The Ollama data disclosure is not current.",
                )
            components = self._ollama_inventory_components(settings)
            fingerprint = stored["expected"]
            model = components["model"]
            client = stored["client"]
            if components["upgrade_required"]:
                raise llm.ProviderError(
                    "config",
                    "Upgrade the configured Ollama server.",
                )
            if not components["service_available"]:
                raise llm.ProviderError(
                    "offline",
                    "The configured Ollama server is unavailable.",
                )
            if fingerprint is None or model is None or client is None:
                raise llm.ProviderError("config", "The selected Ollama model is unavailable.")
            provider = self._provider_for_identity(
                "ollama",
                fingerprint,
                lambda: self._new_ollama_provider(model, client),
            )
        else:
            components = self._api_components(settings)
            provider_id = components["provider"]
            fingerprint = components["expected"]
            if not components["available"] and not components["external"]:
                raise llm.ProviderError(
                    "config", "Secure credential storage is unavailable."
                )
            if components["credential"] is None:
                raise llm.ProviderError("config", "API credential is missing.")
            if not components["disclosure_current"]:
                raise llm.ProviderError("config", "API disclosure is not current.")
            if fingerprint is None:
                raise llm.ProviderError("config", "API setup is invalid.")
            provider = self._provider_for_identity(
                f"api:{provider_id}",
                fingerprint,
                lambda: self._api_provider_factory(
                    provider_id,
                    components["credential"],
                    components["model_id"],
                ),
            )

        try:
            provider.generate(request, deadline, cancelled)
        except llm.ProviderError as error:
            if backend == "api" and error.code in {"auth", "config"}:
                reason = "auth_invalid" if error.code == "auth" else "model_unavailable"
                failure_key = f"api:{components['provider']}"
                self._failure_reasons[failure_key] = (reason, fingerprint)
                self._fingerprint_writer(
                    backend,
                    None,
                    provider=components["provider"],
                )
            elif error.code not in {"offline", "timeout", "rate_limited", "unavailable"}:
                failure_key = (
                    f"api:{components['provider']}" if backend == "api" else backend
                )
                self._failure_reasons[failure_key] = ("setup_required", fingerprint)
            raise

        if backend == "api":
            failure_key = f"api:{components['provider']}"
            self._fingerprint_writer(
                backend,
                fingerprint,
                provider=components["provider"],
            )
        else:
            failure_key = backend
            self._fingerprint_writer(backend, fingerprint)
        self._failure_reasons.pop(failure_key, None)
        return self.status()

    def close(self) -> None:
        """Release cached lightweight provider references."""

        with self._provider_lock:
            self._providers.clear()
            self._ollama_clients.clear()


__all__ = [
    "AICapabilityError",
    "AICapabilityService",
    "CAPABILITY_SCHEMA_VERSION",
    "SETUP_TEST_VERSION",
    "api_setup_fingerprint",
    "ollama_setup_fingerprint",
]
