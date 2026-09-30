"""Translation provider configuration and swappable adapter interface.

Only "mock" is supported in Gate 1. Any other provider name is rejected
before any call is attempted, so no accidental paid usage is possible.
"""
from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_PROVIDERS = {"mock"}
SUPPORTED_MODELS = {"mock": {"mock-echo-1"}}
ALLOWED_CONFIG_FIELDS = {"provider", "target_language", "model"}

MOCK_PLACEHOLDER_PREFIX = "[MOCK-PLACEHOLDER]"


class UnsupportedProviderError(ValueError):
    pass


class ConfigValidationError(ValueError):
    """Raised for malformed or disallowed provider config input.

    Never includes raw field values in messages, since a rejected config
    (e.g. one with a credential-like field) must not leak them.
    """


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "mock"
    target_language: str = "he"
    model: str = "mock-echo-1"

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                "provider is not supported; "
                f"allowed: {sorted(SUPPORTED_PROVIDERS)}"
            )
        if not self.target_language:
            raise ValueError("target_language must be nonempty")
        allowed_models = SUPPORTED_MODELS.get(self.provider, set())
        if self.model not in allowed_models:
            raise UnsupportedProviderError(
                f"model is not supported; allowed: {sorted(allowed_models)}"
            )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "target_language": self.target_language,
            "model": self.model,
        }

    @staticmethod
    def from_dict(data: dict) -> "ProviderConfig":
        """Strictly validate a config mapping before building a config.

        Rejects non-object configs, unknown fields (field names only are
        reported, never values), and wrong field types.
        """
        if not isinstance(data, dict):
            raise ConfigValidationError("config must be a JSON object")
        unknown = set(data) - ALLOWED_CONFIG_FIELDS
        if unknown:
            raise ConfigValidationError(
                f"unknown config fields: {sorted(unknown)}"
            )
        provider = data.get("provider", "mock")
        if not isinstance(provider, str):
            raise ConfigValidationError("provider must be a string")
        target_language = data.get("target_language", "he")
        if not isinstance(target_language, str):
            raise ConfigValidationError("target_language must be a string")
        model = data.get("model", "mock-echo-1")
        if not isinstance(model, str):
            raise ConfigValidationError("model must be a string")
        return ProviderConfig(
            provider=provider, target_language=target_language, model=model
        )


class TranslationAdapter:
    """Small adapter contract. A store never depends on a specific adapter."""

    def translate(self, text: str, target_language: str) -> str:
        raise NotImplementedError


class MockTranslationAdapter(TranslationAdapter):
    """No external calls. Output is explicitly marked as a placeholder."""

    def translate(self, text: str, target_language: str) -> str:
        return f"{MOCK_PLACEHOLDER_PREFIX} ({target_language}) {text}"


def build_adapter(config: ProviderConfig) -> TranslationAdapter:
    if config.provider == "mock":
        return MockTranslationAdapter()
    raise UnsupportedProviderError("provider is not supported")
