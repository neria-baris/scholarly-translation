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

    def edit(self, image, region, text, language_name="Hebrew", rtl=True):
        """Edit ``image`` in place for one sign; returns True when the sign was re-lettered."""
        box, crop_png, mask_png, prompt, size = edit_request(image, region, text, language_name, rtl)
        key = hashlib.sha256(b"|".join([EDIT_VERSION.encode(), self.model.encode(), self.quality.encode(),
                                        crop_png, mask_png, prompt.encode("utf-8")])).hexdigest()[:32]
        cached = self.dir / ("%s.png" % key)
        if not cached.exists():
            if self.spent() >= self.budget:
                raise SignEditError("sign-edit budget reached")
            start = time.monotonic()
            try:
                response = self.client.images.edit(
                    model=self.model, image=("sign.png", crop_png, "image/png"),
                    mask=("mask.png", mask_png, "image/png"), prompt=prompt, size=size, quality=self.quality, n=1)
                data = getattr(response, "data", None) or []
                raw = base64.b64decode(getattr(data[0], "b64_json", "") or "", validate=True) if data else b""
                Image.open(io.BytesIO(raw)).verify()
            except Exception as exc:
                raise SignEditError("image edit failed (%s)" % type(exc).__name__) from None
            usage = _usage(response)
            cached.write_bytes(raw)
            with self.ledger.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({"key": key, "region": region.get("region_id"), "model": self.model,
                                         "quality": self.quality, "size": size, "usage": usage,
                                         "estimated_cost_usd": estimate_cost(usage),
                                         "seconds": round(time.monotonic() - start, 2)}) + "\n")
        edited = Image.open(cached).convert("RGB").resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        x0, y0, x1, y1 = region["bbox"]
        pad = max(4, int(0.15 * min(x1 - x0, y1 - y0)))
        keep = Image.new("L", edited.size, 0)
        ImageDraw.Draw(keep).rectangle([x0 - pad - box[0], y0 - pad - box[1], x1 + pad - box[0], y1 + pad - box[1]],
                                       fill=255)
        image.paste(edited, box[:2], keep.filter(ImageFilter.GaussianBlur(2)))
        return True
