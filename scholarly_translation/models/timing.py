"""Wall-time planning estimate for provider calls: a hypothesis, not a provider promise.

Each profile is (overhead seconds, seconds per 1000 input tokens, seconds per 1000
output tokens incl. reasoning), fitted by least squares on 2026-10-15 to the
latency of completed calls in the local ledgers against their metered usage:
gpt-6-luna 3364 calls (about 118 output tokens/s), gpt-6.1-sol 166 calls (about 67/s).
Calls in a job run one after another, so a job's time is the sum of its calls.

The output share of a planned call's cap was calibrated on the same date against
eight completed "checked" jobs: their whole provider time (passes, rechecks and
corrections) equals the planned first passes at 6%-34% of their output caps,
median 18%-20%. Rechecks and corrections are therefore folded into that share.
"""
from __future__ import annotations

TIMING_VERSION = "2026-10-15"
PROFILES = {
    "gpt-6-luna": (0.0, 0.03, 8.5),
    "gpt-6.1-sol": (3.5, 0.13, 15.0),
}
# An unmeasured model is assumed to be as slow as the slowest measured profile.
DEFAULT_PROFILE = PROFILES["gpt-6.1-sol"]
OUTPUT_SHARE = {"low": .08, "expected": .2, "high": .35}


def call_seconds(provider_type, model, input_tokens, output_tokens):
    """Expected wall seconds of one provider call; a mock call takes none."""
    if provider_type == "mock":
        return 0.0
    overhead, per_input, per_output = PROFILES.get(model, DEFAULT_PROFILE)
    return overhead + per_input * input_tokens / 1000 + per_output * output_tokens / 1000


def planned_seconds(provider_type, model, input_tokens, output_cap):
    """Low/expected/high wall seconds of a planned first pass, its share of
    rechecks and corrections included."""
    return {name: call_seconds(provider_type, model, input_tokens, output_cap * share)
            for name, share in OUTPUT_SHARE.items()}
