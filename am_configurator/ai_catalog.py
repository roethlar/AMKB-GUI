"""Curated xAI model choices and dated USD-tick price estimates.

The catalog is deliberately small: these are the only model IDs the Settings
API accepts. Monetary values use integer USD ticks (10^10 ticks per dollar),
never binary floating point. They are dated estimates rather than billing
truth; provider-reported usage remains authoritative when available.
"""
from __future__ import annotations

import copy
from typing import Any


CATALOG_SCHEMA_VERSION = 1
PRICING_AS_OF = "2026-07-20"
USD_TICKS_PER_DOLLAR = 10_000_000_000
PRIVACY_DISCLOSURE_VERSION = "2026-07-20-xai-v1"
# Conservative upper estimate for the bounded prompt, shared system guidance,
# and strict schema. Tokens cannot outnumber the request's bounded UTF-8 bytes.
RECIPE_API_MAX_INPUT_TOKENS = 32_768
RECIPE_API_MAX_OUTPUT_TOKENS = 1536


MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "interpreter": {
        "default": "grok-4.5",
        "choices": [
            {
                "id": "grok-4.5",
                "label": "Grok 4.5",
                "pricing": {
                    "input_per_million_tokens_usd_ticks": 20_000_000_000,
                    "output_per_million_tokens_usd_ticks": 60_000_000_000,
                },
            },
            {
                "id": "grok-4.3",
                "label": "Grok 4.3",
                "pricing": {
                    "input_per_million_tokens_usd_ticks": 12_500_000_000,
                    "output_per_million_tokens_usd_ticks": 25_000_000_000,
                },
            },
        ],
    },
}

DEFAULT_MODELS: dict[str, str] = {
    role: str(role_data["default"]) for role, role_data in MODEL_CATALOG.items()
}
MODEL_IDS: dict[str, tuple[str, ...]] = {
    role: tuple(str(choice["id"]) for choice in role_data["choices"])
    for role, role_data in MODEL_CATALOG.items()
}

CATALOG: dict[str, Any] = {
    "schema_version": CATALOG_SCHEMA_VERSION,
    "pricing_as_of": PRICING_AS_OF,
    "usd_ticks_per_dollar": USD_TICKS_PER_DOLLAR,
    "roles": MODEL_CATALOG,
}


def catalog_view() -> dict[str, Any]:
    """Return a JSON-safe copy so callers cannot mutate the canonical catalog."""
    return copy.deepcopy(CATALOG)


def validate_model(role: str, model_id: object) -> str:
    """Return a curated model ID or raise a value-safe ``ValueError``."""
    if role not in MODEL_IDS:
        raise ValueError(f"unknown model role {role!r}")
    if not isinstance(model_id, str) or model_id not in MODEL_IDS[role]:
        # Do not interpolate arbitrary request values: malformed values may
        # contain secrets supplied by a confused client.
        raise ValueError(f"unknown {role} model")
    return model_id


def recipe_max_cost_usd_ticks(provider: str, model_id: object) -> int:
    """Return the dated worst-case recipe request estimate in integer ticks."""

    if provider != "xai":
        raise ValueError("unknown recipe API provider")
    normalized = validate_model("interpreter", model_id)
    choice = next(
        item
        for item in MODEL_CATALOG["interpreter"]["choices"]
        if item["id"] == normalized
    )
    pricing = choice["pricing"]
    input_ticks = (
        RECIPE_API_MAX_INPUT_TOKENS
        * pricing["input_per_million_tokens_usd_ticks"]
        + 999_999
    ) // 1_000_000
    output_ticks = (
        RECIPE_API_MAX_OUTPUT_TOKENS
        * pricing["output_per_million_tokens_usd_ticks"]
        + 999_999
    ) // 1_000_000
    return int(input_ticks + output_ticks)
