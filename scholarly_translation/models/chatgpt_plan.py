"""Plan-first text generation through "Sign in with ChatGPT" plan usage.

``ChatGPTPlanAdapter`` sends a text-generation call to the OpenAI Responses
API with the user's ChatGPT plan access token (``store=False``, streamed).
``PlanFirstAdapter`` tries the plan first and, by the user's explicit setting,
continues with the API-key adapter when the plan is exhausted or cannot serve
the call. Tokens are never logged or put in exception text.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional

from . import catalog as model_catalog
from .adapter import (
    OpenAIConfigurationError,
    ImagePrompt,
    RequestValidationError,
    TEXT_GENERATION_TIMEOUT_SECONDS,
    TextGenerationAdapter,
    TextGenerationResult,
    _extract_output_text,
    _extract_usage,
    _failure_kind,
)

PLAN_PROVIDER_ID = "openai-chatgpt-plan"
PLAN_RETRY_SECONDS = 1800
PLAN_BASE_URL = "https://api.openai.com/v1"

_CODE_REASONS = {
    "subscription_sharing_usage_limit_exceeded": "exhausted",
    "subscription_sharing_user_not_eligible": "not_eligible",
    "chatpass_v2_scope_not_authorized": "not_eligible",
    "chatpass_v2_invalid_authorization_context": "not_eligible",
    "subscription_sharing_unsupported_capability": "unsupported",
    "subscription_sharing_usage_unavailable": "unavailable",
    "subscription_sharing_user_unavailable": "unavailable",
}
_INVALID_USER = "subscription_sharing_invalid_user"

_MESSAGES = {
    "exhausted": "תקציב חשבון OpenAI (ChatGPT) נגמר. אפשר להמשיך עם מפתח API או להמתין לחידוש התקציב.",
    "not_eligible": "חשבון ה־ChatGPT המחובר אינו מורשה לשימוש במכסת התוכנית. אפשר להתחבר מחדש או להשתמש במפתח API.",
    "signed_out": "החשבון של OpenAI אינו מחובר. התחברו מחדש או השתמשו במפתח API.",
    "unsupported": "מכסת התוכנית אינה יכולה לשרת בקשה זו. נדרש מפתח API.",
    "unavailable": "מכסת התוכנית אינה זמינה כרגע. נסו שוב מאוחר יותר או השתמשו במפתח API.",
}


class PlanUnavailableError(OpenAIConfigurationError):
    """The ChatGPT plan cannot serve this call. ``reason`` is one of
    "exhausted" | "not_eligible" | "signed_out" | "unsupported" | "unavailable".
    A configuration-class error: the reservation is released, nothing is spent."""

    def __init__(self, reason: str, message: Optional[str] = None):
        super().__init__(message or _MESSAGES.get(reason, _MESSAGES["unavailable"]))
        self.reason = reason


def _iso(timestamp: Optional[float]) -> Optional[str]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


class PlanState:
    """Thread-safe plan availability for one server process."""

    def __init__(self, clock=time.time, retry_seconds: float = PLAN_RETRY_SECONDS):
        self._clock = clock
        self._retry = retry_seconds
        self._lock = threading.Lock()
        self._state = "ready"
        self._since: Optional[float] = None
        self._retry_at: Optional[float] = None
        self._fallbacks = 0
        self._last_fallback: Optional[float] = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state, "since": _iso(self._since), "retry_at": _iso(self._retry_at),
                "fallback_calls": self._fallbacks, "last_fallback_at": _iso(self._last_fallback),
            }

    def reset(self) -> None:
        """On sign-in / sign-out: the plan is presumed ready again."""
        with self._lock:
            self._state, self._since, self._retry_at = "ready", None, None

    def usable(self) -> bool:
        """True when a plan call should be tried now (ready, or exhausted and the pause is over)."""
        with self._lock:
            if self._state == "ready":
                return True
            return self._state == "exhausted" and self._retry_at is not None and self._clock() >= self._retry_at

    def blocking_reason(self) -> str:
        with self._lock:
            return "not_eligible" if self._state == "not_eligible" else "exhausted"

    def mark_ready(self) -> None:
        self.reset()

    def mark_exhausted(self) -> None:
        with self._lock:
            now = self._clock()
            if self._state != "exhausted" or self._since is None:
                self._since = now
            self._state, self._retry_at = "exhausted", now + self._retry

    def mark_not_eligible(self) -> None:
        with self._lock:
            if self._state != "not_eligible":
                self._since = self._clock()
            self._state, self._retry_at = "not_eligible", None

    def note_fallback(self) -> None:
        with self._lock:
            self._fallbacks += 1
            self._last_fallback = self._clock()


def _body_code(body) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        body = error
    code = body.get("code") or (body.get("type") if body is error else None)
    return code if isinstance(code, str) else None


def _error_code(exc) -> Optional[str]:
    """The plan error code carried by an SDK status error (``body`` or response JSON)."""
    code = _body_code(getattr(exc, "body", None))
    if code:
        return code
    response = getattr(exc, "response", None)
    try:
        return _body_code(response.json())
    except Exception:
        return None


def _reason_for_code(code: Optional[str]) -> Optional[str]:
    return _CODE_REASONS.get(code) if code else None


class _Unauthorized(Exception):
    pass


class ChatGPTPlanAdapter(TextGenerationAdapter):
    """Generation billed to the user's ChatGPT plan. ``client_factory(access_token)``
    may be injected (tests); the default builds an ``openai.OpenAI`` client."""

    def __init__(self, account, reasoning=None, timeout=None, client_factory=None, max_wall_seconds=3600):
        self._account = account
        self._reasoning = reasoning
        self._timeout = TEXT_GENERATION_TIMEOUT_SECONDS if timeout is None else timeout
        self._client_factory = client_factory
        self._max_wall_seconds = max_wall_seconds

    def _build_client(self, access_token):
        if self._client_factory is not None:
            return self._client_factory(access_token)
        try:
            import openai
        except ImportError:
            raise OpenAIConfigurationError("openai SDK is not installed; install it before calling openai") from None
        return openai.OpenAI(api_key=access_token, base_url=PLAN_BASE_URL, max_retries=0, timeout=self._timeout)

    def _reasoning_effort(self, model):
        entry = model_catalog.resolve("openai", model)
        if self._reasoning is not None:
            if entry is not None and self._reasoning not in entry.reasoning_values:
                raise RequestValidationError(f"model {model!r} does not support reasoning {self._reasoning!r}")
            return self._reasoning
        return model_catalog.default_reasoning(entry)

    def _token(self):
        from ..account.openai_auth import OpenAISignedOut, OpenAISignInError
        try:
            return self._account.access_token()
        except OpenAISignedOut:
            raise PlanUnavailableError("signed_out") from None
        except OpenAISignInError:
            raise PlanUnavailableError("unavailable") from None

    def _payload(self, prompt_text, model, reasoning_effort):
        payload = dict(model=model, store=False)
        if isinstance(prompt_text, ImagePrompt):
            payload["input"] = [{"role": "user", "content": [
                {"type": "input_text", "text": prompt_text.text},
                {"type": "input_image", "image_url": prompt_text.data_url()},
            ]}]
        else:
            payload["input"] = str(prompt_text)  # a CacheablePrompt is sent as its full text
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}
        return payload

    def _consume(self, client, payload, start):
        """Stream until the response ends; returns (response, streamed_text)."""
        stream = client.responses.create(stream=True, **payload)
        final, deltas = None, []
        for event in stream:
            if time.monotonic() - start > self._max_wall_seconds:
                raise TimeoutError("generation wall limit")
            kind = getattr(event, "type", None)
            if kind == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if isinstance(delta, str):
                    deltas.append(delta)
            elif kind in ("response.completed", "response.incomplete"):
                final = getattr(event, "response", None)
                break
            elif kind == "response.failed":
                response = getattr(event, "response", None)
                error = getattr(response, "error", None)
                code = getattr(error, "code", None)
                reason = _reason_for_code(code) or ("unauthorized" if code == _INVALID_USER else None)
                if reason == "unauthorized":
                    raise _Unauthorized()
                if reason:
                    raise PlanUnavailableError(reason)
                raise RuntimeError("response.failed")
            elif kind == "error":
                code = getattr(event, "code", None)
                reason = _reason_for_code(code)
                if code == _INVALID_USER:
                    raise _Unauthorized()
                if reason:
                    raise PlanUnavailableError(reason)
                raise RuntimeError("stream error event")
        if final is None:
            raise RuntimeError("stream ended before the response completed")
        return final, "".join(deltas)

    @staticmethod
    def _classify(exc):
        """A plan-specific failure as a PlanUnavailableError or _Unauthorized, else None."""
        if isinstance(exc, (PlanUnavailableError, _Unauthorized)):
            return exc
        code = _error_code(exc)
        reason = _reason_for_code(code)
        if reason:
            return PlanUnavailableError(reason)
        if code == _INVALID_USER or getattr(exc, "status_code", None) == 401:
            return _Unauthorized()
        if getattr(exc, "status_code", None) == 503:  # admission or capacity: temporary
            return PlanUnavailableError("unavailable")
        return None

    def generate(self, prompt_text: str, model: str) -> TextGenerationResult:
        if not isinstance(model, str) or not model.strip():
            raise RequestValidationError("model must be a nonempty configured identifier")
        reasoning_effort = self._reasoning_effort(model)
        payload = self._payload(prompt_text, model, reasoning_effort)
        start = time.monotonic()
        response, streamed = None, ""
        for attempt in (1, 2):
            token = self._token()
            try:
                client = self._build_client(token)
                response, streamed = self._consume(client, payload, start)
                break
            except OpenAIConfigurationError:
                raise
            except Exception as exc:
                found = self._classify(exc)
                if isinstance(found, _Unauthorized):
                    self._account.invalidate_access_token()
                    if attempt == 1:
                        continue  # refresh once, then try again
                    raise PlanUnavailableError("unavailable") from None
                if found is not None:
                    raise found from None
                return TextGenerationResult(
                    status="failed_transport", text=None, token_usage="not_metered",
                    observed_model=None, duration_seconds=time.monotonic() - start,
                    error=f"{PLAN_PROVIDER_ID} request failed (transport or timeout: {_failure_kind(exc)})",
                    observed_provider=PLAN_PROVIDER_ID,
                )
        duration = time.monotonic() - start
        response_status = getattr(response, "status", None)
        text = _extract_output_text(response) or (streamed if streamed.strip() else None)
        usage = _extract_usage(response)
        observed_model = getattr(response, "model", None)
        observed_model = observed_model if isinstance(observed_model, str) else None
        incomplete_reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        if response_status == "incomplete" and incomplete_reason == "max_output_tokens":
            return TextGenerationResult(
                status="failed_truncated", text=text, token_usage=usage,
                observed_model=observed_model, duration_seconds=duration,
                error="model response was truncated at max_output_tokens",
                observed_provider=PLAN_PROVIDER_ID,
            )
        if response_status != "completed" or not text:
            return TextGenerationResult(
                status="failed_empty_response", text=None, token_usage=usage,
                observed_model=observed_model, duration_seconds=duration,
                error="model response was incomplete or empty",
                observed_provider=PLAN_PROVIDER_ID,
            )
        return TextGenerationResult(
            status="completed", text=text, token_usage=usage,
            observed_model=observed_model, duration_seconds=duration,
            observed_provider=PLAN_PROVIDER_ID,
        )


class PlanFirstAdapter(TextGenerationAdapter):
    """Plan first; the API-key adapter only by the user's explicit auto-fallback choice."""

    def __init__(self, plan_adapter, plan_state, fallback_adapter=None, auto_fallback=True):
        self._plan = plan_adapter
        self._state = plan_state
        self._fallback = fallback_adapter
        self._auto_fallback = auto_fallback

    def _may_fall_back(self) -> bool:
        flag = self._auto_fallback() if callable(self._auto_fallback) else self._auto_fallback
        return bool(flag) and self._fallback is not None

    def _continue_with_key(self, error, prompt_text, model):
        if not self._may_fall_back():
            raise error
        self._state.note_fallback()
        return self._fallback.generate(prompt_text, model)

    def generate(self, prompt_text: str, model: str) -> TextGenerationResult:
        if not self._state.usable():
            return self._continue_with_key(
                PlanUnavailableError(self._state.blocking_reason()), prompt_text, model)
        try:
            result = self._plan.generate(prompt_text, model)
        except PlanUnavailableError as error:
            if error.reason == "exhausted":
                self._state.mark_exhausted()
            elif error.reason == "not_eligible":
                self._state.mark_not_eligible()
            return self._continue_with_key(error, prompt_text, model)
        if result.status == "completed":
            self._state.mark_ready()
        return result
