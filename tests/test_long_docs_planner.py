"""LONG-DOCS layers 3, 4 and 6: planner speed/equivalence, chapter size safety, unit policy.

No provider or network calls: every function under test is a pure planner.
"""
import copy
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _chapter_pipeline_reference as reference
from _long_docs_synth import configuration, synthetic_structure

from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.chapter_pipeline import (
    ChapterPipelineError, MAX_CHAPTER_SOURCE_CHARS, fit_chapter_groups, plan_chapter, unit_policy_for,
)
from scholarly_translation.glossary import new_store, propose_rule, resolve_applicable, review_rule
from scholarly_translation.source_reading import fingerprint
from scholarly_translation.token_counting import count_tokens

QUALITIES = ('fast', 'checked', 'thorough')


def page_groups(structure):
    groups, order = {}, []
    for unit in structure['units']:
        if unit['page_id'] not in groups:
            groups[unit['page_id']] = []
            order.append(unit['page_id'])
        groups[unit['page_id']].append(unit['unit_id'])
    return [groups[page] for page in order]


def assert_plans_close(case, old, new, tolerance):
    """Plans must have identical shape; numeric bounds may only differ by the
    explicit additive-count slack and the new bound is never lower."""
    if isinstance(old, dict):
        case.assertEqual(set(old), set(new))
        for key in old:
            assert_plans_close(case, old[key], new[key], tolerance)
    elif isinstance(old, list):
        case.assertEqual(len(old), len(new))
        for a, b in zip(old, new):
            assert_plans_close(case, a, b, tolerance)
    elif isinstance(old, float):
        case.assertAlmostEqual(old, new, delta=max(abs(old) * tolerance, 1e-9))
    elif isinstance(old, int) and not isinstance(old, bool):
        case.assertGreaterEqual(new, old)
        case.assertLessEqual(new, old + abs(old) * tolerance)
    else:
        case.assertEqual(old, new)


class PlannerEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The frozen reference re-validates the whole structure for every unit;
        # memoise that (pure) call so the oracle's *planning* algorithm is what runs.
        real, memo = reference.resolve_applicable, {}
        def memoised(store, structure, unit_id):
            key = (id(store), id(structure), unit_id)
            if key not in memo:
                memo[key] = real(store, structure, unit_id)
            return copy.deepcopy(memo[key])
        reference.resolve_applicable = memoised
        cls.addClassCleanup(setattr, reference, 'resolve_applicable', real)
        cls.small = synthetic_structure(chapters=4, chars_per_chapter=1800, unit_policy={'max_unit_words': 70})
        cls.large = synthetic_structure(chapters=1, chars_per_chapter=60000, unit_policy={'max_unit_words': 250})
        cls.small_ids = [u['unit_id'] for u in cls.small['units']]
        cls.large_ids = [u['unit_id'] for u in cls.large['units']]

    def configs(self):
        return [
            ('roomy', configuration()),
            ('many-batches', configuration(translator_output=2200, context=9000, qa_context=12000, qa_output=2048)),
            ('bounded-reading', configuration(translator_output=4096, context=6000, qa_context=16000, qa_output=2048)),
            ('qa-groups', configuration(translator_output=8192, context=60000, qa_context=12000, qa_output=2048)),
        ]

    def test_small_fixtures_produce_identical_plans(self):
        self.assertGreater(len(self.small_ids), 12)
        glossary = new_store()
        for name, config in self.configs():
            for quality in QUALITIES:
                for ids in (self.small_ids, self.small_ids[:5], self.small_ids[7:9]):
                    try:
                        expected = reference.plan_chapter(self.small, glossary, ids, config, quality, 'scholarly')
                    except reference.ChapterPipelineError as exc:
                        with self.assertRaises(ChapterPipelineError) as raised:
                            plan_chapter(self.small, glossary, ids, config, quality, 'scholarly')
                        self.assertEqual(str(raised.exception), str(exc))
                        continue
                    actual = plan_chapter(self.small, glossary, ids, config, quality, 'scholarly')
                    self.assertEqual(expected, actual, '%s/%s/%d' % (name, quality, len(ids)))

    def test_plans_exercise_batches_groups_and_both_context_modes(self):
        glossary = new_store()
        modes, batches, groups = set(), set(), set()
        for _, config in self.configs():
            for quality in ('fast', 'checked'):
                try:
                    plan = plan_chapter(self.small, glossary, self.small_ids, config, quality, 'scholarly')
                except ChapterPipelineError:
                    continue
                modes.add(plan['context_mode'])
                batches.add(len(plan['batches']) > 1)
                groups.add(len(plan['qa_groups']) > 1)
        self.assertEqual(modes, {'whole_chapter', 'bounded_reading_partition'})
        self.assertEqual(batches, {True, False})
        self.assertIn(True, groups)

    def test_large_prompts_keep_shape_and_never_lower_bounds(self):
        glossary = new_store()
        config = configuration(translator_output=8192, context=30000, qa_context=30000, qa_output=2048)
        for quality in QUALITIES:
            old = reference.plan_chapter(self.large, glossary, self.large_ids, config, quality, 'scholarly')
            new = plan_chapter(self.large, glossary, self.large_ids, config, quality, 'scholarly')
            self.assertEqual([b['unit_ids'] for b in old['batches']], [b['unit_ids'] for b in new['batches']])
            self.assertEqual([g['unit_ids'] for g in old['qa_groups']], [g['unit_ids'] for g in new['qa_groups']])
            self.assertEqual(old['context_mode'], new['context_mode'])
            assert_plans_close(self, old, new, 1e-3)
            for role, row in old['role_usage'].items():
                self.assertGreaterEqual(new['role_usage'][role]['input_tokens_upper_bound'], row['input_tokens_upper_bound'])
                self.assertLessEqual(new['role_usage'][role]['input_tokens_upper_bound'],
                                     row['input_tokens_upper_bound'] + 16 * row['calls'])

    def test_reported_input_bound_covers_exact_count_of_sent_prompt(self):
        glossary = new_store()
        config = configuration(translator_output=8192, context=30000, qa_context=30000, qa_output=2048)
        plan = plan_chapter(self.large, glossary, self.large_ids, config, 'fast', 'scholarly')
        selection, _ = config.resolve('translator')
        for batch in plan['batches']:
            prompt = pipeline.build_batch_translation_prompt(
                self.large, glossary, batch['unit_ids'], 'scholarly', None, batch['source_unit_ids'])
            exact = count_tokens(prompt, selection.model)['upper_bound']
            self.assertGreaterEqual(batch['input_tokens_upper_bound'], exact + pipeline.ENVELOPE_TOKENS)
            self.assertLessEqual(exact + batch['call_output_cap'] + pipeline.ENVELOPE_TOKENS,
                                 selection.capabilities.usable_context_tokens)

    def test_repartition_qa_groups_matches_reference(self):
        records = [{'unit_id': 'u%d' % i, 'source_text': ('word ' * (40 + 17 * i)).strip(),
                    'target_text': ('עברית ' * (60 + 11 * i)).strip()} for i in range(40)]
        for usable in (1500, 3000, 12000, 200000):
            capabilities = configuration(qa_context=usable, qa_output=2048).models['chapter_qa'].capabilities
            try:
                expected = reference.repartition_qa_groups(records, capabilities)
            except reference.ChapterPipelineError:
                with self.assertRaises(ChapterPipelineError):
                    pipeline.repartition_qa_groups(records, capabilities)
                continue
            self.assertEqual(expected, pipeline.repartition_qa_groups(records, capabilities))

    def test_invalid_inputs_keep_their_errors(self):
        glossary = new_store()
        config = configuration()
        with self.assertRaises(ChapterPipelineError):
            plan_chapter(self.small, glossary, ['missing'], config, 'fast', 'scholarly')
        with self.assertRaises(ChapterPipelineError):
            plan_chapter(self.small, glossary, self.small_ids[:2] * 2, config, 'fast', 'scholarly')
        with self.assertRaises(ChapterPipelineError):
            plan_chapter(self.small, glossary, self.small_ids[:2], config, 'fast', 'nope')


class PackFastTests(unittest.TestCase):
    def test_wrong_optimistic_bound_is_shrunk_by_the_exact_check(self):
        items = list(range(23))
        calls = []
        def exact(group):
            calls.append(len(group))
            return len(group) <= 3
        groups = pipeline._pack_fast(items, [(1,)] * 23, lambda size, sums: 'yes', exact)
        self.assertEqual([x for g in groups for x in g], items)
        self.assertTrue(all(1 <= len(g) <= 3 for g in groups))

    def test_maybe_extensions_decide_exactly_like_greedy(self):
        items = list(range(17))
        exact = lambda group: sum(group) <= 20
        expected, current = [], []
        for item in items:
            if current and not exact(current + [item]):
                expected.append(current)
                current = []
            current.append(item)
        expected.append(current)
        self.assertEqual(pipeline._pack_fast(items, [(1,)] * 17, lambda size, sums: 'maybe', exact), expected)

    def test_single_unit_that_cannot_fit_raises(self):
        with self.assertRaisesRegex(ChapterPipelineError, 'cannot fit'):
            pipeline._pack_fast([1, 2], [(1,)] * 2, lambda size, sums: 'no', lambda group: False)
        with self.assertRaisesRegex(ChapterPipelineError, 'cannot fit'):
            pipeline._pack_fast([1, 2], [(1,)] * 2, lambda size, sums: 'yes', lambda group: False)


class TermResolverTests(unittest.TestCase):
    def test_resolver_matches_glossary_resolution_for_every_unit(self):
        structure = synthetic_structure(chapters=3, chars_per_chapter=1500, unit_policy={'max_unit_words': 70})
        unit = next(u for u in structure['units'] if all(w in u['text'] for w in ('lantern', 'river', 'silver')) and u['text'].count('market') >= 2)
        store = new_store()
        def add(store, term, target, scope=None, approve=True, occurrence=0):
            start = unit['source_char_start'] + [i for i in range(len(unit['text'])) if unit['text'].startswith(term, i)][occurrence]
            store = propose_rule(store, structure, unit['unit_id'], 'en', start, start + len(term), target, scope=scope)
            rule = store['rules'][-1]
            if approve:
                store = review_rule(store, rule['rule_id'], rule['version'], fingerprint(rule),
                                    'editor@example.org', 'human', 'check', 'approved')
            return store
        store = add(store, 'lantern', 'פנס')
        store = add(store, 'river', 'נהר', scope={'document_ids': [], 'unit_ids': [unit['unit_id']]})
        store = add(store, 'silver', 'כסף', approve=False)
        resolver = pipeline._TermResolver(structure, store)
        approved_units = 0
        for u in structure['units']:
            expected = resolve_applicable(store, structure, u['unit_id'])
            self.assertEqual([row['rule_id'] for row in expected['approved_rules']], [r for r, _ in resolver.terms(u['unit_id'])])
            self.assertEqual([{'source_term': r['source_term'], 'target_term': r['target_term']}
                              for r in expected['approved_rules']], [t for _, t in resolver.terms(u['unit_id'])])
            approved_units += bool(expected['approved_rules'])
        self.assertGreater(approved_units, 1)
        # Conflicting approved targets for one term need a human, as in the glossary.
        conflicted = add(store, 'market', 'שוק')
        conflicted = add(conflicted, 'market', 'מרקט', occurrence=1)
        self.assertEqual(resolve_applicable(conflicted, structure, unit['unit_id'])['status'], 'needs_human')
        with self.assertRaisesRegex(ChapterPipelineError, 'human'):
            pipeline._TermResolver(structure, conflicted).terms(unit['unit_id'])
        # Terminology flows into the prompt identically to the reference implementation.
        ids = [u['unit_id'] for u in structure['units']][:6]
        self.assertEqual(
            str(pipeline.build_batch_translation_prompt(structure, store, ids[:3], 'scholarly', None, ids)),
            str(reference.build_batch_translation_prompt(structure, store, ids[:3], 'scholarly', None, ids)))


class PlannerSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        started = time.time()
        cls.structure = synthetic_structure(chapters=50, chars_per_chapter=16000)
        cls.groups = page_groups(cls.structure)
        cls.build_seconds = time.time() - started

    def test_800k_char_50_chapter_preview_is_fast_in_every_quality(self):
        chars = sum(len(u['text']) for u in self.structure['units'])
        self.assertGreater(chars, 780_000)
        self.assertEqual(len(self.groups), 50)
        config = configuration(translator_output=128000, context=400000, qa_context=400000, qa_output=8192)
        glossary = new_store()
        for quality in QUALITIES:
            started = time.time()
            total = 0.0
            for ids in self.groups:
                plan = pipeline.estimate_preview(self.structure, glossary, ids, config, quality, 'scholarly')
                self.assertEqual(plan['unit_count'], len(ids))
                self.assertGreater(plan['conservative_total_ceiling_usd'], 0)
                total += plan['conservative_total_ceiling_usd']
            elapsed = time.time() - started
            print('LONG-DOCS preview 50 chapters %s: %.2fs (structure build %.1fs)' % (quality, elapsed, self.build_seconds))
            self.assertLess(elapsed, 60, quality)

    def test_whole_book_as_one_chapter_is_bounded_too(self):
        ids = [u['unit_id'] for u in self.structure['units']]
        config = configuration(translator_output=128000, context=400000, qa_context=400000, qa_output=8192)
        started = time.time()
        plan = pipeline.estimate_preview(self.structure, new_store(), ids, config, 'checked', 'scholarly')
        elapsed = time.time() - started
        print('LONG-DOCS whole-book single chapter checked: %.2fs' % elapsed)
        self.assertEqual(sum(len(b['unit_ids']) for b in plan['batches']), len(ids))
        self.assertLess(elapsed, 120)


class FitChapterGroupsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.structure = synthetic_structure(chapters=50, chars_per_chapter=16000)
        cls.ids = [u['unit_id'] for u in cls.structure['units']]
        cls.chars = {u['unit_id']: len(u['text']) for u in cls.structure['units']}
        cls.config = configuration()
        cls.heading_units = pipeline._heading_boundaries(cls.structure, cls.ids)

    def run_fit(self, groups, config=None, quality='fast', structure=None):
        return fit_chapter_groups(structure or self.structure, new_store(), groups, config or self.config, quality, 'scholarly')

    def test_small_groups_are_returned_unchanged(self):
        groups = page_groups(self.structure)
        self.assertEqual(self.run_fit(groups), groups)
        self.assertEqual(self.run_fit(groups, quality='thorough'), groups)

    def test_oversized_group_is_split_balanced_contiguous_at_headings(self):
        result = self.run_fit([self.ids])
        self.assertGreater(len(result), 1)
        self.assertEqual([uid for part in result for uid in part], self.ids)
        sizes = [sum(self.chars[uid] for uid in part) for part in result]
        self.assertTrue(all(0 < size <= MAX_CHAPTER_SOURCE_CHARS for size in sizes), sizes)
        self.assertGreaterEqual(len(result), -(-sum(sizes) // MAX_CHAPTER_SOURCE_CHARS))
        self.assertLessEqual(max(sizes) - min(sizes), 0.6 * MAX_CHAPTER_SOURCE_CHARS)
        position = {uid: i for i, uid in enumerate(self.ids)}
        for part in result[1:]:
            self.assertIn(position[part[0]], self.heading_units)
        self.assertEqual(result, self.run_fit([self.ids]))

    def test_groups_are_never_merged_or_reordered_and_each_unit_appears_once(self):
        mixed = [self.ids[:3], self.ids[3:], ]
        result = self.run_fit(mixed)
        self.assertEqual(result[0], mixed[0])
        self.assertEqual([uid for part in result for uid in part], self.ids)
        self.assertEqual(len({uid for part in result for uid in part}), len(self.ids))
        with self.assertRaises(ChapterPipelineError):
            self.run_fit([self.ids[:3], self.ids[2:5]])
        with self.assertRaises(ChapterPipelineError):
            self.run_fit([[]])

    def test_unit_dicts_are_split_as_dicts(self):
        units = [dict(u) for u in self.structure['units']]
        result = self.run_fit([units])
        self.assertTrue(all(isinstance(item, dict) for part in result for item in part))
        self.assertEqual([item['unit_id'] for part in result for item in part], self.ids)

    def test_group_whose_full_source_exceeds_model_context_is_split_until_it_fits(self):
        structure = synthetic_structure(chapters=1, chars_per_chapter=24000, unit_policy={'max_unit_words': 90})
        ids = [u['unit_id'] for u in structure['units']]
        config = configuration(translator_output=8192, context=12000, qa_context=400000, qa_output=8192)
        whole = plan_chapter(structure, new_store(), ids, config, 'fast', 'scholarly')
        self.assertEqual(whole['context_mode'], 'bounded_reading_partition')
        parts = fit_chapter_groups(structure, new_store(), [ids], config, 'fast', 'scholarly')
        self.assertGreater(len(parts), 1)
        self.assertEqual([uid for part in parts for uid in part], ids)
        for part in parts:
            plan = plan_chapter(structure, new_store(), part, config, 'fast', 'scholarly')
            self.assertEqual(plan['context_mode'], 'whole_chapter')

    def test_qa_context_also_bounds_the_chapter(self):
        structure = synthetic_structure(chapters=1, chars_per_chapter=24000, unit_policy={'max_unit_words': 90})
        ids = [u['unit_id'] for u in structure['units']]
        config = configuration(translator_output=8192, context=400000, qa_context=12000, qa_output=2048)
        fast = fit_chapter_groups(structure, new_store(), [ids], config, 'fast', 'scholarly')
        checked = fit_chapter_groups(structure, new_store(), [ids], config, 'checked', 'scholarly')
        self.assertEqual(fast, [ids])
        self.assertGreater(len(checked), 1)
        self.assertEqual([uid for part in checked for uid in part], ids)

    def test_cjk_style_many_small_units_still_split_by_size(self):
        structure = synthetic_structure(chapters=1, chars_per_chapter=130000, unit_policy={'max_unit_words': 60})
        ids = [u['unit_id'] for u in structure['units']]
        parts = fit_chapter_groups(structure, new_store(), [ids], self.config, 'fast', 'scholarly')
        self.assertEqual([uid for part in parts for uid in part], ids)
        by_id = {u['unit_id']: len(u['text']) for u in structure['units']}
        self.assertTrue(all(sum(by_id[uid] for uid in part) <= MAX_CHAPTER_SOURCE_CHARS for part in parts))
        self.assertEqual(len(parts), 3)


class UnitPolicyTests(unittest.TestCase):
    def test_default_and_large_output_models_keep_default_units(self):
        self.assertIsNone(unit_policy_for(configuration(translator_output=128000)))
        self.assertIsNone(unit_policy_for(configuration(translator_output=100000)))

    def test_small_output_model_gets_a_smaller_unit_policy(self):
        policy = unit_policy_for(configuration(translator_output=8192))
        self.assertEqual(set(policy), {'max_unit_words'})
        self.assertGreaterEqual(policy['max_unit_words'], pipeline.MIN_UNIT_POLICY_WORDS)
        self.assertLess(policy['max_unit_words'], 2000)
        bigger = unit_policy_for(configuration(translator_output=16000))
        self.assertGreater(bigger['max_unit_words'], policy['max_unit_words'])
        worst = pipeline.estimate_output_token_cap(policy['max_unit_words'] * pipeline.UNIT_POLICY_CHARS_PER_WORD)
        self.assertLessEqual(worst, 8192 // 2)

    def test_policy_makes_units_plannable_where_default_units_cannot_fit(self):
        config = configuration(translator_output=8192, context=400000, qa_context=400000, qa_output=8192)
        default = synthetic_structure(chapters=2, chars_per_chapter=16000)
        ids = [u['unit_id'] for u in default['units']]
        with self.assertRaisesRegex(ChapterPipelineError, 'cannot fit'):
            plan_chapter(default, new_store(), ids, config, 'fast', 'scholarly')
        policy = unit_policy_for(config)
        shaped = synthetic_structure(chapters=2, chars_per_chapter=16000, unit_policy=policy)
        self.assertGreater(len(shaped['units']), len(default['units']))
        shaped_ids = [u['unit_id'] for u in shaped['units']]
        for quality in QUALITIES:
            plan = plan_chapter(shaped, new_store(), shaped_ids, config, quality, 'scholarly')
            self.assertEqual(sum(len(b['unit_ids']) for b in plan['batches']), len(shaped_ids))
            self.assertTrue(all(b['call_output_cap'] <= 8192 for b in plan['batches']))

    def test_default_policy_leaves_structure_untouched(self):
        a = synthetic_structure(chapters=2, chars_per_chapter=3000)
        b = synthetic_structure(chapters=2, chars_per_chapter=3000, unit_policy=unit_policy_for(configuration()))
        self.assertEqual(a, b)

    def test_output_limit_too_small_for_any_sane_unit_is_a_clear_error(self):
        with self.assertRaisesRegex(ChapterPipelineError, 'output limit'):
            unit_policy_for(configuration(translator_output=2048))


if __name__ == '__main__':
    unittest.main()
