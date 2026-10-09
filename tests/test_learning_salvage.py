"""LEARN-SALVAGE: miscounted spans, partial acceptance, the book notebook and
book-wide new-word budget, and quick resends of rejected answers. Offline fakes."""
import json
import unittest

from scholarly_translation.learning_contracts import LearningError
from scholarly_translation.learning_generation import (
    NOTEBOOK_PROMPT_VERSION, PACING_FLOOR_WORDS, book_notebook, build_request, new_foreign_words,
    parse_response,
)
from test_learning_generation import catalog, plan

TEXT = '״הוא לבד עכשיו.״ הוא הביט בבית, ואז הוא הלך הביתה.'


def plan3(text=TEXT, words_per_edit=1):
    result = plan()
    result.update({'policy_version': 'learning-policy@3', 'support_mode': 'context',
                   'selected_item_ids': ['fr-maison', 'fr-chat'], 'new_item_ids': ['fr-maison', 'fr-chat'],
                   'review_item_ids': [], 'review_targets': {}})
    result['units'][0]['text'] = text
    result['limits']['max_foreign_words_per_edit'] = words_per_edit
    return result


def edit(original, start, end, replacement='maison', item_ids=('fr-maison',), unit_id='unit-one'):
    return {'unit_id': unit_id, 'start': start, 'end': end, 'original': original, 'replacement': replacement,
            'item_ids': list(item_ids), 'grammar_ids': [], 'gloss_he': 'בית'}


def answer(p, edits, recap=None, **extra):
    return json.dumps({'response_version': 1, 'plan_id': p['plan_id'], 'edits': edits,
                       'recap': recap or {'vocabulary': [], 'grammar': []}, 'warnings': [], **extra},
                      ensure_ascii=False)


def word_catalog(*words):
    result = catalog()
    for lemma, sense in words:
        result['items'].append({'item_id': 'fr-' + lemma, 'kind': 'word', 'lemma': lemma, 'sense_he': sense,
                                'forms': [lemma], 'priority_tier': 1, 'prerequisite_ids': [],
                                'explanation_he': '', 'min_level': 1})
    return result


class SpanResolutionTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.catalog = plan3(), catalog()
        _, self.hash = build_request(self.plan, self.catalog)

    def parse(self, edits, **kwargs):
        return parse_response(answer(self.plan, edits), self.plan, self.catalog, self.hash, **kwargs)

    def test_miscounted_offsets_are_located_by_original_text(self):
        start = TEXT.index('בבית')
        for given in (start - 1, start + 1, start + 9, 0):
            with self.subTest(given=given):
                chunk, _ = self.parse([edit('בבית', given, given + 4)])
                found = chunk['edits'][0]
                self.assertEqual((found['start'], found['end']), (start, start + 4))
                self.assertEqual(TEXT[found['start']:found['end']], 'בבית')

    def test_off_by_one_after_hebrew_quote_mark(self):
        p, cat = plan3(), word_catalog(('seul', 'לבד'))
        p['selected_item_ids'].append('fr-seul')
        p['new_item_ids'].append('fr-seul')
        p['limits']['max_foreign_share'] = .5
        _, h = build_request(p, cat)
        chunk, _ = parse_response(answer(p, [edit('לבד', 4, 7, 'seul', ['fr-seul'])]), p, cat, h)
        self.assertEqual(chunk['edits'][0]['start'], TEXT.index('לבד'))

    def test_repeated_word_takes_the_nearest_free_occurrence(self):
        p, cat = plan3(), word_catalog(('il', 'הוא'))
        p['selected_item_ids'] = ['fr-il']
        p['new_item_ids'] = []
        p['review_item_ids'] = ['fr-il']
        p['review_targets'] = {'fr-il': {'seen_count': 2, 'target_share': .75}}
        _, h = build_request(p, cat)
        occurrences = [i for i in range(len(TEXT)) if TEXT.startswith('הוא', i) and not TEXT[i - 1].isalpha()]
        self.assertEqual(len(occurrences), 3)
        # Two edits both pointing near the middle one: each gets its own occurrence.
        edits = [edit('הוא', occurrences[1] + 2, occurrences[1] + 5, 'il', ['fr-il']),
                 edit('הוא', occurrences[1] + 3, occurrences[1] + 6, 'il', ['fr-il'])]
        chunk, _ = parse_response(answer(p, edits), p, cat, h)
        starts = sorted(e['start'] for e in chunk['edits'])
        self.assertEqual(len(starts), 2)
        self.assertIn(occurrences[1], starts)
        self.assertEqual(len(set(starts)), 2)

    def test_insertion_and_absent_text_are_dropped_and_alone_rejected(self):
        for bad in (edit('', 3, 3), edit('ארמון', 0, 5), edit('בית', 21, 24)):   # בית inside בבית: partial word
            with self.subTest(original=bad['original']):
                with self.assertRaises(LearningError) as raised:
                    self.parse([bad])
                self.assertEqual(str(raised.exception), 'no_valid_edit')

    def test_one_bad_edit_keeps_the_good_one_and_renumbers_recap(self):
        start = TEXT.index('בבית')
        edits = [edit('ארמון', 0, 5), edit('בבית', start, start + 4)]
        recap = {'vocabulary': [{'item_id': 'fr-maison', 'gloss_he': 'בית', 'edit_indexes': [0, 1]}], 'grammar': []}
        report = {}
        chunk, proposal = parse_response(answer(self.plan, edits, recap), self.plan, self.catalog, self.hash,
                                         report=report)
        self.assertEqual([e['original'] for e in chunk['edits']], ['בבית'])
        self.assertEqual(proposal['vocabulary'], [{'item_id': 'fr-maison', 'gloss_he': 'בית', 'edit_indexes': [0]}])
        self.assertEqual(report['dropped'], ['original_mismatch'])

    def test_repeated_hebrew_context_is_trimmed_to_the_replaced_word(self):
        p, cat = plan3(), word_catalog(('maintenant', 'עכשיו'))
        p['selected_item_ids'].append('fr-maintenant')
        p['new_item_ids'].append('fr-maintenant')
        p['limits']['max_foreign_share'] = .5
        _, h = build_request(p, cat)
        context = edit('״הוא לבד עכשיו.״', 0, 16, '״הוא לבד maintenant.״', ['fr-maintenant'])
        chunk, _ = parse_response(answer(p, [context]), p, cat, h)
        found = chunk['edits'][0]
        self.assertEqual((found['original'], found['replacement']), ('עכשיו', 'maintenant'))
        self.assertEqual(TEXT[found['start']:found['end']], 'עכשיו')
        # Context with nothing replaced is an insertion: still dropped.
        insertion = edit('הוא הביט', TEXT.index('הוא הביט'), TEXT.index('הוא הביט') + 8,
                         'הוא הביט maintenant', ['fr-maintenant'])
        with self.assertRaises(LearningError):
            parse_response(answer(p, [insertion]), p, cat, h)

    def test_trimming_never_cuts_inside_a_word(self):
        p, cat = plan3('אני הלכתי.'), word_catalog(('ikh', 'אני'))
        cat['items'][-1]['forms'] = ['איך']   # Same-script target (as in Yiddish).
        p['selected_item_ids'].append('fr-ikh')
        p['new_item_ids'].append('fr-ikh')
        p['limits']['max_foreign_share'] = .5
        _, h = build_request(p, cat)
        chunk, _ = parse_response(answer(p, [edit('אני', 0, 3, 'איך', ['fr-ikh'])]), p, cat, h)
        self.assertEqual((chunk['edits'][0]['original'], chunk['edits'][0]['replacement']), ('אני', 'איך'))

    def test_non_ascii_local_reference_is_remapped(self):
        start = TEXT.index('בבית')
        proposal = {'item_id': 'local-más', 'kind': 'word', 'lemma': 'maisonnette', 'sense_he': 'בית קטן',
                    'forms': ['maisonnette'], 'explanation_he': ''}
        raw = answer(self.plan, [edit('בבית', start, start + 4, 'maisonnette', ['local-más'])],
                     introduced_items=[proposal])
        chunk, _ = parse_response(raw, self.plan, self.catalog, self.hash)
        self.assertTrue(chunk['edits'][0]['item_ids'][0].startswith('fr-learn-'))

    def test_bad_warning_and_unknown_field_are_dropped(self):
        start = TEXT.index('בבית')
        raw = json.loads(answer(self.plan, [edit('בבית', start, start + 4)], progress=100))
        raw['warnings'] = [{'code': 'made_up', 'unit_id': None}]
        report = {}
        chunk, _ = parse_response(json.dumps(raw), self.plan, self.catalog, self.hash, report=report)
        self.assertEqual(len(chunk['edits']), 1)
        self.assertIn('field:progress', report['dropped'])

    def test_structural_problems_still_reject(self):
        start = TEXT.index('בבית')
        good = [edit('בבית', start, start + 4)]
        for raw in ('{not json', 'I cannot help.', answer(dict(self.plan, plan_id='plan-other'), good),
                    json.dumps({'response_version': 1, 'plan_id': self.plan['plan_id'], 'edits': {}})):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(LearningError):
                    parse_response(raw, self.plan, self.catalog, self.hash)

    def test_legacy_policies_stay_all_or_nothing(self):
        legacy = plan()
        legacy['units'][0]['text'] = TEXT
        _, h = build_request(legacy, catalog())
        start = TEXT.index('בבית')
        with self.assertRaises(LearningError):
            parse_response(answer(legacy, [edit('בבית', start + 1, start + 5)]), legacy, catalog(), h)


class BookNotebookTests(unittest.TestCase):
    def plans(self, texts):
        result = []
        for index, text in enumerate(texts):
            p = plan3(text)
            p.update({'plan_id': f'plan-{index}', 'chunk_id': f'chunk-{index}'})
            result.append(p)
        return result

    def learner(self, rows):
        return {'items': [{'item_id': item_id, 'introduced_count': count, 'last_completed_book_id': 'book-one'}
                          for item_id, count in rows]}

    def test_word_totals_pacing_and_ranked_learned_items(self):
        plans = self.plans(['תוכן העניינים', 'מילה ' * 400, 'מילה ' * 600])
        cat = catalog()
        learner = self.learner([('fr-chat', 1), ('fr-maison', 5), ('ghost', 9)])
        first = book_notebook(plans, 0, plans[0], learner, cat)
        self.assertEqual((first['book_words'], first['words_through_passage']), (1002, 2))
        share = plans[0]['limits']['max_foreign_share']
        self.assertEqual(first['new_foreign_word_allowance'], int(share * PACING_FLOOR_WORDS))
        self.assertEqual([row['item_id'] for row in first['learned']], ['fr-maison', 'fr-chat'])
        self.assertEqual(first['learned'][0]['forms'], ['maison'])
        last = book_notebook(plans, 2, plans[2], learner, cat, new_words_used=10)
        self.assertEqual(last['new_foreign_word_allowance'], int(share * 1002) - 10)
        self.assertEqual(book_notebook(plans, 2, plans[2], learner, cat, 10_000)['new_foreign_word_allowance'], 0)

    def test_known_words_replace_everything_new_words_follow_book_budget(self):
        text = 'אני אני אני אני אני ואני'
        cat = word_catalog(('je', 'אני'), ('et', 'ו'))
        cat['items'].append({'item_id': 'fr-etje', 'kind': 'phrase', 'lemma': 'et je', 'sense_he': 'ואני',
                             'forms': ['et je'], 'priority_tier': 1, 'prerequisite_ids': [],
                             'explanation_he': '', 'min_level': 1})
        p = plan3(text, words_per_edit=2)
        p.update({'selected_item_ids': ['fr-etje'], 'new_item_ids': ['fr-etje']})
        p['limits']['max_foreign_share'] = .2
        starts = [i for i in range(len(text)) if text.startswith('אני', i) and (i == 0 or text[i - 1] == ' ')]
        edits = [edit('אני', s, s + 3, 'je', ['fr-je']) for s in starts]
        edits.append(edit('ואני', len(text) - 4, len(text), 'et je', ['fr-etje']))
        rest_of_book = dict(plan3('מילה ' * 300), plan_id='plan-rest', chunk_id='chunk-rest')
        notebook = book_notebook([p, rest_of_book], 0, p, self.learner([('fr-je', 3)]), cat)
        self.assertEqual(notebook['new_foreign_word_allowance'], 40)   # 20% of the 200-word floor.
        _, h = build_request(p, cat, notebook=notebook)
        chunk, _ = parse_response(answer(p, edits), p, cat, h, notebook=notebook)
        self.assertEqual(len(chunk['edits']), 6)   # Five known words plus one new phrase.
        self.assertEqual(new_foreign_words(chunk, p), 2)
        # Without the notebook the learned word is unknown here, and per passage
        # 2 new of 2 words exceeds 20%: nothing is left.
        _, plain = build_request(p, cat)
        report = {}
        chunk, _ = parse_response(answer(p, edits), p, cat, plain, report=report)
        self.assertEqual(chunk['edits'], [])
        self.assertEqual(report['dropped'], ['unselected_item'] * 5 + ['quota:foreign_share'])
        # A spent book budget likewise trims new words only.
        spent = dict(notebook, new_foreign_word_allowance=1)
        _, h = build_request(p, cat, notebook=spent)
        chunk, _ = parse_response(answer(p, edits), p, cat, h, notebook=spent)
        self.assertEqual([e['replacement'] for e in chunk['edits']], ['je'] * 5)

    def test_notebook_prompt_is_a_separate_version(self):
        p, cat = plan3(), catalog()
        plain_prompt, plain_hash = build_request(p, cat)
        notebook = book_notebook([p], 0, p, self.learner([('fr-chat', 2)]), cat)
        prompt, notebook_hash = build_request(p, cat, notebook=notebook)
        self.assertNotIn('BOOK_NOTEBOOK:', plain_prompt)
        self.assertIn('BOOK_NOTEBOOK:\n```json', prompt)
        self.assertIn('max_foreign_share applies to the whole book', prompt)
        self.assertNotEqual(plain_hash, notebook_hash)
        start = TEXT.index('בבית')
        chunk, _ = parse_response(answer(p, [edit('בבית', start, start + 4)]), p, cat, notebook_hash,
                                  notebook=notebook)
        self.assertEqual(chunk['prompt_version'], NOTEBOOK_PROMPT_VERSION)
        with self.assertRaises(LearningError):
            build_request(plan(), cat, notebook=notebook)   # Policy@1 has no notebook.


class RetryPacingTests(unittest.TestCase):
    def test_rejected_answer_resends_quickly_provider_failure_waits(self):
        import tempfile
        from pathlib import Path
        from scholarly_translation.job_blocks import AUTO_RETRY_DELAYS
        from scholarly_translation.learning_service import INVALID_ANSWER_RETRY_DELAYS, LearningService
        with tempfile.TemporaryDirectory() as root:
            service = LearningService(Path(root))
            service._spent = lambda sid: 0.0
            service._data['jobs']['s'] = {'error_code': 'invalid_generation', 'auto_retry': None}
            self.assertEqual(service._plan_auto_retry('s'), INVALID_ANSWER_RETRY_DELAYS[0])
            self.assertEqual(service._plan_auto_retry('s'), INVALID_ANSWER_RETRY_DELAYS[1])
            service._data['jobs']['t'] = {'error_code': 'preparation_stopped', 'auto_retry': None}
            self.assertEqual(service._plan_auto_retry('t'), AUTO_RETRY_DELAYS[0])


if __name__ == '__main__':
    unittest.main()
