"""Local personal dictionary and immutable chapter grammar archive.

No completion or mastery decisions are made here. JSON retains all received
explanations/examples; Markdown is a human-readable companion. A failed write
is explicit even if an earlier atomic file write succeeded, so callers can
warn the reader and retry without losing a previously received explanation.
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from pathlib import Path
from urllib.parse import quote

from .learning_contracts import LearningError, SUPPORTED_LANGUAGE_CODES, check_id, require

_ARCHIVE_LOCK = threading.RLock()


def _safe_path(root, *parts):
    path = root.joinpath(*parts).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise LearningError('archive_save_failed', 'Personal archive path leaves its root') from exc
    return path


def _filename_id(value):
    check_id(value)
    result = quote(value, safe='-_.@')
    # These device names remain reserved on Windows, including with extensions.
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', result, re.I):
        result = '%' + format(ord(result[0]), '02X') + result[1:]
    return result


def _atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'


def _rows(rows):
    require(isinstance(rows, list), 'invalid_archive')
    result = []
    for row in rows:
        require(isinstance(row, dict), 'invalid_archive')
        item_id = check_id(row.get('item_id'))
        require(row.get('kind') in ('word', 'phrase', 'grammar'), 'invalid_archive')
        for field in ('foreign', 'hebrew'):
            require(isinstance(row.get(field), str), 'invalid_archive')
        require(type(row.get('encounters')) is int and row['encounters'] >= 0, 'invalid_archive')
        title = row.get('last_book_title')
        require(title is None or isinstance(title, str), 'invalid_archive')
        result.append({'item_id': item_id, 'kind': row['kind'], 'foreign': row['foreign'],
                       'hebrew': row['hebrew'], 'encounters': row['encounters'],
                       'last_book_title': title})
    require(len({row['item_id'] for row in result}) == len(result), 'invalid_archive')
    return sorted(result, key=lambda row: row['item_id'])


def _dictionary(language, progress):
    require(isinstance(progress, dict), 'invalid_archive')
    active = progress.get('active_book')
    require(active is None or isinstance(active, dict), 'invalid_archive')
    return {'schema_version': 1, 'language': language,
            'saved_items': _rows(progress.get('completed_items', [])),
            'current_items': _rows(active.get('read_items', []) if active else []),
            'current_book_title': active.get('title') if active else None,
            'status_note_he': 'היתקלויות שנשמרו לאחר סימון קראתי, לצד היתקלויות בספר הנוכחי שטרם נשמרו. אין כאן קביעה של שליטה במילים.'}


def _dictionary_md(record):
    lines = ['# המילון האישי', '', record['status_note_he'], '', f"שפה: {record['language']}", '']
    for title, key in [('נשמר לאחר קראתי', 'saved_items'), ('בספר הנוכחי — טרם נשמר', 'current_items')]:
        lines.extend([f'## {title}', ''])
        if not record[key]:
            lines.extend(['אין עדיין פריטים.', ''])
        for row in record[key]:
            lines.extend([f"- {row['foreign']} — {row['hebrew']}",
                          f"  מזהה: {row['item_id']}; סוג: {row['kind']}; היתקלויות: {row['encounters']}",
                          f"  ספר: {row['last_book_title'] or record['current_book_title'] or 'לא צוין'}", ''])
    return '\n'.join(lines) + '\n'


def _chapter_record(language, chapter):
    require(isinstance(chapter, dict), 'invalid_archive')
    identity = {key: check_id(chapter.get(key)) for key in ('session_id', 'book_id', 'chapter_id')}
    require(isinstance(chapter.get('chapter_title'), str), 'invalid_archive')
    recap = chapter.get('recap')
    require(isinstance(recap, dict), 'invalid_archive')
    require(recap.get('chapter_id', identity['chapter_id']) == identity['chapter_id'], 'invalid_archive')
    require(isinstance(recap.get('grammar', []), list) and isinstance(recap.get('vocabulary', []), list), 'invalid_archive')
    items = chapter.get('items', {})
    require(isinstance(items, dict), 'invalid_archive')
    for row in recap.get('grammar', []):
        require(isinstance(row, dict), 'invalid_archive')
        check_id(row.get('item_id'))
        require(isinstance(row.get('explanation_he'), str) and isinstance(row.get('examples', []), list), 'invalid_archive')
        for example in row.get('examples', []):
            require(isinstance(example, dict), 'invalid_archive')
    # Whitelist recap fields and definitions: never persist arbitrary source or
    # caller context (which could include a complete book or credentials).
    definitions = {}
    used = {row['item_id'] for row in recap.get('grammar', [])}
    for row in recap.get('vocabulary', []):
        require(isinstance(row, dict), 'invalid_archive')
        used.add(check_id(row.get('item_id')))
    for item_id in sorted(used):
        item = items.get(item_id, {})
        require(isinstance(item, dict), 'invalid_archive')
        require(all(isinstance(item[key], str) for key in ('lemma', 'sense_he') if key in item), 'invalid_archive')
        definitions[item_id] = {key: item[key] for key in ('lemma', 'sense_he') if key in item}
    return {'schema_version': 1, 'language': language, **identity,
            'chapter_title': chapter['chapter_title'], 'items': definitions,
            'recap': copy.deepcopy({key: recap[key] for key in
                                   ('schema_version', 'chapter_id', 'chunk_hashes', 'grammar', 'vocabulary', 'warnings')
                                   if key in recap}),
            'status_note_he': 'הסברים שהתקבלו בעת קריאת הפרק. שמירתם אינה סימון הספר כנקרא ואינה אישור לשוני.'}


def _chapter_md(record):
    lines = [f"# {record['chapter_title']}", '', record['status_note_he'], '',
             f"שפה: {record['language']}", f"ספר: {record['book_id']}",
             f"קריאה: {record['session_id']}", f"פרק: {record['chapter_id']}", '', '## הסברי דקדוק', '']
    for row in record['recap'].get('grammar', []):
        definition = record['items'].get(row['item_id'], {})
        lines.extend([f"### {definition.get('lemma') or row['item_id']}", '', row['explanation_he'], ''])
        for example in row.get('examples', []):
            foreign = example.get('foreign', example.get('replacement'))
            hebrew = example.get('hebrew', example.get('original'))
            if foreign is not None or hebrew is not None:
                lines.extend([f"- בשפה הנלמדת: {foreign or ''}", f"  בעברית: {hebrew or ''}"])
            # Preserve every metadata field in the readable companion too.
            lines.extend(['  פרטי הדוגמה: ' + json.dumps(example, ensure_ascii=False, sort_keys=True), ''])
    if not record['recap'].get('grammar'):
        lines.extend(['לא התקבל הסבר דקדוק חדש בפרק זה.', ''])
    lines.extend(['## מילים בסיכום הפרק', ''])
    for row in record['recap'].get('vocabulary', []):
        definition = record['items'].get(row['item_id'], {})
        lines.extend([f"- {definition.get('lemma') or row['item_id']} — {row.get('gloss_he', definition.get('sense_he', ''))}", ''])
    return '\n'.join(lines) + '\n'


def _save_personal_archive(root, language, progress, chapter=None):
    """Save a dictionary snapshot and, if given, one immutable received recap.

    Return only after all files succeeded. An altered recap for the same source
    identity raises ``archive_save_failed`` rather than replacing old evidence.
    Existing identical files are reused; a missing companion is repaired.
    """
    require(language in SUPPORTED_LANGUAGE_CODES, 'unsupported_language')
    record = _dictionary(language, progress)
    chapter_record = _chapter_record(language, chapter) if chapter is not None else None
    try:
        root = Path(root).resolve()
        directory = _safe_path(root, 'personal', language)
        dictionary_json = _safe_path(root, 'personal', language, 'dictionary.json')
        dictionary_md = _safe_path(root, 'personal', language, 'dictionary.md')
        grammar_paths = None
        reused = False
        if chapter_record is not None:
            basename = f"{_filename_id(chapter_record['session_id'])}--{_filename_id(chapter_record['chapter_id'])}"
            grammar_json = _safe_path(root, 'personal', language, 'grammar', basename + '.json')
            grammar_md = _safe_path(root, 'personal', language, 'grammar', basename + '.md')
            grammar_text = _chapter_md(chapter_record)
            if grammar_json.exists():
                require(json.loads(grammar_json.read_text(encoding='utf-8')) == chapter_record,
                        'archive_save_failed', 'Stored chapter recap differs; original preserved')
                reused = True
            if grammar_md.exists():
                require(grammar_md.read_text(encoding='utf-8') == grammar_text,
                        'archive_save_failed', 'Stored readable chapter recap differs; original preserved')
            if not grammar_json.exists():
                _atomic_text(grammar_json, _json_text(chapter_record))
            if not grammar_md.exists():
                _atomic_text(grammar_md, grammar_text)
            grammar_paths = {'json': str(grammar_json), 'markdown': str(grammar_md)}
        _atomic_text(dictionary_json, _json_text(record))
        _atomic_text(dictionary_md, _dictionary_md(record))
        return {'status': 'saved', 'directory': str(directory),
                'dictionary': {'json': str(dictionary_json), 'markdown': str(dictionary_md)},
                'grammar': grammar_paths, 'chapter_reused': reused}
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, LearningError) and exc.code == 'archive_save_failed':
            raise
        raise LearningError('archive_save_failed', 'Personal learning archive could not be fully saved') from exc


def save_personal_archive(root, language, progress, chapter=None):
    """Atomically save each file and serialize chapter identity checks locally.

    One local learning process owns a root, as for LearningStore. Immutable
    chapter artifacts are checked before any replacement; multi-process shared
    roots are not supported. Errors never grant completion or suppress reading.
    """
    with _ARCHIVE_LOCK:
        return _save_personal_archive(root, language, progress, chapter)
