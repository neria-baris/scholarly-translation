"""CLOUD-LIBRARY C6 integration in the web UI: update status route, the
automatic-update setting and the quiet notices. Offline; ui_status is patched."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import app_paths
from scholarly_translation.ui import web_ui
from scholarly_translation.ui.web_ui import make_handler

UI_DIR = Path(__file__).resolve().parents[2] / "scholarly_translation" / "ui"
TOKEN = "test-token"
STATUS = {"current": "1.0.0", "auto_update": True, "staged": "1.1.0", "available": "1.1.0",
          "notes_he": "", "notes_en": "", "last_error": "", "last_check": None,
          "updated_to": "1.0.0", "updated_notes_he": "הערות", "updated_notes_en": "Notes", "rejected": []}


class UpdateRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(TOKEN, account_factory=lambda: None))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, route, payload=None, token=TOKEN):
        request = Request(self.url + route, data=json.dumps(payload or {}).encode("utf-8"),
                          headers={"Content-Type": "application/json", "X-UI-Token": token, "Origin": self.url},
                          method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_status_is_null_in_a_development_checkout(self):
        with patch.object(web_ui, "ui_status", return_value=None):
            self.assertEqual(self.post("/update-status"), (200, {"status": None}))

    def test_real_ui_status_is_none_outside_an_installation(self):
        if app_paths.install_root() is not None:
            self.skipTest("running from an installed copy")
        self.assertIsNone(web_ui.ui_status())

    def test_status_is_passed_through_when_installed(self):
        with patch.object(web_ui, "ui_status", return_value=dict(STATUS)):
            status, body = self.post("/update-status")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"]["staged"], "1.1.0")
        self.assertEqual(body["status"]["updated_to"], "1.0.0")

    def test_settings_validate_bool_and_apply(self):
        with patch.object(web_ui, "ui_status", return_value=dict(STATUS)), \
                patch.object(web_ui, "set_auto_update") as setter:
            for bad in ("yes", 1, 0, None, [], {}):
                status, body = self.post("/update-settings", {"auto_update": bad})
                self.assertEqual(status, 400, repr(bad))
                self.assertIn("error", body)
            self.assertEqual(self.post("/update-settings", {})[0], 400)
            setter.assert_not_called()
            self.assertEqual(self.post("/update-settings", {"auto_update": False}),
                             (200, {"ok": True, "auto_update": False}))
            setter.assert_called_once_with(False)
            self.post("/update-settings", {"auto_update": True})
            setter.assert_called_with(True)

    def test_settings_unavailable_in_a_development_checkout(self):
        with patch.object(web_ui, "ui_status", return_value=None), \
                patch.object(web_ui, "set_auto_update") as setter:
            status, body = self.post("/update-settings", {"auto_update": True})
        self.assertEqual(status, 404)
        self.assertIn("error", body)
        setter.assert_not_called()

    def test_token_is_required(self):
        self.assertEqual(self.post("/update-status", token="bad")[0], 403)
        self.assertEqual(self.post("/update-settings", {"auto_update": True}, token="bad")[0], 403)

    def test_set_auto_update_writes_to_the_data_root(self):
        with tempfile.TemporaryDirectory() as data, patch.dict(web_ui.os.environ, {"SCHOLARLY_DATA_ROOT": data}):
            web_ui.set_auto_update(False)
            from scholarly_translation.update import updater
            self.assertFalse(updater.get_auto_update(Path(data)))


class StaticUpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (UI_DIR / "ui.html").read_text(encoding="utf-8")
        cls.js = (UI_DIR / "ui.js").read_text(encoding="utf-8")
        cls.en_block = cls.js[cls.js.index("/*I18N-BEGIN*/"):cls.js.index("/*I18N-END*/")]

    def test_everything_is_hidden_by_default(self):
        self.assertRegex(self.html, r'<div id="update-notice"[^>]*\bhidden\b')
        self.assertRegex(self.html, r'<span id="update-settings"[^>]*\bhidden\b')
        self.assertRegex(self.html, r'<span id="update-ready"[^>]*data-i18n="updateReady"[^>]*\bhidden\b')

    def test_auto_update_checkbox_has_a_localised_label(self):
        self.assertRegex(self.html, r'<input id="auto-update" type="checkbox">')
        self.assertIn('data-i18n="autoUpdate"', self.html)
        self.assertIn('"autoUpdate": "Automatic updates"', self.en_block)
        self.assertIn('"updateReady": "An update is ready', self.en_block)

    def test_notice_is_dismissible_and_remembered_safely(self):
        self.assertIn("localStorage.getItem('update-seen')", self.js)
        self.assertIn("remember('update-seen',", self.js)
        self.assertRegex(self.js, r"try\{seen=localStorage\.getItem\('update-seen'\)\}catch\(_\)\{\}")
        self.assertIn("Updated to version ", self.js)
        self.assertIn("עודכן לגרסה ", self.js)
        self.assertIn('id="update-notice-close"', self.html)

    def test_ui_uses_the_new_routes(self):
        self.assertIn("request('/update-status')", self.js)
        self.assertIn("request('/update-settings',{auto_update:want})", self.js)


if __name__ == "__main__":
    unittest.main()
