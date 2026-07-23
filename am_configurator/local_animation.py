"""Ollama developer adapter for the shared procedural animation contract.

This module remains intentionally isolated from the desktop application.  It
uses a local Ollama model to choose a bounded recipe, then delegates all
validation, rendering, quality checks, artifacts, and device mapping to
``am_configurator.procedural``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Sequence

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
from .ollama_client import OLLAMA_BASE_URL, OllamaClient, OllamaError, valid_model_id


DEFAULT_MODEL = "ornith:latest"
DEFAULT_ENDPOINT = OLLAMA_BASE_URL
MAX_RESPONSE_BYTES = 1_000_000

# Preserve the proof helper's public name while keeping its implementation in
# the backend-neutral module.
write_proof_artifacts = write_animation_artifacts


class OllamaRecipeClient:
    """Small loopback-only Ollama structured-output client for development."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        connection_factory: Callable[..., Any] | None = None,
        timeout_seconds: float = 180,
    ) -> None:
        if endpoint.rstrip("/") != DEFAULT_ENDPOINT:
            raise ValueError("Ollama endpoint is fixed to the local service.")
        if timeout_seconds <= 0 or timeout_seconds > 600:
            raise ValueError("Ollama timeout must be between 0 and 600 seconds.")
        self.endpoint = DEFAULT_ENDPOINT
        self.client = (
            OllamaClient()
            if connection_factory is None
            else OllamaClient(connection_factory=connection_factory)
        )
        self.timeout_seconds = float(timeout_seconds)

    def _request(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.client.chat(
                body,
                deadline=time.monotonic() + self.timeout_seconds,
                cancelled=lambda: False,
            )
        except OllamaError:
            raise RecipeError("Could not use the local Ollama service.") from None

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
        if not valid_model_id(model):
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
