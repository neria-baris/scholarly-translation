"""Real HTTP-to-worker acceptance with injected providers; no external calls."""
import json
import io
import re
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import web_ui
from scholarly_translation.model_adapter import TextGenerationResult
from test_export_epub import make_epub


class UIAutomationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.calls = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.block_translation = False
        self.writer_key, self.qa_key = 'sk-test-writer-snapshot', 'sk-test-qa-snapshot'
        self.output_patch = patch.object(web_ui, 'OUTPUT_ROOT', self.folder)
        self.adapter_patch = patch('scholarly_translation.model_adapter.build_translation_adapter', self.adapter)
        self.output_patch.start()
        self._cross_review_stub = patch("scholarly_translation.chapter_pipeline.cross_review_available", create=True, return_value=False)
        self._cross_review_stub.start()
        self.addCleanup(self._cross_review_stub.stop)
        self.adapter_patch.start()
        self.addCleanup(self.output_patch.stop)
        self.addCleanup(self.adapter_patch.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web_ui.make_handler('contract-token'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.stop)
        self.settings = {'model': 'configured', 'automation': True, 'quality': 'checked',
            'profile': 'scholarly', 'language': 'en', 'budget_usd': 4,   # sonnet QA/keeper; larger notebook and NAMES reserves (NAMES-CROSSQA)
            'font_id': 'david-libre', 'role_selections': {
            'translator': {'source': 'catalog', 'provider': 'openai', 'model': 'gpt-6-luna'},
            'semantic_reviewer': {'source': 'catalog', 'provider': 'anthropic', 'model': 'claude-sonnet-5-5'},
            'chapter_qa': {'source': 'catalog', 'provider': 'anthropic', 'model': 'claude-sonnet-5-5'}}}

    def stop(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def post(self, route, data, binary=False):
        req = Request(self.url+route, json.dumps(data).encode(),
            {'Content-Type': 'application/json', 'X-UI-Token': 'contract-token', 'Origin': self.url})
        with urlopen(req, timeout=10) as response:
            return response.read() if binary else json.load(response)

    def adapter(self, provider, model, **kwargs):
        def generate(prompt, requested):
            self.calls.append({'provider': provider, 'model': model, 'name_table': 'NAME TABLE of a book' in str(prompt), **kwargs})
            if model == 'gpt-6-luna':
                self.entered.set()
                if self.block_translation:
                    if not self.release.wait(timeout=8):
                        raise RuntimeError('test did not release in-flight call')
                ids = json.loads(re.search(r'TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])', prompt).group(1))
                text = json.dumps([{'unit_id': uid, 'translation': 'חלק מהחוקרים אינם מקבלים את הטענה. במסמך 3 טענות.',
                                   'translation_note': None} for uid in ids], ensure_ascii=False)
            elif 'CHAPTER_LEVEL_NOTES' in prompt:
                text = 'VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none'
            else:
                text = 'VERDICT: PASS\nISSUES: none'
            return TextGenerationResult('completed', text, {'input': 100, 'output': 20}, requested, 0)
        return SimpleNamespace(generate=generate)

    def keys(self, writer=None, qa=None):
        return self.post('/model-keys', {'keys': {'openai': self.writer_key if writer is None else writer,
                                               'anthropic': self.qa_key if qa is None else qa}})

    def wait_job(self, job_id, states=('completed', 'failed', 'paused')):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            job = self.post('/document-job', {'job_id': job_id})
            if job['status'] in states:
                return job
            time.sleep(.02)
        self.fail('worker did not reach expected state')

    def start(self):
        sample = self.post('/document-sample', {})
        return self.post('/document-translate', {'path': sample['path'], 'settings': self.settings, 'paid_confirm': True})['job_id']

    def test_memory_keys_resolved_caps_accounting_and_font_download_zero_calls(self):
        self.keys()
        job_id = self.start()
        job = self.wait_job(job_id)
        self.assertEqual(job['status'], 'completed', job.get('error'))
        self.assertEqual({call['model'] for call in self.calls}, {'gpt-6-luna', 'claude-sonnet-5-5'})
        for call in self.calls:
            self.assertEqual(call['api_key'], self.writer_key if call['provider'] == 'openai' else self.qa_key)
            self.assertGreater(call['max_output_tokens'], 0)
            self.assertLess(call['max_output_tokens'], 128000)
        before = len(self.calls)
        first = self.post('/document-download', {'job_id': job_id, 'font_id': 'david-libre'}, binary=True)
        second = self.post('/document-download', {'job_id': job_id, 'font_id': 'noto-serif-hebrew'}, binary=True)
        self.assertTrue(first.startswith(b'%PDF'))
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.calls), before)
        self.assertEqual(job['budget_status']['settled_calls'], before)
        self.assertFalse(job['approved'])
        for file in self.folder.rglob('*'):
            if file.is_file():
                data = file.read_bytes()
                self.assertNotIn(self.writer_key.encode(), data)
                self.assertNotIn(self.qa_key.encode(), data)

    def test_pause_after_inflight_response_then_resume_with_new_qa_key_no_translation_resend(self):
        self.keys()
        self.block_translation = True
        job_id = self.start()
        self.assertTrue(self.entered.wait(timeout=5))
        self.post('/document-pause', {'job_id': job_id})
        self.release.set()
        paused = self.wait_job(job_id)
        self.assertEqual(paused['status'], 'paused', paused.get('error'))
        # The name-table pass over the original book (QA role, old key) runs before chapter 1.
        self.calls = [call for call in self.calls if not call['name_table']]
        self.assertEqual(len(self.calls), 1)
        self.keys(qa='sk-test-renewed-qa')
        self.post('/document-resume', {'job_id': job_id})
        job = self.wait_job(job_id)
        self.assertEqual(job['status'], 'completed', job.get('error'))
        self.assertEqual(sum(call['model'] == 'gpt-6-luna' for call in self.calls), 1)
        self.assertTrue(all(call['api_key'] == 'sk-test-renewed-qa' for call in self.calls[1:]))

    def test_completed_resume_does_not_need_renewed_keys_or_call_provider(self):
        self.keys()
        job_id = self.start()
        self.assertEqual(self.wait_job(job_id)['status'], 'completed')
        before = len(self.calls)
        self.post('/model-keys', {'keys': {'openai': '', 'anthropic': ''}})
        resumed = self.post('/document-resume', {'job_id': job_id})
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual(len(self.calls), before)

    def test_malformed_quality_fails_as_http_error_before_generation(self):
        self.keys()
        sample = self.post('/document-sample', {})
        bad = dict(self.settings, quality=['not-a-quality'])
        with self.assertRaises(HTTPError) as caught:
            self.post('/document-translate', {'path': sample['path'], 'settings': bad, 'paid_confirm': True})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.calls, [])

    def test_missing_quality_uses_validated_default_instead_of_crashing(self):
        self.keys()
        del self.settings['quality']
        job_id = self.start()
        job = self.wait_job(job_id)
        self.assertEqual(job['status'], 'completed', job.get('error'))
        self.assertEqual(job['settings']['quality'], 'checked')

    def test_wrong_origin_blocks_key_save(self):
        available_before = self.post('/model-keys', {})['available']
        req = Request(self.url+'/model-keys', b'{"keys":{"openai":"sk-test"}}',
            {'Content-Type': 'application/json', 'X-UI-Token': 'contract-token', 'Origin': 'https://unrelated.example'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.post('/model-keys', {})['available'], available_before)

    def test_credential_as_provider_id_is_refused_without_echo(self):
        secret_id = 'sk-test-not-a-provider-id'
        with self.assertRaises(HTTPError) as caught:
            self.post('/model-keys', {'keys': {secret_id: 'test-value'}})
        self.assertEqual(caught.exception.code, 400)
        self.assertNotIn(secret_id, caught.exception.read().decode())

    def test_help_prices_preserve_fractional_write_rate_and_html(self):
        with urlopen(self.url+'/help', timeout=10) as response:
            self.assertIn('text/html', response.headers['Content-Type'])
            body = response.read().decode()
        self.assertIn('0.125', body)
        self.assertNotIn('__PRICING_ROWS__', body)
        self.assertIn('272,000', body)

    def test_literary_epub_automated_qa_upload_export_and_completed_resume(self):
        self.keys()
        original = self.folder / 'original.epub'
        make_epub(original)
        req = Request(self.url+'/upload?name=original.epub', original.read_bytes(),
                      {'X-UI-Token': 'contract-token', 'Origin': self.url})
        with urlopen(req, timeout=10) as response:
            uploaded = json.load(response)
        settings = dict(self.settings, profile='literary', quality='thorough')
        job_id = self.post('/document-translate', {'path': uploaded['path'], 'settings': settings,
                                                 'paid_confirm': True})['job_id']
        job = self.wait_job(job_id)
        self.assertEqual(job['status'], 'completed', job.get('error'))
        self.assertEqual(job['source_kind'], 'epub')
        self.assertTrue(job['chapter_qa_results'])
        self.assertFalse(job['approved'])
        before = len(self.calls)
        body = self.post('/document-download', {'job_id': job_id, 'format': 'epub'}, binary=True)
        with zipfile.ZipFile(io.BytesIO(body)) as book:
            self.assertEqual(book.read('mimetype'), b'application/epub+zip')
            self.assertTrue(any('חלק מהחוקרים'.encode() in book.read(name)
                                for name in book.namelist() if name.endswith('.xhtml')))
        self.post('/document-resume', {'job_id': job_id})
        self.assertEqual(len(self.calls), before)
