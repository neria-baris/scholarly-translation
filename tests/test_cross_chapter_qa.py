import unittest
from types import SimpleNamespace

from scholarly_translation import cross_chapter_qa as cq

SRC = "Shae walked home. Shae slept."
HEB = "שיי הלכה הביתה. שֵׁאי ישנה. לוון בא."


def issue_block(cat="consistency", sev="MAJOR", span="שיי", corr="שֵׁאי", n=1):
    return f"{n}. Category: {cat}\n   Severity: {sev}\n   Span: {span}\n   Correction: {corr}\n"


def reply(issues, verdict="REVISE", notes="ok"):
    return f"VERDICT: {verdict}\n\nISSUES:\n{issues}\nNOTES:\n{notes}\n"


class WindowTests(unittest.TestCase):
    def test_table(self):
        self.assertEqual(cq.windows(64), [(0, 7), (7, 14), (14, 21), (21, 28), (28, 35),
                                          (35, 42), (42, 49), (49, 56), (56, 63)])
        self.assertEqual(cq.windows(9), [(0, 7), (7, 8)])
        self.assertEqual(cq.windows(8), [(0, 7)])
        self.assertEqual(cq.windows(5), [(0, 4)])
        self.assertEqual(cq.windows(2), [(0, 1)])
        self.assertEqual(cq.windows(1), [])
        self.assertEqual(cq.windows(0), [])

    def test_key(self):
        self.assertEqual(cq.window_key((7, 14)), "7-14")


class PromptTests(unittest.TestCase):
    chapters = [{"index": 0, "source": "S1", "hebrew": "H1"},
                {"index": 7, "source": "S8 {{NAMES}}", "hebrew": "H8"}]

    def test_headers_and_none(self):
        text = cq.build_cross_qa_prompt(self.chapters, "", "  ", "scholarly")
        self.assertIn("=== CHAPTER 1 — SOURCE ===\nS1\n=== CHAPTER 1 — HEBREW ===\nH1", text)
        self.assertIn("=== CHAPTER 8 — SOURCE ===", text)
        self.assertIn("NAMES:\n(none)", text)
        self.assertIn("BOOK_NOTEBOOK:\n(none)", text)
        self.assertIn("PROFILE:\nscholarly", text)
        self.assertIn("S8 {{NAMES}}", text)
        self.assertIn("STRUCTURED_OUTPUT_CONTRACT", text)
        self.assertNotIn("STATE_UPDATES", text)

    def test_names_given(self):
        text = cq.build_cross_qa_prompt(self.chapters, "NAMES line", "nb", "")
        self.assertIn("NAMES:\nNAMES line", text)
        self.assertIn("BOOK_NOTEBOOK:\nnb", text)


class ParseTests(unittest.TestCase):
    def parse(self, raw):
        return cq.parse_cross_qa_response(raw, SRC, HEB)

    def test_positive(self):
        r = self.parse(reply(issue_block()))
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["issues"], [{"category": "consistency", "severity": "MAJOR",
                                        "span": "שיי", "correction": "שֵׁאי"}])
        self.assertIsNone(r["error"])
        self.assertEqual(r["notes"], "ok")

    def test_pass_none(self):
        r = self.parse(reply("none\n", verdict="PASS"))
        self.assertEqual((r["status"], r["issues"]), ("completed", []))

    def test_quoted_span_grounded(self):
        r = self.parse(reply(issue_block(span='"שיי"')))
        self.assertEqual(r["issues"][0]["span"], "שיי")

    def test_drop_rules(self):
        good = issue_block(span="לוון", corr="ון", n=2)
        for bad in (issue_block(cat="completeness"), issue_block(sev="HUGE"),
                    issue_block(span="לא קיים"), issue_block(corr=""),
                    issue_block(corr='"שיי"'), issue_block() + "stray comment\n"):
            r = self.parse(reply(good.replace("2.", "1.") + bad.replace("1.", "2.", 1)))
            self.assertEqual(r["status"], "completed", bad)
            self.assertEqual(r["dropped_issues"], 1, bad)
            self.assertEqual([i["span"] for i in r["issues"]], ["לוון"], bad)

    def test_needs_human(self):
        self.assertEqual(self.parse("")["status"], "needs_human")
        self.assertEqual(self.parse("ISSUES:\nnone\nNOTES:\n")["status"], "needs_human")
        self.assertEqual(self.parse("VERDICT: MAYBE\nISSUES:\nnone\nNOTES:\n")["status"], "needs_human")
        self.assertEqual(self.parse("VERDICT: PASS\nISSUES:\nnone\n")["status"], "needs_human")
        self.assertEqual(self.parse(reply("garbage\n"))["status"], "needs_human")
        r = self.parse(reply(issue_block(), verdict="PASS"))
        self.assertEqual(r["status"], "needs_human")
        self.assertEqual(r["issues"], [])
        self.assertEqual(self.parse(reply("none\n"))["status"], "needs_human")
        r = self.parse(reply(issue_block(span="לא קיים")))
        self.assertEqual(r["status"], "needs_human")
        self.assertEqual(r["dropped_issues"], 1)


def rec(uid, src="", tgt=""):
    return {"unit_id": uid, "source_text": src, "target_text": tgt}


class LocateTests(unittest.TestCase):
    def issue(self, span, cat="consistency"):
        return {"category": cat, "severity": "MAJOR", "span": span, "correction": "x"}

    def test_single(self):
        recs = [rec("a", tgt="שיי"), rec("b", tgt="אחר")]
        self.assertEqual(cq.locate_issue_units(self.issue("שיי"), recs), ([recs[0]], "ok"))

    def test_multi_short_consistency(self):
        recs = [rec("a", tgt="שיי"), rec("b", tgt="שיי הלכה"), rec("c", tgt="x")]
        self.assertEqual(cq.locate_issue_units(self.issue("שיי"), recs), (recs[:2], "ok"))

    def test_too_many(self):
        recs = [rec(str(i), tgt="שיי") for i in range(5)]
        self.assertEqual(cq.locate_issue_units(self.issue("שיי"), recs, max_units=4), ([], "too_many"))

    def test_long_span_ambiguous(self):
        span = "א" * 41
        recs = [rec("a", tgt=span), rec("b", tgt=span)]
        self.assertEqual(cq.locate_issue_units(self.issue(span), recs), ([], "ambiguous"))

    def test_continuity_multi_ambiguous(self):
        recs = [rec("a", tgt="שיי"), rec("b", tgt="שיי")]
        self.assertEqual(cq.locate_issue_units(self.issue("שיי", "continuity"), recs), ([], "ambiguous"))

    def test_source_only(self):
        recs = [rec("a", src="Shae ran"), rec("b", src="other")]
        self.assertEqual(cq.locate_issue_units(self.issue("Shae"), recs), ([recs[0]], "ok"))
        recs = [rec("a", src="Shae ran"), rec("b", src="Shae sat")]
        self.assertEqual(cq.locate_issue_units(self.issue("Shae"), recs), ([], "ambiguous"))

    def test_not_found(self):
        self.assertEqual(cq.locate_issue_units(self.issue("zzz"), [rec("a", "x", "y")]), ([], "not_found"))
        self.assertEqual(cq.locate_issue_units(self.issue("zzz"), []), ([], "not_found"))


class CapTests(unittest.TestCase):
    def sel(self, v):
        return SimpleNamespace(capabilities=SimpleNamespace(max_output_tokens=v))

    def test_cap(self):
        self.assertEqual(cq.cross_qa_output_cap(self.sel(None)), 8192)
        self.assertEqual(cq.cross_qa_output_cap(self.sel(4000)), 4000)
        self.assertEqual(cq.cross_qa_output_cap(self.sel(64000)), 8192)
        self.assertEqual(cq.cross_qa_output_cap(SimpleNamespace(capabilities=None)), 8192)


class NiqqudFilterTests(unittest.TestCase):
    """EXPORT-NIQQUD: a correction that only adds niqqud is not an inconsistency."""

    HEB = "מדריך כל אדם למגדל בבל. אָדָם הלך."

    def parse(self, raw):
        return cq.parse_cross_qa_response(raw, "Everyman's Guide. Adam went.", self.HEB)

    def test_adding_niqqud_dropped(self):
        good = issue_block(span="מדריך כל אדם", corr="מדריך כל איש", n=2)
        bad = issue_block(span="אדם למגדל בבל", corr="אָדָם לְמִגְדַּל בָּבֶל")
        r = self.parse(reply(bad + good))
        self.assertEqual(r["status"], "completed")
        self.assertEqual([i["correction"] for i in r["issues"]], ["מדריך כל איש"])
        self.assertEqual(r["dropped_issues"], 1)

    def test_only_niqqud_issue_needs_no_revision(self):
        r = self.parse(reply(issue_block(span="אדם למגדל", corr="אָדָם לְמִגְדַּל")))
        self.assertEqual(r["status"], "needs_human")
        self.assertEqual(r["dropped_issues"], 1)

    def test_removing_niqqud_kept(self):
        r = self.parse(reply(issue_block(span="אָדָם", corr="אדם")))
        self.assertEqual(r["issues"][0]["correction"], "אדם")

    def test_prompt_says_prose_is_unvocalized(self):
        prompt = cq.build_cross_qa_prompt([{"index": 0, "source": "a", "hebrew": "ב"}], "", "", "literary")
        self.assertIn("written without niqqud", prompt)


if __name__ == "__main__":
    unittest.main()
