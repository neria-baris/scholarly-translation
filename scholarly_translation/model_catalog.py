"""Secret-free model catalogue: dated list pricing and context/output limits.

Official sources checked 2026-10-05 (see audit/contracts/automation_1.md):
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://platform.claude.com/docs/en/models/sonnet-5-5/overview
- https://platform.claude.com/docs/en/models/opus-5-5/overview

Rates are standard USD list price per 1,000,000 tokens as verified on
``CATALOG_VERSION``'s date. This module performs no network call and holds
no credential; it only resolves known (provider, model) pairs' rates/limits
and turns already-observed provider usage into a cost estimate. It never
decides whether a call is authorized -- that remains ``runtime_controls.py``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

CATALOG_VERSION = "model-catalog-2026-10-05"

# OpenAI gpt-6 family: above this many input tokens in one request, every
# input/cache rate doubles and the output rate is multiplied by 1.5 for the
# *entire* request (not just the tokens past the threshold).
LONG_CONTEXT_INPUT_TOKENS = 272_000
LONG_CONTEXT_INPUT_MULTIPLIER = 2.0
LONG_CONTEXT_OUTPUT_MULTIPLIER = 1.5

# Conservative, explicitly labelled default for a model with no catalogue
# entry and no caller-supplied custom rate: never silently priced like a
# known cheap model, and cache usage gets no discount by default.
UNKNOWN_MODEL_RATES = {"input": 4.0, "output": 20.0, "cached": 4.0, "cache_write": 4.0}

_USAGE_FIELDS = {"input", "output", "cached", "cache_write", "cache_write_1h", "reasoning"}
_PRICING_FIELDS = {"input", "output", "cached", "cache_write", "cache_write_1h"}


class ModelCatalogError(ValueError):
    """Malformed custom pricing or usage; never a network or credential error."""


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    context_window: int
    max_output_tokens: int
    rates_per_million: dict
    reasoning_values: tuple = ()
    long_context: bool = False
    thinking_always_on: bool = False


_CATALOG = {
    ("openai", "gpt-6-luna"): ModelPricing(
        provider="openai", model="gpt-6-luna",
        context_window=1_050_000, max_output_tokens=128_000,
        rates_per_million={"input": 0.10, "output": 0.50, "cached": 0.01, "cache_write": 0.125},
        # Project default remains none; catalogue lists all documented values.
        reasoning_values=("none", "low", "medium", "high", "xhigh", "max"), long_context=True,
    ),
    ("openai", "gpt-6.1-sol"): ModelPricing(
        provider="openai", model="gpt-6.1-sol",
        context_window=1_050_000, max_output_tokens=128_000,
        rates_per_million={"input": 2.0, "output": 10.0, "cached": 0.10, "cache_write": 2.50},
        reasoning_values=("low", "medium", "high", "xhigh", "max"), long_context=True,
    ),
    ("anthropic", "claude-sonnet-5-5"): ModelPricing(
        provider="anthropic", model="claude-sonnet-5-5",
        context_window=1_000_000, max_output_tokens=128_000,
        rates_per_million={"input": 2.0, "output": 10.0, "cached": 0.20,
                            "cache_write": 2.50, "cache_write_1h": 4.0},
        reasoning_values=(), long_context=False, thinking_always_on=False,
    ),
    ("anthropic", "claude-opus-5-5"): ModelPricing(
        provider="anthropic", model="claude-opus-5-5",
        context_window=1_000_000, max_output_tokens=128_000,
        rates_per_million={"input": 4.0, "output": 20.0, "cached": 0.20,
                            "cache_write": 5.0, "cache_write_1h": 8.0},
        reasoning_values=(), long_context=False, thinking_always_on=True,
    ),
}


def known_models(provider=None):
    """Sorted model identifiers in the catalogue, optionally filtered by provider."""
    return sorted(model for prov, model in _CATALOG if provider is None or prov == provider)


def resolve(provider, model):
    """The catalogued ``ModelPricing`` for (provider, model), or ``None`` if unknown."""
    return _CATALOG.get((provider, model))


def _finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_custom_pricing(rates):
    """Validate an explicit custom-rate mapping.

    ``input``/``output`` are required; ``cached``/``cache_write``/
    ``cache_write_1h`` are optional and default to the input rate (no cache
    discount), matching this contract's labelled conservative default for an
    unrecognized model. Every rate must be a finite, nonnegative number.
    """
    if not isinstance(rates, dict):
        raise ModelCatalogError("custom pricing rates must be an object")
    unknown = set(rates) - _PRICING_FIELDS
    if unknown:
        raise ModelCatalogError(f"unknown pricing fields: {sorted(unknown)}")
    missing = {"input", "output"} - set(rates)
    if missing:
        raise ModelCatalogError(f"custom pricing rates missing required fields: {sorted(missing)}")
    for key, value in rates.items():
        if not _finite_nonnegative(value):
            raise ModelCatalogError(f"custom pricing rate {key!r} must be a finite nonnegative number")
    resolved = dict(rates)
    resolved.setdefault("cached", resolved["input"])
    resolved.setdefault("cache_write", resolved["input"])
    return resolved


def unknown_model_pricing():
    """Explicit conservative assumption for a model with no catalogue entry and
    no caller-supplied custom rates. Callers must label the resulting estimate
    accordingly (see ``estimate_cost``'s ``basis``), never present it as exact."""
    return dict(UNKNOWN_MODEL_RATES)


def _valid_usage(value):
    if not isinstance(value, dict) or "input" not in value or "output" not in value:
        return None
    if set(value) - _USAGE_FIELDS:
        return None
    if any(type(v) is not int or v < 0 for v in value.values()):
        return None
    if value.get("reasoning", 0) > value["output"]:
        return None
    return value


def estimate_cost(provider, model, token_usage, *, custom_rates=None):
    """List-price cost estimate from already-observed usage.

    Returns ``None`` if ``token_usage`` is missing/malformed (never guesses a
    charge). Otherwise returns a dict: ``cost_usd``, ``basis``
    (``"catalog"``, ``"custom"`` or ``"unknown_conservative"``),
    ``catalog_version``, ``rates_per_million`` (the rates actually applied,
    after any long-context multiplier) and ``long_context_applied``.

    Reasoning tokens are already included in ``output`` by every supported
    provider's usage shape (never charged twice); this function only sums
    the fields it is given.
    """
    usage = _valid_usage(token_usage)
    if usage is None:
        return None
    entry = resolve(provider, model)
    if custom_rates is not None:
        rates = validate_custom_pricing(custom_rates)
        basis = "custom"
        long_context = False
    elif entry is not None:
        rates = entry.rates_per_million
        basis = "catalog"
        long_context = entry.long_context
    else:
        rates = unknown_model_pricing()
        basis = "unknown_conservative"
        long_context = False

    input_tokens = usage.get("input", 0)
    output_tokens = usage.get("output", 0)
    cached = usage.get("cached", 0)
    cache_write = usage.get("cache_write", 0)
    cache_write_1h = usage.get("cache_write_1h", 0)
    if cached + cache_write + cache_write_1h > input_tokens:
        return None
    uncached = input_tokens - cached - cache_write - cache_write_1h

    apply_long = bool(long_context and input_tokens > LONG_CONTEXT_INPUT_TOKENS)
    input_mult = LONG_CONTEXT_INPUT_MULTIPLIER if apply_long else 1.0
    output_mult = LONG_CONTEXT_OUTPUT_MULTIPLIER if apply_long else 1.0
    effective_rates = {
        "input": rates["input"] * input_mult,
        "output": rates["output"] * output_mult,
        "cached": rates["cached"] * input_mult,
        "cache_write": rates["cache_write"] * input_mult,
        "cache_write_1h": rates.get("cache_write_1h", rates["cache_write"]) * input_mult,
    }
    cost = (uncached * effective_rates["input"]
            + cached * effective_rates["cached"]
            + cache_write * effective_rates["cache_write"]
            + cache_write_1h * effective_rates["cache_write_1h"]
            + output_tokens * effective_rates["output"]) / 1_000_000
    return {
        "cost_usd": cost, "basis": basis, "catalog_version": CATALOG_VERSION,
        "rates_per_million": effective_rates, "long_context_applied": apply_long,
    }
