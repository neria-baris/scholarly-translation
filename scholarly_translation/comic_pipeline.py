"""COMIC pipeline and CLI (audit/contracts/comic_translation.md).

Per page: local detection -> recognition call -> reconcile -> capacities -> translation
call -> fit -> at most one shorten call -> re-fit -> render. Every model call goes through
``chapter_pipeline._controlled`` (journaled, budgeted, replayed on rerun) with the
state in ``<out>/.state/``. Outputs: ``pages/NNN.png``, ``comic.cbz``, ``comic.pdf``,
``comic.json``, ``review.html`` and the untouched ``originals/NNN.png``.

    python -m scholarly_translation.comic_pipeline INPUT --out DIR --source-language en|es|fr|ja
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

from . import chapter_pipeline, comic_model, target_languages
from . import comic_records as records
from .job_blocks import AUTO_ACCEPT_BELOW_USD, AUTO_ACCEPT_MAX_STREAK, AUTO_RETRY_DELAYS
from .model_adapter import OpenAIConfigurationError, TextGenerationResult, build_translation_adapter
from .model_config import ModelConfigError, ModelConfiguration, load_model_configuration
from .runtime_controls import ControlStore, RuntimeControlsError, validate_store_path
from .translation import TranslationBudgetError
from .work_journal import WorkJournal

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
ROLE = "translator"
RECOGNITION_STAGE, TRANSLATION_STAGE, SHORTEN_STAGE = "comic-recognition", "comic-translation", "comic-shorten"
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
    from . import comic_detect, comic_typeset
    return SimpleNamespace(
        DETECT_VERSION=comic_detect.DETECT_VERSION, TYPESET_VERSION=comic_typeset.TYPESET_VERSION,
        detect_candidates=comic_detect.detect_candidates, snap_region=comic_detect.snap_region,
        font_for=comic_typeset.font_for, min_font_px=comic_typeset.min_font_px,
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
            from .key_store import default_key_store
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
    def __init__(self, job_id, configuration, store, journal, budget_usd, adapter_factory, sleep):
        self.job_id, self.configuration, self.store, self.journal = job_id, configuration, store, journal
        self.budget_usd, self.adapter_factory, self.sleep = budget_usd, adapter_factory, sleep
        selection, _ = configuration.resolve(ROLE)
        self.selection = selection
        self.model_cap = selection.capabilities.max_output_tokens or DEFAULT_OUTPUT_TOKENS
        self.shared_cap = max(s.capabilities.max_output_tokens or 4096 for s in configuration.models.values())
        self.stopped = None
        self.replays = 0

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

    def call(self, stage, prompt, validator, dependencies, wanted_cap):
        """One controlled call with the automatic retry rule: a failed, truncated or invalid answer
        is resent (a new attempt number gives a new identity) while this failure row has cost less
        than AUTO_ACCEPT_BELOW_USD and is shorter than AUTO_ACCEPT_MAX_STREAK; otherwise it raises."""
        cap = max(256, min(wanted_cap, self.model_cap, self.shared_cap))
        base, failures, attempt, skipped = self.spent(), 0, 0, 0
        while True:
            deps = dict(dependencies, attempt=attempt) if attempt else dict(dependencies)
            try:
                parsed, replay = chapter_pipeline._controlled(
                    self.job_id, ROLE, stage, prompt, self.configuration, cap, self.store, self.journal,
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
                delay = 0 if invalid else AUTO_RETRY_DELAYS[min(failures, len(AUTO_RETRY_DELAYS)) - 1]
                if delay:
                    self.sleep(delay)
                attempt += 1


def _cap(base, count, each):
    return base + count * each


# ---------------------------------------------------------------- page processing

def apply_kinds(regions):
    """Lettering on an object (kind sign) is set on a backing patch, never as a balloon: the
    art around it must not be erased. Balloons keep the measured shape."""
    for region in regions:
        if region["kind"] == "sign":
            region["plain_background"], region["interior"] = False, None


def separate_regions(regions, gap=4):
    """Keep each region's interior off the other regions' lettering, so touching balloons never
    share space: a row level with another region's lettering is cut short of it when that
    lettering lies beside this one, and dropped (outside this region's own lettering rows) when
    it lies above or below."""
    for region in regions:
        interior = region["interior"]
        if not interior:
            continue
        own, rows = region["bbox"], []
        for y, x0, x1 in interior["rows"]:
            keep = True
            for other in regions:
                box = other["bbox"]
                if other is region or not box[1] - gap <= y < box[3] + gap:
                    continue
                if x1 <= box[0] - gap or x0 >= box[2] + gap:
                    continue
                if box[2] <= own[0]:
                    x0 = max(x0, box[2] + gap)
                elif box[0] >= own[2]:
                    x1 = min(x1, box[0] - gap)
                elif (box[0] + box[2]) / 2 < (own[0] + own[2]) / 2 and box[2] + gap < x1:
                    x0 = max(x0, box[2] + gap)      # overlapping lettering (L-shaped): yield its side
                elif (box[0] + box[2]) / 2 >= (own[0] + own[2]) / 2 and box[0] - gap > x0:
                    x1 = min(x1, box[0] - gap)
                else:
                    keep = False
            if keep and x1 > x0:
                rows.append([y, x0, x1])
        region["interior"] = {"step": interior["step"], "rows": rows} if rows else None


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
    region["layout"] = layout
    region["warnings"] = [w for w in region["warnings"] if w != "overflow"]
    if layout.get("overflow"):
        region["translation"]["status"] = "overflow"
        region["warnings"].append("overflow")
    else:
        region["translation"]["status"] = "ok"


def _render(stages, image, regions, mirror):
    """Output page. Mirrored: the page is flipped, sound effects left in the art are put back
    unflipped (readable) at their mirrored place, and the mirrored regions are rendered."""
    placed = [r for r in regions if r["layout"] is not None]
    if not mirror:
        return stages.render_page(image, placed)
    width, height = image.size
    base = ImageOps.mirror(image)
    for region in placed:
        if region["layout"]["style"] == "subtitle":
            x0, y0, x1, y1 = region["bbox"]
            box = (max(0, x0 - 2), max(0, y0 - 2), min(width, x1 + 2), min(height, y1 + 2))
            base.paste(image.crop(box), (width - box[2], box[1]))
    return stages.render_page(base, [records.mirror_region(r, width) for r in placed])


def process_page(ctx, stages, number, name, image, raw, comic, source_language, target_code, notebook, summaries,
                 mirror=False, dialogue=None):
    """Run one page; returns ``(page, output image)``. Model/validation failures mark the page
    ``failed`` (original kept, unmirrored, as its output). Recognition and translation always
    see the original page; ``mirror`` only changes the rendered output."""
    pack = target_languages.load(target_code)
    page = records.new_page(number, name, raw, image.width, image.height)
    page["versions"] = {"detect": stages.DETECT_VERSION, "typeset": stages.TYPESET_VERSION,
                        "recognition": comic_model.RECOGNITION_VERSION,
                        "translation": comic_model.TRANSLATION_VERSION, "shorten": comic_model.SHORTEN_VERSION}
    base_deps = {"page": number, "image": page["image_sha256"], "detect": stages.DETECT_VERSION,
                 "source": source_language, "target": target_code}
    if ctx.stopped:
        page["status"] = "failed"
        page["warnings"].append("error: skipped, %s" % ctx.stopped)
        return page, image
    try:
        candidates = []
        for i, candidate in enumerate(stages.detect_candidates(image)):
            try:
                records.validate_candidate(candidate, "candidate", image.width, image.height)
                candidates.append(candidate)
            except records.ComicRecordError:
                page["warnings"].append("invalid_candidate:%d" % (i + 1))
        # recognition
        prompt = comic_model.recognition_prompt(image, candidates, source_language, notebook)
        parsed = ctx.call(
            RECOGNITION_STAGE, prompt, lambda result: comic_model.parse_recognition(result.text, len(candidates)),
            dict(base_deps, stage=comic_model.RECOGNITION_VERSION, marks=len(candidates)),
            _cap(8192, len(candidates), 400))
        page["regions"] = comic_model.reconcile(page, image, candidates, parsed, stages.snap_region)
        apply_kinds(page["regions"])
        separate_regions(page["regions"])
        page["summary"] = parsed["summary"]
        page["panels"] = parsed.get("panels", [])
        page["status"] = "recognised"
        update = records.new_notebook()
        update["characters"] = [{"name": c["name"], "target_name": "", "gender": c["gender"],
                                 "note": c["appearance"]} for c in parsed["characters"]]
        merged, warnings = comic_model.merge_notebook(notebook, update)
        notebook.clear()
        notebook.update(merged)
        page["warnings"].extend(w for w in warnings if w not in page["warnings"])
        if not page["regions"]:
            page["warnings"].append("no_text")
            page["status"] = "rendered"
            return page, image
        # translation
        font = stages.font_for(target_code)
        capacities = {r["region_id"]: max(1, int(stages.capacity(r, font, pack.rtl, image.height)))
                      for r in page["regions"]}
        ids = [r["region_id"] for r in page["regions"]]
        kinds = {r["region_id"]: r["kind"] for r in page["regions"]}
        sources = {r["region_id"]: r["source_text"] for r in page["regions"]}
        prompt = comic_model.translation_prompt(image, page, notebook, summaries, source_language, target_code,
                                                capacities, dialogue)
        answer = ctx.call(
            TRANSLATION_STAGE, prompt,
            lambda result: comic_model.parse_translation(result.text, ids, target_code, kinds, sources),
            dict(base_deps, stage=comic_model.TRANSLATION_VERSION, typeset=stages.TYPESET_VERSION,
                 regions=ids), _cap(6144, len(ids), 400))
        for item, region in zip(answer["translations"], page["regions"]):
            region["translation"] = {"text": item["text"], "status": "ok", "note": item["note"]}
        merged, warnings = comic_model.merge_notebook(notebook, answer["notebook"])
        notebook.clear()
        notebook.update(merged)
        page["warnings"].extend(w for w in warnings if w not in page["warnings"])
        page["summary"] = answer["summary"] or page["summary"]
        page["status"] = "translated"
        # typeset, at most one shorten call, re-fit
        for region in page["regions"]:
            _fit_region(stages, region, font, pack.rtl, image.size, mirror)
        over = [r for r in page["regions"] if r["translation"]["status"] == "overflow"]
        if over:
            items = [{"id": r["region_id"], "text": r["translation"]["text"], "max_chars": capacities[r["region_id"]]}
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
        rendered = _render(stages, image, page["regions"], mirror)
        page["mirrored"] = mirror
        page["status"] = "rendered"
        summaries.append(page["summary"])
        if dialogue is not None:   # the next page's translator sees this page's dialogue
            dialogue[:] = [{"speaker": r["speaker"], "source": r["source_text"], "target": r["translation"]["text"]}
                           for r in page["regions"] if r["translation"]]
        return page, rendered
    except _FATAL:
        raise
    except Exception as exc:
        page["status"] = "failed"
        page["warnings"].append("error: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return page, image


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
            parts.append("<tr><td>%d</td>%s%s%s%s%s</tr>" % (
                region["order"], _cell(region["kind"]), _cell(region["speaker"]), _cell(region["source_text"]),
                _cell(translation.get("text"), rtl), _cell(", ".join(region["warnings"]))))
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
              mirror="auto"):
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
        if not model_config:
            raise ComicPipelineError("--model configured needs --model-config PATH")
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
            ctx = _Context(comic_id, configuration, store, journal, budget_usd, adapter_factory, sleep)
            summaries, dialogue = [], []
            for done, (number, (name, load)) in enumerate(todo, 1):
                try:
                    image, raw = load()
                except ComicPipelineError as exc:
                    page = records.new_page(number, name, b"unreadable", 1, 1)
                    page["status"] = "failed"
                    page["warnings"].append("error: %s" % exc)
                    comic["pages"].append(page)
                    names.append(None)
                    images.append(None)
                    continue
                page, rendered = process_page(ctx, stages, number, name, image, raw, comic, source_language,
                                              target_code, notebook, summaries, mirror, dialogue)
                file_name = "%03d.png" % number
                image.save(out / "originals" / file_name)
                rendered.save(out / "pages" / file_name)
                comic["pages"].append(page)
                names.append(file_name)
                images.append(rendered)
                if progress:
                    progress(done, len(todo), page["page_id"])
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m scholarly_translation.comic_pipeline",
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
    parser.add_argument("--mirror", choices=("auto", "yes", "no"), default="auto",
                        help="mirror pages so the panels read right to left (auto: LTR comic into an RTL language)")
    args = parser.parse_args(argv)
    try:
        comic = run_comic(args.input, args.out, args.source_language, args.target, args.model, args.model_config,
                          args.budget_usd, args.pages, args.notebook, mirror=args.mirror,
                          progress=lambda done, total, page_id: _safe_print("%s done (%d/%d)" % (page_id, done, total)))
    except (ComicPipelineError, ModelConfigError, OpenAIConfigurationError, RuntimeControlsError) as exc:
        _safe_print("error: %s" % exc)
        return 2
    _safe_print(summarize(comic, args.out))
    return 1 if any(p["status"] == "failed" for p in comic["pages"]) else 0


if __name__ == "__main__":
    sys.exit(main())
