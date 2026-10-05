"""Builder B: Hebrew EPUB and immutable translation-library import into an
independent LearningSource (learning_contracts.validate_source).

Reuses the existing validated EPUB reader (epub_extract.extract_epub, which
itself reuses epub_archive.py's archive/XML safety checks) for
``import_hebrew_epub``, and document_draft.chapter_groups for
``import_translation_job``'s chapter partitioning -- never a second
independent EPUB archive reader or chapter model. Both paths produce the
same LearningSource contract (learning_contracts.validate_source); neither
touches storage, active-book selection or HTTP resolution -- that is A/Sol's
job (audit/contracts/learn_1.md).
"""
from __future__ import annotations

import re

from . import document_draft, epub_extract
from .learning_contracts import (
    LearningError, MAX_CHUNK_CHARS, check_id, require, source_hash as _source_hash,
    text_hash, validate_source,
)
from .store import deterministic_id

# Headings (h1/h2-h6) are the only segment kinds the EPUB digital-text
# extractor (epub_extract.TAG_NODE_KIND) marks as such; everything else
# (paragraph/list/quotation) is plain reading content for the learner.
_HEADING_NODE_KINDS = ("heading", "subheading")

# Minimum share of Hebrew letters among alphabetic characters for a book to
# be accepted as Hebrew-base; foreign names/quotations stay well under this
# bar in a genuinely Hebrew book, while a non-Hebrew book stays near zero.
_HEBREW_SHARE_THRESHOLD = 0.3

_HEBREW_RE = re.compile(r"[֐-׿]")
_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)

_EPUB_ERROR_CODES = {
    "empty_chapters": "damaged_epub",
    "empty_spine": "empty_epub",
    "bad_spine_item": "damaged_epub",
    "drm": "drm_protected",
    "no_text": "empty_epub",
}


def _hebrew_share(text):
    alpha = _ALPHA_RE.findall(text)
    if not alpha:
        return 0.0
    return len(_HEBREW_RE.findall(text)) / len(alpha)


def _split_paragraph(text, max_chars=MAX_CHUNK_CHARS):
    """Deterministic whitespace split of a long paragraph into <= max_chars
    pieces; never splits inside a word. A single whitespace-free token
    longer than max_chars is returned unsplit (nothing smaller is safe)."""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _units_from_page(page):
    units = []
    for segment in page.segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        prefix = f"p{page.page_number}-s{segment.order}"
        if segment.node_kind in _HEADING_NODE_KINDS:
            units.append({"unit_id": prefix, "kind": "heading", "text": text})
            continue
        for index, part in enumerate(_split_paragraph(text)):
            unit_id = prefix if index == 0 else f"{prefix}-c{index}"
            units.append({"unit_id": unit_id, "kind": "paragraph", "text": part})
    return units


def _group_pages(pages):
    """Merge consecutive spine pages until each group holds at least
    document_draft.MIN_CHAPTER_CHARS of text (mirrors document_draft's own
    EPUB spine-chapter merging); a final short group merges backward."""
    groups, pending = [], []
    for page in pages:
        pending.append(page)
        if sum(len(p.source_text or "") for p in pending) >= document_draft.MIN_CHAPTER_CHARS:
            groups.append(pending)
            pending = []
    if pending:
        if groups:
            groups[-1] = groups[-1] + pending
        else:
            groups.append(pending)
    return groups


def _finalize_source(book_id, title, origin, chapters):
    source = {
        "schema_version": 1, "book_id": check_id(book_id), "revision": 1,
        "title": title[:500] if title else "ספר מיובא",
        "origin": origin, "chapters": chapters,
    }
    source["source_hash"] = _source_hash(source)
    return validate_source(source)


def import_hebrew_epub(path_or_bytes, book_id=None, title=None):
    """Import a Hebrew EPUB into an independent LearningSource. Raises
    LearningError with a stable ``code`` for invalid, empty, damaged, DRM
    protected, unsupported or non-Hebrew-base input."""
    try:
        document = epub_extract.extract_epub(path_or_bytes, language="he")
    except epub_extract.EpubExtractionError as exc:
        raise LearningError(_EPUB_ERROR_CODES.get(exc.code, "invalid_epub"), str(exc)) from None

    full_text = "\n".join(p.source_text or "" for p in document.pages)
    require(bool(full_text.strip()), "no_hebrew_text")
    require(_hebrew_share(full_text) >= _HEBREW_SHARE_THRESHOLD, "wrong_language")

    pages = [p for p in document.pages if p.segments]
    require(bool(pages), "no_hebrew_text")

    # Explicit h1 chapter boundaries take precedence over size grouping. A
    # single spine file may contain several chapters, including short ones.
    groups = []
    if any(s.node_kind == 'heading' for p in pages for s in p.segments):
        current = []
        for page in pages:
            for unit in _units_from_page(page):
                if unit['kind'] == 'heading' and current and any(u['kind'] == 'paragraph' for u in current):
                    groups.append(current)
                    current = []
                current.append(unit)
        if current:
            groups.append(current)
    else:
        groups = [[u for page in group for u in _units_from_page(page)] for group in _group_pages(pages)]
    chapters = []
    for index, units in enumerate(groups, start=1):
        if not units:
            continue
        heading = next((u for u in units if u["kind"] == "heading"), None)
        chapter_title = heading["text"][:500] if heading else f"פרק {index}"
        chapters.append({
            "chapter_id": f"chapter-{index}", "title": chapter_title,
            "units": [{"unit_id": u["unit_id"], "kind": u["kind"], "text": u["text"]} for u in units],
        })
    require(bool(chapters), "no_hebrew_text")

    resolved_book_id = book_id if book_id is not None else deterministic_id("learning-source-epub", document.input_hash)
    first_heading_title = next((c["title"] for c in chapters if any(u['kind'] == 'heading' for u in c['units'])), None)
    origin = {
        "kind": "hebrew_epub", "original_hash": document.input_hash,
        "source_job_id": None, "source_revision": None,
    }
    return _finalize_source(resolved_book_id, title or first_heading_title, origin, chapters)


def import_translation_job(snapshot, book_id=None):
    """Import a server-resolved, completed Hebrew translation job snapshot
    into an independent LearningSource. Raises LearningError for an
    unfinished job or any unit missing its current target_text. The
    returned source is immutable: later edits/regeneration of the original
    job never mutate a previously imported copy (no reference to it is
    stored beyond the recorded job id/revision in ``origin``)."""
    require(isinstance(snapshot, dict), "invalid_job")
    require(snapshot.get("status") == "completed", "unfinished_job")
    units_raw = snapshot.get("units") or []
    require(bool(units_raw), "no_hebrew_text")
    structure = snapshot.get("structure")
    require(isinstance(structure, dict), "invalid_job")
    for unit in units_raw:
        target = unit.get("target_text")
        require(isinstance(target, str) and target.strip(), "missing_target_text")
    require(_hebrew_share('\n'.join(u['target_text'] for u in units_raw)) >= _HEBREW_SHARE_THRESHOLD, 'wrong_language')

    chapters = []
    for index, group in enumerate(document_draft.chapter_groups(structure, units_raw), start=1):
        chapter_units = []
        for unit in group:
            base_id = check_id(unit["unit_id"])
            for part_index, part in enumerate(_split_paragraph(unit["target_text"])):
                unit_id = base_id if part_index == 0 else f"{base_id}-c{part_index}"
                chapter_units.append({"unit_id": unit_id, "kind": "paragraph", "text": part})
        if chapter_units:
            chapters.append({"chapter_id": f"chapter-{index}", "title": f"פרק {index}", "units": chapter_units})
    require(bool(chapters), "no_hebrew_text")

    job_id = check_id(snapshot["job_id"])
    resolved_book_id = book_id if book_id is not None else deterministic_id("learning-source-job", job_id)
    original_source_text = "\n".join(unit.get("source_text") or "" for unit in units_raw)
    origin = {
        "kind": "translation_library", "original_hash": text_hash(original_source_text),
        "source_job_id": job_id, "source_revision": int(snapshot.get("revision") or 0),
    }
    return _finalize_source(resolved_book_id, snapshot.get("filename"), origin, chapters)
