from __future__ import annotations

import json
import os
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from am_configurator.ollama_client import (
    MAX_OLLAMA_RESPONSE_BYTES,
    OLLAMA_CHAT_URL,
    OLLAMA_MODELS_URL,
    OllamaClient,
    OllamaError,
    _NoOllamaRedirects,
    _OLLAMA_OPENER,
    _build_ollama_opener,
)


class _Response:
    def __init__(self, value: object, *, raw: bytes | None = None) -> None:
        self._payload = json.dumps(value).encode("utf-8") if raw is None else raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self._payload[:limit]


class _HTTPResponse(_Response):
    def __init__(
        self,
        value: object,
        *,
        raw: bytes | None = None,
        status: int = 200,
    ) -> None:
        super().__init__(value, raw=raw)
        self.status = status


class _Connection:
    def __init__(self, response: _HTTPResponse, observed: dict[str, object]) -> None:
        self._response = response
        self._observed = observed
        self.closed = False

    def request(self, method, path, *, body, headers) -> None:
        self._observed.update(
            method=method,
            path=path,
            body=json.loads(body),
            headers=headers,
        )

    def getresponse(self) -> _HTTPResponse:
        return self._response

    def close(self) -> None:
        self.closed = True


class _BlockingConnection(_Connection):
    def __init__(self, response: _HTTPResponse, observed: dict[str, object]) -> None:
        super().__init__(response, observed)
        self.entered = threading.Event()
        self.released = threading.Event()

    def getresponse(self) -> _HTTPResponse:
        self.entered.set()
        self.released.wait(5)
        return self._response

    def close(self) -> None:
        super().close()
        self.released.set()


def _connection_factory(
    response: _HTTPResponse,
    observed: dict[str, object],
    *,
    blocking: bool = False,
):
    connection_type = _BlockingConnection if blocking else _Connection

    def create(host, port, *, timeout):
        observed["connection"] = (host, port, timeout)
        connection = connection_type(response, observed)
        observed["connection_object"] = connection
        return connection

    return create


def _model(
    name: str,
    digest: str,
    *,
    size: int = 5_000_000,
    remote: bool = False,
    capabilities: object = None,
) -> dict:
    value = {
        "name": name,
        "model": name,
        "size": size,
        "digest": digest,
        "details": {
            "parameter_size": "9.0B",
            "quantization_level": "Q4_K_M",
        },
        "capabilities": ["completion"] if capabilities is None else capabilities,
    }
    if remote:
        value.update({"remote_model": name.removesuffix(":cloud"), "remote_host": "https://ollama.com:443"})
    return value


class OllamaClientTests(unittest.TestCase):
    def test_discovery_is_fixed_bounded_and_filters_remote_or_invalid_entries(self) -> None:
        calls = []
        payload = {
            "models": [
                _model("ornith:latest", "a" * 64),
                _model("ornith:35b", "b" * 64, size=21_000_000),
                _model("glm-5.2:cloud", "c" * 64, remote=True),
                _model("bad name", "d" * 64),
                _model("no-digest:latest", "short"),
                _model("no-size:latest", "e" * 64, size=0),
                _model("embedding:latest", "f" * 64, capabilities=["embedding"]),
            ]
        }

        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response(payload)

        models = OllamaClient(opener=opener).list_models(
            deadline=time.monotonic() + 10
        )

        self.assertEqual(["ornith:35b", "ornith:latest"], [item.model_id for item in models])
        self.assertEqual("a" * 64, models[1].digest)
        self.assertEqual("9.0B", models[1].parameter_size)
        self.assertEqual("Q4_K_M", models[1].quantization)
        request, timeout = calls[0]
        self.assertEqual(OLLAMA_MODELS_URL, request.full_url)
        self.assertEqual("GET", request.get_method())
        self.assertGreater(timeout, 0)

    def test_older_tags_contract_requires_upgrade_without_show_fallback(self) -> None:
        legacy_model = _model("ornith:latest", "a" * 64)
        legacy_model.pop("capabilities")
        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return _Response({"models": [legacy_model]})

        with self.assertRaises(OllamaError) as captured:
            OllamaClient(opener=opener).list_models(
                deadline=time.monotonic() + 10
            )
        self.assertEqual("upgrade_required", captured.exception.code)
        self.assertIn("must be upgraded", str(captured.exception))
        self.assertEqual([OLLAMA_MODELS_URL], [url for url, _timeout in calls])

        empty = OllamaClient(
            opener=lambda *_args, **_kwargs: _Response({"models": []})
        ).list_models(deadline=time.monotonic() + 10)
        self.assertEqual((), empty)

        non_completion = OllamaClient(
            opener=lambda *_args, **_kwargs: _Response({
                "models": [
                    _model(
                        "embedding:latest",
                        "b" * 64,
                        capabilities=["embedding"],
                    )
                ]
            })
        ).list_models(deadline=time.monotonic() + 10)
        self.assertEqual((), non_completion)

    def test_chat_uses_only_the_fixed_loopback_endpoint_and_rejects_bad_output(self) -> None:
        observed = {}

        body = {"model": "ornith:latest", "stream": False}
        response = OllamaClient(
            connection_factory=_connection_factory(
                _HTTPResponse({"message": {"content": "{}"}}),
                observed,
            )
        ).chat(
            body,
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )
        self.assertEqual({"message": {"content": "{}"}}, response)
        host, port, timeout = observed["connection"]
        self.assertEqual(("127.0.0.1", 11434), (host, port))
        self.assertEqual("POST", observed["method"])
        self.assertEqual("/api/chat", observed["path"])
        self.assertEqual(body, observed["body"])
        self.assertGreater(timeout, 0)
        self.assertTrue(observed["connection_object"].closed)

        with self.assertRaises(OllamaError) as malformed:
            OllamaClient(
                connection_factory=_connection_factory(
                    _HTTPResponse({}, raw=b"not-json"),
                    {},
                )
            ).chat(
                body,
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("bad_response", malformed.exception.code)

        too_large = b"{" + (b" " * MAX_OLLAMA_RESPONSE_BYTES) + b"}"
        with self.assertRaises(OllamaError) as oversized:
            OllamaClient(
                connection_factory=_connection_factory(
                    _HTTPResponse({}, raw=too_large),
                    {},
                )
            ).chat(
                body,
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("bad_response", oversized.exception.code)

    def test_proxy_redirect_timeout_http_and_cancellation_fail_closed(self) -> None:
        handlers = _OLLAMA_OPENER.handlers
        self.assertFalse(
            any(isinstance(handler, urllib.request.ProxyHandler) for handler in handlers)
        )
        self.assertTrue(any(isinstance(handler, _NoOllamaRedirects) for handler in handlers))

        with self.assertRaises(OllamaError) as redirect:
            OllamaClient(
                connection_factory=_connection_factory(
                    _HTTPResponse({}, status=302),
                    {},
                )
            ).chat(
                {"model": "ornith:latest"},
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("unavailable", redirect.exception.code)
        self.assertNotIn(OLLAMA_CHAT_URL, str(redirect.exception))

        with self.assertRaises(OllamaError) as expired:
            OllamaClient(opener=lambda *_args, **_kwargs: self.fail("opened")).list_models(
                deadline=time.monotonic() - 1
            )
        self.assertEqual("timeout", expired.exception.code)

        with self.assertRaises(OllamaError) as cancelled:
            OllamaClient(
                connection_factory=lambda *_args, **_kwargs: self.fail("opened")
            ).chat(
                {"model": "ornith:latest"},
                deadline=time.monotonic() + 10,
                cancelled=lambda: True,
            )
        self.assertEqual("cancelled", cancelled.exception.code)

    def test_actual_discovery_request_ignores_environment_proxy(self) -> None:
        sentinel_proxy = ("127.0.0.1", 54321)
        attempted_connections = []

        def block_network(address, *_args, **_kwargs):
            attempted_connections.append(address)
            raise OSError("test socket blocked")

        with patch.dict(
            os.environ,
            {"HTTP_PROXY": f"http://{sentinel_proxy[0]}:{sentinel_proxy[1]}"},
            clear=True,
        ):
            opener = _build_ollama_opener()
        with patch.object(socket, "create_connection", side_effect=block_network):
            with self.assertRaises(OllamaError) as captured:
                OllamaClient(opener=opener).list_models(
                    deadline=time.monotonic() + 10
                )

        self.assertEqual("unavailable", captured.exception.code)
        self.assertEqual([("127.0.0.1", 11434)], attempted_connections)
        self.assertNotIn(sentinel_proxy, attempted_connections)

    def test_chat_cancellation_closes_the_exchange_and_discards_a_late_response(self) -> None:
        observed: dict[str, object] = {}
        client = OllamaClient(
            connection_factory=_connection_factory(
                _HTTPResponse({"message": {"content": "late"}}),
                observed,
                blocking=True,
            )
        )
        cancelled = threading.Event()
        failures: list[OllamaError] = []

        def run() -> None:
            try:
                client.chat(
                    {"model": "ornith:latest", "stream": False},
                    deadline=time.monotonic() + 10,
                    cancelled=cancelled.is_set,
                )
            except OllamaError as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        creation_deadline = time.monotonic() + 1
        while (
            "connection_object" not in observed
            and time.monotonic() < creation_deadline
        ):
            time.sleep(0.001)
        self.assertIn("connection_object", observed)
        connection = observed["connection_object"]
        self.assertTrue(connection.entered.wait(1))
        cancelled.set()
        worker.join(1)

        self.assertFalse(worker.is_alive())
        self.assertTrue(connection.closed)
        self.assertEqual(["cancelled"], [error.code for error in failures])

    def test_chat_deadline_closes_an_in_flight_exchange(self) -> None:
        observed: dict[str, object] = {}
        client = OllamaClient(
            connection_factory=_connection_factory(
                _HTTPResponse({"message": {"content": "late"}}),
                observed,
                blocking=True,
            )
        )

        with self.assertRaises(OllamaError) as raised:
            client.chat(
                {"model": "ornith:latest", "stream": False},
                deadline=time.monotonic() + 0.1,
                cancelled=lambda: False,
            )

        self.assertEqual("timeout", raised.exception.code)
        self.assertTrue(observed["connection_object"].closed)


if __name__ == "__main__":
    unittest.main()
