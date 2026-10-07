"""Deterministic output checks (audit/contracts/target_languages.md).

Cheap, offline comparisons of one translated unit with its source: they never
judge meaning and never rewrite text. Each finding uses the formal-finding
shape (``type``, ``source_token``, ``source_char_start``, ``source_char_end``,
``target_evidence``, ``severity``) so the pipeline treats it like a formal
finding: a review trigger and a visible note. ``added_dash`` is a note only
(see ``NOTE_ONLY_TYPES``).
"""
from __future__ import annotations

import re
import unicodedata

from . import target_languages

MIN_RATIO_CHARS = 80          # shorter units vary too much for a length ratio
RATIO_LOW, RATIO_HIGH = 0.4, 2.5   # x the pack's expected ratio
MIN_SENTENCES = 4
COPY_WORDS = 8                # consecutive source words copied into the target
COPY_CJK_CHARS = 12
NAME_KINDS = {"character", "person", "place", "organization"}
NOTE_ONLY_TYPES = {"added_dash"}

_SENTENCE_END_RE = re.compile(r"[.!?׃。！？]+(?=[\"'”’)\]]*(?:\s|$))")
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_NIQQUD_RE = re.compile("[֑-ׇ]")
_DASHES = "—–"
_MATH_RE = re.compile("⟦[^⟦⟧]*⟧")


def _finding(kind, token=None, start=None, end=None, evidence=None):
    return {"type": kind, "source_token": token, "source_char_start": start, "source_char_end": end,
            "target_evidence": evidence, "severity": "needs_human"}


def _plain(text):
    return unicodedata.normalize("NFC", _NIQQUD_RE.sub("", unicodedata.normalize("NFD", text or "")))


def _sentences(text):
    return len(_SENTENCE_END_RE.findall(_MATH_RE.sub(" ", text)))


def _length_ratio(source, target, language, pack):
    expected = pack.ratio(language)
    size = len(source.strip())
    if not expected or size < MIN_RATIO_CHARS:
        return []
    actual = len(target.strip()) / size
    if expected * RATIO_LOW <= actual <= expected * RATIO_HIGH:
        return []
    return [_finding("length_ratio", evidence=f"{actual:.2f} (expected about {expected:g})")]


def _sentence_count(source, target):
    src, tgt = _sentences(source), _sentences(target)
    if src < MIN_SENTENCES or src * 0.5 <= tgt <= src * 2:
        return []
    return [_finding("sentence_count", evidence=f"{tgt} sentences for {src}")]


def _copied_run(source, target):
    clean_source, clean_target = _MATH_RE.sub(" ", source), _MATH_RE.sub(" ", target)
    if _CJK_RE.search(clean_source):
        size = COPY_CJK_CHARS
        src = [(m.group(0), m.start()) for m in _CJK_RE.finditer(clean_source)]
        tgt = "".join(_CJK_RE.findall(clean_target))
        grams = {tgt[i:i + size] for i in range(len(tgt) - size + 1)}
        for i in range(len(src) - size + 1):
            window = "".join(ch for ch, _ in src[i:i + size])
            if window in grams:
                start = src[i][1]
                return [_finding("copied_source_run", window, start, src[i + size - 1][1] + 1)]
        return []
    size = COPY_WORDS
    src = [(m.group(0).casefold(), m.start(), m.end()) for m in _WORD_RE.finditer(clean_source)]
    tgt = [w.casefold() for w in _WORD_RE.findall(clean_target)]
    grams = {tuple(tgt[i:i + size]) for i in range(len(tgt) - size + 1)}
    for i in range(len(src) - size + 1):
        window = tuple(w for w, _, _ in src[i:i + size])
        if window in grams:
            start, end = src[i][1], src[i + size - 1][2]
            return [_finding("copied_source_run", source[start:end], start, end)]
    return []


def _added_dash(source, target):
    added = sum(target.count(d) for d in _DASHES) - sum(source.count(d) for d in _DASHES)
    return [_finding("added_dash", evidence=f"{added} more")] if added > 0 else []


def _occurs(form, text):
    return bool(form) and re.search(r"(?<!\w)" + re.escape(form) + r"(?!\w)", text) is not None


def _target_forms(form, pack):
    plain = _plain(form)
    forms = {plain}
    if pack.hebrew_prefixes and plain.startswith("ו") and not plain.startswith("וו"):
        forms.add("ו" + plain)          # a leading vav is written twice after a prefix
    return forms


def _contains(target, form, pack):
    """``form`` appears in ``target``; for Hebrew a prefix letter may stand before it."""
    plain_target = _plain(target)
    for variant in _target_forms(form, pack):
        if pack.hebrew_prefixes:
            if variant in plain_target:
                return True
        elif re.search(r"(?<!\w)" + re.escape(variant), plain_target, re.IGNORECASE):
            return True
    return False


def _names(source, target, entries, pack):
    findings = []
    for entry in entries or ():
        if entry.get("kind") not in NAME_KINDS or not entry.get("hebrew"):
            continue
        name = entry.get("source") or ""
        match = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", source) if name else None
        if match and not _contains(target, entry["hebrew"], pack):
            findings.append(_finding("name_form_missing", name, match.start(), match.end(),
                                     _plain(entry["hebrew"])))
    return findings


def _terms(source, target, terms, pack):
    findings = []
    for term in terms or ():
        src, tgt = term.get("source_term"), term.get("target_term")
        if not src or not tgt:
            continue
        start = source.find(src)
        if start >= 0 and not _contains(target, tgt, pack):
            findings.append(_finding("term_missing", src, start, start + len(src), tgt))
    return findings


def run_output_checks(source_text, target_text, source_language, *, names=None, terms=None, pack=None):
    """Deterministic findings for one translated unit (``[]`` for an empty target)."""
    if not isinstance(source_text, str) or not isinstance(target_text, str) or not target_text.strip():
        return []
    pack = pack or target_languages.current()
    findings = []
    findings += _length_ratio(source_text, target_text, source_language, pack)
    findings += _sentence_count(source_text, target_text)
    findings += _copied_run(source_text, target_text)
    findings += _added_dash(source_text, target_text)
    findings += _names(source_text, target_text, names, pack)
    findings += _terms(source_text, target_text, terms, pack)
    return findings
