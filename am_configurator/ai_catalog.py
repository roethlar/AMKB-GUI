"""Curated API-provider and model metadata for procedural lighting recipes.

Only provider IDs and model IDs in this module are accepted by Settings. Money
uses integer USD ticks (10^10 ticks per dollar), never binary floating point.
Pricing is optional dated estimate metadata rather than billing truth.
"""
from __future__ import annotations

import copy
from typing import Any


CATALOG_SCHEMA_VERSION = 2
PRICING_AS_OF = "2026-07-20"
ANTHROPIC_PRICING_AS_OF = "2026-07-27"
OPENAI_PRICING_AS_OF = "2026-07-27"
GEMINI_PRICING_AS_OF = "2026-07-27"
MOONSHOT_PRICING_AS_OF = "2026-07-27"
USD_TICKS_PER_DOLLAR = 10_000_000_000
RECIPE_API_MAX_INPUT_TOKENS = 32_768
RECIPE_API_MAX_OUTPUT_TOKENS = 1536

API_PROVIDER_IDS = (
    "xai",
    "anthropic",
    "openai",
    "gemini",
    "moonshot",
    "deepseek",
)
PROVIDER_ENVIRONMENT_VARIABLES = {
    "xai": "XAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
PROVIDER_DISCLOSURE_VERSIONS = {
    provider: f"2026-07-27-{provider}-v1" for provider in API_PROVIDER_IDS
}
# Preserve the already-acknowledged xAI disclosure across settings v5 -> v6.
PROVIDER_DISCLOSURE_VERSIONS["xai"] = "2026-07-20-xai-v1"
PRIVACY_DISCLOSURE_VERSION = PROVIDER_DISCLOSURE_VERSIONS["xai"]

_XAI_MODELS = [
    {
        "id": "grok-4.5",
        "label": "Grok 4.5",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 20_000_000_000,
            "output_per_million_tokens_usd_ticks": 60_000_000_000,
        },
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
    },
    {
        "id": "grok-4.3",
        "label": "Grok 4.3",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 12_500_000_000,
            "output_per_million_tokens_usd_ticks": 25_000_000_000,
        },
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
    },
]

# Verified 2026-07-27 against Anthropic's first-party model and pricing tables:
# https://platform.claude.com/docs/en/about-claude/models/overview
# https://platform.claude.com/docs/en/about-claude/pricing
_ANTHROPIC_MODELS = [
    {
        "id": "claude-sonnet-5",
        "label": "Claude Sonnet 5",
        "pricing": {
            # Introductory first-party price through 2026-08-31.
            "input_per_million_tokens_usd_ticks": 20_000_000_000,
            "output_per_million_tokens_usd_ticks": 100_000_000_000,
        },
        "pricing_as_of": ANTHROPIC_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    },
    {
        "id": "claude-opus-5",
        "label": "Claude Opus 5",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 50_000_000_000,
            "output_per_million_tokens_usd_ticks": 250_000_000_000,
        },
        "pricing_as_of": ANTHROPIC_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    },
]

# Verified 2026-07-27 against OpenAI's current resolver, model pages, and
# standard token pricing:
# https://developers.openai.com/api/docs/guides/latest-model
# https://developers.openai.com/api/docs/models/gpt-5.6-sol
# https://developers.openai.com/api/docs/models/gpt-5.6-terra
# https://developers.openai.com/api/docs/pricing
_OPENAI_MODELS = [
    {
        "id": "gpt-5.6-sol",
        "label": "GPT-5.6 Sol",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 50_000_000_000,
            "output_per_million_tokens_usd_ticks": 300_000_000_000,
        },
        "pricing_as_of": OPENAI_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    },
    {
        "id": "gpt-5.6-terra",
        "label": "GPT-5.6 Terra",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 25_000_000_000,
            "output_per_million_tokens_usd_ticks": 150_000_000_000,
        },
        "pricing_as_of": OPENAI_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    },
]

# Verified 2026-07-27 against Google's first-party stable-model, thinking,
# structured-output, Interactions API, and standard paid-tier pricing pages:
# https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash
# https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
# https://ai.google.dev/gemini-api/docs/thinking
# https://ai.google.dev/gemini-api/docs/structured-output
# https://ai.google.dev/api/interactions-api
# https://ai.google.dev/gemini-api/docs/pricing
_GEMINI_MODELS = [
    {
        "id": "gemini-3.6-flash",
        "label": "Gemini 3.6 Flash",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 15_000_000_000,
            "output_per_million_tokens_usd_ticks": 75_000_000_000,
        },
        "pricing_as_of": GEMINI_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    },
    {
        "id": "gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash-Lite",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 3_000_000_000,
            "output_per_million_tokens_usd_ticks": 25_000_000_000,
        },
        "pricing_as_of": GEMINI_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "minimal",
    },
]

# Verified 2026-07-27 against Moonshot's first-party Kimi K3, Chat
# Completions, JSON mode, parameter, and standard pricing pages:
# https://platform.kimi.ai/docs/guide/kimi-k3-quickstart.md
# https://platform.kimi.ai/docs/api/chat.md
# https://platform.kimi.ai/docs/guide/use-json-mode-feature-of-kimi-api
# https://platform.kimi.ai/docs/api/models-overview
# https://platform.kimi.ai/docs/pricing/chat-k3
_KIMI_MODELS = [
    {
        "id": "kimi-k3",
        "label": "Kimi K3",
        "pricing": {
            "input_per_million_tokens_usd_ticks": 30_000_000_000,
            "cached_input_per_million_tokens_usd_ticks": 3_000_000_000,
            "output_per_million_tokens_usd_ticks": 150_000_000_000,
        },
        "pricing_as_of": MOONSHOT_PRICING_AS_OF,
        "max_output_tokens": RECIPE_API_MAX_OUTPUT_TOKENS,
        "reasoning_effort": "max",
    },
]


def _provider(
    label: str,
    structured_output: str,
    *,
    default_model: str | None = None,
    models: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "default_model": default_model,
        "models": [] if models is None else models,
        "structured_output": structured_output,
    }


PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "xai": _provider(
        "xAI",
        "json_schema",
        default_model="grok-4.5",
        models=_XAI_MODELS,
    ),
    "anthropic": _provider(
        "Anthropic",
        "json_schema",
        default_model="claude-sonnet-5",
        models=_ANTHROPIC_MODELS,
    ),
    "openai": _provider(
        "OpenAI",
        "json_schema",
        default_model="gpt-5.6-sol",
        models=_OPENAI_MODELS,
    ),
    "gemini": _provider(
        "Gemini",
        "json_schema",
        default_model="gemini-3.6-flash",
        models=_GEMINI_MODELS,
    ),
    "moonshot": _provider(
        "Kimi / Moonshot",
        "json_object",
        default_model="kimi-k3",
        models=_KIMI_MODELS,
    ),
    "deepseek": _provider("DeepSeek", "json_object"),
}

# Temporary compatibility aliases for the existing xAI adapter. Provider
# adapters migrate to the provider-keyed helpers as they land.
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "interpreter": {
        "default": "grok-4.5",
        "choices": _XAI_MODELS,
    }
}
DEFAULT_MODELS: dict[str, str] = {"interpreter": "grok-4.5"}
MODEL_IDS: dict[str, tuple[str, ...]] = {
    "interpreter": tuple(str(choice["id"]) for choice in _XAI_MODELS)
}

CATALOG: dict[str, Any] = {
    "schema_version": CATALOG_SCHEMA_VERSION,
    "pricing_as_of": PRICING_AS_OF,
    "providers": {
        provider: {
            **metadata,
            "disclosure_version": PROVIDER_DISCLOSURE_VERSIONS[provider],
        }
        for provider, metadata in PROVIDER_CATALOG.items()
    },
    "usd_ticks_per_dollar": USD_TICKS_PER_DOLLAR,
}


def catalog_view() -> dict[str, Any]:
    """Return a JSON-safe copy so callers cannot mutate the canonical catalog."""

    return copy.deepcopy(CATALOG)


def validate_api_provider(provider: object) -> str:
    if not isinstance(provider, str) or provider not in PROVIDER_CATALOG:
        raise ValueError("unknown recipe API provider")
    return provider


def provider_disclosure_version(provider: object) -> str:
    normalized = validate_api_provider(provider)
    return PROVIDER_DISCLOSURE_VERSIONS[normalized]


def provider_environment_variable(provider: object) -> str:
    normalized = validate_api_provider(provider)
    return PROVIDER_ENVIRONMENT_VARIABLES[normalized]


def provider_model_ids(provider: object) -> tuple[str, ...]:
    normalized = validate_api_provider(provider)
    return tuple(
        str(model["id"]) for model in PROVIDER_CATALOG[normalized]["models"]
    )


def validate_provider_model(
    provider: object,
    model_id: object,
    *,
    allow_none: bool = False,
) -> str | None:
    normalized_provider = validate_api_provider(provider)
    if model_id is None and allow_none:
        return None
    if (
        not isinstance(model_id, str)
        or model_id not in provider_model_ids(normalized_provider)
    ):
        raise ValueError("unknown API model")
    return model_id


def provider_model_metadata(provider: object, model_id: object) -> dict[str, Any]:
    normalized_provider = validate_api_provider(provider)
    normalized_model = validate_provider_model(normalized_provider, model_id)
    model = next(
        choice
        for choice in PROVIDER_CATALOG[normalized_provider]["models"]
        if choice["id"] == normalized_model
    )
    return copy.deepcopy(model)


def validate_model(role: str, model_id: object) -> str:
    """Compatibility validator for the existing xAI recipe adapter."""

    if role != "interpreter":
        raise ValueError(f"unknown model role {role!r}")
    normalized = validate_provider_model("xai", model_id)
    assert isinstance(normalized, str)
    return normalized


def recipe_max_cost_usd_ticks(
    provider: str,
    model_id: object,
) -> int | None:
    """Return the dated worst-case estimate, or ``None`` when unavailable."""

    choice = provider_model_metadata(provider, model_id)
    pricing = choice.get("pricing")
    if not isinstance(pricing, dict):
        return None
    return recipe_usage_cost_usd_ticks(
        provider,
        model_id,
        input_tokens=RECIPE_API_MAX_INPUT_TOKENS,
        output_tokens=int(choice["max_output_tokens"]),
    )


def recipe_usage_cost_usd_ticks(
    provider: str,
    model_id: object,
    *,
    input_tokens: object,
    output_tokens: object,
    cached_input_tokens: object = 0,
) -> int | None:
    """Price exact reported token counts with the catalog's dated estimate."""

    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
        or isinstance(cached_input_tokens, bool)
        or not isinstance(cached_input_tokens, int)
        or cached_input_tokens < 0
        or cached_input_tokens > input_tokens
    ):
        raise ValueError("provider token usage must be non-negative integers")
    choice = provider_model_metadata(provider, model_id)
    pricing = choice.get("pricing")
    if not isinstance(pricing, dict):
        return None
    regular_input_rate = pricing["input_per_million_tokens_usd_ticks"]
    cached_input_rate = pricing.get(
        "cached_input_per_million_tokens_usd_ticks",
        regular_input_rate,
    )
    input_ticks = (
        (input_tokens - cached_input_tokens) * regular_input_rate
        + cached_input_tokens * cached_input_rate
        + 999_999
    ) // 1_000_000
    output_ticks = (
        output_tokens * pricing["output_per_million_tokens_usd_ticks"]
        + 999_999
    ) // 1_000_000
    return int(input_ticks + output_ticks)
