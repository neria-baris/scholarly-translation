"""Translated HTML export (LIBRARY-HTML-INSTALLER B1).

Renders the same canonical schema-2 ``document_structure`` and
``unit_id -> translation`` mapping that ``export_pdf.export_pdf`` consumes
into one self-contained UTF-8 HTML5 page: ``<html lang="he" dir="rtl">``,
every text value escaped, no ``<script>``, no external URL or resource.
Unit order, kind handling (page furniture and blank unsupported lines
omitted) and the untranslated-unit fallback to source text mirror the PDF
export exactly. Browsers apply the Unicode bidi algorithm themselves, so no
visual reordering is performed here.

An explicit ``font_id`` must name an available bundled PDF font; its
regular/bold files are embedded as base64 ``@font-face`` data. Unknown or
unavailable fonts raise :class:`ExportError` (never a silent substitution).
``None`` uses a system font stack.
"""
from __future__ import annotations

import base64
import html
import re

from .article_layout import MARK_TOKEN_RE, footnotes
from .export_common import (
    _BUNDLED_FONT_ROOT, _PDF_FONTS, ExportError, _resolve_bundled_font, normalize_nfc,
    display_math, ordered_render_units, require_translation, validate_translations_mapping,
)
from .segmentation import validate_structure
from .source_reading import StructureError
from . import target_languages

# kind -> (tag, css class or None). Headings map to h2..h5 under the h1 title.
_TAG_BY_KIND = {
    "part": ("h2", "part"),
    "chapter": ("h2", None),
    "section": ("h3", None),
    "subsection": ("h4", None),
    "heading": ("h4", None),
    "subheading": ("h5", None),
    "paragraph": ("p", None),
    "quotation": ("blockquote", None),
    "list": ("p", "list"),
    "note": ("p", "note"),
    "caption": ("p", "caption"),
    "formula": ("p", "formula"),
    "bibliography_entry": ("p", "bib"),
    "scene_break": ("p", "scene-break"),
    "unsupported": ("p", "unsupported"),
}
_DEFAULT_TAG = ("p", None)

_SYSTEM_FONT_STACK = ('"David", "Frank Ruehl", "Times New Roman", "Noto Serif Hebrew", "Arial", '
                      '"Cambria Math", "STIX Two Math", "Noto Sans Math", "Segoe UI Symbol", serif')

_BASE_CSS = """
body { font-family: %(family)s; max-width: 46em; margin: 2em auto; padding: 0 1em;
       line-height: 1.6; font-size: 1.1em; color: #1b1b1b; background: #fffdf8; }
h1 { text-align: center; font-size: 1.9em; margin-bottom: 1.2em; }
h2.part { text-align: center; }
h2, h3, h4, h5 { margin: 1.3em 0 .5em; }
p { margin: .35em 0; }
blockquote { margin: .6em 2em .6em 0; }
p.list { margin-right: 1.5em; }
p.note { font-size: .82em; }
section.footnotes { font-size: .82em; }
p.caption, p.formula, p.scene-break { text-align: center; }
p.formula { direction: ltr; unicode-bidi: isolate; }
p.caption { font-size: .82em; }
p.bib { font-size: .92em; }
"""


def _font_css(font_id):
    """Return ``(font-face css, family css value)`` for ``font_id``."""
    if font_id is None:
        return "", _SYSTEM_FONT_STACK
    _resolve_bundled_font(font_id)  # raises ExportError when unknown/unavailable
    _, regular_path, bold_path = _PDF_FONTS[font_id]
    faces = []
    for weight, rel in (("400", regular_path), ("700", bold_path)):
        try:
            data = (_BUNDLED_FONT_ROOT / rel).read_bytes()
        except OSError:
            raise ExportError("selected PDF font is unavailable") from None
        encoded = base64.b64encode(data).decode("ascii")
        faces.append('@font-face { font-family: "st-export-font"; font-weight: %s; font-style: normal; '
                     'src: url(data:font/ttf;base64,%s) format("truetype"); }' % (weight, encoded))
    return "\n".join(faces) + "\n", '"st-export-font", ' + _SYSTEM_FONT_STACK


_HEBREW_RE = re.compile("[֐-׿]")
_LTR_CSS = "p.list { margin-right: 0; margin-left: 1.5em; }\n"


def _escape_text(text):
    return "<br>".join(html.escape(line, quote=True) for line in normalize_nfc(text).split("\n"))


def export_html(structure, translations, title, font_id=None) -> bytes:
    """Render a self-contained HTML page (direction and language of the active target-language
    pack: RTL Hebrew by default) as UTF-8 bytes.

    Raises :class:`ExportError` for an invalid structure, a malformed
    translation mapping or an unknown/unavailable explicit ``font_id``.
    """
    pack = target_languages.current()
    try:
        validate_structure(structure)
    except StructureError as exc:
        raise ExportError(f"invalid document structure: {exc}") from None
    if structure.get("schema_version") != 2:
        raise ExportError("HTML export requires a schema-2 document_structure with nodes")
    translations = validate_translations_mapping(translations)
    render_units = ordered_render_units(structure)
    font_faces, family = _font_css(font_id)

    def text_of(unit_id):
        entry = translations.get(unit_id)
        if entry is not None:
            return entry["text"]
        return next(ru["source_text"] for ru in render_units if ru["unit_id"] == unit_id)
    notes, consumed = footnotes(structure, text_of)
    pages = {u["unit_id"]: u["page_id"] for u in structure["units"]}
    numbers, note_items = {}, []

    def link_marks(escaped, page_id):
        def link(match):
            key = (page_id, match.group(1))
            if key not in notes:
                return f"<sup>{match.group(1)}</sup>"
            if key not in numbers:
                numbers[key] = len(numbers) + 1
                note_items.append((numbers[key], key))
            n = numbers[key]
            return f'<sup id="fnref-{n}"><a href="#fn-{n}">{html.escape(match.group(1))}</a></sup>'
        return MARK_TOKEN_RE.sub(link, escaped)

    body = []
    title_text = title if isinstance(title, str) and title.strip() else ""
    if title_text:
        body.append(f"<h1>{_escape_text(title_text)}</h1>")
    for render_unit in render_units:
        kind = render_unit["kind"]
        if kind == "page_furniture" or render_unit["unit_id"] in consumed:
            continue
        try:
            text, _, _ = require_translation(render_unit["unit_id"], translations)
        except ExportError:
            text = render_unit["source_text"]
        text = display_math(text)
        if kind == "unsupported" and not text.strip():
            continue
        tag, css_class = _TAG_BY_KIND.get(kind, _DEFAULT_TAG)
        attrs = f' class="{css_class}"' if css_class else ""
        original = pack.rtl and not _HEBREW_RE.search(text)
        if original:
            attrs += ' dir="ltr"'          # a reference entry or other text kept in its original
        if (original or not pack.rtl) and kind == "bibliography_entry":
            text = " ".join(text.split())   # the source's line wrapping is not part of the entry
        body.append(f"<{tag}{attrs}>{link_marks(_escape_text(text), pages[render_unit['unit_id']])}</{tag}>")
    if note_items:
        items = "".join(
            f'<li id="fn-{n}" value="{html.escape(key[1]) if key[1].isdigit() else n}">'
            f'{_escape_text(notes[key])} <a href="#fnref-{n}" aria-label="back">↩</a></li>'
            for n, key in note_items)
        body.append(f'<section class="footnotes" role="doc-endnotes"><hr><ol>{items}</ol></section>')

    css = font_faces + _BASE_CSS % {"family": family} + ("" if pack.rtl else _LTR_CSS)
    page = (
        "<!DOCTYPE html>\n"
        f'<html lang="{pack.html_lang}" dir="{pack.direction}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(normalize_nfc(title_text), quote=True)}</title>\n"
        f"<style>\n{css}</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )
    return page.encode("utf-8")
