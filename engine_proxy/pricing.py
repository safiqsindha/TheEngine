"""Anthropic API pricing as of November 2025.

Prices are USD per million tokens. Cache writes cost 1.25x the input rate;
cache reads cost 0.10x the input rate (90% discount).

Update this file when Anthropic publishes new pricing or releases a new
model family. Unknown models default to Sonnet rates so we never undercharge.
"""

# USD per 1M tokens
PRICING = {
    "claude-haiku-4-5":   {"input": 1.00,  "output":  5.00},
    "claude-sonnet-4-5":  {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-opus-4-5":    {"input": 15.00, "output": 75.00},
    "claude-opus-4-6":    {"input": 15.00, "output": 75.00},
}

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

# Fallback when an unrecognized model is requested. Sonnet rates ensure
# we never undercharge by accident.
FALLBACK_PRICES = PRICING["claude-sonnet-4-5"]


def normalize_model(model: str) -> str:
    """Strip the optional date suffix from a model id.

    "claude-haiku-4-5-20251001" -> "claude-haiku-4-5"
    """
    if not model:
        return ""
    # Direct hit
    if model in PRICING:
        return model
    # Strip trailing -YYYYMMDD if present
    if len(model) > 9 and model[-9] == "-" and model[-8:].isdigit():
        base = model[:-9]
        if base in PRICING:
            return base
    # Prefix match (handles unforeseen suffixes)
    for known in PRICING:
        if model.startswith(known):
            return known
    return model


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute the USD cost of a single Anthropic API request from token counts."""
    base = normalize_model(model)
    prices = PRICING.get(base, FALLBACK_PRICES)

    in_per_token = prices["input"] / 1_000_000
    out_per_token = prices["output"] / 1_000_000

    cost = (
        input_tokens * in_per_token
        + output_tokens * out_per_token
        + cache_creation_tokens * in_per_token * CACHE_WRITE_MULTIPLIER
        + cache_read_tokens * in_per_token * CACHE_READ_MULTIPLIER
    )
    return cost
