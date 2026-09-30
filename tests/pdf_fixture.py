"""Tiny original PDF fixtures for Gate 2 digital extraction tests (reportlab-generated, never committed)."""
from __future__ import annotations

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

PAGE1_LINES = [
    "Introduction",
    "This is the first sentence of the introduction concept*.",
    "(Smith, 2020)",
    "42",
    "E = m * c^2",
    "* This is a footnote explaining the concept.",
]

PAGE2_LINES = [
    "Conclusion",
    "Ceci est la phrase de conclusion du concept*.",
    "(Dupont, 2021)",
    "7",
    "x = (a + b) / 2",
    "* Ceci est une note de bas de page expliquant le concept.",
]


def _draw_shuffled(c, height, lines, draw_order):
    y_positions = [height - 100, height - 130, height - 160, height - 190, height - 220, height - 700]
    for idx in draw_order:
        y = y_positions[idx]
        text = lines[idx]
        font = ("Helvetica-Bold", 16) if idx == 0 else ("Helvetica", 12)
        c.setFont(*font)
        c.drawString(72, y, text)


def build_two_page_fixture(path) -> None:
    """Two original pages (English, French) with shuffled draw order for reading-order tests."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    _draw_shuffled(c, height, PAGE1_LINES, draw_order=[5, 0, 3, 1, 4, 2])
    c.showPage()

    _draw_shuffled(c, height, PAGE2_LINES, draw_order=[2, 4, 0, 5, 1, 3])
    c.showPage()

    c.save()


def build_blank_page_fixture(path) -> None:
    """Single blank page with no text content, for empty-page/needs_ocr handling."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.showPage()
    c.save()
