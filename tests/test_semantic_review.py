import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.__main__ import cmd_semantic_review
from scholarly_translation.formal_checks import run_formal_checks
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.model_adapter import (
    OpenAIConfigurationError,
    OpenAITextGenerationAdapter,
    PRICING_VERSION,
    TextGenerationResult,
)
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.records import Document, Page
from scholarly_translation.segmentation import build_structure
from scholarly_translation.semantic_review import (
    SemanticReviewRequestError,
    build_semantic_review_request,
    run_semantic_review,
)
from scholarly_translation.source_reading import build_readings
from scholarly_translation.translation import TranslationBudget, build_translation_request


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _build_structure_for_lines(tmp_path, lines, language):
    pdf_path = tmp_path / "fixture.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 14)
    for i, line in enumerate(lines):
        c.drawString(72, height - 100 - i * 30, line)
    c.showPage()
    c.save()

    document = extract_pdf(pdf_path, language=language)
    page = document.pages[0]
    reading = build_readings(document)[0]
    candidate = next(cand for cand in reading["alternatives"] if cand["origin"] == "digital")
    decisions = {page.page_id: _human_decision(candidate)}
    return build_structure(document, decisions=decisions)


def _make_draft(structure, glossary, unit_id, draft_text, provider="mock", model="mock-translation-1"):
    request = build_translation_request(structure, glossary, unit_id, "scholarly", provider, model)
    findings = run_formal_checks(request.unit["text"], draft_text, request.source_language)
    draft = dict(request.to_metadata_dict())
    draft.update({
        "schema_version": 1, "stage": "translation-draft@1", "observed_model": model,
        "status": "needs_human" if findings else "draft_unapproved",
        "draft_text": draft_text, "token_usage": "not_metered", "pricing_version": PRICING_VERSION,
        "estimated_cost_usd": "not_metered", "budget_notices": [], "actual_charge": "not_metered",
        "duration_seconds": 0.001, "timestamp": "2026-01-01T00:00:00+00:00",
        "findings": findings, "error": None, "approved": False,
    })
    return draft


def make_usage(input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


class FakeResponses:
    def __init__(self, response=None, exc=None):
        self._response, self._exc = response, exc

    def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.responses = FakeResponses(response=response, exc=exc)


class SemanticReviewTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def _structure(self, lines, language="en"):
        return _build_structure_for_lines(Path(self.tmp.name), lines, language)


class RiskRoutingTests(SemanticReviewTestBase):
    def test_no_risk_is_not_triggered(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "not_triggered")
        self.assertEqual(review["risk_triggers"], [])
        self.assertFalse(review["approved"])

    def test_ocr_warning_bypasses_critic_to_human(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        structure["units"][0] = dict(structure["units"][0], warnings=list(structure["units"][0]["warnings"]) + ["low_confidence"])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "bypass_ocr_source_uncertainty")
        self.assertIsNone(review["critic"])
        self.assertFalse(review["approved"])


class CorrectionWorkflowTests(SemanticReviewTestBase):
    def test_negation_error_is_corrected_and_rechecked(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "corrected_unapproved")
        self.assertEqual(review["pdf_hash"], draft["pdf_hash"])
        self.assertEqual(review["page_id"], unit["page_id"])
        self.assertEqual(review["source_char_start"], unit["source_char_start"])
        self.assertEqual(review["review_disposition"], "corrected")
        self.assertEqual(len(review["claims"]), 1)
        self.assertEqual(review["claims"][0]["trigger_type"], "negation")
        self.assertIn("לא", review["correction"]["candidate_text"])
        self.assertFalse(review["approved"])
        self.assertEqual(review["after_findings"], [])

    def test_dismissed_false_positive(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון אינו תקף כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "dismissed_false_positive")
        self.assertIsNone(review["correction"])
        self.assertEqual(len(review["false_positives"]), 1)

    def test_no_second_correction_even_with_two_material_claims(self):
        structure = self._structure(["The argument is not valid in all cases."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף במקרים.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        trigger_types = {t["type"] for t in request.risk_triggers}
        self.assertIn("negation", trigger_types)
        self.assertIn("quantifier", trigger_types)

        from scholarly_translation.semantic_review import FakeSemanticCorrector
        counting = {"calls": 0}
        real_corrector = FakeSemanticCorrector

        class CountingCorrector(real_corrector):
            def generate(self, prompt_text, model):
                counting["calls"] += 1
                return super().generate(prompt_text, model)

        def build_counting(req, claim):
            return CountingCorrector(req, claim)

        with unittest.mock.patch("scholarly_translation.semantic_review._build_corrector_adapter", build_counting):
            review = run_semantic_review(request)
        self.assertEqual(counting["calls"], 1)
        self.assertEqual(review["correction"]["claim"]["trigger_type"], "negation")

    def test_japanese_trigger_is_never_auto_corrected(self):
        structure = self._structure(["定理3は成り立つ。"], language="ja")
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "התיאוריה 3 נכונה.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "needs_human_review")
        self.assertIsNone(review["correction"])

    def test_formal_regression_after_correction_routes_to_human(self):
        structure = self._structure(["The theorem 3 is not true."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "המשפט 3 הוא נכון.")
        self.assertEqual(draft["findings"], [])
        request = build_semantic_review_request(structure, self.glossary, draft)

        class RegressingCorrector:
            def generate(self, prompt_text, model):
                return TextGenerationResult(
                    status="mock_placeholder", text="המשפט אינו נכון.", token_usage="not_metered",
                    observed_model=model, duration_seconds=0.001,
                )

        with unittest.mock.patch(
            "scholarly_translation.semantic_review._build_corrector_adapter",
            lambda req, claim: RegressingCorrector(),
        ):
            review = run_semantic_review(request)
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "correction_unresolved_or_regressed")
        self.assertTrue(any(f["type"] == "missing_number" for f in review["after_findings"]))


class MalformedAndStaleInputTests(SemanticReviewTestBase):
    def test_stale_draft_is_refused_before_provider(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        tampered = dict(draft, source_text_hash="0" * 64)
        with self.assertRaises(SemanticReviewRequestError):
            build_semantic_review_request(structure, self.glossary, tampered)

    def test_missing_canonical_formal_finding_is_refused(self):
        structure = self._structure(["Theorem 3 holds here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "המשפט נכון כאן.")
        self.assertTrue(draft["findings"])
        tampered = dict(draft, findings=[], status="draft_unapproved")
        with self.assertRaises(SemanticReviewRequestError):
            build_semantic_review_request(structure, self.glossary, tampered)

    def test_claim_must_match_exact_risk_span(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)

        class WrongSpanCritic:
            def generate(self, prompt_text, model):
                claim = {
                    "source_char_start": 0, "source_char_end": 3,
                    "trigger_type": "negation", "disposition": "error",
                    "target_span_text": draft["draft_text"], "evidence": "wrong source span",
                }
                return TextGenerationResult(
                    status="mock_placeholder", text=json.dumps({"claims": [claim]}),
                    token_usage="not_metered", observed_model=model, duration_seconds=0.001,
                )

        review = run_semantic_review(request, critic=WrongSpanCritic())
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "malformed_or_ungrounded_critic_response")
        self.assertIsNone(review["correction"])

    def test_failed_provider_draft_is_not_reviewable(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        failed = dict(draft, status="failed_transport", draft_text=None)
        with self.assertRaises(SemanticReviewRequestError):
            build_semantic_review_request(structure, self.glossary, failed)

    def test_non_hebrew_draft_is_not_reviewable(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "Not Hebrew at all.")
        with self.assertRaises(SemanticReviewRequestError):
            build_semantic_review_request(structure, self.glossary, draft)

    def test_malformed_critic_json_routes_to_human(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)

        class BrokenCritic:
            def generate(self, prompt_text, model):
                return TextGenerationResult(
                    status="mock_placeholder", text="not json at all", token_usage="not_metered",
                    observed_model=model, duration_seconds=0.001,
                )

        review = run_semantic_review(request, critic=BrokenCritic())
        self.assertEqual(review["status"], "needs_human")
        self.assertEqual(review["review_disposition"], "malformed_or_ungrounded_critic_response")
        self.assertIsNone(review["correction"])


class OpenAIProviderTests(SemanticReviewTestBase):
    def setUp(self):
        super().setUp()
        self.structure = self._structure(["The argument is not valid here."])
        self.unit = self.structure["units"][0]
        self.draft = _make_draft(
            self.structure, self.glossary, self.unit["unit_id"], "הטיעון תקף כאן.",
            provider="openai", model="gpt-6-luna",
        )
        self.request = build_semantic_review_request(self.structure, self.glossary, self.draft, provider="openai")

    def test_missing_key_raises_before_network(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(OpenAIConfigurationError):
                run_semantic_review(self.request)

    def test_critic_transport_failure_is_explicit(self):
        critic = OpenAITextGenerationAdapter(client=FakeClient(exc=TimeoutError("boom: secret")))
        review = run_semantic_review(self.request, critic=critic)
        self.assertEqual(review["status"], "failed_transport")
        self.assertEqual(review["review_disposition"], "critic_call_failed")
        self.assertFalse(review["approved"])

    def test_budget_exhaustion_before_critic_call_is_explicit(self):
        budget = TranslationBudget(max_calls=2, hard_list_usd=0.000001)
        review = run_semantic_review(self.request, budget=budget)
        self.assertEqual(review["status"], "needs_human_or_budget")
        self.assertEqual(review["review_disposition"], "budget_exhausted_before_critic_call")
        self.assertFalse(review["approved"])

    def test_full_critic_and_correction_round_trip(self):
        critic_response = SimpleNamespace(
            status="completed",
            model="gpt-6-luna",
            output_text=json.dumps({"claims": [{
                "source_char_start": self.unit["text"].index("not"),
                "source_char_end": self.unit["text"].index("not") + 3,
                "trigger_type": "negation", "disposition": "error",
                "target_span_text": self.draft["draft_text"], "evidence": "no negation marker in draft",
            }]}),
            usage=make_usage(),
        )
        corrector_response = SimpleNamespace(status="completed", model="gpt-6-luna", output_text="הטיעון אינו תקף כאן.", usage=make_usage())
        critic = OpenAITextGenerationAdapter(client=FakeClient(response=critic_response))
        corrector = OpenAITextGenerationAdapter(client=FakeClient(response=corrector_response))
        review = run_semantic_review(self.request, critic=critic, corrector=corrector)
        self.assertEqual(review["status"], "corrected_unapproved")
        self.assertFalse(review["approved"])
        self.assertEqual(review["critic"]["model"], "gpt-6-luna")
        self.assertEqual(review["corrector"]["model"], "gpt-6-luna")


class SemanticReviewCLITests(SemanticReviewTestBase):
    def test_mock_round_trip_writes_not_triggered_review(self):
        tmp_path = Path(self.tmp.name)
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")

        structure_path = tmp_path / "structure.json"
        structure_path.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text(json.dumps(self.glossary, ensure_ascii=False), encoding="utf-8")
        draft_path = tmp_path / "draft.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

        out_dir = tmp_path / "out"
        rc = cmd_semantic_review(str(structure_path), str(glossary_path), str(draft_path), "mock", str(out_dir))
        self.assertEqual(rc, 0)
        review_path = out_dir / "semantic_review.json"
        self.assertTrue(review_path.exists())
        data = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "not_triggered")
        self.assertFalse(data["approved"])

    def test_refuses_to_overwrite_existing_review(self):
        tmp_path = Path(self.tmp.name)
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        structure_path = tmp_path / "structure.json"
        structure_path.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text(json.dumps(self.glossary, ensure_ascii=False), encoding="utf-8")
        draft_path = tmp_path / "draft.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        out_dir = tmp_path / "out"
        self.assertEqual(cmd_semantic_review(str(structure_path), str(glossary_path), str(draft_path), "mock", str(out_dir)), 0)
        rc = cmd_semantic_review(str(structure_path), str(glossary_path), str(draft_path), "mock", str(out_dir))
        self.assertEqual(rc, 1)

    def test_unsafe_output_path_rejected(self):
        tmp_path = Path(self.tmp.name)
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        structure_path = tmp_path / "structure.json"
        structure_path.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text(json.dumps(self.glossary, ensure_ascii=False), encoding="utf-8")
        draft_path = tmp_path / "draft.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        package_dir = Path(__file__).resolve().parents[1] / "scholarly_translation"
        rc = cmd_semantic_review(str(structure_path), str(glossary_path), str(draft_path), "mock", str(package_dir))
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
