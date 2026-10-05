"""Persistent local call reservations, verified raw-result cache and usage events.

Reservations enforce dated list-price estimates and dispatch counts, not account
billing. Uncertain calls retain their hold. All events are append-only; mutable
reservation/task state is separate. Only raw cache rows contain response text.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

from .source_reading import fingerprint

SCHEMA_VERSION = 1
DEFAULT_CONTROL_STORE = "outputs/runtime_controls.sqlite3"
DEFAULT_TASK_ID = "document_id"
DEFAULT_MAX_CALLS = 3
DEFAULT_HARD_LIST_USD = 0.01
COMPLETED_STATUSES = ("completed", "mock_placeholder")
SCALE = 1_000_000_000


class RuntimeControlsError(ValueError):
    """Sanitized, fail-closed control error."""


class PolicyMismatchError(RuntimeControlsError):
    pass


class BudgetExhaustedError(RuntimeControlsError):
    pass


class StoreCorruptionError(RuntimeControlsError):
    pass


class _CacheReady(RuntimeControlsError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(value, floor=False):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
        raise RuntimeControlsError("invalid list-price amount")
    return int((Decimal(str(value)) * SCALE).to_integral_value(rounding=ROUND_FLOOR if floor else ROUND_CEILING))


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is not None and not value.startswith("sk-")


def _usage(value):
    if not isinstance(value, dict) or any(k not in {"input", "output", "cached", "cache_write", "reasoning"} or type(v) is not int or v < 0 for k, v in value.items()):
        return "not_metered"
    return value


def _policy_fingerprint(max_calls, hard_list_usd, pricing_version, output_cap):
    return fingerprint(dict(max_calls=max_calls, hard_list_usd=hard_list_usd, pricing_version=pricing_version, output_cap=output_cap))


def validate_store_path(path, protected_paths=()):
    root = Path(__file__).resolve().parent.parent
    resolved = Path(path).resolve()
    unsafe = [root / x for x in ("scholarly_translation", "tests", ".git", ".codex", ".agents", "audit")]
    if any(resolved == p or p in resolved.parents for p in unsafe):
        raise RuntimeControlsError("control store path is inside a protected repository tree")
    if resolved.suffix.lower() not in (".sqlite3", ".sqlite", ".db"):
        raise RuntimeControlsError("control store requires a separate SQLite filename")
    if resolved.parent == root:
        raise RuntimeControlsError("control store must be separate from repository root files")
    targets = [resolved, Path(str(resolved) + "-wal"), Path(str(resolved) + "-shm"), Path(str(resolved) + "-journal")]
    for original in protected_paths:
        if original is None:
            continue
        original = Path(original).resolve()
        for target in targets:
            if target == original or (target.exists() and original.exists() and target.samefile(original)):
                raise RuntimeControlsError("control store aliases protected source evidence")
    return resolved


def _raw_result(result, provider, status):
    from .model_adapter import compute_estimate
    fields = {"status", "text", "token_usage", "observed_model", "error"}
    if (not isinstance(result, dict) or set(result) != fields or result["status"] != status
            or status not in COMPLETED_STATUSES or not isinstance(result["text"], str) or not result["text"].strip()
            or result["error"] is not None
            or not (result["observed_model"] is None or _identifier(result["observed_model"]))):
        raise StoreCorruptionError("invalid cached raw-result schema")
    if provider != "mock" and (status != "completed" or compute_estimate(result["token_usage"]) == "not_metered"):
        raise StoreCorruptionError("unmetered or unsupported live result cannot be cached")
    if _usage(result["token_usage"]) != result["token_usage"]:
        raise StoreCorruptionError("invalid cached usage")


class ControlStore:
    def __init__(self, path, create=True):
        self.path = Path(path).resolve()
        self._conn = None
        exists = self.path.exists()
        if not exists and not create:
            raise StoreCorruptionError("control store does not exist")
        if exists and (not self.path.is_file() or self.path.stat().st_size == 0):
            raise StoreCorruptionError("control store is empty or malformed")
        try:
            if not exists:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            mode = "rwc" if create else "ro"
            self._conn = sqlite3.connect(self.path.as_uri() + "?mode=" + mode, uri=True, timeout=10, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            if exists:
                self._check_schema()
            else:
                with self._transaction():
                    # Another creator may have completed initialization meanwhile.
                    if self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        self._check_schema()
                    else:
                        self._init_schema()
        except (sqlite3.Error, OSError):
            self.close()
            raise StoreCorruptionError("cannot open a valid control store") from None
        except Exception:
            self.close()
            raise

    def close(self):
        if self._conn is not None:
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
                raise StoreCorruptionError("control-store transaction failed") from None
            raise

    def _init_schema(self):
        statements = [
            "CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
            """CREATE TABLE tasks(task_id TEXT PRIMARY KEY,max_calls INTEGER,hard_list_usd REAL,pricing_version TEXT,
               output_cap INTEGER,policy_fingerprint TEXT,calls_reserved INTEGER DEFAULT 0,calls_settled INTEGER DEFAULT 0,
               reserved_nanos INTEGER DEFAULT 0,spent_nanos INTEGER DEFAULT 0,stopped INTEGER DEFAULT 0,created_at TEXT)""",
            """CREATE TABLE events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,stage TEXT,outcome TEXT,
               reserved_usd REAL,observed_usd TEXT,actual_charge TEXT,timestamp TEXT,metadata_json TEXT,parent_event_id INTEGER)""",
            """CREATE TABLE reservations(event_id INTEGER PRIMARY KEY,task_id TEXT,cache_key TEXT,
               amount_nanos INTEGER,state TEXT)""",
            "CREATE UNIQUE INDEX active_calls ON reservations(cache_key) WHERE state IN ('reserved','uncertain')",
            """CREATE TABLE cache(cache_key TEXT PRIMARY KEY,stage TEXT,provider TEXT,model TEXT,status TEXT,
               result_json TEXT,result_hash TEXT,created_event_id INTEGER,created_at TEXT)""",
        ]
        for sql in statements:
            self._conn.execute(sql)
        self._conn.execute("INSERT INTO meta VALUES('schema_version',?)", (str(SCHEMA_VERSION),))

    def _check_schema(self):
        required = {"meta": {"key", "value"}, "tasks": {"task_id", "max_calls", "hard_list_usd", "pricing_version",
                    "output_cap", "policy_fingerprint", "calls_reserved", "calls_settled", "reserved_nanos", "spent_nanos", "stopped", "created_at"},
                    "events": {"event_id", "task_id", "stage", "outcome", "reserved_usd", "observed_usd", "actual_charge", "timestamp", "metadata_json", "parent_event_id"},
                    "reservations": {"event_id", "task_id", "cache_key", "amount_nanos", "state"},
                    "cache": {"cache_key", "stage", "provider", "model", "status", "result_json", "result_hash", "created_event_id", "created_at"}}
        try:
            for table, fields in required.items():
                if fields != {r["name"] for r in self._conn.execute("PRAGMA table_info(" + table + ")")}:
                    raise StoreCorruptionError("unsupported or incomplete control-store schema")
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None or row[0] != str(SCHEMA_VERSION):
                raise StoreCorruptionError("unsupported control-store version")
        except sqlite3.Error:
            raise StoreCorruptionError("malformed control-store schema") from None

    @staticmethod
    def _valid_policy(max_calls, hard_list_usd, pricing_version, output_cap):
        return (type(max_calls) is int and 1 <= max_calls <= 100000
                and type(hard_list_usd) in (int, float) and math.isfinite(hard_list_usd) and 1e-9 <= hard_list_usd <= 1_000_000
                and _identifier(pricing_version) and type(output_cap) is int and 1 <= output_cap <= 100000)

    def _task(self, task_id):
        row = self._conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise RuntimeControlsError("unknown task_id")
        if (not self._valid_policy(row["max_calls"], row["hard_list_usd"], row["pricing_version"], row["output_cap"])
                or row["policy_fingerprint"] != _policy_fingerprint(row["max_calls"], row["hard_list_usd"], row["pricing_version"], row["output_cap"])
                or any(type(row[k]) is not int or row[k] < 0 for k in ("calls_reserved", "calls_settled", "reserved_nanos", "spent_nanos"))
                or row["calls_reserved"] > row["max_calls"] or row["calls_settled"] > row["calls_reserved"] or row["stopped"] not in (0, 1)):
            raise StoreCorruptionError("invalid persisted task state")
        reservations = self._conn.execute("SELECT state,amount_nanos FROM reservations WHERE task_id=?", (task_id,)).fetchall()
        if any(r["state"] not in ("reserved", "settled", "uncertain", "released") or type(r["amount_nanos"]) is not int or r["amount_nanos"] < 0 for r in reservations):
            raise StoreCorruptionError("invalid persisted reservation state")
        if (row["calls_reserved"] != sum(r["state"] != "released" for r in reservations)
                or row["calls_settled"] != sum(r["state"] in ("settled", "uncertain") for r in reservations)
                or row["reserved_nanos"] != sum(r["amount_nanos"] for r in reservations if r["state"] in ("reserved", "uncertain"))):
            raise StoreCorruptionError("task counters differ from durable reservations")
        settlements = self._conn.execute("""SELECT e.observed_usd,e.outcome FROM events e JOIN reservations r
            ON e.parent_event_id=r.event_id WHERE r.task_id=? AND r.state='settled'
            AND e.outcome IN ('settled','anomaly_over_cap')""", (task_id,)).fetchall()
        try:
            spent = sum(_money(json.loads(e["observed_usd"])) for e in settlements)
        except (ValueError, TypeError):
            raise StoreCorruptionError("invalid persisted usage settlement") from None
        if (len(settlements) != sum(r["state"] == "settled" for r in reservations)
                or spent != row["spent_nanos"]
                or (any(r["state"] == "uncertain" for r in reservations) or any(e["outcome"] == "anomaly_over_cap" for e in settlements)) and not row["stopped"]):
            raise StoreCorruptionError("task spending or stop state differs from durable settlements")
        return row

    def get_or_create_task(self, task_id, max_calls, hard_list_usd, pricing_version, output_cap):
        if not _identifier(task_id) or not self._valid_policy(max_calls, hard_list_usd, pricing_version, output_cap):
            raise RuntimeControlsError("invalid task identity or policy")
        policy = _policy_fingerprint(max_calls, float(hard_list_usd), pricing_version, output_cap)
        with self._transaction():
            if self._conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone() is None:
                self._conn.execute("""INSERT INTO tasks(task_id,max_calls,hard_list_usd,pricing_version,output_cap,
                    policy_fingerprint,created_at) VALUES(?,?,?,?,?,?,?)""",
                    (task_id, max_calls, float(hard_list_usd), pricing_version, output_cap, policy, _now()))
            if self._task(task_id)["policy_fingerprint"] != policy:
                raise PolicyMismatchError("task policy is fixed; supplied policy differs")
        return policy

    def _event(self, task_id, stage, outcome, metadata, reservation=0, estimate=None, parent=None, actual="unknown"):
        cur = self._conn.execute("""INSERT INTO events(task_id,stage,outcome,reserved_usd,observed_usd,
                    actual_charge,timestamp,metadata_json,parent_event_id) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (task_id, stage, outcome, reservation, json.dumps(estimate), actual, _now(),
                     json.dumps(metadata, sort_keys=True, allow_nan=False), parent))
        return cur.lastrowid

    def reserve(self, task_id, *, stage, worst_case_usd, document_id=None, unit_id=None, reason=None,
                provider=None, model=None, prompt_hash=None, policy_hash=None, cache_key=None, metadata=None):
        amount = _money(worst_case_usd)
        if not _identifier(stage):
            raise RuntimeControlsError("invalid call stage")
        meta = metadata or {"document_id": document_id, "unit_id": unit_id, "reason": reason,
                            "requested_provider": provider, "requested_model": model, "prompt_hash": prompt_hash,
                            "policy_hash": policy_hash, "cache_hash": cache_key}
        with self._transaction():
            row = self._task(task_id)
            if cache_key is not None:
                if self._conn.execute("SELECT 1 FROM cache WHERE cache_key=?", (cache_key,)).fetchone():
                    raise _CacheReady()
                if self._conn.execute("SELECT 1 FROM reservations WHERE cache_key=? AND state IN ('reserved','uncertain')", (cache_key,)).fetchone():
                    raise BudgetExhaustedError("matching call is in flight or uncertain; automatic retry refused")
            if row["stopped"] or row["calls_reserved"] >= row["max_calls"]:
                raise BudgetExhaustedError("persistent call limit reached or task stopped")
            total = row["reserved_nanos"] + row["spent_nanos"] + amount
            if total > _money(row["hard_list_usd"], floor=True):
                raise BudgetExhaustedError("persistent list-price reservation limit reached")
            event = self._event(task_id, stage, "reserved", meta, amount / SCALE)
            self._conn.execute("INSERT INTO reservations VALUES(?,?,?,?,?)", (event, task_id, cache_key, amount, "reserved"))
            self._conn.execute("UPDATE tasks SET calls_reserved=calls_reserved+1,reserved_nanos=reserved_nanos+? WHERE task_id=?", (amount, task_id))
            fraction = total / _money(row["hard_list_usd"], floor=True)
        return event, [f"budget_preflight_{n}_percent" for n in (50, 80) if fraction >= n / 100]

    def release_unstarted(self, event_id):
        with self._transaction():
            row = self._conn.execute("SELECT * FROM reservations WHERE event_id=?", (event_id,)).fetchone()
            if row is None or row["state"] != "reserved":
                raise RuntimeControlsError("not an unstarted reservation")
            original = self._conn.execute("SELECT stage FROM events WHERE event_id=?", (event_id,)).fetchone()
            self._conn.execute("UPDATE tasks SET calls_reserved=calls_reserved-1,reserved_nanos=reserved_nanos-? WHERE task_id=?", (row["amount_nanos"], row["task_id"]))
            self._conn.execute("UPDATE reservations SET state='released' WHERE event_id=?", (event_id,))
            self._event(row["task_id"], original["stage"], "released_unstarted", {}, parent=event_id, actual="no_provider_call")

    def settle(self, event_id, *, token_usage, estimate, observed_model=None, actual_charge="unknown",
               latency=None, outcome="completed", cache_entry=None):
        known = estimate != "not_metered"
        charge = _money(estimate) if known else 0
        with self._transaction():
            res = self._conn.execute("SELECT * FROM reservations WHERE event_id=?", (event_id,)).fetchone()
            if res is None or res["state"] != "reserved":
                raise RuntimeControlsError("not a settleable reservation")
            original = self._conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            task = self._task(res["task_id"])
            failed = outcome not in COMPLETED_STATUSES
            anomaly = known and (charge > res["amount_nanos"] or task["spent_nanos"] + task["reserved_nanos"] - res["amount_nanos"] + charge > _money(task["hard_list_usd"], floor=True))
            uncertain = not known or failed
            held = res["amount_nanos"] if uncertain else 0
            spent = 0 if uncertain else charge
            stopped = uncertain or anomaly
            final = "stopped_not_metered" if not known else ("anomaly_over_cap" if anomaly else ("failed_held" if failed else "settled"))
            self._conn.execute("""UPDATE tasks SET calls_settled=calls_settled+1,
                reserved_nanos=reserved_nanos-?,spent_nanos=spent_nanos+?,stopped=CASE WHEN ? THEN 1 ELSE stopped END WHERE task_id=?""",
                (res["amount_nanos"] - held, spent, int(stopped), res["task_id"]))
            self._conn.execute("UPDATE reservations SET state=? WHERE event_id=?", ("uncertain" if uncertain else "settled", event_id))
            meta = json.loads(original["metadata_json"])
            meta.update(token_usage=_usage(token_usage), observed_model=observed_model,
                        pricing_version=task["pricing_version"], latency_seconds=latency, provider_outcome=outcome)
            settlement = self._event(res["task_id"], original["stage"], final, meta, held / SCALE,
                                    estimate=estimate, parent=event_id, actual=actual_charge)
            if cache_entry is not None and not stopped:
                self._cache_write(event_id=settlement, **cache_entry)
            total = task["spent_nanos"] + task["reserved_nanos"] - res["amount_nanos"] + held + spent
        notices = ["usage_not_metered_stop"] if not known else []
        if stopped and known:
            notices.append("provider_failure_or_reservation_anomaly_stop")
        notices.extend(f"budget_observed_{n}_percent" for n in (50, 80) if total / _money(task["hard_list_usd"], floor=True) >= n / 100)
        return notices

    def cache_lookup(self, cache_key, expected=None):
        row = self._conn.execute("SELECT * FROM cache WHERE cache_key=?", (cache_key,)).fetchone()
        if row is None:
            return None
        try:
            result = json.loads(row["result_json"])
            bound = {"cache_key": cache_key, "stage": row["stage"], "provider": row["provider"],
                     "model": row["model"], "status": row["status"], "result": result, "source_event_id": row["created_event_id"]}
            if fingerprint(bound) != row["result_hash"] or (expected is not None and tuple(row[k] for k in ("stage", "provider", "model")) != expected):
                raise StoreCorruptionError("cached identity or checksum mismatch")
            _raw_result(result, row["provider"], row["status"])
        except (ValueError, TypeError, KeyError):
            raise StoreCorruptionError("invalid cached result") from None
        return {"result": result, "status": row["status"], "source_event_id": row["created_event_id"]}

    def _cache_write(self, cache_key, *, stage, provider, model, status, result, event_id=None):
        _raw_result(result, provider, status)
        bound = dict(cache_key=cache_key, stage=stage, provider=provider, model=model, status=status, result=result, source_event_id=event_id)
        self._conn.execute("INSERT INTO cache VALUES(?,?,?,?,?,?,?,?,?)",
                           (cache_key, stage, provider, model, status, json.dumps(result, allow_nan=False),
                            fingerprint(bound), event_id, _now()))

    def cache_store(self, cache_key, **kwargs):
        with self._transaction():
            self._cache_write(cache_key, **kwargs)

    def record_cache_hit(self, task_id, *, stage, cache_hash, source_event_id, document_id=None, unit_id=None, metadata=None):
        with self._transaction():
            self._task(task_id)
            meta = dict(metadata or {}, cache_hash=cache_hash, cache_source_event=source_event_id,
                        document_id=document_id, unit_id=unit_id, token_usage={"input": 0, "output": 0})
            return self._event(task_id, stage, "cache_hit", meta, estimate=0, parent=source_event_id, actual="no_provider_call")

    def status(self, task_id):
        row = self._task(task_id)
        events = []
        for event in self._conn.execute("SELECT * FROM events WHERE task_id=? ORDER BY event_id", (task_id,)):
            events.append({k: event[k] for k in ("event_id", "stage", "outcome", "reserved_usd", "observed_usd", "actual_charge", "timestamp", "parent_event_id")})
        return dict(task_id=task_id, max_calls=row["max_calls"], hard_list_usd=row["hard_list_usd"],
                    attempted_calls=row["calls_reserved"], settled_calls=row["calls_settled"],
                    held_usd=row["reserved_nanos"] / SCALE, list_estimated_spent_usd=row["spent_nanos"] / SCALE,
                    stopped=bool(row["stopped"]), cache_hits=sum(e["outcome"] == "cache_hit" for e in events),
                    cache_misses=row["calls_reserved"], events=events)


class PersistentBudget:
    def __init__(self, store, task_id, *, max_calls, hard_list_usd, stage, provider, model,
                 document_id=None, unit_id=None, pricing_version=None, output_cap=None, max_prompt_bytes=None):
        from .model_adapter import PRICING_VERSION, OPENAI_MAX_OUTPUT_TOKENS
        self.store, self.task_id, self.stage, self.provider, self.model = store, task_id, stage, provider, model
        self.max_calls, self.hard_list_usd = max_calls, hard_list_usd
        self.document_id, self.unit_id = document_id, unit_id
        self.pricing_version = PRICING_VERSION if pricing_version is None else pricing_version
        self.output_cap = OPENAI_MAX_OUTPUT_TOKENS if output_cap is None else output_cap
        # The task's output_cap is a worst-case bound used for every call under
        # this task_id (get_or_create_task fixes it per task), not a single
        # global constant: a document task may share one bound across several
        # configured roles/models (e.g. translator vs. chapter_qa) as long as
        # every PersistentBudget sharing that task_id agrees on the same value.
        if self.pricing_version != PRICING_VERSION or type(self.output_cap) is not int or not 1 <= self.output_cap <= 100000:
            raise RuntimeControlsError("unsupported pricing or output-cap configuration")
        self.max_prompt_bytes = max_prompt_bytes
        self.policy_hash = store.get_or_create_task(task_id, max_calls, hard_list_usd, self.pricing_version, self.output_cap)
        self._pending_event = None

    def amount(self, prompt_text):
        from .model_adapter import RATES_PER_MILLION
        from .translation import MAX_PROMPT_BYTES, TranslationBudgetError
        limit = MAX_PROMPT_BYTES if self.max_prompt_bytes is None else self.max_prompt_bytes
        if not isinstance(prompt_text, str) or len(prompt_text.encode("utf-8")) > limit:
            raise TranslationBudgetError("oversized or invalid controlled prompt")
        if self.provider == "mock":
            return 0.0
        return ((2 * len(prompt_text.encode("utf-8")) + 1024) * RATES_PER_MILLION["input"] + self.output_cap * RATES_PER_MILLION["output"]) / 1_000_000

    def reserve(self, prompt_text):
        from .translation import TranslationBudgetError
        if self._pending_event is not None:
            raise TranslationBudgetError("previous reservation is still pending")
        try:
            self._pending_event, notices = self.store.reserve(self.task_id, stage=self.stage, worst_case_usd=self.amount(prompt_text),
                document_id=self.document_id, unit_id=self.unit_id, provider=self.provider, model=self.model,
                prompt_hash=fingerprint(prompt_text), policy_hash=self.policy_hash)
            return notices
        except BudgetExhaustedError as exc:
            raise TranslationBudgetError(str(exc)) from None

    def release_unstarted(self):
        self.store.release_unstarted(self._pending_event)
        self._pending_event = None

    def record(self, token_usage):
        from .model_adapter import compute_estimate
        notices = self.store.settle(self._pending_event, token_usage=token_usage, estimate=compute_estimate(token_usage))
        self._pending_event = None
        return notices


class RuntimeCache:
    def __init__(self, store, *, stage, provider, model):
        self._store, self.stage, self.provider, self.model = store, stage, provider, model
        self.provenance = []

    def lookup(self, cache_key):
        from .model_adapter import TextGenerationResult
        entry = self._store.cache_lookup(cache_key, expected=(self.stage, self.provider, self.model))
        if entry is None:
            return None
        r = entry["result"]
        return TextGenerationResult(r["status"], r["text"], {"input": 0, "output": 0}, r["observed_model"], 0.0)

    def put(self, cache_key, result):
        raw = {k: getattr(result, k) for k in ("status", "text", "token_usage", "observed_model", "error")}
        self._store.cache_store(cache_key, stage=self.stage, provider=self.provider, model=self.model, status=result.status, result=raw)

    def execute(self, identity, prompt_text, model, call, *, stage, metadata, budget=None):
        from .model_adapter import TextGenerationResult, OpenAIConfigurationError, compute_estimate
        from .translation import TranslationBudgetError
        if budget is None:
            budget = PersistentBudget(self._store, metadata["document_id"], max_calls=3, hard_list_usd=0.01,
                                      stage=stage, provider=self.provider, model=model)
        if not isinstance(budget, PersistentBudget) or budget.store is not self._store or budget.provider != self.provider:
            raise RuntimeControlsError("cache and persistent budget must share one store/provider")
        # The actual configured output_cap for this budget/task, never a
        # blind global constant -- two calls that differ only in their
        # resolved role's output cap must not collide on the same cache key.
        key = fingerprint(dict(identity=identity, prompt_hash=fingerprint(prompt_text), stage=stage,
                               provider=self.provider, model=model, gateway_version=1, output_cap=budget.output_cap))
        # Only explicit identities/hashes enter usage events.
        meta = {k: metadata.get(k) for k in ("document_id", "unit_id", "source_text_hash", "pdf_hash", "policy_fingerprint", "profile_id", "provider_type")}
        meta.update(requested_provider=self.provider, requested_model=model, prompt_hash=fingerprint(prompt_text),
                    cache_hash=key, reason="runtime_" + stage)
        expected = (stage, self.provider, model)

        def hit(entry):
            raw = entry["result"]
            original = self._store._conn.execute("SELECT metadata_json,outcome,stage FROM events WHERE event_id=?", (entry["source_event_id"],)).fetchone()
            if original is None or original["outcome"] != "settled" or original["stage"] != stage:
                raise StoreCorruptionError("cached result lacks a verified completed call event")
            try:
                original_meta = json.loads(original["metadata_json"])
                if not isinstance(original_meta, dict):
                    raise ValueError()
            except (ValueError, TypeError):
                raise StoreCorruptionError("invalid cached result event") from None
            if any(original_meta.get(k) != meta[k] for k in ("cache_hash", "requested_provider", "requested_model")):
                raise StoreCorruptionError("cached result event identity differs")
            event = self._store.record_cache_hit(budget.task_id, stage=stage, cache_hash=key,
                source_event_id=entry["source_event_id"], document_id=metadata["document_id"],
                unit_id=metadata["unit_id"], metadata=meta)
            self.provenance.append(dict(event_id=event, task_id=budget.task_id, cache_hit=True,
                source_event_id=entry["source_event_id"], prior_token_usage=raw["token_usage"], provider_requests=0))
            return TextGenerationResult(raw["status"], raw["text"], {"input": 0, "output": 0}, raw["observed_model"], 0.0), True, []

        entry = self._store.cache_lookup(key, expected)
        if entry is not None:
            return hit(entry)
        try:
            event, notices = self._store.reserve(budget.task_id, stage=stage, worst_case_usd=budget.amount(prompt_text),
                                                 cache_key=key, metadata=meta)
        except _CacheReady:
            return hit(self._store.cache_lookup(key, expected))
        except BudgetExhaustedError as exc:
            raise TranslationBudgetError(str(exc)) from None
        start = time.monotonic()
        try:
            result = call(prompt_text, model)
        except OpenAIConfigurationError:
            self._store.release_unstarted(event)
            raise
        except Exception:
            self._store.settle(event, token_usage="not_metered", estimate="not_metered", outcome="failed_transport")
            raise RuntimeControlsError("controlled provider call failed; reservation retained") from None
        try:
            raw = {k: getattr(result, k) for k in ("status", "text", "token_usage", "observed_model", "error")}
            if not _identifier(result.status) or not (result.observed_model is None or _identifier(result.observed_model)):
                raise ValueError()
            provider_type = metadata.get("provider_type", self.provider)
            estimate = (0.0 if provider_type == "mock" else
                        compute_estimate(result.token_usage) if provider_type == "openai" else
                        "not_metered")
            cache_entry = None
            if result.status in COMPLETED_STATUSES and estimate != "not_metered":
                _raw_result(raw, self.provider, result.status)
                cache_entry = dict(cache_key=key, stage=stage, provider=self.provider, model=model, status=result.status, result=raw)
        except (AttributeError, TypeError, ValueError):
            self._store.settle(event, token_usage="not_metered", estimate="not_metered", outcome="invalid_result")
            raise RuntimeControlsError("invalid provider result; reservation retained") from None
        notices.extend(self._store.settle(event, token_usage=result.token_usage, estimate=estimate, observed_model=result.observed_model,
                         actual_charge="synthetic_non_billed" if self.provider == "mock" else "unknown",
                         latency=time.monotonic() - start, outcome=result.status, cache_entry=cache_entry))
        self.provenance.append(dict(event_id=event, task_id=budget.task_id, cache_hit=False, provider_requests=1))
        return result, False, notices
