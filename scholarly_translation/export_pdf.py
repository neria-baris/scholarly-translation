"""Translated PDF export (Session X).

Reconstructs a reflowed, Hebrew-RTL-correct PDF from the canonical
``document_structure`` (schema 2: ``nodes``/``units``/``unit_node_links``,
see ``scholarly_translation/STRUCTURE_SCHEMA.md``) plus a caller-supplied
``unit_id -> translation`` mapping. Operates only on structure already
produced by ``segmentation.build_structure``/``document_structure.py`` --
never re-derives chapter/heading hierarchy from raw text itself.

Pixel-identical reproduction of the source PDF is explicitly out of scope
(see audit/contracts/session_x_export.md); this module reflows translated
text into a fresh, readable, multi-page document using a standard page
size, preserving node kind/level hierarchy as visual style (title >
heading > body > note) and recording any structural element it cannot
faithfully represent (e.g. an image it cannot embed, or a node kind with
no renderable mapping) in an explicit ``limitations`` list rather than
dropping or mis-rendering it silently.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .export_common import (
    ExportError, display_math, font_runs, ordered_render_units, reorder_bidi_line, require_translation,
    resolve_hebrew_font, validate_translations_mapping, wrap_logical_lines,
)
from .segmentation import validate_structure
from .source_reading import StructureError

MARGIN = 54.0  # 0.75 inch
PAGE_SIZE = A4
LINE_LEADING = 1.28

_STYLE_BY_KIND = {
    "part":                {"size": 22, "bold": True,  "before": 26, "after": 10, "align": "center"},
    "chapter":              {"size": 19, "bold": True,  "before": 22, "after": 9,  "align": "right"},
    "section":              {"size": 16, "bold": True,  "before": 18, "after": 8,  "align": "right"},
    "subsection":           {"size": 14, "bold": True,  "before": 14, "after": 6,  "align": "right"},
    "heading":              {"size": 13, "bold": True,  "before": 12, "after": 6,  "align": "right"},
    "subheading":           {"size": 12, "bold": True,  "before": 10, "after": 5,  "align": "right"},
    "paragraph":            {"size": 11, "bold": False, "before": 4,  "after": 4,  "align": "right"},
    "quotation":            {"size": 11, "bold": False, "before": 6,  "after": 6,  "align": "right", "indent": 28},
    "list":                 {"size": 11, "bold": False, "before": 2,  "after": 2,  "align": "right", "indent": 18},
    "note":                 {"size": 9,  "bold": False, "before": 3,  "after": 3,  "align": "right"},
    "caption":              {"size": 9,  "bold": False, "before": 4,  "after": 4,  "align": "center"},
    "formula":              {"size": 11, "bold": False, "before": 8,  "after": 8,  "align": "center"},
    "bibliography_entry":   {"size": 10, "bold": False, "before": 2,  "after": 2,  "align": "right"},
    "scene_break":          {"size": 11, "bold": False, "before": 10, "after": 10, "align": "center"},
    "unsupported":          {"size": 10, "bold": False, "before": 4,  "after": 4,  "align": "right"},
}
_DEFAULT_STYLE = {"size": 11, "bold": False, "before": 4, "after": 4, "align": "right"}

_TITLE_STYLE = {"size": 24, "bold": True, "before": 0, "after": 20, "align": "center"}


@dataclass
class PdfExportResult:
    content: bytes
    manifest: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    page_count: int = 0
    font_id: str | None = None


class _PdfWriter:
    def __init__(self, font_name, bold_font_name):
        self.buf = io.BytesIO()
        self.canvas = rl_canvas.Canvas(self.buf, pagesize=PAGE_SIZE)
        self.font_name = font_name
        self.bold_font_name = bold_font_name
        self.page_width, self.page_height = PAGE_SIZE
        self.right_x = self.page_width - MARGIN
        self.left_x = MARGIN
        self.max_width = self.page_width - 2 * MARGIN
        self.y = self.page_height - MARGIN
        self.page_count = 1

    def _new_page(self):
        self.canvas.showPage()
        self.page_count += 1
        self.y = self.page_height - MARGIN

    def _ensure_room(self, needed_height):
        if self.y - needed_height < MARGIN:
            self._new_page()

    def draw_text_block(self, kind, text, style=None):
        style = style or _STYLE_BY_KIND.get(kind, _DEFAULT_STYLE)
        font = self.bold_font_name if style.get("bold") else self.font_name
        size = style["size"]
        indent = style.get("indent", 0)
        max_width = self.max_width - indent
        logical_lines = wrap_logical_lines(text, font, size, max_width) or [""]
        line_height = size * LINE_LEADING
        needed = style.get("before", 0) + len(logical_lines) * line_height + style.get("after", 0)
        # A block longer than a page necessarily splits. Start its first lines
        # in the current page's remaining room instead of abandoning that room
        # merely because the whole block cannot fit. Short blocks retain their
        # existing keep-together behaviour.
        if needed > self.page_height - 2 * MARGIN:
            needed = style.get("before", 0) + min(2, len(logical_lines)) * line_height
        self._ensure_room(needed)
        self.y -= style.get("before", 0)
        self.canvas.setFont(font, size)
        for logical_line in logical_lines:
            if self.y - line_height < MARGIN:
                self._new_page()
                self.canvas.setFont(font, size)
            visual_line = reorder_bidi_line(logical_line)
            self._draw_line(visual_line, font, size, style.get("align", "right"), indent)
            self.y -= line_height
        self.y -= style.get("after", 0)

    def _draw_line(self, visual_line, font, size, align, indent):
        """Draw one visual-order line, switching to a glyph-fallback font for
        characters the Hebrew font lacks (math symbols, Greek, super/subscripts)."""
        runs = font_runs(visual_line, font)
        width = sum(pdfmetrics.stringWidth(part, name, size) for name, part in runs)
        if align == "center":
            x = (self.left_x + self.right_x) / 2 - width / 2
        elif align == "left":
            x = self.left_x
        else:
            x = self.right_x - indent - width
        for name, part in runs:
            self.canvas.setFont(name, size)
            self.canvas.drawString(x, self.y, part)
            x += pdfmetrics.stringWidth(part, name, size)
        self.canvas.setFont(font, size)

    def draw_image(self, image_bytes, caption_width_ratio=0.8):
        reader = ImageReader(io.BytesIO(image_bytes))
        iw, ih = reader.getSize()
        max_w = self.max_width * caption_width_ratio
        max_h = self.page_height - 2 * MARGIN
        scale = min(max_w / iw, max_h / ih, 1.0)
        w, h = iw * scale, ih * scale
        self._ensure_room(h + 10)
        x = (self.left_x + self.right_x) / 2 - w / 2
        self.canvas.drawImage(reader, x, self.y - h, width=w, height=h, mask="auto")
        self.y -= h + 10

    def finish(self) -> bytes:
        self.canvas.showPage()
        self.canvas.save()
        return self.buf.getvalue()


def export_pdf(structure, translations, *, images=None, title=None, font_id=None) -> PdfExportResult:
    """Render a translated, reflowed, RTL-correct Hebrew PDF.

    ``structure`` must be a schema-2 ``document_structure`` dict (as
    produced by ``segmentation.build_structure``). ``translations`` maps
    ``unit_id -> {"text": ..., "approved": bool, "status": ...}``; a unit
    with no entry falls back to rendering its original source text and
    records a ``missing_translation`` limitation (never silently dropped,
    never a crash). ``images`` optionally maps a node_id (typically of a
    ``caption`` node) to raw PNG/JPEG bytes to embed near that caption --
    the canonical node schema carries no image payload of its own, so this
    is an explicit, additive side channel documented in the delivery
    report, not a change to ``document_structure.py``.

    Raises :class:`ExportError` (never a raw internal traceback) for an
    invalid structure, malformed translation mapping or unknown/unavailable
    explicit font_id. Font selection changes rendering only; callers can
    rerender stored translation records without invoking translation models.
    None preserves the legacy host-font selection behaviour.
    """
    try:
        validate_structure(structure)
    except StructureError as exc:
        raise ExportError(f"invalid document structure: {exc}") from None
    if structure.get("schema_version") != 2:
        raise ExportError("PDF export requires a schema-2 document_structure with nodes")

    translations = validate_translations_mapping(translations)
    images = images or {}

    render_units = ordered_render_units(structure)
    font_name, bold_font_name, font_limitation = resolve_hebrew_font(font_id)
    limitations = []
    if font_id == "david-clm":
        limitations.append({"kind": "font_license_notice", "font_id": font_id,
                             "detail": "David CLM is GPL-2.0 with Bitstream notices; "
                                       "no document embedding exception was identified in the upstream license.",
                             "source": "https://sources.debian.org/src/culmus/0.140-3/LICENSE"})
    if font_limitation:
        limitations.append({"kind": font_limitation, "detail":
                             "no Hebrew-capable TTF font found on this host; "
                             "falling back to a built-in font with no Hebrew glyphs"})
    if any(ru["kind"] == "note" for ru in render_units):
        limitations.append({"kind": "footnotes_rendered_inline", "detail":
                             "notes/footnotes are rendered inline near their source "
                             "position, not pinned to the original page bottom"})

    writer = _PdfWriter(font_name, bold_font_name)
    if title:
        writer.draw_text_block("title", title, style=_TITLE_STYLE)

    manifest = []
    for render_unit in render_units:
        kind = render_unit["kind"]
        unit_id, node_ids = render_unit["unit_id"], render_unit["node_ids"]

        if kind == "page_furniture":
            manifest.append({"unit_id": unit_id, "node_ids": node_ids, "kind": kind,
                              "rendered": False, "reason": "page_furniture_omitted"})
            continue

        try:
            text, approved, status = require_translation(unit_id, translations)
            fell_back = False
        except ExportError:
            text = render_unit["source_text"]
            approved, status, fell_back = False, "missing_translation", True
            limitations.append({"kind": "missing_translation", "unit_id": unit_id,
                                 "node_ids": node_ids,
                                 "detail": "no translation supplied; rendered original source text"})
        text = display_math(text)

        if kind == "unsupported" and not text.strip():
            manifest.append({"unit_id": unit_id, "node_ids": node_ids, "kind": kind,
                              "rendered": False, "reason": "blank_unsupported_line_omitted"})
            continue

        image_note = None
        if kind == "caption":
            image_bytes = next((images[nid] for nid in node_ids if nid in images), None)
            if image_bytes is not None:
                try:
                    writer.draw_image(image_bytes)
                except Exception:
                    image_note = "image_not_embedded"
                    limitations.append({"kind": "image_not_embedded", "unit_id": unit_id,
                                         "node_ids": node_ids,
                                         "detail": "supplied image bytes could not be decoded/embedded; "
                                                   "caption text rendered without its figure"})

        writer.draw_text_block(kind, text)
        manifest.append({
            "unit_id": unit_id, "node_ids": node_ids, "kind": kind,
            "rendered": True, "approved": approved, "status": status,
            "fell_back_to_source": fell_back,
            **({"image_limitation": image_note} if image_note else {}),
        })

    content = writer.finish()
    return PdfExportResult(content=content, manifest=manifest, limitations=limitations,
                            page_count=writer.page_count, font_id=font_id)
