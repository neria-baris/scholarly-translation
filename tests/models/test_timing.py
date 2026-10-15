"""Time estimate beside the cost estimate: pure planning, no provider calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _long_docs_synth import configuration, synthetic_structure

from scholarly_translation.models.timing import DEFAULT_PROFILE, OUTPUT_SHARE, PROFILES, call_seconds, planned_seconds
from scholarly_translation.translate import chapter_pipeline as pipeline
from scholarly_translation.translate.glossary import new_store


class CallSecondsTests(unittest.TestCase):
    def test_measured_profile_grows_with_tokens(self):
        self.assertAlmostEqual(call_seconds('openai', 'gpt-6-luna', 10000, 6000), 0.3 + 51.0)
        self.assertGreater(call_seconds('openai', 'gpt-6-luna', 10000, 6001),
                           call_seconds('openai', 'gpt-6-luna', 10000, 6000))

    def test_unmeasured_model_uses_the_slowest_measured_profile(self):
        slowest = max(PROFILES.values(), key=lambda p: p[2])
        self.assertEqual(DEFAULT_PROFILE, slowest)
        self.assertEqual(call_seconds('anthropic', 'unknown-model', 1000, 1000),
                         call_seconds('openai', 'gpt-6.1-sol', 1000, 1000))

    def test_mock_takes_no_time(self):
        self.assertEqual(call_seconds('mock', 'gpt-6-luna', 10000, 6000), 0.0)
        self.assertEqual(set(planned_seconds('mock', 'gpt-6-luna', 10000, 6000).values()), {0.0})

    def test_planned_range_is_ordered(self):
        seconds = planned_seconds('openai', 'gpt-6-luna', 10000, 6000)
        self.assertLess(seconds['low'], seconds['expected'])
        self.assertLess(seconds['expected'], seconds['high'])
        self.assertAlmostEqual(seconds['expected'], call_seconds('openai', 'gpt-6-luna', 10000, 6000 * OUTPUT_SHARE['expected']))


class PlanTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.structure = synthetic_structure(chapters=1, chars_per_chapter=6000)
        cls.ids = [u['unit_id'] for u in cls.structure['units']]
        cls.config = configuration()

    def plan(self, quality):
        return pipeline.estimate_preview(self.structure, new_store(), self.ids, self.config, quality, 'scholarly')

    def test_totals_sum_the_roles_and_the_range_is_ordered(self):
        for quality in ('fast', 'checked', 'thorough'):
            plan = self.plan(quality)
            rows = plan['role_usage'].values()
            for name in ('low', 'expected', 'high'):
                self.assertAlmostEqual(plan[f'{name}_total_seconds'], sum(r[f'{name}_seconds'] for r in rows))
            self.assertGreater(plan['low_total_seconds'], 0)
            self.assertLess(plan['low_total_seconds'], plan['expected_total_seconds'])
            self.assertLess(plan['expected_total_seconds'], plan['high_total_seconds'])

    def test_expected_translation_time_follows_the_first_pass_batches(self):
        plan = self.plan('fast')
        batches = sum(planned_seconds('openai', 'gpt-6-luna', b['input_tokens_upper_bound'],
                                      b['call_output_cap'])['expected'] for b in plan['batches'])
        self.assertAlmostEqual(plan['role_usage']['translator']['expected_seconds'], batches)

    def test_review_adds_time(self):
        self.assertGreater(self.plan('checked')['expected_total_seconds'], self.plan('fast')['expected_total_seconds'])


if __name__ == '__main__':
    unittest.main()
