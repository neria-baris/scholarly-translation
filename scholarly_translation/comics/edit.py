"""COMIC sign editing (audit/contracts/comic_sign_edit.md).

Lettering that is part of the artwork (kind ``sign``: shop signs, banners, screens, often at an
angle) is not covered by a pasted box: an image model re-letters it in place. One masked edit
per sign on a crop of the OUTPUT page (already mirrored, so the new text reads correctly); only
the masked lettering area is pasted back. Results are cached by request hash under
``<out>/.state/edits/`` and never requested twice; observed usage and a list-price estimate are
appended to ``edits.jsonl``; a separate ceiling stops further edits (the region then keeps the
ordinary backing patch).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

EDIT_MODEL = "gpt-image-2"
EDIT_VERSION = "comic-sign-edit@1"
# USD per 1,000,000 tokens for gpt-image-2 as used by the cover feature (third-party listing
# 2026-10-09; a labelled list-price estimate, not a billing record).
RATES_PER_MILLION = {"text_input": 5.0, "image_input": 8.0, "image_output": 30.0}
EDIT_TIMEOUT_SECONDS = 300.0
_SIZES = {"square": (1024, 1024), "landscape": (1536, 1024), "portrait": (1024, 1536)}


class SignEditError(RuntimeError):
    """A sign could not be edited (the caller falls back to a backing patch)."""


def _shape(width, height):
    ratio = width / height
    return "landscape" if ratio > 1.25 else "portrait" if ratio < 0.8 else "square"


def edit_request(image, region, text, language_name="Hebrew", rtl=True):
    """``(crop_box, image_png, mask_png, prompt, size)`` for one sign region of the output page."""
    width, height = image.size
    x0, y0, x1, y1 = region["bbox"]
    bw, bh = x1 - x0, y1 - y0
    margin = max(64, max(bw, bh) // 2)
    box = (max(0, x0 - margin), max(0, y0 - margin), min(width, x1 + margin), min(height, y1 + margin))
    crop = image.crop(box).convert("RGB")
    size = _SIZES[_shape(*crop.size)]
    sx, sy = size[0] / crop.width, size[1] / crop.height
    model_image = crop.resize(size, Image.LANCZOS)
    pad = max(4, int(0.15 * min(bw, bh)))
    hole = [round((x0 - pad - box[0]) * sx), round((y0 - pad - box[1]) * sy),
            round((x1 + pad - box[0]) * sx), round((y1 + pad - box[1]) * sy)]
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    ImageDraw.Draw(mask).rectangle(hole, fill=(0, 0, 0, 0))     # transparent = may be changed
    direction = "right-to-left" if rtl else "left-to-right"
    prompt = (
        "This is a detail of a black-and-white comic page. Inside the transparent area of the mask there is "
        "lettering that is part of the drawing (a sign, banner, label or screen); it may appear mirrored. "
        "Replace ONLY that lettering with this %s text: «%s». Write it %s, spelled exactly as given, "
        "in a hand-lettered style whose size, weight, colour and perspective match the original lettering and "
        "the surface it is drawn on. Keep the surface, its outline, hatching and everything else in the image "
        "exactly as it is; add nothing else." % (language_name, text, direction))
    return box, _png(model_image), _png(mask), prompt, "%dx%d" % size


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _usage(response):
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    details = getattr(usage, "input_tokens_details", None)
    values = {"input": getattr(usage, "input_tokens", None), "output": getattr(usage, "output_tokens", None),
              "text_input": getattr(details, "text_tokens", None),
              "image_input": getattr(details, "image_tokens", None)}
    if not all(isinstance(values[k], int) for k in ("input", "output")):
        return None
    return {k: v for k, v in values.items() if isinstance(v, int)}


def estimate_cost(usage):
    if not usage:
        return None
    text_in, image_in = usage.get("text_input"), usage.get("image_input")
    if text_in is None or image_in is None:
        text_in, image_in = 0, usage["input"]
    return round((text_in * RATES_PER_MILLION["text_input"] + image_in * RATES_PER_MILLION["image_input"]
                  + usage["output"] * RATES_PER_MILLION["image_output"]) / 1_000_000, 6)


class SignEditor:
    """Masked image edits with a cache and a spending ceiling. ``client`` has ``images.edit``."""

    def __init__(self, state_dir, client, budget_usd=1.0, quality="medium", model=EDIT_MODEL):
        self.dir = Path(state_dir) / "edits"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client, self.budget, self.quality, self.model = client, budget_usd, quality, model
        self.ledger = self.dir / "edits.jsonl"

    def spent(self):
        if not self.ledger.exists():
            return 0.0
        total = 0.0
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            cost = json.loads(line).get("estimated_cost_usd")
            total += cost if isinstance(cost, (int, float)) else 0.0
        return total

    def _request(self, region, crop_png, mask_png, prompt, size, purpose):
        """One cached masked edit; returns the result PNG bytes."""
        key = hashlib.sha256(b"|".join([EDIT_VERSION.encode(), self.model.encode(), self.quality.encode(),
                                        crop_png, mask_png or b"", prompt.encode("utf-8")])).hexdigest()[:32]
        cached = self.dir / ("%s.png" % key)
        if cached.exists():
            return cached.read_bytes()
        if self.spent() >= self.budget:
            raise SignEditError("sign-edit budget reached")
        start = time.monotonic()
        try:
            extra = {"mask": ("mask.png", mask_png, "image/png")} if mask_png else {}
            response = self.client.images.edit(
                model=self.model, image=("sign.png", crop_png, "image/png"), prompt=prompt, size=size,
                quality=self.quality, n=1, **extra)
            data = getattr(response, "data", None) or []
            raw = base64.b64decode(getattr(data[0], "b64_json", "") or "", validate=True) if data else b""
            Image.open(io.BytesIO(raw)).verify()
        except Exception as exc:
            raise SignEditError("image edit failed (%s)" % type(exc).__name__) from None
        usage = _usage(response)
        cached.write_bytes(raw)
        with self.ledger.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({"key": key, "region": region.get("region_id"), "purpose": purpose,
                                     "model": self.model, "quality": self.quality, "size": size, "usage": usage,
                                     "estimated_cost_usd": estimate_cost(usage),
                                     "seconds": round(time.monotonic() - start, 2)}) + "\n")
        return raw

    def edit(self, image, region, text, language_name="Hebrew", rtl=True, locate=None):
        """Re-letter one sign of ``image`` in place; returns the method used ("redraw" or
        "clean+letter"). The model's redraw is kept only when it left the composition alone
        outside the mask; otherwise the model only cleans the surface and the text is lettered
        locally along the original lettering's measured angle."""
        # 1. The smallest local change: regenerate only a tight crop around the sign, paste it whole.
        tbox, tcrop, tprompt, tsize = local_request(image, region, text, language_name, rtl)
        local = self._request(region, tcrop, None, tprompt, tsize, "local")
        if edge_change(tcrop, local) <= EDGE_LIMIT and lettering_present(tcrop, local):
            _paste_whole(image, tbox, local)
            region["edit_method"] = "local"
            return "local"
        # 2. A masked redraw on a wider crop, kept only if the picture outside the mask is intact.
        box, crop_png, mask_png, prompt, size = edit_request(image, region, text, language_name, rtl)
        result = self._request(region, crop_png, mask_png, prompt, size, "redraw")
        if outside_change(crop_png, result, mask_png) <= COMPOSITION_LIMIT:
            _paste(image, box, region, result)
            region["edit_method"] = "redraw"
            return "redraw"
        if locate is not None:
            return self._clean_and_letter(image, region, text, rtl, box, crop_png, size, locate(image, region))
        geometry = lettering_geometry(image, region)             # measured before the surface is cleaned
        if len(geometry["letters"]) < 3:
            raise SignEditError("the sign's lettering could not be measured")
        if surface_is_light(image, geometry):
            clean_locally(image, geometry)                        # a plain surface: no model needed
            method = "local-clean+letter"
        else:
            tight = letters_mask(box, geometry, Image.open(io.BytesIO(crop_png)).size)
            tight_png = _png(tight)
            cleaned = self._request(region, crop_png, tight_png, CLEAN_PROMPT, size, "clean")
            if outside_change(crop_png, cleaned, tight_png) > COMPOSITION_LIMIT:
                raise SignEditError("the image model changed the picture around the sign")
            edited = Image.open(io.BytesIO(cleaned)).convert("RGB").resize((box[2] - box[0], box[3] - box[1]),
                                                                           Image.LANCZOS)
            keep = tight.split()[3].point(lambda v: 255 if v == 0 else 0).resize(edited.size)
            image.paste(edited, box[:2], keep.filter(ImageFilter.GaussianBlur(1)))   # only the letters
            method = "model-clean+letter"
        letter_text(image, geometry, text, rtl)
        region["edit_method"] = method
        return method


    def _clean_and_letter(self, image, region, text, rtl, box, crop_png, size, quad):
        """Fallback with a located quadrilateral: clean only the lettering polygon (locally on a
        light surface, else a model edit masked to the polygon), then letter the text along it."""
        geometry = refine_geometry(image, geometry_from_quad(quad, box))
        grow = max(2, int(0.15 * geometry["height"]))
        if clean_polygon_locally(image, geometry["polygon"], grow):
            method = "local-clean+letter"
        else:
            crop_size = Image.open(io.BytesIO(crop_png)).size
            sx, sy = crop_size[0] / (box[2] - box[0]), crop_size[1] / (box[3] - box[1])
            hole = _polygon_mask(crop_size, [((x - box[0]) * sx, (y - box[1]) * sy) for x, y in geometry["polygon"]],
                                 max(2, int(grow * sx)))
            mask = Image.new("RGBA", crop_size, (0, 0, 0, 255))
            mask.putalpha(hole.point(lambda v: 0 if v else 255))
            mask_png = _png(mask)
            cleaned = self._request(region, crop_png, mask_png, CLEAN_PROMPT, size, "clean")
            if outside_change(crop_png, cleaned, mask_png) > COMPOSITION_LIMIT:
                raise SignEditError("the image model changed the picture around the sign")
            edited = Image.open(io.BytesIO(cleaned)).convert("RGB").resize((box[2] - box[0], box[3] - box[1]),
                                                                           Image.LANCZOS)
            keep = _polygon_mask((box[2] - box[0], box[3] - box[1]),
                                 [(x - box[0], y - box[1]) for x, y in geometry["polygon"]], grow)
            image.paste(edited, box[:2], keep.filter(ImageFilter.GaussianBlur(1)))
            method = "model-clean+letter"
        letter_text(image, geometry, text, rtl)
        region["edit_method"] = method
        return method


CLEAN_PROMPT = (
    "This is a detail of a black-and-white comic page. Inside the transparent area of the mask there is "
    "lettering drawn on a surface (a sign, awning, banner, label or wall). Remove the lettering completely and "
    "restore the surface beneath it, continuing its texture, hatching, outlines and shading as if it had never "
    "been lettered. Do not write any text or letters. Keep the composition, perspective, position and size of "
    "everything exactly as it is.")
COMPOSITION_LIMIT = 8.0   # mean grey change outside the mask above which the model redrew the scene


def outside_change(crop_png, result_png, mask_png):
    """Mean grey difference between the crop and the model's result OUTSIDE the mask hole."""
    from PIL import ImageChops, ImageStat
    crop = Image.open(io.BytesIO(crop_png)).convert("L")
    result = Image.open(io.BytesIO(result_png)).convert("L").resize(crop.size, Image.LANCZOS)
    outside = Image.open(io.BytesIO(mask_png)).split()[3].point(lambda v: 255 if v else 0)
    if outside.getbbox() is None:
        return 0.0
    return ImageStat.Stat(ImageChops.difference(crop, result), outside).mean[0]


def _paste(image, box, region, result_png):
    edited = Image.open(io.BytesIO(result_png)).convert("RGB").resize((box[2] - box[0], box[3] - box[1]),
                                                                       Image.LANCZOS)
    x0, y0, x1, y1 = region["bbox"]
    pad = max(4, int(0.15 * min(x1 - x0, y1 - y0)))
    keep = Image.new("L", edited.size, 0)
    ImageDraw.Draw(keep).rectangle([x0 - pad - box[0], y0 - pad - box[1], x1 + pad - box[0], y1 + pad - box[1]],
                                   fill=255)
    image.paste(edited, box[:2], keep.filter(ImageFilter.GaussianBlur(2)))


def lettering_geometry(image, region):
    """The original lettering of ``region`` as a slanted line of letters: centre, baseline angle
    (degrees, image coordinates), length, letter height and the letter boxes (page
    coordinates). Only letter-shaped components count (thin hatching strokes, windows and
    other art are left out); the line is fitted, far-off components dropped, then refitted."""
    import math
    import statistics
    from .detect import _label, _otsu, _runs
    x0, y0, x1, y1 = region["bbox"]
    crop = image.crop((x0, y0, x1, y1)).convert("L")
    threshold = _otsu(crop.histogram())
    _, stats = _label(_runs(crop.point(lambda v: 255 if v <= threshold else 0)), True)
    shaped = [st for st in stats.values()
              if st[4] >= 6 and st[3] - st[1] >= 4 and 0.25 <= (st[2] - st[0]) / (st[3] - st[1]) <= 2.2]
    fallback = {"centre": ((x0 + x1) / 2, (y0 + y1) / 2), "angle": 0.0, "length": x1 - x0,
                "height": (y1 - y0) * 0.6, "letters": [], "threshold": threshold}
    if len(shaped) < 3:
        return fallback
    median_h = statistics.median(st[3] - st[1] for st in shaped)
    letters = [st for st in shaped if 0.6 * median_h <= st[3] - st[1] <= 1.6 * median_h]
    angle = 0.0
    for _ in range(3):
        if len(letters) < 3:
            return fallback
        centres = [((st[0] + st[2]) / 2, (st[1] + st[3]) / 2) for st in letters]
        mx = sum(c[0] for c in centres) / len(centres)
        my = sum(c[1] for c in centres) / len(centres)
        sxx = sum((c[0] - mx) ** 2 for c in centres)
        sxy = sum((c[0] - mx) * (c[1] - my) for c in centres)
        angle = math.degrees(math.atan2(sxy, sxx)) if sxx > 0 else 0.0
        rad = math.radians(angle)
        near = [st for st, c in zip(letters, centres)
                if abs(-(c[0] - mx) * math.sin(rad) + (c[1] - my) * math.cos(rad)) <= 0.8 * median_h]
        if len(near) == len(letters):
            break
        letters = near
    rad = math.radians(angle)
    along = [(c[0] - mx) * math.cos(rad) + (c[1] - my) * math.sin(rad) for c in centres]
    boxes = [[st[0] + x0, st[1] + y0, st[2] + x0, st[3] + y0] for st in letters]
    return {"centre": (mx + x0, my + y0), "angle": angle, "length": (max(along) - min(along)) + median_h,
            "height": median_h, "letters": boxes, "threshold": threshold}


def surface_is_light(image, geometry, share=0.6):
    """True when the surface right around the letters is mostly light (a plain sign or awning),
    so the letters can be erased locally without a model."""
    if not geometry["letters"]:
        return False
    gray = image.convert("L")
    grow = max(2, int(0.5 * geometry["height"]))
    inside = set()
    for x0, y0, x1, y1 in geometry["letters"]:
        inside.update((x, y) for x in range(x0, x1) for y in range(y0, y1))
    ring = []
    for x0, y0, x1, y1 in geometry["letters"]:
        for x in range(max(0, x0 - grow), min(gray.width, x1 + grow), 2):
            for y in range(max(0, y0 - grow), min(gray.height, y1 + grow), 2):
                if (x, y) not in inside:
                    ring.append(gray.getpixel((x, y)))
    return bool(ring) and sum(1 for v in ring if v >= 170) / len(ring) >= share


def clean_locally(image, geometry):
    """Paint the dark pixels of each letter (slightly grown) with the surface's light colour."""
    import statistics
    rgb = image.load()
    gray = image.convert("L").load()
    width, height = image.size
    light = [rgb[x, y] for x0, y0, x1, y1 in geometry["letters"]
             for x in range(max(0, x0 - 3), min(width, x1 + 3)) for y in (max(0, y0 - 3), min(height - 1, y1 + 2))
             if gray[x, y] >= 170] or [(255, 255, 255)]
    colour = tuple(int(statistics.median(p[k] for p in light)) for k in range(3))
    limit = geometry["threshold"] + 40
    for x0, y0, x1, y1 in geometry["letters"]:
        for x in range(max(0, x0 - 2), min(width, x1 + 2)):
            for y in range(max(0, y0 - 2), min(height, y1 + 2)):
                if gray[x, y] <= limit:
                    image.putpixel((x, y), colour)


def letters_mask(box, geometry, size):
    """Model mask (transparent = may change) covering only the letters, grown a little."""
    sx, sy = size[0] / (box[2] - box[0]), size[1] / (box[3] - box[1])
    grow = max(2, int(0.35 * geometry["height"]))
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in geometry["letters"]:
        draw.rectangle([round((x0 - grow - box[0]) * sx), round((y0 - grow - box[1]) * sy),
                        round((x1 + grow - box[0]) * sx), round((y1 + grow - box[1]) * sy)], fill=(0, 0, 0, 0))
    return mask


def letter_text(image, geometry, text, rtl=True):
    """Draw ``text`` along the measured baseline: comic font, letter height about the original,
    shrunk to the original length, rotated to its angle, centred on its centre."""
    from ..export.common import reorder_bidi_line
    from .typeset import font_for, _font
    font_path = font_for("he" if rtl else "en")
    visual = reorder_bidi_line(text, rtl_paragraph=True) if rtl else text
    size = max(8, int(geometry["height"] * 1.6))
    while size > 8 and _font(font_path, size).getlength(visual) > geometry["length"] * 1.05:
        size -= 1
    font = _font(font_path, size)
    left, top, right, bottom = font.getbbox(visual)
    canvas = Image.new("L", (right - left + 8, bottom - top + 8), 0)
    ImageDraw.Draw(canvas).text((4 - left, 4 - top), visual, font=font, fill=255)
    rotated = canvas.rotate(-geometry["angle"], resample=Image.BICUBIC, expand=True)
    cx, cy = geometry["centre"]
    image.paste((20, 20, 20), (int(round(cx - rotated.width / 2)), int(round(cy - rotated.height / 2))), rotated)


QUAD_PROMPT = (
    "# Comic Sign Location\n\n"
    "The attached image is a detail of a comic page. Somewhere in it there is lettering drawn on a surface "
    "(a sign, awning, banner or wall) that reads «{source}»; it may appear mirrored. Locate ONLY that "
    "lettering and return the four corners of the tightest quadrilateral around its letters, following the "
    "slant and perspective of the lettering. Coordinates are on a 0..1000 grid over this image (x to the right, "
    "y downward). List the corners as: start of the top edge, end of the top edge, end of the bottom edge, "
    "start of the bottom edge, where the top and bottom edges run along the lettering's baseline direction.\n\n"
    "Output ONLY one JSON object, no commentary and no code fences:\n"
    '{{"quad": [[x, y], [x, y], [x, y], [x, y]]}}')


def quad_prompt(image, region, source):
    """Vision prompt asking where the sign's lettering lies, as a quadrilateral; the crop is the
    region box with a margin (the same crop the image edit uses)."""
    from ..models.adapter import ImagePrompt
    box, crop_png, _, _, _ = edit_request(image, region, "", "Hebrew", True)
    return box, ImagePrompt(QUAD_PROMPT.format(source=source), crop_png, "image/png")


def parse_quad(text):
    """Validator: four corners in 0..1000, a non-degenerate quadrilateral."""
    import re
    raw = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        raise SignEditError("sign location: no JSON object") from None
    quad = data.get("quad")
    if (not isinstance(quad, list) or len(quad) != 4 or not all(
            isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1000 for v in p)
            for p in quad)):
        raise SignEditError("sign location: expected four [x, y] corners within 0..1000")
    area = 0.5 * abs(sum(quad[i][0] * quad[(i + 1) % 4][1] - quad[(i + 1) % 4][0] * quad[i][1] for i in range(4)))
    if area < 50:
        raise SignEditError("sign location: degenerate quadrilateral")
    return [[float(x), float(y)] for x, y in quad]


def geometry_from_quad(quad, box):
    """Page-coordinate polygon and lettering geometry from a 0..1000 quad over ``box``."""
    import math
    w, h = box[2] - box[0], box[3] - box[1]
    pts = [(box[0] + x * w / 1000, box[1] + y * h / 1000) for x, y in quad]
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = pts
    angle = math.degrees(math.atan2(((by - ay) + (cy - dy)) / 2, ((bx - ax) + (cx - dx)) / 2))
    length = (math.hypot(bx - ax, by - ay) + math.hypot(cx - dx, cy - dy)) / 2
    height = (math.hypot(dx - ax, dy - ay) + math.hypot(cx - bx, cy - by)) / 2
    if angle > 90 or angle < -90:           # corners given end-first: keep the text upright
        angle = angle - 180 if angle > 0 else angle + 180
    centre = (sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4)
    return {"centre": centre, "angle": angle, "length": length, "height": height / 1.4, "polygon": pts}


def _polygon_mask(size, polygon, grow=0):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon([(round(x), round(y)) for x, y in polygon], fill=255)
    if grow:
        mask = mask.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return mask


def clean_polygon_locally(image, polygon, grow):
    """Paint the dark pixels inside the lettering polygon with the surface's light colour. Returns
    False (nothing changed) when the surface around the polygon is not mostly light."""
    import statistics
    width, height = image.size
    inner = _polygon_mask((width, height), polygon, grow)
    outer = inner.filter(ImageFilter.MaxFilter(2 * max(3, grow) + 1))
    gray = image.convert("L")
    x0, y0, x1, y1 = outer.getbbox()
    ring, inside = [], []
    gp, ip, op, rgb = gray.load(), inner.load(), outer.load(), image.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if op[x, y] and not ip[x, y]:
                ring.append((gp[x, y], rgb[x, y]))
            elif ip[x, y]:
                inside.append((x, y))
    if not ring or sum(1 for v, _ in ring if v >= 170) / len(ring) < 0.6:
        return False
    light = [c for v, c in ring if v >= 170]
    colour = tuple(int(statistics.median(c[k] for c in light)) for k in range(3))
    limit = int(statistics.median(v for v, _ in ring)) - 50
    for x, y in inside:
        if gp[x, y] <= limit:
            image.putpixel((x, y), colour)
    return True


def refine_geometry(image, geometry):
    """Snap a located (approximate) lettering quadrilateral to the letters themselves: with the
    located angle known, letter-sized dark components in a band around it are collected, the
    line refitted through them and the polygon rebuilt tightly around them. The located
    geometry is kept when fewer than three letters are found."""
    import math
    from .detect import _label, _otsu, _runs
    xs = [p[0] for p in geometry["polygon"]]
    ys = [p[1] for p in geometry["polygon"]]
    reach = geometry["height"] * 1.5
    box = (max(0, int(min(xs) - reach)), max(0, int(min(ys) - reach)),
           min(image.width, int(max(xs) + reach)), min(image.height, int(max(ys) + reach)))
    crop = image.crop(box).convert("L")
    threshold = _otsu(crop.histogram())
    _, stats = _label(_runs(crop.point(lambda v: 255 if v <= threshold else 0)), True)
    rad = math.radians(geometry["angle"])
    cos, sin = math.cos(rad), math.sin(rad)
    cx, cy = geometry["centre"]
    half_len, est = geometry["length"] / 2 + geometry["height"], geometry["height"]
    letters = []
    for x0, y0, x1, y1, area in stats.values():
        h = y1 - y0
        if area < 6 or not 0.5 * est <= h <= 2.2 * est or (x1 - x0) > 2.5 * h:
            continue
        mx, my = (x0 + x1) / 2 + box[0] - cx, (y0 + y1) / 2 + box[1] - cy
        if abs(mx * cos + my * sin) <= half_len and abs(-mx * sin + my * cos) <= 1.5 * est:
            letters.append((x0 + box[0], y0 + box[1], x1 + box[0], y1 + box[1]))
    if len(letters) < 3:
        return geometry
    along = [((b[0] + b[2]) / 2 - cx) * cos + ((b[1] + b[3]) / 2 - cy) * sin for b in letters]
    across = [-((b[0] + b[2]) / 2 - cx) * sin + ((b[1] + b[3]) / 2 - cy) * cos for b in letters]
    shift = sum(across) / len(across)
    letter_h = sorted(b[3] - b[1] for b in letters)[len(letters) // 2]
    a0, a1 = min(along) - letter_h * 0.6, max(along) + letter_h * 0.6
    ncx, ncy = cx - shift * sin, cy + shift * cos
    half_h = letter_h * 0.75
    corners = [(a0, -half_h), (a1, -half_h), (a1, half_h), (a0, half_h)]
    polygon = [(ncx + a * cos - b * sin, ncy + a * sin + b * cos) for a, b in corners]
    return dict(geometry, centre=(ncx + (a0 + a1) / 2 * cos, ncy + (a0 + a1) / 2 * sin), length=a1 - a0,
                height=letter_h, polygon=polygon, letters=letters)


EDGE_LIMIT = 18.0   # mean grey change in the crop's outer band above which the patch would not blend


def local_request(image, region, text, language_name="Hebrew", rtl=True):
    """``(box, crop_png, prompt, size)``: the lettering with a narrow margin, nothing more."""
    width, height = image.size
    x0, y0, x1, y1 = region["bbox"]
    margin = max(6, int(0.12 * max(x1 - x0, y1 - y0)))
    box = (max(0, x0 - margin), max(0, y0 - margin), min(width, x1 + margin), min(height, y1 + margin))
    crop = image.crop(box).convert("RGB")
    size = _SIZES[_shape(*crop.size)]
    direction = "right-to-left" if rtl else "left-to-right"
    prompt = (
        "This small image is a detail cut out of a black-and-white comic page; it contains lettering that is part "
        "of the drawing (a sound effect, sign, awning, banner, label, screen or text on the art), which may appear "
        "mirrored. Redraw this same detail, "
        "changing ONLY that lettering: replace it with this %s text: «%s», written %s and spelled "
        "exactly as given, hand-lettered in the same style, weight, size and perspective as the original "
        "lettering (a sound effect stays as bold, expressive and dynamic as drawn), on the same surface. Keep the "
        "composition, every line and hatching, and especially the edges "
        "of the image unchanged, so the detail can be pasted back into the page seamlessly." % (
            language_name, text, direction))
    return box, _png(crop.resize(size, Image.LANCZOS)), prompt, "%dx%d" % size


def edge_change(crop_png, result_png, band_share=0.06):
    """Mean grey difference in the outer band of the crop (where the patch meets the page)."""
    from PIL import ImageChops, ImageStat
    crop = Image.open(io.BytesIO(crop_png)).convert("L")
    result = Image.open(io.BytesIO(result_png)).convert("L").resize(crop.size, Image.LANCZOS)
    band = max(4, int(band_share * min(crop.size)))
    mask = Image.new("L", crop.size, 255)
    ImageDraw.Draw(mask).rectangle([band, band, crop.width - band - 1, crop.height - band - 1], fill=0)
    return ImageStat.Stat(ImageChops.difference(crop, result), mask).mean[0]


def _paste_whole(image, box, result_png):
    """Paste the regenerated crop whole, fading into the page over its outer few pixels."""
    w, h = box[2] - box[0], box[3] - box[1]
    patch = Image.open(io.BytesIO(result_png)).convert("RGB").resize((w, h), Image.LANCZOS)
    fade = max(2, min(w, h) // 12)
    alpha = Image.new("L", (w, h), 0)
    ImageDraw.Draw(alpha).rectangle([fade, fade, w - fade - 1, h - fade - 1], fill=255)
    image.paste(patch, box[:2], alpha.filter(ImageFilter.GaussianBlur(fade / 2)))


def _ink_share(image, threshold=110):
    data = image.convert("L").getdata()
    return sum(1 for v in data if v < threshold) / max(1, len(data))


def lettering_present(crop_png, result_png, keep=0.35):
    """The regenerated crop still carries lettering: the ink in its centre is at least ``keep``
    of the original's (a model that only cleaned the surface left it blank)."""
    crop = Image.open(io.BytesIO(crop_png)).convert("L")
    result = Image.open(io.BytesIO(result_png)).convert("L").resize(crop.size, Image.LANCZOS)
    w, h = crop.size
    centre = (w // 5, h // 5, w - w // 5, h - h // 5)
    before = _ink_share(crop.crop(centre))
    return before == 0 or _ink_share(result.crop(centre)) >= keep * before
