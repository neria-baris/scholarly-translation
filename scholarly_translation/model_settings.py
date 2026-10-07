"""UI-facing model/QA settings: catalogue listing and a config-from-selections
builder for the local document UI (AUTOMATION-3/4). This module never stores,
logs or echoes a credential value; it only assigns a deterministic
``credential_env`` name used later purely as a label. The actual secret value
lives only in ``web_ui.py``'s in-memory session store and is injected directly
into ``model_adapter.build_translation_adapter`` by a per-job adapter_factory,
never through ``os.environ``.

Producer files (``model_config.py``, ``model_catalog.py``) are reused as-is
and not modified by this slice: this module only composes their existing
validated dataclasses from simple UI selections.
"""
from __future__ import annotations

from urllib.parse import urlparse
import hashlib
import re

from . import model_catalog
from .model_config import ModelConfigError, ModelConfiguration

ROLE_NAMES = ("translator", "semantic_reviewer", "chapter_qa")

def endpoint_provider_id(provider_type, base_url):
    prefix = "compatible" if provider_type == "openai_compatible" else provider_type + "-custom"
    return prefix + "-" + hashlib.sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()[:12]
_CREDENTIAL_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compatible": "COMPATIBLE_API_KEY",
}
_OTHER_PROVIDER_TYPES = {"openai", "anthropic", "openai_compatible"}


class ModelSettingsError(ValueError):
    """Malformed UI model/QA selection; messages never contain credential values."""


def catalogue() -> list[dict]:
    """Dated, secret-free real-translator-model catalogue for the UI select,
    sourced only from the accepted ``model_catalog.py`` (never duplicated by
    hand). Returned entries never claim to be official for an unknown model;
    unknown/"Other" models are handled separately by :func:`_validate_other`.
    """
    entries = []
    for (provider, model), pricing in sorted(model_catalog._CATALOG.items()):
        entries.append({
            "provider": provider, "model": model,
            "context_window": pricing.context_window,
            "max_output_tokens": pricing.max_output_tokens,
            "rates_per_million": dict(pricing.rates_per_million),
            "reasoning_values": list(pricing.reasoning_values),
            "default_reasoning": pricing.reasoning_values[0] if pricing.reasoning_values else None,
            "catalog_version": model_catalog.CATALOG_VERSION,
        })
    return entries


def _finite_nonneg(value):
    return type(value) in (int, float) and value == value and value not in (float("inf"), float("-inf")) and value >= 0


def _validate_other(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ModelSettingsError("הגדרת מודל 'אחר' חסרה.")
    provider_type = data.get("provider_type")
    if provider_type not in _OTHER_PROVIDER_TYPES:
        raise ModelSettingsError("בחרו סוג ספק נתמך (OpenAI / Anthropic / תואם-OpenAI).")
    model = data.get("model")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,255}", model.strip()) or model.strip().lower().startswith("sk-"):
        raise ModelSettingsError("יש להזין מזהה מודל תקין.")
    base_url = data.get("base_url")
    if provider_type == "openai_compatible" and not base_url:
        raise ModelSettingsError("ספק תואם-OpenAI דורש כתובת endpoint.")
    if base_url is not None:
        if not isinstance(base_url, str) or len(base_url) > 2048:
            raise ModelSettingsError("כתובת ה-endpoint אינה תקינה.")
        parsed = urlparse(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not local_http:
            raise ModelSettingsError("כתובת ה-endpoint חייבת HTTPS (HTTP מותר רק ל-localhost).")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ModelSettingsError("כתובת ה-endpoint לא יכולה לכלול אישורים, פרמטרים או מזהה.")
    context_window = data.get("context_window")
    max_output_tokens = data.get("max_output_tokens")
    if type(context_window) is not int or isinstance(context_window, bool) or context_window <= 0:
        raise ModelSettingsError("יש להזין חלון הקשר (מספר שלם חיובי).")
    if type(max_output_tokens) is not int or isinstance(max_output_tokens, bool) or max_output_tokens <= 0:
        raise ModelSettingsError("יש להזין תקרת פלט (מספר שלם חיובי).")
    if max_output_tokens > 128_000:
        raise ModelSettingsError("תקרת הפלט הנתמכת כרגע היא עד 128,000 טוקנים לקריאה.")
    usable = data.get("usable_context_tokens", context_window)
    if type(usable) is not int or isinstance(usable, bool) or usable <= 0 or usable > context_window:
        raise ModelSettingsError("חלון השימוש חייב להיות מספר שלם חיובי שלא עולה על חלון ההקשר.")
    rates = data.get("rates")
    custom_pricing = None
    if rates is not None:
        if not isinstance(rates, dict):
            raise ModelSettingsError("תמחור מותאם אינו תקין.")
        unknown_fields = set(rates) - {"input", "output", "cached", "cache_write", "cache_write_1h"}
        if unknown_fields:
            raise ModelSettingsError("תמחור מותאם כולל שדות לא מוכרים.")
        if "input" not in rates or "output" not in rates:
            raise ModelSettingsError("תמחור מותאם חייב לכלול לפחות input ו-output.")
        for key, value in rates.items():
            if not _finite_nonneg(value):
                raise ModelSettingsError(f"תעריף {key!r} חייב להיות מספר סופי ואי-שלילי.")
        custom_pricing = dict(rates)
    return {
        "provider_type": provider_type, "model": model.strip(),
        "base_url": base_url.rstrip("/") if base_url else None,
        "context_window": context_window, "usable_context_tokens": usable,
        "max_output_tokens": max_output_tokens, "custom_pricing": custom_pricing,
        "unknown_assumption": custom_pricing is None,
        "credential_env": _CREDENTIAL_ENV[provider_type],
    }


_FORBIDDEN_FIELD_MARKERS = ("api_key", "apikey", "secret", "password")


def _reject_credential_fields(data: dict) -> None:
    if not isinstance(data, dict):
        return
    for key in data:
        if isinstance(key, str) and any(marker in key.lower() for marker in _FORBIDDEN_FIELD_MARKERS):
            raise ModelSettingsError("אין לשלוח מפתחות/אישורים בתוך הגדרת המודל.")


def _resolve_role_selection(selection):
    if not isinstance(selection, dict):
        raise ModelSettingsError("בחירת מודל לתפקיד אינה תקינה.")
    _reject_credential_fields(selection)
    source = selection.get("source")
    allowed = {"source", "provider", "model", "reasoning"} if source == "catalog" else {
        "source", "provider_type", "model", "base_url", "context_window",
        "usable_context_tokens", "max_output_tokens", "rates"}
    if set(selection) - allowed:
        raise ModelSettingsError("הגדרת המודל כוללת שדות שאינם נתמכים.")
    if source == "catalog":
        provider_type, model = selection.get("provider"), selection.get("model")
        if provider_type not in ("openai", "anthropic") or not isinstance(model, str):
            raise ModelSettingsError("בחרו מודל קיים מהקטלוג.")
        entry = model_catalog.resolve(provider_type, model)
        if entry is None:
            raise ModelSettingsError("המודל שנבחר אינו בקטלוג.")
        provider_dict = {"type": provider_type, "credential_env": _CREDENTIAL_ENV[provider_type]}
        capabilities = {
            "context_window": entry.context_window,
            "usable_context_tokens": entry.context_window,
            "max_output_tokens": entry.max_output_tokens,
        }
        reasoning = selection.get("reasoning")
        if reasoning is not None:
            if not entry.reasoning_values:
                raise ModelSettingsError("למודל שנבחר אין רמות חשיבה לבחירה.")
            if reasoning not in entry.reasoning_values:
                raise ModelSettingsError("רמת החשיבה שנבחרה אינה נתמכת במודל זה.")
            capabilities["reasoning"] = reasoning
        return provider_type, provider_dict, {"model": model, "capabilities": capabilities}
    if source == "other":
        other = _validate_other(selection)
        provider_id = "compatible" if other["provider_type"] == "openai_compatible" else other["provider_type"]
        if other["base_url"]:
            provider_id = endpoint_provider_id(other["provider_type"], other["base_url"])
        provider_dict = {"type": other["provider_type"], "credential_env": other["credential_env"]}
        if other["base_url"]:
            provider_dict["base_url"] = other["base_url"]
        capabilities = {
            "context_window": other["context_window"],
            "usable_context_tokens": other["usable_context_tokens"],
            "max_output_tokens": other["max_output_tokens"],
        }
        if other["custom_pricing"] is not None:
            capabilities["custom_pricing"] = other["custom_pricing"]
        return provider_id, provider_dict, {"model": other["model"], "capabilities": capabilities}
    raise ModelSettingsError("בחרו מקור מודל תקין (קטלוג או מודל אחר).")


def build_configuration(role_selections) -> ModelConfiguration:
    """Build a full :class:`ModelConfiguration` from simple per-role UI
    selections. ``semantic_reviewer``/``chapter_qa`` default to the exact
    translator selection (the contract's "ordinary default: same model until
    changed") when omitted; either may be set independently. Raises
    :class:`ModelSettingsError` -- never a raw provider/model_config.py
    exception -- on any invalid input, and never echoes a credential."""
    if not isinstance(role_selections, dict) or "translator" not in role_selections:
        raise ModelSettingsError("יש לבחור מודל מתרגם.")
    _reject_credential_fields(role_selections)
    if set(role_selections) - set(ROLE_NAMES):
        raise ModelSettingsError("בחירת תפקידים אינה תקינה.")
    translator_selection = role_selections["translator"]
    providers, models = {}, {}
    for role in ROLE_NAMES:
        chosen = role_selections.get(role, translator_selection if role != "translator" else None)
        if chosen is None:
            chosen = translator_selection
        provider_id, provider_dict, model_fields = _resolve_role_selection(chosen)
        if provider_id in providers and providers[provider_id] != provider_dict:
            # Same provider type/id but a different endpoint/model config for
            # this role (e.g. a different "Other" compatible endpoint): keep
            # both configurations distinct instead of silently colliding.
            provider_id = f"{provider_id}-{role}"
        providers[provider_id] = provider_dict
        models[role] = {"provider": provider_id, **model_fields}
    config_dict = {"schema_version": 1, "providers": providers, "models": models}
    try:
        return ModelConfiguration.from_dict(config_dict)
    except ModelConfigError:
        raise ModelSettingsError("הגדרת המודל שהוזנה אינה תקינה.") from None
