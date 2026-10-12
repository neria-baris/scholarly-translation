"""COMIC review on the literary mechanism (audit/contracts/comic_review.md)."""
import io
import json
import unittest

from PIL import Image

from scholarly_translation.comics import records, review as cr
from scholarly_translation.comics.model import ComicModelError


def critique(*issues, verdict=None):
    return json.dumps({"verdict": verdict or ("REVISE" if issues else "PASS"), "issues": list(issues)},
                      ensure_ascii=False)


def issue(**fields):
    base = {"id": "P3.1", "category": "over_literal", "severity": "MINOR", "source_span": "hola",
            "translation_span": "שלום לך", "problem": "literal", "suggested_correction": "היי"}
    base.update(fields)
    return base


def page(index, panels):
    p = records.new_page(index, "p.png", b"x", 400, 400)
    candidate = {"bbox": [10, 10, 60, 40], "interior": None, "background": [255, 255, 255],
                 "plain_background": True, "line_height": 10.0, "confidence": 0.9}
    for n, panel in enumerate(panels, 1):
        region = records.new_region(candidate, index, n, source_text="s%d" % n, panel=panel)
        region["translation"] = {"text": "תרגום %d" % n, "status": "ok", "note": ""}
        p["regions"].append(region)
    return p


class CritiqueTests(unittest.TestCase):
    def test_pass_and_revise(self):
        self.assertEqual(cr.parse_critique(critique(), ["P3.1"]), [])
        found = cr.parse_critique(critique(issue(category="Calque"), issue(category="humour", severity="major")),
                                  ["P3.1"])
        self.assertEqual([i["category"] for i in found], ["over_literal", "humor_wordplay"])
        self.assertEqual(found[1]["severity"], "MAJOR")
        self.assertEqual(cr.parse_critique(critique(issue(category="source_reading", suggested_correction="")),
                                           ["P3.1"])[0]["category"], "source_reading")

    def test_rejects(self):
        bad = [critique(issue(id="P9.9")), critique(issue(severity="huge")), critique(issue(category="style")),
               critique(issue(suggested_correction="שלום לך")), critique(issue(suggested_correction="")),
               critique(issue(), verdict="PASS"), json.dumps({"verdict": "MAYBE", "issues": []}), "no json"]
        for text in bad:
            with self.subTest(text[:40]), self.assertRaises(ComicModelError):
                cr.parse_critique(text, ["P3.1"])

    def test_review_suggestions_rule(self):
        rule = {("mistranslation", "MINOR"): True, ("hebrew_quality", "MINOR"): True,
                ("consistency", "MINOR"): False, ("consistency", "MAJOR"): True, ("continuity", "CRITICAL"): True,
                ("completeness", "CRITICAL"): False, ("source_reading", "MAJOR"): False}
        for (category, severity), expected in rule.items():
            self.assertEqual(cr.applies({"category": category, "severity": severity}), expected, category)

    def test_apply_span_only_when_unique(self):
        self.assertEqual(cr.apply_span("שלום לך, חבר", issue()), "היי, חבר")
        self.assertIsNone(cr.apply_span("שלום לך ושלום לך", issue()))
        self.assertIsNone(cr.apply_span("אחר לגמרי", issue()))


class UnitTests(unittest.TestCase):
    def test_scopes(self):
        pages = [page(1, [1, 1, 2]), page(2, [1, None]), page(3, [1])]
        self.assertEqual(len(cr.units(pages, "page")), 3)
        self.assertEqual([len(u) for u in cr.units(pages, "pages:2")], [2, 1])
        self.assertEqual([[r["order"] for r in u[0][1]] for u in cr.units(pages, "panel")],
                         [[1, 2], [3], [1], [2], [1]])
        for bad in ("pages:1", "chapter", None):
            with self.assertRaises(ComicModelError):
                cr.parse_scope(bad)

    def test_unit_image_and_prompt(self):
        pages = [page(4, [1]), page(5, [1])]
        images = {4: Image.new("RGB", (400, 400), "white"), 5: Image.new("RGB", (400, 400), "white")}
        unit = cr.units(pages, "pages:2")[0]
        self.assertEqual(Image.open(io.BytesIO(cr.unit_image(unit, images))).size, (800, 400))
        prompt = cr.critic_prompt(unit, images, records.new_notebook(), "es", "he")
        self.assertIn('"id": "P4.1"', prompt.text)
        self.assertIn('"id": "P5.1"', prompt.text)
        self.assertIn("source_reading", prompt.text)
        self.assertNotIn("{{", prompt.text)
        focused = cr.critic_prompt(unit, images, records.new_notebook(), "es", "he", focus={"P5.1"})
        self.assertIn("FOCUSED RECHECK", focused.text)
        self.assertNotIn('"id": "P4.1"', focused.text)


if __name__ == "__main__":
    unittest.main()
