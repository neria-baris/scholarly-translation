"""CLOUD-LIBRARY C3: account routes, background Drive sync and the account UI.

Offline: a fake account and a fake Drive replace Google; the handler runs on
127.0.0.1:0 in a thread, as in the other HTTP tests.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import app_paths
from scholarly_translation.account.drive_library import (
    DriveNetworkError, DriveQuotaError, RemoteBook, SyncConflict,
)
from scholarly_translation.account.google_auth import Account, PendingSignIn, SignedOut, SignInError
from scholarly_translation.ui import web_ui
from scholarly_translation.ui.web_ui import make_handler

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "scholarly_translation" / "ui"
TOKEN = "test-token"
SECRET_MARKERS = ("tok-secret", "client-secret", "refresh")


class FakeAccount:
    def __init__(self, signed_in=False, email="reader@example.com", name="Reader One"):
        self.who = Account("sub-1", email, name) if signed_in else None
        self.next_email = email
        self.redirect_uri = None
        self.signed_out_calls = 0

    @property
    def signed_in(self):
        return self.who is not None

    @property
    def account(self):
        return self.who

    def restore(self):
        return self.who

    def begin_sign_in(self, redirect_uri):
        self.redirect_uri = redirect_uri
        return "https://accounts.example/auth?state=state-1", PendingSignIn("state-1", "verifier", redirect_uri)

    def complete_sign_in(self, pending, query):
        if query.get("state") != pending.state:
            raise SignInError("state_mismatch", "missing or mismatched state")
        self.who = Account("sub-1", self.next_email, "Reader One")
        return self.who

    def sign_out(self):
        self.signed_out_calls += 1
        self.who = None

    def access_token(self):
        return "tok-secret"

    def invalidate_access_token(self):
        pass


class FakeDrive:
    def __init__(self):
        self.sync_calls = 0
        self.sync_error = None
        self.download_error = None
        self.downloaded = []
        self.books = [RemoteBook("job-1", "Book One.pdf", 1700000000.0, ("job.json", "source.pdf"))]

    def sync_pending(self):
        self.sync_calls += 1
        if self.sync_error:
            raise self.sync_error
        return {"uploaded": ["a"], "skipped": ["b", "c"], "failed": []}

    def list_remote(self):
        return list(self.books)

    def download(self, job_id):
        if self.download_error:
            raise self.download_error
        self.downloaded.append(job_id)
        return Path(job_id)


class AccountServerCase(unittest.TestCase):
    signed_in = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.account = FakeAccount(signed_in=self.signed_in)
        self.drive = FakeDrive()
        self.start_server(lambda: self.account)

    def start_server(self, account_factory):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(
            TOKEN, account_factory=account_factory, drive_factory=lambda account, root: self.drive))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, route, payload=None, token=TOKEN, origin="same"):
        headers = {"Content-Type": "application/json", "X-UI-Token": token}
        headers["Origin"] = self.url if origin == "same" else origin
        request = Request(self.url + route, data=json.dumps(payload or {}).encode("utf-8"),
                          headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def get(self, path):
        try:
            with urlopen(self.url + path, timeout=15) as response:
                return response.status, response.read().decode("utf-8")
        except HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def wait_sync(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sync = self.post("/account")[1]["sync"]
            if predicate(sync):
                return sync
            time.sleep(0.02)
        self.fail("sync state never reached the expected value: %r" % (sync,))


class UnavailableTests(AccountServerCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drive = FakeDrive()
        self.start_server(lambda: None)

    def test_account_unavailable_when_factory_returns_none(self):
        self.assertEqual(self.post("/account"), (200, {"available": False}))
        for route in ("/account/sign-in", "/account/sync", "/account/remote-library", "/account/restore"):
            status, body = self.post(route, {"job_id": "job-1"})
            self.assertEqual(status, 404, route)
            self.assertIn("error", body)


class SignedOutTests(AccountServerCase):
    def test_account_reports_signed_out(self):
        status, body = self.post("/account")
        self.assertEqual(status, 200)
        self.assertTrue(body["available"])
        self.assertFalse(body["signed_in"])
        self.assertEqual(body["sync"]["state"], "signed_out")

    def test_sign_in_returns_url_and_opens_browser(self):
        with patch.object(web_ui.webbrowser, "open") as opened:
            status, body = self.post("/account/sign-in")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"url": "https://accounts.example/auth?state=state-1"})
        self.assertEqual(self.account.redirect_uri, f"{self.url}/oauth/callback")
        opened.assert_called_once_with(body["url"])

    def test_callback_with_wrong_state_shows_error_and_stays_signed_out(self):
        with patch.object(web_ui.webbrowser, "open"):
            self.post("/account/sign-in")
        status, page = self.get("/oauth/callback?state=attacker-state&code=abc")
        self.assertEqual(status, 200)
        self.assertNotIn("attacker-state", page)
        self.assertIn("state_mismatch", page)
        self.assertFalse(self.post("/account")[1]["signed_in"])
        # A stray request must not cancel the real attempt.
        status, page = self.get("/oauth/callback?state=state-1&code=abc")
        self.assertTrue(self.post("/account")[1]["signed_in"])

    def test_callback_without_pending_sign_in_is_an_error_page(self):
        status, page = self.get("/oauth/callback?state=state-1&code=abc")
        self.assertEqual(status, 200)
        self.assertIn("<html", page)
        self.assertFalse(self.post("/account")[1]["signed_in"])

    def test_callback_success_signs_in_escapes_values_and_starts_sync(self):
        self.account.next_email = "<b>x</b>@example.com"
        with patch.object(web_ui.webbrowser, "open"):
            self.post("/account/sign-in")
        status, page = self.get("/oauth/callback?state=state-1&code=zq9code")
        self.assertEqual(status, 200)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;@example.com", page)
        self.assertNotIn("<b>x</b>", page)
        self.assertNotIn("zq9code", page)
        body = self.post("/account")[1]
        self.assertTrue(body["signed_in"])
        self.assertEqual(body["email"], "<b>x</b>@example.com")
        self.wait_sync(lambda s: s["last_sync_at"] is not None)
        self.assertEqual(self.drive.sync_calls, 1)

    def test_pending_sign_in_expires(self):
        with patch.object(web_ui.webbrowser, "open"):
            self.post("/account/sign-in")
        with patch.object(web_ui, "PENDING_SIGN_IN_SECONDS", -1):
            self.get("/oauth/callback?state=state-1&code=abc")
        self.assertFalse(self.post("/account")[1]["signed_in"])

    def test_sync_remote_and_restore_need_sign_in(self):
        for route in ("/account/sync", "/account/remote-library", "/account/restore"):
            status, body = self.post(route, {"job_id": "job-1"})
            self.assertEqual(status, 401, route)
            self.assertEqual(body["code"], "signed_out")
        self.assertEqual(self.drive.sync_calls, 0)


class SignedInTests(AccountServerCase):
    signed_in = True

    def test_account_reports_identity_without_secrets(self):
        status, body = self.post("/account")
        self.assertEqual((status, body["signed_in"], body["email"], body["name"]),
                         (200, True, "reader@example.com", "Reader One"))
        self.assertEqual(body["sync"]["state"], "idle")
        text = json.dumps(body)
        for marker in SECRET_MARKERS:
            self.assertNotIn(marker, text)

    def test_sign_out(self):
        status, body = self.post("/account/sign-out")
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(self.account.signed_out_calls, 1)
        after = self.post("/account")[1]
        self.assertFalse(after["signed_in"])
        self.assertEqual(after["sync"]["state"], "signed_out")

    def test_new_post_routes_enforce_token_and_origin(self):
        routes = ("/account", "/account/sign-in", "/account/sign-out", "/account/sync",
                  "/account/remote-library", "/account/restore", "/update-status", "/update-settings")
        for route in routes:
            self.assertEqual(self.post(route, {}, token="bad")[0], 403, route)
            self.assertEqual(self.post(route, {}, origin="http://evil.example")[0], 403, route)
        self.assertTrue(self.account.signed_in)
        self.assertEqual(self.drive.sync_calls, 0)
        self.assertEqual(self.account.signed_out_calls, 0)

    def test_sync_now_runs_fake_sync_once_and_reports_summary(self):
        status, body = self.post("/account/sync")
        self.assertEqual(status, 200)
        self.assertTrue(body["started"])
        sync = self.wait_sync(lambda s: s["last_sync_at"] is not None and s["state"] != "running")
        self.assertEqual(sync["state"], "idle")
        self.assertEqual(sync["last_summary"], {"uploaded": 1, "skipped": 2, "failed": 0})
        self.assertIsNone(sync["last_error"])
        self.assertEqual(self.drive.sync_calls, 1)

    def test_signed_out_during_sync_sets_signed_out_state(self):
        self.drive.sync_error = SignedOut("revoked")
        self.post("/account/sync")
        sync = self.wait_sync(lambda s: s["state"] == "signed_out")
        self.assertEqual(sync["last_error"], "signed_out")
        self.assertTrue(self.post("/account")[1]["signed_in"])  # only the sync state changes

    def test_sync_failures_are_reported_as_safe_codes(self):
        for error, code in ((DriveQuotaError("secret detail 1"), "quota"),
                            (DriveNetworkError("secret detail 2"), "network"),
                            (RuntimeError("secret detail 3"), "unknown")):
            self.drive.sync_error = error
            self.post("/account/sync")
            sync = self.wait_sync(lambda s: s["state"] == "error" and s["last_error"] == code)
            self.assertNotIn("secret detail", json.dumps(sync))

    def test_remote_library_lists_books(self):
        status, body = self.post("/account/remote-library")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["books"]), 1)
        book = body["books"][0]
        self.assertEqual((book["job_id"], book["filename"], book["completed_at"]),
                         ("job-1", "Book One.pdf", 1700000000.0))
        self.assertIn("job.json", book["files"])

    def test_remote_library_error_is_safe(self):
        with patch.object(self.drive, "list_remote", side_effect=DriveQuotaError("private detail")):
            status, body = self.post("/account/remote-library")
        self.assertEqual((status, body["code"]), (507, "quota"))
        self.assertNotIn("private detail", json.dumps(body))

    def test_restore_success(self):
        status, body = self.post("/account/restore", {"job_id": "job-1"})
        self.assertEqual((status, body), (200, {"ok": True, "job_id": "job-1"}))
        self.assertEqual(self.drive.downloaded, ["job-1"])

    def test_restore_conflict_is_409(self):
        self.drive.download_error = SyncConflict("exists")
        status, body = self.post("/account/restore", {"job_id": "job-1"})
        self.assertEqual((status, body["code"]), (409, "conflict"))

    def test_restore_rejects_unsafe_ids(self):
        for job_id in ("../escape", "a/b", "", None, 7, "x" * 65):
            status, body = self.post("/account/restore", {"job_id": job_id})
            self.assertEqual(status, 400, repr(job_id))
            self.assertEqual(body["code"], "bad_id")
        self.assertEqual(self.drive.downloaded, [])

    def test_completed_job_triggers_background_sync(self):
        with patch("scholarly_translation.translate.chapter_pipeline.cross_review_available",
                   create=True, return_value=False):
            sample = self.post("/document-sample")[1]
            request = Request(self.url + "/upload?name=uploaded.pdf", data=Path(sample["path"]).read_bytes(),
                              headers={"X-UI-Token": TOKEN, "Origin": self.url}, method="POST")
            with urlopen(request) as response:
                uploaded = json.load(response)
            status, started = self.post("/document-translate", {"path": uploaded["path"], "settings": {
                "model": "auto", "quality": "fast", "language": "en", "budget_usd": 2}})
            self.assertEqual(status, 200)
            deadline = time.monotonic() + 15
            job = {}
            while time.monotonic() < deadline:
                job = self.post("/document-job", started)[1]
                if job.get("status") == "completed":
                    break
                time.sleep(0.05)
            self.assertEqual(job.get("status"), "completed")
        self.wait_sync(lambda s: s["last_sync_at"] is not None)
        self.assertGreaterEqual(self.drive.sync_calls, 1)


class OutputRootTests(unittest.TestCase):
    def test_output_root_derives_from_data_root(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, SCHOLARLY_DATA_ROOT=temp)
            result = subprocess.run(
                [sys.executable, "-I", "-c",
                 "import sys; sys.path.insert(0, sys.argv[1]);"
                 "from scholarly_translation.ui import web_ui; print(web_ui.OUTPUT_ROOT)", str(ROOT)],
                capture_output=True, text=True, encoding="utf-8", env=env, cwd=temp, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), Path(temp) / "ui")

    def test_artifact_checks_accept_data_root_and_dev_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"SCHOLARLY_DATA_ROOT": temp}):
                self.assertEqual(app_paths.data_root(), Path(temp))
                self.assertTrue(web_ui._under_outputs((Path(temp) / "ui" / "a.json").resolve()))
                self.assertTrue(web_ui._under_outputs((ROOT / "outputs" / "ui" / "a.json").resolve()))
                self.assertFalse(web_ui._under_outputs((Path(temp).parent / "elsewhere.json").resolve()))


class StaticAccountUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (UI_DIR / "ui.html").read_text(encoding="utf-8")
        cls.js = (UI_DIR / "ui.js").read_text(encoding="utf-8")
        cls.css = (UI_DIR / "ui.css").read_text(encoding="utf-8")
        cls.header = cls.html[cls.html.index("<header"):cls.html.index("</header>")]
        cls.en_block = cls.js[cls.js.index("/*I18N-BEGIN*/"):cls.js.index("/*I18N-END*/")]

    def test_account_area_is_hidden_until_the_server_says_available(self):
        self.assertRegex(self.header, r'<span id="account-area"[^>]*\bhidden\b')

    def test_sign_in_button_and_menu_exist_with_i18n(self):
        self.assertRegex(self.header, r'<button id="sign-in-button"[^>]*data-i18n="signIn"[^>]*>התחברות עם Google</button>')
        self.assertRegex(self.header, r'<button id="account-button"[^>]*aria-expanded="false"[^>]*data-i18n-aria="accountAria"')
        self.assertIn('id="account-menu"', self.header)
        self.assertRegex(self.header, r'id="account-sync-now"[^>]*data-i18n="syncNow"')
        self.assertRegex(self.header, r'id="account-sign-out"[^>]*data-i18n="signOut"')
        self.assertIn('id="account-email"', self.header)
        self.assertIn('id="account-sync-line"', self.header)

    def test_english_keys_exist(self):
        for key, value in (("signIn", "Sign in with Google"), ("syncNow", "Sync now"), ("signOut", "Sign out"),
                           ("accountAria", "Google account")):
            self.assertIn('"%s": "%s"' % (key, value), self.en_block)

    def test_library_restore_and_badge_text_exist(self):
        self.assertIn("Restore to this computer", self.js)
        self.assertIn("שחזור למחשב הזה", self.js)
        self.assertIn("In Drive", self.js)
        self.assertIn("class=\"drive-badge\"", self.js)
        self.assertIn("request('/account/remote-library'", self.js)
        self.assertIn("request('/account/restore'", self.js)
        self.assertIn('id="library-remote-message"', self.html)

    def test_routes_used_by_the_ui(self):
        for route in ("'/account'", "'/account/sign-in'", "'/account/sign-out'", "'/account/sync'"):
            self.assertIn("request(" + route, self.js)

    def test_menu_is_keyboard_accessible(self):
        self.assertIn("event.key==='Escape'", self.js)
        self.assertIn("setAttribute('aria-expanded'", self.js)
        self.assertIn(".account-menu", self.css)
        self.assertIn(":focus-visible", self.css)

    def test_sync_status_strings_are_localised(self):
        for text in ("Syncing…", "Sign in again", "Not synced yet", "Last synced: "):
            self.assertIn(text, self.js)

    def test_no_secrets_or_external_urls_in_ui_files(self):
        for text in (self.html, self.js, self.css):
            self.assertNotRegex(text, r"client_secret|refresh_token|access_token")


if __name__ == "__main__":
    unittest.main()
