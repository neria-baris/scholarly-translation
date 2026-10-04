"""Versioned, secret-free provider/model configuration.

Model identifiers and limits are deployment data.  Runtime code consumes the
resolved records here and never needs a marketing-model allowlist.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ROLES = (
    "translator",
    "semantic_reviewer",
    "chapter_qa",
    "candidate_evaluator",
    "context_state_builder",
)
PROVIDER_TYPES = {"mock", "openai", "anthropic", "deepseek", "openai_compatible"}
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


class ModelConfigError(ValueError):
    """Malformed model configuration; messages never contain credential values."""


def _object(value, name):
    if not isinstance(value, dict):
        raise ModelConfigError(f"{name} must be an object")
    return value


def _keys(value, allowed, name):
    unknown = set(value) - set(allowed)
    if unknown:
        raise ModelConfigError(f"unknown {name} fields: {sorted(unknown)}")


def _positive_int(value, name, *, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or value <= 0:
        raise ModelConfigError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int
    usable_context_tokens: int
    max_output_tokens: int | None = None
    structured_output: bool = False

    @staticmethod
    def from_dict(data):
        data = _object(data, "capabilities")
        _keys(data, {"context_window", "usable_context_tokens", "max_output_tokens", "structured_output"},
              "capability")
        context = _positive_int(data.get("context_window"), "context_window")
        usable = _positive_int(data.get("usable_context_tokens"), "usable_context_tokens")
        if usable > context:
            raise ModelConfigError("usable_context_tokens cannot exceed context_window")
        structured = data.get("structured_output", False)
        if type(structured) is not bool:
            raise ModelConfigError("structured_output must be a boolean")
        return ModelCapabilities(
            context_window=context,
            usable_context_tokens=usable,
            max_output_tokens=_positive_int(data.get("max_output_tokens"), "max_output_tokens", optional=True),
            structured_output=structured,
        )

    def to_dict(self):
        return {
            "context_window": self.context_window,
            "usable_context_tokens": self.usable_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "structured_output": self.structured_output,
        }


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    provider_type: str
    credential_env: str | None = None
    base_url: str | None = None

    @staticmethod
    def from_dict(provider_id, data):
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ModelConfigError("provider id must be a nonempty string")
        data = _object(data, "provider")
        _keys(data, {"type", "credential_env", "base_url"}, "provider")
        kind = data.get("type")
        if kind not in PROVIDER_TYPES:
            raise ModelConfigError(f"provider type must be one of {sorted(PROVIDER_TYPES)}")
        env = data.get("credential_env")
        if kind != "mock":
            if not isinstance(env, str) or not _ENV_NAME.fullmatch(env):
                raise ModelConfigError("credential_env must be an uppercase environment-variable name")
        elif env is not None:
            raise ModelConfigError("mock provider must not define credential_env")
        base_url = data.get("base_url")
        if base_url is not None:
            if not isinstance(base_url, str) or len(base_url) > 2048:
                raise ModelConfigError("base_url must be a URL string")
            parsed = urlparse(base_url)
            local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme != "https" and not local_http:
                raise ModelConfigError("base_url must use HTTPS (HTTP is allowed only for localhost)")
            if parsed.username or parsed.password or not parsed.netloc or parsed.query or parsed.fragment:
                raise ModelConfigError("base_url must not contain credentials, query, or fragment")
        if kind == "openai_compatible" and not base_url:
            raise ModelConfigError("openai_compatible provider requires base_url")
        return ProviderDefinition(provider_id.strip(), kind, env, base_url.rstrip("/") if base_url else None)

    def require_credential(self, environ=None):
        if self.provider_type == "mock":
            return None
        environ = os.environ if environ is None else environ
        value = environ.get(self.credential_env)
        if not value:
            raise ModelConfigError(
                f"{self.credential_env} is not set; configure it before calling provider {self.provider_id}"
            )
        return value

    def to_dict(self):
        result = {"type": self.provider_type}
        if self.credential_env:
            result["credential_env"] = self.credential_env
        if self.base_url:
            result["base_url"] = self.base_url
        return result


@dataclass(frozen=True)
class ModelSelection:
    role: str
    provider: str
    model: str
    capabilities: ModelCapabilities

    @staticmethod
    def from_dict(role, data):
        if role not in ROLES:
            raise ModelConfigError(f"unsupported model role: {role}")
        data = _object(data, f"model role {role}")
        _keys(data, {"provider", "model", "capabilities"}, "model selection")
        provider, model = data.get("provider"), data.get("model")
        if not isinstance(provider, str) or not provider.strip():
            raise ModelConfigError(f"{role}.provider must be a nonempty string")
        if not isinstance(model, str) or not model.strip() or len(model) > 256:
            raise ModelConfigError(f"{role}.model must be a nonempty string")
        return ModelSelection(role, provider.strip(), model.strip(),
                              ModelCapabilities.from_dict(data.get("capabilities")))

    def to_dict(self):
        return {"provider": self.provider, "model": self.model,
                "capabilities": self.capabilities.to_dict()}


@dataclass(frozen=True)
class ModelConfiguration:
    providers: dict[str, ProviderDefinition]
    models: dict[str, ModelSelection]
    schema_version: int = 1

    @staticmethod
    def from_dict(data):
        data = _object(data, "model configuration")
        _keys(data, {"schema_version", "providers", "models"}, "configuration")
        if data.get("schema_version") != 1:
            raise ModelConfigError("schema_version must be 1")
        providers_data = _object(data.get("providers"), "providers")
        models_data = _object(data.get("models"), "models")
        providers = {name: ProviderDefinition.from_dict(name, value)
                     for name, value in providers_data.items()}
        models = {role: ModelSelection.from_dict(role, value)
                  for role, value in models_data.items()}
        if not models:
            raise ModelConfigError("models must contain at least one role selection")
        missing = sorted({selection.provider for selection in models.values()} - set(providers))
        if missing:
            raise ModelConfigError(f"model selections reference undefined providers: {missing}")
        return ModelConfiguration(providers, models)

    def resolve(self, role):
        if role not in ROLES:
            raise ModelConfigError(f"unsupported model role: {role}")
        if role not in self.models:
            raise ModelConfigError(f"no provider/model configured for role {role}; no fallback is configured")
        selection = self.models[role]
        return selection, self.providers[selection.provider]

    def to_dict(self):
        return {"schema_version": 1,
                "providers": {key: value.to_dict() for key, value in self.providers.items()},
                "models": {key: value.to_dict() for key, value in self.models.items()}}


def load_model_configuration(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ModelConfigError("cannot read valid UTF-8 model configuration JSON") from None
    return ModelConfiguration.from_dict(data)
