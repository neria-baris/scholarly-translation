"""BLOCK-DECISIONS: user-decided budget/stop blocks (audit/contracts/user_decided_blocks.md)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation import book_notebook as bn
from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import job_blocks
from scholarly_translation.model_adapter import CacheablePrompt, TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore, RuntimeControlsError
from scholarly_translation.work_journal import WorkJournal

from tests.test_pipeline_recovery_contract import configuration

JOB = "a" * 32


def raw(status="completed", text='{"target":"עברית"}', output=10):
    return TextGenerationResult(status, text, {"input": 100, "output": output}, "gpt-6-luna", 0)


class JobBlocksTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "outputs"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        data = configuration().to_dict()
        for model in data["models"].values():
            model["capabilities"]["max_output_tokens"] = 128000
        self.config = ModelConfiguration.from_dict(data)
        self.sent = []
        self.store = ControlStore(self.folder / "controls.sqlite3")
        self.journal = WorkJournal(self.folder / "journal.sqlite3")
        self.addCleanup(self.store.close)
        self.addCleanup(self.journal.close)
        self.job = {"job_id": JOB, "status": "failed", "error": None, "units": [],
                    "settings": {"automation": True, "budget_usd": 1.0, "model_config": self.config.to_dict()}}

    def call(self, response, stage="chapter-translate", role="translator", cap=1000, max_calls=20, hard=1.0, prompt="p"):
        def factory(role_name, descriptor):
            def generate(text, model):
                self.sent.append((stage, descriptor.max_output_tokens))
                if isinstance(response, Exception):
                    raise response
                return response
            return SimpleNamespace(generate=generate)
        return pipeline._controlled(JOB, role, stage, CacheablePrompt("Literal source.\n", prompt), self.config, cap,
            self.store, self.journal, hard, max_calls, 4096, lambda r: json.loads(r.text), {"source": stage}, factory)

    def fail(self, response, **kwargs):
        with self.assertRaises(Exception):
            self.call(response, **kwargs)

    # --- control store user actions -----------------------------------------

    def test_user_settle_known_usage_charges_observed_and_resume_clears_stop(self):
        self.fail(raw("failed_truncated", output=4096))
        status = self.store.status(JOB)
        self.assertTrue(status["stopped"])
        [call] = self.store.uncertain_calls(JOB)
        self.assertIsNotNone(call["known_usd"])
        with self.assertRaises(RuntimeControlsError):
            self.store.user_resume(JOB)
        result = self.store.user_settle(JOB, call["event_id"])
        self.assertEqual(result["basis"], "observed_usage")
        self.store.user_resume(JOB)
        status = self.store.status(JOB)
        self.assertFalse(status["stopped"])
        self.assertAlmostEqual(status["list_estimated_spent_usd"], call["known_usd"], places=8)
        self.assertEqual(status["held_usd"], 0)
        with ControlStore(self.folder / "controls.sqlite3", create=False) as reopened:
            self.assertFalse(reopened.status(JOB)["stopped"])   # integrity check accepts user events

    def test_unknown_usage_settles_at_held_worst_case(self):
        self.fail(RuntimeError("connection lost"))
        [call] = self.store.uncertain_calls(JOB)
        self.assertIsNone(call["known_usd"])
        self.assertEqual(self.store.user_settle(JOB, call["event_id"])["basis"], "held_worst_case")
        self.assertAlmostEqual(self.store.status(JOB)["list_estimated_spent_usd"], call["held_usd"], places=8)

    def test_limits_only_increase(self):
        self.call(raw())
        with self.assertRaises(RuntimeControlsError):
            self.store.user_raise_limits(JOB, hard_list_usd=0.5)
        with self.assertRaises(RuntimeControlsError):
            self.store.user_raise_limits(JOB, max_calls=10)
        self.assertEqual(self.store.user_raise_limits(JOB, max_calls=40, hard_list_usd=2.0),
                         {"max_calls": 40, "hard_list_usd": 2.0})
        self.call(raw(), max_calls=40, hard=2.0, prompt="next")   # policy matches the raised task

    # --- diagnosis and decisions --------------------------------------------

    def test_truncated_notebook_offers_cap_story_and_skip_then_raise_reruns_keeper(self):
        self.job["chapter_completion"], self.job["notebook_applied"] = {}, {"0": True}
        self.fail(raw("failed_truncated", output=4096), stage="chapter-notebook", role="chapter_qa", cap=4096)
        block = job_blocks.diagnose(self.job, self.store, self.journal)
        self.assertEqual(block["kind"], "notebook_truncated")
        ids = [o["id"] for o in block["options"]]
        self.assertEqual(ids, ["raise_notebook_cap", "shorten_notebook", "skip_notebook_chapter"])
        self.assertEqual(block["options"][0]["value"], pipeline.KEEPER_MAX_OUTPUT_TOKENS)
        job_blocks.apply_decision(self.job, self.store, self.journal, "raise_notebook_cap")
        self.assertEqual(self.job["settings"]["keeper_output_cap"], pipeline.KEEPER_MAX_OUTPUT_TOKENS)
        self.assertFalse(self.store.status(JOB)["stopped"])
        self.assertIsNone(job_blocks.diagnose(self.job, self.store, self.journal))
        self.assertEqual(self.job["decisions"][0]["option"], "raise_notebook_cap")

    def test_shorten_notebook_changes_prompt_word_limit(self):
        self.fail(raw("failed_truncated", output=4096), stage="chapter-notebook", role="chapter_qa", cap=4096)
        job_blocks.apply_decision(self.job, self.store, self.journal, "shorten_notebook")
        self.assertEqual(self.job["settings"]["notebook_story_words"], job_blocks.SHORT_STORY_WORDS)
        prompt = bn.build_keeper_prompt("", "src", "עברית", 0, "literary", self.job["settings"]["notebook_story_words"])
        self.assertIn("at most 300 words", prompt)
        self.assertIn("as long as the book needs", bn.build_keeper_prompt("", "src", "עברית", 0, "literary"))

    def test_failed_translation_accept_and_retry_resends_same_step_once(self):
        self.fail(raw("failed_truncated", output=1000))
        block = job_blocks.diagnose(self.job, self.store, self.journal)
        self.assertEqual(block["kind"], "failed_call")
        self.assertEqual([o["id"] for o in block["options"]], ["accept_and_retry"])
        job_blocks.apply_decision(self.job, self.store, self.journal, "accept_and_retry")
        self.assertEqual(self.job["retry_history"][0]["status"], "failed")
        self.assertIsNotNone(self.job["retry_history"][0]["raw_json"])
        self.assertEqual(self.call(raw())[0], {"target": "עברית"})
        self.assertEqual(len(self.sent), 2)

    def test_unknown_outcome_retry_after_worst_case_acceptance(self):
        self.fail(RuntimeError("connection lost"))
        block = job_blocks.diagnose(self.job, self.store, self.journal)
        self.assertEqual(block["kind"], "unknown_outcome")
        job_blocks.apply_decision(self.job, self.store, self.journal, "accept_worst_case_and_retry")
        self.call(raw())
        self.assertEqual(len(self.sent), 2)

    def test_skip_notebook_after_unknown_outcome_unblocks_other_calls(self):
        self.fail(RuntimeError("connection lost"), stage="chapter-notebook", role="chapter_qa")
        job_blocks.apply_decision(self.job, self.store, self.journal, "skip_notebook_chapter")
        self.assertIsNone(job_blocks.diagnose(self.job, self.store, self.journal))
        self.call(raw(), prompt="review")
        self.assertEqual(len(self.sent), 2)

    def test_call_limit_and_budget_limit_raise_settings_and_store(self):
        self.call(raw(), max_calls=1)
        block = job_blocks.diagnose(self.job, self.store, self.journal)
        self.assertEqual(block["kind"], "call_limit")
        job_blocks.apply_decision(self.job, self.store, self.journal, "raise_calls")
        self.assertEqual(self.job["settings"]["max_calls"], 2)
        self.assertEqual(self.store.status(JOB)["max_calls"], 2)
        self.job["error"] = "התרגום נעצר: persistent list-price reservation limit reached"
        block = job_blocks.diagnose(self.job, self.store, self.journal)
        self.assertEqual(block["kind"], "budget_limit")
        with self.assertRaises(job_blocks.BlockDecisionError):
            job_blocks.apply_decision(self.job, self.store, self.journal, "raise_budget", 0.5)
        job_blocks.apply_decision(self.job, self.store, self.journal, "raise_budget", 3.0)
        self.assertEqual(self.job["settings"]["budget_usd"], 3.0)
        self.assertEqual(self.store.status(JOB)["hard_list_usd"], 3.0)

    def test_unoffered_option_and_unblocked_job_are_refused(self):
        with self.assertRaises(job_blocks.BlockDecisionError):
            job_blocks.apply_decision(self.job, self.store, self.journal, "acknowledge")
        self.fail(raw("failed_truncated", output=1000))
        with self.assertRaises(job_blocks.BlockDecisionError):
            job_blocks.apply_decision(self.job, self.store, self.journal, "raise_budget", 9.0)
        self.assertTrue(self.store.status(JOB)["stopped"])

    def test_keeper_cap_override_is_bounded_by_role(self):
        selection, _ = self.config.resolve("chapter_qa")
        self.assertEqual(pipeline.keeper_output_cap(selection), pipeline.KEEPER_MAX_OUTPUT_TOKENS)
        self.assertEqual(pipeline.keeper_output_cap(selection, 10 ** 9), 100000 // 3)


if __name__ == "__main__":
    unittest.main()
