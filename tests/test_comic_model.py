"""COMIC model stages (audit/contracts/comic_translation.md): prompts, validators,
reconciliation and notebook merge. Offline; no model is called."""
from __future__ import annotations

import io
import json
import unittest

from PIL import Image

from scholarly_translation import comic_model as cm
from scholarly_translation import comic_records as records
from tests.comic_fixtures import make_page


def candidate(box, **extra):
    base = {"bbox": list(box), "interior": None, "background": [255, 255, 255], "plain_background": True,
            "line_height": 20.0, "confidence": 0.9}
    base.update(extra)
    return base


def entry(mark=1, text="Hello", **extra):
    base = {"mark": mark, "box": None, "kind": "speech", "text": text, "speaker": "Dana",
            "speaker_gender": "female", "addressee_gender": "male", "order": mark}
    base.update(extra)
    return base


def answer(*entries, **extra):
    return json.dumps(dict({"regions": list(entries), "summary": "Dana speaks.", "characters": []}, **extra))


def make_comic_page(image, count=2):
    candidates = [candidate([100 * (i + 1), 100, 100 * (i + 1) + 80, 160]) for i in range(count)]
    page = records.new_page(1, "p.png", b"x", image.width, image.height)
    return page, candidates


def translated_page(image):
    page, candidates = make_comic_page(image, 2)
    parsed = cm.parse_recognition(answer(entry(1, "Where were you?"), entry(2, "At the library!", speaker="Ben",
                                                                              speaker_gender="male",
                                                                              addressee_gender="female")), 2)
    page["regions"] = cm.reconcile(page, image, candidates, parsed, lambda i, b: candidate(b))
    return page


class MarkedImageTests(unittest.TestCase):
    def test_long_edge_limit_and_marks_drawn(self):
        image = Image.new("RGB", (3200, 2000), (255, 255, 255))
        data = cm.marked_page_image(image, [candidate([1000, 500, 1400, 700])])
        marked = Image.open(io.BytesIO(data))
        self.assertEqual(marked.format, "JPEG")
        self.assertEqual(max(marked.size), cm.MARKED_LONG_EDGE)
        x, y = round(1000 * 0.5), round(600 * 0.5)  # the outline's left edge in the scaled image
        reds = [marked.getpixel((x + dx, y)) for dx in range(-4, 5)]
        self.assertTrue(any(r > 200 and g < 80 for r, g, _ in reds), reds)

    def test_small_image_not_enlarged(self):
        data = cm.marked_page_image(Image.new("RGB", (400, 300), (255, 255, 255)), [candidate([50, 50, 150, 100])])
        self.assertEqual(Image.open(io.BytesIO(data)).size, (400, 300))


class RecognitionPromptTests(unittest.TestCase):
    def test_contents(self):
        image = make_page(0.5).image
        notebook = {"characters": [{"name": "Dana", "target_name": "דנה", "gender": "female", "note": ""}],
                    "terms": []}
        prompt = cm.recognition_prompt(image, [candidate([10, 10, 80, 40]), candidate([100, 10, 180, 40])], "en",
                                       notebook)
        self.assertEqual(prompt.media_type, "image/jpeg")
        self.assertIn("1 to 2", prompt.text)
        self.assertIn("English", prompt.text)
        self.assertIn("Dana (female)", prompt.text)
        self.assertIn("left to right", prompt.text)
        self.assertNotIn("{{", prompt.text)
        self.assertIn("TRANSCRIBE", prompt.text)

    def test_manga_reads_right_to_left(self):
        prompt = cm.recognition_prompt(Image.new("RGB", (200, 200), "white"), [candidate([10, 10, 50, 50])], "ja",
                                       {"characters": [], "terms": []})
        self.assertIn("Japanese", prompt.text)
        self.assertIn("right to left", prompt.text)
        self.assertIn("(none yet)", prompt.text)


class ParseRecognitionTests(unittest.TestCase):
    def test_good_answer_with_fences_and_added_box(self):
        text = "```json\n" + answer(entry(2, "Second", order=1),
                                    entry(None, "Added", kind="sign", box=[100, 200.4, 300, 400], order=2),
                                    entry(1, "First  line\nbroken", order=3)) + "\n```"
        parsed = cm.parse_recognition(text, 2)
        self.assertEqual([r["text"] for r in parsed["regions"]], ["Second", "Added", "First line broken"])
        self.assertEqual([r["order"] for r in parsed["regions"]], [1, 2, 3])
        self.assertEqual(parsed["regions"][1]["box"], [100, 200, 300, 400])
        self.assertEqual(parsed["summary"], "Dana speaks.")

    def test_order_missing_or_tied_keeps_list_position(self):
        text = answer(entry(1, "A", order=None), entry(2, "B", order=None))
        self.assertEqual([r["text"] for r in cm.parse_recognition(text, 2)["regions"]], ["A", "B"])
        text = answer(entry(1, "A", order=1), entry(2, "B", order=1))
        self.assertEqual([r["text"] for r in cm.parse_recognition(text, 2)["regions"]], ["A", "B"])

    def test_empty_page_is_valid(self):
        self.assertEqual(cm.parse_recognition(answer(), 3)["regions"], [])

    def test_rejects(self):
        bad = {
            "not json": "no braces here",
            "not an object": "[1, 2]",
            "regions not list": json.dumps({"regions": {}}),
            "mark out of range": answer(entry(3)),
            "mark zero": answer(entry(0)),
            "duplicate mark": answer(entry(1), entry(1, "again")),
            "mark is bool": answer(entry(True)),
            "bad kind": answer(entry(1, kind="shout")),
            "bad gender": answer(entry(1, speaker_gender="robot")),
            "empty text": answer(entry(1, text="  ")),
            "no text": answer({"mark": 1, "kind": "speech"}),
            "no mark no box": answer(entry(None)),
            "box out of range": answer(entry(None, box=[0, 0, 1001, 10])),
            "negative box": answer(entry(None, box=[-1, 0, 10, 10])),
            "empty box": answer(entry(None, box=[10, 10, 10, 20])),
            "short box": answer(entry(None, box=[1, 2, 3])),
            "order not int": answer(entry(1, order="first")),
            "hebrew instead of source": answer(entry(1, text="איפה היית אתמול בלילה?")),
            "character without name": answer(entry(1), characters=[{"gender": "male"}]),
        }
        for label, text in bad.items():
            with self.subTest(label), self.assertRaises(cm.ComicModelError):
                cm.parse_recognition(text, 2)

    def test_non_text_input(self):
        for value in (None, "", "   "):
            with self.assertRaises(cm.ComicModelError):
                cm.parse_recognition(value, 1)

    def test_few_hebrew_letters_in_source_are_fine(self):
        self.assertEqual(len(cm.parse_recognition(answer(entry(1, "Shalom שלום friend, how are you?")), 1)["regions"]), 1)


class ReconcileTests(unittest.TestCase):
    def test_origins_ids_order_and_unanswered_mark(self):
        image = Image.new("RGB", (1000, 2000), "white")
        page, candidates = make_comic_page(image, 3)
        snapped = []

        def snap(img, box):
            snapped.append(box)
            return candidate(box, line_height=33.0)

        parsed = cm.parse_recognition(answer(entry(3, "Third", order=1),
                                             entry(None, "Added", kind="narration", box=[100, 500, 300, 600], order=2),
                                             entry(1, "First", order=3)), 3)
        regions = cm.reconcile(page, image, candidates, parsed, snap)
        self.assertEqual([r["region_id"] for r in regions], ["p001-r01", "p001-r02", "p001-r03"])
        self.assertEqual([r["order"] for r in regions], [1, 2, 3])
        self.assertEqual([r["origin"] for r in regions], ["local", "model", "local"])
        self.assertEqual(regions[0]["bbox"], candidates[2]["bbox"])
        self.assertEqual(snapped, [[100, 1000, 300, 1200]])      # 0..1000 grid scaled to the 1000x2000 page
        self.assertEqual(regions[1]["line_height"], 33.0)
        self.assertEqual(regions[1]["kind"], "narration")
        self.assertEqual(regions[0]["speaker"], "Dana")
        self.assertEqual(page["warnings"], ["unanswered_mark:2"])
        page["regions"] = regions
        records.validate_page(page)

    def test_failed_snap_falls_back_to_the_box(self):
        image = Image.new("RGB", (500, 500), "white")
        page, candidates = make_comic_page(image, 0)
        parsed = cm.parse_recognition(answer(entry(None, "Added", box=[100, 100, 400, 300])), 0)

        def snap(img, box):
            raise RuntimeError("no balloon")
        regions = cm.reconcile(page, image, candidates, parsed, snap)
        self.assertEqual(regions[0]["bbox"], [50, 50, 200, 150])
        self.assertIn("snap_failed", regions[0]["warnings"])
        page["regions"] = regions
        records.validate_page(page)


class TranslationPromptTests(unittest.TestCase):
    def test_contents(self):
        image = make_page(0.5).image
        page = translated_page(image)
        ids = [r["region_id"] for r in page["regions"]]
        notebook = {"characters": [{"name": "Dana", "target_name": "דנה", "gender": "female", "note": "tall"}],
                    "terms": [{"source": "the Guild", "target": "הגילדה"}]}
        prompt = cm.translation_prompt(image, page, notebook, ["Page one.", "Page two.", "Page three."], "en", "he",
                                       {ids[0]: 25, ids[1]: 40})
        text = prompt.text
        self.assertEqual(prompt.media_type, "image/jpeg")
        self.assertIn("Hebrew", text)
        self.assertIn("right-to-left", text)
        self.assertIn("Dana -> דנה (female): tall", text)
        self.assertIn("the Guild -> הגילדה", text)
        self.assertIn("Page two.", text)
        self.assertIn("Page three.", text)
        self.assertNotIn("Page one.", text)                    # only the last two summaries
        rows = [json.loads(line) for line in text.splitlines() if line.startswith('{"id"')]
        self.assertEqual([r["id"] for r in rows], ids)
        self.assertEqual(rows[0]["max_chars"], 25)
        self.assertEqual(rows[0]["speaker_gender"], "female")
        self.assertEqual(rows[1]["addressee_gender"], "female")
        self.assertEqual(rows[1]["speaker"], "Ben")
        self.assertEqual(rows[0]["source"], "Where were you?")
        self.assertNotIn("{{", text)

    def test_ltr_target_and_first_page(self):
        image = make_page(0.5).image
        page = translated_page(image)
        prompt = cm.translation_prompt(image, page, records.new_notebook(), [], "fr", "en", {})
        self.assertIn("left-to-right", prompt.text)
        self.assertIn("English", prompt.text)
        self.assertIn("first page", prompt.text)
        self.assertIn("(none yet)", prompt.text)


def reply(ids, texts=None, **extra):
    texts = texts or ["שלום עולם"] * len(ids)
    return json.dumps(dict({"translations": [{"id": i, "text": t, "note": ""} for i, t in zip(ids, texts)],
                            "notebook": {"characters": [], "terms": []}, "summary": "S"}, **extra),
                      ensure_ascii=False)


class ParseTranslationTests(unittest.TestCase):
    IDS = ["p001-r01", "p001-r02"]

    def test_good_answer(self):
        raw = "```\n" + reply(self.IDS, ["איפה היית אתמול?", "הייתי בספרייה, אמרתי לך. Tom!"],
                              notebook={"characters": [{"name": "Dana", "target_name": "דנה", "gender": "female"},
                                                       {"name": "Ben", "target_name": ""}],
                                        "terms": [{"source": "Guild", "target": "גילדה"}]}) + "\n```"
        parsed = cm.parse_translation(raw, self.IDS, "he")
        self.assertEqual([t["id"] for t in parsed["translations"]], self.IDS)
        self.assertEqual(parsed["notebook"]["characters"], [
            {"name": "Dana", "target_name": "דנה", "gender": "female", "note": ""}])
        self.assertEqual(parsed["notebook"]["terms"], [{"source": "Guild", "target": "גילדה"}])
        self.assertEqual(parsed["summary"], "S")

    def test_answer_in_other_order_is_returned_in_request_order(self):
        raw = reply(list(reversed(self.IDS)), ["שניים שניים", "אחד אחד"])
        parsed = cm.parse_translation(raw, self.IDS, "he")
        self.assertEqual([t["text"] for t in parsed["translations"]], ["אחד אחד", "שניים שניים"])

    def test_rejects(self):
        hebrew = "שלום עולם"
        bad = {
            "missing id": reply(self.IDS[:1]),
            "extra id": reply(self.IDS + ["p001-r03"]),
            "duplicate id": reply([self.IDS[0], self.IDS[0]]),
            "empty text": reply(self.IDS, [hebrew, "  "]),
            "text not string": json.dumps({"translations": [{"id": self.IDS[0], "text": 5},
                                                            {"id": self.IDS[1], "text": hebrew}]}),
            "english instead of hebrew": reply(self.IDS, [hebrew, "Where were you last night?"]),
            "not json": "Sure, here is the translation",
            "translations not list": json.dumps({"translations": "x"}),
            "bad notebook gender": reply(self.IDS, notebook={"characters": [{"name": "A", "target_name": "ב",
                                                                              "gender": "alien"}], "terms": []}),
            "bad term": reply(self.IDS, notebook={"characters": [], "terms": [{"source": "a"}]}),
        }
        for label, raw in bad.items():
            with self.subTest(label), self.assertRaises(cm.ComicModelError):
                cm.parse_translation(raw, self.IDS, "he")

    def test_sfx_may_stay_in_source_letters_and_short_names_pass(self):
        raw = reply(self.IDS, ["BOOM!", "אני בסדר"])
        with self.assertRaises(cm.ComicModelError):
            cm.parse_translation(raw, self.IDS, "he")
        parsed = cm.parse_translation(raw, self.IDS, "he", {self.IDS[0]: "sfx", self.IDS[1]: "speech"})
        self.assertEqual(parsed["translations"][0]["text"], "BOOM!")
        self.assertEqual(len(cm.parse_translation(reply(self.IDS, ["Tom", "123"]), self.IDS, "he")["translations"]), 2)

    def test_english_target_check_uses_latin(self):
        ids = ["a"]
        self.assertEqual(cm.parse_translation(reply(ids, ["Where were you?"]), ids, "en")["translations"][0]["text"],
                         "Where were you?")
        with self.assertRaises(cm.ComicModelError):
            cm.parse_translation(reply(ids, ["איפה היית אתמול"]), ids, "en")


class ShortenTests(unittest.TestCase):
    def test_prompt_and_parse(self):
        image = make_page(0.5).image
        page = translated_page(image)
        ids = [r["region_id"] for r in page["regions"]]
        items = [{"id": ids[1], "text": "הייתי בספרייה ואמרתי לך כבר", "max_chars": 10}]
        prompt = cm.shorten_prompt(image, page, items, "he")
        self.assertIn("Hebrew", prompt.text)
        row = json.loads([l for l in prompt.text.splitlines() if l.startswith('{"id"')][0])
        self.assertEqual((row["id"], row["max_chars"], row["current"]), (ids[1], 10, items[0]["text"]))
        self.assertEqual(row["source"], "At the library!")
        raw = json.dumps({"translations": [{"id": ids[1], "text": "בספרייה!"}]}, ensure_ascii=False)
        self.assertEqual(cm.parse_shorten(raw, [ids[1]], "he", {ids[1]: items[0]["text"]}), {ids[1]: "בספרייה!"})
        longer = json.dumps({"translations": [{"id": ids[1], "text": items[0]["text"] + " עוד"}]}, ensure_ascii=False)
        for raw in (longer, json.dumps({"translations": []}), json.dumps({"translations": [{"id": "x", "text": "ש"}]})):
            with self.assertRaises(cm.ComicModelError):
                cm.parse_shorten(raw, [ids[1]], "he", {ids[1]: items[0]["text"]})


class NotebookMergeTests(unittest.TestCase):
    def test_new_entries_added_and_earlier_names_win(self):
        notebook = {"characters": [{"name": "Dana", "target_name": "דנה", "gender": "unknown", "note": ""}],
                    "terms": [{"source": "Guild", "target": "גילדה"}]}
        updates = {"characters": [{"name": "dana", "target_name": "דנית", "gender": "female", "note": "tall"},
                                  {"name": "Ben", "target_name": "בן", "gender": "male", "note": ""}],
                   "terms": [{"source": "guild", "target": "איגוד"}, {"source": "Keep", "target": "מצודה"}]}
        merged, warnings = cm.merge_notebook(notebook, updates)
        self.assertEqual(warnings, ["notebook_conflict:dana", "notebook_conflict:guild"])
        self.assertEqual(merged["characters"][0], {"name": "Dana", "target_name": "דנה", "gender": "female",
                                                    "note": "tall"})
        self.assertEqual([c["name"] for c in merged["characters"]], ["Dana", "Ben"])
        self.assertEqual(merged["terms"], [{"source": "Guild", "target": "גילדה"},
                                           {"source": "Keep", "target": "מצודה"}])
        self.assertEqual(notebook["characters"][0]["gender"], "unknown")      # input untouched

    def test_agreeing_update_is_silent_and_gender_conflict_warns(self):
        notebook = {"characters": [{"name": "Dana", "target_name": "דנה", "gender": "female", "note": ""}],
                    "terms": []}
        merged, warnings = cm.merge_notebook(notebook, {"characters": [
            {"name": "Dana", "target_name": "דנה", "gender": "female", "note": ""}], "terms": []})
        self.assertEqual(warnings, [])
        _, warnings = cm.merge_notebook(notebook, {"characters": [
            {"name": "Dana", "target_name": "", "gender": "male", "note": ""}], "terms": []})
        self.assertEqual(warnings, ["notebook_conflict:Dana"])

    def test_invalid_result_raises(self):
        with self.assertRaises(records.ComicRecordError):
            cm.merge_notebook(records.new_notebook(), {"characters": [
                {"name": "X", "target_name": "י", "gender": "alien", "note": ""}], "terms": []})


if __name__ == "__main__":
    unittest.main()
