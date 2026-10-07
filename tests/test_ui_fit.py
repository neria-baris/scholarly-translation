"""Static checks for the one-screen layout (UI-POLISH / UI-FIT). Text-level only."""
import re
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "scholarly_translation"


def _read(name):
    return (UI_DIR / name).read_text(encoding="utf-8")


class UiFitTests(unittest.TestCase):
    def test_header_has_help_link(self):
        html = _read("ui.html")
        header = html[html.index('<header class="app-header">'):html.index("</header>")]
        self.assertRegex(header, r'<a id="help-header-link"[^>]*href="/help"[^>]*target="_blank"[^>]*rel="noopener"[^>]*>עזרה</a>')
        self.assertIn("quiet-button", header[header.index("help-header-link"):][:80])

    def test_footer_help_link_kept(self):
        html = _read("ui.html")
        footer = html[html.index('<footer class="app-footer">'):]
        self.assertIn('href="/help"', footer)

    def test_workspace_does_not_force_tall_page(self):
        css = _read("ui.css")
        self.assertNotIn("min-height:calc(100vh - 166px)", css)
        self.assertNotRegex(css, r"\.workspace\{[^}]*min-height")

    def test_processing_panel_padding_is_compact(self):
        css = _read("ui.css")
        self.assertNotIn("padding:110px 0 120px", css)
        m = re.search(r"\.processing-panel\{text-align:center;padding:(\d+)px 0 (\d+)px\}", css)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)) + int(m.group(2)), 60)
        self.assertNotIn(".processing-panel{padding-top:80px}", css)

    def test_book_is_scaled_down(self):
        self.assertIn(".pixel-book{zoom:.75", _read("ui.css"))

    def test_compact_block_follows_laptop_marker_not_end_of_file(self):
        css = _read("ui.css")
        marker = "/* Keep the main action visible on ordinary laptop screens. */"
        self.assertIn(marker, css)
        self.assertLess(css.index(marker), css.index(".help-header-link"))
        self.assertFalse(css.rstrip().endswith(".help-header-link{font-weight:600;color:var(--teal)}"))

    def test_elements_kept(self):
        html = _read("ui.html")
        for i in ("start-panel", "processing-panel", "result-panel", "pixel-book",
                  "processing-percentage", "translation-progress", "processing-detail",
                  "processing-budget", "processing-usage", "translate-button"):
            self.assertIn(f'id="{i}"', html)


if __name__ == "__main__":
    unittest.main()
