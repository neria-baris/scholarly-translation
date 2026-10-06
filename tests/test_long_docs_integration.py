"""LONG-DOCS integration: structural chapters + size fitting + unit policy wired
into preview and the real chapter engine, with persisted groups for resume.
Offline: mock adapters only, no provider/network calls."""
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import document_draft as dd
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore
from scholarly_translation.work_journal import WorkJournal

from tests.test_long_docs_input import build_epub, para_chapter

_TITLE_RE = re.compile(r"\bc(\d{2}) sentence number")


def config_dict(translator_output=128000):
    def role(provider, model, cap):
        return {"provider": provider, "model": model, "capabilities": {
            "context_window": 1000000, "usable_context_tokens": 800000, "max_output_tokens": cap}}
    return {"schema_version": 1, "providers": {
        "openai": {"type": "openai", "credential_env": "OPENAI_API_KEY"}}, "models": {
        "translator": role("openai", "gpt-6.1-sol", translator_output),
        "semantic_reviewer": role("openai", "gpt-6-luna", 128000),
        "chapter_qa": role("openai", "gpt-6-luna", 128000)}}


class LongDocsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / "outputs"
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        cls.book = Path(cls.temp.name) / "long.epub"
        cls.book.write_bytes(build_epub([("c%02d.xhtml" % i, para_chapter("c%02d" % i, 180)) for i in range(50)]))
        cls.structure = dd.extract_structure(cls.book, "en")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.config = ModelConfiguration.from_dict(config_dict())
        self.calls = []
        self.keeper_calls = 0

    def job(self, quality="fast"):
        return {"job_id": "long-job", "settings": {"quality": quality, "profile": "literary", "budget_usd": 40},
                "units": [], "revision": 0, "chapter_qa_results": [], "completed_units": 0}

    def factory(self, pause_after=None):
        def make(role, descriptor):
            def generate(prompt, model):
                if "rolling NOTEBOOK for a book" in prompt:  # book-notebook keeper step (not a translation call)
                    self.keeper_calls += 1
                    return TextGenerationResult("completed", '{"ops": []}', {"input": 100, "output": 10}, model, 0)
                self.calls.append((role, prompt))
                ids = json.loads(re.search(r"TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])", prompt).group(1))
                text = json.dumps([{"unit_id": uid, "translation": "תרגום", "translation_note": None}
                                   for uid in ids], ensure_ascii=False)
                if pause_after is not None and len(self.calls) == pause_after:
                    with WorkJournal(self.folder / "journal.sqlite3", create=False) as journal:
                        journal.pause("long-job")
                return TextGenerationResult("completed", text, {"input": 100, "output": 10}, model, 0)
            return SimpleNamespace(generate=generate)
        return make

    def execute(self, job, factory):
        with ControlStore(self.folder / "controls.sqlite3") as store:
            pipeline.execute_document_chapters(job, self.structure, new_store(), self.structure["units"],
                                               self.config, store, self.folder, lambda _: None, factory)

    def test_long_book_translates_chapter_by_chapter(self):
        job = self.job()
        start = time.time()
        self.execute(job, self.factory())
        print("800k-char 50-chapter mock run seconds: %.1f" % (time.time() - start))
        self.assertEqual(len(job["chapter_groups"]), 50)
        self.assertEqual(sorted(uid for g in job["chapter_groups"] for uid in g),
                         sorted(u["unit_id"] for u in self.structure["units"]))
        self.assertEqual(len(job["units"]), len(self.structure["units"]))
        self.assertTrue(all(job["chapter_completion"].values()))
        batches = sum(len(plan["batches"]) for plan in job["chapter_plans"])
        self.assertEqual(len(self.calls), batches)
        for _, prompt in self.calls:
            # Each request carries one chapter's source, never the whole book.
            self.assertEqual(len(set(_TITLE_RE.findall(prompt.split("PREVIOUS_PASSAGE")[0]))), 1)
            self.assertLess(len(prompt), 60000)

    def test_pause_resume_keeps_groups_and_never_resends(self):
        job = self.job()
        with self.assertRaises(pipeline.PipelinePaused):
            self.execute(job, self.factory(pause_after=3))
        groups = json.loads(json.dumps(job["chapter_groups"]))
        with WorkJournal(self.folder / "journal.sqlite3", create=False) as journal:
            journal.resume("long-job")
        self.execute(job, self.factory())
        self.assertEqual(job["chapter_groups"], groups)
        targets = [uid for _, prompt in self.calls
                   for uid in json.loads(re.search(r"TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])", prompt).group(1))]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(len(job["units"]), len(self.structure["units"]))

    def test_job_planned_before_persisted_groups_is_never_regrouped(self):
        units = self.structure["units"][:6]
        ids = [u["unit_id"] for u in units]
        legacy = {"chapter_plans": [{"batches": [{"unit_ids": ids[:4]}, {"unit_ids": ids[4:]}]}]}
        groups = pipeline._job_chapter_groups(legacy, self.structure, new_store(), units, self.config, "fast", "literary")
        self.assertEqual([[u["unit_id"] for u in g] for g in groups], [ids])

    def test_persisted_groups_must_cover_the_units(self):
        units = self.structure["units"][:4]
        job = {"chapter_groups": [[units[0]["unit_id"]]]}
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline._job_chapter_groups(job, self.structure, new_store(), units, self.config, "fast", "literary")

    def test_preview_uses_real_chapters_quickly(self):
        jobs = dd.DocumentJobs(self.folder)
        for quality in ("fast", "checked", "thorough"):
            start = time.time()
            preview = jobs.preview(self.book, {"model": "configured", "budget_usd": 2.0, "model_config": config_dict(),
                                               "quality": quality, "profile": "literary"})
            elapsed = time.time() - start
            print("preview %s seconds: %.1f" % (quality, elapsed))
            self.assertEqual(preview["chapter_count"], 50)
            self.assertLess(elapsed, 60)

    def test_small_output_translator_narrows_units_instead_of_failing(self):
        jobs = dd.DocumentJobs(self.folder)
        preview = jobs.preview(self.book, {"model": "configured", "budget_usd": 2.0, "model_config": config_dict(8192),
                                           "quality": "fast", "profile": "literary"})
        self.assertGreaterEqual(preview["chapter_count"], 50)
        self.assertGreater(preview["expected_total_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
