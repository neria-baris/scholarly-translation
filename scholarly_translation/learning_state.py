"""Pure learner-state transition for the single "קראתי" completion event.

Never infer mastery, never auto-increase effort/level and never erase older
items: completion unions accepted occurrences into the full committed history.
"""
from __future__ import annotations

import copy

from .learning_contracts import (
    check_id,
    prepared_hash,
    require,
    validate_generated,
    validate_learner,
    validate_recap,
    validate_session,
)


def apply_completion(learner, session, generated_chunks, recaps, *, completion_id, completed_at):
    """Apply one exactly-once completion; pure, returns (LearnerState, CompletionReceipt)."""
    learner = validate_learner(learner)
    session = validate_session(session)
    check_id(completion_id)
    require(isinstance(completed_at, str) and bool(completed_at.strip()), "invalid_record")

    generated_chunks = [validate_generated(chunk) for chunk in generated_chunks]
    recaps = [validate_recap(recap) for recap in recaps]

    require(session["status"] == "ready", "state_conflict")
    require(session["learner_id"] == learner["learner_id"], "state_conflict")
    require(session["language"] == learner["language"], "state_conflict")
    require(session["base_learner_revision"] == learner["revision"], "state_conflict")
    require(all(session[key] == learner[key] for key in ('catalog_version', 'level_id', 'support_mode')), 'state_conflict')
    require(learner["active_book_id"] == session["book_id"], "state_conflict")

    existing_completion_ids = {row["completion_id"] for row in learner["completed_books"]}
    require(completion_id not in existing_completion_ids, "state_conflict")

    expected_hash = prepared_hash(generated_chunks, recaps)
    require(session["prepared_hash"] == expected_hash, "state_conflict")
    require(set(session["chunk_ids"]) == {chunk["plan_id"] for chunk in generated_chunks}, "state_conflict")

    # Every chapter must have a recap, and every generated chunk's content must
    # be covered by exactly the union of chapter recaps (no silent drop/claim).
    require(bool(recaps), "missing_recap")
    chapter_ids = [recap["chapter_id"] for recap in recaps]
    require(len(chapter_ids) == len(set(chapter_ids)), "missing_recap")
    all_content_hashes = {chunk["content_hash"] for chunk in generated_chunks}
    recap_hashes = set()
    for recap in recaps:
        recap_hashes.update(recap["chunk_hashes"])
    require(recap_hashes == all_content_hashes, "missing_recap")

    # Coverage is computed from ACCEPTED edits, never a model claim.
    accepted_counts = {}
    for chunk in generated_chunks:
        for edit in chunk["edits"]:
            for item_id in list(edit["item_ids"]) + list(edit["grammar_ids"]):
                accepted_counts[item_id] = accepted_counts.get(item_id, 0) + 1

    existing_items = {row["item_id"]: dict(row) for row in learner["items"]}
    for item_id, occurrences in accepted_counts.items():
        row = existing_items.get(item_id)
        if row is None:
            existing_items[item_id] = {
                "item_id": item_id, "introduced_count": occurrences, "last_completed_book_id": session["book_id"],
            }
        else:
            row["introduced_count"] += occurrences
            row["last_completed_book_id"] = session["book_id"]

    new_learner = copy.deepcopy(learner)
    if any(chunk.get('introduced_items') for chunk in generated_chunks) or 'vocabulary' in learner:
        from .learning_vocabulary import merge_vocabulary
        new_learner['vocabulary'] = merge_vocabulary(learner.get('vocabulary', []), generated_chunks, learner['language'])
    new_learner["revision"] = learner["revision"] + 1
    new_learner["items"] = sorted(existing_items.values(), key=lambda row: row["item_id"])
    new_learner["completed_books"] = list(learner["completed_books"]) + [
        {"book_id": session["book_id"], "prepared_hash": expected_hash, "completion_id": completion_id},
    ]
    new_learner["active_book_id"] = None
    new_learner = validate_learner(new_learner)

    receipt = {
        "session_id": session['session_id'],
        "completion_id": completion_id,
        "book_id": session["book_id"],
        "prepared_hash": expected_hash,
        "previous_learner_revision": learner["revision"],
        "next_learner_revision": new_learner["revision"],
        "completed_at": completed_at,
    }
    return new_learner, receipt
