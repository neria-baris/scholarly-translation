"""COMIC-A local text/balloon detection (audit/contracts/comic_translation.md).

Pure Pillow + stdlib. A grayscale copy (long edge about 1200 px) is binarised into
dark ink and light fill. Glyph-sized dark components are grouped either by the
enclosed light region around them (a balloon/caption: a plain candidate with an
``interior``) or, on art, into row-aligned clusters (not plain). Coordinates are
mapped back to the original image. Candidates are the plain dicts of
``comic_records.validate_candidate``.
"""
from __future__ import annotations

import math
import re
import statistics
from bisect import bisect_right
from collections import Counter

from PIL import Image, ImageChops, ImageFilter

DETECT_VERSION = "comic-detect@1"
WORK_EDGE = 1200          # long edge of the analysis copy
LIGHT = 200               # gray >= LIGHT is fill
MAX_DARK = 110            # gray < min(Otsu, MAX_DARK) is ink
GLYPH_MAX = 0.12          # glyph w/h limit as a share of the long edge
GLYPH_FILL = 0.10         # min ink area / bbox area of a glyph
REGION_SHARE = 0.25       # max share of the page for a balloon/caption
REGION_TEXT_RATIO = 60    # max region area / text bbox area
TAIL_WIDTH = 0.5          # rows narrower than this share of the widest row end the interior
_RUN = re.compile(b"\xff+")


def _otsu(histogram):
    total = sum(histogram)
    weighted = sum(i * c for i, c in enumerate(histogram))
    best, threshold, w0, sum0 = -1.0, 128, 0, 0
    for i, count in enumerate(histogram):
        w0 += count
        if not w0 or w0 == total:
            continue
        sum0 += i * count
        m0, m1 = sum0 / w0, (weighted - sum0) / (total - w0)
        between = w0 * (total - w0) * (m0 - m1) ** 2
        if between > best:
            best, threshold = between, i
    return threshold


def _runs(mask):
    w, h = mask.size
    data = mask.tobytes()
    return [[(m.start(), m.end()) for m in _RUN.finditer(data[y * w:(y + 1) * w])] for y in range(h)]


def _label(rows, eight):
    """Connected components of row runs. Returns (run ids per row, {root: [x0, y0, x1, y1, area]})."""
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    e = 1 if eight else 0
    ids, prev, pids = [], [], []
    for runs in rows:
        cur, j = [], 0
        for a, b in runs:
            lab = len(parent)
            parent.append(lab)
            while j < len(prev) and prev[j][1] + e <= a:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] < b + e:
                ra, rb = find(lab), find(pids[k])
                if ra != rb:
                    parent[rb] = ra
                k += 1
            cur.append(lab)
        ids.append(cur)
        prev, pids = runs, cur
    stats = {}
    for y, (runs, row_ids) in enumerate(zip(rows, ids)):
        for i, (a, b) in enumerate(runs):
            root = find(row_ids[i])
            row_ids[i] = root
            st = stats.get(root)
            if st is None:
                stats[root] = [a, y, b, y + 1, b - a]
            else:
                st[0] = min(st[0], a)
                st[2] = max(st[2], b)
                st[3] = y + 1
                st[4] += b - a
    return ids, stats


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _group_lines(glyphs):
    """Glyph boxes -> lines (lists) by vertical overlap, top to bottom."""
    lines = []  # [y0, y1, members]
    for g in sorted(glyphs, key=lambda g: (g[1] - g[3], g[0], g[1])):  # tall glyphs seed the lines
        height = max(1, g[3] - g[1])
        for line in lines:
            overlap = min(g[3], line[1]) - max(g[1], line[0])
            if overlap >= 0.5 * height or (overlap > 0 and height < 0.5 * (line[1] - line[0])):
                line[0], line[1] = min(line[0], g[1]), max(line[1], g[3])
                line[2].append(g)
                break
        else:
            lines.append([g[1], g[3], [g]])
    return sorted(lines, key=lambda line: line[0] + line[1])


def _main_text(glyphs):
    """Glyphs of the text block: the fullest line plus lines close below/above it.

    Drops stray ink inside a balloon (fragments of a faint tail outline, specks)."""
    lines = _group_lines(glyphs)
    anchor = max(lines, key=lambda line: len(line[2]))
    kept, box = [anchor], _union(anchor[2])
    reach = max(2, anchor[1] - anchor[0])
    changed = True
    while changed:
        changed = False
        for line in lines:
            if line in kept:
                continue
            gap = max(line[0] - box[3], box[1] - line[1])
            members = _union(line[2])
            if gap <= reach and min(members[2], box[2]) > max(members[0], box[0]):
                kept.append(line)
                box = _union([box, members])
                changed = True
    return [g for line in kept for g in line[2]]


class _Analysis:
    def __init__(self, image):
        self.image = image
        self.width, self.height = image.size
        gray = image.convert("L")
        self.gray = gray
        scale = min(1.0, WORK_EDGE / max(self.width, self.height))
        self.w = max(1, round(self.width * scale))
        self.h = max(1, round(self.height * scale))
        small = gray if (self.w, self.h) == gray.size else gray.resize((self.w, self.h), Image.BOX)
        self.sx, self.sy = self.width / self.w, self.height / self.h
        self.dark_threshold = max(20, min(_otsu(small.histogram()), MAX_DARK))
        threshold = self.dark_threshold
        dark = small.point(lambda v: 255 if v < threshold else 0)
        light = small.point(lambda v: 255 if v >= LIGHT else 0).filter(ImageFilter.MinFilter(3))
        self.light_rows = _runs(light)
        self.light_starts = [[r[0] for r in runs] for runs in self.light_rows]
        self.light_ids, self.light_stats = _label(self.light_rows, False)
        _, dark_stats = _label(_runs(dark), True)
        limit = GLYPH_MAX * max(self.w, self.h)
        self.glyphs = []
        for x0, y0, x1, y1, area in dark_stats.values():
            w, h = x1 - x0, y1 - y0
            if area >= 2 and max(w, h) >= 2 and w <= limit and h <= limit and area / (w * h) >= GLYPH_FILL:
                self.glyphs.append((x0, y0, x1, y1))
        self.glyphs.sort(key=lambda g: (g[1], g[0]))

    # -- light regions ----------------------------------------------------------------------
    def light_label(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        i = bisect_right(self.light_starts[y], x) - 1
        if i >= 0 and x < self.light_rows[y][i][1]:
            return self.light_ids[y][i]
        return None

    def glyph_label(self, g):
        """Light region around a glyph (majority of samples on a ring 3 px outside its box)."""
        x0, y0, x1, y1 = g[0] - 3, g[1] - 3, g[2] + 3, g[3] + 3
        votes = Counter()
        for k in range(6):
            x = x0 + (x1 - x0) * k // 5
            y = y0 + (y1 - y0) * k // 5
            for point in ((x, y0), (x, y1), (x0, y), (x1, y)):
                label = self.light_label(*point)
                if label is not None:
                    votes[label] += 1
        return votes.most_common(1)[0][0] if votes else None

    def region_ok(self, label, text=None):
        x0, y0, x1, y1, area = self.light_stats[label]
        if x0 <= 1 or y0 <= 1 or x1 >= self.w - 1 or y1 >= self.h - 1:
            return False  # leaks to the page edge
        if area > REGION_SHARE * self.w * self.h:
            return False
        return text is None or area <= REGION_TEXT_RATIO * max(1, (text[2] - text[0]) * (text[3] - text[1]))

    def row_spans(self, label):
        st = self.light_stats[label]
        spans = {}
        for y in range(st[1], st[3]):
            ids = self.light_ids[y]
            mine = [self.light_rows[y][i] for i in range(len(ids)) if ids[i] == label]
            if mine:
                spans[y] = (mine[0][0], mine[-1][1])
        return spans

    def interior(self, label, text, step):
        """Sampled light spans of the region holding ``text`` (working-copy box); None if they do not."""
        if not self.region_ok(label, text):
            return None
        spans = self.row_spans(label)
        rows = range(text[1], text[3])
        covered = sum(1 for y in rows if y in spans and spans[y][0] <= text[0] + 1 and spans[y][1] >= text[2] - 1)
        if not rows or covered < 0.9 * len(rows):
            return None
        widest = max(b - a for a, b in spans.values())
        lo, hi = text[1], text[3]
        while lo - 1 in spans and spans[lo - 1][1] - spans[lo - 1][0] >= TAIL_WIDTH * widest:
            lo -= 1
        while hi in spans and spans[hi][1] - spans[hi][0] >= TAIL_WIDTH * widest:
            hi += 1
        top = self.orig_box(text)[1]
        y, out = top, []
        while y - step >= math.ceil(lo * self.sy) + 1:
            y -= step
        while y <= math.floor(hi * self.sy) - 1:
            r0 = min(self.h - 1, int(y / self.sy))
            r1 = min(self.h - 1, r0 + 1)
            if r0 in spans and r1 in spans:
                a, b = max(spans[r0][0], spans[r1][0]), min(spans[r0][1], spans[r1][1])
                x0, x1 = math.ceil(a * self.sx) + 1, math.floor(b * self.sx) - 1
                if x1 > x0:
                    out.append([y, x0, x1])
            y += step
        return {"step": step, "rows": out} if out else None

    # -- geometry / colour ------------------------------------------------------------------
    def orig_box(self, box):
        """Working-copy box -> original pixels, tightened to the ink (dark pixels within 2 px)."""
        x0, y0 = max(0, math.floor(box[0] * self.sx)), max(0, math.floor(box[1] * self.sy))
        x1, y1 = min(self.width, math.ceil(box[2] * self.sx)), min(self.height, math.ceil(box[3] * self.sy))
        wide = (max(0, x0 - 2), max(0, y0 - 2), min(self.width, x1 + 2), min(self.height, y1 + 2))
        threshold = self.dark_threshold
        ink = self.gray.crop(wide).point(lambda v: 255 if v < threshold else 0).getbbox()
        if ink:
            x0, y0, x1, y1 = wide[0] + ink[0], wide[1] + ink[1], wide[0] + ink[2], wide[1] + ink[3]
        return [x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)]

    def line_height(self, glyphs):
        lines = _group_lines(glyphs)
        full = [line for line in lines if len(line[2]) >= 2]
        if len(full) >= 2:
            centres = [(line[0] + line[1]) / 2 for line in full]
            pitch = statistics.median(b - a for a, b in zip(centres, centres[1:]))
        else:
            pitch = 1.5 * max(line[1] - line[0] for line in lines)
        return round(max(1.0, pitch * self.sy), 1)

    def _median_colour(self, points):
        pixels = self.rgb.load()
        samples = [pixels[x, y] for x, y in points if 0 <= x < self.width and 0 <= y < self.height]
        samples = [p for p in samples if (p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000 >= 60]
        if not samples:
            return [255, 255, 255]
        return [int(statistics.median(p[c] for p in samples)) for c in range(3)]

    @property
    def rgb(self):
        if not hasattr(self, "_rgb"):
            self._rgb = self.image.convert("RGB")
        return self._rgb

    def fill_colour(self, interior):
        rows = interior["rows"]
        points = []
        for y, x0, x1 in rows[:: max(1, len(rows) // 30)]:
            stride = max(2, (x1 - x0) // 80)
            points.extend((x, y) for x in range(x0, x1, stride))
        return self._median_colour(points)

    def ring_colour(self, box):
        pad = max(3, (box[3] - box[1]) // 4)
        points = []
        for d in (pad, 2 * pad):
            x0, y0, x1, y1 = box[0] - d, box[1] - d, box[2] + d, box[3] + d
            stride = max(2, (x1 - x0) // 80)
            for x in range(x0, x1, stride):
                points += [(x, y0), (x, y1)]
            for y in range(y0, y1, stride):
                points += [(x0, y), (x1, y)]
        return self._median_colour(points)

    def flat(self, box):
        """True when the pixels of ``box`` look like a flat fill (almost no horizontal edges)."""
        crop = self.gray.crop(tuple(box))
        if crop.width < 2:
            return False
        edges = ImageChops.difference(crop.crop((1, 0, crop.width, crop.height)),
                                      crop.crop((0, 0, crop.width - 1, crop.height)))
        histogram = edges.histogram()
        return sum(histogram[25:]) / max(1, sum(histogram)) < 0.03


def _candidate(an, glyphs, interior, background, confidence):
    return {"bbox": an.orig_box(_union(glyphs)), "interior": interior, "background": background,
            "plain_background": interior is not None, "line_height": an.line_height(glyphs),
            "confidence": confidence}


def _step(an, glyphs):
    return max(2, round(an.line_height(glyphs) / 6))


def _row_clusters(glyphs):
    """Unassigned glyphs -> clusters of row-aligned glyphs (>= 3 in a row), for lettering on art."""
    parent = list(range(len(glyphs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(glyphs):
        for j in range(i + 1, len(glyphs)):
            b = glyphs[j]
            ha, hb = a[3] - a[1], b[3] - b[1]
            gap = max(a[0], b[0]) - min(a[2], b[2])
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            if gap <= max(ha, hb) and overlap >= 0.5 * min(ha, hb) and max(ha, hb) <= 4 * min(ha, hb) + 4:
                parent[find(j)] = find(i)
    groups = {}
    for i, g in enumerate(glyphs):
        groups.setdefault(find(i), []).append(g)
    lines = [m for m in groups.values() if sum(1 for g in m if g[3] - g[1] >= 5) >= 3]
    # stack lines of one block (close vertically, overlapping horizontally)
    merged = []
    for line in sorted(lines, key=lambda m: min(g[1] for g in m)):
        box = _union(line)
        height = statistics.median(g[3] - g[1] for g in line)
        for block in merged:
            bb = _union(block)
            if box[1] - bb[3] <= height and min(box[2], bb[2]) > max(box[0], bb[0]):
                block.extend(line)
                break
        else:
            merged.append(list(line))
    return merged


def detect_candidates(image):
    """Text candidates of a page image, top to bottom then left to right."""
    an = _Analysis(image)
    by_label, unassigned = {}, []
    for g in an.glyphs:
        label = an.glyph_label(g)
        if label is None or not an.region_ok(label):
            unassigned.append(g)
        else:
            by_label.setdefault(label, []).append(g)
    found = []
    for label, glyphs in by_label.items():
        glyphs = _main_text(glyphs)
        interior = an.interior(label, _union(glyphs), _step(an, glyphs))
        if interior is None:
            unassigned.extend(by_label[label])
            continue
        found.append(_candidate(an, glyphs, interior, an.fill_colour(interior),
                                0.95 if len(glyphs) >= 3 else 0.8))
    for cluster in _row_clusters(sorted(unassigned, key=lambda g: (g[1], g[0]))):
        box = an.orig_box(_union(cluster))
        found.append(_candidate(an, cluster, None, an.ring_colour(box), 0.6))
    found.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))
    return found


def snap_region(image, bbox):
    """Candidate for a model-supplied (possibly loose) box: ink bbox plus the bounded light region."""
    an = _Analysis(image)
    x0, y0 = min(max(0, int(bbox[0])), an.width - 1), min(max(0, int(bbox[1])), an.height - 1)
    x1, y1 = min(max(x0 + 1, int(bbox[2])), an.width), min(max(y0 + 1, int(bbox[3])), an.height)
    inside = [g for g in an.glyphs
              if x0 <= (g[0] + g[2]) / 2 * an.sx < x1 and y0 <= (g[1] + g[3]) / 2 * an.sy < y1]
    if not inside:
        box = [x0, y0, x1, y1]
        flat = an.flat(box)
        return {"bbox": box, "interior": None, "background": an.ring_colour(box), "plain_background": flat,
                "line_height": float(max(1, (y1 - y0) // 2)), "confidence": 0.2}
    votes = Counter(label for label in (an.glyph_label(g) for g in inside) if label is not None)
    inside = _main_text(inside)
    interior = None
    if votes:
        interior = an.interior(votes.most_common(1)[0][0], _union(inside), _step(an, inside))
    if interior is not None:
        return _candidate(an, inside, interior, an.fill_colour(interior), 0.9)
    return _candidate(an, inside, None, an.ring_colour(an.orig_box(_union(inside))), 0.5)
