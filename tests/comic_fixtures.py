"""Synthetic comic pages for the COMIC tests (audit/contracts/comic_translation.md).

``make_page(scale)`` draws a deterministic page with panels, hatched "art", elliptical
speech balloons with tails, a thought balloon, a caption box, a sign lettered directly
on the art and a sound effect, plus an empty art area. It returns the RGB image and the
ground truth for every lettered element. All geometry scales with ``scale`` (1.0 gives
a 1000x1500 page; 2.0 gives 2000x3000).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "scholarly_translation" / "assets" / "fonts"
LATIN_FONT = FONT_DIR / "notosans" / "NotoSans-Regular.ttf"
BALLOON_FILL = (255, 255, 255)
CAPTION_FILL = (250, 236, 170)
INK = (20, 20, 20)


@dataclass
class Truth:
    kind: str
    text: str
    text_bbox: list               # union of the drawn glyph ink, [x0, y0, x1, y1]
    container_bbox: list | None   # outer box of the balloon/caption shape, None for text on art
    shape: str | None             # "ellipse" | "rect" | None
    plain_background: bool
    background: tuple
    line_height: float


@dataclass
class FixturePage:
    image: Image.Image
    truths: list = field(default_factory=list)
    panels: list = field(default_factory=list)
    empty_art: list | None = None  # a hatched area with no lettering

    def truth(self, kind):
        return [t for t in self.truths if t.kind == kind]


def _hatch(draw, box, spacing, color=(120, 120, 120)):
    x0, y0, x1, y1 = box
    for offset in range(-(y1 - y0), x1 - x0, spacing):
        draw.line([(x0 + offset, y1), (x0 + offset + (y1 - y0), y0)], fill=color, width=1)
    # crop overspill outside the box is handled by the caller drawing panels in order


def _text_block(draw, lines, font, center, line_gap):
    """Draw centred lines; return the union of their ink boxes and the line height."""
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + line_gap
    total = line_height * len(lines) - line_gap
    cx, cy = center
    y = cy - total // 2
    ink = None
    for line in lines:
        width = font.getlength(line)
        x = int(round(cx - width / 2))
        draw.text((x, y), line, font=font, fill=INK)
        box = draw.textbbox((x, y), line, font=font)
        ink = list(box) if ink is None else [min(ink[0], box[0]), min(ink[1], box[1]),
                                             max(ink[2], box[2]), max(ink[3], box[3])]
        y += line_height
    return ink, float(ascent + descent)


def make_page(scale: float = 1.0) -> FixturePage:
    s = lambda v: int(round(v * scale))  # noqa: E731
    width, height = s(1000), s(1500)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(LATIN_FONT), s(26))
    big = ImageFont.truetype(str(LATIN_FONT), s(70))
    page = FixturePage(image=image)
    margin, gutter = s(40), s(30)

    panels = [
        [margin, margin, width - margin, s(700)],
        [margin, s(700) + gutter, s(480), height - margin],
        [s(480) + gutter, s(700) + gutter, width - margin, height - margin],
    ]
    page.panels = panels
    for panel in panels:
        # hatched art on the lower half of each panel
        x0, y0, x1, y1 = panel
        art = Image.new("RGB", (x1 - x0, (y1 - y0) // 2), (235, 235, 235))
        _hatch(ImageDraw.Draw(art), [0, 0, art.width, art.height], s(14))
        image.paste(art, (x0, y0 + (y1 - y0) // 2))
        draw.rectangle(panel, outline=INK, width=max(2, s(4)))

    def balloon(box, lines, kind="speech", tail_to=None):
        x0, y0, x1, y1 = box
        if tail_to is not None:
            cx = (x0 + x1) // 2
            draw.polygon([(cx - s(25), y1 - s(10)), (cx + s(25), y1 - s(10)), tail_to], fill=BALLOON_FILL,
                         outline=INK)
        draw.ellipse(box, fill=BALLOON_FILL, outline=INK, width=max(2, s(3)))
        if tail_to is not None:  # hide the tail's base line inside the balloon
            cx = (x0 + x1) // 2
            draw.polygon([(cx - s(22), y1 - s(14)), (cx + s(22), y1 - s(14)), (cx, y1 + s(4))], fill=BALLOON_FILL)
        ink, line_height = _text_block(draw, lines, font, ((x0 + x1) // 2, (y0 + y1) // 2), s(6))
        page.truths.append(Truth(kind, " ".join(lines), ink, list(box), "ellipse", True, BALLOON_FILL,
                                 line_height))

    # Panel 1: two speech balloons with tails, one thought balloon (puffs drawn as circles).
    balloon([s(80), s(80), s(440), s(300)], ["Where were you", "last night?"], tail_to=(s(260), s(420)))
    balloon([s(540), s(150), s(920), s(390)], ["I told you already.", "At the library!"],
            tail_to=(s(700), s(520)))
    for i in range(3):
        r = s(10 + 6 * i)
        cx, cy = s(150 + 40 * i), s(560 - 40 * i)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BALLOON_FILL, outline=INK, width=max(1, s(2)))
    balloon([s(240), s(420), s(520), s(560)], ["Liar..."], kind="thought")

    # Panel 2: caption box at the top (rectangular, coloured) and an empty hatched area.
    cap = [s(60), s(750), s(450), s(860)]
    draw.rectangle(cap, fill=CAPTION_FILL, outline=INK, width=max(2, s(3)))
    ink, line_height = _text_block(draw, ["Meanwhile, across", "the city..."], font,
                                   ((cap[0] + cap[2]) // 2, (cap[1] + cap[3]) // 2), s(6))
    page.truths.append(Truth("narration", "Meanwhile, across the city...", ink, cap, "rect", True, CAPTION_FILL,
                             line_height))
    p2 = panels[1]
    page.empty_art = [p2[0] + s(20), (p2[1] + p2[3]) // 2 + s(40), p2[2] - s(20), p2[3] - s(20)]

    # Panel 3: a sign lettered on the hatched art and a big sound effect on the art.
    p3 = panels[2]
    art_top = (p3[1] + p3[3]) // 2
    ink, line_height = _text_block(draw, ["CLOSED"], font, ((p3[0] + p3[2]) // 2, art_top + s(80)), 0)
    page.truths.append(Truth("sign", "CLOSED", ink, None, None, False, (235, 235, 235), line_height))
    ink, line_height = _text_block(draw, ["BOOM!"], big, ((p3[0] + p3[2]) // 2, art_top + s(250)), 0)
    page.truths.append(Truth("sfx", "BOOM!", ink, None, None, False, (235, 235, 235), line_height))
    return page


def box_iou(a, b):
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def inside_ellipse(box, x, y):
    x0, y0, x1, y1 = box
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    cx, cy = x0 + rx, y0 + ry
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def inside_container(truth, x, y):
    """True when point (x, y) is within the truth's balloon/caption shape."""
    if truth.container_bbox is None:
        return False
    if truth.shape == "ellipse":
        return inside_ellipse(truth.container_bbox, x, y)
    x0, y0, x1, y1 = truth.container_bbox
    return x0 <= x < x1 and y0 <= y < y1
