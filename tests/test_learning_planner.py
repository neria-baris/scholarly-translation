import unittest
import tempfile
from pathlib import Path

from scholarly_translation.learning_catalog import load_catalog
from scholarly_translation.learning_contracts import LearningError, fixture_source, new_learner
from scholarly_translation.learning_planner import plan_book, replan_chunk

POLICY = "learning-policy@1"


def _long_source(book_id="book-long", paragraph_len=1200, paragraph_count=4):
    text = ("הילד הלך בדרך הארוכה אל העיר ונשאר שם עד הערב. " * (paragraph_len // 40 + 1))[:paragraph_len]
    units = [{"unit_id": f"unit-{i}", "kind": "paragraph", "text": text} for i in range(paragraph_count)]
    from scholarly_translation.learning_contracts import source_hash, validate_source
    source = {
        "schema_version": 1, "book_id": book_id, "revision": 1, "title": "ספר ארוך",
        "origin": {"kind": "hebrew_epub", "original_hash": "a" * 64, "source_job_id": None, "source_revision": None},
        "chapters": [{"chapter_id": "chapter-one", "title": "פרק", "units": units}],
    }
    source["source_hash"] = source_hash(source)
    return validate_source(source)















class LearningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_common_relevant_opportunities_can_displace_absent_candidates(self):
        from scholarly_translation.learning_contracts import source_hash
        source = fixture_source()
        source['chapters'][0]['units'][0]['text'] = 'אני אמרתי תודה אבל הוא נשאר בעיר. ' * 20
        source['source_hash'] = source_hash(source)
        plan = plan_book(source, new_learner(), load_catalog())[0]
        self.assertTrue(set(plan['new_item_ids']) & {'fr-je', 'fr-merci', 'fr-mais', 'fr-il'})

    def test_plan_book_deterministic_same_input_same_plan(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        source = fixture_source()
        plans_a = plan_book(source, learner, catalog, policy_version=POLICY)
        plans_b = plan_book(source, learner, catalog, policy_version=POLICY)
        assert [p["plan_id"] for p in plans_a] == [p["plan_id"] for p in plans_b]
        assert [p["selected_item_ids"] for p in plans_a] == [p["selected_item_ids"] for p in plans_b]


    def test_plan_book_common_first_and_prerequisite_respected(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        source = fixture_source()
        plans = plan_book(source, learner, catalog, policy_version=POLICY)
        assert plans
        first_new = plans[0]["new_item_ids"]
        # grammar item fr.g-etre-present needs fr-est etc as prerequisites, and must
        # never appear before its prerequisites are introduced.
        assert "fr.g-etre-present" not in first_new

        by_id = {item["item_id"]: item for item in catalog["items"]}
        tiers = [by_id[i]["priority_tier"] for i in first_new]
        assert tiers == sorted(tiers)


    def test_plan_book_new_item_limit_on_short_and_long_chapters(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        level = {lvl["level_id"]: lvl for lvl in catalog["levels"]}[learner["level_id"]]

        short_plans = plan_book(fixture_source("book-short"), learner, catalog, policy_version=POLICY)
        long_plans = plan_book(_long_source(), learner, catalog, policy_version=POLICY)
        assert len(long_plans) > 1
        for plan in short_plans + long_plans:
            assert len(plan["new_item_ids"]) <= level["new_items_per_chunk"]
            assert len(plan["review_item_ids"]) <= level["new_items_per_chunk"]


    def test_plan_book_chunking_bounded_independent_of_chapter_length(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        plans = plan_book(_long_source(), learner, catalog, policy_version=POLICY)
        for plan in plans:
            total_len = sum(len(u["text"]) for u in plan["units"])
            # a single oversized atomic unit may alone exceed the bound; every
            # chunk with more than one unit must still respect it.
            if len(plan["units"]) > 1:
                assert total_len <= 2400


    def test_plan_book_rejects_language_mismatch(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        learner = dict(learner, language="de")
        with self.assertRaises(LearningError):
            plan_book(fixture_source(), learner, catalog, policy_version=POLICY)


    def test_replan_chunk_uses_projected_learner_for_recurrence(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        source = fixture_source()
        plans = plan_book(source, learner, catalog, policy_version=POLICY)
        provisional = plans[0]

        projected = dict(learner)
        projected["items"] = [
            {"item_id": item_id, "introduced_count": 1, "last_completed_book_id": "book-zero"}
            for item_id in provisional["new_item_ids"]
        ]
        final_plan = replan_chunk(provisional, projected, catalog)
        # previously-accepted items should now appear as review, not new, candidates.
        assert set(provisional["new_item_ids"]) & set(final_plan["review_item_ids"]) == set(provisional["new_item_ids"])
        assert final_plan["plan_id"] != provisional["plan_id"]


    def test_replan_chunk_never_forces_skipped_candidate_into_new(self):
        catalog = load_catalog("fr")
        learner = new_learner(language="fr")
        source = fixture_source()
        plans = plan_book(source, learner, catalog, policy_version=POLICY)
        final_plan = replan_chunk(plans[0], learner, catalog)
        assert set(final_plan["new_item_ids"]) <= set(final_plan["selected_item_ids"])
        assert set(final_plan["new_item_ids"]) == set(plans[0]["new_item_ids"])
