import copy
import json
import unittest
from unittest import mock

from scholarly_translation import name_table as nt

SHAE = {"source": "Shae", "aliases": ["Kaul Shae", "Shaelinsan"], "hebrew": "שֵׁאי",
        "kind": "character", "gender": "female", "note": "Green Bone"}
WEN = {"source": "Wen", "aliases": [], "hebrew": "ון", "kind": "character", "gender": "male"}
WOON = {"source": "Woon", "aliases": [], "hebrew": "וון", "kind": "character", "gender": "male"}


def merged(*entries, origin="prepass"):
    t, _ = nt.merge_names(nt.new_table(), list(entries), 0, origin)
    return t


class TableTests(unittest.TestCase):
    def test_new_valid(self):
        self.assertTrue(nt.validate_table(nt.new_table()))

    def test_validate_errors(self):
        good = merged(SHAE)
        for mutate in (
            lambda t: t.update(schema="x"),
            lambda t: t.update(status="done"),
            lambda t: t.update(entries="x"),
            lambda t: t.update(warnings=[1]),
            lambda t: t["entries"][0].update(hebrew="Shae"),
            lambda t: t["entries"][0].update(kind="x"),
            lambda t: t["entries"][0].update(gender="x"),
            lambda t: t["entries"][0].update(origin="x"),
            lambda t: t["entries"][0].update(first_chapter=-1),
            lambda t: t["entries"][0].update(source="x" * 81),
            lambda t: t["entries"][0].update(aliases=["Shae"]),
            lambda t: t["entries"][0].update(note="x" * 301),
        ):
            t = copy.deepcopy(good)
            mutate(t)
            with self.assertRaises(nt.NameTableError):
                nt.validate_table(t)
        with self.assertRaises(nt.NameTableError):
            nt.validate_table([])


class CandidateTests(unittest.TestCase):
    TEXT = ("Kaul Shae walked in. Shae-jen smiled. Then Kaul Shae spoke to O'Neil. "
            "O'Neil nodded. Shae-jen left. The jade was green, then it faded. Jade is rare, said Wen. Wen and Woon met Woon.")

    def test_sequences_and_words(self):
        got = {c["name"]: c for c in nt.name_candidates([self.TEXT], "en")}
        self.assertEqual(got["Kaul Shae"]["count"], 2)
        self.assertEqual(got["O'Neil"]["count"], 2)
        self.assertEqual(got["Shae-jen"]["count"], 2)
        self.assertEqual(got["Wen"]["count"], 2)
        self.assertEqual(got["Woon"]["count"], 2)
        self.assertIn("Kaul Shae walked", got["Kaul Shae"]["snippet"])

    def test_sentence_initial_common_word_dropped(self):
        got = {c["name"] for c in nt.name_candidates(["the jade. The end. The"], "en", min_count=2)}
        self.assertNotIn("The", got)

    def test_sentence_initial_kept_without_lowercase_form(self):
        got = {c["name"] for c in nt.name_candidates(["Wen ran. Wen sat. Wen hid."], "en")}
        self.assertIn("Wen", got)

    def test_non_initial_kept_even_with_lowercase_form(self):
        got = {c["name"] for c in nt.name_candidates(["the jade. Jade ran, said Jade. He met Jade"], "en")}
        self.assertIn("Jade", got)

    def test_min_count_limit_order(self):
        got = nt.name_candidates(["a Bee b Bee c Bee d Ant e Ant f Cat"], "en")
        self.assertEqual([c["name"] for c in got], ["Bee", "Ant"])
        self.assertEqual(len(nt.name_candidates(["a Bee b Bee c Ant d Ant"], "en", limit=1)), 1)
        self.assertEqual(len(nt.name_candidates(["a Bee b Bee c Cat"], "en", min_count=1)), 2)

    def test_across_texts_and_newline_breaks_sequence(self):
        got = {c["name"] for c in nt.name_candidates(["x Kaul\nShae y", "z Kaul\nShae"], "en")}
        self.assertNotIn("Kaul Shae", got)
        self.assertIn("Kaul", got)

    def test_uncased_language(self):
        self.assertEqual(nt.name_candidates(["Shae Shae Shae"], "he"), [])
        self.assertEqual(nt.name_candidates(["Shae Shae"], "zh"), [])
        self.assertEqual(nt.name_candidates(["Shae Shae"], None), [])
        self.assertTrue(nt.name_candidates(["x Shae y Shae"], "fr-CA"))

    def test_snippet_bounded(self):
        got = nt.name_candidates(["word " * 100 + "Shae " + "word " * 100 + "Shae"], "en", snippet_chars=40)
        self.assertLessEqual(len(got[0]["snippet"]), 40)
        self.assertIn("Shae", got[0]["snippet"])


class PromptTests(unittest.TestCase):
    def test_build(self):
        p = nt.build_prepass_prompt([{"name": "Wen", "count": 3, "snippet": "said Wen"}], "literary", "en")
        self.assertIn("- Wen (3): said Wen", p)
        self.assertIn("literary", p)
        self.assertNotIn("{{", p)
        self.assertIn('"names"', p)
        self.assertIn("(none)", nt.build_prepass_prompt([], "scholarly", "fr"))


class ParseTests(unittest.TestCase):
    def test_parse_names(self):
        entries, dropped = nt.parse_names([
            {"source": " Shae ", "aliases": ["Kaul  Shae", "kaul shae", "shae", 3], "hebrew": "שֵׁאי",
             "kind": "Character", "gender": "?", "note": "n"},
            {"source": "X", "hebrew": "latin"},
            {"hebrew": "ון"},
            "bad",
        ], "keeper")
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual((e["source"], e["aliases"], e["kind"], e["gender"], e["origin"]),
                         ("Shae", ["Kaul Shae"], "character", "unknown", "keeper"))
        self.assertEqual([d["index"] for d in dropped], [1, 2, 3])
        self.assertEqual(nt.parse_names("x"), ([], []))
        self.assertEqual(nt.parse_names([{"source": "A", "hebrew": "א"}])[0][0]["kind"], "other")
        nt.validate_table({**nt.new_table(), "entries": entries})

    def test_prepass_response(self):
        obj = {"names": [{"source": "Wen", "hebrew": "ון"}]}
        with mock.patch("scholarly_translation.book_notebook.extract_json_object",
                        create=True, return_value=(obj, False)) as m:
            entries, dropped = nt.parse_prepass_response(json.dumps(obj))
        m.assert_called_once()
        self.assertEqual(m.call_args[0][1], ("names",))
        self.assertEqual(entries[0]["origin"], "prepass")
        for bad in ((None, False), ({"names": "x"}, False), ({"other": []}, False)):
            with mock.patch("scholarly_translation.book_notebook.extract_json_object",
                            create=True, return_value=bad):
                with self.assertRaises(nt.NameTableError):
                    nt.parse_prepass_response("junk")


class MergeTests(unittest.TestCase):
    def test_add_and_no_mutation(self):
        t = nt.new_table()
        before = copy.deepcopy(t)
        new, rep = nt.merge_names(t, [SHAE, WEN], 5, "keeper")
        self.assertEqual(t, before)
        self.assertEqual(rep["added"], ["Shae", "Wen"])
        self.assertEqual(new["entries"][0]["first_chapter"], 5)
        self.assertEqual(new["entries"][0]["origin"], "keeper")
        nt.validate_table(new)

    def test_existing_wins_on_collision(self):
        t = merged(SHAE)
        new, rep = nt.merge_names(t, [
            {"source": "SHAE", "hebrew": "שיי"},
            {"source": "Other", "aliases": ["shaelinsan"], "hebrew": "אחר"},
            {"source": "Fine", "hebrew": "פיין"},
        ], 3, "keeper")
        self.assertEqual([e["source"] for e in new["entries"]], ["Shae", "Fine"])
        self.assertEqual(new["entries"][0]["hebrew"], "שֵׁאי")
        self.assertEqual(len(rep["ignored"]), 2)
        self.assertEqual(rep["added"], ["Fine"])

    def test_identical_hebrew_conflict_added(self):
        t = merged(WEN)
        new, rep = nt.merge_names(t, [dict(WOON, hebrew="ון")], 1, "keeper")
        self.assertEqual(len(new["entries"]), 2)
        self.assertEqual(len(rep["conflicts"]), 1)
        self.assertTrue(new["warnings"])
        self.assertEqual(t["warnings"], [])

    def test_distinct_hebrew_no_conflict(self):
        _, rep = nt.merge_names(merged(WEN), [WOON], 1, "prepass")
        self.assertEqual(rep["conflicts"], [])

    def test_invalid_item_ignored_and_bad_origin(self):
        _, rep = nt.merge_names(nt.new_table(), [{"source": "A", "hebrew": "x"}], 0, "human")
        self.assertEqual(rep["added"], [])
        self.assertEqual(len(rep["ignored"]), 1)
        with self.assertRaises(nt.NameTableError):
            nt.merge_names(nt.new_table(), [], 0, "nobody")

    def test_table_full(self):
        t = nt.new_table()
        t["entries"] = [nt._clean_entry({"source": f"N{i}", "hebrew": "א"}, "prepass")[0]
                        for i in range(nt.MAX_ENTRIES)]
        new, rep = nt.merge_names(t, [{"source": "Extra", "hebrew": "ב"}], 0, "keeper")
        self.assertEqual(len(new["entries"]), nt.MAX_ENTRIES)
        self.assertEqual(rep["added"], [])


class RenderTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(nt.render_names(nt.new_table()), "")

    def test_line_format(self):
        out = nt.render_names(merged(SHAE, WEN))
        lines = out.split("\n")
        self.assertTrue(lines[0].startswith("NAMES (binding Hebrew forms"))
        self.assertEqual(lines[1], "- Shae (also: Kaul Shae, Shaelinsan) → שֵׁאי [character, female] — Green Bone")
        self.assertEqual(lines[2], "- Wen → ון [character, male]")

    def test_text_filter_whole_word_case_sensitive(self):
        t = merged(SHAE, WEN, WOON)
        out = nt.render_names(t, text="Kaul Shae met Woon. wen and Wend")
        self.assertIn("Shae", out)
        self.assertIn("Woon", out)
        self.assertNotIn("- Wen", out)
        self.assertEqual(nt.render_names(t, text="Shaeless"), "")

    def test_budget_truncation(self):
        t = merged(SHAE, WEN, WOON)
        out = nt.render_names(t, token_budget=40, count_tokens=lambda s: len(s.split()))
        self.assertIn("more names omitted)", out)
        self.assertIn("(... 3 more names omitted)", nt.render_names(t, token_budget=1, count_tokens=len))
        full = nt.render_names(t, token_budget=10 ** 6)
        self.assertNotIn("omitted", full)
        self.assertEqual(full, nt.render_names(t))

    def test_invalid_table(self):
        with self.assertRaises(nt.NameTableError):
            nt.render_names({"schema": "x"})


if __name__ == "__main__":
    unittest.main()
