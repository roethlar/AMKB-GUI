"""Absence guard for the AI-removal plan (docs/superpowers/plans/2026-08-14-ai-removal.md).

Follows the tests/test_legacy_inline_generator_removed.py precedent: proves the
removed AI generation surface (modules, tests, server routes, and the ollama/
api-ai identifiers in the grep gate) does not silently reappear.

The grep gate is ``ollama|recipe_provider|ai_catalog|/api/ai/|ai_capability``,
scanned across ``am_configurator/``. One deliberate keep is allowlisted below;
see the plan's slice 3 DONE note and tests/test_packaging.py for why it stays.
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AM_CONFIGURATOR = ROOT / "am_configurator"

GREP_GATE = re.compile(r"ollama|recipe_provider|ai_catalog|/api/ai/|ai_capability", re.IGNORECASE)

# Deliberate, previously-ruled keeps (do not remove without a new plan/ruling):
#   - desktop.py's _assert_ollama_api_only_bundle(): a packaging bundle-content
#     guard (no shipped .gguf/llama-cli/llama-server), independent coverage in
#     tests/test_packaging.py::test_native_packages_are_ollama_api_only. Not an
#     AI-recipe-generation check, so slice 3 kept it.
ALLOWED_HITS = {
    ("am_configurator/desktop.py", "_assert_ollama_api_only_bundle()"),
    ("am_configurator/desktop.py", "def _assert_ollama_api_only_bundle() -> None:"),
}


class AiRemovalAbsenceGuardTests(unittest.TestCase):
    def test_removed_ai_modules_are_not_importable(self) -> None:
        for name in (
            "llm",
            "recipe_provider",
            "recipe_inference",
            "ollama_client",
            "ai_catalog",
            "ai_capability",
            "procedural_generation",
            "generation_admission",
            "credentials",
        ):
            with self.subTest(module=name):
                self.assertIsNone(importlib.util.find_spec(f"am_configurator.{name}"))

    def test_removed_ai_test_modules_are_gone(self) -> None:
        for name in (
            "test_recipe_provider.py",
            "test_recipe_inference.py",
            "test_ollama_client.py",
            "test_ai_capability.py",
            "test_procedural_generation.py",
            "test_generation_admission.py",
            "test_credentials.py",
            "test_ai_routes.py",
        ):
            with self.subTest(test=name):
                self.assertFalse((ROOT / "tests" / name).exists(), name)

    def test_removed_ai_routes_are_gone(self) -> None:
        source = (AM_CONFIGURATOR / "server.py").read_text("utf-8")
        for forbidden in (
            "/api/ai/",
            "/api/settings/ai",
            "/api/settings/ollama",
            "/api/lighting/effects",
            "/api/lighting/jobs",
            "/api/led/generate",
            '"/api/settings/privacy"',
        ):
            with self.subTest(route=forbidden):
                self.assertNotIn(forbidden, source)
        # The legacy-credential migration repair route is a deliberate keep
        # (plan slice 2 DONE note); prove it is still live, not collaterally
        # deleted by a future sweep of this same surface.
        self.assertIn("/api/settings/migration/discard-credential", source)

    def test_browser_has_no_ai_generation_identifiers(self) -> None:
        source = (AM_CONFIGURATOR / "web" / "app.js").read_text("utf-8")
        for token in (
            "aiStudioAvailable",
            "projectApiProviderPicker",
            "ollamaEndpointDataFlow",
            "ollamaModelRefreshFailed",
            "normalizeOllamaModels",
            "projectOllamaModelPicker",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_grep_gate_has_no_unallowed_hits(self) -> None:
        """Mirrors the plan's slice 6 grep gate, scanned line-by-line so a new
        hit's file and text are reported instead of just a bare count."""
        hits: list[tuple[str, str]] = []
        for path in sorted(AM_CONFIGURATOR.rglob("*")):
            if not path.is_file() or path.suffix.casefold() in {".pyc", ".pyo"}:
                continue
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line in text.splitlines():
                if GREP_GATE.search(line):
                    hits.append((relative, line.strip()))

        unexpected = [hit for hit in hits if hit not in ALLOWED_HITS]
        self.assertEqual(unexpected, [], f"unexpected AI-surface residue: {unexpected}")

        # Prove the allowlist itself stays accurate: every entry must still
        # occur, so a future removal of _assert_ollama_api_only_bundle prompts
        # trimming this allowlist rather than leaving it stale.
        for allowed in ALLOWED_HITS:
            with self.subTest(allowed=allowed):
                self.assertIn(allowed, hits, "stale allowlist entry no longer present")


if __name__ == "__main__":
    unittest.main()
