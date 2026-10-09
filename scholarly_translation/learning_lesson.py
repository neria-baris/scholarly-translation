"""Per-chapter grammar lesson: one Luna call after a chapter's chunks are accepted.

Pure request building and deterministic validation; the call itself goes
through the service's controlled path (budget/journal/cache). Every example is
grounded in the chapter: an insertion cites an accepted edit (its text comes
from the edit, never from the model) and a sentence example quotes a chapter
unit exactly. The lesson is supplementary: an invalid response becomes an
honest ``unavailable`` record and never blocks the prepared book.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .learning_contracts import LearningError, check_id, fingerprint, require, unwrap_json_fence

LESSON_PROMPT_VERSION = 'learning-lesson@1'
LESSON_STAGE = 'learning-lesson-v1'
LESSON_OUTPUT_TOKENS = 6000
_PROMPT_ASSET = Path(__file__).resolve().parent.parent / 'runtime_prompts' / '11_learning_grammar_lesson.md'
_MAX_UNIT_CHARS = 40000
_MAX_INSERTIONS = 120
_MAX_PARAGRAPHS = 6
_MAX_EXAMPLES = 5
_HEBREW_LETTER = re.compile('[א-ת]')


def _instructions():
    text = _PROMPT_ASSET.read_text(encoding='utf-8')
    marker = '## Instructions (sent verbatim before the data sections)'
    start = text.index(marker) + len(marker)
    return text[start:text.index('## Data sections')].strip()


def _section(label, value):
    return f"{label}:\n```json\n{json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2)}\n```"


def _sentence(text, start, end, limit=240):
    left = max(text.rfind(mark, 0, start) for mark in '.!?\n') + 1
    rights = [i for i in (text.find(mark, end) for mark in '.!?\n') if i >= 0]
    right = min(rights) + 1 if rights else len(text)
    left, right = max(left, start - limit // 2), min(right, end + limit // 2)
    return text[left:right].strip()


def lesson_inputs(pairs, items):
    """Deterministic grounding view of one chapter: insertion refs and quotable units."""
    edits = []
    for plan, chunk in pairs:
        units = {unit['unit_id']: unit for unit in plan['units']}
        for index, edit in enumerate(chunk['edits']):
            edits.append((plan, chunk, index, edit, units[edit['unit_id']]))
    # Grammar demonstrations first when a dense chapter exceeds the cap.
    chosen = sorted(range(len(edits)), key=lambda i: (not edits[i][3]['grammar_ids'], i))[:_MAX_INSERTIONS]
    refs, insertions = {}, []
    for number, i in enumerate(sorted(chosen), 1):
        _, chunk, index, edit, unit = edits[i]
        ref = f'e{number}'
        refs[ref] = {'chunk_id': chunk['plan_id'], 'edit_index': index,
                     'foreign': edit['replacement'], 'hebrew': edit['original']}
        insertions.append({'ref': ref, 'foreign': edit['replacement'], 'hebrew': edit['original'],
                           'gloss_he': edit['gloss_he'],
                           'items': [items[x]['lemma'] for x in edit['item_ids'] if x in items],
                           'grammar': [items[x]['lemma'] for x in edit['grammar_ids'] if x in items],
                           'sentence_he': _sentence(unit['text'], edit['start'], edit['end'])})
    grammar = {}
    for _, _, _, edit, _ in edits:
        for item_id in edit['grammar_ids']:
            item = items.get(item_id)
            if item:
                grammar[item_id] = {key: item[key] for key in ('item_id', 'lemma', 'sense_he', 'explanation_he')}
    units, used = [], 0
    for plan, _ in pairs:
        for unit in plan['units']:
            if used + len(unit['text']) > _MAX_UNIT_CHARS:
                break
            units.append({'unit_id': unit['unit_id'], 'kind': unit['kind'], 'text': unit['text']})
            used += len(unit['text'])
    return {'refs': refs, 'insertions': insertions, 'grammar': [grammar[k] for k in sorted(grammar)], 'units': units}


def build_lesson_request(chapter_id, language, level_id, pairs, items, prior_topics=()):
    """Returns (prompt, input_hash, grounding). Pure; makes no model call."""
    check_id(chapter_id)
    grounding = lesson_inputs(pairs, items)
    lesson = {'chapter_id': chapter_id, 'language': language, 'level_id': level_id}
    prompt = '\n\n'.join([
        _instructions(),
        _section('LESSON', lesson),
        _section('PRIOR_TOPICS', list(prior_topics)),
        _section('GRAMMAR_ITEMS', grounding['grammar']),
        _section('INSERTIONS', grounding['insertions']),
        _section('CHAPTER_UNITS', grounding['units']),
    ])
    input_hash = fingerprint({'prompt': prompt, 'prompt_version': LESSON_PROMPT_VERSION})
    return prompt, input_hash, grounding


def _text(value, limit, *, empty=False):
    require(isinstance(value, str) and len(value) <= limit and (empty or value.strip()), 'invalid_lesson', 'text')
    return value.strip()


def _example(raw, grounding, units, language):
    """One grounded example, or None when it cannot be verified against the chapter."""
    if not isinstance(raw, dict):
        return None
    note = raw.get('note_he', '')
    if not isinstance(note, str) or len(note) > 600:
        return None
    if set(raw) <= {'edit_ref', 'note_he'} and 'edit_ref' in raw:
        ref = grounding['refs'].get(raw['edit_ref'])
        return ref and {'kind': 'insertion', **ref, 'note_he': note.strip()}
    if set(raw) <= {'unit_id', 'hebrew', 'foreign', 'note_he'} and {'unit_id', 'hebrew', 'foreign'} <= set(raw):
        hebrew, foreign = raw['hebrew'], raw['foreign']
        if not (isinstance(hebrew, str) and isinstance(foreign, str)
                and 0 < len(hebrew.strip()) <= 300 and 0 < len(foreign.strip()) <= 600):
            return None
        hebrew, foreign = ' '.join(hebrew.split()), ' '.join(foreign.split())
        unit = units.get(raw['unit_id']) if isinstance(raw['unit_id'], str) else None
        if unit is None or hebrew not in ' '.join(unit.split()):
            return None
        if language != 'yi' and _HEBREW_LETTER.search(foreign):
            return None
        return {'kind': 'sentence', 'unit_id': raw['unit_id'], 'hebrew': hebrew,
                'foreign': foreign, 'note_he': note.strip()}
    return None


def parse_lesson(raw, chapter_id, language, grounding, input_hash, *, provider='openai', model='gpt-6-luna'):
    """Strict JSON shape; examples that are not grounded in the chapter are dropped and counted."""
    require(isinstance(raw, str) and raw.strip(), 'invalid_lesson', 'empty_response')

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'invalid_lesson', 'duplicate_json_key')
            result[key] = value
        return result
    try:
        data = json.loads(unwrap_json_fence(raw), object_pairs_hook=unique_pairs)
    except json.JSONDecodeError:
        raise LearningError('invalid_lesson', 'malformed_json')
    require(isinstance(data, dict) and set(data) == {'response_version', 'chapter_id', 'topics', 'paragraphs'},
            'invalid_lesson', 'response_fields')
    require(data['response_version'] == 1 and type(data['response_version']) is int, 'invalid_lesson', 'response_version')
    require(data['chapter_id'] == chapter_id, 'invalid_lesson', 'chapter_mismatch')
    topics = data['topics']
    require(isinstance(topics, list) and len(topics) <= 8, 'invalid_lesson', 'topics')
    topics = [_text(topic, 80) for topic in topics]
    paragraphs_raw = data['paragraphs']
    require(isinstance(paragraphs_raw, list) and 0 < len(paragraphs_raw) <= _MAX_PARAGRAPHS, 'invalid_lesson', 'paragraphs')
    units = {unit['unit_id']: unit['text'] for unit in grounding['units']}
    paragraphs, dropped = [], 0
    for paragraph in paragraphs_raw:
        require(isinstance(paragraph, dict) and set(paragraph) == {'heading_he', 'text_he', 'examples'},
                'invalid_lesson', 'paragraph_fields')
        examples_raw = paragraph['examples']
        require(isinstance(examples_raw, list) and len(examples_raw) <= _MAX_EXAMPLES, 'invalid_lesson', 'examples')
        examples = []
        for example in examples_raw:
            checked = _example(example, grounding, units, language)
            if checked is None:
                dropped += 1
            else:
                examples.append(checked)
        paragraphs.append({'heading_he': _text(paragraph['heading_he'], 150),
                           'text_he': _text(paragraph['text_he'], 3000), 'examples': examples})
    return validate_lesson({'schema_version': 1, 'status': 'ready', 'prompt_version': LESSON_PROMPT_VERSION,
                            'provider': provider, 'model': model, 'input_hash': input_hash,
                            'topics': topics, 'paragraphs': paragraphs, 'dropped_examples': dropped})


def unavailable_lesson(input_hash, reason):
    return validate_lesson({'schema_version': 1, 'status': 'unavailable', 'prompt_version': LESSON_PROMPT_VERSION,
                            'input_hash': input_hash, 'reason': reason})


def validate_lesson(lesson):
    """Storage shape of a chapter lesson (ready or honestly unavailable)."""
    require(isinstance(lesson, dict) and lesson.get('schema_version') == 1, 'missing_recap', 'lesson')
    require(lesson.get('status') in ('ready', 'unavailable'), 'missing_recap', 'lesson_status')
    require(isinstance(lesson.get('input_hash'), str), 'missing_recap', 'lesson_hash')
    if lesson['status'] == 'unavailable':
        require(isinstance(lesson.get('reason'), str), 'missing_recap', 'lesson_reason')
        return lesson
    require(isinstance(lesson.get('topics'), list) and all(isinstance(t, str) for t in lesson['topics']),
            'missing_recap', 'lesson_topics')
    require(isinstance(lesson.get('paragraphs'), list) and lesson['paragraphs'], 'missing_recap', 'lesson_paragraphs')
    for paragraph in lesson['paragraphs']:
        require(isinstance(paragraph, dict) and isinstance(paragraph.get('heading_he'), str)
                and isinstance(paragraph.get('text_he'), str) and isinstance(paragraph.get('examples'), list),
                'missing_recap', 'lesson_paragraph')
        for example in paragraph['examples']:
            require(isinstance(example, dict) and example.get('kind') in ('insertion', 'sentence')
                    and all(isinstance(example.get(k), str) for k in ('foreign', 'hebrew', 'note_he')),
                    'missing_recap', 'lesson_example')
    return lesson
