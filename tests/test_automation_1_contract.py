import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation import token_counting
from scholarly_translation.model_adapter import _anthropic_usage, OpenAITextGenerationAdapter
from scholarly_translation.model_config import ModelCapabilities
from scholarly_translation.runtime_controls import ControlStore, PersistentBudget, RuntimeCache
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.translation import build_translation_request, _check_prompt_fits
from scholarly_translation.glossary import new_store
from scholarly_translation.review_qa import (build_chapter_qa_request, run_chapter_qa,
                                             ReviewQARequestError)
from scholarly_translation.document_draft import extract_structure
from reportlab.pdfgen.canvas import Canvas
import textwrap


class AutomationFoundationContractTests(unittest.TestCase):
    def test_default_sol_effort_is_supported_and_other_model_omits_effort(self):
        calls = []
        response = SimpleNamespace(status='completed', output_text='שלום', model='gpt-6.1-sol',
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=20))
        def create(**kwargs):
            calls.append(kwargs)
            return response
        adapter = OpenAITextGenerationAdapter(client=SimpleNamespace(responses=SimpleNamespace(create=create)))
        adapter.generate('prompt', 'gpt-6.1-sol')
        adapter.generate('prompt', 'user-custom-model')
        self.assertEqual(calls[0]['reasoning']['effort'], 'low')
        self.assertNotIn('reasoning', calls[1])

    def test_empty_encoding_cache_never_opens_network(self):
        prior = dict(token_counting._ENCODING_CACHE)
        token_counting._ENCODING_CACHE.clear()
        try:
            with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
                counted = token_counting.count_tokens('שלום こんにちは', 'gpt-4o')
            self.assertEqual(counted['method'], 'byte_upper_bound_estimate')
            self.assertFalse(counted['exact'])
        finally:
            token_counting._ENCODING_CACHE.clear()
            token_counting._ENCODING_CACHE.update(prior)

    def test_configured_long_unit_and_prompt_fit_without_legacy_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'long.pdf'
            canvas = Canvas(str(pdf))
            canvas.setFont('Helvetica', 8)
            for index, line in enumerate(textwrap.wrap('alpha ' * 800, width=90)):
                canvas.drawString(72, 750-index*10, line)
            canvas.save()
            structure = extract_structure(pdf, 'en')
            unit = max(structure['units'], key=lambda u: len(u['text']))
            self.assertGreater(len(unit['text']), 2000)
            caps = ModelCapabilities(100000, 100000, 10000)
            request = build_translation_request(structure, new_store(), unit['unit_id'],
                                                'scholarly', 'openai', 'gpt-6-luna', capabilities=caps)
            self.assertIn(unit['text'], request.prompt_text)
            _check_prompt_fits('x' * 15000, 'gpt-6-luna', caps)

    def test_qa_that_does_not_fit_calls_no_provider(self):
        calls = []
        request = build_chapter_qa_request('source ' * 200, 'שלום ' * 200, policy='on',
                                          capabilities=ModelCapabilities(10000, 1500, 100))
        with self.assertRaises(ReviewQARequestError):
            run_chapter_qa(request, generate=lambda *args: calls.append(args))
        self.assertEqual(calls, [])

    def test_128k_task_ceiling_with_distinct_role_caps_and_alias_price(self):
        with tempfile.TemporaryDirectory() as folder, ControlStore(Path(folder) / 'controls.sqlite3') as store:
            first = PersistentBudget(store, 'task', max_calls=10, hard_list_usd=10,
                                     stage='translate', provider='primary', model='gpt-6-luna',
                                     pricing_provider='openai', output_cap=128000, call_output_cap=1000)
            qa = PersistentBudget(store, 'task', max_calls=10, hard_list_usd=10,
                                  stage='chapter-qa', provider='critic', model='claude-sonnet-5-5',
                                  pricing_provider='anthropic', output_cap=128000, call_output_cap=500)
            self.assertLess(first.amount('hello'), qa.amount('hello'))
            cache = RuntimeCache(store, stage='translate', provider='primary', model='gpt-6-luna')
            result, hit, _ = cache.execute('request', 'hello', 'gpt-6-luna',
                lambda *_: TextGenerationResult('completed', 'שלום', {'input': 1000, 'output': 1000}, 'gpt-6-luna', 0),
                stage='translate', metadata={'document_id': 'doc', 'unit_id': 'unit', 'provider_type': 'openai'},
                budget=first)
            self.assertFalse(hit)
            self.assertAlmostEqual(store.status('task')['list_estimated_spent_usd'], .0006)

    def test_malformed_anthropic_cache_usage_retains_unknown(self):
        response = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=20,
                                   cache_read_input_tokens=-3, cache_creation_input_tokens=0))
        self.assertEqual(_anthropic_usage(response), 'not_metered')

    def test_incomplete_openai_preserves_raw_but_is_not_a_draft(self):
        response = SimpleNamespace(status='incomplete', output_text='partial', model='gpt-6.1-sol',
                                   incomplete_details=SimpleNamespace(reason='max_output_tokens'),
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=20))
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: response))
        result = OpenAITextGenerationAdapter(client=client).generate('prompt', 'gpt-6.1-sol')
        self.assertEqual(result.status, 'failed_truncated')
        self.assertEqual(result.text, 'partial')
