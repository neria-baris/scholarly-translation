"""Tests for learning_import.py (LEARN-1 builder B): Hebrew EPUB and
translation-library-snapshot import into an independent LearningSource.
Synthetic EPUBs are built inline (zipfile) rather than reusing another
module's fixture, per the builder B prompt.
"""
from __future__ import annotations

import io
import unittest
import zipfile

from scholarly_translation.learning_contracts import LearningError, validate_source
from scholarly_translation.learning_import import import_hebrew_epub, import_translation_job

HEBREW_HEADING = "פרק ראשון"
HEBREW_PARAGRAPH_1 = "הילד הביט בבית הישן ואז הלך בדרך הארוכה אל העיר הגדולה."
HEBREW_PARAGRAPH_2 = "היום היה יפה והשמש זרחה מעל הגבעות הירוקות ליד הנהר."
FOREIGN_PARAGRAPH = "This is an entirely English paragraph with no Hebrew letters at all."


def _write(archive, name, data):
    # Fixed date_time (zipfile.writestr otherwise stamps "now", making the
    # archive bytes, and therefore the extractor's content-hash, non-reproducible).
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    archive.writestr(info, data)


def _epub_bytes(chapters, title="כותרת מקור", language="he"):
    """chapters: list of xhtml body-inner-html strings, one per spine item."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _write(archive, "mimetype", "application/epub+zip")
        _write(
            archive, "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf"/></rootfiles></container>',
        )
        manifest_items = "".join(
            f'<item id="c{i}" href="chapter{i}.xhtml" media-type="application/xhtml+xml"/>'
            for i in range(len(chapters))
        )
        spine_items = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
        _write(
            archive, "OEBPS/package.opf",
            '<package xmlns="http://www.idpf.org/2007/opf">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{title}</dc:title><dc:language>{language}</dc:language>"
            "</metadata>"
            f"<manifest>{manifest_items}</manifest>"
            f"<spine>{spine_items}</spine>"
            "</package>",
        )
        for i, body in enumerate(chapters):
            _write(
                archive, f"OEBPS/chapter{i}.xhtml",
                '<?xml version="1.0"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + body + "</body></html>",
            )
    return buffer.getvalue()


def _hebrew_epub_bytes():
    return _epub_bytes([
        f"<h1>{HEBREW_HEADING}</h1><p>{HEBREW_PARAGRAPH_1}</p><p>{HEBREW_PARAGRAPH_2}</p>",
    ])


class ImportHebrewEpubTests(unittest.TestCase):
    def test_valid_hebrew_epub_produces_ordered_source(self):
        source = import_hebrew_epub(_hebrew_epub_bytes(), book_id="book-x")
        validate_source(source)
        self.assertEqual(source["book_id"], "book-x")
        self.assertEqual(source["origin"]["kind"], "hebrew_epub")
        chapter = source["chapters"][0]
        self.assertEqual(chapter["units"][0]["kind"], "heading")
        self.assertEqual(chapter["units"][0]["text"], HEBREW_HEADING)
        self.assertEqual(chapter["units"][1]["text"], HEBREW_PARAGRAPH_1)
        self.assertEqual(chapter["units"][2]["text"], HEBREW_PARAGRAPH_2)

    def test_malicious_markup_stays_inert_text(self):
        malicious = f"<h1>{HEBREW_HEADING}</h1><p>{HEBREW_PARAGRAPH_1}<script>alert(1)</script></p>"
        source = import_hebrew_epub(_epub_bytes([malicious]))
        full_text = " ".join(u["text"] for c in source["chapters"] for u in c["units"])
        self.assertNotIn("<script>", full_text)
        self.assertNotIn("<", full_text)

    def test_empty_epub_rejected(self):
        with self.assertRaises(LearningError) as ctx:
            import_hebrew_epub(_epub_bytes(["<p></p>"]))
        self.assertEqual(ctx.exception.code, "empty_epub")

    def test_damaged_epub_rejected(self):
        with self.assertRaises(LearningError):
            import_hebrew_epub(b"not a real zip file")

    def test_wrong_language_rejected(self):
        with self.assertRaises(LearningError) as ctx:
            import_hebrew_epub(_epub_bytes([f"<p>{FOREIGN_PARAGRAPH}</p>"]))
        self.assertEqual(ctx.exception.code, "wrong_language")

    def test_mixed_script_hebrew_accepted(self):
        mixed = f"<h1>{HEBREW_HEADING}</h1><p>{HEBREW_PARAGRAPH_1} (Paris, London) {HEBREW_PARAGRAPH_2}</p>"
        source = import_hebrew_epub(_epub_bytes([mixed]))
        validate_source(source)

    def test_heading_and_order_stable_across_runs(self):
        first = import_hebrew_epub(_hebrew_epub_bytes(), book_id="book-stable")
        second = import_hebrew_epub(_hebrew_epub_bytes(), book_id="book-stable")
        self.assertEqual(first, second)

    def test_default_book_id_derived_when_not_given(self):
        source = import_hebrew_epub(_hebrew_epub_bytes())
        self.assertRegex(source["book_id"], r"^[a-f0-9]{16}$")


def _completed_job_snapshot(job_id="aa11bb22cc33dd44ee55ff6677889900"):
    units = [
        {"unit_id": "u1", "order": 0, "page_id": "p1", "chapter_node_id": None,
         "source_text": "Le garçon regardait la maison.", "target_text": HEBREW_PARAGRAPH_1,
         "status": "approved", "approved": True, "human_edited": False, "review": None},
        {"unit_id": "u2", "order": 1, "page_id": "p1", "chapter_node_id": None,
         "source_text": "Le soleil brillait sur les collines.", "target_text": HEBREW_PARAGRAPH_2,
         "status": "approved", "approved": True, "human_edited": False, "review": None},
    ]
    structure = {"readings": [], "nodes": [], "unit_node_links": []}
    return {
        "job_id": job_id, "status": "completed", "filename": "ספר תרגום", "revision": 3,
        "units": units, "structure": structure,
    }


class ImportTranslationJobTests(unittest.TestCase):
    def test_non_hebrew_completed_target_rejected(self):
        snapshot = _completed_job_snapshot()
        for unit in snapshot['units']:
            unit['target_text'] = FOREIGN_PARAGRAPH
        with self.assertRaises(LearningError) as ctx:
            import_translation_job(snapshot)
        self.assertEqual(ctx.exception.code, 'wrong_language')

    def test_short_chapters_in_one_spine_file_keep_recaps_boundaries(self):
        content = f'<h1>פרק א</h1><p>{HEBREW_PARAGRAPH_1}</p><h1>פרק ב</h1><p>{HEBREW_PARAGRAPH_2}</p>'
        source = import_hebrew_epub(_epub_bytes([content]))
        self.assertEqual([c['title'] for c in source['chapters']], ['פרק א', 'פרק ב'])

    def test_completed_job_imports_current_target_text(self):
        snapshot = _completed_job_snapshot()
        source = import_translation_job(snapshot, book_id="book-y")
        validate_source(source)
        self.assertEqual(source["origin"]["kind"], "translation_library")
        self.assertEqual(source["origin"]["source_job_id"], snapshot["job_id"])
        self.assertEqual(source["origin"]["source_revision"], 3)
        texts = [u["text"] for c in source["chapters"] for u in c["units"]]
        self.assertEqual(texts, [HEBREW_PARAGRAPH_1, HEBREW_PARAGRAPH_2])

    def test_unfinished_job_rejected(self):
        snapshot = _completed_job_snapshot()
        snapshot["status"] = "translating"
        with self.assertRaises(LearningError) as ctx:
            import_translation_job(snapshot)
        self.assertEqual(ctx.exception.code, "unfinished_job")

    def test_missing_target_text_rejected(self):
        snapshot = _completed_job_snapshot()
        snapshot["units"][0]["target_text"] = ""
        with self.assertRaises(LearningError) as ctx:
            import_translation_job(snapshot)
        self.assertEqual(ctx.exception.code, "missing_target_text")

    def test_later_original_edits_do_not_mutate_imported_copy(self):
        snapshot = _completed_job_snapshot()
        imported = import_translation_job(snapshot, book_id="book-independent")
        snapshot["units"][0]["target_text"] = "טקסט שונה לגמרי"
        snapshot["revision"] = 4
        unaffected_text = imported["chapters"][0]["units"][0]["text"]
        self.assertEqual(unaffected_text, HEBREW_PARAGRAPH_1)
        self.assertEqual(imported["origin"]["source_revision"], 3)

    def test_long_paragraph_split_deterministically(self):
        long_sentence = (HEBREW_PARAGRAPH_1 + " ") * 100
        snapshot = _completed_job_snapshot()
        snapshot["units"][0]["target_text"] = long_sentence
        source = import_translation_job(snapshot)
        validate_source(source)
        units = source["chapters"][0]["units"]
        self.assertTrue(all(len(u["text"]) <= 2400 for u in units))
        self.assertEqual(" ".join(u["text"] for u in units if u["unit_id"].startswith("u1")),
                          " ".join(long_sentence.split()))


if __name__ == "__main__":
    unittest.main()
