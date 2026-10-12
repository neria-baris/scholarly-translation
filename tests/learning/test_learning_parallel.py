"""Parallel learning through real local service/store, with offline fake adapters."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scholarly_translation.learning.contracts import LearningError, validate_session
from scholarly_translation.learning.service import LearningService
from scholarly_translation.models.adapter import TextGenerationResult
from scholarly_translation.learning.store import LearningStore
from learning.test_learning_integration import configuration, is_lesson, _prompt_block, lesson_reply, source
from learning.test_learning_multilingual import butterfly_book, ProposalAdapter


class PluralAdapter(ProposalAdapter):
    def generate(self, prompt, model):
        result = super().generate(prompt, model)
        if is_lesson(prompt):
            return result
        raw = json.loads(result.text)
        for item in raw.get('introduced_items', []):
            item['lemma'], item['forms'] = 'papillons', ['papillons']
        for edit in raw['edits']:
            edit['replacement'] = 'papillons'
        return replace(result, text=json.dumps(raw, ensure_ascii=False))


class ParallelLearningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = LearningService(self.root)
        for book in ('one', 'two', 'three', 'four'):
            self.service._add_source(butterfly_book(book, 1))

    def start(self, book, adapter=None):
        return self.service.start(book, 1, configuration(),
                                  (adapter or ProposalAdapter(self.service)).factory, background=False)

    def complete(self, session):
        return self.service.complete(session['session_id'], session['prepared_hash'], 'done-' + session['session_id'])

    def test_both_completion_orders_accumulate_and_freeze_sibling(self):
        for order in ((0, 1), (1, 0)):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as directory:
                self.service = LearningService(directory)
                for book in ('one', 'two', 'three'):
                    self.service._add_source(butterfly_book(book, 1))
                first = self.start('one')
                second = self.start('two', PluralAdapter(self.service))
                self.assertEqual(first['starting_learner'], second['starting_learner'])
                sessions = [first, second]
                sibling = sessions[order[1]]
                frozen_job = deepcopy(self.service._data['jobs'][sibling['session_id']])
                frozen_content = self.service.store.get_prepared(sibling['session_id'])
                receipt = self.complete(sessions[order[0]])
                self.assertEqual(receipt, self.complete(sessions[order[0]]))
                self.assertEqual(self.service._data['jobs'][sibling['session_id']], frozen_job)
                self.assertEqual(self.service.store.get_prepared(sibling['session_id']), frozen_content)
                self.assertEqual(self.service.store.get_learner()['active_book_id'], sibling['book_id'])
                self.assertEqual(len(self.service.summary()['progress']['active_books']), 1)
                self.complete(sibling)
                learner = self.service.store.get_learner()
                self.assertEqual(len(learner['vocabulary']), 2)
                self.assertEqual(len(learner['items']), 2)
                self.assertEqual(learner['revision'], 2)
                self.assertEqual(learner['active_session_ids'], [])
                next_session = self.start('three')
                self.assertEqual(next_session['starting_learner']['items'], learner['items'])
                self.assertEqual(next_session['vocabulary'], learner['vocabulary'])
                plan = self.service._data['jobs'][next_session['session_id']]['plans'][0]
                self.assertTrue({i['item_id'] for i in learner['items']} <= set(plan['review_item_ids']))

    def test_progress_dictionary_and_archive_cover_each_active_book(self):
        first = self.start('one')
        second = self.start('two')
        self.service.cursor(first['session_id'], 0)
        self.service.cursor(second['session_id'], 0)
        progress = self.service.summary()['progress']
        self.assertEqual({b['book_id'] for b in progress['active_books']}, {'one', 'two'})
        self.assertTrue(all(b['read_items'] for b in progress['active_books']))
        archive = json.loads((self.root / 'personal/fr/dictionary.json').read_text(encoding='utf-8'))
        self.assertEqual(archive['current_items'][0]['encounters'], 2)
        self.assertEqual(len(archive['current_books']), 2)
        self.complete(first)
        progress = self.service.summary()['progress']
        self.assertEqual(progress['completed_items'][0]['encounters'], 1)
        self.assertEqual(progress['active_books'][0]['read_items'][0]['encounters'], 1)
        self.complete(second)
        learner = self.service.store.get_learner()
        self.assertEqual(len(learner['vocabulary']), 1)  # Same word is unioned.
        self.assertEqual(learner['items'][0]['introduced_count'], 2)

    def test_languages_can_prepare_and_complete_independently(self):
        french = self.start('one')
        french_before = self.service.store.get_learner('fr')
        self.service.select_language('de')
        german = self.start('one')  # Same source, distinct language.
        self.assertEqual(self.service.store.get_learner('fr'), french_before)
        self.complete(german)
        self.assertEqual(self.service.store.get_learner('fr'), french_before)
        self.assertEqual(self.service.summary()['selected_language'], 'de')
        self.service.select_language('fr')
        self.assertEqual(len(self.service.summary()['progress']['active_books']), 1)
        self.complete(french)
        self.assertTrue(all(row['item_id'].startswith('fr-') for row in self.service.store.get_learner('fr')['items']))
        self.assertTrue(all(row['item_id'].startswith('de-') for row in self.service.store.get_learner('de')['items']))

    def test_paused_sibling_resumes_after_completion_and_restart(self):
        self.service._add_source(butterfly_book('long', 2))
        paused = self.start('long', ProposalAdapter(self.service, pause=True))
        first = self.start('one')
        self.complete(first)
        self.service = LearningService(self.root)
        adapter = ProposalAdapter(self.service)
        ready = self.service.resume(paused['session_id'], adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(ready['starting_learner']['items'], [])
        self.complete(ready)
        self.assertEqual(self.service.store.get_learner()['items'][0]['introduced_count'], 22)

    def test_abandon_releases_only_its_own_session_and_rejects_resume(self):
        paused = self.start('one', ProposalAdapter(self.service, pause=True))
        sibling = self.start('two')
        self.service.abandon(paused['session_id'])
        learner = self.service.store.get_learner()
        self.assertEqual(learner['items'], [])
        self.assertEqual(learner['active_session_ids'], [sibling['session_id']])
        with self.assertRaises(LearningError):
            self.service.resume(paused['session_id'], ProposalAdapter(self.service).factory, background=False)
        self.complete(sibling)
        with self.assertRaises(LearningError):
            self.service.complete(sibling['session_id'], sibling['prepared_hash'], 'different-receipt')

    def test_new_book_uses_completed_words_while_older_book_keeps_its_baseline(self):
        first, second = self.start('one'), self.start('two')
        self.complete(first)
        third = self.start('three')
        self.assertEqual(second['starting_learner']['items'], [])
        self.assertEqual(second['vocabulary'], [])
        self.assertEqual(third['starting_learner']['items'][0]['introduced_count'], 1)
        self.assertTrue(third['vocabulary'])
        self.complete(second)
        self.complete(third)
        fourth = self.start('four')
        self.assertEqual(fourth['starting_learner']['items'][0]['introduced_count'], 22)

    def test_legacy_single_active_book_migrates_before_sibling_completion(self):
        legacy = self.start('one')
        learner = self.service.store.get_learner()
        learner.pop('active_session_ids')
        legacy.pop('starting_learner')
        (self.root / 'state/learners/fr.json').write_text(json.dumps(learner), encoding='utf-8')
        (self.root / f"state/sessions/{legacy['session_id']}.json").write_text(json.dumps(legacy), encoding='utf-8')
        self.service = LearningService(self.root)
        sibling = self.start('two')
        self.complete(sibling)
        migrated = self.service.store.get_session(legacy['session_id'])
        self.assertEqual(migrated['starting_learner']['items'], [])
        self.complete(migrated)
        self.assertEqual(self.service.store.get_learner()['items'][0]['introduced_count'], 2)

    def test_crash_between_session_and_job_checkpoint_reconstructs_baseline(self):
        first = self.start('one')
        learner = self.service.store.get_learner()
        second = self.service.store.create_session(self.service.store.get_source('two'), learner)
        self.complete(first)
        self.service = LearningService(self.root)
        job = self.service._data['jobs'][second['session_id']]
        self.assertEqual(job['projected']['items'], [])
        self.assertEqual(job['plans'][0]['base_learner_revision'], second['base_learner_revision'])
        ready = self.service.resume(second['session_id'], ProposalAdapter(self.service).factory,
                                    background=False, budget_usd=1)
        self.assertEqual(ready['status'], 'ready')
        self.complete(ready)

    def test_duplicate_and_delete_guards_apply_to_all_active_sessions(self):
        first, second = self.start('one'), self.start('two')
        for book in ('one', 'two'):
            with self.assertRaises(LearningError):
                self.start(book)
            with self.assertRaises(LearningError):
                self.service.delete_book(book)
        with self.assertRaises(LearningError):
            self.service.set_effort('2')
        self.service.select_language('de')
        self.service.set_effort('2')  # Active French books do not lock German effort.

    def test_parallel_store_creation_and_stale_revision_guard(self):
        store = self.service.store
        learner = store.get_learner()
        with ThreadPoolExecutor(max_workers=2) as pool:
            sessions = list(pool.map(lambda book: store.create_session(store.get_source(book), learner), ('one', 'two')))
        self.assertEqual(len(store.get_learner()['active_session_ids']), 2)
        self.assertEqual(sessions[0]['starting_learner'], sessions[1]['starting_learner'])
        store.abandon_session(sessions[0]['session_id'])
        with self.assertRaises(LearningError):
            store.create_session(store.get_source('three'), learner)

    def test_completion_transaction_recovery_retains_sibling(self):
        first, second = self.start('one'), self.start('two')
        with patch.object(self.service.store, '_apply_txn', side_effect=OSError('simulated crash')):
            with self.assertRaises(OSError):
                self.complete(first)
        self.service = LearningService(self.root)
        learner = self.service.store.get_learner()
        self.assertEqual(learner['active_session_ids'], [second['session_id']])
        self.assertEqual(learner['active_book_id'], 'two')
        self.complete(first)  # Receipt replay.
        self.complete(second)
        self.assertEqual(self.service.store.get_learner()['items'][0]['introduced_count'], 2)

    def test_corrupt_baseline_rejected(self):
        session = self.start('one')
        modified = deepcopy(session)
        modified['starting_learner']['items'].append({'item_id': 'fr-bonjour',
            'introduced_count': 1, 'last_completed_book_id': 'other'})
        with self.assertRaises(LearningError):
            self.service.store.update_session(modified)
        session['starting_learner']['language'] = 'de'
        with self.assertRaises(LearningError):
            validate_session(session)

    def test_dictionary_dedup_uses_starting_history_not_sibling_completion(self):
        from learning.test_learning_dictionary import EntryAdapter
        self.service._add_source(source('greeting-one'))
        self.service._add_source(source('greeting-two'))
        first = self.start('greeting-one', EntryAdapter(self.service))
        second = self.service.store.create_session(self.service.store.get_source('greeting-two'),
                                                   self.service.store.get_learner())
        self.complete(first)
        self.service = LearningService(self.root)
        adapter = EntryAdapter(self.service)
        self.service.resume(second['session_id'], adapter.factory, background=False, budget_usd=1)
        self.assertIn('fr-bonjour', adapter.needed[0])

    def _background_preparations(self, second_language):
        entered = [threading.Event(), threading.Event()]
        finished = [threading.Event(), threading.Event()]
        release = threading.Event()

        class BoundAdapter:
            def __init__(self, index):
                self.index, self.calls, self.languages = index, 0, []

            def factory(self, role, request):
                return self

            def generate(self, prompt, model):
                if is_lesson(prompt):
                    return lesson_reply(prompt, model)
                self.calls += 1
                entered[self.index].set()
                if not release.wait(10):
                    raise AssertionError('second independent job did not enter its adapter')
                plan = _prompt_block(prompt, 'PLAN')
                unit = _prompt_block(prompt, 'SOURCE_UNITS')[0]
                language = plan['language']
                self.languages.append(language)
                form = 'papillon' if language == 'fr' else 'Schmetterling'
                start = unit['text'].index('פרפר')
                raw = {'response_version': 1, 'plan_id': plan['plan_id'],
                       'introduced_items': [{'item_id': 'new-word', 'kind': 'word',
                           'lemma': form, 'sense_he': 'פרפר', 'forms': [form], 'explanation_he': ''}],
                       'edits': [{'unit_id': unit['unit_id'], 'start': start, 'end': start + 4,
                           'original': 'פרפר', 'replacement': form, 'item_ids': ['new-word'],
                           'grammar_ids': [], 'gloss_he': 'פרפר'}],
                       'recap': {'vocabulary': [{'item_id': 'new-word', 'gloss_he': 'פרפר',
                                                'edit_indexes': [0]}], 'grammar': []}, 'warnings': []}
                return TextGenerationResult(status='completed', text=json.dumps(raw, ensure_ascii=False),
                    token_usage={'input': 100, 'output': 100, 'cached': 0, 'reasoning': 0},
                    observed_model=model, duration_seconds=0)

        adapters = [BoundAdapter(0), BoundAdapter(1)]
        self.service._schedule = lambda *args: None  # No retry timers outlive this test.
        original_run = self.service._run
        def tracked_run(sid, *args):
            index = 0 if self.service.store.get_session(sid)['book_id'] == 'one' else 1
            try:
                original_run(sid, *args)
            finally:
                finished[index].set()
        self.service._run = tracked_run
        first = self.service.start('one', 1, configuration(), adapters[0].factory)
        self.service.select_language(second_language)
        second = self.service.start('two', 2, configuration(), adapters[1].factory)
        try:
            self.assertTrue(all(event.wait(10) for event in entered))
        finally:
            release.set()
        self.assertTrue(all(event.wait(15) for event in finished))
        for session, adapter, language, budget in zip((first, second), adapters, ('fr', second_language), (1, 2)):
            ready = self.service.store.get_session(session['session_id'])
            self.assertEqual(ready['status'], 'ready', self.service._data['jobs'][session['session_id']]['error_code'])
            self.assertEqual(adapter.languages, [language])
            self.assertEqual(self.service._data['jobs'][session['session_id']]['budget_usd'], budget)
            self.complete(ready)

    def test_different_language_background_jobs_are_independent(self):
        self._background_preparations('de')

    def test_same_language_background_jobs_share_baseline_and_merge_completion(self):
        self._background_preparations('fr')
        self.assertEqual(self.service.store.get_learner()['items'][0]['introduced_count'], 2)


if __name__ == '__main__':
    unittest.main()
