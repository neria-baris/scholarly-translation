import json
from pathlib import Path
import tempfile
import unittest

from scholarly_translation.learning_archive import _dictionary, _dictionary_md
from scholarly_translation.learning_contracts import LearningError, validate_generated
from scholarly_translation.learning_dictionary import dictionary_view, woven_sentence
from scholarly_translation.learning_generation import build_request, parse_response
from scholarly_translation.learning_service import LearningService

from test_learning_generation import catalog, plan, valid_payload
from test_learning_integration import Adapter, configuration, is_lesson, source

MAISON = {'item_id': 'fr-maison', 'part_of_speech': 'noun', 'gender': 'feminine', 'senses_he': ['בית', 'משפחה, שושלת'],
          'forms': [{'label_he': 'יחיד', 'form': 'la maison'}, {'label_he': 'רבים', 'form': 'les maisons'}],
          'notes_he': 'à la maison — בבית'}
BONJOUR = {'item_id': 'fr-bonjour', 'part_of_speech': 'interjection', 'gender': None, 'senses_he': ['שלום'],
           'forms': [], 'notes_he': ''}


def with_entries(entries, payload=None):
    data = json.loads(payload or valid_payload())
    data['dictionary_entries'] = entries
    return json.dumps(data, ensure_ascii=False)


class DictionaryParsingTests(unittest.TestCase):
    def test_request_lists_needed_items_only_when_enabled(self):
        plain, plain_hash = build_request(plan(), catalog())
        prompt, prompt_hash = build_request(plan(), catalog(), dictionary_needed=['fr-maison'])
        self.assertNotIn('DICTIONARY_NEEDED', plain)
        self.assertIn('DICTIONARY_NEEDED', prompt)
        self.assertIn('"fr-maison"', prompt)
        self.assertIn('part_of_speech', prompt)
        self.assertNotEqual(plain_hash, prompt_hash)

    def test_entry_for_used_item_is_kept_and_versioned(self):
        prompt, input_hash = build_request(plan(), catalog(), dictionary_needed=['fr-maison'])
        chunk, _ = parse_response(with_entries([MAISON]), plan(), catalog(), input_hash, dictionary_known=[])
        self.assertEqual(chunk['dictionary_entries'], [MAISON])
        self.assertTrue(chunk['prompt_version'].endswith('+learning-dictionary@1'))

    def test_unused_known_grammar_and_invalid_entries_are_dropped_without_rejecting_the_chunk(self):
        _, input_hash = build_request(plan(), catalog(), dictionary_needed=[])
        cases = [
            dict(MAISON, item_id='fr-chat'),                                   # not used by an edit
            dict(MAISON, item_id='fr-le'),                                     # grammar item
            dict(MAISON, part_of_speech='noun-ish'),
            dict(MAISON, senses_he=['house']),                                 # no Hebrew meaning
            dict(MAISON, forms=[{'label_he': 'רבים', 'form': 'בתים'}]),        # not French
            dict(MAISON, forms=[{'label_he': 'רבים', 'form': '<b>maisons</b>'}]),
        ]
        for entry in cases:
            with self.subTest(entry=entry):
                chunk, _ = parse_response(with_entries([entry]), plan(), catalog(), input_hash, dictionary_known=[])
                self.assertNotIn('dictionary_entries', chunk)
        chunk, _ = parse_response(with_entries([MAISON]), plan(), catalog(), input_hash, dictionary_known=['fr-maison'])
        self.assertNotIn('dictionary_entries', chunk)

    def test_field_is_refused_when_not_enabled_and_contract_checks_usage(self):
        _, input_hash = build_request(plan(), catalog())
        with self.assertRaises(LearningError):
            parse_response(with_entries([MAISON]), plan(), catalog(), input_hash)
        _, input_hash = build_request(plan(), catalog(), dictionary_needed=[])
        chunk, _ = parse_response(with_entries([MAISON]), plan(), catalog(), input_hash, dictionary_known=[])
        chunk['dictionary_entries'][0]['item_id'] = 'fr-chat'
        with self.assertRaises(LearningError):
            validate_generated(chunk)

    def test_view_merges_first_entry_and_woven_examples(self):
        text = 'היום הלכתי לבית שלי. אחר כך נחתי.'
        start = text.index('לבית') + 1
        plan_row = {'chapter_id': 'c1', 'units': [{'unit_id': 'u1', 'kind': 'paragraph', 'text': text}]}
        chunk = {'edits': [{'unit_id': 'u1', 'start': start, 'end': start + 3, 'original': 'בית',
                            'replacement': 'maison', 'item_ids': ['fr-maison'], 'grammar_ids': [], 'gloss_he': 'בית'}],
                 'dictionary_entries': [MAISON]}
        later = dict(chunk, dictionary_entries=[dict(MAISON, notes_he='אחר')])
        entries, examples = dictionary_view([('ספר א', [plan_row], [chunk], None),
                                             ('ספר ב', [plan_row], [later], {'c2'})])
        self.assertEqual(entries['fr-maison']['notes_he'], MAISON['notes_he'])
        self.assertEqual(examples['fr-maison'], [{'foreign': 'maison', 'sentence': 'היום הלכתי לmaison שלי.',
                                                  'book_title': 'ספר א'}])
        self.assertEqual(woven_sentence(text, start, start + 3, 'maison'), 'היום הלכתי לmaison שלי.')

    def test_personal_dictionary_files_include_the_entry(self):
        entry = {k: v for k, v in MAISON.items() if k != 'item_id'}
        record = _dictionary('fr', {'completed_items': [
            {'item_id': 'fr-maison', 'kind': 'word', 'foreign': 'maison', 'hebrew': 'בית', 'encounters': 2,
             'last_book_title': 'ספר', 'entry': entry,
             'examples': [{'foreign': 'maison', 'sentence': 'הלכתי לmaison.', 'book_title': 'ספר'}]}],
            'active_book': None})
        self.assertEqual(record['saved_items'][0]['entry'], entry)
        text = _dictionary_md(record)
        self.assertIn('שם עצם, נקבה', text)
        self.assertIn('רבים: les maisons', text)
        self.assertIn('דוגמה (ספר): הלכתי לmaison.', text)
        with self.assertRaises(LearningError):
            _dictionary('fr', {'completed_items': [dict(record['saved_items'][0], entry={'senses_he': []})],
                               'active_book': None})


class EntryAdapter(Adapter):
    """Fake provider that writes an entry for every item listed as needed."""
    def __init__(self, service):
        super().__init__(service)
        self.needed = []

    def generate(self, prompt, model):
        result = super().generate(prompt, model)
        if is_lesson(prompt) or 'DICTIONARY_NEEDED:' not in prompt:
            return result
        start = prompt.index('DICTIONARY_NEEDED:\n```json\n') + len('DICTIONARY_NEEDED:\n```json\n')
        needed = json.loads(prompt[start:prompt.index('\n```', start)])
        self.needed.append(needed)
        data = json.loads(result.text)
        data['dictionary_entries'] = [BONJOUR] if 'fr-bonjour' in needed else []
        return type(result)(**{**result.__dict__, 'text': json.dumps(data, ensure_ascii=False)})


class DictionaryServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = LearningService(Path(temporary.name))
        self.service._add_source(source())
        self.service._add_source(source('book-two'))

    def test_entry_once_per_item_reaches_progress_and_notebook(self):
        adapter = EntryAdapter(self.service)
        ready = self.service.start('book-one', 1, configuration(), adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(len(adapter.needed), 1)  # One chunk call; every selected word still lacks an entry.
        self.assertIn('fr-bonjour', adapter.needed[0])
        self.service.cursor(ready['session_id'], 0)
        row = next(r for r in self.service.summary()['progress']['active_book']['read_items']
                   if r['item_id'] == 'fr-bonjour')
        self.assertEqual(row['entry']['senses_he'], ['שלום'])
        self.assertIn('bonjour', row['examples'][0]['sentence'])
        notebook = self.service.grammar_notebook()
        self.assertEqual(len(notebook['books']), 1)
        self.assertEqual(notebook['books'][0]['chapters'][0]['chapter_index'], 0)

        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-one')
        saved = next(r for r in self.service.summary()['progress']['completed_items'] if r['item_id'] == 'fr-bonjour')
        self.assertEqual(saved['entry']['part_of_speech'], 'interjection')
        archive = Path(self.service.summary()['personal_archive']['path']) / 'dictionary.md'
        self.assertIn('מילת קריאה', archive.read_text(encoding='utf-8'))

        second = EntryAdapter(self.service)
        self.service.start('book-two', 1, configuration(), second.factory, background=False)
        self.assertTrue(second.needed)
        self.assertTrue(all('fr-bonjour' not in needed for needed in second.needed))

    def test_jobs_without_the_flag_send_the_previous_prompt(self):
        adapter = EntryAdapter(self.service)
        stopped = self.service.start('book-one', .000001, configuration(), adapter.factory, background=False)
        sid = stopped['session_id']
        del self.service._data['jobs'][sid]['dictionary']
        ready = self.service.resume(sid, adapter.factory, budget_usd=1, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.needed, [])
        chunk = self.service.store.get_prepared(sid)['chunks'][0]
        self.assertNotIn('dictionary_entries', chunk)
        self.assertNotIn('+learning-dictionary', chunk['prompt_version'])


if __name__ == '__main__':
    unittest.main()
