"""PROFILE-EVERYWHERE: a drawn profile button and a sign-in window on every page.

Offline: the handler runs on 127.0.0.1:0 in a thread; no network call.
"""
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from scholarly_translation.ui.web_ui import make_handler

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "scholarly_translation" / "ui"
TOKEN = "profile-token-UNIQUE-42"
PAGES = ("/", "/learning", "/help", "/learning/help", "/keys-guide")
HELP_PAGES = ("/help", "/learning/help", "/keys-guide")


class ProfileEverywhereTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(TOKEN))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urlopen(self.url + path, timeout=15) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")

    def test_every_page_has_the_mount_and_loads_the_assets(self):
        for page in PAGES:
            with self.subTest(page=page):
                status, _, html = self.get(page)
                self.assertEqual(status, 200)
                self.assertEqual(html.count('id="profile-mount"'), 1)
                self.assertEqual(html.count('href="/profile.css"'), 1)
                self.assertEqual(html.count('src="/profile.js"'), 1)
                header = html[html.index('<header'):html.index('</header>')]
                self.assertIn('id="profile-mount"', header)

    def test_the_token_config_is_injected_before_the_script(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = self.get(page)[2]
                self.assertNotIn("__CONFIG__", html)
                config = html.index('window.UI_CONFIG = {"token": "%s"}' % TOKEN)
                self.assertLess(config, html.index('src="/profile.js"'))
        for page in HELP_PAGES:
            self.assertEqual(self.get(page)[2].count(TOKEN), 1)

    def test_static_files_are_served(self):
        status, kind, body = self.get("/profile.js")
        self.assertEqual(status, 200)
        self.assertTrue(kind.startswith("text/javascript"))
        self.assertIn("openai-account", body)
        status, kind, body = self.get("/profile.css")
        self.assertEqual(status, 200)
        self.assertTrue(kind.startswith("text/css"))
        self.assertIn(".pf-dialog", body)

    def test_old_google_header_button_is_hidden_but_drive_actions_stay_reachable(self):
        html = self.get("/")[2]
        css = self.get("/ui.css")[2]
        self.assertRegex(css, r"\.app-header \.account-area\{display:none!important\}")
        for element in ("sign-in-button", "account-sync-now", "account-sign-out", "library-button"):
            self.assertIn('id="%s"' % element, html)
        js = self.get("/profile.js")[2]
        for element in ("sign-in-button", "account-sync-now", "account-sign-out", "library-button"):
            self.assertIn("'%s'" % element, js)
        # Only one profile button is drawn in the header.
        self.assertEqual(js.count("button.id='profile-button'"), 1)

    def test_window_uses_only_existing_routes(self):
        js = (UI_DIR / "profile.js").read_text(encoding="utf-8")
        routes = set(re.findall(r"'(/(?:openai-account|account)[^']*)'", js))
        self.assertEqual(routes, {"/openai-account", "/openai-account/sign-in", "/openai-account/sign-out",
                                  "/openai-account/settings", "/account", "/account/sign-in",
                                  "/account/sync", "/account/sign-out"})
        self.assertIn("X-UI-Token", js)

    def test_drawing_is_flat_and_accessible(self):
        js = (UI_DIR / "profile.js").read_text(encoding="utf-8")
        css = (UI_DIR / "profile.css").read_text(encoding="utf-8")
        for colour in ("#e3893a", "#2a1a10", "#fffbea"):
            self.assertIn(colour, js)
        for text in (js, css):
            self.assertNotRegex(text, r"gradient|box-shadow:[^;]*\d+px|filter:|drop-shadow")
        self.assertIn("showModal", js)
        self.assertIn("aria-label", js)
        self.assertIn("MutationObserver", js)

    def test_no_secret_text_in_pages_or_assets(self):
        for name in ("profile.js", "profile.css"):
            text = (UI_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, text)
            self.assertNotRegex(text, r"sk-[A-Za-z0-9]{8}|Bearer ")
        for page in PAGES:
            html = self.get(page)[2]
            self.assertEqual(html.count(TOKEN) <= 1, True)
            self.assertNotRegex(html, r"sk-[A-Za-z0-9]{8}")


if __name__ == "__main__":
    unittest.main()
