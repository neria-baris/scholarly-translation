import tempfile
import unittest
from pathlib import Path

from scholarly_translation import __main__ as cli
from scholarly_translation.pdf_extract import (
    ExtractionError,
    extract_pdf,
    render_pages,
    write_comparison_html,
)
from scholarly_translation.records import Document, Page, RecordValidationError, Segment
from scholarly_translation.store import load_document, save_document

from pdf_fixture import PAGE1_LINES, PAGE2_LINES, build_blank_page_fixture, build_two_page_fixture


class ExtractPdfTests(unittest.TestCase):
    def test_schema_3_pdf_requires_geometry_and_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = extract_pdf(self._fixture(Path(tmp)), language="en").to_dict()
            for field in ("width", "height", "source_text"):
                import copy
                bad = copy.deepcopy(doc)
                bad["pages"][0].pop(field)
                with self.assertRaises(RecordValidationError):
                    Document.from_dict(bad)
            doc["pages"][0]["segments"][0]["bbox"] = None
            with self.assertRaises(RecordValidationError):
                Document.from_dict(doc)

    def test_nonpositive_and_nonfinite_geometry_rejected(self):
        for dim in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(RecordValidationError):
                Page("p", "d", 1, width=dim, height=100)

    def test_encrypted_pdf_fails_without_password_disclosure(self):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pdfencrypt import StandardEncryption
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.pdf"
            c = canvas.Canvas(str(path), encrypt=StandardEncryption("PRIVATE_SENTINEL"))
            c.drawString(20, 20, "PRIVATE_DOCUMENT_SENTINEL")
            c.save()
            with self.assertRaises(ExtractionError) as result:
                extract_pdf(path, "en")
            self.assertNotIn("PRIVATE", str(result.exception))

    def _fixture(self, tmp_dir: Path) -> Path:
        path = tmp_dir / "fixture.pdf"
        build_two_page_fixture(path)
        return path

    def test_extract_two_pages_reading_order_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = self._fixture(Path(tmp))
            document = extract_pdf(pdf_path, language="en")

            self.assertEqual(document.schema_version, 3)
            self.assertEqual(document.stage_id, "digital-pdf")
            self.assertEqual(document.stage_version, 1)
            self.assertEqual(document.status, "needs_human")
            self.assertIn("layout_unverified", document.warnings)
            self.assertEqual(len(document.pages), 2)

            page1, page2 = document.pages[0], document.pages[1]
            self.assertEqual(page1.page_number, 1)
            self.assertEqual(page2.page_number, 2)

            for line in PAGE1_LINES:
                self.assertIn(line, page1.source_text)
            for line in PAGE2_LINES:
                self.assertIn(line, page2.source_text)

            extracted_order = [s.text for s in page1.segments]
            self.assertEqual(extracted_order, PAGE1_LINES)
            extracted_order2 = [s.text for s in page2.segments]
            self.assertEqual(extracted_order2, PAGE2_LINES)

            # footnote marker/note, citation, number, formula all preserved distinctly
            self.assertIn("* This is a footnote explaining the concept.", page1.source_text)
            self.assertIn("(Smith, 2020)", page1.source_text)
            self.assertIn("42", page1.source_text)
            self.assertIn("E = m * c^2", page1.source_text)

    def test_spans_and_bboxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = self._fixture(Path(tmp))
            document = extract_pdf(pdf_path, language="en")
            for page in document.pages:
                self.assertIsNotNone(page.width)
                self.assertIsNotNone(page.height)
                for segment in page.segments:
                    self.assertEqual(
                        page.source_text[segment.source_char_start:segment.source_char_end],
                        segment.text,
                    )
                    self.assertIsNotNone(segment.bbox)
                    x0, top, x1, bottom = segment.bbox
                    self.assertGreaterEqual(x0, 0)
                    self.assertGreaterEqual(top, 0)
                    self.assertLessEqual(x1, page.width)
                    self.assertLessEqual(bottom, page.height)

    def test_stable_ids_on_repeat_and_relocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = self._fixture(tmp_path)
            doc1 = extract_pdf(pdf_path, language="en")
            doc2 = extract_pdf(pdf_path, language="en")
            self.assertEqual(doc1.document_id, doc2.document_id)
            self.assertEqual(doc1.pages[0].page_id, doc2.pages[0].page_id)
            self.assertEqual(doc1.pages[0].segments[0].segment_id, doc2.pages[0].segments[0].segment_id)

            relocated_dir = tmp_path / "elsewhere"
            relocated_dir.mkdir()
            relocated_path = relocated_dir / "same-bytes.pdf"
            relocated_path.write_bytes(pdf_path.read_bytes())
            doc3 = extract_pdf(relocated_path, language="en")
            self.assertEqual(doc1.document_id, doc3.document_id)

    def test_ids_change_with_bytes_or_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = self._fixture(tmp_path)
            doc1 = extract_pdf(pdf_path, language="en", document_version=1)
            doc_v2 = extract_pdf(pdf_path, language="en", document_version=2)
            self.assertNotEqual(doc1.document_id, doc_v2.document_id)

            other_path = tmp_path / "other.pdf"
            build_blank_page_fixture(other_path)
            doc_other = extract_pdf(other_path, language="en")
            self.assertNotEqual(doc1.document_id, doc_other.document_id)

    def test_measured_hash_matches_file(self):
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = self._fixture(Path(tmp))
            document = extract_pdf(pdf_path, language="en")
            expected = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            self.assertEqual(document.input_hash, expected)

    def test_blank_page_flagged_needs_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.pdf"
            build_blank_page_fixture(path)
            document = extract_pdf(path, language="en")
            self.assertEqual(len(document.pages), 1)
            page = document.pages[0]
            self.assertEqual(page.segments, [])
            self.assertEqual(page.source_text, "")
            self.assertIn("page_1_empty_needs_ocr", document.warnings)

    def test_persist_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = self._fixture(tmp_path)
            document = extract_pdf(pdf_path, language="en")
            document_path = tmp_path / "document.json"
            save_document(document, document_path)
            reloaded = load_document(document_path)
            self.assertEqual(reloaded.document_id, document.document_id)
            self.assertEqual(reloaded.pages[0].source_text, document.pages[0].source_text)
            self.assertEqual(reloaded.pages[0].segments[0].bbox, document.pages[0].segments[0].bbox)

    def test_legacy_schema_1_and_2_still_readable(self):
        legacy1 = {
            "schema_version": 1,
            "document_id": "doc-legacy1",
            "document_version": 1,
            "language": "en",
            "source_kind": "synthetic",
            "source_uri": "file:///legacy1.txt",
            "pages": [],
        }
        doc1 = Document.from_dict(legacy1)
        self.assertEqual(doc1.input_hash, "unknown")

        legacy2 = {
            "schema_version": 2,
            "document_id": "doc-legacy2",
            "document_version": 1,
            "language": "en",
            "source_kind": "synthetic",
            "source_uri": "file:///legacy2.txt",
            "pages": [],
            "stage_id": "legacy-import",
            "stage_version": 1,
            "input_hash": "a" * 64,
            "status": "unreviewed",
            "warnings": [],
        }
        doc2 = Document.from_dict(legacy2)
        self.assertEqual(doc2.schema_version, 2)

    def test_missing_pdf_raises_extraction_error(self):
        with self.assertRaises(ExtractionError):
            extract_pdf("/nonexistent/path/does-not-exist.pdf", language="en")

    def test_empty_file_raises_extraction_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.pdf"
            path.write_bytes(b"")
            with self.assertRaises(ExtractionError):
                extract_pdf(path, language="en")

    def test_corrupt_pdf_raises_extraction_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.pdf"
            path.write_bytes(b"not a real pdf file" * 10)
            with self.assertRaises(ExtractionError):
                extract_pdf(path, language="en")

    def test_invalid_bbox_raises_record_validation_error(self):
        with self.assertRaises(RecordValidationError):
            Segment(
                segment_id="seg-1",
                page_id="page-1",
                order=1,
                text="hi",
                source_char_start=0,
                source_char_end=2,
                bbox=(10.0, 0.0, 5.0, 20.0),
            )

    def test_bbox_out_of_page_bounds_raises_record_validation_error(self):
        segment = Segment(
            segment_id="seg-1",
            page_id="page-1",
            order=1,
            text="hi",
            source_char_start=0,
            source_char_end=2,
            bbox=(0.0, 0.0, 5000.0, 20.0),
        )
        with self.assertRaises(RecordValidationError):
            Page(
                page_id="page-1",
                document_id="doc-1",
                page_number=1,
                segments=[segment],
                width=100.0,
                height=100.0,
                source_text="hi",
            )

    def test_render_pages_and_comparison_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = self._fixture(tmp_path)
            document = extract_pdf(pdf_path, language="en")
            out_dir = tmp_path / "out"
            image_paths = render_pages(pdf_path, out_dir)
            self.assertEqual(len(image_paths), 2)
            for image_path in image_paths:
                self.assertTrue(image_path.exists())
                self.assertGreater(image_path.stat().st_size, 0)

            comparison_path = out_dir / "comparison.html"
            write_comparison_html(document, image_paths, comparison_path)
            self.assertTrue(comparison_path.exists())
            html_text = comparison_path.read_text(encoding="utf-8")
            self.assertIn("Introduction", html_text)
            self.assertIn("<img", html_text)

    def test_cli_extract_pdf_writes_expected_outputs_and_inspect_consumes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = self._fixture(tmp_path)
            out_dir = tmp_path / "outputs"
            exit_code = cli.main(
                ["extract-pdf", str(pdf_path), "--language", "en", "--output", str(out_dir)]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((out_dir / "document.json").exists())
            self.assertTrue((out_dir / "page-1.png").exists())
            self.assertTrue((out_dir / "page-2.png").exists())
            self.assertTrue((out_dir / "comparison.html").exists())

            inspect_exit = cli.cmd_inspect(str(out_dir / "document.json"))
            self.assertEqual(inspect_exit, 0)


if __name__ == "__main__":
    unittest.main()
