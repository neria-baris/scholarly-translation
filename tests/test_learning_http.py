import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import web_ui
from scholarly_translation.learning_service import LearningService
from test_learning_import import _completed_job_snapshot, _hebrew_epub_bytes
from test_learning_integration import Adapter, configuration, source


class LearningHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = LearningService(self.root / 'learning')
        self.output_patch = patch.object(web_ui, 'OUTPUT_ROOT', self.root / 'ui')
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web_ui.make_handler('test-token', learning_service=self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def post(self, path, data, *, token='test-token', origin=None, raw=False):
        body = data if raw else json.dumps(data).encode()
        headers = {'X-UI-Token': token, 'Content-Type': 'application/epub+zip' if raw else 'application/json'}
        if origin:
            headers['Origin'] = origin
        try:
            with urlopen(Request(self.base + path, body, headers), timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def test_token_and_origin_guards_cover_learning_routes(self):
        for path, body in [('/learning/state', {}), ('/learning/import-translation', {'job_id': 'bad'})]:
            self.assertEqual(self.post(path, body, token='wrong')[0], 403)
            self.assertEqual(self.post(path, body, origin='https://example.org')[0], 403)
        self.assertEqual(self.service.summary()['books'], [])

    def test_grammar_notebook_route_is_guarded_and_makes_no_call(self):
        self.assertEqual(self.post('/learning/grammar-notebook', {}, token='wrong')[0], 403)
        with patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('unexpected provider')):
            status, notebook = self.post('/learning/grammar-notebook', {})
        self.assertEqual(status, 200)
        self.assertEqual(notebook['books'], [])

    def test_import_upload_and_state_never_send_provider_calls(self):
        with patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('unexpected provider')):
            status, book = self.post('/learning/upload-epub?name=book.epub', _hebrew_epub_bytes(), raw=True)
            self.assertEqual(status, 200)
            status, summary = self.post('/learning/state', {})
            self.assertEqual(status, 200)
            self.assertEqual(summary['books'][0]['book_id'], book['book_id'])
            self.assertEqual(summary['sessions'], [])

    def test_handoff_is_server_snapshot_and_unfinished_job_refused(self):
        with patch('scholarly_translation.document_draft.DocumentJobs.get', return_value=_completed_job_snapshot()) as get:
            status, book = self.post('/learning/import-translation', {'job_id': 'requested-job'})
            self.assertEqual(status, 200)
            get.assert_called_once_with('requested-job')
            self.assertEqual(book['origin'], 'translation_library')
        snapshot = _completed_job_snapshot()
        snapshot['status'] = 'translating'
        with patch('scholarly_translation.document_draft.DocumentJobs.get', return_value=snapshot):
            self.assertEqual(self.post('/learning/import-translation', {'job_id': 'active-job'})[0], 400)

    def test_missing_key_prevents_any_learning_job(self):
        with patch.dict('os.environ', {}, clear=True):
            status, response = self.post('/learning/prepare', {'book_id': 'any', 'budget_usd': 1})
        self.assertEqual(status, 400)
        self.assertEqual(response['code'], 'missing_api_key')
        self.assertEqual(self.service.summary()['sessions'], [])

    def test_reader_forwards_display_choice_without_starting_generation(self):
        with patch.object(self.service, 'reader', return_value={'html': 'fixture'}) as reader:
            status, response = self.post('/learning/read', {'session_id': 'demo', 'gloss_on_click': True})
            self.assertEqual(status, 200)
            self.assertEqual(response['html'], 'fixture')
            reader.assert_called_once_with('demo', 0, gloss_on_click=True)

    def test_language_selection_and_help_use_the_learning_boundary(self):
        self.assertEqual(self.post('/learning/language', {'language': 'yi'}, token='wrong')[0], 403)
        status, state = self.post('/learning/language', {'language': 'yi'})
        self.assertEqual(status, 200)
        self.assertEqual(state['selected_language'], 'yi')
        self.assertTrue(all(row['available'] for row in state['languages']))
        with urlopen(self.base + '/learning/help') as response:
            self.assertIn('עזרה', response.read().decode('utf-8'))
        with patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('unexpected generation')):
            self.assertEqual(self.post('/learning/language', {'language': 'it'})[0], 200)

    def test_resume_forwards_explicit_user_options(self):
        with patch.object(self.service, 'resume', return_value={'status': 'paused'}) as resume:
            # The adapter key gate is intentionally exercised separately by the
            # existing missing-key test; use the route's existing model fixture.
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-test-key'}):
                status, _ = self.post('/learning/resume', {'session_id': 'demo', 'budget_usd': 200,
                    'context_chars': 40000, 'output_tokens': 12000, 'retry': True})
            self.assertEqual(status, 200)
            self.assertEqual(resume.call_args.kwargs, {'budget_usd': 200, 'context_chars': 40000,
                                                       'output_tokens': 12000, 'retry': True})

    def test_legacy_home_and_wordlists_still_available(self):
        with urlopen(self.base + '/') as response:
            self.assertIn('תרגום מסמכים', response.read().decode())
        with urlopen(self.base + '/learning/wordlist?language=yi') as response:
            self.assertIn('500', response.read().decode())
        status, _ = self.post('/learning/upload-epub?name=book.pdf', b'bad', raw=True)
        self.assertEqual(status, 400)

    def test_export_is_guarded_binary_download_without_api_key(self):
        self.assertEqual(self.post('/learning/export', {'session_id': 'any'}, token='wrong')[0], 403)
        self.assertEqual(self.post('/learning/export', {'session_id': 'any'}, origin='https://example.org')[0], 403)
        self.service._add_source(source())
        adapter = Adapter(self.service)
        ready = self.service.start('book-one', 1, configuration(), adapter.factory, background=False)
        with patch.dict('os.environ', {}, clear=True), patch('scholarly_translation.model_adapter.build_translation_adapter', side_effect=AssertionError('unexpected provider')):
            for format, content_type in [('epub', 'application/epub+zip'), ('html', 'text/html; charset=utf-8')]:
                data = json.dumps({'session_id': ready['session_id'], 'format': format,
                                   'include_meanings': False}).encode()
                with urlopen(Request(self.base + '/learning/export', data,
                    {'X-UI-Token': 'test-token', 'Content-Type': 'application/json'}), timeout=5) as response:
                    body = response.read()
                    self.assertEqual(response.headers['Content-Type'], content_type)
                    self.assertEqual(int(response.headers['Content-Length']), len(body))
                    self.assertIn('attachment;', response.headers['Content-Disposition'])
                    self.assertIn('.fr.' + format, response.headers['Content-Disposition'])
                    self.assertEqual(response.headers['X-Learning-Export-Warnings'], 'reflowed_text')
                    self.assertTrue(body.startswith(b'PK') if format == 'epub' else b'<html' in body)
        self.assertIsNone(self.service.store.get_session(ready['session_id'])['read_cursor'])
        self.assertEqual(adapter.calls, 1)
        status, error = self.post('/learning/export', {'session_id': ready['session_id'], 'format': 'pdf'})
        self.assertEqual((status, error['code']), (400, 'invalid_export_format'))
