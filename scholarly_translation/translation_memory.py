"""Exact source-bound, human-approved translation memory.

Current entries are manually supplied text, not product model output. No
fuzzy search, embeddings or real translation cache: exact unit/source binding
plus effective applicable-approved-policy fingerprint only.
"""
from __future__ import annotations
import copy

from .segmentation import validate_structure
from .source_reading import fingerprint, integer, nonempty, sha, text_hash
from .glossary import GlossaryError, validate_resolution
from .store import deterministic_id

SCHEMA_VERSION = 1
STAGE = "approved-memory@1"

_ENTRY_FIELDS = {
    "entry_id", "unit_id", "document_id", "page_id", "reading_id", "reading_version",
    "unit_version", "source_text", "source_text_hash", "policy_fingerprint",
    "target_text", "actor", "actor_kind", "reason", "source_unit", "source_uri", "pdf_hash",
    "source_binding_hash", "policy_dependencies", "status", "target_language",
}


class MemoryError(ValueError):
    """Invalid translation-memory contract input; messages exclude supplied source text."""


def _require(condition, message):
    if not condition:
        raise MemoryError(message)


def new_store():
    return {"schema_version": SCHEMA_VERSION, "stage": STAGE, "revision": 0, "entries": []}


def validate_memory(data):
    _require(isinstance(data, dict) and set(data) == {"schema_version", "stage", "revision", "entries"},
              "invalid memory shape")
    _require(isinstance(data["entries"], list), "memory entries must be a list")
    _require(type(data["schema_version"]) is int and data["schema_version"] == SCHEMA_VERSION and data["stage"] == STAGE
              and integer(data["revision"], 0) and data["revision"] == len(data["entries"]),
              "invalid memory identity/stage")

    seen = set()
    seen_keys = set()
    for entry in data["entries"]:
        _require(isinstance(entry, dict) and set(entry) == _ENTRY_FIELDS, "invalid memory entry shape")
        _require(nonempty(entry["entry_id"]) and entry["entry_id"] not in seen, "duplicate memory entry identity")
        seen.add(entry["entry_id"])
        _require(nonempty(entry["unit_id"]) and nonempty(entry["document_id"]) and nonempty(entry["page_id"])
                  and nonempty(entry["reading_id"]) and integer(entry["reading_version"])
                  and integer(entry["unit_version"]), "invalid memory entry identity fields")
        _require(isinstance(entry["source_text"], str) and entry["source_text"] != ""
                  and entry["source_text_hash"] == text_hash(entry["source_text"]),
                  "invalid memory entry source text/hash")
        _require(sha(entry["policy_fingerprint"]), "invalid memory entry policy fingerprint")
        _require(isinstance(entry["target_text"], str) and entry["target_text"].strip() != "",
                  "invalid memory entry target text")
        _require(nonempty(entry["actor"]) and entry["actor_kind"] == "human" and nonempty(entry["reason"]),
                  "invalid memory entry human approval")
        _require(entry["status"] == "approved" and entry["target_language"] == "he"
                 and nonempty(entry["source_uri"]) and sha(entry["pdf_hash"]), "invalid approved memory provenance")
        unit = entry["source_unit"]
        from .segmentation import _UNIT_FIELDS
        _require(isinstance(unit, dict) and set(unit) == _UNIT_FIELDS, "invalid memory source unit")
        _require(all(unit[k] == entry[k] for k in
                 ("unit_id", "unit_version", "document_id", "page_id", "reading_id", "reading_version"))
                 and unit["text"] == entry["source_text"] and sha(unit["reading_text_hash"])
                 and integer(unit["source_char_start"], 0) and integer(unit["source_char_end"])
                 and unit["source_char_end"] - unit["source_char_start"] == len(unit["text"]),
                 "memory source unit binding mismatch")
        _require(unit["unit_id"] == deterministic_id("unit", unit["document_id"], unit["page_id"],
                 unit["reading_id"], str(unit["reading_version"]), str(unit["source_char_start"]),
                 str(unit["source_char_end"])) and unit["status"] == "unreviewed",
                 "memory source unit identity mismatch")
        _require(entry["source_binding_hash"] == fingerprint({"unit":unit, "source_uri":entry["source_uri"],
                                                             "pdf_hash":entry["pdf_hash"]}),
                 "memory source binding fingerprint mismatch")
        key = (entry["source_binding_hash"], entry["policy_fingerprint"])
        _require(key not in seen_keys, "duplicate approved memory dependency key")
        seen_keys.add(key)
        resolution = dict(schema_version=1, stage="terminology-resolution@1", unit_id=unit["unit_id"],
                          unit_hash=fingerprint(unit), approved_rules=entry["policy_dependencies"],
                          proposed_rules=[], status="ready", warnings=[], policy_fingerprint=entry["policy_fingerprint"])
        _validate_resolution(resolution, unit)
        _require(entry["entry_id"] == deterministic_id(
            "memory-entry", entry["source_binding_hash"], entry["policy_fingerprint"], text_hash(entry["target_text"])),
            "memory entry identity mismatch")


def _validate_resolution(resolution, unit):
    try:
        validate_resolution(resolution, unit)
    except GlossaryError:
        raise MemoryError("invalid terminology resolution for memory") from None


def _binding_hash(unit, structure):
    return fingerprint({"unit":unit, "source_uri":structure["source_uri"], "pdf_hash":structure["pdf_hash"]})


def remember(store, structure, unit_id, resolution, target_text, actor, actor_kind, reason):
    """Add a manually supplied, explicitly human-approved target text.

    Requires a `ready` terminology resolution (see glossary.resolve_applicable)
    for the same unit; refuses to record anything under conflicting policy.
    """
    validate_memory(store)
    validate_structure(structure)
    _require(actor_kind == "human", "memory entries require an explicit human approval")
    _require(nonempty(actor) and nonempty(reason), "invalid memory actor/reason")
    _require(isinstance(target_text, str) and target_text.strip() != "", "invalid memory target text")

    unit = next((u for u in structure["units"] if u["unit_id"] == unit_id), None)
    _require(unit is not None, "unknown unit for memory entry")
    _validate_resolution(resolution, unit)
    _require(resolution["status"] == "ready", "terminology policy is not ready for a memory entry")

    source_text_hash = text_hash(unit["text"])
    binding = _binding_hash(unit, structure)
    entry_id = deterministic_id("memory-entry", binding, resolution["policy_fingerprint"], text_hash(target_text))
    _require(not any(e["entry_id"] == entry_id for e in store["entries"]),
              "memory entry already recorded for this unit and policy")

    entry = {
        "entry_id": entry_id, "unit_id": unit_id, "document_id": unit["document_id"],
        "page_id": unit["page_id"], "reading_id": unit["reading_id"], "reading_version": unit["reading_version"],
        "unit_version": unit["unit_version"], "source_text": unit["text"], "source_text_hash": source_text_hash,
        "policy_fingerprint": resolution["policy_fingerprint"], "target_text": target_text,
        "actor": actor, "actor_kind": "human", "reason": reason,
        "source_unit": unit, "source_uri": structure["source_uri"], "pdf_hash": structure["pdf_hash"],
        "source_binding_hash": binding, "policy_dependencies": resolution["approved_rules"],
        "status": "approved", "target_language": "he",
    }
    new_store = {"schema_version": SCHEMA_VERSION, "stage": STAGE,
                 "revision": store["revision"] + 1, "entries": store["entries"] + [entry]}
    validate_memory(new_store)
    return copy.deepcopy(new_store)


def lookup(store, structure, unit_id, resolution):
    """Exact reuse lookup: miss|reusable|stale_dependencies|needs_human with reasons."""
    validate_memory(store)
    validate_structure(structure)
    unit = next((u for u in structure["units"] if u["unit_id"] == unit_id), None)
    _require(unit is not None, "unknown unit for memory lookup")
    _validate_resolution(resolution, unit)
    if resolution["status"] != "ready":
        return {"outcome": "needs_human", "reasons": ["terminology_policy_not_ready"]}

    source_text_hash = text_hash(unit["text"])
    matches = [e for e in store["entries"] if e["unit_id"] == unit_id and e["source_text_hash"] == source_text_hash]
    if not matches:
        return {"outcome": "miss", "reasons": ["no_prior_approved_entry"]}
    exact = [e for e in matches if e["source_binding_hash"] == _binding_hash(unit, structure)
             and e["policy_fingerprint"] == resolution["policy_fingerprint"]]
    if exact:
        latest = exact[-1]
        return {"outcome": "reusable", "entry_id": latest["entry_id"], "target_text": latest["target_text"]}
    return {"outcome": "stale_dependencies", "reasons": ["source_or_policy_dependency_changed"]}
