"""Segmentation: turn a resolved source reading into versioned, source-linked
translation units, plus a deterministic continuity check and revision tracking.
Never decides translation, terminology or scholarly meaning.
"""
from __future__ import annotations

import copy
from typing import Optional

from .records import Document
from .source_reading import (
    StructureError, build_readings, fingerprint, integer, nonempty, require, sha,
    strings, validate_candidate, validate_decision,
)
from .store import deterministic_id

SCHEMA_VERSION = 1
STAGE = "structure@1"

_READING_FIELDS = {
    "reading_id", "version", "prior_version", "document_id", "page_id", "page_number",
    "status", "reasons", "text", "text_hash", "selected", "decision", "alternatives",
}
_UNIT_FIELDS = {
    "unit_id", "unit_version", "reading_id", "reading_version", "reading_text_hash",
    "document_id", "page_id", "language", "source_char_start", "source_char_end", "text",
    "anchors", "status", "warnings", "predecessor_unit_ids",
}


def _default_line_spans(text: str) -> list:
    spans = []
    start = 0
    for idx, ch in enumerate(text):
        if ch == "\n":
            if idx > start:
                spans.append((start, idx))
            start = idx + 1
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _validate_boundaries(text: str, boundary_list) -> list:
    if not isinstance(boundary_list, list) or not boundary_list:
        raise StructureError("boundaries for a page must be a nonempty list of [start,end] pairs")
    spans = []
    for item in boundary_list:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise StructureError("boundary must be a [start,end] pair")
        start, end = item
        if (
            isinstance(start, bool) or isinstance(end, bool)
            or not isinstance(start, int) or not isinstance(end, int)
        ):
            raise StructureError("boundary start/end must be integers")
        if start < 0 or end > len(text) or end <= start:
            raise StructureError("boundary span is out of bounds")
        spans.append((start, end))
    spans.sort()
    for i in range(1, len(spans)):
        if spans[i][0] < spans[i - 1][1]:
            raise StructureError("boundaries must not overlap")
    return spans


def _intersecting_anchors(anchors: list, start: int, end: int) -> list:
    return [a for a in anchors if a["source_char_start"] < end and a["source_char_end"] > start]


def _build_units_for_reading(
    reading: dict, boundary_spans: Optional[list], previous_units: Optional[list], document_warnings: list,
) -> list:
    text = reading["text"]
    spans = boundary_spans if boundary_spans is not None else _default_line_spans(text)
    previous_units = previous_units or []
    previous_by_id = {pu["unit_id"]: pu for pu in previous_units}
    warnings = ["unreviewed_translation"] + list(reading.get("selected_warnings", [])) + list(document_warnings)
    units = []
    for start, end in spans:
        unit_id = deterministic_id(
            "unit", reading["document_id"], reading["page_id"], reading["reading_id"],
            str(reading["version"]), str(start), str(end),
        )
        overlapping = [
            pu for pu in previous_units
            if pu["source_char_start"] < end and pu["source_char_end"] > start
        ]
        existing = previous_by_id.get(unit_id)
        if existing is not None:
            unit_version = existing["unit_version"]
            predecessor_unit_ids = existing.get("predecessor_unit_ids", [])
        else:
            unit_version = max((pu["unit_version"] for pu in overlapping), default=0) + 1
            predecessor_unit_ids = [pu["unit_id"] for pu in overlapping if pu["unit_id"] != unit_id]
        units.append({
            "unit_id": unit_id,
            "unit_version": unit_version,
            "reading_id": reading["reading_id"],
            "reading_version": reading["version"],
            "reading_text_hash": reading["text_hash"],
            "document_id": reading["document_id"],
            "page_id": reading["page_id"],
            "language": reading["language"],
            "source_char_start": start,
            "source_char_end": end,
            "text": text[start:end],
            "anchors": _intersecting_anchors(reading["selected_anchors"], start, end),
            "status": "unreviewed",
            "warnings": warnings,
            "predecessor_unit_ids": predecessor_unit_ids,
        })
    return units


def check_continuity(reading: dict, units: list) -> list:
    """Deterministic typed findings: gaps, overlaps, duplicate coverage, mismatched
    text or invalid anchors. Gaps of only line separators may remain unsegmented."""
    findings = []
    text = reading["text"] or ""
    spans = sorted((u["source_char_start"], u["source_char_end"], u["unit_id"]) for u in units)

    seen_spans = set()
    for start, end, unit_id in spans:
        key = (start, end)
        if key in seen_spans:
            findings.append({"type": "duplicate_unit", "unit_id": unit_id, "start": start, "end": end})
        seen_spans.add(key)

    for i in range(1, len(spans)):
        prev_start, prev_end, prev_id = spans[i - 1]
        cur_start, cur_end, cur_id = spans[i]
        if cur_start < prev_end:
            findings.append({
                "type": "overlap", "unit_ids": [prev_id, cur_id],
                "start": cur_start, "end": min(cur_end, prev_end),
            })

    covered = bytearray(len(text))
    for start, end, _ in spans:
        for i in range(max(0, start), min(end, len(text))):
            covered[i] = 1
    gap_positions = [i for i, ch in enumerate(text) if not covered[i] and not ch.isspace()]
    i = 0
    while i < len(gap_positions):
        j = i
        while j + 1 < len(gap_positions) and gap_positions[j + 1] == gap_positions[j] + 1:
            j += 1
        findings.append({"type": "gap", "start": gap_positions[i], "end": gap_positions[j] + 1})
        i = j + 1

    for u in units:
        if text[u["source_char_start"]:u["source_char_end"]] != u["text"]:
            findings.append({"type": "mismatched_text", "unit_id": u["unit_id"]})
        for a in u["anchors"]:
            a_start, a_end = a["source_char_start"], a["source_char_end"]
            if a_start < 0 or a_end > len(text) or a_end <= a_start:
                findings.append({"type": "invalid_anchor", "unit_id": u["unit_id"]})

    return findings


def _validate_previous_structure(previous: Optional[dict], document: Document) -> Optional[dict]:
    if previous is None:
        return None
    if not isinstance(previous, dict):
        raise StructureError("previous structure must be an object")
    validate_structure(previous)
    if previous.get("document_id") != document.document_id or previous.get("pdf_hash") != document.input_hash:
        raise StructureError("previous structure does not match this document/PDF lineage")
    return previous


def build_structure(document: Document, ocr_bundle=None, decisions=None, boundaries=None, previous=None) -> dict:
    previous = _validate_previous_structure(previous, document)

    if boundaries is None:
        boundaries = {}
    if not isinstance(boundaries, dict):
        raise StructureError("boundaries must be an object mapping page_id to spans")
    known_page_ids = {p.page_id for p in document.pages}
    for page_id in boundaries:
        if page_id not in known_page_ids:
            raise StructureError("boundaries reference an unknown page_id")

    previous_readings = previous.get("readings") if previous else None
    readings_raw = build_readings(
        document, ocr_bundle=ocr_bundle, decisions=decisions, previous_readings=previous_readings,
    )
    input_hash = fingerprint({"document": document.to_dict(), "ocr": ocr_bundle,
                              "decisions": decisions, "boundaries": boundaries})

    for reading in readings_raw:
        reading["language"] = document.language
        selected_candidate = next(
            (
                c for c in reading["alternatives"]
                if reading["selected"] is not None
                and c["origin"] == reading["selected"]["origin"]
                and c["candidate_hash"] == reading["selected"]["candidate_hash"]
            ),
            None,
        )
        reading["selected_anchors"] = selected_candidate["anchors"] if selected_candidate else []
        reading["selected_warnings"] = selected_candidate["warnings"] if selected_candidate else []

    previous_units_by_page = {}
    if previous:
        for u in previous.get("units", []):
            previous_units_by_page.setdefault(u["page_id"], []).append(u)

    all_units = []
    continuity_findings = []
    for reading in readings_raw:
        if reading["status"] != "resolved" and reading["page_id"] in boundaries:
            raise StructureError("boundaries require a resolved reading")
        if reading["status"] != "resolved":
            continue
        page_boundary = boundaries.get(reading["page_id"])
        boundary_spans = (
            _validate_boundaries(reading["text"], page_boundary) if page_boundary is not None else None
        )
        units = _build_units_for_reading(
            reading, boundary_spans, previous_units_by_page.get(reading["page_id"]), document.warnings,
        )
        all_units.extend(units)
        findings = check_continuity(reading, units)
        require(not findings, "boundary plan violates source continuity")
        continuity_findings.extend(findings)

    readings = []
    for reading in readings_raw:
        reading = dict(reading)
        reading.pop("language", None)
        reading.pop("selected_anchors", None)
        reading.pop("selected_warnings", None)
        readings.append(reading)

    if previous is not None and previous["input_hash"] == input_hash:
        return copy.deepcopy(previous)
    parent_revision = previous["revision"]["id"] if previous else None
    revision_id = deterministic_id("structure-revision", input_hash, parent_revision or "")

    history = list(previous.get("history", [])) if previous else []
    if previous is not None:
        history = history + [{
            "revision_id": previous["revision"]["id"],
            "revision_number": previous["revision"]["number"],
            "parent_revision": previous["revision"]["parent_revision"],
            "input_hash": previous["input_hash"],
            "readings": previous["readings"],
            "units": previous["units"],
            "continuity": previous["continuity"],
        }]

    result = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "document_id": document.document_id,
        "document_version": document.document_version,
        "pdf_hash": document.input_hash,
        "source_uri": document.source_uri,
        "language": document.language,
        "input_hash": input_hash,
        "revision": {"id": revision_id, "number": len(history) + 1, "parent_revision": parent_revision},
        "readings": readings,
        "units": all_units,
        "continuity": continuity_findings,
        "history": history,
    }
    validate_structure(result)
    return copy.deepcopy(result)



def _selected(reading):
    if reading['selected'] is None:
        return None
    return next((c for c in reading['alternatives'] if
                 {k:c[k] for k in ('origin', 'candidate_hash')} == reading['selected']), None)


def _validate_reading(r, document_id, pdf_hash):
    require(isinstance(r, dict) and set(r) == _READING_FIELDS, 'invalid persisted reading shape')
    require(r['document_id'] == document_id and nonempty(r['page_id']) and integer(r['page_number'])
            and integer(r['version']) and (r['prior_version'] is None or
                 integer(r['prior_version']) and r['prior_version'] < r['version']), 'invalid reading identity/version')
    require(r['reading_id'] == deterministic_id('structure-reading', document_id, r['page_id']),
            'reading identity mismatch')
    require(isinstance(r['alternatives'], list) and r['alternatives'], 'missing reading evidence')
    origins = set()
    geometry = None
    for c in r['alternatives']:
        validate_candidate(c)
        require(c['document_id'] == document_id and c['page_id'] == r['page_id']
                and c['page_number'] == r['page_number'] and c['pdf_hash'] == pdf_hash,
                'reading evidence lineage mismatch')
        require(c['origin'] not in origins, 'duplicate source alternative')
        origins.add(c['origin'])
        box = (c['pdf_width'], c['pdf_height'])
        require(geometry is None or geometry == box, 'source alternatives geometry mismatch')
        geometry = box
    require('digital' in origins, 'digital extraction evidence missing')
    if r['status'] == 'resolved':
        validate_decision(r['decision'])
        require(isinstance(r['selected'], dict) and set(r['selected']) == {'origin', 'candidate_hash'},
                'invalid selected evidence reference')
        c = _selected(r)
        require(c is not None and c['usable'] and r['selected'] ==
                {k:r['decision'][k] for k in ('origin', 'candidate_hash')}, 'source decision binding mismatch')
        require(r['text'] == c['text'] and r['text_hash'] == c['text_hash'] and r['reasons'] == [],
                'resolved reading text/hash mismatch')
    else:
        require(r['status'] == 'unresolved' and r['decision'] is None and r['selected'] is None
                and r['text'] is None and r['text_hash'] is None, 'invalid unresolved reading')
        expected = 'unreviewed_source' if any(c['usable'] for c in r['alternatives']) else 'missing_source'
        require(r['reasons'] == [expected], 'unresolved reason mismatch')


def _validate_snapshot(readings, units, continuity, data):
    require(isinstance(readings, list) and isinstance(units, list) and isinstance(continuity, list),
            'invalid structure collections')
    index, pages, numbers = {}, set(), set()
    for r in readings:
        _validate_reading(r, data['document_id'], data['pdf_hash'])
        require(r['page_id'] not in pages and r['page_number'] not in numbers, 'duplicate reading page')
        pages.add(r['page_id']); numbers.add(r['page_number'])
        index[r['reading_id']] = r
    ids, by_reading = set(), {}
    for u in units:
        require(isinstance(u, dict) and set(u) == _UNIT_FIELDS, 'invalid persisted unit shape')
        require(nonempty(u['unit_id']) and u['unit_id'] not in ids and integer(u['unit_version'])
                and nonempty(u['reading_id']) and integer(u['reading_version']), 'invalid/duplicate unit identity')
        ids.add(u['unit_id'])
        r = index.get(u['reading_id'])
        require(r is not None and r['status'] == 'resolved' and r['version'] == u['reading_version'],
                'unit references unresolved/unknown reading')
        start, end = u['source_char_start'], u['source_char_end']
        require(integer(start, 0) and integer(end) and start < end <= len(r['text']), 'invalid unit span')
        require(u['document_id'] == r['document_id'] and u['page_id'] == r['page_id']
                and u['language'] == data['language'] and u['reading_text_hash'] == r['text_hash']
                and u['text'] == r['text'][start:end], 'unit source binding mismatch')
        require(u['unit_id'] == deterministic_id('unit', data['document_id'], r['page_id'], r['reading_id'],
                str(r['version']), str(start), str(end)), 'unit identity mismatch')
        c = _selected(r)
        require(u['anchors'] == _intersecting_anchors(c['anchors'], start, end), 'unit anchors mismatch')
        require(u['status'] == 'unreviewed' and strings(u['warnings'])
                and 'unreviewed_translation' in u['warnings']
                and set(c['warnings']) <= set(u['warnings']), 'unit review/warnings mismatch')
        require(strings(u['predecessor_unit_ids']) and len(set(u['predecessor_unit_ids'])) == len(u['predecessor_unit_ids']),
                'invalid predecessor identities')
        by_reading.setdefault(r['reading_id'], []).append(u)
    findings = []
    for r in readings:
        findings.extend(check_continuity(r, by_reading.get(r['reading_id'], [])))
    require(continuity == findings and not findings, 'persisted source continuity failure')
    return index, {u['unit_id']:u for u in units}


def validate_structure(data):
    """Validate current and historical snapshots with the same evidence checks.

    Detect inconsistent/tampered records, not coordinated rewriting of all source
    evidence or authenticity of the asserted human actor. No files or network.
    """
    fields = {'schema_version','stage','document_id','document_version','pdf_hash','source_uri',
              'language','input_hash','revision','readings','units','continuity','history'}
    require(isinstance(data, dict) and set(data) == fields, 'invalid structure shape')
    require(type(data['schema_version']) is int and data['schema_version'] == SCHEMA_VERSION
            and data['stage'] == STAGE and nonempty(data['document_id']) and integer(data['document_version'])
            and sha(data['pdf_hash']) and sha(data['input_hash']) and nonempty(data['source_uri'])
            and nonempty(data['language']), 'invalid structure identity/stage')
    rev = data['revision']
    require(isinstance(rev, dict) and set(rev) == {'id','number','parent_revision'}
            and nonempty(rev['id']) and integer(rev['number']), 'invalid structure revision')
    require(isinstance(data['history'], list) and rev['number'] == len(data['history']) + 1,
            'invalid structure history count')
    snapshots = data['history'] + [dict(revision_id=rev['id'], revision_number=rev['number'],
                                       parent_revision=rev['parent_revision'], input_hash=data['input_hash'],
                                       readings=data['readings'], units=data['units'], continuity=data['continuity'])]
    previous_id, previous_readings, previous_units, seen = None, {}, {}, set()
    for number, snap in enumerate(snapshots, 1):
        require(isinstance(snap, dict) and set(snap) == {'revision_id','revision_number','parent_revision',
                'input_hash','readings','units','continuity'}, 'invalid history snapshot')
        require(integer(snap['revision_number']) and snap['revision_number'] == number
                and sha(snap['input_hash']) and snap['parent_revision'] == previous_id
                and snap['revision_id'] == deterministic_id('structure-revision', snap['input_hash'], previous_id or ''),
                'revision history linkage mismatch')
        require(snap['revision_id'] not in seen, 'duplicate history revision')
        seen.add(snap['revision_id'])
        readings, units = _validate_snapshot(snap['readings'], snap['units'], snap['continuity'], data)
        require(not previous_readings or set(readings) == set(previous_readings), 'reading pages changed in history')
        for rid, r in readings.items():
            old = previous_readings.get(rid)
            if old is None:
                require(r['version'] == 1 and r['prior_version'] is None, 'invalid initial reading version')
            elif all(r[k] == old[k] for k in r if k not in ('version','prior_version')):
                require(r['version'] == old['version'] and r['prior_version'] == old['prior_version'],
                        'unchanged reading version mismatch')
            else:
                require(r['version'] == old['version'] + 1 and r['prior_version'] == old['version'],
                        'changed reading prior version mismatch')
        for uid, u in units.items():
            old = previous_units.get(uid)
            if old is not None:
                require(u == old, 'unchanged unit mutated')
            else:
                overlaps = [p for p in previous_units.values() if p['page_id'] == u['page_id']
                            and p['source_char_start'] < u['source_char_end'] and p['source_char_end'] > u['source_char_start']]
                require(u['predecessor_unit_ids'] == [p['unit_id'] for p in overlaps]
                        and u['unit_version'] == max((p['unit_version'] for p in overlaps), default=0) + 1,
                        'unit predecessor/version mismatch')
        previous_id, previous_readings, previous_units = snap['revision_id'], readings, units
