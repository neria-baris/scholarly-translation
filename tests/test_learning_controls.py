"""Explicit budget/context/output changes preserve data and previous accounting."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scholarly_translation.learning_contracts import LearningError
from scholarly_translation.learning_service import LearningService
from scholarly_translation.work_journal import WorkJournal
from test_learning_integration import configuration
from test_learning_multilingual import ProposalAdapter, butterfly_book


class LearningControlRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = LearningService(self.root)
        self.service.select_language('de')
        self.service._add_source(butterfly_book())

    def test_budget_increase_over_100_resumes_without_erasing_previous_accounting(self):
        adapter = ProposalAdapter(self.service)
        failed = self.service.start('butterflies', .000001, configuration(), adapter.factory, background=False)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(self.service.summary()['jobs'][failed['session_id']]['error_code'], 'budget_exhausted')
        ready = self.service.resume(failed['session_id'], adapter.factory, budget_usd=1000, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(self.service.summary()['jobs'][ready['session_id']]['usage']['attempted_calls'], 2)
        self.assertTrue((self.root / 'calls' / ready['session_id'] / 'controls.sqlite3').exists())

    def test_truncated_response_preserved_and_explicit_retry_keeps_held_cost(self):
        class Truncated(ProposalAdapter):
            def generate(self, prompt, model):
                result = super().generate(prompt, model)
                return replace(result, status='incomplete', text=result.text[:60])
        adapter = Truncated(self.service)
        failed = self.service.start('butterflies', 1, configuration(), adapter.factory, background=False)
        sid = failed['session_id']
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(self.service.summary()['jobs'][sid]['error_code'], 'response_incomplete')
        with WorkJournal(self.root / 'calls' / sid / 'journal.sqlite3') as journal:
            raw = journal.read_raw(journal.job_steps(sid)[0]['identity'])
        self.assertEqual(len(raw['text']), 60)
        self.assertEqual(self.service.store.get_learner('de')['items'], [])
        self.service.resume(sid, adapter.factory, background=False)
        self.assertEqual(adapter.calls, 1)
        held = self.service.summary()['jobs'][sid]['usage']['held_usd']
        self.assertGreater(held, 0)
        good = ProposalAdapter(self.service)
        ready = self.service.resume(sid, good.factory, output_tokens=16000, retry=True, background=False)
        self.assertEqual(ready['status'], 'ready', self.service.summary()['jobs'][sid]['error_code'])
        usage = self.service.summary()['jobs'][sid]['usage']
        self.assertEqual(usage['attempted_calls'], 3)
        self.assertGreaterEqual(usage['held_usd'], held)
        self.assertEqual(good.calls, 2)

    def test_partial_pause_context_change_and_archive_failure_keep_reading_available(self):
        first = ProposalAdapter(self.service, pause=True)
        paused = self.service.start('butterflies', 1, configuration(), first.factory, background=False)
        original = self.service.store.get_source('butterflies')
        accepted = self.service._data['jobs'][paused['session_id']]['chunks'][0]
        good = ProposalAdapter(self.service)
        ready = self.service.resume(paused['session_id'], good.factory, context_chars=50000, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(self.service.store.get_source('butterflies'), original)
        self.assertEqual(self.service.store.get_prepared(ready['session_id'])['chunks'][0], accepted)
        self.assertEqual(good.calls, 1)
        info = self.service.summary()['jobs'][ready['session_id']]['context_info']
        self.assertEqual(info['requested_chars'], 50000)
        self.assertEqual(info['provided_chars'], info['available_chars'])
        with patch('scholarly_translation.learning_service.save_personal_archive', side_effect=OSError('disk full')):
            reader = self.service.reader(ready['session_id'])
        self.assertIn('Schmetterling', reader['html'])
        self.assertEqual(reader['archive_warning'], 'archive_save_failed')
        self.service.cursor(ready['session_id'], 0)
        archive = self.root / 'personal' / 'de'
        self.assertTrue(list((archive / 'grammar').glob('*.json')))
        snapshot = json.loads((archive / 'dictionary.json').read_text(encoding='utf-8'))
        self.assertTrue(snapshot['current_items'])
        self.assertEqual(snapshot['saved_items'], [])
        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-controls')
        self.assertTrue(json.loads((archive / 'dictionary.json').read_text(encoding='utf-8'))['saved_items'])

    def test_model_output_capacity_is_reported_without_trimming_source(self):
        adapter = ProposalAdapter(self.service)
        model_limit = configuration().resolve('translator')[0].capabilities.max_output_tokens
        failed = self.service.start('butterflies', 1, configuration(), adapter.factory,
                                    output_tokens=model_limit + 1, background=False)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(self.service.summary()['jobs'][failed['session_id']]['error_code'], 'output_capacity')
        for kwargs in ({'context_chars': -1}, {'output_tokens': 0}, {'retry': 'yes'}):
            with self.assertRaises(LearningError):
                self.service.resume(failed['session_id'], adapter.factory, background=False, **kwargs)

    def test_damaged_accounting_is_visible_and_never_dropped_on_retry(self):
        adapter = ProposalAdapter(self.service, pause=True)
        paused = self.service.start('butterflies', 1, configuration(), adapter.factory, background=False)
        ledger = self.root / 'calls' / paused['session_id'] / 'controls.sqlite3'
        ledger.write_bytes(b'damaged ledger fixture')
        usage = self.service.summary()['jobs'][paused['session_id']]['usage']
        self.assertTrue(usage['accounting_unavailable'])
        with self.assertRaises(LearningError) as caught:
            self.service.resume(paused['session_id'], adapter.factory, retry=True, background=False)
        self.assertEqual(caught.exception.code, 'accounting_unavailable')
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(len(self.service._data['jobs'][paused['session_id']]['chunks']), 1)

    def test_unknown_outcome_requires_a_fresh_choice_for_each_lost_call(self):
        class Lost(ProposalAdapter):
            def generate(self, prompt, model):
                self.calls += 1
                raise OSError('simulated transport failure after dispatch')
        lost = Lost(self.service)
        failed = self.service.start('butterflies', 1, configuration(), lost.factory, background=False)
        sid = failed['session_id']
        self.assertEqual(self.service.summary()['jobs'][sid]['error_code'], 'retry_confirmation_required')
        held = self.service.summary()['jobs'][sid]['usage']['held_usd']
        self.assertGreater(held, 0)
        self.service.resume(sid, lost.factory, background=False)
        self.assertEqual(lost.calls, 1)
        self.service.resume(sid, lost.factory, retry=True, background=False)
        self.assertEqual(lost.calls, 2)
        self.service.resume(sid, lost.factory, background=False)
        self.assertEqual(lost.calls, 2)
        good = ProposalAdapter(self.service)
        ready = self.service.resume(sid, good.factory, retry=True, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(good.calls, 2)
        self.assertGreaterEqual(self.service.summary()['jobs'][sid]['usage']['held_usd'], held)
        with WorkJournal(self.root / 'calls' / sid / 'journal.sqlite3') as journal:
            steps = journal.job_steps(sid)
        retired = [step for step in steps if step['status'] == 'failed']
        self.assertEqual(len(retired), 2)
        self.assertTrue(all('Outcome remains unknown; user authorized' in step['error'] for step in retired))


if __name__ == '__main__':
    unittest.main()
