import unittest

from scholarly_translation.learning.catalog import load_catalog
from scholarly_translation.learning.contracts import LearningError
from scholarly_translation.learning.vocabulary import proposal_item
from scholarly_translation.learning.lesson import _example


class ArabicTests(unittest.TestCase):
    def test_starter_provenance_and_native_script(self):
        catalog = load_catalog('ar')
        self.assertEqual(catalog['version'], 'ar-seed@1')
        self.assertIn('not corpus frequency', catalog['provenance']['basis'])
        self.assertIn('كتاب', [row['word'] for row in catalog['frequency_seed']])
        raw = {'item_id': 'new-book', 'kind': 'word', 'lemma': 'كِتاب',
               'sense_he': 'ספר', 'forms': ['كِتاب'], 'explanation_he': ''}
        self.assertTrue(proposal_item(raw, 'ar', 1)['item_id'].startswith('ar-learn-'))
        for foreign in ('kitab', 'ספר', 'كتابbook'):
            with self.subTest(foreign=foreign), self.assertRaises(LearningError):
                proposal_item({**raw, 'lemma': foreign, 'forms': [foreign]}, 'ar', 1)

    def test_arabic_sentence_examples_require_arabic_script(self):
        raw = {'unit_id': 'unit-one', 'hebrew': 'ספר', 'foreign': 'كتاب'}
        self.assertIsNotNone(_example(raw, {}, {'unit-one': 'ספר'}, 'ar'))
        self.assertIsNone(_example({**raw, 'foreign': 'kitab'}, {}, {'unit-one': 'ספר'}, 'ar'))
