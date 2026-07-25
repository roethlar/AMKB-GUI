"""One deterministic Ollama request contract for procedural recipes."""

from __future__ import annotations

import hashlib
from typing import Any


MAX_RECIPE_PROMPT_CHARS = 4000
MAX_LOCAL_RESPONSE_BYTES = 1_000_000
LOCAL_OUTPUT_TOKENS = 1536
LOCAL_MAX_RETRIES = 2
LOCAL_TEMPERATURE = 0.2


def _clean_prompt(prompt: object) -> str:
    if not isinstance(prompt, str):
        raise ValueError("Recipe prompt is invalid.")
    clean = prompt.strip()
    if (
        not clean
        or len(clean) > MAX_RECIPE_PROMPT_CHARS
        or any(ord(character) < 32 and character not in "\n\r\t" for character in clean)
    ):
        raise ValueError("Recipe prompt is invalid.")
    return clean


def _retry_content(
    prompt: str,
    attempt: int,
    validation_reason: str | None,
) -> str:
    if type(attempt) is not int or not 0 <= attempt <= LOCAL_MAX_RETRIES:
        raise ValueError("Local recipe attempt is invalid.")
    if attempt == 0:
        if validation_reason is not None:
            raise ValueError("Initial recipe attempt is invalid.")
        return prompt
    if not isinstance(validation_reason, str) or not validation_reason.strip():
        raise ValueError("Local recipe retry reason is missing.")
    reason = "".join(
        character
        for character in validation_reason.strip()[:200]
        if character.isalnum() or character in " .,:;_()-"
    ).strip()
    if not reason:
        reason = "the recipe did not pass validation"
    return (
        prompt
        + "\n\nRetry correction: the previous recipe failed because "
        + f"{reason}. Return a different corrected recipe."
    )


def _seed(
    prompt: str,
    width: int,
    height: int,
    frame_count: int,
    attempt: int,
) -> int:
    material = (
        f"{prompt}\0{width}\0{height}\0{frame_count}\0{attempt}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big") & 0x7FFF_FFFF


def build_ollama_recipe_payload(
    *,
    model_id: str,
    prompt: str,
    system_prompt: str,
    schema: dict[str, Any],
    width: int,
    height: int,
    frame_count: int,
    attempt: int,
    validation_reason: str | None,
) -> dict[str, Any]:
    """Build one production-equivalent Ollama recipe request.

    Every attempt is a fresh system/user exchange. Retries vary only the
    deterministic seed and the sanitized correction appended to the original
    user prompt.
    """

    if not isinstance(model_id, str) or not model_id:
        raise ValueError("Local recipe model is invalid.")
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ValueError("Local recipe system prompt is invalid.")
    if not isinstance(schema, dict):
        raise ValueError("Local recipe schema is invalid.")
    if any(type(value) is not int or value <= 0 for value in (width, height, frame_count)):
        raise ValueError("Local recipe dimensions are invalid.")
    clean_prompt = _clean_prompt(prompt)
    user_content = _retry_content(clean_prompt, attempt, validation_reason)
    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "format": schema,
        "options": {
            "temperature": LOCAL_TEMPERATURE,
            "seed": _seed(clean_prompt, width, height, frame_count, attempt),
            "num_predict": LOCAL_OUTPUT_TOKENS,
        },
    }


__all__ = [
    "LOCAL_MAX_RETRIES",
    "LOCAL_OUTPUT_TOKENS",
    "LOCAL_TEMPERATURE",
    "MAX_LOCAL_RESPONSE_BYTES",
    "MAX_RECIPE_PROMPT_CHARS",
    "build_ollama_recipe_payload",
]
