"""SCHOLARLY-MATH (audit/contracts/scholarly_profile_and_math.md): profile-aware
notebook keeper, academic risk triggers and review focus, and mathematics in
reading, translation validation and PDF/HTML/EPUB export. Offline only."""
import io
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pdfplumber

from scholarly_translation import book_notebook as bn
from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import review_qa as rq
from scholarly_translation.document_structure import classify_line
from scholarly_translation.epub_archive import MATH_CLOSE, MATH_OPEN, block_text
from scholarly_translation.export_common import fallback_fonts, font_runs, resolve_hebrew_font
from scholarly_translation.export_epub import export_epub_from_document_structure
from scholarly_translation.export_html import export_html
from scholarly_translation.export_pdf import export_pdf
from scholarly_translation.formal_checks import has_translatable_words
from scholarly_translation.semantic_review import ACADEMIC_TRIGGER_TYPES, detect_risk_triggers

from test_export_epub import _canonical_epub_structure
from test_export_pdf import _build_structure_from_lines

MATHML = "http://www.w3.org/1998/Math/MathML"
XHTML = "http://www.w3.org/1999/xhtml"
FORMULA_CHARS = "∑∫√≤≥≠≈∞±×÷∂∇∈∉⊂⊆∪∩→⇒⇔∀∃αβγδθλμπσφωΣΩΔ²³½⁻₁₂ℝℕ"


def math_epub(path):
    paragraph = ('<p>The norm <math xmlns="%s"><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo>'
                 '<msub><mi>y</mi><mn>1</mn></msub></math> is bounded by '
                 '<math xmlns="%s" alttext="\\alpha \\leq 3"><mi>α</mi></math> in every case.</p>' % (MATHML, MATHML))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf"/></rootfiles></container>')
        archive.writestr("OEBPS/package.opf",
            '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>Maths</dc:title><dc:language>en</dc:language></metadata><manifest>'
            '<item id="c0" href="c0.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c0"/></spine></package>')
        archive.writestr("OEBPS/c0.xhtml", '<?xml version="1.0"?><html xmlns="%s"><body>'
            '<h1>Analysis</h1>%s<p>A plain closing paragraph.</p></body></html>' % (XHTML, paragraph))


class KeeperProfileTests(unittest.TestCase):
    def test_scholarly_keeper_tracks_the_argument_and_terminology(self):
        scholarly = bn.build_keeper_prompt("", "src", "עברית", 0, "scholarly")
        literary = bn.build_keeper_prompt("", "src", "עברית", 0, "literary")
        self.assertIn("THE ARGUMENT SO FAR", scholarly)
        self.assertIn("one Hebrew rendering per technical term", scholarly)
        self.assertIn("concept, definition", scholarly)
        self.assertNotIn("subplot", scholarly)
        self.assertIn("subplot", literary)
        self.assertIn("wordplay, humor", literary)
        for prompt in (scholarly, literary):
            self.assertNotIn("{{", prompt)


class AcademicTriggerTests(unittest.TestCase):
    TEXT = ('However, as Smith (2019, p. 23) argues, the rate is defined as at least 40% '
            'if x = 2 and α ≤ 3; perhaps the so-called "Dasein" matters.¹ See [12].')

    def types(self, text, language="en", academic=True):
        return {t["type"] for t in detect_risk_triggers({"text": text, "warnings": []}, language, [], academic=academic)}

    def test_english_and_french_academic_patterns(self):
        self.assertEqual(self.types(self.TEXT), ACADEMIC_TRIGGER_TYPES)
        self.assertEqual(self.types("Cependant, on appelle X ce qui, sans doute, est plus que 3 km.", "fr"),
                         {"contrast_concession", "definition", "hedge", "comparative_degree", "number_unit"})

    def test_opt_in_only_and_scholarly_pipeline_uses_it(self):
        self.assertEqual(self.types(self.TEXT, academic=False), set())
        record = {"source_text": self.TEXT, "source_language": "en", "findings": []}
        self.assertIn("citation", pipeline.detect_risk_triggers(record, "scholarly")["configured_risk_flags"])
        self.assertNotIn("citation", pipeline.detect_risk_triggers(record, "literary")["configured_risk_flags"])

    def test_review_focus_reaches_reviewer_only_when_flagged(self):
        focus = pipeline._review_focus(["citation", "negation", "unknown"])
        self.assertIn("REVIEW_FOCUS", focus)
        self.assertIn("citations, references and page numbers", focus)
        self.assertEqual(pipeline._review_focus([]), "")
        legacy = rq._render(rq.UNIT_REVIEW_PROMPT_ID, {"source_text": "s", "translation": "ת",
                            "source_context": "(none)", "glossary_and_decisions": "(none)"})
        self.assertNotIn("{{review_focus}}", legacy)
        self.assertNotIn("REVIEW_FOCUS", legacy)


class MathTextTests(unittest.TestCase):
    def test_formula_only_units_have_nothing_to_translate(self):
        for formula in ("E = mc²", "∑ αᵢ ≤ √x²", "f(x) = sin x + log y", "x ∈ ℝ, x > 0", MATH_OPEN + "x² + y₁" + MATH_CLOSE):
            self.assertFalse(has_translatable_words(formula), formula)
        for prose in ("Let x be a number", "The proof", "see (Smith)"):
            self.assertTrue(has_translatable_words(prose), prose)
        raw = json.dumps([{"unit_id": "u1", "translation": "E = mc²"}])
        self.assertEqual(pipeline.parse_batch_translation_response(raw, ["u1"], {"u1": "E = mc²"})["u1"]["translation"], "E = mc²")

    def test_unicode_display_formulas_are_formula_nodes(self):
        for line in ("E = mc²", "∑ᵢ αᵢ ≤ √x", "x ∈ ℝ, x > 0", "a = b + 2"):
            self.assertEqual(classify_line(line)[0], "formula", line)
        self.assertEqual(classify_line("The value of x is less than y.")[0], "paragraph")

    def test_protected_formula_tokens_must_survive_translation(self):
        token = MATH_OPEN + "x² + y₁" + MATH_CLOSE
        source = {"u1": "The norm " + token + " is bounded."}
        ok = json.dumps([{"unit_id": "u1", "translation": "הנורמה " + token + " חסומה."}])
        self.assertIn(token, pipeline.parse_batch_translation_response(ok, ["u1"], source)["u1"]["translation"])
        for broken in ("הנורמה x² + y₁ חסומה.", "הנורמה " + MATH_OPEN + "x^2 + y_1" + MATH_CLOSE + " חסומה.",
                       "הנורמה " + token + token + " חסומה."):
            with self.assertRaises(pipeline.ChapterPipelineError):
                pipeline.parse_batch_translation_response(json.dumps([{"unit_id": "u1", "translation": broken}]), ["u1"], source)


class MathExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_fallback_chain_covers_common_math_glyphs_for_every_bundled_font(self):
        self.assertEqual(len(fallback_fonts()), 2)
        for font_id in ("david-libre", "noto-serif-hebrew", "frank-ruhl-libre", "hadasim-clm", "david-clm"):
            regular, _, _ = resolve_hebrew_font(font_id)
            for name, part in font_runs(FORMULA_CHARS, regular):
                if name == regular:
                    from reportlab.pdfbase import pdfmetrics
                    cmap = pdfmetrics.getFont(name).face.charToGlyph
                    self.assertTrue(all(ord(ch) in cmap for ch in part), (font_id, part))

    def test_pdf_draws_math_with_fallback_fonts_and_hides_markers(self):
        structure = _build_structure_from_lines(Path(self.tmp.name) / "s.pdf", ["Intro text here.", "Second paragraph."])
        texts = ["לפי המשפט, ∑ αᵢ ≤ √x² בתחום ℝ.", "הנורמה " + MATH_OPEN + "x² + y₁" + MATH_CLOSE + " חסומה."]
        translations = {u["unit_id"]: {"text": t} for u, t in zip(structure["units"], texts)}
        result = export_pdf(structure, translations, font_id="david-libre")
        with pdfplumber.open(io.BytesIO(result.content)) as pdf:
            chars = [c for page in pdf.pages for c in page.chars]
        fonts = {c["fontname"].split("+")[-1] for c in chars}
        self.assertTrue({"NotoSansMath-Regular", "NotoSans-Regular", "DavidLibre-Regular"} <= fonts, fonts)
        drawn = "".join(c["text"] for c in chars)
        for ch in "∑α≤√²ℝ":
            self.assertIn(ch, drawn)
        self.assertNotIn(MATH_OPEN, drawn)

    def test_html_formula_blocks_are_ltr_and_markers_hidden(self):
        structure = _build_structure_from_lines(Path(self.tmp.name) / "s.pdf", ["Intro text here.", "E = mc2"])
        translations = {u["unit_id"]: {"text": "הנורמה " + MATH_OPEN + "x²" + MATH_CLOSE} for u in structure["units"]}
        page = export_html(structure, translations, title="t").decode("utf-8")
        self.assertIn("p.formula { direction: ltr; unicode-bidi: isolate; }", page)
        self.assertIn("Cambria Math", page)
        self.assertNotIn(MATH_OPEN, page)

    def test_epub_mathml_round_trip_keeps_original_formulas(self):
        path = Path(self.tmp.name) / "maths.epub"
        math_epub(path)
        structure = _canonical_epub_structure(path)
        texts = [u["text"] for u in structure["units"]]
        with_math = next(t for t in texts if MATH_OPEN in t)
        tokens = re.findall(MATH_OPEN + "[^" + MATH_CLOSE + "]*" + MATH_CLOSE, with_math)
        self.assertEqual(tokens, [MATH_OPEN + "x² + y₁" + MATH_CLOSE, MATH_OPEN + "\\alpha \\leq 3" + MATH_CLOSE])
        translations = {}
        for unit in structure["units"]:
            found = re.findall(MATH_OPEN + "[^" + MATH_CLOSE + "]*" + MATH_CLOSE, unit["text"])
            translations[unit["unit_id"]] = {"text": ("הנורמה %s חסומה על ידי %s בכל מקרה." % tuple(found))
                                             if found else "פסקה מתורגמת"}
        result = export_epub_from_document_structure(path, structure, translations)
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            chapter = archive.read("OEBPS/c0.xhtml").decode("utf-8")
        root = ET.fromstring(chapter)
        maths = [el for el in root.iter() if el.tag == "{%s}math" % MATHML]
        self.assertEqual(len(maths), 2)
        self.assertEqual(maths[1].get("alttext"), "\\alpha \\leq 3")
        self.assertTrue(any(el.tag == "{%s}msup" % MATHML for el in maths[0].iter()))
        self.assertNotIn(MATH_OPEN, chapter)
        holder = next(el for el in root.iter() if maths[0] in list(el))
        self.assertTrue(holder.text.startswith("הנורמה"))
        self.assertIn("חסומה על ידי", maths[0].tail)
        self.assertNotIn("math_placement_uncertain", [l["kind"] for l in result.limitations])

    def test_block_text_linearises_mathml(self):
        el = ET.fromstring('<p xmlns="%s">Let <math xmlns="%s"><mfrac><mn>1</mn><mi>n</mi></mfrac><mo>+</mo>'
                           '<msqrt><mi>x</mi></msqrt></math>.</p>' % (XHTML, MATHML))
        self.assertEqual(block_text(el), "Let " + MATH_OPEN + "(1)/(n) + √(x)" + MATH_CLOSE + ".")


if __name__ == "__main__":
    unittest.main()
