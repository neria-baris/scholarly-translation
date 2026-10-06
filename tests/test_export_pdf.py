import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

import pdfplumber

from scholarly_translation.export_common import ExportError, reorder_bidi_line
from scholarly_translation.export_pdf import export_pdf
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.source_reading import build_readings


def _human_decision(candidate, reason="verified against page image"):
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _resolve_all_pages(document):
    readings = build_readings(document)
    decisions = {}
    for page in document.pages:
        reading = next(r for r in readings if r["page_id"] == page.page_id)
        candidate = next(c for c in reading["alternatives"] if c["origin"] == "digital")
        decisions[page.page_id] = _human_decision(candidate)
    return decisions


def _draw_lines(path, lines, pagesize=LETTER):
    c = canvas.Canvas(str(path), pagesize=pagesize)
    width, height = pagesize
    c.setFont("Helvetica", 12)
    y = height - 100
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()


def _build_structure_from_lines(path, lines, **unit_policy_kwargs):
    _draw_lines(path, lines)
    document = extract_pdf(path, language="en")
    decisions = _resolve_all_pages(document)
    return build_structure(document, decisions=decisions, **unit_policy_kwargs)


def _hebrew_translations(structure, text="טקסט מתורגם לעברית", approved=True):
    return {u["unit_id"]: {"text": f"{text} {i}", "approved": approved}
            for i, u in enumerate(structure["units"])}


class BidiReorderTests(unittest.TestCase):
    def test_pure_hebrew_word_is_character_reversed(self):
        self.assertEqual(reorder_bidi_line("שלום"), "".join(reversed("שלום")))

    def test_numbered_list_marker_stays_intact_and_unreversed(self):
        visual = reorder_bidi_line("1. פריט ראשון")
        self.assertIn("1.", visual)
        self.assertNotIn(".1", visual)
        # the digit+period token itself is never internally reordered
        tokens = visual.split(" ")
        self.assertIn("1.", tokens)

    def test_brackets_are_mirrored_when_fully_inside_hebrew_text(self):
        visual = reorder_bidi_line("(ראה הערה)")
        self.assertTrue(visual.startswith("("))
        self.assertTrue(visual.endswith(")"))

    def test_latin_citation_island_is_not_reversed_or_mirrored(self):
        visual = reorder_bidi_line("ראו (Smith, 2020) למידע נוסף")
        self.assertIn("(Smith, 2020)", visual)

    def test_empty_and_plain_ascii_text_are_unaffected(self):
        self.assertEqual(reorder_bidi_line(""), "")
        self.assertEqual(reorder_bidi_line("plain english text"), "plain english text")


class PdfExportStructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.pdf"

    def test_heading_hierarchy_paragraph_and_formula_are_rendered_and_traceable(self):
        structure = _build_structure_from_lines(self.path, [
            "Chapter One",
            "A short paragraph body sentence here.",
            "E = m * c^2",
        ])
        kinds = {n["kind"] for n in structure["nodes"]}
        self.assertIn("chapter", kinds)
        self.assertIn("paragraph", kinds)
        self.assertIn("formula", kinds)

        translations = _hebrew_translations(structure)
        result = export_pdf(structure, translations)
        self.assertTrue(result.content.startswith(b"%PDF"))
        self.assertEqual(len(result.manifest), len(structure["units"]))

        node_ids_by_unit = {link["unit_id"]: link["node_ids"] for link in structure["unit_node_links"]}
        for entry in result.manifest:
            self.assertEqual(entry["node_ids"], node_ids_by_unit[entry["unit_id"]])
            self.assertIn(entry["unit_id"], translations)

    def test_footnote_note_kind_is_rendered_distinctly_and_recorded(self):
        structure = _build_structure_from_lines(self.path, [
            "Body paragraph referencing a note.",
            "[1] A footnote using the bracketed-number form.",
        ])
        self.assertIn("note", {n["kind"] for n in structure["nodes"]})
        translations = _hebrew_translations(structure)
        result = export_pdf(structure, translations)
        # No mark for "[1]" in the body: the note stays where it stood (ARTICLE-NOTES).
        self.assertTrue(any(lim["kind"] == "note_without_mark" for lim in result.limitations))
        note_entries = [m for m in result.manifest if m["kind"] == "note"]
        self.assertEqual(len(note_entries), 1)
        self.assertTrue(note_entries[0]["rendered"])

    def test_image_is_embedded_near_its_caption_node(self):
        structure = _build_structure_from_lines(self.path, [
            "Figure 1. A test chart showing results",
        ])
        caption_node = next(n for n in structure["nodes"] if n["kind"] == "caption")
        translations = _hebrew_translations(structure)

        img = Image.new("RGB", (80, 40), color=(10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        result = export_pdf(structure, translations, images={caption_node["node_id"]: buf.getvalue()})
        self.assertFalse(any(lim["kind"] == "image_not_embedded" for lim in result.limitations))
        self.assertTrue(result.content.startswith(b"%PDF"))

    def test_multipage_generation_and_readable_reflow(self):
        lines = ["Chapter One"] + [f"This is distinct sentence number {i} in the body." for i in range(30)]
        structure = _build_structure_from_lines(self.path, lines, unit_policy={"max_unit_words": 4})
        long_hebrew = ("זהו משפט מתורגם לעברית שחוזר על עצמו כדי לבדוק גלישת שורות ודפים "
                       "באופן קריא וברור. ") * 2
        translations = {u["unit_id"]: {"text": long_hebrew, "approved": True} for u in structure["units"]}
        result = export_pdf(structure, translations, title="כותרת המסמך")

        out_path = Path(self.tmp.name) / "out.pdf"
        out_path.write_bytes(result.content)
        with pdfplumber.open(out_path) as pdf:
            self.assertGreater(len(pdf.pages), 1)

    def test_rtl_rendering_matches_reorder_function_on_the_physical_page(self):
        structure = _build_structure_from_lines(self.path, ["Introduction line only."])
        unit = structure["units"][0]
        hebrew_text = "שלום עולם זהו טקסט לדוגמה"
        result = export_pdf(structure, {unit["unit_id"]: {"text": hebrew_text, "approved": True}})

        out_path = Path(self.tmp.name) / "rtl.pdf"
        out_path.write_bytes(result.content)
        with pdfplumber.open(out_path) as pdf:
            chars = sorted(pdf.pages[0].chars, key=lambda ch: ch["x0"])
            physical_text = "".join(ch["text"] for ch in chars)
        self.assertIn(reorder_bidi_line(hebrew_text), physical_text)


class PdfExportErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.pdf"

    def test_invalid_structure_raises_specific_clean_exception(self):
        with self.assertRaises(ExportError) as ctx:
            export_pdf({"not": "a valid structure"}, {})
        self.assertNotIn("Traceback", str(ctx.exception))

    def test_schema1_structure_is_rejected_with_a_clear_message(self):
        with self.assertRaises(ExportError):
            export_pdf({"schema_version": 1}, {})

    def test_malformed_translation_mapping_raises_specific_exception(self):
        structure = _build_structure_from_lines(self.path, ["A single short paragraph sentence."])
        with self.assertRaises(ExportError):
            export_pdf(structure, {"x": "not-a-dict"})
        with self.assertRaises(ExportError):
            export_pdf(structure, {"x": {"text": ""}})

    def test_missing_translation_falls_back_to_source_with_recorded_limitation(self):
        structure = _build_structure_from_lines(self.path, ["A single short paragraph sentence."])
        result = export_pdf(structure, {})
        self.assertTrue(any(lim["kind"] == "missing_translation" for lim in result.limitations))
        self.assertTrue(result.content.startswith(b"%PDF"))
        self.assertTrue(result.manifest[0]["fell_back_to_source"])

    def test_undecodable_image_degrades_gracefully_without_crashing_export(self):
        structure = _build_structure_from_lines(self.path, ["Figure 1. An irregular floating figure"])
        caption_node = next(n for n in structure["nodes"] if n["kind"] == "caption")
        translations = _hebrew_translations(structure)
        result = export_pdf(structure, translations, images={caption_node["node_id"]: b"not-a-real-image"})
        self.assertTrue(result.content.startswith(b"%PDF"))
        kinds = [lim["kind"] for lim in result.limitations]
        self.assertIn("image_not_embedded", kinds)


class InputFormatDeterminesOutputFormatTests(unittest.TestCase):
    def test_pdf_input_structure_produces_pdf_bytes_by_default(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / "fixture.pdf"
            structure = _build_structure_from_lines(path, ["A single short paragraph sentence."])
            translations = _hebrew_translations(structure)
            result = export_pdf(structure, translations)
            self.assertTrue(result.content.startswith(b"%PDF"))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
