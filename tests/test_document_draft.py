import json
import tempfile
import time
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.document_draft import (
    DocumentDraftError, DocumentJobs, EPUB_BLOCKED_MESSAGE, extract_structure, render_download, validate_settings,
)
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.translation_profiles import style_profile_text

import pdf_fixture


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
            status="completed", text="VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)",
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

    # --- EPUB blocker ----------------------------------------------------------

    def test_epub_upload_is_refused_with_clear_blocker_message(self):
        epub_path = self.root / "book.epub"
        epub_path.write_bytes(b"not a real epub, refused before parsing anyway")
        with self.assertRaisesRegex(DocumentDraftError, "EPUB"):
            extract_structure(epub_path)
        try:
            extract_structure(epub_path)
        except DocumentDraftError as exc:
            self.assertEqual(str(exc), EPUB_BLOCKED_MESSAGE)

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
        self.assertTrue((jobs.root / job["job_id"] / "revision-0.json").is_file())
        with self.assertRaises(DocumentDraftError):
            jobs.review(job["job_id"], 0, "עריכה ישנה", 0)
        body = render_download(edited, "pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_paid_job_requires_explicit_consent(self):
        jobs = DocumentJobs(self.root, adapter_factory=self.make_adapter_factory(FakeTranslationAdapter()))
        with self.assertRaises(DocumentDraftError):
            jobs.start(self.path, {"model": "configured", "model_config": MOCK_MODEL_CONFIG}, paid_confirm=False)

    def test_one_active_job_at_a_time(self):
        jobs = DocumentJobs(self.root)
        jobs.start(self.path, {"model": "auto"}, paid_confirm=False)
        with self.assertRaises(DocumentDraftError):
            jobs.start(self.path, {"model": "auto"}, paid_confirm=False)
        deadline = time.monotonic() + 10
        while jobs.active and time.monotonic() < deadline:
            time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
