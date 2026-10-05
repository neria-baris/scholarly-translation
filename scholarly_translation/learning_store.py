"""Small local filesystem store for language learning state (LEARN builder A).

Source/generated records persist as immutable blobs. Completing a book writes
learner + session + receipt as one recoverable transaction: the transaction is
first durably staged under ``_pending``, then applied to the three individual
files, then the staging file is removed. If the process crashes mid-apply, the
next store open replays any leftover staged transaction (writes are
idempotent, so replay is always safe).
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import threading
import uuid
from pathlib import Path

from .learning_contracts import (
    check_id,
    new_learner,
    prepared_hash,
    require,
    validate_learner,
    validate_session,
    validate_source,
    validate_generated,
    validate_recap,
)


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class LearningStore:
    def __init__(self, root):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._replay_pending()

    # -- paths -----------------------------------------------------------
    def _source_path(self, book_id):
        return self._root / "sources" / f"{check_id(book_id)}.json"

    def _learner_path(self, language):
        return self._root / "learners" / f"{check_id(language)}.json"

    def _session_path(self, session_id):
        return self._root / "sessions" / f"{check_id(session_id)}.json"

    def _prepared_path(self, session_id):
        return self._root / "prepared" / f"{check_id(session_id)}.json"

    def _receipt_path(self, completion_id):
        return self._root / "receipts" / f"{check_id(completion_id)}.json"

    def _pending_dir(self):
        return self._root / "_pending"

    # -- crash recovery ----------------------------------------------------
    def _apply_txn(self, txn):
        validate_learner(txn['learner'])
        validate_session(txn['session'])
        require(txn['learner']['language'] == txn['session']['language'], 'corrupt_store')
        _atomic_write(self._learner_path(txn["learner"]["language"]), txn["learner"])
        _atomic_write(self._session_path(txn["session"]["session_id"]), txn["session"])
        if 'receipt' in txn:
            _atomic_write(self._receipt_path(txn["receipt"]["completion_id"]), txn["receipt"])

    def _replay_pending(self):
        pending_dir = self._pending_dir()
        if not pending_dir.exists():
            return
        for path in sorted(pending_dir.glob("*.json")):
            try:
                txn = _read_json(path)
            except (OSError, ValueError):
                require(False, 'corrupt_store', 'pending transaction cannot be read')
            self._apply_txn(txn)
            path.unlink(missing_ok=True)

    # -- sources -----------------------------------------------------------
    def save_source(self, source):
        source = validate_source(copy.deepcopy(source))
        path = self._source_path(source["book_id"])
        with self._lock:
            if path.exists():
                existing = _read_json(path)
                require(existing == source, "corrupt_store", "source is immutable once saved")
                return copy.deepcopy(existing)
            _atomic_write(path, source)
        return copy.deepcopy(source)

    def get_source(self, book_id):
        path = self._source_path(book_id)
        require(path.exists(), "invalid_record", "unknown book_id")
        return validate_source(_read_json(path))

    # -- learner -----------------------------------------------------------
    def get_learner(self, language="fr"):
        path = self._learner_path(language)
        with self._lock:
            if not path.exists():
                learner = new_learner(language=language)
                _atomic_write(path, learner)
                return copy.deepcopy(learner)
            return validate_learner(_read_json(path))

    def save_learner(self, learner):
        learner = validate_learner(copy.deepcopy(learner))
        with self._lock:
            _atomic_write(self._learner_path(learner["language"]), learner)
        return copy.deepcopy(learner)

    # -- sessions ------------------------------------------------------------
    def create_session(self, source, learner):
        """Import is separate; this call claims the one active-book slot."""
        source = validate_source(copy.deepcopy(source))
        learner = validate_learner(copy.deepcopy(learner))
        with self._lock:
            current = self._read_learner_locked(learner["language"])
            require(current["revision"] == learner["revision"], "state_conflict", "stale learner revision")
            require(current["active_book_id"] is None, "active_book_conflict")
            session_id = f"session-{uuid.uuid4().hex}"
            session = validate_session({
                "schema_version": 1, "session_id": session_id, "learner_id": learner["learner_id"],
                "language": learner["language"], "book_id": source["book_id"], "source_hash": source["source_hash"],
                "base_learner_revision": learner["revision"], "policy_version": "learning-policy@1",
                "catalog_version": learner["catalog_version"], "level_id": learner["level_id"],
                "support_mode": learner["support_mode"], "status": "imported", "prepared_hash": None,
                "chunk_ids": [], "read_cursor": None,
            })
            updated_learner = copy.deepcopy(current)
            updated_learner["active_book_id"] = source["book_id"]
            updated_learner = validate_learner(updated_learner)
            txn = {'learner': updated_learner, 'session': session}
            pending = self._pending_dir() / f'{uuid.uuid4().hex}.json'
            _atomic_write(pending, txn)
            self._apply_txn(txn)
            pending.unlink()
            return copy.deepcopy(session)

    def _read_learner_locked(self, language):
        path = self._learner_path(language)
        if not path.exists():
            learner = new_learner(language=language)
            _atomic_write(path, learner)
            return learner
        return validate_learner(_read_json(path))

    def get_session(self, session_id):
        path = self._session_path(session_id)
        require(path.exists(), "invalid_record", "unknown session_id")
        return validate_session(_read_json(path))

    def list_sessions(self, language=None):
        sessions_dir = self._root / "sessions"
        if not sessions_dir.exists():
            return []
        results = []
        for path in sorted(sessions_dir.glob("*.json")):
            session = validate_session(_read_json(path))
            if language is None or session["language"] == language:
                results.append(session)
        return results

    def update_session(self, session):
        session = validate_session(copy.deepcopy(session))
        with self._lock:
            require(self._session_path(session["session_id"]).exists(), "invalid_record", "unknown session_id")
            _atomic_write(self._session_path(session["session_id"]), session)
        return copy.deepcopy(session)

    def abandon_session(self, session_id):
        """Release a stopped book without recording exposures or completion."""
        with self._lock:
            session = validate_session(_read_json(self._session_path(session_id)))
            require(session['status'] in ('failed', 'paused', 'imported'), 'state_conflict')
            learner = self._read_learner_locked(session['language'])
            require(learner['active_book_id'] == session['book_id'] and
                    learner['revision'] == session['base_learner_revision'], 'state_conflict')
            learner['active_book_id'] = None
            learner['revision'] += 1
            session['status'] = 'failed'
            txn = {'learner': validate_learner(learner), 'session': session}
            pending = self._pending_dir() / f'{uuid.uuid4().hex}.json'
            _atomic_write(pending, txn)
            self._apply_txn(txn)
            pending.unlink()
            return copy.deepcopy(session)

    # -- prepared chunks -----------------------------------------------------
    def save_prepared(self, session_id, chunks, recaps):
        with self._lock:
            session = validate_session(_read_json(self._session_path(session_id)))
            require(session["status"] in ("imported", "preparing", "paused"), "state_conflict")
            chunks = copy.deepcopy(chunks)
            recaps = copy.deepcopy(recaps)
            for chunk in chunks:
                validate_generated(chunk)
            for recap in recaps:
                validate_recap(recap)
            chunk_ids = [chunk["plan_id"] for chunk in chunks]
            require(len(chunk_ids) == len(set(chunk_ids)), "invalid_generation", "duplicate chunk plan_id")
            all_hashes = {chunk["content_hash"] for chunk in chunks}
            recap_hashes = set()
            for recap in recaps:
                recap_hashes.update(recap["chunk_hashes"])
            from .learning_catalog import load_catalog
            from .learning_planner import plan_book
            source = validate_source(_read_json(self._source_path(session['book_id'])))
            learner = self._read_learner_locked(session['language'])
            expected_count = len(plan_book(source, learner, load_catalog(session['language']), policy_version=session['policy_version']))
            full_coverage = (len(chunks) == expected_count and recap_hashes == all_hashes and
                len(recaps) == len(source['chapters']) and
                {r['chapter_id'] for r in recaps} == {c['chapter_id'] for c in source['chapters']})
            session["chunk_ids"] = chunk_ids
            if full_coverage:
                session["prepared_hash"] = prepared_hash(chunks, recaps)
                session["status"] = "ready"
            else:
                session["prepared_hash"] = None
                session["status"] = "preparing"
            session = validate_session(session)
            _atomic_write(self._prepared_path(session_id), {"chunks": chunks, "recaps": recaps})
            _atomic_write(self._session_path(session_id), session)
            return copy.deepcopy(session)

    def get_prepared(self, session_id):
        path = self._prepared_path(session_id)
        require(path.exists(), "invalid_record", "no prepared content for session")
        content = _read_json(path)
        session = self.get_session(session_id)
        if session['prepared_hash'] is not None:
            require(prepared_hash(content['chunks'], content['recaps']) == session['prepared_hash'], 'corrupt_store')
        return content

    # -- cursor (does not advance curriculum) --------------------------------
    def save_cursor(self, session_id, cursor):
        require(cursor is None or isinstance(cursor, dict), "invalid_record")
        with self._lock:
            session = validate_session(_read_json(self._session_path(session_id)))
            session["read_cursor"] = cursor
            session = validate_session(session)
            _atomic_write(self._session_path(session_id), session)
            return copy.deepcopy(session)

    # -- completion ("קראתי") -----------------------------------------------
    def complete_book(self, session_id, expected_prepared_hash, completion_id):
        from .learning_state import apply_completion

        check_id(completion_id)
        with self._lock:
            receipt_path = self._receipt_path(completion_id)
            if receipt_path.exists():
                receipt = _read_json(receipt_path)
                original = validate_session(_read_json(self._session_path(session_id)))
                require(receipt['book_id'] == original['book_id'] and
                        receipt['session_id'] == session_id and
                        receipt['prepared_hash'] == expected_prepared_hash and
                        original['status'] == 'completed', 'state_conflict')
                return copy.deepcopy(receipt)

            session = validate_session(_read_json(self._session_path(session_id)))
            require(session["status"] == "ready", "state_conflict")
            require(session["prepared_hash"] == expected_prepared_hash, "state_conflict")

            learner = self._read_learner_locked(session["language"])
            prepared = _read_json(self._prepared_path(session_id))

            completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            new_learner, receipt = apply_completion(
                learner, session, prepared["chunks"], prepared["recaps"],
                completion_id=completion_id, completed_at=completed_at,
            )
            new_session = validate_session({**session, "status": "completed"})

            txn = {"learner": new_learner, "session": new_session, "receipt": receipt}
            txn_path = self._pending_dir() / f"{uuid.uuid4().hex}.json"
            _atomic_write(txn_path, txn)
            self._apply_txn(txn)
            txn_path.unlink(missing_ok=True)
            return copy.deepcopy(receipt)
