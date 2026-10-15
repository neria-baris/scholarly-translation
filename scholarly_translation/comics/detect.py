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

DETECT_VERSION = "comic-detect@7"
WORK_EDGE = 1200          # long edge of the analysis copy
LIGHT = 200               # gray >= LIGHT is fill
MAX_DARK = 110            # gray < min(Otsu, MAX_DARK) is ink
GLYPH_MAX = 0.12          # glyph w/h limit as a share of the long edge
GLYPH_FILL = 0.10         # min ink area / bbox area of a glyph
REGION_SHARE = 0.25       # max share of the page for a balloon/caption
REGION_TEXT_RATIO = 60    # max region area / text bbox area
TAIL_WIDTH = 0.5          # rows narrower than this share of the widest row end the interior
ART_CLUSTER_SHARE = 0.03  # a "lettering on art" cluster larger than this share of the page is hatching
SNAP_MARGIN = 0.012       # crop margin around a model box, share of the page's long edge
SNAP_DARK = (60, 200)     # full-resolution ink threshold limits (Otsu of the crop between them)
RING_LIGHT = 0.6          # share of light pixels in a thin ring around the lettering for a plain background
RING_BALLOON = 0.35       # lower share still taken as a balloon with a busy or jagged edge (ink-only erase)
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
        if (box[2] - box[0]) * (box[3] - box[1]) > ART_CLUSTER_SHARE * an.width * an.height:
            continue  # dense hatching, not lettering; missed lettering is added by the model
        found.append(_candidate(an, cluster, None, an.ring_colour(box), 0.6))
    found.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))
    return found


def _pitch(glyphs):
    """Median distance between lettering lines (1.5x the line height for a single line)."""
    lines = _group_lines(glyphs)
    full = [line for line in lines if len(line[2]) >= 2]
    if len(full) >= 2:
        centres = [(line[0] + line[1]) / 2 for line in full]
        return float(statistics.median(b - a for a, b in zip(centres, centres[1:])))
    return 1.5 * max(line[1] - line[0] for line in lines)


def _lettering(dark, box):
    """``(core, grow)``: glyph components of the lettering block in ``box`` (crop
    coordinates) and a function returning the block grown to neighbouring glyphs the box cut
    off (used on plain backgrounds only). Components touching the crop edge (balloon
    outlines, panel borders, long hatching) are never lettering."""
    cw, ch = dark.size
    _, stats = _label(_runs(dark), True)
    parts = [tuple(st[:4]) for st in stats.values()
             if st[0] > 0 and st[1] > 0 and st[2] < cw and st[3] < ch and st[4] >= 3]
    inside = [g for g in parts if box[0] <= (g[0] + g[2]) / 2 < box[2] and box[1] <= (g[1] + g[3]) / 2 < box[3]]
    if not inside:
        return [], None
    height = statistics.median(g[3] - g[1] for g in inside)
    inside = [g for g in inside if g[3] - g[1] <= 3 * height + 2]
    if not inside:
        return [], None
    core = _main_text(inside)
    # growth stays near the given box sideways (the model's split between neighbouring balloons
    # wins) but may follow stacked lines a model box cut off at its top or bottom
    near, stacked = 0.75 * height, 2.5 * height
    reachable = [g for g in parts if box[0] - near <= (g[0] + g[2]) / 2 < box[2] + near
                 and box[1] - stacked <= (g[1] + g[3]) / 2 < box[3] + stacked]
    return core, (lambda: _grow(core, reachable, height))


def _grow(core, parts, height):
    kept = set(core)
    others = [g for g in parts if g not in kept and g[3] - g[1] <= 2.5 * height + 2]
    reach = 0.6 * height + 1
    grown = True
    while grown:
        grown = False
        block = _union(list(kept))
        for g in others:
            if g in kept:
                continue
            gap = max(block[0] - g[2], g[0] - block[2], block[1] - g[3], g[1] - block[3])
            if gap <= reach:
                kept.add(g)
                grown = True
    return sorted(kept, key=lambda g: (g[1], g[0]))


def _letter_pitch(glyphs):
    """Line pitch from the letters themselves: 1.5x the median height of the letter-sized
    components (accents and specks, under 40% of the tallest, left out). Independent of how
    the lines are spaced or whether they touch."""
    heights = [g[3] - g[1] for g in glyphs]
    tallest = max(heights)
    letters = [h for h in heights if h >= 0.4 * tallest]
    pitch = 1.5 * statistics.median(letters)
    # Lower-case prose: letter height is the x-height and underestimates the pitch. With at
    # least three clear lines the measured line distance is used when it stays plausible.
    lines = [line for line in _group_lines(glyphs) if len(line[2]) >= 3]
    if len(lines) >= 3:
        measured = _pitch(glyphs)
        if pitch < measured <= 2.2 * pitch:
            return measured
    return pitch


def _words(glyphs, offset):
    """Word boxes (page coordinates) of the lettering: glyphs joined when they overlap
    vertically by half their height and are less than ~0.6 letter heights apart. Follows
    slanted and L-shaped lettering far more closely than one bounding box."""
    import statistics
    if not glyphs:
        return []
    height = statistics.median(g[3] - g[1] for g in glyphs)
    parent = list(range(len(glyphs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(glyphs):
        for j in range(i + 1, len(glyphs)):
            b = glyphs[j]
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            gap = max(a[0], b[0]) - min(a[2], b[2])
            centres = abs((a[1] + a[3]) - (b[1] + b[3])) / 2
            if (overlap >= 0.5 * min(a[3] - a[1], b[3] - b[1], height) and gap <= 0.6 * height
                    and centres <= 0.45 * height):          # same line, also when slanted
                parent[find(j)] = find(i)
    groups = {}
    for i, g in enumerate(glyphs):
        groups.setdefault(find(i), []).append(g)
    return [[min(g[0] for g in m) + offset[0], min(g[1] for g in m) + offset[1],
             max(g[2] for g in m) + offset[0], max(g[3] for g in m) + offset[1]] for m in groups.values()]


def _letter_words(words, line_height):
    """Words of letter height only: chains of outline strokes (a jagged balloon edge) are far
    taller than a line, specks of hatching far smaller."""
    kept = [w for w in words if 0.3 * line_height <= w[3] - w[1] <= 2.2 * line_height]
    return kept or words


def _light_runs(row_bytes):
    return [(m.start(), m.end()) for m in _RUN.finditer(row_bytes)]


def _free_space(gray, bbox, line_height, light_level, letters=None):
    """Interior rows: per sampled row, the light run around the lettering, inside a window
    around it. Rows above/below the lettering count while their run still spans at least half
    its width (the balloon outline ends it); no closed outline is needed."""
    width, height = gray.size
    bw = bbox[2] - bbox[0]
    mh, mv = int(round(max(0.3 * bw, 1.5 * line_height))), int(round(line_height))
    window = (max(0, bbox[0] - mh), max(0, bbox[1] - mv), min(width, bbox[2] + mh), min(height, bbox[3] + mv))
    light = gray.crop(window).point(lambda v: 255 if v >= light_level else 0)
    # the lettering itself counts as free space: its word boxes, not its bounding box (slanted
    # lettering's bounding box can reach over art, e.g. a TV drawn beside the words)
    grow = int(round(0.6 * line_height)) if letters else 0     # closes the gaps between words
    for b in letters or [bbox]:
        light.paste(255, (max(0, max(bbox[0], b[0] - grow) - window[0]), max(0, max(bbox[1], b[1] - grow) - window[1]),
                          max(0, min(bbox[2], b[2] + grow) - window[0]), max(0, min(bbox[3], b[3] + grow) - window[1])))
    data, ww = light.tobytes(), light.width
    step = max(2, int(round(line_height / 6)))
    lx0, lx1 = bbox[0] - window[0], bbox[2] - window[0]

    def span(y):
        runs = _light_runs(data[(y - window[1]) * ww:(y - window[1] + 1) * ww])
        best = max(runs, key=lambda r: min(r[1], lx1) - max(r[0], lx0), default=None)
        if best is None or min(best[1], lx1) - max(best[0], lx0) < (lx1 - lx0) / 2:
            return None
        a, b = best
        a, b = (a + 2 if a > 0 else a), (b - 2 if b < ww else b)
        return [y, window[0] + a, window[0] + b] if b > a else None

    first = bbox[1] - ((bbox[1] - window[1]) // step) * step
    ys = list(range(first, window[3], step))
    inner = [i for i, y in enumerate(ys) if bbox[1] <= y < bbox[3]]
    if not inner:
        inner = [min(range(len(ys)), key=lambda i: abs(ys[i] - bbox[1]))]
    rows = {ys[i]: span(ys[i]) for i in inner}
    sampled = set(ys)
    # walk outwards one pixel row at a time so a thin outline between samples ends the interior
    for direction, limit in ((-1, window[1] - 1), (1, window[3])):
        y = (ys[inner[0]] if direction < 0 else ys[inner[-1]]) + direction
        while y != limit:
            row = span(y)
            if row is None:
                break
            if y in sampled:
                rows[y] = row
            y += direction
    out = [rows[y] for y in sorted(rows) if rows[y] is not None]
    return {"step": step, "rows": out} if out else None


def _shaped(interior, lines, line_height):
    """Interior rows narrowed to the SHAPE of the original lettering: each sampled row keeps
    the free span only within the nearest lettering line's extent (plus a margin), and rows
    more than half a line above or below the lettering are dropped. The letterer already fit
    the text to the balloon (oval, diamond, tail), so the translation follows that shape and
    never reaches an open outline. ``lines``: [(y0, y1, x0, x1)] in page coordinates."""
    margin = max(4, int(round(0.8 * line_height)))
    reach = 0.8 * line_height
    top, bottom = lines[0][0], lines[-1][1]
    rows = []
    for y, a, b in interior["rows"]:
        if y < top - reach or y > bottom + reach:
            continue
        def dist(line):
            return 0 if line[0] <= y < line[1] else min(abs(y - line[0]), abs(y - line[1]))
        best = min(dist(line) for line in lines)
        # every line about as near (a row between two lines) counts, not just the first found
        near = [line for line in lines if dist(line) <= best + 0.5 * line_height]
        a, b = max(a, min(line[2] for line in near) - margin), min(b, max(line[3] for line in near) + margin)
        if b > a:
            rows.append([y, a, b])
    return {"step": interior["step"], "rows": rows} if rows else None


def snap_region(image, bbox):
    """Candidate for a model-supplied lettering box (possibly loose or a little off): the
    bbox is tightened to the lettering's glyphs, the background is plain when the ring around
    the lettering is mostly light, and a plain region's interior is the free light space
    around the lettering (balloon outlines need not be closed)."""
    gray = image.convert("L")
    width, height = gray.size
    x0, y0 = min(max(0, int(bbox[0])), width - 1), min(max(0, int(bbox[1])), height - 1)
    x1, y1 = min(max(x0 + 1, int(bbox[2])), width), min(max(y0 + 1, int(bbox[3])), height)
    margin = max(4, int(round(SNAP_MARGIN * max(width, height))))
    crop_box = (max(0, x0 - margin), max(0, y0 - margin), min(width, x1 + margin), min(height, y1 + margin))
    crop = gray.crop(crop_box)
    threshold = max(SNAP_DARK[0], min(_otsu(crop.histogram()), SNAP_DARK[1]))
    dark = crop.point(lambda v: 255 if v < threshold else 0)
    glyphs, grow = _lettering(dark, (x0 - crop_box[0], y0 - crop_box[1], x1 - crop_box[0], y1 - crop_box[1]))
    rgb = image.convert("RGB")
    if not glyphs:
        box = [x0, y0, x1, y1]
        ring = _ring(gray, rgb, box, max(3, (y1 - y0) // 4))
        return {"bbox": box, "interior": None, "background": ring["colour"],
                "plain_background": _flat(gray, box), "line_height": float(max(1, (y1 - y0) // 2)),
                "confidence": 0.2}
    def placed(parts):
        box = _union(parts)
        return [box[0] + crop_box[0], box[1] + crop_box[1], box[2] + crop_box[0], box[3] + crop_box[1]]
    tight = placed(glyphs)
    line_height = round(max(1.0, _letter_pitch(glyphs)), 1)
    ring = _ring(gray, rgb, tight, max(2, int(round(0.2 * line_height))))
    if ring["light_share"] >= RING_BALLOON:
        grown = grow()
        tight = placed(grown)
        line_height = round(max(1.0, _letter_pitch(grown)), 1)
        level = int((threshold + sum(ring["light_colour"]) / 3) / 2)
        words = _letter_words(_words(grown, crop_box), line_height)
        interior = _free_space(gray, tight, line_height, level, words)
        balloon = interior          # the whole free light area: what is erased, and room for overflow
        if interior is not None:
            lines = [(line[0] + crop_box[1], line[1] + crop_box[1], min(g[0] for g in line[2]) + crop_box[0],
                      max(g[2] for g in line[2]) + crop_box[0]) for line in _group_lines(grown)]
            interior = _shaped(interior, lines, line_height)
        if interior is not None:
            return {"bbox": tight, "interior": interior, "background": ring["light_colour"],
                    "plain_background": True, "line_height": line_height, "confidence": 0.9,
                    "balloon": balloon, "words": words}
    return {"bbox": tight, "interior": None, "background": ring["colour"], "plain_background": False,
            "line_height": line_height, "confidence": 0.6}


def _ring(gray, rgb, box, band):
    """Pixels in a band around ``box``: median colour, median light colour, light share."""
    width, height = gray.size
    outer = (max(0, box[0] - band), max(0, box[1] - band), min(width, box[2] + band), min(height, box[3] + band))
    stride = max(1, (outer[2] - outer[0]) // 120)
    g, c = gray.load(), rgb.load()
    samples = [(x, y) for y in range(outer[1], outer[3], stride) for x in range(outer[0], outer[2], stride)
               if not (box[0] <= x < box[2] and box[1] <= y < box[3])]
    if not samples:
        return {"colour": [255, 255, 255], "light_colour": [255, 255, 255], "light_share": 0.0}
    light = [p for p in samples if g[p] >= LIGHT]

    def median(points):
        if not points:
            return [255, 255, 255]
        return [int(statistics.median(c[p][k] for p in points)) for k in range(3)]
    return {"colour": median(samples), "light_colour": median(light), "light_share": len(light) / len(samples)}


def _flat(gray, box):
    crop = gray.crop(tuple(box))
    if crop.width < 2:
        return False
    edges = ImageChops.difference(crop.crop((1, 0, crop.width, crop.height)),
                                  crop.crop((0, 0, crop.width - 1, crop.height)))
    histogram = edges.histogram()
    return sum(histogram[25:]) / max(1, sum(histogram)) < 0.03
