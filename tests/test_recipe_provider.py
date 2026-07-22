from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from am_configurator import ai_catalog, llm, procedural, recipe_provider
from am_configurator.local_ai_runtime import RuntimePaths, get_local_ai_runtime
from am_configurator.local_model import LocalModelManager, SelectedModel
from am_configurator.ollama_client import OllamaModel
from am_configurator.recipe_provider import (
    ManagedLlamaServer,
    ManagedLocalRecipeProvider,
    OllamaRecipeProvider,
    RecipeRequest,
    XaiRecipeProvider,
)


def _recipe() -> dict:
    return {
        "schema_version": 1,
        "name": "Blue sweep",
        "density": "balanced",
        "background": "#000008",
        "palette": ["#0066FF", "#00FFFF"],
        "layers": [
            {
                "kind": "sweep",
                "color_index": 0,
                "secondary_color_index": 1,
                "speed": 1,
                "phase": 0.0,
                "direction_degrees": 0.0,
                "center_x": 0.5,
                "center_y": 0.5,
                "scale": 1.0,
                "width": 0.4,
                "trail": 0.5,
                "count": 2,
                "intensity": 1.0,
                "seed": 7,
            }
        ],
    }


def _request() -> RecipeRequest:
    return RecipeRequest(
        prompt="A bright blue scanner",
        width=18,
        height=7,
        frame_count=200,
        density_default="balanced",
    )


def _xai_response(recipe: dict, *, cost: int | None = 123) -> dict:
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(recipe)}
                ],
            }
        ]
    }
    if cost is not None:
        response["usage"] = {"cost_in_usd_ticks": cost}
    return response


class XaiRecipeProviderTests(unittest.TestCase):
    def test_curated_api_recipe_cost_ceiling_uses_integer_ticks(self) -> None:
        self.assertEqual(
            747_520_000,
            ai_catalog.recipe_max_cost_usd_ticks("xai", "grok-4.5"),
        )
        with self.assertRaises(ValueError):
            ai_catalog.recipe_max_cost_usd_ticks("other", "grok-4.5")

    def test_one_strict_call_returns_validated_recipe_and_exact_usage(self) -> None:
        calls: list[tuple] = []

        def transport(url, payload, api_key, deadline):
            calls.append((url, payload, api_key, deadline))
            return _xai_response(_recipe())

        provider = XaiRecipeProvider("sk-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        url, payload, api_key, _deadline = calls[0]
        self.assertEqual(llm.XAI_RESPONSES_URL, url)
        self.assertEqual("sk-private", api_key)
        self.assertEqual("grok-4.5", payload["model"])
        self.assertIs(payload["store"], False)
        self.assertEqual(1536, payload["max_output_tokens"])
        self.assertEqual(
            procedural.recipe_schema(), payload["text"]["format"]["schema"]
        )
        self.assertIs(payload["text"]["format"]["strict"], True)
        self.assertIn("18x7", payload["input"][0]["content"])
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("xai", result.provider)
        self.assertEqual("grok-4.5", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 123}, result.usage)

    def test_cancelled_or_invalid_output_never_retries_or_leaks_content(self) -> None:
        calls = 0

        def transport(url, payload, api_key, deadline):
            nonlocal calls
            calls += 1
            return _xai_response({"raw_secret": "provider-body-secret"}, cost=222)

        provider = XaiRecipeProvider("sk-private", transport=transport)
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual(0, calls)
        self.assertNotIn("sk-private", str(cancelled.exception))

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual(1, calls)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(222, invalid.exception.usage.cost_in_usd_ticks)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

    def test_cancellation_after_the_one_paid_call_preserves_exact_usage(self) -> None:
        checks = iter((False, True))
        provider = XaiRecipeProvider(
            "sk-private",
            transport=lambda *_args: _xai_response(_recipe(), cost=456),
        )

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )

        self.assertEqual("unavailable", captured.exception.code)
        self.assertEqual(456, captured.exception.usage.cost_in_usd_ticks)


class _OllamaClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple] = []

    def chat(self, payload, *, deadline, cancelled):
        self.calls.append((payload, deadline, cancelled))
        return self.response


class OllamaRecipeProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = OllamaModel(
            model_id="ornith:latest",
            digest="a" * 64,
            size_bytes=5_629_110_568,
            parameter_size="9.0B",
            quantization="Q4_K_M",
        )

    def test_strict_recipe_request_uses_selected_installed_model(self) -> None:
        client = _OllamaClient({"message": {"content": json.dumps(_recipe())}})
        provider = OllamaRecipeProvider(self.model, client=client)

        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(client.calls))
        payload, _deadline, _cancelled = client.calls[0]
        self.assertEqual("ornith:latest", payload["model"])
        self.assertIs(payload["stream"], False)
        self.assertEqual(procedural.recipe_schema(), payload["format"])
        self.assertEqual(1536, payload["options"]["num_predict"])
        self.assertIn("18x7", payload["messages"][0]["content"])
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("local", result.backend)
        self.assertEqual("ollama", result.provider)
        self.assertEqual("ornith:latest", result.model_id)
        self.assertIsNone(result.usage)

    def test_retry_changes_seed_adds_bounded_reason_and_rejects_bad_output(self) -> None:
        client = _OllamaClient({"message": {"content": json.dumps(_recipe())}})
        provider = OllamaRecipeProvider(self.model, client=client)
        provider.generate(_request(), time.monotonic() + 10, lambda: False)
        provider.generate_attempt(
            _request(),
            time.monotonic() + 10,
            lambda: False,
            attempt=1,
            validation_reason="peak brightness was too low /private/model.gguf",
        )

        first, second = (call[0] for call in client.calls)
        self.assertNotEqual(first["options"]["seed"], second["options"]["seed"])
        self.assertIn("peak brightness was too low", second["messages"][1]["content"])
        self.assertNotIn("/private/model.gguf", second["messages"][1]["content"])

        invalid = OllamaRecipeProvider(
            self.model,
            client=_OllamaClient({"message": {"content": '{"private":"secret"}'}}),
        )
        with self.assertRaises(llm.ProviderError) as captured:
            invalid.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertNotIn("secret", str(captured.exception))


class _ModelManager:
    def __init__(self, selected: SelectedModel) -> None:
        self.selected = selected
        self.calls = 0

    def resolve_selected(self) -> SelectedModel:
        self.calls += 1
        return self.selected


class _Server:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple] = []

    def complete(self, runtime, model, payload, deadline, cancelled):
        self.calls.append((runtime, model, payload, deadline, cancelled))
        return self.response

    def close(self) -> None:
        pass


class ManagedLocalRecipeProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="am-recipe-provider-"))
        model_path = self.directory / "chosen.gguf"
        self.model = SelectedModel(
            path=model_path,
            filename=model_path.name,
            size_bytes=2_000_000,
            sha256="a" * 64,
            device=1,
            inode=2,
            mtime_ns=3,
        )
        self.runtime = RuntimePaths(
            cli=self.directory / "llama-cli",
            server=self.directory / "llama-server",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_uses_only_current_attested_model_and_strict_local_schema(self) -> None:
        manager = _ModelManager(self.model)
        server = _Server({
            "choices": [{"message": {"content": json.dumps(_recipe())}}]
        })
        provider = ManagedLocalRecipeProvider(
            model_manager=manager,
            runtime_resolver=lambda: self.runtime,
            server=server,
        )

        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, manager.calls)
        self.assertEqual(1, len(server.calls))
        runtime, model, payload, _deadline, _cancelled = server.calls[0]
        self.assertEqual(self.runtime, runtime)
        self.assertEqual(self.model, model)
        self.assertEqual("local", payload["model"])
        self.assertEqual(
            procedural.recipe_schema(),
            payload["response_format"]["json_schema"]["schema"],
        )
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("local", result.backend)
        self.assertEqual("llama.cpp", result.provider)
        self.assertEqual("chosen.gguf", result.model_id)
        self.assertIsNone(result.usage)

        provider.generate_attempt(
            _request(),
            time.monotonic() + 10,
            lambda: False,
            attempt=1,
            validation_reason="peak brightness was too low",
        )
        first_payload = server.calls[0][2]
        retry_payload = server.calls[1][2]
        self.assertNotEqual(first_payload["seed"], retry_payload["seed"])
        self.assertIn("peak brightness was too low", retry_payload["messages"][1]["content"])
        with self.assertRaises(llm.ProviderError):
            provider.generate_attempt(
                _request(),
                time.monotonic() + 10,
                lambda: False,
                attempt=3,
                validation_reason="another failure",
            )
        self.assertEqual(2, len(server.calls))

    def test_invalid_local_response_is_pathless_and_content_free(self) -> None:
        manager = _ModelManager(self.model)
        server = _Server({
            "choices": [
                {"message": {"content": '{"path":"/private/model.gguf"}'}}
            ]
        })
        provider = ManagedLocalRecipeProvider(
            model_manager=manager,
            runtime_resolver=lambda: self.runtime,
            server=server,
        )

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertNotIn("/private/model.gguf", str(captured.exception))


class _Process:
    def __init__(self) -> None:
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.returncode = None
        self.terminated = 0
        self.killed = 0

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated += 1
        self.returncode = 0

    def kill(self) -> None:
        self.killed += 1
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise TimeoutError
        return self.returncode


class ManagedLlamaServerTests(unittest.TestCase):
    def test_loopback_client_disables_proxies_and_redirects(self) -> None:
        handlers = recipe_provider._LOOPBACK_OPENER.handlers
        # Supplying ProxyHandler({}) suppresses the default environment proxy;
        # urllib omits the empty handler itself from the installed chain.
        self.assertFalse(
            any(isinstance(handler, urllib.request.ProxyHandler) for handler in handlers)
        )
        self.assertTrue(
            any(
                isinstance(handler, recipe_provider._NoLoopbackRedirects)
                for handler in handlers
            )
        )

    def test_server_is_bounded_authenticated_reused_and_closed(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="am-llama-session-"))
        self.addCleanup(shutil.rmtree, directory, True)
        runtime = RuntimePaths(
            cli=directory / "llama-cli", server=directory / "llama-server"
        )
        model = SelectedModel(
            path=directory / "selected.gguf",
            filename="selected.gguf",
            size_bytes=2_000_000,
            sha256="b" * 64,
            device=1,
            inode=2,
            mtime_ns=3,
        )
        processes: list[_Process] = []
        launches: list[tuple] = []

        def process_factory(arguments, **kwargs):
            launches.append((arguments, kwargs))
            process = _Process()
            processes.append(process)
            return process

        readiness: list[tuple] = []
        exchanges: list[tuple] = []

        def ready(port, token, deadline, process, cancelled):
            readiness.append((port, token, process))

        def exchange(port, token, payload, deadline, cancelled, abort):
            exchanges.append((port, token, payload))
            return {"choices": [{"message": {"content": json.dumps(_recipe())}}]}

        server = ManagedLlamaServer(
            process_factory=process_factory,
            readiness_probe=ready,
            exchange=exchange,
            port_picker=lambda: 54321,
            token_factory=lambda: "private-loopback-token",
            idle_seconds=60,
        )
        deadline = time.monotonic() + 10
        payload = {"model": "local"}
        server.complete(runtime, model, payload, deadline, lambda: False)
        server.complete(runtime, model, payload, deadline, lambda: False)

        self.assertEqual(1, len(launches))
        arguments, kwargs = launches[0]
        self.assertEqual(str(runtime.server), arguments[0])
        self.assertIn(str(model.path), arguments)
        for required in (
            "--offline",
            "--host",
            "127.0.0.1",
            "--api-key",
            "private-loopback-token",
            "--parallel",
            "1",
            "--no-slots",
            "--no-webui",
            "--gpu-layers",
            "all",
        ):
            self.assertIn(required, arguments)
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(1, len(readiness))
        self.assertEqual(2, len(exchanges))

        replacement = SelectedModel(
            path=directory / "replacement.gguf",
            filename="replacement.gguf",
            size_bytes=3_000_000,
            sha256="c" * 64,
            device=1,
            inode=3,
            mtime_ns=4,
        )
        server.complete(runtime, replacement, payload, deadline, lambda: False)
        self.assertEqual(2, len(launches))
        self.assertEqual(1, processes[0].terminated)

        server.close()
        self.assertEqual(1, processes[1].terminated)
        for process in processes:
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)


@unittest.skipUnless(
    os.environ.get("AM_CONFIGURATOR_TEST_LOCAL_MODEL"),
    "prepared local GGUF integration model not configured",
)
class PreparedLocalServerIntegrationTests(unittest.TestCase):
    def test_pinned_server_accepts_authenticated_grammar_request(self) -> None:
        model_path = Path(os.environ["AM_CONFIGURATOR_TEST_LOCAL_MODEL"])
        with tempfile.TemporaryDirectory(prefix="am-local-server-smoke-") as root:
            model = LocalModelManager(Path(root) / "metadata").select(model_path)
            server = ManagedLlamaServer(idle_seconds=5)
            self.addCleanup(server.close)
            response = server.complete(
                get_local_ai_runtime(),
                model,
                {
                    "model": "local",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Return a JSON object whose ok field is true.",
                        }
                    ],
                    "stream": False,
                    "temperature": 0,
                    "max_tokens": 32,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "smoke",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {"ok": {"type": "boolean", "const": True}},
                                "required": ["ok"],
                            },
                        },
                    },
                },
                time.monotonic() + 180,
                lambda: False,
            )
            content = response["choices"][0]["message"]["content"]
            self.assertEqual({"ok": True}, json.loads(content))


if __name__ == "__main__":
    unittest.main()
