import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
        self.scheduled = []  # Automatic retries run when a test fires them.
        self.service._schedule = lambda delay, function, args: self.scheduled.append((delay, function, args))

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

    def test_rename_changes_display_title_only(self):
        renamed = self.service.rename_book('book-one', '  Jade   City ')
        self.assertEqual(renamed['title'], 'Jade City')
        self.assertEqual(self.service.summary()['books'][0]['title'], 'Jade City')
        self.assertEqual(LearningService(self.root).summary()['books'][0]['title'], 'Jade City')
        ready = self.prepare()
        self.assertEqual(self.service.reader(ready['session_id'])['title'], 'Jade City')
        self.assertNotEqual(self.service.store.get_source('book-one')['title'], 'Jade City')
        for bad in ('   ', 'x' * 501, None):
            with self.assertRaises(LearningError) as ctx:
                self.service.rename_book('book-one', bad)
            self.assertEqual(ctx.exception.code, 'invalid_title')

    def test_delete_unused_book_removes_its_files(self):
        self.service.delete_book('book-one')
        self.assertEqual(self.service.summary()['books'], [])
        self.assertFalse((self.root / 'state' / 'sources' / 'book-one.json').exists())
        with self.assertRaises(LearningError) as ctx:
            self.service.delete_book('book-one')
        self.assertEqual(ctx.exception.code, 'book_not_found')

    def test_delete_refuses_active_book_and_hides_completed_one(self):
        ready = self.prepare()
        with self.assertRaises(LearningError) as ctx:
            self.service.delete_book('book-one')
        self.assertEqual(ctx.exception.code, 'book_in_use')
        self.service.complete(ready['session_id'], ready['prepared_hash'], 'complete-one')
        self.assertEqual(self.service.delete_book('book-one')['deleted'], 'hidden')
        self.assertEqual(self.service.summary()['books'], [])
        # History stays readable after the book leaves the list.
        self.assertIn('bonjour', self.service.reader(ready['session_id'])['html'])
        self.assertTrue((self.root / 'state' / 'sources' / 'book-one.json').exists())

    def test_invalid_answer_is_retried_automatically_with_a_fresh_call(self):
        self.adapter.fail = True
        failed = self.prepare()
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(self.service.summary()['jobs'][failed['session_id']]['auto_retry']['count'], 1)
        delay, function, args = self.scheduled.pop()
        self.assertEqual(delay, 2)  # A rejected answer is resent soon, unlike provider failures.
        self.adapter.fail = False
        # Fire the timer in the foreground.
        self.service.resume = (lambda original: lambda *a, **k: original(*a, **{**k, 'background': False}))(self.service.resume)
        function(*args)
        self.assertEqual(self.service.store.get_session(failed['session_id'])['status'], 'ready')
        self.assertEqual(self.adapter.calls, 2)  # The invalid answer was not replayed from cache.
        self.assertIsNone(self.service.summary()['jobs'][failed['session_id']]['auto_retry'])

    def test_automatic_retry_stops_at_one_dollar_of_failures(self):
        self.adapter.fail = True
        with patch.object(LearningService, '_spent', side_effect=[0.0, 1.0]):
            failed = self.prepare()
        self.assertEqual(self.scheduled, [])
        state = self.service.summary()['jobs'][failed['session_id']]['auto_retry']
        self.assertTrue(state['stopped'])
        self.assertIsNone(state['retry_at'])

    def test_automatic_retry_stops_after_ten_in_a_row(self):
        self.adapter.fail = True
        failed = self.prepare()
        self.service.resume = (lambda original: lambda *a, **k: original(*a, **{**k, 'background': False}))(self.service.resume)
        while self.scheduled:
            _delay, function, args = self.scheduled.pop()
            function(*args)
        self.assertEqual(self.adapter.calls, 11)
        self.assertTrue(self.service.summary()['jobs'][failed['session_id']]['auto_retry']['stopped'])

    def test_pause_cancels_a_waiting_automatic_retry(self):
        self.adapter.fail = True
        failed = self.prepare()
        _delay, function, args = self.scheduled.pop()
        self.service.pause(failed['session_id'])
        function(*args)
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.service.store.get_session(failed['session_id'])['status'], 'failed')

    def test_budget_failure_waits_for_the_user(self):
        self.service.start('book-one', 1e-9, configuration(), self.adapter.factory, background=False)
        self.assertEqual(self.scheduled, [])

    def test_reasoning_level_adds_output_headroom(self):
        from scholarly_translation.learning_controls import learning_model_selection
        plain = configuration()
        high = build_configuration({'translator': learning_model_selection('gpt-6-luna', 'high')})
        job = {'plans': [{'policy_version': 'learning-policy@1'}], 'output_tokens': 6000}
        self.assertEqual(self.service._shared_cap(job, plain), 6000)
        self.assertEqual(self.service._shared_cap(job, high), 6000 + 32768)
        with self.assertRaises(LearningError) as ctx:
            learning_model_selection('gpt-6-luna', 'extreme')
        self.assertEqual(ctx.exception.code, 'invalid_model')
        with self.assertRaises(LearningError):
            learning_model_selection('gpt-unknown')
        haiku = learning_model_selection('claude-haiku-4-5')
        self.assertEqual((haiku['provider'], 'reasoning' in haiku), ('anthropic', False))
        with self.assertRaises(LearningError):
            learning_model_selection('claude-haiku-4-5', 'high')  # Haiku takes no effort level.

    def test_automatic_limits_size_context_and_grow_after_cut_off_answer(self):
        from scholarly_translation.learning_controls import auto_context_chars
        self.adapter.fail = True
        failed = self.prepare()
        job = self.service._data['jobs'][failed['session_id']]
        self.assertIsNone(job['context_chars'])
        plan = job['plans'][0]
        self.assertEqual(job['context_info']['requested_chars'], auto_context_chars(plan))
        self.assertTrue(1500 <= auto_context_chars(plan) <= 6000)
        job['error_code'], job['auto_retry'] = 'response_incomplete', None
        self.service._plan_auto_retry(failed['session_id'])
        self.assertEqual(job['output_tokens'], 12000)

    def test_fenced_json_reply_is_accepted(self):
        from scholarly_translation.learning_contracts import unwrap_json_fence
        fence = chr(96) * 3
        self.assertEqual(unwrap_json_fence(fence + 'json\n{"a": 1}\n' + fence), '{"a": 1}')
        prose = 'text ' + fence + 'json\n{}\n' + fence
        self.assertEqual(unwrap_json_fence(prose), prose)

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
        job.pop('new_foreign_words_used')  # Saved with the chunk, so lost with it.
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
