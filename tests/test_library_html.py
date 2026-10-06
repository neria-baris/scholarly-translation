"""LIBRARY-HTML-INSTALLER B1: HTML export, html render_download, the
/document-library route and the /document-download ``format`` field.
Offline only: auto (mock) model, no provider calls."""
import base64
import json
import re
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from scholarly_translation import export_common, web_ui
from scholarly_translation.document_draft import DocumentDraftError, DocumentJobs, render_download
from scholarly_translation.export_common import ExportError, ordered_render_units
from scholarly_translation.export_html import export_html
from scholarly_translation.export_pdf import export_pdf
from scholarly_translation.web_ui import make_handler

from test_document_draft import make_simple_pdf
from test_export_epub import make_epub
from test_export_pdf import _build_structure_from_lines

_RUNNING = ("queued", "reading", "translating", "reviewing", "rebuilding")


def _wait(jobs, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job["status"] not in _RUNNING:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def _body_blocks(page):
    body = page.split("<body>", 1)[1].split("</body>", 1)[0]
    return re.findall(r"<(h[1-5]|p|blockquote)( class=\"[^\"]*\")?>(.*?)</\1>", body, re.S)


class ExportHtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "source.pdf"
        self.structure = _build_structure_from_lines(self.path, [
            "1. Introduction", "This is the first paragraph of the text.",
            "1.1 Background", "A second paragraph follows here.",
        ])
        self.units = ordered_render_units(self.structure)

    def tearDown(self):
        self.temp.cleanup()

    def test_self_contained_rtl_escaped_document(self):
        hostile = '<script>alert("x")</script> & <a href="https://evil.example/">'
        translations = {u["unit_id"]: {"text": f"טקסט {i} {hostile}", "approved": False}
                        for i, u in enumerate(self.structure["units"])}
        page = export_html(self.structure, translations, title="<b>ספר</b>.pdf").decode("utf-8")
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="he" dir="rtl">', page)
        self.assertIn('<meta charset="utf-8">', page)
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("<a ", page)
        self.assertNotIn("<b>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&amp;", page)
        self.assertNotRegex(page, r"(src|href)\s*=\s*\"?(https?:)?//")
        self.assertNotIn("<link", page)
        self.assertIn("&lt;b&gt;ספר&lt;/b&gt;.pdf", page.split("<body>")[1].split("</h1>")[0])

    def test_unit_order_and_kinds_match_pdf_export(self):
        translations = {u["unit_id"]: {"text": f"תרגום {i}"} for i, u in enumerate(self.structure["units"])}
        page = export_html(self.structure, translations, title=None).decode("utf-8")
        blocks = _body_blocks(page)
        manifest = export_pdf(self.structure, translations).manifest
        rendered = [m for m in manifest if m["rendered"]]
        self.assertEqual(len(blocks), len(rendered))
        by_id = {u["unit_id"]: i for i, u in enumerate(self.structure["units"])}
        for (tag, _, text), entry in zip(blocks, rendered):
            self.assertEqual(text, f"תרגום {by_id[entry['unit_id']]}")
            heading = entry["kind"] in ("part", "chapter", "section", "subsection", "heading", "subheading")
            self.assertEqual(tag.startswith("h"), heading, entry["kind"])
        self.assertTrue(any(tag.startswith("h") for tag, _, _ in blocks))
        self.assertTrue(any(tag == "p" for tag, _, _ in blocks))

    def test_untranslated_units_fall_back_to_source_text(self):
        first, *rest = self.structure["units"]
        translations = {u["unit_id"]: {"text": "מתורגם"} for u in rest}
        page = export_html(self.structure, translations, title="t").decode("utf-8")
        texts = [text for _, _, text in _body_blocks(page)]
        source = next(u["source_text"] for u in self.units if u["unit_id"] == first["unit_id"])
        self.assertIn(source, texts)

    def test_malformed_translations_and_structure_raise_export_error(self):
        with self.assertRaises(ExportError):
            export_html(self.structure, {self.structure["units"][0]["unit_id"]: {"text": " "}}, title="t")
        with self.assertRaises(ExportError):
            export_html({"schema_version": 1}, {}, title="t")

    def test_font_embedding_and_validation(self):
        translations = {u["unit_id"]: {"text": "א"} for u in self.structure["units"]}
        plain = export_html(self.structure, translations, title="t").decode("utf-8")
        self.assertNotIn("@font-face", plain)
        self.assertIn("font-family:", plain)
        page = export_html(self.structure, translations, title="t", font_id="david-libre").decode("utf-8")
        self.assertEqual(page.count("@font-face"), 2)
        encoded = re.search(r"base64,([A-Za-z0-9+/=]+)", page).group(1)
        regular = export_common._BUNDLED_FONT_ROOT / export_common._PDF_FONTS["david-libre"][1]
        self.assertEqual(base64.b64decode(encoded), regular.read_bytes())
        self.assertNotRegex(page, r"url\((?!data:)")
        with self.assertRaises(ExportError):
            export_html(self.structure, translations, title="t", font_id="comic-sans")
        with tempfile.TemporaryDirectory() as empty, \
                patch.object(export_common, "_BUNDLED_FONT_ROOT", Path(empty)):
            with self.assertRaises(ExportError):
                export_html(self.structure, translations, title="t", font_id="david-libre")


class RenderDownloadHtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_html_for_completed_pdf_and_epub_jobs(self):
        jobs = DocumentJobs(self.root)
        pdf_path = self.root / "paper.pdf"
        make_simple_pdf(pdf_path)
        pdf_job = _wait(jobs, jobs.start(pdf_path, {"model": "auto", "quality": "fast"})["job_id"])
        self.assertEqual(pdf_job["status"], "completed")
        page = render_download(pdf_job, "html").decode("utf-8")
        self.assertIn('dir="rtl"', page)
        self.assertIn("paper.pdf", page)
        self.assertIn("@font-face", render_download(pdf_job, "html", font_id="frank-ruhl-libre").decode("utf-8"))
        with self.assertRaises(DocumentDraftError):
            render_download(pdf_job, "html", font_id="nope")
        with self.assertRaises(DocumentDraftError):
            render_download(pdf_job, "epub")
        with self.assertRaises(DocumentDraftError):
            render_download({**pdf_job, "status": "failed"}, "html")
        self.assertTrue(render_download(pdf_job, "pdf").startswith(b"%PDF"))

        epub_path = self.root / "book.epub"
        make_epub(epub_path)
        epub_job = _wait(jobs, jobs.start(epub_path, {"model": "auto", "quality": "fast"})["job_id"])
        self.assertEqual(epub_job["status"], "completed")
        page = render_download(epub_job, "html").decode("utf-8")
        self.assertIn('<html lang="he" dir="rtl">', page)
        self.assertNotIn("<script", page.lower())


class LibraryHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output_patch = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        self.output_patch.start()
        self._cross_review_stub = patch("scholarly_translation.chapter_pipeline.cross_review_available", create=True, return_value=False)
        self._cross_review_stub.start()
        self.addCleanup(self._cross_review_stub.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.output_patch.stop()
        self.temp.cleanup()

    def request(self, route, payload, token="test-token"):
        return Request(self.url + route, data=json.dumps(payload).encode("utf-8"),
                       headers={"Content-Type": "application/json", "X-UI-Token": token, "Origin": self.url},
                       method="POST")

    def post(self, route, payload, token="test-token"):
        with urlopen(self.request(route, payload, token), timeout=15) as response:
            return json.load(response)

    def _complete_job(self, name, make, settings=None):
        source = Path(self.temp.name) / "src" / name
        source.parent.mkdir(exist_ok=True)
        make(source)
        upload = Request(self.url + f"/upload?name={name}", data=source.read_bytes(),
                         headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
        with urlopen(upload) as response:
            uploaded = json.load(response)
        started = self.post("/document-translate", {"path": uploaded["path"], "settings": {
            "model": "auto", "quality": "fast", "language": "en", "budget_usd": 2, **(settings or {})}})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = self.post("/document-job", started)
            if job["status"] not in _RUNNING:
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "completed")
        return job

    def test_library_lists_completed_jobs_only_and_skips_corrupt(self):
        self.assertEqual(self.post("/document-library", {}), {"documents": []})
        pdf_job = self._complete_job("paper.pdf", make_simple_pdf, {"font_id": "david-libre"})
        time.sleep(0.05)
        epub_job = self._complete_job("book.epub", make_epub)
        documents_root = Path(self.temp.name) / "documents"
        (documents_root / ("a" * 32)).mkdir()
        (documents_root / ("a" * 32) / "job.json").write_text("{not json", encoding="utf-8")
        (documents_root / ("b" * 32)).mkdir()
        (documents_root / ("b" * 32) / "job.json").write_text(json.dumps({"job_id": "b" * 32}), encoding="utf-8")
        (documents_root / "not-a-job").mkdir()
        (documents_root / "not-a-job" / "job.json").write_text("{}", encoding="utf-8")
        running = json.loads((documents_root / pdf_job["job_id"] / "job.json").read_text(encoding="utf-8"))
        running.update(job_id="c" * 32, status="failed")
        (documents_root / ("c" * 32)).mkdir()
        (documents_root / ("c" * 32) / "job.json").write_text(json.dumps(running), encoding="utf-8")

        library = self.post("/document-library", {})
        self.assertEqual(set(library), {"documents"})
        documents = library["documents"]
        self.assertEqual([d["job_id"] for d in documents], [epub_job["job_id"], pdf_job["job_id"]])
        epub_entry, pdf_entry = documents
        self.assertEqual(pdf_entry, {
            "job_id": pdf_job["job_id"], "filename": "paper.pdf", "source_kind": "pdf",
            "completed_at": pdf_entry["completed_at"], "unit_count": len(pdf_job["units"]),
            "font_id": "david-libre", "formats": ["pdf", "html"]})
        self.assertIsInstance(pdf_entry["completed_at"], float)
        self.assertGreaterEqual(epub_entry["completed_at"], pdf_entry["completed_at"])
        self.assertEqual(epub_entry["source_kind"], "epub")
        self.assertEqual(epub_entry["formats"], ["epub", "html"])
        self.assertIsNone(epub_entry["font_id"])
        raw = json.dumps(library, ensure_ascii=False)
        self.assertNotIn(self.temp.name.replace("\\", "\\\\"), raw)
        self.assertNotIn(pdf_job["units"][0]["source_text"], raw)

        with self.assertRaises(HTTPError) as caught:
            self.post("/document-library", {}, token="bad")
        self.assertEqual(caught.exception.code, 403)

    def test_library_caps_at_200(self):
        jobs_root = Path(self.temp.name) / "documents"
        template = self._complete_job("paper.pdf", make_simple_pdf)
        data = json.loads((jobs_root / template["job_id"] / "job.json").read_text(encoding="utf-8"))
        for index in range(205):
            job_id = f"{index:032x}"
            (jobs_root / job_id).mkdir()
            (jobs_root / job_id / "job.json").write_text(json.dumps({**data, "job_id": job_id}), encoding="utf-8")
        documents = self.post("/document-library", {})["documents"]
        self.assertEqual(len(documents), 200)
        stamps = [d["completed_at"] for d in documents]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_download_format_html_pdf_and_rejections(self):
        job = self._complete_job("paper.pdf", make_simple_pdf)
        ref = {"job_id": job["job_id"]}
        with urlopen(self.request("/document-download", ref)) as response:
            self.assertEqual(response.headers["Content-Type"], "application/pdf")
            self.assertTrue(response.read().startswith(b"%PDF"))
        with urlopen(self.request("/document-download", {**ref, "format": "pdf", "font_id": "hadasim-clm"})) as response:
            self.assertTrue(response.read().startswith(b"%PDF"))
        with urlopen(self.request("/document-download", {**ref, "format": "html"})) as response:
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            disposition = unquote(response.headers["Content-Disposition"])
            self.assertIn("attachment", disposition)
            self.assertTrue(disposition.endswith("paper.he.html"))
            page = response.read().decode("utf-8")
        self.assertIn('<html lang="he" dir="rtl">', page)
        self.assertNotIn("@font-face", page)
        with urlopen(self.request("/document-download", {**ref, "format": "html", "font_id": "noto-serif-hebrew"})) as response:
            self.assertIn("@font-face", response.read().decode("utf-8"))
        for bad in ({"format": "docx"}, {"format": "epub"}, {"format": 3}, {"format": "html", "font_id": "nope"},
                    {"format": "html", "font_id": 7}):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.request("/document-download", {**ref, **bad}))
            self.assertEqual(caught.exception.code, 400, bad)
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.request("/document-download", {**ref, "format": "html"}, token="bad"))
        self.assertEqual(caught.exception.code, 403)

    def test_epub_job_html_download_accepts_font(self):
        job = self._complete_job("book.epub", make_epub)
        ref = {"job_id": job["job_id"]}
        with urlopen(self.request("/document-download", ref)) as response:
            self.assertEqual(response.headers["Content-Type"], "application/epub+zip")
            self.assertTrue(response.read().startswith(b"PK"))
        with urlopen(self.request("/document-download", {**ref, "format": "html", "font_id": "david-libre"})) as response:
            self.assertTrue(unquote(response.headers["Content-Disposition"]).endswith("book.he.html"))
            self.assertIn("@font-face", response.read().decode("utf-8"))
        for bad in ({"format": "pdf"}, {"format": "epub", "font_id": "david-libre"}):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.request("/document-download", {**ref, **bad}))
            self.assertEqual(caught.exception.code, 400, bad)


if __name__ == "__main__":
    unittest.main()
