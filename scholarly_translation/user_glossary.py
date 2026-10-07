"""Personal glossary (USER-TERMS): term choices the user keeps across documents.

Each term is ``{"source", "forms", "target", "target_language", "note"}``: a source term (and
other written forms of it) and the rendering the user requires in one target language. A
translation job takes a snapshot of the terms for its target language when it starts; the
terms that occur in the document become binding, human entries of its book notebook.

Stored locally as ``{"schema": "user-glossary@1", "terms": [...]}``. Pure validation plus
atomic file I/O; never calls a model. The text form edited in the UI is one term per line,
``source | other form = target  # note``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

SCHEMA = "user-glossary@1"
MAX_TERMS = 2000
MAX_FORMS = 8
MAX_SOURCE = 60      # book_notebook.MAX_MATCH_TERM_LEN
MAX_TARGET = 80       # name_table.MAX_HEBREW
MAX_NOTE = 500
_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


class UserGlossaryError(ValueError):
    """Invalid personal glossary input; the (Hebrew) message is shown to the user."""


def _clean(value, limit, what):
    if not isinstance(value, str):
        raise UserGlossaryError("רשימת המונחים אינה תקינה.")
    text = " ".join(value.split())
    if len(text) > limit:
        raise UserGlossaryError(f"{what} ארוך מ־{limit} תווים: {text[:40]}")
    return text


def normalize(terms):
    """Validated terms: whitespace collapsed, empty forms dropped, one term per
    (target language, source); a later duplicate replaces an earlier one."""
    if not isinstance(terms, list):
        raise UserGlossaryError("רשימת המונחים אינה תקינה.")
    if len(terms) > MAX_TERMS:
        raise UserGlossaryError(f"אפשר לשמור עד {MAX_TERMS} מונחים.")
    out = {}
    for row in terms:
        if not isinstance(row, dict):
            raise UserGlossaryError("רשימת המונחים אינה תקינה.")
        source = _clean(row.get("source"), MAX_SOURCE, "מונח המקור")
        target = _clean(row.get("target"), MAX_TARGET, "התרגום")
        if not source or not target:
            raise UserGlossaryError("לכל מונח נדרשים מונח מקור ותרגום.")
        language = row.get("target_language", "he")
        if not isinstance(language, str) or not _LANGUAGE_RE.match(language):
            raise UserGlossaryError("שפת היעד אינה נתמכת.")
        forms = []
        for form in row.get("forms") or []:
            form = _clean(form, MAX_SOURCE, "מונח המקור")
            if form and form != source and form not in forms:
                forms.append(form)
        if len(forms) > MAX_FORMS:
            raise UserGlossaryError(f"אפשר עד {MAX_FORMS} צורות נוספות למונח {source}.")
        note = _clean(row.get("note") or "", MAX_NOTE, "ההערה")
        out[(language, source)] = {"source": source, "forms": forms, "target": target,
                                   "target_language": language, "note": note}
    return list(out.values())


def load(path):
    """The stored terms (``[]`` when the file does not exist yet)."""
    path = Path(path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UserGlossaryError("קובץ המונחים האישי אינו קריא.") from None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise UserGlossaryError("קובץ המונחים האישי אינו קריא.")
    return normalize(data.get("terms"))


def save(path, terms):
    """Validate and atomically replace the stored terms; returns them."""
    terms = normalize(terms)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".user_glossary-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"schema": SCHEMA, "terms": terms}, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return terms


def for_target(terms, target_language):
    return [t for t in terms if t["target_language"] == target_language]


def parse_text(text, target_language):
    """Terms from the UI text form: ``source | other form = target  # note`` per line.
    Blank lines and lines starting with ``#`` are ignored."""
    if not isinstance(text, str):
        raise UserGlossaryError("רשימת המונחים אינה תקינה.")
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        body, _, note = line.partition("#")
        if "=" not in body:
            raise UserGlossaryError(f"שורה {number}: כתבו את המונח בצורה  מקור = תרגום")
        left, _, target = body.partition("=")
        forms = [f.strip() for f in left.split("|") if f.strip()]
        if not forms:
            raise UserGlossaryError(f"שורה {number}: חסר מונח המקור.")
        rows.append({"source": forms[0], "forms": forms[1:], "target": target.strip(),
                     "target_language": target_language, "note": note.strip()})
    return normalize(rows)


def format_text(terms):
    """The UI text form of ``terms`` (inverse of ``parse_text``)."""
    lines = []
    for t in terms:
        line = " | ".join([t["source"]] + t["forms"]) + " = " + t["target"]
        if t["note"]:
            line += "  # " + t["note"]
        lines.append(line)
    return "\n".join(lines)


def occurs(form, text):
    """``form`` occurs in ``text``: a substring for CJK, otherwise a whole word, ignoring case."""
    if _CJK_RE.search(form):
        return form in text
    return re.search(r"(?<!\w)" + re.escape(form) + r"(?!\w)", text, re.IGNORECASE) is not None


def applicable(terms, text):
    """The terms with at least one form occurring in ``text`` (document order of the terms kept)."""
    return [t for t in terms if any(occurs(f, text) for f in [t["source"]] + t["forms"])]
