"""Static checks for the C4 bring-your-own-key guide."""
import re
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[2] / "scholarly_translation" / "ui"
LINKS = (
    "https://platform.openai.com/api-keys",
    "https://platform.openai.com/settings/organization/billing/overview",
    "https://platform.claude.com/settings/keys",
    "https://platform.claude.com/settings/billing",
    "https://platform.deepseek.com/api_keys",
    "https://platform.deepseek.com/top_up",
)


class KeysGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guide = (UI_DIR / "keys_guide.html").read_text(encoding="utf-8")
        cls.ui_html = (UI_DIR / "ui.html").read_text(encoding="utf-8")
        cls.ui_js = (UI_DIR / "ui.js").read_text(encoding="utf-8")

    def test_lang_and_dir(self):
        self.assertRegex(self.guide, r'<html lang="he" dir="rtl"')
        self.assertIn('lang="en" dir="ltr"', self.guide)

    def test_all_links_exact_and_safe(self):
        for url in LINKS:
            self.assertIn('href="%s" target="_blank" rel="noopener noreferrer"' % url, self.guide)
        for tag in re.findall(r"<a [^>]*href=\"https?://[^>]*>", self.guide):
            self.assertIn("noopener", tag)
            self.assertIn('target="_blank"', tag)
        external = set(re.findall(r'href="(https?://[^"]+)"', self.guide))
        self.assertEqual(external, set(LINKS))

    def test_no_external_resources(self):
        self.assertNotRegex(self.guide, r"<script[^>]*\ssrc=")
        self.assertNotRegex(self.guide, r"<link[^>]*href=\"(https?:)?//")
        self.assertNotRegex(self.guide, r"<(img|iframe)\b")
        self.assertNotRegex(self.guide, r"fetch\(|XMLHttpRequest|sendBeacon")

    def test_content(self):
        self.assertIn("gpt-6-luna", self.guide)
        self.assertIn("$0.10", self.guide)
        self.assertIn("$0.50", self.guide)
        self.assertIn("מפתח API", self.guide)
        self.assertIn("API key", self.guide)
        self.assertIn("ChatGPT", self.guide)
        self.assertIn("Remember on this computer", self.guide)
        self.assertIn("לזכור במחשב הזה", self.guide)

    def test_rates_match_catalogue(self):
        from scholarly_translation.models.catalog import CATALOG_VERSION, resolve
        self.assertIn(CATALOG_VERSION, self.guide)
        rates = resolve("openai", "gpt-6-luna").rates_per_million
        self.assertEqual((rates["input"], rates["output"]), (0.10, 0.50))

    def test_linked_from_key_dialog_and_start_panel(self):
        dialog = self.ui_html[self.ui_html.index('<dialog id="key-dialog"'):]
        dialog = dialog[:dialog.index("</dialog>")]
        self.assertIn('href="/keys-guide"', dialog)
        self.assertIn('rel="noopener noreferrer"', dialog)
        self.assertIn('id="start-keys-guide-link"', self.ui_html)
        self.assertIn('"keysGuideLink"', self.ui_js)


if __name__ == "__main__":
    unittest.main()
