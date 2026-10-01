"""Gate 10: offline evidence-based quality pilot manifest validator and report.

Validates a human-labeled `pilot-manifest@1` (exact source/reference evidence,
comparable candidate arms, MQM-style expert annotations) and computes a
reproducible `pilot-report@1` of sample counts, error rates, cost/latency and
missing-data flags. This module never infers semantic truth from model output,
never calls a provider, and never selects a quality winner: a per-language/
genre table and any routing recommendation are a separate, later, human-made
deliverable outside this harness.
"""
from __future__ import annotations

import math
import re

from .source_reading import fingerprint, text_hash

SCHEMA_VERSION = 1
STAGE = "pilot-manifest@1"
REPORT_STAGE = "pilot-report@1"

LANGUAGES = {"en", "fr", "ja"}
OCR_LEVELS = {"digital", "ocr"}
ERROR_TYPES = {
    "omission", "addition", "negation", "scope", "quantifier", "modality",
    "referent", "terminology", "ambiguity", "note_citation_formula", "hebrew",
}
SEVERITIES = {"critical", "major", "minor"}
VERDICTS = {"true_positive", "false_positive", "unconfirmed", None}

MIN_TOTAL_SEGMENTS = 72
MIN_PER_LANGUAGE_SEGMENTS = 24

MANIFEST_FIELDS = {"schema_version", "stage", "units"}
UNIT_FIELDS = {
    "unit_id", "document_id", "pdf_hash", "reading_id", "reading_version",
    "source_char_start", "source_char_end", "source_language", "genre", "ocr_level",
    "source_text", "source_word_count", "source_approval", "reference_text", "reference_approval", "arms",
}
APPROVAL_FIELDS = {"actor", "actor_kind", "reason", "text_hash"}
ARM_FIELDS = {
    "arm_id", "provider", "model", "prompt_version", "context_policy", "critic_enabled",
    "glossary_hash", "draft_hash",
    "pages", "observed_cost_usd", "list_estimated_cost_usd", "latency_seconds",
    "correction_minutes", "expert_reviewed", "expert_review", "annotations",
}
EXPERT_REVIEW_FIELDS = {"actor", "actor_kind", "reason", "draft_hash"}
ANNOTATION_FIELDS = {
    "annotation_id", "actor", "actor_kind", "error_type", "severity",
    "source_char_start", "source_char_end", "reviewer_verdict",
}


class EvaluationError(ValueError):
    """Invalid pilot manifest input; messages contain no private source/reference text."""


def _require(condition, message):
    if not condition:
        raise EvaluationError(message)


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _nonneg(value):
    return _finite(value) and value >= 0


def _positive(value):
    return _finite(value) and value > 0


def _integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _validate_approval(approval, text, field_name):
    _require(isinstance(approval, dict) and set(approval) == APPROVAL_FIELDS,
              f"invalid {field_name} shape")
    _require(_nonempty(approval["actor"]) and approval["actor_kind"] == "human" and _nonempty(approval["reason"]),
              f"{field_name} requires an explicit human actor and reason")
    _require(approval["text_hash"] == text_hash(text), f"{field_name} hash does not match its bound text")


def _validate_annotation(annotation, unit, seen_annotation_ids):
    _require(isinstance(annotation, dict) and set(annotation) == ANNOTATION_FIELDS,
              "invalid annotation shape")
    annotation_id = annotation["annotation_id"]
    _require(_nonempty(annotation_id) and annotation_id not in seen_annotation_ids,
              "duplicate or invalid annotation_id")
    seen_annotation_ids.add(annotation_id)
    _require(_nonempty(annotation["actor"]) and annotation["actor_kind"] == "human",
              "annotation requires an explicit human actor")
    _require(isinstance(annotation["error_type"], str) and annotation["error_type"] in ERROR_TYPES,
              "unsupported annotation error_type")
    _require(isinstance(annotation["severity"], str) and annotation["severity"] in SEVERITIES,
              "invalid annotation severity")
    _require((annotation["reviewer_verdict"] is None or isinstance(annotation["reviewer_verdict"], str))
              and annotation["reviewer_verdict"] in VERDICTS,
              "invalid annotation reviewer_verdict")
    start, end = annotation["source_char_start"], annotation["source_char_end"]
    _require(_integer(start, 0) and _integer(end) and start < end <= len(unit["source_text"]),
              "annotation span out of unit source bounds")


def _validate_arm(arm, unit, seen_annotation_ids):
    _require(isinstance(arm, dict) and set(arm) == ARM_FIELDS, "invalid arm shape")
    _require(
        _nonempty(arm["arm_id"]) and _nonempty(arm["provider"]) and _nonempty(arm["model"])
        and _nonempty(arm["prompt_version"]) and _nonempty(arm["context_policy"]),
        "invalid arm identity",
    )
    _require(isinstance(arm["critic_enabled"], bool), "arm critic_enabled must be boolean")
    _require(isinstance(arm["glossary_hash"], str)
              and re.fullmatch(r"[0-9a-f]{64}", arm["glossary_hash"]) is not None,
              "invalid arm glossary_hash")
    _require(isinstance(arm["draft_hash"], str) and re.fullmatch(r"[0-9a-f]{64}", arm["draft_hash"]) is not None,
              "invalid arm draft_hash")
    _require(_positive(arm["pages"]), "arm pages must be a finite positive number")
    _require(arm["observed_cost_usd"] is None or _nonneg(arm["observed_cost_usd"]),
              "invalid arm observed_cost_usd")
    _require(_nonneg(arm["list_estimated_cost_usd"]), "arm list_estimated_cost_usd must be finite and non-negative")
    _require(arm["latency_seconds"] is None or _positive(arm["latency_seconds"]), "invalid arm latency_seconds")
    _require(arm["correction_minutes"] is None or _nonneg(arm["correction_minutes"]),
              "invalid arm correction_minutes")
    _require(isinstance(arm["expert_reviewed"], bool), "arm expert_reviewed must be boolean")
    review = arm["expert_review"]
    if arm["expert_reviewed"]:
        _require(isinstance(review, dict) and set(review) == EXPERT_REVIEW_FIELDS,
                  "expert_review requires a human attestation")
        _require(_nonempty(review["actor"]) and review["actor_kind"] == "human"
                  and _nonempty(review["reason"]) and review["draft_hash"] == arm["draft_hash"],
                  "expert_review must be human and bound to the draft hash")
    else:
        _require(review is None, "unreviewed arm cannot carry expert_review attestation")
    _require(isinstance(arm["annotations"], list), "arm annotations must be a list")
    _require(arm["expert_reviewed"] or not arm["annotations"],
              "annotations require expert_reviewed to be true")
    for annotation in arm["annotations"]:
        _validate_annotation(annotation, unit, seen_annotation_ids)


def _validate_unit(unit, seen_unit_ids, seen_annotation_ids):
    _require(isinstance(unit, dict) and set(unit) == UNIT_FIELDS, "invalid unit shape")
    unit_id = unit["unit_id"]
    _require(_nonempty(unit_id) and unit_id not in seen_unit_ids, "duplicate or invalid unit_id")
    seen_unit_ids.add(unit_id)
    pdf_hash = unit["pdf_hash"]
    _require(
        _nonempty(unit["document_id"])
        and isinstance(pdf_hash, str) and re.fullmatch(r"[0-9a-f]{64}", pdf_hash) is not None
        and _nonempty(unit["reading_id"]) and _integer(unit["reading_version"], 1),
        "invalid unit source identity",
    )
    start, end = unit["source_char_start"], unit["source_char_end"]
    _require(_integer(start, 0) and _integer(end) and start < end, "invalid unit source span")
    _require(isinstance(unit["source_language"], str) and unit["source_language"] in LANGUAGES,
              "unsupported source language")
    _require(_nonempty(unit["genre"]), "unit genre is required")
    _require(isinstance(unit["ocr_level"], str) and unit["ocr_level"] in OCR_LEVELS,
              "invalid unit ocr_level")
    _require(
        isinstance(unit["source_text"], str) and unit["source_text"] and len(unit["source_text"]) == end - start,
        "unit source_text length must match its declared source span",
    )
    _require(_integer(unit["source_word_count"], 1), "source_word_count must be a positive integer")
    _validate_approval(unit["source_approval"], unit["source_text"], "source_approval")
    _require(isinstance(unit["reference_text"], str) and unit["reference_text"].strip(),
              "reference_text must be nonempty approved Hebrew text")
    _require(any("\u0590" <= char <= "\u05ff" for char in unit["reference_text"]),
              "reference_text must contain Hebrew script")
    _validate_approval(unit["reference_approval"], unit["reference_text"], "reference_approval")
    _require(isinstance(unit["arms"], list) and unit["arms"], "unit requires at least one candidate arm")
    arm_ids = set()
    for arm in unit["arms"]:
        _validate_arm(arm, unit, seen_annotation_ids)
        _require(arm["arm_id"] not in arm_ids, "duplicate arm_id within a unit")
        arm_ids.add(arm["arm_id"])
    _require(len({arm["glossary_hash"] for arm in unit["arms"]}) == 1,
              "arms on one source unit must use the same glossary hash")
    _require(len({arm["pages"] for arm in unit["arms"]}) == 1,
              "arms on one source unit must use the same page denominator")


def validate_manifest(manifest: dict) -> None:
    """Strictly validate a schema-1 pilot manifest; raises `EvaluationError` on any defect."""
    _require(isinstance(manifest, dict) and manifest.get("schema_version") == SCHEMA_VERSION
              and manifest.get("stage") == STAGE, "unsupported manifest schema/stage")
    _require(set(manifest) == MANIFEST_FIELDS, "invalid manifest shape")
    _require(isinstance(manifest["units"], list) and manifest["units"], "manifest requires at least one unit")

    seen_unit_ids, seen_annotation_ids, seen_source_spans = set(), set(), set()
    for unit in manifest["units"]:
        _validate_unit(unit, seen_unit_ids, seen_annotation_ids)
        source_span = (unit["pdf_hash"], unit["reading_id"], unit["reading_version"],
                       unit["source_char_start"], unit["source_char_end"])
        _require(source_span not in seen_source_spans, "duplicate source span under different unit IDs")
        seen_source_spans.add(source_span)

    document_hashes = {}
    for unit in manifest["units"]:
        existing = document_hashes.setdefault(unit["document_id"], unit["pdf_hash"])
        _require(existing == unit["pdf_hash"], "stale source hash: document_id bound to conflicting pdf_hash")

    arm_signatures = {}
    for unit in manifest["units"]:
        for arm in unit["arms"]:
            signature = (arm["provider"], arm["model"], arm["prompt_version"],
                         arm["context_policy"], arm["critic_enabled"], arm["glossary_hash"])
            existing = arm_signatures.setdefault(arm["arm_id"], signature)
            _require(existing == signature, "inconsistent arm definition for the same arm_id")


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100 * (len(ordered) - 1)
    lower, upper = math.floor(rank), math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _arm_pair(unit, fixed_keys, varying_key):
    """True if `unit` has two arms sharing `fixed_keys` but differing on `varying_key`."""
    by_fixed = {}
    for arm in unit["arms"]:
        key = tuple(arm[k] for k in fixed_keys)
        by_fixed.setdefault(key, set()).add(arm[varying_key])
    return any(len(values) > 1 for values in by_fixed.values())


def _critical_count(arm):
    confirmed = set()
    for annotation in arm["annotations"]:
        if annotation["severity"] == "critical" and annotation["reviewer_verdict"] in (None, "true_positive"):
            confirmed.add((annotation["source_char_start"], annotation["source_char_end"],
                           annotation["error_type"]))
    return len(confirmed)


def _paired_comparisons(units, kind, fixed_keys, varying_key):
    rows = []
    for unit in units:
        arms = sorted(unit["arms"], key=lambda arm: arm["arm_id"])
        for left_index, left in enumerate(arms):
            for right in arms[left_index + 1:]:
                if not (left["expert_reviewed"] and right["expert_reviewed"]):
                    continue
                if left[varying_key] == right[varying_key] or any(left[k] != right[k] for k in fixed_keys):
                    continue
                rows.append({
                    "unit_id": unit["unit_id"], "language": unit["source_language"],
                    "genre": unit["genre"], "comparison": kind,
                    "left_arm_id": left["arm_id"], "right_arm_id": right["arm_id"],
                    "left_condition": left[varying_key], "right_condition": right[varying_key],
                    "critical_errors_right_minus_left": _critical_count(right) - _critical_count(left),
                    "correction_minutes_right_minus_left": None if left["correction_minutes"] is None
                    or right["correction_minutes"] is None else right["correction_minutes"] - left["correction_minutes"],
                    "list_estimated_cost_usd_right_minus_left": right["list_estimated_cost_usd"]
                    - left["list_estimated_cost_usd"],
                    "latency_seconds_right_minus_left": None if left["latency_seconds"] is None
                    or right["latency_seconds"] is None else right["latency_seconds"] - left["latency_seconds"],
                })
    return rows


def _empty_arm_metrics():
    return {
        "segment_count": 0, "expert_reviewed_count": 0,
        "critical_errors_per_1000_source_words": None,
        "severity_counts": {s: 0 for s in sorted(SEVERITIES)},
        "correction_minutes_per_page": None, "list_estimated_cost_usd_per_page": None,
        "latency_p50_seconds": None, "latency_p95_seconds": None,
        "reviewer_true_positive_count": 0, "reviewer_false_positive_count": 0,
        "reviewer_verdicts_available": False,
    }


def _accumulate_arm_metrics(pairs):
    """Compute one metrics block from a list of (unit, arm) pairs sharing an arm_id (optionally one language)."""
    metrics = _empty_arm_metrics()
    metrics["segment_count"] = len(pairs)
    total_pages = sum(arm["pages"] for _, arm in pairs)
    total_cost = sum(arm["list_estimated_cost_usd"] for _, arm in pairs)
    metrics["list_estimated_cost_usd_per_page"] = total_cost / total_pages if total_pages else None

    minute_pairs = [(arm["correction_minutes"], arm["pages"]) for _, arm in pairs if arm["correction_minutes"] is not None]
    if minute_pairs:
        minutes_total = sum(m for m, _ in minute_pairs)
        pages_total = sum(p for _, p in minute_pairs)
        metrics["correction_minutes_per_page"] = minutes_total / pages_total if pages_total else None

    latencies = [arm["latency_seconds"] for _, arm in pairs if arm["latency_seconds"] is not None]
    metrics["latency_p50_seconds"] = _percentile(latencies, 50)
    metrics["latency_p95_seconds"] = _percentile(latencies, 95)

    reviewed = [(unit, arm) for unit, arm in pairs if arm["expert_reviewed"]]
    metrics["expert_reviewed_count"] = len(reviewed)

    unique_spans = {}
    verdicts_seen = False
    for unit, arm in reviewed:
        for annotation in arm["annotations"]:
            verdicts_seen = verdicts_seen or annotation["reviewer_verdict"] is not None
            if annotation["reviewer_verdict"] == "true_positive":
                metrics["reviewer_true_positive_count"] += 1
            elif annotation["reviewer_verdict"] == "false_positive":
                metrics["reviewer_false_positive_count"] += 1
            key = (unit["unit_id"], arm["arm_id"], annotation["source_char_start"],
                   annotation["source_char_end"], annotation["error_type"])
            if annotation["reviewer_verdict"] in (None, "true_positive"):
                previous = unique_spans.get(key)
                priority = {"minor": 0, "major": 1, "critical": 2}
                if previous is None or priority[annotation["severity"]] > priority[previous]:
                    unique_spans[key] = annotation["severity"]
    metrics["reviewer_verdicts_available"] = verdicts_seen

    for severity in unique_spans.values():
        metrics["severity_counts"][severity] += 1
    reviewed_words = sum(unit["source_word_count"] for unit, _ in reviewed)
    if reviewed_words:
        critical_count = sum(1 for severity in unique_spans.values() if severity == "critical")
        metrics["critical_errors_per_1000_source_words"] = critical_count / reviewed_words * 1000
    return metrics


def build_report(manifest: dict) -> dict:
    """Validate `manifest` and compute a deterministic schema-1 `pilot-report@1`.

    Never infers semantic truth, calls a provider, or selects a model winner;
    a report built from fewer than 72 expert-approved segments (24 per
    en/fr/ja) or missing paired arms is `preliminary`.
    """
    validate_manifest(manifest)
    input_hash = fingerprint(manifest)
    units = manifest["units"]

    arm_pairs = {}
    for unit in units:
        for arm in unit["arms"]:
            arm_pairs.setdefault(arm["arm_id"], []).append((unit, arm))

    per_arm = {}
    for arm_id, pairs in arm_pairs.items():
        by_language = {}
        for language in sorted({unit["source_language"] for unit, _ in pairs}):
            by_language[language] = _accumulate_arm_metrics([(u, a) for u, a in pairs if u["source_language"] == language])
        by_language_genre = {}
        for language, genre in sorted({(u["source_language"], u["genre"]) for u, _ in pairs}):
            by_language_genre[f"{language}:{genre}"] = _accumulate_arm_metrics([
                (u, a) for u, a in pairs if u["source_language"] == language and u["genre"] == genre
            ])
        per_arm[arm_id] = {"overall": _accumulate_arm_metrics(pairs),
                           "by_language": by_language, "by_language_genre": by_language_genre}

    units_missing_paired_context = [
        u["unit_id"] for u in units
        if not _arm_pair(u, ("provider", "model", "prompt_version", "critic_enabled"), "context_policy")
    ]
    units_missing_paired_critic = [
        u["unit_id"] for u in units
        if not _arm_pair(u, ("provider", "model", "prompt_version", "context_policy"), "critic_enabled")
    ]
    paired_comparisons = {
        "context": _paired_comparisons(
            units, "context", ("provider", "model", "prompt_version", "critic_enabled"), "context_policy"
        ),
        "critic": _paired_comparisons(
            units, "critic", ("provider", "model", "prompt_version", "context_policy"), "critic_enabled"
        ),
    }

    arms_missing_expert_review = []
    arms_missing_observed_cost = []
    arms_missing_latency = []
    arms_missing_correction_minutes = []
    annotations_unconfirmed = []
    for unit in units:
        for arm in unit["arms"]:
            tag = f"{unit['unit_id']}:{arm['arm_id']}"
            if not arm["expert_reviewed"]:
                arms_missing_expert_review.append(tag)
            if arm["observed_cost_usd"] is None:
                arms_missing_observed_cost.append(tag)
            if arm["latency_seconds"] is None:
                arms_missing_latency.append(tag)
            if arm["correction_minutes"] is None:
                arms_missing_correction_minutes.append(tag)
            for annotation in arm["annotations"]:
                if annotation["reviewer_verdict"] == "unconfirmed":
                    annotations_unconfirmed.append(annotation["annotation_id"])

    expert_segments_total = sum(1 for u in units if all(a["expert_reviewed"] for a in u["arms"]))
    expert_segments_by_language = {
        language: sum(1 for u in units if u["source_language"] == language
                      and all(a["expert_reviewed"] for a in u["arms"]))
        for language in sorted(LANGUAGES)
    }

    def _count_by(field):
        counts = {}
        for unit in units:
            counts[unit[field]] = counts.get(unit[field], 0) + 1
        return counts

    sample_counts = {
        "total_units": len(units),
        "total_arm_instances": sum(len(u["arms"]) for u in units),
        "by_language": _count_by("source_language"),
        "by_genre": _count_by("genre"),
        "by_ocr_level": _count_by("ocr_level"),
        "by_arm": {arm_id: len(pairs) for arm_id, pairs in arm_pairs.items()},
        "expert_approved_segments_total": expert_segments_total,
        "expert_approved_segments_by_language": expert_segments_by_language,
    }

    status_reasons = []
    if expert_segments_total < MIN_TOTAL_SEGMENTS:
        status_reasons.append(
            f"expert_approved_segments_total {expert_segments_total} < required {MIN_TOTAL_SEGMENTS}"
        )
    for language in sorted(LANGUAGES):
        count = expert_segments_by_language[language]
        if count < MIN_PER_LANGUAGE_SEGMENTS:
            status_reasons.append(
                f"expert_approved_segments for {language} {count} < required {MIN_PER_LANGUAGE_SEGMENTS}"
            )
    if units_missing_paired_context:
        status_reasons.append(f"{len(units_missing_paired_context)} unit(s) missing a paired context-policy arm")
    if units_missing_paired_critic:
        status_reasons.append(f"{len(units_missing_paired_critic)} unit(s) missing a paired critic-enabled arm")
    if arms_missing_expert_review:
        status_reasons.append(f"{len(arms_missing_expert_review)} arm instance(s) missing expert review")
    if annotations_unconfirmed:
        status_reasons.append(f"{len(annotations_unconfirmed)} annotation(s) lack confirmation")
    if arms_missing_latency:
        status_reasons.append(f"{len(arms_missing_latency)} arm instance(s) missing latency")
    if arms_missing_correction_minutes:
        status_reasons.append(f"{len(arms_missing_correction_minutes)} arm instance(s) missing correction minutes")

    status = "preliminary" if status_reasons else "sample_threshold_met"

    uncertainty = [
        "Synthetic or fixture manifests demonstrate arithmetic/software construction only, "
        "never real translation quality or reviewer accuracy.",
        "PDF hashes, draft hashes and human attestations are checked for manifest consistency only; "
        "the external files and reviewer identities require independent verification.",
        "Reviewer true/false-positive counts are only as reliable as the supplied annotations; "
        "a segment never reviewed by an expert contributes no error evidence.",
    ]
    if arms_missing_expert_review:
        uncertainty.append(f"{len(arms_missing_expert_review)} arm instance(s) have no expert review.")
    if arms_missing_observed_cost:
        uncertainty.append(f"{len(arms_missing_observed_cost)} arm instance(s) have no observed cost; "
                            "only list-estimated cost is available for those.")
    if arms_missing_latency:
        uncertainty.append(f"{len(arms_missing_latency)} arm instance(s) have no recorded latency.")
    if arms_missing_correction_minutes:
        uncertainty.append(f"{len(arms_missing_correction_minutes)} arm instance(s) have no recorded correction minutes.")

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": REPORT_STAGE,
        "input_hash": input_hash,
        "status": status,
        "status_reasons": status_reasons,
        "sample_counts": sample_counts,
        "per_arm_metrics": per_arm,
        "paired_comparisons": paired_comparisons,
        "missing_data": {
            "units_missing_paired_context": units_missing_paired_context,
            "units_missing_paired_critic": units_missing_paired_critic,
            "arms_missing_expert_review": arms_missing_expert_review,
            "arms_missing_observed_cost": arms_missing_observed_cost,
            "arms_missing_latency": arms_missing_latency,
            "arms_missing_correction_minutes": arms_missing_correction_minutes,
            "annotations_unconfirmed": annotations_unconfirmed,
        },
        "uncertainty": uncertainty,
        "model_winner": None,
        "recommendation": None,
        "note": "No model winner or routing recommendation is produced by this offline harness "
                "regardless of status; that requires a separately approved genuine gold-set "
                "evaluation under Gate 10 full acceptance.",
    }
