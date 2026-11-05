"""API keys are entered, remembered and deleted only in the key window (the key icon in the header);
the translation options and the resume step only say what is missing and open it (user request 2026-11-05)."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[2] / "scholarly_translation" / "ui"


def _section(html, start, end):
    i = html.index(start)
    return html[i:html.index(end, i)]


class KeysLiveInTheKeyWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (UI / "ui.html").read_text(encoding="utf-8")
        cls.js = (UI / "ui.js").read_text(encoding="utf-8")
        cls.dialog = _section(cls.html, '<dialog id="key-dialog"', "</dialog>")
        cls.options = _section(cls.html, 'id="model-settings"', '<div id="preview-card"')
        cls.resume = _section(cls.html, '<div id="resume-keys"', '<div id="decision-box"')

    def test_the_key_window_holds_entry_remember_save_and_delete(self):
        for element in ('id="key-dialog-fields"', 'id="remember-keys"', 'id="save-keys"', 'id="forget-keys"', 'id="key-message"'):
            self.assertIn(element, self.dialog)
        self.assertNotIn('id="key-dialog-enter"', self.html)  # it used to send the user into the options

    def test_translation_options_have_no_key_entry(self):
        for gone in ('class="key-fields"', 'remember-keys', 'id="save-keys"', 'id="forget-keys"', 'type="password"'):
            self.assertNotIn(gone, self.options)
        for element in ('id="access-summary"', 'id="access-keys"', 'id="access-open-keys"'):
            self.assertIn(element, self.options)

    def test_resume_opens_the_key_window(self):
        self.assertIn('id="resume-open-keys"', self.resume)
        self.assertIn('id="resume-missing"', self.resume)
        for gone in ('key-fields', 'remember', 'type="password"', 'resume-save-keys'):
            self.assertNotIn(gone, self.resume)
        self.assertIn("$('resume-open-keys').onclick=showKeyDialog", self.js)
        self.assertIn("$('access-open-keys').onclick=showKeyDialog", self.js)

    def test_fields_cover_the_chosen_models_and_are_not_wiped_while_typing(self):
        self.assertIn("for(const pid of requiredProviderIds())ids.add(pid)", self.js)
        self.assertIn("if(!$('key-dialog').open)renderKeyDialogFields()", self.js)
        self.assertRegex(self.js, r"function showKeyDialog\(\)\{[^\n]*renderKeyDialogFields\(\)")

    def test_saving_rechecks_the_translation_and_the_resume_step(self):
        save = self.js[self.js.index("async function saveKeys(){"):]
        save = save[:save.index("\n}\n")]
        for call in ("renderKeyFields()", "updateSettings()", "renderResumeKeyFields()"):
            self.assertIn(call, save)


if __name__ == "__main__":
    unittest.main()
