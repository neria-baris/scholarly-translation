"""Offline regression for review reasoning starving the visible answer."""
import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation import chapter_pipeline as pipeline, cross_chapter_qa as cross, model_settings
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import OpenAITextGenerationAdapter
from scholarly_translation.reasoning_budget import review_output_cap
from scholarly_translation.runtime_controls import ControlStore
from scholarly_translation.translation import TranslationBudgetError
from scholarly_translation.work_journal import WorkJournal
from tests.test_runtime_controls import _synthetic_structure

LUNA = {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}
RECORDS = [dict(unit_id="u" + str(i), source_text="Some scholars reject all claims.",
                source_language="en", target_text="חלק מהחוקרים דוחים את כל הטענות.",
                translation_note=None, findings=[]) for i in range(2)]


def config(effort):
    return model_settings.build_configuration({"translator": LUNA,
        "semantic_reviewer": dict(LUNA, reasoning=effort),
        "chapter_qa": dict(LUNA, reasoning=effort)})


class ReasoningCapTests(unittest.TestCase):
    def test_levels_preserve_answer_space_and_increase_total(self):
        caps = []
        for effort in ("none", "low", "medium", "high", "xhigh", "max"):
            selection = config(effort).models["chapter_qa"]
            caps.append(pipeline._review_cap(selection, 2))
            self.assertLessEqual(caps[-1], selection.capabilities.max_output_tokens)
        self.assertEqual(caps[0], 2304)
        self.assertEqual(caps, sorted(set(caps)))
        self.assertEqual(caps[3] - caps[0], 32768)

    def test_implicit_defaults_match_adapter_and_legacy_none_is_unchanged(self):
        luna = model_settings.build_configuration({"translator": LUNA}).models["chapter_qa"]
        sol = model_settings.build_configuration({"translator": dict(LUNA, model="gpt-6.1-sol")}).models["chapter_qa"]
        self.assertEqual(pipeline._review_cap(luna, 2), 2304)
        self.assertEqual(pipeline._review_cap(sol, 2), pipeline._review_cap(
            replace(sol, capabilities=replace(sol.capabilities, reasoning="low")), 2))
        self.assertGreater(pipeline._review_cap(sol, 2), 2304)

    def test_declared_limit_cannot_silently_erase_answer_allowance(self):
        selection = config("high").models["chapter_qa"]
        selection = replace(selection, capabilities=replace(selection.capabilities, max_output_tokens=2304))
        with self.assertRaisesRegex(ValueError, "output capacity"):
            pipeline._review_cap(selection, 2)
        selection = replace(selection, capabilities=replace(selection.capabilities, max_output_tokens=999999))
        with self.assertRaises(ValueError):
            review_output_cap(selection, 128000)

    def test_context_guard_accounts_for_reasoning_and_cross_review_uses_it(self):
        high = config("high").models["chapter_qa"]
        none = config("none").models["chapter_qa"]
        high = replace(high, capabilities=replace(high.capabilities, usable_context_tokens=20000))
        none = replace(none, capabilities=replace(none.capabilities, usable_context_tokens=20000))
        self.assertTrue(pipeline._fits("small prompt", none, pipeline._review_cap(none, 2)))
        self.assertFalse(pipeline._fits("small prompt", high, pipeline._review_cap(high, 2)))
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline.repartition_qa_groups(RECORDS, high.capabilities, selection=high)
        self.assertGreater(cross.cross_qa_output_cap(high), cross.cross_qa_output_cap(none))
        self.assertGreater(pipeline._unit_review_cap(high, RECORDS[0]),
                           pipeline._unit_review_cap(none, RECORDS[0]))

    def test_preview_includes_same_review_caps_and_extra_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            structure = _synthetic_structure(Path(folder), "en", "Some scholars reject all claims.")
            ids = [u["unit_id"] for u in structure["units"]]
            low = pipeline.plan_chapter(structure, new_store(), ids, config("none"), "checked", "scholarly")
            high = pipeline.plan_chapter(structure, new_store(), ids, config("high"), "checked", "scholarly")
            self.assertEqual(high["qa_groups"][0]["call_output_cap"],
                             pipeline._review_cap(config("high").models["chapter_qa"], len(ids)))
            self.assertGreater(high["qa_tail_usd"], low["qa_tail_usd"])
            self.assertGreater(high["expected_total_cost_usd"], low["expected_total_cost_usd"])
            self.assertEqual(high["batches"], low["batches"])

    def test_saved_plan_refresh_preserves_units_context_and_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            structure = _synthetic_structure(folder, "en", "Some scholars reject all claims.")
            units = structure["units"]
            ids = [u["unit_id"] for u in units]
            saved = pipeline.plan_chapter(structure, new_store(), ids, config("none"), "checked", "scholarly")
            job = {"job_id": "resume", "settings": {"quality": "checked", "profile": "scholarly", "budget_usd": 1},
                   "chapter_groups": [ids], "chapter_plans": [saved], "chapter_completion": {},
                   "units": [dict(RECORDS[0])], "chapter_states": {"0": {"revision": 7}}}
            original_units = copy.deepcopy(job["units"])
            with WorkJournal(folder / "journal.sqlite3") as journal:
                journal.pause("resume")
            with ControlStore(folder / "controls.sqlite3") as store:
                with self.assertRaises(pipeline.PipelinePaused):
                    pipeline.execute_document_chapters(job, structure, new_store(), units, config("high"),
                                                       store, folder, lambda job: None)
            self.assertGreater(job["chapter_plans"][0]["qa_tail_usd"], saved["qa_tail_usd"])
            self.assertEqual(job["units"], original_units)
            self.assertEqual(job["chapter_states"], {"0": {"revision": 7}})
            self.assertEqual(job["chapter_groups"], [ids])

    def test_actual_openai_payload_reserves_headroom_and_recheck_replays(self):
        self._dispatch(hard=1)

    def test_insufficient_budget_blocks_before_provider_call(self):
        self._dispatch(hard=.001, blocked=True)

    def _dispatch(self, hard, blocked=False):
        configuration = config("high")
        payloads, held = [], []
        answer = "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none"
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with ControlStore(folder / "controls.sqlite3") as store, WorkJournal(folder / "journal.sqlite3") as journal:
                def create(**payload):
                    payloads.append(payload)
                    held.append(store.status("dispatch")["held_usd"])
                    truncated = payload["max_output_tokens"] <= 2304
                    return SimpleNamespace(status="incomplete" if truncated else "completed",
                        incomplete_details=SimpleNamespace(reason="max_output_tokens" if truncated else None),
                        output_text="" if truncated else answer, model="gpt-6-luna",
                        usage=SimpleNamespace(input_tokens=10, output_tokens=2304 if truncated else 2364,
                                              output_tokens_details=SimpleNamespace(reasoning_tokens=2304)))
                client = SimpleNamespace(responses=SimpleNamespace(create=create))
                def builder(provider, model, **kwargs):
                    return OpenAITextGenerationAdapter(client=client, **kwargs)
                args = ("dispatch", "chapter_qa", RECORDS, configuration, "scholarly", store,
                        journal, hard, 10, 128000, None, "", 0)
                with patch.object(pipeline, "build_translation_adapter", builder):
                    if blocked:
                        with self.assertRaises(TranslationBudgetError):
                            pipeline._run_review(*args)
                        self.assertEqual(payloads, [])
                        return
                    result, replay = pipeline._run_review(*args)
                    self.assertEqual(result["status"], "completed")
                    self.assertFalse(replay)
                    second, replay = pipeline._run_review(*args)
                    self.assertTrue(replay)
                    self.assertEqual(second, result)
                    # A focused recheck gets the same allowance, not a second addition.
                    pipeline._run_review(*args, stage="recheck")
                cap = pipeline._review_cap(configuration.models["chapter_qa"], 2)
                self.assertEqual(len(payloads), 2)
                for payload in payloads:
                    self.assertEqual(payload["max_output_tokens"], cap)
                    self.assertEqual(payload["reasoning"], {"effort": "high"})
                self.assertTrue(all(amount >= cap * .5 / 1000000 for amount in held))
                self.assertEqual(store.status("dispatch")["attempted_calls"], 2)


if __name__ == "__main__":
    unittest.main()
