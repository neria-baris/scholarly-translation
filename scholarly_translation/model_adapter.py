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
    if type(cached) is int:
        result["cached"] = cached
    cache_write = getattr(input_details, "cache_write_tokens", None) if input_details is not None else None
    if type(cache_write) is int:
        result["cache_write"] = cache_write
    output_details = getattr(usage, "output_tokens_details", None)
    reasoning = getattr(output_details, "reasoning_tokens", None) if output_details is not None else None
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
