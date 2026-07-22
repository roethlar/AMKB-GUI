from __future__ import annotations

import json
import time
import unittest
import urllib.error
import urllib.request

from am_configurator.ollama_client import (
    MAX_OLLAMA_RESPONSE_BYTES,
    OLLAMA_CHAT_URL,
    OLLAMA_MODELS_URL,
    OllamaClient,
    OllamaError,
    _NoOllamaRedirects,
    _OLLAMA_OPENER,
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

    def test_chat_uses_only_the_fixed_loopback_endpoint_and_rejects_bad_output(self) -> None:
        observed = {}

        def opener(request, timeout):
            observed.update(url=request.full_url, body=json.loads(request.data), timeout=timeout)
            return _Response({"message": {"content": "{}"}})

        body = {"model": "ornith:latest", "stream": False}
        response = OllamaClient(opener=opener).chat(
            body,
            deadline=time.monotonic() + 10,
            cancelled=lambda: False,
        )
        self.assertEqual({"message": {"content": "{}"}}, response)
        self.assertEqual(OLLAMA_CHAT_URL, observed["url"])
        self.assertEqual(body, observed["body"])
        self.assertGreater(observed["timeout"], 0)

        with self.assertRaises(OllamaError) as malformed:
            OllamaClient(opener=lambda *_args, **_kwargs: _Response({}, raw=b"not-json")).chat(
                body,
                deadline=time.monotonic() + 10,
                cancelled=lambda: False,
            )
        self.assertEqual("bad_response", malformed.exception.code)

        too_large = b"{" + (b" " * MAX_OLLAMA_RESPONSE_BYTES) + b"}"
        with self.assertRaises(OllamaError) as oversized:
            OllamaClient(opener=lambda *_args, **_kwargs: _Response({}, raw=too_large)).chat(
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

        def redirected(request, timeout):
            del request, timeout
            raise urllib.error.HTTPError(
                OLLAMA_CHAT_URL, 302, "redirect", {}, None
            )

        with self.assertRaises(OllamaError) as redirect:
            OllamaClient(opener=redirected).chat(
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
            OllamaClient(opener=lambda *_args, **_kwargs: self.fail("opened")).chat(
                {"model": "ornith:latest"},
                deadline=time.monotonic() + 10,
                cancelled=lambda: True,
            )
        self.assertEqual("cancelled", cancelled.exception.code)


if __name__ == "__main__":
    unittest.main()
