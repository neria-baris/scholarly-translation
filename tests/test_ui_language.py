"""Static and node checks for UI-EN: English interface switch for the main UI."""
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "scholarly_translation"
HEBREW = re.compile("[֐-׿]")
# Elements whose Hebrew text is (re)written by ui.js on every render, so no static key is needed.
DYNAMIC_IDS = {
    "profile-summary", "quality-summary", "model-summary", "translate-label", "send-note",
    "quality-help", "model-help", "connection-label", "connection-detail", "processing-title",
    "processing-detail", "library-intro", "library-empty", "result-eyebrow", "result-title",
    "cross-review-button", "result-cross-review-button",
}
VOID = {"br", "input", "meta", "link", "img", "hr"}


def _read(name):
    return (UI_DIR / name).read_text(encoding="utf-8")


class _Collect(HTMLParser):
    """Collects Hebrew-bearing elements and the i18n keys they declare."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems, self.keys = [], [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for attr, key in (("aria-label", "data-i18n-aria"), ("placeholder", "data-i18n-ph"), ("title", "data-i18n-title")):
            if a.get(attr) and HEBREW.search(a[attr]) and not a.get(key):
                self.problems.append("%s #%s: Hebrew %s without %s" % (tag, a.get("id"), attr, key))
        for key in ("data-i18n", "data-i18n-aria", "data-i18n-ph"):
            if a.get(key):
                self.keys.add(a[key])
        if tag not in VOID:
            covered = bool(a.get("data-i18n")) or a.get("id") in DYNAMIC_IDS or tag == "title"
            parent = self.stack[-1][1] if self.stack else False
            self.stack.append((tag, covered or parent, a.get("id")))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_data(self, data):
        if self.stack and HEBREW.search(data) and not self.stack[-1][1]:
            tag, _, ident = self.stack[-1]
            self.problems.append("<%s id=%s> has Hebrew text without an English entry: %s" % (tag, ident, data.strip()[:40]))


def _tables():
    js = _read("ui.js")
    block = js[js.index("/*I18N-BEGIN*/"):js.index("/*I18N-END*/")]
    script = block + "\nconsole.log(JSON.stringify({EN,STAGE_EN,IN_PROGRESS_EN,LIMITATION_EN}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


class StaticTests(unittest.TestCase):
    def setUp(self):
        self.js, self.html = _read("ui.js"), _read("ui.html")

    def test_language_button_in_header(self):
        header = self.html[self.html.index('<div class="header-actions">'):self.html.index("</header>")]
        self.assertRegex(header, r'<button id="language-button"[^>]*class="[^"]*quiet-button[^"]*"[^>]*>English</button>')
        self.assertIn('$(\'language-button\').onclick', self.js)
        self.assertIn("'עברית'", self.js)  # label in English mode

    def test_preference_persisted_with_try_catch(self):
        self.assertRegex(self.js, r"try\{if\(localStorage\.getItem\('ui-language'\)==='en'\)LANG='en'\}catch\(_\)\{\}")
        self.assertIn("remember('ui-language',next)", self.js)
        self.assertIn("function remember(key,value){try{", self.js)
        self.assertIn("let LANG='he'", self.js)  # Hebrew is the default

    def test_lang_and_dir_switching(self):
        self.assertIn("root.lang=LANG;root.dir=LANG==='en'?'ltr':'rtl'", self.js)
        self.assertIn('<html lang="he" dir="rtl">', self.html)
        self.assertIn("document.title=t(", self.js)

    def test_switch_does_not_reload_or_reset_review(self):
        body = self.js[self.js.index("function setLanguage("):]
        body = body[:body.index("\n}\n")]
        self.assertNotIn("location.reload", body)
        self.assertNotIn("renderResult()", body)  # would hide the review panel and drop edits
        self.assertIn("renderResultSummary()", body)
        self.assertIn("renderReviewLabels(", body)
        self.assertNotIn("review-target", body)
        self.assertNotIn("initRoleUI", body)  # would drop typed model fields

    def test_hebrew_target_stays_rtl(self):
        self.assertIn('<textarea id="review-target" dir="rtl"', self.html)
        css = _read("ui.css")
        self.assertIn("html[dir=ltr] .review-columns #review-target{direction:rtl}", css)

    def test_every_hebrew_element_has_english_entry(self):
        parser = _Collect()
        parser.feed(self.html)
        self.assertEqual(parser.problems, [])

    def test_hebrew_literals_in_js_are_wrapped(self):
        outside = self.js[:self.js.index("/*I18N-BEGIN*/")] + self.js[self.js.index("/*I18N-END*/"):]
        allowed = ("data-i18n", "LIMITATION_LABELS=", "IN_PROGRESS_STATUS=", "filename:'המסמך האחרון'", "const m=/^בדיקה")
        for number, line in enumerate(outside.split("\n"), 1):
            if HEBREW.search(line) and "t(" not in line and not any(token in line for token in allowed):
                self.fail("ui.js line %d has unwrapped Hebrew: %s" % (number, line.strip()[:100]))

    def test_dynamic_elements_listed_exist(self):
        for ident in DYNAMIC_IDS:
            self.assertIn('id="%s"' % ident, self.html)

    def test_free_form_server_text_rendered_dir_auto(self):
        for ident in ("decision-message", "processing-detail", "result-notice", "library-message"):
            self.assertIn("#" + ident, self.js[self.js.index("const FREE_SEL"):][:700])
        self.assertIn("setAttribute('dir','auto')", self.js)

    def test_forward_arrows_flip(self):
        self.assertIn("t('←','→')", self.js)
        self.assertEqual(self.js.count('<span aria-hidden="true">←</span>'), 0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = _tables()
        cls.html = _read("ui.html")
        cls.js = _read("ui.js")

    def test_syntax(self):
        subprocess.run(["node", "--check", str(UI_DIR / "ui.js")], check=True)

    def test_every_html_key_has_english(self):
        parser = _Collect()
        parser.feed(self.html)
        en = self.tables["EN"]
        # keys used by markup built in ui.js (role fields)
        keys = parser.keys | set(re.findall(r'data-i18n(?:-ph)?="([A-Za-z0-9]+)"', self.js))
        self.assertGreater(len(keys), 80)
        self.assertEqual(sorted(k for k in keys if k not in en), [])
        self.assertEqual(sorted(k for k in en if k not in keys), [])  # no dead entries

    def test_english_values_are_english(self):
        for key, value in self.tables["EN"].items():
            self.assertTrue(value.strip(), key)
            self.assertIsNone(HEBREW.search(value), key)
        for table in ("STAGE_EN", "IN_PROGRESS_EN", "LIMITATION_EN"):
            for key, value in self.tables[table].items():
                self.assertIsNone(HEBREW.search(value), (table, key))

    def test_markup_matches_hebrew_structure(self):
        en = self.tables["EN"]
        for key in ("heroTitle", "heroText", "chooseFile", "optionsLabel", "roleQa", "libraryStart", "downloadBtn", "reviewBtn", "nbDownload"):
            tags = sorted(re.findall(r"<(?:span|br|small)\b", en[key]))
            source = re.search(r'data-i18n="%s"[^>]*>(.*?)</(?:h1|h3|p|span|button|summary)>' % key, self.html, re.S)
            self.assertIsNotNone(source, key)
            self.assertEqual(tags, sorted(re.findall(r"<(?:span|br|small)\b", source.group(1))), key)

    def test_known_server_stage_labels_mapped(self):
        stages = self.tables["STAGE_EN"]
        known = ["קריאת המסמך", "מתרגם", "בניית המסמך המתורגם", "הושלם", "מושהה — התוצאות נשמרו",
                 "זיהוי טקסט (OCR) בעמודים סרוקים", "בדיקת ה־OCR בעזרת המודל", "בבדיקה", "בבדיקת פרקים",
                 "ממתין לבדיקה רוחבית", "הופסק", "בניית טבלת השמות של הספר", "בניית טבלת השמות והמונחים", "תרגום פרק / קבוצת יחידות",
                 "ביקורת מקטעים ו־QA פרקי"]
        for label in known:
            self.assertIn(label, stages)
        # every literal stage label assigned by the Python pipeline is mapped
        found = set()
        for path in UI_DIR.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            found.update(re.findall(r"stage_label[\"']\]\s*=\s*[^,\n]+,\s*[\"']([^\"'\n%]+)[\"']", text))
        self.assertGreater(len(found), 8)
        self.assertEqual(sorted(label for label in found if label not in stages), [])

    def test_stage_label_function_and_cross_window_pattern(self):
        js = self.js
        block = js[js.index("/*I18N-BEGIN*/"):js.index("/*I18N-END*/")]
        start = js.index("function stageLabel(")
        fn = js[start:js.index("\n}\n", start) + 3]
        script = "let LANG='en';\n" + block + "\n" + fn + """
const out={known:stageLabel('מתרגם'),window:stageLabel('בדיקה רוחבית של פרקים 3–9'),other:stageLabel('תווית חדשה'),empty:stageLabel('')};
LANG='he';out.he=stageLabel('מתרגם');
console.log(JSON.stringify(out));"""
        out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
        self.assertEqual(out["known"], "Translating")
        self.assertIn("3–9", out["window"])
        self.assertIsNone(HEBREW.search(out["window"]))
        self.assertEqual(out["other"], "תווית חדשה")  # unknown server text is shown as sent
        self.assertEqual(out["empty"], "")
        self.assertEqual(out["he"], "מתרגם")

    def test_english_terms_match_help_page(self):
        help_html = (UI_DIR / "help.html").read_text(encoding="utf-8")
        en = self.tables["EN"]
        for term in ("Library", "Ready", "In progress", "Pause", "Resume", "Decision required"):
            self.assertIn(term, help_html)
        self.assertEqual((en["library"], en["tabDone"], en["tabProgress"], en["pauseBtn"], en["resumeBtn"]),
                         ("Library", "Ready", "In progress", "Pause", "Resume"))
        self.assertIn("Decision required", self.js)
        self.assertIn("Prepare cross-review", self.js)
        self.assertIn("Run cross-review again", self.js)


if __name__ == "__main__":
    unittest.main()
