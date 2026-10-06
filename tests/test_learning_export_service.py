"""Export is a read-only learning operation using the pinned prepared edition."""
import json
from pathlib import Path
import tempfile
import unittest
import io
import zipfile
from unittest.mock import patch

from scholarly_translation.learning_contracts import LearningError
from scholarly_translation.learning_service import LearningService
from test_learning_integration import Adapter, configuration, source
from test_learning_epub_preserve import epub


class LearningExportServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = LearningService(self.root)
        self.service._add_source(source(chapters=2))
        self.adapter = Adapter(self.service)
        self.ready = self.service.start('book-one', 1, configuration(), self.adapter.factory, background=False)
        self.assertEqual(self.ready['status'], 'ready')

    def test_export_has_no_cursor_completion_archive_or_model_side_effects(self):
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('unexpected model')):
            for format in ('epub', 'html'):
                result = self.service.export_book(self.ready['session_id'], format=format)
                self.assertTrue(result['body'])
                self.assertTrue(result['filename'].endswith('.fr.' + format))
                self.assertEqual(result['warnings'], ['reflowed_text'])
                self.assertEqual(self.service.export_book(self.ready['session_id'], format=format)['body'], result['body'])
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.adapter.calls, 2)
        self.assertIsNone(self.service.store.get_session(self.ready['session_id'])['read_cursor'])
        self.assertEqual(self.service.store.get_learner('fr')['completed_books'], [])

    def test_completion_and_reopen_keep_the_same_exported_edition(self):
        before = self.service.export_book(self.ready['session_id'])['body']
        self.service.complete(self.ready['session_id'], self.ready['prepared_hash'], 'export-complete')
        reopened = LearningService(self.root)
        reopened.select_language('de')
        self.assertEqual(reopened.export_book(self.ready['session_id'])['body'], before)

    def test_partial_and_corrupt_prepared_data_cannot_export(self):
        sid = self.ready['session_id']
        for kwargs, code in [({'format': 'pdf'}, 'invalid_export_format'),
                             ({'include_meanings': 'true'}, 'invalid_export_options')]:
            with self.assertRaises(LearningError) as caught:
                self.service.export_book(sid, **kwargs)
            self.assertEqual(caught.exception.code, code)
        prepared_path = self.service.store._prepared_path(sid)
        prepared = json.loads(prepared_path.read_text(encoding='utf-8'))
        prepared['chunks'].pop()
        prepared_path.write_text(json.dumps(prepared), encoding='utf-8')
        with self.assertRaises(LearningError) as caught:
            self.service.export_book(sid)
        self.assertEqual(caught.exception.code, 'corrupt_store')
        session = self.service.store.get_session(sid)
        session['status'] = 'paused'
        self.service.store.update_session(session)
        with self.assertRaises(LearningError) as caught:
            self.service.export_book(sid)
        self.assertEqual(caught.exception.code, 'book_not_ready')

    def test_real_import_prepare_preserve_export_keeps_assets_and_state(self):
        service = LearningService(self.root / 'retained')
        raw = epub('<h1>פרק ראשון</h1><p>שלום, אני קורא ספר בעברית ליד הבית. ' * 1 +
                   'זהו טקסט בעברית לקריאה בשדה. ' * 15 + '</p>')
        book = service.import_epub(raw)
        adapter = Adapter(service)
        ready = service.start(book['book_id'], 1, configuration(), adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = service.export_book(ready['session_id'])
        self.assertEqual(result['warnings'], [])
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(io.BytesIO(result['body'])) as output:
            for name in original.namelist():
                if name != 'OPS/chapter.xhtml':
                    self.assertEqual(output.read(name), original.read(name), name)
            self.assertIn('bonjour', output.read('OPS/chapter.xhtml').decode())
        self.assertEqual(service.export_book(ready['session_id'], preserve_layout=False)['warnings'], ['reflowed_text'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(adapter.calls, 1)

    def test_retained_asset_loss_errors_and_user_can_choose_text_export(self):
        from scholarly_translation.learning_assets import retain_epub
        source_record = self.service.store.get_source('book-one')
        retain_epub(self.root, source_record, epub('<p>טקסט עברי אחר.</p>'))
        self.service._data['books']['book-one']['epub_layout'] = 'retained'
        with self.assertRaises(LearningError) as caught:
            self.service.export_book(self.ready['session_id'])
        self.assertEqual(caught.exception.code, 'invalid_preserved_epub')
        with patch('scholarly_translation.learning_epub_preserve.build_preserved_epub',
                   side_effect=LearningError('preservation_unavailable')):
            with self.assertRaises(LearningError) as caught:
                self.service.export_book(self.ready['session_id'])
            self.assertEqual(caught.exception.code, 'preservation_unavailable')
        target = self.root / 'epub_assets' / 'book-one'
        for path in target.iterdir():
            path.unlink()
        target.rmdir()
        with self.assertRaises(LearningError) as caught:
            self.service.export_book(self.ready['session_id'])
        self.assertEqual(caught.exception.code, 'invalid_preserved_epub')
        self.assertTrue(self.service.export_book(self.ready['session_id'], preserve_layout=False)['body'])
