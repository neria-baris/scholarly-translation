"""Proposal admission, grounding, legacy prompts and immutable definitions."""
from copy import deepcopy
import json
import unittest

from scholarly_translation.learning_catalog import load_catalog
from scholarly_translation.learning_contracts import LearningError, new_learner, validate_learner
from scholarly_translation.learning_generation import build_request, parse_response
from scholarly_translation.learning_vocabulary import effective_catalog
from test_learning_generation import catalog, plan


class OpenVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog()
        self.plan = plan()
        self.plan.update({'policy_version': 'learning-policy@3', 'support_mode': 'context',
                          'selected_item_ids': [], 'new_item_ids': [], 'review_item_ids': [], 'review_targets': {}})
        self.prompt, self.hash = build_request(self.plan, self.catalog)
        self.payload = {'response_version': 1, 'plan_id': self.plan['plan_id'],
            'introduced_items': [{'item_id': 'new-home', 'kind': 'word', 'lemma': 'maisonnette',
                'sense_he': 'בית קטן', 'forms': ['maisonnette'], 'explanation_he': ''}],
            'edits': [{'unit_id': 'unit-one', 'start': 10, 'end': 14, 'original': 'בבית',
                      'replacement': 'maisonnette', 'item_ids': ['new-home'], 'grammar_ids': [], 'gloss_he': 'בית קטן'}],
            'recap': {'vocabulary': [{'item_id': 'new-home', 'gloss_he': 'בית קטן', 'edit_indexes': [0]}], 'grammar': []},
            'warnings': []}

    def parse(self):
        return parse_response(json.dumps(self.payload), self.plan, self.catalog, self.hash)

    def test_stable_ids_grounded_recap_and_definition_hash(self):
        chunk, recap = self.parse()
        item_id = chunk['introduced_items'][0]['item_id']
        self.assertTrue(item_id.startswith('fr-learn-'))
        self.assertEqual(chunk['edits'][0]['item_ids'], [item_id])
        self.assertEqual(recap['vocabulary'][0]['item_id'], item_id)
        self.payload['introduced_items'][0]['item_id'] = 'another-ref'
        self.payload['edits'][0]['item_ids'] = ['another-ref']
        self.payload['recap']['vocabulary'][0]['item_id'] = 'another-ref'
        self.assertEqual(self.parse()[0]['content_hash'], chunk['content_hash'])
        self.payload['introduced_items'][0]['sense_he'] = 'בית זעיר'
        self.assertNotEqual(self.parse()[0]['content_hash'], chunk['content_hash'])

    def test_invalid_proposals_never_enter_history(self):
        original = deepcopy(self.payload)
        # The only edit depends on the broken proposal or source: nothing survives.
        rejected = [lambda p: p['introduced_items'][0].update(sense_he='English'),
                    lambda p: p['introduced_items'][0].update(forms=['שלום']),
                    lambda p: p['introduced_items'][0].update(item_id='fr-maison'),
                    lambda p: p['edits'][0].update(item_ids=['undefined']),
                    lambda p: p['edits'][0].update(original='not source')]
        for mutation in rejected:
            with self.subTest(mutation=mutation):
                self.payload = deepcopy(original)
                mutation(self.payload)
                with self.assertRaises(LearningError):
                    self.parse()
        # A duplicate or unused proposal is dropped; the rest of the answer stands.
        for mutation in (lambda p: p['introduced_items'].append(deepcopy(p['introduced_items'][0])),
                         lambda p: p.update(edits=[])):
            with self.subTest(mutation=mutation):
                self.payload = deepcopy(original)
                mutation(self.payload)
                report = {}
                chunk, _ = parse_response(json.dumps(self.payload), self.plan, self.catalog, self.hash,
                                          report=report)
                self.assertEqual(len(chunk.get('introduced_items', [])), len(chunk['edits']))
                self.assertTrue(report['dropped'])

    def test_new_density_and_combined_quotas_trim_edits(self):
        self.plan['limits']['max_foreign_share'] = .01
        chunk, _ = self.parse()
        self.assertEqual((chunk['edits'], chunk.get('introduced_items')), ([], None))
        self.plan['limits']['max_foreign_share'] = .5
        self.plan['limits']['new_items_per_chunk'] = 1
        self.payload['introduced_items'].append({'item_id': 'new-grammar', 'kind': 'grammar', 'lemma': 'maisonnette',
             'sense_he': 'סיומת הקטנה', 'forms': ['maisonnette'], 'explanation_he': 'במילה זו מודגמת צורת הקטנה.'})
        self.payload['edits'][0]['grammar_ids'] = ['new-grammar']
        report = {}
        chunk, _ = parse_response(json.dumps(self.payload), self.plan, self.catalog, self.hash, report=report)
        self.assertEqual(chunk['edits'], [])
        self.assertIn('quota:new_items_per_chunk', report['dropped'])
        self.plan['limits']['new_items_per_chunk'] = 3
        chunk, recap = self.parse()
        self.assertEqual(len(chunk['introduced_items']), 2)
        self.assertTrue(recap['grammar'])
        self.payload['introduced_items'][1]['forms'] = ['autre']
        with self.assertRaises(LearningError):
            self.parse()

    def test_conflicting_definitions_are_not_overwritten(self):
        chunk, _ = self.parse()
        enriched = effective_catalog(self.catalog, [], [chunk])
        self.assertEqual(enriched['items'][-1], chunk['introduced_items'][0])
        bad = deepcopy(chunk)
        bad['introduced_items'][0]['sense_he'] = 'הגדרה שונה'
        with self.assertRaises(LearningError):
            effective_catalog(enriched, [], [bad])
        learner = new_learner()
        learner['vocabulary'] = [{'item': chunk['introduced_items'][0], 'origin': {
            key: chunk[key] for key in ('provider', 'model', 'prompt_version', 'input_hash')}}]
        validate_learner(learner)
        learner['language'] = 'de'
        with self.assertRaises(LearningError):
            validate_learner(learner)

    def test_frequency_hints_are_bounded_and_legacy_assets_unchanged(self):
        cat = load_catalog('de')
        self.assertEqual(len(cat['frequency_seed']), 500)
        self.assertEqual(cat['items'], [])
        prompt, _ = build_request(self.plan, cat)
        self.assertIn('"response_version":1', prompt)
        self.assertIn('"introduced_items":[', prompt)
        self.assertIn('"recap":{', prompt)
        hints = json.loads(prompt.split('FREQUENCY_HINTS:\n```json\n')[-1].split('\n```')[0])
        self.assertEqual(len(hints), 100)
        for version in (1, 2):
            old_plan = plan()
            if version == 2:
                old_plan.update({'policy_version': 'learning-policy@2', 'selected_item_ids': ['fr-maison'],
                                 'new_item_ids': ['fr-maison']})
            prompt, old_hash = build_request(old_plan, self.catalog)
            self.assertNotIn('FREQUENCY_HINTS:', prompt)
            self.payload['plan_id'] = old_plan['plan_id']
            with self.assertRaises(LearningError):
                parse_response(json.dumps(self.payload), old_plan, self.catalog, old_hash)


if __name__ == '__main__':
    unittest.main()
