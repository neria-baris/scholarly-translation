"""Frequency coverage, compatibility and honest eligibility of the teaching catalog."""
import json
from pathlib import Path
import unittest

from scholarly_translation.learning_catalog import load_catalog
from scholarly_translation.learning_contracts import new_learner, fixture_source, source_hash
from scholarly_translation.learning_planner import plan_book

ROOT = Path(__file__).resolve().parent.parent


class ExpandedCatalogTests(unittest.TestCase):
    def test_all_source500_forms_are_present_without_losing_previous_items(self):
        old, current = load_catalog(version='fr-common@1'), load_catalog()
        dataset = json.loads((ROOT / 'prompts/language_learning/wordlists/european_500.json').read_text(encoding='utf-8'))
        forms = {form for item in current['items'] for form in item['forms']}
        self.assertEqual(len(dataset['languages']['fr']['words']), 500)
        self.assertTrue({row['word'] for row in dataset['languages']['fr']['words']} <= forms)
        by_id = {item['item_id']: item for item in current['items']}
        for item in old['items']:
            self.assertEqual(by_id[item['item_id']], item)
        self.assertEqual(current['version'], 'fr-common@2')
        self.assertEqual(sum(item['kind'] == 'word' and item['min_level'] <= 3 for item in current['items']), 500)

    def test_added_meanings_and_frequency_ids_are_not_empty_or_invented_ranks(self):
        current = load_catalog()
        dataset = json.loads((ROOT / 'prompts/language_learning/wordlists/european_500.json').read_text(encoding='utf-8'))
        ranks = {row['rank']: row['word'] for row in dataset['languages']['fr']['words']}
        for item in current['items']:
            self.assertTrue(any('\u0590' <= char <= '\u05ff' for char in item['sense_he']))
            if item['item_id'].startswith('fr-freq-'):
                rank = int(item['item_id'].removeprefix('fr-freq-'))
                self.assertEqual(item['forms'], [ranks[rank]])
                self.assertEqual(item['priority_tier'], rank)
        provenance = ' '.join(current['provenance'].values())
        self.assertIn('CC-BY-SA-4.0', provenance)
        self.assertIn('525f9b560de45753a5ea01069454e72e9aa541c6', provenance)
        self.assertIn('not linguistically reviewed', provenance)

    def test_uncertain_corpus_token_is_retained_but_not_taught_as_a_french_word(self):
        catalog = load_catalog()
        token = next(item for item in catalog['items'] if 'ii' in item['forms'])
        self.assertEqual(token['min_level'], 99)
        book = fixture_source()
        book['chapters'][0]['units'][0]['text'] = 'שתיים בספרות רומיות. ' * 12
        book['source_hash'] = source_hash(book)
        for level in catalog['levels']:
            learner = new_learner()
            learner['level_id'] = level['level_id']
            self.assertNotIn(token['item_id'], plan_book(book, learner, catalog)[0]['selected_item_ids'])


if __name__ == '__main__':
    unittest.main()
