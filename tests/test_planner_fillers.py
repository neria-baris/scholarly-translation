import re
import unittest

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.token_counting import count_tokens, upper_bound_tokens


LONG_RUN = re.compile(r'\S{65,}')


class PlannerFillerTests(unittest.TestCase):
    """Planning placeholders keep the old byte size (so every byte bound and plan is
    unchanged) without one long unbroken run, which tiktoken's BPE counts in quadratic time."""

    def test_filler_keeps_bytes_and_breaks_runs(self):
        for char in ('x', 'א', '—', '𐀀'):
            for length in (0, 1, 63, 64, 65, 1000, 66001):
                filler = pipeline._filler(char, length)
                self.assertEqual(len(filler.encode('utf-8')), len((char * length).encode('utf-8')))
                self.assertIsNone(LONG_RUN.search(filler))

    def test_synthetic_planning_text_has_no_long_runs(self):
        texts = [pipeline._synthetic_book_context(), pipeline._synthetic_notebook_excerpt(),
                 pipeline._synthetic_target('word ' * 20000)]
        for text in texts:
            self.assertIsNone(LONG_RUN.search(text))

    def test_upper_bound_matches_count_tokens(self):
        for model in (None, 'gpt-6-luna', 'gpt-4o', 'claude-sonnet-5-5'):
            for text in ('', 'Hello, world.', 'שלום עולם ' * 50, pipeline._filler('א', 5000)):
                self.assertEqual(upper_bound_tokens(text, model), count_tokens(text, model)['upper_bound'])
                self.assertEqual(pipeline._ub(text, model), count_tokens(text, model)['upper_bound'])


if __name__ == '__main__':
    unittest.main()
