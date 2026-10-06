"""Cross-chapter review action for an existing book: backend, HTTP, UI and help text.
Offline: chapter_pipeline.enable_cross_review / cross_review_available are patched
(the conductor provides them); nothing is sent to a provider."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from scholarly_translation import chapter_pipeline
from scholarly_translation.document_draft import DocumentDraftError, DocumentJobs

from test_export_epub import make_epub
import test_library_html as _library_http

ROOT = Path(__file__).resolve().parents[1] / "scholarly_translation"


class CrossReviewActionTests(unittest.TestCase):
    def setUp(self):
        _library_http.LibraryHttpTests.setUp(self)
        # The conductor adds the real function; every /document-job call needs it meanwhile.
        patcher = patch.object(chapter_pipeline, "cross_review_available", create=True, return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    tearDown = _library_http.LibraryHttpTests.tearDown
    request, post, _complete_job = _library_http.LibraryHttpTests.request, _library_http.LibraryHttpTests.post, _library_http.LibraryHttpTests._complete_job

    def folder(self, job_id):
        return Path(self.temp.name) / "documents" / job_id

    def notebook_job(self):
        job = self._complete_job("book.epub", make_epub)
        path = self.folder(job["job_id"]) / "job.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["settings"]["automation"] = True
        data["book_notebook"] = {"entries": [{"id": "e1"}]}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        (self.folder(job["job_id"]) / "journal.sqlite3").touch()
        return job["job_id"], DocumentJobs(Path(self.temp.name))

    def edit(self, job_id, fn):
        path = self.folder(job_id) / "job.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_success_pauses_persists_and_sends_nothing(self):
        job_id, jobs = self.notebook_job()
        with patch.object(chapter_pipeline, "enable_cross_review", create=True,
                          return_value={"windows": 3}) as enable:
            job = jobs.cross_chapter_review(job_id)
        enable.assert_called_once()
        self.assertEqual((job["status"], job["stage_label"]), ("paused", "ממתין לבדיקה רוחבית"))
        self.assertEqual(job["cross_review_report"], {"windows": 3})
        self.assertIn("blocker", job)
        saved = json.loads((self.folder(job_id) / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "paused")
        self.assertNotIn("budget_status", saved)
        self.assertIsNone(jobs.active)

    def test_refusals_never_reach_the_pipeline(self):
        job_id, jobs = self.notebook_job()
        with patch.object(chapter_pipeline, "enable_cross_review", create=True,
                          return_value={"windows": 1}) as enable:
            jobs.active = "other"
            with self.assertRaises(DocumentDraftError):
                jobs.cross_chapter_review(job_id)
            jobs.active = None
            self.edit(job_id, lambda d: d.update(book_notebook=None))
            with self.assertRaises(DocumentDraftError):
                jobs.cross_chapter_review(job_id)
            self.edit(job_id, lambda d: d.update(book_notebook={"entries": [1]}))
            self.edit(job_id, lambda d: d["settings"].update(automation=False))
            with self.assertRaises(DocumentDraftError):
                jobs.cross_chapter_review(job_id)
            self.edit(job_id, lambda d: d["settings"].update(automation=True))
            (self.folder(job_id) / "journal.sqlite3").unlink()
            with self.assertRaises(DocumentDraftError):
                jobs.cross_chapter_review(job_id)
            enable.assert_not_called()

    def test_pipeline_error_becomes_draft_error_and_job_unchanged(self):
        job_id, jobs = self.notebook_job()
        with patch.object(chapter_pipeline, "enable_cross_review", create=True,
                          side_effect=chapter_pipeline.ChapterPipelineError("אין פרקים")):
            with self.assertRaises(DocumentDraftError):
                jobs.cross_chapter_review(job_id)
        self.assertEqual(jobs.get(job_id)["status"], "completed")

    def test_http_route_and_job_flag(self):
        job_id, _ = self.notebook_job()
        with patch.object(chapter_pipeline, "cross_review_available", create=True, return_value=True):
            self.assertIs(self.post("/document-job", {"job_id": job_id})["cross_review_available"], True)
        with patch.object(chapter_pipeline, "cross_review_available", create=True, return_value=False):
            self.assertIs(self.post("/document-job", {"job_id": job_id})["cross_review_available"], False)
        with patch.object(chapter_pipeline, "enable_cross_review", create=True, return_value={"windows": 2}):
            job = self.post("/document-cross-review", {"job_id": job_id})
        self.assertEqual((job["status"], job["cross_review_report"]), ("paused", {"windows": 2}))
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-cross-review", {"job_id": "x" * 32})
        self.assertEqual(caught.exception.code, 400)

    def test_ui_static_presence(self):
        html = (ROOT / "ui.html").read_text(encoding="utf-8")
        js = (ROOT / "ui.js").read_text(encoding="utf-8")
        for needle in ('id="cross-review-box"', 'id="cross-review-button"', 'id="cross-review-error"',
                       'id="cross-review-done"', "להכין בדיקה רוחבית", "הבדיקה הוכנה. לחצו ״המשך״ כדי להריץ אותה.",
                       "8 פרקים", "רק כשתלחצו ״המשך״"):
            self.assertIn(needle, html)
        for needle in ("/document-cross-review", "cross_review_available", "renderCrossReview", "prepareCrossReview",
                       "$('cross-review-button').onclick=prepareCrossReview"):
            self.assertIn(needle, js)
        # A completed book shows the result view: the entry point lives in its notebook section.
        self.assertIn('id="result-cross-review-button"', html)
        self.assertIn("$('result-cross-review-button').onclick=prepareCrossReviewFromResult", js)
        self.assertIn("show('processing-panel')", js[js.index('async function prepareCrossReviewFromResult'):])

    def test_help_documents_names_and_cross_review(self):
        with urlopen(self.url + "/help", timeout=10) as response:
            page = response.read().decode("utf-8")
        section = page.split('id="notebook"')[1].split('id="scanned"')[0]
        for text in ("טבלת שמות", "ננעלת אוטומטית", "ניקוד", "בדיקה רוחבית", "חלונות של 8 פרקים",
                     "להכין בדיקה רוחבית"):
            self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
