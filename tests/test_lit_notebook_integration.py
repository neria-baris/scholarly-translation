"""LIT-NOTEBOOK integration: rolling book notebook wired into the chapter engine,
previews, QA and the results download route. Offline: mock adapters only."""
import json
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import book_notebook as bn
from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation import document_draft as dd
from scholarly_translation import web_ui
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.runtime_controls import ControlStore
from scholarly_translation.work_journal import WorkJournal

from tests.test_long_docs_input import XHTML, build_epub

CHAPTERS = [
    ('<h1>One</h1><p>"Where is the whale?" asked Captain Ahab. The sea was calm and the crew was silent.</p>'
     '<p>The mate shrugged. It was a long morning at sea, and the water lay flat.</p>'),
    ('<h1>Two</h1><p>Ahab kept silent before the mate. "There she blows!" cried the lookout from above.</p>'
     '<p>The crew ran to the rail. The captain stared ahead that day.</p>'),
]
FILLER = ''.join('<p>The sea went on and on while the crew kept watch over the water, watch section %s of the long watch.</p>' % i
                 for i in 'abcdefghijklmnopqrst')
HEADER = 'BOOK_NOTEBOOK (memory of this book'
KEEPER_MARK = 'rolling NOTEBOOK for a book'
HEBREW = 'הקפטן שאל היכן הלווייתן והים היה רגוע.'


def config_dict(with_state_builder=False):
    def role(provider, model):
        return {'provider': provider, 'model': model, 'capabilities': {
            'context_window': 1000000, 'usable_context_tokens': 800000, 'max_output_tokens': 128000}}
    models = {'translator': role('openai', 'gpt-6.1-sol'), 'semantic_reviewer': role('openai', 'gpt-6-luna'),
              'chapter_qa': role('openai', 'gpt-6-luna')}
    if with_state_builder:
        models['context_state_builder'] = role('openai', 'gpt-6-luna')
    return {'schema_version': 1, 'providers': {'openai': {'type': 'openai', 'credential_env': 'OPENAI_API_KEY'}},
            'models': models}


def keeper_json(chapter):
    ops = ([{'op': 'add', 'tags': ['character', 'name'], 'title': 'Captain Ahab', 'note': 'Captain; stern voice.',
             'hebrew_rendering': 'אחאב', 'match_terms': ['Ahab'], 'scope': 'local'}] if chapter == 0 else [])
    return json.dumps({'ops': ops, 'chapter_summary': 'Summary of chapter %d: Ahab at sea.' % (chapter + 1),
                       'story_so_far': 'Ahab hunts.'})


class LitNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / 'outputs'
        scratch.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        cls.book = Path(cls.temp.name) / 'lit.epub'
        cls.book.write_bytes(build_epub([('c%d.xhtml' % i, XHTML % (body + FILLER)) for i, body in enumerate(CHAPTERS)]))
        cls.structure = dd.extract_structure(cls.book, 'en')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.config = ModelConfiguration.from_dict(config_dict())
        self.calls = []

    def job(self, quality='fast', profile='literary'):
        return {'job_id': 'lit-job', 'settings': {'quality': quality, 'profile': profile, 'budget_usd': 30},
                'units': [], 'revision': 0, 'chapter_qa_results': [], 'completed_units': 0}

    def factory(self, keeper_text=None, pause_after_translation=None):
        def make(role, descriptor):
            def generate(prompt, model):
                prompt = str(prompt)
                if 'Translate exactly these units' in prompt:
                    kind = 'translate'
                    ids = json.loads(re.search(r'TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])', prompt).group(1))
                    text = json.dumps([{'unit_id': uid, 'translation': HEBREW, 'translation_note': None}
                                       for uid in ids], ensure_ascii=False)
                elif KEEPER_MARK in prompt:
                    kind = 'keeper'
                    chapter = int(re.search(r'Chapter index: (\d+)', prompt).group(1))
                    text = keeper_text if keeper_text is not None else keeper_json(chapter)
                elif role == 'chapter_qa':
                    kind = 'qa'
                    text = 'VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none'
                else:
                    kind = 'review'
                    text = 'VERDICT: PASS\nISSUES: none'
                self.calls.append((kind, prompt))
                if pause_after_translation == len([c for c in self.calls if c[0] == 'translate']) and kind == 'translate':
                    with WorkJournal(self.folder / 'journal.sqlite3', create=False) as journal:
                        journal.pause('lit-job')
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

    # (a)
    def test_fast_mode_runs_translator_then_keeper_per_chapter(self):
        job = self.job()
        self.execute(job, self.factory())
        self.assertEqual(self.kinds(), ['translate', 'keeper', 'translate', 'keeper'])
        nb = job['book_notebook']
        bn.validate_notebook(nb)
        self.assertEqual(sorted(nb['chapter_summaries']), ['0', '1'])
        self.assertEqual([e['title'] for e in nb['entries']], ['Captain Ahab'])
        self.assertEqual([r['status'] for r in job['notebook_reports']], ['ok', 'ok'])
        self.assertTrue(all(job['chapter_completion'].values()))
        self.assertEqual(job['review_notes'] if 'review_notes' in job else [], [])

    # (b)
    def test_chapter_two_translation_sees_notebook_summary_and_previous_passage(self):
        job = self.job()
        self.execute(job, self.factory())
        first, second = self.prompts('translate')
        self.assertNotIn('PREVIOUS_PASSAGE', first)
        self.assertIn(HEADER, second)
        self.assertIn('Captain Ahab', second)
        self.assertIn('Summary of chapter 1', second)
        self.assertIn('PREVIOUS_PASSAGE', second)
        self.assertIn('SOURCE_END', second)
        self.assertIn(HEBREW, second.split('PREVIOUS_PASSAGE', 1)[1])
        self.assertNotIn('PERSISTENT_DOCUMENT_STATE', second)
        # The cacheable source prefix stays before the notebook/bridge suffix.
        self.assertLess(second.index('SOURCE_UNITS'), second.index(HEADER))

    # (c)
    def test_checked_qa_prompt_contains_updated_notebook(self):
        job = self.job('checked')
        self.execute(job, self.factory())
        qa = self.prompts('qa')
        self.assertEqual(len(qa), 2)
        self.assertIn('Captain Ahab', qa[0])  # chapter 1's QA sees the keeper's chapter-1 update
        self.assertIn('Summary of chapter 2', qa[1])
        order = self.kinds()
        self.assertLess(order.index('keeper'), order.index('qa'))

    # (d)
    def test_garbage_keeper_output_degrades_with_visible_note(self):
        job = self.job()
        self.execute(job, self.factory(keeper_text='I could not do this, sorry'))
        self.assertTrue(all(job['chapter_completion'].values()))
        self.assertEqual(job['book_notebook']['entries'], [])
        self.assertEqual([r['status'] for r in job['notebook_reports']], ['unparsed', 'unparsed'])
        self.assertTrue(any('מחברת הספר' in note for note in job['review_notes']))

    # (e)
    def test_pause_before_keeper_resumes_without_resending_translation_and_same_keeper_prompt(self):
        clean = self.job()
        self.execute(clean, self.factory())
        clean_calls = list(self.calls)
        self.folder = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.calls = []
        job = self.job()
        with self.assertRaises(pipeline.PipelinePaused):
            self.execute(job, self.factory(pause_after_translation=1))
        self.assertEqual(self.kinds(), ['translate'])
        with WorkJournal(self.folder / 'journal.sqlite3', create=False) as journal:
            journal.resume('lit-job')
        self.execute(job, self.factory())
        self.assertEqual(self.kinds(), ['translate', 'keeper', 'translate', 'keeper'])
        self.assertEqual([p for k, p in self.calls if k == 'keeper'], [p for k, p in clean_calls if k == 'keeper'])
        self.assertEqual([p for k, p in self.calls if k == 'translate'], [p for k, p in clean_calls if k == 'translate'])
        self.assertEqual(len(job['units']), len(self.structure['units']))

    # (f)
    def test_legacy_job_keeps_document_state_and_makes_no_keeper_calls(self):
        job = self.job()
        groups = pipeline._job_chapter_groups(job, self.structure, new_store(), self.structure['units'], self.config,
                                              'fast', 'literary')
        ids = [[u['unit_id'] for u in g] for g in groups]
        from scholarly_translation import document_state as ds
        state = ds.new_document_state(self.structure['document_id'])
        plans = [pipeline.plan_chapter(self.structure, new_store(), g, self.config, 'fast', 'literary') for g in ids]
        job.update(chapter_plans=plans, chapter_groups=ids, chapter_states={}, chapter_completion={},
                   document_state=state, glossary=new_store())
        self.assertFalse(pipeline.is_notebook_job(job))
        self.execute(job, self.factory())
        self.assertEqual(self.kinds(), ['translate', 'translate'])
        self.assertNotIn('book_notebook', job)
        for prompt in self.prompts('translate'):
            self.assertIn('PERSISTENT_DOCUMENT_STATE', prompt)
            self.assertNotIn(HEADER, prompt)

    # (g)
    def test_preview_includes_keeper_cost_in_every_mode(self):
        groups = [[u['unit_id'] for u in self.structure['units'][:2]], [u['unit_id'] for u in self.structure['units'][2:]]]
        for quality in ('fast', 'checked', 'thorough'):
            for ids in groups:
                with_keeper = pipeline.estimate_preview(self.structure, new_store(), ids, self.config, quality, 'literary')
                without = pipeline.plan_chapter(self.structure, new_store(), ids, self.config, quality, 'literary')
                row = with_keeper['role_usage']['notebook_keeper']
                self.assertEqual(row['calls'], 1)
                self.assertGreater(row['conservative_cost_usd'], 0)
                self.assertEqual(with_keeper['notebook_keeper']['role'], 'chapter_qa')
                self.assertEqual(with_keeper['notebook_keeper']['call_output_cap'],
                                 pipeline.keeper_output_cap(self.config.resolve('chapter_qa')[0]))
                self.assertNotIn('notebook_keeper', without['role_usage'])
                self.assertGreater(with_keeper['conservative_total_ceiling_usd'], without['conservative_total_ceiling_usd'])
                self.assertGreater(with_keeper['expected_total_cost_usd'], without['expected_total_cost_usd'])
                self.assertEqual(set(without['role_usage']) | {'notebook_keeper'}, set(with_keeper['role_usage']))

    def test_keeper_role_prefers_state_builder_then_qa_then_translator(self):
        cfg = ModelConfiguration.from_dict(config_dict(with_state_builder=True))
        self.assertEqual(pipeline.resolve_keeper_role(cfg), 'context_state_builder')
        self.assertEqual(pipeline.resolve_keeper_role(self.config), 'chapter_qa')
        data = config_dict()
        del data['models']['chapter_qa'], data['models']['semantic_reviewer']
        self.assertEqual(pipeline.resolve_keeper_role(ModelConfiguration.from_dict(data)), 'translator')

    def test_oversized_chapter_sends_bounded_keeper_prompt(self):
        small = dict(config_dict())
        small['models'] = {k: dict(v, capabilities=dict(v['capabilities'], context_window=9000, usable_context_tokens=9000,
                                                        max_output_tokens=2000)) for k, v in small['models'].items()}
        selection, _ = ModelConfiguration.from_dict(small).resolve('chapter_qa')
        source, hebrew = 'word ' * 20000, 'מילה ' * 20000
        prompt, fits = pipeline._bounded_keeper_prompt(source, hebrew, 'BOOK_NOTEBOOK:\n', 3, 'literary', selection,
                                                       pipeline.keeper_output_cap(selection))
        self.assertTrue(fits)
        self.assertIn('middle omitted', prompt)
        self.assertLess(len(prompt), len(source))

    def test_bridge_is_bounded_and_starts_at_a_boundary(self):
        text = ' '.join('Sentence number %d ends here.' % i for i in range(200))
        tail = pipeline._tail_at_boundary(text)
        self.assertLessEqual(len(tail), pipeline.BRIDGE_CHARS)
        self.assertTrue(tail.startswith('Sentence'))
        self.assertEqual(pipeline._tail_at_boundary('short text'), 'short text')

    # (i)
    def test_literary_risk_triggers_reach_unit_review_in_checked_mode(self):
        literary = self.job('checked', 'literary')
        self.execute(literary, self.factory())
        self.assertTrue(any('Where is the whale' in p for p in self.prompts('review')))
        dialogue = next(r for r in literary['units'] if 'Where is the whale' in r['source_text'])
        clean = dict(dialogue, findings=[], translation_note=None)
        self.assertIn('literary_dialogue', pipeline.detect_risk_triggers(clean, 'literary')['configured_risk_flags'])
        self.assertEqual(pipeline.detect_risk_triggers(clean, 'scholarly')['configured_risk_flags'], [])

    # (h)
    def test_notebook_markdown_download_route(self):
        job = self.job()
        self.execute(job, self.factory())
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        job_id = 'a' * 32
        folder = root / 'documents' / job_id
        folder.mkdir(parents=True)
        stored = dict(job, job_id=job_id, status='completed', filename='moby.epub', source_kind='epub')
        (folder / 'job.json').write_text(json.dumps(stored, ensure_ascii=False), encoding='utf-8')
        plain = 'b' * 32
        (root / 'documents' / plain).mkdir()
        (root / 'documents' / plain / 'job.json').write_text(json.dumps(
            {'job_id': plain, 'status': 'completed', 'filename': 'x.pdf', 'source_kind': 'pdf'}), encoding='utf-8')
        with patch.object(web_ui, 'OUTPUT_ROOT', root), patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            server = ThreadingHTTPServer(('127.0.0.1', 0), web_ui.make_handler('tok'))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = 'http://127.0.0.1:%d' % server.server_port
            def post(payload, token='tok'):
                request = Request(url + '/document-notebook', data=json.dumps(payload).encode(),
                                  headers={'Content-Type': 'application/json', 'X-UI-Token': token, 'Origin': url},
                                  method='POST')
                return urlopen(request, timeout=15)
            try:
                with post({'job_id': job_id}) as response:
                    body = response.read().decode('utf-8')
                    self.assertEqual(response.status, 200)
                    self.assertIn('markdown', response.headers['Content-Type'])
                    self.assertIn('attachment', response.headers['Content-Disposition'])
                self.assertEqual(body, bn.render_markdown(job['book_notebook']))
                self.assertIn('Captain Ahab', body)
                for payload, token, code in (({'job_id': job_id}, 'bad', 403), ({'job_id': 'c' * 32}, 'tok', 404),
                                             ({'job_id': plain}, 'tok', 404), ({'job_id': '../x'}, 'tok', 404)):
                    with self.assertRaises(HTTPError) as caught:
                        post(payload, token)
                    self.assertEqual(caught.exception.code, code)
                    caught.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
