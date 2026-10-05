"""Gate 6: bounded provider-independent diagnostic request/result boundary.

Provider plumbing only: a mock adapter (no network) and an optional OpenAI
Responses-API adapter used for a single bounded live probe. This is not the
Gate-7 translation workflow, not translation memory, and establishes no
model-quality claim. The OpenAI SDK is imported only inside the adapter that
needs it, never at module import time, so this module loads with no
dependency installed.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import model_catalog
from .model_config import ModelConfigError, ProviderDefinition

SUPPORTED_PROVIDERS = {"mock", "openai"}
SUPPORTED_MODELS = {
    "mock": {"mock-diagnostic-1"},
    "openai": {"gpt-6-luna"},
}

PROFILE_ID = "scholarly"
SYNTHETIC_MARKER = "GATE6-DIAGNOSTIC-SYNTHETIC"
TARGET_LANGUAGE = "he"
MAX_SOURCE_TEXT_CHARS = 2000

MOCK_PLACEHOLDER_PREFIX = "[GATE6-MOCK-PLACEHOLDER]"

PRICING_VERSION = "2026-09-30"
# USD per 1,000,000 tokens, standard list rates as verified 2026-09-30.
RATES_PER_MILLION = {
    "input": 0.10,
    "cached": 0.01,
    "cache_write": 0.125,
    "output": 0.50,
}

OPENAI_MAX_OUTPUT_TOKENS = 256
OPENAI_TIMEOUT_SECONDS = 20.0
OPENAI_MAX_RETRIES = 0

# Gate-7+ text-generation calls (translation/review/QA) are not the bounded
# Gate-6 diagnostic probe: they default to a longer configurable timeout.
# OPENAI_TIMEOUT_SECONDS/OPENAI_MAX_OUTPUT_TOKENS above remain the diagnostic
# probe's own fixed 256/20s behavior and are never changed by this default.
TEXT_GENERATION_TIMEOUT_SECONDS = 180.0


def estimate_model_cost(provider, model, token_usage, custom_rates=None):
    """Model-aware list-price estimate, or "not_metered" if usage is missing/invalid.

    Drop-in replacement for the legacy, Luna-rate-only `compute_estimate` for
    any provider/model: resolves `model_catalog.py`'s dated rates for a known
    model, an explicit `custom_rates` override, or its labelled conservative
    unknown-model assumption -- never silently reusing another model's rate.
    """
    result = model_catalog.estimate_cost(provider, model, token_usage, custom_rates=custom_rates)
    return "not_metered" if result is None else result["cost_usd"]


class RequestValidationError(ValueError):
    """Raised for a malformed or unsupported diagnostic request.

    Never includes the request's source text in the message.
    """


class OpenAIConfigurationError(RuntimeError):
    """Local setup problem (missing key or SDK) detected before any network call."""


@dataclass(frozen=True)
class DiagnosticRequest:
    """Schema-1 diagnostic request. Not a Gate-7 translation job."""

    request_id: str
    profile_id: str
    marker: str
    source_language: str
    target_language: str
    source_text: str
    source_sha256: str
    prompt_version: str
    config_version: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        errors = []
        if not isinstance(self.request_id, str) or not self.request_id:
            errors.append("request_id must be a nonempty string")
        if self.profile_id != PROFILE_ID:
            errors.append(f"profile_id must be {PROFILE_ID!r}")
        if self.marker != SYNTHETIC_MARKER:
            errors.append(f"marker must be {SYNTHETIC_MARKER!r}")
        if not isinstance(self.source_language, str) or not self.source_language:
            errors.append("source_language must be a nonempty string")
        if self.target_language != TARGET_LANGUAGE:
            errors.append(f"target_language must be {TARGET_LANGUAGE!r}")
        if not isinstance(self.source_text, str) or not self.source_text:
            errors.append("source_text must be a nonempty string")
        elif len(self.source_text) > MAX_SOURCE_TEXT_CHARS:
            errors.append("source_text exceeds bounded length")
        if not isinstance(self.source_sha256, str) or len(self.source_sha256) != 64:
            errors.append("source_sha256 must be a 64-character hex string")
        elif isinstance(self.source_text, str):
            expected = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
            if self.source_sha256.lower() != expected:
                errors.append("source_sha256 does not match source_text")
        if not isinstance(self.prompt_version, str) or not self.prompt_version:
            errors.append("prompt_version must be a nonempty string")
        if not isinstance(self.config_version, str) or not self.config_version:
            errors.append("config_version must be a nonempty string")
        if not isinstance(self.provider, str) or self.provider not in SUPPORTED_PROVIDERS:
            errors.append(f"provider is not supported; allowed: {sorted(SUPPORTED_PROVIDERS)}")
        else:
            allowed_models = SUPPORTED_MODELS[self.provider]
            if not isinstance(self.model, str) or self.model not in allowed_models:
                errors.append(f"model is not supported for provider; allowed: {sorted(allowed_models)}")
        if errors:
            raise RequestValidationError("; ".join(errors))

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "stage": "provider-diagnostic-request@1",
            "request_id": self.request_id,
            "profile_id": self.profile_id,
            "marker": self.marker,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "source_sha256": self.source_sha256,
            "prompt_version": self.prompt_version,
            "config_version": self.config_version,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass(frozen=True)
class DiagnosticResult:
    """Schema-1 diagnostic result. Never translation memory or a final translation."""

    status: str
    profile_id: str
    request_id: str
    provider: str
    model: str
    prompt_version: str
    config_version: str
    duration_seconds: float
    response_text: Optional[str] = None
    token_usage: object = "not_metered"
    pricing_version: str = PRICING_VERSION
    estimated_cost_usd: object = "not_metered"
    actual_charge: str = "unknown"
    approved: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "stage": "provider-diagnostic-result@1",
            "status": self.status,
            "profile_id": self.profile_id,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "config_version": self.config_version,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "response_text": self.response_text,
            "token_usage": self.token_usage,
            "pricing_version": self.pricing_version,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_charge": self.actual_charge,
            "approved": self.approved,
            "error": self.error,
        }


def compute_estimate(token_usage: object, pricing_version: str = PRICING_VERSION) -> object:
    """List-price estimate from observed usage, or "not_metered" if usage is missing/invalid.

    Never invents a charge: any non-dict, missing, or non-numeric/negative field
    causes a safe "not_metered" result rather than a guessed cost.
    """
    if pricing_version != PRICING_VERSION:
        return "not_metered"
    if not isinstance(token_usage, dict) or not token_usage:
        return "not_metered"
    totals = {}
    for key in ("input", "output", "cached", "cache_write"):
        if key in ("input", "output") and key not in token_usage:
            return "not_metered"
        value = token_usage.get(key, 0)
        if type(value) is not int or value < 0:
            return "not_metered"
        totals[key] = value
    if totals["cached"] + totals["cache_write"] > totals["input"]:
        return "not_metered"
    uncached = totals["input"] - totals["cached"] - totals["cache_write"]
    return (
        uncached * RATES_PER_MILLION["input"]
        + totals["cached"] * RATES_PER_MILLION["cached"]
        + totals["cache_write"] * RATES_PER_MILLION["cache_write"]
        + totals["output"] * RATES_PER_MILLION["output"]
    ) / 1_000_000


class DiagnosticAdapter:
    """Shared adapter contract: mock and OpenAI return the same result shape."""

    def run(self, request: DiagnosticRequest) -> DiagnosticResult:
        raise NotImplementedError


class MockDiagnosticAdapter(DiagnosticAdapter):
    """No network, no secret needed. Deterministic, conspicuous, non-billed."""

    def run(self, request: DiagnosticRequest) -> DiagnosticResult:
        if not isinstance(request, DiagnosticRequest) or request.provider != "mock" or request.model != "mock-diagnostic-1":
            raise RequestValidationError("mock adapter requires a mock diagnostic request")
        start = time.monotonic()
        text = f"{MOCK_PLACEHOLDER_PREFIX} ({request.target_language}) {request.source_text}"
        duration = time.monotonic() - start
        return DiagnosticResult(
            status="mock_placeholder",
            profile_id=request.profile_id,
            request_id=request.request_id,
            provider=request.provider,
            model=request.model,
            prompt_version=request.prompt_version,
            config_version=request.config_version,
            duration_seconds=duration,
            response_text=text,
            token_usage="not_metered",
            estimated_cost_usd="not_metered",
            actual_charge="not_metered",
            approved=False,
        )


def _extract_output_text(response) -> Optional[str]:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text
    return None


def _extract_usage(response) -> object:
    usage = getattr(response, "usage", None)
    if usage is None:
        return "not_metered"
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if type(input_tokens) is not int or type(output_tokens) is not int or input_tokens < 0 or output_tokens < 0:
        return "not_metered"
    result = {"input": input_tokens, "output": output_tokens}
    input_details = getattr(usage, "input_tokens_details", None)
    cached = getattr(input_details, "cached_tokens", None) if input_details is not None else None
    if cached is not None and (type(cached) is not int or cached < 0):
        return 'not_metered'
    if type(cached) is int:
        result["cached"] = cached
    cache_write = getattr(input_details, "cache_write_tokens", None) if input_details is not None else None
    if cache_write is not None and (type(cache_write) is not int or cache_write < 0):
        return 'not_metered'
    if type(cache_write) is int:
        result["cache_write"] = cache_write
    output_details = getattr(usage, "output_tokens_details", None)
    reasoning = getattr(output_details, "reasoning_tokens", None) if output_details is not None else None
    if reasoning is not None and (type(reasoning) is not int or reasoning < 0):
        return 'not_metered'
    if type(reasoning) is int:
        result["reasoning"] = reasoning
    if compute_estimate(result) == "not_metered" or ("reasoning" in result and not 0 <= result["reasoning"] <= output_tokens):
        return "not_metered"
    return result


class OpenAIDiagnosticAdapter(DiagnosticAdapter):
    """Real calls only via the official OpenAI Python SDK, imported lazily.

    A `client` may be injected (tests only) to avoid any SDK import or
    network access. Without an injected client, the SDK is imported and a
    client built only inside `run`, and only after an `OPENAI_API_KEY`
    environment variable is found; its value is never stored or logged.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    def _build_client(self):
        import os

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise OpenAIConfigurationError(
                "OPENAI_API_KEY is not set in the environment; configure it before probing openai"
            )
        try:
            import openai
        except ImportError:
            raise OpenAIConfigurationError(
                "openai SDK is not installed; install it before probing openai"
            ) from None
        return openai.OpenAI(
            api_key=api_key,
            max_retries=OPENAI_MAX_RETRIES,
            timeout=OPENAI_TIMEOUT_SECONDS,
        )

    def run(self, request: DiagnosticRequest) -> DiagnosticResult:
        if not isinstance(request, DiagnosticRequest) or request.provider != "openai" or request.model != "gpt-6-luna":
            raise RequestValidationError("openai adapter requires a gpt-6-luna diagnostic request")
        client = self._client
        if client is None:
            client = self._build_client()

        start = time.monotonic()
        try:
            response = client.responses.create(
                model=request.model,
                input=request.source_text,
                store=False,
                tools=[],
                reasoning={"effort": "none"},
                max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
            )
        except Exception:
            duration = time.monotonic() - start
            return DiagnosticResult(
                status="failed_transport",
                profile_id=request.profile_id,
                request_id=request.request_id,
                provider=request.provider,
                model=request.model,
                prompt_version=request.prompt_version,
                config_version=request.config_version,
                duration_seconds=duration,
                response_text=None,
                token_usage="not_metered",
                estimated_cost_usd="not_metered",
                actual_charge="unknown",
                approved=False,
                error="openai request failed (transport or timeout)",
            )
        duration = time.monotonic() - start

        text = _extract_output_text(response) if getattr(response, "status", None) == "completed" else None
        usage = _extract_usage(response)
        estimate = compute_estimate(usage)
        if not text:
            return DiagnosticResult(
                status="failed_empty_response",
                profile_id=request.profile_id,
                request_id=request.request_id,
                provider=request.provider,
                model=request.model,
                prompt_version=request.prompt_version,
                config_version=request.config_version,
                duration_seconds=duration,
                response_text=None,
                token_usage=usage,
                estimated_cost_usd=estimate,
                actual_charge="unknown",
                approved=False,
                error="model response was incomplete or empty",
            )

        return DiagnosticResult(
            status="completed_unapproved",
            profile_id=request.profile_id,
            request_id=request.request_id,
            provider=request.provider,
            model=request.model,
            prompt_version=request.prompt_version,
            config_version=request.config_version,
            duration_seconds=duration,
            response_text=text,
            token_usage=usage,
            estimated_cost_usd=estimate,
            actual_charge="unknown",
            approved=False,
        )


def build_adapter(provider: str, model: str, client=None) -> DiagnosticAdapter:
    """Build the adapter for a supported provider/model; never silently substitutes providers."""
    if provider not in SUPPORTED_PROVIDERS:
        raise RequestValidationError(f"provider is not supported; allowed: {sorted(SUPPORTED_PROVIDERS)}")
    allowed_models = SUPPORTED_MODELS[provider]
    if model not in allowed_models:
        raise RequestValidationError(f"model is not supported for provider; allowed: {sorted(allowed_models)}")
    if provider == "mock":
        return MockDiagnosticAdapter()
    if provider == "openai":
        return OpenAIDiagnosticAdapter(client=client)
    raise RequestValidationError("provider is not supported")


# --- Gate 7: minimal generic text-generation adapter (provider plumbing only).
#
# Receives a fully resolved prompt string from a caller (e.g. the Gate-7
# translation workflow) and returns a provider-independent result shape. This
# adapter contains no scholarly/profile branching and makes no decision about
# approval, caching or terminology.

TRANSLATION_SUPPORTED_PROVIDERS = {"mock", "openai", "anthropic", "deepseek", "openai_compatible"}
# Kept for compatibility with callers that display the offline fixture. Live
# model identifiers are deliberately not allowlisted here; they come from
# ModelConfiguration.
TRANSLATION_SUPPORTED_MODELS = {"mock": {"mock-translation-1"}}
MOCK_TRANSLATION_PLACEHOLDER_PREFIX = "[GATE7-MOCK-PLACEHOLDER-NON-HEBREW]"


@dataclass(frozen=True)
class TextGenerationResult:
    """Provider-independent result of a single text-generation call."""

    status: str  # "completed" | "mock_placeholder" | "failed_transport" | "failed_empty_response" | "failed_truncated"
    text: Optional[str]
    token_usage: object
    observed_model: Optional[str]
    duration_seconds: float
    error: Optional[str] = None
    observed_provider: Optional[str] = None


class TextGenerationAdapter:
    """Shared adapter contract: mock and OpenAI return the same result shape."""

    def generate(self, prompt_text: str, model: str) -> TextGenerationResult:
        raise NotImplementedError


class CacheablePrompt(str):
    """A plain `str` (same text, same hashing/equality/identity everywhere)
    that additionally carries an explicit stable-prefix/dynamic-suffix split
    for a provider cache breakpoint. A caller that renders a chapter-batch
    prompt as immutable source/IDs/profile/glossary (the stable prefix)
    followed by dynamic target IDs/state instructions (the suffix) builds
    this instead of a plain string; any adapter that does not know about it
    (mock, or an adapter that receives `str(prompt)`) sees exactly the same
    full prompt text with no behavior change.
    """

    def __new__(cls, stable_prefix: str, suffix: str):
        self = str.__new__(cls, stable_prefix + suffix)
        self.stable_prefix = stable_prefix
        self.suffix = suffix
        return self


class MockTextGenerationAdapter(TextGenerationAdapter):
    """No network, no secret needed. Conspicuous non-Hebrew placeholder, never a real translation."""

    def generate(self, prompt_text: str, model: str) -> TextGenerationResult:
        if model != "mock-translation-1":
            raise RequestValidationError("mock adapter requires mock-translation-1")
        start = time.monotonic()
        text = MOCK_TRANSLATION_PLACEHOLDER_PREFIX
        duration = time.monotonic() - start
        return TextGenerationResult(
            status="mock_placeholder", text=text, token_usage="not_metered",
            observed_model=model, duration_seconds=duration,
        )


class OpenAITextGenerationAdapter(TextGenerationAdapter):
    """Real calls only via the official OpenAI Python SDK, imported lazily.

    A `client` may be injected (tests only) to avoid any SDK import or
    network access. Without an injected client, the SDK is imported and a
    client built only inside `generate`, and only after an `OPENAI_API_KEY`
    environment variable is found; its value is never stored or logged.
    """

    def __init__(self, client=None, provider_definition=None, max_output_tokens=None,
                 reasoning=None, timeout=None, api_key=None, max_wall_seconds=3600) -> None:
        self._client = client
        self._provider = provider_definition or ProviderDefinition(
            "openai", "openai", "OPENAI_API_KEY", None,
        )
        self._max_output_tokens = max_output_tokens or OPENAI_MAX_OUTPUT_TOKENS
        # Per-model reasoning effort comes from the dated catalogue. `None`
        # uses project defaults (Luna none, Sol low); an unsupported value is
        # never silently sent to the provider.
        self._reasoning = reasoning
        self._timeout = TEXT_GENERATION_TIMEOUT_SECONDS if timeout is None else timeout
        # Explicit key takes precedence over the provider's env-var lookup;
        # `os.environ` is only ever read, never mutated.
        self._api_key = api_key
        self._max_wall_seconds = max_wall_seconds

    def _build_client(self):
        import os

        api_key = self._api_key
        if api_key is None:
            try:
                api_key = self._provider.require_credential(os.environ)
            except ModelConfigError as exc:
                raise OpenAIConfigurationError(str(exc)) from None
        try:
            import openai
        except ImportError:
            raise OpenAIConfigurationError(
                "openai SDK is not installed; install it before calling openai"
            ) from None
        kwargs = dict(api_key=api_key, max_retries=OPENAI_MAX_RETRIES, timeout=self._timeout)
        if self._provider.base_url:
            kwargs["base_url"] = self._provider.base_url
        return openai.OpenAI(**kwargs)

    def _reasoning_effort(self, model):
        if self._reasoning is not None:
            entry = model_catalog.resolve("openai", model)
            if entry is not None and self._reasoning not in entry.reasoning_values:
                raise RequestValidationError(f"model {model!r} does not support reasoning {self._reasoning!r}")
            return self._reasoning
        entry = model_catalog.resolve('openai', model)
        return entry.reasoning_values[0] if entry and entry.reasoning_values else None

    def generate(self, prompt_text: str, model: str) -> TextGenerationResult:
        if not isinstance(model, str) or not model.strip():
            raise RequestValidationError("model must be a nonempty configured identifier")
        # Resolved before the network try/except below: an unsupported
        # reasoning effort is a local configuration error, never silently
        # swallowed into a generic "failed_transport" result.
        reasoning_effort = self._reasoning_effort(model)
        client = self._client
        if client is None:
            client = self._build_client()

        start = time.monotonic()
        try:
            payload = dict(
                model=model,
                store=False,
                tools=[],
                max_output_tokens=self._max_output_tokens,
            )
            # Explicit OpenAI prompt caching (official `prompt_cache_options`
            # schema): only applied when the caller marked an explicit
            # stable/dynamic split via CacheablePrompt; a plain string keeps
            # the historical single opaque `input` string. No cache warming:
            # this is the same single generation call either way, just with
            # a breakpoint hint on the stable block.
            if (isinstance(prompt_text, CacheablePrompt) and prompt_text.stable_prefix
                    and model_catalog.resolve('openai', model) is not None):
                payload["input"] = [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text.stable_prefix,
                         "prompt_cache_breakpoint": {"mode": "explicit"}},
                        {"type": "input_text", "text": prompt_text.suffix},
                    ],
                }]
                payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
            else:
                payload["input"] = str(prompt_text)
            if reasoning_effort is not None:
                payload['reasoning'] = {'effort': reasoning_effort}
            if self._max_output_tokens > 8192 and callable(getattr(client.responses, 'stream', None)):
                with client.responses.stream(**payload) as stream:
                    for _event in stream:
                        if time.monotonic() - start > self._max_wall_seconds:
                            raise TimeoutError('generation wall limit')
                    response = stream.get_final_response()
            else:
                response = client.responses.create(**payload)
        except Exception:
            duration = time.monotonic() - start
            return TextGenerationResult(
                status="failed_transport", text=None, token_usage="not_metered",
                observed_model=None, duration_seconds=duration,
                error=f"{self._provider.provider_id} request failed (transport or timeout)",
                observed_provider=self._provider.provider_id,
            )
        duration = time.monotonic() - start

        response_status = getattr(response, "status", None)
        text = _extract_output_text(response)
        usage = _extract_usage(response)
        observed_model = getattr(response, "model", None)
        observed_model = observed_model if isinstance(observed_model, str) else None
        incomplete_reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        if response_status == "incomplete" and incomplete_reason == "max_output_tokens":
            return TextGenerationResult(
                status="failed_truncated", text=text, token_usage=usage,
                observed_model=observed_model, duration_seconds=duration,
                error="model response was truncated at max_output_tokens",
                observed_provider=self._provider.provider_id,
            )
        if response_status != "completed" or not text:
            return TextGenerationResult(
                status="failed_empty_response", text=None, token_usage=usage,
                observed_model=observed_model, duration_seconds=duration,
                error="model response was incomplete or empty",
                observed_provider=self._provider.provider_id,
            )
        return TextGenerationResult(
            status="completed", text=text, token_usage=usage,
            observed_model=observed_model, duration_seconds=duration,
            observed_provider=self._provider.provider_id,
        )


def _anthropic_text(response):
    content = getattr(response, "content", None)
    if not isinstance(content, (list, tuple)):
        return None
    parts = [getattr(item, "text", None) for item in content]
    text = "".join(part for part in parts if isinstance(part, str))
    return text if text.strip() else None


def _anthropic_usage(response):
    """Normalize Anthropic usage: `input` is the uncached-plus-cache total
    (uncached input_tokens + cache_read + cache_creation), never only the
    uncached figure, matching this contract's cache-aware accounting.
    `cache_write`/`cache_write_1h` separate the 5m/1h cache-creation
    breakdown when the SDK reports it; thinking tokens are already counted
    once inside `output_tokens` by the API and are never added again.
    """
    usage = getattr(response, "usage", None)
    uncached_input = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if type(uncached_input) is not int or type(output_tokens) is not int or uncached_input < 0 or output_tokens < 0:
        return "not_metered"
    cache_read = getattr(usage, "cache_read_input_tokens", None)
    if cache_read is not None and (type(cache_read) is not int or cache_read < 0):
        return 'not_metered'
    cache_read = cache_read if type(cache_read) is int and cache_read >= 0 else 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", None)
    if cache_creation is not None and (type(cache_creation) is not int or cache_creation < 0):
        return 'not_metered'
    cache_creation = cache_creation if type(cache_creation) is int and cache_creation >= 0 else 0
    breakdown = getattr(usage, "cache_creation", None)
    cache_write_1h = getattr(breakdown, "ephemeral_1h_input_tokens", None) if breakdown is not None else None
    cache_write_5m = getattr(breakdown, "ephemeral_5m_input_tokens", None) if breakdown is not None else None
    if breakdown is not None and (type(cache_write_1h) is not int or type(cache_write_5m) is not int or
                                  min(cache_write_1h, cache_write_5m) < 0 or
                                  cache_write_1h + cache_write_5m != cache_creation):
        return 'not_metered'
    if type(cache_write_1h) is int and type(cache_write_5m) is int and cache_write_1h >= 0 and cache_write_5m >= 0:
        cache_write, cache_write_1h_value = cache_write_5m, cache_write_1h
    else:
        cache_write, cache_write_1h_value = cache_creation, 0
    result = {
        "input": uncached_input + cache_read + cache_creation,
        "output": output_tokens, "cached": cache_read,
        "cache_write": cache_write,
    }
    if cache_write_1h_value:
        result["cache_write_1h"] = cache_write_1h_value
    return result


class AnthropicTextGenerationAdapter(TextGenerationAdapter):
    """Anthropic Messages adapter behind the shared result boundary."""

    def __init__(self, client=None, provider_definition=None, max_output_tokens=None,
                 timeout=None, api_key=None, max_wall_seconds=3600):
        self._client = client
        self._provider = provider_definition or ProviderDefinition(
            "anthropic", "anthropic", "ANTHROPIC_API_KEY", None,
        )
        self._max_output_tokens = max_output_tokens or OPENAI_MAX_OUTPUT_TOKENS
        self._timeout = TEXT_GENERATION_TIMEOUT_SECONDS if timeout is None else timeout
        self._api_key = api_key
        self._max_wall_seconds = max_wall_seconds

    def _build_client(self):
        import os
        api_key = self._api_key
        if api_key is None:
            try:
                api_key = self._provider.require_credential(os.environ)
            except ModelConfigError as exc:
                raise OpenAIConfigurationError(str(exc)) from None
        try:
            import anthropic
        except ImportError:
            raise OpenAIConfigurationError(
                "anthropic SDK is not installed; install it before calling anthropic"
            ) from None
        kwargs = {"api_key": api_key, "max_retries": 0, "timeout": self._timeout}
        if self._provider.base_url:
            kwargs["base_url"] = self._provider.base_url
        return anthropic.Anthropic(**kwargs)

    def generate(self, prompt_text, model):
        if not isinstance(model, str) or not model.strip():
            raise RequestValidationError("model must be a nonempty configured identifier")
        client = self._client or self._build_client()
        start = time.monotonic()
        # Explicit Anthropic prompt caching: a single user-message content
        # block list with an `ephemeral` cache_control breakpoint on the
        # stable prefix only when the caller marked one via CacheablePrompt;
        # a plain string keeps the historical single-string content.
        if isinstance(prompt_text, CacheablePrompt) and prompt_text.stable_prefix:
            content = [
                {"type": "text", "text": prompt_text.stable_prefix,
                 "cache_control": {"type": "ephemeral", "ttl": "5m"}},
                {"type": "text", "text": prompt_text.suffix},
            ]
        else:
            content = str(prompt_text)
        try:
            payload = dict(model=model, max_tokens=self._max_output_tokens,
                           messages=[{"role": "user", "content": content}])
            if self._max_output_tokens > 8192 and callable(getattr(client.messages, 'stream', None)):
                with client.messages.stream(**payload) as stream:
                    for _event in stream:
                        if time.monotonic() - start > self._max_wall_seconds:
                            raise TimeoutError('generation wall limit')
                    response = stream.get_final_message()
            else:
                response = client.messages.create(**payload)
        except Exception:
            return TextGenerationResult(
                "failed_transport", None, "not_metered", None,
                time.monotonic() - start,
                f"{self._provider.provider_id} request failed (transport or timeout)",
                self._provider.provider_id,
            )
        duration = time.monotonic() - start
        text, usage = _anthropic_text(response), _anthropic_usage(response)
        observed = getattr(response, "model", None)
        observed = observed if isinstance(observed, str) else None
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "max_tokens":
            return TextGenerationResult("failed_truncated", text, usage, observed, duration,
                                        "model response was truncated at max_tokens", self._provider.provider_id)
        if stop_reason not in (None, 'end_turn', 'stop_sequence', 'refusal'):
            return TextGenerationResult('failed_incomplete', text, usage, observed, duration,
                                        'model response did not finish a text turn', self._provider.provider_id)
        if stop_reason == "refusal":
            return TextGenerationResult("failed_empty_response", None, usage, observed, duration,
                                        "model refused to respond", self._provider.provider_id)
        if not text:
            return TextGenerationResult("failed_empty_response", None, usage, observed, duration,
                                        "model response was incomplete or empty", self._provider.provider_id)
        return TextGenerationResult("completed", text, usage, observed, duration,
                                    observed_provider=self._provider.provider_id)


def _chat_text(response):
    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    text = getattr(getattr(choices[0], "message", None), "content", None)
    return text if isinstance(text, str) and text.strip() else None


def _chat_finish_reason(response):
    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    return getattr(choices[0], "finish_reason", None)


def _chat_usage(response):
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if type(input_tokens) is not int or type(output_tokens) is not int or input_tokens < 0 or output_tokens < 0:
        return "not_metered"
    return {"input": input_tokens, "output": output_tokens}


class OpenAICompatibleTextGenerationAdapter(TextGenerationAdapter):
    """DeepSeek and explicitly configured OpenAI-compatible chat endpoints."""

    def __init__(self, client=None, provider_definition=None, max_output_tokens=None,
                 timeout=None, api_key=None):
        self._client = client
        self._provider = provider_definition
        self._max_output_tokens = max_output_tokens or OPENAI_MAX_OUTPUT_TOKENS
        self._timeout = TEXT_GENERATION_TIMEOUT_SECONDS if timeout is None else timeout
        self._api_key = api_key

    def _build_client(self):
        import os
        api_key = self._api_key
        if api_key is None:
            try:
                api_key = self._provider.require_credential(os.environ)
            except ModelConfigError as exc:
                raise OpenAIConfigurationError(str(exc)) from None
        try:
            import openai
        except ImportError:
            raise OpenAIConfigurationError(
                "openai SDK is not installed; install it for compatible-provider calls"
            ) from None
        return openai.OpenAI(api_key=api_key, base_url=self._provider.base_url,
                             max_retries=0, timeout=self._timeout)

    def generate(self, prompt_text, model):
        if not isinstance(model, str) or not model.strip():
            raise RequestValidationError("model must be a nonempty configured identifier")
        client = self._client or self._build_client()
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt_text}],
                max_tokens=self._max_output_tokens,
            )
        except Exception:
            return TextGenerationResult(
                "failed_transport", None, "not_metered", None,
                time.monotonic() - start,
                f"{self._provider.provider_id} request failed (transport or timeout)",
                self._provider.provider_id,
            )
        duration = time.monotonic() - start
        text, usage = _chat_text(response), _chat_usage(response)
        observed = getattr(response, "model", None)
        observed = observed if isinstance(observed, str) else None
        if _chat_finish_reason(response) not in (None, 'stop', 'length'):
            return TextGenerationResult('failed_incomplete', text, usage, observed, duration,
                                        'model response did not finish a text turn', self._provider.provider_id)
        if _chat_finish_reason(response) == "length":
            return TextGenerationResult("failed_truncated", text, usage, observed, duration,
                                        "model response was truncated at the length limit", self._provider.provider_id)
        if not text:
            return TextGenerationResult("failed_empty_response", None, usage, observed, duration,
                                        "model response was incomplete or empty", self._provider.provider_id)
        return TextGenerationResult("completed", text, usage, observed, duration,
                                    observed_provider=self._provider.provider_id)


def _default_provider(provider):
    defaults = {
        "openai": ProviderDefinition("openai", "openai", "OPENAI_API_KEY"),
        "anthropic": ProviderDefinition("anthropic", "anthropic", "ANTHROPIC_API_KEY"),
        "deepseek": ProviderDefinition("deepseek", "deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    }
    return defaults.get(provider)


def build_translation_adapter(provider: str, model: str, client=None,
                              provider_definition=None, max_output_tokens=None,
                              reasoning=None, timeout=None, api_key=None) -> TextGenerationAdapter:
    """Build exactly the configured adapter; never substitutes a fallback.

    `api_key` (or a future resolver callable at a higher layer) lets a caller
    inject credentials explicitly instead of relying on the environment
    fallback; `os.environ` is still read when `api_key` is omitted, and is
    never mutated either way. `reasoning`/`timeout` are optional per-model
    overrides; omitted, each adapter keeps its existing default.
    """
    if not isinstance(model, str) or not model.strip():
        raise RequestValidationError("model must be a nonempty configured identifier")
    definition = provider_definition or _default_provider(provider)
    if provider == "mock":
        if model != "mock-translation-1":
            raise RequestValidationError("mock adapter requires mock-translation-1")
        return MockTextGenerationAdapter()
    if definition is None or definition.provider_id != provider:
        raise RequestValidationError("provider is not configured; no fallback is available")
    if definition.provider_type == "openai":
        return OpenAITextGenerationAdapter(client, definition, max_output_tokens,
                                           reasoning=reasoning, timeout=timeout, api_key=api_key)
    if definition.provider_type == "anthropic":
        return AnthropicTextGenerationAdapter(client, definition, max_output_tokens,
                                              timeout=timeout, api_key=api_key)
    if definition.provider_type in {"deepseek", "openai_compatible"}:
        return OpenAICompatibleTextGenerationAdapter(client, definition, max_output_tokens,
                                                     timeout=timeout, api_key=api_key)
    raise RequestValidationError("provider type is not supported")
