"""Article layout (ARTICLE-NOTES): footnotes, note marks, page furniture and reference lists.

Pure and deterministic, no I/O and no provider calls. Two layers:

* ``analyze_readings(readings)`` looks at the line geometry of resolved PDF/OCR page
  readings (document-wide) and returns per-page line overrides: the bottom-of-page note zone
  (``note``), repeated running headers/footers (``page_furniture``) and the reference list
  (``heading`` + ``bibliography_entry``). ``document_structure`` applies them when it builds
  nodes; source characters are never rewritten.
* ``note_index(structure)`` derives, from a built structure, the note units with their
  labels and the note marks inside body units; ``marked_text`` shows a mark as ``[^n]``.

Mathematics is never a mark: a digit run after a single letter, a Greek letter, a math
symbol, ``^``/``_`` or a digit, or inside a formula node, stays plain text.
"""
from __future__ import annotations

import re
import statistics

NOTE_HEIGHT_RATIO = 0.88
HEADING_HEIGHT_RATIO = 1.15
MIN_BODY_WORDS = 4
FURNITURE_MIN_PAGES = 3
EDGE_LINES = 2
MARK_TOKEN_RE = re.compile(r"\[\^(\d{1,3}|[*†‡§]{1,3})\]")
PASSTHROUGH_KINDS = frozenset({"page_furniture", "bibliography_entry"})
_STRUCTURAL_KINDS = frozenset({"part", "chapter", "section", "subsection", "subheading"})
BODY_KINDS = frozenset({"paragraph", "heading", "subheading", "section", "subsection", "chapter", "part",
                        "list", "quotation", "caption", "unsupported"})

_LABEL_RE = re.compile(r"^\s*(?:(\d{1,3})(?!\d)(?![.,]\d)|([*†‡§]{1,3})|([¹²³⁰⁴-⁹]{1,3}))[.)]?\s*(?=\S)")
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_REFERENCES_RE = re.compile(
    r"^\s*(?:[\dIVX]+\.?\s+)?(references|bibliography|select bibliography|works cited|literature cited|"
    r"literature|literatur|literaturverzeichnis|bibliographie|références|références bibliographiques|"
    r"riferimenti bibliografici|bibliografia|bibliografía|referencias|参考文献|sources|notes and references)"
    r"\s*:?\s*$", re.IGNORECASE)
_ENTRY_START_RE = re.compile(
    r"^\s*(?:\[\d{1,4}\]|\d{1,4}\.\s|[A-ZÀ-Ý][\w'’\-]+(?:\s[A-ZÀ-Ý][\w'’\-]+)?,\s|[A-ZÀ-Ý][\w'’\-]+\s[A-Z]\.|[—–-]{2,})")
_HEADINGISH_RE = re.compile(r"^\s*(?:appendix|anhang|annexe|acknowledg|notes?\s*$)", re.IGNORECASE)
_PAGE_NUMBER_RE = re.compile(r"^(?:(?:page|page\s+n°|ページ)\s*)?\d{1,4}$", re.IGNORECASE)
_GREEK_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")
_MATH_CHARS = set("=<>≤≥≠≈≡∈∉⊂⊆→⇒⇔∑∏∫√+−×÷·^_∂∇∞±∓′″")
# A mark: digits glued to a word (>= 2 letters) or to closing punctuation, then space/punct/end.
_MARK_RE = re.compile(r"(?:(?<=[^\W\d_][^\W\d_])|(?<=[.,;:!?)\]”\"’']))(\d{1,3}|[*†‡§]{1,3})(?=[\s.,;:!?)\]”\"’']|$)")


# ------------------------------------------------------------------ geometry

def _text_lines(text):
    lines, start = [], 0
    for idx, ch in enumerate(text):
        if ch == "\n":
            if idx > start:
                lines.append((start, idx))
            start = idx + 1
    if start < len(text):
        lines.append((start, len(text)))
    return lines


def _anchor_box(anchor):
    box = anchor.get("bbox") if anchor.get("kind") == "line" else anchor.get("pdf_bbox")
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
        x0, top, x1, bottom = (float(v) for v in box)
        if bottom > top and x1 > x0:
            return x0, top, x1, bottom
    return None


def line_geometry(text, anchors):
    """``[{start, end, text, top, bottom, x0, x1, height}]`` for each text line; geometry
    fields are None when no anchor with a box covers the line."""
    out = []
    boxes = [(a.get("source_char_start"), a.get("source_char_end"), _anchor_box(a)) for a in anchors or []]
    for start, end in _text_lines(text or ""):
        hit = [b for s, e, b in boxes if b is not None and isinstance(s, int) and isinstance(e, int)
               and s < end and e > start]
        row = {"start": start, "end": end, "text": text[start:end], "top": None, "bottom": None,
               "x0": None, "x1": None, "height": None}
        if hit:
            row.update(top=min(b[1] for b in hit), bottom=max(b[3] for b in hit),
                       x0=min(b[0] for b in hit), x1=max(b[2] for b in hit),
                       height=statistics.median(b[3] - b[1] for b in hit))
        out.append(row)
    return out


def note_label(text):
    """The note label at the start of ``text`` ('12', '*') or None."""
    m = _LABEL_RE.match(text or "")
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3).translate(_SUPERSCRIPT_DIGITS)


def _normalise_edge(text):
    return re.sub(r"\d+", "#", " ".join(text.split()).casefold())


# ------------------------------------------------------------------ analysis

def _line_gap(pages, body):
    """Document-wide normal gap between consecutive lines (gaps under two body heights)."""
    gaps = []
    for _, lines in pages:
        geo = [ln for ln in lines if ln["top"] is not None]
        gaps.extend(b["top"] - a["bottom"] for a, b in zip(geo, geo[1:]) if b["top"] - a["bottom"] < 2 * body)
    return statistics.median(gaps) if gaps else None


def _edge_lines(lines, gap, body):
    """Top and bottom blocks of at most EDGE_LINES lines set apart from the rest of the page
    by a gap clearly wider than the document's normal line gap (geometry required)."""
    geo = [ln for ln in lines if ln["top"] is not None]
    if len(geo) < 3 or gap is None:
        return []
    gaps = [b["top"] - a["bottom"] for a, b in zip(geo, geo[1:])]
    wide = max(gap * 1.6, gap + body * 0.5)
    edge = []
    for i in range(min(EDGE_LINES, len(gaps))):
        if gaps[i] >= wide:
            edge.extend(geo[:i + 1])
            break
    for i in range(min(EDGE_LINES, len(gaps))):
        if gaps[-1 - i] >= wide:
            edge.extend(geo[len(geo) - 1 - i:])
            break
    return edge


def _selected_anchors(reading):
    selected = reading.get("selected") or {}
    for c in reading.get("alternatives", []):
        if c.get("origin") == selected.get("origin") and c.get("candidate_hash") == selected.get("candidate_hash"):
            return c.get("anchors") or [], c.get("origin")
    return [], None


def analyze_readings(readings):
    """Per-page overrides ``{page_id: {line_start: (kind, level, group_start)}}``.

    ``group_start`` is the start of the first line of the node the line belongs to; lines
    sharing it form one node. Only resolved PDF/OCR readings with geometry take part."""
    pages = []
    for r in readings or []:
        if r.get("status") != "resolved" or not isinstance(r.get("text"), str):
            continue
        anchors, origin = _selected_anchors(r)
        if origin not in ("digital", "ocr"):
            continue
        pages.append((r["page_id"], line_geometry(r["text"], anchors)))
    if not pages:
        return {}
    from .document_structure import classify_line
    heights = [ln["height"] for _, lines in pages for ln in lines
               if ln["height"] and len(ln["text"].split()) >= MIN_BODY_WORDS]
    body = statistics.median(heights) if heights else None
    overrides = {page_id: {} for page_id, _ in pages}

    # Running headers/footers: an edge line, set apart from the text by a wider gap than the
    # page's line spacing, whose normalised text repeats on at least 3 pages.
    gap = _line_gap(pages, body) if body else None
    edges = {page_id: _edge_lines(lines, gap, body) for page_id, lines in pages}
    edge_counts = {}
    for edge in edges.values():
        for key in {_normalise_edge(ln["text"]) for ln in edge}:
            edge_counts[key] = edge_counts.get(key, 0) + 1
    for page_id, lines in pages:
        if len(pages) < FURNITURE_MIN_PAGES:
            break
        for ln in edges[page_id]:
            key = _normalise_edge(ln["text"])
            if (key and edge_counts.get(key, 0) >= FURNITURE_MIN_PAGES and len(ln["text"].split()) <= 16
                    and classify_line(ln["text"])[0] not in _STRUCTURAL_KINDS):   # "Chapter 3" is no header
                overrides[page_id][ln["start"]] = ("page_furniture", None, ln["start"])

    # Bottom-of-page note zone.
    previous_had_notes = False
    for page_id, lines in pages:
        page_over = overrides[page_id]
        if body is None:
            previous_had_notes = False
            continue
        zone = []
        for ln in reversed(lines):
            if ln["start"] in page_over or _PAGE_NUMBER_RE.match(ln["text"].strip()):
                continue            # footer / page number below the notes
            if ln["height"] is None or ln["height"] > body * NOTE_HEIGHT_RATIO:
                break
            zone.append(ln)
        zone.reverse()
        first_label = next((i for i, ln in enumerate(zone) if note_label(ln["text"]) is not None), None)
        if first_label is None and not (zone and previous_had_notes):
            previous_had_notes = False      # no notes here; small lines stay body text
            continue
        if first_label is not None and first_label > 0 and not previous_had_notes:
            zone = zone[first_label:]       # nothing to continue: lines above the first note stay body
        # Lines before the first label continue the previous page's last note.
        group = zone[0]["start"]
        for ln in zone:
            if note_label(ln["text"]) is not None:
                group = ln["start"]
            page_over[ln["start"]] = ("note", None, group)
        previous_had_notes = True

    # Display-size lines (titles, section headings): short, larger type, no final period.
    if body is not None:
        for page_id, lines in pages:
            page_over = overrides[page_id]
            for ln in lines:
                text = ln["text"].strip()
                if (ln["start"] not in page_over and ln["height"] and ln["height"] >= body * HEADING_HEIGHT_RATIO
                        and len(text.split()) <= 14 and not text.endswith((".", ",", ";", ":"))
                        and not _PAGE_NUMBER_RE.match(text) and not text[:1].islower()
                        and classify_line(text)[0] == "paragraph"    # keep chapter/section/list kinds
                        # a raised note mark makes a body line taller; such a line is no heading
                        and not any(not _math_context(text, m.start(1)) for m in _MARK_RE.finditer(text))):
                    page_over[ln["start"]] = ("heading", 5, ln["start"])

    # Reference list: after a references heading, until the next heading-like line.
    in_refs, entry_group, prev_text = False, None, ""
    for page_id, lines in pages:
        page_over = overrides[page_id]
        for ln in lines:
            text = ln["text"].strip()
            over = page_over.get(ln["start"])
            if _REFERENCES_RE.match(text) and (over is None or over[0] == "heading"):
                page_over[ln["start"]] = ("heading", 5, ln["start"])
                in_refs, entry_group, prev_text = True, None, ""
                continue
            if over is not None:
                if over[0] == "heading":
                    in_refs = False         # the next section starts
                continue
            if _PAGE_NUMBER_RE.match(text) or not in_refs:
                continue
            if _HEADINGISH_RE.match(text) or (len(text) <= 60 and text.isupper() and len(text.split()) <= 6):
                in_refs = False
                continue
            starts = entry_group is None or (prev_text.rstrip().endswith((".", ")", "]")) and _ENTRY_START_RE.match(text))
            if starts:
                entry_group = (page_id, ln["start"])
            if entry_group[0] != page_id:      # an entry continuing on a new page starts a new node
                entry_group = (page_id, ln["start"])
            page_over[ln["start"]] = ("bibliography_entry", None, entry_group[1])
            prev_text = text
    return {page_id: over for page_id, over in overrides.items() if over}


# ------------------------------------------------------------------ marks

def _math_context(text, pos):
    """True when the digits at ``pos`` follow mathematics rather than a word or punctuation."""
    before = text[max(0, pos - 3):pos]
    if not before:
        return True
    last = before[-1]
    if last in _MATH_CHARS or _GREEK_RE.match(last) or last.isdigit():
        return True
    m = re.search(r"([^\W\d_]+)$", text[:pos])
    if m and (len(m.group(1)) < 2 or _GREEK_RE.search(m.group(1))):
        return True
    window = text[max(0, pos - 12):pos]
    return sum(ch in _MATH_CHARS for ch in window) >= 2


def find_marks(text, labels):
    """Marks for ``labels`` (in order, each at most once) in ``text``: ``[(start, end, label)]``."""
    found, cursor, want = [], 0, list(labels)
    candidates = [(m.start(1), m.end(1), m.group(1)) for m in _MARK_RE.finditer(text or "")
                  if not _math_context(text, m.start(1))]
    for label in want:
        hit = next((c for c in candidates if c[0] >= cursor and c[2] == label), None)
        if hit is not None:
            found.append(hit)
            cursor = hit[1]
    return found


def mark_token(label):
    return "[^" + label + "]"


def _units_and_kinds(structure):
    nodes = {n["node_id"]: n for n in structure.get("nodes", [])}
    links = {link["unit_id"]: link["node_ids"] for link in structure.get("unit_node_links", [])}
    rows = []
    for unit in structure.get("units", []):
        linked = [nodes[nid] for nid in links.get(unit["unit_id"], []) if nid in nodes]
        kinds = {n["kind"] for n in linked}
        order = min((n["order"] for n in linked), default=0)
        rows.append((order, unit, kinds))
    rows.sort(key=lambda r: r[0])
    return rows


_INDEX_CACHE = {}


def note_index(structure):
    """``{"notes": {unit_id: {"label", "page_id", "continues"}}, "marks": {unit_id: [(s, e, label)]},
    "passthrough": {unit_id: reason}}`` for a schema-2 structure (cached per revision)."""
    units = structure.get("units", [])
    key = (structure.get("input_hash"), (structure.get("revision") or {}).get("id"), len(units),
           units[0]["unit_id"] if units else None, units[-1]["unit_id"] if units else None,
           None if structure.get("revision") else id(structure), len(structure.get("nodes", [])))
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    from .formal_checks import has_translatable_words
    rows = _units_and_kinds(structure)
    notes, marks, passthrough = {}, {}, {}
    page_labels, last_note = {}, None
    for _, unit, kinds in rows:
        uid = unit["unit_id"]
        if kinds and kinds <= PASSTHROUGH_KINDS:
            passthrough[uid] = sorted(kinds)[0]
        elif kinds == {"formula"} and not has_translatable_words(unit["text"]):
            passthrough[uid] = "formula"
        if kinds == {"note"}:
            label = note_label(unit["text"])
            notes[uid] = {"label": label, "page_id": unit["page_id"],
                          "continues": None if label is not None else last_note}
            if label is not None:
                page_labels.setdefault(unit["page_id"], []).append(label)
                last_note = uid
    by_page = {}
    for _, unit, kinds in rows:
        if kinds and kinds <= BODY_KINDS:
            by_page.setdefault(unit["page_id"], []).append(unit)
    for page_id, labels in page_labels.items():
        units = by_page.get(page_id, [])
        joined, spans, pos = "", [], 0
        for unit in units:
            spans.append((unit["unit_id"], pos, pos + len(unit["text"])))
            joined += unit["text"] + "\n"
            pos += len(unit["text"]) + 1
        for start, end, label in find_marks(joined, labels):
            for uid, s, e in spans:
                if s <= start and end <= e:
                    marks.setdefault(uid, []).append((start - s, end - s, label))
                    break
    result = {"notes": notes, "marks": marks, "passthrough": passthrough}
    if len(_INDEX_CACHE) > 32:
        _INDEX_CACHE.clear()
    _INDEX_CACHE[key] = result
    return result


def marked_text(structure, unit):
    """Unit text with its note marks shown as ``[^n]`` (unchanged without marks)."""
    text = unit["text"]
    for start, end, label in sorted(note_index(structure)["marks"].get(unit["unit_id"], []), reverse=True):
        text = text[:start] + mark_token(label) + text[end:]
    return text


def repair_marks(source, target):
    """Make ``target`` hold exactly the marks of ``source`` (each once). Returns
    ``(target, changed)``: unknown or repeated marks are removed, missing ones appended."""
    wanted = MARK_TOKEN_RE.findall(source or "")
    if not wanted and not MARK_TOKEN_RE.search(target or ""):
        return target, False
    seen, changed = set(), False

    def keep(m):
        nonlocal changed
        label = m.group(1)
        if label in wanted and label not in seen:
            seen.add(label)
            return m.group(0)
        changed = True
        return ""
    out = MARK_TOKEN_RE.sub(keep, target)
    missing = [label for label in wanted if label not in seen]
    if missing:
        changed = True
        out = out.rstrip() + "".join(mark_token(label) for label in missing)
    return out, changed


def display_marks(text):
    """``[^12]`` -> superscript ¹² for plain-text displays."""
    sup = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    return MARK_TOKEN_RE.sub(lambda m: m.group(1).translate(sup), text or "")


def strip_note_label(text, label):
    """Hebrew note text without its leading number (the export prints the label itself)."""
    if not label:
        return text
    pattern = r"^\s*(?:\[\^?" + re.escape(label) + r"\]|" + re.escape(label) + r")[.)]?\s*"
    return re.sub(pattern, "", text or "", count=1)


def footnotes(structure, text_of):
    """Notes that have a mark in the body, joined with their continuations.

    ``text_of(unit_id)`` gives the text to show for a unit (translation or source). Returns
    ``(notes, consumed)``: ``notes[(page_id, label)]`` is the note text without its leading
    number; ``consumed`` holds the note unit ids rendered as footnotes (the others stay
    where they were)."""
    idx = note_index(structure)
    pages = {u["unit_id"]: u["page_id"] for u in structure.get("units", [])}
    marked = {(pages[uid], label) for uid, marks in idx["marks"].items() for _, _, label in marks}
    notes, consumed, key_of = {}, set(), {}
    for uid, info in idx["notes"].items():
        if info["label"] is not None:
            key = (info["page_id"], info["label"])
        else:
            key = key_of.get(info["continues"])
        key_of[uid] = key
        if key is None or key not in marked:
            continue
        text = text_of(uid)
        if info["label"] is not None:
            text = strip_note_label(text, info["label"])
        notes[key] = (notes.get(key, "") + " " + " ".join(text.split())).strip()
        consumed.add(uid)
    return notes, consumed
