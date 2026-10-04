import json
import copy
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation import __main__ as cli
from scholarly_translation.ocr import run_ocr
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure, check_continuity, validate_structure
from scholarly_translation.source_reading import StructureError
from scholarly_translation.store import save_document

from ocr_fixture import (
    build_digital_plus_image_fixture,
    build_image_only_fixture,
    write_fake_tesseract,
)


def _build_annotated_digital_fixture(path) -> None:
    """Original digital PDF with a footnote marker, citation and formula line."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 14)
    c.drawString(72, height - 100, "Main text with a footnote marker [1].")
    c.drawString(72, height - 130, "A citation follows (Author, 2020).")
    c.drawString(72, height - 160, "A formula appears: E=mc^2.")
    c.drawString(72, height - 190, "[1] Footnote body text.")
    c.showPage()
    c.save()


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"],
        "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org",
        "actor_kind": "human",
        "reason": reason,
    }


def _digital_candidate_for(document, page_id):
    from scholarly_translation.source_reading import build_readings

    readings = build_readings(document)
    reading = next(r for r in readings if r["page_id"] == page_id)
    return next(c for c in reading["alternatives"] if c["origin"] == "digital")


class DigitalToUnitsTests(unittest.TestCase):
    def test_digital_reading_with_human_decision_produces_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}

            structure = build_structure(document, decisions=decisions)
            reading = structure["readings"][0]
            self.assertEqual(reading["status"], "resolved")
            self.assertEqual(reading["selected"]["origin"], "digital")
            self.assertEqual(len(structure["nodes"]), 4)
            self.assertEqual(len(structure["units"]), 2)
            for unit in structure["units"]:
                self.assertEqual(unit["text"], candidate["text"][unit["source_char_start"]:unit["source_char_end"]])
            self.assertEqual(structure["continuity"], [])
            validate_structure(structure)

    def test_footnote_citation_formula_lines_keep_exact_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}
            structure = build_structure(document, decisions=decisions)

            node_texts = [n["text"] for n in structure["nodes"]]
            self.assertTrue(any(t.endswith("marker [1].") for t in node_texts))
            self.assertTrue(any("Author, 2020" in t for t in node_texts))
            self.assertTrue(any("E=mc^2" in t for t in node_texts))
            self.assertTrue(any(t.startswith("[1] Footnote body text.") for t in node_texts))
            for unit in structure["units"]:
                for anchor in unit["anchors"]:
                    self.assertEqual(anchor["kind"], "line")
                    self.assertIsNotNone(anchor["bbox"])

    def test_model_actor_cannot_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decision = _human_decision(candidate)
            decision["actor_kind"] = "model"
            with self.assertRaises(StructureError):
                build_structure(document, decisions={page.page_id: decision})

    def test_stale_candidate_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            decisions = {page.page_id: {
                "origin": "digital", "candidate_hash": "0" * 64,
                "actor": "reviewer", "actor_kind": "human", "reason": "stale",
            }}
            with self.assertRaises(StructureError):
                build_structure(document, decisions=decisions)


class OcrToUnitsTests(unittest.TestCase):
    def test_real_ocr_producer_then_human_decision_produces_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "image.pdf"
            build_image_only_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            engine = write_fake_tesseract(tmp_path, "success")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            page = document.pages[0]

            from scholarly_translation.source_reading import build_readings
            reading = build_readings(document, ocr_bundle=bundle)[0]
            ocr_candidate = next(c for c in reading["alternatives"] if c["origin"] == "ocr")
            decisions = {page.page_id: _human_decision(ocr_candidate)}

            structure = build_structure(document, ocr_bundle=bundle, decisions=decisions)
            self.assertEqual(structure["readings"][0]["status"], "resolved")
            self.assertGreater(len(structure["units"]), 0)
            for unit in structure["units"]:
                for anchor in unit["anchors"]:
                    self.assertEqual(anchor["kind"], "word")
                    self.assertIn("image_uri", anchor)
            validate_structure(structure)

    def test_ambiguous_unreviewed_ocr_stays_unresolved_no_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "image.pdf"
            build_image_only_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            engine = write_fake_tesseract(tmp_path, "low_confidence")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            structure = build_structure(document, ocr_bundle=bundle)
            reading = structure["readings"][0]
            self.assertEqual(reading["status"], "unresolved")
            self.assertEqual(reading["reasons"], ["unreviewed_source"])
            self.assertEqual(structure["units"], [])

    def test_engine_error_ocr_stays_unresolved_no_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "image.pdf"
            build_image_only_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            engine = write_fake_tesseract(tmp_path, "failure")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            structure = build_structure(document, ocr_bundle=bundle)
            reading = structure["readings"][0]
            self.assertEqual(reading["status"], "unresolved")
            self.assertEqual(reading["reasons"], ["missing_source"])
            self.assertEqual(structure["units"], [])


class OcrBundleRejectionTests(unittest.TestCase):
    def _document_and_bundle(self, tmp_path: Path):
        pdf_path = tmp_path / "image.pdf"
        build_image_only_fixture(pdf_path)
        document = extract_pdf(pdf_path, language="en")
        engine = write_fake_tesseract(tmp_path, "success")
        bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                          output_dir=tmp_path / "out")
        return document, bundle

    def test_wrong_document_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["document_id"] = "wrong"
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)

    def test_wrong_base_extraction_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["base_extraction_hash"] = "0" * 64
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)

    def test_wrong_image_hash_format_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["pages"][0]["image_hash"] = "not-a-hash"
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)

    def test_mismatched_pdf_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["pages"][0]["pdf_width"] = bundle["pages"][0]["pdf_width"] + 100
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)

    def test_word_span_text_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["pages"][0]["words"][0]["text"] = "Tampered"
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)

    def test_inconsistent_pixel_to_pdf_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document, bundle = self._document_and_bundle(tmp_path)
            bundle["pages"][0]["words"][0]["pdf_bbox"] = [0.0, 0.0, 1.0, 1.0]
            with self.assertRaises(StructureError):
                build_structure(document, ocr_bundle=bundle)


class CorrectionAndRevisionTests(unittest.TestCase):
    def test_merge_split_preserves_snapshots_and_unaffected_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}

            # Default logical-structure segmentation would merge these three
            # single-sentence body lines into one scholarly unit; pin the
            # original per-line boundaries explicitly so this test exercises
            # merge/split identity and versioning, not the default policy
            # (covered separately in test_structure_v2.py).
            text = candidate["text"]
            first_line_end = text.index("\n")
            second_line_end = text.index("\n", first_line_end + 1)
            third_line_end = text.index("\n", second_line_end + 1)
            original_boundaries = {page.page_id: [
                [0, first_line_end],
                [first_line_end + 1, second_line_end],
                [second_line_end + 1, third_line_end],
                [third_line_end + 1, len(text)],
            ]}

            first = build_structure(document, decisions=decisions, boundaries=original_boundaries)
            self.assertEqual(len(first["units"]), 4)
            first_unit_ids = [u["unit_id"] for u in first["units"]]
            self.assertTrue(all(u["unit_version"] == 1 for u in first["units"]))

            # Merge the first two lines into one unit; the last two lines are
            # explicitly included unaffected, covering the full source text.
            boundaries = {page.page_id: [
                [0, second_line_end],
                [second_line_end + 1, third_line_end],
                [third_line_end + 1, len(text)],
            ]}
            second = build_structure(document, decisions=decisions, boundaries=boundaries, previous=first)

            self.assertEqual(len(second["units"]), 3)
            merged_unit = next(u for u in second["units"] if u["source_char_start"] == 0)
            unaffected = [u for u in second["units"] if u["unit_id"] in first_unit_ids]
            self.assertEqual(len(unaffected), 2)
            for u in unaffected:
                self.assertEqual(u["unit_version"], 1)
                self.assertEqual(u["predecessor_unit_ids"], [])
            self.assertEqual(sorted(merged_unit["predecessor_unit_ids"]), sorted(first_unit_ids[:2]))
            self.assertEqual(merged_unit["unit_version"], 2)
            self.assertEqual(len(second["history"]), 1)
            self.assertEqual(second["history"][0]["units"], first["units"])
            validate_structure(second)

            # Split back to the original four lines; unaffected units keep prior
            # versions, affected ones increment again, and both snapshots remain.
            third = build_structure(document, decisions=decisions, boundaries=original_boundaries, previous=second)
            self.assertEqual(len(third["units"]), 4)
            third_by_span = {(u["source_char_start"], u["source_char_end"]): u for u in third["units"]}
            first_by_span = {(u["source_char_start"], u["source_char_end"]): u for u in first["units"]}
            for span, unit in third_by_span.items():
                self.assertEqual(unit["unit_id"], first_by_span[span]["unit_id"])
            self.assertGreater(third_by_span[(0, first_line_end)]["unit_version"], 1)
            self.assertGreater(third_by_span[(first_line_end + 1, second_line_end)]["unit_version"], 1)
            self.assertEqual(len(third["history"]), 2)
            self.assertEqual(third["history"][0]["units"], first["units"])
            self.assertEqual(third["history"][1]["units"], second["units"])
            validate_structure(third)

    def test_changed_selected_reading_retains_prior_reading_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "mixed.pdf"
            build_digital_plus_image_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            engine = write_fake_tesseract(tmp_path, "success")
            bundle = run_ocr(pdf_path, document, language="en", tesseract_path=str(engine),
                              output_dir=tmp_path / "out")
            page2 = document.pages[1]
            page1 = document.pages[0]

            from scholarly_translation.source_reading import build_readings
            reading2 = build_readings(document, ocr_bundle=bundle)[1]
            ocr_candidate = next(c for c in reading2["alternatives"] if c["origin"] == "ocr")
            decisions = {page2.page_id: _human_decision(ocr_candidate)}

            first = build_structure(document, ocr_bundle=bundle, decisions=decisions)
            first_reading = next(r for r in first["readings"] if r["page_id"] == page2.page_id)
            self.assertEqual(first_reading["version"], 1)

            digital_candidate = _digital_candidate_for(document, page1.page_id)
            new_decisions = dict(decisions)
            new_decisions[page1.page_id] = _human_decision(digital_candidate)
            second = build_structure(document, ocr_bundle=bundle, decisions=new_decisions, previous=first)
            second_reading = next(r for r in second["readings"] if r["page_id"] == page1.page_id)
            self.assertEqual(second_reading["version"], 2)
            self.assertEqual(second_reading["prior_version"], 1)
            unchanged_reading = next(r for r in second["readings"] if r["page_id"] == page2.page_id)
            self.assertEqual(unchanged_reading["version"], 1)
            self.assertIsNone(unchanged_reading["prior_version"])

    def test_previous_structure_lineage_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}
            first = build_structure(document, decisions=decisions)
            first["document_id"] = "different-document"
            with self.assertRaises(StructureError):
                build_structure(document, decisions=decisions, previous=first)


class ContinuityTests(unittest.TestCase):
    def test_omitted_and_duplicated_units_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}
            text = candidate["text"]
            first_line_end = text.index("\n")
            boundaries = {page.page_id: [[0, first_line_end], [0, first_line_end]]}
            with self.assertRaises(StructureError):
                build_structure(document, decisions=decisions, boundaries=boundaries)

            structure = build_structure(document, decisions=decisions)
            reading = structure["readings"][0]
            duplicated = dict(structure["units"][0])
            omitted_units = structure["units"][1:]
            findings = check_continuity(reading, [structure["units"][0], duplicated] + omitted_units[1:])
            types = {f["type"] for f in findings}
            self.assertIn("duplicate_unit", types)
            self.assertIn("gap", types)

    def test_invalid_user_boundaries_rejected_not_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}
            for bad_boundary in ([[5, 2]], [[-1, 5]], [[0, 10 ** 6]]):
                with self.assertRaises(StructureError):
                    build_structure(document, decisions=decisions, boundaries={page.page_id: bad_boundary})


class PersistedConsumerTests(unittest.TestCase):
    def test_corrupted_persisted_structure_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions = {page.page_id: _human_decision(candidate)}
            structure = build_structure(document, decisions=decisions)
            validate_structure(structure)

            tampered = json.loads(json.dumps(structure))
            tampered["units"][0]["text"] = "TAMPERED"
            with self.assertRaises(StructureError):
                validate_structure(tampered)


class CliDemonstrationTests(unittest.TestCase):
    def test_cli_unresolved_then_decision_then_revision_and_inspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "annotated.pdf"
            _build_annotated_digital_fixture(pdf_path)
            document = extract_pdf(pdf_path, language="en")
            document_path = tmp_path / "document.json"
            save_document(document, document_path)

            first_out = tmp_path / "structure1.json"
            exit_code = cli.main([
                "structure", str(document_path), "--output", str(first_out),
            ])
            self.assertEqual(exit_code, 0)
            first_data = json.loads(first_out.read_text(encoding="utf-8"))
            self.assertEqual(first_data["readings"][0]["status"], "unresolved")
            self.assertEqual(first_data["units"], [])

            page = document.pages[0]
            candidate = _digital_candidate_for(document, page.page_id)
            decisions_path = tmp_path / "decisions.json"
            decisions_path.write_text(json.dumps({page.page_id: _human_decision(candidate)}), encoding="utf-8")

            second_out = tmp_path / "structure2.json"
            exit_code = cli.main([
                "structure", str(document_path), "--output", str(second_out),
                "--decisions", str(decisions_path), "--previous", str(first_out),
            ])
            self.assertEqual(exit_code, 0)
            second_data = json.loads(second_out.read_text(encoding="utf-8"))
            self.assertEqual(second_data["readings"][0]["status"], "resolved")
            self.assertGreater(len(second_data["units"]), 0)
            self.assertEqual(second_data["revision"]["parent_revision"], first_data["revision"]["id"])

            exit_code = cli.main(["inspect-structure", str(second_out)])
            self.assertEqual(exit_code, 0)

            corrupted = tmp_path / "corrupted.json"
            bad = dict(second_data)
            bad["units"][0]["text"] = "TAMPERED"
            corrupted.write_text(json.dumps(bad), encoding="utf-8")
            exit_code = cli.main(["inspect-structure", str(corrupted)])
            self.assertEqual(exit_code, 1)


class StructureContractRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.pdf = self.folder / "source.pdf"
        _build_annotated_digital_fixture(self.pdf)
        self.document = extract_pdf(self.pdf, language="en")
        self.page_id = self.document.pages[0].page_id
        self.decisions = {self.page_id: _human_decision(_digital_candidate_for(self.document, self.page_id),
                                                       "synthetic construction simulation only")}
        self.structure = build_structure(self.document, decisions=self.decisions)

    def test_negative_persisted_contract_matrix(self):
        mutations = {
            "anchor_bounds": lambda x: x["units"][0]["anchors"][0].update(bbox=[-1]*4),
            "wrong_page": lambda x: x["units"][0].update(page_id="wrong"),
            "wrong_document": lambda x: x["units"][0].update(document_id="wrong"),
            "bool_version": lambda x: x["units"][0].update(unit_version=True),
            "bool_span": lambda x: x["units"][0].update(source_char_start=False),
            "missing_anchors": lambda x: x["units"][0].update(anchors=[]),
            "duplicate_unit": lambda x: x["units"].append(copy.deepcopy(x["units"][0])),
            "duplicate_reading": lambda x: x["readings"].append(copy.deepcopy(x["readings"][0])),
            "malformed_reading": lambda x: x.update(readings=[None]),
            "model_actor": lambda x: x["readings"][0]["decision"].update(actor_kind="model"),
            "lost_warning": lambda x: x["units"][0].update(warnings=["unreviewed_translation"]),
            "evidence_hash": lambda x: x["readings"][0]["alternatives"][0].update(candidate_hash="0"*64),
            "unit_hash": lambda x: x["units"][0].update(reading_text_hash="0"*64),
            "input_hash": lambda x: x.update(input_hash="0"*64),
            "approved_unit": lambda x: x["units"][0].update(status="approved"),
            "missing_unit": lambda x: x["units"].pop(),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                bad = copy.deepcopy(self.structure)
                mutate(bad)
                with self.assertRaises(StructureError):
                    validate_structure(bad)

    def test_previous_replay_and_history_use_same_validation(self):
        self.assertEqual(build_structure(self.document, decisions=self.decisions,
                                         previous=self.structure), self.structure)
        old = self.structure["units"]
        boundaries = {self.page_id: [[old[0]["source_char_start"],old[1]["source_char_end"]]] +
                                   [[u["source_char_start"],u["source_char_end"]] for u in old[2:]]}
        revised = build_structure(self.document, decisions=self.decisions,
                                  boundaries=boundaries, previous=self.structure)
        self.assertEqual(revised["units"][1:], self.structure["units"][2:])
        self.assertEqual(revised["units"][0]["unit_version"], 2)
        for field in ("bbox", "region_id"):
            bad = copy.deepcopy(revised)
            bad["history"][0]["units"][0]["anchors"][0][field] = [-1]*4 if field == "bbox" else "wrong"
            with self.assertRaises(StructureError):
                validate_structure(bad)
            with self.assertRaises(StructureError):
                build_structure(self.document, decisions=self.decisions, previous=bad)
        mutated = copy.deepcopy(self.structure)
        mutated["units"][0]["text"] = "x"*len(mutated["units"][0]["text"])
        with self.assertRaises(StructureError):
            build_structure(self.document, decisions=self.decisions, previous=mutated)

    def test_invalid_boundary_gap_and_unresolved_override_rejected(self):
        with self.assertRaises(StructureError):
            build_structure(self.document, decisions=self.decisions, boundaries={self.page_id:[[0,1]]})
        with self.assertRaises(StructureError):
            build_structure(self.document, boundaries={self.page_id:[[0,1]]})

    def test_cli_duplicate_json_malformed_consumer_and_source_overwrite(self):
        document_path = self.folder / "document.json"
        save_document(self.document, document_path)
        decisions_path = self.folder / "decisions.json"
        decisions_path.write_text('{"p":1,"p":2}', encoding="utf-8")
        output = self.folder / "result.json"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["structure",str(document_path),"--decisions",str(decisions_path),
                                       "--output",str(output)]), 1)
        self.assertFalse(output.exists())
        for protected in (document_path, self.pdf):
            before = protected.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["structure",str(document_path),"--output",str(protected)]), 1)
            self.assertEqual(protected.read_bytes(),before)
        bad = self.folder / "bad.json"
        bad.write_text('{"schema_version":1,"schema_version":true}',encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["inspect-structure",str(bad)]),1)

    def test_derived_records_do_not_alias_evidence(self):
        from scholarly_translation.source_reading import build_readings
        before = copy.deepcopy(self.document.to_dict())
        readings = build_readings(self.document)
        readings[0]["alternatives"][0]["warnings"].append("changed")
        readings[0]["alternatives"][0]["anchors"][0]["bbox"][0] = -1
        self.assertEqual(self.document.to_dict(),before)


class OcrEvidenceRegressionTests(unittest.TestCase):
    _document_and_bundle = OcrBundleRejectionTests._document_and_bundle
    def test_coverage_mapping_and_stale_decision(self):
        from scholarly_translation.source_reading import build_readings
        with tempfile.TemporaryDirectory() as tmp:
            document,bundle = self._document_and_bundle(Path(tmp))
            reading = build_readings(document,ocr_bundle=bundle)[0]
            candidate = next(c for c in reading["alternatives"] if c["origin"] == "ocr")
            decisions = {reading["page_id"]:_human_decision(candidate)}
            for kind in ("drop", "duplicate", "missing_bbox"):
                bad = copy.deepcopy(bundle)
                words = bad["pages"][0]["words"]
                if kind == "drop": words.pop(0)
                elif kind == "duplicate": words.append(copy.deepcopy(words[0]))
                else: words[0]["pdf_bbox"] = None
                with self.subTest(kind=kind),self.assertRaises(StructureError):
                    build_structure(document,ocr_bundle=bad)
            bad = copy.deepcopy(bundle)
            bad["pages"][0]["image_hash"] = "1"*64
            with self.assertRaises(StructureError):
                build_structure(document,ocr_bundle=bad,decisions=decisions)
            new = build_readings(document,ocr_bundle=bad)[0]
            fresh = next(c for c in new["alternatives"] if c["origin"] == "ocr")
            first = build_structure(document,ocr_bundle=bundle,decisions=decisions)
            second = build_structure(document,ocr_bundle=bad,
                                     decisions={new["page_id"]:_human_decision(fresh)},previous=first)
            self.assertEqual(first["readings"][0]["text"],second["readings"][0]["text"])
            self.assertEqual(second["readings"][0]["version"],2)
            self.assertNotEqual(first["units"][0]["unit_id"],second["units"][0]["unit_id"])

    def test_low_confidence_and_engine_provenance_survive(self):
        from scholarly_translation.source_reading import build_readings
        with tempfile.TemporaryDirectory() as tmp:
            document,bundle = self._document_and_bundle(Path(tmp))
            bundle["pages"][0]["words"][0]["confidence"] = 10
            bundle["pages"][0]["warnings"].append("low_confidence")
            reading = build_readings(document,ocr_bundle=bundle)[0]
            c = next(c for c in reading["alternatives"] if c["origin"] == "ocr")
            result = build_structure(document,ocr_bundle=bundle,
                                     decisions={reading["page_id"]:_human_decision(c)})
            self.assertIn("low_confidence",result["units"][0]["warnings"])
            self.assertEqual(c["provenance"]["engine_version"],bundle["engine_version"])
            self.assertEqual(c["anchors"][0]["confidence"],10)
            self.assertEqual(c["image"]["hash"],bundle["pages"][0]["image_hash"])

    def test_render_error_is_retained_and_never_selectable(self):
        from scholarly_translation.source_reading import build_readings
        with tempfile.TemporaryDirectory() as tmp:
            document,bundle = self._document_and_bundle(Path(tmp))
            page = bundle["pages"][0]
            page.update(transcription="",words=[],error={"code":"render_failed","message":"synthetic failure"},
                        image_uri=None,image_hash=None,image_width=None,image_height=None)
            page["warnings"].append("error")
            r = build_readings(document,ocr_bundle=bundle)[0]
            c = next(c for c in r["alternatives"] if c["origin"] == "ocr")
            self.assertFalse(c["usable"])
            self.assertEqual(c["error"]["code"],"render_failed")
            self.assertEqual(build_structure(document,ocr_bundle=bundle)["units"],[])
            with self.assertRaises(StructureError):
                build_structure(document,ocr_bundle=bundle,decisions={r["page_id"]:_human_decision(c)})


if __name__ == "__main__":
    unittest.main()
