"""Canonical, authenticated H5a hub editor document boundaries."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from am_configurator import hub_profile
from am_configurator.server import create_server


def _profile() -> dict:
    return {
        "schema_version": 1,
        "identity": {
            "ecosystem": "via",
            "family": "Fixture Pad",
            "wire_identity": "CAFE:BEEF",
            "endpoint": {"vid": 0xCAFE, "pid": 0xBEEF, "transport": "hid"},
            "protocol": {"via_protocol": 9},
            "definition": {
                "source": "user_import",
                "hash": "sha256-" + "ab" * 32,
            },
        },
    }


class HubEditorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        data_dir = tempfile.TemporaryDirectory(prefix="openkeeb_hub_editor_api_")
        self.addCleanup(data_dir.cleanup)
        env = mock.patch.dict(os.environ, {"AM_CONFIGURATOR_DATA_DIR": data_dir.name})
        env.start()
        self.addCleanup(env.stop)
        self.server, url = create_server()
        self.addCleanup(self.server.server_close)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        parsed = urlparse(url)
        self.token = parse_qs(parsed.query)["token"][0]
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request(
        self, path: str, body: dict, *, authenticated: bool = True
    ) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["X-AM-Token"] = self.token
        call = Request(self.base + path, data=data, method="POST", headers=headers)
        try:
            with urlopen(call, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_open_validates_untrusted_bytes_with_canonical_loader(self) -> None:
        canonical = hub_profile.dumps_hub_profile(_profile())
        status, opened = self.request(
            "/api/hub/open",
            {"data": base64.b64encode(canonical.encode("utf-8")).decode("ascii")},
        )

        self.assertEqual(200, status)
        self.assertEqual(hub_profile.loads_hub_profile(canonical), opened["profile"])

        duplicate = canonical.replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1
        )
        status, rejected = self.request(
            "/api/hub/open",
            {"data": base64.b64encode(duplicate.encode("utf-8")).decode("ascii")},
        )
        self.assertEqual(400, status)
        self.assertIn("repeats", rejected["error"])

    def test_save_returns_canonical_utf8_from_canonical_dumper(self) -> None:
        profile = _profile()
        profile["identity"]["family"] = "Clavier Éclair"
        status, saved = self.request("/api/hub/save", {"profile": profile})

        self.assertEqual(200, status)
        self.assertEqual(hub_profile.dumps_hub_profile(profile), saved["data"])
        self.assertTrue(saved["data"].endswith("\n"))
        self.assertIn("Éclair", saved["data"])

    def test_open_and_save_require_local_authentication(self) -> None:
        encoded = base64.b64encode(
            hub_profile.dumps_hub_profile(_profile()).encode("utf-8")
        ).decode("ascii")
        for path, body in (
            ("/api/hub/open", {"data": encoded}),
            ("/api/hub/save", {"profile": _profile()}),
        ):
            with self.subTest(path=path):
                status, response = self.request(path, body, authenticated=False)
                self.assertEqual(403, status)
                self.assertIn("Unauthorized", response["error"])


if __name__ == "__main__":
    unittest.main()
