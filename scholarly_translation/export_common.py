"""Shared helpers for the Session X format-preserving export path
(``export_pdf.py`` / ``export_epub.py``): a specific failure exception,
translation-mapping validation, document-order unit resolution over the
canonical ``document_structure`` (schema 2), and a deliberately small,
documented Hebrew/RTL bidi reordering routine used because this
environment has no ``rlbidi`` package installed (reportlab's own
``wordWrap='RTL'`` support silently falls back to no reordering without
it -- see module docstring on :func:`reorder_bidi_line`).

Never decides translation, terminology or scholarly meaning. Never builds
a second independent interpretation of PDF chapters/headings -- callers
must supply a ``document_structure`` already produced by
``segmentation.build_structure``.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from pathlib import Path

_HEBREW_RANGE_RE = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")

_MIRROR_PAIRS = {
    "(": ")", ")": "(",
    "[": "]", "]": "[",
    "{": "}", "}": "{",
    "<": ">", ">": "<",
    "\u00ab": "\u00bb", "\u00bb": "\u00ab",  # « »
}


class ExportError(Exception):
    """Raised for any export-time failure (invalid structure, missing or
    malformed translation mapping, unreadable source archive, etc).
    Messages are user-facing and never embed a raw internal traceback."""


def validate_translations_mapping(translations) -> dict:
    """Validate the caller-supplied ``unit_id -> translation`` mapping.

    Each entry must be a dict with a nonempty string ``text``. ``approved``
    (bool) and ``status`` (str) are optional per-unit provenance/approval
    state, carried through to the export manifest unchanged; any other
    keys (e.g. provider/model provenance) are preserved as-is but not
    otherwise interpreted here -- this module never decides translation
    quality or approval policy.
    """
    if not isinstance(translations, dict):
        raise ExportError("translations must be a mapping of unit_id to translation records")
    validated = {}
    for unit_id, record in translations.items():
        if not isinstance(unit_id, str) or not unit_id:
            raise ExportError("translation mapping keys must be nonempty unit_id strings")
        if not isinstance(record, dict) or not isinstance(record.get("text"), str) or not record["text"].strip():
            raise ExportError(f"translation for unit {unit_id!r} must be a dict with nonempty 'text'")
        entry = dict(record)
        entry.setdefault("approved", False)
        entry.setdefault("status", "unreviewed")
        validated[unit_id] = entry
    return validated


def require_translation(unit_id: str, translations: dict):
    """Return ``(text, approved, status)`` for ``unit_id`` or raise
    :class:`ExportError` with a clear, specific message."""
    record = translations.get(unit_id)
    if record is None:
        raise ExportError(f"no translation supplied for unit {unit_id!r}")
    return record["text"], bool(record.get("approved", False)), record.get("status", "unreviewed")


def ordered_render_units(structure: dict) -> list:
    """Resolve schema-2 ``units`` into document-ordered render blocks.

    Each returned dict has ``unit_id``, ``node_ids`` (ordered), ``kind``
    (the shared kind of its linked node(s) -- always a single kind because
    STRUCTURE_SCHEMA.md guarantees that a unit spanning more than one node
    is always a run of plain ``paragraph`` nodes), ``level``, ``order``
    (the minimum order of its linked nodes, for document-order sorting)
    and ``source_text`` (the unit's own source text, used as a last-resort
    fallback when no translation is supplied for it).
    """
    nodes_by_id = {n["node_id"]: n for n in structure.get("nodes", [])}
    links_by_unit = {link["unit_id"]: link["node_ids"] for link in structure.get("unit_node_links", [])}
    render_units = []
    for unit in structure.get("units", []):
        node_ids = links_by_unit.get(unit["unit_id"], [])
        linked = [nodes_by_id[nid] for nid in node_ids if nid in nodes_by_id]
        if not linked:
            raise ExportError(f"unit {unit['unit_id']!r} has no linked structural node")
        kinds = {n["kind"] for n in linked}
        if len(kinds) != 1:
            raise ExportError(f"unit {unit['unit_id']!r} links nodes of mixed kinds {sorted(kinds)!r}")
        render_units.append({
            "unit_id": unit["unit_id"],
            "node_ids": node_ids,
            "kind": next(iter(kinds)),
            "level": linked[0]["level"],
            "order": min(n["order"] for n in linked),
            "source_text": unit["text"],
        })
    render_units.sort(key=lambda r: r["order"])
    return render_units


# ---------------------------------------------------------------------------
# Hebrew RTL rendering
# ---------------------------------------------------------------------------

_HEBREW_FONT_CANDIDATES = [
    # Windows
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/david.ttf"),
    Path("C:/Windows/Fonts/tahoma.ttf"),
    # Linux (DejaVu covers the Hebrew block)
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    # macOS
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]

_BOLD_CANDIDATES = {
    "arial": Path("C:/Windows/Fonts/arialbd.ttf"),
    "david": Path("C:/Windows/Fonts/davidbd.ttf"),
    "tahoma": Path("C:/Windows/Fonts/tahomabd.ttf"),
}

_font_cache = {}
_font_lock = threading.RLock()
_BUNDLED_FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"
_PDF_FONTS = {
    "david-libre": ("David Libre", "davidlibre/DavidLibre-Regular.ttf", "davidlibre/DavidLibre-Bold.ttf"),
    "hadasim-clm": ("Hadasim CLM", "culmus/HadasimCLM-Regular.ttf", "culmus/HadasimCLM-Bold.ttf"),
    "noto-serif-hebrew": ("Noto Serif Hebrew", "notoserifhebrew/NotoSerifHebrew-Regular.ttf", "notoserifhebrew/NotoSerifHebrew-Bold.ttf"),
    "frank-ruhl-libre": ("Frank Ruhl Libre", "frankruhllibre/FrankRuhlLibre-Regular.ttf", "frankruhllibre/FrankRuhlLibre-Bold.ttf"),
    "david-clm": ("David CLM", "culmus/DavidCLMPDF-Regular.ttf", "culmus/DavidCLMPDF-Bold.ttf"),
}


def list_pdf_fonts() -> list[dict]:
    """Return the closed set of bundled choices, without local filesystem paths.

    Availability checks registration and Hebrew/Latin coverage locally. A
    damaged/missing font is unavailable; selecting it subsequently fails rather
    than substituting another face. No download or provider call is performed.
    """
    fonts = []
    for font_id, (name, _, _) in _PDF_FONTS.items():
        try:
            _resolve_bundled_font(font_id)
            available = True
        except ExportError:
            available = False
        license_id = ("GPL-2.0 with font embedding exception" if font_id == "hadasim-clm"
                      else "GPL-2.0; Bitstream notices" if font_id == "david-clm"
                      else "OFL-1.1")
        fonts.append({"id": font_id, "name": name, "available": available,
                      "license": license_id,
                      "license_url": ("https://sources.debian.org/src/culmus/0.140-3/LICENSE"
                                      if font_id.endswith("clm") else "https://openfontlicense.org/"),
                      "embedding_note": ("David CLM upstream license has no identified document embedding exception."
                                         if font_id == "david-clm" else None)})
    return fonts


def _resolve_bundled_font(font_id):
    if not isinstance(font_id, str) or font_id not in _PDF_FONTS:
        raise ExportError("unknown PDF font selection")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _, regular_path, bold_path = _PDF_FONTS[font_id]
    paths = [_BUNDLED_FONT_ROOT / regular_path, _BUNDLED_FONT_ROOT / bold_path]
    # Check before the registration cache: a removed deployment asset must not
    # be reported available merely because a previous request registered it.
    if any(not path.is_file() for path in paths):
        raise ExportError("selected PDF font is unavailable")
    names = [f"export-bundled-{font_id}-regular", f"export-bundled-{font_id}-bold"]
    with _font_lock:
        if font_id in _font_cache:
            return _font_cache[font_id]
        try:
            for name, path in zip(names, paths):
                font = TTFont(name, str(path))
                required = set(range(32, 127)) | set(range(0x05D0, 0x05EB))
                if not required.issubset(font.face.charToGlyph):
                    raise ValueError("font has insufficient Hebrew/Latin coverage")
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(font)
        except Exception:
            raise ExportError("selected PDF font could not be loaded") from None
        result = (names[0], names[1], None)
        _font_cache[font_id] = result
        return result


# Glyph fallback for characters the Hebrew fonts lack (math operators, Greek,
# super/subscripts): Noto Sans Math first, then Noto Sans. SIL OFL 1.1, bundled.
_FALLBACK_FONTS = (
    ("export-fallback-noto-sans-math", "notosansmath/NotoSansMath-Regular.ttf"),
    ("export-fallback-noto-sans", "notosans/NotoSans-Regular.ttf"),
)


def fallback_fonts() -> list:
    """Register (once) and return the available glyph-fallback font names, in order."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _font_lock:
        if "fallback" in _font_cache:
            return _font_cache["fallback"]
        names = []
        for name, relative in _FALLBACK_FONTS:
            path = _BUNDLED_FONT_ROOT / relative
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    if not path.is_file():
                        continue
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                names.append(name)
            except Exception:
                continue
        _font_cache["fallback"] = names
        return names


def _glyph_map(font_name):
    from reportlab.pdfbase import pdfmetrics
    face = getattr(pdfmetrics.getFont(font_name), "face", None)
    return getattr(face, "charToGlyph", None)


def font_runs(text: str, font_name: str, fallbacks=None) -> list:
    """Split ``text`` into ``[(font, substring)]`` runs: each character uses
    ``font_name`` when it has the glyph, else the first fallback that has it,
    else ``font_name`` (spaces always stay in the current run)."""
    primary = _glyph_map(font_name)
    if primary is None:   # built-in Type 1 font: no cmap to consult
        return [(font_name, text)] if text else []
    chain = [(name, _glyph_map(name)) for name in (fallback_fonts() if fallbacks is None else fallbacks)]
    runs = []
    for ch in text:
        if ch.isspace() and runs:
            chosen = runs[-1][0]
        elif ord(ch) in primary or ch.isspace():
            chosen = font_name
        else:
            chosen = next((name for name, cmap in chain if cmap is not None and ord(ch) in cmap), font_name)
        if runs and runs[-1][0] == chosen:
            runs[-1][1].append(ch)
        else:
            runs.append((chosen, [ch]))
    return [(name, "".join(chars)) for name, chars in runs]


def mixed_string_width(text: str, font_name: str, font_size: float) -> float:
    from reportlab.pdfbase import pdfmetrics
    return sum(pdfmetrics.stringWidth(part, name, font_size) for name, part in font_runs(text, font_name))


def resolve_hebrew_font(font_id=None):
    """Register and return ``(regular_font_name, bold_font_name, limitation)``.

    An explicit font_id selects only its bundled, licensed regular/bold pair.
    Unknown or unavailable explicit selections raise ExportError. With no
    selection, preserve the legacy short list of host font locations for a
    Hebrew-capable TTF. Returns ``Helvetica``/``Helvetica-Bold``
    (no Hebrew glyphs) plus a non-``None`` limitation string when no such
    font is found on the host, so callers can record it rather than fail.
    """
    if font_id is not None:
        return _resolve_bundled_font(font_id)
    if "resolved" in _font_cache:
        return _font_cache["resolved"]
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for candidate in _HEBREW_FONT_CANDIDATES:
        if not candidate.is_file():
            continue
        font_name = f"export-hebrew-{candidate.stem}"
        try:
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, str(candidate)))
        except Exception:
            continue
        bold_name = font_name
        bold_path = _BOLD_CANDIDATES.get(candidate.stem.lower())
        if bold_path and bold_path.is_file():
            candidate_bold_name = f"export-hebrew-{bold_path.stem}"
            try:
                if candidate_bold_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(candidate_bold_name, str(bold_path)))
                bold_name = candidate_bold_name
            except Exception:
                pass
        result = (font_name, bold_name, None)
        _font_cache["resolved"] = result
        return result
    result = ("Helvetica", "Helvetica-Bold", "no_hebrew_capable_font_found_on_host")
    _font_cache["resolved"] = result
    return result


def _is_hebrew_token(token: str) -> bool:
    return bool(_HEBREW_RANGE_RE.search(token))


_SUPERSCRIPT_RUN_RE = re.compile("([⁰¹²³⁴-⁹]+)")


def _reverse_hebrew_token(token: str) -> str:
    """Reverse one Hebrew token for drawing, mirroring brackets; a run of superscript digits
    (a footnote mark glued to the word) keeps its own left-to-right digit order."""
    parts = _SUPERSCRIPT_RUN_RE.split(token)
    return "".join(part if _SUPERSCRIPT_RUN_RE.fullmatch(part) else
                   "".join(_MIRROR_PAIRS.get(ch, ch) for ch in reversed(part))
                   for part in reversed(parts))


def reorder_bidi_line(text: str) -> str:
    """Return a left-to-right-drawable "visual order" rendering of one
    line of mixed Hebrew/Latin/digit text, assuming an overall
    right-to-left (Hebrew) paragraph base direction.

    This is a deliberately small, word-token-granularity simplification of
    the Unicode Bidirectional Algorithm (UAX #9), not a full implementation:
    rather than resolving bidi at the character-run level (which requires
    careful neutral-character attribution to avoid swallowing inter-word
    spaces at run boundaries), each whitespace-delimited token is classified
    as a whole -- Hebrew if it contains any Hebrew-block character,
    otherwise left-to-right (covers Latin words, citations, numbers and
    punctuation-only tokens such as list markers). Consecutive tokens that
    share a classification are grouped into one run first (so a multi-word
    left-to-right island such as a Latin citation keeps its own internal
    word order), and then runs -- not individual tokens -- are emitted in
    reverse order (so the first-read run ends up rightmost once drawn
    left-to-right). Within a Hebrew run, both the token order and each
    token's characters are reversed, and any paired bracket/quote character
    is swapped with its mirror partner (the standard behaviour for mirrored
    glyphs in an RTL run); a left-to-right run (including embedded numbers)
    is left internally untouched, so numbers and numbered-list markers such
    as ``"1."`` are never broken, reversed or reordered internally. Pure
    left-to-right text (no Hebrew token at all) is returned unchanged.

    Known limitation: a single token that mixes Hebrew and non-Hebrew
    characters with no intervening space (e.g. ``"COVID19"`` immediately
    glued to a Hebrew word) is classified as one Hebrew token and reversed
    as a whole, which is not a fully correct embedded-number treatment for
    that rare case. Reflects the smallest-robust-exporter scope of this
    session, not full UAX #9 compliance.
    """
    if not text:
        return text
    lines = normalize_nfc(text).split("\n")
    return "\n".join(_reorder_bidi_single_line(line) for line in lines)


def _reorder_bidi_single_line(line: str) -> str:
    tokens = line.split(" ")
    if not any(_is_hebrew_token(t) for t in tokens):
        return line  # no Hebrew at all: pure left-to-right, nothing to reorder

    # Group consecutive same-direction tokens into runs first, so that a
    # multi-token left-to-right island (e.g. a two-word Latin citation
    # "(Smith, 2020)") keeps its own internal token order even though the
    # run as a whole moves to a different position among the surrounding
    # Hebrew runs. Reversing every token individually (without this
    # run-grouping step) would also swap such an island's tokens relative
    # to *each other*, which is wrong.
    runs = []  # list of [is_hebrew, [tokens]]
    for token in tokens:
        is_hebrew = _is_hebrew_token(token)
        if runs and runs[-1][0] == is_hebrew:
            runs[-1][1].append(token)
        else:
            runs.append([is_hebrew, [token]])

    visual_runs = []
    for is_hebrew, run_tokens in reversed(runs):
        if is_hebrew:
            processed = [_reverse_hebrew_token(tok) for tok in reversed(run_tokens)]
        else:
            processed = run_tokens
        visual_runs.append(" ".join(processed))
    return " ".join(visual_runs)


def wrap_logical_lines(text: str, font_name: str, font_size: float, max_width: float) -> list:
    """Greedily word-wrap ``text`` (in its original, logical reading order)
    to fit ``max_width`` at ``font_name``/``font_size``, preserving explicit
    ``\\n`` as hard breaks. Wrapping is direction-neutral (it only measures
    pixel widths of whitespace-delimited words in reading order); apply
    :func:`reorder_bidi_line` to each returned line before drawing it.
    """
    from reportlab.pdfbase import pdfmetrics

    out_lines = []
    for hard_line in text.split("\n"):
        words = hard_line.split()
        if not words:
            out_lines.append("")
            continue
        current = []
        for word in words:
            candidate = " ".join(current + [word])
            width = mixed_string_width(candidate, font_name, font_size)
            if current and width > max_width:
                out_lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            out_lines.append(" ".join(current))
    return out_lines


def display_math(text: str) -> str:
    """Show protected EPUB formula tokens as their readable form: drop the
    MATH_OPEN/MATH_CLOSE markers (U+27E6/U+27E7) used to carry them through translation."""
    return (text or "").replace("⟦", "").replace("⟧", "")


def normalize_nfc(text: str) -> str:
    """Normalize to NFC so precomposed/decomposed Hebrew niqqud or presentation
    variants measure and draw consistently."""
    return unicodedata.normalize("NFC", text or "")
