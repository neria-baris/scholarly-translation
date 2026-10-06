"""Five-language lifecycle fixtures; one controlled fake call per chunk."""
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest

from scholarly_translation.learning_contracts import LearningError, fixture_source, source_hash
from scholarly_translation.learning_service import LearningService
from scholarly_translation.model_adapter import TextGenerationResult
from test_learning_integration import configuration

FORMS = {'fr': 'papillon', 'de': 'Schmetterling', 'es': 'mariposa',
         'yi': 'פֿלאַטערל', 'it': 'farfalla'}


def butterfly_book(book_id='butterflies', chapters=2):
    book = fixture_source(book_id)
    book['chapters'] = [{'chapter_id': f'chapter-{i}', 'title': f'פרק {i + 1}', 'units': [
        {'unit_id': f'unit-{i}', 'kind': 'paragraph', 'text': 'פרפר צבעוני עף מעל הפרחים בשדה. ' * 20}]} for i in range(chapters)]
    book['source_hash'] = source_hash(book)
    return book


class ProposalAdapter:
    def __init__(self, service, pause=False):
        self.service, self.pause = service, pause
        self.calls, self.roles, self.plans = 0, [], []

    def factory(self, role, request):
        self.roles.append(role)
        return self

    def generate(self, prompt, model):
        self.calls += 1
        job = next(job for job in self.service._data['jobs'].values() if job['status'] == 'preparing')
        plan = job['current_plan']
        self.plans.append(deepcopy(plan))
        language = self.service.store.get_session(job['session_id'])['language']
        surface = FORMS[language]
        known = next((row['item'] for row in job['projected'].get('vocabulary', [])
                      if row['item']['lemma'] == surface), None)
        local_id = known['item_id'] if known else 'new-butterfly'
        definitions = [] if known else [{'item_id': local_id, 'kind': 'word', 'lemma': surface,
                                        'sense_he': 'פרפר', 'forms': [surface], 'explanation_he': ''}]
        unit = next(unit for unit in plan['units'] if unit['kind'] == 'paragraph')
        matches = list(re.finditer('פרפר', unit['text']))
        if not known:
            matches = matches[:1]
        edits = [{'unit_id': unit['unit_id'], 'start': match.start(), 'end': match.end(),
                  'original': 'פרפר', 'replacement': surface, 'item_ids': [local_id],
                  'grammar_ids': [], 'gloss_he': 'פרפר'} for match in matches]
        payload = {'response_version': 1, 'plan_id': plan['plan_id'], 'introduced_items': definitions,
                   'edits': edits, 'recap': {'vocabulary': [
                       {'item_id': local_id, 'gloss_he': 'פרפר', 'edit_indexes': list(range(len(edits)))}],
                       'grammar': []}, 'warnings': []}
        if self.pause:
            self.service.pause(job['session_id'])
        return TextGenerationResult(status='completed', text=json.dumps(payload, ensure_ascii=False),
                                    token_usage={'input': 100, 'output': 100, 'cached': 0, 'reasoning': 0},
                                    observed_model=model, duration_seconds=0)


class MultilingualLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = LearningService(self.root)
        self.service._add_source(butterfly_book())

    def prepare(self, adapter, book_id='butterflies'):
        session = self.service.start(book_id, 1, configuration(), adapter.factory, background=False)
        self.assertEqual(session['status'], 'ready', self.service._data['jobs'][session['session_id']].get('error_code'))
        return session

    def test_five_languages_grow_recur_and_keep_separate_history(self):
        for language, form in FORMS.items():
            with self.subTest(language=language):
                summary = self.service.select_language(language)
                self.assertTrue(all(row['available'] for row in summary['languages']))
                self.assertEqual(summary['progress']['completed_word_count'], 0)
                adapter = ProposalAdapter(self.service)
                session = self.prepare(adapter)
                self.assertEqual(adapter.calls, 2)
                self.assertEqual(adapter.roles, ['translator', 'translator'])
                chunks = self.service.store.get_prepared(session['session_id'])['chunks']
                item_id = chunks[0]['introduced_items'][0]['item_id']
                self.assertTrue(item_id.startswith(language + '-learn-'))
                self.assertIn(item_id, adapter.plans[1]['review_item_ids'])
                self.assertEqual(len(chunks[1]['edits']), 20)
                self.assertEqual(self.service.store.get_learner(language)['items'], [])
                self.assertEqual(self.service.summary()['progress']['active_book']['read_items'], [])
                self.service.cursor(session['session_id'], 0)
                current = self.service.summary()['progress']['active_book']['read_items'][0]
                self.assertEqual((current['foreign'], current['hebrew']), (form, 'פרפר'))
                if language == 'fr':
                    self.assertGreater(self.service.summary()['progress']['catalog_word_count'], 500)
                reader = self.service.reader(session['session_id'], gloss_on_click=True)
                self.assertEqual(reader['language'], language)
                self.assertIn(form, reader['html'])
                if language == 'yi':
                    self.assertIn('lang="yi" dir="rtl"', reader['html'])
                self.service.complete(session['session_id'], session['prepared_hash'], 'complete-' + language)
                before = self.service.store.get_learner(language)
                self.service.complete(session['session_id'], session['prepared_hash'], 'complete-' + language)
                self.assertEqual(self.service.store.get_learner(language), before)
                self.assertEqual(before['items'][0]['introduced_count'], 21)
                self.assertEqual(before['vocabulary'][0]['item']['item_id'], item_id)
        reopened = LearningService(self.root)
        reopened.select_language('de')
        self.assertEqual(reopened.summary()['progress']['completed_items'][0]['foreign'], FORMS['de'])
        reopened._add_source(butterfly_book('next-book', 1))
        next_adapter = ProposalAdapter(reopened)
        next_session = reopened.start('next-book', 1, configuration(), next_adapter.factory, background=False)
        self.assertEqual(next_session['status'], 'ready')
        self.assertEqual(next_adapter.calls, 1)
        self.assertEqual(next_adapter.plans[0]['review_targets'][
            reopened.store.get_learner('de')['items'][0]['item_id']]['seen_count'], 21)

    def test_active_guard_and_language_selection_persist_without_generation(self):
        self.service.select_language('es')
        self.assertEqual(LearningService(self.root).summary()['selected_language'], 'es')
        adapter = ProposalAdapter(self.service)
        self.prepare(adapter)
        with self.assertRaises(LearningError):
            self.service.select_language('yi')
        self.assertEqual(adapter.calls, 2)
        with self.assertRaises(LearningError):
            self.service.select_language('unknown')

    def test_pause_restart_retains_definitions_and_abandon_does_not_promote(self):
        self.service.select_language('yi')
        adapter = ProposalAdapter(self.service, pause=True)
        paused = self.service.start('butterflies', 1, configuration(), adapter.factory, background=False)
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(adapter.calls, 1)
        reopened = LearningService(self.root)
        second = ProposalAdapter(reopened)
        ready = reopened.resume(paused['session_id'], second.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(second.calls, 1)
        self.assertTrue(second.plans[0]['review_item_ids'])
        reopened.complete(ready['session_id'], ready['prepared_hash'], 'complete-restart')
        self.assertEqual(reopened.store.get_learner('yi')['items'][0]['introduced_count'], 21)
        reopened.select_language('es')
        stopping = ProposalAdapter(reopened, pause=True)
        partial = reopened.start('butterflies', 1, configuration(), stopping.factory, background=False)
        reopened.abandon(partial['session_id'])
        self.assertEqual(reopened.store.get_learner('es')['items'], [])
        self.assertEqual(reopened.store.get_learner('es').get('vocabulary', []), [])

    def test_received_grammar_is_archived_with_the_actual_examples_before_completion(self):
        class GrammarAdapter(ProposalAdapter):
            def generate(self, prompt, model):
                result = super().generate(prompt, model)
                raw = json.loads(result.text)
                job = next(job for job in self.service._data['jobs'].values() if job['status'] == 'preparing')
                known = next((row['item'] for row in job['projected'].get('vocabulary', [])
                              if row['item']['kind'] == 'grammar'), None)
                item_id = known['item_id'] if known else 'new-capitalization'
                explanation = 'בגרמנית שמות העצם נכתבים באות גדולה בתחילת המילה.'
                if not known:
                    raw['introduced_items'].append({'item_id': item_id, 'kind': 'grammar',
                        'lemma': 'Großschreibung', 'sense_he': 'אות גדולה בשמות עצם',
                        'forms': ['Schmetterling'], 'explanation_he': explanation})
                for edit in raw['edits']:
                    edit['grammar_ids'] = [item_id]
                raw['recap']['grammar'] = [{'item_id': item_id, 'explanation_he': explanation,
                                           'edit_indexes': list(range(len(raw['edits'])))}]
                from dataclasses import replace
                return replace(result, text=json.dumps(raw, ensure_ascii=False))
        self.service.select_language('de')
        self.service.set_effort('3')
        adapter = GrammarAdapter(self.service)
        ready = self.prepare(adapter)
        received = self.service.reader(ready['session_id'])
        self.assertTrue(received['recap']['grammar'])
        paths = list((self.root / 'personal' / 'de' / 'grammar').glob('*.json'))
        self.assertEqual(len(paths), 1)
        archive = json.loads(paths[0].read_text(encoding='utf-8'))
        self.assertEqual(archive['recap']['grammar'], received['recap']['grammar'])
        example = archive['recap']['grammar'][0]['examples'][0]
        self.assertEqual((example['foreign'], example['hebrew']), ('Schmetterling', 'פרפר'))
        self.assertEqual(self.service.store.get_learner('de')['items'], [])
        self.service.reader(ready['session_id'])
        self.assertEqual(len(list(paths[0].parent.glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
