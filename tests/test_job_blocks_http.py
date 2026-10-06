"""BLOCK-DECISIONS over HTTP: in-progress listing, partial download and decide.
Offline only: the job is produced by the auto (mock) model, the failed call by a fake adapter."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.model_adapter import CacheablePrompt, TextGenerationResult
from scholarly_translation.runtime_controls import ControlStore
from scholarly_translation.work_journal import WorkJournal

from test_export_epub import make_epub
import test_library_html as _library_http
from test_pipeline_recovery_contract import configuration


class InProgressHttpTests(unittest.TestCase):
    # Borrow the HTTP fixture without re-running the library tests themselves.
    setUp, tearDown = _library_http.LibraryHttpTests.setUp, _library_http.LibraryHttpTests.tearDown
    request, post, _complete_job = _library_http.LibraryHttpTests.request, _library_http.LibraryHttpTests.post, _library_http.LibraryHttpTests._complete_job

    def stuck_job(self):
        job = self._complete_job("book.epub", make_epub)
        folder = Path(self.temp.name) / "documents" / job["job_id"]
        data = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        self.assertGreater(len(data["units"]), 1)
        self.dropped = data["units"][-1]
        data.update(status="failed", error="התרגום האוטומטי נעצר: provider response failed",
                    units=data["units"][:-1], progress={"completed_chapters": 1, "total_chapters": 2})
        data["settings"]["automation"] = True
        (folder / "job.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        def factory(role, descriptor):
            return SimpleNamespace(generate=lambda text, model: TextGenerationResult(
                "failed_truncated", "{", {"input": 100, "output": 1000}, model, 0))
        with ControlStore(folder / "controls.sqlite3") as store, WorkJournal(folder / "journal.sqlite3") as journal:
            with self.assertRaises(pipeline.ChapterPipelineError):
                pipeline._controlled(job["job_id"], "translator", "chapter-translate", CacheablePrompt("s\n", "p"),
                    configuration(), 1000, store, journal, 1.0, 20, 4096, json.loads, {"x": 1}, factory)
        return job["job_id"]

    def download(self, payload):
        with urlopen(self.request("/document-download", payload), timeout=15) as response:
            return response.read(), response.headers["Content-Disposition"]

    def test_in_progress_listing_partial_download_and_decision(self):
        job_id = self.stuck_job()
        self.assertEqual(self.post("/document-library", {})["documents"], [])
        [entry] = self.post("/document-in-progress", {})["documents"]
        self.assertEqual(entry["job_id"], job_id)
        self.assertEqual(entry["blocker"]["kind"], "failed_call")
        self.assertEqual((entry["translated_units"], entry["formats"]), (entry["total_units"] - 1, ["epub", "html"]))
        self.assertIsNone(entry["error"])
        self.assertNotIn("source_text", json.dumps(entry))

        with self.assertRaises(HTTPError) as caught:
            self.download({"job_id": job_id, "format": "html"})
        self.assertEqual(caught.exception.code, 400)
        page, disposition = self.download({"job_id": job_id, "format": "html", "partial": True})
        self.assertIn(".he.partial.html", disposition)
        self.assertIn(self.dropped["source_text"].split()[0], page.decode("utf-8"))
        epub, _ = self.download({"job_id": job_id, "format": "epub", "partial": True})
        self.assertTrue(epub.startswith(b"PK"))

        job = self.post("/document-job", {"job_id": job_id})
        self.assertEqual(job["blocker"]["options"][0]["id"], "accept_and_retry")
        with self.assertRaises(HTTPError):
            self.post("/document-decide", {"job_id": job_id, "option": "raise_budget", "value": 5})
        decided = self.post("/document-decide", {"job_id": job_id, "option": "accept_and_retry"})
        self.assertIsNone(decided["blocker"])
        self.assertFalse(decided["budget_status"]["stopped"])
        self.assertEqual(decided["decisions"][0]["option"], "accept_and_retry")
        with self.assertRaises(HTTPError):
            self.post("/document-decide", {"job_id": job_id, "option": "accept_and_retry", "value": True})


if __name__ == "__main__":
    unittest.main()
