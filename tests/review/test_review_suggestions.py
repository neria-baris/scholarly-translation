"""REVIEW-SUGGESTIONS: review suggestions (any unit-review issue, chapter-QA Hebrew quality) are
applied automatically, each once; finished books get their unsent suggestions on resume."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation.translate import chapter_pipeline as pipeline
from scholarly_translation.translate.glossary import new_store
from scholarly_translation.models.adapter import TextGenerationResult
from scholarly_translation.models.config import ModelConfiguration
from scholarly_translation.budget.runtime_controls import ControlStore

from tests.translate.test_lit_notebook_integration import CHAPTERS, FILLER, HEBREW, KEEPER_MARK, config_dict, keeper_json
from tests.sources.test_long_docs_input import XHTML, build_epub
from scholarly_translation.translate import document_draft as dd

CORRECTED = 'הקפטן שאל איפה הלווייתן והים היה רגוע.'
CALM = 'הקפטן שאל איפה הלווייתן והים שקט.'
WHALE_REVIEW = ('VERDICT: REVISE\n\nISSUES:\n'
                '1. Severity: MAJOR\n   Source span: Where is the whale?\n   Translation span: היכן הלווייתן\n'
                '   Problem: register\n   Suggested correction: איפה הלווייתן\n'
                '2. Severity: MINOR\n   Source span: The sea was calm\n   Translation span: והים היה רגוע\n'
                '   Problem: too literal\n   Suggested correction: והים שקט\n')


class ReviewSuggestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[2] / 'outputs'
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        book = Path(cls.temp.name) / 'lit.epub'
        book.write_bytes(build_epub([('c%d.xhtml' % i, XHTML % (body + FILLER)) for i, body in enumerate(CHAPTERS)]))
        cls.structure = dd.extract_structure(book, 'en')
        cls.whale_id = next(u['unit_id'] for u in cls.structure['units'] if 'Where is the whale' in u['text'])
        cls.blows_id = next(u['unit_id'] for u in cls.structure['units'] if 'There she blows' in u['text'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.config = ModelConfiguration.from_dict(config_dict())
        self.calls, self.sent = [], []
        self.qa_category = 'hebrew_quality'

    def factory(self, role, descriptor):
        def generate(prompt, model):
            text = str(prompt)
            if 'Correct ONLY the supplied Hebrew unit' in text:
                payload = json.loads(text.split('\n', 1)[1])
                kind, uid = 'correct', payload['unit_id']
                self.sent.append((uid, sorted(i['severity'] for i in payload['issues'])))
                calm = any(i.get('suggested_correction') == 'והים שקט' for i in payload['issues'])
                out = json.dumps([{'unit_id': uid, 'translation': CALM if calm else CORRECTED, 'translation_note': None}],
                                 ensure_ascii=False)
            elif 'Translate exactly these units' in text:
                kind = 'translate'
                ids = json.loads(re.search(r'TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])', text).group(1))
                out = json.dumps([{'unit_id': u, 'translation': HEBREW, 'translation_note': None} for u in ids],
                                 ensure_ascii=False)
            elif KEEPER_MARK in text:
                kind, out = 'keeper', keeper_json(int(re.search(r'Chapter index: (\d+)', text).group(1)))
            elif role == 'chapter_qa':
                kind = 'qa'
                issue = ('1. Category: %s\n   Severity: MINOR\n   Span: There she blows!\n   Correction: הנה היא נושפת!\n'
                         % self.qa_category) if 'There she blows' in text and 'CHAPTER_LEVEL_NOTES' in text else 'none'
                out = 'VERDICT: %s\nISSUES: %s\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none' % (
                    'PASS' if issue == 'none' else 'REVISE', issue if issue == 'none' else '\n' + issue)
            elif role == 'semantic_reviewer' and re.search(r'TARGET_UNIT_IDS: (\[[^\n]*\])', text).group(1) \
                    == json.dumps([self.whale_id]) and CORRECTED not in text and CALM not in text:
                kind, out = 'review', WHALE_REVIEW
            else:
                kind, out = 'review', 'VERDICT: PASS\nISSUES: none'
            self.calls.append(kind)
            return TextGenerationResult('completed', out, {'input': 100, 'output': 10}, model, 0)
        return SimpleNamespace(generate=generate)

    def job(self):
        return {'job_id': 'suggest-job', 'units': [], 'revision': 0, 'chapter_qa_results': [], 'completed_units': 0,
                'settings': {'quality': 'checked', 'profile': 'literary', 'budget_usd': 30, 'automation': True,
                             'model_config': config_dict()}}

    def execute(self, job):
        with ControlStore(self.folder / 'controls.sqlite3') as store:
            pipeline.execute_document_chapters(job, self.structure, new_store(), self.structure['units'],
                                               self.config, store, self.folder, lambda _: None, self.factory)

    def unit(self, job, uid):
        return next(r for r in job['units'] if r['unit_id'] == uid)

    def test_which_issues_apply_automatically(self):
        self.assertTrue(pipeline._applies_automatically({'severity': 'MINOR', 'translation_span': 'ב'}))
        for category, severity, expected in (('hebrew_quality', 'MINOR', True), ('hebrew_quality', 'MAJOR', True),
                                             ('consistency', 'MAJOR', True), ('consistency', 'MINOR', False),
                                             ('continuity', 'MINOR', False), ('completeness', 'MAJOR', False)):
            self.assertEqual(pipeline._applies_automatically(
                {'category': category, 'severity': severity, 'span': 'x'}), expected, (category, severity))

    def test_new_job_applies_minor_and_hebrew_quality_suggestions_once(self):
        job = self.job()
        self.execute(job)
        self.assertEqual(sorted(self.sent), sorted([(self.whale_id, ['MAJOR', 'MINOR']), (self.blows_id, ['MINOR'])]))
        self.assertEqual(self.unit(job, self.blows_id)['target_text'], CORRECTED)
        self.assertEqual(self.unit(job, self.blows_id)['target_versions'][0]['text'], HEBREW)
        self.assertFalse(any(e['type'] == 'qa_note_retained' for e in job.get('exceptions', [])))
        self.assertEqual(pipeline.review_suggestions(job), {})
        self.calls.clear()
        self.execute(job)
        self.assertNotIn('correct', self.calls)

    def test_minor_consistency_stays_a_retained_note(self):
        self.qa_category = 'consistency'
        job = self.job()
        self.execute(job)
        self.assertNotIn(self.blows_id, [uid for uid, _ in self.sent])
        self.assertTrue(any(e['type'] == 'qa_note_retained' and e['issue']['category'] == 'consistency'
                            for e in job['exceptions']))

    def legacy_book(self):
        """A book finished before 2026-10-10: only the old rule's issues were corrected."""
        job = self.job()
        with patch.object(pipeline, '_applies_automatically', pipeline._corrects_automatically):
            self.execute(job)
        for record in job['units']:
            record.pop('applied_issues', None)
        job['status'] = 'completed'
        self.assertEqual(self.sent, [(self.whale_id, ['MAJOR'])])
        self.calls.clear()
        self.sent.clear()
        return job

    def test_finished_book_gets_its_unsent_suggestions_once(self):
        job = self.legacy_book()
        self.assertEqual(pipeline.review_suggestions(job), {0: 1, 1: 1})
        report = pipeline.enable_review_suggestions(job)
        self.assertEqual(report, {'reopened_chapters': [1, 2], 'units_to_correct': 2})
        self.assertEqual(self.calls, [])                                   # preparing sends nothing
        self.assertEqual(job['status'], 'paused')
        self.assertFalse(any(e['type'] == 'qa_note_retained' for e in job['exceptions']))
        self.execute(job)
        # The whale's MAJOR issue was corrected before; only its MINOR suggestion is sent now.
        self.assertEqual(sorted(self.sent), sorted([(self.whale_id, ['MINOR']), (self.blows_id, ['MINOR'])]))
        self.assertEqual(self.calls.count('correct'), 2)
        self.assertEqual(self.calls.count('review'), 2)                    # one focused recheck each
        self.assertEqual(len(self.unit(job, self.whale_id)['target_versions']), 2)
        self.assertEqual(self.unit(job, self.whale_id)['target_text'], CALM)
        self.assertTrue(all(job['chapter_completion'].values()))
        self.assertEqual(pipeline.review_suggestions(job), {})
        self.calls.clear()
        self.execute(job)
        self.assertNotIn('correct', self.calls)

    def test_human_edits_and_rewritten_spans_are_left_alone(self):
        job = self.legacy_book()
        self.unit(job, self.blows_id)['human_edited'] = True
        self.unit(job, self.whale_id)['target_text'] = 'נוסח אחר לגמרי.'
        self.assertEqual(pipeline.review_suggestions(job), {})
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline.enable_review_suggestions(dict(job, settings=dict(job['settings'], quality='fast')))


if __name__ == '__main__':
    unittest.main()
