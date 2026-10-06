"""Session C: optional semantic review, candidate comparison and chapter QA.

A lightweight, provider-neutral review/evaluation layer over already
selected source/context and already produced Hebrew. This module does not
redesign segmentation, context selection, Gate-8 correction behavior,
provider adapters, runtime budget/cache controls or persistent schemas; it
takes explicit plain-data requests (never instructions) and returns
schema-versioned, unapproved plain-data records.

Three independent jobs, each faithfully rendering one versioned runtime
prompt asset under ``runtime_prompts/``:

- unit review (``04_independent_semantic_review.md``): PASS or REVISE with
  grounded, severity-classified issues;
- candidate comparison (``05_candidate_comparison.md``): material
  differences, per-candidate assessments and a best-supported candidate or
  NO_CLEAR_WINNER over 2-3 anonymous candidates;
- chapter-level QA (``06_chapter_level_qa.md``): cross-unit boundary,
  consistency, continuity and Hebrew-quality issues with local corrections,
  never a wholesale retranslation.

The adapter boundary is a minimal injected ``generate(prompt_text, model)``
callable returning a ``model_adapter.TextGenerationResult``; tests use
deterministic fakes and make no network/provider call. All records remain
``approved: false``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .model_adapter import (
    PRICING_VERSION, TextGenerationResult, build_translation_adapter, estimate_model_cost,
)
from .document_state import CATEGORIES as STATE_CATEGORIES
from .model_config import ModelCapabilities, ModelConfiguration, ProviderDefinition
from .source_reading import fingerprint, text_hash

SCHEMA_VERSION = 1
STAGE_UNIT_REVIEW = "unit-review@1"
STAGE_CANDIDATE_COMPARISON = "candidate-comparison@1"
STAGE_CHAPTER_QA = "chapter-qa@1"

_PROMPT_DIR = Path(__file__).resolve().parent / "runtime_prompts"
UNIT_REVIEW_PROMPT_ID = "independent-semantic-review@1"
CANDIDATE_COMPARISON_PROMPT_ID = "candidate-comparison@1"
CHAPTER_QA_PROMPT_ID = "chapter-level-qa@1"
_PROMPT_FILENAMES = {
    UNIT_REVIEW_PROMPT_ID: "04_independent_semantic_review.md",
    CANDIDATE_COMPARISON_PROMPT_ID: "05_candidate_comparison.md",
    CHAPTER_QA_PROMPT_ID: "06_chapter_level_qa.md",
}
_OUTPUT_CONTRACTS = {
    CANDIDATE_COMPARISON_PROMPT_ID: """

STRUCTURED_OUTPUT_CONTRACT:
In MATERIAL_DIFFERENCES, write `none` or one difference per line as
`- [stylistic_only|genuine_interpretive_difference|likely_translation_error] description`.
In CANDIDATE_ASSESSMENTS, write each supplied candidate id exactly once as
`candidate id: assessment`. Use no candidate ids other than those supplied.
""",
    CHAPTER_QA_PROMPT_ID: """

STRUCTURED_OUTPUT_CONTRACT:
In ISSUES, write `none` or number every issue using exactly these fields:
1. Category: completeness | consistency | continuity | hebrew_quality
   Severity: CRITICAL | MAJOR | MINOR
   Span: one line copied verbatim from HEBREW_CHAPTER or SOURCE_CHAPTER, without added quotes or backticks
   Correction: a nonempty local correction that changes the text, never a wholesale retranslation
Each field on one line. List only issues you stand behind: no comments or retractions inside ISSUES.
In STATE_UPDATES, write `none` or one proposed persistent-state item per
line, in exactly this form (double-colon separated, no extra `::`):
- [category] label :: value :: certainty :: span
where `category` is one of """ + ", ".join(sorted(STATE_CATEGORIES)) + """;
`certainty` is `likely` or `unresolved` (never `established`); and `span`
is an exact literal substring of SOURCE_CHAPTER.
""",
}

UNIT_REVIEW_POLICIES = {"off", "risk_based", "all"}
CHAPTER_QA_POLICIES = {"off", "on"}
SEVERITIES = {"CRITICAL", "MAJOR", "MINOR"}
CHAPTER_ISSUE_CATEGORIES = {"completeness", "consistency", "continuity", "hebrew_quality"}
# A model may never author an "established" fact (document_state.py enforces
# this too, as defense in depth); chapter QA may only ever propose "likely"
# or "unresolved" persistent-state candidates.
STATE_UPDATE_CERTAINTIES = {"likely", "unresolved"}
DIFFERENCE_CLASSIFICATIONS = {
    "stylistic_only", "genuine_interpretive_difference", "likely_translation_error",
}
RISK_FLAG_KEYS = {"translation_notes", "extraction_or_ocr_risk", "formal_check_failure"}
VERDICTS = {"PASS", "REVISE"}

_HEBREW_RE = re.compile(r"[֑-׿]")


class ReviewQARequestError(ValueError):
    """Invalid review/comparison/QA request. Never includes source or translation text."""


def _require(condition, message):
    if not condition:
        raise ReviewQARequestError(message)


def _require_nonempty_str(value, message):
    _require(isinstance(value, str) and value.strip(), message)


def _require_hebrew(value, message):
    _require_nonempty_str(value, message)
    _require(bool(_HEBREW_RE.search(value)), message)


def _require_string_sequence(value, message):
    _require(isinstance(value, (list, tuple)), message)
    _require(all(isinstance(item, str) and item.strip() for item in value), message)


def _prompt_text(prompt_id: str) -> str:
    path = _PROMPT_DIR / _PROMPT_FILENAMES[prompt_id]
    return path.read_text(encoding="utf-8")


def _render(prompt_id: str, substitutions: dict) -> str:
    text = _prompt_text(prompt_id)
    for key in substitutions:
        token = "{{" + key + "}}"
        _require(token in text, "runtime prompt is missing a required input placeholder")
    pattern = re.compile(r"\{\{(" + "|".join(re.escape(key) for key in substitutions) + r")\}\}")
    text = pattern.sub(lambda match: substitutions[match.group(1)], text)
    # Optional placeholder: callers that do not supply a notebook render "(none)".
    text = text.replace("{{book_notebook}}", "(none)")
    # Optional block: callers without deterministic review focus add nothing.
    text = text.replace("{{review_focus}}", "")
    return text + _OUTPUT_CONTRACTS.get(prompt_id, "")


def _context_text(context_segments) -> str:
    if not context_segments:
        return "(none)"
    return "\n".join(str(segment) for segment in context_segments)


def _glossary_text(glossary_decisions) -> str:
    if not glossary_decisions:
        return "(none)"
    return "\n".join(str(entry) for entry in glossary_decisions)


def _provider_type(provider, provider_definition):
    return provider_definition.provider_type if provider_definition else provider


def _call_record(result, prompt_text, request) -> dict:
    from .model_catalog import estimate_cost, CATALOG_VERSION
    custom_rates = request.capabilities.custom_pricing if request.capabilities else None
    quote = estimate_cost(_provider_type(request.provider, request.provider_definition), request.model,
                          result.token_usage, custom_rates=custom_rates) if request.provider != 'mock' else None
    estimate = (estimate_model_cost(_provider_type(request.provider, request.provider_definition),
                                   request.model, result.token_usage, custom_rates=custom_rates)
                if request.provider != "mock" else "not_metered")
    return {
        "prompt_hash": text_hash(prompt_text), "provider": request.provider,
        "model": request.model, "observed_provider": result.observed_provider or request.provider,
        "observed_model": result.observed_model,
        "token_usage": result.token_usage, "pricing_version": PRICING_VERSION,
        "estimated_cost_usd": estimate, "status": result.status, "error": result.error,
        'pricing_basis': quote['basis'] if quote else 'not_metered', 'catalog_version': CATALOG_VERSION,
        "actual_charge": "unknown",
    }


def _check_review_prompt(prompt_text, request):
    from .token_counting import count_tokens
    if request.capabilities is None:
        return
    needed = count_tokens(prompt_text, request.model)['upper_bound'] + 1024
    needed += request.capabilities.max_output_tokens or 0
    _require(len(prompt_text.encode('utf-8')) <= 2_000_000 and
             needed <= request.capabilities.usable_context_tokens,
             'review prompt exceeds the selected model context including output')


def _base_record(stage, prompt_id, provider, model, policy,
                 provider_definition=None, capabilities=None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "prompt_id": prompt_id,
        "prompt_version": prompt_id,
        "prompt_asset_hash": text_hash(_prompt_text(prompt_id)),
        "policy": policy,
        "provider": provider,
        "model": model,
        "provider_type": _provider_type(provider, provider_definition),
        "model_capabilities": capabilities.to_dict() if capabilities else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approved": False,
        "error": None,
    }


# --- Unit review (04_independent_semantic_review.md) -----------------------


@dataclass(frozen=True)
class UnitReviewRequest:
    source_text: str
    translation: str
    source_context: tuple
    glossary_decisions: tuple
    policy: str
    risk_flags: dict
    provider: str
    model: str
    provider_definition: ProviderDefinition | None = None
    capabilities: ModelCapabilities | None = None


def build_unit_review_request(
    source_text, translation, source_context=(), glossary_decisions=(),
    policy="off", risk_flags=None, provider="mock", model="mock-review-1",
    provider_definition=None, capabilities=None,
) -> UnitReviewRequest:
    _require_nonempty_str(source_text, "source_text must be a nonempty string")
    _require_hebrew(translation, "translation must be a nonempty Hebrew string")
    _require(policy in UNIT_REVIEW_POLICIES, "unit review policy must be off, risk_based or all")
    _require_string_sequence(source_context, "source_context must contain only nonempty strings")
    _require_string_sequence(glossary_decisions, "glossary_decisions must contain only nonempty strings")

    risk_flags = {} if risk_flags is None else risk_flags
    _require(isinstance(risk_flags, dict), "risk_flags must be an object")
    configured = risk_flags.get("configured_risk_flags", [])
    _require(isinstance(configured, (list, tuple)), "configured_risk_flags must be a list")
    _require(
        all(isinstance(flag, str) and flag.strip() for flag in configured),
        "configured_risk_flags must be nonempty strings",
    )
    for key, value in risk_flags.items():
        if key == "configured_risk_flags":
            continue
        _require(key in RISK_FLAG_KEYS, "risk_flags contains an unknown flag")
        _require(isinstance(value, bool), "risk_flags values must be booleans")

    _require_nonempty_str(provider, "provider must be a nonempty string")
    _require_nonempty_str(model, "model must be a nonempty string")
    _require(provider_definition is None or (
        isinstance(provider_definition, ProviderDefinition)
        and provider_definition.provider_id == provider
    ), "provider definition does not match selected provider")
    _require(capabilities is None or isinstance(capabilities, ModelCapabilities),
             "invalid model capability metadata")

    return UnitReviewRequest(
        source_text=source_text, translation=translation,
        source_context=tuple(source_context), glossary_decisions=tuple(glossary_decisions),
        policy=policy, risk_flags=dict(risk_flags), provider=provider, model=model,
        provider_definition=provider_definition, capabilities=capabilities,
    )


def build_unit_review_request_for_role(
    source_text, translation, configuration: ModelConfiguration,
    source_context=(), glossary_decisions=(), policy="off", risk_flags=None,
) -> UnitReviewRequest:
    _require(isinstance(configuration, ModelConfiguration),
             "configuration must be a validated ModelConfiguration")
    selection, definition = configuration.resolve("semantic_reviewer")
    return build_unit_review_request(
        source_text, translation, source_context, glossary_decisions, policy, risk_flags,
        selection.provider, selection.model, definition, selection.capabilities,
    )


def _unit_review_is_risky(risk_flags: dict) -> bool:
    configured = risk_flags.get("configured_risk_flags", [])
    if configured:
        return True
    return any(risk_flags.get(key) for key in RISK_FLAG_KEYS)


_UNIT_ISSUE_RE = re.compile(
    r"\d+\.\s*Severity:\s*(?P<severity>[^\n]+)\n"
    r"\s*Source span:\s*(?P<source_span>[^\n]*)\n"
    r"\s*Translation span:\s*(?P<translation_span>[^\n]*)\n"
    r"\s*Problem:\s*(?P<problem>[^\n]*)\n"
    r"\s*Suggested correction:\s*(?P<correction>[^\n]*)",
)


_SPAN_WRAPPERS = (('"', '"'), ("“", "”"), ("„", "”"), ("„", "“"),
                  ("״", "״"), ("'", "'"), ("‘", "’"), ("`", "`"), ("«", "»"),
                  ("”", "”"))


def _unwrap_once(text):
    for opening, closing in _SPAN_WRAPPERS:
        if len(text) > len(opening) + len(closing) and text.startswith(opening) and text.endswith(closing):
            return text[len(opening):-len(closing)].strip()
    if len(text) > 1 and text.endswith("."):
        return text[:-1].strip()
    return None


def _unwrap(text):
    text = (text or "").strip()
    while True:
        inner = _unwrap_once(text)
        if inner is None or not inner:
            return text
        text = inner


def ground_span(span, *texts):
    """The span as it literally occurs in one of ``texts``: exact first, else after
    removing matching quote/backtick wrappers and a final period (repeatedly). Models
    often quote the span they cite; the stored span is always a real substring.
    Returns None when the span is not grounded."""
    candidate = (span or "").strip()
    while candidate:
        if any(candidate in text for text in texts):
            return candidate
        candidate = _unwrap_once(candidate)
    return None


def _issue_slices(block, matches):
    """(match, stray) per structured issue; ``stray`` is any non-blank text between this
    issue and the next one (comments, retractions, extra lines)."""
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        yield match, block[match.end():end].strip()


def _parse_unit_review_response(raw_text, request: UnitReviewRequest):
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None, "model response was empty"
    verdict_match = re.search(r"VERDICT:\s*(\S+)", raw_text)
    if verdict_match is None or verdict_match.group(1) not in VERDICTS:
        return None, "model response did not contain a valid VERDICT"
    verdict = verdict_match.group(1)

    issues_match = re.search(r"ISSUES:\s*(.*)", raw_text, re.DOTALL)
    if issues_match is None:
        return None, "model response did not contain an ISSUES section"
    issues_block = issues_match.group(1).strip()

    issues, dropped = [], 0
    if issues_block.rstrip(".").lower() != "none":
        matches = list(_UNIT_ISSUE_RE.finditer(issues_block))
        if not matches:
            return None, "ISSUES section contains malformed or unexpected content"
        # Each issue stands alone: one that is ungrounded, incomplete or followed by
        # stray text (often a retraction) is dropped and counted, never guessed at.
        for match, stray in _issue_slices(issues_block, matches):
            severity = match.group("severity").strip()
            source_span = ground_span(match.group("source_span"), request.source_text)
            translation_span = ground_span(match.group("translation_span"), request.translation)
            problem = match.group("problem").strip()
            correction = match.group("correction").strip()
            if (stray or severity not in SEVERITIES or source_span is None or translation_span is None
                    or not problem or not correction or _unwrap(correction) == translation_span):
                dropped += 1
                continue
            issues.append({
                "severity": severity, "source_span": source_span,
                "translation_span": translation_span, "problem": problem,
                "suggested_correction": correction,
            })

    if verdict == "PASS" and issues:
        return None, "PASS verdict must not carry invented issues"
    if verdict == "REVISE" and not issues:
        return None, ("every REVISE issue was ungrounded or malformed" if dropped
                      else "REVISE verdict must carry at least one grounded issue")
    return {"verdict": verdict, "issues": issues, "dropped_issues": dropped}, None


def run_unit_review(request: UnitReviewRequest, generate=None) -> dict:
    """Run the unit-review workflow. Returns an unapproved schema-1 `unit-review@1` dict."""
    _require(isinstance(request, UnitReviewRequest), "run_unit_review requires a resolved UnitReviewRequest")
    request = build_unit_review_request(
        request.source_text, request.translation, request.source_context, request.glossary_decisions,
        request.policy, request.risk_flags, request.provider, request.model,
        request.provider_definition, request.capabilities,
    )
    base = _base_record(
        STAGE_UNIT_REVIEW, UNIT_REVIEW_PROMPT_ID, request.provider, request.model,
        request.policy, request.provider_definition, request.capabilities,
    )
    base["risk_flags"] = dict(request.risk_flags)
    base["input_hash"] = fingerprint({
        "source_text": request.source_text,
        "translation": request.translation,
        "source_context": request.source_context,
        "glossary_decisions": request.glossary_decisions,
        "policy": request.policy,
        "risk_flags": request.risk_flags,
    })

    if request.policy == "off":
        return dict(base, status="skipped", skip_reason="policy_off", verdict=None, issues=[], call=None)
    if request.policy == "risk_based" and not _unit_review_is_risky(request.risk_flags):
        return dict(base, status="skipped", skip_reason="no_risk_flagged", verdict=None, issues=[], call=None)

    if generate is None and request.provider_definition is not None:
        generate = build_translation_adapter(
            request.provider, request.model, provider_definition=request.provider_definition,
            max_output_tokens=(request.capabilities.max_output_tokens if request.capabilities else None),
        ).generate
    _require(callable(generate), "a generate callable is required when the adapter is invoked")
    prompt_text = _render(UNIT_REVIEW_PROMPT_ID, {
        "source_context": _context_text(request.source_context),
        "source_text": request.source_text,
        "translation": request.translation,
        "glossary_and_decisions": _glossary_text(request.glossary_decisions),
    })
    _check_review_prompt(prompt_text, request)
    try:
        result = generate(prompt_text, request.model)
    except Exception:
        return dict(
            base, status="failed", skip_reason=None, verdict=None, issues=[], call=None,
            error="adapter call failed",
        )
    if not isinstance(result, TextGenerationResult):
        return dict(
            base, status="failed", skip_reason=None, verdict=None, issues=[], call=None,
            error="adapter returned an invalid result",
        )
    call = _call_record(result, prompt_text, request)
    if result.status not in ("completed", "mock_placeholder"):
        return dict(base, status="failed", skip_reason=None, verdict=None, issues=[], call=call)

    parsed, parse_error = _parse_unit_review_response(result.text, request)
    if parse_error is not None:
        return dict(
            base, status="needs_human", skip_reason=None, verdict=None, issues=[],
            call=call, error=parse_error,
        )
    return dict(
        base, status="completed", skip_reason=None,
        verdict=parsed["verdict"], issues=parsed["issues"], call=call,
        dropped_issues=parsed["dropped_issues"],
    )


# --- Candidate comparison (05_candidate_comparison.md) ----------------------


@dataclass(frozen=True)
class CandidateComparisonRequest:
    source_text: str
    source_context: tuple
    glossary_decisions: tuple
    candidates: tuple  # tuple of (candidate_id, text) pairs, order preserved
    provider: str
    model: str
    provider_definition: ProviderDefinition | None = None
    capabilities: ModelCapabilities | None = None


def build_candidate_comparison_request(
    source_text, candidates, source_context=(), glossary_decisions=(),
    provider="mock", model="mock-review-1", provider_definition=None, capabilities=None,
) -> CandidateComparisonRequest:
    _require_nonempty_str(source_text, "source_text must be a nonempty string")
    _require(isinstance(candidates, dict), "candidates must be an object of id -> Hebrew text")
    _require(2 <= len(candidates) <= 3, "candidate comparison requires exactly 2 or 3 candidates")
    for candidate_id, candidate_text in candidates.items():
        _require_nonempty_str(candidate_id, "candidate id must be a nonempty string")
        _require(
            re.fullmatch(r"[A-Za-z0-9_.-]+", candidate_id) is not None,
            "candidate id must use only ASCII letters, digits, dot, underscore or hyphen",
        )
        _require_hebrew(candidate_text, "candidate text must be a nonempty Hebrew string")
    _require_string_sequence(source_context, "source_context must contain only nonempty strings")
    _require_string_sequence(glossary_decisions, "glossary_decisions must contain only nonempty strings")
    _require_nonempty_str(provider, "provider must be a nonempty string")
    _require_nonempty_str(model, "model must be a nonempty string")
    _require(provider_definition is None or (
        isinstance(provider_definition, ProviderDefinition)
        and provider_definition.provider_id == provider
    ), "provider definition does not match selected provider")
    _require(capabilities is None or isinstance(capabilities, ModelCapabilities),
             "invalid model capability metadata")

    return CandidateComparisonRequest(
        source_text=source_text, source_context=tuple(source_context),
        glossary_decisions=tuple(glossary_decisions), candidates=tuple(candidates.items()),
        provider=provider, model=model, provider_definition=provider_definition,
        capabilities=capabilities,
    )


def build_candidate_comparison_request_for_role(
    source_text, candidates, configuration: ModelConfiguration,
    source_context=(), glossary_decisions=(),
) -> CandidateComparisonRequest:
    _require(isinstance(configuration, ModelConfiguration),
             "configuration must be a validated ModelConfiguration")
    selection, definition = configuration.resolve("candidate_evaluator")
    return build_candidate_comparison_request(
        source_text, candidates, source_context, glossary_decisions,
        selection.provider, selection.model, definition, selection.capabilities,
    )


def _candidates_text(candidates) -> str:
    return "\n".join(f"[{candidate_id}]\n{text}" for candidate_id, text in candidates)


_DIFFERENCE_LINE_RE = re.compile(r"-\s*\[(?P<tag>[^\]]+)\]\s*(?P<description>.+)")
_ASSESSMENT_LINE_RE = re.compile(r"(?P<id>[^:\n]+):\s*(?P<assessment>.+)")


def _parse_section(raw_text, header, next_headers):
    pattern = re.escape(header) + r"\s*\n(.*?)(?=" + "|".join(re.escape(h) for h in next_headers) + r"|\Z)"
    match = re.search(pattern, raw_text, re.DOTALL)
    if match is None:
        return None
    return match.group(1).strip()


def _parse_candidate_comparison_response(raw_text, request: CandidateComparisonRequest):
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None, "model response was empty"
    headers = [
        "MATERIAL_DIFFERENCES:", "CANDIDATE_ASSESSMENTS:", "BEST_SUPPORTED_TRANSLATION:",
        "REASON:", "UNCERTAINTIES:",
    ]
    sections = {}
    for i, header in enumerate(headers):
        block = _parse_section(raw_text, header, headers[i + 1:])
        if block is None:
            return None, f"model response is missing the {header} section"
        sections[header] = block

    known_ids = {candidate_id for candidate_id, _ in request.candidates}

    differences_block = sections["MATERIAL_DIFFERENCES:"]
    differences = []
    if differences_block.lower() != "none":
        for line in differences_block.splitlines():
            line = line.strip()
            if not line:
                continue
            match = _DIFFERENCE_LINE_RE.fullmatch(line)
            if match is None:
                return None, "a material difference line is malformed"
            tag = match.group("tag").strip()
            if tag not in DIFFERENCE_CLASSIFICATIONS:
                return None, "a material difference classification is not allowlisted"
            description = match.group("description").strip()
            if not description:
                return None, "a material difference description is missing"
            differences.append({"classification": tag, "description": description})

    assessments_block = sections["CANDIDATE_ASSESSMENTS:"]
    assessments = {}
    for line in assessments_block.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _ASSESSMENT_LINE_RE.fullmatch(line)
        if match is None:
            return None, "a candidate assessment line is malformed"
        candidate_id = match.group("id").strip()
        if candidate_id not in known_ids:
            return None, "a candidate assessment refers to an unknown candidate id"
        if candidate_id in assessments:
            return None, "a candidate assessment is duplicated"
        assessment = match.group("assessment").strip()
        if not assessment:
            return None, "a candidate assessment is empty"
        assessments[candidate_id] = assessment
    if set(assessments) != known_ids:
        return None, "candidate assessments must cover every known candidate exactly once"

    best = sections["BEST_SUPPORTED_TRANSLATION:"].strip()
    if best != "NO_CLEAR_WINNER" and best not in known_ids:
        return None, "best supported translation is not a known candidate id or NO_CLEAR_WINNER"

    reason = sections["REASON:"].strip()
    if not reason:
        return None, "reason is missing"
    uncertainties = sections["UNCERTAINTIES:"].strip()

    return {
        "material_differences": differences, "candidate_assessments": assessments,
        "best_supported_translation": best, "reason": reason, "uncertainties": uncertainties,
    }, None


def run_candidate_comparison(request: CandidateComparisonRequest, generate=None) -> dict:
    """Run the candidate-comparison workflow. Returns an unapproved schema-1 `candidate-comparison@1` dict."""
    _require(
        isinstance(request, CandidateComparisonRequest),
        "run_candidate_comparison requires a resolved CandidateComparisonRequest",
    )
    request = build_candidate_comparison_request(
        request.source_text, dict(request.candidates), request.source_context,
        request.glossary_decisions, request.provider, request.model,
        request.provider_definition, request.capabilities,
    )
    base = _base_record(
        STAGE_CANDIDATE_COMPARISON, CANDIDATE_COMPARISON_PROMPT_ID, request.provider, request.model, policy=None,
        provider_definition=request.provider_definition, capabilities=request.capabilities,
    )
    base.pop("policy")
    base["candidate_ids"] = [candidate_id for candidate_id, _ in request.candidates]
    base["input_hash"] = fingerprint({
        "source_text": request.source_text,
        "source_context": request.source_context,
        "glossary_decisions": request.glossary_decisions,
        "candidates": request.candidates,
    })

    if generate is None and request.provider_definition is not None:
        generate = build_translation_adapter(
            request.provider, request.model, provider_definition=request.provider_definition,
            max_output_tokens=(request.capabilities.max_output_tokens if request.capabilities else None),
        ).generate
    _require(callable(generate), "a generate callable is required")

    prompt_text = _render(CANDIDATE_COMPARISON_PROMPT_ID, {
        "source_context": _context_text(request.source_context),
        "source_text": request.source_text,
        "glossary_and_decisions": _glossary_text(request.glossary_decisions),
        "candidates": _candidates_text(request.candidates),
    })
    _check_review_prompt(prompt_text, request)
    try:
        result = generate(prompt_text, request.model)
    except Exception:
        return dict(base, status="failed", call=None, result=None, error="adapter call failed")
    if not isinstance(result, TextGenerationResult):
        return dict(base, status="failed", call=None, result=None, error="adapter returned an invalid result")
    call = _call_record(result, prompt_text, request)
    if result.status not in ("completed", "mock_placeholder"):
        return dict(base, status="failed", call=call, result=None)

    parsed, parse_error = _parse_candidate_comparison_response(result.text, request)
    if parse_error is not None:
        return dict(base, status="needs_human", call=call, result=None, error=parse_error)
    return dict(base, status="completed", call=call, result=parsed)


# --- Chapter-level QA (06_chapter_level_qa.md) ------------------------------


@dataclass(frozen=True)
class ChapterQARequest:
    source_chapter: str
    hebrew_chapter: str
    profile: str
    glossary_decisions: tuple
    policy: str
    provider: str
    model: str
    provider_definition: ProviderDefinition | None = None
    capabilities: ModelCapabilities | None = None
    book_notebook: str = ""


def build_chapter_qa_request(
    source_chapter, hebrew_chapter, profile="", glossary_decisions=(),
    policy="off", provider="mock", model="mock-review-1",
    provider_definition=None, capabilities=None, book_notebook="",
) -> ChapterQARequest:
    _require_nonempty_str(source_chapter, "source_chapter must be a nonempty string")
    _require_hebrew(hebrew_chapter, "hebrew_chapter must be a nonempty Hebrew string")
    _require(isinstance(profile, str), "profile must be a string")
    _require(isinstance(book_notebook, str), "book_notebook must be a string")
    _require_string_sequence(glossary_decisions, "glossary_decisions must contain only nonempty strings")
    _require(policy in CHAPTER_QA_POLICIES, "chapter QA policy must be off or on")
    _require_nonempty_str(provider, "provider must be a nonempty string")
    _require_nonempty_str(model, "model must be a nonempty string")
    _require(provider_definition is None or (
        isinstance(provider_definition, ProviderDefinition)
        and provider_definition.provider_id == provider
    ), "provider definition does not match selected provider")
    _require(capabilities is None or isinstance(capabilities, ModelCapabilities),
             "invalid model capability metadata")

    return ChapterQARequest(
        source_chapter=source_chapter, hebrew_chapter=hebrew_chapter, profile=profile,
        glossary_decisions=tuple(glossary_decisions), policy=policy, provider=provider, model=model,
        provider_definition=provider_definition, capabilities=capabilities,
        book_notebook=book_notebook,
    )


def build_chapter_qa_request_for_role(
    source_chapter, hebrew_chapter, configuration: ModelConfiguration,
    profile="", glossary_decisions=(), policy="off", book_notebook="",
) -> ChapterQARequest:
    _require(isinstance(configuration, ModelConfiguration),
             "configuration must be a validated ModelConfiguration")
    selection, definition = configuration.resolve("chapter_qa")
    return build_chapter_qa_request(
        source_chapter, hebrew_chapter, profile, glossary_decisions, policy,
        selection.provider, selection.model, definition, selection.capabilities,
        book_notebook,
    )


_CHAPTER_ISSUE_RE = re.compile(
    r"\d+\.\s*Category:\s*(?P<category>[^\n]+)\n"
    r"\s*Severity:\s*(?P<severity>[^\n]+)\n"
    r"\s*Span:\s*(?P<span>[^\n]*)\n"
    r"\s*Correction:\s*(?P<correction>[^\n]*)",
)

_STATE_UPDATE_LINE_RE = re.compile(
    r"-\s*\[(?P<category>[^\]]+)\]\s*(?P<label>[^:]+?)\s*::\s*(?P<value>.+?)\s*::\s*"
    r"(?P<certainty>[^:]+?)\s*::\s*(?P<span>.+)",
)


def _parse_state_updates_block(block, source_chapter):
    """Proposed state items, one per line. A malformed, non-allowlisted, ``established``
    or ungrounded line is dropped and counted; it never fails the whole QA result."""
    if block.rstrip(".").lower() == "none":
        return [], 0
    updates, dropped = [], 0
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _STATE_UPDATE_LINE_RE.fullmatch(line)
        if match is None:
            dropped += 1
            continue
        category = match.group("category").strip()
        certainty = match.group("certainty").strip()
        label = match.group("label").strip()
        value = match.group("value").strip()
        span = ground_span(match.group("span"), source_chapter)
        if (category not in STATE_CATEGORIES or certainty not in STATE_UPDATE_CERTAINTIES
                or not label or not value or span is None):
            dropped += 1
            continue
        updates.append({"category": category, "label": label, "value": value,
                         "certainty": certainty, "span": span})
    return updates, dropped


def _parse_chapter_qa_response(raw_text, request: ChapterQARequest):
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None, "model response was empty"
    verdict_match = re.search(r"VERDICT:\s*(\S+)", raw_text)
    if verdict_match is None or verdict_match.group(1) not in VERDICTS:
        return None, "model response did not contain a valid VERDICT"
    verdict = verdict_match.group(1)

    sections_match = re.search(
        r"ISSUES:\s*(.*?)CHAPTER_LEVEL_NOTES:\s*(.*?)STATE_UPDATES:\s*(.*)", raw_text, re.DOTALL,
    )
    if sections_match is None:
        return None, "model response is missing ISSUES, CHAPTER_LEVEL_NOTES or STATE_UPDATES"
    issues_block = sections_match.group(1).strip()
    notes = sections_match.group(2).strip()
    state_updates_block = sections_match.group(3).strip()

    issues, dropped = [], 0
    if issues_block.rstrip(".").lower() != "none":
        matches = list(_CHAPTER_ISSUE_RE.finditer(issues_block))
        if not matches:
            return None, "ISSUES section contains malformed or unexpected content"
        for match, stray in _issue_slices(issues_block, matches):
            category = match.group("category").strip()
            severity = match.group("severity").strip()
            span = ground_span(match.group("span"), request.source_chapter, request.hebrew_chapter)
            correction = match.group("correction").strip()
            if (stray or category not in CHAPTER_ISSUE_CATEGORIES or severity not in SEVERITIES
                    or span is None or not correction or _unwrap(correction) == span):
                dropped += 1
                continue
            issues.append({
                "category": category, "severity": severity, "span": span, "correction": correction,
            })

    if verdict == "PASS" and issues:
        return None, "PASS verdict must not carry invented issues"
    if verdict == "REVISE" and not issues:
        return None, ("every REVISE issue was ungrounded or malformed" if dropped
                      else "REVISE verdict must carry at least one grounded issue")

    state_updates, state_dropped = _parse_state_updates_block(state_updates_block, request.source_chapter)

    return {"verdict": verdict, "issues": issues, "chapter_level_notes": notes,
            "proposed_state_updates": state_updates, "dropped_issues": dropped,
            "dropped_state_updates": state_dropped}, None


def run_chapter_qa(request: ChapterQARequest, generate=None) -> dict:
    """Run the chapter-level QA workflow. Returns an unapproved schema-1 `chapter-qa@1` dict."""
    _require(isinstance(request, ChapterQARequest), "run_chapter_qa requires a resolved ChapterQARequest")
    request = build_chapter_qa_request(
        request.source_chapter, request.hebrew_chapter, request.profile,
        request.glossary_decisions, request.policy, request.provider, request.model,
        request.provider_definition, request.capabilities, request.book_notebook,
    )
    base = _base_record(
        STAGE_CHAPTER_QA, CHAPTER_QA_PROMPT_ID, request.provider, request.model,
        request.policy, request.provider_definition, request.capabilities,
    )
    base["input_hash"] = fingerprint({
        "source_chapter": request.source_chapter,
        "hebrew_chapter": request.hebrew_chapter,
        "profile": request.profile,
        "glossary_decisions": request.glossary_decisions,
        "policy": request.policy,
        **({"book_notebook": request.book_notebook} if request.book_notebook else {}),
    })

    if request.policy == "off":
        return dict(base, status="skipped", skip_reason="policy_off", verdict=None, issues=[],
                    chapter_level_notes=None, call=None, proposed_state_updates=[])

    if generate is None and request.provider_definition is not None:
        generate = build_translation_adapter(
            request.provider, request.model, provider_definition=request.provider_definition,
            max_output_tokens=(request.capabilities.max_output_tokens if request.capabilities else None),
        ).generate
    _require(callable(generate), "a generate callable is required when the adapter is invoked")
    prompt_text = _render(CHAPTER_QA_PROMPT_ID, {
        "source_chapter": request.source_chapter,
        "hebrew_chapter": request.hebrew_chapter,
        "profile": request.profile or "(none)",
        "glossary_and_decisions": _glossary_text(request.glossary_decisions),
        "book_notebook": request.book_notebook.strip() or "(none)",
    })
    _check_review_prompt(prompt_text, request)
    try:
        result = generate(prompt_text, request.model)
    except Exception:
        return dict(
            base, status="failed", skip_reason=None, verdict=None, issues=[],
            chapter_level_notes=None, call=None, error="adapter call failed", proposed_state_updates=[],
        )
    if not isinstance(result, TextGenerationResult):
        return dict(
            base, status="failed", skip_reason=None, verdict=None, issues=[],
            chapter_level_notes=None, call=None, error="adapter returned an invalid result",
            proposed_state_updates=[],
        )
    call = _call_record(result, prompt_text, request)
    if result.status not in ("completed", "mock_placeholder"):
        return dict(base, status="failed", skip_reason=None, verdict=None, issues=[],
                    chapter_level_notes=None, call=call, proposed_state_updates=[])

    parsed, parse_error = _parse_chapter_qa_response(result.text, request)
    if parse_error is not None:
        return dict(
            base, status="needs_human", skip_reason=None, verdict=None, issues=[],
            chapter_level_notes=None, call=call, error=parse_error, proposed_state_updates=[],
        )
    return dict(
        base, status="completed", skip_reason=None, verdict=parsed["verdict"],
        issues=parsed["issues"], chapter_level_notes=parsed["chapter_level_notes"], call=call,
        proposed_state_updates=parsed["proposed_state_updates"], dropped_issues=parsed["dropped_issues"],
        dropped_state_updates=parsed["dropped_state_updates"],
    )
