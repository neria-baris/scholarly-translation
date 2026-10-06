"""REVIEW-EFFECT salvage: saved review answers an older parser rejected are re-read
without a provider call; the chapter is reopened and the resume runs the correction."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import review_qa as rq
from scholarly_translation import review_salvage
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore
from scholarly_translation.work_journal import WorkJournal

from tests.test_lit_notebook_integration import CHAPTERS, FILLER, HEBREW, KEEPER_MARK, config_dict, keeper_json
from tests.test_long_docs_input import XHTML, build_epub
from scholarly_translation import document_draft as dd

CORRECTED = 'הקפטן שאל איפה הלווייתן והים היה רגוע.'


class ReviewSalvageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / 'outputs'
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        book = Path(cls.temp.name) / 'lit.epub'
        book.write_bytes(build_epub([('c%d.xhtml' % i, XHTML % (body + FILLER)) for i, body in enumerate(CHAPTERS)]))
        cls.structure = dd.extract_structure(book, 'en')
        cls.whale_id = next(u['unit_id'] for u in cls.structure['units'] if 'Where is the whale' in u['text'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.config = ModelConfiguration.from_dict(config_dict())
        self.calls = []

    def factory(self, role, descriptor):
        def generate(prompt, model):
            text = str(prompt)
            if 'Correct ONLY the supplied Hebrew unit' in text:
                kind, uid = 'correct', json.loads(text.split('\n', 1)[1])['unit_id']
                out = json.dumps([{'unit_id': uid, 'translation': CORRECTED, 'translation_note': None}], ensure_ascii=False)
            elif 'Translate exactly these units' in text:
                kind = 'translate'
                ids = json.loads(re.search(r'TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])', text).group(1))
                out = json.dumps([{'unit_id': u, 'translation': HEBREW, 'translation_note': None} for u in ids],
                                 ensure_ascii=False)
            elif KEEPER_MARK in text:
                kind, out = 'keeper', keeper_json(int(re.search(r'Chapter index: (\d+)', text).group(1)))
            elif role == 'chapter_qa':
                kind, out = 'qa', 'VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none'
            elif role == 'semantic_reviewer' and re.search(r'TARGET_UNIT_IDS: (\[[^\n]*\])', text).group(1) \
                    == json.dumps([self.whale_id]):
                kind = 'review'
                out = ('VERDICT: REVISE\n\nISSUES:\n1. Severity: MAJOR\n   Source span: “Where is the whale?”\n'
                       '   Translation span: ״היכן הלווייתן״\n   Problem: register\n'
                       '   Suggested correction: איפה הלווייתן\n') if CORRECTED not in text else 'VERDICT: PASS\nISSUES: none'
            else:
                kind, out = 'review', 'VERDICT: PASS\nISSUES: none'
            self.calls.append(kind)
            return TextGenerationResult('completed', out, {'input': 100, 'output': 10}, model, 0)
        return SimpleNamespace(generate=generate)

    def execute(self, job):
        with ControlStore(self.folder / 'controls.sqlite3') as store:
            pipeline.execute_document_chapters(job, self.structure, new_store(), self.structure['units'],
                                               self.config, store, self.folder, lambda _: None, self.factory)

    def test_rejected_saved_review_is_recovered_and_corrected_on_resume(self):
        job = {'job_id': 'salvage-job', 'units': [], 'revision': 0, 'chapter_qa_results': [], 'completed_units': 0,
               'settings': {'quality': 'checked', 'profile': 'literary', 'budget_usd': 30, 'automation': True,
                            'model_config': config_dict()}}
        old_parser = lambda raw, request: (None, 'issue source span is not a grounded substring of the source')
        with patch.object(rq, '_parse_unit_review_response', side_effect=lambda raw, request: (
                old_parser(raw, request) if raw.startswith('VERDICT: REVISE') else rq_parse(raw, request))):
            self.execute(job)
        self.assertNotIn('correct', self.calls)
        whale = next(r for r in job['units'] if 'Where is the whale' in r['source_text'])
        self.assertEqual(whale['review']['status'], 'needs_human')
        self.assertEqual(review_salvage.candidates(job), (1, 0))
        provider_calls = len(self.calls)

        with WorkJournal(self.folder / 'journal.sqlite3', create=False) as journal:
            report = review_salvage.recheck_saved_reviews(job, journal)
        self.assertEqual(len(self.calls), provider_calls)               # re-reading sends nothing
        self.assertEqual(report['unit_reviews_recovered'], 1)
        self.assertEqual(report['reopened_chapters'], [1])
        self.assertEqual(report['units_to_correct'], 1)
        self.assertEqual(whale['review']['issues'][0]['translation_span'], 'היכן הלווייתן')
        self.assertFalse(any(e['type'] == 'qa_result_needs_human' and e['chapter'] == 1 for e in job['exceptions']))

        self.calls.clear()
        self.execute(job)
        self.assertEqual(self.calls, ['correct', 'review'])               # one correction, one focused recheck
        self.assertEqual(whale['target_text'], CORRECTED)
        self.assertEqual(whale['target_versions'][0]['text'], HEBREW)
        self.assertEqual(whale['recheck']['verdict'], 'PASS')
        self.assertTrue(all(job['chapter_completion'].values()))

    def test_recheck_without_saved_answers_changes_nothing(self):
        job = {'job_id': 'x', 'units': [{'unit_id': 'u', 'source_text': 'Where?', 'target_text': 'איפה?',
                                         'review': {'status': 'needs_human'}}],
               'chapter_groups': [['u']], 'chapter_qa_results': [], 'chapter_completion': {'0': True},
               'settings': {'profile': 'literary', 'model_config': config_dict()}}
        with WorkJournal(self.folder / 'journal.sqlite3') as journal:
            report = review_salvage.recheck_saved_reviews(job, journal)
        self.assertEqual(report['no_saved_answer'], 1)
        self.assertEqual(report['reopened_chapters'], [])
        self.assertTrue(job['chapter_completion']['0'])


rq_parse = rq._parse_unit_review_response

if __name__ == '__main__':
    unittest.main()
