"""Offline learning export fidelity/coverage checks without model or network."""
from copy import deepcopy
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from scholarly_translation.learning_contracts import (
    DEFAULT_LEVELS, LearningError, fingerprint, fixture_source, new_learner,
    prepared_hash, source_hash,
)
from scholarly_translation.learning_export import export_learning_book
from scholarly_translation.learning_generation import build_chapter_recap
from scholarly_translation.learning_planner import plan_book
from scholarly_translation.learning_vocabulary import proposal_item

FORMS = {'fr': ('bonjour', 'suis'), 'de': ('Hallo', 'bin'), 'es': ('hola', 'soy'),
         'yi': ('שלום', 'בין'), 'it': ('ciao', 'sono')}
NS = {'x': 'http://www.w3.org/1999/xhtml', 'opf': 'http://www.idpf.org/2007/opf',
      'dc': 'http://purl.org/dc/elements/1.1/'}
EPUB_TYPE = '{http://www.idpf.org/2007/ops}type'


def records(language='fr', *, dynamic=False, long=False, policy='learning-policy@3'):
    source = fixture_source()
    source['title'] = 'ספר <שלם> & בעברית'
    body = 'שלום, אני כאן. <script>alert(1)</script> & טקסט 😀\r\n'
    if long:
        body += 'סיפור ארוך מאוד בלי חיתוך. ' * 9000
    source['chapters'] = [{'chapter_id': f'chapter-{index}', 'title': f'פרק {index + 1}', 'units': [
        {'unit_id': f'heading-{index}', 'kind': 'heading', 'text': f'כותרת {index + 1}'},
        {'unit_id': f'unit-{index}', 'kind': 'paragraph', 'text': body},
        {'unit_id': f'last-{index}', 'kind': 'paragraph', 'text': 'שלום, אני עדיין כאן בסוף הפרק.'}
    ]} for index in range(2)]
    source['source_hash'] = source_hash(source)
    items = []
    for kind, surface, sense in zip(('word', 'grammar'), FORMS[language], ('שלום', 'אני')):
        item = {'item_id': f'{language}-{kind}', 'kind': kind, 'lemma': surface, 'sense_he': sense,
                'forms': [surface], 'priority_tier': 1, 'prerequisite_ids': [],
                'explanation_he': 'צורת גוף ראשון בהווה.\nהסבר <מלא> & בטוח.' if kind == 'grammar' else '',
                'min_level': 1}
        if dynamic:
            item = proposal_item({key: item[key] for key in
                                  ('item_id', 'kind', 'lemma', 'sense_he', 'forms', 'explanation_he')},
                                 language, 1)
        items.append(item)
    catalog = {'schema_version': 1, 'language': language, 'version': language + '-export@1',
               'provenance': {'basis': 'fixture', 'source': 'local', 'license': 'test'},
               'items': items, 'levels': deepcopy(DEFAULT_LEVELS)}
    learner = new_learner(language, catalog_version=catalog['version'])
    plans = plan_book(source, learner, catalog, policy_version=policy)
    chunks, proposals = [], []
    for plan in plans:
        edits, vocabulary, grammar = [], [], []
        for unit in plan['units']:
            if unit['kind'] == 'heading':
                continue
            for item in items:
                start = unit['text'].index(item['sense_he'])
                edit = {'unit_id': unit['unit_id'], 'start': start,
                        'end': start + len(item['sense_he']), 'original': item['sense_he'],
                        'replacement': item['lemma'], 'item_ids': [item['item_id']] if item['kind'] == 'word' else [],
                        'grammar_ids': [item['item_id']] if item['kind'] == 'grammar' else [],
                        'gloss_he': item['sense_he']}
                edits.append(edit)
                entry = {'item_id': item['item_id'], 'edit_indexes': [len(edits) - 1]}
                if item['kind'] == 'word':
                    vocabulary.append({**entry, 'gloss_he': item['sense_he']})
                else:
                    grammar.append({**entry, 'explanation_he': item['explanation_he']})
        chunk = {'schema_version': 1, 'plan_id': plan['plan_id'], 'response_version': 1,
                 'provider': 'fake', 'model': 'synthetic', 'prompt_version': 'learning-generation@3',
                 'input_hash': fingerprint(plan), 'edits': edits,
                 'warnings': [{'code': 'ambiguous_meaning', 'unit_id': plan['units'][0]['unit_id']}],
                 'coverage_item_ids': sorted({key for edit in edits for key in edit['item_ids'] + edit['grammar_ids']}),
                 'language': language, 'content_hash': ''}
        if dynamic and edits:
            chunk['introduced_items'] = deepcopy(items)
        refresh_chunk(chunk)
        chunks.append(chunk)
        proposals.append({'chunk_id': plan['plan_id'], 'recap': {'vocabulary': vocabulary, 'grammar': grammar}})
    recaps = [build_chapter_recap(chapter['chapter_id'],
                               [chunk for plan, chunk in zip(plans, chunks) if plan['chapter_id'] == chapter['chapter_id']],
                               [entry for plan, entry in zip(plans, proposals) if plan['chapter_id'] == chapter['chapter_id']])
              for chapter in source['chapters']]
    prepared = {'chunks': chunks, 'recaps': recaps}
    session = {'schema_version': 1, 'session_id': 'session-export', 'learner_id': 'local',
               'language': language, 'book_id': source['book_id'], 'source_hash': source['source_hash'],
               'base_learner_revision': 0, 'policy_version': policy, 'catalog_version': catalog['version'],
               'level_id': '1', 'support_mode': 'context', 'status': 'ready',
               'prepared_hash': prepared_hash(chunks, recaps), 'chunk_ids': [plan['plan_id'] for plan in plans],
               'read_cursor': None}
    return source, plans, prepared, session, catalog


def refresh_chunk(chunk):
    data = {key: chunk[key] for key in ('plan_id', 'input_hash', 'edits', 'coverage_item_ids')}
    if chunk.get('introduced_items'):
        data['introduced_items'] = chunk['introduced_items']
    chunk['content_hash'] = fingerprint(data)


def refresh_prepared(args):
    args[3]['prepared_hash'] = prepared_hash(args[2]['chunks'], args[2]['recaps'])


class LearningExportTests(unittest.TestCase):
    def assert_code(self, code, args, **options):
        with self.assertRaises(LearningError) as raised:
            export_learning_book(*args, **options)
        self.assertEqual(raised.exception.code, code)

    def test_epub_structure_navigation_xml_notes_and_determinism(self):
        args = records()
        before = deepcopy(args)
        payload = export_learning_book(*args)
        self.assertEqual(payload, export_learning_book(*args))
        self.assertEqual(args, before)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(archive.infolist()[0].filename, 'mimetype')
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read('mimetype'), b'application/epub+zip')
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            self.assertTrue(all(not name.startswith('/') and '..' not in name for name in archive.namelist()))
            for name in archive.namelist():
                if name.endswith(('.xml', '.opf', '.xhtml')):
                    ET.fromstring(archive.read(name))
            opf = ET.fromstring(archive.read('EPUB/package.opf'))
            self.assertEqual(opf.attrib['version'], '3.0')
            spine = opf.find('opf:spine', NS)
            self.assertEqual(spine.attrib['page-progression-direction'], 'rtl')
            self.assertEqual([row.attrib['idref'] for row in spine], ['chapter-0001', 'chapter-0002'])
            self.assertEqual(opf.find('opf:metadata/dc:title', NS).text, args[0]['title'])
            nav = ET.fromstring(archive.read('EPUB/nav.xhtml'))
            self.assertEqual([link.attrib['href'] for link in nav.findall('.//x:nav//x:a', NS)],
                             ['chapter-0001.xhtml', 'chapter-0002.xhtml'])
            chapter = ET.fromstring(archive.read('EPUB/chapter-0001.xhtml'))
            ids = {node.attrib['id']: node for node in chapter.iter() if 'id' in node.attrib}
            notes = [node for node in chapter.iter() if node.attrib.get(EPUB_TYPE) == 'noteref']
            self.assertEqual(len(notes), 4)
            for link in notes:
                self.assertEqual(ids[link.attrib['href'][1:]].attrib[EPUB_TYPE], 'footnote')
                self.assertNotIn('שלום', ''.join(link.itertext()))
            self.assertIn('צורת גוף ראשון בהווה.', ''.join(chapter.itertext()))
            self.assertIn('עמימות', ''.join(chapter.itertext()))
            self.assertFalse(chapter.findall('.//x:script', NS))
            self.assertIn('script>alert', ''.join(chapter.itertext()))

    def test_exact_long_units_and_unicode_preserved_with_no_adjacent_glosses(self):
        args = records('yi', long=True)
        html_bytes = export_learning_book(*args, format='html', include_meanings=False)
        root = ET.fromstring(html_bytes)
        units = root.findall('.//*[@data-unit-id]')
        self.assertEqual(len(units), 6)
        originals = {unit['unit_id']: unit for chapter in args[0]['chapters'] for unit in chapter['units']}
        edits = {unit_id: [] for unit_id in originals}
        for chunk in args[2]['chunks']:
            for edit in chunk['edits']:
                edits[edit['unit_id']].append(edit)
        for node in units:
            unit_id = node.attrib['data-unit-id']
            expected = originals[unit_id]['text']
            for edit in sorted(edits[unit_id], key=lambda row: row['start'], reverse=True):
                expected = expected[:edit['start']] + edit['replacement'] + expected[edit['end']:]
            self.assertEqual(''.join(node.itertext()), expected)
        self.assertGreater(len(html_bytes), 400000)
        self.assertFalse(any(node.attrib.get(EPUB_TYPE) == 'noteref' for node in root.iter()))
        self.assertFalse(root.findall('.//x:script', NS))
        self.assertFalse(root.findall('.//x:link', NS))
        self.assertEqual(root.attrib['dir'], 'rtl')
        self.assertTrue(all(node.attrib['dir'] == 'rtl' for node in root.findall('.//x:bdi', NS)))

    def test_all_languages_dynamic_definitions_and_actual_examples(self):
        for language in FORMS:
            with self.subTest(language=language):
                args = records(language, dynamic=True)
                # Untrusted cached display fields never override the accepted edit.
                args[2]['recaps'][0]['grammar'][0]['examples'][0].update(
                    {'foreign': 'FAKE EXAMPLE', 'hebrew': 'דוגמה שגויה'})
                refresh_prepared(args)
                root = ET.fromstring(export_learning_book(*args, format='html'))
                text = ''.join(root.itertext())
                self.assertIn(FORMS[language][1], text)
                self.assertNotIn('FAKE EXAMPLE', text)
                self.assertIn('הסבר <מלא> & בטוח.', text)
                self.assertTrue(all(node.attrib['lang'] == language for node in root.findall('.//x:bdi', NS)))
                self.assertTrue(all(node.attrib['dir'] == ('rtl' if language == 'yi' else 'ltr')
                                    for node in root.findall('.//x:bdi', NS)))

    def test_format_and_options_strict_and_incomplete_sessions_refused(self):
        args = records()
        for value in ('pdf', 'EPUB', '', None, 1, ['epub']):
            self.assert_code('invalid_export_format', args, format=value)
        for value in (1, 0, 'true', None, []):
            self.assert_code('invalid_export_options', args, include_meanings=value)
        for status in ('imported', 'preparing', 'paused', 'failed'):
            stopped = deepcopy(args)
            stopped[3]['status'] = status
            self.assert_code('book_not_ready', stopped)
        done = deepcopy(args)
        done[3]['status'] = 'completed'
        self.assertEqual(export_learning_book(*done), export_learning_book(*args))

    def test_missing_duplicate_reordered_or_changed_source_units_refused(self):
        cases = []
        args = records()
        changed = deepcopy(args); changed[1][0]['units'].pop(); cases.append(changed)
        changed = deepcopy(args); changed[1][0]['units'].append(deepcopy(changed[1][0]['units'][0])); cases.append(changed)
        changed = deepcopy(args); changed[1][0]['units'].reverse(); cases.append(changed)
        changed = deepcopy(args); changed[1][0]['units'][0]['text'] += ' שינוי'; cases.append(changed)
        changed = deepcopy(args); changed[1].reverse(); cases.append(changed)
        changed = deepcopy(args); changed[2]['chunks'].reverse(); refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[2]['recaps'].reverse(); refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[3]['chunk_ids'].pop(); cases.append(changed)
        changed = deepcopy(args); changed[3]['source_hash'] = '0' * 64; cases.append(changed)
        for index, changed in enumerate(cases):
            with self.subTest(case=index):
                self.assert_code('invalid_export_coverage', changed)

    def test_hashes_examples_definitions_and_source_spans_refused(self):
        cases = []
        args = records()
        changed = deepcopy(args); changed[3]['prepared_hash'] = '0' * 64; cases.append(changed)
        changed = deepcopy(args); changed[2]['chunks'][0]['content_hash'] = '0' * 64; refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[2]['recaps'][0]['chunk_hashes'] = []; refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[2]['recaps'][0]['warnings'] = []; refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[2]['recaps'][0]['grammar'][0]['examples'][0]['chunk_id'] = 'unknown'; refresh_prepared(changed); cases.append(changed)
        changed = deepcopy(args); changed[4]['items'].pop(); cases.append(changed)
        changed = records(dynamic=True); changed[4]['items'][0]['lemma'] = 'different'; cases.append(changed)
        changed = deepcopy(args); changed[2]['chunks'][0]['edits'][0]['original'] = 'מזויף'; refresh_chunk(changed[2]['chunks'][0]);
        changed[2]['recaps'][0]['chunk_hashes'] = sorted({chunk['content_hash'] for chunk in changed[2]['chunks'][:1]});
        refresh_prepared(changed); cases.append(changed)
        for index, changed in enumerate(cases):
            with self.subTest(case=index):
                self.assert_code('invalid_export_coverage', changed)

    def test_xml_forbidden_controls_and_surrogates_never_silently_dropped(self):
        for character in ('\x00', '\x08', '\x1f', '\ufffe', '\ud800'):
            args = records()
            args[2]['recaps'][0]['grammar'][0]['explanation_he'] += character
            self.assert_code('invalid_export_text', args)

    def test_malformed_prepared_fields_fail_explicitly(self):
        args = records()
        args[2]['chunks'][0]['edits'][0]['item_ids'] = [{}]
        refresh_chunk(args[2]['chunks'][0])
        refresh_prepared(args)
        self.assert_code('invalid_export_coverage', args)

    def test_html_links_have_unique_ids_and_preserve_all_prepared_labels(self):
        args = records()
        args[4]['items'][0]['lemma'] = '<script>foreign & unsafe</script>'
        for chunk in args[2]['chunks']:
            for edit in chunk['edits']:
                if edit['item_ids']:
                    edit['replacement'] = args[4]['items'][0]['lemma']
                    edit['gloss_he'] = 'פירוש <מלא> & בטוח'
            refresh_chunk(chunk)
        for recap, chapter in zip(args[2]['recaps'], args[0]['chapters']):
            recap['chunk_hashes'] = sorted({chunk['content_hash'] for plan, chunk in zip(args[1], args[2]['chunks'])
                                           if plan['chapter_id'] == chapter['chapter_id']})
        refresh_prepared(args)
        root = ET.fromstring(export_learning_book(*args, format='html'))
        ids = [node.attrib['id'] for node in root.iter() if 'id' in node.attrib]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(args[4]['items'][0]['lemma'], ''.join(root.itertext()))
        self.assertIn('פירוש <מלא> & בטוח', ''.join(root.itertext()))
        self.assertFalse(root.findall('.//x:script', NS))
        for link in root.findall('.//x:a', NS):
            self.assertIn(link.attrib['href'][1:], ids)

    def test_legacy_policy_chunks_without_language_keep_pinned_direction(self):
        for policy in ('learning-policy@1', 'learning-policy@2'):
            args = records('yi', policy=policy)
            for chunk in args[2]['chunks']:
                chunk.pop('language')
            refresh_prepared(args)
            root = ET.fromstring(export_learning_book(*args, format='html'))
            self.assertTrue(all(node.attrib['lang'] == 'yi' and node.attrib['dir'] == 'rtl'
                                for node in root.findall('.//x:bdi', NS)))


if __name__ == '__main__':
    unittest.main()
