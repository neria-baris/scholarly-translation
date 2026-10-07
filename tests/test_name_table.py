import copy
import json
import unittest

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
    CH = [{"index": 0, "source": "Wen ran."}, {"index": 1, "source": "Woon sat."}]

    def test_build(self):
        p = nt.build_source_pass_prompt(self.CH, "  NAMES block  ", [{"name": "Wen", "count": 3}],
                                        "literary", "en")
        self.assertIn("=== CHAPTER 1 ===\nWen ran.\n\n=== CHAPTER 2 ===\nWoon sat.", p)
        self.assertLess(p.index("=== CHAPTER 1 ==="), p.index("=== CHAPTER 2 ==="))
        self.assertIn("\nNAMES block\n", p)
        self.assertIn("- Wen (3)\n", p)
        self.assertIn("literary", p)
        self.assertNotIn("{{", p)
        self.assertIn('"names"', p)

    def test_none_defaults(self):
        p = nt.build_source_pass_prompt(self.CH, "", [], "scholarly", "fr")
        self.assertEqual(p.count("(none)"), 2)
        p = nt.build_source_pass_prompt(self.CH, None, None, None, None)
        self.assertEqual(p.count("(none)"), 2)

    def test_placeholder_injection_safe(self):
        chs = [{"index": 4, "source": "Text {{NAMES_SO_FAR}} and {{CANDIDATES}} {{PROFILE_ID}}"}]
        p = nt.build_source_pass_prompt(chs, "KNOWN", [{"name": "Zed", "count": 2}], "lit", "en")
        self.assertIn("=== CHAPTER 5 ===\nText {{NAMES_SO_FAR}} and {{CANDIDATES}} {{PROFILE_ID}}", p)

    def test_candidates_without_snippet_and_old_function_gone(self):
        got = nt.name_candidates(["x Shae y Shae"], "en", snippet_chars=0)
        self.assertEqual(got[0]["name"], "Shae")
        self.assertEqual(got[0].get("snippet", ""), "")
        self.assertFalse(hasattr(nt, "build_prepass_prompt"))


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
        entries, dropped = nt.parse_prepass_response(json.dumps(obj))
        self.assertEqual(entries[0]["origin"], "prepass")
        self.assertEqual(dropped, [])
        entries, _ = nt.parse_prepass_response("```json\n" + json.dumps(obj) + "\n```")
        self.assertEqual(entries[0]["source"], "Wen")
        self.assertEqual(nt.parse_prepass_response('{"names":[]}'), ([], []))
        for bad in ("junk", '{"names": "x"}', '{"other": []}'):
            with self.assertRaises(nt.NameTableError):
                nt.parse_prepass_response(bad)


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
        self.assertEqual(lines[1], "- Shae (also: Kaul Shae, Shaelinsan) → שאי [character, female] — Green Bone")
        self.assertEqual(lines[2], "- Wen → ון [character, male]")

    def test_text_filter_whole_word_case_sensitive(self):
        t = merged(SHAE, WEN, WOON)
        out = nt.render_names(t, text="Kaul Shae met Woon. wen and Wend")
        self.assertIn("Shae", out)
        self.assertIn("Woon", out)
        self.assertNotIn("- Wen", out)
        self.assertEqual(nt.render_names(t, text="Shaeless"), "")

    def test_text_filter_cjk(self):
        # Japanese has no spaces: a particle or the next word follows the name directly.
        hilbert = {"source": "ヒルベルト", "aliases": [], "hebrew": "דויד הילברט", "kind": "person", "gender": "male"}
        formalism = {"source": "形式主義", "aliases": [], "hebrew": "פורמליזם", "kind": "term", "gender": "none"}
        zf = {"source": "ZF集合論", "aliases": [], "hebrew": "תורת הקבוצות של צרמלו ופרנקל", "kind": "term",
              "gender": "none"}
        kant = {"source": "Kant", "aliases": [], "hebrew": "קאנט", "kind": "person", "gender": "male"}
        t = merged(hilbert, formalism, zf, kant)
        out = nt.render_names(t, text="ヒルベルトの形式主義をZF集合論で論じた")
        for name in ("ヒルベルト", "形式主義", "ZF集合論"):
            self.assertIn("- " + name + " →", out)
        self.assertNotIn("- Kant", out)
        self.assertIn("- Kant →", nt.render_names(t, text="これはKantの議論である"))
        self.assertEqual(nt.render_names(t, text="Kantian ethics"), "")

    def test_markdown(self):
        self.assertEqual(nt.render_markdown(nt.new_table()), "")
        self.assertEqual(nt.render_markdown(None), "")
        pipe = dict(WEN, note="a|b")
        out = nt.render_markdown(merged(SHAE, pipe))
        self.assertIn("| Source | Also | Hebrew | Kind | Note |", out)
        self.assertIn("| Shae | Kaul Shae, Shaelinsan | שֵׁאי | character | Green Bone |", out)
        self.assertIn("| Wen |  | ון | character | a\\|b |", out)

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


class NiqqudTests(unittest.TestCase):
    """EXPORT-NIQQUD: prose is unvocalized, so NAMES shows plain forms except where they collide."""

    def test_plain_form(self):
        self.assertEqual(nt.plain_form("אָדָם בּוֹרֵיאַס"), "אדם בוריאס")
        self.assertEqual(nt.plain_form("בַּת־יַעֲנָה"), "בת־יענה")
        self.assertEqual(nt.plain_form("ג׳וֹן"), "ג׳ון")

    def test_vocalized_form_rendered_plain(self):
        adam = {"source": "Adam Boreas", "aliases": [], "hebrew": "אָדָם בּוֹרֵיאַס",
                "kind": "character", "gender": "male"}
        out = nt.render_names(merged(adam))
        self.assertIn("→ אדם בוריאס [", out)
        self.assertNotIn("אָדָם", out)

    def test_niqqud_kept_where_plain_forms_collide(self):
        a = {"source": "Bel", "aliases": [], "hebrew": "בֵּל", "kind": "character", "gender": "male"}
        b = {"source": "Bal", "aliases": [], "hebrew": "בַּל", "kind": "place", "gender": "none"}
        out = nt.render_names(merged(a, b, WEN))
        self.assertIn("→ בֵּל [", out)
        self.assertIn("→ בַּל [", out)
        self.assertIn("- Wen → ון [", out)

    def test_vav_doubling_counts_as_collision(self):
        wen = dict(WEN, hebrew="וֶן")
        woon = dict(WOON, hebrew="וּוּן")
        out = nt.render_names(merged(wen, woon))
        self.assertIn("→ וֶן [", out)
        self.assertIn("→ וּוּן [", out)

    def test_stored_table_unchanged(self):
        t = merged(SHAE)
        nt.render_names(t)
        self.assertEqual(t["entries"][0]["hebrew"], "שֵׁאי")


class VoiceTests(unittest.TestCase):
    """BOOK-VOICE: the first source-pass step also asks for register and key words."""

    def prompt(self, profile="literary", ask_voice=False):
        return nt.build_source_pass_prompt([{"index": 0, "source": "Senlin Ascends"}], "", [], profile, "en",
                                           ask_voice=ask_voice)

    def test_only_first_step_asks(self):
        self.assertNotIn("VOICE", self.prompt())
        self.assertNotIn("{{", self.prompt())
        literary = self.prompt(ask_voice=True)
        self.assertIn('- VOICE (this first step only)', literary)
        self.assertIn('"key_words"', literary)
        self.assertIn("נוסק", literary)
        self.assertIn("Output strict JSON only", literary)
        scholarly = self.prompt("scholarly", ask_voice=True)
        self.assertIn("academic Hebrew register", scholarly)
        self.assertNotIn("נוסק", scholarly)

    def test_parse_voice(self):
        raw = json.dumps({"names": [], "voice": {
            "register": "  עברית ספרותית,\n מעט ארכאית ", "key_words": [
                {"source": "ascend", "forms": ["ascends", "Ascend", "ascent", 7], "hebrew": "נסק", "note": "גבוה"},
                {"source": "ASCEND", "hebrew": "עלה"},
                {"source": "tower", "hebrew": "tower"},
                "junk"]}}, ensure_ascii=False)
        voice = nt.parse_voice(raw)
        self.assertEqual(voice["register"], "עברית ספרותית, מעט ארכאית")
        self.assertEqual(voice["key_words"], [{"source": "ascend", "forms": ["ascends", "ascent"],
                                               "hebrew": "נסק", "note": "גבוה"}])

    def test_parse_voice_absent_or_broken(self):
        for raw in (None, "", "not json", json.dumps({"names": []}), json.dumps({"names": [], "voice": "x"}),
                    json.dumps({"names": [], "voice": {"register": "", "key_words": []}})):
            self.assertIsNone(nt.parse_voice(raw), raw)

    def test_parse_voice_bounds(self):
        words = [{"source": "w%d" % i, "forms": ["f%d" % j for j in range(20)], "hebrew": "מילה"} for i in range(40)]
        voice = nt.parse_voice(json.dumps({"names": [], "voice": {"register": "א" * 5000, "key_words": words}}))
        self.assertEqual(len(voice["register"]), nt.MAX_REGISTER)
        self.assertEqual(len(voice["key_words"]), nt.MAX_KEY_WORDS)
        self.assertEqual(len(voice["key_words"][0]["forms"]), nt.MAX_KEY_WORD_FORMS)

    def test_names_parsing_unchanged_by_voice(self):
        raw = json.dumps({"names": [SHAE], "voice": {"register": "x"}}, ensure_ascii=False)
        entries, dropped = nt.parse_prepass_response(raw)
        self.assertEqual([e["source"] for e in entries], ["Shae"])


if __name__ == "__main__":
    unittest.main()
