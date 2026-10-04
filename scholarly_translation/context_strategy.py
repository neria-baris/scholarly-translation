"""Session D: semantic-unit, chapter-aware translation context selection.

Built entirely on the existing document-structure node/unit hierarchy
(STRUCTURE_SCHEMA.md): this module never re-derives a second chapter model,
never invents a tokenizer, and never generates a summary. Context shown to
the model beyond the exact translation target is always bounded, literal
original source text, carrying its own node/unit identity for provenance.

Two context-selection branches exist for a single translation unit:

* ``whole_chapter``: the unit's enclosing ``chapter``/``part`` node's full
  source span fits the selected model's usable context budget (headroom
  reserved for instructions/glossary/local state/output/review metadata).
  The full chapter is shown as context with the exact target span marked;
  the model is instructed to translate only the target.
* ``bounded_fallback``: the chapter does not fit (or none exists - flat/
  short documents degrade gracefully), so the target unit is shown with as
  much adjacent original source as the budget allows, expanding outward
  unit by unit. With no model capabilities supplied at all, this reduces
  exactly to the historical one-previous/one-next-unit behavior so existing
  callers are unaffected.

A third, explicitly separate mode - translating an entire chapter *as the
target* in one request, for comparing against per-unit translation - is
``build_whole_chapter_translation_request`` in ``translation.py``; nothing
in this module makes that the default.
"""
from __future__ import annotations

from .document_structure import _word_count
from .source_reading import text_hash

CONTEXT_POLICY_VERSION = "context-policy-chapter-aware@1"

# This project ships no second tokenizer (STRUCTURE_SCHEMA.md / the Session D
# contract's known_risks explicitly forbid inventing one). Each
# whitespace/CJK "word" counted by the existing deterministic size heuristic
# (document_structure._word_count) is conservatively assumed to cost this
# many model tokens, so a budget-fit check only ever *underestimates* how
# much chapter text can fit, never overestimates it.
WORDS_TO_TOKENS_RATIO = 2.0

# Fraction of usable_context_tokens permanently reserved for instructions,
# glossary/approved decisions, local state, output and review metadata
# before any chapter source text is even considered. Deliberately
# configurable per call (Session D spec section 6); this is only the
# default.
DEFAULT_HEADROOM_FRACTION = 0.35

CHAPTER_KINDS = ("part", "chapter")


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for budget-fit checks; see module docstring."""
    return int(_word_count(text) * WORDS_TO_TOKENS_RATIO)


def available_chapter_token_budget(capabilities, headroom_fraction=DEFAULT_HEADROOM_FRACTION) -> int:
    """Usable input budget left for chapter/context source text.

    Reserves ``headroom_fraction`` of the usable context for instructions,
    glossary, local state and review metadata, and separately reserves the
    model's max output tokens (never assumes usable_context_tokens already
    excludes output).
    """
    if capabilities is None:
        return 0
    reserved_output = capabilities.max_output_tokens or 0
    reserved_headroom = int(capabilities.usable_context_tokens * headroom_fraction)
    return max(capabilities.usable_context_tokens - reserved_headroom - reserved_output, 0)


def find_enclosing_chapter_node(structure, unit):
    """Nearest ``chapter``/``part`` ancestor node of ``unit``.

    Returns ``None`` for flat/short documents with no chapter-level nodes;
    callers must degrade to the bounded fallback rather than fabricate a
    chapter (known_risks in the Session D contract).
    """
    link = next((l for l in structure["unit_node_links"] if l["unit_id"] == unit["unit_id"]), None)
    if not link or not link["node_ids"]:
        return None
    by_id = {n["node_id"]: n for n in structure["nodes"]}
    node = by_id.get(link["node_ids"][0])
    seen = set()
    while node is not None:
        if node["kind"] in CHAPTER_KINDS:
            return node
        parent_id = node["parent_node_id"]
        if parent_id is None or parent_id in seen:
            return None
        seen.add(parent_id)
        node = by_id.get(parent_id)
    return None


def chapter_node_span(structure, chapter_node):
    """Ordered nodes making up ``chapter_node``'s own extent.

    From the chapter node itself up to (but not including) the next node at
    the same or shallower level, using the document-wide contiguous ``order``
    field - this is exactly how node ``order``/``parent_node_id`` already
    cross page boundaries (STRUCTURE_SCHEMA.md), so a chapter spanning
    multiple PDF pages is handled with no extra logic.
    """
    nodes = sorted(structure["nodes"], key=lambda n: n["order"])
    level = chapter_node["level"]
    start_index = next(i for i, n in enumerate(nodes) if n["node_id"] == chapter_node["node_id"])
    span = [chapter_node]
    for n in nodes[start_index + 1:]:
        if n["level"] is not None and n["level"] <= level:
            break
        span.append(n)
    return span


def chapter_unit_ids(structure, chapter_nodes):
    """Real translation unit ids intersecting ``chapter_nodes``, in document order."""
    node_ids = {n["node_id"] for n in chapter_nodes}
    order_by_node = {n["node_id"]: n["order"] for n in structure["nodes"]}
    links = [l for l in structure["unit_node_links"] if set(l["node_ids"]) & node_ids]
    links.sort(key=lambda l: min(order_by_node[nid] for nid in l["node_ids"] if nid in order_by_node))
    return [l["unit_id"] for l in links]


def _unit_segment(unit, role):
    return {
        "role": role, "unit_id": unit["unit_id"], "unit_version": unit["unit_version"],
        "node_ids": [], "text": unit["text"], "text_hash": text_hash(unit["text"]),
    }


def _node_segment(nodes, role):
    text = "\n\n".join(n["text"] for n in nodes)
    return {
        "role": role, "unit_id": None, "unit_version": None,
        "node_ids": [n["node_id"] for n in nodes], "text": text, "text_hash": text_hash(text),
    }


_TARGET_MARKER_TEXT = (
    "[TARGET_UNIT_SPAN - the exact text being translated appears in the "
    "<TARGET_UNIT> section below; nothing here should be translated]"
)


def _whole_chapter_segments(structure, unit, span_nodes):
    link = next(l for l in structure["unit_node_links"] if l["unit_id"] == unit["unit_id"])
    target_node_ids = set(link["node_ids"])
    before, after, seen_target = [], [], False
    for node in span_nodes:
        if node["node_id"] in target_node_ids:
            seen_target = True
            continue
        (after if seen_target else before).append(node)
    segments = []
    if before:
        segments.append(_node_segment(before, "chapter_before"))
    segments.append({
        "role": "target_marker", "unit_id": None, "unit_version": None,
        "node_ids": sorted(target_node_ids), "text": _TARGET_MARKER_TEXT,
        "text_hash": text_hash(_TARGET_MARKER_TEXT),
    })
    segments.append(_unit_segment(unit, "target"))
    if after:
        segments.append(_node_segment(after, "chapter_after"))
    return segments


def _bounded_fallback_segments(structure, unit, limit_tokens=None, chapter_unit_ids_pool=None):
    """Target unit plus as much adjacent original source as fits.

    With ``limit_tokens is None`` (no model capability metadata available)
    this reduces exactly to the historical one-previous/one-next-unit
    behavior within the same reading. With a token budget, it expands
    outward unit by unit - within the enclosing chapter's own units when
    known, else the same reading - never generating a summary.
    """
    if chapter_unit_ids_pool:
        units_by_id = {u["unit_id"]: u for u in structure["units"]}
        candidates = [units_by_id[uid] for uid in chapter_unit_ids_pool if uid in units_by_id]
    else:
        candidates = sorted(
            (u for u in structure["units"] if u["reading_id"] == unit["reading_id"]),
            key=lambda u: u["source_char_start"],
        )
    index = next(i for i, u in enumerate(candidates) if u["unit_id"] == unit["unit_id"])

    if limit_tokens is None:
        segments = []
        if index > 0:
            segments.append(_unit_segment(candidates[index - 1], "previous"))
        segments.append(_unit_segment(unit, "target"))
        if index + 1 < len(candidates):
            segments.append(_unit_segment(candidates[index + 1], "next"))
        return segments

    included = {index}
    used = estimate_tokens(unit["text"])
    left, right = index - 1, index + 1
    while left >= 0 or right < len(candidates):
        if left >= 0:
            cost = estimate_tokens(candidates[left]["text"])
            if used + cost <= limit_tokens:
                included.add(left)
                used += cost
                left -= 1
            else:
                left = -1
        if right < len(candidates):
            cost = estimate_tokens(candidates[right]["text"])
            if used + cost <= limit_tokens:
                included.add(right)
                used += cost
                right += 1
            else:
                right = len(candidates)

    ordered = sorted(included)
    segments = []
    for i in ordered:
        if i == index:
            segments.append(_unit_segment(unit, "target"))
        elif i < index:
            segments.append(_unit_segment(candidates[i], "previous"))
        else:
            segments.append(_unit_segment(candidates[i], "next"))
    return segments


def _segment_page_ids(structure, segments):
    units_by_id = {u["unit_id"]: u for u in structure["units"]}
    nodes_by_id = {n["node_id"]: n for n in structure["nodes"]}
    page_ids = set()
    for s in segments:
        if s.get("unit_id") and s["unit_id"] in units_by_id:
            page_ids.add(units_by_id[s["unit_id"]]["page_id"])
        for nid in s.get("node_ids", []):
            if nid in nodes_by_id:
                page_ids.add(nodes_by_id[nid]["page_id"])
    return page_ids


def plan_context(structure, unit, capabilities=None, headroom_fraction=None):
    """Resolve the Session D context decision and segments for ``unit``.

    Returns ``(decision, segments)``. ``decision`` always carries
    ``context_mode`` (``"whole_chapter"`` or ``"bounded_fallback"``),
    ``chapter_node_id`` (nullable), ``estimated_chapter_tokens`` (nullable),
    ``available_token_budget`` (nullable), ``crosses_page_boundary`` and
    ``chapter_unit_ids``. ``capabilities is None`` always yields the exact
    historical bounded-neighbor behavior.
    """
    effective_headroom = DEFAULT_HEADROOM_FRACTION if headroom_fraction is None else headroom_fraction

    if capabilities is None:
        segments = _bounded_fallback_segments(structure, unit, limit_tokens=None)
        decision = {
            "context_mode": "bounded_fallback", "chapter_node_id": None,
            "estimated_chapter_tokens": None, "available_token_budget": None,
            "crosses_page_boundary": len(_segment_page_ids(structure, segments) | {unit["page_id"]}) > 1,
            "chapter_unit_ids": [],
        }
        return decision, segments

    chapter_node = find_enclosing_chapter_node(structure, unit)
    if chapter_node is None:
        budget = available_chapter_token_budget(capabilities, effective_headroom)
        segments = _bounded_fallback_segments(structure, unit, limit_tokens=budget)
        decision = {
            "context_mode": "bounded_fallback", "chapter_node_id": None,
            "estimated_chapter_tokens": None, "available_token_budget": budget,
            "crosses_page_boundary": len(_segment_page_ids(structure, segments) | {unit["page_id"]}) > 1,
            "chapter_unit_ids": [],
        }
        return decision, segments

    span_nodes = chapter_node_span(structure, chapter_node)
    budget = available_chapter_token_budget(capabilities, effective_headroom)
    estimated = sum(estimate_tokens(n["text"]) for n in span_nodes)
    units_in_chapter = chapter_unit_ids(structure, span_nodes)

    if estimated <= budget:
        segments = _whole_chapter_segments(structure, unit, span_nodes)
        mode = "whole_chapter"
    else:
        segments = _bounded_fallback_segments(structure, unit, limit_tokens=budget, chapter_unit_ids_pool=units_in_chapter)
        mode = "bounded_fallback"

    decision = {
        "context_mode": mode, "chapter_node_id": chapter_node["node_id"],
        "estimated_chapter_tokens": estimated, "available_token_budget": budget,
        "crosses_page_boundary": len(_segment_page_ids(structure, segments) | {unit["page_id"]}) > 1,
        "chapter_unit_ids": units_in_chapter,
    }
    return decision, segments
