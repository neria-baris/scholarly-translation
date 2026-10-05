"""Durable per-job step journal for resumable automated chapter processing.

Each journalled step identity is bound to its full prompt text, role, stage,
model and call-output cap, plus its logical dependencies (e.g. the batch's
unit ids) -- never only a bare counter. Transitions are strictly ordered:
``planned -> dispatched -> received(raw) -> validated -> completed``, or
``unknown`` when a dispatched call's outcome is lost (process crash, timeout
with no confirmed response). The raw provider result is persisted BEFORE any
parsing: a restart that finds a ``received`` (or later) step re-parses the
already-saved raw text with zero further provider calls. A step is never
re-dispatched while its own prior identity is ``dispatched`` or ``unknown``;
only a fresh different identity (e.g. a deliberate repair step) may be
planned alongside it.

This module is local SQLite bookkeeping only: it does not itself call a
provider, enforce budget, or interpret translation/QA content.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .source_reading import fingerprint

SCHEMA_VERSION = 2
RAW_RESULT_FIELDS = {"status", "text", "token_usage", "observed_model", "error"}


class WorkJournalError(ValueError):
    """Sanitized, fail-closed journal error."""


class StepCorruptionError(WorkJournalError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def step_identity(*, job_id, role, stage, model, call_output_cap, prompt_text, dependencies):
    """Deterministic step identity: distinct prompt text, role, stage, model,
    call-output cap or dependency set is always a distinct step, never reused."""
    return fingerprint({
        "job_id": job_id, "role": role, "stage": stage, "model": model,
        "call_output_cap": call_output_cap, "prompt_hash": fingerprint(str(prompt_text)),
        "dependencies": dependencies,
    })


class WorkJournal:
    def __init__(self, path, create=True):
        self.path = Path(path).resolve()
        exists = self.path.exists()
        if not exists and not create:
            raise StepCorruptionError("journal does not exist")
        if exists and (not self.path.is_file() or self.path.stat().st_size == 0):
            raise StepCorruptionError("journal is empty or malformed")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            if exists:
                self._check_schema()
            else:
                with self._transaction():
                    if self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        self._check_schema()
                    else:
                        self._init_schema()
        except (sqlite3.Error, OSError):
            self.close()
            raise StepCorruptionError("cannot open a valid work journal") from None
        except Exception:
            self.close()
            raise

    def close(self):
        if getattr(self, "_conn", None) is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def _transaction(self):
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            yield
            self._conn.execute("COMMIT")
        except Exception as exc:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            if isinstance(exc, sqlite3.Error):
                raise StepCorruptionError("journal transaction failed") from None
            raise

    def _init_schema(self):
        self._conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._conn.execute("""CREATE TABLE steps(
            identity TEXT PRIMARY KEY, job_id TEXT NOT NULL, role TEXT NOT NULL, stage TEXT NOT NULL,
            model TEXT NOT NULL, call_output_cap INTEGER NOT NULL, prompt_hash TEXT NOT NULL,
            dependencies_json TEXT NOT NULL, status TEXT NOT NULL,
            raw_json TEXT, raw_hash TEXT, validated_json TEXT, error TEXT, event_id INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        self._conn.execute("CREATE TABLE job_control(job_id TEXT PRIMARY KEY, paused INTEGER NOT NULL, status TEXT NOT NULL)")
        self._conn.execute("INSERT INTO meta VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))

    def _check_schema(self):
        required = {
            "meta": {"key", "value"},
            "steps": {"identity", "job_id", "role", "stage", "model", "call_output_cap", "prompt_hash",
                      "dependencies_json", "status", "raw_json", "raw_hash", "validated_json", "error",
                      "created_at", "updated_at", "event_id"},
            "job_control": {"job_id", "paused", "status"},
        }
        try:
            for table, fields in required.items():
                cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
                if cols != fields:
                    raise StepCorruptionError("unsupported or incomplete journal schema")
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None or row[0] != str(SCHEMA_VERSION):
                raise StepCorruptionError("unsupported journal schema version")
        except sqlite3.Error:
            raise StepCorruptionError("malformed journal schema") from None

    def plan_step(self, identity, *, job_id, role, stage, model, call_output_cap, prompt_text, dependencies):
        """Idempotent: planning an identity that already exists returns its
        current row unchanged (never resets progress already made)."""
        with self._transaction():
            existing = self._conn.execute("SELECT * FROM steps WHERE identity=?", (identity,)).fetchone()
            if existing is not None:
                return dict(existing)
            self._conn.execute(
                """INSERT INTO steps(identity, job_id, role, stage, model, call_output_cap, prompt_hash,
                   dependencies_json, status, raw_json, raw_hash, validated_json, error, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (identity, job_id, role, stage, model, call_output_cap, fingerprint(str(prompt_text)),
                 json.dumps(dependencies, sort_keys=True, ensure_ascii=False), "planned",
                 None, None, None, None, _now(), _now()),
            )
        return self.get(identity)

    def get(self, identity):
        row = self._conn.execute("SELECT * FROM steps WHERE identity=?", (identity,)).fetchone()
        return dict(row) if row else None

    def status_of(self, identity):
        row = self.get(identity)
        return row["status"] if row else None

    def _require_status(self, identity, allowed):
        row = self._conn.execute("SELECT * FROM steps WHERE identity=?", (identity,)).fetchone()
        if row is None:
            raise WorkJournalError("unknown step identity")
        if row["status"] not in allowed:
            raise WorkJournalError(
                f"step is not in an expected status for this transition (actual: {row['status']})"
            )
        return row

    def mark_dispatched(self, identity, event_id=None):
        with self._transaction():
            self._require_status(identity, ("planned",))
            self._conn.execute("UPDATE steps SET status='dispatched', event_id=?, updated_at=? WHERE identity=?", (event_id, _now(), identity))

    def receive_reused(self, identity, raw):
        """A proven local cache result required no provider dispatch."""
        self.mark_dispatched(identity)
        self.mark_received(identity, raw)

    def reset_unstarted(self, identity):
        with self._transaction():
            self._require_status(identity, ('dispatched',))
            self._conn.execute("UPDATE steps SET status='planned',event_id=NULL WHERE identity=?", (identity,))

    def mark_unknown(self, identity):
        """The dispatched call's outcome was lost (exception/crash before a
        confirmed response). Blocks any further automatic resend of this
        exact identity; a caller must plan a distinct repair/retry identity."""
        with self._transaction():
            row = self._conn.execute("SELECT status FROM steps WHERE identity=?", (identity,)).fetchone()
            if row is None:
                raise WorkJournalError("unknown step identity")
            if row["status"] not in ("dispatched", "unknown"):
                raise WorkJournalError("only a dispatched step can become unknown")
            self._conn.execute("UPDATE steps SET status='unknown', updated_at=? WHERE identity=?", (_now(), identity))

    def mark_received(self, identity, raw: dict):
        if not isinstance(raw, dict) or set(raw) != RAW_RESULT_FIELDS:
            raise WorkJournalError("invalid raw result shape")
        raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        raw_hash = fingerprint(raw)
        with self._transaction():
            self._require_status(identity, ("dispatched", "unknown"))
            self._conn.execute(
                "UPDATE steps SET status='received', raw_json=?, raw_hash=?, updated_at=? WHERE identity=?",
                (raw_json, raw_hash, _now(), identity),
            )

    def read_raw(self, identity):
        row = self._conn.execute(
            "SELECT raw_json, raw_hash FROM steps WHERE identity=? AND status IN ('received','validated','completed')",
            (identity,),
        ).fetchone()
        if row is None or row["raw_json"] is None:
            return None
        raw = json.loads(row["raw_json"])
        if fingerprint(raw) != row["raw_hash"]:
            raise StepCorruptionError("journal raw result checksum mismatch")
        return raw

    def mark_validated(self, identity, validated: dict):
        with self._transaction():
            self._require_status(identity, ("received", "validated"))
            self._conn.execute(
                "UPDATE steps SET status='validated', validated_json=?, updated_at=? WHERE identity=?",
                (json.dumps(validated, sort_keys=True, ensure_ascii=False), _now(), identity),
            )

    def read_validated(self, identity):
        row = self._conn.execute(
            "SELECT validated_json FROM steps WHERE identity=? AND status IN ('validated','completed')",
            (identity,),
        ).fetchone()
        return json.loads(row["validated_json"]) if row and row["validated_json"] is not None else None

    def mark_completed(self, identity):
        with self._transaction():
            self._require_status(identity, ("validated", "completed"))
            self._conn.execute("UPDATE steps SET status='completed', updated_at=? WHERE identity=?", (_now(), identity))

    def mark_failed(self, identity, error):
        with self._transaction():
            row = self._conn.execute("SELECT status FROM steps WHERE identity=?", (identity,)).fetchone()
            if row is None:
                raise WorkJournalError("unknown step identity")
            self._conn.execute(
                "UPDATE steps SET status='failed', error=?, updated_at=? WHERE identity=?",
                (str(error)[:4000], _now(), identity),
            )

    def pause(self, job_id):
        with self._transaction():
            self._conn.execute(
                "INSERT INTO job_control(job_id, paused, status) VALUES (?, 1, 'paused') "
                "ON CONFLICT(job_id) DO UPDATE SET paused=1, status='paused'", (job_id,),
            )

    def resume(self, job_id):
        with self._transaction():
            self._conn.execute(
                "INSERT INTO job_control(job_id, paused, status) VALUES (?, 0, 'running') "
                "ON CONFLICT(job_id) DO UPDATE SET paused=0, status='running'", (job_id,),
            )

    def is_paused(self, job_id):
        row = self._conn.execute("SELECT paused FROM job_control WHERE job_id=?", (job_id,)).fetchone()
        return bool(row["paused"]) if row else False

    def job_steps(self, job_id):
        return [dict(row) for row in self._conn.execute(
            "SELECT * FROM steps WHERE job_id=? ORDER BY created_at", (job_id,),
        )]
