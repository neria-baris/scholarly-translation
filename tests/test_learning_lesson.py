import io
import json
import re
from pathlib import Path
import tempfile
import unittest
import zipfile

from scholarly_translation.learning_archive import _chapter_md, _chapter_record
from scholarly_translation.learning_contracts import LearningError, validate_recap
from scholarly_translation.learning_lesson import build_lesson_request, parse_lesson
from scholarly_translation.learning_service import LearningService
from scholarly_translation.model_adapter import TextGenerationResult

from test_learning_integration import Adapter, configuration, is_lesson, source

UNIT_TEXT = 'הספר נכתב על ידי הסופר. הילדה הקטנה ראתה את הבית.'


def visible(markup):
    return re.sub(r'<[^>]+>', '', markup)


def pairs():
    plan = {'chapter_id': 'chapter-0', 'units': [{'unit_id': 'unit-0', 'kind': 'paragraph', 'text': UNIT_TEXT}]}
    start = UNIT_TEXT.index('הבית')
    chunk = {'plan_id': 'plan-0', 'edits': [{'unit_id': 'unit-0', 'start': start, 'end': start + 4,
             'original': 'הבית', 'replacement': 'la maison', 'item_ids': ['fr-maison'],
             'grammar_ids': ['fr-article-la'], 'gloss_he': 'הבית'}]}
    return [(plan, chunk)]


ITEMS = {'fr-maison': {'item_id': 'fr-maison', 'lemma': 'maison', 'sense_he': 'בית', 'explanation_he': ''},
         'fr-article-la': {'item_id': 'fr-article-la', 'lemma': 'la', 'sense_he': 'ה- (נקבה)',
                           'explanation_he': 'יידוע לשם עצם בלשון נקבה.'}}


def reply(examples, **extra):
    raw = {'response_version': 1, 'chapter_id': 'chapter-0', 'topics': ['מין דקדוקי'],
           'paragraphs': [{'heading_he': 'מין דקדוקי', 'text_he': 'בצרפתית לכל שם עצם יש מין.', 'examples': examples}]}
    raw.update(extra)
    return json.dumps(raw, ensure_ascii=False)


class LessonParsingTests(unittest.TestCase):
    def setUp(self):
        self.prompt, self.hash, self.grounding = build_lesson_request(
            'chapter-0', 'fr', 'level-1', pairs(), ITEMS, ['זמן הווה'])

    def parse(self, text):
        return parse_lesson(text, 'chapter-0', 'fr', self.grounding, self.hash)

    def test_prompt_carries_grounding_and_prior_topics(self):
        self.assertTrue(is_lesson(self.prompt))
        self.assertIn('"ref": "e1"', self.prompt)
        self.assertIn('la maison', self.prompt)
        self.assertIn('זמן הווה', self.prompt)
        self.assertIn('יידוע לשם עצם בלשון נקבה.', self.prompt)
        self.assertIn('active versus passive', self.prompt)

    def test_insertion_text_comes_from_the_accepted_edit_and_sentence_is_quoted(self):
        lesson = self.parse(reply([{'edit_ref': 'e1', 'note_he': 'la לפני שם נקבה'},
                                   {'unit_id': 'unit-0', 'hebrew': 'הספר נכתב על ידי הסופר.',
                                    'foreign': "Le livre a été écrit par l'auteur.", 'note_he': 'סביל'}]))
        first, second = lesson['paragraphs'][0]['examples']
        self.assertEqual(first, {'kind': 'insertion', 'chunk_id': 'plan-0', 'edit_index': 0,
                                 'foreign': 'la maison', 'hebrew': 'הבית', 'note_he': 'la לפני שם נקבה'})
        self.assertEqual(second['kind'], 'sentence')
        self.assertEqual(lesson['dropped_examples'], 0)
        self.assertEqual(lesson['status'], 'ready')

    def test_ungrounded_examples_are_dropped_and_counted(self):
        lesson = self.parse(reply([
            {'edit_ref': 'e9', 'note_he': ''},                                         # unknown ref
            {'unit_id': 'unit-0', 'hebrew': 'משפט שלא מופיע בפרק', 'foreign': 'x', 'note_he': ''},
            {'unit_id': 'unit-0', 'hebrew': 'הילדה הקטנה', 'foreign': 'הילדה', 'note_he': ''},  # not French
            {'unit_id': 'unit-9', 'hebrew': 'הילדה הקטנה', 'foreign': 'la petite fille', 'note_he': ''},
            {'unit_id': 'unit-0', 'hebrew': 'הילדה  הקטנה', 'foreign': 'la petite fille', 'note_he': ''}]))
        self.assertEqual(lesson['dropped_examples'], 4)
        self.assertEqual(lesson['paragraphs'][0]['examples'][0]['hebrew'], 'הילדה הקטנה')

    def test_structural_errors_reject_the_whole_answer(self):
        for text in ('not json', reply([], extra=1), reply([], chapter_id='chapter-1'),
                     json.dumps({'response_version': 1, 'chapter_id': 'chapter-0', 'topics': [], 'paragraphs': []})):
            with self.subTest(text=text[:40]), self.assertRaises(LearningError):
                self.parse(text)

    def test_recap_contract_accepts_lesson_and_rejects_malformed_lesson(self):
        recap = {'schema_version': 1, 'chapter_id': 'chapter-0', 'chunk_hashes': [], 'vocabulary': [],
                 'grammar': [], 'warnings': [], 'lesson': self.parse(reply([{'edit_ref': 'e1', 'note_he': ''}]))}
        validate_recap(recap)
        recap['lesson'] = {'schema_version': 1, 'status': 'ready', 'input_hash': 'x', 'topics': [], 'paragraphs': []}
        with self.assertRaises(LearningError):
            validate_recap(recap)

    def test_archive_markdown_includes_the_lesson(self):
        lesson = self.parse(reply([{'edit_ref': 'e1', 'note_he': 'שימו לב'}]))
        record = _chapter_record('fr', {'session_id': 'session-1', 'book_id': 'book-1', 'chapter_id': 'chapter-0',
            'chapter_title': 'פרק', 'items': {}, 'recap': {'schema_version': 1, 'chapter_id': 'chapter-0',
            'chunk_hashes': [], 'vocabulary': [], 'grammar': [], 'warnings': [], 'lesson': lesson}})
        text = _chapter_md(record)
        self.assertIn('## שיעור דקדוק לפרק', text)
        self.assertIn('בצרפתית לכל שם עצם יש מין.', text)
        self.assertIn('la maison', text)


class LessonServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = LearningService(self.root)
        self.service._add_source(source(chapters=2))

    def test_one_lesson_call_per_chapter_reaches_reader_and_export(self):
        adapter = Adapter(self.service)
        ready = self.service.start('book-one', 1, configuration(), adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.lesson_calls, 2)
        job = self.service.summary()['jobs'][ready['session_id']]
        self.assertEqual((job['lessons_done'], job['lessons_total']), (2, 2))
        reader = self.service.reader(ready['session_id'], 1)
        self.assertEqual(reader['recap']['lesson']['status'], 'ready')
        body = self.service.export_book(ready['session_id'], format='html')['body']
        body = body.decode('utf-8') if isinstance(body, bytes) else body
        self.assertEqual(body.count('שיעור דקדוק לפרק'), 2)
        # Opening and exporting a prepared book never makes another call.
        self.assertEqual(adapter.lesson_calls, 2)

    def test_invalid_lesson_answer_is_recorded_and_book_is_still_ready(self):
        class BadLesson(Adapter):
            def generate(self, prompt, model):
                if is_lesson(prompt):
                    return TextGenerationResult(status='completed', text='{"oops": 1}',
                        token_usage={'input': 1, 'output': 1, 'cached': 0, 'reasoning': 0},
                        observed_model=model, duration_seconds=0)
                return super().generate(prompt, model)
        ready = self.service.start('book-one', 1, configuration(), BadLesson(self.service).factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        lesson = self.service.reader(ready['session_id'], 0)['recap']['lesson']
        self.assertEqual(lesson['status'], 'unavailable')

    def test_jobs_started_before_lessons_make_no_lesson_call(self):
        adapter = Adapter(self.service)
        stopped = self.service.start('book-one', .000001, configuration(), adapter.factory, background=False)
        sid = stopped['session_id']
        self.assertEqual((stopped['status'], adapter.calls), ('failed', 0))
        del self.service._data['jobs'][sid]['lessons']  # Shape of a job saved by the previous version.
        ready = self.service.resume(sid, adapter.factory, budget_usd=1, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.lesson_calls, 0)
        self.assertNotIn('lesson', self.service.reader(sid, 0)['recap'])
        self.assertNotIn('lessons_total', self.service.summary()['jobs'][sid])

    def assert_single_woven_copy(self, text, chapter):
        """Woven chapter once, then its lesson; never an unwoven second copy of the chapter."""
        woven, tail = f'bonjour, אני קורא את פרק {chapter}', f'כאן נגמר פרק {chapter}.'
        self.assertNotIn(f'שלום, אני קורא את פרק {chapter}', text)
        self.assertEqual(text.count(woven), 1)
        self.assertEqual(text.count(tail), 1)
        self.assertLess(text.index(woven), text.index(tail))

    def test_outputs_hold_one_woven_chapter_followed_by_its_lesson(self):
        from scholarly_translation.learning_contracts import source_hash
        from test_learning_epub_preserve import epub
        unique = source(chapters=2)
        for i, chapter in enumerate(unique['chapters']):
            chapter['units'][0]['text'] = (f'שלום, אני קורא את פרק {i}. ' + 'זהו טקסט בעברית לקריאה. ' * 15 +
                                           f'כאן נגמר פרק {i}.')
        unique['book_id'] = 'book-unique'
        unique['source_hash'] = source_hash(unique)
        self.service._add_source(unique)
        ready = self.service.start('book-unique', 1, configuration(), Adapter(self.service).factory, background=False)
        sid = ready['session_id']
        for i in range(2):
            reader = self.service.reader(sid, i)
            self.assert_single_woven_copy(visible(reader['html']), i)
            self.assertNotIn('כאן נגמר פרק', json.dumps(reader['recap']['lesson'], ensure_ascii=False))
        html = self.service.export_book(sid, format='html')['body']
        html = visible(html.decode('utf-8') if isinstance(html, bytes) else html)
        lessons = [m.start() for m in re.finditer('שיעור דקדוק לפרק', html)]
        self.assertEqual(len(lessons), 2)
        for i in range(2):
            self.assert_single_woven_copy(html, i)
            self.assertLess(html.index(f'כאן נגמר פרק {i}.'), lessons[i])
        self.assertLess(lessons[0], html.index('bonjour, אני קורא את פרק 1'))

        self.service.complete(sid, ready['prepared_hash'], 'complete-unique')
        book = self.service.import_epub(epub('<h1>פרק ראשון</h1><p>שלום, אני קורא את פרק 0. ' +
                                             'זהו טקסט בעברית לקריאה. ' * 15 + 'כאן נגמר פרק 0.</p>'))
        retained = self.service.start(book['book_id'], 1, configuration(), Adapter(self.service).factory,
                                      background=False)
        result = self.service.export_book(retained['session_id'])
        self.assertEqual(result['warnings'], [])
        with zipfile.ZipFile(io.BytesIO(result['body'])) as output:
            chapter = visible(output.read('OPS/chapter.xhtml').decode('utf-8'))
        self.assert_single_woven_copy(chapter, 0)
        self.assertEqual(chapter.count('שיעור דקדוק לפרק'), 1)
        self.assertLess(chapter.index('כאן נגמר פרק 0.'), chapter.index('שיעור דקדוק לפרק'))

    def test_pause_during_lessons_resumes_only_missing_chapters(self):
        class PauseAfterLesson(Adapter):
            def generate(self, prompt, model):
                result = super().generate(prompt, model)
                if is_lesson(prompt) and self.lesson_calls == 1:
                    self.service.pause(next(j['session_id'] for j in self.service._data['jobs'].values()
                                            if j['status'] == 'preparing'))
                return result
        adapter = PauseAfterLesson(self.service)
        paused = self.service.start('book-one', 1, configuration(), adapter.factory, background=False)
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(adapter.lesson_calls, 1)
        ready = self.service.resume(paused['session_id'], adapter.factory, background=False)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(adapter.lesson_calls, 2)
        self.assertEqual(adapter.calls, 2)


if __name__ == '__main__':
    unittest.main()
