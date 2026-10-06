"""Cross-chapter QA: windows of consecutive chapters, prompt, response parsing, unit location.

Offline helpers only; the caller (chapter_pipeline) owns provider calls."""

import re
from pathlib import Path

from .review_qa import (
    SEVERITIES, VERDICTS, _CHAPTER_ISSUE_RE, _issue_slices, _unwrap, ground_span,
)

WINDOW_CHAPTERS = 8
CROSS_ISSUE_CATEGORIES = {"consistency", "continuity"}
MAX_OUTPUT_TOKENS = 8192
SHORT_SPAN_CHARS = 40

_PROMPT_PATH = Path(__file__).resolve().parent / "runtime_prompts" / "10_cross_chapter_qa.md"
_PROFILE_CHECKS = {
    "literary": (
        "- forms of address between the same characters;\n"
        "- titles and recurring terms;\n"
        "- recurring phrases and motifs;\n"
        "- gender agreement of each character (verbs, adjectives, pronouns) across chapters;\n"
        "- continuity contradictions introduced by the translation (not present in the source);\n"
        "- voice drift of a character or of the narrator."),
    "scholarly": (
        "- one Hebrew rendering per technical term and concept in all chapters; a term keeps the sense the "
        "author defined, and the author's distinctions between neighbouring terms stay distinct in Hebrew;\n"
        "- normal Hebrew inflection of a term (number, construct state, prefixes) is not an inconsistency: "
        "report only a different word;\n"
        "- definitions and theses restated in a later chapter agree with the earlier rendering;\n"
        "- references to earlier chapters, sections, figures, tables, equations and notes match what they "
        "point to, and their numbering and wording are consistent;\n"
        "- cited authors and works: one Hebrew form per author and per title, and one established Hebrew "
        "translation per quoted canonical text;\n"
        "- abbreviations, symbols and notation, and whether the original-language term is kept in parentheses;\n"
        "- gender agreement of each cited author and of the addressed reader across chapters;\n"
        "- attribution: a claim the source attributes to the author, a cited author or an opponent keeps that "
        "attribution and the author's stance (endorse, reject, report) in Hebrew;\n"
        "- contradictions in the argument introduced by the translation (not present in the source);\n"
        "- drift of the authorial voice (first person singular or plural, impersonal) or register."),
}

_OUTPUT_CONTRACT = """

STRUCTURED_OUTPUT_CONTRACT:
In ISSUES, write `none` or number every issue using exactly these fields:
1. Category: consistency | continuity
   Severity: CRITICAL | MAJOR | MINOR
   Span: one line copied verbatim from a HEBREW or SOURCE chapter text, without added quotes or backticks
   Correction: a nonempty local correction that changes the text, never a wholesale retranslation
Each field on one line. List only issues you stand behind: no comments or retractions inside ISSUES.
Write the sections in this order: VERDICT:, ISSUES:, NOTES:.
"""


def windows(n):
    """0-based inclusive (start, end) windows of WINDOW_CHAPTERS chapters, one chapter of overlap."""
    if not isinstance(n, int) or n < 2:
        return []
    result, start = [], 0
    step = WINDOW_CHAPTERS - 1
    while True:
        end = min(start + step, n - 1)
        result.append((start, end))
        if end >= n - 1:
            return result
        start = end


def window_key(window):
    return f"{window[0]}-{window[1]}"


def build_cross_qa_prompt(chapters, names_text, notebook_text, profile, reference_index=None):
    """``reference_index``: the overlap chapter (0-based) already checked with the chapters
    before it; it is authoritative and the later chapters of the window follow it."""
    parts = []
    for chapter in chapters:
        number = int(chapter["index"]) + 1
        mark = " (REFERENCE)" if reference_index is not None and int(chapter["index"]) == reference_index else ""
        parts.append(f"=== CHAPTER {number}{mark} — SOURCE ===\n{chapter['source']}\n"
                     f"=== CHAPTER {number}{mark} — HEBREW ===\n{chapter['hebrew']}")
    if reference_index is None:
        reference = "(none: no chapter of this window has been checked across chapters yet)"
    else:
        number = int(reference_index) + 1
        reference = (f"Chapter {number} was already checked together with the chapters before it and is "
                     f"authoritative. Where a later chapter of this window disagrees with chapter {number} "
                     f"(names, terms, forms of address, recurring phrases, cross-references), the later chapter "
                     f"is wrong: give the span from the later chapter and chapter {number}'s form as the correction. Never report an "
                     f"issue whose span occurs only in chapter {number}.")
    values = {
        "NAMES": (names_text or "").strip() or "(none)",
        "BOOK_NOTEBOOK": (notebook_text or "").strip() or "(none)",
        "PROFILE": (profile or "").strip() or "(none)",
        "PROFILE_CHECKS": _PROFILE_CHECKS["scholarly" if (profile or "").strip() == "scholarly" else "literary"],
        "REFERENCE": reference,
        "CHAPTERS": "\n\n".join(parts),
    }
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"\{\{(" + "|".join(values) + r")\}\}")
    return pattern.sub(lambda match: values[match.group(1)], text) + _OUTPUT_CONTRACT


def _needs_human(error, verdict=None, notes="", dropped=0):
    return {"status": "needs_human", "verdict": verdict, "issues": [], "notes": notes,
            "dropped_issues": dropped, "error": error}


def parse_cross_qa_response(raw, source_text, hebrew_text):
    if not isinstance(raw, str) or not raw.strip():
        return _needs_human("model response was empty")
    verdict_match = re.search(r"VERDICT:\s*(\S+)", raw)
    if verdict_match is None or verdict_match.group(1) not in VERDICTS:
        return _needs_human("model response did not contain a valid VERDICT")
    verdict = verdict_match.group(1)
    sections = re.search(r"ISSUES:\s*(.*?)NOTES:\s*(.*)", raw, re.DOTALL)
    if sections is None:
        return _needs_human("model response is missing ISSUES or NOTES", verdict)
    issues_block = sections.group(1).strip()
    notes = sections.group(2).strip()

    issues, dropped = [], 0
    if issues_block.rstrip(".").lower() != "none":
        matches = list(_CHAPTER_ISSUE_RE.finditer(issues_block))
        if not matches:
            return _needs_human("ISSUES section contains malformed or unexpected content",
                                verdict, notes)
        for match, stray in _issue_slices(issues_block, matches):
            category = match.group("category").strip()
            severity = match.group("severity").strip()
            span = ground_span(match.group("span"), source_text, hebrew_text)
            correction = match.group("correction").strip()
            if (stray or category not in CROSS_ISSUE_CATEGORIES or severity not in SEVERITIES
                    or span is None or not correction or _unwrap(correction) == span):
                dropped += 1
                continue
            issues.append({"category": category, "severity": severity,
                           "span": span, "correction": correction})

    if verdict == "PASS" and issues:
        return _needs_human("PASS verdict must not carry invented issues", verdict, notes, dropped)
    if verdict == "REVISE" and not issues:
        return _needs_human("every REVISE issue was ungrounded or malformed" if dropped
                            else "REVISE verdict must carry at least one grounded issue",
                            verdict, notes, dropped)
    return {"status": "completed", "verdict": verdict, "issues": issues, "notes": notes,
            "dropped_issues": dropped, "error": None}


def locate_issue_units(issue, records, max_units=80):
    """(records, reason): reason in ok | ambiguous | not_found | too_many."""
    span = issue.get("span") or ""
    if not span:
        return [], "not_found"
    in_hebrew = [r for r in records if span in (r.get("target_text") or "")]
    if len(in_hebrew) == 1:
        return in_hebrew, "ok"
    if len(in_hebrew) > 1:
        if issue.get("category") == "consistency" and len(span) <= SHORT_SPAN_CHARS:
            if len(in_hebrew) > max_units:
                return [], "too_many"
            return in_hebrew, "ok"
        return [], "ambiguous"
    in_source = [r for r in records if span in (r.get("source_text") or "")]
    if len(in_source) == 1:
        return in_source, "ok"
    if len(in_source) > 1:
        return [], "ambiguous"
    return [], "not_found"


def cross_qa_output_cap(selection):
    capabilities = getattr(selection, "capabilities", None)
    declared = getattr(capabilities, "max_output_tokens", None)
    return min(declared or MAX_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS)
