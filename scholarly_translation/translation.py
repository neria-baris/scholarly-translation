"""Gate 7: smallest source-bound scholarly translation job.

Resolves a validated Gate-4 structure unit and Gate-5 glossary policy into a
provider-independent translation request, runs it through a replaceable
mock/OpenAI text adapter, and formally checks the result. The output is an
unapproved schema-1 `translation-draft@1` record: never approved memory, a
final translation, review or export, and this stage does not select a
quality winner between providers.
"""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import context_strategy
from .formal_checks import run_formal_checks
from .glossary import GlossaryError, effective_fingerprint, resolve_applicable, validate_glossary
from .model_adapter import (
    OPENAI_MAX_OUTPUT_TOKENS,
    PRICING_VERSION,
    RATES_PER_MILLION,
    OpenAIConfigurationError,
    build_translation_adapter,
    compute_estimate,
)
from .model_config import ModelCapabilities, ModelConfiguration, ProviderDefinition
from .segmentation import validate_structure
from .source_reading import StructureError, fingerprint, text_hash
from .store import deterministic_id
from .translation_profiles import (
    CONFIG_VERSIONS,
    PROMPT_VERSIONS,
    ProfileError,
    SUPPORTED_PROFILE_IDS,
    render_prompt,
    style_profile_text,
    validate_approved_decisions,
    validate_local_state,
    validate_source_context,
)

SCHEMA_VERSION = 1
STAGE = "translation-draft@1"

SUPPORTED_SOURCE_LANGUAGES = {"en", "fr", "ja"}
TARGET_LANGUAGE = "he"

_STRUCTURED_OUTPUT_RE = re.compile(
    r"^\s*TRANSLATION:\s*(?P<translation>.*?)\n\s*TRANSLATION_NOTE:\s*(?P<note>.*)\s*$",
    re.DOTALL,
)


def _parse_structured_output(text):
    """Split a profile-structured response into translation text and note.

    Legacy/mock adapters that return plain, unstructured text are passed
    through unchanged with a null note: compatibility must never fabricate
    semantic certainty by guessing a note from unstructured output.
    """
    if text is None:
        return None, None
    match = _STRUCTURED_OUTPUT_RE.match(text)
    if not match:
        return text, None
    translation = match.group("translation").strip()
    note_raw = match.group("note").strip()
    note = None if note_raw.lower() in ("", "null", "none") else note_raw
    return translation, note

MAX_UNIT_CHARS = 2000
MAX_NEIGHBOR_CHARS = 2000
MAX_PROMPT_BYTES = 12000
DECODING_PARAMS = {"max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS, "reasoning_effort": "none"}


class TranslationRequestError(ValueError):
    """Invalid or unresolved translation job input; never includes source text."""


class TranslationBudgetError(TranslationRequestError):
    """The bounded live-call budget cannot authorize another attempt."""


class TranslationBudget:
    """Process-local standard list-price gateway for a bounded live run.

    The conservative reservation bounds calls and tokens. It is not an account
    billing limit: actual charges remain unknown. Reuse one instance across a
    multi-unit run to enforce its cumulative cap.
    """

    def __init__(self, max_calls=3, hard_list_usd=0.01):
        if (type(max_calls) is not int or max_calls < 1 or type(hard_list_usd) not in (int, float)
                or not math.isfinite(hard_list_usd) or hard_list_usd <= 0):
            raise TranslationBudgetError("invalid translation budget")
        self.max_calls = max_calls
        self.hard_list_usd = float(hard_list_usd)
        self.calls = 0
        self.spent_list_usd = 0.0
        self.stopped = False

    def reserve(self, prompt_text):
        if self.stopped or self.calls >= self.max_calls:
            raise TranslationBudgetError("translation call limit reached")
        prompt_bytes = len(prompt_text.encode("utf-8"))
        if prompt_bytes > MAX_PROMPT_BYTES:
            raise TranslationBudgetError("oversized translation prompt")
        # Includes substantial headroom for request framing and tokenizer variation.
        input_bound = 2 * prompt_bytes + 1024
        worst_case = (input_bound * RATES_PER_MILLION["input"]
                      + OPENAI_MAX_OUTPUT_TOKENS * RATES_PER_MILLION["output"]) / 1_000_000
        if self.spent_list_usd + worst_case > self.hard_list_usd:
            raise TranslationBudgetError("translation list-price budget exhausted")
        self.calls += 1
        fraction = (self.spent_list_usd + worst_case) / self.hard_list_usd
        return [f"budget_preflight_{level}_percent" for level in (50, 80) if fraction >= level / 100]

    def release_unstarted(self):
        self.calls -= 1

    def record(self, token_usage):
        estimate = compute_estimate(token_usage)
        if estimate == "not_metered":
            self.stopped = True
            return ["usage_not_metered_stop"]
        self.spent_list_usd += estimate
        if self.spent_list_usd > self.hard_list_usd:
            self.stopped = True
        fraction = self.spent_list_usd / self.hard_list_usd
        return [f"budget_observed_{level}_percent" for level in (50, 80) if fraction >= level / 100]


def _require(condition, message):
    if not condition:
        raise TranslationRequestError(message)


def _build_context_and_decision(structure, unit, capabilities, headroom_fraction):
    """Shared Session D context resolution for ``build_context`` and
    ``build_translation_request``. With no model capabilities, this enforces
    the exact historical MAX_NEIGHBOR_CHARS-bounded one-previous/one-next
    behavior; with capabilities, it defers to the chapter-aware policy in
    ``context_strategy``."""
    decision, segments = context_strategy.plan_context(
        structure, unit, capabilities, headroom_fraction=headroom_fraction,
    )
    if capabilities is None:
        for segment in segments:
            _require(len(segment["text"]) <= MAX_NEIGHBOR_CHARS, "oversized neighbor context")
    return decision, segments


def build_context(structure, unit, capabilities=None, headroom_fraction=None):
    """Session D context selection for ``unit``.

    With ``capabilities=None`` (the default, for backward compatibility),
    this is exactly the historical target unit plus at most one previous/one
    next unit from the same reading, each bounded by MAX_NEIGHBOR_CHARS --
    never crossing page/document/readings and never sending a whole chapter.

    With model capabilities supplied, this instead returns the semantic-
    unit, chapter-aware context described in
    ``audit/contracts/session_d_context_strategy.md``: the whole enclosing
    chapter (exact target span marked) when it fits the model's usable
    context budget, else the target plus as much bounded original source as
    fits. Never a generated summary.
    """
    _, segments = _build_context_and_decision(structure, unit, capabilities, headroom_fraction)
    return segments


def _render_prompt(profile_id, segments, source_language, applicable_rules,
                    approved_decisions, local_state, source_context):
    terms = [
        {"source_term": r["source_term"], "target_term": r["target_term"],
         "version": r["version"], "loaded": r["loaded"]}
        for r in applicable_rules
    ]
    glossary_lines = [
        "Approved applicable terminology (JSON): " + json.dumps(terms, ensure_ascii=False, sort_keys=True)
    ]
    if approved_decisions:
        glossary_lines.append(
            "Caller-supplied approved decisions (JSON): "
            + json.dumps(approved_decisions, ensure_ascii=False, sort_keys=True)
        )
    glossary_and_decisions = "\n".join(glossary_lines)

    target_segment = next(s for s in segments if s["role"] == "target")
    neighbor_lines = [
        json.dumps({"role": s["role"], "text": s["text"]}, ensure_ascii=False)
        for s in segments if s["role"] != "target"
    ]
    if source_context:
        neighbor_lines.append(source_context)
    rendered_source_context = "\n".join(neighbor_lines)

    header = f"Source language: {source_language}. Target language: he."
    return header + "\n\n" + render_prompt(
        profile_id=profile_id,
        style_profile=style_profile_text(profile_id),
        glossary_and_decisions=glossary_and_decisions,
        local_state=local_state,
        source_context=rendered_source_context,
        target_unit_text=target_segment["text"],
    )


def compute_cache_key(
    *, profile_id, pdf_hash, source_uri, document_id, reading_id, reading_version,
    reading_text_hash, unit_id, unit_version, source_char_start, source_char_end,
    unit_text_hash, neighbor_fingerprint, policy_fingerprint, provider, model,
    prompt_version, config_version, decoding_params, caller_context_fingerprint="",
    context_policy_version=context_strategy.CONTEXT_POLICY_VERSION, context_mode="bounded_fallback",
):
    """Deterministic cache identity bound to exact source/policy/provider/config.

    `caller_context_fingerprint` binds caller-supplied approved decisions,
    local state and source context (Gate 12); it defaults to the empty
    string so pre-Gate-12 callers keep their existing cache identity.

    `context_policy_version`/`context_mode` (Session D) default to the
    current chapter-aware policy and the legacy-equivalent mode name, so
    pre-Session-D callers that omit them keep calling this with the same
    shape; the computed key value still changes once these fields exist,
    which is the deliberate Session D invalidation behavior documented in
    `audit/contracts/session_d_context_strategy.md`: a unit's cache identity
    depends only on the exact text actually sent to the model (the target
    unit plus whichever context segments were actually included), never on
    unrelated text elsewhere in the same chapter that was not sent.
    """
    payload = {
        "profile_id": profile_id, "pdf_hash": pdf_hash, "source_uri": source_uri,
        "document_id": document_id, "reading_id": reading_id, "reading_version": reading_version,
        "reading_text_hash": reading_text_hash, "unit_id": unit_id, "unit_version": unit_version,
        "source_char_start": source_char_start, "source_char_end": source_char_end,
        "unit_text_hash": unit_text_hash, "neighbor_fingerprint": neighbor_fingerprint,
        "policy_fingerprint": policy_fingerprint, "provider": provider, "model": model,
        "prompt_version": prompt_version, "config_version": config_version,
        "decoding_params": decoding_params, "caller_context_fingerprint": caller_context_fingerprint,
        "context_policy_version": context_policy_version, "context_mode": context_mode,
    }
    return fingerprint(payload)


@dataclass(frozen=True)
class TranslationRequest:
    """Resolved, provider-independent translation job. Not yet a result."""

    profile_id: str
    provider: str
    model: str
    source_language: str
    target_language: str
    structure: dict
    glossary_store: dict
    unit: dict
    context_segments: list
    applicable_rules: list
    proposed_loaded_rules: list
    policy_fingerprint: str
    approved_decisions: tuple
    local_state: str
    source_context: str
    caller_context_fingerprint: str
    prompt_version: str
    config_version: str
    prompt_text: str
    cache_key: str
    provider_definition: ProviderDefinition | None = None
    capabilities: ModelCapabilities | None = None
    # Session D: distinguishes "what exact text was translated" (target_text/
    # target_unit_ids) from "what source/stored context did the model see"
    # (context_segments). All default so pre-Session-D construction keeps
    # working; build_translation_request/build_whole_chapter_translation_request
    # always set them explicitly.
    target_text: str = ""
    target_unit_ids: tuple = ()
    context_mode: str = "bounded_fallback"
    context_policy_version: str = context_strategy.CONTEXT_POLICY_VERSION
    chapter_node_id: str | None = None
    crosses_page_boundary: bool = False
    # Resolved (never None) headroom fraction actually used for the context
    # decision above; stored so run_translation's canonical re-derivation
    # reproduces the exact same decision rather than silently falling back
    # to the default fraction.
    context_headroom_fraction: float = context_strategy.DEFAULT_HEADROOM_FRACTION

    def to_metadata_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "provider_type": (
                self.provider_definition.provider_type if self.provider_definition else self.provider
            ),
            "provider_definition": (
                self.provider_definition.to_dict() if self.provider_definition else None
            ),
            "source_language": self.source_language,
            "target_language": self.target_language,
            "source_uri": self.structure["source_uri"],
            "pdf_hash": self.structure["pdf_hash"],
            "document_id": self.unit["document_id"],
            "page_id": self.unit["page_id"],
            "reading_id": self.unit["reading_id"],
            "reading_version": self.unit["reading_version"],
            "unit_id": self.unit["unit_id"],
            "unit_version": self.unit["unit_version"],
            "source_char_start": self.unit["source_char_start"],
            "source_char_end": self.unit["source_char_end"],
            "source_text_hash": text_hash(self.target_text),
            "reading_text_hash": self.unit["reading_text_hash"],
            "neighbor_fingerprint": fingerprint(self.context_segments),
            "policy_fingerprint": self.policy_fingerprint,
            "applicable_rule_ids": [
                {"rule_id": r["rule_id"], "version": r["version"]} for r in self.applicable_rules
            ],
            "proposed_loaded_rule_ids": [
                {"rule_id": r["rule_id"], "version": r["version"]} for r in self.proposed_loaded_rules
            ],
            "prompt_version": self.prompt_version,
            "config_version": self.config_version,
            "prompt_hash": text_hash(self.prompt_text),
            "cache_key": self.cache_key,
            "model_capabilities": self.capabilities.to_dict() if self.capabilities else None,
            # Session D: independently recoverable target-vs-context provenance.
            "context_policy_version": self.context_policy_version,
            "context_mode": self.context_mode,
            "chapter_node_id": self.chapter_node_id,
            "crosses_page_boundary": self.crosses_page_boundary,
            "target_source": {
                "unit_ids": list(self.target_unit_ids),
                "source_char_start": self.unit["source_char_start"],
                "source_char_end": self.unit["source_char_end"],
                "text_hash": text_hash(self.target_text),
            },
            "context_source": {
                "mode": self.context_mode,
                "chapter_node_id": self.chapter_node_id,
                "segments": [
                    {"role": s["role"], "unit_id": s.get("unit_id"), "node_ids": s.get("node_ids", [])}
                    for s in self.context_segments if s["role"] not in ("target", "target_marker")
                ],
                "fingerprint": fingerprint(self.context_segments),
            },
        }


def build_translation_request(
    structure, glossary, unit_id, profile_id, provider, model,
    provider_definition=None, capabilities=None,
    approved_decisions=None, local_state=None, source_context=None,
    context_headroom_fraction=None,
) -> TranslationRequest:
    """Validate and resolve a translation job before any network call.

    Refuses unresolved readings, continuity findings, a missing unit,
    conflicting glossary resolution, malformed source/policy and an oversized
    prompt. No supplied free-form text bypasses source validation: the source
    text always comes from the validated structure, never a caller argument.

    `approved_decisions`/`local_state`/`source_context` are optional, bounded,
    caller-supplied layered context (Gate 12): this builder never selects that
    context itself, only validates, renders and fingerprints it.

    Session D: when `capabilities` is supplied, context selection becomes
    chapter-aware (see `context_strategy.plan_context`); `context_headroom_fraction`
    overrides the fraction of the model's usable context reserved for
    instructions/glossary/local-state/output/review metadata before chapter
    source text is considered (default `context_strategy.DEFAULT_HEADROOM_FRACTION`).
    With `capabilities=None` this builder's context selection is unchanged
    from before Session D.
    """
    try:
        if profile_id not in SUPPORTED_PROFILE_IDS:
            raise ProfileError(f"profile_id must be one of {SUPPORTED_PROFILE_IDS}; no fallback profile")
        approved_decisions = validate_approved_decisions(approved_decisions)
        local_state = validate_local_state(local_state)
        source_context = validate_source_context(source_context)
    except ProfileError as exc:
        raise TranslationRequestError(str(exc)) from None
    try:
        validate_structure(structure)
        validate_glossary(glossary)
    except (StructureError, GlossaryError):
        raise TranslationRequestError("invalid source or glossary for translation") from None
    _require(not structure["continuity"], "structure has unresolved continuity findings")
    _require(isinstance(provider, str) and bool(provider.strip()), "unsupported provider")
    _require(isinstance(model, str) and bool(model.strip()), "unsupported model for provider")
    if provider == "mock":
        _require(model == "mock-translation-1", "unsupported model for mock provider")
    elif provider_definition is None:
        _require(provider in {"openai", "anthropic", "deepseek"},
                 "custom provider requires an explicit provider definition")
    else:
        _require(isinstance(provider_definition, ProviderDefinition)
                 and provider_definition.provider_id == provider,
                 "provider definition does not match selected provider")
    _require(capabilities is None or isinstance(capabilities, ModelCapabilities),
             "invalid model capability metadata")

    unit = next((u for u in structure["units"] if u["unit_id"] == unit_id), None)
    _require(unit is not None, "unknown or missing unit for translation job")
    source_language = unit["language"]
    _require(source_language in SUPPORTED_SOURCE_LANGUAGES, "unsupported source language")
    _require(len(unit["text"]) <= MAX_UNIT_CHARS, "oversized source unit")

    resolution = resolve_applicable(glossary, structure, unit_id)
    _require(resolution["status"] != "needs_human", "conflicting glossary resolution for unit")
    applicable_rules = resolution["approved_rules"]
    proposed_loaded_rules = [r for r in resolution["proposed_rules"] if r["loaded"]]
    policy_fingerprint = resolution["policy_fingerprint"]
    _require(
        policy_fingerprint == effective_fingerprint(applicable_rules),
        "glossary policy fingerprint mismatch",
    )

    effective_headroom = (
        context_strategy.DEFAULT_HEADROOM_FRACTION if context_headroom_fraction is None else context_headroom_fraction
    )
    decision, context_segments = _build_context_and_decision(
        structure, unit, capabilities, effective_headroom,
    )
    target_text = unit["text"]
    prompt_version = PROMPT_VERSIONS[profile_id]
    config_version = CONFIG_VERSIONS[profile_id]
    prompt_text = _render_prompt(
        profile_id, context_segments, source_language, applicable_rules,
        approved_decisions, local_state, source_context,
    )
    _require(len(prompt_text.encode("utf-8")) <= MAX_PROMPT_BYTES, "oversized translation prompt")

    caller_context_fingerprint = fingerprint({
        "approved_decisions": approved_decisions, "local_state": local_state, "source_context": source_context,
    })

    cache_key = compute_cache_key(
        profile_id=profile_id, pdf_hash=structure["pdf_hash"], source_uri=structure["source_uri"],
        document_id=unit["document_id"], reading_id=unit["reading_id"], reading_version=unit["reading_version"],
        reading_text_hash=unit["reading_text_hash"], unit_id=unit["unit_id"], unit_version=unit["unit_version"],
        source_char_start=unit["source_char_start"], source_char_end=unit["source_char_end"],
        unit_text_hash=text_hash(target_text), neighbor_fingerprint=fingerprint(context_segments),
        policy_fingerprint=policy_fingerprint, provider=provider, model=model,
        prompt_version=prompt_version, config_version=config_version,
        decoding_params={
            **DECODING_PARAMS,
            "provider_definition": provider_definition.to_dict() if provider_definition else None,
            "capabilities": capabilities.to_dict() if capabilities else None,
        },
        caller_context_fingerprint=caller_context_fingerprint,
        context_policy_version=context_strategy.CONTEXT_POLICY_VERSION,
        context_mode=decision["context_mode"],
    )

    return TranslationRequest(
        profile_id=profile_id, provider=provider, model=model, source_language=source_language,
        target_language=TARGET_LANGUAGE, structure=structure, glossary_store=glossary,
        unit=unit, context_segments=context_segments,
        applicable_rules=applicable_rules, proposed_loaded_rules=proposed_loaded_rules,
        policy_fingerprint=policy_fingerprint,
        approved_decisions=tuple(approved_decisions), local_state=local_state, source_context=source_context,
        caller_context_fingerprint=caller_context_fingerprint,
        prompt_version=prompt_version, config_version=config_version,
        prompt_text=prompt_text, cache_key=cache_key,
        provider_definition=provider_definition, capabilities=capabilities,
        target_text=target_text, target_unit_ids=(unit["unit_id"],),
        context_mode=decision["context_mode"], context_policy_version=context_strategy.CONTEXT_POLICY_VERSION,
        chapter_node_id=decision["chapter_node_id"], crosses_page_boundary=decision["crosses_page_boundary"],
        context_headroom_fraction=effective_headroom,
    )


def build_translation_request_for_role(structure, glossary, unit_id, profile_id,
                                       configuration: ModelConfiguration,
                                       role="translator", context_headroom_fraction=None) -> TranslationRequest:
    """Resolve an explicit role selection before constructing the core request.

    The resolved role's `ModelCapabilities` automatically activates the
    Session D chapter-aware context strategy (see `build_translation_request`).
    """
    if not isinstance(configuration, ModelConfiguration):
        raise TranslationRequestError("configuration must be a validated ModelConfiguration")
    selection, definition = configuration.resolve(role)
    return build_translation_request(
        structure, glossary, unit_id, profile_id, selection.provider, selection.model,
        provider_definition=definition, capabilities=selection.capabilities,
        context_headroom_fraction=context_headroom_fraction,
    )


def build_whole_chapter_translation_request(
    structure, glossary, unit_id, profile_id, provider, model,
    provider_definition=None, capabilities=None,
    approved_decisions=None, local_state=None, source_context=None,
    context_headroom_fraction=None,
) -> TranslationRequest:
    """Session D whole-chapter comparison mode (spec section 7): translate an
    entire enclosing chapter as one target in a single request, instead of
    per semantic unit with chapter context. Never the default: callers opt
    in explicitly, e.g. to compare against `build_translation_request` on
    the same chapter for quality/completeness/runtime/cost.

    `unit_id` only anchors which chapter to resolve (any real unit inside
    it); the actual target becomes every unit in that chapter concatenated
    in document order. Requires `capabilities` so the chapter can be
    checked against the same budget used by the default per-unit context
    decision; refuses (raises `TranslationRequestError`) rather than
    silently truncating or summarizing a chapter that does not fit
    comfortably, and refuses a flat/short document with no enclosing
    chapter/part node at all.
    """
    try:
        if profile_id not in SUPPORTED_PROFILE_IDS:
            raise ProfileError(f"profile_id must be one of {SUPPORTED_PROFILE_IDS}; no fallback profile")
        approved_decisions = validate_approved_decisions(approved_decisions)
        local_state = validate_local_state(local_state)
        source_context = validate_source_context(source_context)
    except ProfileError as exc:
        raise TranslationRequestError(str(exc)) from None
    try:
        validate_structure(structure)
        validate_glossary(glossary)
    except (StructureError, GlossaryError):
        raise TranslationRequestError("invalid source or glossary for translation") from None
    _require(not structure["continuity"], "structure has unresolved continuity findings")
    _require(isinstance(provider, str) and bool(provider.strip()), "unsupported provider")
    _require(isinstance(model, str) and bool(model.strip()), "unsupported model for provider")
    if provider == "mock":
        _require(model == "mock-translation-1", "unsupported model for mock provider")
    elif provider_definition is None:
        _require(provider in {"openai", "anthropic", "deepseek"},
                 "custom provider requires an explicit provider definition")
    else:
        _require(isinstance(provider_definition, ProviderDefinition)
                 and provider_definition.provider_id == provider,
                 "provider definition does not match selected provider")
    _require(isinstance(capabilities, ModelCapabilities),
             "whole-chapter mode requires model capability metadata to check the chapter fits")

    unit = next((u for u in structure["units"] if u["unit_id"] == unit_id), None)
    _require(unit is not None, "unknown or missing unit for translation job")
    source_language = unit["language"]
    _require(source_language in SUPPORTED_SOURCE_LANGUAGES, "unsupported source language")

    effective_headroom = (
        context_strategy.DEFAULT_HEADROOM_FRACTION if context_headroom_fraction is None else context_headroom_fraction
    )
    chapter_node = context_strategy.find_enclosing_chapter_node(structure, unit)
    _require(chapter_node is not None, "whole-chapter mode requires an enclosing chapter/part node")
    span_nodes = context_strategy.chapter_node_span(structure, chapter_node)
    budget = context_strategy.available_chapter_token_budget(capabilities, effective_headroom)
    estimated = sum(context_strategy.estimate_tokens(n["text"]) for n in span_nodes)
    _require(estimated <= budget,
             "chapter too large for whole-chapter mode within the model's usable context budget")

    target_unit_ids = tuple(context_strategy.chapter_unit_ids(structure, span_nodes))
    _require(target_unit_ids, "no translation units found in enclosing chapter")
    units_by_id = {u["unit_id"]: u for u in structure["units"]}
    member_units = [units_by_id[uid] for uid in target_unit_ids if uid in units_by_id]
    _require(len(member_units) == len(target_unit_ids), "chapter contains units outside the resolved structure")
    target_text = "\n\n".join(u["text"] for u in member_units)

    approved_by_id, proposed_loaded_by_id = {}, {}
    for uid in target_unit_ids:
        resolution = resolve_applicable(glossary, structure, uid)
        _require(resolution["status"] != "needs_human", "conflicting glossary resolution for unit in chapter")
        for rule in resolution["approved_rules"]:
            approved_by_id[rule["rule_id"]] = rule
        for rule in resolution["proposed_rules"]:
            if rule["loaded"]:
                proposed_loaded_by_id[rule["rule_id"]] = rule
    applicable_rules = sorted(approved_by_id.values(), key=lambda r: r["rule_id"])
    proposed_loaded_rules = sorted(proposed_loaded_by_id.values(), key=lambda r: r["rule_id"])
    policy_fingerprint = effective_fingerprint(applicable_rules)

    anchor_unit = member_units[0]
    context_segments = [{
        "role": "target", "unit_id": None, "unit_version": None,
        "node_ids": [n["node_id"] for n in span_nodes], "text": target_text, "text_hash": text_hash(target_text),
    }]
    prompt_version = PROMPT_VERSIONS[profile_id]
    config_version = CONFIG_VERSIONS[profile_id]
    prompt_text = _render_prompt(
        profile_id, context_segments, source_language, applicable_rules,
        approved_decisions, local_state, source_context,
    )
    _require(len(prompt_text.encode("utf-8")) <= MAX_PROMPT_BYTES, "oversized translation prompt")

    caller_context_fingerprint = fingerprint({
        "approved_decisions": approved_decisions, "local_state": local_state, "source_context": source_context,
    })
    composite_unit_id = deterministic_id(
        "chapter-translation-target", chapter_node["node_id"], *sorted(target_unit_ids),
    )
    cache_key = compute_cache_key(
        profile_id=profile_id, pdf_hash=structure["pdf_hash"], source_uri=structure["source_uri"],
        document_id=anchor_unit["document_id"], reading_id=anchor_unit["reading_id"],
        reading_version=anchor_unit["reading_version"], reading_text_hash=anchor_unit["reading_text_hash"],
        unit_id=composite_unit_id, unit_version=1,
        source_char_start=anchor_unit["source_char_start"], source_char_end=member_units[-1]["source_char_end"],
        unit_text_hash=text_hash(target_text), neighbor_fingerprint=fingerprint(context_segments),
        policy_fingerprint=policy_fingerprint, provider=provider, model=model,
        prompt_version=prompt_version, config_version=config_version,
        decoding_params={
            **DECODING_PARAMS,
            "provider_definition": provider_definition.to_dict() if provider_definition else None,
            "capabilities": capabilities.to_dict() if capabilities else None,
        },
        caller_context_fingerprint=caller_context_fingerprint,
        context_policy_version=context_strategy.CONTEXT_POLICY_VERSION,
        context_mode="whole_chapter_translation",
    )

    return TranslationRequest(
        profile_id=profile_id, provider=provider, model=model, source_language=source_language,
        target_language=TARGET_LANGUAGE, structure=structure, glossary_store=glossary,
        unit=anchor_unit, context_segments=context_segments,
        applicable_rules=applicable_rules, proposed_loaded_rules=proposed_loaded_rules,
        policy_fingerprint=policy_fingerprint,
        approved_decisions=tuple(approved_decisions), local_state=local_state, source_context=source_context,
        caller_context_fingerprint=caller_context_fingerprint,
        prompt_version=prompt_version, config_version=config_version,
        prompt_text=prompt_text, cache_key=cache_key,
        provider_definition=provider_definition, capabilities=capabilities,
        target_text=target_text, target_unit_ids=target_unit_ids,
        context_mode="whole_chapter_translation", context_policy_version=context_strategy.CONTEXT_POLICY_VERSION,
        chapter_node_id=chapter_node["node_id"],
        crosses_page_boundary=len({n["page_id"] for n in span_nodes}) > 1,
        context_headroom_fraction=effective_headroom,
    )


def run_translation(request: TranslationRequest, adapter=None, budget=None, cache=None) -> dict:
    """Run the resolved request through a text-generation adapter and formal checks.

    Returns a schema-1 `translation-draft@1` dict with `approved` always
    False. A formal-check failure never sets approval; a formally clean draft
    remains `draft_unapproved`, not approved. An optional `cache` (e.g.
    `runtime_controls.RuntimeCache`) may supply a prior successful raw
    result for `request.cache_key`, skipping the adapter call and any
    budget reservation/cost entirely; formal checks below always rerun
    against the resulting text regardless of its origin.
    """
    if not isinstance(request, TranslationRequest):
        raise TranslationRequestError("run_translation requires a resolved TranslationRequest")
    if request.context_mode == "whole_chapter_translation":
        canonical = build_whole_chapter_translation_request(
            request.structure, request.glossary_store, request.target_unit_ids[0],
            request.profile_id, request.provider, request.model,
            provider_definition=request.provider_definition, capabilities=request.capabilities,
            approved_decisions=list(request.approved_decisions),
            local_state=request.local_state, source_context=request.source_context,
            context_headroom_fraction=request.context_headroom_fraction,
        )
    else:
        canonical = build_translation_request(
            request.structure, request.glossary_store, request.unit["unit_id"],
            request.profile_id, request.provider, request.model,
            provider_definition=request.provider_definition, capabilities=request.capabilities,
            approved_decisions=list(request.approved_decisions),
            local_state=request.local_state, source_context=request.source_context,
            context_headroom_fraction=request.context_headroom_fraction,
        )
    _require(request == canonical, "translation request changed after source/policy resolution")

    notices = []
    cache_hit = False
    live_provider = request.provider != "mock"
    provider_type = request.provider_definition.provider_type if request.provider_definition else request.provider
    priced_provider = provider_type == "openai"
    if cache is not None:
        adapter = adapter or build_translation_adapter(
            request.provider, request.model, provider_definition=request.provider_definition,
            max_output_tokens=(request.capabilities.max_output_tokens if request.capabilities else None),
        )
        result, cache_hit, control_notices = cache.execute(
            request.cache_key, request.prompt_text, request.model, adapter.generate,
            stage="translate", metadata=request.to_metadata_dict(), budget=budget,
        )
        notices.extend(control_notices)
        duration = result.duration_seconds
    else:
        if adapter is None:
            adapter = build_translation_adapter(
                request.provider, request.model, provider_definition=request.provider_definition,
                max_output_tokens=(request.capabilities.max_output_tokens if request.capabilities else None),
            )
        if live_provider:
            budget = budget or TranslationBudget(max_calls=1)
            notices.extend(budget.reserve(request.prompt_text))

        start = time.monotonic()
        try:
            result = adapter.generate(request.prompt_text, request.model)
        except OpenAIConfigurationError:
            if live_provider:
                budget.release_unstarted()
            raise
        duration = getattr(result, "duration_seconds", time.monotonic() - start)

    token_usage = result.token_usage
    estimate = compute_estimate(token_usage) if priced_provider else "not_metered"
    if live_provider and cache is None:
        if priced_provider:
            notices.extend(budget.record(token_usage))
        else:
            budget.stopped = True
            notices.append("pricing_not_configured_stop")
    raw_text = result.text if result.status in ("completed", "mock_placeholder") else None
    draft_text, translation_note = _parse_structured_output(raw_text)

    findings = run_formal_checks(request.target_text, draft_text, request.source_language)
    for rule in request.proposed_loaded_rules:
        term = rule["source_term"]
        start_offset = request.target_text.find(term)
        findings.append({
            "type": "unapproved_loaded_term", "source_token": term,
            "source_char_start": start_offset, "source_char_end": start_offset + len(term),
            "target_evidence": None, "severity": "needs_human",
        })
    if priced_provider and estimate == "not_metered":
        findings.append({
            "type": "usage_not_metered", "source_token": None,
            "source_char_start": None, "source_char_end": None,
            "target_evidence": None, "severity": "needs_human",
        })
    elif live_provider and not priced_provider:
        findings.append({
            "type": "pricing_not_configured", "source_token": None,
            "source_char_start": None, "source_char_end": None,
            "target_evidence": None, "severity": "needs_human",
        })
    if result.status == "completed":
        status = "needs_human" if findings else "draft_unapproved"
    else:
        status = result.status

    draft = dict(request.to_metadata_dict())
    draft.update({
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "observed_model": result.observed_model,
        "observed_provider": result.observed_provider or request.provider,
        "status": status,
        "draft_text": draft_text,
        "translation_note": translation_note,
        "token_usage": token_usage,
        "pricing_version": PRICING_VERSION,
        "estimated_cost_usd": estimate,
        "budget_notices": notices,
        "actual_charge": "not_metered" if cache_hit else (
            "unknown" if live_provider else "not_metered"
        ),
        "duration_seconds": duration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "error": result.error,
        "approved": False,
        "cache_hit": cache_hit,
    })
    if cache is not None:
        draft["control_provenance"] = dict(cache.provenance[-1])
    return draft
