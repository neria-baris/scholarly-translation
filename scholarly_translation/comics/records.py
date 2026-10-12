"""COMIC data spine (audit/contracts/comic_translation.md).

Plain-dict records for comic pages: detection candidates, regions (source
evidence plus separate derived translation/layout), pages and the comic job.
Coordinates are original-image pixels; boxes are ``[x0, y0, x1, y1]`` with
x1/y1 exclusive. Validators raise ``ComicRecordError`` with the offending path.
"""
from __future__ import annotations

import hashlib

COMIC_SCHEMA = 1
KINDS = ("speech", "thought", "narration", "sfx", "sign", "other")
GENDERS = ("male", "female", "mixed", "unknown")
TRANSLATION_STATUSES = ("ok", "overflow", "missing", "skipped")
PAGE_STATUSES = ("pending", "recognised", "translated", "rendered", "failed")
ORIGINS = ("local", "model")
LAYOUT_STYLES = ("bubble", "box", "subtitle")


class ComicRecordError(ValueError):
    """A comic record does not match the schema."""


def page_id(index: int) -> str:
    return "p%03d" % index


def region_id(page_index: int, number: int) -> str:
    return "p%03d-r%02d" % (page_index, number)


def image_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail(path, message):
    raise ComicRecordError("%s: %s" % (path, message))


def _int(value, path):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "expected an integer")
    return value


def validate_box(box, path="bbox", width=None, height=None):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        _fail(path, "expected [x0, y0, x1, y1]")
    x0, y0, x1, y1 = (_int(v, path) for v in box)
    if not (x0 < x1 and y0 < y1) or x0 < 0 or y0 < 0:
        _fail(path, "empty or negative box %r" % (list(box),))
    if (width is not None and x1 > width) or (height is not None and y1 > height):
        _fail(path, "box %r outside the %sx%s page" % (list(box), width, height))
    return [x0, y0, x1, y1]


def validate_interior(interior, path="interior"):
    if interior is None:
        return None
    if not isinstance(interior, dict) or set(interior) != {"step", "rows"}:
        _fail(path, "expected {step, rows} or null")
    if _int(interior["step"], path + ".step") < 1:
        _fail(path + ".step", "must be >= 1")
    rows = interior["rows"]
    if not isinstance(rows, list) or not rows:
        _fail(path + ".rows", "expected a non-empty list")
    previous = None
    for i, row in enumerate(rows):
        where = "%s.rows[%d]" % (path, i)
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            _fail(where, "expected [y, x0, x1]")
        y, x0, x1 = (_int(v, where) for v in row)
        if x0 >= x1 or y < 0 or x0 < 0:
            _fail(where, "empty span")
        if previous is not None and y <= previous:
            _fail(where, "rows must ascend")
        previous = y
    return interior


def validate_candidate(candidate, path="candidate", width=None, height=None):
    if not isinstance(candidate, dict):
        _fail(path, "expected an object")
    for key in ("bbox", "interior", "background", "plain_background", "line_height", "confidence"):
        if key not in candidate:
            _fail(path, "missing %s" % key)
    validate_box(candidate["bbox"], path + ".bbox", width, height)
    validate_interior(candidate["interior"], path + ".interior")
    background = candidate["background"]
    if not isinstance(background, (list, tuple)) or len(background) != 3 or not all(
            isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in background):
        _fail(path + ".background", "expected [r, g, b]")
    if not isinstance(candidate["plain_background"], bool):
        _fail(path + ".plain_background", "expected a boolean")
    if not isinstance(candidate["line_height"], (int, float)) or candidate["line_height"] <= 0:
        _fail(path + ".line_height", "expected a positive number")
    confidence = candidate["confidence"]
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        _fail(path + ".confidence", "expected 0..1")
    return candidate


def new_region(candidate, page_index, number, **fields):
    """Region from a detection candidate; recognition fields come from ``fields``."""
    region = {
        "region_id": region_id(page_index, number), "page_id": page_id(page_index), "order": number,
        "bbox": list(candidate["bbox"]), "interior": candidate["interior"],
        "background": list(candidate["background"]), "plain_background": candidate["plain_background"],
        "line_height": candidate["line_height"], "confidence": candidate["confidence"],
        "kind": "speech", "source_text": "", "speaker": None,
        "speaker_gender": "unknown", "addressee_gender": "unknown", "origin": "local",
        "warnings": [], "translation": None, "layout": None, "panel": None,
        "balloon": candidate.get("balloon"), "words": candidate.get("words"),
    }
    unknown = set(fields) - set(region)
    if unknown:
        raise ComicRecordError("unknown region fields %s" % sorted(unknown))
    region.update(fields)
    return region


def mirror_region(region, width):
    """Copy of ``region`` with its bbox and interior mirrored left-right on a page ``width``
    wide (pages are mirrored so a right-to-left reader meets the panels in order)."""
    mirrored = dict(region)
    x0, y0, x1, y1 = region["bbox"]
    mirrored["bbox"] = [width - x1, y0, width - x0, y1]
    if region.get("words"):
        mirrored["words"] = [[width - b[2], b[1], width - b[0], b[3]] for b in region["words"]]
    for key in ("interior", "balloon", "room"):
        area = region.get(key)
        if area:
            mirrored[key] = {"step": area["step"], "rows": [[y, width - b, width - a] for y, a, b in area["rows"]]}
    return mirrored


def validate_region(region, path="region", width=None, height=None):
    validate_candidate(region, path, width, height)
    for key in ("region_id", "page_id", "order", "kind", "source_text", "speaker", "speaker_gender",
                "addressee_gender", "origin", "warnings", "translation", "layout"):
        if key not in region:
            _fail(path, "missing %s" % key)
    _int(region["order"], path + ".order")
    if region.get("panel") is not None:
        _int(region["panel"], path + ".panel")
    if region["kind"] not in KINDS:
        _fail(path + ".kind", "unknown kind %r" % region["kind"])
    if not isinstance(region["source_text"], str):
        _fail(path + ".source_text", "expected a string")
    if region["speaker"] is not None and not isinstance(region["speaker"], str):
        _fail(path + ".speaker", "expected a string or null")
    for key in ("speaker_gender", "addressee_gender"):
        if region[key] not in GENDERS:
            _fail(path + "." + key, "unknown gender %r" % region[key])
    if region["origin"] not in ORIGINS:
        _fail(path + ".origin", "unknown origin %r" % region["origin"])
    if not isinstance(region["warnings"], list) or not all(isinstance(w, str) for w in region["warnings"]):
        _fail(path + ".warnings", "expected a list of strings")
    translation = region["translation"]
    if translation is not None:
        if not isinstance(translation, dict) or not {"text", "status", "note"} <= set(translation):
            _fail(path + ".translation", "expected {text, status, note}")
        if translation["status"] not in TRANSLATION_STATUSES:
            _fail(path + ".translation.status", "unknown status %r" % translation["status"])
        if not isinstance(translation["text"], str):
            _fail(path + ".translation.text", "expected a string")
    layout = region["layout"]
    if layout is not None:
        if not isinstance(layout, dict) or layout.get("style") not in LAYOUT_STYLES:
            _fail(path + ".layout", "expected a layout with a known style")
        if not isinstance(layout.get("lines"), list) or not isinstance(layout.get("overflow"), bool):
            _fail(path + ".layout", "expected lines and overflow")
    return region


def new_page(index, source_name, image_bytes, width, height):
    return {"page_id": page_id(index), "index": index, "source_name": source_name,
            "image_sha256": image_sha256(image_bytes), "width": width, "height": height,
            "regions": [], "summary": "", "status": "pending", "warnings": [], "versions": {}}


def validate_page(page, path="page"):
    for key in ("page_id", "index", "source_name", "image_sha256", "width", "height", "regions", "summary",
                "status", "warnings", "versions"):
        if key not in page:
            _fail(path, "missing %s" % key)
    index = _int(page["index"], path + ".index")
    if page["page_id"] != page_id(index):
        _fail(path + ".page_id", "does not match index")
    width, height = _int(page["width"], path + ".width"), _int(page["height"], path + ".height")
    if page["status"] not in PAGE_STATUSES:
        _fail(path + ".status", "unknown status %r" % page["status"])
    seen = set()
    for i, region in enumerate(page["regions"]):
        where = "%s.regions[%d]" % (path, i)
        validate_region(region, where, width, height)
        if region["page_id"] != page["page_id"]:
            _fail(where + ".page_id", "belongs to another page")
        if region["region_id"] in seen:
            _fail(where + ".region_id", "duplicate id")
        seen.add(region["region_id"])
    return page


def new_notebook():
    return {"characters": [], "terms": [], "story": ""}


def validate_notebook(notebook, path="notebook"):
    if (not isinstance(notebook, dict) or not {"characters", "terms"} <= set(notebook)
            or not set(notebook) <= {"characters", "terms", "story"}):
        _fail(path, "expected {characters, terms, story}")
    if not isinstance(notebook.get("story", ""), str):
        _fail(path + ".story", "expected a string")
    for i, item in enumerate(notebook["characters"]):
        where = "%s.characters[%d]" % (path, i)
        if not isinstance(item, dict) or not {"name", "target_name", "gender", "note"} <= set(item):
            _fail(where, "expected {name, target_name, gender, note}")
        if item["gender"] not in GENDERS:
            _fail(where + ".gender", "unknown gender %r" % item["gender"])
    for i, item in enumerate(notebook["terms"]):
        if not isinstance(item, dict) or not {"source", "target"} <= set(item):
            _fail("%s.terms[%d]" % (path, i), "expected {source, target}")
    return notebook


def new_comic(comic_id, source_language, target_language):
    return {"schema": COMIC_SCHEMA, "comic_id": comic_id, "source_language": source_language,
            "target_language": target_language, "pages": [], "notebook": new_notebook()}


def validate_comic(comic):
    if not isinstance(comic, dict) or comic.get("schema") != COMIC_SCHEMA:
        _fail("comic", "unsupported schema %r" % (comic.get("schema") if isinstance(comic, dict) else None))
    for key in ("comic_id", "source_language", "target_language", "pages", "notebook"):
        if key not in comic:
            _fail("comic", "missing %s" % key)
    for i, page in enumerate(comic["pages"]):
        validate_page(page, "comic.pages[%d]" % i)
    validate_notebook(comic["notebook"], "comic.notebook")
    return comic
