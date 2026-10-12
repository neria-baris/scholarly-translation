"""COMIC review on the literary engine's mechanism (audit/contracts/comic_review.md).

An independent critic (taxonomy and severities of the independent semantic review and the
chapter-level QA, plus the comic-only ``source_reading``) returns findings only. Findings are
applied by the review-suggestions rule: every fidelity finding and every ``hebrew_quality``
finding; ``consistency``/``continuity`` only when MAJOR or CRITICAL; ``completeness`` stays a
note. An applied finding whose translation span occurs exactly once is replaced locally (no
call); the rest go to one correction call per unit; corrected regions get one focused
recheck whose findings are recorded, never applied again (each finding is sent once). A
``source_reading`` finding triggers a fresh reading of that lettering and a retranslation.

The review unit is configurable (``panel``, ``page`` or ``pages:N``) so its size can be
compared and changed.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw

from . import model as comic_model
from ..core import target_languages
from .model import ComicModelError
from ..models.adapter import ImagePrompt

CRITIC_PROMPT = comic_model.PROMPT_DIR / "17_comic_review.md"
CORRECTION_PROMPT = comic_model.PROMPT_DIR / "18_comic_correction.md"
REREAD_PROMPT = comic_model.PROMPT_DIR / "19_comic_reread.md"
CRITIC_VERSION = "comic-critic@1"
CORRECTION_VERSION = "comic-correction@1"
REREAD_VERSION = "comic-reread@1"

FIDELITY = ("omission", "addition", "mistranslation", "negation", "quantifier_scope", "modality",
            "condition_causality", "referent_speaker", "notebook_departure", "names_numbers", "disambiguation",
            "lost_ambiguity", "over_literal", "humor_wordplay", "voice_register")
QUALITY = ("hebrew_quality",)
COHERENCE = ("consistency", "continuity")
NOTE_ONLY = ("completeness",)
SOURCE_READING = "source_reading"
CATEGORIES = FIDELITY + QUALITY + COHERENCE + NOTE_ONLY + (SOURCE_READING,)
SEVERITIES = ("CRITICAL", "MAJOR", "MINOR")
UNIT_SCOPES = ("panel", "page")
_ALIASES = {"over-literal": "over_literal", "calque": "over_literal", "quantifier": "quantifier_scope",
            "scope": "quantifier_scope", "speaker": "referent_speaker", "referent": "referent_speaker",
            "gender": "referent_speaker", "notebook": "notebook_departure", "names": "names_numbers",
            "humor": "humor_wordplay", "humour": "humor_wordplay", "wordplay": "humor_wordplay",
            "voice": "voice_register", "register": "voice_register", "quality": "hebrew_quality",
            "target_quality": "hebrew_quality", "source": SOURCE_READING, "transcription": SOURCE_READING}
_MAX_IMAGE_EDGE = 2048


def parse_scope(scope):
    """``panel``, ``page`` or ``pages:N`` (N >= 2) -> (kind, pages per unit)."""
    if scope in UNIT_SCOPES:
        return scope, 1
    match = re.fullmatch(r"pages:(\d+)", str(scope or ""))
    if match and int(match.group(1)) >= 2:
        return "pages", int(match.group(1))
    raise ComicModelError("review unit must be panel, page or pages:N (N >= 2), got %r" % scope)


def label(region):
    page = int(region["page_id"][1:])
    return "P%d.%d" % (page, region["order"])


def applies(issue):
    """The review-suggestions rule for automatic application."""
    category = issue["category"]
    if category in FIDELITY or category in QUALITY:
        return True
    if category in COHERENCE:
        return issue["severity"] in ("CRITICAL", "MAJOR")
    return False


def units(pages, scope):
    """Review units: lists of (page, regions). ``panel`` groups a page's regions by panel."""
    kind, size = parse_scope(scope)
    usable = [p for p in pages if p["regions"] and all(r["translation"] for r in p["regions"])]
    if kind == "page":
        return [[(p, list(p["regions"]))] for p in usable]
    if kind == "panel":
        result = []
        for page in usable:
            groups = {}
            for region in page["regions"]:
                key = region.get("panel") if region.get("panel") is not None else "r%d" % region["order"]
                groups.setdefault(key, []).append(region)
            result.extend([[(page, regions)] for regions in groups.values()])
        return result
    return [[(p, list(p["regions"])) for p in usable[i:i + size]] for i in range(0, len(usable), size)]


# ---------------------------------------------------------------- images

def _jpeg(image):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=False)
    return buffer.getvalue()


def unit_image(unit, images):
    """The unit's pages side by side, each with its unit regions framed and labelled."""
    tiles = []
    for page, regions in unit:
        data = comic_model.marked_page_image(images[page["index"]], regions, [label(r) for r in regions])
        tiles.append(Image.open(io.BytesIO(data)).convert("RGB"))
    height = min(t.height for t in tiles)
    tiles = [t.resize((max(1, round(t.width * height / t.height)), height), Image.LANCZOS) if t.height != height
             else t for t in tiles]
    sheet = Image.new("RGB", (sum(t.width for t in tiles), height), "white")
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width
    scale = min(1.0, _MAX_IMAGE_EDGE / max(sheet.size))
    if scale < 1.0:
        sheet = sheet.resize((max(1, round(sheet.width * scale)), max(1, round(sheet.height * scale))),
                             Image.LANCZOS)
    return _jpeg(sheet)


def crops_image(items, images):
    """Each doubted region enlarged (its box plus a margin), one under the other, labelled."""
    font = comic_model._font(22)
    crops = []
    for page, region in items:
        image = images[page["index"]]
        x0, y0, x1, y1 = region["bbox"]
        mx, my = max(12, (x1 - x0) // 4), max(12, (y1 - y0) // 4)
        crop = image.crop((max(0, x0 - mx), max(0, y0 - my), min(image.width, x1 + mx), min(image.height, y1 + my)))
        scale = min(3.0, max(1.0, 900 / max(crop.size)))
        crop = crop.convert("RGB").resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
        crops.append((label(region), crop))
    width = max(c.width for _, c in crops) + 20
    height = sum(c.height + 44 for _, c in crops)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    y = 0
    for name, crop in crops:
        draw.rectangle([0, y, width, y + 36], fill=(255, 235, 0))
        draw.text((8, y + 6), name, font=font, fill=(0, 0, 0))
        sheet.paste(crop, (10, y + 40))
        y += crop.height + 44
    scale = min(1.0, _MAX_IMAGE_EDGE / max(sheet.size))
    if scale < 1.0:
        sheet = sheet.resize((max(1, round(sheet.width * scale)), max(1, round(sheet.height * scale))),
                             Image.LANCZOS)
    return _jpeg(sheet)


# ---------------------------------------------------------------- critic

def _template(path, target_code):
    pack = target_languages.load(target_code)
    return target_languages.localize(comic_model._template(path), pack)


def _rows(unit, with_translation=True):
    rows = []
    for page, regions in unit:
        for region in regions:
            row = {"id": label(region), "kind": region["kind"], "speaker": region["speaker"],
                   "speaker_gender": region["speaker_gender"], "addressee_gender": region["addressee_gender"],
                   "source": region["source_text"]}
            if with_translation:
                row["translation"] = region["translation"]["text"]
            rows.append(row)
    return rows


def _panels(unit):
    lines = []
    for page, regions in unit:
        wanted = {r.get("panel") for r in regions}
        for panel in page.get("panels") or []:
            if panel["panel"] in wanted or len(wanted - {None}) == 0:
                lines.append("- Page %d, panel %d: %s" % (page["index"], panel["panel"], panel["description"]))
    return "\n".join(lines) or "(no panel descriptions)"


def critic_prompt(unit, images, notebook, source_language, target_code, focus=None):
    """Independent critic prompt for a unit; ``focus`` (labels) makes it a focused recheck."""
    focus_note = ""
    if focus:
        focus_note = ("\nFOCUSED RECHECK: these regions were just corrected after an earlier review; check "
                      "only %s, and report only problems that remain or that the correction introduced.\n"
                      % ", ".join(sorted(focus)))
        unit = [(page, [r for r in regions if label(r) in focus]) for page, regions in unit]
        unit = [(page, regions) for page, regions in unit if regions]
    text = comic_model._fill(
        _template(CRITIC_PROMPT, target_code),
        LANGUAGE=comic_model.LANGUAGE_NAMES.get(source_language, source_language), FOCUS=focus_note,
        STORY=(notebook or {}).get("story") or "(the album begins here)", PANELS=_panels(unit),
        CHARACTERS=comic_model._character_lines(notebook, True), TERMS=comic_model._term_lines(notebook),
        REGIONS="\n".join(comic_model._json(row) for row in _rows(unit)))
    return ImagePrompt(text, unit_image(unit, images), "image/jpeg")


def _category(value):
    key = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = _ALIASES.get(key, key)
    if key not in CATEGORIES:
        raise ComicModelError("unknown issue category %r" % value)
    return key


def parse_critique(text, labels):
    """Validator for the critic: verdict and issues on known labels, spans as strings, a
    correction that differs from its translation span. Returns the list of issues."""
    data = comic_model._object(text, "review")
    issues = data.get("issues")
    if issues is None:
        issues = []
    if not isinstance(issues, list):
        raise ComicModelError("review: 'issues' must be a list")
    verdict = str(data.get("verdict", "")).upper()
    if verdict not in ("PASS", "REVISE"):
        raise ComicModelError("review: verdict must be PASS or REVISE")
    if verdict == "PASS" and issues:
        raise ComicModelError("review: PASS with issues")
    result = []
    for i, item in enumerate(issues):
        where = "issues[%d]" % i
        if not isinstance(item, dict) or item.get("id") not in labels:
            raise ComicModelError("%s: unknown or missing id" % where)
        severity = str(item.get("severity", "")).upper()
        if severity not in SEVERITIES:
            raise ComicModelError("%s: severity must be CRITICAL, MAJOR or MINOR" % where)
        fields = {}
        for key in ("source_span", "translation_span", "problem", "suggested_correction"):
            value = item.get(key, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ComicModelError("%s.%s: expected a string" % (where, key))
            fields[key] = value.strip()
        category = _category(item.get("category"))
        if category != SOURCE_READING and category not in NOTE_ONLY:
            if not fields["suggested_correction"]:
                raise ComicModelError("%s: an issue needs a suggested correction" % where)
            if fields["suggested_correction"] == fields["translation_span"]:
                raise ComicModelError("%s: the correction repeats the translation span" % where)
        result.append(dict(fields, id=item["id"], category=category, severity=severity))
    return result


def apply_span(text, issue):
    """The translation with the issue's span replaced, when that span occurs exactly once."""
    span = issue["translation_span"]
    if span and text.count(span) == 1:
        return text.replace(span, issue["suggested_correction"], 1)
    return None


# ---------------------------------------------------------------- correction and re-reading

def correction_prompt(unit, images, pending, notebook, source_language, target_code):
    """``pending``: label -> list of issues for regions whose spans could not be replaced."""
    rows = []
    for row in _rows(unit):
        if row["id"] in pending:
            row["issues"] = [{k: issue[k] for k in ("category", "severity", "translation_span", "problem",
                                                    "suggested_correction")} for issue in pending[row["id"]]]
            rows.append(row)
    chosen = [(page, [r for r in regions if label(r) in pending]) for page, regions in unit]
    chosen = [(page, regions) for page, regions in chosen if regions]
    text = comic_model._fill(
        _template(CORRECTION_PROMPT, target_code),
        LANGUAGE=comic_model.LANGUAGE_NAMES.get(source_language, source_language),
        CHARACTERS=comic_model._character_lines(notebook, True), TERMS=comic_model._term_lines(notebook),
        REGIONS="\n".join(comic_model._json(row) for row in rows))
    return ImagePrompt(text, unit_image(chosen, images), "image/jpeg")


def parse_correction(text, labels, target_code, kinds=None, sources=None):
    data = comic_model._object(text, "correction")
    items = comic_model._translations(data, list(labels), target_code, kinds, False, sources)
    return {item["id"]: item["text"] for item in items}


def reread_prompt(items, images, issues, source_language):
    """``items``: [(page, region)] doubted; ``issues``: label -> the source_reading issue."""
    rows = []
    for page, region in items:
        issue = issues[label(region)]
        rows.append({"id": label(region), "earlier": region["source_text"],
                     "reviewer_reading": issue["suggested_correction"] or issue["source_span"],
                     "remark": issue["problem"]})
    text = comic_model._fill(comic_model._template(REREAD_PROMPT),
                             LANGUAGE=comic_model.LANGUAGE_NAMES.get(source_language, source_language),
                             REGIONS="\n".join(comic_model._json(row) for row in rows))
    return ImagePrompt(text, crops_image(items, images), "image/jpeg")


def parse_reread(text, labels):
    data = comic_model._object(text, "reading")
    entries = data.get("readings")
    if not isinstance(entries, list):
        raise ComicModelError("'readings' must be a list")
    found = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("id") not in labels or entry["id"] in found:
            raise ComicModelError("readings[%d]: unknown, missing or repeated id" % i)
        value = entry.get("text")
        if not isinstance(value, str) or not value.strip():
            raise ComicModelError("readings[%d]: expected the transcribed text" % i)
        value = " ".join(value.split())
        if comic_model._hebrew_share(value) > comic_model.SOURCE_HEBREW_LIMIT:
            raise ComicModelError("readings[%d]: Hebrew text; a reading must transcribe the source" % i)
        found[entry["id"]] = value
    missing = [name for name in labels if name not in found]
    if missing:
        raise ComicModelError("missing readings for %s" % ", ".join(missing))
    return found
