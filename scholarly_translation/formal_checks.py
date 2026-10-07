"""Gate 7: pure, deterministic formal checks over a source unit and its draft.

This is a structural checker, not a quality or semantic verdict. It reports
typed findings so a formally clean draft can still require human review, and
it never rewrites text, asserts a transliteration is wrong, or sets approval.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from . import target_languages

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


_URL_RE = re.compile(r'^(?:[a-z][a-z0-9+.-]*://|www\.)\S+$', re.IGNORECASE)
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[a-z]{2,}$', re.IGNORECASE)
_DOMAIN_RE = re.compile(r'^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?$', re.IGNORECASE)
_TOKEN_EDGE = '()[]{}<>"\'.,;:!?‘’“”'


_MATH_CHARS = set("=+*/^_<>|\\") | set(
    "≤≥≠≈±×÷∑∏∫√∂∇∞∈∉"
    "⊂⊆⊃∪∩→⇒⇔↔∀∃∅∘⋅′″")
_MATH_FUNCTIONS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "lim", "max", "min",
                   "sup", "inf", "det", "deg", "arg", "dim", "mod", "gcd", "lcm", "var", "cov"}


def _is_math_token(token):
    """Variables, operators, Greek letters, super/subscripts and function names."""
    letters = [ch for ch in token if ch.isalpha()]
    return (len(letters) == 1
            or any(ch in _MATH_CHARS for ch in token)
            or any(ch in "([{" for ch in token[1:])       # f(x), a[i]: application/indexing
            or any("Ͱ" <= ch <= "Ͽ" or "⁰" <= ch <= "₟" or "ᵢ" <= ch <= "ᵪ"
                   or "²" <= ch <= "³" or ch == "¹" or "℀" <= ch <= "⅏"
                   or "\U0001d400" <= ch <= "\U0001d7ff" for ch in token)
            or token.lower().rstrip("(") in _MATH_FUNCTIONS)


def has_translatable_words(text):
    """True when ``text`` contains a word a translator should render in Hebrew.
    URLs, e-mail addresses, domain names, tokens containing a digit (ISBNs,
    dates, codes), letterless tokens and mathematical tokens (single-letter
    variables, operators, Greek, super/subscripts, function names) are not."""
    for token in text.split():
        token = token.strip(_TOKEN_EDGE)
        if not any(ch.isalpha() for ch in token):
            continue
        if any(ch.isdigit() for ch in token):
            continue
        if _URL_RE.match(token) or _EMAIL_RE.match(token) or _DOMAIN_RE.match(token):
            continue
        if _is_math_token(token):
            continue
        return True
    return False


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

    pack = target_languages.current()
    if (target_text is not None and target_text.strip() and not pack.has_script(target_text)
            and has_translatable_words(source_text)):
        findings.append({
            "type": "missing_hebrew_script" if pack.code == "he" else "missing_target_script",
            "source_token": None,
            "source_char_start": None,
            "source_char_end": None,
            "target_evidence": None,
            "severity": "needs_human",
        })

    return findings
