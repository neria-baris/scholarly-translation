import unittest

from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.review_qa import (
    ReviewQARequestError,
    build_candidate_comparison_request,
    build_chapter_qa_request,
    build_unit_review_request,
    run_candidate_comparison,
    run_chapter_qa,
    run_unit_review,
)

SOURCE = "The theory is not valid in this case."
TRANSLATION_PASS = "התיאוריה תקפה במקרה זה."
TRANSLATION_ISSUE = "התיאוריה תקפה במקרה זה."  # dropped "not" -> reviewer should flag


def _fake_generate(text):
    def generate(prompt_text, model):
        return TextGenerationResult(
            status="mock_placeholder", text=text, token_usage="not_metered",
            observed_model=model, duration_seconds=0.001,
        )
    return generate


def _counting_generate(text):
    calls = {"count": 0}

    def generate(prompt_text, model):
        calls["count"] += 1
        return TextGenerationResult(
            status="mock_placeholder", text=text, token_usage="not_metered",
            observed_model=model, duration_seconds=0.001,
        )
    generate.calls = calls
    return generate


class UnitReviewTests(unittest.TestCase):
    def test_policy_off_skips_without_calling_adapter(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="off")
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n")
        review = run_unit_review(request, generate)
        self.assertEqual(review["status"], "skipped")
        self.assertEqual(review["skip_reason"], "policy_off")
        self.assertFalse(review["approved"])
        self.assertEqual(generate.calls["count"], 0)
        self.assertRegex(review["input_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(review["prompt_asset_hash"], r"^[0-9a-f]{64}$")

    def test_risk_based_non_risky_skips_without_calling_adapter(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="risk_based")
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n")
        review = run_unit_review(request, generate)
        self.assertEqual(review["status"], "skipped")
        self.assertEqual(review["skip_reason"], "no_risk_flagged")
        self.assertEqual(generate.calls["count"], 0)

    def test_risk_based_routes_on_translation_notes_flag(self):
        request = build_unit_review_request(
            SOURCE, TRANSLATION_ISSUE, policy="risk_based",
            risk_flags={"translation_notes": True},
        )
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n")
        review = run_unit_review(request, generate)
        self.assertEqual(review["status"], "completed")
        self.assertEqual(generate.calls["count"], 1)

    def test_risk_based_routes_on_configured_risk_flag(self):
        request = build_unit_review_request(
            SOURCE, TRANSLATION_ISSUE, policy="risk_based",
            risk_flags={"configured_risk_flags": ["caller_custom_flag"]},
        )
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n")
        review = run_unit_review(request, generate)
        self.assertEqual(review["status"], "completed")
        self.assertEqual(generate.calls["count"], 1)

    def test_policy_all_calls_even_without_risk(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="all")
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n")
        review = run_unit_review(request, generate)
        self.assertEqual(review["status"], "completed")
        self.assertEqual(review["verdict"], "PASS")
        self.assertEqual(review["issues"], [])
        self.assertEqual(generate.calls["count"], 1)
        self.assertFalse(review["approved"])

    def test_pass_without_invented_issues(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="all")
        review = run_unit_review(request, _fake_generate("VERDICT: PASS\n\nISSUES: none\n"))
        self.assertEqual(review["verdict"], "PASS")
        self.assertEqual(review["issues"], [])

    def test_revise_with_every_severity(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")
        response = (
            "VERDICT: REVISE\n\nISSUES:\n"
            "1. Severity: CRITICAL\n"
            "   Source span: not valid\n"
            "   Translation span: תקפה\n"
            "   Problem: negation dropped\n"
            "   Suggested correction: אינה תקפה\n"
            "2. Severity: MAJOR\n"
            "   Source span: theory\n"
            "   Translation span: התיאוריה\n"
            "   Problem: terminology drift\n"
            "   Suggested correction: use approved term\n"
            "3. Severity: MINOR\n"
            "   Source span: this case\n"
            "   Translation span: במקרה זה\n"
            "   Problem: minor register issue\n"
            "   Suggested correction: adjust register\n"
        )
        review = run_unit_review(request, _fake_generate(response))
        self.assertEqual(review["status"], "completed")
        self.assertEqual(review["verdict"], "REVISE")
        severities = [issue["severity"] for issue in review["issues"]]
        self.assertEqual(severities, ["CRITICAL", "MAJOR", "MINOR"])
        self.assertFalse(review["approved"])

    def test_malformed_response_fails_closed(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")
        review = run_unit_review(request, _fake_generate("not a valid response"))
        self.assertEqual(review["status"], "needs_human")
        self.assertIsNotNone(review["error"])
        self.assertFalse(review["approved"])

    def test_partly_parseable_issue_block_fails_closed(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")
        response = (
            "VERDICT: REVISE\n\nISSUES:\n"
            "unexpected preface\n"
            "1. Severity: CRITICAL\n"
            "   Source span: not valid\n"
            "   Translation span: תקפה\n"
            "   Problem: negation dropped\n"
            "   Suggested correction: אינה תקפה\n"
        )
        review = run_unit_review(request, _fake_generate(response))
        self.assertEqual(review["status"], "needs_human")

    def test_adapter_exception_is_bounded(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")

        def fail(prompt_text, model):
            raise RuntimeError("private source text must not escape")

        review = run_unit_review(request, fail)
        self.assertEqual(review["status"], "failed")
        self.assertEqual(review["error"], "adapter call failed")

    def test_ungrounded_span_fails_closed(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")
        response = (
            "VERDICT: REVISE\n\nISSUES:\n"
            "1. Severity: CRITICAL\n"
            "   Source span: this text does not appear in source\n"
            "   Translation span: תקפה\n"
            "   Problem: negation dropped\n"
            "   Suggested correction: אינה תקפה\n"
        )
        review = run_unit_review(request, _fake_generate(response))
        self.assertEqual(review["status"], "needs_human")
        self.assertIn("grounded", review["error"])

    def test_pass_verdict_with_issues_is_rejected(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_ISSUE, policy="all")
        response = (
            "VERDICT: PASS\n\nISSUES:\n"
            "1. Severity: MINOR\n"
            "   Source span: theory\n"
            "   Translation span: התיאוריה\n"
            "   Problem: invented\n"
            "   Suggested correction: n/a\n"
        )
        review = run_unit_review(request, _fake_generate(response))
        self.assertEqual(review["status"], "needs_human")

    def test_none_with_trailing_content_is_rejected(self):
        request = build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="all")
        review = run_unit_review(request, _fake_generate("VERDICT: PASS\n\nISSUES: none\nunexpected"))
        self.assertEqual(review["status"], "needs_human")

    def test_input_placeholder_text_is_not_cross_substituted(self):
        request = build_unit_review_request(
            SOURCE, TRANSLATION_PASS, source_context=("literal {{source_text}} marker",), policy="all",
        )
        seen = {}

        def generate(prompt_text, model):
            seen["prompt"] = prompt_text
            return TextGenerationResult(
                status="mock_placeholder", text="VERDICT: PASS\n\nISSUES: none\n",
                token_usage="not_metered", observed_model=model, duration_seconds=0.001,
            )

        run_unit_review(request, generate)
        self.assertIn("literal {{source_text}} marker", seen["prompt"])

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="sometimes")

    def test_non_hebrew_translation_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_unit_review_request(SOURCE, "not hebrew at all", policy="off")

    def test_malformed_risk_flags_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_unit_review_request(SOURCE, TRANSLATION_PASS, policy="risk_based", risk_flags={"unknown_flag": True})


class CandidateComparisonTests(unittest.TestCase):
    def test_requires_two_or_three_candidates(self):
        with self.assertRaises(ReviewQARequestError):
            build_candidate_comparison_request(SOURCE, {"A": TRANSLATION_PASS})
        with self.assertRaises(ReviewQARequestError):
            build_candidate_comparison_request(
                SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_PASS, "C": TRANSLATION_PASS, "D": TRANSLATION_PASS},
            )

    def test_three_candidates_are_allowed(self):
        request = build_candidate_comparison_request(
            SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_PASS, "C": TRANSLATION_PASS},
        )
        response = (
            "MATERIAL_DIFFERENCES:\nnone\n"
            "CANDIDATE_ASSESSMENTS:\nA: faithful\nB: faithful\nC: faithful\n"
            "BEST_SUPPORTED_TRANSLATION:\nNO_CLEAR_WINNER\n"
            "REASON:\nequivalent\nUNCERTAINTIES:\nnone\n"
        )
        comparison = run_candidate_comparison(request, _fake_generate(response))
        self.assertEqual(comparison["status"], "completed")
        self.assertEqual(comparison["candidate_ids"], ["A", "B", "C"])
        self.assertRegex(comparison["input_hash"], r"^[0-9a-f]{64}$")

    def test_winner_selected(self):
        request = build_candidate_comparison_request(SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_ISSUE})
        response = (
            "MATERIAL_DIFFERENCES:\n"
            "- [likely_translation_error] candidate B drops the negation\n"
            "CANDIDATE_ASSESSMENTS:\n"
            "A: faithful and complete\n"
            "B: drops a negation, materially changes the claim\n"
            "BEST_SUPPORTED_TRANSLATION:\n"
            "A\n"
            "REASON:\n"
            "A preserves the negated claim; B does not.\n"
            "UNCERTAINTIES:\n"
            "none\n"
        )
        comparison = run_candidate_comparison(request, _fake_generate(response))
        self.assertEqual(comparison["status"], "completed")
        self.assertEqual(comparison["result"]["best_supported_translation"], "A")
        self.assertEqual(len(comparison["result"]["material_differences"]), 1)
        self.assertFalse(comparison["approved"])

    def test_no_clear_winner_allowed(self):
        request = build_candidate_comparison_request(SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_PASS})
        response = (
            "MATERIAL_DIFFERENCES:\n"
            "none\n"
            "CANDIDATE_ASSESSMENTS:\n"
            "A: faithful\n"
            "B: equally faithful\n"
            "BEST_SUPPORTED_TRANSLATION:\n"
            "NO_CLEAR_WINNER\n"
            "REASON:\n"
            "Both candidates are equivalently supported.\n"
            "UNCERTAINTIES:\n"
            "none\n"
        )
        comparison = run_candidate_comparison(request, _fake_generate(response))
        self.assertEqual(comparison["result"]["best_supported_translation"], "NO_CLEAR_WINNER")

    def test_unknown_winner_id_rejected(self):
        request = build_candidate_comparison_request(SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_PASS})
        response = (
            "MATERIAL_DIFFERENCES:\n"
            "none\n"
            "CANDIDATE_ASSESSMENTS:\n"
            "A: faithful\n"
            "B: faithful\n"
            "BEST_SUPPORTED_TRANSLATION:\n"
            "Z\n"
            "REASON:\n"
            "bogus\n"
            "UNCERTAINTIES:\n"
            "none\n"
        )
        comparison = run_candidate_comparison(request, _fake_generate(response))
        self.assertEqual(comparison["status"], "needs_human")

    def test_duplicate_candidate_assessment_rejected(self):
        request = build_candidate_comparison_request(SOURCE, {"A": TRANSLATION_PASS, "B": TRANSLATION_PASS})
        response = (
            "MATERIAL_DIFFERENCES:\nnone\n"
            "CANDIDATE_ASSESSMENTS:\nA: faithful\nA: repeated\nB: faithful\n"
            "BEST_SUPPORTED_TRANSLATION:\nNO_CLEAR_WINNER\n"
            "REASON:\nequivalent\nUNCERTAINTIES:\nnone\n"
        )
        comparison = run_candidate_comparison(request, _fake_generate(response))
        self.assertEqual(comparison["status"], "needs_human")

    def test_duplicate_candidate_ids_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_candidate_comparison_request(SOURCE, {"": TRANSLATION_PASS, "B": TRANSLATION_PASS})

    def test_candidate_id_with_format_delimiter_is_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_candidate_comparison_request(SOURCE, {"A: injected": TRANSLATION_PASS, "B": TRANSLATION_PASS})


class ChapterQATests(unittest.TestCase):
    SOURCE_CHAPTER = "Chapter one begins here. Chapter one ends here."
    HEBREW_CHAPTER = "הפרק הראשון מתחיל כאן. הפרק הראשון מסתיים כאן. הפרק הראשון מתחיל כאן."

    def test_policy_off_skips_without_calling_adapter(self):
        request = build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="off")
        generate = _counting_generate("VERDICT: PASS\n\nISSUES: none\n\nCHAPTER_LEVEL_NOTES:\nnone\n")
        qa = run_chapter_qa(request, generate)
        self.assertEqual(qa["status"], "skipped")
        self.assertEqual(generate.calls["count"], 0)
        self.assertFalse(qa["approved"])

    def test_policy_on_pass(self):
        request = build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="on")
        qa = run_chapter_qa(request, _fake_generate("VERDICT: PASS\n\nISSUES: none\n\nCHAPTER_LEVEL_NOTES:\nnone\n"))
        self.assertEqual(qa["status"], "completed")
        self.assertEqual(qa["verdict"], "PASS")
        self.assertEqual(qa["issues"], [])

    def test_boundary_duplication_issue_with_local_correction(self):
        request = build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="on")
        response = (
            "VERDICT: REVISE\n\nISSUES:\n"
            "1. Category: completeness\n"
            "   Severity: MAJOR\n"
            "   Span: הפרק הראשון מתחיל כאן\n"
            "   Correction: remove the duplicated sentence at the unit boundary\n"
            "\nCHAPTER_LEVEL_NOTES:\n"
            "Unit boundary duplication detected between the first two merged units.\n"
        )
        qa = run_chapter_qa(request, _fake_generate(response))
        self.assertEqual(qa["status"], "completed")
        self.assertEqual(qa["verdict"], "REVISE")
        self.assertEqual(qa["issues"][0]["category"], "completeness")
        self.assertFalse(qa["approved"])
        self.assertRegex(qa["input_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(qa["prompt_asset_hash"], r"^[0-9a-f]{64}$")

    def test_structured_output_contract_is_sent_to_adapter(self):
        request = build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="on")
        seen = {}

        def generate(prompt_text, model):
            seen["prompt"] = prompt_text
            return TextGenerationResult(
                status="mock_placeholder",
                text="VERDICT: PASS\n\nISSUES: none\n\nCHAPTER_LEVEL_NOTES:\nnone\n",
                token_usage="not_metered", observed_model=model, duration_seconds=0.001,
            )

        qa = run_chapter_qa(request, generate)
        self.assertEqual(qa["verdict"], "PASS")
        self.assertIn("STRUCTURED_OUTPUT_CONTRACT:", seen["prompt"])

    def test_malformed_response_fails_closed(self):
        request = build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="on")
        qa = run_chapter_qa(request, _fake_generate("garbage"))
        self.assertEqual(qa["status"], "needs_human")
        self.assertIsNotNone(qa["error"])

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ReviewQARequestError):
            build_chapter_qa_request(self.SOURCE_CHAPTER, self.HEBREW_CHAPTER, policy="sometimes")


if __name__ == "__main__":
    unittest.main()
