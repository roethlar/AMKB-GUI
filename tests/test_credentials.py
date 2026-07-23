from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import credentials, store


V3_DEFAULTS = {
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

V4_DEFAULTS = {
    "schema_version": 4,
    "ai": {
        "enabled": False,
        "backend": None,
        "local": {
            "source": "ollama",
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

V5_DEFAULTS = {
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


def _v2_settings(*, key: str | None = None, root: Path | None = None) -> dict:
    keys = {} if key is None else {"xai": key}
    current_root = None if root is None else str(root)
    return {
        "schema_version": 2,
        "llm": {
            "models": {
                "interpreter": "grok-4.3",
                "concept": "grok-imagine-image-quality",
                "video": "grok-imagine-video",
            },
            "keys": keys,
        },
        "library": {"current_root": current_root, "roots": []},
        "generation": {
            "candidate_count": 8,
            "loop_mode": "ping_pong",
            "privacy_ack_version": "2026-07-20-xai-v1",
            "privacy_ack_at": "2026-07-20T12:00:00+00:00",
        },
    }


class _SecureBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[tuple] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append(("get", service, username))
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.calls.append(("set", service, username, value))
        self.values[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append(("delete", service, username))
        self.values.pop((service, username), None)


_SecureBackend.__module__ = "keyring.backends.macOS"
_SecureBackend.__name__ = "Keyring"
_SecureBackend.__qualname__ = "Keyring"


class CredentialAdapterTests(unittest.TestCase):
    def test_keyring_adapter_accepts_only_os_backends_and_fixed_identifiers(self) -> None:
        backend = _SecureBackend()
        adapter = credentials.KeyringCredentialStore(
            backend=backend,
            secure_backend_types=(_SecureBackend,),
        )
        self.assertTrue(adapter.available())

        adapter.set("xai", "sk-private")
        self.assertEqual("sk-private", adapter.get("xai"))
        adapter.delete("xai")
        self.assertIsNone(adapter.get("xai"))
        self.assertTrue(
            all(
                call[1:3]
                == (credentials.SERVICE_IDENTIFIER, credentials.XAI_USERNAME)
                for call in backend.calls
            )
        )

        for module, name in (
            ("keyring.backends.null", "Keyring"),
            ("keyrings.alt.file", "PlaintextKeyring"),
            ("keyring.backends.chainer", "ChainerBackend"),
        ):
            with self.subTest(backend=f"{module}.{name}"):
                backend_type = type(name, (_SecureBackend,), {"__module__": module})
                rejected = credentials.KeyringCredentialStore(
                    backend=backend_type(),
                    secure_backend_types=(_SecureBackend,),
                )
                self.assertFalse(rejected.available())
                with self.assertRaises(credentials.CredentialStoreError):
                    rejected.set("xai", "sk-never-written")

        direct = credentials.KeyringCredentialStore(
            secure_backend_types=(_SecureBackend,)
        )
        self.assertTrue(direct.available())
        direct.set("xai", "sk-direct-os-backend")
        self.assertEqual("sk-direct-os-backend", direct.get("xai"))

    def test_keyring_adapter_severs_secret_bearing_backend_errors(self) -> None:
        secret = "sk-backend-error-secret"

        class FailingBackend(_SecureBackend):
            def set_password(self, service: str, username: str, value: str) -> None:
                raise RuntimeError(f"backend rejected {value}")

        backend = FailingBackend()
        adapter = credentials.KeyringCredentialStore(
            backend=backend,
            secure_backend_types=(FailingBackend,),
        )
        with self.assertRaises(credentials.CredentialStoreError) as captured:
            adapter.set("xai", secret)
        self.assertNotIn(secret, str(captured.exception))
        self.assertIsNone(captured.exception.__cause__)
        self.assertIsNone(captured.exception.__context__)

    def test_memory_store_is_explicit_strict_and_never_echoes_a_secret(self) -> None:
        memory = credentials.MemoryCredentialStore()
        memory.set("xai", "sk-memory")
        self.assertEqual("sk-memory", memory.get("xai"))
        memory.delete("xai")
        self.assertIsNone(memory.get("xai"))
        with self.assertRaises(credentials.CredentialStoreError):
            memory.set("other", "sk-secret")
        with self.assertRaises(credentials.CredentialStoreError) as captured:
            memory.set("xai", "")
        self.assertNotIn("sk-secret", str(captured.exception))


class SettingsV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="am-settings-v3-"))
        self.saved = {
            name: os.environ.get(name)
            for name in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME", "XAI_API_KEY")
        }
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = str(self.directory / "data")
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("XAI_API_KEY", None)
        self.vault = credentials.MemoryCredentialStore()

    def tearDown(self) -> None:
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(self.directory, ignore_errors=True)

    def _write(self, value: dict) -> bytes:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(value, indent=2) + "\n").encode("utf-8")
        path.write_bytes(payload)
        return payload

    def test_defaults_are_exact_and_read_only(self) -> None:
        settings, reason = store.load_settings_with_status(
            credential_store=self.vault
        )
        self.assertEqual(V5_DEFAULTS, settings)
        self.assertIsNone(reason)
        self.assertFalse(store.settings_path().exists())

    def test_v2_key_migration_is_verified_before_plaintext_is_removed(self) -> None:
        library = self.directory / "library"
        original = _v2_settings(key="sk-only-copy", root=library)
        self._write(original)

        settings, reason = store.load_settings_with_status(
            credential_store=self.vault
        )
        self.assertIsNone(reason)
        self.assertEqual("sk-only-copy", self.vault.get("xai"))
        self.assertEqual(5, settings["schema_version"])
        self.assertFalse(settings["ai"]["enabled"])
        self.assertIsNone(settings["ai"]["backend"])
        self.assertEqual(str(library.resolve()), settings["library"]["current_root"])
        self.assertEqual("ping_pong", settings["generation"]["loop_mode"])
        self.assertEqual(
            "2026-07-20-xai-v1",
            settings["ai"]["api"]["disclosure_version"],
        )
        disk = store.settings_path().read_text("utf-8")
        self.assertNotIn("sk-only-copy", disk)
        self.assertNotIn('"llm"', disk)
        self.assertNotIn("candidate_count", disk)

    def test_v3_direct_readiness_migrates_to_unselected_ollama(self) -> None:
        legacy = copy.deepcopy(V3_DEFAULTS)
        legacy["ai"].update({"enabled": True, "backend": "local"})
        legacy["ai"]["local"]["setup_fingerprint"] = "a" * 64
        self._write(legacy)

        settings, reason = store.load_settings_with_status(
            credential_store=self.vault
        )

        self.assertIsNone(reason)
        self.assertEqual(5, settings["schema_version"])
        self.assertEqual(
            {
                "model_id": None,
                "model_digest": None,
                "setup_fingerprint": None,
            },
            settings["ai"]["local"],
        )
        self.assertTrue(settings["ai"]["enabled"])
        self.assertEqual("local", settings["ai"]["backend"])
        self.assertEqual(5, json.loads(store.settings_path().read_text())["schema_version"])

    def test_v4_gguf_selection_migrates_without_touching_model_file(self) -> None:
        model = self.directory / "owner-model.gguf"
        model.write_bytes(b"GGUF-owner-bytes")
        before = model.stat()
        legacy = copy.deepcopy(V4_DEFAULTS)
        legacy["ai"].update({"enabled": True, "backend": "local"})
        legacy["ai"]["local"].update({
            "source": "gguf",
            "setup_fingerprint": "a" * 64,
        })
        legacy["ai"]["api"].update({
            "disclosure_version": "2026-07-20-xai-v1",
            "disclosure_at": "2026-07-20T12:00:00+00:00",
        })
        legacy["library"] = {
            "current_root": str((self.directory / "library").resolve()),
            "roots": [str((self.directory / "library").resolve())],
        }
        legacy["generation"]["loop_mode"] = "ping_pong"
        self._write(legacy)

        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == model:
                raise AssertionError("settings migration opened the GGUF model")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open):
            settings, reason = store.load_settings_with_status(
                credential_store=self.vault
            )

        self.assertIsNone(reason)
        self.assertEqual(5, settings["schema_version"])
        self.assertEqual(
            {"model_id": None, "model_digest": None, "setup_fingerprint": None},
            settings["ai"]["local"],
        )
        self.assertTrue(settings["ai"]["enabled"])
        self.assertEqual("local", settings["ai"]["backend"])
        self.assertEqual("ping_pong", settings["generation"]["loop_mode"])
        self.assertEqual(
            "2026-07-20-xai-v1",
            settings["ai"]["api"]["disclosure_version"],
        )
        self.assertEqual(b"GGUF-owner-bytes", model.read_bytes())
        after = model.stat()
        self.assertEqual(
            (before.st_size, before.st_mtime_ns),
            (after.st_size, after.st_mtime_ns),
        )

    def test_ollama_selection_is_strict_and_invalidates_local_setup(self) -> None:
        updated = store.update_local_ai_settings(
            {
                "model_id": "ornith:latest",
                "model_digest": "b" * 64,
            },
            credential_store=self.vault,
        )
        self.assertEqual("ornith:latest", updated["ai"]["local"]["model_id"])
        self.assertIsNone(updated["ai"]["local"]["setup_fingerprint"])

        with self.assertRaises(ValueError):
            store.update_local_ai_settings(
                {"model_id": "cloud:cloud", "model_digest": None},
                credential_store=self.vault,
            )

    def test_unavailable_or_unverified_vault_preserves_the_only_v2_copy(self) -> None:
        original = self._write(_v2_settings(key="sk-only-copy"))
        unavailable = credentials.MemoryCredentialStore(available=False)

        settings, reason = store.load_settings_with_status(
            credential_store=unavailable
        )
        self.assertEqual("credential_store_unavailable", reason)
        self.assertFalse(settings["ai"]["enabled"])
        self.assertIsNone(settings["ai"]["backend"])
        self.assertEqual("ping_pong", settings["generation"]["loop_mode"])
        self.assertEqual(original, store.settings_path().read_bytes())
        self.assertNotIn("sk-only-copy", json.dumps(settings))

        class NonPersistingStore(credentials.MemoryCredentialStore):
            def set(self, provider: str, value: str) -> None:
                pass

        settings, reason = store.load_settings_with_status(
            credential_store=NonPersistingStore()
        )
        self.assertEqual("credential_store_unavailable", reason)
        self.assertFalse(settings["ai"]["enabled"])
        self.assertIsNone(settings["ai"]["backend"])
        self.assertEqual(original, store.settings_path().read_bytes())

        settings, reason = store.load_settings_with_status(
            credential_store=self.vault
        )
        self.assertIsNone(reason)
        self.assertEqual("sk-only-copy", self.vault.get("xai"))
        self.assertEqual(5, settings["schema_version"])
        self.assertNotIn("sk-only-copy", store.settings_path().read_text("utf-8"))

    def test_failed_final_migration_write_restores_the_previous_vault_value(self) -> None:
        original = self._write(_v2_settings(key="sk-only-copy"))
        self.vault.set("xai", "sk-existing-vault")

        with patch.object(store, "_write_settings_file", side_effect=OSError("disk")):
            settings, reason = store.load_settings_with_status(
                credential_store=self.vault
            )

        self.assertEqual("credential_store_unavailable", reason)
        self.assertFalse(settings["ai"]["enabled"])
        self.assertEqual("sk-existing-vault", self.vault.get("xai"))
        self.assertEqual(original, store.settings_path().read_bytes())

    def test_strict_updates_never_persist_credentials_and_invalidate_setup(self) -> None:
        configured = copy.deepcopy(V5_DEFAULTS)
        configured["ai"]["backend"] = "api"
        configured["ai"]["api"]["setup_fingerprint"] = "a" * 64
        store.save_settings(configured, credential_store=self.vault)

        updated = store.update_api_key(
            {"provider": "xai", "key": "sk-new-private"},
            credential_store=self.vault,
        )
        self.assertEqual("sk-new-private", self.vault.get("xai"))
        self.assertIsNone(updated["ai"]["api"]["setup_fingerprint"])
        self.assertNotIn("sk-new-private", store.settings_path().read_text("utf-8"))

        with self.assertRaises(ValueError):
            store.update_ai_settings(
                {"enabled": True, "backend": "api"},
                ready=False,
                credential_store=self.vault,
            )
        updated = store.update_ai_settings(
            {"enabled": False, "backend": "local"},
            ready=False,
            credential_store=self.vault,
        )
        self.assertEqual("local", updated["ai"]["backend"])
        with self.assertRaises(ValueError):
            store.update_generation_settings(
                {"loop_mode": "smooth", "unknown": True},
                credential_store=self.vault,
            )
        updated = store.update_generation_settings(
            {"loop_mode": "none"}, credential_store=self.vault
        )
        self.assertEqual("none", updated["generation"]["loop_mode"])

    def test_failed_key_update_restores_the_previous_vault_value(self) -> None:
        configured = copy.deepcopy(V5_DEFAULTS)
        configured["ai"]["backend"] = "api"
        configured["ai"]["api"]["setup_fingerprint"] = "a" * 64
        store.save_settings(configured, credential_store=self.vault)
        before = store.settings_path().read_bytes()
        self.vault.set("xai", "sk-existing-vault")

        with patch.object(store, "_write_settings_file", side_effect=OSError("disk")):
            with self.assertRaisesRegex(
                ValueError, "Secure credential storage is unavailable"
            ):
                store.update_api_key(
                    {"provider": "xai", "key": "sk-replacement"},
                    credential_store=self.vault,
                )

        self.assertEqual("sk-existing-vault", self.vault.get("xai"))
        self.assertEqual(before, store.settings_path().read_bytes())

    def test_environment_override_is_external_and_never_written(self) -> None:
        store.save_settings(copy.deepcopy(V5_DEFAULTS), credential_store=self.vault)
        before = store.settings_path().read_bytes()
        os.environ["XAI_API_KEY"] = "sk-environment-only"

        self.assertEqual(
            "sk-environment-only",
            store.resolve_xai_key(credential_store=self.vault),
        )
        self.assertEqual(
            {
                "available": True,
                "configured": True,
                "external": True,
            },
            store.credential_status(credential_store=self.vault),
        )
        self.assertEqual(before, store.settings_path().read_bytes())


if __name__ == "__main__":
    unittest.main()
