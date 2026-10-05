import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation.model_adapter import (
    OpenAITextGenerationAdapter,
    TextGenerationResult,
)
from scholarly_translation.records import Document, Page, Segment
from scholarly_translation.runtime_controls import (
    BudgetExhaustedError,
    ControlStore,
    PersistentBudget,
    PolicyMismatchError,
    RuntimeCache,
    RuntimeControlsError,
    StoreCorruptionError,
    validate_store_path,
)
from scholarly_translation.segmentation import build_structure
from scholarly_translation.semantic_review import (
    build_semantic_review_request,
    run_semantic_review,
)
from scholarly_translation.source_reading import build_readings
from scholarly_translation.store import deterministic_id
from scholarly_translation.translation import (
    TranslationBudgetError,
    build_translation_request,
    run_translation,
)


def _synthetic_structure(tmp_path, language, text, name="source.bin"):
    """A minimal schema-3 structure; build_readings never opens the file bytes."""
    source_path = tmp_path / name
    source_path.write_bytes(b"synthetic-fixture-bytes-not-a-real-pdf")
    document_id = deterministic_id("gate11-synthetic", language, name)
    page_id = deterministic_id(document_id, "page", "1")
    segment = Segment(
        segment_id=deterministic_id(page_id, "line", "1"), page_id=page_id,
        order=1, text=text, source_char_start=0, source_char_end=len(text),
        bbox=(10, 10, 500, 30),
    )
    page = Page(
        page_id=page_id, document_id=document_id, page_number=1, segments=[segment],
        width=600, height=800, source_text=text + "\n",
    )
    document = Document(
        schema_version=3, document_id=document_id, document_version=1,
        language=language, source_kind="pdf", source_uri=source_path.resolve().as_uri(),
        pages=[page], stage_id="digital-pdf", stage_version=1,
        input_hash=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        status="synthetic", warnings=["synthetic_not_quality_evidence"],
    )
    candidate = build_readings(document)[0]["alternatives"][0]
    decision = {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": "fixture selection",
    }
    return build_structure(document, decisions={page_id: decision})


class ControlStoreBasicsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "controls.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_task_reserve_and_settle_cycle(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 3, 0.01, "2026-09-30", 256)
        event_id, notices = store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        self.assertIsInstance(notices, list)
        notices2 = store.settle(event_id, token_usage={"input": 100, "output": 50}, estimate=0.00003)
        self.assertIsInstance(notices2, list)
        status = store.status("task-1")
        self.assertEqual(status["attempted_calls"], 1)
        self.assertEqual(status["settled_calls"], 1)
        self.assertAlmostEqual(status["list_estimated_spent_usd"], 0.00003)
        self.assertFalse(status["stopped"])
        store.close()

    def test_mismatched_policy_rejected(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 3, 0.01, "2026-09-30", 256)
        with self.assertRaises(PolicyMismatchError):
            store.get_or_create_task("task-1", 5, 0.01, "2026-09-30", 256)
        status = store.status("task-1")
        self.assertEqual(status["max_calls"], 3)
        store.close()

    def test_call_limit_enforced(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 1, 0.01, "2026-09-30", 256)
        store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        with self.assertRaises(BudgetExhaustedError):
            store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        store.close()

    def test_hard_cap_enforced_before_call_limit(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 5, 0.001, "2026-09-30", 256)
        with self.assertRaises(BudgetExhaustedError):
            store.reserve("task-1", stage="translate", worst_case_usd=0.002)
        status = store.status("task-1")
        self.assertEqual(status["attempted_calls"], 0)
        store.close()

    def test_release_unstarted_frees_slot(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 1, 0.01, "2026-09-30", 256)
        event_id, _ = store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        store.release_unstarted(event_id)
        status = store.status("task-1")
        self.assertEqual(status["attempted_calls"], 0)
        self.assertEqual(status["held_usd"], 0)
        store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        store.close()

    def test_failed_settlement_retains_reservation(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 1, 0.01, "2026-09-30", 256)
        event_id, _ = store.reserve("task-1", stage="translate", worst_case_usd=0.001)
        notices = store.settle(event_id, token_usage=None, estimate="not_metered")
        self.assertIn("usage_not_metered_stop", notices)
        status = store.status("task-1")
        self.assertTrue(status["stopped"])
        self.assertEqual(status["attempted_calls"], 1)
        self.assertAlmostEqual(status["held_usd"], 0.001)
        with self.assertRaises(BudgetExhaustedError):
            store.reserve("task-1", stage="translate", worst_case_usd=0.0000001)
        store.close()

    def test_anomalous_overage_freezes_task(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 5, 0.0001, "2026-09-30", 256)
        event_id, _ = store.reserve("task-1", stage="translate", worst_case_usd=0.00005)
        store.settle(event_id, token_usage={"input": 1, "output": 1}, estimate=0.0005)
        status = store.status("task-1")
        self.assertTrue(status["stopped"])
        self.assertIn("anomaly_over_cap", [e["outcome"] for e in status["events"]])
        store.close()

    def test_two_independently_opened_stores_share_cap(self):
        store_a = ControlStore(self.db_path)
        store_a.get_or_create_task("task-1", 1, 0.01, "2026-09-30", 256)
        store_a.reserve("task-1", stage="translate", worst_case_usd=0.001)
        store_b = ControlStore(self.db_path)
        with self.assertRaises(BudgetExhaustedError):
            store_b.reserve("task-1", stage="translate", worst_case_usd=0.001)
        store_a.close()
        store_b.close()

    def test_invalid_policy_rejected(self):
        store = ControlStore(self.db_path)
        for bad in [(0, 0.01), (3, 0), (3, float("nan")), (True, 0.01)]:
            with self.assertRaises(RuntimeControlsError):
                store.get_or_create_task("task-x", bad[0], bad[1], "2026-09-30", 256)
        store.close()

    def test_status_never_includes_prompt_or_text_fields(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 3, 0.01, "2026-09-30", 256)
        status = store.status("task-1")
        serialized = str(status)
        for forbidden in ("prompt", "source_text", "draft_text"):
            self.assertNotIn(forbidden, serialized)
        store.close()

    def test_missing_store_fails_closed_for_status(self):
        with self.assertRaises(StoreCorruptionError):
            ControlStore(self.db_path, create=False)

    def test_empty_file_fails_closed(self):
        self.db_path.touch()
        with self.assertRaises(StoreCorruptionError):
            ControlStore(self.db_path)

    def test_unknown_schema_version_fails_closed(self):
        store = ControlStore(self.db_path)
        store.get_or_create_task("task-1", 3, 0.01, "2026-09-30", 256)
        store.close()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()
        with self.assertRaises(StoreCorruptionError):
            ControlStore(self.db_path)

    def test_malformed_database_file_fails_closed(self):
        self.db_path.write_bytes(b"not a sqlite database at all")
        with self.assertRaises(StoreCorruptionError):
            ControlStore(self.db_path)

    def test_unknown_task_id_in_status_rejected(self):
        store = ControlStore(self.db_path)
        with self.assertRaises(RuntimeControlsError):
            store.status("no-such-task")
        store.close()


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "controls.sqlite3"
        self.store = ControlStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_cache_roundtrip_only_stores_raw_result(self):
        result = TextGenerationResult(
            status="completed", text="hello", token_usage={"input": 1, "output": 1},
            observed_model="gpt-6-luna", duration_seconds=0.1,
        )
        self.store.cache_store("key-1", stage="translate", provider="openai", model="gpt-6-luna",
                                status=result.status, result={"status": result.status, "text": result.text,
                                                              "token_usage": result.token_usage,
                                                              "observed_model": result.observed_model,
                                                              "error": result.error})
        entry = self.store.cache_lookup("key-1")
        self.assertEqual(entry["result"]["text"], "hello")
        self.assertEqual(entry["status"], "completed")

    def test_cache_rejects_non_completed_status(self):
        with self.assertRaises(RuntimeControlsError):
            self.store.cache_store("key-1", stage="translate", provider="mock", model="mock-translation-1",
                                    status="failed_transport", result={"status": "failed_transport"})

    def test_cache_miss_returns_none(self):
        self.assertIsNone(self.store.cache_lookup("no-such-key"))

    def test_tampered_cache_entry_fails_closed(self):
        self.store.cache_store("key-1", stage="translate", provider="mock", model="mock-translation-1",
                                status="mock_placeholder", result={"status": "mock_placeholder", "text": "x",
                                "token_usage": "not_metered", "observed_model": "mock-translation-1", "error": None})
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE cache SET result_hash = 'deadbeef' WHERE cache_key = 'key-1'")
        conn.commit()
        conn.close()
        with self.assertRaises(StoreCorruptionError):
            self.store.cache_lookup("key-1")

    def test_runtime_cache_wraps_control_store(self):
        cache = RuntimeCache(self.store, stage="translate", provider="mock", model="mock-translation-1")
        result = TextGenerationResult(
            status="mock_placeholder", text="placeholder", token_usage="not_metered",
            observed_model="mock-translation-1", duration_seconds=0.0,
        )
        self.assertIsNone(cache.lookup("key-2"))
        cache.put("key-2", result)
        cached = cache.lookup("key-2")
        self.assertEqual(cached.text, "placeholder")
        self.assertEqual(cached.status, "mock_placeholder")


class ValidateStorePathTests(unittest.TestCase):
    def test_rejects_path_inside_source_tree(self):
        package_dir = Path(__file__).resolve().parents[1] / "scholarly_translation"
        with self.assertRaises(RuntimeControlsError):
            validate_store_path(package_dir / "controls.sqlite3")

    def test_rejects_alias_of_protected_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            protected = Path(tmp) / "structure.json"
            protected.write_text("{}", encoding="utf-8")
            with self.assertRaises(RuntimeControlsError):
                validate_store_path(protected, protected_paths=[protected])

    def test_accepts_safe_separate_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outputs" / "controls.sqlite3"
            validate_store_path(path, protected_paths=[Path(tmp) / "structure.json"])


def make_usage(input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


class FakeResponses:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


class CountingAdapter:
    """Wraps a real adapter and counts dispatches, to prove a cache hit skips the call."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def generate(self, prompt_text, model):
        self.calls += 1
        return self._inner.generate(prompt_text, model)


class TranslationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _synthetic_structure(Path(self.tmp.name), "en", "Axiom 3 remains true.")
        self.unit = self.structure["units"][0]
        self.db_path = Path(self.tmp.name) / "controls.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_controlled_cached_hebrew_draft_remains_reviewable_and_unapproved(self):
        from scholarly_translation.glossary import new_store as new_glossary_store
        from scholarly_translation.human_review import resolve_review_unit
        glossary = new_glossary_store()
        request = build_translation_request(self.structure, glossary, self.unit["unit_id"], "scholarly", "openai", "gpt-6-luna")
        response = SimpleNamespace(status="completed", output_text="אקסיומה 3 נותרת נכונה.", usage=make_usage())
        counting = CountingAdapter(OpenAITextGenerationAdapter(client=FakeClient(response)))
        with ControlStore(self.db_path) as store:
            cache = RuntimeCache(store, stage="translate", provider="openai", model="gpt-6-luna")
            first = run_translation(request, adapter=counting, cache=cache)
            second = run_translation(request, adapter=counting, cache=cache)
            self.assertEqual(counting.calls, 1)
            self.assertEqual(second["estimated_cost_usd"], 0)
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["findings"], second["findings"])
            resolved = resolve_review_unit(self.structure, glossary, second)
            self.assertFalse(resolved.draft["approved"])

    def test_persistent_budget_settles_and_updates_status(self):
        from scholarly_translation.glossary import new_store as new_glossary_store

        request = build_translation_request(
            self.structure, new_glossary_store(), self.unit["unit_id"], "scholarly", "openai", "gpt-6-luna",
        )
        response = SimpleNamespace(status="completed", output_text="אקסיומה 3 נותרת נכונה.", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response))
        with ControlStore(self.db_path) as store:
            budget = PersistentBudget(
                store, "doc-1", max_calls=3, hard_list_usd=0.01, stage="translate",
                provider="openai", model="gpt-6-luna",
            )
            draft = run_translation(request, adapter=adapter, budget=budget)
            self.assertEqual(draft["status"], "needs_human")
            self.assertIn("proper_name_candidate", [f["type"] for f in draft["findings"]])
            self.assertFalse(draft["approved"])
            status = store.status("doc-1")
            self.assertEqual(status["settled_calls"], 1)
            self.assertGreater(status["list_estimated_spent_usd"], 0)

    def test_persistent_budget_call_limit_raises_translation_budget_error(self):
        from scholarly_translation.glossary import new_store as new_glossary_store

        request = build_translation_request(
            self.structure, new_glossary_store(), self.unit["unit_id"], "scholarly", "openai", "gpt-6-luna",
        )
        response = SimpleNamespace(status="completed", output_text="הלוגוס מרכזי.", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response))
        store = ControlStore(self.db_path)
        store.get_or_create_task("doc-1", 1, 0.01, "2026-09-30", 256)
        store.reserve("doc-1", stage="translate", worst_case_usd=0.001)
        budget = PersistentBudget(
            store, "doc-1", max_calls=1, hard_list_usd=0.01, stage="translate",
            provider="openai", model="gpt-6-luna",
        )
        with self.assertRaises(TranslationBudgetError):
            run_translation(request, adapter=adapter, budget=budget)
        store.close()

    def test_cache_hit_skips_second_adapter_dispatch(self):
        from scholarly_translation.glossary import new_store as new_glossary_store

        request = build_translation_request(
            self.structure, new_glossary_store(), self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        from scholarly_translation.model_adapter import MockTextGenerationAdapter

        store = ControlStore(self.db_path)
        cache = RuntimeCache(store, stage="translate", provider="mock", model="mock-translation-1")
        counting = CountingAdapter(MockTextGenerationAdapter())

        draft1 = run_translation(request, adapter=counting, cache=cache)
        draft2 = run_translation(request, adapter=counting, cache=cache)

        self.assertEqual(counting.calls, 1)
        self.assertFalse(draft1["cache_hit"])
        self.assertTrue(draft2["cache_hit"])
        self.assertEqual(draft1["draft_text"], draft2["draft_text"])
        store.close()


class SemanticReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # "not" triggers a negation risk flag that routes to the critic.
        self.structure = _synthetic_structure(
            Path(self.tmp.name), "en", "This claim is not universally true.",
        )
        self.unit = self.structure["units"][0]
        self.db_path = Path(self.tmp.name) / "controls.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def _draft(self):
        from scholarly_translation.glossary import new_store as new_glossary_store
        from scholarly_translation.translation import run_translation as run_translation_

        glossary = new_glossary_store()
        request = build_translation_request(
            self.structure, glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        draft = run_translation_(request)
        # Mock drafts are non-Hebrew placeholders; substitute a reviewable Hebrew draft.
        draft = dict(draft, draft_text="התביעה הזו אינה נכונה באופן אוניברסלי.", status="draft_unapproved",
                     findings=[])
        return glossary, draft

    def test_critic_cache_hit_skips_second_dispatch(self):
        glossary, draft = self._draft()
        request = build_semantic_review_request(self.structure, glossary, draft, provider="mock")

        store = ControlStore(self.db_path)
        cache = RuntimeCache(store, stage="semantic_review", provider="mock", model="mock-semantic-critic-1")

        from scholarly_translation.semantic_review import FakeSemanticCritic

        inner_critic = FakeSemanticCritic(request)
        counting_critic = CountingAdapter(inner_critic)

        review1 = run_semantic_review(request, critic=counting_critic, cache=cache)
        review2 = run_semantic_review(request, critic=counting_critic, cache=cache)

        self.assertEqual(counting_critic.calls, 1)
        self.assertFalse(review1["approved"])
        self.assertFalse(review2["approved"])
        self.assertTrue(review2.get("cache_hit"))
        store.close()


class DurableBoundaryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "controls.sqlite3"
        self.metadata = {"document_id": "doc-1", "unit_id": "unit-1", "source_text": "PRIVATE_SOURCE_SENTINEL"}

    def _controls(self, store, provider="mock", max_calls=3):
        budget = PersistentBudget(store, "doc-1", max_calls=max_calls, hard_list_usd=0.01,
                                  stage="translate", provider=provider, model="gpt-6-luna")
        return RuntimeCache(store, stage="translate", provider=provider, model="gpt-6-luna"), budget

    def _execute(self, cache, budget, call=None, identity="identity-1", prompt="PRIVATE_PROMPT_SENTINEL", stage="translate", model="gpt-6-luna"):
        call = call or (lambda prompt, model: TextGenerationResult("completed", "PRIVATE_RESPONSE_SENTINEL",
                      {"input": 10, "output": 5}, model, 0.1))
        return cache.execute(identity, prompt, model, call, stage=stage, metadata=self.metadata, budget=budget)

    def test_cache_hit_has_zero_current_usage_and_linked_append_only_event(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            self._execute(cache, budget)
            original = [tuple(r) for r in store._conn.execute("SELECT * FROM events ORDER BY event_id")]
            historical_spent = store.status("doc-1")["list_estimated_spent_usd"]
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            result, hit, _ = self._execute(cache, budget, call=lambda *args: self.fail("cached call dispatched"))
            self.assertTrue(hit)
            self.assertEqual(result.token_usage, {"input": 0, "output": 0})
            status = store.status("doc-1")
            self.assertEqual(status["attempted_calls"], 1)
            self.assertEqual(status["cache_hits"], 1)
            self.assertEqual(status["list_estimated_spent_usd"], historical_spent)
            rows = [tuple(r) for r in store._conn.execute("SELECT * FROM events ORDER BY event_id")]
            self.assertEqual(rows[:len(original)], original)
            self.assertEqual(status["events"][-1]["parent_event_id"], cache.provenance[-1]["source_event_id"])
            self.assertEqual(cache.provenance[-1]["prior_token_usage"], {"input": 10, "output": 5})
            event_data = json.dumps(rows)
            for private in ("PRIVATE_SOURCE_SENTINEL", "PRIVATE_PROMPT_SENTINEL", "PRIVATE_RESPONSE_SENTINEL"):
                self.assertNotIn(private, event_data)

    def test_namespaced_compatible_model_settles_and_replays_without_dispatch(self):
        model = 'meta-llama/' + 'Llama-3.3-70B-Instruct-' * 7
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, 'openai_compatible')
            first, hit, _ = self._execute(cache, budget, model=model)
            self.assertFalse(hit)
            self.assertEqual(first.observed_model, model)
            cost = store.status('doc-1')['list_estimated_spent_usd']
            self.assertGreater(cost, 0)
            result, hit, _ = self._execute(cache, budget, model=model,
                call=lambda *args: self.fail('valid namespaced cache redispatched'))
            self.assertTrue(hit)
            self.assertEqual(result.observed_model, model)
            self.assertEqual(store.status('doc-1')['list_estimated_spent_usd'], cost)

    def test_identity_prompt_stage_and_model_changes_each_dispatch(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, max_calls=10)
            for kwargs in ({}, {"identity": "changed-source-policy"}, {"prompt": "changed prompt"},
                           {"stage": "critic"}, {"model": "other-model"}):
                self.assertFalse(self._execute(cache, budget, **kwargs)[1])
            self.assertEqual(store.status("doc-1")["attempted_calls"], 5)

    def test_inflight_duplicate_from_independent_store_never_dispatches(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store)
            def outer_call(prompt, model):
                with ControlStore(self.path) as other:
                    other_cache, other_budget = self._controls(other)
                    with self.assertRaises(TranslationBudgetError):
                        self._execute(other_cache, other_budget, call=lambda *args: self.fail("duplicate dispatched"))
                return TextGenerationResult("completed", "raw", {"input": 1, "output": 1}, model, 0)
            self._execute(cache, budget, outer_call)
            self.assertEqual(store.status("doc-1")["attempted_calls"], 1)

    def test_concurrent_independent_reservations_have_one_winner(self):
        with ControlStore(self.path) as store:
            store.get_or_create_task("doc-1", 1, 0.01, "2026-09-30", 256)
        def attempt(index):
            with ControlStore(self.path) as store:
                try:
                    store.reserve("doc-1", stage="translate", worst_case_usd=0.001, cache_key=str(index))
                    return "reserved"
                except BudgetExhaustedError:
                    return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (1, 2)))
        self.assertCountEqual(outcomes, ["reserved", "blocked"])

    def test_unknown_live_usage_retains_hold_and_freezes_without_cache(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            self._execute(cache, budget, lambda *args: TextGenerationResult("completed", "raw", "not_metered", "gpt-6-luna", 0))
            status = store.status("doc-1")
            self.assertTrue(status["stopped"])
            self.assertGreater(status["held_usd"], 0)
            self.assertEqual(store._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0], 0)
            with self.assertRaises(TranslationBudgetError):
                self._execute(cache, budget, call=lambda *args: self.fail("uncertain call retried"))

    def test_transport_exception_is_sanitized_and_hold_survives_reopen(self):
        def failed(*args):
            raise RuntimeError("PRIVATE_EXCEPTION_SENTINEL")
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            with self.assertRaisesRegex(RuntimeControlsError, "reservation retained") as caught:
                self._execute(cache, budget, failed)
            self.assertNotIn("PRIVATE_EXCEPTION_SENTINEL", str(caught.exception))
        with ControlStore(self.path) as store:
            self.assertTrue(store.status("doc-1")["stopped"])
            self.assertGreater(store.status("doc-1")["held_usd"], 0)
            self.assertNotIn("PRIVATE_EXCEPTION_SENTINEL", str([tuple(r) for r in store._conn.execute("SELECT * FROM events")]))

    def test_local_configuration_failure_releases_without_freezing(self):
        from scholarly_translation.model_adapter import OpenAIConfigurationError
        def missing_key(*args):
            raise OpenAIConfigurationError("missing local configuration")
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            with self.assertRaises(OpenAIConfigurationError):
                self._execute(cache, budget, missing_key)
            status = store.status("doc-1")
            self.assertEqual(status["attempted_calls"], 0)
            self.assertEqual(status["held_usd"], 0)
            self.assertFalse(status["stopped"])

    def test_malformed_adapter_result_is_sanitized_and_frozen(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store, "openai")
            with self.assertRaisesRegex(RuntimeControlsError, "invalid provider result"):
                self._execute(cache, budget, lambda *args: SimpleNamespace(text="PRIVATE_RESPONSE_SENTINEL"))
            self.assertTrue(store.status("doc-1")["stopped"])
            self.assertGreater(store.status("doc-1")["held_usd"], 0)

    def test_reservation_overage_below_task_cap_still_freezes(self):
        with ControlStore(self.path) as store:
            store.get_or_create_task("doc-1", 3, 0.01, "2026-09-30", 256)
            event, _ = store.reserve("doc-1", stage="translate", worst_case_usd=0.001)
            before = tuple(store._conn.execute("SELECT * FROM events WHERE event_id=?", (event,)).fetchone())
            store.settle(event, token_usage={"input": 1, "output": 1}, estimate=0.002)
            self.assertTrue(store.status("doc-1")["stopped"])
            self.assertEqual(tuple(store._conn.execute("SELECT * FROM events WHERE event_id=?", (event,)).fetchone()), before)

    def test_counter_reset_cannot_silently_restore_budget(self):
        with ControlStore(self.path) as store:
            store.get_or_create_task("doc-1", 3, 0.01, "2026-09-30", 256)
            event, _ = store.reserve("doc-1", stage="translate", worst_case_usd=0.001)
            store._conn.execute("UPDATE tasks SET calls_reserved=0,reserved_nanos=0 WHERE task_id='doc-1'")
            with self.assertRaises(StoreCorruptionError):
                store.reserve("doc-1", stage="translate", worst_case_usd=0.001)
            store._conn.execute("UPDATE tasks SET calls_reserved=1,reserved_nanos=1000000 WHERE task_id='doc-1'")
            store.settle(event, token_usage={"input": 1, "output": 1}, estimate=0.00003)
            store._conn.execute("UPDATE tasks SET spent_nanos=0 WHERE task_id='doc-1'")
            with self.assertRaises(StoreCorruptionError):
                store.reserve("doc-1", stage="translate", worst_case_usd=0.001)

    def test_cache_model_and_original_event_tampering_fail_closed(self):
        with ControlStore(self.path) as store:
            cache, budget = self._controls(store)
            self._execute(cache, budget)
            store._conn.execute("UPDATE cache SET model='other-model'")
            with self.assertRaises(StoreCorruptionError):
                self._execute(cache, budget, call=lambda *args: self.fail("tamper caused dispatch"))
            store._conn.execute("UPDATE cache SET model='gpt-6-luna'")
            store._conn.execute("UPDATE events SET metadata_json='[]' WHERE outcome='settled'")
            with self.assertRaises(StoreCorruptionError):
                self._execute(cache, budget)

    def test_cli_omitted_path_opens_durable_default_and_shared_document_task(self):
        from scholarly_translation.__main__ import _open_runtime_controls
        with unittest.mock.patch("scholarly_translation.runtime_controls.DEFAULT_CONTROL_STORE", str(self.path)):
            for stage in ("translate", "semantic_review"):
                store, budget, cache = _open_runtime_controls(None, None, 3, 0.01,
                    stage=stage, provider="mock", model="mock-translation-1",
                    document_id="doc-1", unit_id="unit-1", protected_paths=[])
                try:
                    self.assertEqual(store.path, self.path.resolve())
                    self.assertEqual(budget.task_id, "doc-1")
                    if stage == "translate":
                        self._execute(cache, budget)
                    else:
                        self.assertEqual(store.status("doc-1")["attempted_calls"], 1)
                finally:
                    store.close()

    def test_invalid_cli_policy_does_not_create_store(self):
        from scholarly_translation.__main__ import _open_runtime_controls
        for task, amount in (("", 0.01), ("doc-1", float("nan")), ("doc-1", -1)):
            with self.assertRaises(RuntimeControlsError):
                _open_runtime_controls(self.path, task, 3, amount, stage="translate", provider="mock",
                    model="mock-translation-1", document_id="doc-1", unit_id="unit-1", protected_paths=[])
            self.assertFalse(self.path.exists())

    def test_public_status_is_read_only_and_missing_store_not_created(self):
        from scholarly_translation.__main__ import main
        with ControlStore(self.path) as store:
            self._controls(store)
        before = self.path.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["runtime-status", "--control-store", str(self.path), "--task-id", "doc-1"]), 0)
            missing = self.path.parent / "missing.sqlite3"
            self.assertEqual(main(["runtime-status", "--control-store", str(missing), "--task-id", "doc-1"]), 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(missing.exists())

    def test_protected_evidence_sidecar_hardlink_rejected(self):
        evidence = self.path.parent / "source.pdf"
        evidence.write_bytes(b"immutable fixture evidence")
        os.link(str(evidence), str(self.path) + "-journal")
        with self.assertRaises(RuntimeControlsError):
            validate_store_path(self.path, [evidence])
        root = Path(__file__).resolve().parents[1]
        for directory in ("audit", ".git", "tests", ".codex"):
            with self.assertRaises(RuntimeControlsError):
                validate_store_path(root / directory / "controls.sqlite3")


if __name__ == "__main__":
    unittest.main()
