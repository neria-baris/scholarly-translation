import tempfile
import textwrap
import unittest
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas
from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.document_draft import DocumentJobs, extract_structure
from scholarly_translation.glossary import new_store
from scholarly_translation.model_config import ModelConfiguration


def configuration(output=2048, qa_context=30000):
    providers = {'writer': {'type': 'openai', 'credential_env': 'WRITER_API_KEY'},
                 'critic': {'type': 'anthropic', 'credential_env': 'CRITIC_API_KEY'}}
    def role(provider, model, context, cap):
        return {'provider': provider, 'model': model, 'capabilities': {
            'context_window': context, 'usable_context_tokens': context,
            'max_output_tokens': cap}}
    return ModelConfiguration.from_dict({'schema_version': 1, 'providers': providers, 'models': {
        'translator': role('writer', 'gpt-6-luna', 100000, output),
        'semantic_reviewer': role('critic', 'claude-sonnet-5-5', 30000, 2048),
        'chapter_qa': role('critic', 'claude-sonnet-5-5', qa_context, 2048)}})


class ChapterAutomationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'source.pdf'
        pdf = Canvas(str(path))
        for page in range(4):
            pdf.setFont('Helvetica', 9)
            for index, line in enumerate(textwrap.wrap('Some scholars do not accept all claims. ' * 8, width=85)):
                pdf.drawString(72, 700-index*12, line)
            pdf.showPage()
        pdf.save()
        self.structure = extract_structure(path, 'en')
        self.ids = [unit['unit_id'] for unit in self.structure['units']]

    def test_output_capacity_splits_instead_of_clamping_oversized_output(self):
        config = configuration(output=1200)
        manifest = pipeline.plan_chapter(self.structure, new_store(), self.ids, config, 'fast', 'scholarly')
        self.assertGreater(len(manifest['batches']), 1)
        by_id = {unit['unit_id']: unit for unit in self.structure['units']}
        for batch in manifest['batches']:
            estimate = pipeline.estimate_output_token_cap(sum(len(by_id[uid]['text']) for uid in batch['unit_ids']))
            self.assertLessEqual(estimate, 1200)

    def test_risk_based_review_routes_negation_and_quantifier_without_note(self):
        record = {'source_text': 'Some scholars do not accept all claims.', 'source_language': 'en',
                  'target_text': 'חלק מהחוקרים אינם מקבלים את כל הטענות.',
                  'translation_note': None, 'findings': []}
        risk = pipeline.detect_risk_triggers(record)
        self.assertTrue(risk['configured_risk_flags'])

    def test_actual_hebrew_qa_group_that_cannot_fit_fails_before_dispatch(self):
        records = [{'unit_id': 'one', 'source_text': 'source ' * 150,
                    'target_text': 'עברית ' * 2000}]
        caps = configuration(qa_context=5000).models['chapter_qa'].capabilities
        with self.assertRaises(pipeline.ChapterPipelineError):
            pipeline.repartition_qa_groups(records, caps)

    def test_pause_resume_are_job_operations_not_only_unused_journal_flags(self):
        self.assertTrue(callable(getattr(DocumentJobs, 'pause', None)))
        self.assertTrue(callable(getattr(DocumentJobs, 'resume', None)))

    def test_heavier_qa_model_has_preflight_groups_and_role_token_counts(self):
        manifest = pipeline.plan_chapter(self.structure, new_store(), self.ids,
                                        configuration(qa_context=13500), 'thorough', 'scholarly')  # PROMPT-FIXES: longer QA contract
        self.assertIn('qa_groups', manifest)
        self.assertIn('role_usage', manifest)
        self.assertGreater(len(manifest['qa_groups']), 1)
