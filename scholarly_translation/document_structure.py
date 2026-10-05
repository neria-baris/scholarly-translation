"""Logical document structure (schema 2): hierarchical nodes plus bounded
semantic translation units built on resolved source readings.

Nodes reconstruct conservative logical blocks (paragraphs, headings, notes,
captions, formulas, bibliography entries, lists, quotations, scene breaks and
page furniture) from PDF/OCR visual lines without rewriting source
characters. Units group semantically coherent adjacent paragraph nodes toward
a bounded word-count target, preferring structural boundaries over the
heuristic target. Classification is explicit heuristics only; unsupported or
ambiguous content is marked ``unsupported``/``paragraph`` rather than guessed.
Never decides translation, terminology or quality.
"""
from __future__ import annotations

import copy
import re

from .segmentation import _build_units_for_reading, _intersecting_anchors, _UNIT_FIELDS
from .source_reading import (
    StructureError, build_readings, fingerprint, integer, nonempty, require, sha,
    strings, validate_candidate, validate_decision,
)
from .store import deterministic_id

SCHEMA_VERSION = 2
STAGE = "structure@2"

DEFAULT_MAX_UNIT_WORDS = 2000

NODE_KINDS = {
    "part", "chapter", "section", "subsection", "heading", "subheading",
    "paragraph", "scene_break", "quotation", "list", "note", "caption",
    "formula", "bibliography_entry", "page_furniture", "unsupported",
}

_NODE_FIELDS = {
    "node_id", "node_version", "kind", "level", "order", "parent_node_id",
    "reading_id", "reading_version",
    "document_id", "page_id", "language", "source_char_start", "source_char_end",
    "text", "anchors", "predecessor_node_ids",
}

_UNIT_NODE_LINK_FIELDS = {"unit_id", "node_ids"}

_READING_FIELDS = {
    "reading_id", "version", "prior_version", "document_id", "page_id", "page_number",
    "status", "reasons", "text", "text_hash", "selected", "decision", "alternatives",
}

_HEADING_WORD_RE = re.compile(
    r"^(part|partie|chapter|chapitre|section|subsection|sous-section|heading|subheading)\s+\S",
    re.IGNORECASE,
)
_JAPANESE_HEADING_RE = re.compile(r"^第[0-9一二三四五六七八九十百千]+([部章節項])")
_NUMBERED_HEADING_RE = re.compile(r"^\d+(\.\d+)*[\.\)]?\s+\S")
_NOTE_RE = re.compile(r"^(?:\[\d+\]|［\d+］|[※＊])\s*\S")
_CAPTION_RE = re.compile(r"^(figure|fig\.|table|plate|tableau|図|表)\s*\d", re.IGNORECASE)
_BIBLIOGRAPHY_RE = re.compile(r"^[A-Z][\w'-]+,\s*[A-Z]\.(\s*[A-Z]\.)*\s*\(\d{4}\)")
_LIST_RE = re.compile(r"^(?:(?:•|・|●|○|-|\*)\s*|\d+[\.\)]\s+)\S")
_FORMULA_RE = re.compile(r"^[A-Za-z0-9\s\+\-\*/\^_\.\(\)=]+$")
_SCENE_BREAK_RE = re.compile(r"^[\*＊\-–—#~ ]{3,}$")
_PAGE_FURNITURE_RE = re.compile(r"^(?:(?:page|page\s+n°|ページ)\s*)?\d{1,4}$", re.IGNORECASE)
_QUOTE_PAIRS = [('"', '"'), ("“", "”"), ("'", "'")]
_SENTENCE_END_RE = re.compile(r"[\.\!\?。！？…”\"')\]]\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\!\?。！？])(?:\s+|(?=\S))")
_CJK_CHARACTER_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def classify_line(line: str):
    """Return ``(kind, level)`` for one raw visual line using bounded,
    explicit heuristics. Unmatched content is a plain ``paragraph``."""
    stripped = line.strip()
    if not stripped:
        return "unsupported", None
    if _SCENE_BREAK_RE.match(stripped):
        return "scene_break", None
    if _PAGE_FURNITURE_RE.match(stripped):
        return "page_furniture", None
    if _NOTE_RE.match(stripped):
        return "note", None
    if _CAPTION_RE.match(stripped):
        return "caption", None
    if _BIBLIOGRAPHY_RE.match(stripped):
        return "bibliography_entry", None
    if _LIST_RE.match(stripped):
        return "list", None
    if "=" in stripped and len(stripped.split()) <= 8 and _FORMULA_RE.match(stripped):
        return "formula", None
    for open_q, close_q in _QUOTE_PAIRS:
        if len(stripped) > 1 and stripped.startswith(open_q) and stripped.endswith(close_q):
            return "quotation", None
    heading = _HEADING_WORD_RE.match(stripped)
    if heading:
        word = stripped.split(None, 1)[0].lower()
        aliases = {"partie": "part", "chapitre": "chapter", "sous-section": "subsection"}
        kind = aliases.get(word, word)
        return kind, {
            "part": 1, "chapter": 2, "section": 3, "subsection": 4,
            "heading": 5, "subheading": 6,
        }[kind]
    japanese_heading = _JAPANESE_HEADING_RE.match(stripped)
    if japanese_heading:
        kind = {"部": "part", "章": "chapter", "節": "section", "項": "subsection"}[
            japanese_heading.group(1)
        ]
        return kind, {"part": 1, "chapter": 2, "section": 3, "subsection": 4}[kind]
    if (len(stripped) <= 80 and not _SENTENCE_END_RE.search(stripped)
            and re.match(r"^\d+(?:\.\d+){2,}[\.\)]?\s+\S", stripped)):
        return "subheading", 6
    if len(stripped) <= 80 and not _SENTENCE_END_RE.search(stripped) and _NUMBERED_HEADING_RE.match(stripped):
        return "subsection", 4
    if len(stripped) <= 80 and not _SENTENCE_END_RE.search(stripped) and (
        stripped.isupper() or (stripped.istitle() and len(stripped.split()) > 1)
    ):
        return "heading", 5
    return "paragraph", None


def _classified_lines(text: str) -> list:
    lines = []
    start = 0
    for idx, ch in enumerate(text):
        if ch == "\n":
            if idx > start:
                kind, level = classify_line(text[start:idx])
                lines.append((start, idx, kind, level))
            start = idx + 1
    if start < len(text):
        kind, level = classify_line(text[start:])
        lines.append((start, len(text), kind, level))
    return lines


def _merge_paragraph_lines(text: str, raw: list) -> list:
    """Reconstruct wrapped visual lines into one paragraph node when a line
    does not end a sentence and is immediately followed by another paragraph
    line, without altering any source character."""
    groups = []
    i, n = 0, len(raw)
    while i < n:
        start, end, kind, level = raw[i]
        if kind != "paragraph":
            groups.append((start, end, kind, level))
            i += 1
            continue
        group_start, group_end, j = start, end, i
        while True:
            segment = text[raw[j][0]:raw[j][1]].strip()
            nxt = j + 1
            if (nxt < n and raw[nxt][2] == "paragraph" and raw[nxt][0] == raw[j][1] + 1
                    and not _SENTENCE_END_RE.search(segment)):
                j = nxt
                group_end = raw[j][1]
            else:
                break
        groups.append((group_start, group_end, "paragraph", None))
        i = j + 1
    return groups


def _build_nodes_for_digital_text_reading(reading: dict, previous_nodes) -> list:
    """Build nodes directly from the selected "digital-text" (EPUB) candidate's
    anchors -- one node per anchor, using its already-known node_kind/
    node_level -- instead of re-deriving kind/level via classify_line. EPUB
    markup already encodes its own block structure unambiguously; guessing
    structure from flattened plain text here would be exactly the second,
    heuristic interpretation of chapters/headings the project forbids."""
    text = reading["text"]
    previous_nodes = previous_nodes or []
    previous_by_id = {n["node_id"]: n for n in previous_nodes}
    nodes = []
    for anchor in reading["selected_anchors"]:
        start, end = anchor["source_char_start"], anchor["source_char_end"]
        kind, level = anchor["node_kind"], anchor["node_level"]
        require(kind in NODE_KINDS, "unrecognized digital-text node kind")
        node_id = deterministic_id(
            "node", reading["document_id"], reading["page_id"], reading["reading_id"],
            str(reading["version"]), str(start), str(end), kind,
        )
        overlapping = [
            n for n in previous_nodes
            if n["source_char_start"] < end and n["source_char_end"] > start
        ]
        existing = previous_by_id.get(node_id)
        if existing is not None:
            node_version = existing["node_version"]
            predecessor_node_ids = existing.get("predecessor_node_ids", [])
        else:
            node_version = max((n["node_version"] for n in overlapping), default=0) + 1
            predecessor_node_ids = [n["node_id"] for n in overlapping if n["node_id"] != node_id]
        nodes.append({
            "node_id": node_id, "node_version": node_version, "kind": kind, "level": level,
            "order": 0, "parent_node_id": None,
            "reading_id": reading["reading_id"], "reading_version": reading["version"],
            "document_id": reading["document_id"], "page_id": reading["page_id"],
            "language": reading["language"], "source_char_start": start, "source_char_end": end,
            "text": text[start:end], "anchors": _intersecting_anchors(reading["selected_anchors"], start, end),
            "predecessor_node_ids": predecessor_node_ids,
        })
    return nodes


def _build_nodes_for_reading(reading: dict, previous_nodes) -> list:
    origin = reading["selected"]["origin"] if reading["selected"] else None
    if origin == "digital-text":
        return _build_nodes_for_digital_text_reading(reading, previous_nodes)
    text = reading["text"]
    previous_nodes = previous_nodes or []
    previous_by_id = {n["node_id"]: n for n in previous_nodes}
    groups = _merge_paragraph_lines(text, _classified_lines(text))
    nodes = []
    for start, end, kind, level in groups:
        node_id = deterministic_id(
            "node", reading["document_id"], reading["page_id"], reading["reading_id"],
            str(reading["version"]), str(start), str(end), kind,
        )
        overlapping = [
            n for n in previous_nodes
            if n["source_char_start"] < end and n["source_char_end"] > start
        ]
        existing = previous_by_id.get(node_id)
        if existing is not None:
            node_version = existing["node_version"]
            predecessor_node_ids = existing.get("predecessor_node_ids", [])
        else:
            node_version = max((n["node_version"] for n in overlapping), default=0) + 1
            predecessor_node_ids = [n["node_id"] for n in overlapping if n["node_id"] != node_id]
        nodes.append({
            "node_id": node_id, "node_version": node_version, "kind": kind, "level": level,
            "order": 0, "parent_node_id": None,
            "reading_id": reading["reading_id"], "reading_version": reading["version"],
            "document_id": reading["document_id"], "page_id": reading["page_id"],
            "language": reading["language"], "source_char_start": start, "source_char_end": end,
            "text": text[start:end], "anchors": _intersecting_anchors(reading["selected_anchors"], start, end),
            "predecessor_node_ids": predecessor_node_ids,
        })
    return nodes


def _finalize_hierarchy(nodes: list, previous_nodes: list) -> None:
    """Assign deterministic document order and nearest structural parent.

    Parent links may cross page readings. If resolving an earlier page changes
    a later node's structural parent/order, the stable node identity remains
    but its version increments so dependent artifacts can invalidate safely.
    """
    previous_by_id = {n["node_id"]: n for n in previous_nodes}
    active = {}
    for order, node in enumerate(nodes, 1):
        level = node["level"]
        if level is not None:
            parent_levels = [candidate for candidate in active if candidate < level]
            node["parent_node_id"] = active[max(parent_levels)] if parent_levels else None
            active = {candidate: node_id for candidate, node_id in active.items()
                      if candidate < level}
            active[level] = node["node_id"]
        else:
            node["parent_node_id"] = active[max(active)] if active else None
        node["order"] = order

        old = previous_by_id.get(node["node_id"])
        if old is None:
            continue
        comparable = {key: value for key, value in node.items()
                      if key not in ("node_version", "predecessor_node_ids")}
        old_comparable = {key: value for key, value in old.items()
                          if key not in ("node_version", "predecessor_node_ids")}
        if comparable == old_comparable:
            node["node_version"] = old["node_version"]
            node["predecessor_node_ids"] = old["predecessor_node_ids"]
        else:
            node["node_version"] = old["node_version"] + 1
            node["predecessor_node_ids"] = old["predecessor_node_ids"]


def _build_unit_node_links(units: list, nodes: list) -> list:
    links = []
    for unit in units:
        links.append({
            "unit_id": unit["unit_id"],
            "node_ids": [
                node["node_id"] for node in nodes
                if node["page_id"] == unit["page_id"]
                and node["source_char_start"] < unit["source_char_end"]
                and node["source_char_end"] > unit["source_char_start"]
            ],
        })
    return links


def _word_count(text: str) -> int:
    """Deterministic size heuristic for spaced languages and Japanese.

    Each Japanese/CJK character counts as one conservative token; remaining
    non-CJK material is counted by whitespace-delimited token. This is not a
    linguistic tokenizer and intentionally errs toward bounded units.
    """
    cjk_count = len(_CJK_CHARACTER_RE.findall(text))
    remainder = _CJK_CHARACTER_RE.sub(" ", text)
    return cjk_count + len(remainder.split())


def _split_oversized(text: str, start: int, end: int, max_words: int) -> list:
    """Split one span at the strongest available internal boundary (sentence
    breaks) only when it exceeds the word-count target; never mid-sentence."""
    segment = text[start:end]
    if _word_count(segment) <= max_words:
        return [(start, end)]
    cut_points = sorted({start, end, *(start + m.start() for m in _SENTENCE_SPLIT_RE.finditer(segment))})
    spans, piece_start, word_count = [], start, 0
    for i in range(1, len(cut_points)):
        left, right = cut_points[i - 1], cut_points[i]
        piece_words = _word_count(text[left:right])
        if word_count > 0 and word_count + piece_words > max_words:
            spans.append((piece_start, left))
            piece_start, word_count = left, piece_words
        else:
            word_count += piece_words
    spans.append((piece_start, end))
    return spans


def _group_spans_from_nodes(text: str, nodes: list, max_unit_words: int) -> list:
    """Group adjacent paragraph nodes toward the word-count target; any other
    node kind (heading, note, scene break, ...) is always its own boundary.
    A group (or a lone oversized node) exceeding the target is split at the
    strongest available internal boundary."""
    spans, run_start, run_end, run_words = [], None, None, 0
    for node in nodes:
        if node["kind"] != "paragraph":
            if run_start is not None:
                spans.extend(_split_oversized(text, run_start, run_end, max_unit_words))
                run_start = None
            spans.extend(_split_oversized(text, node["source_char_start"], node["source_char_end"], max_unit_words))
            continue
        words = _word_count(node["text"])
        if run_start is None:
            run_start, run_end, run_words = node["source_char_start"], node["source_char_end"], words
        elif run_words + words > max_unit_words:
            spans.extend(_split_oversized(text, run_start, run_end, max_unit_words))
            run_start, run_end, run_words = node["source_char_start"], node["source_char_end"], words
        else:
            run_end = node["source_char_end"]
            run_words += words
    if run_start is not None:
        spans.extend(_split_oversized(text, run_start, run_end, max_unit_words))
    return spans


def _validate_unit_policy(unit_policy):
    if unit_policy is None:
        return {"version": "semantic-units@1", "max_unit_words": DEFAULT_MAX_UNIT_WORDS}
    require(isinstance(unit_policy, dict) and set(unit_policy) <= {"max_unit_words"},
            "unit policy must only narrow the deterministic word-count target")
    max_words = unit_policy.get("max_unit_words", DEFAULT_MAX_UNIT_WORDS)
    require(integer(max_words, 1), "invalid unit policy max_unit_words")
    return {"version": "semantic-units@1", "max_unit_words": max_words}


def build_structure_v2(document, ocr_bundle=None, decisions=None, boundaries=None, previous=None,
                       unit_policy=None, validate_any=None, validate_boundaries=None, continuity_check=None):
    effective_policy = _validate_unit_policy(unit_policy)
    max_unit_words = effective_policy["max_unit_words"]

    legacy_predecessor_hash, effective_previous = None, None
    if previous is not None:
        require(isinstance(previous, dict), "previous structure must be an object")
        validate_any(previous)
        require(previous.get("document_id") == document.document_id
                and previous.get("pdf_hash") == document.input_hash,
                "previous structure does not match this document/PDF lineage")
        if previous.get("schema_version") == 1:
            legacy_predecessor_hash = fingerprint(previous)
        else:
            effective_previous = previous
            legacy_predecessor_hash = previous.get("legacy_predecessor_hash")

    if boundaries is None:
        boundaries = {}
    require(isinstance(boundaries, dict), "boundaries must be an object mapping page_id to spans")
    known_page_ids = {p.page_id for p in document.pages}
    for page_id in boundaries:
        require(page_id in known_page_ids, "boundaries reference an unknown page_id")

    previous_readings = effective_previous.get("readings") if effective_previous else None
    readings_raw = build_readings(
        document, ocr_bundle=ocr_bundle, decisions=decisions, previous_readings=previous_readings,
    )
    input_hash = fingerprint({"document": document.to_dict(), "ocr": ocr_bundle, "decisions": decisions,
                              "boundaries": boundaries, "unit_policy": effective_policy})

    for reading in readings_raw:
        reading["language"] = document.language
        selected_candidate = next(
            (
                c for c in reading["alternatives"]
                if reading["selected"] is not None
                and c["origin"] == reading["selected"]["origin"]
                and c["candidate_hash"] == reading["selected"]["candidate_hash"]
            ),
            None,
        )
        reading["selected_anchors"] = selected_candidate["anchors"] if selected_candidate else []
        reading["selected_warnings"] = selected_candidate["warnings"] if selected_candidate else []

    previous_nodes_by_page, previous_units_by_page = {}, {}
    if effective_previous:
        for n in effective_previous.get("nodes", []):
            previous_nodes_by_page.setdefault(n["page_id"], []).append(n)
        for u in effective_previous.get("units", []):
            previous_units_by_page.setdefault(u["page_id"], []).append(u)

    all_nodes, all_units, all_unit_node_links, continuity_findings = [], [], [], []
    for reading in readings_raw:
        if reading["status"] != "resolved" and reading["page_id"] in boundaries:
            raise StructureError("boundaries require a resolved reading")
        if reading["status"] != "resolved":
            continue
        nodes = _build_nodes_for_reading(reading, previous_nodes_by_page.get(reading["page_id"]))
        all_nodes.extend(nodes)

        page_boundary = boundaries.get(reading["page_id"])
        if page_boundary is not None:
            spans = validate_boundaries(reading["text"], page_boundary)
        else:
            spans = _group_spans_from_nodes(reading["text"], nodes, max_unit_words)
        units = _build_units_for_reading(
            reading, spans, previous_units_by_page.get(reading["page_id"]), document.warnings,
        )
        all_units.extend(units)
        all_unit_node_links.extend(_build_unit_node_links(units, nodes))
        findings = continuity_check(reading, units)
        require(not findings, "boundary plan violates source continuity")
        continuity_findings.extend(findings)

    previous_nodes = effective_previous.get("nodes", []) if effective_previous else []
    _finalize_hierarchy(all_nodes, previous_nodes)

    readings = []
    for reading in readings_raw:
        reading = dict(reading)
        reading.pop("language", None)
        reading.pop("selected_anchors", None)
        reading.pop("selected_warnings", None)
        readings.append(reading)

    if (effective_previous is not None and effective_previous["input_hash"] == input_hash
            and effective_previous.get("legacy_predecessor_hash") == legacy_predecessor_hash):
        return copy.deepcopy(effective_previous)

    parent_revision = effective_previous["revision"]["id"] if effective_previous else None
    revision_id = deterministic_id("structure-revision", input_hash, parent_revision or "")
    history = list(effective_previous.get("history", [])) if effective_previous else []
    if effective_previous is not None:
        history = history + [{
            "revision_id": effective_previous["revision"]["id"],
            "revision_number": effective_previous["revision"]["number"],
            "parent_revision": effective_previous["revision"]["parent_revision"],
            "input_hash": effective_previous["input_hash"],
            "readings": effective_previous["readings"],
            "nodes": effective_previous["nodes"],
            "units": effective_previous["units"],
            "unit_node_links": effective_previous["unit_node_links"],
            "unit_policy": effective_previous["unit_policy"],
            "continuity": effective_previous["continuity"],
        }]

    result = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "document_id": document.document_id,
        "document_version": document.document_version,
        "pdf_hash": document.input_hash,
        "source_uri": document.source_uri,
        "language": document.language,
        "input_hash": input_hash,
        "legacy_predecessor_hash": legacy_predecessor_hash,
        "unit_policy": effective_policy,
        "revision": {"id": revision_id, "number": len(history) + 1, "parent_revision": parent_revision},
        "readings": readings,
        "nodes": all_nodes,
        "units": all_units,
        "unit_node_links": all_unit_node_links,
        "continuity": continuity_findings,
        "history": history,
    }
    validate_any(result)
    return copy.deepcopy(result)


def _selected(reading):
    if reading["selected"] is None:
        return None
    return next((c for c in reading["alternatives"] if
                 {k: c[k] for k in ("origin", "candidate_hash")} == reading["selected"]), None)


def _validate_reading(r, document_id, pdf_hash):
    require(isinstance(r, dict) and set(r) == _READING_FIELDS, "invalid persisted reading shape")
    require(r["document_id"] == document_id and nonempty(r["page_id"]) and integer(r["page_number"])
            and integer(r["version"]) and (r["prior_version"] is None or
                 integer(r["prior_version"]) and r["prior_version"] < r["version"]), "invalid reading identity/version")
    require(r["reading_id"] == deterministic_id("structure-reading", document_id, r["page_id"]),
            "reading identity mismatch")
    require(isinstance(r["alternatives"], list) and r["alternatives"], "missing reading evidence")
    origins = set()
    geometry = None
    for c in r["alternatives"]:
        validate_candidate(c)
        require(c["document_id"] == document_id and c["page_id"] == r["page_id"]
                and c["page_number"] == r["page_number"] and c["pdf_hash"] == pdf_hash,
                "reading evidence lineage mismatch")
        require(c["origin"] not in origins, "duplicate source alternative")
        origins.add(c["origin"])
        box = (c["pdf_width"], c["pdf_height"])
        require(geometry is None or geometry == box, "source alternatives geometry mismatch")
        geometry = box
    # PDF/OCR readings always carry a "digital" alternative (build_readings
    # always adds one); EPUB readings carry only "digital-text" instead
    # (there is no PDF digital-extraction stage for EPUB). Either is
    # acceptable primary digital evidence; this is additive, not a
    # relaxation of the PDF/OCR requirement, which is unaffected.
    require("digital" in origins or "digital-text" in origins, "digital extraction evidence missing")
    if r["status"] == "resolved":
        validate_decision(r["decision"])
        require(isinstance(r["selected"], dict) and set(r["selected"]) == {"origin", "candidate_hash"},
                "invalid selected evidence reference")
        c = _selected(r)
        require(c is not None and c["usable"] and r["selected"] ==
                {k: r["decision"][k] for k in ("origin", "candidate_hash")}, "source decision binding mismatch")
        require(r["text"] == c["text"] and r["text_hash"] == c["text_hash"] and r["reasons"] == [],
                "resolved reading text/hash mismatch")
    else:
        require(r["status"] == "unresolved" and r["decision"] is None and r["selected"] is None
                and r["text"] is None and r["text_hash"] is None, "invalid unresolved reading")
        expected = "unreviewed_source" if any(c["usable"] for c in r["alternatives"]) else "missing_source"
        require(r["reasons"] == [expected], "unresolved reason mismatch")


def _validate_node(n, index_readings, data):
    require(isinstance(n, dict) and set(n) == _NODE_FIELDS, "invalid persisted node shape")
    require(nonempty(n["node_id"]) and integer(n["node_version"]) and n["kind"] in NODE_KINDS
            and (n["level"] is None or integer(n["level"], 1)) and integer(n["order"])
            and (n["parent_node_id"] is None or nonempty(n["parent_node_id"])),
            "invalid node identity/kind/order")
    r = index_readings.get(n["reading_id"])
    require(r is not None and r["status"] == "resolved" and r["version"] == n["reading_version"],
            "node references unresolved/unknown reading")
    start, end = n["source_char_start"], n["source_char_end"]
    require(integer(start, 0) and integer(end) and start < end <= len(r["text"]), "invalid node span")
    require(n["document_id"] == r["document_id"] and n["page_id"] == r["page_id"]
            and n["language"] == data["language"] and n["text"] == r["text"][start:end],
            "node source binding mismatch")
    require(n["node_id"] == deterministic_id("node", n["document_id"], r["page_id"], r["reading_id"],
            str(r["version"]), str(start), str(end), n["kind"]), "node identity mismatch")
    c = _selected(r)
    require(n["anchors"] == _intersecting_anchors(c["anchors"], start, end), "node anchors mismatch")
    require(strings(n["predecessor_node_ids"]) and len(set(n["predecessor_node_ids"])) == len(n["predecessor_node_ids"]),
            "invalid predecessor node identities")


def _validate_unit(u, index_readings, data):
    require(isinstance(u, dict) and set(u) == _UNIT_FIELDS, "invalid persisted unit shape")
    require(nonempty(u["unit_id"]) and integer(u["unit_version"])
            and nonempty(u["reading_id"]) and integer(u["reading_version"]), "invalid unit identity")
    r = index_readings.get(u["reading_id"])
    require(r is not None and r["status"] == "resolved" and r["version"] == u["reading_version"],
            "unit references unresolved/unknown reading")
    start, end = u["source_char_start"], u["source_char_end"]
    require(integer(start, 0) and integer(end) and start < end <= len(r["text"]), "invalid unit span")
    require(u["document_id"] == r["document_id"] and u["page_id"] == r["page_id"]
            and u["language"] == data["language"] and u["reading_text_hash"] == r["text_hash"]
            and u["text"] == r["text"][start:end], "unit source binding mismatch")
    require(u["unit_id"] == deterministic_id("unit", data["document_id"], r["page_id"], r["reading_id"],
            str(r["version"]), str(start), str(end)), "unit identity mismatch")
    c = _selected(r)
    require(u["anchors"] == _intersecting_anchors(c["anchors"], start, end), "unit anchors mismatch")
    require(u["status"] == "unreviewed" and strings(u["warnings"])
            and "unreviewed_translation" in u["warnings"]
            and set(c["warnings"]) <= set(u["warnings"]), "unit review/warnings mismatch")
    require(strings(u["predecessor_unit_ids"]) and len(set(u["predecessor_unit_ids"])) == len(u["predecessor_unit_ids"]),
            "invalid predecessor identities")
def _validate_snapshot(readings, nodes, units, unit_node_links, continuity, data, continuity_check):
    require(isinstance(readings, list) and isinstance(nodes, list) and isinstance(units, list)
            and isinstance(unit_node_links, list) and isinstance(continuity, list),
            "invalid structure collections")
    index, pages, numbers = {}, set(), set()
    for r in readings:
        _validate_reading(r, data["document_id"], data["pdf_hash"])
        require(r["page_id"] not in pages and r["page_number"] not in numbers, "duplicate reading page")
        pages.add(r["page_id"]); numbers.add(r["page_number"])
        index[r["reading_id"]] = r
    node_ids, by_node, orders = set(), {}, set()
    for n in nodes:
        _validate_node(n, index, data)
        require(n["node_id"] not in node_ids and n["order"] not in orders, "duplicate node identity/order")
        node_ids.add(n["node_id"])
        orders.add(n["order"])
        by_node[n["node_id"]] = n
    require(orders == set(range(1, len(nodes) + 1)), "node reading order is not contiguous")
    for n in nodes:
        require(n["parent_node_id"] is None or n["parent_node_id"] in by_node,
                "node parent reference is unknown")
        parent = by_node.get(n["parent_node_id"]) if n["parent_node_id"] is not None else None
        require(parent is None or (parent["order"] < n["order"] and parent["level"] is not None
                                   and (n["level"] is None or parent["level"] < n["level"])),
                "invalid node parent hierarchy")
    ids, by_reading = set(), {}
    for u in units:
        _validate_unit(u, index, data)
        require(u["unit_id"] not in ids, "duplicate/invalid unit identity")
        ids.add(u["unit_id"])
        by_reading.setdefault(u["reading_id"], []).append(u)
    links_by_unit = {}
    units_by_id = {unit["unit_id"]: unit for unit in units}
    for link in unit_node_links:
        require(isinstance(link, dict) and set(link) == _UNIT_NODE_LINK_FIELDS
                and nonempty(link["unit_id"]) and link["unit_id"] not in links_by_unit
                and strings(link["node_ids"]), "invalid unit-node link")
        unit = units_by_id.get(link["unit_id"])
        require(unit is not None, "unit-node link references unknown unit")
        expected_nodes = [
            node["node_id"] for node in sorted(nodes, key=lambda item: item["order"])
            if node["page_id"] == unit["page_id"]
            and node["source_char_start"] < unit["source_char_end"]
            and node["source_char_end"] > unit["source_char_start"]
        ]
        require(link["node_ids"] == expected_nodes, "unit logical-node binding mismatch")
        links_by_unit[link["unit_id"]] = link
    require(set(links_by_unit) == ids, "missing unit-node link")
    findings = []
    for r in readings:
        findings.extend(continuity_check(r, by_reading.get(r["reading_id"], [])))
    require(continuity == findings and not findings, "persisted source continuity failure")
    return index, by_node, {u["unit_id"]: u for u in units}


def validate_structure_v2(data, validate_legacy=None):
    """Validate a current or historical schema-2 logical-structure snapshot.

    Detects inconsistent/tampered records, not coordinated rewriting of all
    source evidence or authenticity of the asserted human actor. No files or
    network access.
    """
    from .segmentation import check_continuity

    fields = {"schema_version", "stage", "document_id", "document_version", "pdf_hash", "source_uri",
              "language", "input_hash", "legacy_predecessor_hash", "unit_policy", "revision", "readings", "nodes",
              "units", "unit_node_links", "continuity", "history"}
    require(isinstance(data, dict) and set(data) == fields, "invalid structure shape")
    require(type(data["schema_version"]) is int and data["schema_version"] == SCHEMA_VERSION
            and data["stage"] == STAGE and nonempty(data["document_id"]) and integer(data["document_version"])
            and sha(data["pdf_hash"]) and sha(data["input_hash"]) and nonempty(data["source_uri"])
            and nonempty(data["language"]), "invalid structure identity/stage")
    require(data["legacy_predecessor_hash"] is None or sha(data["legacy_predecessor_hash"]),
            "invalid legacy predecessor reference")
    require(isinstance(data["unit_policy"], dict)
            and set(data["unit_policy"]) == {"version", "max_unit_words"}
            and data["unit_policy"]["version"] == "semantic-units@1"
            and integer(data["unit_policy"]["max_unit_words"], 1), "invalid unit policy")
    rev = data["revision"]
    require(isinstance(rev, dict) and set(rev) == {"id", "number", "parent_revision"}
            and nonempty(rev["id"]) and integer(rev["number"]), "invalid structure revision")
    require(isinstance(data["history"], list) and rev["number"] == len(data["history"]) + 1,
            "invalid structure history count")
    snapshots = data["history"] + [dict(revision_id=rev["id"], revision_number=rev["number"],
                                       parent_revision=rev["parent_revision"], input_hash=data["input_hash"],
                                       readings=data["readings"], nodes=data["nodes"], units=data["units"],
                                       unit_node_links=data["unit_node_links"],
                                       unit_policy=data["unit_policy"],
                                       continuity=data["continuity"])]
    previous_id, previous_readings, previous_nodes, previous_units, seen = None, {}, {}, {}, set()
    for number, snap in enumerate(snapshots, 1):
        require(isinstance(snap, dict) and set(snap) == {"revision_id", "revision_number", "parent_revision",
                "input_hash", "readings", "nodes", "units", "unit_node_links", "unit_policy", "continuity"},
                "invalid history snapshot")
        require(isinstance(snap["unit_policy"], dict)
                and set(snap["unit_policy"]) == {"version", "max_unit_words"}
                and snap["unit_policy"]["version"] == "semantic-units@1"
                and integer(snap["unit_policy"]["max_unit_words"], 1), "invalid snapshot unit policy")
        require(integer(snap["revision_number"]) and snap["revision_number"] == number
                and sha(snap["input_hash"]) and snap["parent_revision"] == previous_id
                and snap["revision_id"] == deterministic_id("structure-revision", snap["input_hash"], previous_id or ""),
                "revision history linkage mismatch")
        require(snap["revision_id"] not in seen, "duplicate history revision")
        seen.add(snap["revision_id"])
        readings, nodes, units = _validate_snapshot(
            snap["readings"], snap["nodes"], snap["units"], snap["unit_node_links"],
            snap["continuity"], data, check_continuity,
        )
        require(not previous_readings or set(readings) == set(previous_readings), "reading pages changed in history")
        for rid, r in readings.items():
            old = previous_readings.get(rid)
            if old is None:
                require(r["version"] == 1 and r["prior_version"] is None, "invalid initial reading version")
            elif all(r[k] == old[k] for k in r if k not in ("version", "prior_version")):
                require(r["version"] == old["version"] and r["prior_version"] == old["prior_version"],
                        "unchanged reading version mismatch")
            else:
                require(r["version"] == old["version"] + 1 and r["prior_version"] == old["version"],
                        "changed reading prior version mismatch")
        for nid, nd in nodes.items():
            old = previous_nodes.get(nid)
            if old is not None:
                old_core = {key: value for key, value in old.items()
                            if key not in ("node_version", "predecessor_node_ids")}
                new_core = {key: value for key, value in nd.items()
                            if key not in ("node_version", "predecessor_node_ids")}
                if new_core == old_core:
                    require(nd == old, "unchanged node mutated")
                else:
                    require(nd["node_version"] == old["node_version"] + 1
                            and nd["predecessor_node_ids"] == old["predecessor_node_ids"],
                            "changed stable node version mismatch")
            else:
                overlaps = [p for p in previous_nodes.values() if p["page_id"] == nd["page_id"]
                            and p["source_char_start"] < nd["source_char_end"] and p["source_char_end"] > nd["source_char_start"]]
                require(nd["predecessor_node_ids"] == [p["node_id"] for p in overlaps]
                        and nd["node_version"] == max((p["node_version"] for p in overlaps), default=0) + 1,
                        "node predecessor/version mismatch")
        for uid, u in units.items():
            old = previous_units.get(uid)
            if old is not None:
                old_core = {key: value for key, value in old.items()
                            if key not in ("unit_version", "predecessor_unit_ids")}
                new_core = {key: value for key, value in u.items()
                            if key not in ("unit_version", "predecessor_unit_ids")}
                if new_core == old_core:
                    require(u == old, "unchanged unit mutated")
                else:
                    require(u["unit_version"] == old["unit_version"] + 1
                            and u["predecessor_unit_ids"] == old["predecessor_unit_ids"],
                            "changed stable unit version mismatch")
            else:
                overlaps = [p for p in previous_units.values() if p["page_id"] == u["page_id"]
                            and p["source_char_start"] < u["source_char_end"] and p["source_char_end"] > u["source_char_start"]]
                require(u["predecessor_unit_ids"] == [p["unit_id"] for p in overlaps]
                        and u["unit_version"] == max((p["unit_version"] for p in overlaps), default=0) + 1,
                        "unit predecessor/version mismatch")
        previous_id, previous_readings, previous_nodes, previous_units = (
            snap["revision_id"], readings, nodes, units,
        )
