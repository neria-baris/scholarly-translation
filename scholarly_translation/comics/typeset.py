"""COMIC-B: typeset translated text into comic regions and render the page
(audit/contracts/comic_translation.md).

``fit`` lays a translation out inside one region (``bubble`` in a plain
interior, ``box`` on art, ``subtitle`` for sound effects); ``render_page`` erases
the source lettering and draws the layouts onto a copy of the page. RTL lines are
wrapped on the logical text and drawn through ``reorder_bidi_line`` (visual order).
Pure Pillow + stdlib, deterministic, no model calls.
"""
from __future__ import annotations

import bisect
import functools
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..core import target_languages
from ..export.common import reorder_bidi_line

TYPESET_VERSION = "comic-typeset@3"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
HEBREW_FONT = FONT_DIR / "culmus" / "HadasimCLM-Bold.ttf"
LATIN_FONT = FONT_DIR / "notosans" / "NotoSans-Regular.ttf"
DARK, LIGHT = (20, 20, 20), (255, 255, 255)
ERASE_GROW = 3


def font_for(target_code) -> Path:
    return HEBREW_FONT if target_languages.load(target_code).rtl else LATIN_FONT


def min_font_px(page_height) -> int:
    return max(10, int(round(0.011 * page_height)))


@functools.lru_cache(maxsize=256)
def _font(path, size):
    return ImageFont.truetype(str(path), int(size))


def _line_height(font):
    ascent, descent = font.getmetrics()
    return ascent + descent


_GLYPH_FALLBACKS = {"…": "..."}   # the Hebrew font has no ellipsis glyph


def _visual(text, rtl):
    for char, plain in _GLYPH_FALLBACKS.items():
        text = text.replace(char, plain)
    return reorder_bidi_line(text, rtl_paragraph=True) if rtl else text


def _width(font, text, rtl):
    return font.getlength(_visual(text, rtl))


def _max_size(region, page_height, font_path):
    """Largest size whose line pitch stays within about 1.05x the source line pitch
    (detection reports ``line_height`` as the distance between lettering lines)."""
    ratio = _line_height(_font(font_path, 100)) / 100
    return max(min_font_px(page_height), int(1.05 * float(region["line_height"]) / ratio))


# ---------------------------------------------------------------- areas

class _Area:
    """Where text may go: interior spans per sampled row, or a plain rectangle."""

    def __init__(self, region):
        interior, bbox = region.get("interior"), region["bbox"]
        self.interior = interior
        if interior:
            self.step = interior["step"]
            self.ys = [r[0] for r in interior["rows"]]
            self.rows = interior["rows"]
            self.top, self.bottom = self.ys[0], self.ys[-1]
            self.cy = (self.top + self.bottom) / 2
        else:
            w, lh = bbox[2] - bbox[0], float(region["line_height"])
            ex, ey = int(0.1 * w) + 4, max(3, int(0.3 * lh))
            self.rect = (max(0, bbox[0] - ex), max(0, bbox[1] - ey), bbox[2] + ex, bbox[3] + ey)
            self.top, self.bottom = self.rect[1], self.rect[3]
            self.cy = (self.top + self.bottom) / 2

    def span(self, y0, y1, strict=True):
        """Common x-span of all rows covering [y0, y1); None when outside the area."""
        if not self.interior:
            if strict and (y0 < self.top or y1 > self.bottom):
                return None
            return self.rect[0], self.rect[2]
        if strict and (y0 < self.top or y1 > self.bottom):
            return None
        lo = max(0, bisect.bisect_right(self.ys, y0) - 1)
        hi = min(len(self.ys) - 1, bisect.bisect_left(self.ys, y1))
        rows = self.rows[lo:hi + 1]
        x0, x1 = max(r[1] for r in rows), min(r[2] for r in rows)
        return (x0, x1) if x1 > x0 else None


def _avail(span):
    if span is None:
        return None
    pad = max(2, int(0.08 * (span[1] - span[0])))
    width = span[1] - span[0] - 2 * pad
    return width if width > 0 else None


# ---------------------------------------------------------------- wrapping

def _wrap(text, font, rtl, avail, split=True):
    """Greedy word wrap on logical text; ``avail(i)`` is line i's width or None (fail)."""
    lines = []

    def limit():
        return avail(len(lines))

    for paragraph in text.split("\n"):
        words = paragraph.split()
        current = ""
        if not words:
            if not current and paragraph == "" and lines:
                pass
            continue
        for word in words:
            while True:
                lim = limit()
                if lim is None:
                    return None
                trial = word if not current else current + " " + word
                if _width(font, trial, rtl) <= lim:
                    current = trial
                    break
                if current:
                    lines.append(current)
                    current = ""
                    continue
                # the word alone does not fit: split by characters (only where allowed)
                if not split:
                    return None
                cut = len(word)
                while cut > 1 and _width(font, word[:cut], rtl) > lim:
                    cut -= 1
                if _width(font, word[:cut], rtl) > lim:
                    return None
                lines.append(word[:cut])
                word = word[cut:]
                if not word:
                    break
            if not word:
                continue
        if current:
            lines.append(current)
    return lines


def _make_lines(texts, font, rtl, tops, xcs):
    out = []
    for text, y, xc in zip(texts, tops, xcs):
        width = int(math.ceil(_width(font, text, rtl)))
        out.append({"text": text, "x": int(round(xc - width / 2)), "y": int(y), "width": width})
    return out


def _bounds(lines, lh, grow=0):
    return [min(l["x"] for l in lines) - grow, min(l["y"] for l in lines) - grow,
            max(l["x"] + l["width"] for l in lines) + grow, max(l["y"] for l in lines) + lh + grow]


def _layout(style, size, lh, lines, box, overflow, font_path, rtl):
    try:
        name = str(Path(font_path).resolve().relative_to(FONT_DIR.resolve())).replace("\\", "/")
    except ValueError:
        name = str(font_path)
    return {"style": style, "font_size": int(size), "line_height": int(lh), "lines": lines,
            "box": [int(v) for v in box], "overflow": bool(overflow), "font": name, "rtl": bool(rtl)}


# ---------------------------------------------------------------- styles

def _try_block(area, text, font, rtl, lh, cy, strict=True):
    """Wrap into n lines centred on cy; first n whose wrap gives exactly n lines."""
    nmax = max(1, int((area.bottom - area.top) / lh) + 1)
    for n in range(1, nmax + 1):
        top = int(round(cy - n * lh / 2))
        spans = {}

        def avail(i, top=top, spans=spans):
            span = area.span(top + i * lh, top + (i + 1) * lh, strict)
            spans[i] = span
            return _avail(span)

        lines = _wrap(text, font, rtl, avail, split=False)   # a balloon never breaks a word
        if lines is not None and len(lines) == n:
            xcs = [(spans[i][0] + spans[i][1]) / 2 for i in range(n)]
            return _make_lines(lines, font, rtl, [top + i * lh for i in range(n)], xcs)
    return None


def _fit_bubble(region, text, font_path, rtl, page_height):
    area = _Area(region)
    lo, hi = min_font_px(page_height), _max_size(region, page_height, font_path)
    src_cy = (region["bbox"][1] + region["bbox"][3]) / 2
    for size in range(hi, lo - 1, -1):
        font = _font(font_path, size)
        lh = _line_height(font)
        for cy in (src_cy, area.cy):
            lines = _try_block(area, text, font, rtl, lh, cy)
            if lines:
                return _layout("bubble", size, lh, lines, _bounds(lines, lh), False, font_path, rtl)
    # nothing fits: minimum size, centred in the area, overflow reported
    font = _font(font_path, lo)
    lh = _line_height(font)
    n = 1
    for _ in range(8):
        top = int(round(area.cy - n * lh / 2))
        spans = {}

        def avail(i, top=top, spans=spans):
            span = area.span(top + i * lh, top + (i + 1) * lh, False)
            spans[i] = span
            # never narrower than the lettering block itself, so words are not broken
            return max(_avail(span) or 0, region["bbox"][2] - region["bbox"][0], lo)

        lines = _wrap(text, font, rtl, avail, split=False) or _wrap(text, font, rtl, avail) or []
        if len(lines) == n or not lines:
            break
        n = len(lines)
    lines = lines or [text]
    n = len(lines)
    top = int(round(area.cy - n * lh / 2))
    xcs = []
    for i in range(n):
        span = area.span(top + i * lh, top + (i + 1) * lh, False)
        xcs.append((span[0] + span[1]) / 2 if span else (region["bbox"][0] + region["bbox"][2]) / 2)
    lines = _make_lines(lines, font, rtl, [top + i * lh for i in range(n)], xcs)
    return _layout("bubble", lo, lh, lines, _bounds(lines, lh), True, font_path, rtl)


def _fit_box(region, text, font_path, rtl, page_height, page_width):
    bbox = region["bbox"]
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    lo, hi = min_font_px(page_height), _max_size(region, page_height, font_path)
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    right = page_width if page_width else bbox[2] + int(0.5 * bw) + 20
    width_cap = max(int(bw * 1.4), 8 * lo)
    height_cap = max(int(bh * 1.8), 3 * lo)
    result = None
    for size in range(hi, lo - 1, -1):
        font = _font(font_path, size)
        lh = _line_height(font)
        pad = max(3, int(0.35 * size))
        width = min(width_cap, int(2 * min(cx, right - cx)) - 2 * pad)
        lines = _wrap(text, font, rtl, lambda i: width if width > 0 else None)
        if lines and len(lines) * lh <= height_cap:
            result = (size, font, lh, lines, pad, False)
            break
    if result is None:
        font = _font(font_path, lo)
        lh = _line_height(font)
        width = max(lo, min(width_cap, int(2 * min(cx, right - cx)) - 2 * lo))
        lines = _wrap(text, font, rtl, lambda i: width) or [text]
        result = (lo, font, lh, lines, max(3, int(0.35 * lo)), True)
    size, font, lh, lines, pad, overflow = result
    n = len(lines)
    top = int(round(cy - n * lh / 2))
    top = max(pad, min(top, page_height - pad - n * lh)) if page_height > n * lh + 2 * pad else top
    placed = _make_lines(lines, font, rtl, [top + i * lh for i in range(n)], [cx] * n)
    shift = 0
    left_edge = min(l["x"] for l in placed) - pad
    right_edge = max(l["x"] + l["width"] for l in placed) + pad
    if left_edge < 0:
        shift = -left_edge
    elif page_width and right_edge > page_width:
        shift = page_width - right_edge
    for l in placed:
        l["x"] += shift
    text_box = _bounds(placed, lh, pad)
    if region.get("confidence", 1.0) < 0.3:
        box = list(text_box)        # no lettering was found in a model box: never stretch over it
    else:
        box = [min(text_box[0], bbox[0] - pad), min(text_box[1], bbox[1] - pad),
               max(text_box[2], bbox[2] + pad), max(text_box[3], bbox[3] + pad)]
    box = [max(0, box[0]), max(0, box[1]), min(page_width, box[2]) if page_width else box[2],
           min(page_height, box[3])]
    return _layout("box", size, lh, placed, box, overflow, font_path, rtl)


def _fit_subtitle(region, text, font_path, rtl, page_height, page_width):
    bbox = region["bbox"]
    size = int(round(min_font_px(page_height) * 1.3))
    font = _font(font_path, size)
    lh = _line_height(font)
    stroke = max(1, size // 8)
    cx = (bbox[0] + bbox[2]) / 2
    width = max(int((bbox[2] - bbox[0]) * 1.2), 10 * size)
    if page_width:
        width = min(width, page_width - 2 * stroke - 2)
    lines = _wrap(text, font, rtl, lambda i: width) or [text]
    n = len(lines)
    block = n * lh
    gap = max(4, lh // 3) + stroke  # clear of the source lettering's descenders
    top = bbox[3] + gap
    if top + block + stroke > page_height:
        top = bbox[1] - gap - block
    top = max(stroke, min(top, page_height - stroke - block))
    placed = _make_lines(lines, font, rtl, [top + i * lh for i in range(n)], [cx] * n)
    left = min(l["x"] for l in placed) - stroke
    shift = -left if left < 0 else 0
    if page_width:
        over = max(l["x"] + l["width"] for l in placed) + stroke + shift - page_width
        shift -= max(0, over)
    for l in placed:
        l["x"] += shift
    layout = _layout("subtitle", size, lh, placed, _bounds(placed, lh, stroke), block + 2 * stroke > page_height,
                     font_path, rtl)
    layout["stroke_width"] = stroke
    return layout


def fit(region, text, font_path, rtl, page_height, page_width=None) -> dict:
    """Layout of ``text`` in ``region`` (contract COMIC-B). ``page_width`` is optional and,
    when given, keeps box/subtitle layouts inside the page horizontally."""
    if region.get("kind") == "sfx":
        return _fit_subtitle(region, text, font_path, rtl, page_height, page_width)
    if region.get("plain_background"):
        return _fit_bubble(region, text, font_path, rtl, page_height)
    return _fit_box(region, text, font_path, rtl, page_height, page_width)


def capacity(region, font_path, rtl, page_height) -> int:
    """Approximate characters that fit at a comfortable size (a length hint for the prompt)."""
    lo = min_font_px(page_height)
    size = max(lo, int(round(_max_size(region, page_height, font_path) * 0.85)))
    font = _font(font_path, size)
    sample = "שלום לכולם אנחנו הולכים" if rtl else "the quick brown fox jumps"
    char_w = font.getlength(sample) / len(sample)
    lh = _line_height(font)
    interior = region.get("interior")
    if interior:
        area = sum(interior["step"] * max(0, r[2] - r[1]) for r in interior["rows"]) * 0.84
    else:
        bbox = region["bbox"]
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) * 1.2
    return max(1, int(0.75 * area / (char_w * lh)))


# ---------------------------------------------------------------- rendering

def _luminance(color):
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


def _erase_ink(image, region):
    """Erase only the lettering's ink: dark components inside the lettering box (grown a few
    pixels) that do not touch its edge are painted with the background, slightly dilated for
    anti-aliasing. Balloon outlines, tails and art cross the edge and stay untouched, so the
    balloon keeps its exact shape; no rectangle is ever filled."""
    from .detect import _label, _otsu, _runs
    width, height = image.size
    x0, y0, x1, y1 = region["bbox"]
    box = (max(0, x0 - ERASE_GROW), max(0, y0 - ERASE_GROW), min(width, x1 + ERASE_GROW),
           min(height, y1 + ERASE_GROW))
    crop = image.crop(box).convert("L")
    background = _luminance(region["background"])
    threshold = min(_otsu(crop.histogram()), int(background) - 30)
    dark = crop.point(lambda v: 255 if v < threshold else 0)
    rows = _runs(dark)
    ids, stats = _label(rows, True)
    cw, ch = crop.size
    inner = {root for root, st in stats.items() if st[0] > 0 and st[1] > 0 and st[2] < cw and st[3] < ch}
    if not inner:
        return
    mask = Image.new("L", crop.size, 0)
    draw = ImageDraw.Draw(mask)
    for y, (runs, row_ids) in enumerate(zip(rows, ids)):
        for (a, b), root in zip(runs, row_ids):
            if root in inner:
                draw.line([(a, y), (b - 1, y)], fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(5))
    image.paste(tuple(region["background"]), box, mask)


def _erase_balloon(image, region):
    """Erase ALL lettering inside the balloon's free light area, whether or not it was part of
    the lettering box or got a translation: every dark component that lies wholly inside the
    area (and does not touch the crop edge) is painted with the background. Outlines, tails and
    art reach outside the area and stay."""
    from .detect import _label, _otsu, _runs
    area = region.get("balloon")
    if not area:
        _erase_ink(image, region)
        return
    width, height = image.size
    rows, step = area["rows"], area["step"]
    box = (max(0, min(r[1] for r in rows) - 2), max(0, rows[0][0] - step), min(width, max(r[2] for r in rows) + 2),
           min(height, rows[-1][0] + step + 1))
    inside = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
    mark = ImageDraw.Draw(inside)
    for i, (y, a, b) in enumerate(rows):
        y_end = rows[i + 1][0] if i + 1 < len(rows) else y + step
        mark.rectangle([a - box[0], y - box[1], b - 1 - box[0], y_end - 1 - box[1]], fill=255)
    inside_px = inside.load()
    crop = image.crop(box).convert("L")
    background = _luminance(region["background"])
    threshold = min(_otsu(crop.histogram()), int(background) - 30)
    dark = crop.point(lambda v: 255 if v < threshold else 0)
    runs = _runs(dark)
    ids, stats = _label(runs, True)
    cw, ch = crop.size
    outside = set()
    for y, (row, row_ids) in enumerate(zip(runs, ids)):
        for (a, b), root in zip(row, row_ids):
            if not inside_px[a, y] or not inside_px[b - 1, y]:
                outside.add(root)
    keep = {root for root, st in stats.items() if st[0] == 0 or st[1] == 0 or st[2] >= cw or st[3] >= ch}
    erase = set(stats) - outside - keep
    if not erase:
        return
    mask = Image.new("L", crop.size, 0)
    draw = ImageDraw.Draw(mask)
    for y, (row, row_ids) in enumerate(zip(runs, ids)):
        for (a, b), root in zip(row, row_ids):
            if root in erase:
                draw.line([(a, y), (b - 1, y)], fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(5))
    image.paste(tuple(region["background"]), box, mask)


def _erase_bubble(draw, region, size):
    width, height = size
    x0, y0, x1, y1 = region["bbox"]
    x0, y0, x1, y1 = max(0, x0 - ERASE_GROW), max(0, y0 - ERASE_GROW), min(width, x1 + ERASE_GROW), \
        min(height, y1 + ERASE_GROW)
    colour = tuple(region["background"])
    if not region.get("interior"):
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=colour)
        return
    area = _Area(region)
    for y in range(y0, y1):
        span = area.span(y, y + 1, strict=False)
        if span is None:
            continue
        a, b = max(x0, span[0]), min(x1, span[1])
        if b > a:
            draw.line([(a, y), (b - 1, y)], fill=colour)


def render_page(image, regions) -> Image.Image:
    """Erase the source lettering and draw the translations on a copy of ``image``."""
    out = image.convert("RGB").copy() if image.mode != "RGB" else image.copy()
    draw = ImageDraw.Draw(out)
    placed = [r for r in regions if r.get("translation") and r.get("layout")
              and r["translation"].get("status") != "skipped"]
    # Erase first, independent of the translation: every balloon's lettering goes, also where no
    # translation could be placed, so no original text is left behind or cut into new text.
    for region in regions:
        if region.get("kind") in ("sfx", "sign") or not region.get("plain_background"):
            continue
        _erase_balloon(out, region)
    for region in placed:
        layout, colour = region["layout"], tuple(region["background"])
        if layout["style"] == "box" and not region.get("edited"):
            draw.rounded_rectangle(layout["box"], radius=max(3, layout["font_size"] // 2), fill=colour)
    for region in placed:
        if region.get("edited"):
            continue                 # an image model already lettered it into the art
        layout, colour = region["layout"], tuple(region["background"])
        style, rtl = layout["style"], layout.get("rtl", False)
        font = _font(FONT_DIR / layout["font"], layout["font_size"])
        for line in layout["lines"]:
            text = _visual(line["text"], rtl)
            if style == "subtitle":
                draw.text((line["x"], line["y"]), text, font=font, fill=DARK,
                          stroke_width=layout.get("stroke_width", 1), stroke_fill=LIGHT)
            else:
                draw.text((line["x"], line["y"]), text, font=font,
                          fill=LIGHT if _luminance(colour) < 100 else DARK)
    return out
