"""LIT-NOTEBOOK component D: mandatory budget, sharper literary prompts, literary risk triggers."""
import math
import tempfile
import unittest
from pathlib import Path

from scholarly_translation import review_qa, semantic_review
from scholarly_translation.document_draft import (
    DocumentDraftError, DocumentJobs, MAX_BUDGET_USD, validate_settings,
)
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.translation_profiles import PROMPT_VERSIONS, style_profile_text

from test_document_draft import MOCK_MODEL_CONFIG

PASS_TEXT = "VERDICT: PASS\n\nISSUES: none\n\nCHAPTER_LEVEL_NOTES:\nnone\n\nSTATE_UPDATES:\nnone\n"
SOURCE = "Chapter one begins here. Chapter one ends here."
HEBREW = "הפרק הראשון מתחיל כאן. הפרק הראשון מסתיים כאן."


def _configured(**extra):
    settings = {"model": "configured", "model_config": MOCK_MODEL_CONFIG}
    settings.update(extra)
    return settings


class MandatoryBudgetTests(unittest.TestCase):
    def test_no_code_ceiling_constant(self):
        self.assertIsNone(MAX_BUDGET_USD)

    def test_configured_requires_budget(self):
        with self.assertRaises(DocumentDraftError) as ctx:
            validate_settings(_configured())
        self.assertIn("תקציב מרבי", str(ctx.exception))

    def test_every_invalid_budget_form_rejected_for_configured(self):
        for bad in (None, "", 0, 0.0, -1, -0.5, math.nan, math.inf, -math.inf, True, False, "5", "abc", [5]):
            with self.subTest(budget=bad):
                with self.assertRaises(DocumentDraftError):
                    validate_settings(_configured(budget_usd=bad))

    def test_no_upper_bound(self):
        for good in (0.001, 2, 30, 31, 500, 1e6):
            with self.subTest(budget=good):
                self.assertEqual(validate_settings(_configured(budget_usd=good))["budget_usd"], float(good))

    def test_auto_works_without_budget_but_given_budget_must_be_valid(self):
        settings = validate_settings({})
        self.assertEqual(settings["model"], "auto")
        validate_settings({"budget_usd": 500})
        for bad in (0, -1, math.nan, True, "5", ""):
            with self.subTest(budget=bad):
                with self.assertRaises(DocumentDraftError):
                    validate_settings({"budget_usd": bad})

    def test_preview_and_start_require_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = DocumentJobs(Path(tmp))
            with self.assertRaises(DocumentDraftError) as ctx:
                jobs.preview(Path(tmp) / "missing.pdf", _configured())
            self.assertIn("תקציב מרבי", str(ctx.exception))
            with self.assertRaises(DocumentDraftError) as ctx:
                jobs.start(Path(tmp) / "missing.pdf", _configured(), paid_confirm=True)
            self.assertIn("תקציב מרבי", str(ctx.exception))

    def test_ui_has_no_default_or_ceiling(self):
        root = Path(__file__).resolve().parent.parent / "scholarly_translation"
        html = (root / "ui.html").read_text(encoding="utf-8")
        js = (root / "ui.js").read_text(encoding="utf-8")
        field = html[html.index('id="budget"'):]
        field = field[:field.index(">")]
        self.assertIn("required", field)
        self.assertNotIn('value="2"', field)
        self.assertNotIn("max=", field)
        self.assertNotIn("budget_usd:2,", js)
        self.assertNotIn("$30", js)


class PromptRenderTests(unittest.TestCase):
    def _prompt(self, **kwargs):
        captured = {}

        def generate(prompt_text, model):
            captured["prompt"] = prompt_text
            return TextGenerationResult(status="mock_placeholder", text=PASS_TEXT, token_usage="not_metered",
                                        observed_model=model, duration_seconds=0.001)
        request = review_qa.build_chapter_qa_request(SOURCE, HEBREW, policy="on", **kwargs)
        review_qa.run_chapter_qa(request, generate)
        return captured["prompt"]

    def test_chapter_qa_renders_without_notebook(self):
        prompt = self._prompt()
        self.assertIn("BOOK_NOTEBOOK:\n(none)", prompt)
        self.assertNotIn("{{", prompt)

    def test_chapter_qa_renders_with_notebook(self):
        prompt = self._prompt(book_notebook="NAME: Anna -> אנה")
        self.assertIn("BOOK_NOTEBOOK:\nNAME: Anna -> אנה", prompt)
        self.assertNotIn("{{", prompt)

    def test_legacy_render_without_placeholder_value_is_empty_marker(self):
        text = review_qa._render(review_qa.CHAPTER_QA_PROMPT_ID, {
            "source_chapter": "s", "hebrew_chapter": "h", "profile": "p", "glossary_and_decisions": "g"})
        self.assertNotIn("{{", text)
        self.assertIn("BOOK_NOTEBOOK:\n(none)", text)

    def test_notebook_changes_input_hash_only_when_present(self):
        def hashed(**kw):
            request = review_qa.build_chapter_qa_request(SOURCE, HEBREW, policy="off", **kw)
            return review_qa.run_chapter_qa(request)["input_hash"]
        self.assertEqual(hashed(), hashed(book_notebook=""))
        self.assertNotEqual(hashed(), hashed(book_notebook="x"))

    def test_notebook_must_be_string(self):
        with self.assertRaises(review_qa.ReviewQARequestError):
            review_qa.build_chapter_qa_request(SOURCE, HEBREW, policy="on", book_notebook=5)

    def test_prompt_texts_mention_new_checks(self):
        root = Path(__file__).resolve().parent.parent / "scholarly_translation" / "runtime_prompts"
        qa = (root / "06_chapter_level_qa.md").read_text(encoding="utf-8")
        for needle in ("{{book_notebook}}", "BOOK_NOTEBOOK", "translationese", "dialogue punctuation", "contradicts"):
            self.assertIn(needle, qa)
        review = (root / "04_independent_semantic_review.md").read_text(encoding="utf-8")
        self.assertIn("wordplay", review)
        self.assertIn("voice", review)

    def test_literary_style_guidance_and_version_bump(self):
        self.assertEqual(PROMPT_VERSIONS["literary"], "literary-prompts-v2@2")
        self.assertEqual(PROMPT_VERSIONS["scholarly"], "scholarly-prompts-v2@2")
        literary = style_profile_text("literary")
        self.assertIn("literary-prompts-v2@2", literary)
        for needle in ("BOOK_NOTEBOOK", "translation_note", "translationese", "dialogue punctuation"):
            self.assertIn(needle, literary)
        self.assertNotIn("BOOK_NOTEBOOK", style_profile_text("scholarly"))


class LiteraryTriggerTests(unittest.TestCase):
    DIALOGUE = {"text": 'He said, "Come here, my friend." Why did she leave? It was a "pun" indeed!'}
    PROSE = {"text": "The author develops a theory of institutional design across several chapters."}

    def _types(self, unit, profile):
        return {t["type"] for t in semantic_review.detect_risk_triggers(unit, "en", [], None, profile=profile)}

    def test_literary_triggers_fire_on_dialogue_and_markers(self):
        types = self._types(self.DIALOGUE, "literary")
        self.assertEqual(types, {"literary_dialogue", "literary_exclamation_question", "literary_wordplay_marker"})

    def test_deterministic(self):
        first = semantic_review.detect_risk_triggers(self.DIALOGUE, "en", [], None, profile="literary")
        second = semantic_review.detect_risk_triggers(self.DIALOGUE, "en", [], None, profile="literary")
        self.assertEqual(first, second)

    def test_plain_prose_has_no_literary_triggers(self):
        self.assertEqual(self._types(self.PROSE, "literary"), set())

    def test_scholarly_and_default_unchanged(self):
        self.assertEqual(self._types(self.DIALOGUE, "scholarly"), set())
        self.assertEqual(self._types(self.DIALOGUE, None), set())

    def test_literary_types_are_not_human_review_required(self):
        from scholarly_translation.human_review import REVIEW_REQUIRED_TRIGGER_TYPES
        self.assertFalse(semantic_review.LITERARY_TRIGGER_TYPES & REVIEW_REQUIRED_TRIGGER_TYPES)
        self.assertTrue(semantic_review.LITERARY_TRIGGER_TYPES <= semantic_review.ALL_CRITIC_TRIGGER_TYPES)

    def test_bounded(self):
        unit = {"text": " ".join('"a b"' for _ in range(100))}
        triggers = semantic_review.detect_risk_triggers(unit, "en", [], None, profile="literary")
        self.assertLessEqual(len(triggers), semantic_review.MAX_LITERARY_TRIGGERS_PER_TYPE)


if __name__ == "__main__":
    unittest.main()
