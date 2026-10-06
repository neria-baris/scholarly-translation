"""Pure, deterministic chunk planning for language learning (LEARN builder A).

No LLM selection. Same (source, learner, catalog, policy_version) always yields
the same plans, ordering and hashes.
"""
from __future__ import annotations
import re

from .learning_contracts import (
    MAX_CHUNK_CHARS,
    POLICY_VERSION,
    fingerprint,
    require,
    validate_catalog,
    validate_learner,
    validate_plan,
    validate_source,
)


def _level_by_id(catalog, level_id):
    for level in catalog["levels"]:
        if level["level_id"] == level_id:
            return level
    require(False, "invalid_plan", f"unknown level_id: {level_id!r}")


def _chunk_units(units):
    """Group ordered units into whole-unit chunks bounded by MAX_CHUNK_CHARS."""
    chunks = []
    current = []
    current_len = 0
    for unit in units:
        unit_len = len(unit["text"])
        if current and current_len + unit_len > MAX_CHUNK_CHARS:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(unit)
        current_len += unit_len
    if current:
        chunks.append(current)
    return chunks


def _select_items(introduced_ids, catalog, level_numeric, new_limit, review_limit, units):
    """Common-first/prerequisite-respecting selection; stable tie-break by item_id."""
    source = ' '.join(u['text'] for u in units if u['kind'] == 'paragraph')
    def opportunity(item):
        if item['kind'] == 'grammar':
            return True
        senses = re.sub(r'\([^)]*\)', '', item['sense_he']).split('/')
        return any(re.search(r'(?<![\w])[ובכלמשה]{0,2}' + re.escape(sense.strip()) + r'(?![\w])', source)
                   for sense in senses if len(sense.strip()) > 1)
    candidates = sorted(
        (item for item in catalog["items"] if item["min_level"] <= level_numeric),
        key=lambda item: (not opportunity(item), item["priority_tier"], item["item_id"]),
    )
    new_ids = []
    review_ids = []
    for item in candidates:
        item_id = item["item_id"]
        if item_id in introduced_ids:
            if (review_limit is None and opportunity(item)) or (review_limit is not None and len(review_ids) < review_limit):
                review_ids.append(item_id)
            continue
        if len(new_ids) >= new_limit:
            continue
        if not set(item["prerequisite_ids"]) <= introduced_ids:
            continue
        new_ids.append(item_id)
    return new_ids, review_ids


def _review_targets(review_ids, learner):
    counts = {row['item_id']: row['introduced_count'] for row in learner['items']}
    return {item_id: {'seen_count': counts[item_id],
                     'target_share': round(min(.95, .55 + .10 * counts[item_id]), 2)}
            for item_id in review_ids}


def _build_plan(source, chapter, chunk_index, units, learner, catalog, level, policy_version):
    introduced_ids = {row["item_id"] for row in learner["items"]}
    level_numeric = int(level["level_id"])
    new_ids, review_ids = _select_items(
        introduced_ids, catalog, level_numeric, level["new_items_per_chunk"],
        level["new_items_per_chunk"] if policy_version == 'learning-policy@1' else None, units,
    )
    selected = new_ids + review_ids
    chunk_id = f"{chapter['chapter_id']}-chunk-{chunk_index}"
    seed = {
        "book_id": source["book_id"], "chunk_id": chunk_id, "chunk_index": chunk_index,
        "base_learner_revision": learner["revision"], "level_id": level["level_id"],
        "selected_item_ids": selected,
    }
    plan = {
        "schema_version": 1,
        "plan_id": f"plan-{fingerprint(seed)[:32]}",
        "book_id": source["book_id"],
        "chapter_id": chapter["chapter_id"],
        "chunk_id": chunk_id,
        "source_hash": source["source_hash"],
        "units": [{"unit_id": u["unit_id"], "text": u["text"], "kind": u["kind"]} for u in units],
        "base_learner_revision": learner["revision"],
        "catalog_version": catalog["version"],
        "policy_version": policy_version,
        "level_id": level["level_id"],
        "support_mode": learner["support_mode"],
        "selected_item_ids": selected,
        "new_item_ids": new_ids,
        "review_item_ids": review_ids,
        "limits": dict(level),
    }
    if policy_version != 'learning-policy@1':
        plan['review_targets'] = _review_targets(review_ids, learner)
        plan['plan_id'] = 'plan-' + fingerprint({'seed': seed, 'policy_version': policy_version,
                                                'review_targets': plan['review_targets']})[:32]
    return validate_plan(plan)


def plan_book(source, learner, catalog, *, policy_version=POLICY_VERSION):
    """Freeze chunk boundaries and provisional candidates for every chapter."""
    source = validate_source(source)
    learner = validate_learner(learner)
    catalog = validate_catalog(catalog)
    require(learner["language"] == catalog["language"], "unsupported_language")
    require(isinstance(policy_version, str) and bool(policy_version.strip()), "invalid_plan")
    level = _level_by_id(catalog, learner["level_id"])

    plans = []
    for chapter in source["chapters"]:
        for chunk_index, units in enumerate(_chunk_units(chapter["units"])):
            plans.append(_build_plan(source, chapter, chunk_index, units, learner, catalog, level, policy_version))
    return plans


def replan_chunk(provisional_plan, projected_learner, catalog):
    """Recompute the final plan right before generation using accepted earlier occurrences."""
    provisional_plan = validate_plan(provisional_plan)
    projected_learner = validate_learner(projected_learner)
    catalog = validate_catalog(catalog)
    require(projected_learner["language"] == catalog["language"], "unsupported_language")
    level = _level_by_id(catalog, provisional_plan["level_id"])

    introduced_ids = {row["item_id"] for row in projected_learner["items"]}
    level_numeric = int(level["level_id"])
    new_ids, review_ids = _select_items(
        introduced_ids, catalog, level_numeric, level["new_items_per_chunk"],
        level["new_items_per_chunk"] if provisional_plan['policy_version'] == 'learning-policy@1' else None,
        provisional_plan['units'],
    )
    selected = new_ids + review_ids
    seed = {
        "chunk_id": provisional_plan["chunk_id"], "book_id": provisional_plan["book_id"],
        "base_learner_revision": projected_learner["revision"], "level_id": provisional_plan["level_id"],
        "selected_item_ids": selected, "introduced_ids": sorted(introduced_ids),
    }
    final_plan = dict(provisional_plan)
    final_plan.update({
        "plan_id": f"plan-{fingerprint(seed)[:32]}",
        "base_learner_revision": projected_learner["revision"],
        "catalog_version": catalog["version"],
        "support_mode": projected_learner["support_mode"],
        "selected_item_ids": selected,
        "new_item_ids": new_ids,
        "review_item_ids": review_ids,
        "limits": dict(level),
    })
    if provisional_plan['policy_version'] != 'learning-policy@1':
        final_plan['review_targets'] = _review_targets(review_ids, projected_learner)
        final_plan['plan_id'] = 'plan-' + fingerprint({'seed': seed,
            'policy_version': provisional_plan['policy_version'], 'review_targets': final_plan['review_targets']})[:32]
    return validate_plan(final_plan)
