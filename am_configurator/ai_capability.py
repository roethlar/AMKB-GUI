"""The single pathless readiness gate for every optional AI entry point."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import ai_catalog, llm, procedural, store
from .local_ai_runtime import (
    GpuProbe,
    LocalRuntimeError,
    RuntimePaths,
    get_local_ai_runtime,
    probe_full_gpu_offload,
)
from .local_model import LocalModelManager, SelectedModel
from .ollama_client import OllamaClient, OllamaError, OllamaModel, valid_model_digest, valid_model_id
from .recipe_provider import (
    ManagedLocalRecipeProvider,
    OllamaRecipeProvider,
    RecipeRequest,
    XaiRecipeProvider,
)


CAPABILITY_SCHEMA_VERSION = 1
SETUP_TEST_VERSION = 1
_SETUP_PROMPT = "A balanced blue pulse that loops cleanly across the whole board."
_ALLOWED_REASONS = {
    "disabled",
    "backend_unselected",
    "gpu_unsupported",
    "runtime_unavailable",
    "ollama_unavailable",
    "model_missing",
    "model_invalid",
    "credential_store_unavailable",
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


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def local_setup_fingerprint(runtime_identity: str, model_sha256: str) -> str:
    """Bind readiness to the verified runtime, selected weights, and schema."""

    return _sha256_object({
        "kind": "local",
        "runtime_attestation_sha256": _digest(
            runtime_identity, "runtime identity"
        ),
        "model_sha256": _digest(model_sha256, "model identity"),
        "recipe_schema_version": procedural.SCHEMA_VERSION,
        "setup_test_version": SETUP_TEST_VERSION,
    })


def ollama_setup_fingerprint(model_id: str, model_digest: str) -> str:
    """Bind readiness to one installed fixed-loopback Ollama model identity."""

    if not valid_model_id(model_id) or not valid_model_digest(model_digest):
        raise ValueError("Ollama model identity is invalid")
    return _sha256_object({
        "kind": "ollama-loopback-v1",
        "model_id": model_id,
        "model_digest": model_digest,
        "recipe_schema_version": procedural.SCHEMA_VERSION,
        "setup_test_version": SETUP_TEST_VERSION,
    })


def api_setup_fingerprint(
    provider: str,
    model_id: str,
    credential: str,
    disclosure_version: str,
    disclosure_at: str,
) -> str:
    """Bind readiness to the API configuration without retaining the key."""

    if provider != "xai" or model_id != "grok-4.5":
        raise ValueError("API provider or model is invalid")
    if not isinstance(credential, str) or not credential:
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
        "model_id": model_id,
        "credential_identity_sha256": credential_identity,
        "recipe_schema_version": procedural.SCHEMA_VERSION,
        "disclosure_version": disclosure_version,
        "disclosure_at": disclosure_at,
        "setup_test_version": SETUP_TEST_VERSION,
    })


def host_gpu_capability() -> tuple[bool, str | None]:
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return True, "metal"
    if sys.platform in {"win32", "linux"} and machine in {"amd64", "x86_64"}:
        return True, "vulkan"
    return False, None


def runtime_identity(runtime: RuntimePaths) -> str:
    """Hash the already-verified, bounded runtime attestation."""

    attestation = runtime.server.parent / "llama-runtime.json"
    try:
        if attestation.is_symlink():
            raise OSError
        raw = attestation.read_bytes()
    except OSError:
        raise LocalRuntimeError("Local runtime identity is unavailable.") from None
    if not raw or len(raw) > 64 * 1024:
        raise LocalRuntimeError("Local runtime identity is invalid.")
    return hashlib.sha256(raw).hexdigest()


def _safe_filename(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or Path(value).name != value
        or any(ord(character) < 32 for character in value)
    ):
        return None
    return value


class AICapabilityService:
    """Compute and enforce the sole AI readiness decision."""

    def __init__(
        self,
        *,
        settings_loader=None,
        model_manager: LocalModelManager | None = None,
        runtime_resolver=None,
        runtime_identity_loader=None,
        host_capability=None,
        credential_status_loader=None,
        credential_resolver=None,
        fingerprint_writer=None,
        ai_settings_writer=None,
        gpu_probe=None,
        local_provider_factory=None,
        api_provider_factory=None,
        ollama_client: OllamaClient | None = None,
        ollama_provider_factory=None,
    ) -> None:
        self._settings_loader = store.load_settings if settings_loader is None else settings_loader
        self._model_manager = LocalModelManager() if model_manager is None else model_manager
        self._runtime_resolver = (
            get_local_ai_runtime if runtime_resolver is None else runtime_resolver
        )
        self._runtime_identity_loader = (
            runtime_identity if runtime_identity_loader is None else runtime_identity_loader
        )
        self._host_capability = (
            host_gpu_capability if host_capability is None else host_capability
        )
        self._credential_status_loader = (
            store.credential_status
            if credential_status_loader is None
            else credential_status_loader
        )
        self._credential_resolver = (
            store.resolve_xai_key if credential_resolver is None else credential_resolver
        )
        self._fingerprint_writer = (
            store.set_ai_setup_fingerprint
            if fingerprint_writer is None
            else fingerprint_writer
        )
        self._ai_settings_writer = (
            store.update_ai_settings if ai_settings_writer is None else ai_settings_writer
        )
        self._gpu_probe = probe_full_gpu_offload if gpu_probe is None else gpu_probe
        self._local_provider_factory = (
            self._default_local_provider
            if local_provider_factory is None
            else local_provider_factory
        )
        self._api_provider_factory = (
            self._default_api_provider
            if api_provider_factory is None
            else api_provider_factory
        )
        self._ollama_client = OllamaClient() if ollama_client is None else ollama_client
        self._ollama_provider_factory = (
            self._default_ollama_provider
            if ollama_provider_factory is None
            else ollama_provider_factory
        )
        self._local_provider_instance = None
        self._failure_reasons: dict[str, tuple[str, str]] = {}

    def _default_local_provider(self):
        return ManagedLocalRecipeProvider(
            model_manager=self._model_manager,
            runtime_resolver=self._runtime_resolver,
        )

    @staticmethod
    def _default_api_provider(key: str, model_id: str):
        return XaiRecipeProvider(key, model_id=model_id)

    def _default_ollama_provider(self, model: OllamaModel):
        return OllamaRecipeProvider(model, client=self._ollama_client)

    def _managed_local_provider(self):
        if self._local_provider_instance is None:
            self._local_provider_instance = self._local_provider_factory()
        return self._local_provider_instance

    def _gguf_components(self) -> dict[str, Any]:
        try:
            supported, gpu_backend = self._host_capability()
        except Exception:
            supported, gpu_backend = False, None
        supported = type(supported) is bool and supported
        if gpu_backend not in {"metal", "vulkan", "cuda", "gpu"}:
            gpu_backend = None
        runtime = None
        runtime_hash = None
        if supported:
            try:
                runtime = self._runtime_resolver()
                runtime_hash = self._runtime_identity_loader(runtime)
                _digest(runtime_hash, "runtime identity")
            except Exception:
                runtime = None
                runtime_hash = None
        try:
            model_status = self._model_manager.status()
        except Exception:
            model_status = {
                "selected": True,
                "filename": None,
                "verified": False,
                "reason": "model_invalid",
            }
        selected = model_status.get("selected") is True
        verified = model_status.get("verified") is True
        filename = _safe_filename(model_status.get("filename")) if verified else None
        model = None
        if verified and filename is not None:
            try:
                model = self._model_manager.resolve_selected()
            except Exception:
                model = None
                verified = False
                filename = None
        expected = None
        if runtime_hash is not None and model is not None and verified:
            try:
                expected = local_setup_fingerprint(runtime_hash, model.sha256)
            except ValueError:
                expected = None
        return {
            "supported": supported,
            "gpu_backend": gpu_backend if supported else None,
            "runtime": runtime,
            "runtime_hash": runtime_hash,
            "runtime_verified": runtime is not None,
            "selected": selected,
            "filename": filename,
            "verified": verified and filename is not None,
            "model": model,
            "expected": expected,
        }

    def discover_local_models(self) -> dict[str, Any]:
        """Return a bounded public list of eligible fixed-loopback models."""

        try:
            models = self._ollama_client.list_models(deadline=time.monotonic() + 5.0)
        except (OllamaError, OSError, RuntimeError):
            return {"available": False, "models": []}
        if not isinstance(models, tuple) or any(
            not isinstance(model, OllamaModel) for model in models
        ):
            return {"available": False, "models": []}
        return {
            "available": True,
            "models": [model.public() for model in models],
        }

    def _ollama_components(self, settings: dict[str, Any]) -> dict[str, Any]:
        local = settings["ai"]["local"]
        selected_id = local["model_id"]
        selected_digest = local["model_digest"]
        try:
            models = self._ollama_client.list_models(deadline=time.monotonic() + 5.0)
            if not isinstance(models, tuple) or any(
                not isinstance(model, OllamaModel) for model in models
            ):
                raise OllamaError("bad_response", "Invalid local model list.")
            available = True
        except (OllamaError, OSError, RuntimeError):
            models = ()
            available = False
        model = next(
            (
                candidate
                for candidate in models
                if candidate.model_id == selected_id
                and candidate.digest == selected_digest
            ),
            None,
        )
        expected = None
        if model is not None:
            try:
                expected = ollama_setup_fingerprint(model.model_id, model.digest)
            except ValueError:
                expected = None
        return {
            "available": available,
            "selected": selected_id is not None and selected_digest is not None,
            "model_id": selected_id,
            "model": model,
            "verified": model is not None,
            "expected": expected,
        }

    def _local_components(self, settings: dict[str, Any]) -> dict[str, Any]:
        source = settings["ai"]["local"]["source"]
        gguf = self._gguf_components()
        if source == "ollama":
            ollama = self._ollama_components(settings)
            return {
                "source": source,
                "service_available": ollama["available"],
                "selected": ollama["selected"],
                "model_id": ollama["model_id"],
                "verified": ollama["verified"],
                "model": ollama["model"],
                "expected": ollama["expected"],
                "provider": "ollama",
                "gguf": gguf,
            }
        return {
            "source": "gguf",
            "service_available": None,
            "selected": gguf["selected"],
            "model_id": gguf["filename"],
            "verified": gguf["verified"],
            "model": gguf["model"],
            "expected": gguf["expected"],
            "provider": "llama.cpp",
            "gguf": gguf,
        }

    def _api_components(self, settings: dict[str, Any]) -> dict[str, Any]:
        api = settings["ai"]["api"]
        try:
            status = self._credential_status_loader()
        except Exception:
            status = {}
        available = status.get("available") is True
        configured = status.get("configured") is True
        external = status.get("external") is True
        disclosure_current = (
            api["disclosure_version"] == ai_catalog.PRIVACY_DISCLOSURE_VERSION
            and isinstance(api["disclosure_at"], str)
            and bool(api["disclosure_at"])
        )
        credential = None
        if configured and (available or external):
            try:
                credential = self._credential_resolver()
            except Exception:
                credential = None
        expected = None
        if credential and disclosure_current:
            try:
                expected = api_setup_fingerprint(
                    api["provider"],
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
            "credential": credential,
            "disclosure_current": disclosure_current,
            "expected": expected,
        }

    def _remembered_reason(self, backend: str, component: str | None) -> str | None:
        remembered = self._failure_reasons.get(backend)
        if remembered is None or component is None or remembered[1] != component:
            return None
        return remembered[0]

    def status(self) -> dict[str, Any]:
        try:
            settings = self._settings_loader()
            local = self._local_components(settings)
            api = self._api_components(settings)
            enabled = settings["ai"]["enabled"] is True
            backend = settings["ai"]["backend"]
            local_tested = (
                local["expected"] is not None
                and settings["ai"]["local"]["setup_fingerprint"] == local["expected"]
            )
            api_tested = (
                api["expected"] is not None
                and settings["ai"]["api"]["setup_fingerprint"] == api["expected"]
            )

            ready = False
            if not enabled:
                reason = "disabled"
            elif backend is None:
                reason = "backend_unselected"
            elif backend == "local":
                if local["source"] == "ollama" and not local["service_available"]:
                    reason = "ollama_unavailable"
                elif local["source"] == "gguf" and not local["gguf"]["supported"]:
                    reason = "gpu_unsupported"
                elif local["source"] == "gguf" and not local["gguf"]["runtime_verified"]:
                    reason = "runtime_unavailable"
                elif not local["selected"]:
                    reason = "model_missing"
                elif not local["verified"]:
                    reason = "model_unavailable" if local["source"] == "ollama" else "model_invalid"
                else:
                    reason = self._remembered_reason("local", local["expected"])
                    if reason is None and not local_tested:
                        reason = "setup_required"
                    elif reason is None:
                        reason = "ready"
                        ready = True
            elif backend == "api":
                if not api["available"] and not api["external"]:
                    reason = "credential_store_unavailable"
                elif not api["configured"]:
                    reason = "credential_missing"
                elif not api["disclosure_current"]:
                    reason = "disclosure_required"
                else:
                    reason = self._remembered_reason("api", api["expected"])
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
                "backend": backend if backend in {None, "local", "api"} else None,
                "ready": ready,
                "reason": reason,
                "local": {
                    "source": local["source"],
                    "service_available": local["service_available"],
                    "model_selected": local["selected"],
                    "model_id": local["model_id"],
                    "model_verified": local["verified"],
                    "setup_tested": local_tested,
                    "provider": local["provider"],
                    "advanced": {
                        "supported": local["gguf"]["supported"],
                        "gpu_backend": local["gguf"]["gpu_backend"],
                        "runtime_verified": local["gguf"]["runtime_verified"],
                        "model_selected": local["gguf"]["selected"],
                        "model_filename": local["gguf"]["filename"],
                        "model_verified": local["gguf"]["verified"],
                    },
                },
                "api": {
                    "provider": settings["ai"]["api"]["provider"],
                    "model_id": settings["ai"]["api"]["model_id"],
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
                "local": {
                    "source": "ollama",
                    "service_available": False,
                    "model_selected": False,
                    "model_id": None,
                    "model_verified": False,
                    "setup_tested": False,
                    "provider": "ollama",
                    "advanced": {
                        "supported": False,
                        "gpu_backend": None,
                        "runtime_verified": False,
                        "model_selected": False,
                        "model_filename": None,
                        "model_verified": False,
                    },
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
        if status["backend"] == "local":
            settings = self._settings_loader()
            components = self._local_components(settings)
            if components["source"] == "ollama":
                model = components["model"]
                if not isinstance(model, OllamaModel):
                    raise AICapabilityError("model_unavailable")
                return self._ollama_provider_factory(model)
            return self._managed_local_provider()
        settings = self._settings_loader()
        components = self._api_components(settings)
        credential = components["credential"]
        if credential is None:
            raise AICapabilityError("credential_missing")
        return self._api_provider_factory(
            credential,
            settings["ai"]["api"]["model_id"],
        )

    def test_and_enable(
        self,
        backend: str,
        *,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        if backend not in {"local", "api"}:
            raise ValueError("AI backend must be local or api")
        settings = self._settings_loader()
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

        if backend == "local":
            components = self._local_components(settings)
            fingerprint = components["expected"]
            model = components["model"]
            if fingerprint is None or model is None:
                raise llm.ProviderError("config", "The selected local model is unavailable.")
            if components["source"] == "ollama":
                provider = self._ollama_provider_factory(model)
            else:
                gguf = components["gguf"]
                if not gguf["supported"]:
                    raise llm.ProviderError("config", "Local GPU support is unavailable.")
                runtime = gguf["runtime"]
                if runtime is None:
                    raise llm.ProviderError(
                        "config", "Verified local inference components are unavailable."
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise llm.ProviderError("timeout", "Local setup test timed out.")
                try:
                    probe = self._gpu_probe(
                        runtime,
                        model,
                        timeout_seconds=min(180.0, remaining),
                    )
                except Exception:
                    probe = None
                if (
                    not isinstance(probe, GpuProbe)
                    or probe.total_layers < 1
                    or probe.offloaded_layers != probe.total_layers
                ):
                    self._failure_reasons["local"] = ("setup_required", fingerprint)
                    raise llm.ProviderError("config", "Full local GPU offload failed.")
                provider = self._managed_local_provider()
        else:
            components = self._api_components(settings)
            api = settings["ai"]["api"]
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
            provider = self._api_provider_factory(
                components["credential"], api["model_id"]
            )

        try:
            provider.generate(request, deadline, cancelled)
        except llm.ProviderError as error:
            if backend == "api" and error.code in {"auth", "config"}:
                reason = "auth_invalid" if error.code == "auth" else "model_unavailable"
                self._failure_reasons[backend] = (reason, fingerprint)
                self._fingerprint_writer(backend, None)
            elif error.code not in {"offline", "timeout", "rate_limited", "unavailable"}:
                self._failure_reasons[backend] = ("setup_required", fingerprint)
            raise

        self._fingerprint_writer(backend, fingerprint)
        self._failure_reasons.pop(backend, None)
        self._ai_settings_writer(
            {"enabled": True, "backend": backend},
            ready=True,
        )
        return self.status()

    def close(self) -> None:
        provider = self._local_provider_instance
        self._local_provider_instance = None
        close = getattr(provider, "close", None)
        if callable(close):
            close()


__all__ = [
    "AICapabilityError",
    "AICapabilityService",
    "CAPABILITY_SCHEMA_VERSION",
    "SETUP_TEST_VERSION",
    "api_setup_fingerprint",
    "host_gpu_capability",
    "local_setup_fingerprint",
    "ollama_setup_fingerprint",
    "runtime_identity",
]
