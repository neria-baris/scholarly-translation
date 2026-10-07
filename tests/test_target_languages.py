"""TARGET-LANGUAGES (audit/contracts/target_languages.md): packs, localized prompts, validators,
deterministic output checks, settings, exports and a full mock run into English. Offline only."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation import (book_notebook as bn, chapter_pipeline as pipeline, cross_chapter_qa as cq,
                                   document_draft as dd, name_table as nt, output_checks as oc, review_qa as rq,
                                   target_languages as tl, translation_profiles as tp)
from scholarly_translation.formal_checks import run_formal_checks
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore

from tests.test_lit_notebook_integration import config_dict
from tests.test_long_docs_input import XHTML, build_epub

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "scholarly_translation" / "runtime_prompts"
HEBREW_LETTER = re.compile("[֐-׿]")


def all_prompt_texts():
    """Every model-facing prompt template and prompt constant, localized for the active pack."""
    texts = {}
    for profile in ("literary", "scholarly"):
        texts["style:" + profile] = tp.style_profile_text(profile)
        texts["gate7:" + profile] = tp.render_prompt(
            profile_id=profile, style_profile=tp.style_profile_text(profile), glossary_and_decisions="G",
            local_state="L", source_context="C", target_unit_text="T")
        texts["names:" + profile] = nt.build_source_pass_prompt(
            [{"index": 0, "source": "Senlin went up."}], "", [], profile, "fr", True)
        texts["keeper:" + profile] = bn.build_keeper_prompt("EX", "SRC", "TGT", 2, profile, 900, "NAMES")
        texts["cross:" + profile] = cq.build_cross_qa_prompt(
            [{"index": 0, "source": "S0", "hebrew": "H0"}, {"index": 1, "source": "S1", "hebrew": "H1"}],
            "N", "NB", profile, 0)
        texts["qa:" + profile] = rq._render(rq.CHAPTER_QA_PROMPT_ID, {
            "source_chapter": "S", "hebrew_chapter": "H", "profile": profile, "glossary_and_decisions": "G",
            "book_notebook": "NB"})
    texts["unit"] = rq._render(rq.UNIT_REVIEW_PROMPT_ID, {
        "source_text": "S", "translation": "H", "source_context": "C", "glossary_and_decisions": "G"})
    texts["compare"] = rq._render(rq.CANDIDATE_COMPARISON_PROMPT_ID, {
        "source_context": "C", "source_text": "S", "glossary_and_decisions": "G", "candidates": "A"})
    texts["correction"] = pipeline._correction_prompt({"unit_id": "u", "source_text": "S", "target_text": "H"}, [])
    texts["head"] = pipeline._prefix_head("fr", "literary") + pipeline._batch_suffix(["u"], "CTX")
    texts["names_header"] = tl.localize(nt.HEADER)
    return texts


class PackTests(unittest.TestCase):
    def test_available_packs_hebrew_first(self):
        self.assertEqual(tl.available()[:1], ["he"])
        self.assertIn("en", tl.available())
        he, en = tl.load("he"), tl.load("en")
        self.assertTrue(he.rtl and he.hebrew_prefixes and he.niqqud)
        self.assertFalse(en.rtl or en.hebrew_prefixes or en.niqqud)
        self.assertEqual((he.html_lang, en.html_lang), ("he", "en"))
        self.assertTrue(he.has_script("שלום") and not he.has_script("hello"))
        self.assertTrue(en.has_script("hello") and not en.has_script("שלום"))

    def test_default_and_context(self):
        self.assertEqual(tl.current_code(), "he")
        with tl.use("en") as pack:
            self.assertEqual(pack.code, "en")
            self.assertEqual(tl.current().name, "English")
        self.assertEqual(tl.current_code(), "he")
        self.assertEqual(tl.settings_code({}), "he")
        self.assertEqual(tl.settings_code({"target_language": "en"}), "en")

    def test_unknown_pack_and_token_fail_loudly(self):
        for bad in ("xx", "../he", "", None, "HE"):
            with self.subTest(code=bad), self.assertRaises(tl.TargetLanguageError):
                tl.load(bad)
        with self.assertRaises(tl.TargetLanguageError):
            tl.localize("a {{T:NO_SUCH_KEY}} b")

    def test_empty_fragment_removes_its_line(self):
        with tl.use("en"):
            self.assertEqual(tl.localize("a\n{{T:NAMES_NIQQUD}}\nb\n"), "a\nb\n")
            self.assertEqual(tl.localize("x{{T:CROSS_SPAN_PREFIX}}y"), "xy")
        with tl.use("he"):
            self.assertIn("NIQQUD", tl.localize("a\n{{T:NAMES_NIQQUD}}\nb\n"))

    def test_every_template_token_exists_in_every_pack(self):
        tokens = set()
        for path in list(TEMPLATES.glob("*.md")) + [p for p in (ROOT / "scholarly_translation").glob("*.py")
                                                     if p.name != "target_languages.py"]:
            tokens |= set(re.findall(r"\{\{T:([A-Z0-9_]+)\}\}", path.read_text(encoding="utf-8")))
        self.assertGreater(len(tokens), 20)
        for code in tl.available():
            missing = sorted(tokens - set(tl.load(code).fragments))
            self.assertEqual(missing, [], code)


class LocalizedPromptTests(unittest.TestCase):
    def test_hebrew_prompts_keep_hebrew_rules(self):
        texts = all_prompt_texts()
        for key, text in texts.items():
            self.assertNotIn("{{T:", text, key)
        self.assertIn("Target language: he.", texts["head"])
        self.assertIn("ון + ל = לוון", texts["keeper:literary"])
        self.assertIn("NIQQUD:", texts["names:literary"])
        self.assertIn("<HEBREW_TRANSLATION>", texts["unit"])
        self.assertIn("HEBREW_CHAPTER:", texts["qa:literary"])
        self.assertIn("Correct ONLY the supplied Hebrew unit", texts["correction"])

    def test_english_prompts_have_no_hebrew_rules(self):
        with tl.use("en"):
            texts = all_prompt_texts()
        for key, text in texts.items():
            with self.subTest(prompt=key):
                self.assertNotIn("{{T:", text)
                self.assertNotIn("Hebrew", text)
                self.assertNotIn("HEBREW", text)
                self.assertNotIn("niqqud", text)
                self.assertIsNone(HEBREW_LETTER.search(text))
        self.assertIn("Target language: en.", texts["head"])
        self.assertIn("<ENGLISH_TRANSLATION>", texts["unit"])
        self.assertIn("ENGLISH_CHAPTER:", texts["qa:literary"])
        self.assertIn("— ENGLISH ===", texts["cross:literary"])
        self.assertIn("translation (nonempty English)", texts["head"])
        self.assertIn('"hebrew" (the field keeps its historical name)', texts["names:literary"])
        self.assertIn("hebrew_quality is the fixed name", texts["qa:literary"])
        # Output formats are unchanged.
        self.assertIn("VERDICT: PASS | REVISE", texts["unit"])
        self.assertIn('{"names":[', texts["names:scholarly"])
        self.assertIn('"hebrew_rendering"', texts["keeper:scholarly"])


class ValidatorTests(unittest.TestCase):
    SOURCE = "Le capitaine regardait la mer pendant que l'équipage dormait profondément."

    def _parse(self, translation):
        raw = json.dumps([{"unit_id": "u1", "translation": translation, "translation_note": None}],
                         ensure_ascii=False)
        return pipeline.parse_batch_translation_response(raw, ["u1"], {"u1": self.SOURCE})

    def test_english_target_accepts_english_and_rejects_hebrew_or_copies(self):
        with tl.use("en"):
            self.assertEqual(self._parse("The captain watched the sea.")["u1"]["translation"],
                             "The captain watched the sea.")
            with self.assertRaisesRegex(pipeline.ChapterPipelineError, "not in the target language"):
                self._parse("הקפטן הביט בים.")
            with self.assertRaisesRegex(pipeline.ChapterPipelineError, "repeats the source"):
                self._parse(self.SOURCE)
        with self.assertRaisesRegex(pipeline.ChapterPipelineError, "not Hebrew"):
            self._parse("The captain watched the sea.")

    def test_review_requests_and_formal_check_follow_the_pack(self):
        with tl.use("en"):
            rq.build_chapter_qa_request(self.SOURCE, "The captain watched the sea.", policy="on")
            with self.assertRaises(rq.ReviewQARequestError):
                rq.build_chapter_qa_request(self.SOURCE, "הקפטן הביט בים.", policy="on")
            types = {f["type"] for f in run_formal_checks(self.SOURCE, "הקפטן הביט בים.", "fr")}
            self.assertIn("missing_target_script", types)
        types = {f["type"] for f in run_formal_checks(self.SOURCE, "The captain.", "fr")}
        self.assertIn("missing_hebrew_script", types)

    def test_name_table_accepts_target_letters(self):
        entry = {"source": "Shae", "hebrew": "Shae", "kind": "character", "gender": "female"}
        with tl.use("en"):
            cleaned, reason = nt._clean_entry(entry, "prepass")
            self.assertIsNotNone(cleaned, reason)
        cleaned, reason = nt._clean_entry(entry, "prepass")
        self.assertIsNone(cleaned)


class OutputCheckTests(unittest.TestCase):
    HE = tl.load("he")
    EN = tl.load("en")
    SOURCE = ("Shae walked home along the harbour. The sea was quiet. Woon waited at the gate. "
              "They spoke about the clan until night fell.")
    GOOD = "שאי הלכה הביתה לאורך הנמל. הים היה שקט. ווּן חיכה בשער. הם דיברו על השבט עד שירד הלילה."

    def types(self, target, **kw):
        return [f["type"] for f in oc.run_output_checks(self.SOURCE, target, "en", pack=kw.pop("pack", self.HE), **kw)]

    def test_clean_translation_has_no_findings(self):
        names = [{"source": "Shae", "hebrew": "שֵׁאי", "kind": "character"},
                 {"source": "Woon", "hebrew": "וּן", "kind": "character"}]
        self.assertEqual(self.types(self.GOOD, names=names), [])

    def test_length_ratio(self):
        self.assertIn("length_ratio", self.types("שאי הלכה."))
        self.assertIn("length_ratio", self.types(self.GOOD * 4))
        self.assertNotIn("length_ratio", oc.run_output_checks("Short.", "קצר.", "en", pack=self.HE))

    def test_sentence_count(self):
        self.assertIn("sentence_count", self.types(self.GOOD.replace(".", ",")[:-1] + "."))

    def test_copied_source_run(self):
        copied = "שאי הלכה הביתה. " + "They spoke about the clan until night fell and slept."
        self.assertIn("copied_source_run", self.types(copied))
        cjk = oc.run_output_checks("彼は港に沿って家まで歩いた。海は静かだった。", "He walked home 彼は港に沿って家まで歩いた。",
                                   "ja", pack=self.EN)
        self.assertIn("copied_source_run", [f["type"] for f in cjk])

    def test_added_dash_is_a_note_only(self):
        found = oc.run_output_checks(self.SOURCE, self.GOOD.replace(". הים", " — הים"), "en", pack=self.HE)
        self.assertIn("added_dash", [f["type"] for f in found])
        self.assertEqual(pipeline._material_findings(found), [f for f in found if f["type"] != "added_dash"])

    def test_names_with_prefix_vav_and_niqqud(self):
        names = [{"source": "Shae", "hebrew": "שֵׁאי", "kind": "character"},
                 {"source": "Woon", "hebrew": "ון", "kind": "character"},
                 {"source": "clan", "hebrew": "שבט", "kind": "term"}]       # terms are not name-checked
        target = self.GOOD.replace("ווּן", "ולוון")                        # prefix + doubled vav
        self.assertEqual(self.types(target, names=names), [])
        missing = oc.run_output_checks(self.SOURCE, self.GOOD.replace("שאי", "שיי"), "en",
                                       names=names, pack=self.HE)
        self.assertEqual([(f["type"], f["source_token"]) for f in missing], [("name_form_missing", "Shae")])

    def test_english_names_and_terms(self):
        source = "Kaul Shae and the Green Bone clan met at dawn by the old harbour wall near the market."
        target = "Kaul Shae and the Green Bone clan met at dawn by the old harbour wall near the market square."
        names = [{"source": "Kaul Shae", "hebrew": "Kaul Shae", "kind": "character"}]
        terms = [{"source_term": "Green Bone", "target_term": "Green Bone"}]
        fr = oc.run_output_checks(source, target, "fr", names=names, terms=terms, pack=self.EN)
        self.assertNotIn("name_form_missing", [f["type"] for f in fr])
        wrong = oc.run_output_checks(source, target.replace("Green Bone", "jade"), "fr", terms=terms, pack=self.EN)
        self.assertIn("term_missing", [f["type"] for f in wrong])

    def test_findings_have_the_formal_shape(self):
        for finding in oc.run_output_checks(self.SOURCE, "שאי הלכה.", "en", pack=self.HE):
            self.assertTrue({"type", "source_token", "source_char_start", "source_char_end",
                             "target_evidence", "severity"} <= set(finding))

    def test_unit_findings_feed_the_review_trigger(self):
        record = {"source_text": self.SOURCE, "target_text": "שאי הלכה.", "source_language": "en",
                  "findings": pipeline._unit_findings(self.SOURCE, "שאי הלכה.", "en")}
        self.assertTrue(pipeline.detect_risk_triggers(record, "literary")["formal_check_failure"])


class SettingsAndExportTests(unittest.TestCase):
    def settings(self, **extra):
        base = {"model": "configured", "automation": True, "budget_usd": 5, "language": "fr",
                "model_config": config_dict()}
        base.update(extra)
        return base

    def test_english_target_needs_the_configured_model(self):
        self.assertEqual(dd.validate_settings(self.settings(target_language="en"))["target_language"], "en")
        self.assertNotIn("target_language", dd.validate_settings(self.settings()))   # Hebrew: unchanged shape
        with self.assertRaises(dd.DocumentDraftError):
            dd.validate_settings({"model": "auto", "target_language": "en"})
        with self.assertRaises(dd.DocumentDraftError):
            dd.validate_settings(self.settings(target_language="xx"))
        with self.assertRaises(dd.DocumentDraftError):
            dd.validate_settings(self.settings(target_language="en", language="en"))

    def test_detected_source_equal_to_target_is_rejected(self):
        with self.assertRaises(dd.DocumentDraftError):
            dd._check_source_differs(SimpleNamespace(language="en"), {"target_language": "en"})
        dd._check_source_differs(SimpleNamespace(language="en"), {})

    def test_epub_language_and_direction(self):
        from scholarly_translation import export_epub
        from xml.etree import ElementTree as ET
        root = ET.fromstring('<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>')
        with tl.use("en"):
            export_epub._set_rtl_attributes(root)
        self.assertEqual((root.get("dir"), root.get("lang")), ("ltr", "en"))
        export_epub._set_rtl_attributes(root)
        self.assertEqual((root.get("dir"), root.get("lang")), ("rtl", "he"))


def chapter(i):
    return ('<h1>Chapitre %d</h1><p>Shae marchait le long du port au chapitre %d. La mer était calme.</p>'
            '<p>Shae rencontra Woon à la porte et ils parlèrent du clan.</p>' % (i, i))


ENGLISH = "Shae walked home along the harbour, and the sea was quiet."


class EnglishRunTests(unittest.TestCase):
    """A whole book through the chapter pipeline with English as the target language."""

    @classmethod
    def setUpClass(cls):
        scratch = ROOT / "outputs"
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        book = Path(cls.temp.name) / "fr.epub"
        book.write_bytes(build_epub([("c%d.xhtml" % i, XHTML % chapter(i + 1)) for i in range(3)]))
        cls.structure = dd.extract_structure(book, "fr")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_mock_run_into_english(self):
        calls = []

        def make(role, descriptor):
            def generate(prompt, model):
                prompt = str(prompt)
                if "Correct ONLY the supplied English unit" in prompt:
                    payload = json.loads(prompt[prompt.index("{", prompt.index("Correct ONLY")):])
                    kind, text = "correct", json.dumps([{"unit_id": payload["unit_id"], "translation": ENGLISH,
                                                         "translation_note": None}])
                elif "Translate exactly these units" in prompt:
                    ids = json.loads(re.search(r"TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])", prompt).group(1))
                    kind, text = "translate", json.dumps([{"unit_id": uid, "translation": ENGLISH,
                                                          "translation_note": None} for uid in ids])
                elif "NAME TABLE of a book" in prompt:
                    kind, text = "names", json.dumps({"names": [
                        {"source": "Shae", "hebrew": "Shae", "kind": "character", "gender": "female"}]})
                elif "several consecutive chapters" in prompt:
                    kind, text = "cross", "VERDICT: PASS\nISSUES: none\nNOTES: none"
                elif "rolling NOTEBOOK for a book" in prompt:
                    kind, text = "keeper", json.dumps({"ops": [], "chapter_summary": "Shae walks.",
                                                       "story_so_far": "Shae walks home."})
                elif role == "chapter_qa":
                    kind, text = "qa", "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none"
                else:
                    kind, text = "review", "VERDICT: PASS\nISSUES: none"
                calls.append((kind, prompt))
                return TextGenerationResult("completed", text, {"input": 100, "output": 10}, model, 0)
            return SimpleNamespace(generate=generate)

        job = {"job_id": "en-job", "settings": {"quality": "thorough", "profile": "literary", "budget_usd": 30,
                                                "automation": True, "target_language": "en"},
               "units": [], "revision": 0, "chapter_qa_results": [], "completed_units": 0}
        folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        with tl.use("en"), ControlStore(folder / "controls.sqlite3") as store:
            pipeline.execute_document_chapters(job, self.structure, new_store(), self.structure["units"],
                                               ModelConfiguration.from_dict(config_dict()), store, folder,
                                               lambda _: None, make)
        kinds = {k for k, _ in calls}
        self.assertTrue({"names", "translate", "review", "qa", "keeper"} <= kinds, kinds)
        self.assertEqual(job["name_table"]["entries"][0]["hebrew"], "Shae")
        self.assertTrue(job["units"] and all(r["target_text"] == ENGLISH for r in job["units"]
                                             if not r.get("passthrough")))
        for kind, prompt in calls:
            with self.subTest(kind=kind):
                self.assertNotIn("Hebrew", prompt)
                self.assertIsNone(HEBREW_LETTER.search(prompt))
        translate = next(p for k, p in calls if k == "translate")
        self.assertIn("Target language: en.", translate)
        self.assertIn("NAMES (binding English forms", translate)


if __name__ == "__main__":
    unittest.main()
