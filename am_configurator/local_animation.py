"""Ollama developer adapter for the shared procedural animation contract.

This module remains intentionally isolated from the desktop application.  It
uses a local Ollama model to choose a bounded recipe, then delegates all
validation, rendering, quality checks, artifacts, and device mapping to
``am_configurator.procedural``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .procedural import (
    DEFAULT_DURATION_MS,
    DEFAULT_FRAME_COUNT,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    RecipeError,
    recipe_schema,
    recipe_system_prompt,
    render_recipe,
    validate_recipe,
    write_animation_artifacts,
)


DEFAULT_MODEL = "ornith:latest"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
MAX_RESPONSE_BYTES = 1_000_000

_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

# Preserve the proof helper's public name while keeping its implementation in
# the backend-neutral module.
write_proof_artifacts = write_animation_artifacts


class OllamaRecipeClient:
    """Small loopback-only Ollama structured-output client for development."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 180,
    ) -> None:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama endpoint must be an unauthenticated loopback HTTP URL.")
        if timeout_seconds <= 0 or timeout_seconds > 600:
            raise ValueError("Ollama timeout must be between 0 and 600 seconds.")
        self.endpoint = endpoint.rstrip("/")
        self.opener = opener
        self.timeout_seconds = float(timeout_seconds)

    def _request(self, body: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(body, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise RecipeError(f"Ollama returned HTTP {exc.code}.") from None
        except (OSError, TimeoutError, URLError):
            raise RecipeError("Could not reach the local Ollama service.") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise RecipeError("Ollama response exceeded the local size limit.")
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RecipeError("Ollama returned malformed JSON.") from None
        if not isinstance(parsed, dict):
            raise RecipeError("Ollama returned an invalid response object.")
        return parsed

    def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        frame_count: int = DEFAULT_FRAME_COUNT,
        density_default: str = "balanced",
    ) -> dict[str, Any]:
        clean_prompt = str(prompt).strip()
        if not 1 <= len(clean_prompt) <= 4000:
            raise RecipeError("Prompt must contain 1 to 4000 characters.")
        if not _MODEL_NAME.fullmatch(model):
            raise RecipeError("Ollama model name is invalid.")
        system_prompt = recipe_system_prompt(
            width,
            height,
            frame_count,
            density_default=density_default,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": clean_prompt},
        ]
        last_error: RecipeError | None = None
        for attempt in range(3):
            response = self._request(
                {
                    "model": model,
                    "stream": False,
                    "format": recipe_schema(),
                    "options": {"temperature": 0.35, "seed": 7319 + attempt},
                    "messages": messages,
                }
            )
            content = response.get("message", {}).get("content")
            try:
                if not isinstance(content, str) or len(content.encode()) > MAX_RESPONSE_BYTES:
                    raise RecipeError("Ollama did not return a bounded recipe string.")
                recipe = json.loads(content)
                return validate_recipe(recipe)
            except (json.JSONDecodeError, RecipeError) as exc:
                last_error = (
                    exc
                    if isinstance(exc, RecipeError)
                    else RecipeError("Ollama recipe was not JSON.")
                )
                if attempt < 2:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The recipe failed validation: {last_error}. "
                                "Return a corrected complete recipe."
                            ),
                        }
                    )
        raise last_error or RecipeError("Ollama did not return a usable recipe.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a local procedural LED animation proof."
    )
    parser.add_argument("prompt", help="Natural-language lighting effect description")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Installed Ollama model name")
    parser.add_argument(
        "--output", type=Path, required=True, help="Directory for GIF and LED artifacts"
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Loopback Ollama base URL")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAME_COUNT)
    parser.add_argument(
        "--density", choices=("sparse", "balanced", "dense"), default="balanced"
    )
    args = parser.parse_args(argv)
    client = OllamaRecipeClient(endpoint=args.endpoint)
    recipe = client.generate(
        args.prompt,
        model=args.model,
        width=args.width,
        height=args.height,
        frame_count=args.frames,
        density_default=args.density,
    )
    paths = write_proof_artifacts(
        recipe,
        args.output,
        width=args.width,
        height=args.height,
        frame_count=args.frames,
    )
    print(json.dumps({key: str(path) for key, path in paths.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
