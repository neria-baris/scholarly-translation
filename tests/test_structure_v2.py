import copy
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.document_structure import classify_line, _split_oversized, _word_count
from scholarly_translation.segmentation import (
    _build_structure_v1, build_structure, check_continuity, validate_structure,
)
from scholarly_translation.source_reading import StructureError


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


def _build_lines_fixture(path, lines) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    y = height - 100
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()


def _build_pages_fixture(path, pages) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    for lines in pages:
        y = height - 100
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()


def _extract_and_resolve(lines):
    tmp = tempfile.TemporaryDirectory()
    tmp_path = Path(tmp.name)
    pdf_path = tmp_path / "fixture.pdf"
    _build_lines_fixture(pdf_path, lines)
    document = extract_pdf(pdf_path, language="en")
    page = document.pages[0]
    candidate = _digital_candidate_for(document, page.page_id)
    decisions = {page.page_id: _human_decision(candidate)}
    return tmp, document, page, candidate, decisions


class ParagraphReconstructionTests(unittest.TestCase):
    def test_wrapped_lines_merge_into_one_paragraph_node_with_exact_span(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve([
            "This sentence continues onto the next visual line without",
            "ending punctuation, demonstrating paragraph reconstruction across lines.",
        ])
        with tmp:
            structure = build_structure(document, decisions=decisions)
            self.assertEqual(len(structure["nodes"]), 1)
            node = structure["nodes"][0]
            self.assertEqual(node["kind"], "paragraph")
            self.assertEqual(node["text"], candidate["text"])
            self.assertTrue(node["text"].endswith("lines."))
            self.assertIn("\n", node["text"])
            for anchor in node["anchors"]:
                self.assertEqual(anchor["kind"], "line")
            validate_structure(structure)

    def test_sentence_final_line_does_not_merge_with_next_paragraph(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve([
            "A complete sentence that ends here.",
            "A second complete sentence that also ends here.",
        ])
        with tmp:
            structure = build_structure(document, decisions=decisions)
            self.assertEqual(len(structure["nodes"]), 2)
            self.assertTrue(all(n["kind"] == "paragraph" for n in structure["nodes"]))


class MultilingualHeuristicTests(unittest.TestCase):
    def test_french_and_japanese_markers_are_conservative_structural_kinds(self):
        self.assertEqual(classify_line("Partie I")[0], "part")
        self.assertEqual(classify_line("Chapitre 2")[0], "chapter")
        self.assertEqual(classify_line("Tableau 3")[0], "caption")
        self.assertEqual(classify_line("第三章 方法")[0], "chapter")
        self.assertEqual(classify_line("図2")[0], "caption")

    def test_japanese_size_heuristic_and_sentence_boundary_do_not_require_spaces(self):
        text = "第一の文です。第二の文です。"
        self.assertGreater(_word_count(text), 10)
        spans = _split_oversized(text, 0, len(text), 8)
        self.assertEqual(len(spans), 2)
        self.assertEqual("".join(text[start:end] for start, end in spans), text)


class LogicalNodeCoverageTests(unittest.TestCase):
    def test_distinct_kinds_classified_in_deterministic_order_without_loss(self):
        lines = [
            "Part One",
            "Chapter One",
            "Section 2 Overview",
            "1.1 Scope and method",
            "A Note On Method",
            "Subheading Detailed implications",
            "***",
            "- First item in a short list",
            '"A quoted line in full."',
            "Figure 1: Diagram of the apparatus.",
            "Smith, J. (2020). A study of things.",
            "[2] A footnote body sentence.",
            "E = mc^2",
            "99",
            "An ordinary paragraph sentence that ends here.",
        ]
        tmp, document, page, candidate, decisions = _extract_and_resolve(lines)
        with tmp:
            structure = build_structure(document, decisions=decisions)
            kinds = [n["kind"] for n in structure["nodes"]]
            self.assertEqual(kinds, [
                "part", "chapter", "section", "subsection", "heading", "subheading",
                "scene_break", "list", "quotation",
                "caption", "bibliography_entry", "note", "formula", "page_furniture", "paragraph",
            ])
            self.assertEqual([n["order"] for n in structure["nodes"]],
                             list(range(1, len(structure["nodes"]) + 1)))
            by_kind = {n["kind"]: n for n in structure["nodes"]}
            self.assertEqual(by_kind["chapter"]["parent_node_id"], by_kind["part"]["node_id"])
            self.assertEqual(by_kind["section"]["parent_node_id"], by_kind["chapter"]["node_id"])
            self.assertEqual(by_kind["subsection"]["parent_node_id"], by_kind["section"]["node_id"])
            self.assertEqual(by_kind["subheading"]["parent_node_id"], by_kind["heading"]["node_id"])
            spans = sorted((n["source_char_start"], n["source_char_end"]) for n in structure["nodes"])
            for i in range(1, len(spans)):
                self.assertLessEqual(spans[i - 1][1], spans[i][0])
            self.assertEqual(structure["continuity"], [])
            self.assertEqual(structure["unit_policy"],
                             {"version": "semantic-units@1", "max_unit_words": 2000})
            node_ids = {node["node_id"] for node in structure["nodes"]}
            self.assertEqual({link["unit_id"] for link in structure["unit_node_links"]},
                             {unit["unit_id"] for unit in structure["units"]})
            self.assertTrue(all(link["node_ids"] and set(link["node_ids"]) <= node_ids
                                for link in structure["unit_node_links"]))
            validate_structure(structure)

    def test_document_reading_order_and_hierarchy_cross_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "two-pages.pdf"
            _build_pages_fixture(pdf_path, [
                ["Chapter One", "Opening paragraph ends here."],
                ["Continuation paragraph on page two."],
            ])
            document = extract_pdf(pdf_path, language="en")
            decisions = {}
            for page in document.pages:
                decisions[page.page_id] = _human_decision(_digital_candidate_for(document, page.page_id))
            structure = build_structure(document, decisions=decisions)
            nodes = structure["nodes"]
            self.assertEqual([node["order"] for node in nodes], list(range(1, len(nodes) + 1)))
            self.assertEqual([node["page_id"] for node in nodes],
                             [document.pages[0].page_id, document.pages[0].page_id,
                              document.pages[1].page_id])
            chapter = nodes[0]
            self.assertEqual(nodes[-1]["parent_node_id"], chapter["node_id"])
            validate_structure(structure)


class SemanticUnitBoundaryTests(unittest.TestCase):
    def test_structural_boundary_preferred_over_word_target(self):
        lines = [
            "Chapter One",
            "Short paragraph number one here.",
            "Short paragraph number two here.",
            "Short paragraph number three here.",
            "Chapter Two",
            "Final paragraph after second heading.",
        ]
        tmp, document, page, candidate, decisions = _extract_and_resolve(lines)
        with tmp:
            structure = build_structure(document, decisions=decisions, unit_policy={"max_unit_words": 200})
            texts = [u["text"] for u in structure["units"]]
            self.assertEqual(len(texts), 4)
            merged = next(t for t in texts if "number one" in t)
            self.assertIn("number two", merged)
            self.assertIn("number three", merged)
            self.assertNotIn("Final paragraph", merged)
            self.assertTrue(any(t == "Chapter One" for t in texts))
            self.assertTrue(any(t == "Chapter Two" for t in texts))
            self.assertEqual(structure["continuity"], [])
            validate_structure(structure)

    def test_oversized_group_splits_at_strongest_internal_boundary(self):
        lines = [
            "This is the first sentence. This is the second sentence continuing",
            "across the wrap boundary and it keeps going for many more words",
            "to exceed the target threshold nicely.",
        ]
        tmp, document, page, candidate, decisions = _extract_and_resolve(lines)
        with tmp:
            structure = build_structure(document, decisions=decisions, unit_policy={"max_unit_words": 15})
            self.assertEqual(len(structure["nodes"]), 1)
            units = sorted(structure["units"], key=lambda u: u["source_char_start"])
            self.assertEqual(len(units), 2)
            self.assertTrue(units[0]["text"].endswith("sentence."))
            self.assertTrue(units[1]["text"].lstrip().startswith("This is the second"))
            self.assertEqual(units[0]["source_char_end"], units[1]["source_char_start"])
            self.assertEqual(
                units[0]["text"] + units[1]["text"],
                candidate["text"][units[0]["source_char_start"]:units[1]["source_char_end"]],
            )
            self.assertEqual(structure["continuity"], [])
            validate_structure(structure)

    def test_invalid_unit_policy_rejected(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve(["A single plain sentence."])
        with tmp:
            with self.assertRaises(StructureError):
                build_structure(document, decisions=decisions, unit_policy={"max_unit_words": 0})
            with self.assertRaises(StructureError):
                build_structure(document, decisions=decisions, unit_policy={"other": 1})


class UnresolvedReadingTests(unittest.TestCase):
    def test_unresolved_reading_has_no_nodes_or_units(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve(["Some body text here."])
        with tmp:
            structure = build_structure(document)
            self.assertEqual(structure["readings"][0]["status"], "unresolved")
            self.assertEqual(structure["nodes"], [])
            self.assertEqual(structure["units"], [])
            validate_structure(structure)


class LegacySchemaAcceptanceTests(unittest.TestCase):
    def test_legacy_schema1_artifact_validated_and_not_fabricated(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve([
            "Main text with a footnote marker [1].",
            "[1] Footnote body text.",
        ])
        with tmp:
            legacy = _build_structure_v1(document, decisions=decisions)
            self.assertEqual(legacy["schema_version"], 1)
            validate_structure(legacy)

            upgraded = build_structure(document, decisions=decisions, previous=legacy)
            self.assertEqual(upgraded["schema_version"], 2)
            self.assertIsNotNone(upgraded["legacy_predecessor_hash"])
            self.assertIsNone(upgraded["revision"]["parent_revision"])
            self.assertEqual(upgraded["history"], [])
            self.assertTrue(all(u["predecessor_unit_ids"] == [] for u in upgraded["units"]))
            self.assertTrue(all(n["predecessor_node_ids"] == [] for n in upgraded["nodes"]))
            validate_structure(upgraded)


class PdfPathUnaffectedByEpubSchemaExtensionTests(unittest.TestCase):
    """audit/contracts/session_epub_digital_text_schema.md acceptance check:
    the full existing PDF acceptance path is byte-for-byte unaffected by the
    new "digital-text" origin -- same candidate/anchor shape, same errors,
    same hashes."""

    def test_pdf_digital_candidate_shape_and_geometry_unchanged(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve(["A single plain sentence."])
        with tmp:
            self.assertEqual(candidate["origin"], "digital")
            self.assertEqual(candidate["provenance"], {
                "base_extraction_hash": candidate["provenance"]["base_extraction_hash"],
                "stage": "digital-pdf@1",
            })
            self.assertGreater(candidate["pdf_width"], 0)
            self.assertGreater(candidate["pdf_height"], 0)
            for anchor in candidate["anchors"]:
                self.assertEqual(set(anchor), {
                    "kind", "source_char_start", "source_char_end",
                    "segment_id", "region_id", "bbox",
                })
                self.assertEqual(anchor["kind"], "line")
                self.assertNotIn("node_kind", anchor)
                self.assertNotIn("node_level", anchor)
            structure = build_structure(document, decisions=decisions)
            validate_structure(structure)
            self.assertEqual(structure["nodes"][0]["kind"], "paragraph")

    def test_unknown_source_kind_still_rejected(self):
        from scholarly_translation.records import Document, Page, Segment
        import hashlib
        document_id = "doc-1"
        page_id = "page-1"
        segment = Segment(segment_id="seg-1", page_id=page_id, order=1, text="x",
                          source_char_start=0, source_char_end=1)
        page = Page(page_id=page_id, document_id=document_id, page_number=1,
                   segments=[segment], source_text="x")
        document = Document(
            schema_version=3, document_id=document_id, document_version=1, language="en",
            source_kind="docx", source_uri="urn:test:docx", pages=[page],
            input_hash=hashlib.sha256(b"x").hexdigest(),
        )
        from scholarly_translation.source_reading import build_readings
        with self.assertRaises(StructureError):
            build_readings(document)


class PersistedSchema2ValidationTests(unittest.TestCase):
    def test_hierarchy_policy_and_unit_node_link_tampering_is_rejected(self):
        tmp, document, page, candidate, decisions = _extract_and_resolve([
            "Chapter One", "A complete paragraph sentence.",
        ])
        with tmp:
            structure = build_structure(document, decisions=decisions)
            mutations = []

            bad_parent = copy.deepcopy(structure)
            bad_parent["nodes"][1]["parent_node_id"] = "unknown-node"
            mutations.append(bad_parent)

            bad_order = copy.deepcopy(structure)
            bad_order["nodes"][1]["order"] = bad_order["nodes"][0]["order"]
            mutations.append(bad_order)

            bad_link = copy.deepcopy(structure)
            bad_link["unit_node_links"][0]["node_ids"] = ["unknown-node"]
            mutations.append(bad_link)

            bad_policy = copy.deepcopy(structure)
            bad_policy["unit_policy"]["max_unit_words"] = 0
            mutations.append(bad_policy)

            for bad in mutations:
                with self.subTest(keys=set(bad)):
                    with self.assertRaises(StructureError):
                        validate_structure(bad)


if __name__ == "__main__":
    unittest.main()
