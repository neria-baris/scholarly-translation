"""Tiny original image-only PDF and fake-engine fixtures for Gate 3 OCR tests.

Image-only pages are rasterized with Pillow and embedded with reportlab (no text
layer), never committed. Fake engines are tiny local scripts standing in for
Tesseract's CLI contract (argv/stdout/exit-code/TSV), used for deterministic
success/failure/timeout/malformed tests.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

SENTINEL_WORD = "SENTINEL"
CLEAR_EN_TEXT = f"{SENTINEL_WORD} the quick brown fox"
BLURRED_FR_TEXT = "Le renard brun rapide"


def _render_text_image(text: str, size=(900, 220), blur: bool = False, font_path="arial.ttf") -> Image.Image:
    image = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(font_path, 40)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 80), text, fill="black", font=font)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=5))
    return image


def _embed_image_page(c: canvas.Canvas, image: Image.Image, page_width: float, page_height: float) -> None:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    reader = ImageReader(buf)
    img_w, img_h = image.size
    draw_width = page_width * 0.8
    draw_height = draw_width * img_h / img_w
    c.drawImage(reader, page_width * 0.1, page_height - draw_height - 150, width=draw_width, height=draw_height)
    c.showPage()


def build_image_only_fixture(path) -> None:
    """Single clear image-only English page, no text layer."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    _embed_image_page(c, _render_text_image(CLEAR_EN_TEXT, blur=False), width, height)
    c.save()


def build_multi_page_mixed_fixture(path) -> None:
    """Page 1 clear image-only English, page 2 blurred image-only French."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    _embed_image_page(c, _render_text_image(CLEAR_EN_TEXT, blur=False), width, height)
    _embed_image_page(c, _render_text_image(BLURRED_FR_TEXT, blur=True), width, height)
    c.save()


def build_language_fixture(path, language="en") -> None:
    """Original clear/degraded synthetic pages; no claim about real scholarly accuracy."""
    texts = {"en": CLEAR_EN_TEXT, "fr": "SENTINEL Le renard n'est pas blanc.",
             "ja": "日本語の合成テストです。"}
    font = "C:/Windows/Fonts/msgothic.ttc" if language == "ja" else "arial.ttf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    for blur in (False, True):
        _embed_image_page(c, _render_text_image(texts[language], blur=blur, font_path=font), width, height)
    c.save()


def build_digital_plus_image_fixture(path) -> None:
    """Page 1 real digital text, page 2 image-only: selection/skip producer-consumer fixture."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 14)
    c.drawString(72, height - 100, "This page has real digital text.")
    c.showPage()
    _embed_image_page(c, _render_text_image(CLEAR_EN_TEXT, blur=False), width, height)
    c.save()


def write_fake_tesseract(tmp_dir: Path, behavior: str) -> Path:
    """Write a tiny local fake engine implementing (image, 'stdout', '-l', lang, 'tsv') -> stdout/exit.

    behavior: 'success' | 'low_confidence' | 'failure' | 'timeout' | 'malformed'
    """
    tmp_dir = Path(tmp_dir)
    script_path = tmp_dir / f"fake_tesseract_{behavior}.py"
    bat_path = tmp_dir / f"fake_tesseract_{behavior}.bat"

    if behavior == "success":
        body = (
            "import sys\n"
            "sys.stdout.write(\n"
            "    'level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n'\n"
            "    '5\\t1\\t1\\t1\\t1\\t1\\t10\\t20\\t50\\t15\\t95.5\\tHello\\n'\n"
            "    '5\\t1\\t1\\t1\\t1\\t2\\t70\\t20\\t50\\t15\\t88.0\\tWorld\\n'\n"
            "    '5\\t1\\t1\\t1\\t2\\t1\\t10\\t50\\t50\\t15\\t80.0\\tSecond\\n'\n"
            ")\n"
            "sys.exit(0)\n"
        )
    elif behavior == "low_confidence":
        body = (
            "import sys\n"
            "sys.stdout.write(\n"
            "    'level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n'\n"
            "    '5\\t1\\t1\\t1\\t1\\t1\\t10\\t20\\t50\\t15\\t12.0\\tblur\\n'\n"
            ")\n"
            "sys.exit(0)\n"
        )
    elif behavior == "failure":
        body = "import sys\nsys.stderr.write('PRIVATE_PATH_SHOULD_NOT_LEAK /secret/dir')\nsys.exit(1)\n"
    elif behavior == "timeout":
        body = "import time\ntime.sleep(30)\n"
    elif behavior == "malformed":
        body = "import sys\nsys.stdout.write('not a tsv table\\n')\nsys.exit(0)\n"
    else:
        raise ValueError(f"unknown behavior {behavior!r}")

    body = "import sys\nif '--version' in sys.argv:\n    print('fake-tesseract-fixture-1')\n    sys.exit(0)\n" + body
    script_path.write_text(body, encoding="utf-8")
    bat_path.write_text(f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n', encoding="utf-8")
    return bat_path
