import json
import tempfile
import unittest
import subprocess
from unittest.mock import patch
from pathlib import Path

from scholarly_translation import __main__ as cli
from scholarly_translation.ocr import (
    OCRInputError,
    _parse_tsv,
    _reconstruct_text_and_spans,
    run_ocr,
)
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.store import save_document

from ocr_fixture import (
    SENTINEL_WORD,
    build_digital_plus_image_fixture,
    build_image_only_fixture,
    build_multi_page_mixed_fixture,
    write_fake_tesseract,
)

REAL_TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
VALID_TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t95.5\tHello\n"
    "5\t1\t1\t1\t1\t2\t70\t20\t50\t15\t88.0\tWorld\n"
    "5\t1\t1\t1\t2\t1\t10\t50\t50\t15\t80.0\tSecond\n"
)


class ParseTsvTests(unittest.TestCase):
    def test_nonfinite_negative_and_outside_image_coordinates(self):
        for coordinate in ("nan", "inf", "-1"):
            with self.assertRaises(ValueError):
                _parse_tsv(VALID_TSV.replace("\t10\t20\t", "\t" + coordinate + "\t20\t"))
        with self.assertRaises(ValueError):
            _reconstruct_text_and_spans(_parse_tsv(VALID_TSV), 600, 800, 20, 20)
    def test_parses_word_level_rows_only(self):
        words = _parse_tsv(VALID_TSV)
        self.assertEqual([w["text"] for w in words], ["Hello", "World", "Second"])

    def test_rejects_out_of_range_confidence(self):
        bad = VALID_TSV.replace("95.5", "150.0")
        with self.assertRaises(ValueError):
            _parse_tsv(bad)

    def test_rejects_malformed_header(self):
        with self.assertRaises(ValueError):
            _parse_tsv("not\ta\tvalid\theader\n")

    def test_rejects_malformed_row(self):
        with self.assertRaises(ValueError):
            _parse_tsv(VALID_TSV + "5\t1\t1\n")

    def test_empty_output_raises(self):
        with self.assertRaises(ValueError):
            _parse_tsv("")


class ReconstructionTests(unittest.TestCase):
    def test_line_breaks_from_block_par_line_ids_and_exact_offsets(self):
        words = _parse_tsv(VALID_TSV)
        text, records = _reconstruct_text_and_spans(words, 600.0, 800.0, 900, 1200)
        self.assertEqual(text, "Hello World\nSecond")
        for record in records:
            self.assertEqual(text[record["source_char_start"]:record["source_char_end"]], record["text"])
            x0, top, x1, bottom = record["pdf_bbox"]
            self.assertGreaterEqual(x0, 0)
            self.assertGreaterEqual(top, 0)
            self.assertLessEqual(x1, 600.0)
            self.assertLessEqual(bottom, 800.0)


class SelectionAndInputErrorTests(unittest.TestCase):
    def _document_and_pdf(self, tmp_path: Path):
        pdf_path = tmp_path / "mixed.pdf"
        build_digital_plus_image_fixture(pdf_path)
        document = extract_pdf(pdf_path, language="en")
        return pdf_path, document

    def test_unsupported_language_raises_before_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            with self.assertRaises(OCRInputError):
                run_ocr(pdf_path, document, language="de", tesseract_path="unused",
                         output_dir=tmp_path / "out")

    def test_invalid_timeout_raises_before_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            for timeout in (0, float("nan"), float("inf"), 121, True):
                with self.assertRaises(OCRInputError):
                    run_ocr(pdf_path, document, language="en", tesseract_path="unused",
                             output_dir=tmp_path / "out", timeout=timeout)

    def test_hash_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            other_path = tmp_path / "other.pdf"
            build_image_only_fixture(other_path)
            with self.assertRaises(OCRInputError):
                run_ocr(other_path, document, language="en", tesseract_path="unused",
                         output_dir=tmp_path / "out")

    def test_invalid_page_selection_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            with self.assertRaises(OCRInputError):
                run_ocr(pdf_path, document, language="en", tesseract_path="unused",
                         output_dir=tmp_path / "out", pages=[99])
            with self.assertRaises(OCRInputError):
                run_ocr(pdf_path, document, language="en", tesseract_path="unused",
                         output_dir=tmp_path / "out", pages=[])

    def test_default_selection_skips_digital_page_ocrs_image_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            engine = write_fake_tesseract(tmp_path, "success")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            self.assertEqual([p["page_number"] for p in bundle["skipped_pages"]], [1])
            self.assertEqual(bundle["skipped_pages"][0]["reason"], "digital_text_available")
            self.assertEqual([p["page_number"] for p in bundle["pages"]], [2])
            self.assertFalse(bundle["pages"][0]["forced_page_review"])

    def test_explicit_selection_flags_forced_page_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._document_and_pdf(tmp_path)
            engine = write_fake_tesseract(tmp_path, "success")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out", pages=[1])
            self.assertEqual(len(bundle["pages"]), 1)
            self.assertTrue(bundle["pages"][0]["forced_page_review"])
            self.assertIn("forced_page_review", bundle["pages"][0]["warnings"])
            self.assertEqual(bundle["skipped_pages"][0]["reason"], "not_selected")


class FakeEngineOutcomeTests(unittest.TestCase):
    def _single_image_document(self, tmp_path: Path):
        pdf_path = tmp_path / "image.pdf"
        build_image_only_fixture(pdf_path)
        document = extract_pdf(pdf_path, language="en")
        return pdf_path, document

    def test_success_produces_words_and_needs_human_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            engine = write_fake_tesseract(tmp_path, "success")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            page = bundle["pages"][0]
            self.assertEqual(page["status"], "needs_human")
            self.assertFalse(page["eligible_for_translation"])
            self.assertIn("ocr_unreviewed", page["warnings"])
            self.assertEqual(page["transcription"], "Hello World\nSecond")
            self.assertEqual(len(page["words"]), 3)
            self.assertIsNone(page["error"])
            self.assertTrue(Path(tmp_path / "out" / "ocr-page-1.png").exists())

    def test_low_confidence_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            engine = write_fake_tesseract(tmp_path, "low_confidence")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            self.assertIn("low_confidence", bundle["pages"][0]["warnings"])

    def test_failure_needs_human_without_private_stderr_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            engine = write_fake_tesseract(tmp_path, "failure")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            page = bundle["pages"][0]
            self.assertEqual(page["status"], "needs_human")
            self.assertEqual(page["transcription"], "")
            self.assertEqual(page["error"]["code"], "engine_error")
            self.assertNotIn("PRIVATE", page["error"]["message"])
            self.assertNotIn("/secret/dir", page["error"]["message"])
            self.assertTrue(Path(tmp_path / "out" / "ocr-page-1.png").exists())

    def test_timeout_needs_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            engine = write_fake_tesseract(tmp_path, "timeout")
            with patch("scholarly_translation.ocr._run_tesseract_tsv",
                       side_effect=subprocess.TimeoutExpired("fixture", 1)):
                bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                                 output_dir=tmp_path / "out", timeout=1.0)
            page = bundle["pages"][0]
            self.assertEqual(page["error"]["code"], "timeout")

    def test_malformed_output_needs_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            engine = write_fake_tesseract(tmp_path, "malformed")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            page = bundle["pages"][0]
            self.assertEqual(page["error"]["code"], "malformed_output")

    def test_engine_unavailable_needs_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path, document = self._single_image_document(tmp_path)
            bundle = run_ocr(pdf_path, document, language="en",
                              tesseract_path=str(tmp_path / "does-not-exist.exe"),
                              output_dir=tmp_path / "out")
            page = bundle["pages"][0]
            self.assertEqual(page["error"]["code"], "engine_unavailable")


class CliTests(unittest.TestCase):
    def test_cli_ocr_pdf_writes_bundle_and_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "image.pdf"
            build_image_only_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            document_path = tmp_path / "document.json"
            save_document(document, document_path)
            engine = write_fake_tesseract(tmp_path, "success")
            out_dir = tmp_path / "outputs"

            exit_code = cli.main([
                "ocr-pdf", str(pdf_path), str(document_path),
                "--language", "en", "--output", str(out_dir),
                "--tesseract", str(engine),
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue((out_dir / "ocr.json").exists())
            self.assertTrue((out_dir / "ocr-page-1.png").exists())

            bundle = json.loads((out_dir / "ocr.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle["stage"], "local-ocr@1")
            self.assertEqual(bundle["document_id"], document.document_id)


@unittest.skipUnless(Path(REAL_TESSERACT_PATH).is_file(), "local Tesseract engine not installed")
class RealEngineTests(unittest.TestCase):
    @unittest.skipUnless(Path("cache/ocr/tessdata/eng.traineddata").is_file(), "optional best weights not installed")
    def test_standalone_language_directory_produces_tsv_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "standalone.pdf"
            build_image_only_fixture(pdf)
            doc = extract_pdf(pdf, "en")
            before = doc.to_dict()
            bundle = run_ocr(pdf, doc, "en", REAL_TESSERACT_PATH, folder / "out",
                             tessdata_dir="cache/ocr/tessdata")
            page = bundle["pages"][0]
            self.assertIsNone(page["error"])
            self.assertIn(SENTINEL_WORD, page["transcription"])
            self.assertTrue(bundle["model_file_hash"])
            self.assertEqual(doc.to_dict(), before)
            self.assertFalse(page["eligible_for_translation"])

    def test_clear_page_recognized_blurred_page_stays_needs_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "mixed.pdf"
            build_multi_page_mixed_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            for page in document.pages:
                self.assertEqual(page.source_text, "")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=REAL_TESSERACT_PATH,
                              output_dir=tmp_path / "out", timeout=60.0)
            clear_page = bundle["pages"][0]
            self.assertIn(SENTINEL_WORD, clear_page["transcription"])
            self.assertEqual(clear_page["status"], "needs_human")
            blurred_page = bundle["pages"][1]
            self.assertEqual(blurred_page["status"], "needs_human")


if __name__ == "__main__":
    unittest.main()
