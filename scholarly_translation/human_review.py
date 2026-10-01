"""Gate 9: local human review, explicit decision and bilingual export.

Binds a Gate-4 structure, Gate-5 glossary, Gate-7 `translation-draft@1` and an
optional Gate-8 `semantic-review@1` to one reviewable unit, renders a static
offline review page, validates a *separate* explicit human decision JSON, and
exports only a currently valid approved schema-1 `human-review@1` record to
escaped bilingual HTML. No model/network call, no default button, no implicit
approval: an explicit nonempty actor/reason/candidate and `action` are
required, and a decision that merely loads this module grants nothing.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .formal_checks import run_formal_checks
from .glossary import GlossaryError, validate_glossary
from .segmentation import validate_structure
from .semantic_review import (
    BYPASS_TRIGGER_TYPES,
    CRITIC_TRIGGER_TYPES,
    SemanticReviewRequestError,
    build_semantic_review_request,
    detect_risk_triggers,
)
from .source_reading import StructureError, fingerprint, text_hash
from .translation import TranslationRequestError, build_translation_request

SCHEMA_VERSION = 1
STAGE = "human-review@1"

CANDIDATE_ORIGINS = {"draft", "correction", "human_edit"}
ACTIONS = {"approve", "defer"}

# "formal_finding" risk is excluded here: Gate 9 already reruns the Gate-7
# formal checker itself and requires an explicit documented override, so a
# unit flagged only for a formal finding does not also need a Gate-8 pass.
REVIEW_REQUIRED_TRIGGER_TYPES = CRITIC_TRIGGER_TYPES | (BYPASS_TRIGGER_TYPES - {"formal_finding"})
PROTECTED_FORMAL_TYPES = {
    "missing_number", "missing_footnote_marker", "missing_citation_reference",
    "missing_formula_token", "missing_hebrew_script",
}

DECISION_FIELDS = {
    "unit_id", "expected_pdf_hash", "expected_draft_cache_key", "expected_draft_hash",
    "expected_review_cache_key", "expected_review_hash", "candidate_origin", "candidate_text",
    "actor", "reason", "action", "formal_override_reason", "prior_decision_hash",
}

_HEBREW_RE = re.compile(r"[֐-׿]")


class HumanReviewRequestError(ValueError):
    """Invalid, stale or tampered human-review input; never includes source/draft text."""


def _require(condition, message):
    if not condition:
        raise HumanReviewRequestError(message)


@dataclass(frozen=True)
class ReviewUnit:
    """Resolved, source/policy-bound reviewable unit. Not a decision or an approval."""

    structure: dict
    glossary_store: dict
    draft: dict
    review: Optional[dict]
    unit: dict
    reading: dict
    selected_candidate: dict
    source_language: str
    applicable_rules: tuple
    risk_triggers: tuple


def resolve_review_unit(structure, glossary, draft, review=None) -> ReviewUnit:
    """Bind a Gate-7 draft and optional Gate-8 review to their canonical source/policy identity.

    Refuses a draft or review that diverges from the canonical request rebuilt
    from the same structure/glossary (stale or tampered source/policy/draft).
    """
    try:
        validate_structure(structure)
        validate_glossary(glossary)
    except (StructureError, GlossaryError):
        raise HumanReviewRequestError("invalid source or glossary for human review") from None

    _require(isinstance(draft, dict) and draft.get("schema_version") == 1
              and draft.get("stage") == "translation-draft@1",
              "draft must be a schema-1 translation-draft@1 record")
    try:
        canonical = build_translation_request(
            structure, glossary, draft.get("unit_id"), draft.get("profile_id"),
            draft.get("provider"), draft.get("model"),
        )
    except TranslationRequestError:
        raise HumanReviewRequestError(
            "draft is not bound to a valid canonical source/policy request"
        ) from None
    for key, value in canonical.to_metadata_dict().items():
        _require(draft.get(key) == value, "draft does not match canonical source/policy identity")

    try:
        semantic_request = build_semantic_review_request(
            structure, glossary, draft, review.get("review_provider", "mock") if isinstance(review, dict) else "mock",
        )
    except SemanticReviewRequestError:
        raise HumanReviewRequestError("draft is not a completed unapproved source-bound Hebrew draft") from None

    if review is not None:
        _require(isinstance(review, dict) and review.get("schema_version") == 1
                  and review.get("stage") == "semantic-review@1",
                  "review must be a schema-1 semantic-review@1 record")
        expected = {
            "review_cache_key": semantic_request.review_cache_key,
            "review_policy_version": semantic_request.review_policy_version,
            "draft_cache_key": draft["cache_key"],
            "draft_hash": fingerprint(draft),
            "source_uri": draft["source_uri"],
            "pdf_hash": draft["pdf_hash"],
            "source_text_hash": draft["source_text_hash"],
            "unit_id": canonical.unit["unit_id"],
            "unit_version": canonical.unit["unit_version"],
            "page_id": canonical.unit["page_id"],
            "reading_id": canonical.unit["reading_id"],
            "reading_version": canonical.unit["reading_version"],
            "source_char_start": canonical.unit["source_char_start"],
            "source_char_end": canonical.unit["source_char_end"],
            "profile_id": draft["profile_id"],
            "policy_fingerprint": draft["policy_fingerprint"],
            "risk_triggers": [dict(item) for item in semantic_request.risk_triggers],
            "before_findings": draft["findings"],
            "approved": False,
        }
        for key, value in expected.items():
            _require(review.get(key) == value, "review does not match canonical draft/source/policy identity")

    reading = next(
        (r for r in structure["readings"]
         if r["reading_id"] == canonical.unit["reading_id"] and r["version"] == canonical.unit["reading_version"]),
        None,
    )
    _require(reading is not None and reading["selected"] is not None, "unit has no resolved source reading")
    selected_candidate = next(
        c for c in reading["alternatives"] if c["candidate_hash"] == reading["selected"]["candidate_hash"]
    )

    risk_triggers = semantic_request.risk_triggers

    return ReviewUnit(
        structure=structure, glossary_store=glossary, draft=draft, review=review,
        unit=canonical.unit, reading=reading, selected_candidate=selected_candidate,
        source_language=canonical.source_language, applicable_rules=tuple(canonical.applicable_rules),
        risk_triggers=risk_triggers,
    )


def _evidence_link(review_unit: ReviewUnit) -> str:
    candidate = review_unit.selected_candidate
    if candidate["origin"] == "ocr" and candidate.get("image"):
        return candidate["image"]["uri"]
    return f"{review_unit.structure['source_uri']}#page={candidate['page_number']}"


def decision_template(review_unit: ReviewUnit) -> dict:
    """A filled-in-identity, action-blank decision skeleton. Never itself an approval."""
    return {
        "unit_id": review_unit.unit["unit_id"],
        "expected_pdf_hash": review_unit.structure["pdf_hash"],
        "expected_draft_cache_key": review_unit.draft["cache_key"],
        "expected_draft_hash": fingerprint(review_unit.draft),
        "expected_review_cache_key": review_unit.review["review_cache_key"] if review_unit.review else None,
        "expected_review_hash": fingerprint(review_unit.review) if review_unit.review else None,
        "candidate_origin": None,
        "candidate_text": None,
        "actor": None,
        "reason": None,
        "action": None,
        "formal_override_reason": None,
        "prior_decision_hash": None,
    }


def render_review_page(review_unit: ReviewUnit) -> str:
    """Static, escaped local HTML: source/evidence, Hebrew draft, flags, glossary, history."""
    e = html.escape
    unit, draft, review = review_unit.unit, review_unit.draft, review_unit.review
    link = _evidence_link(review_unit)

    flags = list(draft["findings"])
    if review is not None:
        flags.extend(review.get("risk_triggers", []))
        flags.extend({"type": "semantic_claim", **c} for c in review.get("claims", []))
    flag_rows = "".join(
        f"<tr><td>{e(str(f.get('type')))}</td><td>{e(str(f.get('source_token', f.get('trigger_type', ''))))}</td>"
        f"<td>{e(str(f.get('severity', f.get('disposition', ''))))}</td></tr>"
        for f in flags
    )

    glossary_rows = "".join(
        f"<tr><td>{e(r['source_term'])}</td><td>{e(r['target_term'])}</td>"
        f"<td>{e(str(r['version']))}</td><td>{e(str(r['loaded']))}</td></tr>"
        for r in review_unit.applicable_rules
    )

    correction = review.get("correction") if review else None
    correction_html = (
        f"<p>Candidate: <span dir='rtl'>{e(correction['candidate_text'])}</span> "
        f"accepted={e(str(correction['accepted']))} evidence={e(correction['recheck_evidence'])}</p>"
        if correction else "<p>No Gate-8 correction on record.</p>"
    )

    template_json = json.dumps(decision_template(review_unit), ensure_ascii=False, indent=2)
    # JSON in a script element must not contain a literal closing tag supplied by source text.
    candidate_json = json.dumps({
        "draft": draft["draft_text"],
        "correction": correction["candidate_text"] if correction else None,
    }, ensure_ascii=False)
    safe_template_json = template_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    safe_candidate_json = candidate_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    preview = (
        f'<img src="{e(link)}" alt="Selected OCR page image" style="max-width:100%;max-height:35rem">'
        if review_unit.selected_candidate["origin"] == "ocr" else
        f'<iframe src="{e(link)}" title="Source PDF page" style="width:100%;height:35rem"></iframe>'
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Human review: {e(unit['unit_id'])}</title></head>
<body>
<h1>Human review</h1>
<p>document_id={e(unit['document_id'])} page_id={e(unit['page_id'])} unit_id={e(unit['unit_id'])}
 v{e(str(unit['unit_version']))} span=[{e(str(unit['source_char_start']))}:{e(str(unit['source_char_end']))}]</p>
<p>Source evidence: <a href="{e(link)}">{e(link)}</a></p>
{preview}
<section id="unit-{e(unit['unit_id'])}">
<h2>Source ({e(review_unit.source_language)})</h2>
<div dir="ltr" lang="{e(review_unit.source_language)}">{e(unit['text'])}</div>
</section>
<section>
<h2>Hebrew draft</h2>
<div dir="rtl" lang="he">{e(draft['draft_text'] or '')}</div>
</section>
<section>
<h2>Flags</h2>
<table border="1"><tr><th>type</th><th>token</th><th>severity/disposition</th></tr>{flag_rows}</table>
</section>
<section>
<h2>Applicable glossary</h2>
<table border="1"><tr><th>source_term</th><th>target_term</th><th>version</th><th>loaded</th></tr>{glossary_rows}</table>
</section>
<section>
<h2>Correction history (Gate 8)</h2>
{correction_html}
</section>
<section>
<h2>Decision</h2>
<p>This page makes no approval by itself. Fill the form, download its JSON, then
submit that separate file through the human-review-decide CLI.</p>
<form id="decision-form">
<p><label>Actor <input id="actor" required></label></p>
<p><label>Reason <input id="reason" required></label></p>
<p><label>Candidate origin <select id="candidate-origin" required>
<option value="">Choose one</option><option value="draft">Draft</option>
<option value="correction">Gate 8 correction</option><option value="human_edit">My edit</option>
</select></label></p>
<p><label>Hebrew candidate<br><textarea id="candidate-text" dir="rtl" lang="he" rows="8" cols="80" required></textarea></label></p>
<p><label>Action <select id="action" required><option value="">Choose one</option>
<option value="approve">Approve after review</option><option value="defer">Defer</option></select></label></p>
<p><label>Formal override reason, if applicable <input id="formal-override-reason"></label></p>
<button type="submit">Download decision JSON</button>
</form>
<p>For a revision, add the prior record hash to <code>prior_decision_hash</code> and pass
that record with <code>--previous</code>. Template:</p>
<pre>{e(template_json)}</pre>
<script type="application/json" id="decision-template">{safe_template_json}</script>
<script type="application/json" id="candidate-options">{safe_candidate_json}</script>
<script>
const template = JSON.parse(document.getElementById('decision-template').textContent);
const candidates = JSON.parse(document.getElementById('candidate-options').textContent);
document.getElementById('candidate-origin').addEventListener('change', function () {{
  const selected = this.value;
  document.getElementById('candidate-text').value = selected === 'human_edit' ? '' : (candidates[selected] || '');
}});
document.getElementById('decision-form').addEventListener('submit', function (event) {{
  event.preventDefault();
  if (!this.reportValidity()) return;
  const decision = Object.assign({{}}, template);
  decision.actor = document.getElementById('actor').value.trim();
  decision.reason = document.getElementById('reason').value.trim();
  decision.candidate_origin = document.getElementById('candidate-origin').value;
  decision.candidate_text = document.getElementById('candidate-text').value;
  decision.action = document.getElementById('action').value;
  decision.formal_override_reason = document.getElementById('formal-override-reason').value.trim() || null;
  const blob = new Blob([JSON.stringify(decision, null, 2)], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'human_decision.json'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}});
</script>
</section>
</body></html>"""


def _validate_candidate(review_unit: ReviewUnit, decision: dict) -> None:
    origin, text = decision["candidate_origin"], decision["candidate_text"]
    _require(origin in CANDIDATE_ORIGINS, "invalid candidate_origin")
    _require(isinstance(text, str) and text.strip() and _HEBREW_RE.search(text),
              "candidate_text must be nonempty reviewable Hebrew text")
    if origin == "draft":
        _require(text == review_unit.draft["draft_text"], "draft candidate_text does not match the draft")
    elif origin == "correction":
        correction = review_unit.review["correction"] if review_unit.review else None
        _require(correction is not None and text == correction["candidate_text"],
                  "correction candidate_text does not match the on-record Gate-8 correction")


def _validate_prior(review_unit: ReviewUnit, decision: dict, previous: Optional[dict]) -> None:
    if previous is None:
        _require(decision["prior_decision_hash"] is None, "prior_decision_hash set with no previous record supplied")
        return
    _require(isinstance(previous, dict) and previous.get("schema_version") == SCHEMA_VERSION
              and previous.get("stage") == STAGE, "previous must be a schema-1 human-review@1 record")
    _require(previous.get("record_hash") == fingerprint({k: v for k, v in previous.items() if k != "record_hash"}),
              "previous decision record hash does not match its content")
    _require(previous.get("unit_id") == review_unit.unit["unit_id"]
              and previous.get("draft_hash") == fingerprint(review_unit.draft)
              and previous.get("review_hash") == (fingerprint(review_unit.review) if review_unit.review else None),
              "previous decision does not belong to this exact unit/draft identity")
    _require(decision["prior_decision_hash"] == previous["record_hash"],
              "prior_decision_hash does not match the supplied previous record")


def run_human_review(review_unit: ReviewUnit, decision: dict, previous: Optional[dict] = None) -> dict:
    """Validate an explicit human decision and produce a schema-1 `human-review@1` record.

    Never defaults to approval: an unknown field, missing actor/reason, a
    candidate that does not match its declared origin, a stale expected hash,
    missing semantic review on flagged risk, or an unresolved formal finding
    without an explicit documented override all refuse approval.
    """
    if not isinstance(review_unit, ReviewUnit):
        raise HumanReviewRequestError("run_human_review requires a resolved ReviewUnit")
    _require(isinstance(decision, dict) and set(decision) == DECISION_FIELDS,
              "decision has unexpected or missing fields")
    _require(decision["action"] in ACTIONS, "decision action must be 'approve' or 'defer'")
    _require(isinstance(decision["actor"], str) and decision["actor"].strip(), "decision actor is required")
    _require(isinstance(decision["reason"], str) and decision["reason"].strip(), "decision reason is required")
    _require(decision["unit_id"] == review_unit.unit["unit_id"], "decision targets a different unit")
    _require(decision["expected_pdf_hash"] == review_unit.structure["pdf_hash"], "stale pdf_hash in decision")
    _require(decision["expected_draft_cache_key"] == review_unit.draft["cache_key"], "stale draft_cache_key in decision")
    _require(decision["expected_draft_hash"] == fingerprint(review_unit.draft), "stale draft_hash in decision")
    expected_review_key = review_unit.review["review_cache_key"] if review_unit.review else None
    _require(decision["expected_review_cache_key"] == expected_review_key, "stale review_cache_key in decision")
    expected_review_hash = fingerprint(review_unit.review) if review_unit.review else None
    _require(decision["expected_review_hash"] == expected_review_hash, "stale review content in decision")

    _validate_candidate(review_unit, decision)
    _validate_prior(review_unit, decision, previous)

    unit = review_unit.unit
    candidate_text = decision["candidate_text"]
    formal_findings = run_formal_checks(unit["text"], candidate_text, review_unit.source_language)

    status, approved = "deferred", False
    if decision["action"] == "approve":
        needs_review = any(t["type"] in REVIEW_REQUIRED_TRIGGER_TYPES for t in review_unit.risk_triggers)
        _require(
            not (needs_review and review_unit.review is None),
            "a flagged-risk unit requires a Gate-8 semantic review before human approval",
        )
        protected_failures = [f for f in formal_findings if f["type"] in PROTECTED_FORMAL_TYPES]
        _require(not protected_failures, "protected source elements must be corrected before approval")
        if formal_findings:
            override = decision.get("formal_override_reason")
            _require(isinstance(override, str) and override.strip(),
                      "unresolved formal failure cannot be approved without an explicit documented correction")
        status, approved = "approved", True

    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "unit_id": unit["unit_id"],
        "unit_version": unit["unit_version"],
        "document_id": unit["document_id"],
        "page_id": unit["page_id"],
        "reading_id": unit["reading_id"],
        "reading_version": unit["reading_version"],
        "source_char_start": unit["source_char_start"],
        "source_char_end": unit["source_char_end"],
        "pdf_hash": review_unit.structure["pdf_hash"],
        "source_uri": review_unit.structure["source_uri"],
        "profile_id": review_unit.draft["profile_id"],
        "policy_fingerprint": review_unit.draft["policy_fingerprint"],
        "draft_cache_key": review_unit.draft["cache_key"],
        "draft_hash": fingerprint(review_unit.draft),
        "review_cache_key": expected_review_key,
        "review_hash": expected_review_hash,
        "candidate_origin": decision["candidate_origin"],
        "candidate_text": candidate_text,
        "candidate_text_hash": text_hash(candidate_text),
        "actor": decision["actor"],
        "actor_kind": "human",
        "reason": decision["reason"],
        "action": decision["action"],
        "status": status,
        "approved": approved,
        "formal_findings": formal_findings,
        "formal_override_reason": decision.get("formal_override_reason"),
        "prior_decision_hash": decision["prior_decision_hash"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    record["record_hash"] = fingerprint(record)
    return record


def latest_decision(records) -> Optional[dict]:
    """Return the one record in a history not superseded by another, or None.

    Raises if the supplied history has more than one unresolved head, since
    that signals a broken or forked decision chain rather than a valid export.
    """
    records = list(records)
    _require(all(isinstance(r, dict) and r.get("record_hash") == fingerprint({k: v for k, v in r.items() if k != "record_hash"})
                 for r in records), "decision history contains a tampered record")
    hashes = {r["record_hash"] for r in records}
    _require(len(hashes) == len(records), "decision history contains duplicate records")
    superseded = {r["prior_decision_hash"] for r in records if r.get("prior_decision_hash")}
    _require(superseded <= hashes, "decision history references an unknown prior record")
    heads = [r for r in records if r["record_hash"] not in superseded]
    _require(len(heads) <= 1, "ambiguous decision history: multiple unresolved heads")
    return heads[0] if heads else None


def export_bilingual_html(review_unit: ReviewUnit, record: dict) -> str:
    """Escaped bilingual HTML for a *currently valid* approved human-review record only.

    Refuses a deferred, stale, tampered or otherwise unapproved record; this
    is the only path that may render exported text as approved.
    """
    _require(isinstance(record, dict) and record.get("schema_version") == SCHEMA_VERSION
              and record.get("stage") == STAGE, "record must be a schema-1 human-review@1 record")
    _require(record.get("record_hash") == fingerprint({k: v for k, v in record.items() if k != "record_hash"}),
              "record hash does not match record content")
    _require(record.get("status") == "approved" and record.get("approved") is True,
              "only a currently valid approved human-review record may be exported")
    _require(record.get("unit_id") == review_unit.unit["unit_id"], "record targets a different unit")
    _require(record.get("pdf_hash") == review_unit.structure["pdf_hash"], "stale pdf_hash for export")
    _require(record.get("draft_hash") == fingerprint(review_unit.draft), "stale draft for export")
    _require(record.get("draft_cache_key") == review_unit.draft["cache_key"], "stale draft for export")
    expected_review_key = review_unit.review["review_cache_key"] if review_unit.review else None
    _require(record.get("review_cache_key") == expected_review_key, "stale review for export")
    expected_review_hash = fingerprint(review_unit.review) if review_unit.review else None
    _require(record.get("review_hash") == expected_review_hash, "stale review content for export")

    candidate_text = record["candidate_text"]
    _require(record.get("candidate_text_hash") == text_hash(candidate_text), "candidate text does not match its hash")
    recheck = run_formal_checks(review_unit.unit["text"], candidate_text, review_unit.source_language)
    _require(recheck == record.get("formal_findings"), "export recheck does not match the approved record")

    e = html.escape
    unit = review_unit.unit
    link = _evidence_link(review_unit)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Bilingual export: {e(unit['unit_id'])}</title></head>
<body>
<p>unit_id={e(unit['unit_id'])} page_id={e(unit['page_id'])}
 span=[{e(str(unit['source_char_start']))}:{e(str(unit['source_char_end']))}]</p>
<p>Source evidence: <a href="{e(link)}">{e(link)}</a></p>
<p><a href="#source-unit-{e(unit['unit_id'])}">Return to exact source unit</a></p>
<div id="source-unit-{e(unit['unit_id'])}" dir="ltr" lang="{e(review_unit.source_language)}">{e(unit['text'])}</div>
<div dir="rtl" lang="he">{e(candidate_text)}</div>
</body></html>"""
