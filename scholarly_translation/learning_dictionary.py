"""Learner's-dictionary entries for lexical items, and their read-only views.

Entries arrive inside the normal chunk generation response (no extra call) for
preparations started with dictionary entries. They are supplementary: an entry
that does not validate is dropped and never rejects the chunk. Book examples
are derived locally from accepted edits; the model never supplies them.
"""
from __future__ import annotations

from pathlib import Path
import unicodedata

from .learning_contracts import LearningError, check_id, require

DICTIONARY_VERSION = 'learning-dictionary@1'
PARTS_OF_SPEECH = ('noun', 'verb', 'adjective', 'adverb', 'pronoun', 'preposition', 'conjunction',
                   'determiner', 'numeral', 'interjection', 'phrase', 'other')
GENDERS = ('masculine', 'feminine', 'neuter', 'common')
_ENTRY_FIELDS = {'item_id', 'part_of_speech', 'gender', 'senses_he', 'forms', 'notes_he'}
_PROMPT_ASSET = Path(__file__).resolve().parent.parent / 'runtime_prompts' / '12_learning_dictionary_entries.md'
_MAX_EXAMPLES = 3


def instructions():
    text = _PROMPT_ASSET.read_text(encoding='utf-8')
    marker = '## Instructions (appended after the generation instructions)'
    return text[text.index(marker) + len(marker):].strip()


def _clean(value, limit, *, empty=False):
    require(isinstance(value, str) and len(value) <= limit, 'invalid_dictionary_entry')
    value = ' '.join(unicodedata.normalize('NFC', value).split())
    require(empty or bool(value), 'invalid_dictionary_entry')
    return value


def _hebrew(text):
    return any('א' <= char <= 'ת' for char in text)


def _foreign_form(text, language):
    letters = [char for char in text if char.isalpha()]
    script = 'HEBREW' if language == 'yi' else 'LATIN'
    return bool(letters) and all(script in unicodedata.name(char, '') for char in letters) \
        and not any(char in '<>&' for char in text)


def dictionary_entry(raw, language):
    """Normalized entry without item_id, or LearningError('invalid_dictionary_entry')."""
    require(isinstance(raw, dict) and set(raw) == _ENTRY_FIELDS, 'invalid_dictionary_entry')
    require(raw['part_of_speech'] in PARTS_OF_SPEECH, 'invalid_dictionary_entry')
    require(raw['gender'] is None or raw['gender'] in GENDERS, 'invalid_dictionary_entry')
    senses = raw['senses_he']
    require(isinstance(senses, list) and 1 <= len(senses) <= 4, 'invalid_dictionary_entry')
    senses = [_clean(sense, 200) for sense in senses]
    require(all(_hebrew(sense) for sense in senses), 'invalid_dictionary_entry')
    forms = raw['forms']
    require(isinstance(forms, list) and len(forms) <= 16, 'invalid_dictionary_entry')
    clean_forms = []
    for row in forms:
        require(isinstance(row, dict) and set(row) == {'label_he', 'form'}, 'invalid_dictionary_entry')
        label, form = _clean(row['label_he'], 60), _clean(row['form'], 100)
        require(_hebrew(label) and _foreign_form(form, language), 'invalid_dictionary_entry')
        clean_forms.append({'label_he': label, 'form': form})
    return {'part_of_speech': raw['part_of_speech'], 'gender': raw['gender'], 'senses_he': senses,
            'forms': clean_forms, 'notes_he': _clean(raw['notes_he'], 400, empty=True)}


def parse_entries(raw_entries, *, language, aliases, eligible_ids):
    """Entries for eligible lexical ids (first one wins); invalid rows are dropped."""
    if raw_entries is None:
        return []
    require(isinstance(raw_entries, list), 'invalid_generation', 'dictionary_entries')
    result, seen = [], set()
    for raw in raw_entries:
        if not isinstance(raw, dict) or not isinstance(raw.get('item_id'), str):
            continue
        item_id = aliases.get(raw['item_id'], raw['item_id'])
        if item_id not in eligible_ids or item_id in seen:
            continue
        try:
            entry = dictionary_entry(raw, language)
        except LearningError:
            continue
        seen.add(item_id)
        result.append({'item_id': item_id, **entry})
    return result


def validate_entries(entries, language):
    require(isinstance(entries, list), 'invalid_generation', 'dictionary_entries')
    seen = set()
    for row in entries:
        require(isinstance(row, dict) and set(row) == _ENTRY_FIELDS, 'invalid_generation', 'dictionary_entries')
        check_id(row['item_id'])
        require(row['item_id'] not in seen, 'invalid_generation', 'dictionary_entries')
        seen.add(row['item_id'])
        dictionary_entry(row, language)
    return entries


def woven_sentence(text, start, end, replacement, limit=240):
    """The Hebrew sentence around an edit, with the foreign replacement in place."""
    left = max(text.rfind(mark, 0, start) for mark in '.!?\n') + 1
    rights = [i for i in (text.find(mark, end) for mark in '.!?\n') if i >= 0]
    right = min(rights) + 1 if rights else len(text)
    left, right = max(left, start - limit // 2), min(right, end + limit // 2)
    return (text[left:start] + replacement + text[end:right]).strip()


def dictionary_view(sources):
    """Entries (first wins) and up to three book examples per item.

    ``sources`` is an ordered list of (book_title, plans, chunks, chapter_ids or
    None for every chapter). Pure; reads only accepted data.
    """
    entries, examples = {}, {}
    for title, plans, chunks, chapters in sources:
        for plan, chunk in zip(plans, chunks):
            for row in chunk.get('dictionary_entries', []):
                entries.setdefault(row['item_id'], {k: v for k, v in row.items() if k != 'item_id'})
            if chapters is not None and plan['chapter_id'] not in chapters:
                continue
            units = {unit['unit_id']: unit['text'] for unit in plan['units']}
            for edit in chunk['edits']:
                for item_id in edit['item_ids']:
                    bucket = examples.setdefault(item_id, [])
                    if len(bucket) < _MAX_EXAMPLES and edit['unit_id'] in units:
                        sentence = woven_sentence(units[edit['unit_id']], edit['start'], edit['end'],
                                                  edit['replacement'])
                        if all(sentence != row['sentence'] for row in bucket):
                            bucket.append({'foreign': edit['replacement'], 'sentence': sentence,
                                           'book_title': title})
    return entries, examples
