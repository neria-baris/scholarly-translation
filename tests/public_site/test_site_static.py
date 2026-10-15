"""Static checks for the public site (C5)."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[2] / "site"
PAGES = ["index.html", "keys.html", "privacy.html"]
PROVIDER_LINKS = [
    "https://platform.openai.com/api-keys",
    "https://platform.openai.com/settings/organization/billing/overview",
    "https://platform.claude.com/settings/keys",
    "https://platform.claude.com/settings/billing",
    "https://platform.deepseek.com/api_keys",
    "https://platform.deepseek.com/top_up",
]
DOWNLOAD = ("https://github.com/<DIST_REPO>/releases/latest/download/"
            "ScholarlyTranslation-Setup.zip")


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []  # (tag, attrs dict)
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def load(name):
    text = (SITE / name).read_text(encoding="utf-8")
    parser = Collector()
    parser.feed(text)
    return text, parser


def is_external(href):
    return bool(re.match(r"^(https?:)?//", href or ""))


class SiteStaticTests(unittest.TestCase):
    def test_pages_exist(self):
        for name in PAGES + ["site.css"]:
            self.assertTrue((SITE / name).is_file(), name)

    def test_head_basics(self):
        for name in PAGES:
            text, p = load(name)
            html = [a for t, a in p.tags if t == "html"]
            self.assertEqual(len(html), 1, name)
            self.assertTrue(html[0].get("lang"), name)
            self.assertIn(html[0].get("dir"), ("rtl", "ltr"), name)
            self.assertTrue(p.title.strip(), name)
            metas = [a for t, a in p.tags if t == "meta"]
            self.assertTrue(any(m.get("charset") for m in metas), name)
            self.assertTrue(any(m.get("name") == "viewport" for m in metas), name)

    def test_english_section_present(self):
        for name in PAGES:
            _, p = load(name)
            self.assertTrue(
                any(t == "section" and a.get("lang") == "en" and a.get("dir") == "ltr"
                    for t, a in p.tags), name)

    def test_no_external_resources(self):
        for name in PAGES:
            text, p = load(name)
            for t, a in p.tags:
                if t == "script":
                    self.assertNotIn("src", a, name)
                if t == "link":
                    self.assertFalse(is_external(a.get("href")), name)
                if t in ("img", "source", "iframe", "video", "audio"):
                    self.assertFalse(is_external(a.get("src")), name)
            self.assertNotRegex(text, r"url\(\s*['\"]?https?:", name)
            self.assertNotRegex(text, r"@import", name)
        css = (SITE / "site.css").read_text(encoding="utf-8")
        self.assertNotRegex(css, r"https?:|@import")

    def test_external_links_noopener(self):
        for name in PAGES:
            _, p = load(name)
            for t, a in p.tags:
                if t == "a" and is_external(a.get("href")):
                    self.assertIn("noopener", (a.get("rel") or "").split(), name)

    def test_keys_provider_links(self):
        text, p = load("keys.html")
        hrefs = {a.get("href") for t, a in p.tags if t == "a"}
        for link in PROVIDER_LINKS:
            self.assertIn(link, hrefs)
        external = {h for h in hrefs if is_external(h)}
        self.assertEqual(external, set(PROVIDER_LINKS))

    def test_index_download_placeholder(self):
        _, p = load("index.html")
        hrefs = [a.get("href") for t, a in p.tags if t == "a"]
        self.assertEqual(hrefs.count(DOWNLOAD), 2)  # Hebrew and English buttons

    def test_privacy_content(self):
        text, _ = load("privacy.html")
        self.assertIn("drive.file", text)
        self.assertIn("&lt;CONTACT_EMAIL&gt;", text)
        self.assertIn("Credential Manager", text)

    def test_internal_links_resolve(self):
        for name in PAGES:
            _, p = load(name)
            for t, a in p.tags:
                if t == "link" or t == "a":
                    href = a.get("href")
                    if not href or is_external(href) or href.startswith("mailto:"):
                        continue
                    parts = urlsplit(href)
                    target = SITE / parts.path if parts.path else SITE / name
                    self.assertTrue(target.is_file(), f"{name}: {href}")
                    if parts.fragment and target.suffix == ".html":
                        _, tp = load(target.name)
                        ids = {x.get("id") for _, x in tp.tags}
                        self.assertIn(parts.fragment, ids, f"{name}: {href}")


if __name__ == "__main__":
    unittest.main()
