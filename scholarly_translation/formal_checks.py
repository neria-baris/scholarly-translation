"""Gate 7: pure, deterministic formal checks over a source unit and its draft.

This is a structural checker, not a quality or semantic verdict. It reports
typed findings so a formally clean draft can still require human review, and
it never rewrites text, asserts a transliteration is wrong, or sets approval.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_PROPER_NAME_RE = re.compile(r"\b[A-Z][a-zA-ZÀ-ɏ]+\b")
_SENTENCE_WORDS = {"The", "A", "An", "This", "That", "These", "Those", "Later", "Le", "La", "Les", "Un", "Une", "Ce", "Cette"}
_FOOTNOTE_RE = re.compile(r"[¹²³⁰-⁹†‡*]")
_CITATION_RE = re.compile(
    r"\[\d+(?:\s*,\s*\d+)*\]"
    r"|\([A-Z][a-zA-Z]+(?:\s+(?:et al\.?|and|&)\s+[A-Z][a-zA-Z]+)?,?\s*\d{4}[a-z]?\)"
)
_FORMULA_RE = re.compile(
    r"\d+\s*[-+*/=^]\s*\d+"
    r"|[A-Za-z]\s*=\s*[A-Za-z0-9]+"
    r"|[A-Za-z]\^\d+"
    r"|[∑∫√±≤≥≠π∞]"
)
_HEBREW_RE = re.compile(r"[֐-׿]")


class FormalCheckError(ValueError):
    """Invalid input to the formal checker."""


def _normalize(text):
    return unicodedata.normalize("NFC", text)


def _spans(pattern, text):
    return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]


def _missing_findings(pattern, finding_type, source_text, target_text):
    findings = []
    available = Counter(_normalize(token) for _, _, token in _spans(pattern, target_text or ""))
    for start, end, token in _spans(pattern, source_text):
        normalized = _normalize(token)
        if available[normalized]:
            available[normalized] -= 1
        else:
            findings.append({
                "type": finding_type,
                "source_token": token,
                "source_char_start": start,
                "source_char_end": end,
                "target_evidence": None,
                "severity": "needs_human",
            })
    return findings


def run_formal_checks(source_text, target_text, source_language):
    """Typed findings over protected source elements.

    Unicode-normalized exact token multiplicity is the only equivalence checked;
    there is no silent rewrite, transliteration assertion or semantic truth
    claim. Proper-name candidates are always surfaced for human review rather
    than judged, since a missing Latin spelling in a Hebrew draft does not by
    itself mean the name was translated incorrectly.
    """
    if not isinstance(source_text, str):
        raise FormalCheckError("source_text must be a string")
    if target_text is not None and not isinstance(target_text, str):
        raise FormalCheckError("target_text must be a string or None")

    findings = []
    findings.extend(_missing_findings(_NUMBER_RE, "missing_number", source_text, target_text))
    findings.extend(_missing_findings(_FOOTNOTE_RE, "missing_footnote_marker", source_text, target_text))
    findings.extend(_missing_findings(_CITATION_RE, "missing_citation_reference", source_text, target_text))
    findings.extend(_missing_findings(_FORMULA_RE, "missing_formula_token", source_text, target_text))

    if source_language in ("en", "fr"):
        for start, end, token in _spans(_PROPER_NAME_RE, source_text):
            if token in _SENTENCE_WORDS:
                continue
            findings.append({
                "type": "proper_name_candidate",
                "source_token": token,
                "source_char_start": start,
                "source_char_end": end,
                "target_evidence": "uncertain_transliteration_not_asserted",
                "severity": "needs_human",
            })

    if target_text is not None and target_text.strip() and not _HEBREW_RE.search(target_text):
        findings.append({
            "type": "missing_hebrew_script",
            "source_token": None,
            "source_char_start": None,
            "source_char_end": None,
            "target_evidence": None,
            "severity": "needs_human",
        })

    return findings
