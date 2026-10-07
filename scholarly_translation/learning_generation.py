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
    LearningError, check_id, fingerprint, require, validate_catalog,
    validate_generated, validate_plan, validate_recap, word_count,
)

PROMPT_VERSION = "learning-generation@3"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-6-luna"
_ALLOWED_WARNING_CODES = ("coverage_shortfall", "ambiguous_meaning")
_PROMPT_ASSET_PATH = Path(__file__).resolve().parent.parent / "runtime_prompts" / "08_learning_generation.md"
_INSTRUCTIONS_MARKER = "## Instructions (sent verbatim before the data sections)"
_DATA_SECTIONS_MARKER = "## Data sections"


def _prompt_version(plan):
    return {'learning-policy@1': 'learning-generation@1',
            'learning-policy@2': 'learning-generation@2'}.get(plan['policy_version'], PROMPT_VERSION)


def _chunk_prompt_version(plan, dictionary):
    from .learning_dictionary import DICTIONARY_VERSION
    return _prompt_version(plan) + ('+' + DICTIONARY_VERSION if dictionary else '')


def _load_instructions(plan):
    asset_name = {'learning-generation@1': '08_learning_generation.md',
                  'learning-generation@2': '09_learning_cumulative_generation.md',
                  'learning-generation@3': '10_learning_open_vocabulary.md'}[_prompt_version(plan)]
    asset = _PROMPT_ASSET_PATH.with_name(asset_name)
    text = asset.read_text(encoding="utf-8")
    start = text.index(_INSTRUCTIONS_MARKER) + len(_INSTRUCTIONS_MARKER)
    end = text.index(_DATA_SECTIONS_MARKER)
    return text[start:end].strip() + '\n\n' + text[text.index('## Output JSON only'):].strip()


def _section(label, value):
    return f"{label}:\n```json\n{json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2)}\n```"


def build_request(plan, catalog, context="", dictionary_needed=None):
    """Returns (prompt_string, input_hash). Pure; makes no model call.

    ``dictionary_needed`` (lexical IDs still without a dictionary entry)
    enables dictionary entries in the same response; None keeps the earlier
    prompt unchanged.
    """
    validate_plan(plan)
    validate_catalog(catalog)
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
    instructions = _load_instructions(plan)
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
    if dictionary_needed is not None:
        from .learning_dictionary import instructions
        require(isinstance(dictionary_needed, list) and all(isinstance(x, str) for x in dictionary_needed),
                'invalid_plan', 'dictionary_needed')
        prompt += '\n\n' + instructions() + '\n\n' + _section('DICTIONARY_NEEDED', sorted(dictionary_needed))
    input_hash = fingerprint({
        "prompt": prompt,
        "prompt_version": _chunk_prompt_version(plan, dictionary_needed is not None), "plan": plan, "catalog_version": catalog["version"],
        "selected_items": selected_items, "context": context,
        "provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL,
    })
    return prompt, input_hash


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


def parse_response(raw, plan, catalog, input_hash, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL,
                   dictionary_known=None):
    """Strict JSON + structural validation. Returns (GeneratedChunk, recap_proposal).

    ``dictionary_known`` (IDs that already have an entry) enables the optional
    dictionary_entries field; entries are kept only for lexical items used by
    accepted edits here and not already known.
    """
    validate_plan(plan)
    validate_catalog(catalog)
    require(isinstance(raw, str) and raw.strip(), "invalid_generation", "empty_response")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'invalid_generation', 'duplicate_json_key')
            result[key] = value
        return result
    try:
        data = json.loads(raw, object_pairs_hook=unique_pairs)
    except json.JSONDecodeError:
        raise LearningError("invalid_generation", "malformed_json")
    require(isinstance(data, dict), "invalid_generation", "not_an_object")
    fields = {'response_version', 'plan_id', 'edits', 'recap', 'warnings'}
    optional = {'introduced_items'} if plan['policy_version'] == 'learning-policy@3' else set()
    if dictionary_known is not None:
        optional.add('dictionary_entries')
    require(fields <= set(data) and set(data) <= fields | optional, 'invalid_generation', 'response_fields')
    require(type(data.get("response_version")) is int and data["response_version"] == 1, "invalid_generation", "response_version")
    require(data.get("plan_id") == plan["plan_id"], "invalid_generation", "plan_id_mismatch")

    units_by_id = {unit["unit_id"]: unit for unit in plan["units"]}
    items_by_id = {item["item_id"]: item for item in catalog["items"]}
    selected_ids = set(plan["selected_item_ids"])
    new_ids = set(plan['new_item_ids'])
    limits = plan["limits"]

    introduced = data.get('introduced_items', [])
    require(isinstance(introduced, list) and len(introduced) <= limits['new_items_per_chunk'],
            'invalid_generation', 'proposal_quota')
    admitted, aliases = [], {}
    from .learning_vocabulary import proposal_item
    for proposal in introduced:
        item = proposal_item(proposal, catalog['language'], plan['level_id'], catalog.get('frequency_seed', []))
        local_id = check_id(proposal['item_id'])
        require(local_id not in aliases and local_id not in items_by_id and
                item['item_id'] not in items_by_id, 'invalid_generation', 'definition_conflict')
        aliases[local_id] = item['item_id']
        items_by_id[item['item_id']] = item
        admitted.append(item)
        selected_ids.add(item['item_id'])
        new_ids.add(item['item_id'])
    if aliases:
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

    edits_raw = data.get("edits")
    require(isinstance(edits_raw, list), "invalid_generation", "edits")
    edits = []
    occupied = {}
    grammar_used = set()
    foreign_words = 0
    new_foreign_words = 0
    removed_words = 0
    new_items_used = set()

    for raw_edit in edits_raw:
        require(isinstance(raw_edit, dict), "invalid_generation", "edit_shape")
        require(set(raw_edit) == {'unit_id', 'start', 'end', 'original', 'replacement', 'item_ids', 'grammar_ids', 'gloss_he'}, 'invalid_generation', 'edit_fields')
        unit_id = raw_edit.get("unit_id")
        check_id(unit_id)
        require(unit_id in units_by_id, "invalid_generation", "unknown_unit")
        unit = units_by_id[unit_id]
        require(unit["kind"] != "heading", "invalid_generation", "heading_edit")

        start, end = raw_edit.get("start"), raw_edit.get("end")
        require(isinstance(start, int) and isinstance(end, int) and not isinstance(start, bool)
                and not isinstance(end, bool) and 0 <= start < end <= len(unit["text"]),
                "invalid_generation", "span")
        original = raw_edit.get("original")
        require(isinstance(original, str) and unit["text"][start:end] == original,
                "invalid_generation", "original_mismatch")
        require(not (start and unit['text'][start-1].isalpha() and original[0].isalpha()) and
                not (end < len(unit['text']) and unit['text'][end].isalpha() and original[-1].isalpha()),
                'invalid_generation', 'partial_word_span')
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
        rep_words = max(word_count(replacement), 1)
        require(rep_words <= limits["max_foreign_words_per_edit"], "invalid_generation", "foreign_words_per_edit")

        edits.append({
            "unit_id": unit_id, "start": start, "end": end, "original": original,
            "replacement": replacement, "item_ids": list(item_ids), "grammar_ids": list(grammar_ids),
            "gloss_he": gloss_he,
        })
        occupied.setdefault(unit_id, []).append((start, end))
        grammar_used.update(grammar_ids)
        foreign_words += rep_words
        if set(item_ids + grammar_ids) & new_ids:
            new_foreign_words += rep_words
        removed_words += word_count(original)
        new_items_used |= set(item_ids + grammar_ids) & new_ids

    for spans in occupied.values():
        spans.sort()
        for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
            require(prev_end <= next_start, "invalid_generation", "overlapping_edits")

    total_words = max(sum(word_count(unit["text"]) for unit in plan["units"] if unit['kind'] == 'paragraph') - removed_words + foreign_words, 1)
    cumulative = plan['policy_version'] != 'learning-policy@1'
    grammar_objectives = grammar_used & new_ids if cumulative else grammar_used
    require(len(grammar_objectives) <= limits["max_grammar_per_chunk"], "invalid_generation", "grammar_per_chunk")
    counted_foreign = new_foreign_words if cumulative else foreign_words
    require(counted_foreign / total_words <= limits["max_foreign_share"] + 1e-9,
            "invalid_generation", "foreign_share")
    require(len(new_items_used) <= limits["new_items_per_chunk"], "invalid_generation", "new_items_per_chunk")

    warnings_raw = data.get("warnings", [])
    require(isinstance(warnings_raw, list), "invalid_generation", "warnings")
    warnings = []
    for warning in warnings_raw:
        require(isinstance(warning, dict) and warning.get("code") in _ALLOWED_WARNING_CODES,
                "invalid_generation", "warning_code")
        unit_ref = warning.get("unit_id")
        if unit_ref is not None:
            check_id(unit_ref)
        require(unit_ref is None or unit_ref in units_by_id, "invalid_generation", "warning_unit")
        warnings.append({"code": warning["code"], "unit_id": unit_ref})

    coverage_item_ids = sorted({item_id for edit in edits for item_id in edit["item_ids"] + edit['grammar_ids']})
    require(all(item['item_id'] in coverage_item_ids for item in admitted), 'invalid_generation', 'unused_proposal')
    if set(plan['selected_item_ids']) - set(coverage_item_ids) and not any(w['code'] == 'coverage_shortfall' for w in warnings):
        warnings.append({'code': 'coverage_shortfall', 'unit_id': None})
    chunk = {
        "schema_version": 1, "plan_id": plan["plan_id"], "response_version": 1,
        "provider": provider, "model": model,
        "prompt_version": _chunk_prompt_version(plan, dictionary_known is not None),
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

    recap_raw = data.get("recap")
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
