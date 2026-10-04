"""Session D extension: small, versioned, source-backed persistent document
state carried across chapters.

This is deliberately NOT a Story Bible and NOT RAG: it is a small, bounded,
append-only, versioned store (same spirit as glossary.py) of only the
translation-relevant facts/decisions a later chapter may depend on --
approved terminology, definitions, notation, character/register traits,
recurring names/places, and explicitly-marked unresolved ambiguities.
Never a chapter summary, never free-form prose memory.

Pure data module: proposals are supplied by the caller (a chapter-level
QA/review stage, or a human), never generated here. A model-derived item can
never be marked "established" by this module -- only a human actor can
promote an item to "established" certainty, so an inference never silently
becomes a fact. Every item carries a `source` pointer (chapter node + unit
ids + exact span) back to where it was introduced or last refined, and
updating a (category, label) key never deletes the prior value -- it adds a
new version, so historical revisions remain fully reconstructible.
"""
from __future__ import annotations

import copy
import json

from .source_reading import fingerprint, integer, nonempty, strings
from .store import deterministic_id

SCHEMA_VERSION = 1
STAGE = "document-state@1"

CERTAINTY_LEVELS = ("established", "likely", "unresolved")
CATEGORIES = (
    "terminology", "definition", "notation", "distinction", "character",
    "register", "motif", "place", "decision", "ambiguity", "other",
)
ACTOR_KINDS = ("human", "model")

MAX_LABEL_CHARS = 200
MAX_VALUE_CHARS = 1000
MAX_REASON_CHARS = 500
MAX_ITEMS = 2000  # small and bounded by design -- never a growing Story Bible

_ITEM_FIELDS = {
    "item_id", "version", "prior_version", "category", "label", "value", "certainty",
    "source", "reason", "actor", "actor_kind", "committed_in_chapter_node_id",
}
_SOURCE_REF_FIELDS = {"chapter_node_id", "unit_ids", "document_id", "source_char_start", "source_char_end"}


class DocumentStateError(ValueError):
    """Invalid persistent document state input; never includes full source/chapter text."""


def _require(condition, message):
    if not condition:
        raise DocumentStateError(message)


def new_document_state(document_id):
    _require(nonempty(document_id), "document_id must be a nonempty string")
    return {"schema_version": SCHEMA_VERSION, "stage": STAGE, "document_id": document_id,
            "revision": 0, "items": []}


def validate_source_ref(ref, *, document_id=None):
    _require(isinstance(ref, dict) and set(ref) == _SOURCE_REF_FIELDS, "invalid persistent-state source reference")
    _require(nonempty(ref["chapter_node_id"]) and nonempty(ref["document_id"]),
              "invalid persistent-state source identity")
    _require(document_id is None or ref["document_id"] == document_id,
              "persistent-state source reference belongs to a different document")
    _require(strings(ref["unit_ids"]) and len(ref["unit_ids"]) > 0,
              "persistent-state item must reference at least one source translation unit")
    _require(integer(ref["source_char_start"], 0) and integer(ref["source_char_end"])
              and ref["source_char_start"] < ref["source_char_end"],
              "invalid persistent-state source span")


def _validate_item_row(row, document_id):
    _require(isinstance(row, dict) and set(row) == _ITEM_FIELDS, "invalid persistent-state item shape")
    _require(nonempty(row["item_id"]) and integer(row["version"])
              and (row["prior_version"] is None
                   or (integer(row["prior_version"]) and row["prior_version"] < row["version"])),
              "invalid persistent-state item identity/version")
    _require(row["category"] in CATEGORIES, "unsupported persistent-state category")
    _require(nonempty(row["label"]) and len(row["label"]) <= MAX_LABEL_CHARS, "invalid persistent-state label")
    _require(isinstance(row["value"], str) and 0 < len(row["value"]) <= MAX_VALUE_CHARS,
              "invalid persistent-state value")
    _require(row["certainty"] in CERTAINTY_LEVELS, "invalid persistent-state certainty")
    _require(nonempty(row["reason"]) and len(row["reason"]) <= MAX_REASON_CHARS,
              "invalid persistent-state update reason")
    _require(nonempty(row["actor"]), "invalid persistent-state update actor")
    _require(row["actor_kind"] in ACTOR_KINDS, "invalid persistent-state update actor_kind")
    _require(nonempty(row["committed_in_chapter_node_id"]), "invalid persistent-state committing chapter reference")
    # A model-generated inference must never silently become a fact: only a
    # human actor may mark an item "established".
    _require(not (row["actor_kind"] == "model" and row["certainty"] == "established"),
              "a model-derived persistent-state item cannot be marked 'established' without human confirmation")
    validate_source_ref(row["source"], document_id=document_id)
    _require(row["item_id"] == deterministic_id("document-state-item", document_id, row["category"], row["label"]),
              "persistent-state item identity mismatch")


def validate_document_state(state):
    _require(isinstance(state, dict) and set(state) == {"schema_version", "stage", "document_id", "revision", "items"},
              "invalid persistent document state shape")
    _require(type(state["schema_version"]) is int and state["schema_version"] == SCHEMA_VERSION
              and state["stage"] == STAGE and nonempty(state["document_id"]),
              "invalid persistent document state identity")
    _require(isinstance(state["items"], list) and len(state["items"]) <= MAX_ITEMS,
              "too many persistent document state items (not a Story Bible)")
    _require(integer(state["revision"], 0), "invalid persistent document state revision")

    by_item = {}
    for row in state["items"]:
        _validate_item_row(row, state["document_id"])
        by_item.setdefault(row["item_id"], []).append(row)

    for rows in by_item.values():
        _require([r["version"] for r in rows] == list(range(1, len(rows) + 1)),
                  "persistent-state item version sequence invalid")
        _require(rows[0]["prior_version"] is None, "initial persistent-state item version must have no prior_version")
        for prev, cur in zip(rows, rows[1:]):
            _require(cur["prior_version"] == prev["version"], "persistent-state item version chain broken")
            _require(cur["category"] == prev["category"] and cur["label"] == prev["label"],
                      "persistent-state item category/label changed across versions")


def _latest_by_key(state):
    """Most recent version of every (category, label) item key."""
    latest = {}
    for row in state["items"]:
        key = (row["category"], row["label"])
        current = latest.get(key)
        if current is None or row["version"] > current["version"]:
            latest[key] = row
    return latest


def propose_item(*, category, label, value, certainty, source, reason):
    """Build one candidate persistent-state update (not yet committed).

    Pure and deterministic; the caller (a chapter-level QA/review stage, or
    a human) supplies the certainty explicitly -- this function never
    upgrades or infers it.
    """
    _require(category in CATEGORIES, "unsupported persistent-state category")
    _require(nonempty(label) and len(label) <= MAX_LABEL_CHARS, "invalid persistent-state label")
    _require(isinstance(value, str) and 0 < len(value) <= MAX_VALUE_CHARS, "invalid persistent-state value")
    _require(certainty in CERTAINTY_LEVELS, "invalid persistent-state certainty")
    validate_source_ref(source)
    _require(nonempty(reason) and len(reason) <= MAX_REASON_CHARS, "invalid persistent-state update reason")
    return {"category": category, "label": label, "value": value, "certainty": certainty,
            "source": source, "reason": reason}


def find_conflicts(state, candidates):
    """Deterministic contradiction detection against the current latest
    state: a chapter-QA stage can use this to identify, before committing,
    which proposed updates would silently overwrite an existing value with
    a different one. Never auto-resolves anything."""
    validate_document_state(state)
    latest = _latest_by_key(state)
    conflicts = []
    for candidate in candidates:
        existing = latest.get((candidate["category"], candidate["label"]))
        if existing is not None and existing["value"] != candidate["value"]:
            conflicts.append({
                "category": candidate["category"], "label": candidate["label"],
                "existing_value": existing["value"], "existing_certainty": existing["certainty"],
                "candidate_value": candidate["value"], "candidate_certainty": candidate["certainty"],
            })
    return conflicts


def commit_update(state, candidates, *, chapter_node_id, actor, actor_kind, reason,
                   acknowledged_contradictions=()):
    """Append accepted candidate items as one new persistent-state revision.

    Updating an existing (category, label) key adds a new *version* of that
    item rather than overwriting or deleting the prior one -- the prior
    version remains in `items` (its history is reconstructible by filtering
    to versions <= a given revision). Refuses (fails closed) if a candidate
    would silently overwrite a differing existing value unless its
    (category, label) key is explicitly acknowledged via
    `acknowledged_contradictions`.
    """
    validate_document_state(state)
    _require(nonempty(chapter_node_id), "invalid chapter_node_id")
    _require(nonempty(actor), "invalid persistent-state update actor")
    _require(actor_kind in ACTOR_KINDS, "invalid persistent-state update actor_kind")
    _require(nonempty(reason) and len(reason) <= MAX_REASON_CHARS, "invalid persistent-state update reason")
    _require(isinstance(candidates, list) and candidates, "commit_update requires at least one candidate item")

    acknowledged = set(acknowledged_contradictions)
    unacknowledged = [
        c for c in find_conflicts(state, candidates) if (c["category"], c["label"]) not in acknowledged
    ]
    _require(not unacknowledged,
              "unacknowledged contradiction with existing persistent document state: "
              f"{[(c['category'], c['label']) for c in unacknowledged]}")

    latest = _latest_by_key(state)
    new_rows = list(state["items"])
    for candidate in candidates:
        _require(not (actor_kind == "model" and candidate["certainty"] == "established"),
                  "a model-derived persistent-state item cannot be marked 'established' without human confirmation")
        validate_source_ref(candidate["source"], document_id=state["document_id"])
        key = (candidate["category"], candidate["label"])
        existing = latest.get(key)
        item_id = deterministic_id("document-state-item", state["document_id"], candidate["category"], candidate["label"])
        new_row = {
            "item_id": item_id, "version": (existing["version"] + 1) if existing else 1,
            "prior_version": existing["version"] if existing else None,
            "category": candidate["category"], "label": candidate["label"], "value": candidate["value"],
            "certainty": candidate["certainty"], "source": candidate["source"], "reason": candidate["reason"],
            "actor": actor, "actor_kind": actor_kind, "committed_in_chapter_node_id": chapter_node_id,
        }
        new_rows.append(new_row)
        latest[key] = new_row

    new_state = {"schema_version": SCHEMA_VERSION, "stage": STAGE, "document_id": state["document_id"],
                 "revision": state["revision"] + 1, "items": new_rows}
    validate_document_state(new_state)
    return copy.deepcopy(new_state)


def effective_fingerprint(state):
    """Fingerprint of only the current latest view (what actually gets
    rendered/sent), not the full version history -- mirrors
    glossary.effective_fingerprint's "only applied meaning is a dependency"
    rule, so cache identity tracks exactly what was supplied to the model."""
    validate_document_state(state)
    latest = sorted(_latest_by_key(state).values(), key=lambda r: (r["category"], r["label"]))
    return fingerprint([
        {k: r[k] for k in ("category", "label", "value", "certainty", "source")} for r in latest
    ])


def render_persistent_state_text(state):
    """Bounded, labelled rendering of the current latest state for the
    PERSISTENT DOCUMENT STATE context layer. Always literal source-backed
    data, never a generated summary; certainty is carried explicitly so
    'likely'/'unresolved' items are never read by the model as established
    fact."""
    validate_document_state(state)
    latest = sorted(_latest_by_key(state).values(), key=lambda r: (r["category"], r["label"]))
    payload = [
        {"category": r["category"], "label": r["label"], "value": r["value"], "certainty": r["certainty"],
         "source": r["source"]}
        for r in latest
    ]
    return (
        f"Persistent document state (revision {state['revision']}; JSON; certainty is one of "
        "established/likely/unresolved -- treat 'likely' and 'unresolved' items as provisional, "
        "never as an established fact; each item's `source` names the chapter node and translation "
        "unit span it was introduced or last refined on): " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )
