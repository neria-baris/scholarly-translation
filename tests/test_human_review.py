import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.formal_checks import run_formal_checks
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.human_review import (
    HumanReviewRequestError,
    decision_template,
    export_bilingual_html,
    latest_decision,
    render_review_page,
    resolve_review_unit,
    run_human_review,
)
from scholarly_translation.model_adapter import PRICING_VERSION
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.semantic_review import build_semantic_review_request, run_semantic_review
from scholarly_translation.source_reading import build_readings, fingerprint
from scholarly_translation.translation import TranslationBudget, build_translation_request


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _build_structure_for_lines(tmp_path, lines, language="en"):
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


class HumanReviewTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def _structure(self, lines, language="en"):
        return _build_structure_for_lines(Path(self.tmp.name), lines, language)

    def _decide(self, review_unit, **overrides):
        decision = decision_template(review_unit)
        decision.update(overrides)
        return decision


class ResolveAndRenderTests(HumanReviewTestBase):
    def test_resolve_binds_draft_and_renders_source_and_hebrew(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        self.assertEqual(review_unit.unit["unit_id"], unit["unit_id"])
        self.assertEqual(review_unit.risk_triggers, ())

        page = render_review_page(review_unit)
        self.assertIn("A calm and ordinary sentence here.", page)
        self.assertIn("משפט רגיל כאן.", page)
        self.assertIn('dir="ltr"', page)
        self.assertIn('dir="rtl"', page)
        self.assertIn(structure["source_uri"], page)

    def test_resolve_rejects_tampered_draft(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        tampered = dict(draft, pdf_hash="0" * 64)
        with self.assertRaises(HumanReviewRequestError):
            resolve_review_unit(structure, self.glossary, tampered)

    def test_html_injection_in_source_and_candidate_is_escaped(self):
        structure = self._structure(["A <script>alert(1)</script> sentence."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="human_edit",
            candidate_text="<img onerror=alert(1)> משפט עברי עם תסריט.",
            actor="reviewer@example.org", reason="manual edit to neutralize markup", action="approve",
        )
        record = run_human_review(review_unit, decision)
        self.assertTrue(record["approved"])
        page = render_review_page(review_unit)
        exported = export_bilingual_html(review_unit, record)
        for html_text in (page, exported):
            self.assertNotIn("<script>alert(1)</script>", html_text)
            self.assertIn("&lt;script&gt;", html_text)
        self.assertIn('id="decision-form"', page)
        self.assertIn('id="action" required', page)
        self.assertIn("&lt;img onerror=alert(1)&gt;", exported)


class DecisionValidationTests(HumanReviewTestBase):
    def test_approve_no_risk_unit_without_review(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="matches source", action="approve",
        )
        record = run_human_review(review_unit, decision)
        self.assertEqual(record["status"], "approved")
        self.assertTrue(record["approved"])
        self.assertEqual(record["actor_kind"], "human")
        self.assertEqual(record["candidate_text"], draft["draft_text"])

    def test_defer_never_approves(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="not sure yet", action="defer",
        )
        record = run_human_review(review_unit, decision)
        self.assertEqual(record["status"], "deferred")
        self.assertFalse(record["approved"])

    def test_missing_review_blocks_approval_for_flagged_risk(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        self.assertTrue(review_unit.risk_triggers)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="looks fine", action="approve",
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

    def test_approve_with_review_and_correction_candidate(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        request = build_semantic_review_request(structure, self.glossary, draft)
        review = run_semantic_review(request)
        self.assertEqual(review["status"], "corrected_unapproved")

        review_unit = resolve_review_unit(structure, self.glossary, draft, review)
        decision = self._decide(
            review_unit, candidate_origin="correction", candidate_text=review["correction"]["candidate_text"],
            actor="reviewer@example.org", reason="correction verified against source", action="approve",
        )
        record = run_human_review(review_unit, decision)
        self.assertTrue(record["approved"])
        self.assertEqual(record["candidate_text"], review["correction"]["candidate_text"])
        self.assertEqual(record["review_hash"], fingerprint(review))
        altered_review = dict(review, review_disposition="needs_human_review")
        altered_unit = resolve_review_unit(structure, self.glossary, draft, altered_review)
        with self.assertRaises(HumanReviewRequestError):
            export_bilingual_html(altered_unit, record)

    def test_tampered_review_risk_flags_are_refused(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        review = run_semantic_review(build_semantic_review_request(structure, self.glossary, draft))
        tampered = dict(review, risk_triggers=[])
        with self.assertRaises(HumanReviewRequestError):
            resolve_review_unit(structure, self.glossary, draft, tampered)

    def test_candidate_must_match_declared_origin(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text="משפט שונה לגמרי.",
            actor="reviewer@example.org", reason="mismatch", action="approve",
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

    def test_correction_origin_requires_an_actual_correction_on_record(self):
        structure = self._structure(["The argument is not valid here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "הטיעון תקף כאן.")
        tiny_budget = TranslationBudget(max_calls=1, hard_list_usd=1e-9)
        request = build_semantic_review_request(structure, self.glossary, draft, provider="openai")
        review = run_semantic_review(request, budget=tiny_budget)
        self.assertEqual(review["status"], "needs_human_or_budget")
        self.assertIsNone(review["correction"])

        review_unit = resolve_review_unit(structure, self.glossary, draft, review)
        decision = self._decide(
            review_unit, candidate_origin="correction", candidate_text="הטיעון תקף כאן.",
            actor="reviewer@example.org", reason="claiming a nonexistent correction", action="approve",
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

    def test_unexpected_field_including_actor_kind_is_refused(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="ok", action="approve",
        )
        decision["actor_kind"] = "model"
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

    def test_formal_failure_blocks_approval_without_documented_override(self):
        structure = self._structure(["There are 3 cases to consider."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "יש מקרים לשקול.")
        self.assertTrue(any(f["type"] == "missing_number" for f in draft["findings"]))
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving despite dropped number", action="approve",
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

        decision["formal_override_reason"] = "verified against source: number intentionally omitted per style note"
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)

        decision["candidate_origin"] = "human_edit"
        decision["candidate_text"] = "יש 3 מקרים לשקול."
        decision["formal_override_reason"] = "Reviewed the source-initial name candidate against the page."
        record = run_human_review(review_unit, decision)
        self.assertTrue(record["approved"])
        self.assertFalse(any(f["type"] == "missing_number" for f in record["formal_findings"]))

    def test_stale_pdf_hash_is_refused(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="ok", action="approve",
            expected_pdf_hash="0" * 64,
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, decision)


class HistoryAndExportTests(HumanReviewTestBase):
    def test_prior_decision_chain_and_latest_decision(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)

        first_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="first pass", action="defer",
        )
        first_record = run_human_review(review_unit, first_decision)

        second_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="second look, approving", action="approve",
            prior_decision_hash=first_record["record_hash"],
        )
        second_record = run_human_review(review_unit, second_decision, previous=first_record)

        self.assertEqual(latest_decision([first_record, second_record])["record_hash"], second_record["record_hash"])
        # Original record is preserved untouched, not overwritten.
        self.assertEqual(first_record["status"], "deferred")

    def test_prior_decision_hash_must_match_supplied_previous(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        first_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="first pass", action="defer",
        )
        first_record = run_human_review(review_unit, first_decision)

        bad_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving", action="approve",
            prior_decision_hash="0" * 64,
        )
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, bad_decision, previous=first_record)

        matching_decision = dict(bad_decision, prior_decision_hash=first_record["record_hash"])
        altered_previous = dict(first_record, reason="altered after review")
        with self.assertRaises(HumanReviewRequestError):
            run_human_review(review_unit, matching_decision, previous=altered_previous)
        with self.assertRaises(HumanReviewRequestError):
            latest_decision([altered_previous])

    def test_export_requires_currently_valid_approved_record(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)

        deferred_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="not yet", action="defer",
        )
        deferred_record = run_human_review(review_unit, deferred_decision)
        with self.assertRaises(HumanReviewRequestError):
            export_bilingual_html(review_unit, deferred_record)

        approved_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving now", action="approve",
        )
        approved_record = run_human_review(review_unit, approved_decision)
        exported = export_bilingual_html(review_unit, approved_record)
        self.assertIn("A calm and ordinary sentence here.", exported)
        self.assertIn("משפט רגיל כאן.", exported)
        self.assertIn(structure["source_uri"], exported)
        self.assertIn(f"#page={review_unit.selected_candidate['page_number']}", exported)
        self.assertIn(f'href="#source-unit-{unit["unit_id"]}"', exported)

    def test_export_rejects_record_stale_against_a_changed_draft(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving", action="approve",
        )
        record = run_human_review(review_unit, decision)

        other_draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט אחר לגמרי כאן.")
        other_review_unit = resolve_review_unit(structure, self.glossary, other_draft)
        with self.assertRaises(HumanReviewRequestError):
            export_bilingual_html(other_review_unit, record)

    def test_export_rejects_tampered_record_content(self):
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving", action="approve",
        )
        record = run_human_review(review_unit, decision)
        tampered = dict(record, candidate_text="טקסט מזויף שלא אושר.")
        with self.assertRaises(HumanReviewRequestError):
            export_bilingual_html(review_unit, tampered)


class CliOutputOverwriteTests(HumanReviewTestBase):
    def test_cli_render_decide_export_round_trip_and_refuses_overwrite(self):
        import json

        from scholarly_translation.__main__ import (
            cmd_human_review_decide,
            cmd_human_review_export,
            cmd_human_review_render,
        )

        tmp_path = Path(self.tmp.name)
        structure = self._structure(["A calm and ordinary sentence here."])
        unit = structure["units"][0]
        draft = _make_draft(structure, self.glossary, unit["unit_id"], "משפט רגיל כאן.")
        review_unit = resolve_review_unit(structure, self.glossary, draft)

        structure_path = tmp_path / "structure.json"
        glossary_path = tmp_path / "glossary.json"
        draft_path = tmp_path / "draft.json"
        decision_path = tmp_path / "decision.json"
        structure_path.write_text(json.dumps(structure), encoding="utf-8")
        glossary_path.write_text(json.dumps(self.glossary), encoding="utf-8")
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="approving", action="approve",
        )
        decision_path.write_text(json.dumps(decision), encoding="utf-8")

        render_out = tmp_path / "render_out"
        self.assertEqual(cmd_human_review_render(
            str(structure_path), str(glossary_path), str(draft_path), None, str(render_out),
        ), 0)
        self.assertTrue((render_out / "review.html").exists())
        self.assertNotEqual(cmd_human_review_render(
            str(structure_path), str(glossary_path), str(draft_path), None, str(render_out),
        ), 0)

        decide_out = tmp_path / "decide_out"
        self.assertEqual(cmd_human_review_decide(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(decision_path), None, str(decide_out),
        ), 0)
        record_files = list(decide_out.glob("human_review_*.json"))
        self.assertEqual(len(record_files), 1)
        self.assertNotEqual(cmd_human_review_decide(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(decision_path), None, str(decide_out),
        ), 0)
        self.assertEqual(len(list(decide_out.glob("human_review_*.json"))), 1)

        export_out = tmp_path / "export_out"
        self.assertEqual(cmd_human_review_export(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(record_files[0]), str(export_out),
        ), 0)
        exported_text = (export_out / "export.html").read_text(encoding="utf-8")
        self.assertIn("משפט רגיל כאן.", exported_text)
        self.assertNotEqual(cmd_human_review_export(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(record_files[0]), str(export_out),
        ), 0)

        first_record = json.loads(record_files[0].read_text(encoding="utf-8"))
        later_decision = self._decide(
            review_unit, candidate_origin="draft", candidate_text=draft["draft_text"],
            actor="reviewer@example.org", reason="hold publication", action="defer",
        )
        later_decision["prior_decision_hash"] = first_record["record_hash"]
        later_path = tmp_path / "later_decision.json"
        later_path.write_text(json.dumps(later_decision), encoding="utf-8")
        self.assertEqual(cmd_human_review_decide(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(later_path), str(record_files[0]), str(decide_out),
        ), 0)
        self.assertNotEqual(cmd_human_review_export(
            str(structure_path), str(glossary_path), str(draft_path), None,
            str(record_files[0]), str(tmp_path / "old_approval_export"),
        ), 0)


if __name__ == "__main__":
    unittest.main()
