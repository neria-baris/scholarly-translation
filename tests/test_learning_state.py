import unittest
import tempfile
from pathlib import Path

from scholarly_translation.learning_contracts import LearningError, new_learner, prepared_hash
from scholarly_translation.learning_state import apply_completion

LANGUAGE = "fr"


def _generated_chunk(plan_id="plan-one", content_hash="hash-one", item_ids=("fr-est",)):
    return {
        "schema_version": 1, "plan_id": plan_id, "response_version": 1, "provider": "test",
        "model": "test-model", "prompt_version": "v1", "input_hash": "input-hash",
        "edits": [{
            "unit_id": "unit-one", "start": 0, "end": 3, "original": "היה", "replacement": "était",
            "item_ids": list(item_ids), "grammar_ids": [], "gloss_he": "היה",
        }],
        "warnings": [], "coverage_item_ids": list(item_ids), "content_hash": content_hash,
    }


def _recap(chapter_id="chapter-one", chunk_hashes=("hash-one",), item_ids=("fr-est",)):
    return {
        "schema_version": 1, "chapter_id": chapter_id, "chunk_hashes": list(chunk_hashes),
        "vocabulary": [{"item_id": item_id, "gloss_he": "היה"} for item_id in item_ids],
        "grammar": [], "warnings": [],
    }


def _ready_session(learner, book_id="book-one", chunk_ids=("plan-one",), prep_hash="irrelevant"):
    return {
        "schema_version": 1, "session_id": "session-one", "learner_id": learner["learner_id"],
        "language": learner["language"], "book_id": book_id, "source_hash": "a" * 64,
        "base_learner_revision": learner["revision"], "policy_version": "learning-policy@1",
        "catalog_version": learner["catalog_version"], "level_id": learner["level_id"],
        "support_mode": learner["support_mode"], "status": "ready", "prepared_hash": prep_hash,
        "chunk_ids": list(chunk_ids), "read_cursor": None,
    }


def _ready_scenario():
    learner = dict(new_learner(language=LANGUAGE), active_book_id="book-one")
    chunk = _generated_chunk()
    recap = _recap()
    session = _ready_session(learner, prep_hash=prepared_hash([chunk], [recap]))
    session["prepared_hash"] = prepared_hash([chunk], [recap])
    return learner, session, chunk, recap















class LearningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_apply_completion_commits_items_and_increments_revision(self):
        learner, session, chunk, recap = _ready_scenario()
        new_learner_state, receipt = apply_completion(
            learner, session, [chunk], [recap], completion_id="c1", completed_at="2026-01-01T00:00:00Z",
        )
        assert new_learner_state["revision"] == learner["revision"] + 1
        assert new_learner_state["active_book_id"] is None
        items = {row["item_id"]: row for row in new_learner_state["items"]}
        assert items["fr-est"]["introduced_count"] == 1
        assert [b["completion_id"] for b in new_learner_state["completed_books"]] == ["c1"]
        assert receipt["previous_learner_revision"] == learner["revision"]
        assert receipt["next_learner_revision"] == new_learner_state["revision"]
        assert receipt["book_id"] == "book-one"


    def test_apply_completion_rejects_stale_base_revision(self):
        learner, session, chunk, recap = _ready_scenario()
        session = dict(session, base_learner_revision=learner["revision"] + 5)
        with self.assertRaises(LearningError) as exc:
            apply_completion(learner, session, [chunk], [recap], completion_id="c1", completed_at="t")
        assert exc.exception.code == "state_conflict"


    def test_apply_completion_rejects_non_ready_session(self):
        learner, session, chunk, recap = _ready_scenario()
        session = dict(session, status="preparing")
        with self.assertRaises(LearningError) as exc:
            apply_completion(learner, session, [chunk], [recap], completion_id="c1", completed_at="t")
        assert exc.exception.code == "state_conflict"


    def test_apply_completion_requires_full_recap_coverage(self):
        learner, session, chunk, recap = _ready_scenario()
        incomplete_recap = dict(recap, chunk_hashes=[])
        session = dict(session, prepared_hash=prepared_hash([chunk], [incomplete_recap]))
        with self.assertRaises(LearningError) as exc:
            apply_completion(learner, session, [chunk], [incomplete_recap], completion_id="c1", completed_at="t")
        assert exc.exception.code == "missing_recap"


    def test_apply_completion_rejects_prepared_hash_mismatch(self):
        learner, session, chunk, recap = _ready_scenario()
        session = dict(session, prepared_hash="not-the-real-hash")
        with self.assertRaises(LearningError) as exc:
            apply_completion(learner, session, [chunk], [recap], completion_id="c1", completed_at="t")
        assert exc.exception.code == "state_conflict"


    def test_apply_completion_rejects_reused_completion_id_in_learner_history(self):
        learner, session, chunk, recap = _ready_scenario()
        learner = dict(learner, completed_books=[
            {"book_id": "book-zero", "prepared_hash": "x" * 10, "completion_id": "c1"},
        ])
        with self.assertRaises(LearningError) as exc:
            apply_completion(learner, session, [chunk], [recap], completion_id="c1", completed_at="t")
        assert exc.exception.code == "state_conflict"


    def test_apply_completion_continuity_second_book_unions_and_increments(self):
        learner, session, chunk, recap = _ready_scenario()
        learner_after_first, _ = apply_completion(
            learner, session, [chunk], [recap], completion_id="c1", completed_at="t1",
        )

        second_learner = dict(learner_after_first, active_book_id="book-two")
        second_chunk = _generated_chunk(plan_id="plan-two", content_hash="hash-two", item_ids=("fr-est", "fr-je"))
        second_recap = _recap(chunk_hashes=("hash-two",), item_ids=("fr-est", "fr-je"))
        second_session = _ready_session(
            second_learner, book_id="book-two", chunk_ids=("plan-two",),
            prep_hash=prepared_hash([second_chunk], [second_recap]),
        )

        final_learner, receipt = apply_completion(
            second_learner, second_session, [second_chunk], [second_recap],
            completion_id="c2", completed_at="t2",
        )
        items = {row["item_id"]: row for row in final_learner["items"]}
        assert items["fr-est"]["introduced_count"] == 2
        assert items["fr-je"]["introduced_count"] == 1
        book_ids = {b["book_id"] for b in final_learner["completed_books"]}
        assert book_ids == {"book-one", "book-two"}
