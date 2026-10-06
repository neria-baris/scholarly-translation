import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation import chapter_pipeline
from scholarly_translation.chapter_pipeline import (
    ChapterPipelineError, build_batch_translation_prompt, estimate_output_token_cap,
    parse_batch_translation_response, plan_chapter,
)
from scholarly_translation.document_draft import extract_structure
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.model_config import ModelConfiguration

HEBREW = "זהו טקסט עברי לדוגמה."


def _build_pdf(path, pages_lines):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    _, height = LETTER
    for lines in pages_lines:
        y = height - 100
        for i, text in enumerate(lines):
            if len(text) > 90:
                c.setFont('Helvetica', 8)
                for line in textwrap.wrap(text, width=90):
                    if y < 60:
                        c.showPage()
                        y = height-100
                        c.setFont('Helvetica', 8)
                    c.drawString(72, y, line)
                    y -= 11
                continue
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 14 if i == 0 else 12)
            c.drawString(72, y, text)
            y -= 28
        c.showPage()
    c.save()


def _config(usable_context_tokens=6000, roles=("translator",)):
    models = {}
    if "translator" in roles:
        models["translator"] = {"provider": "fake", "model": "fake-translator-1",
                                "capabilities": {"context_window": 100000,
                                                 "usable_context_tokens": usable_context_tokens,
                                                 "max_output_tokens": 1024}}
    if "chapter_qa" in roles:
        models["chapter_qa"] = {"provider": "fake", "model": "fake-qa-1",
                                "capabilities": {"context_window": 100000, "usable_context_tokens": 100000,
                                                 "max_output_tokens": 1024}}
    if "semantic_reviewer" in roles:
        models["semantic_reviewer"] = {"provider": "fake", "model": "fake-reviewer-1",
                                       "capabilities": {"context_window": 100000, "usable_context_tokens": 100000,
                                                        "max_output_tokens": 1024}}
    return ModelConfiguration.from_dict({
        "schema_version": 1,
        "providers": {"fake": {"type": "openai", "credential_env": "FAKE_TEST_API_KEY"}},
        "models": models,
    })


class ChapterPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _structure(self, pages_lines):
        path = self.root / "paper.pdf"
        _build_pdf(path, pages_lines)
        return extract_structure(path, "en")

    # --- batch response parsing ------------------------------------------

    def test_parse_batch_translation_response_happy_path(self):
        structure = self._structure([["Some scholars argue that the point holds."]])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        raw = json.dumps([{"unit_id": unit_ids[0], "translation": HEBREW, "translation_note": None}])
        result = parse_batch_translation_response(raw, unit_ids)
        self.assertEqual(result[unit_ids[0]]["translation"], HEBREW)

    def test_rejects_unknown_unit_id(self):
        raw = json.dumps([{"unit_id": "not-real", "translation": HEBREW}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_rejects_duplicate_unit_id(self):
        raw = json.dumps([{"unit_id": "u1", "translation": HEBREW}, {"unit_id": "u1", "translation": HEBREW}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_rejects_missing_unit_id(self):
        raw = json.dumps([{"unit_id": "u1", "translation": HEBREW}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1", "u2"])

    def test_rejects_out_of_order(self):
        raw = json.dumps([{"unit_id": "u2", "translation": HEBREW}, {"unit_id": "u1", "translation": HEBREW}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1", "u2"])

    def test_rejects_non_hebrew_target(self):
        raw = json.dumps([{"unit_id": "u1", "translation": "this is English, not Hebrew"}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_rejects_empty_translation(self):
        raw = json.dumps([{"unit_id": "u1", "translation": "   "}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_rejects_truncated_json(self):
        raw = '[{"unit_id": "u1", "translation": "' + HEBREW  # no closing
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_tolerates_only_trailing_closers_or_code_fence(self):
        item = {"unit_id": "u1", "translation": HEBREW, "translation_note": None}
        for raw in (json.dumps([item]) + "}", json.dumps([item]) + "]}\n", "```json\n" + json.dumps([item]) + "\n```"):
            self.assertEqual(parse_batch_translation_response(raw, ["u1"])["u1"]["translation"], HEBREW)
        for raw in ("Here it is: " + json.dumps([item]), json.dumps([item]) + " and more", json.dumps([item])[:-2]):
            with self.assertRaises(ChapterPipelineError):
                parse_batch_translation_response(raw, ["u1"])

    def test_tolerates_only_a_missing_final_bracket_after_a_complete_item(self):
        items = [{"unit_id": u, "translation": HEBREW, "translation_note": None} for u in ("u1", "u2")]
        body = json.dumps(items)[:-1]   # complete items, final "]" missing
        self.assertEqual(set(parse_batch_translation_response(body, ["u1", "u2"])), {"u1", "u2"})
        for raw, ids in ((body, ["u1", "u2", "u3"]),          # a unit is still missing -> coverage fails
                         (body + ",", ["u1", "u2"]),           # dangling comma
                         (body[:-1], ["u1", "u2"])):           # cut inside the last item
            with self.assertRaises(ChapterPipelineError):
                parse_batch_translation_response(raw, ids)

    def test_never_falls_back_to_source_text(self):
        source_text = "Some scholars argue that the point holds."
        raw = json.dumps([{"unit_id": "u1", "translation": source_text}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])

    def test_accepts_untranslatable_unit_kept_verbatim(self):
        source = "orbitbooks.net\norbitshortfiction.com"
        raw = json.dumps([{"unit_id": "u1", "translation": source, "translation_note": None}])
        result = parse_batch_translation_response(raw, ["u1"], {"u1": source})
        self.assertEqual(result["u1"]["translation"], source)
        for source in ("978-0-316-44086-8", "(866) 376-6591", "permissions@hbgusa.com", "https://example.org/a"):
            raw = json.dumps([{"unit_id": "u1", "translation": source}])
            self.assertIn("u1", parse_batch_translation_response(raw, ["u1"], {"u1": source}))

    def test_untranslatable_exemption_requires_source_and_no_words(self):
        urls = "orbitbooks.net"
        raw = json.dumps([{"unit_id": "u1", "translation": urls}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"], {"u1": "Visit orbitbooks.net"})
        raw = json.dumps([{"unit_id": "u1", "translation": "orbitbooks.net website"}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"], {"u1": urls})
        source = "Some scholars argue that the point holds."
        raw = json.dumps([{"unit_id": "u1", "translation": source}])
        with self.assertRaises(ChapterPipelineError):
            parse_batch_translation_response(raw, ["u1"], {"u1": source})

    # --- output cap estimation --------------------------------------------

    def test_output_token_cap_is_deterministic_and_monotonic(self):
        small = estimate_output_token_cap(100)
        large = estimate_output_token_cap(1000)
        self.assertEqual(small, estimate_output_token_cap(100))
        self.assertGreater(large, small)

    # --- planner -----------------------------------------------------------

    def test_plan_whole_chapter_when_it_fits(self):
        structure = self._structure([
            ["Chapter 1", "The first chapter contains an opening argument worth reading."],
        ])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        manifest = plan_chapter(structure, new_glossary_store(), unit_ids, _config(), "fast", "scholarly")
        self.assertTrue(manifest["whole_chapter"])
        self.assertEqual(len(manifest["batches"]), 1)
        self.assertEqual(sorted(manifest["batches"][0]["unit_ids"]), sorted(unit_ids))

    def test_plan_splits_when_translator_capacity_is_small(self):
        structure = self._structure([
            ["Chapter 1", "The first chapter contains an opening argument worth reading."],
            ["Chapter 1 continued", "A second paragraph with more content to translate here too."],
        ])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        # A usable context this small (120 tokens) cannot hold the fixed
        # ~512-token prompt-overhead reservation at all, which is an
        # impossible translator configuration, not a realistic "small
        # capacity forces a split" case; 1300 is small enough to hold one
        # short unit's batch but not two, which is what this test exercises.
        # Constrain output while leaving room for the complete versioned prompt.
        config_data = _config(usable_context_tokens=20000).to_dict()
        config_data['models']['translator']['capabilities']['max_output_tokens'] = 450
        manifest = plan_chapter(structure, new_glossary_store(), unit_ids, ModelConfiguration.from_dict(config_data),
                                "fast", "scholarly")
        self.assertGreater(len(manifest["batches"]), 1)
        covered = [uid for batch in manifest["batches"] for uid in batch["unit_ids"]]
        self.assertEqual(sorted(covered), sorted(unit_ids))

    def test_checked_quality_requires_chapter_qa_and_semantic_reviewer(self):
        structure = self._structure([["Some scholars argue that the point holds for the discussion."]])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        with self.assertRaises(ChapterPipelineError):
            plan_chapter(structure, new_glossary_store(), unit_ids, _config(roles=("translator",)),
                        "checked", "scholarly")

    def test_checked_quality_plans_with_required_roles_configured(self):
        structure = self._structure([["Some scholars argue that the point holds for the discussion."]])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        manifest = plan_chapter(
            structure, new_glossary_store(), unit_ids,
            _config(roles=("translator", "chapter_qa", "semantic_reviewer")), "checked", "scholarly",
        )
        self.assertEqual(set(manifest["qa_roles"]), {"chapter_qa", "semantic_reviewer"})
        self.assertGreaterEqual(manifest["conservative_total_ceiling_usd"], manifest["expected_total_cost_usd"])

    def test_too_large_single_unit_is_explicit_error_never_cropped(self):
        huge_text = "word " * 5000
        structure = self._structure([["Chapter 1", huge_text]])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        with self.assertRaises(ChapterPipelineError):
            plan_chapter(structure, new_glossary_store(), unit_ids, _config(usable_context_tokens=200),
                        "fast", "scholarly")

    # --- prompt construction -------------------------------------------------

    def test_batch_prompt_has_stable_prefix_and_dynamic_suffix(self):
        structure = self._structure([["Some scholars argue that the point holds for the discussion."]])
        unit_ids = [u["unit_id"] for u in structure["units"]]
        prompt = build_batch_translation_prompt(structure, new_glossary_store(), unit_ids, "scholarly")
        self.assertIn("SOURCE_UNITS", prompt.stable_prefix)
        self.assertIn("TARGET_UNIT_IDS", prompt.suffix)
        self.assertEqual(str(prompt), prompt.stable_prefix + prompt.suffix)


if __name__ == "__main__":
    unittest.main()
