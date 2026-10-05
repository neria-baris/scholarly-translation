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

from .export_common import (
    _BUNDLED_FONT_ROOT, _PDF_FONTS, ExportError, _resolve_bundled_font, normalize_nfc,
    ordered_render_units, require_translation, validate_translations_mapping,
)
from .segmentation import validate_structure
from .source_reading import StructureError

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

_SYSTEM_FONT_STACK = '"David", "Frank Ruehl", "Times New Roman", "Noto Serif Hebrew", "Arial", serif'

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
p.caption, p.formula, p.scene-break { text-align: center; }
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


def _escape_text(text):
    return "<br>".join(html.escape(line, quote=True) for line in normalize_nfc(text).split("\n"))


def export_html(structure, translations, title, font_id=None) -> bytes:
    """Render a self-contained, RTL Hebrew HTML page as UTF-8 bytes.

    Raises :class:`ExportError` for an invalid structure, a malformed
    translation mapping or an unknown/unavailable explicit ``font_id``.
    """
    try:
        validate_structure(structure)
    except StructureError as exc:
        raise ExportError(f"invalid document structure: {exc}") from None
    if structure.get("schema_version") != 2:
        raise ExportError("HTML export requires a schema-2 document_structure with nodes")
    translations = validate_translations_mapping(translations)
    render_units = ordered_render_units(structure)
    font_faces, family = _font_css(font_id)

    body = []
    title_text = title if isinstance(title, str) and title.strip() else ""
    if title_text:
        body.append(f"<h1>{_escape_text(title_text)}</h1>")
    for render_unit in render_units:
        kind = render_unit["kind"]
        if kind == "page_furniture":
            continue
        try:
            text, _, _ = require_translation(render_unit["unit_id"], translations)
        except ExportError:
            text = render_unit["source_text"]
        if kind == "unsupported" and not text.strip():
            continue
        tag, css_class = _TAG_BY_KIND.get(kind, _DEFAULT_TAG)
        attrs = f' class="{css_class}"' if css_class else ""
        body.append(f"<{tag}{attrs}>{_escape_text(text)}</{tag}>")

    css = font_faces + _BASE_CSS % {"family": family}
    page = (
        "<!DOCTYPE html>\n"
        '<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(normalize_nfc(title_text), quote=True)}</title>\n"
        f"<style>\n{css}</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )
    return page.encode("utf-8")
