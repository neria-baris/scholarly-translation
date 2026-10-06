import copy
import json
import unittest
from scholarly_translation import learning_contracts as c


class LearningContractsTests(unittest.TestCase):
    def test_source_roundtrip_and_hash(self):
        source = c.fixture_source()
        self.assertEqual(c.validate_source(json.loads(json.dumps(source))), source)
        changed = copy.deepcopy(source)
        changed['chapters'][0]['units'][0]['text'] += ' שינוי'
        with self.assertRaises(c.LearningError):
            c.validate_source(changed)

    def test_duplicates_and_unknown_fields_refused(self):
        source = c.fixture_source()
        source['chapters'][0]['units'] *= 2
        source['source_hash'] = c.source_hash(source)
        with self.assertRaises(c.LearningError):
            c.validate_source(source)
        learner = c.new_learner()
        learner['api_key'] = 'not-a-real-key'
        with self.assertRaises(c.LearningError):
            c.validate_learner(learner)

    def test_unicode_and_initial_state(self):
        self.assertEqual(c.word_count('פֿון אַ הויז'), 3)
        state = c.new_learner('yi', catalog_version='yi-common@1')
        self.assertEqual(state['items'], [])
        self.assertEqual(state['revision'], 0)
        with self.assertRaises(c.LearningError):
            c.check_id('../escape')

    def test_unsupported_language_and_schema(self):
        with self.assertRaises(c.LearningError):
            c.new_learner('unknown')
        state = c.new_learner()
        state['schema_version'] = True
        with self.assertRaises(c.LearningError):
            c.validate_learner(state)


if __name__ == '__main__':
    unittest.main()
