"""Bounded model proposals and persistent definitions; no model or file I/O."""
from copy import deepcopy
import unicodedata

from .learning_contracts import fingerprint, require, require_fields, validate_catalog

ITEM_FIELDS = ('item_id', 'kind', 'lemma', 'sense_he', 'forms', 'priority_tier',
               'prerequisite_ids', 'explanation_he', 'min_level')
ORIGIN_FIELDS = ('provider', 'model', 'prompt_version', 'input_hash')


def _normalized(value, limit, *, empty=False):
    require(isinstance(value, str) and len(value) <= limit, 'invalid_generation')
    value = unicodedata.normalize('NFC', value).strip()
    require(empty or bool(value), 'invalid_generation')
    return value


def dynamic_id(language, item):
    identity = {key: item[key] for key in ('kind', 'lemma', 'sense_he', 'explanation_he')}
    identity['forms'] = sorted(item['forms'])
    return language + '-learn-' + fingerprint({'language': language, 'definition': identity})[:24]


def proposal_item(raw, language, level, frequency_seed=()):
    require_fields(raw, ('item_id', 'kind', 'lemma', 'sense_he', 'forms', 'explanation_he'),
                   code='invalid_generation')
    require(raw['kind'] in ('word', 'phrase', 'grammar'), 'invalid_generation')
    lemma = _normalized(raw['lemma'], 300)
    sense = _normalized(raw['sense_he'], 300)
    explanation = _normalized(raw['explanation_he'], 1000, empty=raw['kind'] != 'grammar')
    require(any('\u05d0' <= char <= '\u05ea' for char in sense), 'invalid_generation', 'hebrew_sense')
    require(isinstance(raw['forms'], list) and 1 <= len(raw['forms']) <= 12, 'invalid_generation')
    forms = [_normalized(form, 300) for form in raw['forms']]
    require(len(set(forms)) == len(forms), 'invalid_generation', 'duplicate_form')
    for form in [lemma] + forms:
        letters = [char for char in form if char.isalpha()]
        script = 'HEBREW' if language == 'yi' else 'LATIN'
        require(letters and all(script in unicodedata.name(char, '') for char in letters),
                'invalid_generation', 'foreign_script')
        require(not any(char in '<>&' for char in form), 'invalid_generation', 'foreign_markup')
    ranks = [row['rank'] for row in frequency_seed if row['word'] in forms or row['word'] == lemma]
    item = {'item_id': '', 'kind': raw['kind'], 'lemma': lemma, 'sense_he': sense,
            'forms': forms, 'priority_tier': min(ranks) if ranks else 501,
            'prerequisite_ids': [], 'explanation_he': explanation, 'min_level': int(level)}
    item['item_id'] = dynamic_id(language, item)
    return item


def validate_vocabulary(vocabulary, language):
    require(isinstance(vocabulary, list), 'invalid_record')
    seen = set()
    for row in vocabulary:
        require_fields(row, ('item', 'origin'))
        item = row['item']
        require_fields(item, ITEM_FIELDS)
        require(item['item_id'] == dynamic_id(language, item), 'catalog_changed')
        require(item['item_id'] not in seen, 'duplicate_id')
        seen.add(item['item_id'])
        require_fields(row['origin'], ORIGIN_FIELDS)
        require(all(isinstance(row['origin'][key], str) and row['origin'][key]
                    for key in ORIGIN_FIELDS), 'invalid_record')
        require(len(row['origin']['input_hash']) == 64, 'invalid_record')
    # Reuse the established item validator, including forms and prerequisites.
    from .learning_contracts import DEFAULT_LEVELS
    validate_catalog({'schema_version': 1, 'language': language, 'version': 'vocabulary@1',
                      'provenance': {'basis': 'model-derived', 'source': 'accepted edits', 'license': 'local'},
                      'items': [row['item'] for row in vocabulary], 'levels': deepcopy(DEFAULT_LEVELS)})
    return vocabulary


def merge_vocabulary(vocabulary, chunks, language):
    rows = deepcopy(validate_vocabulary(vocabulary, language))
    by_id = {row['item']['item_id']: row['item'] for row in rows}
    for chunk in chunks:
        for item in chunk.get('introduced_items', []):
            require(item['item_id'] not in by_id or by_id[item['item_id']] == item, 'catalog_changed')
            if item['item_id'] not in by_id:
                rows.append({'item': deepcopy(item), 'origin': {key: chunk[key] for key in ORIGIN_FIELDS}})
                by_id[item['item_id']] = item
    return validate_vocabulary(rows, language)


def effective_catalog(base, vocabulary, chunks=()):
    """Merge frozen base and admitted definitions without mutating/redefining either."""
    catalog = deepcopy(validate_catalog(base))
    rows = merge_vocabulary(vocabulary, chunks, catalog['language'])
    by_id = {item['item_id']: item for item in catalog['items']}
    for row in rows:
        item = row['item']
        require(item['item_id'] not in by_id or by_id[item['item_id']] == item, 'catalog_changed')
        if item['item_id'] not in by_id:
            catalog['items'].append(deepcopy(item))
            by_id[item['item_id']] = item
    return validate_catalog(catalog)
