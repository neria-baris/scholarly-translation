"""COMIC model stages (audit/contracts/comic_translation.md): prompts, strict validators,
reconciliation and notebook merge for the three vision calls of a comic page
(recognition, in-context translation, shorten). Pure: the only I/O is reading the
runtime prompt files; calls are made by ``comic_pipeline`` through the controlled
chapter-pipeline path.
"""
from __future__ import annotations

import copy
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import records
from ..core import target_languages
from ..models.adapter import ImagePrompt

PROMPT_DIR = Path(__file__).resolve().parents[1] / "runtime_prompts"
RECOGNITION_PROMPT = PROMPT_DIR / "14_comic_recognition.md"
TRANSLATION_PROMPT = PROMPT_DIR / "15_comic_translation.md"
SHORTEN_PROMPT = PROMPT_DIR / "16_comic_shorten.md"
PLACEMENT_PROMPT = PROMPT_DIR / "20_comic_placement.md"
PLACEMENT_VERSION = "comic-placement@1"
RECOGNITION_VERSION = "comic-recognition@3"
TRANSLATION_VERSION = "comic-translation@6"
SHORTEN_VERSION = "comic-shorten@1"

MARKED_LONG_EDGE = 2048
LABEL_FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "notosans" / "NotoSans-Regular.ttf"
LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish", "ja": "Japanese"}
RIGHT_TO_LEFT_SOURCES = ("ja",)
PREVIOUS_SUMMARIES = 2
SOURCE_HEBREW_LIMIT = 0.5      # a recognised text with more Hebrew letters was translated, not transcribed
TARGET_SCRIPT_MIN = 0.5        # share of target-script letters required in a translation
SHORT_WORD_LETTERS = 3         # up to this many letters a text may stay in Latin (a name, "OK")
_FENCE_RE = re.compile(r"^```[A-Za-z]*\s*|\s*```$")
_HEBREW_RE = re.compile(r"[֐-׿]")


class ComicModelError(ValueError):
    """A model answer does not match the strict contract."""


def _fail(message):
    raise ComicModelError(message)


# ---------------------------------------------------------------- images

def _font(size):
    try:
        return ImageFont.truetype(str(LABEL_FONT), size)
    except OSError:
        return ImageFont.load_default()


def marked_page_image(image, candidates, labels=None):
    """JPEG bytes of the page (long edge <= MARKED_LONG_EDGE) with every candidate bbox framed
    in thin red a little outside the lettering (so the frame never covers a letter) and its
    number (1-based position, or ``labels[i]``) in a black-on-yellow label outside the frame."""
    image = image.convert("RGB")
    scale = min(1.0, MARKED_LONG_EDGE / max(image.size))
    if scale < 1.0:
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                             Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    size = max(14, round(max(image.size) / 70))
    font = _font(size)
    width = max(1, round(max(image.size) / 900))
    for i, candidate in enumerate(candidates):
        x0, y0, x1, y1 = (round(v * scale) for v in candidate["bbox"])
        pad = width + max(3, size // 4)
        box = [max(0, x0 - pad), max(0, y0 - pad), min(image.width - 1, x1 + pad), min(image.height - 1, y1 + pad)]
        draw.rectangle(box, outline=(255, 0, 0), width=width)
        label = str(labels[i] if labels is not None else i + 1)
        text_box = draw.textbbox((0, 0), label, font=font)
        w, h = text_box[2] - text_box[0] + 8, text_box[3] - text_box[1] + 8
        lx = min(max(0, box[0]), max(0, image.width - w))
        ly = box[1] - h if box[1] - h >= 0 else min(box[1], max(0, image.height - h))
        draw.rectangle([lx, ly, lx + w, ly + h], fill=(255, 235, 0), outline=(0, 0, 0))
        draw.text((lx + 4 - text_box[0], ly + 4 - text_box[1]), label, font=font, fill=(0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=False)
    return buffer.getvalue()


# ---------------------------------------------------------------- prompts

def _template(path, target_code=None):
    text = path.read_text(encoding="utf-8")
    if target_code is not None:
        text = target_languages.localize(text, target_languages.load(target_code))
    return text


def _fill(text, **values):
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _character_lines(notebook, with_target):
    lines = []
    for item in (notebook or {}).get("characters", []):
        if with_target:
            lines.append("- %s -> %s (%s)%s" % (item["name"], item["target_name"] or "(not fixed yet)", item["gender"],
                                                 ": " + item["note"] if item.get("note") else ""))
        else:
            lines.append("- %s (%s)%s" % (item["name"], item["gender"],
                                          ": " + item["note"] if item.get("note") else ""))
    return "\n".join(lines) or "(none yet)"


def recognition_prompt(image, candidates, source_language, notebook):
    """Vision prompt for the recognition call: the page with numbered candidate marks."""
    if source_language in RIGHT_TO_LEFT_SOURCES:
        direction = "This is a manga: pages and balloons are read from right to left, panels from top to bottom."
        order_rule = "Number entries in manga order: panels right to left then top to bottom, and inside a panel the right/upper balloon first."
    else:
        direction = "Pages are read from left to right, panels from top to bottom."
        order_rule = "Number entries in reading order: panels left to right then top to bottom, and inside a panel the upper/left balloon first."
    text = _fill(_template(RECOGNITION_PROMPT), MARK_COUNT=str(len(candidates)),
                 LANGUAGE=LANGUAGE_NAMES.get(source_language, source_language), DIRECTION=direction,
                 ORDER_RULE=order_rule, NOTEBOOK=_character_lines(notebook, False))
    return ImagePrompt(text, marked_page_image(image, candidates), "image/jpeg")


# ---------------------------------------------------------------- validators

def _object(raw_text, what):
    if not isinstance(raw_text, str):
        _fail("%s returned no text" % what)
    text = _FENCE_RE.sub("", raw_text.replace("\r\n", "\n").strip()).strip()
    if not text:
        _fail("%s returned an empty answer" % what)
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            _fail("%s is not a JSON object" % what)
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            _fail("%s is not valid JSON" % what)
    if not isinstance(data, dict):
        _fail("%s must be a JSON object" % what)
    return data


def _hebrew_share(text):
    letters = sum(ch.isalpha() for ch in text)
    return len(_HEBREW_RE.findall(text)) / letters if letters else 0.0


def _gender(entry, key, where):
    value = entry.get(key, "unknown")
    if value is None:
        return "unknown"
    if value not in records.GENDERS:
        _fail("%s.%s: unknown gender %r" % (where, key, value))
    return value


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _norm_box(box, where):
    if not isinstance(box, list) or len(box) != 4 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in box):
        _fail("%s.box: expected [x0, y0, x1, y1]" % where)
    if any(v < 0 or v > 1000 for v in box):
        _fail("%s.box: coordinates must be within 0..1000" % where)
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    if not (x0 < x1 and y0 < y1):
        _fail("%s.box: empty box" % where)
    return [x0, y0, x1, y1]


def parse_recognition(text, mark_count):
    """Validator for the recognition answer. Returns ``{"regions", "summary", "characters"}``.

    Regions are returned in reading order: sorted by the model's ``order`` (entries without
    one, or with equal values, keep the model's list position as tie-break). The ``order``
    values themselves are not trusted beyond that; ``reconcile`` renumbers 1..n.
    """
    data = _object(text, "recognition")
    entries = data.get("regions")
    if not isinstance(entries, list):
        _fail("recognition: 'regions' must be a list")
    regions = []
    for i, entry in enumerate(entries):
        where = "regions[%d]" % i
        if not isinstance(entry, dict):
            _fail("%s: expected an object" % where)
        if "marks" in entry:
            marks = entry["marks"]
            if marks is None:
                marks = []
            if not isinstance(marks, list):
                _fail("%s.marks: expected a list of mark numbers" % where)
        else:  # recognition@1 answers: one "mark" or null
            marks = [] if entry.get("mark") is None else [entry.get("mark")]
        for mark in marks:
            if not _int(mark) or not 1 <= mark <= mark_count:
                _fail("%s.marks: %r is not one of the %d marks" % (where, mark, mark_count))
        marks = sorted(set(marks))   # one mark may cover the lettering of two balloons
        box = entry.get("box")
        if box is None:
            if not marks:
                _fail("%s: a region without marks needs a box" % where)
        else:
            box = _norm_box(box, where)
        kind = entry.get("kind")
        if kind not in records.KINDS:
            _fail("%s.kind: unknown kind %r" % (where, kind))
        source = entry.get("text")
        if not isinstance(source, str) or not source.strip():
            _fail("%s.text: expected the transcribed text" % where)
        source = " ".join(source.split())
        if _hebrew_share(source) > SOURCE_HEBREW_LIMIT:
            _fail("%s.text: Hebrew text; recognition must transcribe the source, not translate it" % where)
        speaker = entry.get("speaker")
        if speaker is not None and not isinstance(speaker, str):
            _fail("%s.speaker: expected a string or null" % where)
        speaker = (speaker or "").strip() or None
        order = entry.get("order")
        if order is not None and not _int(order):
            _fail("%s.order: expected an integer" % where)
        panel = entry.get("panel")
        if panel is not None and not _int(panel):
            _fail("%s.panel: expected an integer" % where)
        regions.append({"marks": marks, "box": box, "kind": kind, "text": source, "speaker": speaker,
                        "speaker_gender": _gender(entry, "speaker_gender", where),
                        "addressee_gender": _gender(entry, "addressee_gender", where),
                        "order": order, "panel": panel, "_position": i})
    regions.sort(key=lambda r: (r["order"] if r["order"] is not None else r["_position"] + 1, r["_position"]))
    for number, region in enumerate(regions, 1):
        region["order"] = number
        del region["_position"]
    summary = data.get("summary", "")
    if not isinstance(summary, str):
        _fail("recognition: 'summary' must be a string")
    characters = []
    for i, item in enumerate(data.get("characters") or []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            _fail("characters[%d]: expected an object with a name" % i)
        appearance = item.get("appearance", "")
        characters.append({"name": item["name"].strip(), "gender": _gender(item, "gender", "characters[%d]" % i),
                           "appearance": appearance if isinstance(appearance, str) else ""})
    panels = []
    raw_panels = data.get("panels") or []
    if not isinstance(raw_panels, list):
        _fail("recognition: 'panels' must be a list")
    for i, item in enumerate(raw_panels):
        if (not isinstance(item, dict) or not _int(item.get("panel"))
                or not isinstance(item.get("description"), str)):
            _fail("panels[%d]: expected {panel, description}" % i)
        panels.append({"panel": item["panel"], "description": " ".join(item["description"].split())})
    return {"regions": regions, "summary": summary.strip(), "characters": characters, "panels": panels}


# ---------------------------------------------------------------- reconcile

def _pixel_box(box, width, height):
    x0 = min(width - 1, max(0, int(box[0] * width / 1000)))
    y0 = min(height - 1, max(0, int(box[1] * height / 1000)))
    x1 = min(width, max(x0 + 1, int(round(box[2] * width / 1000))))
    y1 = min(height, max(y0 + 1, int(round(box[3] * height / 1000))))
    return [x0, y0, x1, y1]


def _near(box, model_box):
    """A mark joins a model box only when it touches the box grown by half its size: a mark
    elsewhere on the page (a wrong mark number) must not stretch the region across panels."""
    gx, gy = (model_box[2] - model_box[0]) / 2, (model_box[3] - model_box[1]) / 2
    return (box[0] < model_box[2] + gx and box[2] > model_box[0] - gx
            and box[1] < model_box[3] + gy and box[3] > model_box[1] - gy)


def _area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def reconcile(page, image, candidates, parsed, snap):
    """Regions of a page from a validated recognition answer.

    Every region is measured with ``snap(image, pixel_box)``. The box is the model's
    lettering box joined with the marks it lists (a mark far larger than the model's box is
    art and is ignored); a region without a model box uses its marks. ``origin`` is local
    when marks contributed, else model. Ids and ``order`` follow the model's reading order. A
    mark the model did not answer is dropped visibly: ``unanswered_mark:N`` in
    ``page["warnings"]``.
    """
    width, height = image.size
    uses = {}
    for r in parsed["regions"]:
        for mark in r["marks"]:
            uses[mark] = uses.get(mark, 0) + 1
    answered = set(uses)
    for number in range(1, len(candidates) + 1):
        warning = "unanswered_mark:%d" % number
        if number not in answered and warning not in page["warnings"]:
            page["warnings"].append(warning)
    result = []
    for number, entry in enumerate(parsed["regions"], 1):
        warnings = []
        model_box = _pixel_box(entry["box"], width, height) if entry["box"] is not None else None
        boxes = [candidates[m - 1]["bbox"] for m in entry["marks"]]
        if model_box is not None:
            # a mark shared with another entry or far larger than the lettering adds no geometry
            sized = [candidates[m - 1]["bbox"] for m in entry["marks"]
                     if uses[m] == 1 and _area(candidates[m - 1]["bbox"]) <= 3 * _area(model_box)]
            boxes = [b for b in sized if _near(b, model_box)]
            if sized and not boxes:
                # None of its own marks is near the model's box: the marks are measured from the
                # ink, the box is the model's estimate, so the marks give the place.
                boxes = sized
                warnings.append("box_from_marks")
            else:
                if len(boxes) < len(entry["marks"]):
                    warnings.append("mark_ignored")
                boxes.append(model_box)
        pixels = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                  max(b[3] for b in boxes)]
        origin = "local" if len(boxes) > (model_box is not None) else "model"
        try:
            candidate = snap(image, pixels)
            records.validate_candidate(candidate, "snap", width, height)
        except Exception:
            warnings.append("snap_failed")
            candidate = {"bbox": pixels, "interior": None, "background": [255, 255, 255],
                         "plain_background": False, "line_height": max(1.0, (pixels[3] - pixels[1]) / 2),
                         "confidence": 0.0}
        result.append(records.new_region(
            candidate, page["index"], number, order=number, kind=entry["kind"], source_text=entry["text"],
            speaker=entry["speaker"], speaker_gender=entry["speaker_gender"],
            addressee_gender=entry["addressee_gender"], origin=origin, warnings=warnings,
            panel=entry.get("panel")))
        result[-1]["source_box"] = model_box or pixels      # where the recogniser put this text
    return result


# ---------------------------------------------------------------- translation

def _region_rows(regions, capacities):
    return [{"id": r["region_id"], "order": r["order"], "panel": r.get("panel"), "kind": r["kind"],
             "speaker": r["speaker"],
             "speaker_gender": r["speaker_gender"], "addressee_gender": r["addressee_gender"],
             "source": r["source_text"], "max_chars": int(capacities.get(r["region_id"], 0)) or None}
            for r in regions]


def _term_lines(notebook):
    lines = ["- %s -> %s" % (t["source"], t["target"]) for t in (notebook or {}).get("terms", [])]
    return "\n".join(lines) or "(none yet)"


def _panel_lines(page):
    lines = ["- Panel %d: %s" % (p["panel"], p["description"]) for p in page.get("panels") or []]
    return "\n".join(lines) or "(no panel descriptions)"


def _dialogue_lines(previous_dialogue):
    lines = []
    for item in previous_dialogue or []:
        who = "[%s] " % item["speaker"] if item.get("speaker") else ""
        lines.append("- %s%s -> %s" % (who, item["source"], item["target"]))
    return "\n".join(lines) or "(none)"


def translation_prompt(image, page, notebook, previous_summaries, source_language, target_code, capacities,
                       previous_dialogue=None):
    """Vision prompt for the translation call of one page: the page, its panel descriptions,
    the running story, the previous page's dialogue and the notebook."""
    pack = target_languages.load(target_code)
    regions = page["regions"]
    if pack.rtl:
        direction = ("The text will be set right-to-left in {{T:TARGET}}. Write it in logical order, "
                     "as a person would type it; do not reverse it and do not add direction marks.")
    else:
        direction = "The text will be set left-to-right in {{T:TARGET}}."
    template = target_languages.localize(_template(TRANSLATION_PROMPT).replace("{{DIRECTION_NOTE}}", direction), pack)
    recent = [s for s in (previous_summaries or []) if s][-PREVIOUS_SUMMARIES:]
    text = _fill(template, LANGUAGE=LANGUAGE_NAMES.get(source_language, source_language),
                 REGIONS="\n".join(_json(row) for row in _region_rows(regions, capacities)),
                 CHARACTERS=_character_lines(notebook, True), TERMS=_term_lines(notebook),
                 SUMMARIES="\n".join("- " + s for s in recent) or "(this is the first page)",
                 STORY=(notebook or {}).get("story") or "(the album begins here)",
                 PANELS=_panel_lines(page), PREVIOUS_DIALOGUE=_dialogue_lines(previous_dialogue))
    labels = [r["order"] for r in regions]
    return ImagePrompt(text, marked_page_image(image, regions, labels), "image/jpeg")


def _clean_text(value, where):
    if not isinstance(value, str) or not value.strip():
        _fail("%s: expected non-empty text" % where)
    return " ".join(value.split())


def _check_script(text, target_code, where):
    """Target-script check: the letters of a translation must be mostly in the target script.
    Up to ``SHORT_WORD_LETTERS`` letters may stay Latin (a name, "OK"); digits and punctuation
    are not letters; names inside a longer text are fine as long as the target script wins."""
    pack = target_languages.load(target_code)
    letters = [ch for ch in text if ch.isalpha()]
    if not letters or len(letters) <= SHORT_WORD_LETTERS:
        return
    in_script = len(pack.letters_re.findall(text))
    if in_script / len(letters) < TARGET_SCRIPT_MIN:
        _fail("%s: not written in %s" % (where, pack.name))


def _translations(data, ids, target_code, kinds, with_note, sources=None):
    entries = data.get("translations")
    if not isinstance(entries, list):
        _fail("'translations' must be a list")
    found, order = {}, []
    for i, entry in enumerate(entries):
        where = "translations[%d]" % i
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            _fail("%s: expected an object with an id" % where)
        key = entry["id"]
        if key not in ids:
            _fail("%s: unknown id %r" % (where, key))
        if key in found:
            _fail("%s: id %r answered twice" % (where, key))
        text = _clean_text(entry.get("text"), where)
        source = (sources or {}).get(key, "")
        if any(ch.isalpha() for ch in source) and not any(ch.isalpha() for ch in text):
            _fail("%s: the source has words but the translation has none" % where)
        # Sound effects may stay in the original lettering when no equivalent exists.
        if (kinds or {}).get(key) != "sfx":
            _check_script(text, target_code, where)
        note = entry.get("note", "")
        found[key] = {"id": key, "text": text, "note": note.strip() if with_note and isinstance(note, str) else ""}
        order.append(key)
    missing = [key for key in ids if key not in found]
    if missing:
        _fail("missing translations for %s" % ", ".join(missing))
    return [found[key] for key in ids]


def parse_translation(text, region_ids, target_code, kinds=None, sources=None):
    """Validator for the translation answer: every id exactly once, no extras, non-empty text
    in the target script. ``kinds`` (id -> kind) lets ``sfx`` skip the script check.
    Returns ``{"translations": [{id, text, note}] (request order), "notebook", "summary"}``."""
    data = _object(text, "translation")
    ids = list(region_ids)
    translations = _translations(data, ids, target_code, kinds, True, sources)
    notes = {e.get("id"): e.get("footnote") is True for e in data.get("translations") or [] if isinstance(e, dict)}
    for item in translations:   # only lettering in the scene gets a footnote
        item["footnote"] = notes.get(item["id"], False) and (kinds or {}).get(item["id"]) in ("sign", "other")
    notebook = records.new_notebook()
    raw = data.get("notebook") or {}
    if not isinstance(raw, dict):
        _fail("'notebook' must be an object")
    for i, item in enumerate(raw.get("characters") or []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            _fail("notebook.characters[%d]: expected a name" % i)
        target = item.get("target_name")
        if not isinstance(target, str) or not target.strip():
            continue  # a character without a target form yet changes nothing
        note = item.get("note", "")
        notebook["characters"].append({"name": item["name"].strip(), "target_name": target.strip(),
                                       "gender": _gender(item, "gender", "notebook.characters[%d]" % i),
                                       "note": note.strip() if isinstance(note, str) else ""})
    for i, item in enumerate(raw.get("terms") or []):
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip()
                                                   for k in ("source", "target")):
            _fail("notebook.terms[%d]: expected source and target" % i)
        notebook["terms"].append({"source": item["source"].strip(), "target": item["target"].strip()})
    summary, story = data.get("summary", ""), data.get("story", "")
    if not isinstance(summary, str):
        _fail("translation: 'summary' must be a string")
    if not isinstance(story, str):
        _fail("translation: 'story' must be a string")
    notebook["story"] = story.strip()
    return {"translations": translations, "notebook": notebook, "summary": summary.strip()}


def placement_prompt(image, page):
    """Vision prompt checking that each region's frame encloses its own lettering."""
    regions = page["regions"]
    rows = [{"number": r["order"], "kind": r["kind"], "lettering": r["source_text"]} for r in regions]
    text = _fill(_template(PLACEMENT_PROMPT), REGIONS="\n".join(_json(row) for row in rows))
    return ImagePrompt(text, marked_page_image(image, regions, [r["order"] for r in regions]), "image/jpeg")


def parse_placement(text, numbers):
    """Validator: every number once; a wrong placement carries a corrected 0..1000 box.
    Returns {number: None (ok) or box}."""
    data = _object(text, "placement")
    entries = data.get("regions")
    if not isinstance(entries, list):
        _fail("placement: 'regions' must be a list")
    found = {}
    for i, entry in enumerate(entries):
        where = "regions[%d]" % i
        if not isinstance(entry, dict) or entry.get("number") not in numbers or entry["number"] in found:
            _fail("%s: unknown, missing or repeated number" % where)
        ok = entry.get("ok")
        if not isinstance(ok, bool):
            _fail("%s.ok: expected true or false" % where)
        found[entry["number"]] = None if ok else _norm_box(entry.get("box"), where)
    missing = [n for n in numbers if n not in found]
    if missing:
        _fail("placement: missing numbers %s" % missing)
    return found


def shorten_prompt(image, page, overflowing, target_code):
    """Vision prompt asking for shorter translations of the ``overflowing`` regions.
    ``overflowing``: list of ``{"id", "text" (current translation), "max_chars"}``."""
    by_id = {r["region_id"]: r for r in page["regions"]}
    rows = []
    for item in overflowing:
        region = by_id[item["id"]]
        rows.append({"id": item["id"], "order": region["order"], "kind": region["kind"],
                     "speaker": region["speaker"], "source": region["source_text"],
                     "current": item["text"], "current_chars": len(item["text"]), "max_chars": item["max_chars"]})
    text = _fill(_template(SHORTEN_PROMPT, target_code), REGIONS="\n".join(_json(row) for row in rows))
    chosen = [by_id[item["id"]] for item in overflowing]
    return ImagePrompt(text, marked_page_image(image, chosen, [r["order"] for r in chosen]), "image/jpeg")


def parse_shorten(text, ids, target_code, current=None, kinds=None, sources=None):
    """Validator for the shorten answer: exactly ``ids``, non-empty target-script text; when
    ``current`` (id -> present text) is given the new text must not be longer.
    Returns ``{id: text}``."""
    data = _object(text, "shorten")
    result = {}
    for item in _translations(data, list(ids), target_code, kinds, False, sources):
        if current and len(item["text"]) > len(current[item["id"]]):
            _fail("%s: the rewrite is longer than the current text" % item["id"])
        result[item["id"]] = item["text"]
    return result


# ---------------------------------------------------------------- notebook

def merge_notebook(notebook, updates):
    """Notebook with ``updates`` merged in, and the warnings. Earlier decisions win: an update
    that proposes a different ``target_name``/term target for a known name/source is dropped
    and reported as ``notebook_conflict:<name>``; a missing gender or note is filled in."""
    merged = copy.deepcopy(notebook)
    merged.setdefault("story", "")
    if updates.get("story"):
        merged["story"] = updates["story"]          # the running synopsis is rewritten each page
    warnings = []

    def warn(name):
        warning = "notebook_conflict:%s" % name
        if warning not in warnings:
            warnings.append(warning)

    known = {c["name"].casefold(): c for c in merged["characters"]}
    for item in updates.get("characters", []):
        current = known.get(item["name"].casefold())
        if current is None:
            current = {"name": item["name"], "target_name": item["target_name"], "gender": item["gender"],
                       "note": item.get("note", "")}
            merged["characters"].append(current)
            known[item["name"].casefold()] = current
            continue
        if not current["target_name"]:
            current["target_name"] = item["target_name"]
        elif item["target_name"] and item["target_name"] != current["target_name"]:
            warn(item["name"])
        if current["gender"] == "unknown":
            current["gender"] = item["gender"]
        elif item["gender"] not in ("unknown", current["gender"]):
            warn(item["name"])
        if not current.get("note"):
            current["note"] = item.get("note", "")
    terms = {t["source"].casefold(): t for t in merged["terms"]}
    for item in updates.get("terms", []):
        current = terms.get(item["source"].casefold())
        if current is None:
            current = {"source": item["source"], "target": item["target"]}
            merged["terms"].append(current)
            terms[item["source"].casefold()] = current
        elif current["target"] != item["target"]:
            warn(item["source"])
    records.validate_notebook(merged)
    return merged, warnings
