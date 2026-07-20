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
    "concept": {
        "default": "grok-imagine-image",
        "choices": [
            {
                "id": "grok-imagine-image",
                "label": "Imagine",
                "pricing": {
                    "input_per_image_usd_ticks": 20_000_000,
                    "output_per_1k_image_usd_ticks": 200_000_000,
                },
            },
            {
                "id": "grok-imagine-image-quality",
                "label": "Imagine Quality",
                "pricing": {
                    "input_per_image_usd_ticks": 100_000_000,
                    "output_per_1k_image_usd_ticks": 500_000_000,
                },
            },
        ],
    },
    "video": {
        "default": "grok-imagine-video-1.5",
        "choices": [
            {
                "id": "grok-imagine-video-1.5",
                "label": "Imagine Video 1.5",
                "pricing": {
                    "input_per_image_usd_ticks": 100_000_000,
                    "output_per_second_480p_usd_ticks": 800_000_000,
                },
            },
            {
                "id": "grok-imagine-video",
                "label": "Imagine Video",
                "pricing": {
                    "input_per_image_usd_ticks": 20_000_000,
                    "output_per_second_480p_usd_ticks": 500_000_000,
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
