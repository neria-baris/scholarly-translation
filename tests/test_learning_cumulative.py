"""Cumulative learning invariants, exercised offline with accepted edit fixtures."""
from copy import deepcopy
from dataclasses import replace
import json
import math
import re
from pathlib import Path
import tempfile
import unittest

from scholarly_translation.learning_contracts import (
    LearningError, fixture_source, new_learner, source_hash, validate_catalog,
)
from scholarly_translation.learning_catalog import load_catalog
from scholarly_translation.learning_generation import build_request, parse_response
from scholarly_translation.learning_planner import plan_book, replan_chunk
from test_learning_generation import catalog as small_catalog, plan as small_plan, valid_payload
from scholarly_translation.learning_service import LearningService
from test_learning_integration import source, configuration, Adapter


class CumulativePlanningTests(unittest.TestCase):
    def test_all_relevant_known_items_survive_beyond_new_quota(self):
        catalog = load_catalog(version='fr-common@1')
        learner = new_learner(catalog_version=catalog['version'])
        known = ['fr-bonjour', 'fr-je', 'fr-il', 'fr-merci', 'fr-mais', 'fr-oui', 'fr-non']
        learner['items'] = [{'item_id': item_id, 'introduced_count': 1,
                             'last_completed_book_id': 'earlier-book'} for item_id in known]
        book = fixture_source()
        book['chapters'][0]['units'][0]['text'] = 'שלום אני הוא תודה אבל כן לא. ' * 12
        book['source_hash'] = source_hash(book)
        plan = plan_book(book, learner, catalog)[0]
        self.assertTrue(set(known) <= set(plan['review_item_ids']))
        self.assertGreater(len(plan['review_item_ids']), plan['limits']['new_items_per_chunk'])
        self.assertLessEqual(len(plan['new_item_ids']), plan['limits']['new_items_per_chunk'])
        projected = deepcopy(learner)
        projected['items'][0]['introduced_count'] = 4
        later = replan_chunk(plan, projected, catalog)
        self.assertGreater(later['review_targets']['fr-bonjour']['target_share'],
                           plan['review_targets']['fr-bonjour']['target_share'])
        self.assertNotEqual(plan['plan_id'], later['plan_id'])
        prompt, _ = build_request(later, catalog)
        self.assertIn('review_targets', prompt)
        self.assertIn('Already\nencountered words do not consume', prompt)

    def test_catalog_extensions_have_no_500_item_ceiling(self):
        cat = load_catalog()
        extended = deepcopy(cat)
        extra = deepcopy(next(item for item in cat['items'] if item['kind'] == 'word'))
        extra.update({'item_id': 'fr-future-501', 'lemma': 'papillon', 'forms': ['papillon'],
                      'sense_he': 'פרפר', 'priority_tier': 1000, 'prerequisite_ids': []})
        extended['items'].append(extra)
        validate_catalog(extended)
        book = fixture_source()
        book['chapters'][0]['units'][0]['text'] = 'פרפר צבעוני עף בשמיים. ' * 12
        book['source_hash'] = source_hash(book)
        plan = plan_book(book, new_learner(), extended)[0]
        self.assertIn(extra['item_id'], plan['selected_item_ids'])

    def test_known_density_can_grow_but_new_density_is_still_bounded(self):
        cat, plan = small_catalog(), small_plan()
        plan.update({'policy_version': 'learning-policy@2', 'support_mode': 'context',
                     'new_item_ids': [], 'review_item_ids': ['fr-maison'],
                     'selected_item_ids': ['fr-maison'],
                     'review_targets': {'fr-maison': {'seen_count': 3, 'target_share': .85}}})
        plan['limits']['max_foreign_share'] = .1
        _, input_hash = build_request(plan, cat)
        chunk, _ = parse_response(valid_payload(), plan, cat, input_hash)
        self.assertEqual(chunk['prompt_version'], 'learning-generation@2')
        # One known replacement / four words exceeds10%, but introduces nothing new.
        plan.update({'review_item_ids': [], 'review_targets': {}, 'new_item_ids': ['fr-maison']})
        _, input_hash = build_request(plan, cat)
        with self.assertRaises(LearningError):
            parse_response(valid_payload(), plan, cat, input_hash)


class CumulativeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = LearningService(Path(self.temp.name))
        self.service._add_source(source())
        self.adapter = Adapter(self.service)

    def prepare(self):
        return self.service.start('book-one', 1, configuration(), self.adapter.factory, background=False)

    def test_repeated_accepted_occurrences_drive_later_chapters_and_next_book(self):
        class RepeatingAdapter(Adapter):
            def __init__(self, service):
                super().__init__(service)
                self.final_plans = []

            def generate(self, prompt, model):
                result = super().generate(prompt, model)
                job = next(j for j in self.service._data['jobs'].values() if j['status'] == 'preparing')
                plan = deepcopy(job['current_plan'])
                self.final_plans.append(plan)
                text = next(unit['text'] for unit in plan['units'] if unit['kind'] == 'paragraph')
                matches = list(re.finditer('שלום', text))
                target = plan.get('review_targets', {}).get('fr-bonjour', {}).get('target_share', .2)
                payload = json.loads(result.text)
                template = payload['edits'][0]
                payload['edits'] = [{**template, 'start': match.start(), 'end': match.end()}
                                    for match in matches[:math.ceil(len(matches) * target)]]
                payload['recap']['vocabulary'][0]['edit_indexes'] = list(range(len(payload['edits'])))
                return replace(result, text=json.dumps(payload, ensure_ascii=False))

        self.service._add_source(source('cumulative-book', chapters=3))
        adapter = RepeatingAdapter(self.service)
        ready = self.service.start('cumulative-book', 1, configuration(), adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.final_plans[1]['review_targets']['fr-bonjour']['seen_count'], 3)
        self.assertEqual(adapter.final_plans[2]['review_targets']['fr-bonjour']['seen_count'], 14)
        self.assertGreater(adapter.final_plans[2]['review_targets']['fr-bonjour']['target_share'],
                           adapter.final_plans[1]['review_targets']['fr-bonjour']['target_share'])
        counts = [len(chunk['edits']) for chunk in self.service.store.get_prepared(ready['session_id'])['chunks']]
        self.assertEqual(counts, [3, 11, 12])
        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-cumulative')
        self.assertEqual(self.service.store.get_learner()['items'][0]['introduced_count'], 26)
        next_book = self.prepare()
        plan = self.service._data['jobs'][next_book['session_id']]['plans'][0]
        self.assertEqual(plan['review_targets']['fr-bonjour']['seen_count'], 26)

    def test_prepared_unread_is_not_displayed_as_encountered(self):
        self.service._add_source(source('book-many', chapters=2))
        ready = self.service.start('book-many', 1, configuration(), self.adapter.factory, background=False)
        progress = self.service.summary()['progress']
        self.assertEqual(progress['completed_items'], [])
        self.assertEqual(progress['active_book']['read_items'], [])
        self.service.cursor(ready['session_id'], 0)
        row = self.service.summary()['progress']['active_book']['read_items'][0]
        self.assertEqual(row['foreign'], 'bonjour')
        self.assertEqual(row['encounters'], 1)
        self.service.cursor(ready['session_id'], 1)
        self.service.cursor(ready['session_id'], 0)
        self.assertEqual(self.service.summary()['progress']['active_book']['read_items'][0]['encounters'], 2)
        self.assertEqual(self.service.summary()['progress']['completed_word_count'], 0)
        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-many')
        progress = self.service.summary()['progress']
        self.assertIsNone(progress['active_book'])
        self.assertEqual(progress['completed_word_count'], 1)
        self.assertEqual(progress['completed_items'][0]['encounters'], 2)
        self.assertEqual(progress['initial_word_goal'], 500)

    def test_reader_uses_context_even_for_legacy_support(self):
        ready = self.prepare()
        session = self.service.store.get_session(ready['session_id'])
        session['support_mode'] = 'inline'
        self.service.store.update_session(session)
        fragment = self.service.reader(ready['session_id'])['html']
        self.assertIn('bonjour', fragment)
        self.assertNotIn('learning-gloss-inline', fragment)
        self.assertNotIn('data-gloss-he', fragment)
        self.assertNotIn('role="button"', fragment)

    def test_inactive_catalog_upgrade_preserves_history_and_legacy_catalog(self):
        learner = self.service.store.get_learner()
        learner.update({'catalog_version': 'fr-common@1', 'support_mode': 'inline',
                        'items': [{'item_id': 'fr-bonjour', 'introduced_count': 9,
                                   'last_completed_book_id': 'old-book'}]})
        self.service.store.save_learner(learner)
        ready = self.prepare()
        upgraded = self.service.store.get_learner()
        self.assertEqual(upgraded['catalog_version'], 'fr-common@2')
        self.assertEqual(upgraded['support_mode'], 'context')
        self.assertEqual(upgraded['items'], learner['items'])
        self.assertEqual(ready['base_learner_revision'], learner['revision'] + 1)
        self.assertEqual(load_catalog(version='fr-common@1')['version'], 'fr-common@1')

    def test_click_gloss_is_display_only_and_requires_boolean_opt_in(self):
        ready = self.prepare()
        before = self.service.store.get_prepared(ready['session_id'])
        calls = self.adapter.calls
        fragment = self.service.reader(ready['session_id'], gloss_on_click=True)['html']
        self.assertIn('learning-foreign-click', fragment)
        self.assertIn('aria-controls="gloss-popup"', fragment)
        self.assertNotIn('learning-gloss-inline', fragment)
        self.assertNotIn('aria-label="שלום"', fragment)
        self.assertNotIn('data-gloss-he', self.service.reader(ready['session_id'])['html'])
        self.assertEqual(self.adapter.calls, calls)
        self.assertEqual(self.service.store.get_prepared(ready['session_id']), before)
        with self.assertRaises(LearningError):
            self.service.reader(ready['session_id'], gloss_on_click='true')


if __name__ == '__main__':
    unittest.main()
