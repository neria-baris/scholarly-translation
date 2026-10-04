"""Cross-chapter persistent translation state (Session D extension).

Covers: versioned store shape/validation, propose/commit mechanics,
contradiction detection, the "a model-derived item can never silently
become established" rule, source-backing requirements, certainty levels,
reproducibility across revisions, and integration into translation.py's
prompt/cache/provenance (the PERSISTENT DOCUMENT STATE layer).
"""
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation import document_state as ds
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.model_config import ModelCapabilities
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.source_reading import build_readings
from scholarly_translation.translation import TranslationRequestError, build_translation_request


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _single_page_structure(tmp_path, lines, unit_policy=None):
    pdf_path = tmp_path / "fixture.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    y = height - 100
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()
    document = extract_pdf(pdf_path, language="en")
    page = document.pages[0]
    reading = build_readings(document)[0]
    candidate = next(cnd for cnd in reading["alternatives"] if cnd["origin"] == "digital")
    decisions = {page.page_id: _human_decision(candidate)}
    return build_structure(document, decisions=decisions, unit_policy=unit_policy)


CHAPTER_LINES = [
    "Chapter One",
    "Alpha sentence introduces the topic.",
    "Beta sentence continues the discussion further.",
    "Gamma sentence is the target unit here today.",
]


def _source_ref(structure, unit, document_id, chapter_node_id):
    return {
        "chapter_node_id": chapter_node_id, "unit_ids": [unit["unit_id"]], "document_id": document_id,
        "source_char_start": unit["source_char_start"], "source_char_end": unit["source_char_end"],
    }


class DocumentStateShapeTests(unittest.TestCase):
    def test_new_store_is_empty_and_valid(self):
        state = ds.new_document_state("doc-1")
        ds.validate_document_state(state)
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["items"], [])

    def test_bad_document_id_rejected(self):
        with self.assertRaises(ds.DocumentStateError):
            ds.new_document_state("")

    def test_propose_rejects_unsupported_category(self):
        with self.assertRaises(ds.DocumentStateError):
            ds.propose_item(
                category="not-a-real-category", label="X", value="Y", certainty="established",
                source={"chapter_node_id": "c1", "unit_ids": ["u1"], "document_id": "d1",
                        "source_char_start": 0, "source_char_end": 1},
                reason="test",
            )

    def test_propose_rejects_bad_certainty(self):
        with self.assertRaises(ds.DocumentStateError):
            ds.propose_item(
                category="character", label="X", value="Y", certainty="definitely",
                source={"chapter_node_id": "c1", "unit_ids": ["u1"], "document_id": "d1",
                        "source_char_start": 0, "source_char_end": 1},
                reason="test",
            )


class CommitUpdateTests(unittest.TestCase):
    def setUp(self):
        self.state = ds.new_document_state("doc-1")
        self.source = {"chapter_node_id": "chapter-1", "unit_ids": ["unit-1"], "document_id": "doc-1",
                       "source_char_start": 0, "source_char_end": 10}

    def test_commit_single_item_bumps_revision_and_version(self):
        candidate = ds.propose_item(
            category="character", label="Elena", value="Established Hebrew spelling: אלנה.",
            certainty="established", source=self.source, reason="named on first appearance",
        )
        new_state = ds.commit_update(
            self.state, [candidate], chapter_node_id="chapter-1",
            actor="editor@example.org", actor_kind="human", reason="chapter 1 QA pass",
        )
        self.assertEqual(new_state["revision"], 1)
        self.assertEqual(len(new_state["items"]), 1)
        item = new_state["items"][0]
        self.assertEqual(item["version"], 1)
        self.assertIsNone(item["prior_version"])
        self.assertEqual(item["certainty"], "established")

    def test_model_derived_item_cannot_be_established(self):
        candidate = ds.propose_item(
            category="character", label="Elena", value="Possibly the narrator's sister.",
            certainty="established", source=self.source, reason="inferred from dialogue",
        )
        with self.assertRaises(ds.DocumentStateError):
            ds.commit_update(
                self.state, [candidate], chapter_node_id="chapter-1",
                actor="semantic-reviewer-model", actor_kind="model", reason="chapter QA candidate",
            )

    def test_model_derived_item_can_be_likely_or_unresolved(self):
        candidate = ds.propose_item(
            category="character", label="Elena", value="Possibly the narrator's sister.",
            certainty="likely", source=self.source, reason="inferred from dialogue",
        )
        new_state = ds.commit_update(
            self.state, [candidate], chapter_node_id="chapter-1",
            actor="semantic-reviewer-model", actor_kind="model", reason="chapter QA candidate",
        )
        self.assertEqual(new_state["items"][0]["certainty"], "likely")

    def test_updating_same_key_creates_new_version_not_a_new_item_id(self):
        first = ds.propose_item(
            category="terminology", label="logos", value="לוגוס (transliterated)",
            certainty="established", source=self.source, reason="first approved rendering",
        )
        state1 = ds.commit_update(
            self.state, [first], chapter_node_id="chapter-1",
            actor="editor@example.org", actor_kind="human", reason="chapter 1",
        )
        second = ds.propose_item(
            category="terminology", label="logos", value="לוגוס (refined, consistent with ch.3)",
            certainty="established", source=self.source, reason="refined after chapter 3",
        )
        state2 = ds.commit_update(
            state1, [second], chapter_node_id="chapter-3",
            actor="editor@example.org", actor_kind="human", reason="chapter 3 refinement",
            acknowledged_contradictions=(("terminology", "logos"),),
        )
        rows = [r for r in state2["items"] if r["label"] == "logos"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["item_id"] for r in rows}, {rows[0]["item_id"]})  # same item_id, two versions
        self.assertEqual([r["version"] for r in rows], [1, 2])
        self.assertEqual(rows[1]["prior_version"], 1)
        # Historical reproducibility: revision 1's view is still reconstructible.
        state1_latest = {r["label"]: r["value"] for r in state1["items"]}
        self.assertEqual(state1_latest["logos"], "לוגוס (transliterated)")

    def test_contradiction_is_detected_and_blocks_silent_overwrite(self):
        first = ds.propose_item(
            category="terminology", label="logos", value="לוגוס-א",
            certainty="established", source=self.source, reason="first approved rendering",
        )
        state1 = ds.commit_update(
            self.state, [first], chapter_node_id="chapter-1",
            actor="editor@example.org", actor_kind="human", reason="chapter 1",
        )
        conflicting = ds.propose_item(
            category="terminology", label="logos", value="לוגוס-ב",
            certainty="established", source=self.source, reason="different later rendering",
        )
        conflicts = ds.find_conflicts(state1, [conflicting])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["existing_value"], "לוגוס-א")
        with self.assertRaises(ds.DocumentStateError):
            ds.commit_update(
                state1, [conflicting], chapter_node_id="chapter-2",
                actor="editor@example.org", actor_kind="human", reason="attempted silent change",
            )
        # Explicitly acknowledging the contradiction allows the versioned update through.
        state2 = ds.commit_update(
            state1, [conflicting], chapter_node_id="chapter-2",
            actor="editor@example.org", actor_kind="human", reason="deliberate correction",
            acknowledged_contradictions=(("terminology", "logos"),),
        )
        self.assertEqual(state2["revision"], 2)

    def test_source_reference_is_required_and_validated(self):
        with self.assertRaises(ds.DocumentStateError):
            ds.propose_item(
                category="character", label="Elena", value="x", certainty="established",
                source={"chapter_node_id": "", "unit_ids": [], "document_id": "doc-1",
                        "source_char_start": 0, "source_char_end": 1},
                reason="test",
            )

    def test_commit_requires_at_least_one_candidate(self):
        with self.assertRaises(ds.DocumentStateError):
            ds.commit_update(
                self.state, [], chapter_node_id="chapter-1",
                actor="editor@example.org", actor_kind="human", reason="empty",
            )

    def test_store_stays_small_not_a_growing_story_bible(self):
        # MAX_ITEMS bounds the store; this does not attempt to actually
        # reach the bound (too slow) but documents/asserts the constant
        # exists and is small, not unbounded.
        self.assertLessEqual(ds.MAX_ITEMS, 2000)


class TranslationIntegrationTests(unittest.TestCase):
    """document_state wired into build_translation_request's PERSISTENT
    DOCUMENT STATE layer, prompt rendering, provenance and cache identity."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.target = next(u for u in self.structure["units"] if u["text"].startswith("Gamma"))
        self.glossary = new_glossary_store()
        self.document_id = self.structure["document_id"]
        chapter_unit = next(u for u in self.structure["units"] if u["text"] == "Chapter One")
        link = next(l for l in self.structure["unit_node_links"] if l["unit_id"] == chapter_unit["unit_id"])
        self.chapter_node_id = link["node_ids"][0]

    def tearDown(self):
        self.tmp.cleanup()

    def _state_with_one_item(self):
        state = ds.new_document_state(self.document_id)
        candidate = ds.propose_item(
            category="terminology", label="gamma", value="גמא (approved transliteration)",
            certainty="established",
            source={"chapter_node_id": self.chapter_node_id, "unit_ids": [self.target["unit_id"]],
                    "document_id": self.document_id, "source_char_start": self.target["source_char_start"],
                    "source_char_end": self.target["source_char_end"]},
            reason="approved in chapter 1",
        )
        return ds.commit_update(
            state, [candidate], chapter_node_id=self.chapter_node_id,
            actor="editor@example.org", actor_kind="human", reason="chapter 1 QA pass",
        )

    def test_no_document_state_is_unchanged_default(self):
        request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        self.assertIsNone(request.document_state)
        self.assertEqual(request.document_state_version, 0)
        self.assertEqual(request.document_state_fingerprint, "")
        self.assertNotIn("Persistent document state", request.prompt_text)

    def test_document_state_appears_as_its_own_labelled_layer(self):
        state = self._state_with_one_item()
        request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state,
        )
        self.assertIn("Persistent document state (revision 1", request.prompt_text)
        self.assertIn("גמא (approved transliteration)", request.prompt_text)
        self.assertIn("established", request.prompt_text)
        # Still inside the existing, fixed glossary/decisions section (render_prompt
        # itself is out of this contract's scope to change) -- appears after that
        # marker and before LOCAL_STATE.
        glossary_index = request.prompt_text.index("GLOSSARY_AND_APPROVED_DECISIONS:")
        state_index = request.prompt_text.index("Persistent document state")
        local_state_index = request.prompt_text.index("LOCAL_STATE:")
        self.assertTrue(glossary_index < state_index < local_state_index)

    def test_document_state_must_belong_to_the_same_document(self):
        other_state = ds.new_document_state("a-completely-different-document")
        with self.assertRaises(TranslationRequestError):
            build_translation_request(
                self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
                document_state=other_state,
            )

    def test_provenance_records_document_state_version_and_fingerprint(self):
        state = self._state_with_one_item()
        request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state,
        )
        metadata = request.to_metadata_dict()
        self.assertEqual(metadata["document_state_version"], 1)
        self.assertEqual(metadata["document_state_version"], request.document_state_version)
        self.assertEqual(metadata["document_state_fingerprint"], ds.effective_fingerprint(state))

    def test_cache_key_changes_when_document_state_changes_but_not_otherwise(self):
        baseline = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        state = self._state_with_one_item()
        with_state = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state,
        )
        self.assertNotEqual(baseline.cache_key, with_state.cache_key)

        # Rebuilding against the exact same state revision is stable/reproducible.
        again = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state,
        )
        self.assertEqual(with_state.cache_key, again.cache_key)

    def test_later_state_revision_does_not_disturb_earlier_revisions_cache_key(self):
        """A later persistent-state update must not retroactively change the
        cache key recorded for a unit translated against an earlier
        revision -- historical reproducibility is preserved."""
        state_v1 = self._state_with_one_item()
        request_v1 = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state_v1,
        )

        candidate2 = ds.propose_item(
            category="character", label="Narrator", value="First-person retrospective narrator.",
            certainty="established",
            source={"chapter_node_id": self.chapter_node_id, "unit_ids": [self.target["unit_id"]],
                    "document_id": self.document_id, "source_char_start": self.target["source_char_start"],
                    "source_char_end": self.target["source_char_end"]},
            reason="established in chapter 2",
        )
        state_v2 = ds.commit_update(
            state_v1, [candidate2], chapter_node_id=self.chapter_node_id,
            actor="editor@example.org", actor_kind="human", reason="chapter 2 QA pass",
        )
        self.assertEqual(state_v2["revision"], 2)

        # Rebuilding the identical v1-based request after v2 exists elsewhere
        # reproduces the exact same cache key -- v2 did not retroactively
        # invalidate or alter it.
        request_v1_again = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state_v1,
        )
        self.assertEqual(request_v1.cache_key, request_v1_again.cache_key)

        request_v2 = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state_v2,
        )
        self.assertNotEqual(request_v1.cache_key, request_v2.cache_key)

    def test_run_translation_round_trips_with_document_state(self):
        from scholarly_translation.translation import run_translation
        state = self._state_with_one_item()
        request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            document_state=state,
        )
        draft = run_translation(request)
        self.assertFalse(draft["approved"])
        self.assertEqual(draft["document_state_version"], 1)


if __name__ == "__main__":
    unittest.main()
