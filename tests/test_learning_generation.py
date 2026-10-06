"""Offline fixtures for learning_generation; no network, fakes only."""
import json
import unittest
from dataclasses import dataclass
from typing import Optional

from scholarly_translation.learning_contracts import LearningError, fingerprint
from scholarly_translation.learning_generation import (
    build_chapter_recap, build_request, generate_chunk, parse_response,
)


@dataclass
class FakeResult:
    status: str
    text: Optional[str]


def catalog():
    return {
        "schema_version": 1, "language": "fr", "version": "fr-test@1",
        "provenance": {"basis": "curated", "source": "fixture", "license": "cc0"},
        "items": [
            {"item_id": "fr-chat", "kind": "word", "lemma": "chat", "sense_he": "חתול",
             "forms": ["chat"], "priority_tier": 1, "prerequisite_ids": [],
             "explanation_he": "", "min_level": 1},
            {"item_id": "fr-maison", "kind": "word", "lemma": "maison", "sense_he": "בית",
             "forms": ["maison"], "priority_tier": 1, "prerequisite_ids": [],
             "explanation_he": "", "min_level": 1},
            {"item_id": "fr-le", "kind": "grammar", "lemma": "le/la", "sense_he": "ה- (זכר/נקבה)",
             "forms": ["le", "la"], "priority_tier": 1, "prerequisite_ids": [],
             "explanation_he": "תווית יידוע", "min_level": 1},
        ],
        "levels": [{"level_id": "1", "new_items_per_chunk": 3, "max_foreign_share": .5,
                    "max_grammar_per_chunk": 1, "max_foreign_words_per_edit": 1,
                    "support_mode": "inline"}],
    }


def plan():
    return {
        "schema_version": 1, "plan_id": "plan-1", "book_id": "book-one", "chapter_id": "chapter-one",
        "chunk_id": "chunk-1", "source_hash": "a" * 64, "units": [
            {"unit_id": "unit-one", "kind": "paragraph", "text": "הילד הביט בבית הגדול."},
            {"unit_id": "unit-heading", "kind": "heading", "text": "פרק ראשון"},
        ],
        "base_learner_revision": 0, "catalog_version": "fr-test@1", "policy_version": "learning-policy@1",
        "level_id": "1", "support_mode": "inline",
        "selected_item_ids": ["fr-chat", "fr-maison", "fr-le"],
        "new_item_ids": ["fr-chat", "fr-maison"], "review_item_ids": [],
        "limits": {"level_id": "1", "new_items_per_chunk": 3, "max_foreign_share": .5,
                   "max_grammar_per_chunk": 1, "max_foreign_words_per_edit": 1, "support_mode": "inline"},
    }


def valid_payload(plan_id="plan-1"):
    return json.dumps({
        "response_version": 1, "plan_id": plan_id,
        "edits": [
            {"unit_id": "unit-one", "start": 10, "end": 14, "original": "בבית",
             "replacement": "maison", "item_ids": ["fr-maison"], "grammar_ids": [],
             "gloss_he": "בית"},
        ],
        "recap": {
            "vocabulary": [{"item_id": "fr-maison", "gloss_he": "בית", "edit_indexes": [0]}],
            "grammar": [],
        },
        "warnings": [],
    })


class BuildRequestTests(unittest.TestCase):
    def test_deterministic_and_stable_fingerprint(self):
        p, cat = plan(), catalog()
        prompt_a, hash_a = build_request(p, cat, context="הקשר")
        prompt_b, hash_b = build_request(p, cat, context="הקשר")
        self.assertEqual(prompt_a, prompt_b)
        self.assertEqual(hash_a, hash_b)
        self.assertIn("SOURCE_UNITS", prompt_a)
        self.assertIn("fr-maison", prompt_a)

    def test_fingerprint_changes_with_context(self):
        p, cat = plan(), catalog()
        _, hash_a = build_request(p, cat, context="A")
        _, hash_b = build_request(p, cat, context="B")
        self.assertNotEqual(hash_a, hash_b)

    def test_unknown_selected_item_rejected(self):
        p = plan()
        p["selected_item_ids"] = p["selected_item_ids"] + ["fr-ghost"]
        with self.assertRaises(LearningError):
            build_request(p, catalog())


class ParseResponseTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan()
        self.catalog = catalog()
        _, self.input_hash = build_request(self.plan, self.catalog)

    def test_request_contains_required_json_shape(self):
        prompt, _ = build_request(self.plan, self.catalog)
        self.assertIn('"edit_indexes"', prompt)
        self.assertIn('"response_version"', prompt)

    def test_curated_complete_phrase_demonstrates_grammar_locally(self):
        from scholarly_translation.learning_catalog import load_catalog
        from scholarly_translation.learning_planner import plan_book
        from scholarly_translation.learning_contracts import fixture_source, new_learner, source_hash
        cat = load_catalog()
        learner = new_learner()
        learner.update({'level_id': '3', 'support_mode': 'click', 'items': [
            {'item_id': 'fr-je', 'introduced_count': 1, 'last_completed_book_id': 'previous-book'}]})
        source = fixture_source()
        source['chapters'][0]['units'][0]['text'] = 'אני כאן והספר נשאר על השולחן בעיר ליד הילד. ' * 10
        source['source_hash'] = source_hash(source)
        p = plan_book(source, learner, cat)[0]
        _, input_hash = build_request(p, cat)
        payload = {'response_version': 1, 'plan_id': p['plan_id'], 'edits': [{
            'unit_id': 'unit-one', 'start': 0, 'end': len('אני כאן'), 'original': 'אני כאן',
            'replacement': 'je suis ici', 'item_ids': ['fr-phrase-ici'],
            'grammar_ids': ['fr.g-etre-present'], 'gloss_he': 'אני כאן'}],
            'recap': {'vocabulary': [], 'grammar': []}, 'warnings': []}
        chunk, proposals = parse_response(json.dumps(payload), p, cat, input_hash)
        recap = build_chapter_recap('chapter-one', [chunk], [{'chunk_id': p['plan_id'], 'recap': proposals}])
        self.assertIn('fr.g-etre-present', chunk['coverage_item_ids'])
        self.assertIn('je suis', recap['grammar'][0]['explanation_he'])
        self.assertEqual(recap['grammar'][0]['examples'], [{'chunk_id': p['plan_id'], 'edit_index': 0}])

    def test_duplicate_json_fields_and_unknown_fields_refused(self):
        payload = json.loads(valid_payload())
        payload['progress'] = 100
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        duplicate = valid_payload().replace('"response_version": 1', '"response_version": 1, "response_version": 1')
        with self.assertRaises(LearningError):
            parse_response(duplicate, self.plan, self.catalog, self.input_hash)

    def test_grammar_cannot_claim_arbitrary_foreign_text(self):
        payload = json.loads(valid_payload())
        payload['edits'][0].update({'item_ids': [], 'grammar_ids': ['fr-le'], 'replacement': 'maison'})
        with self.assertRaises(LearningError) as raised:
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        self.assertEqual(str(raised.exception), 'ungrounded_grammar')

    def test_extra_item_claim_must_match_accepted_surface(self):
        payload = json.loads(valid_payload())
        payload['edits'][0]['item_ids'].append('fr-chat')
        with self.assertRaises(LearningError) as raised:
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        self.assertEqual(str(raised.exception), 'unapproved_surface')

    def test_empty_chunk_hash_bound_to_its_plan(self):
        payload = json.loads(valid_payload())
        payload['edits'] = []
        payload['recap'] = {'vocabulary': [], 'grammar': []}
        first, _ = parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        second_plan = dict(self.plan, plan_id='plan-two')
        payload['plan_id'] = 'plan-two'
        second, _ = parse_response(json.dumps(payload), second_plan, self.catalog, self.input_hash)
        self.assertNotEqual(first['content_hash'], second['content_hash'])

    def test_valid_word_edit_and_recap(self):
        chunk, recap_proposal = parse_response(valid_payload(), self.plan, self.catalog, self.input_hash)
        self.assertEqual(chunk["coverage_item_ids"], ["fr-maison"])
        self.assertEqual(len(chunk["edits"]), 1)
        self.assertEqual(recap_proposal["vocabulary"][0]["item_id"], "fr-maison")
        self.assertEqual(recap_proposal["grammar"], [])

    def test_source_text_outside_replacement_untouched(self):
        chunk, _ = parse_response(valid_payload(), self.plan, self.catalog, self.input_hash)
        edit = chunk["edits"][0]
        unit_text = self.plan["units"][0]["text"]
        self.assertEqual(unit_text[edit["start"]:edit["end"]], edit["original"])
        self.assertEqual(edit["original"], "בבית")

    def test_unknown_unit_id_rejected(self):
        payload = json.loads(valid_payload())
        payload["edits"][0]["unit_id"] = "ghost-unit"
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_changed_original_slice_rejected(self):
        payload = json.loads(valid_payload())
        payload["edits"][0]["original"] = "משהו אחר"
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_heading_edit_rejected(self):
        payload = json.loads(valid_payload())
        payload["edits"][0]["unit_id"] = "unit-heading"
        payload["edits"][0]["start"] = 0
        payload["edits"][0]["end"] = 3
        payload["edits"][0]["original"] = "פרק"
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_overlapping_edits_rejected(self):
        payload = json.loads(valid_payload())
        second = dict(payload["edits"][0])
        second["start"], second["end"], second["original"] = 12, 16, "ית ה"
        payload["edits"].append(second)
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_out_of_range_span_rejected(self):
        payload = json.loads(valid_payload())
        payload["edits"][0]["start"] = 0
        payload["edits"][0]["end"] = 10_000
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_non_bmp_text_span_is_handled_as_codepoints(self):
        plan_with_emoji = plan()
        plan_with_emoji["units"][0]["text"] = "הילד 😀 הביט בבית."
        _, input_hash = build_request(plan_with_emoji, self.catalog)
        text = plan_with_emoji["units"][0]["text"]
        start = text.index("בבית")
        end = start + len("בבית")
        payload = json.loads(valid_payload())
        payload["edits"][0]["start"], payload["edits"][0]["end"] = start, end
        payload["edits"][0]["original"] = text[start:end]
        chunk, _ = parse_response(json.dumps(payload), plan_with_emoji, self.catalog, input_hash)
        self.assertEqual(chunk["edits"][0]["original"], "בבית")

    def test_unapproved_foreign_surface_rejected(self):
        payload = json.loads(valid_payload())
        payload["edits"][0]["replacement"] = "casa"
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_quota_overflow_foreign_share_rejected(self):
        tight_plan = plan()
        tight_plan["limits"]["max_foreign_share"] = .01
        _, input_hash = build_request(tight_plan, self.catalog)
        with self.assertRaises(LearningError):
            parse_response(valid_payload(), tight_plan, self.catalog, input_hash)

    def test_ungrounded_recap_entry_dropped_not_raised(self):
        payload = json.loads(valid_payload())
        payload["recap"]["vocabulary"].append({"item_id": "fr-chat", "gloss_he": "חתול", "edit_indexes": [0]})
        chunk, recap_proposal = parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        item_ids = {entry["item_id"] for entry in recap_proposal["vocabulary"]}
        self.assertNotIn("fr-chat", item_ids)
        self.assertIn("fr-maison", item_ids)

    def test_malformed_json_rejected(self):
        with self.assertRaises(LearningError):
            parse_response("{not json", self.plan, self.catalog, self.input_hash)

    def test_refusal_text_rejected(self):
        with self.assertRaises(LearningError):
            parse_response("I cannot comply with this request.", self.plan, self.catalog, self.input_hash)

    def test_disallowed_warning_code_rejected(self):
        payload = json.loads(valid_payload())
        payload["warnings"] = [{"code": "made_up_code", "unit_id": None}]
        with self.assertRaises(LearningError):
            parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)

    def test_coverage_shortfall_warning_accepted_with_sparse_edits(self):
        payload = json.loads(valid_payload())
        payload["edits"] = []
        payload["recap"] = {"vocabulary": [], "grammar": []}
        payload["warnings"] = [{"code": "coverage_shortfall", "unit_id": "unit-one"}]
        chunk, recap_proposal = parse_response(json.dumps(payload), self.plan, self.catalog, self.input_hash)
        self.assertEqual(chunk["edits"], [])
        self.assertEqual(chunk["warnings"][0]["code"], "coverage_shortfall")


class GenerateChunkTests(unittest.TestCase):
    def test_calls_controlled_generate_exactly_once_and_passes_result(self):
        calls = []

        def controlled_generate(prompt, input_hash):
            calls.append((prompt, input_hash))
            return FakeResult("completed", valid_payload())

        chunk, recap_proposal = generate_chunk(plan(), catalog(), controlled_generate=controlled_generate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(chunk["coverage_item_ids"], ["fr-maison"])

    def test_raw_string_result_accepted(self):
        chunk, _ = generate_chunk(plan(), catalog(), controlled_generate=lambda p, h: valid_payload())
        self.assertEqual(chunk["coverage_item_ids"], ["fr-maison"])

    def test_truncated_result_status_raises(self):
        def controlled_generate(prompt, input_hash):
            return FakeResult("failed_truncated", None)

        with self.assertRaises(LearningError):
            generate_chunk(plan(), catalog(), controlled_generate=controlled_generate)

    def test_cache_fingerprint_changes_with_catalog_version(self):
        cat_a, cat_b = catalog(), catalog()
        cat_b["version"] = "fr-test@2"
        _, hash_a = build_request(plan(), cat_a)
        _, hash_b = build_request(plan(), cat_b)
        self.assertNotEqual(hash_a, hash_b)


class BuildChapterRecapTests(unittest.TestCase):
    def test_merges_accepted_chunks_deduplicated_by_item(self):
        p, cat = plan(), catalog()
        _, input_hash = build_request(p, cat)
        chunk, recap_proposal = parse_response(valid_payload(), p, cat, input_hash)
        recap = build_chapter_recap(
            "chapter-one", [chunk],
            [{"chunk_id": "plan-1", "recap": recap_proposal}],
        )
        self.assertEqual(len(recap["vocabulary"]), 1)
        self.assertEqual(recap["vocabulary"][0]["item_id"], "fr-maison")
        self.assertEqual(recap["chunk_hashes"], [chunk["content_hash"]])

    def test_no_items_introduced_yields_empty_recap(self):
        p, cat = plan(), catalog()
        _, input_hash = build_request(p, cat)
        payload = json.loads(valid_payload())
        payload["edits"] = []
        payload["recap"] = {"vocabulary": [], "grammar": []}
        chunk, recap_proposal = parse_response(json.dumps(payload), p, cat, input_hash)
        recap = build_chapter_recap("chapter-one", [chunk], [{"chunk_id": "plan-1", "recap": recap_proposal}])
        self.assertEqual(recap["vocabulary"], [])
        self.assertEqual(recap["grammar"], [])

    def test_unknown_chunk_id_rejected(self):
        p, cat = plan(), catalog()
        _, input_hash = build_request(p, cat)
        chunk, _ = parse_response(valid_payload(), p, cat, input_hash)
        with self.assertRaises(LearningError):
            build_chapter_recap("chapter-one", [chunk], [{"chunk_id": "ghost", "recap": {}}])


if __name__ == "__main__":
    unittest.main()
