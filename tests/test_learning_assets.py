"""Retained archives are immutable, hash-pinned and never silently discarded."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scholarly_translation.learning_assets import retain_epub, load_epub
from scholarly_translation.learning_contracts import LearningError
from scholarly_translation.learning_service import LearningService
from scholarly_translation.learning_install_check import verify_learning_assets
from test_learning_import import _hebrew_epub_bytes, _completed_job_snapshot


class LearningAssetTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.service = LearningService(self.root)

    def test_import_retains_exact_epub_and_reopen_keeps_pinned_copy(self):
        raw = _hebrew_epub_bytes()
        book = self.service.import_epub(raw)
        source = self.service.store.get_source(book['book_id'])
        self.assertEqual(book['epub_layout'], 'retained')
        self.assertEqual(load_epub(self.root, source), raw)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        retain_epub(self.root, source, raw)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        reopened = LearningService(self.root)
        self.assertEqual(load_epub(reopened.root, source), raw)

    def test_corrupt_or_missing_retained_file_is_error_legacy_is_none(self):
        raw = _hebrew_epub_bytes()
        book = self.service.import_epub(raw)
        source = self.service.store.get_source(book['book_id'])
        with self.assertRaises(LearningError):
            retain_epub(self.root, source, b'different')
        path = self.root / 'epub_assets' / book['book_id'] / 'original.epub'
        path.write_bytes(raw + b'corruption')
        with self.assertRaises(LearningError) as caught:
            load_epub(self.root, source)
        self.assertEqual(caught.exception.code, 'invalid_preserved_epub')
        path.unlink()
        with self.assertRaises(LearningError):
            load_epub(self.root, source)
        source['book_id'] = 'legacy-book'
        self.assertIsNone(load_epub(self.root, source))

    def test_failed_asset_write_does_not_publish_book(self):
        with patch('scholarly_translation.learning_assets.os.rename', side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):
                self.service.import_epub(_hebrew_epub_bytes())
        self.assertEqual(self.service.summary()['books'], [])
        self.assertEqual(list((self.root / 'state' / 'sources').glob('*.json')), [])

    def test_translation_template_is_retained_and_install_check_is_read_only(self):
        book = self.service.import_translation(_completed_job_snapshot(), epub_template=_hebrew_epub_bytes())
        source = self.service.store.get_source(book['book_id'])
        self.assertEqual(load_epub(self.root, source), _hebrew_epub_bytes())
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('provider')):
            verify_learning_assets()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_transient_windows_save_lock_retries_and_persistent_lock_keeps_previous(self):
        import json
        from scholarly_translation.learning_service import os as service_os
        original = service_os.replace
        calls = []
        def transient(source, target):
            calls.append(source)
            if len(calls) < 3:
                raise PermissionError('sharing violation')
            return original(source, target)
        with patch('scholarly_translation.learning_service.os.replace', side_effect=transient), \
             patch('scholarly_translation.learning_service.time.sleep'):
            self.service._save()
        self.assertEqual(len(calls), 3)
        previous = self.service._path.read_bytes()
        self.service._data['selected_language'] = 'yi'
        with patch('scholarly_translation.learning_service.os.replace', side_effect=PermissionError('still locked')) as replace, \
             patch('scholarly_translation.learning_service.time.sleep'):
            with self.assertRaises(LearningError) as caught:
                self.service._save()
        self.assertEqual(caught.exception.code, 'learning_save_failed')
        self.assertEqual(replace.call_count, 6)
        self.assertEqual(self.service._path.read_bytes(), previous)
        staged = list(self.root.glob('.service-*.tmp'))
        self.assertEqual(len(staged), 1)
        self.assertEqual(json.loads(staged[0].read_text())['selected_language'], 'yi')
