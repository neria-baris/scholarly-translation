"""Asset/DOM fidelity and exact span checks for retained EPUB learning export."""
from copy import deepcopy
import io
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

from scholarly_translation.learning_contracts import (
    DEFAULT_LEVELS, LearningError, fingerprint, new_learner, prepared_hash,
    source_hash, text_hash,
)
from scholarly_translation.learning_epub_preserve import build_preserved_epub
from scholarly_translation.learning_generation import build_chapter_recap
from scholarly_translation.learning_import import import_hebrew_epub
from scholarly_translation.learning_planner import plan_book

NS = {'x': 'http://www.w3.org/1999/xhtml', 's': 'http://www.w3.org/2000/svg'}
EPUB_TYPE = '{http://www.idpf.org/2007/ops}type'
FORMS = {'fr': ('enfant', 'était'), 'de': ('Kind', 'war'), 'es': ('niño', 'era'),
         'yi': ('קינד', 'געווען'), 'it': ('bambino', 'era')}


def epub(body, *, version='3.0'):
    buffer = io.BytesIO()
    entries = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                                 b'<rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        'OPS/book.opf': ('<package xmlns="http://www.idpf.org/2007/opf" version="' + version + '">'
                         '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>ספר מקור</dc:title>'
                         '<dc:language>he</dc:language></metadata><manifest>'
                         '<item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
                         '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
                         '<item id="css" href="style.css" media-type="text/css"/>'
                         '<item id="font" href="book.woff" media-type="font/woff"/>'
                         '<item id="cover" href="cover.png" media-type="image/png"/>'
                         '</manifest><spine page-progression-direction="rtl"><itemref idref="c1"/>'
                         '</spine></package>').encode('utf-8'),
        'OPS/chapter.xhtml': ('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" '
                              'xmlns:svg="http://www.w3.org/2000/svg" xml:lang="he"><head><title>מקור</title>'
                              '<link rel="stylesheet" href="style.css"/></head>'
                              '<body dir="rtl" class="book" style="margin:3em">' + body +
                              '<script type="application/javascript">var original = 1;</script>'
                              '</body></html>').encode('utf-8'),
        'OPS/nav.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><a href="chapter.xhtml#top">TOC</a></body></html>',
        'OPS/style.css': b'@font-face{font-family:Original;src:url(book.woff)}body{font-family:Original;margin:3em}',
        'OPS/book.woff': b'FONT-EXACT-OPAQUE-BYTES\x00\xff',
        'OPS/cover.png': b'\x89PNG\r\n\x1a\nEXACT-ASSET',
        'OPS/audio.mp3': b'ID3EXACT-AUDIO',
    }
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.comment = b'original comment'
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            archive.writestr(info, data)
    return buffer.getvalue()


def records(raw, language='fr', source=None):
    source = source or import_hebrew_epub(raw, book_id='book-preserved')
    items = [{'item_id': language + '-child', 'kind': 'word', 'lemma': FORMS[language][0],
              'sense_he': 'הילד', 'forms': [FORMS[language][0]], 'priority_tier': 1,
              'prerequisite_ids': [], 'explanation_he': '', 'min_level': 1},
             {'item_id': language + '-past', 'kind': 'grammar', 'lemma': FORMS[language][1],
              'sense_he': 'היה', 'forms': [FORMS[language][1]], 'priority_tier': 1,
              'prerequisite_ids': [], 'explanation_he': 'צורת עבר שמוצגת בפרק.', 'min_level': 1}]
    catalog = {'schema_version': 1, 'language': language, 'version': language + '-preserve@1',
               'provenance': {'basis': 'fixture', 'source': 'local', 'license': 'test'},
               'items': items, 'levels': deepcopy(DEFAULT_LEVELS)}
    plans = plan_book(source, new_learner(language, catalog_version=catalog['version']), catalog)
    chunks, proposals = [], []
    for plan in plans:
        edits, vocabulary, grammar = [], [], []
        for unit in plan['units']:
            if unit['kind'] == 'heading':
                continue
            for item in items:
                for match in re.finditer(item['sense_he'], unit['text']):
                    edit = {'unit_id': unit['unit_id'], 'start': match.start(), 'end': match.end(),
                            'original': item['sense_he'], 'replacement': item['lemma'],
                            'item_ids': [item['item_id']] if item['kind'] == 'word' else [],
                            'grammar_ids': [item['item_id']] if item['kind'] == 'grammar' else [],
                            'gloss_he': item['sense_he']}
                    edits.append(edit)
                    entry = {'item_id': item['item_id'], 'edit_indexes': [len(edits) - 1]}
                    if item['kind'] == 'word':
                        vocabulary.append({**entry, 'gloss_he': item['sense_he']})
                    else:
                        grammar.append({**entry, 'explanation_he': item['explanation_he']})
        chunk = {'schema_version': 1, 'plan_id': plan['plan_id'], 'response_version': 1,
                 'provider': 'fake', 'model': 'fixture', 'prompt_version': 'learning-generation@3',
                 'input_hash': fingerprint(plan), 'edits': edits, 'warnings': [], 'language': language,
                 'coverage_item_ids': sorted({key for edit in edits for key in edit['item_ids'] + edit['grammar_ids']}),
                 'content_hash': ''}
        chunk['content_hash'] = fingerprint({key: chunk[key] for key in
                                             ('plan_id', 'input_hash', 'edits', 'coverage_item_ids')})
        chunks.append(chunk)
        proposals.append({'chunk_id': plan['plan_id'], 'recap': {'vocabulary': vocabulary, 'grammar': grammar}})
    recaps = [build_chapter_recap(chapter['chapter_id'],
                               [chunk for plan, chunk in zip(plans, chunks) if plan['chapter_id'] == chapter['chapter_id']],
                               [entry for plan, entry in zip(plans, proposals) if plan['chapter_id'] == chapter['chapter_id']])
              for chapter in source['chapters']]
    prepared = {'chunks': chunks, 'recaps': recaps}
    session = {'schema_version': 1, 'session_id': 'session-preserved', 'learner_id': 'local',
               'language': language, 'book_id': source['book_id'], 'source_hash': source['source_hash'],
               'base_learner_revision': 0, 'policy_version': 'learning-policy@3', 'catalog_version': catalog['version'],
               'level_id': '1', 'support_mode': 'context', 'status': 'ready',
               'prepared_hash': prepared_hash(chunks, recaps), 'chunk_ids': [plan['plan_id'] for plan in plans],
               'read_cursor': None}
    return source, plans, prepared, session, catalog


def chapter(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return ET.fromstring(archive.read('OPS/chapter.xhtml'))


class PreservedEpubTests(unittest.TestCase):
    def assert_code(self, code, raw, args, **options):
        with self.assertRaises(LearningError) as raised:
            build_preserved_epub(raw, *args, **options)
        self.assertEqual(raised.exception.code, code)

    def test_assets_original_layout_inline_media_links_and_comments_preserved(self):
        body = ('<h1 id="top">פרק ראשון</h1><p id="p1" class="poem" xml:space="preserve">'
                '  <em class="accent">הי</em>לד היה כאן. '
                '<img src="cover.png" alt="עטיפה" width="120"/>'
                '<a id="old-link" href="#top"><strong>קישור</strong></a>'
                '<svg:svg viewBox="0 0 1 1"><svg:path d="M0 0L1 1"/></svg:svg>'
                '<audio src="audio.mp3" controls="controls"/> סוף. <!--retain-comment-->  </p>')
        raw = epub(body)
        args = records(raw)
        before = deepcopy(args)
        payload = build_preserved_epub(raw, *args, include_meanings=False)
        self.assertEqual(payload, build_preserved_epub(raw, *args, include_meanings=False))
        self.assertEqual(args, before)
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(io.BytesIO(payload)) as exported:
            self.assertEqual(original.namelist(), exported.namelist())
            self.assertEqual(original.comment, exported.comment)
            for name in original.namelist():
                if name != 'OPS/chapter.xhtml':
                    self.assertEqual(original.read(name), exported.read(name), name)
            self.assertIn(b'<!--retain-comment-->', exported.read('OPS/chapter.xhtml'))
            self.assertEqual(exported.infolist()[0].compress_type, zipfile.ZIP_STORED)
        root = chapter(payload)
        p = root.find('.//x:p[@id="p1"]', NS)
        self.assertEqual(''.join(p.itertext()), '  enfant était כאן. קישור סוף.   ')
        self.assertIsNotNone(p.find('x:em[@class="accent"]', NS))
        self.assertEqual(p.attrib['{http://www.w3.org/XML/1998/namespace}space'], 'preserve')
        self.assertEqual(p.find('x:a[@id="old-link"]', NS).attrib['href'], '#top')
        self.assertEqual(p.find('x:img', NS).attrib['src'], 'cover.png')
        self.assertEqual(p.find('s:svg/s:path', NS).attrib['d'], 'M0 0L1 1')
        self.assertEqual(p.find('x:audio', NS).attrib['src'], 'audio.mp3')
        body_out = root.find('x:body', NS)
        self.assertEqual(body_out.attrib, {'dir': 'rtl', 'class': 'book', 'style': 'margin:3em'})
        self.assertEqual(root.find('.//x:script', NS).text, 'var original = 1;')

    def test_optional_notes_preserve_existing_anchor_and_avoid_nested_links(self):
        raw = epub('<h1 id="top">פרק ראשון</h1><p id="p1">'
                   '<a id="old" href="#top"><em>הי</em>לד</a> היה כאן.</p>')
        payload = build_preserved_epub(raw, *records(raw))
        root = chapter(payload)
        old = root.find('.//x:a[@id="old"]', NS)
        self.assertEqual(old.attrib['href'], '#top')
        self.assertEqual(''.join(old.itertext()), 'enfant')
        self.assertFalse(old.findall('.//x:a', NS))
        p = root.find('.//x:p[@id="p1"]', NS)
        self.assertNotIn('הילד', ''.join(p.itertext()))
        references = [node for node in root.iter() if node.attrib.get(EPUB_TYPE) == 'noteref']
        notes = [node for node in root.iter() if node.attrib.get(EPUB_TYPE) == 'footnote']
        self.assertEqual(len(references), 2)
        self.assertEqual(len(notes), 2)
        ids = [node.get('id') for node in root.iter() if node.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        for reference in references:
            self.assertIn(reference.attrib['href'][1:], ids)
        self.assertIn('צורת עבר שמוצגת בפרק.', ''.join(root.itertext()))

    def test_long_split_units_preserve_original_whitespace_exactly(self):
        text = ' \nהילד\tהיה  כאן.\n' + 'טקסט ארוך עם  רווחים\n\t' * 190 + '\nהילד היה בסוף.  '
        raw = epub('<h1>פרק ראשון</h1><p id="long">' + text + '</p>')
        args = records(raw)
        self.assertTrue(any('-c1' in unit['unit_id'] for unit in args[0]['chapters'][0]['units']))
        payload = build_preserved_epub(raw, *args, include_meanings=False)
        actual = ''.join(chapter(payload).find('.//x:p[@id="long"]', NS).itertext())
        self.assertEqual(actual, text.replace('הילד', 'enfant').replace('היה', 'était'))

    def test_translation_canonical_ids_exact_sequence_and_extra_front_matter(self):
        raw = epub('<h1>כותרת מקדימה</h1><p id="one">הילד היה כאן.</p><p id="two">טקסט נוסף בעברית.</p>')
        source = import_hebrew_epub(raw, book_id='from-translation')
        source['chapters'][0]['units'] = source['chapters'][0]['units'][1:]
        for index, unit in enumerate(source['chapters'][0]['units']):
            unit['unit_id'] = f'canonical-unit-{index}'
        source['origin'] = {'kind': 'translation_library', 'original_hash': text_hash('source-language-original'),
                            'source_job_id': 'job-one', 'source_revision': 4}
        source['source_hash'] = source_hash(source)
        payload = build_preserved_epub(raw, *records(raw, source=source), include_meanings=False)
        root = chapter(payload)
        self.assertEqual(root.find('.//x:h1', NS).text, 'כותרת מקדימה')
        self.assertEqual(''.join(root.find('.//x:p[@id="one"]', NS).itertext()), 'enfant était כאן.')

    def test_five_foreign_directions_and_highlight_without_inline_meaning(self):
        raw = epub('<h1>פרק ראשון</h1><p id="p1">הילד היה כאן.</p>')
        for language in FORMS:
            with self.subTest(language=language):
                root = chapter(build_preserved_epub(raw, *records(raw, language), include_meanings=False))
                p = root.find('.//x:p[@id="p1"]', NS)
                self.assertEqual(''.join(p.itertext()), FORMS[language][0] + ' ' + FORMS[language][1] + ' כאן.')
                for node in root.findall('.//x:bdi', NS):
                    self.assertEqual(node.get('dir'), 'rtl' if language == 'yi' else 'ltr')
                    self.assertEqual(node.get('lang'), language)
                    self.assertIn('unicode-bidi:isolate', node.get('style'))
                    self.assertIn('underline dotted', node.get('style'))

    def test_multiple_learning_chapters_recaps_insert_at_their_boundaries(self):
        raw = epub('<h1 id="one">פרק ראשון</h1><p id="p1">הילד היה כאן.</p>'
                   '<h1 id="two">פרק שני</h1><p id="p2">הילד היה שם.</p>')
        root = chapter(build_preserved_epub(raw, *records(raw), include_meanings=False))
        children = list(root.find('x:body', NS))
        classes = [node.get('class') for node in children]
        self.assertEqual(classes.count('learning-recap'), 2)
        one_recap = classes.index('learning-recap')
        two_heading = next(index for index, node in enumerate(children) if node.get('id') == 'two')
        self.assertLess(one_recap, two_heading)

    def test_merged_chapter_cross_spine_note_links_and_backlinks_resolve(self):
        raw = epub('<p id="p1">הילד היה כאן.</p>')
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(output, 'w') as archive:
            for item in original.infolist():
                content = original.read(item.filename)
                if item.filename == 'OPS/book.opf':
                    content = content.replace(b'</manifest>', b'<item id="c2" href="sub/second.xhtml" '
                                              b'media-type="application/xhtml+xml"/></manifest>')
                    content = content.replace(b'</spine>', b'<itemref idref="c2"/></spine>')
                archive.writestr(item, content)
            archive.writestr(zipfile.ZipInfo('OPS/sub/second.xhtml', (2000, 1, 1, 0, 0, 0)),
                             '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="p2">'
                             'הילד היה שם.</p></body></html>')
        raw = output.getvalue()
        args = records(raw)
        self.assertEqual(len(args[0]['chapters']), 1)
        payload = build_preserved_epub(raw, *args)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            first = ET.fromstring(archive.read('OPS/chapter.xhtml'))
            second = ET.fromstring(archive.read('OPS/sub/second.xhtml'))
        first_refs = [node for node in first.iter() if node.get(EPUB_TYPE) == 'noteref']
        notes = [node for node in second.iter() if node.get(EPUB_TYPE) == 'footnote']
        second_ids = {node.get('id') for node in second.iter() if node.get('id')}
        self.assertEqual(len(notes), 4)
        for reference in first_refs:
            self.assertTrue(reference.get('href').startswith('sub/second.xhtml#'))
            self.assertIn(reference.get('href').split('#')[1], second_ids)
            note = next(node for node in notes if node.get('id') == reference.get('href').split('#')[1])
            self.assertEqual(note.find('.//x:a', NS).get('href'), '../chapter.xhtml#' + reference.get('id'))

    def test_mapping_mismatch_ambiguity_and_nested_blocks_fail_without_guessing(self):
        raw = epub('<h1>פרק ראשון</h1><p>הילד היה כאן.</p>')
        source = import_hebrew_epub(raw)
        source['chapters'][0]['units'][1]['text'] = 'טקסט אחר בעברית.'
        source['source_hash'] = source_hash(source)
        self.assert_code('preservation_unavailable', raw, records(raw, source=source))
        duplicate_raw = epub('<p>הילד היה כאן.</p><p>הילד היה כאן.</p>')
        source = import_hebrew_epub(duplicate_raw)
        source['chapters'][0]['units'] = source['chapters'][0]['units'][:1]
        source['chapters'][0]['units'][0]['unit_id'] = 'canonical'
        source['origin']['kind'] = 'translation_library'
        source['source_hash'] = source_hash(source)
        self.assert_code('preservation_unavailable', duplicate_raw, records(duplicate_raw, source=source))
        nested_raw = epub('<blockquote><p>הילד היה כאן.</p></blockquote>')
        self.assert_code('preservation_unavailable', nested_raw, records(nested_raw))

    def test_corrupt_archive_original_hash_incomplete_book_and_options_fail_explicitly(self):
        raw = epub('<h1>פרק ראשון</h1><p>הילד היה כאן.</p>')
        args = records(raw)
        self.assert_code('invalid_preserved_epub', b'not an archive', args)
        changed = deepcopy(args)
        changed[0]['origin']['original_hash'] = '0' * 64
        self.assert_code('invalid_preserved_epub', raw, changed)
        changed = deepcopy(args)
        changed[3]['status'] = 'paused'
        self.assert_code('book_not_ready', raw, changed)
        self.assert_code('invalid_export_options', raw, args, include_meanings=1)

    def test_original_epub2_package_is_copied_without_conversion(self):
        raw = epub('<h1>פרק ראשון</h1><p>הילד היה כאן.</p>', version='2.0')
        payload = build_preserved_epub(raw, *records(raw))
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(io.BytesIO(payload)) as output:
            self.assertEqual(original.read('OPS/book.opf'), output.read('OPS/book.opf'))


if __name__ == '__main__':
    unittest.main()
