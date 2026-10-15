"""UI-LIBRARY-REDESIGN: theme layer, bundled typeface, logo and the library cat (contract
audit/contracts/ui_library_redesign.md). Static text checks plus a live route check."""
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from scholarly_translation.ui.web_ui import make_handler

UI_DIR = Path(__file__).resolve().parents[2] / "scholarly_translation" / "ui"


def _read(name):
    return (UI_DIR / name).read_text(encoding="utf-8")


class RedesignStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("ui.html")
        cls.js = _read("ui.js")
        cls.theme = _read("ui-theme.css")
        cls.cat = _read("cat.js")
        cls.cat_css = _read("cat.css")

    def test_theme_and_cat_load_after_the_base_styles_and_before_the_app(self):
        self.assertLess(self.html.index('href="/ui.css"'), self.html.index('href="/ui-theme.css"'))
        self.assertIn('<link rel="stylesheet" href="/cat.css">', self.html)
        self.assertLess(self.html.index('src="/cat.js"'), self.html.index('src="/ui.js"'))

    def test_logo_and_tab_icon(self):
        header = self.html[self.html.index('<header class="app-header">'):self.html.index("</header>")]
        self.assertIn('class="brand-logo"', header)
        self.assertIn('data-i18n="brand"', header)  # the brand name keeps its translation
        self.assertRegex(self.html, r'<link rel="icon" href="data:image/svg\+xml,')

    def test_cat_perches_mark_real_surfaces(self):
        for perch in ("hero", "desk", "dropzone", "result", "review", "library"):
            self.assertIn(f'data-perch="{perch}"', self.html)
        self.assertIn("footer.dataset.perch = 'footer'", self.cat)  # the footer tag itself stays untouched
        self.assertIn('<button id="cat-button" type="button" class="text-button cat-button" hidden>', self.html[self.html.index('<footer class="app-footer">'):])

    def test_no_remote_resources(self):
        for text in (self.theme, self.cat, self.cat_css):
            self.assertNotRegex(text, r"https?://(?!www\.w3\.org/2000/svg)")
            self.assertNotIn("@import", text)
        self.assertEqual(re.findall(r'url\("([^"]+)"\)', self.theme), ["/fonts/frank-ruhl-libre.ttf"])

    def test_cat_is_local_and_decorative(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "eval(", "speechSynthesis"):
            self.assertNotIn(forbidden, self.cat)
        self.assertEqual(sorted(set(re.findall(r"writePref\('([a-z-]+)'", self.cat))), ["cat-mode", "cat-sound"])
        self.assertIn('<div class="roam-thought" aria-hidden="true" hidden>', self.cat)
        self.assertIn("prefers-reduced-motion: reduce", self.cat)

    def test_app_hooks_are_guarded(self):
        self.assertIn("const catReact=(type,detail)=>{try{window.libraryCat?.react(type,detail)}catch(_){}}", self.js)
        self.assertNotRegex(self.js, r"(?<!\?)\blibraryCat\.(?!react)")


class ShelfTests(unittest.TestCase):
    """Stage 2: the shelf is built from the rendered list items and keeps their handlers."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("ui.html")
        cls.js = _read("ui.js")
        cls.shelf = _read("shelf.js")
        cls.theme = _read("ui-theme.css")

    def test_shelf_loads_between_the_cat_and_the_app(self):
        self.assertLess(self.html.index('src="/cat.js"'), self.html.index('src="/shelf.js"'))
        self.assertLess(self.html.index('src="/shelf.js"'), self.html.index('src="/ui.js"'))
        for element in ('id="library-tools"', 'id="library-shelf"', 'id="library-shelf-detail"', 'id="library-list"'):
            self.assertIn(element, self.html)

    def test_every_library_render_rebuilds_the_shelf(self):
        self.assertEqual(self.js.count("window.libraryShelf?.build()"), 2)
        for field in ("item.dataset.date=doc.completed_at", "item.dataset.size=doc.unit_count",
                      "item.dataset.progress=doc.total_units?", "item.dataset.date=book.completed_at"):
            self.assertIn(field, self.js)

    def test_shelf_moves_whole_items_so_their_actions_keep_working(self):
        self.assertIn("card.querySelector('.shelf-detail-item').append(b.li)", self.shelf)
        self.assertIn("$('library-list')?.append(li)", self.shelf)
        for forbidden in ("fetch(", "request(", "XMLHttpRequest", "/document-delete", "confirm("):
            self.assertNotIn(forbidden, self.shelf)

    def test_books_are_matte(self):
        shelf_css = self.theme[self.theme.index("Stage 2"):]
        for forbidden in ("perspective", "preserve-3d", "rotateY", "radial-gradient"):
            self.assertNotIn(forbidden, shelf_css)
        self.assertIn(".lib-spine:focus-visible .cover-face{transform:scaleX(1)", shelf_css)


class RedesignRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_new_static_files_are_served(self):
        for path, kind in (("/ui-theme.css", "text/css"), ("/cat.css", "text/css"), ("/cat.js", "text/javascript"), ("/shelf.js", "text/javascript"),
                           ("/fonts/frank-ruhl-libre.ttf", "font/ttf")):
            with urlopen(self.base + path, timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.headers.get("Content-Type", "").startswith(kind), path)
                self.assertGreater(len(response.read()), 1000, path)

    def test_unknown_paths_stay_closed(self):
        from urllib.error import HTTPError
        for path in ("/fonts/../ui.js", "/cat.js.map", "/fonts/other.ttf"):
            with self.assertRaises(HTTPError):
                urlopen(self.base + path, timeout=10)


if __name__ == "__main__":
    unittest.main()
