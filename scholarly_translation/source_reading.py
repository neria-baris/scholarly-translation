"""Pure evidence validation and explicit human source selection.

Hashes check internal consistency; they do not authenticate a human or read
image bytes. Source files stay immutable; OCR failures remain visible evidence.
"""
from __future__ import annotations

import hashlib
import copy
import json
import math
import re
from urllib.parse import urlparse

from .records import Document
from .store import deterministic_id


class StructureError(ValueError):
    """Invalid contract input; messages contain no private input values."""


def require(condition, message):
    if not condition:
        raise StructureError(message)


def integer(value, minimum=1):
    return type(value) is int and value >= minimum


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def fingerprint(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise StructureError("input must contain finite JSON values") from None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def positive(value):
    return finite_number(value) and value > 0


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def strings(value):
    return isinstance(value, list) and all(nonempty(x) for x in value)


def validate_image(image, absent_allowed=False):
    if image is None:
        require(absent_allowed, "image evidence is required")
        return
    require(isinstance(image, dict) and set(image) == {"uri", "hash", "width", "height"},
            "invalid image evidence shape")
    try:
        local = nonempty(image["uri"]) and urlparse(image["uri"]).scheme == "file"
    except ValueError:
        local = False
    require(local
            and sha(image["hash"]) and positive(image["width"]) and positive(image["height"]),
            "invalid image evidence reference or dimensions")


def validate_box(box, width, height):
    require(isinstance(box, list) and len(box) == 4 and all(
        finite_number(v) for v in box), "invalid anchor box")
    x0, top, x1, bottom = box
    require(0 <= x0 < x1 <= width and 0 <= top < bottom <= height,
            "anchor box outside evidence bounds")


def validate_anchors(text, anchors, origin, width, height, image):
    require(isinstance(anchors, list), "anchors must be a list")
    spans, ids = [], set()
    for a in anchors:
        common = {"kind", "source_char_start", "source_char_end"}
        if origin == "digital":
            expected = common | {"segment_id", "region_id", "bbox"}
        elif origin == "digital-text":
            expected = common | {"segment_id", "region_id", "node_kind", "node_level"}
        else:
            expected = common | {"text", "confidence", "pixel_bbox", "pdf_bbox", "image_uri", "image_hash"}
        require(isinstance(a, dict) and set(a) == expected, "invalid source anchor shape")
        start, end = a["source_char_start"], a["source_char_end"]
        require(integer(start, 0) and integer(end) and start < end <= len(text), "invalid source anchor span")
        spans.append((start, end))
        if origin == "digital":
            require(a["kind"] == "line" and nonempty(a["segment_id"]) and nonempty(a["region_id"]),
                    "invalid source region identity")
            require(a["segment_id"] not in ids, "duplicate source anchor")
            ids.add(a["segment_id"])
            validate_box(a["bbox"], width, height)
        elif origin == "digital-text":
            require(a["kind"] == "block" and nonempty(a["segment_id"]) and nonempty(a["region_id"]),
                    "invalid source region identity")
            require(a["segment_id"] not in ids, "duplicate source anchor")
            ids.add(a["segment_id"])
            # No pixel-to-PDF bbox mapping applies to this non-geometric origin.
            # node_kind vocabulary (NODE_KINDS) is owned and checked by
            # document_structure.py, not here.
            require(nonempty(a["node_kind"]), "invalid digital-text node kind")
            require(a["node_level"] is None or integer(a["node_level"], 1), "invalid digital-text node level")
        else:
            require(a["kind"] == "word" and nonempty(a["text"]) and text[start:end] == a["text"],
                    "word differs from source span")
            confidence = a["confidence"]
            require(finite_number(confidence)
                    and 0 <= confidence <= 100, "invalid word confidence")
            validate_box(a["pixel_bbox"], image["width"], image["height"])
            validate_box(a["pdf_bbox"], width, height)
            require(a["image_uri"] == image["uri"] and a["image_hash"] == image["hash"],
                    "anchor image reference mismatch")
            expected_box = [a["pixel_bbox"][i] / (image["width"] if i % 2 == 0 else image["height"])
                            * (width if i % 2 == 0 else height) for i in range(4)]
            require(all(abs(x-y) <= 1e-6 for x, y in zip(expected_box, a["pdf_bbox"])),
                    "pixel-to-PDF mapping mismatch")
    spans.sort()
    require(all(spans[i][0] >= spans[i-1][1] for i in range(1, len(spans))), "overlapping source anchors")
    cursor = 0
    for start, end in spans:
        require(not text[cursor:start].strip(), "source anchor coverage gap")
        cursor = end
    require(not text[cursor:].strip(), "source anchor coverage gap")


CANDIDATE_FIELDS = {"origin", "usable", "document_id", "page_id", "page_number", "pdf_hash",
                    "pdf_width", "pdf_height", "text", "text_hash", "warnings", "anchors",
                    "image", "error", "status", "provenance", "candidate_hash"}


def validate_candidate(c):
    require(isinstance(c, dict) and set(c) == CANDIDATE_FIELDS, "invalid evidence candidate shape")
    require(c["origin"] in ("digital", "ocr", "digital-text") and type(c["usable"]) is bool
            and nonempty(c["document_id"]) and nonempty(c["page_id"]) and integer(c["page_number"])
            and sha(c["pdf_hash"]), "invalid evidence candidate identity")
    if c["origin"] == "digital-text":
        require(c["pdf_width"] is None and c["pdf_height"] is None,
                "digital-text evidence must not carry PDF page geometry")
    else:
        require(positive(c["pdf_width"]) and positive(c["pdf_height"]), "invalid evidence candidate geometry")
    require(isinstance(c["text"], str) and c["text_hash"] == text_hash(c["text"])
            and strings(c["warnings"]) and c["status"] == "needs_human", "invalid evidence text/status")
    p = c["provenance"]
    require(isinstance(p, dict) and sha(p.get("base_extraction_hash")), "invalid extraction provenance")
    if c["origin"] == "digital":
        require(set(p) == {"base_extraction_hash", "stage"} and p["stage"] == "digital-pdf@1"
                and c["image"] is None and c["error"] is None, "invalid digital provenance")
    elif c["origin"] == "digital-text":
        require(set(p) == {"base_extraction_hash", "stage"} and p["stage"] == "digital-text-epub@1"
                and c["image"] is None and c["error"] is None, "invalid digital-text provenance")
    else:
        require(set(p) == {"base_extraction_hash", "stage", "language", "engine_version", "model_file_hash"}
                and p["stage"] == "local-ocr@1" and nonempty(p["language"])
                and nonempty(p["engine_version"]) and (p["model_file_hash"] is None or sha(p["model_file_hash"])),
                "invalid OCR provenance")
        if c["error"] is not None:
            require(isinstance(c["error"], dict) and set(c["error"]) == {"code", "message"}
                    and all(nonempty(v) for v in c["error"].values()), "invalid OCR error")
        validate_image(c["image"], absent_allowed=(c["error"] is not None and
                                                   c["error"]["code"] == "render_failed"))
        require(c["image"] is not None or c["text"] == "" and c["anchors"] == [],
                "missing image has unexpected source content")
    require(c["usable"] == (bool(c["text"].strip()) and c["error"] is None), "invalid evidence usability")
    validate_anchors(c["text"], c["anchors"], c["origin"], c["pdf_width"], c["pdf_height"], c["image"])
    require(c["candidate_hash"] == fingerprint({k: v for k, v in c.items() if k != "candidate_hash"}),
            "evidence fingerprint mismatch")


def _candidate(document, page, origin, text, anchors, warnings, image, error, provenance):
    c = dict(origin=origin, usable=bool(text.strip()) and error is None,
             document_id=document.document_id, page_id=page.page_id, page_number=page.page_number,
             pdf_hash=document.input_hash, pdf_width=page.width, pdf_height=page.height,
             text=text, text_hash=text_hash(text), warnings=warnings, anchors=anchors,
             image=image, error=error, status="needs_human", provenance=provenance)
    c["candidate_hash"] = fingerprint(c)
    validate_candidate(c)
    return c


def _digital_candidate(document, page):
    anchors = [dict(kind="line", segment_id=s.segment_id, region_id=s.region_id,
                    source_char_start=s.source_char_start, source_char_end=s.source_char_end,
                    bbox=list(s.bbox)) for s in page.segments]
    return _candidate(document, page, "digital", page.source_text, anchors, list(document.warnings), None, None,
                      {"base_extraction_hash": fingerprint(document.to_dict()),
                       "stage": f"{document.stage_id}@{document.stage_version}"})


def _digital_text_candidate(document, page):
    """Non-geometric EPUB source evidence: one 'block' anchor per discovered
    HTML block (Segment), carrying the block's already-known node_kind/
    node_level instead of PDF line geometry. pdf_width/pdf_height stay
    explicitly None (never a fabricated geometry value)."""
    anchors = [dict(kind="block", segment_id=s.segment_id, region_id=s.region_id,
                    source_char_start=s.source_char_start, source_char_end=s.source_char_end,
                    node_kind=s.node_kind, node_level=s.node_level) for s in page.segments]
    return _candidate(document, page, "digital-text", page.source_text, anchors, list(document.warnings), None, None,
                      {"base_extraction_hash": fingerprint(document.to_dict()),
                       "stage": f"{document.stage_id}@{document.stage_version}"})


def validate_ocr_bundle(document, bundle):
    """Gate 3 consumer; validates declared evidence, never opens image files."""
    require(isinstance(bundle, dict) and type(bundle.get("schema_version")) is int
            and bundle["schema_version"] == 1 and bundle.get("stage") == "local-ocr@1",
            "unsupported OCR schema/stage")
    require(bundle.get("document_id") == document.document_id and bundle.get("source_hash") == document.input_hash
            and bundle.get("base_extraction_hash") == fingerprint(document.to_dict()), "OCR document lineage mismatch")
    require(nonempty(bundle.get("engine_version")) and bundle.get("language") == document.language
            and (bundle.get("model_file_hash") is None or sha(bundle["model_file_hash"])), "invalid OCR engine provenance")
    require(isinstance(bundle.get("pages"), list), "OCR pages must be a list")
    by_id, result = {p.page_id: p for p in document.pages}, {}
    for entry in bundle["pages"]:
        require(isinstance(entry, dict) and isinstance(entry.get("page_id"), str), "invalid OCR page entry")
        page_id = entry["page_id"]
        require(page_id in by_id and page_id not in result, "unknown/duplicate OCR page")
        page = by_id[page_id]
        require(integer(entry.get("page_number")) and entry["page_number"] == page.page_number
                and positive(entry.get("pdf_width")) and positive(entry.get("pdf_height"))
                and entry["pdf_width"] == page.width and entry["pdf_height"] == page.height, "OCR page geometry mismatch")
        require(entry.get("status") == "needs_human" and entry.get("eligible_for_translation") is False
                and type(entry.get("forced_page_review")) is bool and strings(entry.get("warnings"))
                and isinstance(entry.get("transcription"), str) and isinstance(entry.get("words"), list),
                "invalid OCR review/text fields")
        fields = [entry.get(k) for k in ("image_uri", "image_hash", "image_width", "image_height")]
        image = None if all(v is None for v in fields) else dict(zip(("uri", "hash", "width", "height"), fields))
        anchors = []
        for word in entry["words"]:
            require(isinstance(word, dict) and {"text", "confidence", "source_char_start", "source_char_end",
                    "pixel_bbox", "pdf_bbox"} <= set(word), "invalid OCR word fields")
            anchors.append(dict(kind="word", text=word["text"], confidence=word["confidence"],
                                source_char_start=word["source_char_start"], source_char_end=word["source_char_end"],
                                pixel_bbox=word["pixel_bbox"], pdf_bbox=word["pdf_bbox"],
                                image_uri=entry.get("image_uri"), image_hash=entry.get("image_hash")))
        require("error" in entry, "OCR error field missing")
        provenance = {k: bundle[k] for k in ("base_extraction_hash", "stage", "language", "engine_version", "model_file_hash")}
        result[page_id] = _candidate(document, page, "ocr", entry["transcription"], anchors,
                                      list(dict.fromkeys(document.warnings + entry["warnings"])), image,
                                      entry["error"], provenance)
    return result


DECISION_FIELDS = {"origin", "candidate_hash", "actor", "actor_kind", "reason"}


def validate_decision(decision):
    require(isinstance(decision, dict) and set(decision) == DECISION_FIELDS
            and decision["origin"] in ("digital", "ocr", "digital-text") and sha(decision["candidate_hash"])
            and nonempty(decision["actor"]) and decision["actor_kind"] == "human"
            and nonempty(decision["reason"]), "invalid human source decision")


def build_readings(document: Document, ocr_bundle=None, decisions=None, previous_readings=None):
    require(isinstance(document, Document) and document.schema_version == 3
            and document.source_kind in ("pdf", "epub"),
            "source reading requires schema-3 PDF or EPUB extraction")
    if document.source_kind == "epub":
        require(ocr_bundle is None, "OCR is not supported for EPUB documents")
    decisions = {} if decisions is None else decisions
    require(isinstance(decisions, dict), "decisions must be a page mapping")
    known = {p.page_id for p in document.pages}
    for page_id, decision in decisions.items():
        require(page_id in known, "unknown source decision page")
        validate_decision(decision)
    ocr = validate_ocr_bundle(document, ocr_bundle) if ocr_bundle is not None else {}
    previous_by_page = {r["page_id"]: r for r in (previous_readings or [])}
    readings = []
    for page in document.pages:
        if document.source_kind == "epub":
            alternatives = [_digital_text_candidate(document, page)]
        else:
            alternatives = [_digital_candidate(document, page)] + ([ocr[page.page_id]] if page.page_id in ocr else [])
        decision, selected = decisions.get(page.page_id), None
        if decision is not None:
            selected = next((c for c in alternatives if c["usable"] and c["origin"] == decision["origin"]
                             and c["candidate_hash"] == decision["candidate_hash"]), None)
            require(selected is not None, "unknown, unusable or stale source decision")
        r = dict(reading_id=deterministic_id("structure-reading", page.document_id, page.page_id),
                 version=1, prior_version=None, document_id=page.document_id, page_id=page.page_id,
                 page_number=page.page_number, status="resolved" if selected else "unresolved",
                 reasons=[] if selected else ["unreviewed_source" if any(c["usable"] for c in alternatives) else "missing_source"],
                 text=selected["text"] if selected else None, text_hash=selected["text_hash"] if selected else None,
                 selected={k:selected[k] for k in ("origin", "candidate_hash")} if selected else None,
                 decision=decision, alternatives=alternatives)
        old = previous_by_page.get(page.page_id)
        if old:
            unchanged = all(r[k] == old[k] for k in r if k not in ("version", "prior_version"))
            r["version"] = old["version"] if unchanged else old["version"] + 1
            r["prior_version"] = old["prior_version"] if unchanged else old["version"]
        readings.append(r)
    return copy.deepcopy(readings)
