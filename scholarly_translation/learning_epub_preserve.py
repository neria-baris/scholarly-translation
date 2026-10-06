"""Apply accepted learning edits to a retained EPUB without flattening its DOM.

Only text/tail slots covered by accepted source spans change. Original inline
elements, links, media and every non-chapter ZIP member are retained. A mapping
that cannot be proved complete and unique fails explicitly.
"""
from __future__ import annotations

from copy import copy
import hashlib
import io
import posixpath
import re
import zipfile
from urllib.parse import quote
from xml.etree import ElementTree as ET

from .epub_archive import (
    BLOCK_TAGS, EpubArchiveError, block_text, local_tag, open_validated_archive,
    parse_xml, resolve_package, resolve_reading_order,
)
from . import epub_archive
from .learning_contracts import LearningError, require
from .learning_export import _recap, _validate
from .learning_import import _split_paragraph
from .learning_render import render_chunk

_XHTML = 'http://www.w3.org/1999/xhtml'
_EPUB = 'http://www.idpf.org/2007/ops'
_IMPORT_ID = re.compile(r'p([1-9]\d*)-s([1-9]\d*)(?:-c([1-9]\d*))?\Z')
_FOREIGN_STYLE = ('color:#526d85;text-decoration:underline dotted;'
                  'text-underline-offset:.16em;unicode-bidi:isolate;')


def _mapping(condition, message):
    require(condition, 'preservation_unavailable', message)


def _tag(element):
    return local_tag(element.tag) if isinstance(element.tag, str) else ''


def _slots(element):
    """Text slots in itertext order, excluding comments/PI but retaining tails."""
    result = []
    def visit(node):
        if isinstance(node.tag, str):
            if node.text:
                result.append((node, 'text', node.text))
            for child in node:
                if _tag(child) == 'math' and hasattr(epub_archive, 'math_text'):
                    # The main extractor represents MathML as a protected
                    # logical slot. Its coordinates participate in matching,
                    # while the original XML formula remains untouched.
                    result.append((child, 'protected', epub_archive.MATH_OPEN +
                                   epub_archive.math_text(child) + epub_archive.MATH_CLOSE))
                else:
                    visit(child)
                if child.tail:
                    result.append((child, 'tail', child.tail))
    visit(element)
    return result


def _documents(archive, paths):
    documents, blocks = {}, []
    for page, path in enumerate(paths, 1):
        raw = archive.read(path)
        if not raw.strip():
            continue
        validated = parse_xml(raw)
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(raw, parser=parser)
        original_nodes = [node for node in root.iter() if isinstance(node.tag, str)]
        checked_nodes = list(validated.iter())
        _mapping(len(original_nodes) == len(checked_nodes), 'xml_node_mapping')
        shadow = dict(zip(original_nodes, checked_nodes))
        parents = {child: parent for parent in root.iter() for child in parent}
        body = next((node for node in root.iter() if _tag(node) == 'body'), root)
        documents[path] = {'root': root, 'parents': parents, 'raw': raw, 'changed': False}
        order = 0
        for node in body.iter():
            if _tag(node) not in BLOCK_TAGS:
                continue
            text = block_text(shadow[node])
            if not text:
                continue
            order += 1
            slots = _slots(node)
            full_text = ''.join(value for _, _, value in slots)
            # Match the exact producer coordinates, including protected math.
            _mapping(full_text.strip() == text, 'protected_or_nonliteral_text')
            blocks.append({'key': (page, order), 'path': path, 'element': node,
                           'text': text, 'slots': slots, 'full_text': full_text,
                           'leading': len(full_text) - len(full_text.lstrip())})
    _mapping(bool(blocks), 'no_reading_blocks')
    return documents, blocks


def _normalized_coordinates(block):
    """Map each normalized character to its original half-open text interval."""
    text, leading = block['text'], block['leading']
    characters, intervals = [], []
    previous_end = None
    for match in re.finditer(r'\S+', text):
        if previous_end is not None:
            characters.append(' ')
            intervals.append((leading + previous_end, leading + match.start()))
        for index in range(match.start(), match.end()):
            characters.append(text[index])
            intervals.append((leading + index, leading + index + 1))
        previous_end = match.end()
    return ''.join(characters), intervals


def _block_parts(block, *, heading=False):
    parts = [block['text']] if heading else _split_paragraph(block['text'])
    if len(parts) == 1 and parts[0] == block['text']:
        intervals = [(block['leading'] + index, block['leading'] + index + 1)
                     for index in range(len(block['text']))]
    else:
        normalized, intervals = _normalized_coordinates(block)
        _mapping(' '.join(parts) == normalized, 'normalized_paragraph_mapping')
    result, offset = [], 0
    for part in parts:
        result.append((part, intervals[offset:offset + len(part)]))
        offset += len(part) + 1
    return result


def _import_mapping(units, blocks):
    by_key = {block['key']: block for block in blocks}
    grouped, ordered_keys = {}, []
    for unit in units:
        match = _IMPORT_ID.fullmatch(unit['unit_id'])
        _mapping(match is not None, 'import_unit_id')
        key = (int(match[1]), int(match[2]))
        suffix = int(match[3] or 0)
        _mapping(key in by_key, 'missing_import_block')
        if not ordered_keys or ordered_keys[-1] != key:
            ordered_keys.append(key)
        grouped.setdefault(key, []).append((suffix, unit))
    _mapping(ordered_keys == [block['key'] for block in blocks], 'import_block_order')
    result = {}
    for key, rows in grouped.items():
        block = by_key[key]
        heading = _tag(block['element']) in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
        parts = _block_parts(block, heading=heading)
        _mapping([suffix for suffix, _ in rows] == list(range(len(parts))), 'split_unit_order')
        for (_, unit), (text, intervals) in zip(rows, parts):
            _mapping(unit['text'] == text and unit['kind'] == ('heading' if heading else 'paragraph'),
                     'import_text_mismatch')
            result[unit['unit_id']] = (block, intervals)
    return result


def _translation_mapping(units, blocks):
    """Unique sequential match of whole target blocks, with no fuzzy matching.

    Original front matter/media blocks can remain outside the learning source.
    Multiple possible alignments, even when text is repeated, are rejected.
    """
    candidates = [_block_parts(block) for block in blocks]
    texts = [unit['text'] for unit in units]
    flat = [text for parts in candidates for text, _ in parts]
    if flat == texts:
        selected, offset = [], 0
        for block_index, parts in enumerate(candidates):
            selected.append((block_index, offset, len(parts)))
            offset += len(parts)
    else:
        # State count is capped at two: only uniqueness matters. Paths are
        # linked records so matching long books does not copy whole histories.
        states = {0: (1, None)}
        for block_index, parts in enumerate(candidates):
            next_states = dict(states)
            expected = [text for text, _ in parts]
            for offset, (count, path) in states.items():
                end = offset + len(expected)
                if end > len(texts) or texts[offset:end] != expected:
                    continue
                candidate_path = (path, (block_index, offset, len(parts)))
                if end in next_states:
                    old_count, old_path = next_states[end]
                    next_states[end] = (min(2, old_count + count), old_path)
                else:
                    next_states[end] = (count, candidate_path)
            states = next_states
        _mapping(len(texts) in states and states[len(texts)][0] == 1, 'ambiguous_translation_mapping')
        selected, path = [], states[len(texts)][1]
        while path is not None:
            path, entry = path
            selected.append(entry)
        selected.reverse()
    result = {}
    for block_index, offset, count in selected:
        block, parts = blocks[block_index], candidates[block_index]
        for unit, (text, intervals) in zip(units[offset:offset + count], parts):
            _mapping(unit['text'] == text, 'translation_text_mismatch')
            result[unit['unit_id']] = (block, intervals)
    _mapping(len(result) == len(units), 'translation_unit_coverage')
    return result


def _foreign(text, language):
    direction = 'rtl' if language == 'yi' else 'ltr'
    element = ET.Element('{' + _XHTML + '}bdi', {'lang': language, 'dir': direction,
                         'class': 'learning-foreign', 'style': _FOREIGN_STYLE + 'direction:' + direction})
    element.text = text
    return element


def _new_id(prefix, identifiers):
    index = 1
    candidate = prefix
    while candidate in identifiers:
        index += 1
        candidate = prefix + '-' + str(index)
    identifiers.add(candidate)
    return candidate


def _insert_slot(owner, attribute, start, end, replacement, parents):
    current = getattr(owner, attribute) or ''
    _mapping(0 <= start <= end <= len(current), 'slot_span')
    prefix, suffix = current[:start], current[end:]
    setattr(owner, attribute, prefix)
    replacement.tail = suffix
    if attribute == 'text':
        owner.insert(0, replacement)
        parents[replacement] = owner
    else:
        _mapping(owner in parents, 'tail_parent')
        parent = parents[owner]
        parent.insert(list(parent).index(owner) + 1, replacement)
        parents[replacement] = parent


def _link_ancestor(owner, attribute, parents):
    node = owner if attribute == 'text' else parents.get(owner)
    while node is not None:
        if _tag(node) == 'a':
            return node
        node = parents.get(node)
    return None


def _apply_edit(block, start, end, element, parents):
    _mapping(0 <= start < end <= len(block['full_text']), 'block_edit_span')
    offset, spans = 0, []
    for owner, attribute, original in block['slots']:
        slot_end = offset + len(original)
        if offset < end and start < slot_end:
            spans.append((owner, attribute, max(start, offset) - offset, min(end, slot_end) - offset))
        offset = slot_end
    _mapping(bool(spans), 'missing_edit_slots')
    _mapping(all(attribute != 'protected' for _, attribute, _, _ in spans), 'edit_crosses_protected_formula')
    first_owner, first_attribute, first_start, first_end = spans[0]
    link = _link_ancestor(first_owner, first_attribute, parents)
    for owner, attribute, local_start, local_end in reversed(spans[1:]):
        current = getattr(owner, attribute) or ''
        _mapping(local_end <= len(current), 'covered_slot_span')
        setattr(owner, attribute, current[:local_start] + current[local_end:])
    _insert_slot(first_owner, first_attribute, first_start, first_end, element, parents)
    return link


def _fragment_link(from_path, to_path, fragment):
    prefix = '' if from_path == to_path else quote(
        posixpath.relpath(to_path, posixpath.dirname(from_path)), safe='/')
    return prefix + '#' + fragment


def _note(edit, language, note_id, back_href):
    note = ET.Element('{' + _XHTML + '}aside', {'{' + _EPUB + '}type': 'footnote',
                     'role': 'doc-footnote', 'id': note_id, 'dir': 'rtl'})
    paragraph = ET.SubElement(note, '{' + _XHTML + '}p', {'style': 'white-space:pre-wrap'})
    label = _foreign(edit['replacement'], language)
    paragraph.append(label)
    label.tail = ' — ' + edit['gloss_he'] + ' '
    backlink = ET.SubElement(paragraph, '{' + _XHTML + '}a', {'href': back_href,
                            'aria-label': 'חזרה למילה'})
    backlink.text = '↩'
    return note


def _recap_elements(recap, pairs, items, language, notes):
    raw = (f'<div xmlns="{_XHTML}" xmlns:epub="{_EPUB}">' +
           _recap(recap, pairs, items, language) + '</div>')
    wrapper = ET.fromstring(raw)
    section = wrapper[0]
    section.set('dir', 'rtl')
    section.set('style', 'direction:rtl;margin-top:2em;border-top:1px solid #aaa')
    for element in section.iter():
        if _tag(element) in ('p', 'li', 'h2', 'h3'):
            element.set('style', 'white-space:pre-wrap;overflow-wrap:anywhere')
        elif _tag(element) == 'bdi':
            element.set('style', _FOREIGN_STYLE + 'direction:' + element.get('dir', 'ltr'))
    if notes:
        note_section = ET.Element('{' + _XHTML + '}section', {'class': 'learning-notes', 'dir': 'rtl',
                                 'aria-label': 'פירושי מילים'})
        ET.SubElement(note_section, '{' + _XHTML + '}h2').text = 'פירושי מילים'
        note_section.extend(notes)
        return [section, note_section]
    return [section]


def _safe_recap_anchor(element, parents):
    restricted = {'ul', 'ol', 'dl', 'table', 'tbody', 'thead', 'tfoot', 'tr', 'select'}
    anchor = element
    while anchor in parents and _tag(parents[anchor]) in restricted:
        anchor = parents[anchor]
    _mapping(anchor in parents, 'recap_parent')
    return anchor


def _build(raw, source, plans, prepared, session, catalog, include_meanings):
    grouped, items = _validate(source, plans, prepared, session, catalog)
    for plan, chunk in zip(plans, prepared['chunks']):
        # Reuse the same exact source span validator as online/text export.
        try:
            render_chunk(plan['units'], {**chunk, 'language': session['language']}, 'context')
        except LearningError as error:
            raise LearningError('invalid_export_coverage', 'invalid_source_span') from error
    if source['origin']['kind'] == 'hebrew_epub':
        require(hashlib.sha256(raw).hexdigest() == source['origin']['original_hash'],
                'invalid_preserved_epub', 'original_hash_mismatch')
    with open_validated_archive(io.BytesIO(raw)) as archive:
        require(archive.read('mimetype') == b'application/epub+zip', 'invalid_preserved_epub', 'mimetype')
        _, package, base = resolve_package(archive)
        paths, _ = resolve_reading_order(archive, package, base)
        _mapping(len(paths) == len(set(paths)), 'duplicate_spine_path')
        documents, blocks = _documents(archive, paths)
        units = [unit for chapter in source['chapters'] for unit in chapter['units']]
        unit_mapping = (_import_mapping(units, blocks) if source['origin']['kind'] == 'hebrew_epub'
                        else _translation_mapping(units, blocks))
        block_chapter = {}
        for chapter_index, chapter in enumerate(source['chapters']):
            for unit in chapter['units']:
                block, _ = unit_mapping[unit['unit_id']]
                key = block['key']
                _mapping(key not in block_chapter or block_chapter[key] == chapter_index, 'chapter_splits_block')
                block_chapter[key] = chapter_index
        mapped_elements = {unit_mapping[unit['unit_id']][0]['element'] for unit in units}
        element_blocks = {block['element']: block for block in blocks}
        for element in mapped_elements:
            parents = documents[element_blocks[element]['path']]['parents']
            parent = parents.get(element)
            while parent is not None:
                _mapping(parent not in mapped_elements, 'overlapping_nested_blocks')
                parent = parents.get(parent)
        identifiers = {element.get('id') for doc in documents.values() for element in doc['root'].iter()
                       if element.get('id')}
        edits_by_block, chapter_notes = {}, {index: [] for index in range(len(source['chapters']))}
        ref_prefix = 'learning-' + session['prepared_hash'][:16]
        for chapter_index, chapter in enumerate(source['chapters']):
            pairs = grouped[chapter['chapter_id']]
            notes_path = unit_mapping[chapter['units'][-1]['unit_id']][0]['path']
            for _, chunk in pairs:
                for edit in chunk['edits']:
                    block, intervals = unit_mapping[edit['unit_id']]
                    _mapping(edit['end'] <= len(intervals), 'unit_coordinate_span')
                    start, end = intervals[edit['start']][0], intervals[edit['end'] - 1][1]
                    foreign = _foreign(edit['replacement'], session['language'])
                    reference = None
                    if include_meanings:
                        count = len(chapter_notes[chapter_index]) + 1
                        suffix = f'{chapter_index + 1}-{count}'
                        note_id = _new_id(ref_prefix + '-note-' + suffix, identifiers)
                        ref_id = _new_id(ref_prefix + '-ref-' + suffix, identifiers)
                        reference = ET.Element('{' + _XHTML + '}a', {'{' + _EPUB + '}type': 'noteref',
                                               'role': 'doc-noteref',
                                               'href': _fragment_link(block['path'], notes_path, note_id), 'id': ref_id,
                                               'style': 'color:inherit;text-decoration:none'})
                        reference.append(foreign)
                        chapter_notes[chapter_index].append(_note(edit, session['language'], note_id,
                            _fragment_link(notes_path, block['path'], ref_id)))
                    edits_by_block.setdefault(block['key'], []).append((start, end, foreign, reference))
        for block in blocks:
            edits = edits_by_block.get(block['key'], [])
            ascending = sorted(edits, key=lambda row: row[0])
            _mapping(all(first[1] <= second[0] for first, second in zip(ascending, ascending[1:])),
                     'overlapping_mapped_edits')
            doc = documents[block['path']]
            for start, end, foreign, reference in reversed(ascending):
                # Existing links retain their targets; never nest a new <a>.
                offset = 0
                first_link = None
                for owner, attribute, original in block['slots']:
                    if offset <= start < offset + len(original):
                        first_link = _link_ancestor(owner, attribute, doc['parents'])
                        break
                    offset += len(original)
                element = reference if reference is not None and first_link is None else foreign
                _apply_edit(block, start, end, element, doc['parents'])
                if reference is not None and first_link is not None:
                    reference.remove(foreign)
                    reference.text = '†'
                    reference.set('aria-label', 'הצג פירוש למילה')
                    parent = doc['parents'].get(first_link)
                    _mapping(parent is not None, 'original_link_parent')
                    reference.tail, first_link.tail = first_link.tail, None
                    parent.insert(list(parent).index(first_link) + 1, reference)
                    doc['parents'][reference] = parent
                doc['changed'] = True
        for chapter_index, (chapter, recap) in enumerate(zip(source['chapters'], prepared['recaps'])):
            block, _ = unit_mapping[chapter['units'][-1]['unit_id']]
            doc = documents[block['path']]
            anchor = _safe_recap_anchor(block['element'], doc['parents'])
            descendants = set(anchor.iter())
            _mapping(all(block_chapter.get(candidate['key'], chapter_index) <= chapter_index
                         for candidate in blocks if candidate['element'] in descendants), 'recap_crosses_chapter')
            parent = doc['parents'][anchor]
            index = list(parent).index(anchor) + 1
            sections = _recap_elements(recap, grouped[chapter['chapter_id']], items, session['language'],
                                       chapter_notes[chapter_index])
            for offset, section in enumerate(sections):
                parent.insert(index + offset, section)
            # The old tail belongs after the inserted recap, not inside it.
            sections[-1].tail, anchor.tail = anchor.tail, None
            doc['changed'] = True
        changes = {path: ET.tostring(doc['root'], encoding='utf-8', xml_declaration=True)
                   for path, doc in documents.items() if doc['changed']}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as target:
            target.comment = archive.comment
            entries = sorted(archive.infolist(), key=lambda item: item.filename != 'mimetype')
            for original in entries:
                item = copy(original)
                if item.filename == 'mimetype':
                    item.compress_type = zipfile.ZIP_STORED
                target.writestr(item, changes.get(item.filename, archive.read(item.filename)))
        return output.getvalue()


def build_preserved_epub(raw, source, plans, prepared, session, catalog, *, include_meanings=True):
    """Return an EPUB retaining original assets, or an explicit mapping error.

    Original stylesheet/layout remains in charge. New learning spans have only
    scoped inline styling; existing CSS, fonts, media, scripts, nav and package
    content are copied unchanged. The caller decides whether to offer fallback.
    """
    require(isinstance(raw, bytes) and bool(raw), 'invalid_preserved_epub')
    require(type(include_meanings) is bool, 'invalid_export_options')
    try:
        return _build(raw, source, plans, prepared, session, catalog, include_meanings)
    except LearningError:
        raise
    except (EpubArchiveError, zipfile.BadZipFile, ET.ParseError, KeyError, OSError) as error:
        raise LearningError('invalid_preserved_epub', 'archive_or_xml_invalid') from error
    except (IndexError, TypeError, ValueError, AttributeError) as error:
        raise LearningError('preservation_unavailable', 'mapping_invalid') from error
