"""Validated action builders for local human source and glossary forms."""

from __future__ import annotations

from .glossary import fingerprint, propose_rule, review_rule, validate_glossary
from .segmentation import validate_structure


class UIDecisionError(ValueError):
    pass


def _human_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise UIDecisionError(f"{label} is required (maximum 500 characters)")
    return value.strip()


def source_options(structure: dict) -> dict:
    validate_structure(structure)
    return {
        "revision": structure["revision"]["id"],
        "readings": [
            {
                "page_id": reading["page_id"],
                "page_number": reading["page_number"],
                "status": reading["status"],
                "selected": reading["selected"],
                "alternatives": [
                    {"origin": item["origin"], "candidate_hash": item["candidate_hash"],
                     "text": item["text"][:20000], "usable": item["usable"],
                     "warnings": item["warnings"]}
                    for item in reading["alternatives"]
                ],
            }
            for reading in structure["readings"]
        ],
    }


def source_decisions(structure: dict, request: dict) -> dict:
    validate_structure(structure)
    if request.get("expected_revision") != structure["revision"]["id"]:
        raise UIDecisionError("source structure changed; reload the page options")
    page_id = request.get("page_id")
    candidate_hash = request.get("candidate_hash")
    actor = _human_text(request.get("actor"), "human actor")
    reason = _human_text(request.get("reason"), "source reason")
    reading = next((r for r in structure["readings"] if r["page_id"] == page_id), None)
    if reading is None:
        raise UIDecisionError("unknown page")
    candidate = next((item for item in reading["alternatives"]
                      if item["candidate_hash"] == candidate_hash), None)
    if candidate is None or not candidate["usable"] or not candidate["text"]:
        raise UIDecisionError("source candidate is unavailable or stale")
    decisions = {item["page_id"]: item["decision"] for item in structure["readings"]
                 if item["decision"] is not None}
    decisions[page_id] = {"origin": candidate["origin"], "candidate_hash": candidate_hash,
                          "actor": actor, "actor_kind": "human", "reason": reason}
    return decisions


def glossary_options(structure: dict, glossary: dict) -> dict:
    validate_structure(structure)
    validate_glossary(glossary)
    latest = {}
    for row in glossary["rules"]:
        current = latest.get(row["rule_id"])
        if current is None or row["version"] > current["version"]:
            latest[row["rule_id"]] = row
    return {
        "units": [{"unit_id": unit["unit_id"], "page_id": unit["page_id"],
                   "language": unit["language"], "text": unit["text"][:20000],
                   "source_char_start": unit["source_char_start"]}
                  for unit in structure["units"]],
        "rules": [{"rule_id": row["rule_id"], "version": row["version"],
                   "fingerprint": fingerprint(row), "status": row["status"],
                   "source_term": row["source_term"], "target_term": row["target_term"],
                   "loaded": row["loaded"], "scope": row["scope"]}
                  for row in latest.values()],
    }


def glossary_action(structure: dict, glossary: dict, request: dict) -> dict:
    validate_structure(structure)
    validate_glossary(glossary)
    kind = request.get("kind")
    if kind == "propose":
        unit = next((item for item in structure["units"] if item["unit_id"] == request.get("unit_id")), None)
        if unit is None:
            raise UIDecisionError("unknown or unresolved unit")
        term = _human_text(request.get("source_term"), "source term")
        target = _human_text(request.get("target_term"), "target term")
        occurrence = request.get("occurrence", 1)
        if type(occurrence) is not int or occurrence < 1:
            raise UIDecisionError("occurrence must be a positive integer")
        matches = []
        offset = unit["text"].find(term)
        while offset >= 0:
            matches.append(offset)
            offset = unit["text"].find(term, offset + 1)
        if occurrence > len(matches):
            raise UIDecisionError("source term occurrence was not found in the unit")
        start = unit["source_char_start"] + matches[occurrence - 1]
        scope_name = request.get("scope", "unit")
        if scope_name not in ("unit", "document", "global"):
            raise UIDecisionError("invalid glossary scope")
        scope = {"document_ids": [structure["document_id"]] if scope_name == "document" else [],
                 "unit_ids": [unit["unit_id"]] if scope_name == "unit" else []}
        loaded = request.get("loaded", False)
        if type(loaded) is not bool:
            raise UIDecisionError("loaded must be a boolean")
        action = {"action": "propose", "unit_id": unit["unit_id"],
                  "source_language": unit["language"], "source_char_start": start,
                  "source_char_end": start + len(term), "target_term": target,
                  "scope": scope, "loaded": loaded}
        propose_rule(glossary, structure, unit["unit_id"], unit["language"], start,
                     start + len(term), target, scope=scope, loaded=loaded)
        return action
    if kind == "review":
        rule_id = request.get("rule_id")
        rows = [row for row in glossary["rules"] if row["rule_id"] == rule_id]
        if not rows:
            raise UIDecisionError("unknown glossary rule")
        current = max(rows, key=lambda row: row["version"])
        if request.get("expected_version") != current["version"] or request.get("expected_fingerprint") != fingerprint(current):
            raise UIDecisionError("glossary rule changed; reload before reviewing")
        actor = _human_text(request.get("actor"), "human actor")
        reason = _human_text(request.get("reason"), "review reason")
        status = request.get("status")
        if status not in ("approved", "rejected"):
            raise UIDecisionError("choose approve or reject")
        target = request.get("target_term")
        if target is not None:
            target = _human_text(target, "target term")
        action = {"action": "review", "rule_id": rule_id,
                  "expected_version": current["version"],
                  "expected_rule_fingerprint": fingerprint(current),
                  "actor": actor, "actor_kind": "human", "reason": reason, "status": status}
        if target is not None and target != current["target_term"]:
            action["target_term"] = target
        review_rule(glossary, rule_id, current["version"], fingerprint(current), actor,
                    "human", reason, status, target_term=action.get("target_term"))
        return action
    raise UIDecisionError("unknown terminology action")
