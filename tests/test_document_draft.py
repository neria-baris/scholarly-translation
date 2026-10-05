import json
import tempfile
import time
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.document_draft import (
    DocumentDraftError, DocumentJobs, extract_structure, render_download, validate_settings,
)
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.translation_profiles import style_profile_text

import pdf_fixture
from test_export_epub import make_epub


def _build_pdf(path, pages_lines):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    _, height = LETTER
    for lines in pages_lines:
        y = height - 100
        for i, text in enumerate(lines):
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 14 if i == 0 else 12)
            c.drawString(72, y, text)
            y -= 28
        c.showPage()
    c.save()


def make_simple_pdf(path):
    _build_pdf(path, [
        ["Some scholars do not accept 3 claims about the argument today."],
        ["A second paragraph with more content for the second page here."],
    ])


def make_chaptered_pdf(path):
    _build_pdf(path, [
        ["Chapter 1", "The first chapter contains an opening argument worth reading."],
        ["Chapter 2", "The second chapter continues the discussion in more detail."],
    ])


class FakeTranslationAdapter:
    """Deterministic non-network stand-in for a configured translator role."""

    def __init__(self, prefix="תרגום מדומה: "):
        self.prefix = prefix
        self.calls = []

    def generate(self, prompt_text, model):
        self.calls.append(prompt_text)
        return TextGenerationResult(
            status="completed", text=self.prefix + "טקסט עברי לדוגמה.",
            token_usage={"input": 10, "output": 5}, observed_model=model,
            duration_seconds=0.0, observed_provider="fake",
        )


class FakeReviewAdapter:
    def __init__(self, verdict_text="VERDICT: PASS\nISSUES: none"):
        self.verdict_text = verdict_text
        self.calls = 0

    def generate(self, prompt_text, model):
        self.calls += 1
        return TextGenerationResult(
            status="completed", text=self.verdict_text, token_usage={"input": 5, "output": 2},
            observed_model=model, duration_seconds=0.0, observed_provider="fake",
        )


class FakeChapterQAAdapter:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt_text, model):
        self.calls += 1
        return TextGenerationResult(
            status="completed",
            text="VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)\nSTATE_UPDATES: none",
            token_usage={"input": 5, "output": 2}, observed_model=model,
            duration_seconds=0.0, observed_provider="fake",
        )


MOCK_MODEL_CONFIG = {
    "schema_version": 1,
    "providers": {"fake": {"type": "openai", "credential_env": "FAKE_TEST_API_KEY"}},
    "models": {
        "translator": {"provider": "fake", "model": "fake-translator-1",
                        "capabilities": {"context_window": 8000, "usable_context_tokens": 6000}},
        "semantic_reviewer": {"provider": "fake", "model": "fake-reviewer-1",
                              "capabilities": {"context_window": 8000, "usable_context_tokens": 6000}},
        "chapter_qa": {"provider": "fake", "model": "fake-chapter-qa-1",
                       "capabilities": {"context_window": 8000, "usable_context_tokens": 6000}},
    },
}


class DocumentDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "paper.pdf"
        make_simple_pdf(self.path)

    def make_adapter_factory(self, translator=None, reviewer=None, chapter_qa=None):
        fakes = {"translator": translator, "semantic_reviewer": reviewer, "chapter_qa": chapter_qa}

        def factory(role, request):
            return fakes[role]
        return factory

    def run_job(self, settings, manager=None, adapter_factory=None, paid_confirm=None):
        jobs = manager or DocumentJobs(self.root, adapter_factory=adapter_factory)
        if paid_confirm is None:
            paid_confirm = settings.get("model") == "configured"
        started = jobs.start(self.path, settings, paid_confirm=paid_confirm)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = jobs.get(started["job_id"])
            if result["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                while jobs.active and time.monotonic() < deadline:
                    time.sleep(0.01)
                return jobs, jobs.get(started["job_id"])
            time.sleep(0.01)
        self.fail("document worker did not complete")

    # --- settings validation -------------------------------------------------

    def test_bad_settings_rejected(self):
        for bad in (
            {"profile": "invented"}, {"quality": "magic"}, {"budget_usd": float("nan")},
            {"budget_usd": True}, {"model": "invented-model"},
            {"model": "configured"},  # no model_config supplied
            {"model": "configured", "model_config": {"not": "valid"}},
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "profile": "literary", "budget_usd": 100},
        ):
            with self.assertRaises(DocumentDraftError):
                validate_settings(bad)

    def test_auto_is_the_default_and_requires_no_model_config(self):
        settings = validate_settings({})
        self.assertEqual(settings["model"], "auto")
        self.assertIsNone(settings["model_config"])

    # --- EPUB end-to-end (Session G: reconciled with export_epub.py) ----------

    def test_invalid_epub_upload_is_rejected_with_a_clear_message(self):
        epub_path = self.root / "book.epub"
        epub_path.write_bytes(b"not a real epub")
        with self.assertRaisesRegex(DocumentDraftError, "לא ניתן"):
            extract_structure(epub_path)

    def test_epub_fast_mode_auto_model_exports_valid_epub(self):
        epub_path = self.root / "book.epub"
        make_epub(epub_path)
        jobs = DocumentJobs(self.root)
        started = jobs.start(epub_path, {"model": "auto", "quality": "fast"})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["source_kind"], "epub")
        source_path = jobs.source_path(job["job_id"], "epub")
        body = render_download(job, "epub", source_path=source_path)
        self.assertTrue(body.startswith(b"PK"))  # EPUB is a zip archive

    def test_epub_configured_mode_end_to_end_with_chapter_qa_and_state(self):
        epub_path = self.root / "book.epub"
        make_epub(epub_path)
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        jobs = DocumentJobs(self.root, adapter_factory=factory)
        started = jobs.start(
            epub_path, {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "thorough"},
            paid_confirm=True,
        )
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        self.assertGreaterEqual(chapter_qa.calls, 1)
        source_path = jobs.source_path(job["job_id"], "epub")
        body = render_download(job, "epub", source_path=source_path)
        self.assertTrue(body.startswith(b"PK"))
        # The rebuilt EPUB actually contains the translated text, not the
        # original-language source.
        self.assertIn(translator.prefix.encode("utf-8"), body)

    # --- PDF end-to-end, Fast mode, Auto/mock model -----------------------------

    def test_pdf_fast_mode_auto_model_exports_valid_pdf_with_no_review_calls(self):
        _, job = self.run_job({"model": "auto", "quality": "fast"})
        self.assertEqual(job["status"], "completed")
        self.assertGreater(job["total_units"], 0)
        self.assertEqual(job["completed_units"], job["total_units"])
        self.assertEqual(job["review_notes"], [])  # Fast never even asks review_qa to skip
        self.assertEqual(job["chapter_qa_results"], [])
        body = render_download(job, "pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_zero_extractable_text_raises_clear_error(self):
        blank = self.root / "blank.pdf"
        pdf_fixture.build_blank_page_fixture(blank)
        with self.assertRaisesRegex(DocumentDraftError, "OCR"):
            extract_structure(blank)

    # --- profile selection reaches the actual translation request --------------

    def test_profile_choice_reaches_translation_request_prompt(self):
        for profile in ("scholarly", "literary"):
            translator = FakeTranslationAdapter()
            factory = self.make_adapter_factory(translator=translator)
            jobs = DocumentJobs(self.root, adapter_factory=factory)
            _, job = self.run_job(
                {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "profile": profile, "quality": "fast"},
                manager=jobs, adapter_factory=factory,
            )
            self.assertEqual(job["status"], "completed")
            self.assertTrue(translator.calls)
            self.assertIn(style_profile_text(profile), translator.calls[0])

    # --- quality-mode -> review_qa policy mapping -------------------------------

    def test_fast_mode_calls_no_review_adapter_at_all(self):
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        _, job = self.run_job(
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "fast"},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(reviewer.calls, 0)
        self.assertEqual(chapter_qa.calls, 0)

    def test_thorough_mode_reviews_every_unit_and_runs_chapter_qa(self):
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        _, job = self.run_job(
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "thorough"},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(reviewer.calls, job["total_units"])
        self.assertGreaterEqual(chapter_qa.calls, 1)
        self.assertTrue(all(u["review"]["status"] == "completed" for u in job["units"]))

    def test_checked_mode_triggers_chapter_qa_after_chapter_assembled(self):
        chaptered = self.root / "chaptered.pdf"
        make_chaptered_pdf(chaptered)
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        jobs = DocumentJobs(self.root, adapter_factory=factory)
        started = jobs.start(chaptered, {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "checked"},
                            paid_confirm=True)
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        self.assertGreaterEqual(chapter_qa.calls, 1)
        self.assertEqual(len(job["chapter_qa_results"]), chapter_qa.calls)

    def test_role_not_configured_skips_gracefully_with_a_note(self):
        partial_config = {**MOCK_MODEL_CONFIG, "models": {"translator": MOCK_MODEL_CONFIG["models"]["translator"]}}
        translator = FakeTranslationAdapter()
        factory = self.make_adapter_factory(translator=translator)
        _, job = self.run_job(
            {"model": "configured", "model_config": partial_config, "quality": "thorough"},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertTrue(job["review_notes"])

    # --- Auto never runs review_qa against non-Hebrew placeholder text ---------

    def test_auto_mode_review_is_a_graceful_noop_not_a_crash(self):
        _, job = self.run_job({"model": "auto", "quality": "thorough"})
        self.assertEqual(job["status"], "completed")
        self.assertTrue(job["review_notes"])
        self.assertTrue(all(u["review"] is None for u in job["units"]))

    # --- export limitations reach the job record --------------------------------

    def test_export_limitations_reach_job_record(self):
        noted = self.root / "footnote.pdf"
        _build_pdf(noted, [["[1] A footnote-style line that classifies as a note block."]])
        jobs = DocumentJobs(self.root)
        started = jobs.start(noted, {"model": "auto", "quality": "fast"}, paid_confirm=False)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        self.assertTrue(any(limit["kind"] == "footnotes_rendered_inline" for limit in job["export_limitations"]))

    # --- job surviving/resuming the same way as before --------------------------

    def test_finished_job_recovers_after_restart_but_inflight_not_retried(self):
        jobs, job = self.run_job({"model": "auto", "quality": "fast"})
        recovered = DocumentJobs(self.root).get(job["job_id"])
        self.assertEqual(recovered["status"], "completed")
        folder = jobs.root / job["job_id"]
        job["status"] = "translating"
        (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")
        self.assertEqual(DocumentJobs(self.root).get(job["job_id"])["status"], "interrupted")

    # --- human edit / revision tracking -----------------------------------------

    def test_optional_review_versions_edits_without_approval_and_refuses_stale(self):
        jobs, job = self.run_job({"model": "auto", "quality": "fast"})
        edited = jobs.review(job["job_id"], 0, "טיוטה שנערכה ובה 3 טענות.", 0)
        self.assertEqual(edited["revision"], 1)
        self.assertFalse(edited["approved"])
        self.assertTrue(edited['units'][0]['review_stale'])
        self.assertEqual(edited['quality_status'], 'edited_draft_review_stale')
        previous = json.loads((jobs.root / job['job_id'] / 'revision-0.json').read_text(encoding='utf-8'))
        self.assertNotEqual(previous['units'][0]['target_text'], edited['units'][0]['target_text'])
        self.assertTrue((jobs.root / job["job_id"] / "revision-0.json").is_file())
        with self.assertRaises(DocumentDraftError):
            jobs.review(job["job_id"], 0, "עריכה ישנה", 0)
        body = render_download(edited, "pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_paid_job_requires_explicit_consent(self):
        jobs = DocumentJobs(self.root, adapter_factory=self.make_adapter_factory(FakeTranslationAdapter()))
        with self.assertRaises(DocumentDraftError):
            jobs.start(self.path, {"model": "configured", "model_config": MOCK_MODEL_CONFIG}, paid_confirm=False)

    # --- budget/cache wiring (Session G: review/QA calls now share the
    # document's persistent budget and cache, not a separate free path) ----

    def test_estimated_cost_usd_updates_as_the_job_progresses(self):
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        _, job = self.run_job(
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "thorough"},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertGreater(job["estimated_cost_usd"], 0.0)

    def test_review_and_chapter_qa_calls_share_the_translation_budget_and_cache(self):
        chaptered = self.root / "chaptered.pdf"
        make_chaptered_pdf(chaptered)
        translator, reviewer, chapter_qa = FakeTranslationAdapter(), FakeReviewAdapter(), FakeChapterQAAdapter()
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        jobs = DocumentJobs(self.root, adapter_factory=factory)
        started = jobs.start(
            chaptered, {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "thorough"},
            paid_confirm=True,
        )
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        from scholarly_translation.runtime_controls import ControlStore
        store_path = jobs.root / job["job_id"] / "controls.sqlite3"
        self.assertTrue(store_path.is_file())
        with ControlStore(store_path, create=False) as store:
            status = store.status(job["job_id"])
            stages = {event["stage"] for event in status["events"]}
        # The same persistent per-document task now covers every stage --
        # not just "translate" with review/QA calls bypassing it entirely.
        self.assertIn("translate", stages)
        self.assertIn("unit-review", stages)
        self.assertIn("chapter-qa", stages)
        self.assertGreater(status["list_estimated_spent_usd"], 0.0)

    def test_one_active_job_at_a_time(self):
        jobs = DocumentJobs(self.root)
        jobs.start(self.path, {"model": "auto"}, paid_confirm=False)
        with self.assertRaises(DocumentDraftError):
            jobs.start(self.path, {"model": "auto"}, paid_confirm=False)
        deadline = time.monotonic() + 10
        while jobs.active and time.monotonic() < deadline:
            time.sleep(0.01)

    # --- automation=True: the new planned/batched chapter_pipeline flow ----

    def test_automation_defaults_to_false_and_is_boolean(self):
        self.assertFalse(validate_settings({})["automation"])
        self.assertTrue(validate_settings({"automation": True})["automation"])
        with self.assertRaises(DocumentDraftError):
            validate_settings({"automation": "yes"})

    def test_automation_fast_mode_end_to_end_batched_translation(self):
        import json as _json

        class FakeBatchTranslationAdapter:
            def __init__(self):
                self.calls = []

            def generate(self, prompt_text, model):
                self.calls.append(prompt_text)
                suffix = prompt_text.suffix if hasattr(prompt_text, "suffix") else prompt_text
                marker = "TARGET_UNIT_IDS (translate exactly these ids, in exactly this order, each exactly once): "
                start = suffix.index(marker) + len(marker)
                end = suffix.index("\n", start)
                unit_ids = _json.loads(suffix[start:end])
                payload = [{"unit_id": uid, "translation": f"תרגום של {uid}", "translation_note": None}
                          for uid in unit_ids]
                return TextGenerationResult(
                    status="completed", text=_json.dumps(payload, ensure_ascii=False),
                    token_usage={"input": 10, "output": 10}, observed_model=model,
                    duration_seconds=0.0, observed_provider="fake",
                )

        translator = FakeBatchTranslationAdapter()
        factory = self.make_adapter_factory(translator=translator)
        _, job = self.run_job(
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "fast", "automation": True},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["completed_units"], job["total_units"])
        self.assertTrue(translator.calls)
        self.assertTrue(all("תרגום של" in u["target_text"] for u in job["units"]))
        # The stable chapter-source/profile/glossary prefix precedes the
        # dynamic target-ids/state suffix in exactly the dispatched prompt.
        self.assertIn("SOURCE_UNITS", translator.calls[0].stable_prefix)
        self.assertIn("TARGET_UNIT_IDS", translator.calls[0].suffix)
        body = render_download(job, "pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_automation_false_keeps_the_legacy_per_unit_path(self):
        translator = FakeTranslationAdapter()
        factory = self.make_adapter_factory(translator=translator)
        _, job = self.run_job(
            {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "fast", "automation": False},
            adapter_factory=factory,
        )
        self.assertEqual(job["status"], "completed")
        self.assertTrue(translator.calls)
        self.assertFalse((self.root / "documents" / job["job_id"] / "journal.sqlite3").exists())


class _StatefulChapterQAAdapter:
    """A FakeChapterQAAdapter stand-in that returns a different scripted
    response per call, so a test can control exactly what each chapter's
    QA pass proposes (used only by ChapterQAPersistentStateTests below)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.prompts = []

    def generate(self, prompt_text, model):
        self.prompts.append(prompt_text)
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return TextGenerationResult(
            status="completed", text=text, token_usage={"input": 5, "output": 2},
            observed_model=model, duration_seconds=0.0, observed_provider="fake",
        )


class ChapterQAPersistentStateTests(unittest.TestCase):
    """End-to-end coverage of the 2026-10-05 addendum's ten required test
    scenarios (Session G: wiring Session C's chapter QA into Session D's
    document_state.py) -- exercised through the real job runner, not just
    review_qa.py/document_state.py in isolation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_adapter_factory(self, translator=None, reviewer=None, chapter_qa=None):
        fakes = {"translator": translator, "semantic_reviewer": reviewer, "chapter_qa": chapter_qa}

        def factory(role, request):
            return fakes[role]
        return factory

    CHAPTER_ONE_PROPOSES_TWO_ITEMS = (
        "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)\nSTATE_UPDATES:\n"
        "- [terminology] argument :: consistently rendered as \"טענה\" :: likely :: "
        "opening argument\n"
        "- [character] narrator :: formal, third-person register :: unresolved :: "
        "The first chapter contains an opening argument worth reading.\n"
    )
    CHAPTER_TWO_CONTRADICTS_AND_PASSES = (
        "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)\nSTATE_UPDATES:\n"
        "- [terminology] argument :: rendered instead as \"טיעון\" :: likely :: "
        "The second chapter continues the discussion in more detail.\n"
    )

    def _run_two_chapter_job(self, quality="checked"):
        chaptered = self.root / "chaptered.pdf"
        make_chaptered_pdf(chaptered)
        translator, reviewer = FakeTranslationAdapter(), FakeReviewAdapter()
        chapter_qa = _StatefulChapterQAAdapter([
            self.CHAPTER_ONE_PROPOSES_TWO_ITEMS, self.CHAPTER_TWO_CONTRADICTS_AND_PASSES,
        ])
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        jobs = DocumentJobs(self.root, adapter_factory=factory)
        started = jobs.start(
            chaptered, {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": quality},
            paid_confirm=True,
        )
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        return jobs, job, translator, chapter_qa

    def test_01_terminology_choice_carries_into_the_next_chapter(self):
        _, job, translator, chapter_qa = self._run_two_chapter_job()
        self.assertEqual(job["status"], "completed")
        self.assertGreaterEqual(chapter_qa.calls, 2)
        # The committed Hebrew rendering only appears in prompts sent AFTER
        # chapter one's QA committed it -- never in chapter one's own
        # translation prompts.
        first_chapter_prompts = translator.calls[:2]
        later_prompts = translator.calls[2:]
        self.assertFalse(any("טענה" in p for p in first_chapter_prompts))
        self.assertTrue(any("טענה" in p for p in later_prompts))

    def test_02_literary_character_register_persists_the_same_way(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        items = job["document_state"]["items"]
        character_items = [i for i in items if i["category"] == "character" and i["label"] == "narrator"]
        self.assertEqual(len(character_items), 1)
        self.assertEqual(character_items[0]["certainty"], "unresolved")

    def test_03_chapter_qa_can_propose_a_state_update(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        self.assertEqual(job["chapter_qa_results"][0]["state_proposed"], 2)
        self.assertEqual(job["chapter_qa_results"][0]["state_committed"], 2)

    def test_04_state_item_retains_source_provenance(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        item = next(i for i in job["document_state"]["items"] if i["label"] == "argument")
        source = item["source"]
        self.assertTrue(source["chapter_node_id"])
        self.assertTrue(source["unit_ids"])
        self.assertEqual(source["document_id"], job["document_state"]["document_id"])
        self.assertLess(source["source_char_start"], source["source_char_end"])

    def test_05_unresolved_ambiguity_is_never_promoted_to_established(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        item = next(i for i in job["document_state"]["items"] if i["label"] == "narrator")
        self.assertEqual(item["certainty"], "unresolved")
        self.assertTrue(all(i["certainty"] != "established" for i in job["document_state"]["items"]))

    def test_06_contradiction_with_existing_state_is_surfaced_not_overwritten(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        self.assertEqual(len(job["chapter_qa_results"]), 2)
        second = job["chapter_qa_results"][1]
        self.assertEqual(second["state_proposed"], 1)
        self.assertEqual(second["state_committed"], 0)  # contradiction withheld, not auto-applied
        self.assertTrue(second["state_conflicts"])
        self.assertEqual(second["state_conflicts"][0]["label"], "argument")
        # The original (chapter-one) value remains the latest -- never
        # silently overwritten by chapter two's conflicting proposal.
        latest = [i for i in job["document_state"]["items"] if i["label"] == "argument"]
        self.assertEqual(len(latest), 1)
        self.assertIn("טענה", latest[0]["value"])

    def test_07_each_translation_records_the_state_version_it_used(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        versions = {u["chapter_node_id"]: u["document_state_version"] for u in job["units"]}
        self.assertEqual(len(set(u["document_state_version"] for u in job["units"][:2])), 1)
        first_chapter_version = job["units"][0]["document_state_version"]
        last_chapter_version = job["units"][-1]["document_state_version"]
        self.assertLess(first_chapter_version, last_chapter_version)

    def test_08_updating_state_does_not_rewrite_earlier_chapters_recorded_version(self):
        _, job, _translator, _chapter_qa = self._run_two_chapter_job()
        # Chapter one's units were translated and persisted before chapter
        # one's own QA committed anything; their recorded version (0) must
        # stay 0 even after later commits bump the document's revision.
        self.assertEqual(job["units"][0]["document_state_version"], 0)
        self.assertGreater(job["document_state"]["revision"], 0)

    def test_09_the_next_chapter_receives_the_updated_state(self):
        _, job, translator, _chapter_qa = self._run_two_chapter_job()
        self.assertTrue(any("טענה" in p for p in translator.calls[2:]))

    def test_10_arbitrary_chapter_summary_category_is_not_accepted(self):
        chaptered = self.root / "chaptered.pdf"
        make_chaptered_pdf(chaptered)
        translator, reviewer = FakeTranslationAdapter(), FakeReviewAdapter()
        chapter_qa = _StatefulChapterQAAdapter([
            "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)\nSTATE_UPDATES:\n"
            "- [summary] chapter_one :: the chapter is about an argument :: likely :: "
            "opening argument\n",
        ])
        factory = self.make_adapter_factory(translator, reviewer, chapter_qa)
        jobs = DocumentJobs(self.root, adapter_factory=factory)
        started = jobs.start(
            chaptered, {"model": "configured", "model_config": MOCK_MODEL_CONFIG, "quality": "checked"},
            paid_confirm=True,
        )
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = jobs.get(started["job_id"])
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "completed")
        # An unallowlisted "summary" category fails closed (needs_human),
        # never silently stored as persistent memory.
        self.assertEqual(job["chapter_qa_results"][0]["status"], "needs_human")
        self.assertEqual(job["chapter_qa_results"][0]["state_proposed"], 0)
        self.assertEqual(job["document_state"]["items"], [])


if __name__ == "__main__":
    unittest.main()
