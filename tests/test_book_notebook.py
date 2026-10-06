import copy
import json
import time
import unittest

from scholarly_translation import book_notebook as bn


def resp(ops=None, summary="A chapter happened.", story="So far."):
    return json.dumps({"ops": ops or [], "chapter_summary": summary, "story_so_far": story})


def add(title, tags=("name",), **kw):
    d = {"op": "add", "tags": list(tags), "title": title, "note": "note for " + title}
    d.update(kw)
    return d


def words(text):
    return len(text.split())


class BookNotebookTests(unittest.TestCase):
    def setUp(self):
        self.nb = bn.new_notebook("doc1")

    def test_new_notebook_validates(self):
        self.assertTrue(bn.validate_notebook(self.nb))
        self.assertEqual(self.nb["revision"], 0)

    def test_validate_rejects_bad(self):
        for mutate in (
            lambda n: n.update(schema="x"),
            lambda n: n.update(revision=-1),
            lambda n: n.update(story_so_far="x" * (bn.MAX_STORY + 1)),
            lambda n: n["chapter_summaries"].update({"a": "s"}),
        ):
            nb = bn.new_notebook("d")
            mutate(nb)
            with self.assertRaises(bn.NotebookError):
                bn.validate_notebook(nb)
        nb, _ = bn.apply_keeper_response(self.nb, resp([add("X")]), 0)
        nb["entries"][0]["tags"] = ["A"]
        with self.assertRaises(bn.NotebookError):
            bn.validate_notebook(nb)

    def test_bounds_clamped(self):
        op = add("T" * 500, tags=["  Word Play ", "a" * 100, "b", "c", "d", "e"],
                 note="n" * (bn.MAX_NOTE + 500), hebrew_rendering="h" * (bn.MAX_RENDERING + 99),
                 match_terms=["m%d" % i for i in range(bn.MAX_MATCH_TERMS + 28)] + [7])
        nb, rep = bn.apply_keeper_response(self.nb, resp([op], summary="s" * (bn.MAX_SUMMARY + 800), story="t" * (bn.MAX_STORY + 5000)), 2)
        bn.validate_notebook(nb)
        e = nb["entries"][0]
        self.assertEqual(len(e["title"]), bn.MAX_TITLE)
        self.assertEqual(e["tags"][0], "word play")
        self.assertEqual(len(e["tags"]), 4)
        self.assertEqual(len(e["tags"][1]), bn.MAX_TAG_LEN)
        self.assertEqual(len(e["note"]), bn.MAX_NOTE)
        self.assertEqual(len(e["hebrew_rendering"]), bn.MAX_RENDERING)
        self.assertEqual(len(e["match_terms"]), bn.MAX_MATCH_TERMS)
        self.assertEqual(len(nb["chapter_summaries"]["2"]), bn.MAX_SUMMARY)
        self.assertEqual(len(nb["story_so_far"]), bn.MAX_STORY)
        for reported in ("story_so_far exceeded", "chapter_summary exceeded", "note longer than", "hebrew_rendering longer than"):
            self.assertTrue(any(reported in w for w in rep["warnings"]), reported)
        self.assertEqual(rep["added"], 1)

    def test_long_story_is_kept_whole_and_trimmed_not_dropped_in_excerpt(self):
        story = " ".join("thread%d" % i for i in range(1500))   # ~13k chars, like a real novel summary
        nb, _ = bn.apply_keeper_response(self.nb, resp([], story=story), 0)
        self.assertEqual(nb["story_so_far"], story)
        excerpt = bn.render_for_chapter(nb, "", token_budget=600, count_tokens=lambda t: len(t) // 4)
        self.assertIn("STORY_SO_FAR:", excerpt)
        self.assertIn("thread0 ", excerpt)
        self.assertIn("thread1499", excerpt)
        self.assertIn("omitted for length", excerpt)
        self.assertLessEqual(len(excerpt) // 4, 600)

    def test_deterministic_ids_stable_across_updates(self):
        a, _ = bn.apply_keeper_response(self.nb, resp([add("Mr. Darcy", ["name", "character"])]), 0)
        b, _ = bn.apply_keeper_response(bn.new_notebook("doc1"), resp([add("  mr.  DARCY ", ["Name"])]), 5)
        self.assertEqual(a["entries"][0]["entry_id"], b["entries"][0]["entry_id"])
        c, _ = bn.apply_keeper_response(bn.new_notebook("doc2"), resp([add("Mr. Darcy")]), 0)
        self.assertNotEqual(a["entries"][0]["entry_id"], c["entries"][0]["entry_id"])
        eid = a["entries"][0]["entry_id"]
        d, _ = bn.apply_keeper_response(
            a, resp([{"op": "update", "entry_id": eid, "tags": ["term"], "note": "new"}]), 1)
        self.assertEqual(d["entries"][0]["entry_id"], eid)

    def test_tolerant_parsing(self):
        body = resp([add("Fenced")])
        for raw in ("```json\n" + body + "\n```", "Sure! Here you go:\n" + body + "\nHope it helps {x}"):
            nb, rep = bn.apply_keeper_response(self.nb, raw, 0)
            self.assertEqual(rep["status"], "ok")
            self.assertEqual(len(nb["entries"]), 1)

    def test_garbage_unparsed(self):
        for raw in ("not json", "", None, "{broken", "[1,2]"):
            nb, rep = bn.apply_keeper_response(self.nb, raw, 0)
            self.assertEqual(rep["status"], "unparsed")
            self.assertTrue(rep["warnings"])
            self.assertEqual(nb["revision"], 0)
            self.assertEqual(nb, self.nb)

    def test_partial_bad_ops_skipped(self):
        ops = [add("Good"), "junk", {"op": "zap"}, {"op": "add", "title": "no tags"},
               {"op": "update", "entry_id": "missing"}, {"op": "supersede", "entry_id": "missing"}]
        nb, rep = bn.apply_keeper_response(self.nb, resp(ops), 0)
        self.assertEqual(rep["added"], 1)
        self.assertEqual(rep["skipped"], 5)
        self.assertGreaterEqual(len(rep["warnings"]), 5)
        bn.validate_notebook(nb)

    def test_update_supersede_dedupe(self):
        nb, _ = bn.apply_keeper_response(self.nb, resp([add("Ana", match_terms=["Ana"])]), 0)
        eid = nb["entries"][0]["entry_id"]
        nb, rep = bn.apply_keeper_response(nb, resp([
            {"op": "update", "entry_id": eid, "note": "changed", "hebrew_rendering": "אנה",
             "match_terms": ["Anna"]}]), 3)
        e = nb["entries"][0]
        self.assertEqual((rep["updated"], e["note"], e["last_chapter"], e["first_chapter"]), (1, "changed", 3, 0))
        self.assertEqual(e["match_terms"], ["Ana", "Anna"])
        nb, rep = bn.apply_keeper_response(nb, resp([add("ANA", note="dup")]), 4)
        self.assertEqual((len(nb["entries"]), rep["updated"], rep["added"]), (1, 1, 0))
        self.assertEqual(nb["entries"][0]["note"], "dup")
        nb, rep = bn.apply_keeper_response(nb, resp([{"op": "supersede", "entry_id": eid}]), 5)
        self.assertEqual((nb["entries"][0]["status"], rep["superseded"]), ("superseded", 1))
        nb, rep = bn.apply_keeper_response(nb, resp([add("Ana")]), 6)
        self.assertEqual((rep["updated"], rep["added"]), (1, 0))  # re-adding reactivates
        self.assertEqual(nb["entries"][0]["status"], "active")

    def test_pinned_and_human_protected(self):
        nb, _ = bn.apply_keeper_response(self.nb, resp([add("Pin"), add("Hum")]), 0)
        nb["entries"][0]["pinned"] = True
        nb["entries"][1]["origin"] = "human"
        ids = [e["entry_id"] for e in nb["entries"]]
        ops = [{"op": "update", "entry_id": i, "note": "hack"} for i in ids]
        ops += [{"op": "supersede", "entry_id": i} for i in ids] + [add("pin", note="dedupe hack")]
        out, rep = bn.apply_keeper_response(nb, resp(ops), 1)
        self.assertEqual(rep["skipped"], 5)
        self.assertEqual(out["entries"], nb["entries"])

    def test_input_not_mutated(self):
        nb, _ = bn.apply_keeper_response(self.nb, resp([add("A")]), 0)
        snap = copy.deepcopy(nb)
        eid = nb["entries"][0]["entry_id"]
        out, _ = bn.apply_keeper_response(nb, resp([
            {"op": "update", "entry_id": eid, "note": "z"}, add("B")]), 1)
        self.assertEqual(nb, snap)
        self.assertIsNot(out, nb)
        self.assertEqual(out["revision"], 2)

    def test_entry_cap(self):
        nb = bn.new_notebook("d")
        nb, _ = bn.apply_keeper_response(nb, resp([add("seed")]), 0)
        base = nb["entries"][0]
        nb["entries"] = [dict(base, entry_id="id%d" % i, title="t%d" % i) for i in range(bn.MAX_ENTRIES)]
        out, rep = bn.apply_keeper_response(nb, resp([add("overflow")]), 1)
        self.assertEqual(len(out["entries"]), bn.MAX_ENTRIES)
        self.assertEqual(rep["skipped"], 1)
        self.assertTrue(any("full" in w for w in rep["warnings"]))

    def test_history_bounded(self):
        nb = self.nb
        for i in range(bn.MAX_HISTORY + 15):
            nb, _ = bn.apply_keeper_response(nb, resp(), i)
        self.assertEqual(len(nb["history"]), bn.MAX_HISTORY)
        self.assertEqual(nb["history"][-1]["revision"], bn.MAX_HISTORY + 15)

    def _book(self):
        ops = [
            add("Pinned rule", ["style"], scope="local", match_terms=["zzz"]),
            add("Global voice", ["register"], scope="global"),
            add("Matching Harry", ["name"], match_terms=["Harry"]),
            add("Recent thing", ["motif"], match_terms=["qqq"]),
            add("Old thing", ["motif"], match_terms=["old"]),
        ]
        nb, _ = bn.apply_keeper_response(self.nb, resp(ops, summary="sum0", story="story0"), 0)
        nb["entries"][0]["pinned"] = True
        nb["entries"][3]["last_chapter"] = 9
        nb["entries"][4]["last_chapter"] = 1
        nb["chapter_summaries"]["10"] = "prev chapter ten"
        return nb

    def test_retrieval_priority(self):
        nb = self._book()
        text = bn.render_for_chapter(nb, "Then Harry arrived.", count_tokens=lambda t: len(t))
        self.assertIn("BOOK_NOTEBOOK", text)
        self.assertIn("STORY_SO_FAR:\nstory0", text)
        self.assertIn("PREVIOUS_CHAPTER_SUMMARY:\nprev chapter ten", text)
        order = [text.index(t) for t in ("Pinned rule", "Global voice", "Matching Harry", "Recent thing")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("Old thing", text)
        self.assertNotIn("Matching Harry", bn.render_for_chapter(nb, "Harrypotter nothing", count_tokens=len))
        self.assertEqual(text, bn.render_for_chapter(nb, "Then Harry arrived.", count_tokens=lambda t: len(t)))

    def test_budget_truncates_lowest_priority_first(self):
        nb = self._book()
        full = bn.render_for_chapter(nb, "Harry", count_tokens=len)
        self.assertIn("Recent thing", full)
        budget = len(full) - 5
        cut = bn.render_for_chapter(nb, "Harry", token_budget=budget, count_tokens=len)
        self.assertLessEqual(len(cut), budget)
        self.assertNotIn("Recent thing", cut)
        self.assertIn("Pinned rule", cut)
        tiny = bn.render_for_chapter(nb, "Harry", token_budget=10, count_tokens=len)
        self.assertNotIn("Pinned rule", tiny)

    def test_default_counter_budget(self):
        nb = self._book()
        text = bn.render_for_chapter(nb, "Harry", token_budget=200)
        from scholarly_translation.token_counting import count_tokens
        self.assertLessEqual(count_tokens(text)["upper_bound"], 200)

    def test_cjk_substring(self):
        nb, _ = bn.apply_keeper_response(self.nb, resp([add("Lin", match_terms=["林冲"])]), 0)
        nb["chapter_summaries"] = {}
        text = bn.render_for_chapter(nb, "那天林冲走进了酒店。", count_tokens=len)
        self.assertIn("Lin", text)
        self.assertNotIn("Lin ", bn.render_for_chapter(nb, "无关的文字。", count_tokens=len))

    def test_markdown(self):
        nb = self._book()
        md = bn.render_markdown(nb)
        self.assertIn("# Book notebook", md)
        self.assertIn("## register", md)
        self.assertIn("(pinned)", md)
        self.assertLess(md.index("### Chapter 0"), md.index("### Chapter 10"))
        e = nb["entries"][2]
        e["hebrew_rendering"] = "הארי"
        self.assertIn("Hebrew: הארי", bn.render_markdown(nb))

    def test_prompt_build(self):
        p = bn.build_keeper_prompt("EXCERPT", "SRC TEXT", "עברית", 3, "literary")
        for s in ("EXCERPT", "SRC TEXT", "עברית", "literary", "wordplay"):
            self.assertIn(s, p)
        self.assertNotIn("{{", p)
        self.assertIn('"ops"', p)

    def test_performance(self):
        nb = bn.new_notebook("big")
        base = bn.apply_keeper_response(nb, resp([add("seed")]), 0)[0]["entries"][0]
        nb["entries"] = [dict(base, entry_id="i%d" % i, title="Title %d" % i, scope="local",
                              match_terms=["term%d" % i, "alt%d" % i], last_chapter=i % 50)
                         for i in range(3000)]
        nb["chapter_summaries"] = {str(i): "s" for i in range(50)}
        src = " ".join("term%d" % i for i in range(0, 3000, 7)) * 3
        t = time.time()
        text = bn.render_for_chapter(nb, src, token_budget=6000, count_tokens=lambda s: len(s) // 3)
        self.assertLess(time.time() - t, 5.0)
        self.assertIn("Title 0", text)
        t = time.time()
        for i in range(50):
            nb, _ = bn.apply_keeper_response(nb, resp([add("n%d" % i)]), i)
        self.assertLess(time.time() - t, 20.0)


if __name__ == "__main__":
    unittest.main()
