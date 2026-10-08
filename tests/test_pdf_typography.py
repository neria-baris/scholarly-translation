"""PDF-TYPOGRAPHY: justified body text, two-sided quotation indents, paragraph
breaks inside a unit, edge punctuation of left-to-right islands and stand-ins
for punctuation no bundled font can draw."""
import io
import tempfile
import unittest
from pathlib import Path

import pdfplumber

from scholarly_translation.export_common import reorder_bidi_line, substitute_missing_glyphs, resolve_hebrew_font
from scholarly_translation.export_pdf import MARGIN, PAGE_SIZE, export_pdf
from test_export_pdf import _build_structure_from_lines

LEFT, RIGHT = MARGIN, PAGE_SIZE[0] - MARGIN
BODY = ("המחקר בוחן את יסודות המתמטיקה ואת הוויכוח בין הגישות השונות בראשית המאה, "
        "ומציע קריאה חדשה של המקורות ושל הטענות המרכזיות שהועלו בהם. ") * 4


def _lines(content, page=0):
    """Return the page's text lines as ``(top, x0, x1)``, top to bottom."""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        chars = [c for c in pdf.pages[page].chars if c["text"].strip()]
    rows = {}
    for c in chars:
        rows.setdefault(round(c["top"]), []).append(c)
    return [(top, min(c["x0"] for c in row), max(c["x1"] for c in row)) for top, row in sorted(rows.items())]


class BidiEdgePunctuationTests(unittest.TestCase):
    def test_comma_after_number_sits_on_the_hebrew_side(self):
        self.assertEqual(reorder_bidi_line("משנת 1931, שבו"), "ובש ,1931 תנשמ")

    def test_closing_period_after_a_bracketed_number_goes_to_the_line_end(self):
        self.assertEqual(reorder_bidi_line("תמיד (1)."), ".(1) דימת")

    def test_bracket_pairs_inside_an_island_are_never_split(self):
        self.assertEqual(reorder_bidi_line("הקבוצות ZF (1963) (4)."), ".ZF (1963) (4) תוצובקה")

    def test_list_marker_period_is_drawn_left_of_the_number(self):
        self.assertTrue(reorder_bidi_line("1. פריט").endswith(" .1"))

    def test_wrapped_citation_tail_follows_the_paragraph_direction(self):
        self.assertEqual(reorder_bidi_line("1995a, p. 383).", rtl_paragraph=True), ".(1995a, p. 383")
        self.assertEqual(reorder_bidi_line("1995a, p. 383)."), "1995a, p. 383).")

    def test_percent_stays_with_its_number(self):
        self.assertEqual(reorder_bidi_line("עלה 50%, ואז"), "זאו ,50% הלע")


class GlyphSubstituteTests(unittest.TestCase):
    def test_cjk_angle_brackets_get_a_drawable_stand_in(self):
        font, _, _ = resolve_hebrew_font("david-libre")
        self.assertEqual(substitute_missing_glyphs("〈מושג〉", font), "⟨מושג⟩")
        self.assertEqual(substitute_missing_glyphs("(מושג)", font), "(מושג)")

    def test_exported_pdf_draws_no_cjk_bracket(self):
        with tempfile.TemporaryDirectory() as tmp:
            structure = _build_structure_from_lines(Path(tmp) / "s.pdf", ["Intro text here."])
        unit = structure["units"][0]
        result = export_pdf(structure, {unit["unit_id"]: {"text": "〈אי־מיצוי〉 ושתי פילוסופיות"}},
                            font_id="david-libre")
        with pdfplumber.open(io.BytesIO(result.content)) as pdf:
            drawn = "".join(c["text"] for c in pdf.pages[0].chars)
        self.assertNotIn("〈", drawn)
        self.assertIn("⟨", drawn)
        self.assertIn("⟩", drawn)


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def export(self, source_lines, texts):
        structure = _build_structure_from_lines(Path(self.tmp.name) / "s.pdf", source_lines)
        translations = {u["unit_id"]: {"text": t} for u, t in zip(structure["units"], texts)}
        kinds = {n["kind"] for n in structure["nodes"]}
        return export_pdf(structure, translations, font_id="david-libre").content, kinds

    def test_paragraph_lines_are_justified_except_the_last(self):
        content, _ = self.export(["Intro text here."], [BODY])
        lines = _lines(content)
        self.assertGreater(len(lines), 3)
        for _, x0, x1 in lines[:-1]:
            self.assertAlmostEqual(x1, RIGHT, delta=1)
            self.assertAlmostEqual(x0, LEFT, delta=1)
        self.assertAlmostEqual(lines[-1][2], RIGHT, delta=1)
        self.assertGreater(lines[-1][1], LEFT + 20)       # last line keeps its natural width

    def test_quotation_is_indented_on_both_sides_and_justified(self):
        content, kinds = self.export(['"A quoted passage from the source."'], [BODY])
        self.assertIn("quotation", kinds)
        lines = _lines(content)
        for _, x0, x1 in lines[:-1]:
            self.assertAlmostEqual(x1, RIGHT - 30, delta=1)
            self.assertAlmostEqual(x0, LEFT + 30, delta=1)
        self.assertLessEqual(lines[-1][2], RIGHT - 29)

    def test_left_to_right_quotation_keeps_both_indents(self):
        english = "A long quoted passage in the original language that wraps over several lines. " * 4
        content, _ = self.export(['"A quoted passage from the source."'], [english])
        lines = _lines(content)
        self.assertAlmostEqual(lines[0][1], LEFT + 30, delta=1)
        self.assertAlmostEqual(lines[0][2], RIGHT - 30, delta=1)

    def test_paragraph_break_inside_a_unit_adds_space(self):
        short = "פסקה קצרה אחת."
        content, _ = self.export(["Intro text here."], [short + "\n" + short + "\n" + BODY])
        tops = [top for top, _, _ in _lines(content)]
        steps = [b - a for a, b in zip(tops, tops[1:])]
        line_step = min(steps)
        self.assertGreater(steps[0], line_step + 4)
        self.assertGreater(steps[1], line_step + 4)


if __name__ == "__main__":
    unittest.main()
