"""Static and node checks for UI-STATUS: short result card and clear processing rows."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "scholarly_translation"


def _read(name):
    return (UI_DIR / name).read_text(encoding="utf-8")


def _function(js, name):
    start = js.index("function " + name + "(")
    depth, i = 0, js.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(js[i], 0)
        if depth == 0:
            return js[start:i + 1]
        i += 1


class ResultCardTests(unittest.TestCase):
    def setUp(self):
        self.js, self.html = _read("ui.js"), _read("ui.html")

    def test_limitations_grouped_not_joined(self):
        self.assertIn("groupLimitations", self.js)
        for kind in ("missing_translation", "inline_markup_flattened", "units_merged_multiple_blocks"):
            self.assertIn(kind, self.js)
        self.assertNotIn("limitations.map(l=>l.detail", self.js)
        self.assertNotIn("הערות על בניית הקובץ המתורגם: '+", self.js)

    def test_single_collapsed_details_holds_secondary_ids(self):
        m = re.search(r'<details id="result-details"[^>]*>(.*?)</details>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn(" open", m.group(0).split(">")[0])
        for ident in ("result-limitations", "result-notes", "result-findings", "result-usage"):
            self.assertIn('id="%s"' % ident, m.group(1))
        for ident in ("result-notice", "result-exceptions"):
            self.assertIn('id="%s"' % ident, self.html)
            self.assertNotIn('id="%s"' % ident, m.group(1))

    def test_review_notes_truncated_and_not_in_notice(self):
        self.assertIn("notes.slice(0,shown)", self.js)
        self.assertIn("ועוד ", self.js)
        self.assertNotIn("review_notes||[]).forEach(n=>notices", self.js)

    def test_notice_keeps_error_and_demo(self):
        body = _function(self.js, "renderResult")
        self.assertIn("currentJob.error", body)
        self.assertIn("תצוגת ניסיון", body)
        self.assertIn("הקובץ מוכן. נרשמו הערות בדיקה ובנייה", body)


class ProcessingRowsTests(unittest.TestCase):
    def setUp(self):
        self.js = _read("ui.js")

    def test_usage_isolated_ltr_with_separators(self):
        self.assertIn('<bdi dir="ltr">', self.js)
        self.assertIn("toLocaleString('en-US')", self.js)
        usage = _function(self.js, "renderUsage") + _function(self.js, "renderStats")
        self.assertIn("ltr(", usage)
        self.assertNotIn("קריאות לספק", usage)
        self.assertNotIn("toFixed", usage)  # money goes through usd()
        self.assertIn("<table", usage)
        self.assertIn("<details", usage)

    def test_labelled_rows(self):
        stats = _function(self.js, "renderStats")
        for label in ("שלב", "פרקים", "קריאות", "הוצאה משוערת", "שמור/ממתין", "נותר מהתקציב"):
            self.assertIn(label, stats)
        for label in ("מודל", "טוקנים בקלט", "טוקנים בפלט"):
            self.assertIn(label, self.js)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_helpers(self):
        src = "\n".join(
            [self.js[self.js.index("function esc("):].split("\n", 1)[0]]
            + [re.search(r"^const num=.*$", self.js, re.M).group(0)]
            + [_function(self.js, "groupLimitations")]
            + [re.search(r"^const LIMITATION_LABELS=.*$", self.js, re.M).group(0)]
        )
        script = src + """
const g=groupLimitations([{kind:'missing_translation'},{kind:'missing_translation'},{kind:'weird'},{kind:'inline_markup_flattened'}]);
console.log(JSON.stringify({g,n:num(1234567),u:esc('<b>')}));"""
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        data = json.loads(out)
        self.assertEqual(data["g"][0]["kind"], "missing_translation")
        self.assertEqual(data["g"][0]["count"], 2)
        self.assertEqual(data["n"], "1,234,567")
        self.assertEqual([x["label"] for x in data["g"] if x["kind"] == "weird"], ["weird"])
        self.assertEqual(len(data["g"]), 3)
        self.assertEqual(data["u"], "&lt;b&gt;")


if __name__ == "__main__":
    unittest.main()
