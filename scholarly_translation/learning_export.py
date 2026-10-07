"""Deterministic offline exports of complete, immutable learning books.

This module only transforms validated records to bytes. It never reads files,
calls a model, changes reading progress, or regenerates accepted substitutions.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

from .learning_contracts import (
    LearningError, fingerprint, prepared_hash, require, validate_catalog,
    validate_generated, validate_plan, validate_recap, validate_session,
    validate_source,
)
from .learning_render import render_chunk

_XHTML = 'http://www.w3.org/1999/xhtml'
_EPUB = 'http://www.idpf.org/2007/ops'
_MODIFIED = '2000-01-01T00:00:00Z'
_LIMITATION = ('זהו ייצוא טקסט בעימוד חדש. תמונות, עיצוב וקובצי מדיה מהספר המקורי '
               'אינם נכללים. תמיכה בקישורי פירוש ובכיווניות תלויה ביישום הקריאה.')
_CSS = '''html,body{direction:rtl}body{font-family:serif;line-height:1.65;margin:1.4em;
max-width:48em}p,h1,h2,h3,li{white-space:pre-wrap;overflow-wrap:anywhere}
bdi[dir="ltr"]{direction:ltr;unicode-bidi:isolate}bdi[dir="rtl"]{direction:rtl;
unicode-bidi:isolate}.learning-foreign{font-weight:bold}a{color:inherit}
.learning-noteref{text-decoration:underline dotted}.export-notice{font-size:.9em}
.chapter{break-before:page}.learning-recap{margin-top:2em;border-top:1px solid #888}
.learning-notes{margin-top:2em}.learning-backlink{font-size:.85em}
.learning-foreign[lang="yi"]{color:#725125;text-decoration:underline dotted;text-underline-offset:.18em}
'''
_WARNING_LABELS = {'coverage_shortfall': 'לא כל פריטי הלימוד המתוכננים הופיעו בקטע.',
                   'ambiguous_meaning': 'בקטע נמצאה משמעות שיש בה עמימות.'}


def _coverage(condition, message):
    require(condition, 'invalid_export_coverage', message)


def _check_text(value):
    """Reject XML 1.0 forbidden characters without dropping any user text."""
    if isinstance(value, str):
        require(all(char in '\t\n\r' or 0x20 <= ord(char) <= 0xD7FF or
                    0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF
                    for char in value), 'invalid_export_text')
    elif isinstance(value, dict):
        for key, entry in value.items():
            _check_text(key)
            _check_text(entry)
    elif isinstance(value, (list, tuple)):
        for entry in value:
            _check_text(entry)


def _e(value):
    return html.escape(value, quote=True).replace('\r', '&#13;')


def _validate(source, plans, prepared, session, catalog):
    for record in (source, plans, prepared, session, catalog):
        _check_text(record)
    _coverage(isinstance(prepared, dict) and set(prepared) == {'chunks', 'recaps'}, 'prepared_shape')
    _coverage(isinstance(plans, list) and bool(plans), 'plans')
    _coverage(isinstance(prepared['chunks'], list) and isinstance(prepared['recaps'], list), 'prepared_lists')
    try:
        validate_source(source)
        validate_session(session)
        validate_catalog(catalog)
        for plan in plans:
            validate_plan(plan)
        for chunk in prepared['chunks']:
            validate_generated(chunk)
        for recap in prepared['recaps']:
            validate_recap(recap)
    except (LearningError, KeyError, TypeError, ValueError) as error:
        raise LearningError('invalid_export_coverage', 'invalid_record') from error
    require(session['status'] in ('ready', 'completed') and session['prepared_hash'] is not None,
            'book_not_ready')
    _coverage(session['prepared_hash'] == prepared_hash(prepared['chunks'], prepared['recaps']),
              'prepared_hash_mismatch')
    _coverage(session['book_id'] == source['book_id'] and session['source_hash'] == source['source_hash']
              and session['language'] == catalog['language'] and session['catalog_version'] == catalog['version'],
              'pinned_records')
    chunks = prepared['chunks']
    plan_ids = [plan['plan_id'] for plan in plans]
    _coverage(len(plans) == len(chunks) and len(plan_ids) == len(set(plan_ids)) and
              plan_ids == session['chunk_ids'] == [chunk['plan_id'] for chunk in chunks], 'chunk_order')
    chapter_ids = [chapter['chapter_id'] for chapter in source['chapters']]
    _coverage(chapter_ids == [recap['chapter_id'] for recap in prepared['recaps']], 'recap_order')
    items = {item['item_id']: item for item in catalog['items']}
    for row in session.get('vocabulary', []):
        _coverage(items.get(row['item']['item_id']) == row['item'], 'snapshot_definition')
    grouped = {chapter_id: [] for chapter_id in chapter_ids}
    ordered_chapters = []
    for plan, chunk in zip(plans, chunks):
        _coverage(plan['chapter_id'] in grouped, 'unknown_chapter')
        _coverage(all(plan[key] == session[key] for key in
                      ('book_id', 'source_hash', 'catalog_version', 'policy_version', 'level_id', 'support_mode')),
                  'pinned_plan')
        _coverage(plan.get('language', session['language']) == session['language'] and
                  chunk.get('language', session['language']) == session['language'], 'chunk_language')
        grouped[plan['chapter_id']].append((plan, chunk))
        if not ordered_chapters or ordered_chapters[-1] != plan['chapter_id']:
            ordered_chapters.append(plan['chapter_id'])
        used = {item_id for edit in chunk['edits'] for item_id in edit['item_ids'] + edit['grammar_ids']}
        _coverage(used <= set(items) and sorted(used) == chunk['coverage_item_ids'], 'chunk_items')
        for item in chunk.get('introduced_items', []):
            _coverage(items.get(item['item_id']) == item, 'introduced_definition')
        hash_input = {key: chunk[key] for key in ('plan_id', 'input_hash', 'edits', 'coverage_item_ids')}
        if chunk.get('introduced_items'):
            hash_input['introduced_items'] = chunk['introduced_items']
        _coverage(fingerprint(hash_input) == chunk['content_hash'], 'chunk_hash_mismatch')
    _coverage(ordered_chapters == chapter_ids, 'chapter_order')
    for chapter, recap in zip(source['chapters'], prepared['recaps']):
        pairs = grouped[chapter['chapter_id']]
        _coverage([unit for plan, _ in pairs for unit in plan['units']] == chapter['units'], 'unit_coverage')
        by_chunk = {chunk['plan_id']: chunk for _, chunk in pairs}
        _coverage(recap['chunk_hashes'] == sorted({chunk['content_hash'] for _, chunk in pairs}), 'recap_chunks')
        _coverage(recap['warnings'] == [warning for _, chunk in pairs for warning in chunk['warnings']],
                  'recap_warnings')
        for kind, field in (('vocabulary', 'item_ids'), ('grammar', 'grammar_ids')):
            entries = recap[kind]
            ids = [entry.get('item_id') for entry in entries if isinstance(entry, dict)]
            _coverage(len(ids) == len(entries) and len(ids) == len(set(ids)), 'recap_entries')
            used = {item_id for _, chunk in pairs for edit in chunk['edits'] for item_id in edit[field]}
            _coverage(set(ids) == used and set(ids) <= set(items), 'recap_items')
            for entry in entries:
                text_key = 'gloss_he' if kind == 'vocabulary' else 'explanation_he'
                _coverage(isinstance(entry.get(text_key), str), 'recap_text')
                if kind == 'grammar':
                    _coverage(isinstance(entry.get('examples'), list) and bool(entry['examples']), 'grammar_examples')
                    for example in entry['examples']:
                        _coverage(isinstance(example, dict) and example.get('chunk_id') in by_chunk and
                                  type(example.get('edit_index')) is int, 'grammar_example')
                        edits = by_chunk[example['chunk_id']]['edits']
                        index = example['edit_index']
                        _coverage(0 <= index < len(edits) and entry['item_id'] in edits[index]['grammar_ids'],
                                  'grammar_example_occurrence')
        for warning in recap['warnings']:
            _coverage(isinstance(warning, dict) and isinstance(warning.get('code'), str), 'warning')
        if 'lesson' in recap:
            from .learning_lesson import validate_lesson
            try:
                validate_lesson(recap['lesson'])
            except LearningError:
                _coverage(False, 'lesson')
    return grouped, items


def _foreign(text, language):
    direction = 'rtl' if language == 'yi' else 'ltr'
    return f'<bdi lang="{language}" dir="{direction}" class="learning-foreign">{_e(text)}</bdi>'


def _recap(recap, pairs, items, language):
    parts = ['<section class="learning-recap" aria-label="סיכום הפרק"><h2>סיכום הפרק</h2>']
    if recap['vocabulary']:
        parts.append('<h3>מילים וביטויים</h3><ul>')
        for entry in recap['vocabulary']:
            label = _foreign(items[entry['item_id']]['lemma'], language)
            parts.append(f'<li>{label} — <span lang="he" dir="rtl">{_e(entry["gloss_he"])}</span></li>')
        parts.append('</ul>')
    if recap['grammar']:
        by_chunk = {chunk['plan_id']: chunk for _, chunk in pairs}
        parts.append('<h3>דקדוק</h3>')
        for entry in recap['grammar']:
            item = items[entry['item_id']]
            parts.append(f'<section><h3>{_foreign(item["lemma"], language)} — {_e(item["sense_he"])}</h3>'
                         f'<p>{_e(entry["explanation_he"])}</p><ul>')
            for example in entry['examples']:
                edit = by_chunk[example['chunk_id']]['edits'][example['edit_index']]
                parts.append(f'<li>{_foreign(edit["replacement"], language)} — '
                             f'<span lang="he" dir="rtl">{_e(edit["original"])}</span></li>')
            parts.append('</ul></section>')
    lesson = recap.get('lesson')
    if lesson and lesson['status'] == 'ready':
        parts.append('<section class="learning-lesson"><h3>שיעור דקדוק לפרק</h3>')
        for paragraph in lesson['paragraphs']:
            parts.append(f'<h4>{_e(paragraph["heading_he"])}</h4><p>{_e(paragraph["text_he"])}</p>')
            if paragraph['examples']:
                parts.append('<ul>')
                for example in paragraph['examples']:
                    note = f' <small>{_e(example["note_he"])}</small>' if example['note_he'] else ''
                    parts.append(f'<li>{_foreign(example["foreign"], language)} — '
                                 f'<span lang="he" dir="rtl">{_e(example["hebrew"])}</span>{note}</li>')
                parts.append('</ul>')
        parts.append('<p><small>השיעור נכתב בעזרת המודל ולא עבר ביקורת לשונית נפרדת.</small></p></section>')
    if not recap['vocabulary'] and not recap['grammar'] and not (lesson and lesson['status'] == 'ready'):
        parts.append('<p>לא נוספו פריטי לימוד חדשים בפרק זה.</p>')
    if recap['warnings']:
        parts.append('<h3>הערות הכנה</h3><ul>')
        for warning in recap['warnings']:
            text = _WARNING_LABELS.get(warning['code'], warning['code'])
            if warning.get('unit_id') is not None:
                text += ' (' + str(warning['unit_id']) + ')'
            parts.append(f'<li>{_e(text)}</li>')
        parts.append('</ul>')
    parts.append('</section>')
    return ''.join(parts)


def _chapter_body(chapter, recap, pairs, items, language, index, include_meanings):
    parts = [f'<section class="chapter" id="chapter-{index:04d}"><h1>{_e(chapter["title"])}</h1>']
    if index == 1:
        parts.append(f'<p class="export-notice">{_e(_LIMITATION)}</p>')
    notes = []
    for pair_index, (plan, chunk) in enumerate(pairs, 1):
        # The context renderer is the single source of truth for source slicing.
        try:
            fragment = render_chunk(plan['units'], {**chunk, 'language': language}, 'context')
        except (LearningError, KeyError, TypeError) as error:
            raise LearningError('invalid_export_coverage', 'invalid_source_span') from error
        if include_meanings:
            by_occurrence = {f'{edit["unit_id"]}-{edit_index}': edit
                             for edit_index, edit in enumerate(chunk['edits'])}
            def note_link(match):
                occurrence = re.search(r'data-occurrence-id="([^"]+)"', match.group(0)).group(1)
                edit = by_occurrence[html.unescape(occurrence)]
                suffix = f'{index:04d}-{pair_index:04d}-{len(notes) + 1:06d}'
                note_id, ref_id = 'note-' + suffix, 'ref-' + suffix
                notes.append(f'<aside epub:type="footnote" role="doc-footnote" id="{note_id}"><p>'
                             f'{_foreign(edit["replacement"], language)} — '
                             f'<span lang="he" dir="rtl">{_e(edit["gloss_he"])}</span> '
                             f'<a class="learning-backlink" href="#{ref_id}" aria-label="חזרה למילה">↩</a>'
                             '</p></aside>')
                return (f'<a epub:type="noteref" role="doc-noteref" class="learning-noteref" '
                        f'href="#{note_id}" id="{ref_id}">{match.group(0)}</a>')
            fragment = re.sub(r'<bdi\b[^>]*>.*?</bdi>', note_link, fragment, flags=re.DOTALL)
        parts.append(fragment.replace('\r', '&#13;'))
    parts.append(_recap(recap, pairs, items, language))
    if notes:
        parts.append('<section class="learning-notes" aria-label="פירושי מילים"><h2>פירושי מילים</h2>' +
                     ''.join(notes) + '</section>')
    parts.append('</section>')
    return ''.join(parts)


def _document(title, body, *, standalone=False):
    head = '<style>' + _CSS + '</style>' if standalone else '<link rel="stylesheet" href="learning.css"/>'
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="{_XHTML}" xmlns:epub="{_EPUB}" lang="he" xml:lang="he" dir="rtl">'
            f'<head><meta charset="utf-8"/><title>{_e(title)}</title>{head}</head>'
            f'<body>{body}</body></html>').encode('utf-8')


def _epub(source, session, bodies):
    identifier = 'urn:sha256:' + fingerprint({'source_hash': source['source_hash'],
                                            'prepared_hash': session['prepared_hash'],
                                            'language': session['language'],
                                            'export_content_hash': fingerprint(bodies)})
    links = ''.join(f'<li><a href="chapter-{index:04d}.xhtml">{_e(chapter["title"])}</a></li>'
                    for index, chapter in enumerate(source['chapters'], 1))
    nav = _document(source['title'], f'<h1>{_e(source["title"])}</h1><p class="export-notice">'
                    f'{_e(_LIMITATION)}</p><nav epub:type="toc" id="toc"><h2>תוכן עניינים</h2><ol>{links}</ol></nav>')
    manifest = ''.join(f'<item id="chapter-{index:04d}" href="chapter-{index:04d}.xhtml" '
                       'media-type="application/xhtml+xml"/>' for index in range(1, len(bodies) + 1))
    spine = ''.join(f'<itemref idref="chapter-{index:04d}"/>' for index in range(1, len(bodies) + 1))
    opf = (f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
           f'version="3.0" unique-identifier="book-id" xml:lang="he"><metadata '
           f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">{identifier}</dc:identifier>'
           f'<dc:title>{_e(source["title"])}</dc:title><dc:language>he</dc:language>'
           f'<dc:language>{session["language"]}</dc:language><meta property="dcterms:modified">{_MODIFIED}</meta>'
           '</metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
           'properties="nav"/><item id="css" href="learning.css" media-type="text/css"/>' + manifest +
           '</manifest><spine page-progression-direction="rtl">' + spine + '</spine></package>').encode('utf-8')
    container = (b'<?xml version="1.0" encoding="utf-8"?><container version="1.0" '
                 b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 b'<rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>'
                 b'</rootfiles></container>')
    entries = [('mimetype', b'application/epub+zip'), ('META-INF/container.xml', container),
               ('EPUB/package.opf', opf), ('EPUB/nav.xhtml', nav), ('EPUB/learning.css', _CSS.encode('utf-8'))]
    entries.extend((f'EPUB/chapter-{index:04d}.xhtml', _document(chapter['title'], body))
                   for index, (chapter, body) in enumerate(zip(source['chapters'], bodies), 1))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.create_system = 0
            info.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()


def export_learning_book(source, plans, prepared, session, catalog, *, format='epub', include_meanings=True):
    """Return EPUB3 or standalone HTML bytes, or a specific LearningError.

    ``catalog`` is the pinned effective catalog including accepted definitions.
    ``plans`` and ``prepared`` must describe every source unit exactly once.
    EPUB modified/ZIP timestamps use a fixed build epoch for reproducible bytes.
    """
    require(isinstance(format, str) and format in ('epub', 'html'), 'invalid_export_format')
    require(type(include_meanings) is bool, 'invalid_export_options')
    try:
        grouped, items = _validate(source, plans, prepared, session, catalog)
        bodies = [_chapter_body(chapter, recap, grouped[chapter['chapter_id']], items,
                                session['language'], index, include_meanings)
                  for index, (chapter, recap) in enumerate(zip(source['chapters'], prepared['recaps']), 1)]
    except LearningError:
        raise
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
        raise LearningError('invalid_export_coverage', 'invalid_record') from error
    if format == 'epub':
        return _epub(source, session, bodies)
    links = ''.join(f'<li><a href="#chapter-{index:04d}">{_e(chapter["title"])}</a></li>'
                    for index, chapter in enumerate(source['chapters'], 1))
    return _document(source['title'], f'<h1>{_e(source["title"])}</h1><nav epub:type="toc"><h2>תוכן עניינים</h2>'
                     f'<ol>{links}</ol></nav>' + ''.join(bodies), standalone=True)
