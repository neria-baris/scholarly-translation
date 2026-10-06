import json

import unittest
import tempfile
from pathlib import Path

from scholarly_translation.learning_contracts import LearningError, fixture_source, prepared_hash
from scholarly_translation.learning_store import LearningStore


def _chunk(plan_id="plan-one", content_hash="hash-one"):
    return {
        "schema_version": 1, "plan_id": plan_id, "response_version": 1, "provider": "test",
        "model": "test-model", "prompt_version": "v1", "input_hash": "input-hash",
        "edits": [{
            "unit_id": "unit-one", "start": 0, "end": 3, "original": "היה", "replacement": "était",
            "item_ids": ["fr-est"], "grammar_ids": [], "gloss_he": "היה",
        }],
        "warnings": [], "coverage_item_ids": ["fr-est"], "content_hash": content_hash,
    }


def _recap(chunk_hashes=("hash-one",)):
    return {
        "schema_version": 1, "chapter_id": "chapter-one", "chunk_hashes": list(chunk_hashes),
        "vocabulary": [{"item_id": "fr-est", "gloss_he": "היה"}], "grammar": [], "warnings": [],
    }

















class LearningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_completion_receipt_cannot_complete_another_book(self):
        store = LearningStore(Path(self._tmp.name))
        first = fixture_source('book-one')
        store.save_source(first)
        session = store.create_session(first, store.get_learner())
        ready = store.save_prepared(session['session_id'], [_chunk()], [_recap()])
        store.complete_book(session['session_id'], ready['prepared_hash'], 'receipt-one')
        second = fixture_source('book-two')
        store.save_source(second)
        session_two = store.create_session(second, store.get_learner())
        with self.assertRaises(LearningError):
            store.complete_book(session_two['session_id'], ready['prepared_hash'], 'receipt-one')
        self.assertEqual(store.get_session(session_two['session_id'])['status'], 'imported')

    def test_missing_source_chapter_cannot_be_marked_ready(self):
        from scholarly_translation.learning_contracts import source_hash
        store = LearningStore(Path(self._tmp.name))
        source = fixture_source()
        extra = {'chapter_id': 'chapter-two', 'title': 'פרק ב', 'units': [
            {'unit_id': 'unit-two', 'kind': 'paragraph', 'text': 'פרק נוסף שהקורא צריך לקבל לפני סימון קראתי.'}]}
        source['chapters'].append(extra)
        source['source_hash'] = source_hash(source)
        store.save_source(source)
        session = store.create_session(source, store.get_learner())
        partial = store.save_prepared(session['session_id'], [_chunk()], [_recap()])
        self.assertEqual(partial['status'], 'preparing')
        with self.assertRaises(LearningError):
            store.complete_book(session['session_id'], partial['prepared_hash'], 'complete-partial')

    def test_save_source_is_immutable(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        source = fixture_source()
        store.save_source(source)
        store.save_source(source)  # idempotent no-op for identical content
        assert store.get_source(source["book_id"])["book_id"] == source["book_id"]

        mutated = dict(source, title="שונה")
        with self.assertRaises(LearningError) as exc:
            store.save_source(mutated)
        assert exc.exception.code == "corrupt_store"


    def test_get_learner_creates_default_once(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        first = store.get_learner("fr")
        second = store.get_learner("fr")
        assert first == second
        assert first["active_book_id"] is None


    def test_create_session_claims_single_active_slot(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        learner = store.get_learner("fr")
        source = fixture_source("book-one")
        store.save_source(source)
        session = store.create_session(source, learner)
        assert session["status"] == "imported"

        other_source = fixture_source("book-two")
        store.save_source(other_source)
        stale_learner = store.get_learner("fr")
        with self.assertRaises(LearningError) as exc:
            store.create_session(other_source, stale_learner)
        assert exc.exception.code == "active_book_conflict"


    def test_save_prepared_marks_ready_only_on_full_coverage(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        learner = store.get_learner("fr")
        source = fixture_source("book-one")
        store.save_source(source)
        session = store.create_session(source, learner)

        chunk = _chunk()
        incomplete_recap = _recap(chunk_hashes=())
        partial = store.save_prepared(session["session_id"], [chunk], [incomplete_recap])
        assert partial["status"] == "preparing"
        assert partial["prepared_hash"] is None

        full = store.save_prepared(session["session_id"], [chunk], [_recap()])
        assert full["status"] == "ready"
        assert full["prepared_hash"] == prepared_hash([chunk], [_recap()])


    def test_complete_book_is_idempotent_and_rejects_stale_hash(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        learner = store.get_learner("fr")
        source = fixture_source("book-one")
        store.save_source(source)
        session = store.create_session(source, learner)
        chunk = _chunk()
        recap = _recap()
        ready = store.save_prepared(session["session_id"], [chunk], [recap])

        with self.assertRaises(LearningError) as exc:
            store.complete_book(ready["session_id"], "wrong-hash", "c1")
        assert exc.exception.code == "state_conflict"

        receipt = store.complete_book(ready["session_id"], ready["prepared_hash"], "c1")
        assert receipt["book_id"] == "book-one"

        repeat_receipt = store.complete_book(ready["session_id"], ready["prepared_hash"], "c1")
        assert repeat_receipt == receipt

        final_learner = store.get_learner("fr")
        assert final_learner["active_book_id"] is None
        assert final_learner["revision"] == learner["revision"] + 1


    def test_complete_book_recovers_from_interrupted_transaction(self):
        tmp_path = Path(self._tmp.name)
        root = tmp_path / "learning"
        store = LearningStore(root)
        learner = store.get_learner("fr")
        source = fixture_source("book-one")
        store.save_source(source)
        session = store.create_session(source, learner)
        ready = store.save_prepared(session["session_id"], [_chunk()], [_recap()])

        # Simulate a crash right after the transaction was durably staged but
        # before it was applied to the individual files.
        from scholarly_translation.learning_state import apply_completion
        full_learner = store.get_learner("fr")
        new_learner_state, receipt = apply_completion(
            full_learner, ready, [_chunk()], [_recap()], completion_id="c-crash", completed_at="t",
        )
        new_session = dict(ready, status="completed")
        txn = {"learner": new_learner_state, "session": new_session, "receipt": receipt}
        pending_dir = root / "_pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / "staged.json").write_text(json.dumps(txn), encoding="utf-8")

        recovered_store = LearningStore(root)
        assert not (pending_dir / "staged.json").exists()
        assert recovered_store.get_session(ready["session_id"])["status"] == "completed"
        assert recovered_store.get_learner("fr")["active_book_id"] is None


    def test_path_containment_rejects_invalid_ids(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        with self.assertRaises(LearningError):
            store.get_source("../../etc/passwd")
        with self.assertRaises(LearningError):
            store.get_session("not valid id")


    def test_cursor_does_not_advance_curriculum(self):
        tmp_path = Path(self._tmp.name)
        store = LearningStore(tmp_path / "learning")
        learner = store.get_learner("fr")
        source = fixture_source("book-one")
        store.save_source(source)
        session = store.create_session(source, learner)
        updated = store.save_cursor(session["session_id"], {"chapter_id": "chapter-one", "unit_id": "unit-one"})
        assert updated["status"] == "imported"
        assert updated["read_cursor"] == {"chapter_id": "chapter-one", "unit_id": "unit-one"}
