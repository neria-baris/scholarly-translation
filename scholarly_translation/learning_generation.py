"""LEARN builder C: one Luna generation role, deterministic validation.

Builds a bounded prompt from a ChunkPlan + LanguageCatalog subset, sends it
through a caller-supplied ``controlled_generate`` (budget/cache/journal are
Sol's concern, never this module's), and strictly validates the structured
JSON response before it becomes a GeneratedChunk + recap proposal. No direct
network/provider call, no second model call for chapter recap merging.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .learning_contracts import (
    LearningError, check_id, fingerprint, require, unwrap_json_fence, validate_catalog,
    validate_generated, validate_plan, validate_recap, word_count,
)

PROMPT_VERSION = "learning-generation@3"
NOTEBOOK_PROMPT_VERSION = "learning-generation@4"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-6-luna"
_ALLOWED_WARNING_CODES = ("coverage_shortfall", "ambiguous_meaning")
_PROMPT_ASSET_PATH = Path(__file__).resolve().parent.parent / "runtime_prompts" / "08_learning_generation.md"
_INSTRUCTIONS_MARKER = "## Instructions (sent verbatim before the data sections)"
_DATA_SECTIONS_MARKER = "## Data sections"
_EDIT_FIELDS = {'unit_id', 'start', 'end', 'original', 'replacement', 'item_ids', 'grammar_ids', 'gloss_he'}
# Book-level new-word pacing: the share applies to the words read so far, with a
# starting floor so the first short passages (contents, headings) are not starved.
PACING_FLOOR_WORDS = 200
NOTEBOOK_LEARNED_LIMIT = 150


def _prompt_version(plan, notebook=False):
    if notebook:
        return NOTEBOOK_PROMPT_VERSION
    return {'learning-policy@1': 'learning-generation@1',
            'learning-policy@2': 'learning-generation@2'}.get(plan['policy_version'], PROMPT_VERSION)


def _chunk_prompt_version(plan, dictionary, notebook=False):
    from .learning_dictionary import DICTIONARY_VERSION
    return _prompt_version(plan, notebook) + ('+' + DICTIONARY_VERSION if dictionary else '')


def _load_instructions(plan, notebook=False):
    asset_name = {'learning-generation@1': '08_learning_generation.md',
                  'learning-generation@2': '09_learning_cumulative_generation.md',
                  'learning-generation@3': '10_learning_open_vocabulary.md',
                  'learning-generation@4': '13_learning_book_notebook.md'}[_prompt_version(plan, notebook)]
    asset = _PROMPT_ASSET_PATH.with_name(asset_name)
    text = asset.read_text(encoding="utf-8")
    return _section_text(text, _INSTRUCTIONS_MARKER, False) + '\n\n' + _section_text(text, '## Output JSON only', True)


def _section_text(text, heading, keep_heading):
    """One ``## `` section of a prompt asset: from ``heading`` up to the next ``## `` heading."""
    start = text.index(heading)
    body = start + len(heading)
    nxt = text.find('\n## ', body)
    return text[start if keep_heading else body:len(text) if nxt < 0 else nxt].strip()


def _section(label, value):
    return f"{label}:\n```json\n{json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2)}\n```"


def book_notebook(plans, index, plan, learner, catalog, new_words_used=0):
    """The book ledger sent with passage ``index`` (policy@3): local word totals from
    the frozen plans, the new-word allowance at this point of the book and the
    learned items ranked by exposure. Pure and cheap; makes no model call.

    ``max_foreign_share`` bounds new foreign words against the book read so far
    (floored at PACING_FLOOR_WORDS, capped at the whole book), never one passage.
    """
    words = [sum(word_count(unit['text']) for unit in p['units'] if unit['kind'] == 'paragraph') for p in plans]
    book_words, through = sum(words), sum(words[:index + 1])
    share = plan['limits']['max_foreign_share']
    allowance = share * min(book_words, max(through, PACING_FLOOR_WORDS)) - new_words_used
    items = {item['item_id']: item for item in catalog['items']}
    rows = sorted((row for row in learner['items'] if row['item_id'] in items),
                  key=lambda row: (-row['introduced_count'], row['item_id']))[:NOTEBOOK_LEARNED_LIMIT]
    learned = [{'item_id': row['item_id'], 'kind': items[row['item_id']]['kind'],
                'lemma': items[row['item_id']]['lemma'], 'sense_he': items[row['item_id']]['sense_he'],
                'forms': items[row['item_id']]['forms'], 'seen': row['introduced_count']} for row in rows]
    return {'book_words': book_words, 'words_through_passage': through,
            'new_foreign_words_used': new_words_used,
            'new_foreign_word_allowance': max(0, int(allowance)), 'learned': learned}


def new_foreign_words(chunk, plan):
    """Foreign words this accepted chunk spent on items new to the learner."""
    new_ids = set(plan['new_item_ids']) | {item['item_id'] for item in chunk.get('introduced_items', [])}
    return sum(max(word_count(edit['replacement']), 1) for edit in chunk['edits']
               if set(edit['item_ids'] + edit['grammar_ids']) & new_ids)


def _check_notebook(plan, notebook):
    require(plan['policy_version'] == 'learning-policy@3' and isinstance(notebook, dict)
            and type(notebook.get('new_foreign_word_allowance')) is int
            and isinstance(notebook.get('learned'), list), 'invalid_plan', 'notebook')


def build_request(plan, catalog, context="", dictionary_needed=None, notebook=None):
    """Returns (prompt_string, input_hash). Pure; makes no model call.

    ``dictionary_needed`` (lexical IDs still without a dictionary entry)
    enables dictionary entries in the same response; None keeps the earlier
    prompt unchanged. ``notebook`` (see ``book_notebook``) adds the book ledger
    and its prompt version; None keeps the earlier prompt unchanged.
    """
    validate_plan(plan)
    validate_catalog(catalog)
    if notebook is not None:
        _check_notebook(plan, notebook)
    require(isinstance(context, str) and len(context) <= 2000000, "invalid_plan", "context_too_long")

    items_by_id = {item["item_id"]: item for item in catalog["items"]}
    selected_items = []
    for item_id in plan["selected_item_ids"]:
        require(item_id in items_by_id, "invalid_plan", "unknown_selected_item")
        selected_items.append(items_by_id[item_id])
    review_item_ids = sorted(set(plan["review_item_ids"]))

    plan_view = {
        "plan_id": plan["plan_id"], "book_id": plan["book_id"], "chapter_id": plan["chapter_id"],
        "chunk_id": plan["chunk_id"], "level_id": plan["level_id"], "support_mode": plan["support_mode"],
        "selected_item_ids": sorted(plan["selected_item_ids"]), "new_item_ids": sorted(plan["new_item_ids"]),
        "limits": plan["limits"],
    }
    if 'review_targets' in plan:
        plan_view['review_targets'] = plan['review_targets']
    if plan['policy_version'] == 'learning-policy@3':
        plan_view['language'] = catalog['language']
    instructions = _load_instructions(plan, notebook is not None)
    prompt = "\n\n".join([
        instructions,
        _section("PLAN", plan_view),
        _section("SELECTED_ITEMS", selected_items),
        _section("REVIEW_ITEM_IDS", review_item_ids),
        _section("BOOK_CONTEXT", context),
        _section("SOURCE_UNITS", plan["units"]),
    ])
    if plan['policy_version'] == 'learning-policy@3':
        prompt += '\n\n' + _section('FREQUENCY_HINTS', catalog.get('frequency_seed', [])[:100])
    if notebook is not None:
        prompt += '\n\n' + _section('BOOK_NOTEBOOK', notebook)
    if dictionary_needed is not None:
        from .learning_dictionary import instructions
        require(isinstance(dictionary_needed, list) and all(isinstance(x, str) for x in dictionary_needed),
                'invalid_plan', 'dictionary_needed')
        prompt += '\n\n' + instructions() + '\n\n' + _section('DICTIONARY_NEEDED', sorted(dictionary_needed))
    identity = {
        "prompt": prompt,
        "prompt_version": _chunk_prompt_version(plan, dictionary_needed is not None, notebook is not None),
        "plan": plan, "catalog_version": catalog["version"],
        "selected_items": selected_items, "context": context,
        "provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL,
    }
    if notebook is not None:
        identity['notebook'] = notebook
    return prompt, fingerprint(identity)


def _grounded_entries(entries, edits, pool_key, text_field):
    require(isinstance(entries, list), "missing_recap")
    result = []
    for entry in entries or []:
        require(isinstance(entry, dict), "missing_recap")
        item_id = entry.get("item_id")
        check_id(item_id)
        edit_indexes = entry.get("edit_indexes")
        require(isinstance(edit_indexes, list) and bool(edit_indexes), "missing_recap")
        grounded = []
        for idx in edit_indexes:
            require(type(idx) is int and 0 <= idx < len(edits), "missing_recap")
            if item_id in edits[idx][pool_key]:
                grounded.append(idx)
        if not grounded:
            continue
        text_value = entry.get(text_field, "")
        require(isinstance(text_value, str) and len(text_value) <= 2000, "missing_recap")
        result.append({"item_id": item_id, text_field: text_value, "edit_indexes": grounded})
    return result


def _whole_word(text, start, end):
    original = text[start:end]
    return (not (start and text[start - 1].isalpha() and original[0].isalpha()) and
            not (end < len(text) and text[end].isalpha() and original[-1].isalpha()))


def _resolve_span(text, start, end, original, taken):
    """Where ``original`` stands in ``text``: the given offsets when they match a free
    whole-word slice, otherwise the free whole-word occurrence nearest the given
    start (models miscount codepoints, e.g. around ״). None when there is none."""
    if not isinstance(original, str) or not original.strip():
        return None

    def usable(s, e):
        return _whole_word(text, s, e) and all(e <= a or s >= b for a, b in taken)
    if (type(start) is int and type(end) is int and 0 <= start < end <= len(text)
            and text[start:end] == original and usable(start, end)):
        return start, end
    hint = start if type(start) is int else 0
    found, position = [], text.find(original)
    while position >= 0:
        found.append(position)
        position = text.find(original, position + 1)
    for position in sorted(found, key=lambda s: (abs(s - hint), s)):
        if usable(position, position + len(original)):
            return position, position + len(original)
    return None


def _checked_edit(raw_edit, units_by_id, items_by_id, selected_ids, limits, taken=None):
    """One validated edit; raises LearningError. With ``taken`` (lenient parsing) a
    miscounted span is located by its ``original`` text among free positions."""
    require(isinstance(raw_edit, dict), "invalid_generation", "edit_shape")
    require(set(raw_edit) == _EDIT_FIELDS, 'invalid_generation', 'edit_fields')
    unit_id = raw_edit.get("unit_id")
    check_id(unit_id)
    require(unit_id in units_by_id, "invalid_generation", "unknown_unit")
    unit = units_by_id[unit_id]
    require(unit["kind"] != "heading", "invalid_generation", "heading_edit")

    start, end = raw_edit.get("start"), raw_edit.get("end")
    original = raw_edit.get("original")
    if taken is not None:
        span = _resolve_span(unit['text'], start, end, original, taken.get(unit_id, []))
        require(span is not None, 'invalid_generation', 'original_mismatch')
        start, end = span
    require(isinstance(start, int) and isinstance(end, int) and not isinstance(start, bool)
            and not isinstance(end, bool) and 0 <= start < end <= len(unit["text"]),
            "invalid_generation", "span")
    require(isinstance(original, str) and unit["text"][start:end] == original,
            "invalid_generation", "original_mismatch")
    require(_whole_word(unit['text'], start, end), 'invalid_generation', 'partial_word_span')
    require(word_count(original) <= limits['max_foreign_words_per_edit'] + 3, 'invalid_generation', 'source_span_too_large')

    item_ids = raw_edit.get("item_ids")
    grammar_ids = raw_edit.get("grammar_ids")
    require(isinstance(item_ids, list) and isinstance(grammar_ids, list), "invalid_generation", "id_lists")
    require(bool(item_ids or grammar_ids), 'invalid_generation', 'untracked_edit')
    require(all(isinstance(x, str) for x in item_ids + grammar_ids), 'invalid_generation', 'id_lists')
    require(len(set(item_ids)) == len(item_ids) and len(set(grammar_ids)) == len(grammar_ids), 'invalid_generation', 'duplicate_item_id')
    require(set(item_ids) <= selected_ids and set(grammar_ids) <= selected_ids,
            "invalid_generation", "unselected_item")
    for item_id in item_ids:
        require(item_id in items_by_id and items_by_id[item_id]["kind"] in ("word", "phrase"),
                "invalid_generation", "lexical_item")
    for grammar_id in grammar_ids:
        require(grammar_id in items_by_id and items_by_id[grammar_id]["kind"] == "grammar",
                "invalid_generation", "grammar_item")

    replacement = raw_edit.get("replacement")
    gloss_he = raw_edit.get("gloss_he", "")
    require(isinstance(replacement, str) and bool(replacement), "invalid_generation", "replacement")
    require(isinstance(gloss_he, str), "invalid_generation", "gloss")
    if item_ids:
        require(all(replacement in items_by_id[item_id]["forms"] for item_id in item_ids),
                "invalid_generation", "unapproved_surface")
    for grammar_id in grammar_ids:
        forms = items_by_id[grammar_id]['forms']
        matches = any(re.search(r'(?<!\w)' + re.escape(form) + r'(?!\w)', replacement) for form in forms)
        require(matches and (bool(item_ids) or replacement in forms), 'invalid_generation', 'ungrounded_grammar')
    require(max(word_count(replacement), 1) <= limits["max_foreign_words_per_edit"],
            "invalid_generation", "foreign_words_per_edit")
    return {"unit_id": unit_id, "start": start, "end": end, "original": original,
            "replacement": replacement, "item_ids": list(item_ids), "grammar_ids": list(grammar_ids),
            "gloss_he": gloss_he}


def _narrowed_edit(raw_edit):
    """The edit without whole-word Hebrew context the model repeated around its foreign
    form (e.g. original "״הוא לבד עכשיו.״" -> replacement "״הוא לבד ahora.״"), or None."""
    if not isinstance(raw_edit, dict):
        return None
    original, replacement = raw_edit.get('original'), raw_edit.get('replacement')
    if not isinstance(original, str) or not isinstance(replacement, str):
        return None
    shortest = min(len(original), len(replacement))
    lead = 0
    while lead < shortest and original[lead] == replacement[lead]:
        lead += 1
    while lead and original[lead - 1].isalpha():
        lead -= 1
    trail = 0
    while trail < shortest - lead and original[-1 - trail] == replacement[-1 - trail]:
        trail += 1
    while trail and original[len(original) - trail].isalpha():
        trail -= 1
    if not (lead or trail):
        return None
    core, foreign = original[lead:len(original) - trail], replacement[lead:len(replacement) - trail].strip()
    lead += len(core) - len(core.lstrip())
    core = core.strip()
    if not core or not foreign:
        return None
    start = raw_edit.get('start')
    return dict(raw_edit, original=core, replacement=foreign,
                start=start + lead if type(start) is int else start,
                end=start + lead + len(core) if type(start) is int else raw_edit.get('end'))


def _lenient_edit(raw_edit, units_by_id, items_by_id, selected_ids, limits, taken):
    """``_checked_edit`` that retries an unacceptable foreign surface once without
    repeated Hebrew context; raises the first error when that does not help."""
    try:
        return _checked_edit(raw_edit, units_by_id, items_by_id, selected_ids, limits, taken)
    except LearningError as exc:
        narrowed = _narrowed_edit(raw_edit) if str(exc) in (
            'unapproved_surface', 'ungrounded_grammar', 'source_span_too_large', 'foreign_words_per_edit') else None
        if narrowed is None:
            raise
        try:
            return _checked_edit(narrowed, units_by_id, items_by_id, selected_ids, limits, taken)
        except LearningError:
            raise exc from None


def _remapped_recap(recap, index_map):
    """Lenient recap: entries keep only accepted edits' indexes (renumbered); a
    malformed entry or one left without an accepted edit is dropped."""
    result = {'vocabulary': [], 'grammar': []}
    if not isinstance(recap, dict):
        return result
    for key, text_field in (('vocabulary', 'gloss_he'), ('grammar', 'explanation_he')):
        entries = recap.get(key)
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get('edit_indexes'), list):
                continue
            try:
                check_id(entry.get('item_id'))
            except LearningError:
                continue
            indexes = [index_map[i] for i in entry['edit_indexes'] if type(i) is int and i in index_map]
            text = entry.get(text_field, '')
            if indexes and isinstance(text, str) and len(text) <= 2000:
                result[key].append({'item_id': entry['item_id'], text_field: text, 'edit_indexes': indexes})
    return result


def _local_ref(value):
    """A proposal's local reference: any short string (it is remapped to a stable ID)."""
    require(isinstance(value, str) and 0 < len(value) <= 128, 'invalid_generation', 'invalid_id')
    return value


def parse_response(raw, plan, catalog, input_hash, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL,
                   dictionary_known=None, notebook=None, report=None):
    """JSON + structural validation. Returns (GeneratedChunk, recap_proposal).

    ``dictionary_known`` (IDs that already have an entry) enables the optional
    dictionary_entries field; entries are kept only for lexical items used by
    accepted edits here and not already known.

    Policy@1/@2 answers are all-or-nothing. Policy@3 answers are salvaged: a
    miscounted span is located by its ``original`` text, and an invalid edit,
    proposal, warning or recap entry is dropped (reason appended to
    ``report['dropped']`` when a dict is given) instead of rejecting the answer;
    quotas trim edits in answer order. The answer is still rejected when it is not
    the expected JSON object for this plan, or proposed edits and none survived
    for a non-quota reason. ``notebook`` (see ``book_notebook``) makes the learned
    items usable as known items and replaces the per-passage foreign share with
    the book allowance.
    """
    validate_plan(plan)
    validate_catalog(catalog)
    lenient = plan['policy_version'] == 'learning-policy@3'
    if notebook is not None:
        _check_notebook(plan, notebook)
    dropped = []
    if report is not None:
        report['dropped'] = dropped   # Filled as parts are dropped, also when the answer is rejected.
    require(isinstance(raw, str) and raw.strip(), "invalid_generation", "empty_response")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'invalid_generation', 'duplicate_json_key')
            result[key] = value
        return result
    try:
        data = json.loads(unwrap_json_fence(raw), object_pairs_hook=unique_pairs)
    except json.JSONDecodeError:
        raise LearningError("invalid_generation", "malformed_json")
    require(isinstance(data, dict), "invalid_generation", "not_an_object")
    fields = {'response_version', 'plan_id', 'edits', 'recap', 'warnings'}
    optional = {'introduced_items'} if plan['policy_version'] == 'learning-policy@3' else set()
    if dictionary_known is not None:
        optional.add('dictionary_entries')
    if lenient:
        require({'response_version', 'plan_id', 'edits'} <= set(data), 'invalid_generation', 'response_fields')
        dropped.extend('field:' + key for key in sorted(set(data) - fields - optional))
    else:
        require(fields <= set(data) and set(data) <= fields | optional, 'invalid_generation', 'response_fields')
    require(type(data.get("response_version")) is int and data["response_version"] == 1, "invalid_generation", "response_version")
    require(data.get("plan_id") == plan["plan_id"], "invalid_generation", "plan_id_mismatch")

    units_by_id = {unit["unit_id"]: unit for unit in plan["units"]}
    items_by_id = {item["item_id"]: item for item in catalog["items"]}
    selected_ids = set(plan["selected_item_ids"])
    new_ids = set(plan['new_item_ids'])
    if notebook is not None:
        # Learned items are known everywhere in the book: usable, never new.
        selected_ids |= {row['item_id'] for row in notebook['learned'] if row.get('item_id') in items_by_id}
    limits = plan["limits"]

    introduced = data.get('introduced_items', [])
    if lenient:
        introduced = introduced if isinstance(introduced, list) else []
    else:
        require(isinstance(introduced, list) and len(introduced) <= limits['new_items_per_chunk'],
                'invalid_generation', 'proposal_quota')
    admitted, aliases = [], {}
    from .learning_vocabulary import proposal_item
    for proposal in introduced:
        if not lenient:
            item = proposal_item(proposal, catalog['language'], plan['level_id'], catalog.get('frequency_seed', []))
            local_id = check_id(proposal['item_id'])
            require(local_id not in aliases and local_id not in items_by_id and
                    item['item_id'] not in items_by_id, 'invalid_generation', 'definition_conflict')
        else:
            try:
                require(isinstance(proposal, dict), 'invalid_generation', 'proposal_shape')
                item = proposal_item(proposal, catalog['language'], plan['level_id'], catalog.get('frequency_seed', []))
                local_id = _local_ref(proposal['item_id'])
                require(local_id not in aliases and local_id not in items_by_id,
                        'invalid_generation', 'definition_conflict')
            except LearningError as exc:
                dropped.append('proposal:' + str(exc))
                continue
            if item['item_id'] in items_by_id:
                # The same definition already exists: reuse it (new unless already usable).
                aliases[local_id] = item['item_id']
                if item['item_id'] not in selected_ids:
                    selected_ids.add(item['item_id'])
                    new_ids.add(item['item_id'])
                continue
        aliases[local_id] = item['item_id']
        items_by_id[item['item_id']] = item
        admitted.append(item)
        selected_ids.add(item['item_id'])
        new_ids.add(item['item_id'])
    if aliases and not lenient:
        require(isinstance(data['edits'], list), 'invalid_generation')
        for edit in data['edits']:
            require(isinstance(edit, dict), 'invalid_generation')
            for key in ('item_ids', 'grammar_ids'):
                require(isinstance(edit.get(key), list) and all(isinstance(value, str) for value in edit[key]), 'invalid_generation')
                edit[key] = [aliases.get(value, value) for value in edit[key]]
        require(isinstance(data['recap'], dict), 'missing_recap')
        for key in ('vocabulary', 'grammar'):
            require(isinstance(data['recap'].get(key), list), 'missing_recap')
            for entry in data['recap'][key]:
                require(isinstance(entry, dict), 'missing_recap')
                entry['item_id'] = aliases.get(entry.get('item_id'), entry.get('item_id'))
    elif aliases:
        for edit in data['edits'] if isinstance(data['edits'], list) else []:
            for key in ('item_ids', 'grammar_ids'):
                if isinstance(edit, dict) and isinstance(edit.get(key), list):
                    edit[key] = [aliases.get(value, value) if isinstance(value, str) else value for value in edit[key]]
        recap = data.get('recap')
        for key in ('vocabulary', 'grammar'):
            for entry in recap.get(key) if isinstance(recap, dict) and isinstance(recap.get(key), list) else []:
                if isinstance(entry, dict) and isinstance(entry.get('item_id'), str):
                    entry['item_id'] = aliases.get(entry['item_id'], entry['item_id'])

    edits_raw = data.get("edits")
    require(isinstance(edits_raw, list), "invalid_generation", "edits")
    edits = []
    occupied = {}
    grammar_used = set()
    foreign_words = 0
    new_foreign_words = 0
    removed_words = 0
    new_items_used = set()
    index_map = {}
    cumulative = plan['policy_version'] != 'learning-policy@1'
    paragraph_words = sum(word_count(unit["text"]) for unit in plan["units"] if unit['kind'] == 'paragraph')

    for position, raw_edit in enumerate(edits_raw):
        if not lenient:
            edit = _checked_edit(raw_edit, units_by_id, items_by_id, selected_ids, limits)
        else:
            try:
                edit = _lenient_edit(raw_edit, units_by_id, items_by_id, selected_ids, limits, occupied)
            except LearningError as exc:
                dropped.append(str(exc))
                continue
        ids = set(edit['item_ids'] + edit['grammar_ids'])
        rep_words = max(word_count(edit['replacement']), 1)
        is_new = bool(ids & new_ids)
        if lenient:
            # Quotas trim edits in answer order instead of rejecting the answer.
            grammar = grammar_used | set(edit['grammar_ids'])
            counted = new_foreign_words + (rep_words if is_new else 0)
            total = max(paragraph_words - removed_words - word_count(edit['original']) + foreign_words + rep_words, 1)
            if notebook is not None:
                over_share = counted > notebook['new_foreign_word_allowance']
            else:
                over_share = counted / total > limits['max_foreign_share'] + 1e-9
            quota = ('grammar_per_chunk' if len(grammar & new_ids) > limits['max_grammar_per_chunk'] else
                     'new_items_per_chunk' if len(new_items_used | (ids & new_ids)) > limits['new_items_per_chunk'] else
                     'foreign_share' if over_share else None)
            if quota:
                dropped.append('quota:' + quota)
                continue
        index_map[position] = len(edits)
        edits.append(edit)
        occupied.setdefault(edit['unit_id'], []).append((edit['start'], edit['end']))
        grammar_used.update(edit['grammar_ids'])
        foreign_words += rep_words
        if is_new:
            new_foreign_words += rep_words
        removed_words += word_count(edit['original'])
        new_items_used |= ids & new_ids
    if lenient:
        require(edits or not edits_raw or any(code.startswith('quota:') for code in dropped),
                'invalid_generation', 'no_valid_edit')

    for spans in occupied.values():
        spans.sort()
        for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
            require(prev_end <= next_start, "invalid_generation", "overlapping_edits")

    total_words = max(paragraph_words - removed_words + foreign_words, 1)
    grammar_objectives = grammar_used & new_ids if cumulative else grammar_used
    require(len(grammar_objectives) <= limits["max_grammar_per_chunk"], "invalid_generation", "grammar_per_chunk")
    counted_foreign = new_foreign_words if cumulative else foreign_words
    if notebook is None:
        require(counted_foreign / total_words <= limits["max_foreign_share"] + 1e-9,
                "invalid_generation", "foreign_share")
    require(len(new_items_used) <= limits["new_items_per_chunk"], "invalid_generation", "new_items_per_chunk")

    warnings_raw = data.get("warnings", [])
    if lenient and not isinstance(warnings_raw, list):
        dropped.append('warnings')
        warnings_raw = []
    require(isinstance(warnings_raw, list), "invalid_generation", "warnings")
    warnings = []
    for warning in warnings_raw:
        try:
            require(isinstance(warning, dict) and warning.get("code") in _ALLOWED_WARNING_CODES,
                    "invalid_generation", "warning_code")
            unit_ref = warning.get("unit_id")
            if unit_ref is not None:
                check_id(unit_ref)
            require(unit_ref is None or unit_ref in units_by_id, "invalid_generation", "warning_unit")
        except LearningError as exc:
            if not lenient:
                raise
            dropped.append('warning:' + str(exc))
            continue
        warnings.append({"code": warning["code"], "unit_id": unit_ref})

    coverage_item_ids = sorted({item_id for edit in edits for item_id in edit["item_ids"] + edit['grammar_ids']})
    if lenient:
        dropped.extend('proposal:unused' for item in admitted if item['item_id'] not in coverage_item_ids)
        admitted = [item for item in admitted if item['item_id'] in coverage_item_ids]
    require(all(item['item_id'] in coverage_item_ids for item in admitted), 'invalid_generation', 'unused_proposal')
    if set(plan['selected_item_ids']) - set(coverage_item_ids) and not any(w['code'] == 'coverage_shortfall' for w in warnings):
        warnings.append({'code': 'coverage_shortfall', 'unit_id': None})
    chunk = {
        "schema_version": 1, "plan_id": plan["plan_id"], "response_version": 1,
        "provider": provider, "model": model,
        "prompt_version": _chunk_prompt_version(plan, dictionary_known is not None, notebook is not None),
        "input_hash": input_hash, "edits": edits, "warnings": warnings,
        "language": catalog['language'],
        "coverage_item_ids": coverage_item_ids,
        "content_hash": fingerprint({"plan_id": plan['plan_id'], "input_hash": input_hash, "edits": edits, "coverage_item_ids": coverage_item_ids}),
    }
    if admitted:
        chunk['introduced_items'] = admitted
        chunk['content_hash'] = fingerprint({'plan_id': plan['plan_id'], 'input_hash': input_hash,
                                            'edits': edits, 'coverage_item_ids': coverage_item_ids,
                                            'introduced_items': admitted})
    if dictionary_known is not None:
        from .learning_dictionary import parse_entries
        lexical_used = {item_id for edit in edits for item_id in edit['item_ids']}
        entries = parse_entries(data.get('dictionary_entries'), language=catalog['language'], aliases=aliases,
                                eligible_ids=lexical_used - set(dictionary_known))
        if entries:
            # Supplementary data: covered by the prepared hash, not by content_hash.
            chunk['dictionary_entries'] = entries
    validate_generated(chunk)

    recap_raw = _remapped_recap(data.get('recap'), index_map) if lenient else data.get("recap")
    require(isinstance(recap_raw, dict) and set(recap_raw) == {'vocabulary', 'grammar'}, "missing_recap")
    recap_proposal = {
        "vocabulary": _grounded_entries(recap_raw.get("vocabulary"), edits, "item_ids", "gloss_he"),
        "grammar": _grounded_entries(recap_raw.get("grammar"), edits, "grammar_ids", "explanation_he"),
    }
    for entry in recap_proposal['grammar']:
        entry['explanation_he'] = items_by_id[entry['item_id']]['explanation_he']
    # Sparse model recap cannot hide a real accepted occurrence.
    for edit in edits:
        for item_id in edit['item_ids']:
            if not any(x['item_id'] == item_id for x in recap_proposal['vocabulary']):
                recap_proposal['vocabulary'].append({'item_id': item_id, 'gloss_he': edit['gloss_he'], 'edit_indexes': [edits.index(edit)]})
        for item_id in edit['grammar_ids']:
            if not any(x['item_id'] == item_id for x in recap_proposal['grammar']):
                recap_proposal['grammar'].append({'item_id': item_id, 'explanation_he': items_by_id[item_id]['explanation_he'], 'edit_indexes': [edits.index(edit)]})
    return chunk, recap_proposal


def generate_chunk(plan, catalog, context="", *, controlled_generate,
                    provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL):
    """Builds the request, calls controlled_generate exactly once, validates the reply."""
    prompt, input_hash = build_request(plan, catalog, context)
    raw_result = controlled_generate(prompt, input_hash)
    if hasattr(raw_result, "status") and hasattr(raw_result, "text"):
        require(raw_result.status == "completed", "invalid_generation", raw_result.status)
        raw_text = raw_result.text
    elif isinstance(raw_result, str):
        raw_text = raw_result
    else:
        raise LearningError("invalid_generation", "unexpected_result_type")
    return parse_response(raw_text, plan, catalog, input_hash, provider=provider, model=model)


def build_chapter_recap(chapter_id, accepted_chunks, proposed_entries):
    """Deterministic local merge of accepted-chunk recap proposals. No model call."""
    check_id(chapter_id)
    require(isinstance(accepted_chunks, list) and bool(accepted_chunks), "missing_recap")
    chunks_by_plan_id = {}
    for chunk in accepted_chunks:
        validate_generated(chunk)
        chunks_by_plan_id[chunk["plan_id"]] = chunk
    chunk_hashes = sorted({chunk["content_hash"] for chunk in accepted_chunks})

    vocabulary = {}
    grammar = {}
    for entry in proposed_entries or []:
        require(isinstance(entry, dict), "missing_recap")
        chunk_id = entry.get("chunk_id")
        require(chunk_id in chunks_by_plan_id, "missing_recap", "unknown_chunk")
        chunk = chunks_by_plan_id[chunk_id]
        recap = entry.get("recap") or {}
        require(isinstance(recap, dict), "missing_recap")

        for voc in recap.get("vocabulary") or []:
            item_id = voc.get("item_id")
            indexes = [idx for idx in voc.get("edit_indexes", [])
                       if isinstance(idx, int) and 0 <= idx < len(chunk["edits"])
                       and item_id in chunk["edits"][idx]["item_ids"]]
            if not indexes:
                continue
            vocabulary.setdefault(item_id, {"item_id": item_id, "gloss_he": voc.get("gloss_he", "")})

        for gr in recap.get("grammar") or []:
            item_id = gr.get("item_id")
            indexes = [idx for idx in gr.get("edit_indexes", [])
                       if isinstance(idx, int) and 0 <= idx < len(chunk["edits"])
                       and item_id in chunk["edits"][idx]["grammar_ids"]]
            if not indexes:
                continue
            bucket = grammar.setdefault(item_id, {"item_id": item_id,
                                                   "explanation_he": gr.get("explanation_he", ""),
                                                   "examples": []})
            for idx in indexes:
                bucket["examples"].append({"chunk_id": chunk_id, "edit_index": idx})

    recap = {
        "schema_version": 1, "chapter_id": chapter_id, "chunk_hashes": chunk_hashes,
        "vocabulary": [{"item_id": v["item_id"], "gloss_he": v["gloss_he"]}
                        for v in sorted(vocabulary.values(), key=lambda v: v["item_id"])],
        "grammar": [{"item_id": g["item_id"], "explanation_he": g["explanation_he"], "examples": g["examples"]}
                     for g in sorted(grammar.values(), key=lambda g: g["item_id"])],
        "warnings": [warning for chunk in accepted_chunks for warning in chunk['warnings']],
    }
    return validate_recap(recap)
