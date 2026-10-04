import json
import hashlib
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation.gui import STEPS, build_command
from scholarly_translation import web_ui
from scholarly_translation.web_ui import make_handler


class BrowserShellTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, route, payload, token="test-token"):
        request = Request(
            self.url + route,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-UI-Token": token,
                     "Origin": self.url},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def test_mock_demo_runs_through_browser_endpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            output = str(Path(temp) / "demo")
            response = self.post("/run", {"command": "demo", "values": {}, "output": output})
            self.assertEqual(response["code"], 0)
            self.assertTrue((Path(output) / "document.json").is_file())
            self.assertIn("Wrote document", response["stdout"])
            with patch.object(web_ui.webbrowser, "open") as browser_open:
                opened = self.post("/open", {"path": str(Path(output) / "document.json")})
                self.assertTrue(opened["opened"])
                browser_open.assert_called_once()

    def test_paid_request_needs_explicit_confirmation(self):
        with self.assertRaises(HTTPError) as caught:
            self.post("/run", {"command": "probe-provider", "values": {"provider": "openai"},
                               "output": "outputs/ui/test-paid"})
        self.assertEqual(caught.exception.code, 400)

    def test_token_and_required_fields(self):
        with self.assertRaises(HTTPError) as caught:
            self.post("/run", {"command": "demo", "values": {}, "output": "outputs/ui/demo"}, token="bad")
        self.assertEqual(caught.exception.code, 403)
        extract = next(step for step in STEPS if step.command == "extract-pdf")
        with self.assertRaises(ValueError):
            build_command(extract, {"language": "en"}, "outputs/ui/extract")

    def test_session_key_is_never_echoed(self):
        with patch.dict(web_ui.os.environ, {"OPENAI_API_KEY": ""}):
            result = self.post("/settings", {"api_key": "local-test-secret"})
            self.assertTrue(result["api_key_available"])
            self.assertNotIn("local-test-secret", json.dumps(result))
            self.assertFalse(self.post("/settings", {"api_key": ""})["api_key_available"])

    def test_preview_pairs_only_matching_source_and_draft(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(web_ui, "ROOT", Path(temp)):
            folder = Path(temp) / "outputs" / "ui"
            folder.mkdir(parents=True)
            source = "A source sentence."
            structure = {"stage": "structure@1", "document_id": "doc-1", "source_uri": "file:///example.pdf",
                         "language": "en", "units": [{"unit_id": "unit-1", "text": source}]}
            draft = {"document_id": "doc-1", "unit_id": "unit-1",
                     "source_text_hash": hashlib.sha256(source.encode()).hexdigest(),
                     "draft_text": "משפט מקור", "status": "draft_unapproved"}
            (folder / "structure.json").write_text(json.dumps(structure), encoding="utf-8")
            (folder / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
            paths = {"structure_json": str(folder / "structure.json"), "draft": str(folder / "draft.json")}
            preview = web_ui.preview_artifacts(paths)
            self.assertEqual(preview["translation_text"], "משפט מקור")
            draft["source_text_hash"] = "stale"
            (folder / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
            self.assertEqual(web_ui.preview_artifacts(paths)["translation_text"], "")


class DocumentFlowHTTPTests(unittest.TestCase):
    post = BrowserShellTests.post
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output_patch = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        self.output_patch.start()
        BrowserShellTests.setUp(self)

    def tearDown(self):
        BrowserShellTests.tearDown(self)
        self.output_patch.stop()
        self.temp.cleanup()

    def test_document_lifecycle_download_and_optional_review(self):
        sample = self.post("/document-sample", {})
        request = Request(self.url + "/upload?name=uploaded.epub",
                          data=Path(sample["path"]).read_bytes(),
                          headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
        with urlopen(request) as response:
            uploaded = json.load(response)
        started = self.post("/document-translate", {"path": uploaded["path"],
                            "settings": {"model": "demo", "quality": "balanced", "language": "auto", "budget_usd": 2}})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.post("/document-job", started)
            if job["status"] not in ("queued", "reading", "translating"):
                break
            time.sleep(.02)
        self.assertEqual(job["status"], "demo")
        self.assertFalse(job["approved"])
        self.assertFalse(job["source_reviewed"])
        self.assertEqual(self.post("/document-recent", {})["job"]["job_id"], job["job_id"])
        for kind in ("html", "txt"):
            request = Request(self.url + "/document-download", data=json.dumps({**started, "format": kind}).encode(),
                              headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
            with urlopen(request) as response:
                self.assertIn("attachment", response.headers["Content-Disposition"])
                self.assertIn("Some scholars", response.read().decode("utf-8"))
        edit = {**started, "chunk_index": 0, "target_text": "An edited draft <script>bad()</script>", "expected_revision": 0}
        revised = self.post("/document-review", edit)
        self.assertEqual(revised["revision"], 1)
        self.assertFalse(revised["approved"])
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-review", edit)
        self.assertEqual(caught.exception.code, 400)

    def test_document_guards_and_live_consent(self):
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-config", {}, token="bad")
        self.assertEqual(caught.exception.code, 403)
        for path in (str(Path(__file__).resolve()), "../outside.epub"):
            with self.assertRaises(HTTPError) as caught:
                self.post("/document-translate", {"path": path, "settings": {"model": "demo"}})
            self.assertEqual(caught.exception.code, 400)
        sample = self.post("/document-sample", {})
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-translate", {"path": sample["path"], "settings": {
                      "model": "gpt-6-luna", "quality": "balanced", "language": "auto", "budget_usd": 2}})
        self.assertEqual(caught.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
