"""Tests for the "digital-text" EPUB source-evidence schema extension
(audit/contracts/session_epub_digital_text_schema.md): epub_extract.py's
Document/Page/Segment construction, source_reading.py's new "digital-text"
candidate/anchor shape, document_structure.py building nodes directly from
EPUB-encoded node_kind/node_level, and the end-to-end acceptance proof that
translation.build_translation_request succeeds for an EPUB-derived unit.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from test_export_epub import make_epub

from scholarly_translation.document_structure import NODE_KINDS
from scholarly_translation.epub_extract import EpubExtractionError, extract_epub
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.records import Document, Page, Segment
from scholarly_translation.segmentation import build_structure, validate_structure
from scholarly_translation.source_reading import StructureError, build_readings
from scholarly_translation.store import deterministic_id
from scholarly_translation.translation import build_translation_request


def _human_decision(candidate, reason="verified EPUB digital-text extraction") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _decisions_for(document):
    readings = build_readings(document)
    decisions = {}
    for page in document.pages:
        reading = next(r for r in readings if r["page_id"] == page.page_id)
        candidate = reading["alternatives"][0]
        decisions[page.page_id] = _human_decision(candidate)
    return decisions


def _build_epub_structure(path, unit_policy=None):
    document = extract_epub(path, language="en")
    structure = build_structure(document, decisions=_decisions_for(document), unit_policy=unit_policy)
    return document, structure


def _synthetic_epub_document(language, blocks):
    """blocks: list of (text, node_kind, node_level) for a single chapter/page.
    Mirrors epub_extract.extract_epub's own Segment/Page construction, but
    lets a test inject a node_kind that extract_epub itself would never
    produce (to prove document_structure.py rejects it rather than guessing)."""
    document_id = deterministic_id("epub-synthetic-source", language, str(len(blocks)))
    page_id = deterministic_id(document_id, "page", "1")
    segments, parts, offset = [], [], 0
    for i, (text, kind, level) in enumerate(blocks, start=1):
        if i > 1:
            parts.append("\n")
            offset += 1
        start = offset
        end = start + len(text)
        parts.append(text)
        offset = end
        segments.append(Segment(
            segment_id=deterministic_id(page_id, "segment", str(i)), page_id=page_id,
            order=i, text=text, source_char_start=start, source_char_end=end,
            node_kind=kind, node_level=level,
        ))
    page = Page(page_id=page_id, document_id=document_id, page_number=1, segments=segments,
                width=None, height=None, source_text="".join(parts))
    return Document(
        schema_version=3, document_id=document_id, document_version=1, language=language,
        source_kind="epub", source_uri="urn:test:synthetic-epub", pages=[page],
        stage_id="digital-text-epub", stage_version=1,
        input_hash=hashlib.sha256(b"synthetic-epub-fixture").hexdigest(),
        status="needs_human", warnings=[],
    )


class EpubExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)

    def test_extracted_document_is_schema3_epub_with_no_geometry(self):
        document = extract_epub(self.path, language="en")
        self.assertEqual(document.schema_version, 3)
        self.assertEqual(document.source_kind, "epub")
        self.assertEqual(document.stage_id, "digital-text-epub")
        self.assertEqual(document.stage_version, 1)
        self.assertEqual(len(document.pages), 2)  # two spine chapters
        for page in document.pages:
            self.assertIsNone(page.width)
            self.assertIsNone(page.height)
            for segment in page.segments:
                self.assertIsNone(segment.bbox)
                self.assertIsNotNone(segment.node_kind)

    def test_invalid_input_raises_local_error_without_page_content(self):
        bad_path = Path(self.tmp.name) / "broken.epub"
        bad_path.write_bytes(b"not a real epub")
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(bad_path, language="en")
        self.assertNotIn("Traceback", str(ctx.exception))

    def test_empty_bytes_rejected(self):
        with self.assertRaises(EpubExtractionError):
            extract_epub(b"", language="en")


class DigitalTextCandidateShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)
        self.document = extract_epub(self.path, language="en")

    def test_candidate_origin_and_geometry_absence(self):
        reading = build_readings(self.document)[0]
        self.assertEqual(len(reading["alternatives"]), 1)
        candidate = reading["alternatives"][0]
        self.assertEqual(candidate["origin"], "digital-text")
        self.assertIsNone(candidate["pdf_width"])
        self.assertIsNone(candidate["pdf_height"])
        self.assertEqual(candidate["provenance"]["stage"], "digital-text-epub@1")
        self.assertTrue(candidate["usable"])

    def test_anchor_shape_has_no_bbox_and_carries_node_kind_level(self):
        reading = build_readings(self.document)[0]
        candidate = reading["alternatives"][0]
        self.assertTrue(candidate["anchors"])
        for anchor in candidate["anchors"]:
            self.assertEqual(anchor["kind"], "block")
            self.assertEqual(set(anchor), {
                "kind", "source_char_start", "source_char_end",
                "segment_id", "region_id", "node_kind", "node_level",
            })
            self.assertNotIn("bbox", anchor)
            self.assertIsInstance(anchor["node_kind"], str)

    def test_ocr_bundle_rejected_for_epub_documents(self):
        with self.assertRaises(StructureError):
            build_readings(self.document, ocr_bundle={"schema_version": 1, "stage": "local-ocr@1"})


class EpubStructureNodeMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)

    def test_node_kinds_and_levels_match_fixture_tags_not_a_classify_line_guess(self):
        document, structure = _build_epub_structure(self.path)
        by_text = {n["text"]: (n["kind"], n["level"]) for n in structure["nodes"]}
        # chapter0: h1, three <p> blocks (one of them inside the figure div)
        self.assertEqual(by_text["Chapter Zero"], ("heading", 5))
        self.assertEqual(by_text["A plain paragraph with no inline markup."], ("paragraph", None))
        self.assertEqual(by_text["Figure caption text."], ("paragraph", None))
        # chapter1: h2, p, two <li>, blockquote
        self.assertEqual(by_text["Chapter One"], ("subheading", 6))
        self.assertEqual(by_text["Target paragraph for the internal link."], ("paragraph", None))
        self.assertEqual(by_text["First item"], ("list", None))
        self.assertEqual(by_text["Second item"], ("list", None))
        self.assertEqual(by_text["A quoted passage."], ("quotation", None))
        validate_structure(structure)

    def test_units_and_unit_node_links_are_valid_schema2(self):
        document, structure = _build_epub_structure(self.path)
        self.assertEqual(structure["schema_version"], 2)
        self.assertEqual(structure["pdf_hash"], document.input_hash)
        self.assertTrue(structure["units"])
        self.assertEqual(structure["continuity"], [])
        node_ids = {n["node_id"] for n in structure["nodes"]}
        for link in structure["unit_node_links"]:
            self.assertTrue(set(link["node_ids"]) <= node_ids)
        validate_structure(structure)


class InvalidNodeKindRejectionTests(unittest.TestCase):
    def test_unrecognized_node_kind_raises_structure_error_not_silently_accepted(self):
        document = _synthetic_epub_document("en", [("A heading of sorts.", "not_a_real_node_kind", None)])
        decisions = _decisions_for(document)
        with self.assertRaises(StructureError):
            build_structure(document, decisions=decisions)

    def test_valid_node_kinds_from_full_vocabulary_are_accepted(self):
        document = _synthetic_epub_document("en", [("A paragraph.", "paragraph", None)])
        self.assertIn("paragraph", NODE_KINDS)
        decisions = _decisions_for(document)
        structure = build_structure(document, decisions=decisions)
        self.assertEqual(structure["nodes"][0]["kind"], "paragraph")
        validate_structure(structure)


class TranslationRequestAcceptanceTests(unittest.TestCase):
    """The concrete proof that the original blocking error -- every reading
    candidate must carry stage == digital-pdf@1 plus positive pdf_width/
    pdf_height -- no longer applies to EPUB input."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)

    def test_build_translation_request_succeeds_for_epub_derived_unit(self):
        document, structure = _build_epub_structure(self.path)
        unit = structure["units"][0]
        request = build_translation_request(
            structure, new_glossary_store(), unit["unit_id"],
            "scholarly", "mock", "mock-translation-1",
        )
        self.assertEqual(request.source_language, "en")
        self.assertEqual(request.unit["unit_id"], unit["unit_id"])
        self.assertTrue(request.prompt_text)
        self.assertTrue(request.cache_key)

    def test_build_translation_request_succeeds_for_every_unit(self):
        document, structure = _build_epub_structure(self.path)
        for unit in structure["units"]:
            with self.subTest(unit_id=unit["unit_id"]):
                request = build_translation_request(
                    structure, new_glossary_store(), unit["unit_id"],
                    "scholarly", "mock", "mock-translation-1",
                )
                self.assertEqual(request.unit["unit_id"], unit["unit_id"])


if __name__ == "__main__":
    unittest.main()
