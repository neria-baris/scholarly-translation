"""Static checks for the translation library UI (LIBRARY-HTML-INSTALLER B2).

These tests read ui.html / ui.js / ui.css as text; they need no browser, no
server and no provider calls. An optional syntax check runs only when node is
installed.
"""
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "scholarly_translation"


def _read(name):
    return (UI_DIR / name).read_text(encoding="utf-8")


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []  # (tag, attrs dict)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _elements(html):
    parser = _Collector()
    parser.feed(html)
    return parser.elements


class LibraryUiStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("ui.html")
        cls.js = _read("ui.js")
        cls.css = _read("ui.css")
        cls.elements = _elements(cls.html)
        cls.by_id = {attrs["id"]: (tag, attrs) for tag, attrs in cls.elements if "id" in attrs}

    def test_library_panel_present_hidden_and_labelled(self):
        tag, attrs = self.by_id["library-panel"]
        self.assertEqual(tag, "section")
        self.assertIn("hidden", attrs)
        self.assertEqual(attrs.get("aria-labelledby"), "library-title")
        for required in ("library-title", "library-list", "library-empty", "library-message", "library-back"):
            self.assertIn(required, self.by_id)

    def test_entry_points_in_header_and_start_panel(self):
        header = self.html[self.html.index('<header'):self.html.index('</header>')]
        self.assertIn('id="library-button"', header)
        self.assertIn("הספרייה", header)
        start = self.html[self.html.index('id="start-panel"'):self.html.index('id="processing-panel"')]
        self.assertIn('id="library-start-button"', start)
        for button_id in ("library-button", "library-start-button", "library-back"):
            tag, attrs = self.by_id[button_id]
            self.assertEqual(tag, "button")
            self.assertEqual(attrs.get("type"), "button")

    def test_library_panel_in_show_list(self):
        match = re.search(r"function show\(panel\)\{.*?for\(const id of \[([^\]]*)\]\)", self.js, re.S)
        self.assertIsNotNone(match)
        panels = re.findall(r"'([^']+)'", match.group(1))
        self.assertEqual(panels, ["start-panel", "processing-panel", "result-panel", "library-panel"])

    def test_routes_and_formats(self):
        self.assertIn("request('/document-library',{})", self.js)
        self.assertIn("request('/document-download',payload,true)", self.js)
        self.assertIn('data-format="html"', self.js)
        self.assertIn('data-format="${kind}"', self.js)
        self.assertIn("payload={job_id:doc.job_id,format}", self.js)
        self.assertIn("'.he.'+format", self.js)
        for label in ("הורדת HTML", "הורדת ${kind.toUpperCase()}", "פתיחה"):
            self.assertIn(label, self.js)

    def test_pdf_font_select_uses_available_fonts_and_job_default(self):
        self.assertIn("pdfFonts.filter(f=>f.available)", self.js)
        self.assertIn("libraryFontOptions(doc.font_id)", self.js)
        self.assertIn('class="library-font-select"', self.js)
        self.assertIn("kind==='pdf'?", self.js)
        self.assertIn("payload.font_id=select.value", self.js)

    def test_entries_are_accessible_and_escaped(self):
        self.assertIn('aria-expanded="false"', self.js)
        self.assertIn("aria-controls=", self.js)
        self.assertIn("setAttribute('aria-expanded'", self.js)
        self.assertIn("esc(doc.filename)", self.js)
        self.assertIn("esc(f.name)", self.js)
        self.assertIn("esc(f.id)", self.js)
        self.assertIn('class="library-entry"', self.js)
        self.assertIn('type="button" class="library-entry"', self.js)

    def test_open_reuses_existing_poll(self):
        body = self.js[self.js.index("function libraryOpen"):]
        body = body[:body.index("\n}")]
        self.assertIn("poll(doc.job_id)", body)

    def test_every_library_id_used_by_js_exists_in_html(self):
        used = set(re.findall(r"\$\('([a-z0-9-]+)'\)", self.js))
        missing = sorted(i for i in used if i not in self.by_id)
        self.assertEqual(missing, [])

    def test_css_matches_theme_and_mobile(self):
        for selector in (".library-card", ".library-entry", ".library-kind", ".library-actions", ".header-actions"):
            self.assertIn(selector, self.css)
        library_css = self.css[self.css.index(".header-actions"):]
        self.assertIn("var(--teal)", library_css)
        self.assertIn("var(--line)", library_css)
        self.assertIn("overflow-wrap:anywhere", library_css)
        self.assertIn("@media(max-width:650px)", library_css)
        self.assertNotRegex(library_css, r"url\(|@import|https?://")

    def test_no_new_external_resources(self):
        self.assertNotRegex(self.html, r"<(script|link)[^>]+(src|href)=\"https?://")
        self.assertNotIn("http://", self.js)
        self.assertNotIn("https://cdn", self.js)

    def test_existing_flows_still_wired(self):
        for wiring in ("$('translation-form').onsubmit=translate", "$('download-pdf').onclick=download",
                       "$('download-notebook').onclick=downloadNotebook", "$('review-button').onclick",
                       "$('library-button').onclick=openLibrary", "$('library-start-button').onclick=openLibrary",
                       "$('library-back').onclick=closeLibrary"):
            self.assertIn(wiring, self.js)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class LibraryUiSyntaxTests(unittest.TestCase):
    def test_ui_js_parses(self):
        result = subprocess.run(["node", "--check", str(UI_DIR / "ui.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
