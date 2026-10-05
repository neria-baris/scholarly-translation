"""Offline crash, budget and pause acceptance tests for the real chapter engine."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.document_draft import extract_structure
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import (
    AnthropicTextGenerationAdapter, CacheablePrompt,
    OpenAIConfigurationError, OpenAITextGenerationAdapter, TextGenerationResult,
)
from scholarly_translation.model_catalog import estimate_cost
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore, PersistentBudget, RuntimeCache
from scholarly_translation.translation import TranslationBudgetError
from scholarly_translation.work_journal import WorkJournal


def configuration(writer="writer", context=100000):
    def role(provider, model):
        return {"provider": provider, "model": model, "capabilities": {
            "context_window": context, "usable_context_tokens": context,
            "max_output_tokens": 4096}}
    return ModelConfiguration.from_dict({"schema_version": 1, "providers": {
        writer: {"type": "openai", "credential_env": "WRITER_API_KEY"},
        "critic": {"type": "anthropic", "credential_env": "CRITIC_API_KEY"}},
        "models": {"translator": role(writer, "gpt-6-luna"),
                   "semantic_reviewer": role("critic", "claude-sonnet-5-5"),
                   "chapter_qa": role("critic", "claude-sonnet-5-5")}})


def result(text, model):
    return TextGenerationResult("completed", text, {"input": 100, "output": 10}, model, 0)


class PipelineRecoveryAcceptanceTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "outputs"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.config = configuration()
        self.calls = []

    def control(self, store, journal, factory, **overrides):
        args = dict(job_id="recovery-job", role="translator", stage="contract-call",
            prompt=CacheablePrompt("Literal source.\n", "Translate it."),
            configuration=self.config, cap=1000, store=store, journal=journal,
            hard_list_usd=1.0, max_calls=20, shared_output_cap=4096,
            validator=lambda raw: json.loads(raw.text), dependencies={"source": "fixed"},
            adapter_factory=factory)
        args.update(overrides)
        return pipeline._controlled(**args)

    def factory(self, role, descriptor):
        def generate(prompt, model):
            self.calls.append((role, descriptor, prompt))
            return result('{"target":"עברית"}', model)
        return SimpleNamespace(generate=generate)

    def test_received_raw_survives_accounting_crash_and_settles_original_event_once(self):
        controls, journal_path = self.folder / "controls.sqlite3", self.folder / "journal.sqlite3"
        with ControlStore(controls) as store, WorkJournal(journal_path) as journal:
            with patch.object(store, "settle", side_effect=RuntimeError("simulated crash")):
                with self.assertRaises(RuntimeError):
                    self.control(store, journal, self.factory)
            row = journal.job_steps("recovery-job")[0]
            self.assertEqual(row["status"], "received")
            self.assertEqual(journal.read_raw(row["identity"])["text"], '{"target":"עברית"}')
            event = row["event_id"]
            self.assertIsNotNone(event)
            self.assertEqual(store.status("recovery-job")["settled_calls"], 0)
        self.assertTrue(controls.is_file())
        with ControlStore(controls, create=True) as store, WorkJournal(journal_path, create=False) as journal:
            actual, replayed = self.control(store, journal, self.factory)
            self.assertEqual(actual, {"target": "עברית"})
            self.assertTrue(replayed)
            before = store.status("recovery-job")
            self.assertEqual(before["settled_calls"], 1)
            settlements = [entry for entry in before["events"] if entry["outcome"] == "settled"]
            self.assertEqual([entry["parent_event_id"] for entry in settlements], [event])
            self.control(store, journal, self.factory)
            after = store.status("recovery-job")
            self.assertEqual(after["list_estimated_spent_usd"], before["list_estimated_spent_usd"])
            self.assertEqual(after["settled_calls"], 1)
        self.assertEqual(len(self.calls), 1)

    def test_unknown_dispatch_blocks_same_and_different_new_steps(self):
        def factory(role, descriptor):
            def generate(*_):
                self.calls.append(role)
                raise RuntimeError("connection lost")
            return SimpleNamespace(generate=generate)
        with ControlStore(self.folder / "controls.sqlite3") as store, WorkJournal(self.folder / "journal.sqlite3") as journal:
            with self.assertRaises(ValueError):
                self.control(store, journal, factory)
            self.assertEqual(journal.job_steps("recovery-job")[0]["status"], "unknown")
            for prompt in (CacheablePrompt("Literal source.\n", "Translate it."), "Different step"):
                with self.assertRaises(pipeline.ChapterPipelineError):
                    self.control(store, journal, factory, prompt=prompt)
            self.assertTrue(store.status("recovery-job")["stopped"])
        self.assertEqual(len(self.calls), 1)

    def test_protected_tail_rejection_never_dispatches_or_consumes_call_limit(self):
        with ControlStore(self.folder / "controls.sqlite3") as store, WorkJournal(self.folder / "journal.sqlite3") as journal:
            with self.assertRaises(TranslationBudgetError):
                self.control(store, journal, self.factory, hard_list_usd=.001, protect_tail_usd=.0009)
            self.assertEqual(store.status("recovery-job")["attempted_calls"], 0)
            self.assertEqual(journal.job_steps("recovery-job")[0]["status"], "planned")
        self.assertEqual(self.calls, [])

    def test_proven_local_missing_key_is_retryable_without_duplicate_paid_call(self):
        def missing(*_):
            raise OpenAIConfigurationError("missing credential")
        with ControlStore(self.folder / "controls.sqlite3") as store, WorkJournal(self.folder / "journal.sqlite3") as journal:
            with self.assertRaises(OpenAIConfigurationError):
                self.control(store, journal, lambda *_: SimpleNamespace(generate=missing))
            self.assertEqual(journal.job_steps("recovery-job")[0]["status"], "planned")
            self.assertEqual(store.status("recovery-job")["attempted_calls"], 0)
            self.control(store, journal, self.factory)
        self.assertEqual(len(self.calls), 1)

    def test_changed_provider_binding_does_not_replay_prior_provider_result(self):
        with ControlStore(self.folder / "controls.sqlite3") as store, WorkJournal(self.folder / "journal.sqlite3") as journal:
            self.control(store, journal, self.factory)
            _, replayed = self.control(store, journal, self.factory, configuration=configuration("replacement"))
            self.assertFalse(replayed)
            self.assertEqual(len(journal.job_steps("recovery-job")), 2)
        self.assertEqual([call[1].provider for call in self.calls], ["writer", "replacement"])

    def document_fixture(self, quality="checked", pages=1):
        path = self.folder / "source.pdf"
        pdf = Canvas(str(path))
        for _ in range(pages):
            pdf.drawString(72, 700, "Some scholars do not accept all claims.")
            pdf.showPage()
        pdf.save()
        structure = extract_structure(path, "en")
        self.assertEqual(len(structure["units"]), pages)
        job = {"job_id": "document-job", "settings": {"quality": quality, "profile": "scholarly", "budget_usd": 10},
            "units": [], "revision": 0, "chapter_qa_results": [], "completed_units": 0}
        return job, structure

    def document_factory(self, pause_at=None, revise=False, qa_text=None):
        def factory(role, descriptor):
            def generate(prompt, model):
                correction = role == "translator" and prompt.startswith("Correct ONLY")
                stage = "correction" if correction else role
                self.calls.append((stage, descriptor, prompt))
                if role == "translator":
                    ids = ([json.loads(prompt.split("\n", 1)[1])["unit_id"]] if correction else
                           json.loads(re.search(r"TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])", prompt).group(1)))
                    target = "חלק מהחוקרים לא מקבלים את כל הטענות." if correction else "חלק מהחוקרים אינם מקבלים את כל הטענות."
                    text = json.dumps([{"unit_id": uid, "translation": target, "translation_note": None} for uid in ids], ensure_ascii=False)
                elif role == "chapter_qa":
                    text = qa_text if qa_text is not None else "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none"
                elif revise and "אינם" in prompt:
                    text = ("VERDICT: REVISE\nISSUES:\n1. Severity: MAJOR\nSource span: not\n"
                            "Translation span: אינם\nProblem: prefer the specified wording\nSuggested correction: לא")
                else:
                    text = "VERDICT: PASS\nISSUES: none"
                if pause_at == stage:
                    with WorkJournal(self.folder / "journal.sqlite3", create=False) as journal:
                        journal.pause("document-job")
                return result(text, model)
            return SimpleNamespace(generate=generate)
        return factory

    def execute(self, job, structure, factory):
        with ControlStore(self.folder / "controls.sqlite3") as store:
            pipeline.execute_document_chapters(job, structure, new_store(), structure["units"],
                self.config, store, self.folder, lambda _: None, factory)
            return store.status(job["job_id"])

    def resume_journal(self):
        with WorkJournal(self.folder / "journal.sqlite3", create=False) as journal:
            journal.resume("document-job")

    def test_checked_execution_passes_resolved_caps_and_prices_alias_provider_types(self):
        job, structure = self.document_fixture()
        status = self.execute(job, structure, self.document_factory())
        self.assertEqual({call[0] for call in self.calls}, {"translator", "semantic_reviewer", "chapter_qa"})
        expected = 0.0
        for role, descriptor, _ in self.calls:
            selection, definition = self.config.resolve(descriptor.role)
            self.assertEqual(descriptor.provider_definition, definition)
            self.assertEqual(descriptor.max_output_tokens, descriptor.capabilities.max_output_tokens)
            self.assertGreater(descriptor.max_output_tokens, 0)
            self.assertLessEqual(descriptor.max_output_tokens, selection.capabilities.max_output_tokens)
            expected += estimate_cost(definition.provider_type, selection.model, {"input": 100, "output": 10})["cost_usd"]
        self.assertAlmostEqual(status["list_estimated_spent_usd"], expected, places=8)
        usage = status["provider_usage"]
        self.assertEqual({row["provider"] for row in usage}, {"writer", "critic"})
        self.assertEqual(sum(row["calls"] for row in usage), len(self.calls))
        self.assertEqual(sum(row["input"] for row in usage), 100 * len(self.calls))
        self.assertEqual(sum(row["output"] for row in usage), 10 * len(self.calls))
        self.assertEqual(sum(row["cached"] for row in usage), 0)
        self.assertEqual(sum(row["unmetered_calls"] for row in usage), 0)
        self.assertTrue(job["chapter_completion"]["0"])
        self.assertFalse(job["units"][0]["approved"])

    def test_provider_usage_excludes_verified_local_cache_hit(self):
        with ControlStore(self.folder / "controls.sqlite3") as store, WorkJournal(self.folder / "journal.sqlite3") as journal:
            self.control(store, journal, self.factory)
            identity = journal.job_steps("recovery-job")[0]["identity"]
            budget = PersistentBudget(store, "recovery-job", max_calls=20, hard_list_usd=1,
                stage="contract-call", provider="writer", model="gpt-6-luna",
                pricing_provider="openai", output_cap=4096, call_output_cap=1000)
            _, hit, _ = RuntimeCache(store, stage="contract-call", provider="writer", model="gpt-6-luna").execute(
                identity, CacheablePrompt("Literal source.\n", "Translate it."), "gpt-6-luna",
                lambda *_: self.fail("verified local result must not dispatch"), stage="contract-call",
                metadata={"document_id": "recovery-job", "unit_id": None, "provider_type": "openai"}, budget=budget)
            status = store.status("recovery-job")
            self.assertTrue(hit)
            self.assertEqual(status["cache_hits"], 1)
            self.assertEqual(sum(row["calls"] for row in status["provider_usage"]), 1)
            self.assertEqual(sum(row["input"] for row in status["provider_usage"]), 100)

    def test_malformed_chapter_qa_is_visible_as_draft_with_exceptions(self):
        job, structure = self.document_fixture()
        self.execute(job, structure, self.document_factory(qa_text="unstructured QA response"))
        self.assertEqual(job["chapter_qa_results"][0]["status"], "needs_human")
        self.assertEqual(job["quality_status"], "draft_with_exceptions")
        self.assertFalse(job["units"][0]["approved"])

    def test_nonpassing_minor_chapter_qa_is_visible_as_draft_with_exceptions(self):
        job, structure = self.document_fixture()
        qa = ("VERDICT: REVISE\nISSUES:\n1. Category: hebrew_quality\nSeverity: MINOR\n"
              "Span: חלק מהחוקרים\nCorrection: מקצת החוקרים\nCHAPTER_LEVEL_NOTES: wording\nSTATE_UPDATES: none")
        self.execute(job, structure, self.document_factory(qa_text=qa))
        self.assertEqual(job["chapter_qa_results"][0]["verdict"], "REVISE")
        self.assertEqual(job["quality_status"], "draft_with_exceptions")

    def test_pause_after_translation_resumes_without_translator_resend(self):
        job, structure = self.document_fixture()
        with self.assertRaises(pipeline.PipelinePaused):
            self.execute(job, structure, self.document_factory(pause_at="translator"))
        self.assertEqual([call[0] for call in self.calls], ["translator"])
        self.assertEqual(job["completed_units"], 1)
        self.resume_journal()
        self.execute(job, structure, self.document_factory())
        self.assertEqual([call[0] for call in self.calls].count("translator"), 1)
        self.assertTrue(job["chapter_completion"]["0"])

    def test_pause_after_correction_resumes_only_pending_recheck(self):
        job, structure = self.document_fixture()
        with self.assertRaises(pipeline.PipelinePaused):
            self.execute(job, structure, self.document_factory(pause_at="correction", revise=True))
        self.assertTrue(job["units"][0]["correction_pending_recheck"])
        before = len(self.calls)
        self.resume_journal()
        self.execute(job, structure, self.document_factory(revise=True))
        self.assertEqual([call[0] for call in self.calls[before:]], ["semantic_reviewer"])
        self.assertEqual([call[0] for call in self.calls].count("correction"), 1)
        self.assertEqual(job["units"][0]["recheck"]["verdict"], "PASS")
        self.assertFalse(job["units"][0]["correction_pending_recheck"])

    def test_source_prefix_remains_stable_across_target_batches(self):
        _, structure = self.document_fixture("fast", pages=2)
        first, second = structure["units"]
        all_ids = [first["unit_id"], second["unit_id"]]
        prompts = [pipeline.build_batch_translation_prompt(structure, new_store(), [uid], "scholarly",
                   source_unit_ids=all_ids) for uid in all_ids]
        self.assertEqual(prompts[0].stable_prefix, prompts[1].stable_prefix)
        self.assertNotEqual(prompts[0].suffix, prompts[1].suffix)


class FakeStream:
    def __init__(self, final):
        self.final = final
        self.closed = False
        self.final_reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def __iter__(self):
        yield SimpleNamespace(type="text.delta")

    def get_final_response(self):
        self.final_reads += 1
        return self.final

    get_final_message = get_final_response


class StreamingCapacityAcceptanceTests(unittest.TestCase):
    def clients(self):
        responses = SimpleNamespace(status="completed", output_text="עברית", model="gpt-6-luna",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                input_tokens_details=SimpleNamespace(cached_tokens=30, cache_write_tokens=10)))
        messages = SimpleNamespace(content=[SimpleNamespace(text="עברית")], stop_reason="end_turn",
            model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=60, output_tokens=20,
                cache_read_input_tokens=30, cache_creation_input_tokens=10))
        for adapter_type, api_name, final, model in (
            (OpenAITextGenerationAdapter, "responses", responses, "gpt-6-luna"),
            (AnthropicTextGenerationAdapter, "messages", messages, "claude-sonnet-5-5")):
            stream = FakeStream(final)
            api = SimpleNamespace(stream=lambda **kwargs: stream,
                create=lambda **kwargs: self.fail("large generation must use streaming"))
            client = SimpleNamespace(**{api_name: api})
            yield adapter_type, client, stream, model

    def test_large_generation_preserves_final_complete_text_and_cache_usage(self):
        for adapter_type, client, stream, model in self.clients():
            with self.subTest(provider=adapter_type.__name__):
                adapter = adapter_type(client=client, max_output_tokens=9000)
                answer = adapter.generate(CacheablePrompt("source", "target"), model)
                self.assertEqual(answer.status, "completed")
                self.assertEqual(answer.text, "עברית")
                self.assertEqual(answer.token_usage, {"input": 100, "output": 20, "cached": 30, "cache_write": 10})
                self.assertEqual(stream.final_reads, 1)
                self.assertTrue(stream.closed)

    def test_stream_wall_deadline_closes_stream_and_marks_unknown_usage(self):
        for adapter_type, client, stream, model in self.clients():
            with self.subTest(provider=adapter_type.__name__):
                adapter = adapter_type(client=client, max_output_tokens=9000, max_wall_seconds=5)
                with patch("scholarly_translation.model_adapter.time.monotonic", side_effect=[0, 6, 7]):
                    answer = adapter.generate("literal source", model)
                self.assertEqual(answer.status, "failed_transport")
                self.assertEqual(answer.token_usage, "not_metered")
                self.assertTrue(stream.closed)
                self.assertEqual(stream.final_reads, 0)


if __name__ == "__main__":
    unittest.main()
