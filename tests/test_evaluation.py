import json
import tempfile
import unittest
from pathlib import Path

from scholarly_translation.__main__ import main as cli_main
from scholarly_translation.evaluation import (
    STAGE,
    SCHEMA_VERSION,
    EvaluationError,
    build_report,
    validate_manifest,
)
from scholarly_translation.source_reading import text_hash


def _approval(text, actor="expert@example.org", reason="verified against approved source PDF"):
    return {"actor": actor, "actor_kind": "human", "reason": reason, "text_hash": text_hash(text)}


def _annotation(annotation_id, error_type="omission", severity="critical", start=0, end=4,
                reviewer_verdict="true_positive", actor="reviewer@example.org"):
    return {
        "annotation_id": annotation_id, "actor": actor, "actor_kind": "human",
        "error_type": error_type, "severity": severity,
        "source_char_start": start, "source_char_end": end, "reviewer_verdict": reviewer_verdict,
    }


def _arm(arm_id, provider="mock", model="mock-translation-1", prompt_version="v1",
         context_policy="none", critic_enabled=False, pages=1.0,
         observed_cost_usd=0.01, list_estimated_cost_usd=0.02, latency_seconds=2.0,
         correction_minutes=3.0, expert_reviewed=True, annotations=None,
         glossary_hash="b" * 64):
    draft_hash = text_hash(f"synthetic draft {arm_id}")
    return {
        "arm_id": arm_id, "provider": provider, "model": model, "prompt_version": prompt_version,
        "context_policy": context_policy, "critic_enabled": critic_enabled,
        "glossary_hash": glossary_hash, "draft_hash": draft_hash,
        "pages": pages,
        "observed_cost_usd": observed_cost_usd, "list_estimated_cost_usd": list_estimated_cost_usd,
        "latency_seconds": latency_seconds, "correction_minutes": correction_minutes,
        "expert_reviewed": expert_reviewed,
        "expert_review": {"actor": "reviewer@example.org", "actor_kind": "human",
                          "reason": "synthetic fixture review", "draft_hash": draft_hash}
        if expert_reviewed else None,
        "annotations": annotations if annotations is not None else [],
    }


def _unit(unit_id, language="en", genre="philosophy", ocr_level="digital", text=None,
          reference=None, arms=None, document_id="doc-1", pdf_hash="a" * 64,
          reading_id="reading-1", reading_version=1, start=0, source_word_count=None):
    text = (text if text is not None else "word " * 20).rstrip()
    reference = (reference if reference is not None else "מילה " * 20).rstrip()
    end = start + len(text)
    return {
        "unit_id": unit_id, "document_id": document_id, "pdf_hash": pdf_hash,
        "reading_id": reading_id, "reading_version": reading_version,
        "source_char_start": start, "source_char_end": end,
        "source_language": language, "genre": genre, "ocr_level": ocr_level,
        "source_text": text, "source_word_count": source_word_count or len(text.split()),
        "source_approval": _approval(text),
        "reference_text": reference, "reference_approval": _approval(reference),
        "arms": arms if arms is not None else [_arm("baseline")],
    }


def _manifest(units):
    return {"schema_version": SCHEMA_VERSION, "stage": STAGE, "units": units}


class BuildReportTests(unittest.TestCase):
    def test_valid_manifest_is_preliminary_below_threshold(self):
        report = build_report(_manifest([_unit("u1")]))
        self.assertEqual(report["status"], "preliminary")
        self.assertTrue(any("expert_approved_segments_total" in r for r in report["status_reasons"]))
        self.assertIsNone(report["model_winner"])
        self.assertIsNone(report["recommendation"])
        self.assertEqual(report["input_hash"], build_report(_manifest([_unit("u1")]))["input_hash"])

    def test_language_genre_ocr_grouping_counts(self):
        units = [
            _unit("u-en", language="en", genre="philosophy", ocr_level="digital"),
            _unit("u-fr", language="fr", genre="history", ocr_level="ocr"),
            _unit("u-ja", language="ja", genre="philosophy", ocr_level="digital"),
        ]
        report = build_report(_manifest(units))
        self.assertEqual(report["sample_counts"]["by_language"], {"en": 1, "fr": 1, "ja": 1})
        self.assertEqual(report["sample_counts"]["by_genre"], {"philosophy": 2, "history": 1})
        self.assertEqual(report["sample_counts"]["by_ocr_level"], {"digital": 2, "ocr": 1})

    def test_critical_errors_per_1000_source_words(self):
        text = ("word " * 100).rstrip()
        arm = _arm("baseline", annotations=[_annotation("a1", severity="critical")])
        report = build_report(_manifest([_unit("u1", text=text, arms=[arm])]))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["critical_errors_per_1000_source_words"], 10.0)
        self.assertEqual(metrics["severity_counts"]["critical"], 1)

    def test_minutes_and_cost_per_page(self):
        arm1 = _arm("baseline", pages=2.0, correction_minutes=10.0, list_estimated_cost_usd=4.0)
        arm2 = _arm("baseline", pages=3.0, correction_minutes=5.0, list_estimated_cost_usd=2.0)
        units = [_unit("u1", arms=[arm1]), _unit("u2", arms=[arm2])]
        report = build_report(_manifest(units))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertAlmostEqual(metrics["correction_minutes_per_page"], 15 / 5)
        self.assertAlmostEqual(metrics["list_estimated_cost_usd_per_page"], 6 / 5)

    def test_latency_percentiles(self):
        units = [
            _unit(f"u{i}", arms=[_arm("baseline", latency_seconds=float(latency))])
            for i, latency in enumerate([1, 2, 3, 4, 5])
        ]
        report = build_report(_manifest(units))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["latency_p50_seconds"], 3.0)
        self.assertAlmostEqual(metrics["latency_p95_seconds"], 4.8)

    def test_reviewer_true_false_positive_counts(self):
        annotations = [
            _annotation("a1", reviewer_verdict="true_positive"),
            _annotation("a2", reviewer_verdict="false_positive", start=5, end=9),
            _annotation("a3", reviewer_verdict="unconfirmed", start=10, end=14),
        ]
        arm = _arm("baseline", annotations=annotations)
        report = build_report(_manifest([_unit("u1", arms=[arm])]))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["reviewer_true_positive_count"], 1)
        self.assertEqual(metrics["reviewer_false_positive_count"], 1)
        self.assertTrue(metrics["reviewer_verdicts_available"])
        self.assertEqual(metrics["severity_counts"]["critical"], 1)

    def test_false_positive_is_not_counted_as_translation_error(self):
        arm = _arm("baseline", annotations=[_annotation("fp", reviewer_verdict="false_positive")])
        metrics = build_report(_manifest([_unit("u1", arms=[arm])]))["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["severity_counts"]["critical"], 0)
        self.assertEqual(metrics["critical_errors_per_1000_source_words"], 0.0)

    def test_direct_expert_error_counts_without_critic_verdict(self):
        arm = _arm("baseline", annotations=[_annotation("expert", reviewer_verdict=None)])
        metrics = build_report(_manifest([_unit("u1", arms=[arm])]))["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["severity_counts"]["critical"], 1)
        self.assertEqual(metrics["reviewer_true_positive_count"], 0)
        self.assertFalse(metrics["reviewer_verdicts_available"])

    def test_unconfirmed_flag_keeps_report_preliminary(self):
        arm = _arm("baseline", annotations=[_annotation("u", reviewer_verdict="unconfirmed")])
        report = build_report(_manifest([_unit("u1", arms=[arm])]))
        self.assertEqual(report["missing_data"]["annotations_unconfirmed"], ["u"])
        self.assertTrue(any("lack confirmation" in reason for reason in report["status_reasons"]))

    def test_japanese_uses_approved_word_count_not_whitespace(self):
        arm = _arm("baseline", annotations=[_annotation("a1")])
        unit = _unit("ja-1", language="ja", text="これは日本語の研究文です", source_word_count=10, arms=[arm])
        metrics = build_report(_manifest([unit]))["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["critical_errors_per_1000_source_words"], 100.0)

    def test_expert_reviewed_with_no_findings_reports_zero_rate(self):
        report = build_report(_manifest([_unit("u1")]))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertFalse(metrics["reviewer_verdicts_available"])
        self.assertEqual(metrics["critical_errors_per_1000_source_words"], 0.0)

    def test_unreviewed_arm_leaves_critical_rate_unknown(self):
        arm = _arm("baseline", expert_reviewed=False)
        report = build_report(_manifest([_unit("u1", arms=[arm])]))
        metrics = report["per_arm_metrics"]["baseline"]["overall"]
        self.assertEqual(metrics["expert_reviewed_count"], 0)
        self.assertIsNone(metrics["critical_errors_per_1000_source_words"])

    def test_paired_context_and_critic_missingness(self):
        paired_unit = _unit("u-paired", arms=[
            _arm("a", context_policy="none", critic_enabled=False),
            _arm("b", context_policy="previous_next", critic_enabled=False),
        ])
        unpaired_unit = _unit("u-unpaired", arms=[_arm("c")])
        report = build_report(_manifest([paired_unit, unpaired_unit]))
        missing = report["missing_data"]
        self.assertNotIn("u-paired", missing["units_missing_paired_context"])
        self.assertIn("u-unpaired", missing["units_missing_paired_context"])
        self.assertIn("u-paired", missing["units_missing_paired_critic"])
        self.assertIn("u-unpaired", missing["units_missing_paired_critic"])
        self.assertEqual(len(report["paired_comparisons"]["context"]), 1)
        self.assertEqual(report["paired_comparisons"]["critic"], [])

    def test_paired_comparison_reports_measured_deltas(self):
        arms = [_arm("baseline", correction_minutes=4, list_estimated_cost_usd=0.01,
                     annotations=[_annotation("a1")]),
                _arm("context", context_policy="previous_next", correction_minutes=2,
                     list_estimated_cost_usd=0.02)]
        row = build_report(_manifest([_unit("u1", arms=arms)]))["paired_comparisons"]["context"][0]
        self.assertEqual(row["critical_errors_right_minus_left"], -1)
        self.assertEqual(row["correction_minutes_right_minus_left"], -2)
        self.assertAlmostEqual(row["list_estimated_cost_usd_right_minus_left"], 0.01)

    def test_sample_threshold_met_with_full_paired_evidence(self):
        units = []
        for language in ("en", "fr", "ja"):
            for i in range(24):
                arms = [
                    _arm("baseline", context_policy="none", critic_enabled=False),
                    _arm("context", context_policy="previous_next", critic_enabled=False),
                    _arm("critic", context_policy="none", critic_enabled=True),
                ]
                units.append(_unit(f"{language}-{i}", language=language, arms=arms))
        report = build_report(_manifest(units))
        self.assertEqual(report["status"], "sample_threshold_met")
        self.assertEqual(report["status_reasons"], [])
        self.assertEqual(report["missing_data"]["units_missing_paired_context"], [])
        self.assertEqual(report["missing_data"]["units_missing_paired_critic"], [])
        self.assertIsNone(report["model_winner"])
        self.assertIsNone(report["recommendation"])

    def test_many_arms_cannot_inflate_unique_approved_segments(self):
        units = []
        for language in ("en", "fr", "ja"):
            for i in range(8):
                arms = [_arm("baseline"), _arm("context", context_policy="previous_next"),
                        _arm("critic", critic_enabled=True)]
                units.append(_unit(f"{language}-{i}", language=language, arms=arms))
        report = build_report(_manifest(units))
        self.assertEqual(report["sample_counts"]["total_arm_instances"], 72)
        self.assertEqual(report["sample_counts"]["expert_approved_segments_total"], 24)
        self.assertEqual(report["status"], "preliminary")

    def test_partly_reviewed_unit_does_not_count_as_approved(self):
        unit = _unit("u1", arms=[_arm("baseline"), _arm("critic", critic_enabled=True,
                                                        expert_reviewed=False)])
        report = build_report(_manifest([unit]))
        self.assertEqual(report["sample_counts"]["expert_approved_segments_total"], 0)
        self.assertTrue(any("missing expert review" in reason for reason in report["status_reasons"]))


class ValidateManifestTests(unittest.TestCase):
    def test_source_approval_hash_mismatch_rejected(self):
        unit = _unit("u1")
        unit["source_approval"]["text_hash"] = "0" * 64
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_reference_without_hebrew_script_rejected(self):
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([_unit("u1", reference="English only")]))

    def test_non_human_actor_rejected(self):
        unit = _unit("u1")
        unit["reference_approval"]["actor_kind"] = "model"
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_unsupported_language_rejected(self):
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([_unit("u1", language="de")]))

    def test_invalid_ocr_level_rejected(self):
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([_unit("u1", ocr_level="scan")]))

    def test_empty_genre_rejected(self):
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([_unit("u1", genre="  ")]))

    def test_duplicate_unit_id_rejected(self):
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([_unit("dup"), _unit("dup")]))

    def test_duplicate_annotation_id_rejected(self):
        unit = _unit("u1", arms=[
            _arm("a", annotations=[_annotation("same-id")]),
            _arm("b", annotations=[_annotation("same-id", start=5, end=9)]),
        ])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_duplicate_arm_id_within_unit_rejected(self):
        unit = _unit("u1", arms=[_arm("a"), _arm("a")])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_inconsistent_arm_signature_rejected(self):
        u1 = _unit("u1", arms=[_arm("baseline", provider="mock")])
        u2 = _unit("u2", arms=[_arm("baseline", provider="openai")])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([u1, u2]))

    def test_stale_pdf_hash_rejected(self):
        u1 = _unit("u1", document_id="doc-x", pdf_hash="a" * 64)
        u2 = _unit("u2", document_id="doc-x", pdf_hash="b" * 64)
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([u1, u2]))

    def test_nonfinite_cost_rejected(self):
        unit = _unit("u1", arms=[_arm("a", list_estimated_cost_usd=float("nan"))])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_annotation_span_out_of_bounds_rejected(self):
        unit = _unit("u1", arms=[_arm("a", annotations=[_annotation("a1", start=0, end=10000)])])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_annotations_require_expert_reviewed(self):
        unit = _unit("u1", arms=[_arm("a", annotations=[_annotation("a1")], expert_reviewed=False)])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_expert_review_must_match_draft_hash(self):
        unit = _unit("u1")
        unit["arms"][0]["expert_review"]["draft_hash"] = "0" * 64
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_mismatched_glossary_between_arms_rejected(self):
        unit = _unit("u1", arms=[_arm("a"), _arm("b", glossary_hash="c" * 64)])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_unexpected_manifest_field_rejected(self):
        manifest = _manifest([_unit("u1")])
        manifest["extra"] = True
        with self.assertRaises(EvaluationError):
            validate_manifest(manifest)

    def test_source_text_length_must_match_span_rejected(self):
        unit = _unit("u1")
        unit["source_char_end"] += 5
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_bad_word_count_rejected(self):
        unit = _unit("u1")
        unit["source_word_count"] = 0
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_unhashable_category_rejected_cleanly(self):
        unit = _unit("u1", language=["en"])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))

    def test_unit_without_arms_rejected(self):
        unit = _unit("u1", arms=[])
        with self.assertRaises(EvaluationError):
            validate_manifest(_manifest([unit]))


class EvaluatePilotCliTests(unittest.TestCase):
    def test_cli_writes_report_once_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest([_unit("u1")])), encoding="utf-8")
            out_dir = Path(tmp) / "out"

            exit_code = cli_main(["evaluate-pilot", str(manifest_path), "--output", str(out_dir)])
            self.assertEqual(exit_code, 0)
            report_path = out_dir / "pilot_report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "preliminary")
            self.assertIsNone(report["model_winner"])

            exit_code_again = cli_main(["evaluate-pilot", str(manifest_path), "--output", str(out_dir)])
            self.assertEqual(exit_code_again, 1)

    def test_cli_rejects_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            bad_unit = _unit("u1", language="de")
            manifest_path.write_text(json.dumps(_manifest([bad_unit])), encoding="utf-8")
            out_dir = Path(tmp) / "out"
            exit_code = cli_main(["evaluate-pilot", str(manifest_path), "--output", str(out_dir)])
            self.assertEqual(exit_code, 1)
            self.assertFalse((out_dir / "pilot_report.json").exists())


if __name__ == "__main__":
    unittest.main()
