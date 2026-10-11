"""Prefix exclusion is durable and free, while retaining complete book coverage."""
from copy import deepcopy
import tempfile
import unittest

from scholarly_translation.learning_contracts import LearningError, source_hash
from scholarly_translation.learning_service import LearningService
from scholarly_translation.learning_generation import book_notebook
from scholarly_translation.learning_catalog import load_catalog
from scholarly_translation.learning_controls import surrounding_context
from test_learning_multilingual import ProposalAdapter, butterfly_book
from test_learning_integration import configuration


class FrontmatterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = LearningService(temporary.name)
        book = butterfly_book(chapters=3)
        book['chapters'][0]['title'] = 'זכויות יוצרים'
        book['chapters'][0]['units'][0]['text'] = 'כל הזכויות שמורות. אין להעתיק. '
        book['source_hash'] = source_hash(book)
        self.book = book
        self.service._add_source(book)

    def prepare(self):
        adapter = ProposalAdapter(self.service)
        session = self.service.start('butterflies', 1, configuration(), adapter.factory,
                                     background=False, skip_initial_chapters=1)
        self.assertEqual(session['status'], 'ready', self.service._data['jobs'][session['session_id']]['error_code'])
        return session, adapter

    def test_excluded_prefix_has_no_calls_exposures_or_lesson_and_survives_restart(self):
        session, adapter = self.prepare()
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(len(adapter.roles), 4)
        sid = session['session_id']
        job = self.service._data['jobs'][sid]
        self.assertEqual(self.service._max_calls(job), 4)
        prepared = self.service.store.get_prepared(sid)
        self.assertEqual(prepared['chunks'][0]['provider'], 'local')
        self.assertEqual(prepared['chunks'][0]['edits'], [])
        self.assertNotIn('lesson', prepared['recaps'][0])
        summary = self.service.summary()
        self.assertEqual(summary['jobs'][sid]['total_chunks'], 2)
        self.assertEqual(summary['jobs'][sid]['accepted_chunks'], 2)
        self.assertEqual(summary['books'][0]['chapters'][0]['title'], 'זכויות יוצרים')
        reader = self.service.reader(sid, 0)
        self.assertTrue(reader['learning_excluded'])
        self.assertIn('כל הזכויות שמורות.', reader['html'])
        self.service.cursor(sid, 0)
        self.assertEqual(self.service.summary()['progress']['active_book']['read_items'], [])
        reopened = LearningService(self.service.root)
        self.assertEqual(reopened.store.get_session(sid)['skip_initial_chapters'], 1)
        self.assertTrue(reopened.reader(sid, 0)['learning_excluded'])
        exported = reopened.export_book(sid, format='html')
        html = exported['body'].decode('utf-8')
        self.assertIn('כל הזכויות שמורות.', html)
        self.assertEqual(html.count('aria-label="סיכום הפרק"'), 2)
        reopened.complete(sid, session['prepared_hash'], 'finished')
        self.assertEqual(reopened.store.get_learner()['items'][0]['introduced_count'], 21)

    def test_learning_allowance_and_context_ignore_prefix(self):
        session, _ = self.prepare()
        job = self.service._data['jobs'][session['session_id']]
        plans = job['plans']
        baseline = session['starting_learner']
        catalog = load_catalog()
        notebook = book_notebook(plans, 1, plans[1], baseline, catalog)
        expected = book_notebook(plans[1:], 0, plans[1], baseline, catalog)
        self.assertEqual(notebook, expected)
        context, _ = surrounding_context(plans, 1, 100000)
        self.assertNotIn('כל הזכויות', context)

    def test_invalid_counts_do_not_claim_session(self):
        for count in (-1, 3, True, '1', 1.5, None):
            with self.subTest(count=count), self.assertRaises(LearningError):
                self.service.start('butterflies', 1, configuration(), lambda *args: None,
                                   background=False, skip_initial_chapters=count)
        self.assertEqual(self.service.store.list_sessions(), [])

    def test_setting_and_pass_through_cannot_be_changed(self):
        session, _ = self.prepare()
        changed = deepcopy(session)
        changed['skip_initial_chapters'] = 0
        with self.assertRaises(LearningError):
            self.service.store.update_session(changed)
        from scholarly_translation.learning_export import _validate
        job = self.service._data['jobs'][session['session_id']]
        prepared = self.service.store.get_prepared(session['session_id'])
        plans = deepcopy(job['plans'])
        plans[0]['learning_excluded'] = False
        with self.assertRaises(LearningError):
            _validate(self.book, plans, prepared, session, load_catalog())

    def test_preserved_epub_keeps_prefix_plain_and_adds_only_body_recap(self):
        from test_learning_epub_preserve import epub, chapter, NS
        from scholarly_translation.learning_import import import_hebrew_epub
        raw = epub('<h1>זכויות יוצרים</h1><p id="front">כל הזכויות שמורות.</p>'
                   '<h1>תחילת הסיפור</h1><p id="story">' + 'פרפר צבעוני עף מעל הפרחים בשדה. ' * 20 + '</p>')
        source = import_hebrew_epub(raw, book_id='preserved-prefix')
        self.assertEqual(len(source['chapters']), 2)
        self.service._add_source(source, epub=raw)
        adapter = ProposalAdapter(self.service)
        session = self.service.start(source['book_id'], 1, configuration(), adapter.factory,
                                     background=False, skip_initial_chapters=1)
        self.assertEqual(session['status'], 'ready')
        self.assertEqual(adapter.calls, 1)
        result = self.service.export_book(session['session_id'])
        self.assertEqual(result['warnings'], [])
        dom = chapter(result['body'])
        front = dom.find('.//x:p[@id="front"]', NS)
        self.assertEqual(''.join(front.itertext()), 'כל הזכויות שמורות.')
        self.assertEqual(list(front), [])
        self.assertEqual(len(dom.findall('.//x:section[@class="learning-recap"]', NS)), 1)

    def test_new_book_with_prior_vocabulary_can_skip_prefix(self):
        first, _ = self.prepare()
        self.service.complete(first['session_id'], first['prepared_hash'], 'first-finished')
        book = deepcopy(self.book)
        book['book_id'] = 'next-prefix'
        book['source_hash'] = source_hash(book)
        self.service._add_source(book)
        adapter = ProposalAdapter(self.service)
        session = self.service.start(book['book_id'], 1, configuration(), adapter.factory,
                                     background=False, skip_initial_chapters=1)
        self.assertEqual(session['status'], 'ready', self.service._data['jobs'][session['session_id']]['error_code'])
        self.assertEqual(adapter.calls, 2)

    def test_paused_restart_resumes_only_body_and_recovers_pinned_prefix(self):
        adapter = ProposalAdapter(self.service, pause=True)
        session = self.service.start('butterflies', 1, configuration(), adapter.factory,
                                     background=False, skip_initial_chapters=1)
        self.assertEqual(session['status'], 'paused')
        reopened = LearningService(self.service.root)
        resumed = ProposalAdapter(reopened)
        result = reopened.resume(session['session_id'], resumed.factory, background=False)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(resumed.calls, 1)
        self.assertEqual(resumed.plans[0]['chapter_id'], 'chapter-2')
        self.assertEqual(reopened.store.get_prepared(session['session_id'])['chunks'][0]['provider'], 'local')

    def test_crash_before_job_checkpoint_rebuilds_excluded_plans(self):
        learner = self.service.store.get_learner()
        session = self.service.store.create_session(self.book, learner, skip_initial_chapters=1)
        reopened = LearningService(self.service.root)
        job = reopened._data['jobs'][session['session_id']]
        self.assertTrue(job['plans'][0]['learning_excluded'])
        self.assertFalse(job['plans'][1].get('learning_excluded', False))
        self.assertEqual(job['error_code'], 'budget_required')


if __name__ == '__main__':
    unittest.main()
