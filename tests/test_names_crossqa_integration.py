"""NAMES-CROSSQA integration: name table before chapter 1, NAMES in every prompt, cross-chapter
QA windows 1-8, 8-15 ... with the overlap chapter as the reference, automatic corrections,
and preparing an existing book. Offline: mock adapters only."""
import json
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import document_draft as dd
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore

from tests.test_lit_notebook_integration import FILLER, config_dict
from tests.test_long_docs_input import XHTML, build_epub

CHAPTER_COUNT = 10
NAMES_MARK = 'NAME TABLE of a book'
CROSS_MARK = 'several consecutive chapters'
KEEPER_MARK = 'rolling NOTEBOOK for a book'
CORRECTION_MARK = 'Correct ONLY the supplied Hebrew unit'
WRONG, RIGHT = 'שיי', 'שֵׁאי'
SHOWN = 'שאי'
HEBREW = WRONG + ' הלכה הביתה לאורך הנמל, והים היה שקט.'


def chapter(i):
    return ('<h1>Chapter %d</h1><p>Shae walked home along the harbour in chapter %d. The sea was quiet.</p>'
            '<p>Shae met Woon at the gate and they spoke about the clan.</p>' % (i, i)) + FILLER


class NamesCrossQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / 'outputs'
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        book = Path(cls.temp.name) / 'names.epub'
        book.write_bytes(build_epub([('c%d.xhtml' % i, XHTML % chapter(i + 1)) for i in range(CHAPTER_COUNT)]))
        cls.structure = dd.extract_structure(book, 'en')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.config = ModelConfiguration.from_dict(config_dict())
        self.calls = []

    def job(self, quality='checked'):
        return {'job_id': 'names-job', 'settings': {'quality': quality, 'profile': 'literary', 'budget_usd': 30,
                                                    'automation': True},
                'units': [], 'revision': 0, 'chapter_qa_results': [], 'completed_units': 0}

    def factory(self, names_text=None, cross_issue_window=1):
        def make(role, descriptor):
            def generate(prompt, model):
                prompt = str(prompt)
                if CORRECTION_MARK in prompt:
                    kind = 'correct'
                    payload = json.loads(prompt[prompt.index('{', prompt.index(CORRECTION_MARK)):])
                    text = json.dumps([{'unit_id': payload['unit_id'],
                                        'translation': payload['current_hebrew'].replace(WRONG, RIGHT),
                                        'translation_note': None}], ensure_ascii=False)
                elif 'Translate exactly these units' in prompt:
                    kind = 'translate'
                    ids = json.loads(re.search(r'TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])', prompt).group(1))
                    text = json.dumps([{'unit_id': uid, 'translation': HEBREW, 'translation_note': None}
                                       for uid in ids], ensure_ascii=False)
                elif NAMES_MARK in prompt:
                    kind = 'names'
                    chunk = re.findall(r'=== CHAPTER (\d+) ===', prompt)
                    if names_text is not None:
                        text = names_text if not callable(names_text) else names_text(chunk)
                    elif '1' in chunk:
                        text = json.dumps({'names': [
                            {'source': 'Shae', 'aliases': ['Kaul Shae'], 'hebrew': RIGHT, 'kind': 'character',
                             'gender': 'female'},
                            {'source': 'Woon', 'hebrew': 'ווּן', 'kind': 'character', 'gender': 'male',
                             'note': 'distinct from Wen'}]}, ensure_ascii=False)
                    else:
                        text = json.dumps({'names': [{'source': 'Gate Chapter %s' % chunk[0],
                                                      'hebrew': 'שער %s' % chunk[0], 'kind': 'place'}]})
                elif CROSS_MARK in prompt:
                    kind = 'cross'
                    windows = len([c for c in self.calls if c[0] == 'cross'])
                    if windows == cross_issue_window:
                        text = ('VERDICT: REVISE\nISSUES:\n1. Category: consistency\n   Severity: MAJOR\n'
                                '   Span: %s\n   Correction: %s\nNOTES: none' % (WRONG, RIGHT))
                    else:
                        text = 'VERDICT: PASS\nISSUES: none\nNOTES: none'
                elif KEEPER_MARK in prompt:
                    kind = 'keeper'
                    text = json.dumps({'ops': [], 'chapter_summary': 'A chapter.', 'story_so_far': 'Shae walks.',
                                       'names': [{'source': 'Harbour Master', 'hebrew': 'מנהל הנמל',
                                                  'kind': 'title', 'gender': 'male'}]})
                elif role == 'chapter_qa':
                    kind = 'qa'
                    text = 'VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none'
                else:
                    kind = 'review'
                    text = 'VERDICT: PASS\nISSUES: none'
                self.calls.append((kind, prompt))
                return TextGenerationResult('completed', text, {'input': 100, 'output': 10}, model, 0)
            return SimpleNamespace(generate=generate)
        return make

    def execute(self, job, factory):
        with ControlStore(self.folder / 'controls.sqlite3') as store:
            pipeline.execute_document_chapters(job, self.structure, new_store(), self.structure['units'],
                                               self.config, store, self.folder, lambda _: None, factory)

    def kinds(self):
        return [k for k, _ in self.calls]

    def prompts(self, kind):
        return [p for k, p in self.calls if k == kind]

    def chapter_units(self, job, index):
        ids = set(job['chapter_groups'][index])
        return [r for r in job['units'] if r['unit_id'] in ids]

    def test_name_table_is_built_first_and_reaches_every_role(self):
        job = self.job()
        self.execute(job, self.factory())
        self.assertEqual(self.kinds()[0], 'names')
        table = job['name_table']
        self.assertEqual(table['status'], 'ready')
        by_source = {e['source']: e for e in table['entries']}
        self.assertEqual(by_source['Shae']['hebrew'], RIGHT)
        self.assertEqual(by_source['Shae']['origin'], 'prepass')
        self.assertEqual(by_source['Harbour Master']['origin'], 'keeper')   # added by the keeper, add-only
        line = '→ ' + SHOWN   # NAMES shows the plain form (EXPORT-NIQQUD)
        for kind in ('translate', 'qa', 'keeper'):
            self.assertTrue(all(line in p for p in self.prompts(kind)), kind)
        # A unit review gets only the names of its own unit.
        self.assertTrue(any(line in p for p in self.prompts('review')))
        self.assertFalse(all(line in p for p in self.prompts('review')))
        self.assertFalse(any('{{NAMES_TABLE}}' in p for p in self.prompts('keeper')))

    def test_windows_run_every_eight_chapters_with_the_overlap_chapter_as_reference(self):
        job = self.job()
        self.execute(job, self.factory())
        self.assertEqual(sorted(job['cross_qa']['windows']), ['0-7', '7-9'])
        self.assertTrue(all(w['status'] == 'completed' for w in job['cross_qa']['windows'].values()))
        order = self.kinds()
        first_cross = order.index('cross')
        translations = [i for i, k in enumerate(order) if k == 'translate']
        self.assertGreater(first_cross, translations[7])     # after chapter 8 ...
        self.assertLess(first_cross, translations[8])        # ... before chapter 9
        first, second = self.prompts('cross')
        self.assertIn('=== CHAPTER 1 — SOURCE ===', first)
        self.assertNotIn('(REFERENCE)', first)
        self.assertIn('=== CHAPTER 8 (REFERENCE) — HEBREW ===', second)
        self.assertIn('Chapter 8 was already checked', second)
        self.assertIn('=== CHAPTER 10 — HEBREW ===', second)
        # The window-2 issue is corrected only after the reference chapter: chapter 8 decides.
        for record in self.chapter_units(job, 7):
            self.assertIn(WRONG, record['target_text'])
            self.assertFalse(any(v['reason'] == 'cross_chapter_correction' for v in record['target_versions']))
        for index in (8, 9):
            for record in self.chapter_units(job, index):
                self.assertNotIn(WRONG, record['target_text'])
                self.assertEqual(record['target_versions'][-1]['reason'], 'cross_chapter_correction')
                self.assertEqual(record['recheck']['verdict'], 'PASS')
        corrected = len(self.chapter_units(job, 8)) + len(self.chapter_units(job, 9))
        self.assertEqual(len(self.prompts('correct')), corrected)

    def test_resume_does_not_repeat_completed_windows(self):
        job = self.job()
        self.execute(job, self.factory())
        before = len(self.calls)
        self.execute(job, self.factory())
        self.assertEqual(len(self.calls), before)

    def test_fast_quality_builds_the_table_but_runs_no_cross_qa(self):
        job = self.job('fast')
        self.execute(job, self.factory())
        self.assertIn('names', self.kinds())
        self.assertNotIn('cross', self.kinds())

    def test_broken_name_table_answer_is_skipped_with_a_note(self):
        job = self.job()
        self.execute(job, self.factory(names_text='not json at all'))
        self.assertEqual(job['name_table']['status'], 'skipped')
        self.assertIn(pipeline.NAME_TABLE_SKIPPED_NOTE, job['review_notes'])
        self.assertTrue(all(job['chapter_completion'].values()))
        self.assertTrue(any(e['origin'] == 'keeper' for e in job['name_table']['entries']))

    def test_existing_book_is_prepared_then_reviewed_on_resume(self):
        job = self.job()
        self.execute(job, self.factory())
        # Simulate a book translated before NAMES-CROSSQA.
        for key in ('name_table', 'cross_qa'):
            job.pop(key)
        self.assertTrue(pipeline.cross_review_available(job))
        job['status'] = 'completed'
        self.assertEqual(pipeline.enable_cross_review(job), {'windows': 2})
        self.assertFalse(pipeline.cross_review_available(job))
        self.calls = []
        self.execute(job, self.factory(cross_issue_window=99))
        # Nothing is retranslated; identical earlier answers are replayed from the journal.
        self.assertFalse({'translate', 'keeper', 'qa', 'review'} & set(self.kinds()))
        self.assertEqual(job['name_table']['status'], 'ready')
        self.assertTrue(job['name_table']['entries'])
        self.assertEqual({k: w['status'] for k, w in job['cross_qa']['windows'].items()},
                         {'0-7': 'completed', '7-9': 'completed'})

    def test_name_table_reads_the_original_book_in_chunks(self):
        job = self.job('fast')
        with unittest.mock.patch.object(pipeline, 'NAME_SOURCE_CHUNK_TOKENS', 1):   # one chapter per chunk
            self.execute(job, self.factory())
        prompts = self.prompts('names')
        self.assertEqual(len(prompts), CHAPTER_COUNT)
        self.assertIn('=== CHAPTER 1 ===', prompts[0])
        self.assertIn('Shae walked home along the harbour in chapter 1.', prompts[0])   # the original text itself
        self.assertNotIn(HEBREW, prompts[0])
        self.assertIn('→ ' + SHOWN, prompts[1])          # later chunks see the names decided so far
        table = job['name_table']
        self.assertEqual((table['status'], table['chunks_done'], len(table['chunks'])), ('ready', 10, 10))
        self.assertEqual(self.kinds()[:CHAPTER_COUNT], ['names'] * CHAPTER_COUNT)   # all before chapter 1

    def test_failed_chunk_keeps_names_and_resume_continues_with_the_next_chunk(self):
        job = self.job('fast')
        def answer(chunk):
            return 'not json' if chunk == ['2'] else json.dumps({'names': []})
        with unittest.mock.patch.object(pipeline, 'NAME_SOURCE_CHUNK_TOKENS', 1):
            self.execute(job, self.factory())   # build normally first to have a journal ...
        # ... then simulate an older job whose table stopped after chunk 1.
        job['name_table'] = dict(job['name_table'], status='pending', chunks=job['name_table']['chunks'][:1],
                                 chunks_done=1)
        self.calls = []
        with unittest.mock.patch.object(pipeline, 'NAME_SOURCE_CHUNK_TOKENS', 1):
            self.execute(job, self.factory(names_text=answer))
        self.assertEqual(re.findall(r'=== CHAPTER (\d+) ===', self.prompts('names')[0]), ['2'])
        self.assertEqual(job['name_table']['status'], 'skipped')
        self.assertEqual(job['name_table']['chunks_done'], 1)
        self.assertIn(pipeline.NAME_TABLE_SKIPPED_NOTE, job['review_notes'])

    def test_completed_check_can_run_again(self):
        job = self.job()
        self.execute(job, self.factory())
        self.assertTrue(pipeline.cross_review_available(job))     # every window completed
        self.assertEqual(pipeline.enable_cross_review(job), {'windows': 2, 'rerun': True})
        self.assertEqual(len(job['cross_qa']['history']), 1)
        self.assertEqual(job['cross_qa']['windows'], {})
        self.calls = []
        self.execute(job, self.factory(cross_issue_window=99))
        self.assertFalse({'translate', 'keeper', 'names'} & set(self.kinds()))
        self.assertEqual({k: w['status'] for k, w in job['cross_qa']['windows'].items()},
                         {'0-7': 'completed', '7-9': 'completed'})

    def test_enable_refuses_fast_and_non_notebook_jobs(self):
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline.enable_cross_review({'settings': {'automation': True, 'quality': 'checked'}})
        job = self.job('fast')
        self.execute(job, self.factory())
        self.assertFalse(pipeline.cross_review_available(job))
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline.enable_cross_review(job)

    def test_successful_keeper_retires_its_chapter_failure_note(self):
        job = {'review_notes': [pipeline.KEEPER_SKIPPED_NOTE % 3, pipeline.KEEPER_SKIPPED_NOTE % 4]}
        pipeline._clear_keeper_notes(job, 2)
        self.assertEqual(job['review_notes'], [pipeline.KEEPER_SKIPPED_NOTE % 4])

    def test_first_chunk_sets_the_book_voice(self):
        # BOOK-VOICE: only the first source-pass step asks; its register and key words reach the notebook.
        job = self.job('fast')
        def answer(chunk):
            names = {'names': [{'source': 'Shae', 'hebrew': RIGHT, 'kind': 'character', 'gender': 'female'}]}
            if chunk[0] == '1':
                names['voice'] = {'register': 'עברית ספרותית מאופקת', 'key_words': [
                    {'source': 'harbour', 'forms': ['harbours'], 'hebrew': 'נמל', 'note': 'קבוע'}]}
            return json.dumps(names, ensure_ascii=False) if chunk[0] in ('1', '2') else json.dumps({'names': []})
        with unittest.mock.patch.object(pipeline, 'NAME_SOURCE_CHUNK_TOKENS', 1):
            self.execute(job, self.factory(names_text=answer))
        prompts = self.prompts('names')
        self.assertIn('- VOICE (this first step only)', prompts[0])
        self.assertFalse(any('- VOICE' in p for p in prompts[1:]))
        titles = [e['title'] for e in job['book_notebook']['entries']]
        self.assertIn('משלב וקול הספר', titles)
        self.assertIn('מילת מפתח: harbour', titles)
        self.assertEqual(job['name_table']['status'], 'ready')
        self.assertTrue(all('עברית ספרותית מאופקת' in p for p in self.prompts('translate')))

    def test_broken_voice_changes_nothing_else(self):
        job = self.job('fast')
        def answer(chunk):
            return json.dumps({'names': [{'source': 'Shae', 'hebrew': RIGHT, 'kind': 'character',
                                          'gender': 'female'}], 'voice': 'garbage'}, ensure_ascii=False)
        self.execute(job, self.factory(names_text=answer))
        self.assertEqual(job['name_table']['status'], 'ready')
        self.assertEqual(job['name_table']['entries'][0]['origin'], 'prepass')
        self.assertNotIn('משלב וקול הספר', [e['title'] for e in job['book_notebook']['entries']])


if __name__ == '__main__':
    unittest.main()
