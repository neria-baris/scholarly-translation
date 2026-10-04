import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from reportlab.pdfgen import canvas

from scholarly_translation.document_draft import (
    DocumentDraftError, DocumentJobs, extract_document, render_download, validate_settings,
)
from scholarly_translation.runtime_controls import ControlStore


def make_epub(path, texts=None, spine=None):
    texts = texts or ["Some scholars do not accept 3 claims."]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book/package.opf"/></rootfiles></container>')
        items = ''.join(f'<item id="c{i}" href="chapter{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(texts)))
        order = range(len(texts)) if spine is None else spine
        refs = ''.join(f'<itemref idref="c{i}"/>' for i in order)
        archive.writestr("book/package.opf", f'<package xmlns="http://www.idpf.org/2007/opf"><manifest>{items}</manifest><spine>{refs}</spine></package>')
        for i, text in enumerate(texts):
            archive.writestr(f"book/chapter{i}.xhtml", '<html><head><title>Not body</title></head><body><p>' + text + '</p><script>not source code</script></body></html>')


class FakeClient:
    def __init__(self, status="completed", usage=True, fail_on=None):
        self.responses = self
        self.calls, self.status, self.usage, self.fail_on = [], status, usage, fail_on

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == self.fail_on:
            raise RuntimeError("private-secret-must-not-be-logged")
        usage = SimpleNamespace(input_tokens=100, output_tokens=30) if self.usage else None
        return SimpleNamespace(status=self.status, model=kwargs["model"], output_text="החוקרים אינם מקבלים 3 טענות.", usage=usage)


class DocumentDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "book.epub"
        make_epub(self.path)

    def run_job(self, client=None, settings=None, path=None, manager=None):
        client = client or FakeClient()
        jobs = manager or DocumentJobs(self.root, client_factory=lambda: client)
        started = jobs.start(path or self.path, settings or {}, api_key="local-fixture-key", paid_confirm=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = jobs.get(started["job_id"])
            if result["status"] not in ("queued", "reading", "translating"):
                # The worker writes its final record before dropping active state.
                while jobs.active and time.monotonic() < deadline:
                    time.sleep(0.01)
                return jobs, jobs.get(started["job_id"])
            time.sleep(0.01)
        self.fail("document worker did not complete")

    def test_epub_spine_order_and_no_head_or_script_content(self):
        make_epub(self.path, ["chapter zero", "chapter one"], [1, 0])
        source = extract_document(self.path)
        self.assertEqual([c["source_text"] for c in source["chunks"]], ["chapter one", "chapter zero"])
        self.assertEqual(source["chunks"][0]["chapter_path"], "book/chapter1.xhtml")

    def test_pdf_reads_pages_in_order_and_keeps_chunk_spans(self):
        path = self.root / "paper.pdf"
        pdf = canvas.Canvas(str(path))
        for text in ("First page 1.", "Second page 2."):
            pdf.drawString(72, 700, text)
            pdf.showPage()
        pdf.save()
        source = extract_document(path, "en")
        self.assertEqual([c["page_number"] for c in source["chunks"]], [1, 2])
        self.assertEqual(source["chunks"][0]["source_start"], 0)
        self.assertIn("First page", source["chunks"][0]["source_text"])

    def test_chunks_preserve_all_source_characters(self):
        text = "some text &amp; more text " * 250
        make_epub(self.path, [text])
        chunks = extract_document(self.path)["chunks"]
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(c["source_text"] for c in chunks), text.replace("&amp;", "&").strip())
        self.assertEqual([c["source_start"] for c in chunks[1:]], [c["source_end"] for c in chunks[:-1]])

    def test_archive_outside_reference_and_encrypted_content_rejected(self):
        with zipfile.ZipFile(self.path, "a") as archive:
            archive.writestr("META-INF/encryption.xml", '<encryption xmlns="urn:test"><CipherReference URI="book/chapter0.xhtml"/></encryption>')
        with self.assertRaisesRegex(DocumentDraftError, "DRM"):
            extract_document(self.path)
        with self.assertRaises(DocumentDraftError):
            from scholarly_translation.document_draft import _archive_path
            _archive_path("book", "../../secret.xhtml")

    def test_bad_files_settings_and_oversized_source_fail_without_dispatch(self):
        for bad in ({"model": "invented-model"}, {"quality": "magic"}, {"budget_usd": float("nan")}, {"budget_usd": True}):
            with self.assertRaises(DocumentDraftError):
                validate_settings(bad)
        make_epub(self.path, ["x" * 150001])
        client = FakeClient()
        _, job = self.run_job(client)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(client.calls, [])

    def test_model_and_quality_are_real_request_parameters(self):
        client = FakeClient()
        _, job = self.run_job(client, {"model": "gpt-6.1-sol", "quality": "careful", "budget_usd": 2})
        self.assertEqual(job["status"], "completed")
        self.assertEqual(client.calls[0]["model"], "gpt-6.1-sol")
        self.assertEqual(client.calls[0]["reasoning"], {"effort": "high"})
        self.assertEqual(client.calls[0]["max_output_tokens"], 16384)
        self.assertFalse(client.calls[0]["store"])
        self.assertEqual(client.calls[0]["tools"], [])
        self.assertFalse(job["approved"])
        self.assertFalse(job["source_reviewed"])
        self.assertNotIn("local-fixture-key", json.dumps(job))
        self.assertGreater(job["estimated_cost_usd"], 0)

    def test_download_available_without_review_and_html_escapes_text(self):
        _, job = self.run_job()
        self.assertEqual(job["revision"], 0)
        self.assertIn("החוקרים", render_download(job, "txt").decode("utf-8"))
        job["chunks"][0]["target_text"] = "<script>alert(1)</script>"
        download = render_download(job, "html").decode("utf-8")
        self.assertNotIn("<script>", download)
        self.assertIn("&lt;script&gt;", download)
        self.assertIn("ללא אישור מחקרי", download)

    def test_optional_review_versions_edits_without_approval_and_refuses_stale(self):
        jobs, job = self.run_job()
        edited = jobs.review(job["job_id"], 0, "טיוטה שנערכה ובה 3 טענות.", 0)
        self.assertEqual(edited["revision"], 1)
        self.assertFalse(edited["approved"])
        self.assertTrue((jobs.root / job["job_id"] / "revision-0.json").is_file())
        with self.assertRaises(DocumentDraftError):
            jobs.review(job["job_id"], 0, "עריכה ישנה", 0)

    def test_exact_repeat_cache_has_no_dispatch_or_current_cost(self):
        client = FakeClient()
        jobs, first = self.run_job(client)
        _, second = self.run_job(client, manager=jobs)
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(first["chunks"][0]["cache_hit"])
        self.assertTrue(second["chunks"][0]["cache_hit"])
        self.assertEqual(second["estimated_cost_usd"], 0)
        _, third = self.run_job(client, {"quality": "fast"}, manager=jobs)
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(third["chunks"][0]["cache_hit"])

    def test_cap_preflight_stops_before_paid_dispatch(self):
        client = FakeClient()
        _, job = self.run_job(client, {"model": "gpt-6.1-sol", "budget_usd": 0.01})
        self.assertEqual(job["status"], "failed")
        self.assertEqual(client.calls, [])

    def test_unknown_usage_incomplete_and_transport_keep_hold_without_retry(self):
        for client in (FakeClient(usage=False), FakeClient(status="incomplete"), FakeClient(fail_on=1)):
            with self.subTest(kind=(client.status, client.usage, client.fail_on)), tempfile.TemporaryDirectory() as temp:
                manager = DocumentJobs(Path(temp), client_factory=lambda: client)
                jobs, job = self.run_job(client, manager=manager)
                self.assertEqual(job["status"], "failed")
                self.assertEqual(job["completed_chunks"], 0)
                self.assertEqual(len(client.calls), 1)
                self.assertNotIn("private-secret", json.dumps(job))
                with ControlStore(jobs.root / "controls.sqlite3", create=False) as store:
                    status = store.status("document-" + job["job_id"])
                    self.assertTrue(status["stopped"])
                    self.assertGreater(status["held_usd"], 0)

    def test_partial_failure_keeps_untranslated_locations_and_download_label(self):
        make_epub(self.path, ["first chapter 3", "second chapter 3"])
        _, job = self.run_job(FakeClient(fail_on=2))
        self.assertEqual(job["completed_chunks"], 1)
        self.assertEqual(job["total_chunks"], 2)
        self.assertEqual(job["chunks"][1]["target_text"], "")
        output = render_download(job, "txt").decode("utf-8")
        self.assertIn("חלקית", output)
        self.assertIn("טרם תורגם", output)

    def test_finished_job_recovers_after_restart_but_inflight_not_retried(self):
        jobs, job = self.run_job()
        recovered = DocumentJobs(self.root).get(job["job_id"])
        self.assertEqual(recovered["status"], "completed")
        folder = jobs.root / job["job_id"]
        job["status"] = "translating"
        (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")
        self.assertEqual(DocumentJobs(self.root).get(job["job_id"])["status"], "interrupted")

    def test_paid_job_requires_explicit_consent(self):
        jobs = DocumentJobs(self.root, client_factory=FakeClient)
        with self.assertRaises(DocumentDraftError):
            jobs.start(self.path, {}, paid_confirm=False)


if __name__ == "__main__":
    unittest.main()
