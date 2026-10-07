"""Text-level checks for the bilingual help page."""
import re
import unittest
from pathlib import Path

HELP = Path(__file__).resolve().parents[1] / "scholarly_translation" / "help.html"


class HelpEnglishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = HELP.read_text(encoding="utf-8")
        he_start = cls.page.index('id="help-he"')
        en_start = cls.page.index('id="help-en"')
        cls.he = cls.page[he_start:en_start]
        cls.en = cls.page[en_start:cls.page.index("</main>")]

    def test_both_containers_exist_and_hebrew_is_default(self):
        self.assertIn('<html lang="he" dir="rtl"', self.page)
        self.assertIn('lang="he" dir="rtl"', self.he[:200] + self.page[self.page.index('id="help-he"') - 40:self.page.index('id="help-he"') + 80])
        self.assertIn('lang="en" dir="ltr"', self.page[self.page.index('id="help-en"') - 40:self.page.index('id="help-en"') + 80])
        self.assertIn("<title>עזרה", self.page)

    def test_same_number_of_sections(self):
        he = len(re.findall(r"<h2\b", self.he))
        en = len(re.findall(r"<h2\b", self.en))
        self.assertGreater(he, 5)
        self.assertEqual(he, en)
        for tag in ("<table", "<article", "<ol", "<ul", 'class="callout'):
            self.assertEqual(self.he.count(tag), self.en.count(tag), tag)

    def test_placeholders_in_both_languages(self):
        for ph in ("__PRICING_ROWS__", "__CATALOG_VERSION__", "__FONT_LIST__"):
            self.assertIn(ph, self.he)
            self.assertIn(ph, self.en)

    def test_language_script(self):
        self.assertIn("ui-language", self.page)
        self.assertIn("#en", self.page)
        self.assertIn("#he", self.page)
        self.assertIn("localStorage", self.page)
        self.assertIn("try{", self.page)

    def test_english_nav_points_to_english_ids(self):
        ids = set(re.findall(r'\bid="([^"]+)"', self.en))
        links = re.findall(r'href="#([^"]+)"', self.en)
        self.assertGreaterEqual(len(links), 12)
        for link in links:
            self.assertTrue(link.startswith("en-"), link)
            self.assertIn(link, ids)
        for h2_id in re.findall(r'<h2 id="([^"]+)"', self.en):
            self.assertTrue(h2_id.startswith("en-"), h2_id)

    def test_hebrew_links_stay_hebrew(self):
        ids = set(re.findall(r'\bid="([^"]+)"', self.he))
        for link in re.findall(r'href="#([^"]+)"', self.he):
            self.assertIn(link, ids)

    def test_ids_unique(self):
        ids = re.findall(r'\bid="([^"]+)"', self.page)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
