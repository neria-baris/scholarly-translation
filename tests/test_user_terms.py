"""USER-TERMS: the personal glossary, binding user terms in the notebook and the name table,
and the deterministic check that a user term's rendering appears in the translation."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import book_notebook as bn
from scholarly_translation import chapter_pipeline as cp
from scholarly_translation import name_table as nt
from scholarly_translation import user_glossary as ug
from scholarly_translation import web_ui

TERM = {"source": "無尽蔵性", "forms": ["inexhaustibility"], "target": "אי-מיצוי",
        "target_language": "he", "note": "Gödel"}


class UserGlossaryTests(unittest.TestCase):
    def test_text_form_round_trip(self):
        terms = ug.parse_text("# my terms\n無尽蔵性 | inexhaustibility = אי-מיצוי  # Gödel\n\n本稿 = מאמר זה\n", "he")
        self.assertEqual(terms[0], TERM)
        self.assertEqual(terms[1]["forms"], [])
        self.assertEqual(ug.parse_text(ug.format_text(terms), "he"), terms)

    def test_invalid_lines_name_their_line(self):
        with self.assertRaisesRegex(ug.UserGlossaryError, "^שורה 2"):
            ug.parse_text("本稿 = מאמר זה\nno equals sign here", "he")
        with self.assertRaises(ug.UserGlossaryError):
            ug.parse_text("本稿 = ", "he")
        with self.assertRaises(ug.UserGlossaryError):
            ug.parse_text("本稿 = " + "א" * (ug.MAX_TARGET + 1), "he")

    def test_later_duplicate_wins_and_targets_stay_apart(self):
        terms = ug.normalize([dict(TERM, target="אי התכלות"), TERM, dict(TERM, target_language="en", target="x")])
        self.assertEqual([(t["target_language"], t["target"]) for t in terms], [("he", "אי-מיצוי"), ("en", "x")])
        self.assertEqual(ug.for_target(terms, "en"), [terms[1]])

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "user_glossary.json"
            self.assertEqual(ug.load(path), [])
            ug.save(path, [TERM])
            self.assertEqual(ug.load(path), [TERM])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], ug.SCHEMA)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ug.UserGlossaryError):
                ug.load(path)

    def test_applicable_matches_cjk_substrings_and_latin_words(self):
        self.assertEqual(ug.applicable([TERM], "ゲーデルの数学の無尽蔵性のテーゼ"), [TERM])
        self.assertEqual(ug.applicable([TERM], "the Inexhaustibility thesis"), [TERM])
        self.assertEqual(ug.applicable([TERM], "inexhaustibilityness"), [])


class NotebookTests(unittest.TestCase):
    def _notebook(self):
        nb = bn.new_notebook("doc")
        nb, _ = bn.add_voice_entries(nb, {"register": "", "key_words": [
            {"source": "数学の無尽蔵性", "forms": ["無尽蔵性", "不完全性"], "hebrew": "אי התכלות", "note": ""},
            {"source": "本稿", "forms": [], "hebrew": "מאמר זה", "note": ""}]})
        return bn.add_user_terms(nb, [TERM])[0]

    def test_user_term_is_binding_human_and_shadows_the_model_choice(self):
        nb = self._notebook()
        bn.validate_notebook(nb)
        self.assertEqual(bn.user_terms(nb), [(["無尽蔵性", "inexhaustibility"], "אי-מיצוי")])
        excerpt = bn.render_for_chapter(nb, "数学の無尽蔵性と本稿", 4000, len)
        self.assertIn("BINDING", excerpt)
        self.assertIn("אי-מיצוי", excerpt)
        self.assertNotIn("אי התכלות", excerpt)          # the model entry shares 無尽蔵性
        self.assertIn("מאמר זה", excerpt)                # unrelated model entries stay
        self.assertIn("overridden by a user term", bn.render_markdown(nb))

    def test_keeper_cannot_change_a_user_term(self):
        nb = self._notebook()
        entry = next(e for e in nb["entries"] if e["origin"] == "human")
        raw = json.dumps({"ops": [{"op": "update", "entry_id": entry["entry_id"], "hebrew_rendering": "אי התכלות"}],
                          "chapter_summary": "", "story_so_far": ""})
        after, _ = bn.apply_keeper_response(nb, raw, 1)
        self.assertEqual(bn.user_terms(after), bn.user_terms(nb))


class PipelineTests(unittest.TestCase):
    def _job(self, terms):
        return {"user_terms": terms, "book_notebook": bn.new_notebook("doc"), "name_table": nt.new_table()}

    def test_seed_enters_notebook_and_name_table_first(self):
        job = self._job([TERM, dict(TERM, source="存在しない語", forms=[])])
        structure = {"units": [{"text": "ゲーデルの「数学の無尽蔵性」のテーゼ"}]}
        cp._seed_user_terms(job, structure)
        self.assertEqual(job["user_terms_applied"], ["無尽蔵性"])
        self.assertEqual(len(bn.user_terms(job["book_notebook"])), 1)
        self.assertEqual([(e["source"], e["hebrew"], e["origin"]) for e in job["name_table"]["entries"]],
                         [("無尽蔵性", "אי-מיצוי", "human")])
        # The source pass proposes the same term with another rendering: the add-only merge drops it.
        merged, report = nt.merge_names(job["name_table"], [{"source": "数学の無尽蔵性", "aliases": ["無尽蔵性"],
                                                             "hebrew": "אי התכלות", "kind": "term"}], 0, "prepass")
        self.assertEqual(len(merged["entries"]), 1)
        self.assertEqual(report["added"], [])

    def test_no_terms_changes_nothing(self):
        job = self._job([])
        cp._seed_user_terms(job, {"units": [{"text": "x"}]})
        self.assertEqual(job["book_notebook"]["entries"], [])
        self.assertNotIn("user_terms_applied", job)

    def test_term_missing_finding_for_a_user_term(self):
        job = self._job([TERM])
        source = "数学の無尽蔵性のテーゼに着目する。"
        cp._seed_user_terms(job, {"units": [{"text": source}]})
        kinds = lambda target: [f["type"] for f in cp._unit_findings(source, target, "ja", job=job)]
        self.assertIn("term_missing", kinds("נתמקד בתזה בדבר אי התכלות המתמטיקה."))
        self.assertNotIn("term_missing", kinds("נתמקד בתזה בדבר אי־מיצוי המתמטיקה."))
        self.assertNotIn("term_missing", kinds("נתמקד בתזה בדבר האי מיצוי של המתמטיקה."))


class GlossaryHTTPTests(unittest.TestCase):
    def setUp(self):
        from http.server import ThreadingHTTPServer
        import threading
        self.temp = tempfile.TemporaryDirectory()
        self.output_patch = patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        self.output_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_ui.make_handler("test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.output_patch.stop()
        self.temp.cleanup()

    def post(self, route, payload):
        request = Request(self.url + route, data=json.dumps(payload).encode("utf-8"), method="POST",
                          headers={"Content-Type": "application/json", "X-UI-Token": "test-token", "Origin": self.url})
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def test_save_load_and_job_snapshot(self):
        self.assertEqual(self.post("/user-glossary", {"target_language": "he"}), {"text": "", "count": 0})
        saved = self.post("/user-glossary-save", {"target_language": "he", "text": "無尽蔵性 | inexhaustibility = אי-מיצוי # Gödel"})
        self.assertEqual(saved["count"], 1)
        self.assertEqual(self.post("/user-glossary", {"target_language": "en"})["count"], 0)
        with self.assertRaises(HTTPError) as caught:
            self.post("/user-glossary-save", {"target_language": "he", "text": "no equals"})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.post("/user-glossary", {"target_language": "he"})["count"], 1)   # unchanged
        sample = self.post("/document-sample", {})
        request = Request(self.url + "/upload?name=uploaded.pdf", data=Path(sample["path"]).read_bytes(),
                          headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
        with urlopen(request) as response:
            uploaded = json.load(response)
        started = self.post("/document-translate", {"path": uploaded["path"],
                            "settings": {"model": "auto", "quality": "fast", "language": "en", "budget_usd": 2}})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = self.post("/document-job", started)
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(.02)
        self.assertEqual([t["target"] for t in job["user_terms"]], ["אי-מיצוי"])


if __name__ == "__main__":
    unittest.main()
