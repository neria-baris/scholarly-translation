"""COMIC pipeline and CLI (audit/contracts/comic_translation.md).

Per page: local detection -> recognition call -> reconcile -> capacities -> translation
call -> fit -> at most one shorten call -> re-fit -> render. Every model call goes through
``chapter_pipeline._controlled`` (journaled, budgeted, replayed on rerun) with the
state in ``<out>/.state/``. Outputs: ``pages/NNN.png``, ``comic.cbz``, ``comic.pdf``,
``comic.json``, ``review.html`` and the untouched ``originals/NNN.png``.

    python -m scholarly_translation.comics.pipeline INPUT --out DIR --source-language en|es|fr|ja
        --target he [--model mock|configured --model-config PATH] [--budget-usd 1.0]
        [--pages 1-5,8] [--notebook PATH]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from PIL import Image, ImageOps

from ..translate import chapter_pipeline
from . import model as comic_model
from . import review as comic_review
from . import edit as comic_edit
from ..core import target_languages
from . import records
from ..translate.job_blocks import AUTO_ACCEPT_BELOW_USD, AUTO_ACCEPT_MAX_STREAK, AUTO_RETRY_DELAYS
from ..models.adapter import OpenAIConfigurationError, TextGenerationResult, build_translation_adapter
from ..models.config import ModelConfigError, ModelConfiguration, load_model_configuration
from ..budget.runtime_controls import ControlStore, RuntimeControlsError, validate_store_path
from ..translate.translation import TranslationBudgetError
from ..core.work_journal import WorkJournal

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
ROLE, REVIEW_ROLE, RECOGNIZER_ROLE = "translator", "semantic_reviewer", "comic_recognizer"
RECOGNITION_STAGE, TRANSLATION_STAGE, SHORTEN_STAGE = "comic-recognition", "comic-translation", "comic-shorten"
REVIEW_STAGE, CORRECTION_STAGE, REREAD_STAGE = "comic-review", "comic-correction", "comic-reread"
LOCATE_STAGE = "comic-sign-locate"
PLACEMENT_STAGE = "comic-placement"
MAX_CALLS = 20000                 # task call ceiling (fixed per task; the budget is the real limit)
DEFAULT_OUTPUT_TOKENS = 16384
PDF_RENDER_SCALE = 2.0
MAX_MEMBER_BYTES = 200 * 1024 * 1024
MOCK_MODEL = "mock-translation-1"
MOCK_TRANSLATION = "[תרגום-דמה %d]"   # conspicuous placeholder (glyphs the Hebrew font has), never a translation
MOCK_SHORTENED = "[קצר-דמה %d]"
MOCK_CONFIG = {"schema_version": 1, "providers": {"mock": {"type": "mock"}},
               "models": {role: {"provider": "mock", "model": MOCK_MODEL,
                                 "capabilities": {"context_window": 200000, "usable_context_tokens": 200000,
                                                  "max_output_tokens": DEFAULT_OUTPUT_TOKENS}}
                          for role in ("translator", "semantic_reviewer", "chapter_qa")}}
_FATAL = (OpenAIConfigurationError, ModelConfigError)


class ComicPipelineError(Exception):
    """User-facing reason why a comic cannot be processed."""


# ---------------------------------------------------------------- stages

def default_stages():
    """The real detection and typesetting modules (imported when first needed)."""
    from . import detect as comic_detect
    from . import typeset as comic_typeset
    return SimpleNamespace(
        DETECT_VERSION=comic_detect.DETECT_VERSION, TYPESET_VERSION=comic_typeset.TYPESET_VERSION,
        detect_candidates=comic_detect.detect_candidates, snap_region=comic_detect.snap_region,
        font_for=comic_typeset.font_for, min_font_px=comic_typeset.min_font_px,
        erase_balloons=comic_typeset.erase_balloons, trim_to_ink=comic_typeset.trim_to_ink,
        capacity=comic_typeset.capacity, fit=comic_typeset.fit, render_page=comic_typeset.render_page)


# ---------------------------------------------------------------- input loading

def natural_key(name):
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", name.casefold())]


def parse_pages(spec, total=None):
    """``"1-5,8"`` -> sorted set of 1-based page numbers (None = all pages)."""
    if spec is None or not str(spec).strip():
        return None
    pages = set()
    for part in str(spec).split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
        if not match:
            raise ComicPipelineError("bad --pages value %r (use e.g. 1-5,8)" % part)
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first:
            raise ComicPipelineError("bad page range %r" % part)
        pages.update(range(first, last + 1))
    if total is not None:
        pages = {p for p in pages if p <= total}
        if not pages:
            raise ComicPipelineError("--pages selects no page (the comic has %d)" % total)
    return pages


def _decode_image(raw):
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise ComicPipelineError("cannot read an image (%s)" % type(exc).__name__) from None
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def _png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _safe_member(name):
    if "\\" in name:
        name = name.replace("\\", "/")
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        return False
    return ":" not in path.parts[0]


def open_input(path, stack):
    """List of ``(name, load)`` pages of ``path`` in natural order; ``load()`` returns
    ``(rgb image, source bytes)``. Archives are read in memory, nothing is extracted."""
    path = Path(path)
    if path.is_dir():
        files = sorted((p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                       key=lambda p: natural_key(p.name))
        return [(p.name, (lambda p=p: _from_file(p))) for p in files]
    if not path.is_file():
        raise ComicPipelineError("input not found: %s" % path)
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return [(path.name, lambda: _from_file(path))]
    if suffix in (".cbz", ".zip"):
        try:
            archive = stack.enter_context(zipfile.ZipFile(path))
        except zipfile.BadZipFile:
            raise ComicPipelineError("not a readable zip/cbz archive") from None
        members = sorted((i for i in archive.infolist()
                          if not i.is_dir() and i.filename.lower().endswith(IMAGE_SUFFIXES)
                          and _safe_member(i.filename) and i.file_size <= MAX_MEMBER_BYTES
                          and "__MACOSX" not in i.filename),
                         key=lambda i: natural_key(i.filename))
        return [(PurePosixPath(i.filename.replace("\\", "/")).name, (lambda i=i: _from_bytes(archive.read(i))))
                for i in members]
    if suffix == ".pdf":
        import pypdfium2
        document = stack.enter_context(contextlib.closing(pypdfium2.PdfDocument(str(path))))

        def render(index):
            page = document[index]
            try:
                image = page.render(scale=PDF_RENDER_SCALE).to_pil().convert("RGB")
            finally:
                page.close()
            return image, _png_bytes(image)
        return [("%s-p%03d" % (path.stem, i + 1), (lambda i=i: render(i))) for i in range(len(document))]
    raise ComicPipelineError("unsupported input (use an image, a folder, .cbz/.zip or .pdf)")


def _from_file(path):
    return _from_bytes(path.read_bytes())


def _from_bytes(raw):
    return _decode_image(raw), raw


# ---------------------------------------------------------------- mock model

class MockComicAdapter:
    """No network: valid JSON derived from the request. Recognition answers one region per mark
    ("[source N]"); translation answers a conspicuous placeholder per region."""

    def __init__(self):
        self.calls = 0

    def generate(self, prompt_text, model):
        self.calls += 1
        text = str(prompt_text)
        if text.startswith("# Comic Independent Review"):
            return TextGenerationResult("mock_placeholder", json.dumps({"verdict": "PASS", "issues": []}),
                                        "not_metered", model, 0.0)
        if text.startswith("# Comic Source Re-reading") or text.startswith("# Comic Correction"):
            ids = [json.loads(line)["id"] for line in text.splitlines() if line.startswith('{"id"')]
            key, value = (("readings", "[source]") if text.startswith("# Comic Source")
                          else ("translations", MOCK_TRANSLATION % 0))
            body = {key: [{"id": i, "text": value} for i in ids]}
            return TextGenerationResult("mock_placeholder", json.dumps(body, ensure_ascii=False), "not_metered",
                                        model, 0.0)
        if text.startswith("# Comic Text Recognition"):
            count = int(re.search(r"numbered them 1 to (\d+)", text).group(1))
            body = {"regions": [{"marks": [n], "box": None, "kind": "speech", "text": "[source %d]" % n,
                                 "speaker": None, "speaker_gender": "unknown", "addressee_gender": "unknown",
                                 "order": n} for n in range(1, count + 1)],
                    "summary": "Mock page.", "characters": []}
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.startswith('{"id"')]
            shorten = text.startswith("# Comic Shortening")
            template = MOCK_SHORTENED if shorten else MOCK_TRANSLATION
            body = {"translations": [{"id": row["id"], "text": template % row["order"], "note": ""} for row in rows],
                    "notebook": {"characters": [], "terms": []}, "summary": "Mock page."}
        return TextGenerationResult("mock_placeholder", json.dumps(body, ensure_ascii=False), "not_metered",
                                    model, 0.0)


def _mock_adapter_factory():
    adapter = MockComicAdapter()
    return (lambda role, descriptor: adapter), adapter


def _configured_adapter_factory():
    """Real provider adapters the way the web UI builds them: the key comes from the provider's
    ``credential_env`` environment variable, else from the saved key store (Windows)."""
    saved = {}

    def stored_key(definition):
        if os.environ.get(definition.credential_env or ""):
            return None
        if not saved:
            from ..models.key_store import default_key_store
            store = default_key_store()
            saved["loaded"] = ""     # marks the lookup done (provider ids cannot be "loaded")
            try:
                saved.update(store.load_all() if store is not None else {})
            except OSError:
                pass
        return saved.get(definition.provider_id) or None

    def factory(role, descriptor):
        definition = descriptor.provider_definition
        key = stored_key(definition) if definition.provider_type != "mock" else None
        return build_translation_adapter(
            descriptor.provider, descriptor.model, provider_definition=definition,
            max_output_tokens=descriptor.max_output_tokens, reasoning=descriptor.capabilities.reasoning,
            api_key=key)
    return factory


# ---------------------------------------------------------------- controlled calls

class _Context:
    def __init__(self, job_id, configuration, store, journal, budget_usd, adapter_factory, sleep, review=False,
                 review_unit="page", recheck=True):
        self.job_id, self.configuration, self.store, self.journal = job_id, configuration, store, journal
        self.budget_usd, self.adapter_factory, self.sleep = budget_usd, adapter_factory, sleep
        selection, _ = configuration.resolve(ROLE)
        self.selection = selection
        self.model_cap = selection.capabilities.max_output_tokens or DEFAULT_OUTPUT_TOKENS
        self.shared_cap = max(s.capabilities.max_output_tokens or 4096 for s in configuration.models.values())
        self.stopped = None
        self.replays = 0
        self.review = review
        self.review_unit, self.recheck = review_unit, recheck
        self.editor = None
        self.placement_check = False
        # reading the page (recognition, re-reading, sign location, placement) may use its own model
        self.recognizer_role = RECOGNIZER_ROLE if RECOGNIZER_ROLE in configuration.models else ROLE
        self.fallbacks = []
        comic_review.parse_scope(review_unit)
        self.review_role = REVIEW_ROLE if REVIEW_ROLE in configuration.models else ROLE

    def spent(self):
        try:
            status = self.store.status(self.job_id)
        except RuntimeControlsError:
            return 0.0
        return status["list_estimated_spent_usd"] + status["held_usd"]

    def release_stop(self, base):
        """The user's standing rule for a failed provider call: while this failure row has cost less
        than AUTO_ACCEPT_BELOW_USD, accept the held charge and lift the stop so the call can be
        resent. False when the stop is not a cheap failure (a person must decide)."""
        try:
            if not self.store.status(self.job_id)["stopped"]:
                return True
            if max(0.0, self.spent() - base) >= AUTO_ACCEPT_BELOW_USD:
                return False
            for call in self.store.uncertain_calls(self.job_id):
                self.store.user_settle(self.job_id, call["event_id"])
            self.store.user_resume(self.job_id)
            return True
        except RuntimeControlsError:
            return False

    def call(self, stage, prompt, validator, dependencies, wanted_cap, role=ROLE):
        """One controlled call with the automatic retry rule: a failed, truncated or invalid answer
        is resent (a new attempt number gives a new identity) while this failure row has cost less
        than AUTO_ACCEPT_BELOW_USD and is shorter than AUTO_ACCEPT_MAX_STREAK; otherwise it raises."""
        cap = max(256, min(wanted_cap, self.model_cap, self.shared_cap))
        base, failures, attempt, skipped = self.spent(), 0, 0, 0
        while True:
            deps = dict(dependencies, attempt=attempt) if attempt else dict(dependencies)
            try:
                parsed, replay = chapter_pipeline._controlled(
                    self.job_id, role, stage, prompt, self.configuration, cap, self.store, self.journal,
                    self.budget_usd, MAX_CALLS, self.shared_cap, validator, deps, self.adapter_factory)
                self.replays += int(replay)
                return parsed
            except chapter_pipeline.PipelinePaused:
                raise
            except _FATAL:
                raise
            except TranslationBudgetError as exc:
                failures += 1
                # A stop left by an earlier failed call (e.g. a rerun) is lifted under the same rule.
                if failures > AUTO_ACCEPT_MAX_STREAK or not self.release_stop(base):
                    self.stopped = str(exc)
                    raise
            except (chapter_pipeline.ChapterPipelineError, comic_model.ComicModelError) as exc:
                message = str(exc)
                if message.startswith("previous call failed"):
                    attempt += 1      # an earlier attempt of this row (a rerun): go on to the next one
                    skipped += 1
                    if skipped > 10 * AUTO_ACCEPT_MAX_STREAK:
                        raise
                    continue
                if "unknown" in message and "refused" in message:
                    raise
                failures += 1
                if (failures > AUTO_ACCEPT_MAX_STREAK or not self.release_stop(base)
                        or max(0.0, self.spent() - base) >= AUTO_ACCEPT_BELOW_USD):
                    raise
                invalid = isinstance(exc, comic_model.ComicModelError) or "validation failed" in message
                if not invalid and role != ROLE and role == self.recognizer_role and failures >= 2:
                    # the separate recognition model keeps failing at the provider: read the rest of
                    # the run with the translator's model instead of waiting on it
                    self.recognizer_role = role = ROLE
                    self.fallbacks.append(stage)
                    attempt += 1
                    continue
                delay = 0 if invalid else AUTO_RETRY_DELAYS[min(failures, len(AUTO_RETRY_DELAYS)) - 1]
                if delay:
                    self.sleep(delay)
                attempt += 1


def _cap(base, count, each):
    return base + count * each


# ---------------------------------------------------------------- page processing

def check_placement(ctx, stages, page, image, base_deps):
    """One vision call per page: does each region's frame enclose its own lettering? A region
    reported misplaced is re-measured at the corrected box (warning ``placement_fixed``); a
    failed check changes nothing (warning ``placement_check_failed``)."""
    numbers = [r["order"] for r in page["regions"]]
    try:
        verdict = ctx.call(
            PLACEMENT_STAGE, comic_model.placement_prompt(image, page),
            lambda result: comic_model.parse_placement(result.text, numbers),
            dict(base_deps, stage=comic_model.PLACEMENT_VERSION,
                 regions=[[r["order"], r["source_text"], r["bbox"]] for r in page["regions"]]),
            _cap(2048, len(numbers), 80), role=ctx.recognizer_role)
    except _FATAL:
        raise
    except (chapter_pipeline.ChapterPipelineError, comic_model.ComicModelError, TranslationBudgetError):
        page["warnings"].append("placement_check_failed")
        return
    width, height = image.size
    for region in page["regions"]:
        box = verdict.get(region["order"])
        if box is None:
            continue
        pixels = comic_model._pixel_box(box, width, height)
        try:
            candidate = stages.snap_region(image, pixels)
            records.validate_candidate(candidate, "snap", width, height)
        except Exception:
            region["warnings"].append("placement_snap_failed")
            continue
        region.update({key: candidate.get(key) for key in ("bbox", "interior", "background", "plain_background",
                                                            "line_height", "confidence", "balloon")})
        region["warnings"].append("placement_fixed")


def drop_duplicate_boxes(page, limit=0.5):
    """A region whose box almost coincides with an earlier region's (the recogniser placed two
    texts on one balloon) is not typeset over it: it keeps its translation for the review page
    but gets no layout area, and warns ``overlapping_region``."""
    kept = []
    for region in page["regions"]:
        if any(_iou(region["bbox"], other["bbox"]) >= limit for other in kept):
            region["warnings"].append("overlapping_region")
            region["skip_layout"] = True
            continue
        kept.append(region)


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def apply_kinds(regions):
    """Lettering on an object (kind sign) is set on a backing patch, never as a balloon: the
    art around it must not be erased. Balloons keep the measured shape."""
    for region in regions:
        if region["kind"] == "sign":
            region["plain_background"], region["interior"] = False, None


def resolve_shared_words(regions):
    """A word claimed by several regions (a region's lettering grew into a neighbour's) belongs
    to the region whose recognised box (``source_box``) holds it deepest, else to the smallest
    region; the others drop it and their lettering box is rebuilt from the words they keep."""
    def area(b):
        return max(1, (b[2] - b[0]) * (b[3] - b[1]))

    def overlaps(w, other):
        ix = max(0, min(w[2], other[2]) - max(w[0], other[0]))
        iy = max(0, min(w[3], other[3]) - max(w[1], other[1]))
        return ix * iy >= 0.5 * min(area(w), area(other))

    def depth(box, w):
        if not box:
            return -1
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        return min(cx - box[0], box[2] - cx, cy - box[1], box[3] - cy)
    for region in regions:
        words = region.get("words")
        if not words:
            continue
        box, margin = region.get("source_box"), float(region.get("line_height") or 0)
        if box:   # a word far outside where the recogniser put this text is a neighbour's fragment
            near = [w for w in words if box[0] - margin <= (w[0] + w[2]) / 2 <= box[2] + margin
                    and box[1] - margin <= (w[1] + w[3]) / 2 <= box[3] + margin]
            words = near or words
        kept = []
        for w in words:
            rivals = [r for r in regions if r is not region and any(overlaps(w, o) for o in r.get("words") or [])]
            if not rivals:
                kept.append(w)
                continue
            contenders = [region] + rivals
            owner = max(contenders, key=lambda r: (depth(r.get("source_box"), w) > 0, depth(r.get("source_box"), w),
                                                  -area(r["bbox"])))
            if owner is region:
                kept.append(w)
        region["_kept"] = kept
    for region in regions:
        kept = region.pop("_kept", None)
        if kept is None or len(kept) == len(region["words"]) and kept == region["words"]:
            continue
        if not kept:
            region["words"] = []
            continue
        region["words"] = kept
        box = [min(w[0] for w in kept), min(w[1] for w in kept), max(w[2] for w in kept), max(w[3] for w in kept)]
        if area(box) >= 0.25 * area(region["bbox"]):        # never shrink to a speck
            region["bbox"] = box


def separate_regions(regions, gap=4, key="interior"):
    """Split the space between neighbouring regions by their actual lettering: a point of a
    region's text area (``key``) is kept only when it is at least as close to this region's
    words as to any other region's words (minus ``gap``). Bounding boxes of slanted or L-shaped
    lettering overlap; the words do not, so a small balloon next to a big one keeps its room.
    Of a row, the run nearest this region's own lettering is kept."""
    words = {id(r): r.get("words") or [r["bbox"]] for r in regions}
    for region in regions:
        interior = region.get(key)
        if not interior:
            continue
        own = words[id(region)]
        others = [(other, words[id(other)]) for other in regions if other is not region]
        if not others:
            continue
        rows = []
        for y, x0, x1 in interior["rows"]:
            near = [w for _, ws in others for w in ws if _gap_y(w, y) <= 4 * max(8, w[3] - w[1])]
            if not near:
                rows.append([y, x0, x1])
                continue
            step = max(1, (x1 - x0) // 120)
            runs, start = [], None
            for x in range(x0, x1 + step, step):
                inside = x < x1 and _dist(own, x, y) <= _dist(near, x, y) - gap
                if inside and start is None:
                    start = x
                elif not inside and start is not None:
                    runs.append((start, min(x, x1)))
                    start = None
            if not runs:
                continue
            centre = min(own, key=lambda w: _gap_y(w, y))
            cx = (centre[0] + centre[2]) / 2
            best = min(runs, key=lambda r: 0 if r[0] <= cx < r[1] else min(abs(cx - r[0]), abs(cx - r[1])))
            if best[1] > best[0]:
                rows.append([y, best[0], best[1]])
        region[key] = {"step": interior["step"], "rows": rows} if rows else None


def _gap_y(box, y):
    return max(box[1] - y, 0, y - box[3])


def _dist(boxes, x, y):
    best = None
    for b in boxes:
        dx = max(b[0] - x, 0, x - b[2])
        dy = max(b[1] - y, 0, y - b[3])
        d = (dx * dx + dy * dy) ** 0.5
        if best is None or d < best:
            best = d
    return best if best is not None else float("inf")


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _area_boxes(region):
    """Boxes a region occupies: its lettering box and each row of its text area."""
    boxes = [region["bbox"]]
    interior = region.get("interior")
    if interior:
        step = interior["step"]
        boxes += [[a, y, b, y + step] for y, a, b in interior["rows"]]
    return boxes


def make_room(regions):
    """``room``: the whole balloon area, kept off the neighbours, for text that does not fit
    the lettering shape."""
    for region in regions:
        if region.get("balloon"):
            region["room"] = {"step": region["balloon"]["step"], "rows": [list(r) for r in region["balloon"]["rows"]]}
    separate_regions(regions, key="room")


def should_mirror(mirror, source_language, target_code):
    """``auto``: mirror the page when a left-to-right comic is translated into a right-to-left
    language, so the panel grid is read right to left too (never for manga, already RTL)."""
    if mirror in (True, "yes"):
        return True
    if mirror in (False, "no"):
        return False
    if mirror != "auto":
        raise ComicPipelineError("mirror must be auto, yes or no")
    return target_languages.load(target_code).rtl and source_language not in comic_model.RIGHT_TO_LEFT_SOURCES


def _fit_region(stages, region, font, rtl, size, mirror=False):
    """Layout in output-page coordinates: on a mirrored page it is fitted to the mirrored region."""
    text = region["translation"]["text"]
    target = records.mirror_region(region, size[0]) if mirror else region
    layout = stages.fit(target, text, font, rtl, size[1], size[0])
    if layout.get("overflow") and target.get("room"):      # use the whole balloon before shrinking further
        roomy = stages.fit(dict(target, interior=target["room"]), text, font, rtl, size[1], size[0])
        if not roomy.get("overflow") or roomy["font_size"] > layout["font_size"]:
            layout = roomy
    region["layout"] = layout
    region["warnings"] = [w for w in region["warnings"] if w != "overflow"]
    if layout.get("overflow"):
        region["translation"]["status"] = "overflow"
        region["warnings"].append("overflow")
    else:
        region["translation"]["status"] = "ok"


def is_art_text(region):
    """Lettering that belongs to the artwork rather than to a plain balloon or caption: sound
    effects, signs, labels, screens and any text set on art (a backing box or a subtitle)."""
    layout = region.get("layout") or {}
    return region.get("kind") in ("sfx", "sign") or layout.get("style") in ("box", "subtitle")


def draw_footnotes(image, notes, pack=None):
    """Translator's footnotes for scene lettering kept in the original: a numbered marker beside
    the lettering and the notes, smallest readable size, in the page's bottom margin (or on a
    light strip at the bottom when the art reaches the edge). ``notes``: (region, shown region)."""
    from PIL import ImageDraw
    from . import typeset
    from ..export.common import reorder_bidi_line
    rtl = pack.rtl if pack else True
    width, height = image.size
    size = max(12, int(round(height * 0.012)))
    # a footnote quotes the original (accented Latin) next to Hebrew: a font with both scripts
    font = typeset._font(typeset.FONT_DIR / "davidlibre" / "DavidLibre-Regular.ttf", size)
    draw = ImageDraw.Draw(image)
    lines = []
    for number, (region, shown) in enumerate(notes, 1):
        marker = "*" * number if number <= 3 else "(%d)" % number
        x0, y0, x1, y1 = shown["bbox"]
        mark_font = typeset._font(typeset.FONT_DIR / "davidlibre" / "DavidLibre-Bold.ttf", int(size * 1.6))
        mw = mark_font.getlength(marker)
        mx = x0 - mw - 2 if rtl else x1 + 2
        draw.text((max(2, mx), max(2, y0 - size // 2)), marker, font=mark_font, fill=(20, 20, 20),
                  stroke_width=3, stroke_fill=(255, 255, 255))
        translation = region["translation"]
        note = region["source_text"]
        if translation.get("footnote"):      # the meaning matters: add it
            note = "%s: %s" % (note, translation["text"])
        wrapped = typeset._wrap("%s %s" % (marker, note), font, rtl, lambda i: width - 24) or [note]
        lines.extend(wrapped)
    line_h = int(size * 1.35)
    block = line_h * len(lines) + 6
    gray = image.convert("L")
    # the empty margin under the art: white rows from the bottom up
    free = 0
    for y in range(height - 1, -1, -1):
        row = gray.crop((0, y, width, y + 1)).getdata()
        if sum(1 for v in row if v < 200) > 0.02 * width:
            break
        free += 1
    if free < block + 4:
        # no room: extend the page downwards, never paint over the art
        taller = Image.new("RGB", (width, height + block + 8 - free), (255, 255, 255))
        taller.paste(image, (0, 0))
        image, height = taller, taller.height
        draw = ImageDraw.Draw(image)
        free = block + 8
    top = height - free + max(0, (free - block) // 2)
    y = top + 3
    for line in lines:
        visual = reorder_bidi_line(line, rtl_paragraph=True) if rtl else line
        w = font.getlength(visual)
        x = width - 12 - w if rtl else 12
        draw.text((x, y), visual, font=font, fill=(20, 20, 20))
        y += line_h
    return image


def stages_font(pack):
    from . import typeset
    return typeset.font_for(pack.code if pack else "he")


KEEP_FLAT_DEGREES = 6.0   # kept lettering slanted less than this is restored by pasting the original


def keep_original(base, image, region, mirror, editor=None, source_language=None, locate=None):
    """Lettering the translator chose to keep (a name, a word readable as it stands) stays in
    the original. On a mirrored page it must read the right way: flat lettering is restored by
    pasting the unmirrored original at its mirrored place (free); slanted lettering, whose
    perspective would turn the wrong way, is re-lettered with the same original text by the
    image model when one is available. Returns the method."""
    region["edited"] = True
    if not mirror:
        return "kept"
    width, height = image.size
    angle = abs(comic_edit.lettering_geometry(image, region)["angle"])
    if angle > KEEP_FLAT_DEGREES and editor is not None:
        target = records.mirror_region(region, width)
        try:
            editor.edit(base, dict(target, kind="sign"), region["source_text"],
                        comic_model.LANGUAGE_NAMES.get(source_language, "the original language"), False,
                        (lambda img, reg, src=region["source_text"]: locate(img, reg, src)) if locate else None)
            return "kept-relettered"
        except comic_edit.SignEditError as exc:
            region["warnings"].append("keep_edit_failed: %s" % exc)
    x0, y0, x1, y1 = region["bbox"]
    box = (max(0, x0 - 3), max(0, y0 - 3), min(width, x1 + 3), min(height, y1 + 3))
    base.paste(image.crop(box), (width - box[2], box[1]))
    return "kept"


def _render(stages, image, regions, mirror, editor=None, pack=None, locate=None, source_language=None):
    """Output page. Mirrored: the page is flipped, sound effects left in the art are put back
    unflipped (readable) at their mirrored place, and the mirrored regions are rendered. With an
    ``editor``, every piece of lettering in the art (sound effects, signs, labels, text on art) is
    re-lettered in place by an image model (on the output page, so the new text reads correctly);
    one whose edit fails keeps its backing patch or subtitle."""
    placed = [r for r in regions if r["layout"] is not None]
    width, height = image.size
    base = ImageOps.mirror(image) if mirror else image.copy()
    if mirror:
        for region in placed:
            # an unflipped sound effect is pasted back only when it stays as drawn; one that an
            # image model re-letters is edited on the mirrored art (a pasted patch leaves a seam)
            if region["layout"]["style"] == "subtitle" and editor is None:
                x0, y0, x1, y1 = region["bbox"]
                box = (max(0, x0 - 2), max(0, y0 - 2), min(width, x1 + 2), min(height, y1 + 2))
                base.paste(image.crop(box), (width - box[2], box[1]))
    shown = [records.mirror_region(r, width) for r in regions] if mirror else regions
    if editor is not None:
        # balloons are erased BEFORE the art is re-lettered, so a balloon's erase can never wipe
        # out new lettering an image edit just drew next to it
        erase = getattr(stages, "erase_balloons", None)
        if erase is not None:
            erase(base, shown)
        for region in placed:
            if not is_art_text(region) or not region.get("translation"):
                continue
            if region["translation"].get("keep_original"):
                region["edited"], region["edit_method"] = True, "kept-as-drawn"
                continue
            target = records.mirror_region(region, width) if mirror else region
            try:
                method = editor.edit(base, target, region["translation"]["text"], pack.name if pack else "Hebrew",
                                     pack.rtl if pack else True,
                                     (lambda img, reg, src=region["source_text"]: locate(img, reg, src)) if locate
                                     else None)
                region["edited"], region["edit_method"] = True, method
            except comic_edit.SignEditError as exc:
                region["warnings"].append("sign_edit_failed: %s" % exc)
    if editor is None:
        for region in placed:
            if is_art_text(region) and (region.get("translation") or {}).get("keep_original"):
                region["edited"], region["edit_method"] = True, "kept-as-drawn"
    shown = [records.mirror_region(r, width) for r in regions] if mirror else regions   # with "edited" flags
    if editor is not None and getattr(stages, "erase_balloons", None) is not None:
        out = stages.render_page(base, shown, erase=False)
    else:
        out = stages.render_page(base, shown)
    notes = [(r, s) for r, s in zip(regions, shown) if (r.get("translation") or {}).get("keep_original")]
    if notes:
        out = draw_footnotes(out, notes, pack)
    return out


def _failed(page, exc):
    page["status"] = "failed"
    page["warnings"].append("error: %s: %s" % (type(exc).__name__, str(exc)[:300]))


def prepare_page(ctx, stages, number, name, image, raw, source_language, target_code, notebook, summaries,
                 dialogue=None):
    """Detection, recognition and translation of one page (always on the original page). The
    page's summary and dialogue feed the next page's translation right away. Returns the page;
    a failure marks it ``failed``."""
    pack = target_languages.load(target_code)
    page = records.new_page(number, name, raw, image.width, image.height)
    page["versions"] = {"detect": stages.DETECT_VERSION, "typeset": stages.TYPESET_VERSION,
                        "recognition": comic_model.RECOGNITION_VERSION,
                        "translation": comic_model.TRANSLATION_VERSION, "shorten": comic_model.SHORTEN_VERSION}
    if ctx.stopped:
        page["status"] = "failed"
        page["warnings"].append("error: skipped, %s" % ctx.stopped)
        return page
    base_deps = _base_deps(page, stages, source_language, target_code)
    try:
        candidates = []
        for i, candidate in enumerate(stages.detect_candidates(image)):
            try:
                records.validate_candidate(candidate, "candidate", image.width, image.height)
                candidates.append(candidate)
            except records.ComicRecordError:
                page["warnings"].append("invalid_candidate:%d" % (i + 1))
        prompt = comic_model.recognition_prompt(image, candidates, source_language, notebook)
        parsed = ctx.call(
            RECOGNITION_STAGE, prompt, lambda result: comic_model.parse_recognition(result.text, len(candidates)),
            dict(base_deps, stage=comic_model.RECOGNITION_VERSION, marks=len(candidates)),
            _cap(8192, len(candidates), 400), role=ctx.recognizer_role)
        page["regions"] = comic_model.reconcile(page, image, candidates, parsed, stages.snap_region)
        if ctx.placement_check and page["regions"]:
            check_placement(ctx, stages, page, image, base_deps)
        apply_kinds(page["regions"])
        drop_duplicate_boxes(page)
        resolve_shared_words(page["regions"])
        separate_regions(page["regions"])
        make_room(page["regions"])
        page["summary"] = parsed["summary"]
        page["panels"] = parsed.get("panels", [])
        page["status"] = "recognised"
        update = records.new_notebook()
        update["characters"] = [{"name": c["name"], "target_name": "", "gender": c["gender"],
                                 "note": c["appearance"]} for c in parsed["characters"]]
        _merge(notebook, update, page)
        if not page["regions"]:
            page["warnings"].append("no_text")
            return page
        font = stages.font_for(target_code)
        for region in page["regions"]:
            region["capacity"] = max(1, int(stages.capacity(region, font, pack.rtl, image.height)))
        answer = _translate(ctx, image, page, page["regions"], notebook, summaries, source_language, target_code,
                            dialogue, base_deps)
        for item, region in zip(answer["translations"], page["regions"]):
            region["translation"] = {"text": item["text"], "status": "ok", "note": item["note"]}
            if region["kind"] == "sign":      # scene lettering stays in the original
                region["translation"]["keep_original"] = True
                if item.get("footnote"):
                    region["translation"]["footnote"] = True
        _merge(notebook, answer["notebook"], page)
        page["summary"] = answer["summary"] or page["summary"]
        page["status"] = "translated"
        summaries.append(page["summary"])
        if dialogue is not None:   # the next page's translator sees this page's dialogue
            dialogue[:] = [{"speaker": r["speaker"], "source": r["source_text"], "target": r["translation"]["text"]}
                           for r in page["regions"]]
        return page
    except _FATAL:
        raise
    except Exception as exc:
        _failed(page, exc)
        return page


def _base_deps(page, stages, source_language, target_code):
    return {"page": page["index"], "image": page["image_sha256"], "detect": stages.DETECT_VERSION,
            "source": source_language, "target": target_code}


def _merge(notebook, update, page):
    merged, warnings = comic_model.merge_notebook(notebook, update)
    notebook.clear()
    notebook.update(merged)
    page["warnings"].extend(w for w in warnings if w not in page["warnings"])


def _translate(ctx, image, page, regions, notebook, summaries, source_language, target_code, dialogue, base_deps):
    ids = [r["region_id"] for r in regions]
    kinds = {r["region_id"]: r["kind"] for r in regions}
    sources = {r["region_id"]: r["source_text"] for r in regions}
    capacities = {r["region_id"]: r.get("capacity", 0) for r in regions}
    view = dict(page, regions=regions)
    prompt = comic_model.translation_prompt(image, view, notebook, summaries, source_language, target_code,
                                            capacities, dialogue)
    deps = dict(base_deps, stage=comic_model.TRANSLATION_VERSION, regions=ids)
    if len(regions) != len(page["regions"]):   # a retranslation after a fresh reading of the source
        deps["sources"] = sources
    return ctx.call(TRANSLATION_STAGE, prompt,
                    lambda result: comic_model.parse_translation(result.text, ids, target_code, kinds, sources),
                    deps, _cap(6144, len(ids), 400))


def review_group(ctx, stages, group, images, notebook, source_language, target_code):
    """The literary review mechanism over ``group`` (translated pages), unit by unit."""
    for unit in comic_review.units(group, ctx.review_unit):
        try:
            _review_unit(ctx, stages, unit, images, notebook, source_language, target_code)
        except _FATAL:
            raise
        except (chapter_pipeline.ChapterPipelineError, comic_model.ComicModelError, TranslationBudgetError) as exc:
            for page, _ in unit:
                if "review_failed" not in page["warnings"]:
                    page["warnings"].append("review_failed")
            if isinstance(exc, TranslationBudgetError):
                return


def _unit_deps(unit, stages, source_language, target_code, stage):
    return {"stage": stage, "detect": stages.DETECT_VERSION, "source": source_language, "target": target_code,
            "images": [page["image_sha256"] for page, _ in unit],
            "regions": {comic_review.label(r): [r["source_text"], r["translation"]["text"]]
                        for _, regions in unit for r in regions}}


def _review_unit(ctx, stages, unit, images, notebook, source_language, target_code):
    by_label = {comic_review.label(r): (page, r) for page, regions in unit for r in regions}
    labels = list(by_label)
    kinds = {name: r["kind"] for name, (_, r) in by_label.items()}
    issues = ctx.call(
        REVIEW_STAGE, comic_review.critic_prompt(unit, images, notebook, source_language, target_code),
        lambda result: comic_review.parse_critique(result.text, labels),
        _unit_deps(unit, stages, source_language, target_code, comic_review.CRITIC_VERSION),
        _cap(6144, len(labels), 300), role=ctx.review_role)
    for page, _ in unit:
        page["reviewed"] = page.get("reviewed", 0) + sum(1 for i in issues if by_label[i["id"]][0] is page)
    rereads, pending, changed = {}, {}, set()
    for issue in issues:
        page, region = by_label[issue["id"]]
        record = region["translation"].setdefault("review", {"issues": [], "applied": [], "notes": []})
        record["issues"].append(issue)
        if issue["category"] == comic_review.SOURCE_READING:
            rereads.setdefault(issue["id"], issue)
    for issue in issues:
        name = issue["id"]
        if issue["category"] == comic_review.SOURCE_READING or name in rereads:
            continue
        region = by_label[name][1]
        translation, record = region["translation"], region["translation"]["review"]
        if not comic_review.applies(issue):
            record["notes"].append(issue)
            continue
        replaced = comic_review.apply_span(translation["text"], issue)
        if replaced is not None:
            try:
                comic_model._check_script(replaced, target_code, name)
            except comic_model.ComicModelError:
                replaced = None
        if replaced is None:
            pending.setdefault(name, []).append(issue)
            continue
        record.setdefault("previous", translation["text"])
        translation["text"] = replaced
        record["applied"].append(dict(issue, method="span"))
        changed.add(name)
    if pending:
        sources = {name: by_label[name][1]["source_text"] for name in pending}
        fixed = ctx.call(
            CORRECTION_STAGE,
            comic_review.correction_prompt(unit, images, pending, notebook, source_language, target_code),
            lambda result: comic_review.parse_correction(result.text, list(pending), target_code, kinds, sources),
            dict(_unit_deps(unit, stages, source_language, target_code, comic_review.CORRECTION_VERSION),
                 pending={name: [i["suggested_correction"] for i in items] for name, items in pending.items()}),
            _cap(4096, len(pending), 400))
        for name, text in fixed.items():
            translation = by_label[name][1]["translation"]
            record = translation["review"]
            record.setdefault("previous", translation["text"])
            translation["text"] = text
            record["applied"].extend(dict(issue, method="correction") for issue in pending[name])
            changed.add(name)
    if rereads:
        _reread(ctx, stages, unit, images, by_label, rereads, notebook, source_language, target_code)
        changed.update(rereads)
    if changed and ctx.recheck:
        focus = sorted(changed)
        notes = ctx.call(
            REVIEW_STAGE,
            comic_review.critic_prompt(unit, images, notebook, source_language, target_code, focus=set(focus)),
            lambda result: comic_review.parse_critique(result.text, focus),
            dict(_unit_deps(unit, stages, source_language, target_code, comic_review.CRITIC_VERSION),
                 recheck=focus), _cap(4096, len(focus), 300), role=ctx.review_role)
        for issue in notes:   # each finding is sent once: recheck findings are recorded, not applied
            by_label[issue["id"]][1]["translation"]["review"].setdefault("recheck", []).append(issue)


def _reread(ctx, stages, unit, images, by_label, rereads, notebook, source_language, target_code):
    """Fresh reading of doubted lettering, then a retranslation of the regions whose reading
    changed (recorded on the region; the earlier transcription is kept)."""
    names = sorted(rereads)
    items = [by_label[name] for name in names]
    readings = ctx.call(
        REREAD_STAGE, comic_review.reread_prompt(items, images, rereads, source_language),
        lambda result: comic_review.parse_reread(result.text, names),
        dict(_unit_deps(unit, stages, source_language, target_code, comic_review.REREAD_VERSION), reread=names),
        _cap(2048, len(names), 300), role=ctx.recognizer_role)
    by_page = {}
    for name in names:
        page, region = by_label[name]
        if readings[name] != region["source_text"]:
            region["source_reread"] = {"previous": region["source_text"], "reviewer": rereads[name]["source_span"]}
            region["source_text"] = readings[name]
            by_page.setdefault(page["index"], (page, []))[1].append(region)
    for page, regions in by_page.values():
        answer = _translate(ctx, images[page["index"]], page, regions, notebook, [], source_language, target_code,
                            None, _base_deps(page, stages, source_language, target_code))
        for item, region in zip(answer["translations"], regions):
            record = region["translation"]["review"]
            record.setdefault("previous", region["translation"]["text"])
            region["translation"]["text"] = item["text"]
            record["applied"].append(dict(rereads[comic_review.label(region)], method="reread"))


def _locator(ctx, page):
    """Sign locator for the editor's fallback: a journaled vision call returning the lettering's
    quadrilateral on the editor's crop (a failure becomes a SignEditError: backing patch)."""
    def locate(image, region, source):
        box, prompt = comic_edit.quad_prompt(image, region, source)
        try:
            return ctx.call(LOCATE_STAGE, prompt, lambda result: _quad(result.text),
                            {"stage": "comic-sign-locate@1", "page": page["index"], "image": page["image_sha256"],
                             "region": region["region_id"], "box": list(box), "source": source}, 2048,
                            role=ctx.recognizer_role)
        except _FATAL:
            raise
        except (chapter_pipeline.ChapterPipelineError, comic_model.ComicModelError, TranslationBudgetError) as exc:
            raise comic_edit.SignEditError("the sign could not be located (%s)" % type(exc).__name__) from None
    return locate


def _quad(text):
    try:
        return comic_edit.parse_quad(text)
    except comic_edit.SignEditError as exc:
        raise comic_model.ComicModelError(str(exc)) from None


def finish_page(ctx, stages, page, image, source_language, target_code, mirror=False):
    """Typesetting (at most one shorten call) and rendering; returns the output image (the
    original, unmirrored, for a failed page)."""
    if page["status"] == "failed":
        return image
    if not page["regions"]:
        page["status"] = "rendered"
        return image
    pack = target_languages.load(target_code)
    font = stages.font_for(target_code)
    base_deps = _base_deps(page, stages, source_language, target_code)
    try:
        kinds = {r["region_id"]: r["kind"] for r in page["regions"]}
        sources = {r["region_id"]: r["source_text"] for r in page["regions"]}
        trim = getattr(stages, "trim_to_ink", None)
        if trim is not None:          # text areas end at drawn lines of the page as it will look
            erased = image.copy()
            stages.erase_balloons(erased, page["regions"])
            for region in page["regions"]:
                if region.get("plain_background"):
                    trim(region, erased)
                    trim(region, erased, "room")
        for region in page["regions"]:
            if region.get("skip_layout"):
                region["translation"]["status"] = "skipped"
                continue
            _fit_region(stages, region, font, pack.rtl, image.size, mirror)
        over = [r for r in page["regions"] if r["translation"]["status"] == "overflow"]
        if over:
            items = [{"id": r["region_id"], "text": r["translation"]["text"], "max_chars": r.get("capacity", 0)}
                     for r in over]
            over_ids = [i["id"] for i in items]
            current = {i["id"]: i["text"] for i in items}
            try:
                shorter = ctx.call(
                    SHORTEN_STAGE, comic_model.shorten_prompt(image, page, items, target_code),
                    lambda result: comic_model.parse_shorten(result.text, over_ids, target_code, current, kinds,
                                                             sources),
                    dict(base_deps, stage=comic_model.SHORTEN_VERSION, typeset=stages.TYPESET_VERSION,
                         regions=over_ids, current=current), _cap(4096, len(items), 300))
            except _FATAL:
                raise
            except (chapter_pipeline.ChapterPipelineError, comic_model.ComicModelError, TranslationBudgetError):
                page["warnings"].append("shorten_failed")
            else:
                for region in over:
                    region["translation"]["text"] = shorter[region["region_id"]]
                    _fit_region(stages, region, font, pack.rtl, image.size, mirror)
        rendered = _render(stages, image, page["regions"], mirror, ctx.editor, pack, _locator(ctx, page),
                           source_language)
        page["mirrored"] = mirror
        page["status"] = "rendered"
        return rendered
    except _FATAL:
        raise
    except Exception as exc:
        _failed(page, exc)
        return image


def process_page(ctx, stages, number, name, image, raw, comic, source_language, target_code, notebook, summaries,
                 mirror=False, dialogue=None):
    """One page end to end (prepare, review as a one-page unit, finish); returns ``(page, image)``."""
    page = prepare_page(ctx, stages, number, name, image, raw, source_language, target_code, notebook, summaries,
                        dialogue)
    if ctx.review and page["status"] == "translated":
        review_group(ctx, stages, [page], {page["index"]: image}, notebook, source_language, target_code)
    return page, finish_page(ctx, stages, page, image, source_language, target_code, mirror)


# ---------------------------------------------------------------- outputs

def _write_cbz(path, pages_dir, names, language=None, rtl=False):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name in names:
            archive.write(pages_dir / name, name)
        if rtl:  # comic readers turn pages right to left
            archive.writestr("ComicInfo.xml", '<?xml version="1.0" encoding="utf-8"?>\n<ComicInfo>'
                             '<LanguageISO>%s</LanguageISO><Manga>YesAndRightToLeft</Manga></ComicInfo>\n'
                             % html.escape(language or ""))


def _write_pdf(path, images):
    first, rest = images[0], images[1:]
    first.save(path, "PDF", save_all=True, append_images=rest, resolution=150.0)


def _cell(text, rtl=False):
    return '<td%s>%s</td>' % (' dir="rtl" lang="he"' if rtl else "", html.escape(text or ""))


def render_review(comic, names, rtl, html_lang, mock):
    """Side-by-side review page (relative links, escaped text)."""
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Comic review</title>'
             '<style>body{font:14px sans-serif;margin:1em 2em}.pair{display:flex;gap:1em;align-items:flex-start}'
             '.pair img{max-width:48%;height:auto;border:1px solid #888}table{border-collapse:collapse;margin:1em 0;'
             'width:100%}td,th{border:1px solid #ccc;padding:.3em .5em;vertical-align:top}.warn{color:#a40}'
             '.failed{color:#b00;font-weight:bold}</style></head><body>',
             "<h1>Comic review: %s to %s</h1>" % (html.escape(comic["source_language"]),
                                                  html.escape(comic["target_language"]))]
    if mock:
        parts.append("<p class=\"warn\">Mock run: the translations are placeholders, not real text.</p>")
    for page, name in zip(comic["pages"], names):
        parts.append('<section><h2>Page %d <small>%s</small></h2>' % (page["index"], html.escape(page["source_name"])))
        if page["status"] == "failed":
            parts.append('<p class="failed">This page failed; the original is shown.</p>')
        parts.append('<div class="pair"><a href="originals/%s"><img src="originals/%s" alt="original"></a>'
                     '<a href="pages/%s"><img src="pages/%s" alt="translated"></a></div>' % ((name,) * 4))
        if page["summary"]:
            parts.append("<p>%s</p>" % html.escape(page["summary"]))
        if page["warnings"]:
            parts.append('<p class="warn">Page warnings: %s</p>' % html.escape("; ".join(page["warnings"])))
        parts.append("<table><tr><th>Order</th><th>Kind</th><th>Speaker</th><th>Source</th><th>Translation</th>"
                     "<th>Warnings</th></tr>")
        for region in page["regions"]:
            translation = region["translation"] or {}
            notes = list(region["warnings"])
            review = translation.get("review") or {}
            for issue in review.get("applied", []):
                notes.append("applied %s/%s (%s): %s" % (issue["category"], issue["severity"], issue["method"],
                                                        issue["problem"]))
            for issue in review.get("notes", []):
                notes.append("note %s/%s: %s" % (issue["category"], issue["severity"], issue["problem"]))
            for issue in review.get("recheck", []):
                notes.append("recheck %s/%s: %s" % (issue["category"], issue["severity"], issue["problem"]))
            if review.get("previous"):
                notes.append("was: %s" % review["previous"])
            if region.get("source_reread"):
                notes.append("source re-read; was: %s" % region["source_reread"]["previous"])
            parts.append("<tr><td>%d</td>%s%s%s%s%s</tr>" % (
                region["order"], _cell(region["kind"]), _cell(region["speaker"]), _cell(region["source_text"]),
                _cell(translation.get("text"), rtl), _cell("; ".join(notes))))
        parts.append("</table></section>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _read_notebook(path):
    if not path or not Path(path).is_file():
        return records.new_notebook()
    try:
        return records.validate_notebook(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ComicPipelineError("cannot read the notebook %s (%s)" % (path, exc)) from None


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- run

def _settle_budget(store, comic_id, budget_usd):
    """A task's budget is fixed by its first call. A higher ``--budget-usd`` on a later run is
    the user raising the ceiling (recorded as a user decision); a lower one keeps the stored
    ceiling, which is returned."""
    try:
        stored = store.status(comic_id)["hard_list_usd"]
    except RuntimeControlsError:
        return budget_usd                      # no call yet: the first call fixes the policy
    if budget_usd > stored:
        store.user_raise_limits(comic_id, hard_list_usd=budget_usd)
        return budget_usd
    return stored


def run_comic(input_path, out_dir, source_language, target_code, model="mock", model_config=None, budget_usd=1.0,
              pages=None, notebook_path=None, adapter_factory=None, stages=None, progress=None, sleep=None,
              mirror="auto", review=True, configuration=None, review_unit="page", recheck=True,
              edit_art_text=False, edit_budget_usd=1.0, edit_quality="medium", edit_client=None,
              placement_check=False):
    """Translate a comic into ``out_dir`` and return the validated comic dict."""
    if model not in ("mock", "configured"):
        raise ComicPipelineError("model must be mock or configured")
    try:
        target_languages.load(target_code)
    except target_languages.TargetLanguageError as exc:
        raise ComicPipelineError(str(exc)) from None
    pack = target_languages.load(target_code)
    mirror = should_mirror(mirror, source_language, target_code)
    out = Path(out_dir)
    stages = stages or default_stages()
    sleep = sleep or time.sleep
    mock_adapter = None
    if model == "mock":
        configuration = ModelConfiguration.from_dict(MOCK_CONFIG)
        if adapter_factory is None:
            adapter_factory, mock_adapter = _mock_adapter_factory()
    else:
        if configuration is None:
            if not model_config:
                raise ComicPipelineError("--model configured needs --model-config PATH or --translator")
            configuration = load_model_configuration(model_config)
        configuration.resolve(ROLE)
        adapter_factory = adapter_factory or _configured_adapter_factory()
    notebook = _read_notebook(notebook_path)
    for sub in ("pages", "originals", ".state"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    selected = parse_pages(pages)
    comic_id = "comic-" + hashlib.sha256(
        ("%s|%s|%s" % (Path(input_path).name, source_language, target_code)).encode("utf-8")).hexdigest()[:12]
    comic = records.new_comic(comic_id, source_language, target_code)
    names, images = [], []
    store = ControlStore(validate_store_path(out / ".state" / "controls.sqlite3"), create=True)
    try:
        with contextlib.ExitStack() as stack, WorkJournal(out / ".state" / "journal.sqlite3", create=True) as journal:
            sources = open_input(input_path, stack)
            if not sources:
                raise ComicPipelineError("the input holds no images")
            if selected is not None:
                selected = parse_pages(pages, len(sources))
            todo = [(i + 1, s) for i, s in enumerate(sources) if selected is None or (i + 1) in selected]
            budget_usd = _settle_budget(store, comic_id, budget_usd)
            ctx = _Context(comic_id, configuration, store, journal, budget_usd, adapter_factory, sleep, review,
                           review_unit, recheck)
            ctx.placement_check = placement_check
            if edit_art_text:
                ctx.editor = comic_edit.SignEditor(out / ".state", edit_client or _openai_image_client(),
                                                   edit_budget_usd, edit_quality)
            summaries, dialogue = [], []
            group_size = comic_review.parse_scope(review_unit)[1] if review else 1
            results, group = [], []

            def flush():
                if review and group:
                    review_group(ctx, stages, [page for page, _ in group], {page["index"]: image
                                 for page, image in group}, notebook, source_language, target_code)
                for page, image in group:
                    rendered = finish_page(ctx, stages, page, image, source_language, target_code, mirror)
                    file_name = "%03d.png" % page["index"]
                    image.save(out / "originals" / file_name)
                    rendered.save(out / "pages" / file_name)
                    results.append((page, file_name, rendered))
                    if progress:
                        progress(len(results), len(todo), page["page_id"])
                group.clear()

            for number, (name, load) in todo:
                try:
                    image, raw = load()
                except ComicPipelineError as exc:
                    flush()
                    page = records.new_page(number, name, b"unreadable", 1, 1)
                    page["status"] = "failed"
                    page["warnings"].append("error: %s" % exc)
                    results.append((page, None, None))
                    continue
                page = prepare_page(ctx, stages, number, name, image, raw, source_language, target_code, notebook,
                                    summaries, dialogue)
                group.append((page, image))
                if len(group) >= group_size:
                    flush()
            flush()
            for page, file_name, rendered in results:
                comic["pages"].append(page)
                names.append(file_name)
                images.append(rendered)
            comic["notebook"] = notebook
            records.validate_comic(comic)
    finally:
        store.close()
    good = [(n, i) for n, i in zip(names, images) if n]
    if good:
        _write_cbz(out / "comic.cbz", out / "pages", [n for n, _ in good], target_code, pack.rtl)
        _write_pdf(out / "comic.pdf", [i for _, i in good])
    _write_json(out / "comic.json", comic)
    reviewed = [p for p, n in zip(comic["pages"], names) if n]
    review_comic = dict(comic, pages=reviewed)
    (out / "review.html").write_text(
        render_review(review_comic, [n for n in names if n], pack.rtl, pack.html_lang, model == "mock"),
        encoding="utf-8")
    if notebook_path:
        _write_json(Path(notebook_path), notebook)
    return comic


# ---------------------------------------------------------------- CLI

def _safe_print(text):
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    print(text.encode(encoding, "replace").decode(encoding))


def summarize(comic, out_dir):
    pages = comic["pages"]
    counts = {}
    for page in pages:
        counts[page["status"]] = counts.get(page["status"], 0) + 1
    overflow = sum(1 for p in pages for r in p["regions"] if "overflow" in r["warnings"])
    lines = ["pages: %d (%s)" % (len(pages), ", ".join("%s %d" % item for item in sorted(counts.items()))),
             "regions: %d, overflow: %d" % (sum(len(p["regions"]) for p in pages), overflow),
             "output: %s" % out_dir]
    for page in pages:
        if page["status"] == "failed":
            lines.append("page %d failed: %s" % (page["index"], "; ".join(w for w in page["warnings"]
                                                                             if w.startswith("error"))))
    return "\n".join(lines)


def _openai_image_client():
    """OpenAI client for image edits; the key comes from OPENAI_API_KEY or the saved key store."""
    import openai
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        from ..models.key_store import default_key_store
        store = default_key_store()
        key = (store.load_all() if store is not None else {}).get("openai")
    if not key:
        raise ComicPipelineError("sign editing needs an OpenAI key (OPENAI_API_KEY or the saved key)")
    return openai.OpenAI(api_key=key, max_retries=0, timeout=comic_edit.EDIT_TIMEOUT_SECONDS)


def _catalogue_selection(spec):
    parts = (spec or "").split(":")
    if len(parts) not in (2, 3) or not all(parts):
        raise ComicPipelineError("model spec must be PROVIDER:MODEL[:REASONING], got %r" % spec)
    selection = {"source": "catalog", "provider": parts[0], "model": parts[1]}
    if len(parts) == 3:
        selection["reasoning"] = parts[2]
    return selection


def catalogue_configuration(translator, reviewer=None, recognizer=None):
    """Model configuration from catalogue specs, built the way the web UI builds it (keys come
    from the provider's environment variable or the saved key store). ``recognizer`` adds the
    comic_recognizer role (reading the page) with its own model."""
    from ..models.settings import ModelSettingsError, build_configuration
    roles = {"translator": _catalogue_selection(translator)}
    if reviewer:
        roles["semantic_reviewer"] = _catalogue_selection(reviewer)
    try:
        configuration = build_configuration(roles)
        if not recognizer:
            return configuration
        reading = build_configuration({"translator": _catalogue_selection(recognizer)}).to_dict()
        merged = configuration.to_dict()
        model = reading["models"]["translator"]
        provider_id = model["provider"]
        if provider_id in merged["providers"] and merged["providers"][provider_id] != reading["providers"][provider_id]:
            provider_id += "-recognizer"
        merged["providers"][provider_id] = reading["providers"][model["provider"]]
        merged["models"][RECOGNIZER_ROLE] = dict(model, provider=provider_id)
        return ModelConfiguration.from_dict(merged)
    except ModelSettingsError as exc:
        raise ComicPipelineError(str(exc)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m scholarly_translation.comics.pipeline",
                                     description="Translate comic pages in place.")
    parser.add_argument("input", help="image, folder of images, .cbz/.zip or .pdf")
    parser.add_argument("--out", required=True, help="output folder")
    parser.add_argument("--source-language", required=True, choices=sorted(comic_model.LANGUAGE_NAMES))
    parser.add_argument("--target", required=True, help="target language code (he)")
    parser.add_argument("--model", choices=("mock", "configured"), default="mock")
    parser.add_argument("--model-config", help="model configuration JSON (for --model configured)")
    parser.add_argument("--budget-usd", type=float, default=1.0)
    parser.add_argument("--pages", help="pages to process, e.g. 1-5,8")
    parser.add_argument("--notebook", help="comic notebook JSON shared across volumes (read, then written)")
    parser.add_argument("--translator", help="catalogue model for recognition and translation, "
                                             "PROVIDER:MODEL[:REASONING], e.g. openai:gpt-6.1-sol:high")
    parser.add_argument("--reviewer", help="catalogue model for the review pass (default: the translator)")
    parser.add_argument("--recognizer", help="catalogue model for reading the page (recognition, re-reading, "
                                             "placement; default: the translator)")
    parser.add_argument("--placement-check", choices=("on", "off"), default="off",
                        help="one vision call per page verifying that each region's box holds its lettering")
    parser.add_argument("--review", choices=("on", "off"), default="on",
                        help="independent review (literary mechanism) whose findings are applied automatically")
    parser.add_argument("--review-unit", default="page",
                        help="how much one review call covers: panel, page or pages:N (default page)")
    parser.add_argument("--recheck", choices=("on", "off"), default="on",
                        help="focused recheck of corrected regions (findings recorded, not applied)")
    parser.add_argument("--edit-art-text", "--edit-signs", dest="edit_art_text", choices=("on", "off"),
                        default="off", help="re-letter text in the artwork (sound effects, signs, labels, text on "
                                            "art) in place with an image model (paid, cached)")
    parser.add_argument("--edit-budget-usd", type=float, default=1.0, help="ceiling for sign edits")
    parser.add_argument("--edit-quality", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--mirror", choices=("auto", "yes", "no"), default="auto",
                        help="mirror pages so the panels read right to left (auto: LTR comic into an RTL language)")
    args = parser.parse_args(argv)
    try:
        configuration = None
        if args.translator:
            configuration = catalogue_configuration(args.translator, args.reviewer, args.recognizer)
            args.model = "configured"
        comic = run_comic(args.input, args.out, args.source_language, args.target, args.model, args.model_config,
                          args.budget_usd, args.pages, args.notebook, mirror=args.mirror,
                          review=args.review == "on", configuration=configuration, review_unit=args.review_unit,
                          recheck=args.recheck == "on", edit_art_text=args.edit_art_text == "on",
                          placement_check=args.placement_check == "on",
                          edit_budget_usd=args.edit_budget_usd, edit_quality=args.edit_quality,
                          progress=lambda done, total, page_id: _safe_print("%s done (%d/%d)" % (page_id, done, total)))
    except (ComicPipelineError, ModelConfigError, OpenAIConfigurationError, RuntimeControlsError) as exc:
        _safe_print("error: %s" % exc)
        return 2
    _safe_print(summarize(comic, args.out))
    return 1 if any(p["status"] == "failed" for p in comic["pages"]) else 0


if __name__ == "__main__":
    sys.exit(main())
