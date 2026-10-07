"""Local review output planning: answer allowance plus reasoning headroom.

Headroom is an experimental planning assumption, not a provider guarantee.
Callers pass original model capabilities, never an already resolved call cap.
"""
from .model_catalog import resolve

REVIEW_CAP_VERSION = 1
REASONING_HEADROOM = {
    "none": 0, "low": 8192, "medium": 16384, "high": 32768,
    "xhigh": 49152, "max": 65536,
}


def review_reasoning_headroom(selection):
    capabilities = getattr(selection, "capabilities", None)
    effort = getattr(capabilities, "reasoning", None)
    entry = resolve("openai", getattr(selection, "model", ""))
    if effort is None:
        effort = entry.reasoning_values[0] if entry and entry.reasoning_values else "none"
    if effort not in REASONING_HEADROOM:
        raise ValueError("unsupported review reasoning effort")
    if entry and effort not in entry.reasoning_values:
        raise ValueError("unsupported review reasoning effort for model")
    return REASONING_HEADROOM[effort]


def review_output_cap(selection, answer_tokens, fallback_limit=4096):
    capabilities = getattr(selection, "capabilities", None)
    declared = getattr(capabilities, "max_output_tokens", None)
    headroom = review_reasoning_headroom(selection)
    # The fallback is a legacy answer bound, not a model limit on reasoning.
    entry = resolve("openai", getattr(selection, "model", ""))
    limit = declared or (entry.max_output_tokens if headroom and entry else fallback_limit)
    if entry:
        limit = min(limit, entry.max_output_tokens)
    answer = min(answer_tokens, limit)
    total = answer + headroom
    if total > limit:
        raise ValueError("review answer and reasoning allowance exceed model output capacity")
    return total
