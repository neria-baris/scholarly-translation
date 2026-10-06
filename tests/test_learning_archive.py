"""Personal learning artifacts retain evidence without granting completion."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarly_translation.learning_archive import save_personal_archive, _safe_path
from scholarly_translation.learning_contracts import LearningError


def progress():
    saved = {'item_id': 'fr-bonjour', 'kind': 'word', 'foreign': 'bonjour',
             'hebrew': 'שלום', 'encounters': 8, 'last_book_title': 'ספר קודם'}
    current = {**saved, 'encounters': 3, 'last_book_title': 'ספר נוכחי'}
    return {'completed_items': [saved], 'active_book': {'title': 'ספר נוכחי', 'read_items': [current]}}


def chapter(chapter_id='chapter-1'):
    return {'session_id': 'session-1', 'book_id': 'book-1', 'chapter_id': chapter_id,
            'chapter_title': 'פרק ראשון', 'items': {'fr-g-present': {'lemma': 'être', 'sense_he': 'להיות'},
                                                   'fr-bonjour': {'lemma': 'bonjour', 'sense_he': 'שלום'}},
            'recap': {'schema_version': 1, 'chapter_id': chapter_id, 'chunk_hashes': ['a' * 64],
                      'grammar': [{'item_id': 'fr-g-present', 'explanation_he': 'הסבר עם ניקוד: הוּא; לא נחתך.',
                                   'examples': [{'foreign': 'je suis', 'hebrew': 'אני', 'chunk_id': 'chunk-1', 'edit_index': 0},
                                                {'foreign': 'il est', 'hebrew': 'הוא', 'chunk_id': 'chunk-2', 'edit_index': 2}]}],
                      'vocabulary': [{'item_id': 'fr-bonjour', 'gloss_he': 'שלום'}], 'warnings': []}}


class PersonalArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_all_explanations_examples_and_unicode_retained_before_completion(self):
        data = chapter()
        # Long saved explanations have no arbitrary truncation limit.
        data['recap']['grammar'].append({'item_id': 'fr-g-other', 'explanation_he': 'הסבר ארוך ' * 20000,
                                        'examples': [{'foreign': 'אַ גוטן טאָג', 'hebrew': 'יום טוב'}]})
        result = save_personal_archive(self.root, 'fr', progress(), data)
        stored = json.loads(Path(result['grammar']['json']).read_text(encoding='utf-8'))
        self.assertEqual(stored['recap'], data['recap'])
        readable = Path(result['grammar']['markdown']).read_text(encoding='utf-8')
        for text in ['je suis', 'il est', 'אַ גוטן טאָג', 'הוּא', 'ספר: book-1', 'קריאה: session-1']:
            self.assertIn(text, readable)
        self.assertIn('הסבר ארוך ' * 20000, readable)
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(stored['book_id'], 'book-1')

    def test_dictionary_distinguishes_saved_and_current_without_mastery(self):
        input_progress = progress()
        prior = copy.deepcopy(input_progress)
        result = save_personal_archive(self.root, 'fr', input_progress)
        stored = json.loads(Path(result['dictionary']['json']).read_text(encoding='utf-8'))
        self.assertEqual(stored['saved_items'][0]['encounters'], 8)
        self.assertEqual(stored['current_items'][0]['encounters'], 3)
        self.assertNotIn('mastered', stored['saved_items'][0])
        readable = Path(result['dictionary']['markdown']).read_text(encoding='utf-8')
        self.assertIn('נשמר לאחר קראתי', readable)
        self.assertIn('בספר הנוכחי — טרם נשמר', readable)
        self.assertEqual(input_progress, prior)

    def test_repeated_identical_chapter_is_immutable_and_missing_md_repaired(self):
        first = save_personal_archive(self.root, 'fr', progress(), chapter())
        json_path = Path(first['grammar']['json'])
        modified_time = json_path.stat().st_mtime_ns
        second = save_personal_archive(self.root, 'fr', progress(), chapter())
        self.assertTrue(second['chapter_reused'])
        self.assertEqual(json_path.stat().st_mtime_ns, modified_time)
        Path(first['grammar']['markdown']).unlink()
        third = save_personal_archive(self.root, 'fr', progress(), chapter())
        self.assertTrue(Path(third['grammar']['markdown']).exists())
        self.assertEqual(json_path.stat().st_mtime_ns, modified_time)

    def test_changed_explanation_or_book_identity_preserves_prior_artifact(self):
        first = save_personal_archive(self.root, 'fr', progress(), chapter())
        old_bytes = Path(first['grammar']['json']).read_bytes()
        for field in ('explanation', 'book'):
            changed = chapter()
            if field == 'explanation':
                changed['recap']['grammar'][0]['explanation_he'] = 'שינוי'
            else:
                changed['book_id'] = 'other-book'
            with self.assertRaises(LearningError) as caught:
                save_personal_archive(self.root, 'fr', progress(), changed)
            self.assertEqual(caught.exception.code, 'archive_save_failed')
            self.assertEqual(Path(first['grammar']['json']).read_bytes(), old_bytes)

    def test_chapters_are_separate_and_completed_snapshot_updates_only_dictionary(self):
        first = save_personal_archive(self.root, 'fr', progress(), chapter())
        old = Path(first['grammar']['json']).read_bytes()
        second = save_personal_archive(self.root, 'fr', progress(), chapter('chapter-2'))
        self.assertNotEqual(first['grammar']['json'], second['grammar']['json'])
        completed = progress()
        completed['completed_items'][0]['encounters'] = 11
        completed['active_book'] = None
        result = save_personal_archive(self.root, 'fr', completed)
        updated = json.loads(Path(result['dictionary']['json']).read_text(encoding='utf-8'))
        self.assertEqual(updated['saved_items'][0]['encounters'], 11)
        self.assertEqual(updated['current_items'], [])
        self.assertEqual(Path(first['grammar']['json']).read_bytes(), old)

    def test_invalid_paths_rejected_and_windows_names_encoded(self):
        for key in ('session_id', 'book_id', 'chapter_id'):
            bad = chapter()
            bad[key] = '../escape'
            with self.assertRaises(LearningError):
                save_personal_archive(self.root, 'fr', progress(), bad)
        with self.assertRaises(LearningError):
            save_personal_archive(self.root, '../escape', progress())
        with self.assertRaises(LearningError) as caught:
            _safe_path(self.root, '..', 'outside')
        self.assertEqual(caught.exception.code, 'archive_save_failed')
        safe = chapter('chapter:1')
        safe['session_id'] = 'CON'
        result = save_personal_archive(self.root, 'yi', progress(), safe)
        self.assertTrue(Path(result['grammar']['json']).is_relative_to(self.root))
        self.assertIn('%43ON--chapter%3A1.json', result['grammar']['json'])

    def test_inconsistent_source_reference_rejected_before_writes(self):
        data = chapter()
        data['recap']['chapter_id'] = 'other-chapter'
        with self.assertRaises(LearningError):
            save_personal_archive(self.root, 'fr', progress(), data)
        self.assertFalse((self.root / 'personal').exists())

    def test_concurrent_conflicting_chapter_cannot_overwrite_evidence(self):
        barrier = threading.Barrier(2)
        alternatives = [chapter(), chapter()]
        alternatives[1]['recap']['grammar'][0]['explanation_he'] = 'הסבר חלופי'
        def save(data):
            barrier.wait(timeout=5)
            try:
                return save_personal_archive(self.root, 'fr', progress(), data)
            except LearningError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, alternatives))
        self.assertEqual(sum(isinstance(row, dict) for row in results), 1)
        self.assertIn('archive_save_failed', results)
        received = next(row for row in results if isinstance(row, dict))
        stored = json.loads(Path(received['grammar']['json']).read_text(encoding='utf-8'))
        self.assertIn(stored['recap']['grammar'][0]['explanation_he'],
                      [data['recap']['grammar'][0]['explanation_he'] for data in alternatives])

    def test_atomic_failure_warns_without_truncating_old_dictionary(self):
        first = save_personal_archive(self.root, 'fr', progress())
        old = Path(first['dictionary']['json']).read_bytes()
        with patch('scholarly_translation.learning_archive.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(LearningError) as caught:
                save_personal_archive(self.root, 'fr', progress(), chapter())
        self.assertEqual(caught.exception.code, 'archive_save_failed')
        self.assertEqual(Path(first['dictionary']['json']).read_bytes(), old)
        self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_root_resolution_io_failure_uses_explicit_error(self):
        with patch('scholarly_translation.learning_archive.Path.resolve', side_effect=OSError('inaccessible root')):
            with self.assertRaises(LearningError) as caught:
                save_personal_archive(self.root, 'fr', progress())
        self.assertEqual(caught.exception.code, 'archive_save_failed')

    def test_partial_pair_failure_is_explicit_and_retry_repairs_it(self):
        from scholarly_translation.learning_archive import _atomic_text
        def fail_md(path, text):
            if path.suffix == '.md':
                raise OSError('failed companion')
            return _atomic_text(path, text)
        with patch('scholarly_translation.learning_archive._atomic_text', side_effect=fail_md):
            with self.assertRaises(LearningError) as caught:
                save_personal_archive(self.root, 'fr', progress(), chapter())
        self.assertEqual(caught.exception.code, 'archive_save_failed')
        self.assertEqual(len(list(self.root.rglob('grammar/*.json'))), 1)
        result = save_personal_archive(self.root, 'fr', progress(), chapter())
        self.assertTrue(result['chapter_reused'])
        self.assertTrue(Path(result['grammar']['markdown']).exists())

    def test_arbitrary_book_credentials_and_unused_definitions_not_archived(self):
        data = chapter()
        data['source'] = 'complete private book'
        data['api_key'] = 'credential value'
        data['items']['unused'] = {'lemma': 'unused', 'sense_he': 'unused'}
        result = save_personal_archive(self.root, 'fr', progress(), data)
        text = Path(result['grammar']['json']).read_text(encoding='utf-8')
        for forbidden in ('complete private book', 'credential value', 'unused'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
