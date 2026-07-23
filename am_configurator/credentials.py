"""Fail-closed operating-system credential storage for AI providers."""

from __future__ import annotations

import sys
from threading import Lock
from typing import Any, Protocol


SERVICE_IDENTIFIER = "dev.amconfigurator.ai"
XAI_USERNAME = "xai"
MAX_CREDENTIAL_CHARS = 4096
_PROVIDER_USERNAMES = {"xai": XAI_USERNAME}


class CredentialStoreError(RuntimeError):
    """A credential request was invalid or no secure OS backend was usable."""


class InvalidCredentialError(CredentialStoreError):
    """A credential value failed the provider-independent storage contract."""


class CredentialStore(Protocol):
    def available(self) -> bool: ...

    def get(self, provider: str) -> str | None: ...

    def set(self, provider: str, value: str) -> None: ...

    def delete(self, provider: str) -> None: ...


def _username(provider: str) -> str:
    try:
        return _PROVIDER_USERNAMES[provider]
    except (KeyError, TypeError):
        raise CredentialStoreError("Credential provider is unsupported.") from None


def validate_credential(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_CREDENTIAL_CHARS
        or any(ord(character) < 32 for character in value)
    ):
        raise InvalidCredentialError("Credential value is invalid.")
    return value


def _platform_secure_backend_types() -> tuple[type, ...]:
    try:
        if sys.platform == "darwin":
            from keyring.backends.macOS import Keyring

            return (Keyring,)
        if sys.platform == "win32":
            from keyring.backends.Windows import WinVaultKeyring

            return (WinVaultKeyring,)
        if sys.platform.startswith("linux"):
            from keyring.backends.SecretService import Keyring

            return (Keyring,)
    except Exception:
        pass
    return ()


class KeyringCredentialStore:
    """Use only keyring's built-in OS-backed implementations.

    Null, plaintext, encrypted-file, chainer, and third-party backends are
    rejected even if keyring selected one through user configuration.
    """

    def __init__(
        self,
        *,
        backend: Any | None = None,
        secure_backend_types: tuple[type, ...] | None = None,
    ) -> None:
        self._secure_backend_types = (
            _platform_secure_backend_types()
            if secure_backend_types is None
            else secure_backend_types
        )
        if backend is None and self._secure_backend_types:
            try:
                # Instantiate the one built-in backend selected by platform.
                # Do not honor user-configured keyring backends: those may be
                # chained, third-party, or file-backed.
                backend = self._secure_backend_types[0]()
            except Exception:
                backend = None
        self._backend = backend

    def available(self) -> bool:
        if self._backend is None:
            return False
        return type(self._backend) in self._secure_backend_types

    def _require_backend(self) -> Any:
        if not self.available():
            raise CredentialStoreError("Secure credential storage is unavailable.")
        return self._backend

    def get(self, provider: str) -> str | None:
        username = _username(provider)
        backend = self._require_backend()
        try:
            value = backend.get_password(SERVICE_IDENTIFIER, username)
        except Exception:
            pass
        else:
            if value is None:
                return None
            return validate_credential(value)
        # Raise outside the handler so a backend exception containing a raw
        # credential cannot remain attached as exception context.
        raise CredentialStoreError("Secure credential storage is unavailable.")

    def set(self, provider: str, value: str) -> None:
        username = _username(provider)
        normalized = validate_credential(value)
        backend = self._require_backend()
        try:
            backend.set_password(SERVICE_IDENTIFIER, username, normalized)
        except Exception:
            pass
        else:
            return
        raise CredentialStoreError("Secure credential storage is unavailable.")

    def delete(self, provider: str) -> None:
        username = _username(provider)
        backend = self._require_backend()
        try:
            if backend.get_password(SERVICE_IDENTIFIER, username) is None:
                return
            backend.delete_password(SERVICE_IDENTIFIER, username)
        except Exception:
            pass
        else:
            return
        raise CredentialStoreError("Secure credential storage is unavailable.")


class MemoryCredentialStore:
    """Explicit in-process test double; never selected by production code."""

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self._values: dict[str, str] = {}

    def available(self) -> bool:
        return self._available

    def _require_available(self) -> None:
        if not self._available:
            raise CredentialStoreError("Secure credential storage is unavailable.")

    def get(self, provider: str) -> str | None:
        _username(provider)
        self._require_available()
        value = self._values.get(provider)
        return None if value is None else validate_credential(value)

    def set(self, provider: str, value: str) -> None:
        _username(provider)
        self._require_available()
        self._values[provider] = validate_credential(value)

    def delete(self, provider: str) -> None:
        _username(provider)
        self._require_available()
        self._values.pop(provider, None)


_default_credential_store: CredentialStore | None = None
_default_credential_store_lock = Lock()


def default_credential_store() -> CredentialStore:
    """Return the shared secure adapter without pinning failed discovery."""

    global _default_credential_store
    with _default_credential_store_lock:
        if _default_credential_store is not None:
            return _default_credential_store
        candidate = KeyringCredentialStore()
        if candidate.available():
            _default_credential_store = candidate
        return candidate


__all__ = [
    "CredentialStore",
    "CredentialStoreError",
    "InvalidCredentialError",
    "KeyringCredentialStore",
    "MAX_CREDENTIAL_CHARS",
    "MemoryCredentialStore",
    "SERVICE_IDENTIFIER",
    "XAI_USERNAME",
    "default_credential_store",
    "validate_credential",
]
