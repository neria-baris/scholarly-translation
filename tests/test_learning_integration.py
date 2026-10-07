import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scholarly_translation.learning_contracts import LearningError, fixture_source, source_hash
from scholarly_translation.learning_service import LearningService
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_settings import build_configuration
from scholarly_translation.learning_planner import replan_chunk
from scholarly_translation.learning_catalog import load_catalog


def configuration():
    return build_configuration({'translator': {'source': 'catalog', 'provider': 'openai', 'model': 'gpt-6-luna'}})


def source(book_id='book-one', chapters=1):
    result = fixture_source(book_id)
    result['chapters'] = [{'chapter_id': f'chapter-{i}', 'title': f'פרק {i}', 'units': [
        {'unit_id': f'unit-{i}', 'kind': 'paragraph', 'text': 'שלום, אני קורא ספר והוא נשאר כאן. תודה על היום הנעים ועל הדרך הארוכה בעיר. ' * 12}
    ]} for i in range(chapters)]
    result['source_hash'] = source_hash(result)
    return result


def _prompt_block(prompt, label):
    start = prompt.index(label + ':\n```json\n') + len(label) + 9
    return json.loads(prompt[start:prompt.index('\n```', start)])


def is_lesson(prompt):
    return '\nLESSON:\n```json' in prompt


def lesson_reply(prompt, model):
    """A valid grammar lesson grounded in the supplied chapter (fake provider)."""
    lesson, insertions = _prompt_block(prompt, 'LESSON'), _prompt_block(prompt, 'INSERTIONS')
    unit = next(u for u in _prompt_block(prompt, 'CHAPTER_UNITS') if u['kind'] == 'paragraph')
    examples = [{'edit_ref': insertions[0]['ref'], 'note_he': 'צורה'}] if insertions else []
    examples.append({'unit_id': unit['unit_id'], 'hebrew': unit['text'][:12], 'foreign': 'phrase', 'note_he': ''})
    raw = {'response_version': 1, 'chapter_id': lesson['chapter_id'], 'topics': ['מין'],
           'paragraphs': [{'heading_he': 'מין', 'text_he': 'פסקה',
                           'examples': examples}]}
    return TextGenerationResult(status='completed', text=json.dumps(raw, ensure_ascii=False),
        token_usage={'input': 100, 'output': 100, 'cached': 0, 'reasoning': 0},
        observed_model=model, duration_seconds=0)


class Adapter:
    def __init__(self, service, fail=False, pause=False):
        self.service, self.calls, self.fail, self.pause_after = service, 0, fail, pause
        self.roles = []
        self.lesson_calls = 0

    def factory(self, role, request):
        self.roles.append(role)
        return self

    def generate(self, prompt, model):
        if is_lesson(prompt):
            self.lesson_calls += 1
            return lesson_reply(prompt, model)
        self.calls += 1
        job = next(j for j in self.service._data['jobs'].values() if j['status'] == 'preparing')
        plan = job['current_plan']
        unit = next(u for u in plan['units'] if u['kind'] == 'paragraph')
        start = unit['text'].index('שלום')
        raw = {'response_version': 1, 'plan_id': plan['plan_id'], 'edits': [{
            'unit_id': unit['unit_id'], 'start': start, 'end': start + 4, 'original': 'שלום',
            'replacement': 'bonjour', 'item_ids': ['fr-bonjour'], 'grammar_ids': [], 'gloss_he': 'שלום'}],
            'recap': {'vocabulary': [{'item_id': 'fr-bonjour', 'gloss_he': 'שלום', 'edit_indexes': [0]}], 'grammar': []},
            'warnings': []}
        if self.fail:
            raw['edits'][0]['original'] = 'שינוי'
        if self.pause_after:
            self.service.pause(job['session_id'])
        return TextGenerationResult(status='completed', text=json.dumps(raw, ensure_ascii=False),
            token_usage={'input': 100, 'output': 100, 'cached': 0, 'reasoning': 0},
            observed_model=model, duration_seconds=0)


class LearningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = LearningService(self.root)
        self.service._add_source(source())
        self.adapter = Adapter(self.service)

    def prepare(self):
        return self.service.start('book-one', 1, configuration(), self.adapter.factory, background=False)

    def test_read_completion_continuity_and_idempotency(self):
        ready = self.prepare()
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(self.adapter.roles, ['translator', 'translator'])  # chunk + chapter lesson
        self.assertEqual(self.adapter.lesson_calls, 1)
        reader = self.service.reader(ready['session_id'])
        self.assertIn('bonjour', reader['html'])
        lesson = reader['recap']['lesson']
        self.assertEqual(lesson['status'], 'ready')
        self.assertEqual([x['kind'] for x in lesson['paragraphs'][0]['examples']], ['insertion', 'sentence'])
        self.assertEqual(lesson['paragraphs'][0]['examples'][0]['foreign'], 'bonjour')
        self.assertEqual(self.service.store.get_learner()['items'], [])
        self.service.cursor(ready['session_id'], 0)
        self.assertEqual(self.service.store.get_learner()['revision'], 0)
        receipt = self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-one')
        self.assertEqual(receipt, self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-one'))
        committed = self.service.store.get_learner()
        self.assertEqual(committed['revision'], 1)
        self.assertEqual(committed['items'][0]['item_id'], 'fr-bonjour')
        self.service._add_source(source('book-two'))
        next_session = self.service.start('book-two', 1, configuration(), self.adapter.factory, background=False)
        next_plan = self.service._data['jobs'][next_session['session_id']]['plans'][0]
        self.assertIn('fr-bonjour', next_plan['review_item_ids'])
        self.assertEqual(next_session['level_id'], ready['level_id'])
        self.assertEqual(next_session['support_mode'], ready['support_mode'])

    def test_invalid_edit_preserves_state_and_replay_never_resends(self):
        self.adapter.fail = True
        session = self.prepare()
        self.assertEqual(session['status'], 'failed')
        self.service.resume(session['session_id'], self.adapter.factory, background=False)
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.service.store.get_learner()['items'], [])
        with self.assertRaises(LearningError):
            self.service.complete(session['session_id'], 'wrong', 'complete-one')

    def test_pause_restart_and_resume_only_pending_chunk(self):
        second = source('book-many', chapters=2)
        self.service._add_source(second)
        self.adapter.pause_after = True
        session = self.service.start('book-many', 1, configuration(), self.adapter.factory, background=False)
        self.assertEqual(session['status'], 'paused')
        self.assertEqual(self.adapter.calls, 1)
        reopened = LearningService(self.root)
        next_adapter = Adapter(reopened)
        completed = reopened.resume(session['session_id'], next_adapter.factory, background=False)
        self.assertEqual(completed['status'], 'ready')
        self.assertEqual(next_adapter.calls, 1)
        self.assertEqual(len(reopened.store.get_prepared(session['session_id'])['recaps']), 2)

    def test_budget_stop_and_active_book_guard(self):
        for amount in (0, -1, float('nan'), True):
            with self.assertRaises(LearningError):
                self.service.start('book-one', amount, configuration(), self.adapter.factory, background=False)
        stopped = self.service.start('book-one', 0.000001, configuration(), self.adapter.factory, background=False)
        self.assertEqual(stopped['status'], 'failed')
        self.assertEqual(self.adapter.calls, 0)
        self.service._add_source(source('book-two'))
        with self.assertRaises(LearningError):
            self.service.start('book-two', 1, configuration(), self.adapter.factory, background=False)

    def test_effort_carries_into_next_book(self):
        self.service.set_effort('2')
        ready = self.prepare()
        self.assertEqual(ready['support_mode'], 'context')
        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-one')
        self.assertEqual(self.service.store.get_learner()['level_id'], '2')
        with self.assertRaises(LearningError):
            self.service.set_effort('4')

    def test_completed_dispatch_replays_after_lost_service_checkpoint(self):
        ready = self.prepare()
        sid = ready['session_id']
        job = self.service._data['jobs'][sid]
        base = self.service.store.get_learner()
        job.update({'status': 'preparing', 'chunks': [], 'proposals': [], 'projected': base,
                    'current_plan': replan_chunk(job['plans'][0], base, load_catalog())})
        session = self.service.store.get_session(sid)
        session.update({'status': 'preparing', 'prepared_hash': None, 'chunk_ids': []})
        self.service.store.update_session(session)
        self.service._save()
        reopened = LearningService(self.root)
        adapter = Adapter(reopened)
        replayed = reopened.resume(sid, adapter.factory, background=False)
        self.assertEqual(replayed['status'], 'ready')
        self.assertEqual(replayed['prepared_hash'], ready['prepared_hash'])
        self.assertEqual(adapter.calls, 0)

    def test_orphan_slot_requires_explicit_budget_then_recovers(self):
        session = self.service.store.create_session(source(), self.service.store.get_learner())
        reopened = LearningService(self.root)
        adapter = Adapter(reopened)
        with self.assertRaises(LearningError):
            reopened.resume(session['session_id'], adapter.factory, background=False)
        self.assertEqual(adapter.calls, 0)
        ready = reopened.resume(session['session_id'], adapter.factory, background=False, budget_usd=1)
        self.assertEqual(ready['status'], 'ready')

    def test_stopped_book_can_be_abandoned_without_learning_advancement(self):
        session = self.service.start('book-one', 0.000001, configuration(), self.adapter.factory, background=False)
        self.service.abandon(session['session_id'])
        learner = self.service.store.get_learner()
        self.assertIsNone(learner['active_book_id'])
        self.assertEqual(learner['items'], [])
        self.assertEqual(learner['completed_books'], [])
        with self.assertRaises(LearningError):
            self.service.resume(session['session_id'], self.adapter.factory, background=False)
