"""Automated whole-document drafts, driven by the canonical translation
backend (Session F/G). No source or scholarly approval is inferred beyond
the single, explicitly-logged auto-accept decision described below.

PDF jobs flow: pdf_extract.extract_pdf -> (auto-accept the sole digital
candidate per page, since this simple flow offers no OCR/alternative to
choose between) -> segmentation.build_structure -> export_pdf.export_pdf.
EPUB jobs flow the same way through epub_extract.extract_epub ->
segmentation.build_structure (digital-text origin) ->
export_epub.export_epub_from_document_structure, reusing the identical
canonical schema-2 structure (Session G: the EPUB digital-text schema
session already made segmentation/translation/review_qa/document_state
origin-agnostic; this module only had to stop refusing the upload and
plug in the matching extractor/exporter).

Per chapter: translate its units (using profile/style, persistent
document state, current chapter context and local translation state) ->
(quality-mode-gated) per-unit semantic review -> chapter-level QA ->
proposed persistent-state updates -> validated/committed document state
used by the *next* chapter (Session G: wires Session C's chapter QA into
Session D's document_state.py). Every live translation/review/QA call
for a configured (non-Auto) job shares one persistent per-document
budget and cache (runtime_controls.ControlStore), not just translation.
"""
from __future__ import annotations

import json
import math
import os
import re
import secrets
import shutil
import threading
from dataclasses import replace as _dc_replace
from datetime import datetime, timezone
from pathlib import Path

from . import chapter_pipeline, job_blocks, review_salvage, scanned_ocr, target_languages
from . import context_strategy, document_state as document_state_module
from . import epub_extract, pdf_extract, segmentation
from .work_journal import WorkJournal
from .source_reading import text_hash
from .export_common import ExportError
from .formal_checks import run_formal_checks
from .export_epub import export_epub_from_document_structure as _export_epub
from .export_pdf import export_pdf as _export_pdf
from .glossary import new_store as _new_glossary_store
from .model_adapter import OpenAIConfigurationError, TextGenerationResult, build_translation_adapter, OPENAI_MAX_OUTPUT_TOKENS
from .model_config import ModelConfigError, ModelConfiguration
from .review_qa import (
    build_chapter_qa_request,
    build_chapter_qa_request_for_role,
    build_unit_review_request,
    build_unit_review_request_for_role,
    run_chapter_qa,
    run_unit_review,
)
from .runtime_controls import (
    ControlStore, PersistentBudget, RuntimeCache, RuntimeControlsError, validate_store_path,
)
from .translation import (
    TranslationBudget,
    TranslationBudgetError,
    TranslationRequestError,
    build_translation_request,
    build_translation_request_for_role,
    run_translation,
)
from .translation_profiles import SUPPORTED_PROFILE_IDS

# Chapter-level QA prompts legitimately exceed translation.MAX_PROMPT_BYTES
# (a whole assembled chapter, not one ~2000-char unit); this is a separate,
# explicit bound for the review/QA control path only -- comfortably above
# MAX_SOURCE_CHARS (one whole document) at 2 bytes/char for Hebrew, never
# unbounded.
REVIEW_MAX_PROMPT_BYTES = 700_000

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_SOURCE_CHARS = 3_000_000
MAX_PAGES = 2_000
# No code-level budget ceiling (user decision): the user's own per-document limit
# is the cap. A positive finite budget is mandatory for paid (configured) runs.
MAX_BUDGET_USD = None
BUDGET_REQUIRED_MESSAGE = "יש להגדיר תקציב מרבי למסמך (מספר חיובי) לפני תרגום בתשלום."
MIN_CHAPTER_CHARS = 1500
LANGUAGES = {"auto", "en", "fr", "ja"}
QUALITY_MODES = {"fast", "checked", "thorough"}
MODEL_CHOICES = {"auto", "configured"}

# Fast = no review at all; Checked = risk-based unit review + chapter QA;
# Thorough = unit review on every unit + chapter QA. Exactly the mapping
# the Session F contract specifies onto review_qa.py's own policies.
_QUALITY_POLICIES = {
    "fast": {"unit_review": "off", "chapter_qa": "off"},
    "checked": {"unit_review": "risk_based", "chapter_qa": "on"},
    "thorough": {"unit_review": "all", "chapter_qa": "on"},
}

# Historical note (Session F / pre-Session-G): EPUB upload used to be
# refused here because the canonical document_structure schema had no
# legitimate non-PDF source-evidence origin. The EPUB digital-text schema
# session added exactly that ("digital-text" origin, epub_extract.py) and
# Session G reconciled export_epub.py with it (see
# export_epub.export_epub_from_document_structure); EPUB is fully wired
# below. Kept only as an exported symbol for tests/imports referencing it.
EPUB_BLOCKED_MESSAGE = None


class DocumentDraftError(ValueError):
    pass


def _mock_review_generate(prompt_text: str, model: str) -> TextGenerationResult:
    """Conspicuous, non-network stand-in generate() for Auto/mock-mode
    review calls (review_qa.py's own mock/translation adapter is scoped to
    the translation workflow only, not review/QA)."""
    return TextGenerationResult(
        status="mock_placeholder", text="VERDICT: PASS\nISSUES: none",
        token_usage="not_metered", observed_model=model, duration_seconds=0.0,
        observed_provider="mock",
    )


def _mock_chapter_qa_generate(prompt_text: str, model: str) -> TextGenerationResult:
    return TextGenerationResult(
        status="mock_placeholder",
        text="VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)\nSTATE_UPDATES: none",
        token_usage="not_metered", observed_model=model, duration_seconds=0.0,
        observed_provider="mock",
    )


def _state_candidates_from_chapter_qa(proposed_updates, *, document_id, chapter_node_id, unit_ids, source_chapter):
    """The smallest adapter between Session C's chapter QA output and
    Session D's document_state.py (Session G's explicit integration job,
    per the 2026-10-05 addendum): review_qa.run_chapter_qa's
    ``proposed_state_updates`` are already category/certainty-validated
    plain dicts with a source-grounded ``span``; this turns each into a
    document_state.propose_item() candidate with full source provenance
    resolved to an exact character span. A span review_qa already checked
    is a literal substring of ``source_chapter`` is never missing here,
    but this still never raises on a malformed item -- it is skipped
    (fail-closed) rather than guessed, since document_state.py must never
    receive an ungrounded or otherwise invalid candidate."""
    candidates = []
    for update in proposed_updates:
        span = update.get("span") or ""
        start = source_chapter.find(span) if span else -1
        if start < 0:
            continue
        source = {
            "chapter_node_id": chapter_node_id, "unit_ids": list(unit_ids),
            "document_id": document_id, "source_char_start": start, "source_char_end": start + len(span),
        }
        try:
            candidates.append(document_state_module.propose_item(
                category=update["category"], label=update["label"], value=update["value"],
                certainty=update["certainty"], source=source,
                reason=f"chapter_qa:{chapter_node_id}",
            ))
        except (document_state_module.DocumentStateError, KeyError):
            continue
    return candidates


_LANGUAGE_WORD_RE = re.compile(r"\b(?:les|des|une|dans|pour|avec|est|qui)\b")
_CJK_RE = re.compile(r"[぀-ヿ一-鿿]")


def _detect_language(document) -> str:
    sample = "\n".join(p.source_text or "" for p in document.pages)[:10000]
    if _CJK_RE.search(sample):
        return "ja"
    if len(_LANGUAGE_WORD_RE.findall(sample.lower())) >= 3:
        return "fr"
    return "en"


def _auto_accept_decisions(document, unit_policy=None, ocr_bundle=None):
    """Resolve each page's sole usable (digital) candidate automatically.

    This simple flow offers no OCR and no alternative source candidate to
    choose between, so there is no real choice for a human to make; the
    uploading user, by starting translation, is the accepting human. A page
    with no usable digital text (e.g. scanned, no extractable text) is left
    unresolved -- same unsupported spirit as before, surfaced later as a
    clear error if it leaves the whole document with no translatable text.
    """
    draft_structure = segmentation.build_structure(document, ocr_bundle=ocr_bundle, unit_policy=unit_policy)
    decisions = {}
    for reading in draft_structure["readings"]:
        if reading["status"] == "resolved":
            continue
        usable = next((c for c in reading["alternatives"] if c["usable"]), None)
        if usable is None:
            continue
        reason = ("single available digital-extraction candidate; automatically accepted by "
                  "the simple upload-and-translate flow (no OCR offered, no alternative to choose between)")
        if usable["origin"] == "ocr":
            reason = ("scanned page with no digital text: the OCR reading (local Tesseract%s) is the only "
                      "usable candidate; accepted by the simple flow and flagged for OCR-aware review"
                      % (", model-reviewed" if usable["provenance"]["stage"] != "local-ocr@1" else ""))
        decisions[reading["page_id"]] = {
            "origin": usable["origin"], "candidate_hash": usable["candidate_hash"],
            "actor": "simple-upload-flow (initiating user)", "actor_kind": "human", "reason": reason,
        }
    if not decisions:
        return draft_structure
    return segmentation.build_structure(document, ocr_bundle=ocr_bundle, decisions=decisions,
                                        previous=draft_structure, unit_policy=unit_policy)


def source_kind_for(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return "epub"
    if suffix == ".pdf":
        return "pdf"
    raise DocumentDraftError("ניתן לתרגם קובצי PDF או EPUB בלבד כרגע.")


_EPUB_ERROR_MESSAGES = {
    "empty_chapters": "קובץ ה־EPUB פגום: קובצי הפרקים בתוכו ריקים (נראה שהומר באופן חלקי). השתמשו בקובץ ה־EPUB המקורי.",
    "empty_spine": "קובץ ה־EPUB פגום: רשימת הפרקים (spine) ריקה ולא נמצאו בו קובצי פרקים. השתמשו בקובץ ה־EPUB המקורי.",
    "drm": "קובץ ה־EPUB מוגן בהגנת DRM ולא ניתן לתרגום. השתמשו בגרסה ללא הגנה.",
    "bad_spine_item": "קובץ ה־EPUB פגום: רשימת הפרקים מפנה לקובץ חסר או שאינו XHTML. השתמשו בקובץ ה־EPUB המקורי.",
    "no_text": "קובץ ה־EPUB אינו מכיל טקסט הניתן לתרגום.",
}


def chapter_groups(structure, units):
    """Pure partition of ``units`` (document order) into contiguous groups.

    Units with an enclosing chapter/part node are grouped by that node
    (historical behaviour). When no unit has one and the structure is of
    EPUB ("digital-text") origin, each spine document (``page_id``) is a
    boundary and documents shorter than ``MIN_CHAPTER_CHARS`` merge forward
    into the next group (a small final group merges backward). Other
    chapter-less structures (PDF) remain a single run."""
    keys = []
    for unit in units:
        node = context_strategy.find_enclosing_chapter_node(structure, unit)
        keys.append(node["node_id"] if node else None)
    if units and all(key is None for key in keys) and _is_epub_structure(structure):
        return _spine_groups(units)
    groups, current_key, current = [], object(), []
    for unit, key in zip(units, keys):
        if current and key != current_key:
            groups.append(current)
            current = []
        current_key, current = key, current + [unit]
    if current:
        groups.append(current)
    return groups


def _is_epub_structure(structure):
    for reading in structure.get("readings", []):
        selected = reading.get("selected") or {}
        origins = {selected.get("origin")} | {a.get("origin") for a in reading.get("alternatives", [])}
        if "digital-text" in origins:
            return True
    return False


def _spine_groups(units):
    runs = []
    for unit in units:
        if runs and runs[-1][0] == unit["page_id"]:
            runs[-1][1].append(unit)
        else:
            runs.append((unit["page_id"], [unit]))
    groups, pending = [], []
    for _, run in runs:
        pending = pending + run
        if sum(len(u.get("text") or u.get("source_text") or "") for u in pending) >= MIN_CHAPTER_CHARS:
            groups.append(pending)
            pending = []
    if pending:
        if groups:
            groups[-1] = groups[-1] + pending
        else:
            groups.append(pending)
    return groups


def _planned_structure(path, language, configuration, document=None, ocr_bundle=None):
    """Structure for a planned run: default units unless an actual unit is too
    large for the configured translator's output; only then re-segment with
    the narrower unit policy (default structures stay byte-identical)."""
    document = document if document is not None else extract_document(path, language)
    structure = structure_from_document(document, ocr_bundle=ocr_bundle)
    if chapter_pipeline.units_fit_translator(structure, configuration):
        return structure
    return structure_from_document(document, unit_policy=chapter_pipeline.unit_policy_for(configuration),
                                   ocr_bundle=ocr_bundle)


def extract_document(path, language="auto"):
    """Validated schema-3 extraction with the source language resolved (no OCR yet)."""
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
        raise DocumentDraftError("בחרו קובץ תקין עד 25 MB.")
    kind = source_kind_for(path)
    if language not in LANGUAGES:
        raise DocumentDraftError("שפת מקור לא נתמכת.")
    resolved_language = language if language != "auto" else "en"
    try:
        if kind == "epub":
            document = epub_extract.extract_epub(path, resolved_language)
        else:
            document = pdf_extract.extract_pdf(path, resolved_language)
    except epub_extract.EpubExtractionError as exc:
        hebrew = _EPUB_ERROR_MESSAGES.get(getattr(exc, "code", None))
        if hebrew:
            raise DocumentDraftError(hebrew) from None
        raise DocumentDraftError(f"לא ניתן לקרוא את הקובץ: {exc}") from None
    except pdf_extract.ExtractionError as exc:
        raise DocumentDraftError(f"לא ניתן לקרוא את הקובץ: {exc}") from None
    if len(document.pages) > MAX_PAGES:
        raise DocumentDraftError(f"המסמך מוגבל כרגע ל־{MAX_PAGES:,} עמודים/פרקים.")
    total_chars = sum(len(p.source_text or "") for p in document.pages)
    if total_chars > MAX_SOURCE_CHARS:
        raise DocumentDraftError(f"המסמך ארוך מדי כרגע. המגבלה היא {MAX_SOURCE_CHARS:,} תווי מקור.")
    if language == "auto":
        document = _dc_replace(document, language=_detect_language(document))
    return document


def structure_from_document(document, unit_policy=None, ocr_bundle=None):
    """Canonical structure from an extracted document (and its OCR bundle, if any)."""
    kind = document.source_kind
    try:
        structure = _auto_accept_decisions(document, unit_policy=unit_policy, ocr_bundle=ocr_bundle)
    except segmentation.StructureError as exc:
        raise DocumentDraftError(f"מבנה המסמך אינו תקין: {exc}") from None
    if not structure["units"]:
        if kind == "epub":
            raise DocumentDraftError("קובץ ה־EPUB אינו מכיל טקסט הניתן לתרגום.")
        raise DocumentDraftError("ה־PDF מכיל עמודים סרוקים ללא טקסט. נדרש OCR לפני התרגום.")
    return structure


def extract_structure(path, language="auto", unit_policy=None, ocr_bundle=None):
    """Extract a PDF or EPUB into the canonical schema-2 document_structure,
    with every resolvable page's sole candidate auto-accepted. Raises
    DocumentDraftError for anything invalid, oversized, or with no
    extractable text at all (same spirit as the historical OCR-required
    message). EPUB uses the same "digital-text" source-evidence origin and
    the same segmentation/translation pipeline as PDF -- no second,
    EPUB-specific interpretation of structure."""
    return structure_from_document(extract_document(path, language), unit_policy, ocr_bundle)


def validate_settings(settings):
    profile = settings.get("profile", "scholarly")
    quality = settings.get("quality", "fast")
    language = settings.get("language", "auto")
    budget = settings.get("budget_usd")
    model_choice = settings.get("model", "auto")
    model_config_data = settings.get("model_config")
    # Opt-in (default False): preserves every existing saved/library job's
    # behavior exactly (the legacy one-unit-at-a-time path below). A future
        # UI sets this True for a real translation run; it is the
    # new planned/batched/journaled chapter_pipeline.py flow.
    automation = settings.get("automation", False)
    ocr_review = settings.get("ocr_review", "vision")
    if ocr_review not in ("vision", "off"):
        raise DocumentDraftError("הגדרת בדיקת ה־OCR אינה תקינה.")
    font_id = settings.get('font_id')
    if font_id is not None:
        from .export_common import list_pdf_fonts
        if not isinstance(font_id, str) or font_id not in {f['id'] for f in list_pdf_fonts() if f['available']}:
            raise DocumentDraftError('בחרו פונט PDF זמין מהרשימה.')
    if type(automation) is not bool:
        raise DocumentDraftError("הגדרת האוטומציה חייבת להיות בוליאנית.")
    if profile not in SUPPORTED_PROFILE_IDS:
        raise DocumentDraftError("בחרו פרופיל תרגום נתמך (אקדמי/ספרותי).")
    if quality not in QUALITY_MODES:
        raise DocumentDraftError("בחרו רמת בדיקה נתמכת.")
    if language not in LANGUAGES:
        raise DocumentDraftError("הגדרות תרגום לא תקינות.")
    target = settings.get("target_language", target_languages.DEFAULT)
    if target not in target_languages.available():
        raise DocumentDraftError("בחרו שפת יעד נתמכת.")
    if target != target_languages.DEFAULT and not (model_choice == "configured" and automation):
        raise DocumentDraftError("תרגום לשפת יעד שאינה עברית זמין רק עם מודל מוגדר (API).")
    if language == target:
        raise DocumentDraftError("שפת המקור זהה לשפת היעד.")
    budget_valid = (type(budget) in (int, float) and not isinstance(budget, bool)
                    and math.isfinite(budget) and budget > 0)
    if model_choice == "configured":
        # Paid runs and previews: an explicit positive finite budget is mandatory.
        if not budget_valid:
            raise DocumentDraftError(BUDGET_REQUIRED_MESSAGE)
    elif budget is None:
        # Auto/mock mode makes no paid calls, so it needs no user budget; the
        # internal value is inert and never enforced against real spend.
        budget = 2.0
    elif not budget_valid:
        raise DocumentDraftError(BUDGET_REQUIRED_MESSAGE)
    if model_choice not in MODEL_CHOICES:
        raise DocumentDraftError("בחרו מודל נתמך.")
    if model_choice == "configured":
        if not isinstance(model_config_data, dict):
            raise DocumentDraftError("יש לצרף קובץ תצורת מודל כדי להשתמש במודל מוגדר.")
        try:
            configuration = ModelConfiguration.from_dict(model_config_data)
        except ModelConfigError as exc:
            raise DocumentDraftError(f"קובץ תצורת המודל אינו תקין: {exc}") from None
        if "translator" not in configuration.models:
            raise DocumentDraftError("קובץ תצורת המודל חייב להגדיר תפקיד translator.")
    return {
        "profile": profile, "quality": quality, "language": language,
        "budget_usd": float(budget), "model": model_choice, "model_config": model_config_data,
        "automation": automation,
        'font_id': font_id, "ocr_review": ocr_review,
        # Hebrew jobs keep their historical settings shape (no key = Hebrew).
        **({"target_language": target} if target != target_languages.DEFAULT else {}),
    }


def _check_source_differs(document, settings):
    """A detected source language equal to the target language cannot be translated."""
    if getattr(document, "language", None) == target_languages.settings_code(settings):
        raise DocumentDraftError("שפת המקור זהה לשפת היעד.")


def _write_json(path, value):
    # Flushed to disk before the replace: an unflushed replace survives a power loss
    # as a zero-filled job.json, and the job then disappears from the library.
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _build_translations_mapping(units):
    return {
        u["unit_id"]: {"text": u["target_text"] or u["source_text"], "approved": u["approved"], "status": u["status"]}
        for u in units
    }


def _partial_translations_mapping(job):
    """Translated units plus every not-yet-translated unit in its source text."""
    translations = _build_translations_mapping(job["units"])
    for unit in job["structure"]["units"]:
        translations.setdefault(unit["unit_id"], {"text": unit["text"], "approved": False, "status": "untranslated"})
    return translations


def render_download(job, kind, source_path=None, font_id=None, partial=False):
    """Rebuild the translated document in the job's target language (see ``_render_download``)."""
    with target_languages.use(target_languages.settings_code(job.get("settings"))):
        return _render_download(job, kind, source_path, font_id, partial)


def _render_download(job, kind, source_path=None, font_id=None, partial=False):
    """Rebuild the translated document from the job's current (possibly
    human-edited) unit texts; never a frozen completion-time snapshot.

    PDF is a pure re-render from ``structure`` text (no original bytes
    needed). EPUB rebuilds the original archive byte-for-byte except for
    translated text, so it needs the original upload's bytes; callers
    must pass ``source_path`` (the job folder's persisted ``source.epub``)
    for an EPUB job.

    ``kind="html"`` is accepted for any completed job (PDF or EPUB source)
    and renders a self-contained HTML page from the same structure and
    translations mapping; an explicit ``font_id`` (else the job's stored
    PDF font) is embedded, ``None`` uses a system font stack.
    """
    if kind != "html" and kind != job.get("source_kind", "pdf"):
        raise DocumentDraftError("סוג הורדה לא תואם את קובץ המקור.")
    if partial:
        if job["status"] == "completed" or not job.get("units") or not job.get("structure"):
            raise DocumentDraftError("אין תרגום חלקי להורדה.")
        translations = (_build_translations_mapping(job["units"]) if kind == "epub"
                        else _partial_translations_mapping(job))
    elif job["status"] not in ("completed",) or not job.get("units"):
        raise DocumentDraftError("עדיין אין תוצאה להורדה.")
    else:
        translations = _build_translations_mapping(job["units"])
    if kind == "html":
        from .export_html import export_html as _export_html
        try:
            return _export_html(job["structure"], translations, title=job["filename"],
                                font_id=font_id if font_id is not None else job.get('settings', {}).get('font_id'))
        except ExportError as exc:
            raise DocumentDraftError(f"בניית ה-HTML נכשלה: {exc}") from None
    if kind == "epub":
        if source_path is None:
            raise DocumentDraftError("קובץ ה־EPUB המקורי אינו זמין להורדה.")
        try:
            result = _export_epub(source_path, job["structure"], translations)
        except ExportError as exc:
            raise DocumentDraftError(f"בנייית ה-EPUB נכשלה: {exc}") from None
        return result.content
    try:
        result = _export_pdf(job["structure"], translations, title=job["filename"],
                             font_id=font_id if font_id is not None else job['settings'].get('font_id'))
    except ExportError as exc:
        raise DocumentDraftError(f"בנייית ה-PDF נכשלה: {exc}") from None
    return result.content


class DocumentJobs:
    """One active document worker; durable local results, no background retries."""

    def __init__(self, root, adapter_factory=None):
        self.root = Path(root) / "documents"
        self.adapter_factory = adapter_factory
        self._job_adapter_factories = {}
        self.lock = threading.RLock()
        self.active = None

    def _folder(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise DocumentDraftError("מסמך לא נמצא.")
        return self.root / job_id

    def get(self, job_id):
        path = self._folder(job_id) / "job.json"
        with self.lock:
            if not path.is_file():
                raise DocumentDraftError("מסמך לא נמצא.")
            job = json.loads(path.read_text(encoding="utf-8"))
            active = self.active == job_id
        if job["status"] in ("queued", "reading", "translating", "reviewing", "rebuilding") and not active:
            job["status"], job["error"] = "interrupted", "ההרצה הופסקה. התוצאות שכבר נשמרו זמינות; לא בוצע ניסיון אוטומטי נוסף."
        controls = self._folder(job_id) / 'controls.sqlite3'
        if controls.is_file():
            try:
                with ControlStore(controls, create=False) as store:
                    job['budget_status'] = store.status(job_id)
                    job['remaining_budget_usd'] = store.remaining_list_usd(job_id)
                    job['estimated_cost_usd'] = job['budget_status']['list_estimated_spent_usd']
            except RuntimeControlsError:
                pass  # Worker may not have created its first task yet.
        if job['status'] == 'completed' and job.get('progress'):
            job['progress']['percentage'] = 100
        return job

    def _persist(self, job):
        with self.lock:
            _write_json(self._folder(job["job_id"]) / "job.json", job)

    def start(self, path, settings, paid_confirm=False, adapter_factory=None):
        settings = validate_settings(settings)
        if settings["model"] == "configured" and paid_confirm is not True:
            raise DocumentDraftError("נדרש אישור לשליחת המסמך לספק המודל המוגדר.")
        if settings["model"] == "configured" and self.adapter_factory is None and adapter_factory is None:
            configuration = ModelConfiguration.from_dict(settings["model_config"])
            roles = chapter_pipeline._resolve_required_roles(configuration, settings["quality"]) if settings["automation"] else {"translator": configuration.resolve("translator")}
            try:
                for _, definition in roles.values():
                    definition.require_credential(os.environ)
            except ModelConfigError as exc:
                raise DocumentDraftError(str(exc)) from None
        source_kind = source_kind_for(path)
        with self.lock:
            if self.active:
                raise DocumentDraftError("מסמך אחר מתורגם כרגע. המתינו לסיום.")
            job_id = secrets.token_hex(16)
            folder = self._folder(job_id)
            folder.mkdir(parents=True, exist_ok=False)
            source_path = folder / f"source.{source_kind}"
            if source_kind in ("pdf", "epub"):
                # PDF export is a pure re-render from structure text; EPUB
                # export rebuilds the original archive byte-for-byte except
                # for translated text, so the original upload must outlive
                # the transient upload path for later downloads/re-renders.
                shutil.copyfile(path, source_path)
            job = {
                "schema_version": 2, "stage": "document-draft@2", "job_id": job_id,
                "filename": Path(path).name, "source_kind": source_kind, "settings": settings,
                "status": "queued",
                "stage_label": None, "completed_units": 0, "total_units": 0, "chapter_progress": None,
                "units": [], "structure": None, "approved": False, "source_reviewed": False,
                "revision": 0, "created_at": datetime.now(timezone.utc).isoformat(),
                "error": None, "estimated_cost_usd": 0.0,
                "export_limitations": [], "export_page_count": 0, "review_notes": [],
                "chapter_qa_results": [], "document_state": None,
            }
            self._persist(job)
            self.active = job_id
            self._job_adapter_factories[job_id] = adapter_factory or self.adapter_factory
        threading.Thread(target=self._run, args=(job, source_path), daemon=True).start()
        return {"job_id": job_id}

    def source_path(self, job_id, source_kind):
        """The persisted original upload for a completed EPUB job's export,
        or None if this job has no persisted original (e.g. PDF, which
        never needs one)."""
        candidate = self._folder(job_id) / f"source.{source_kind}"
        return candidate if candidate.is_file() else None

    def _resolve_role(self, configuration, role):
        """Returns (provider, model, provider_definition, capabilities) for
        role, or None if that role is simply not configured (graceful
        skip, never an error for an optional review role)."""
        try:
            selection, definition = configuration.resolve(role)
        except ModelConfigError:
            return None
        return selection.provider, selection.model, definition, selection.capabilities

    def _translation_adapter(self, request):
        if self.adapter_factory is not None:
            return self.adapter_factory("translator", request)
        return None  # let run_translation build the real adapter from provider_definition

    def _shared_output_cap(self, configuration):
        """One worst-case output-token bound shared by every role's budget
        under this document's single ControlStore task (get_or_create_task
        fixes one output_cap per task_id): the max of every configured
        role's own capabilities, never a blind single global constant, so
        a role actually allowed to emit more than OPENAI_MAX_OUTPUT_TOKENS
        (model_config.py capabilities.max_output_tokens) is never
        silently undercounted."""
        caps = [sel.capabilities.max_output_tokens for sel in configuration.models.values()
                if sel.capabilities and sel.capabilities.max_output_tokens]
        return max(caps) if caps else OPENAI_MAX_OUTPUT_TOKENS

    def _store_cost(self, store, job_id):
        status = store.status(job_id)
        return status["held_usd"] + status["list_estimated_spent_usd"]

    def _resolve_review_controls(self, role, stage, provider, model, provider_definition, capabilities,
                                  store, output_cap, max_calls, hard_list_usd, job_id):
        """Build one persistent budget+cache pair for this role, shared by
        every call made under it, and return a ``make_generate(identity,
        unit_id)`` factory producing a plain ``generate(prompt_text,
        model)`` callable -- review_qa.py's own call signature -- that
        routes every call through them. Review/QA calls previously bypassed
        the document's budget/cache entirely; this is the fix."""
        if self.adapter_factory is not None:
            raw = self.adapter_factory(role, None).generate
        elif provider_definition is not None:
            raw = build_translation_adapter(
                provider, model, provider_definition=provider_definition,
                max_output_tokens=(capabilities.max_output_tokens if capabilities else None),
                reasoning=(capabilities.reasoning if capabilities else None),
            ).generate
        else:
            raw = _mock_review_generate if role == "semantic_reviewer" else _mock_chapter_qa_generate

        if store is None:
            return lambda identity, unit_id: raw

        budget = PersistentBudget(
            store, job_id, max_calls=max_calls, hard_list_usd=hard_list_usd, stage=stage,
            provider=provider, model=model, output_cap=output_cap, max_prompt_bytes=REVIEW_MAX_PROMPT_BYTES,
        )
        cache = RuntimeCache(store, stage=stage, provider=provider, model=model)
        provider_type = provider_definition.provider_type if provider_definition else provider

        def make_generate(identity, unit_id):
            def generate(prompt_text, model_arg):
                metadata = {"document_id": job_id, "unit_id": unit_id, "provider_type": provider_type}
                try:
                    result, _cache_hit, _notices = cache.execute(
                        identity, prompt_text, model_arg, raw, stage=stage, metadata=metadata, budget=budget,
                    )
                except TranslationBudgetError:
                    # The document's shared budget is exhausted: fail this
                    # one optional review/QA call cleanly rather than spend
                    # further or crash the whole (already-translated) job.
                    return TextGenerationResult(
                        status="failed", text=None, token_usage="not_metered", observed_model=model_arg,
                        duration_seconds=0.0, error="document_budget_exhausted", observed_provider=provider_type,
                    )
                return result
            return generate
        return make_generate

    def _chapter_groups(self, structure, units):
        """Partition ``units`` (already in document order) into contiguous
        per-chapter runs using the same enclosing chapter/part node
        context_strategy.py already resolves -- never a second
        independent chapter model. Units with no enclosing chapter/part
        (flat/short documents) form their own run(s), exactly like the
        historical post-hoc grouping by ``chapter_node_id`` did."""
        return chapter_groups(structure, units)

    def _target_settings(self, job_id):
        try:
            return self.get(job_id).get("settings")
        except Exception:
            return None

    def _run(self, job, path):
        with target_languages.use(target_languages.settings_code(job.get("settings"))):
            return self._run_body(job, path)

    def _run_body(self, job, path):
        store = None
        try:
            job["status"], job["stage_label"] = "reading", "קריאת המסמך"
            self._persist(job)
            document = extract_document(path, job["settings"]["language"])
            _check_source_differs(document, job["settings"])
            ocr_bundle = self._read_scanned_pages(job, path, document) if document.source_kind == "pdf" else None
            if job["settings"]["model"] == "configured" and job["settings"].get("automation"):
                structure = _planned_structure(path, job["settings"]["language"],
                                               ModelConfiguration.from_dict(job["settings"]["model_config"]),
                                               document=document, ocr_bundle=ocr_bundle)
            else:
                structure = structure_from_document(document, ocr_bundle=ocr_bundle)
            job["structure"] = structure
            page_number_by_id = {r["page_id"]: r["page_number"] for r in structure["readings"]}
            units = sorted(
                structure["units"],
                key=lambda u: (page_number_by_id[u["page_id"]], u["source_char_start"]),
            )
            job["total_units"] = len(units)
            self._persist(job)

            configuration = (
                ModelConfiguration.from_dict(job["settings"]["model_config"])
                if job["settings"]["model"] == "configured" else None
            )
            glossary = _new_glossary_store()
            policies = _QUALITY_POLICIES[job["settings"]["quality"]]

            job["status"], job["stage_label"] = "translating", "מתרגם"
            self._persist(job)

            if configuration is None:
                self._run_auto_mode(job, structure, glossary, units)
            else:
                store_path = validate_store_path(self._folder(job["job_id"]) / "controls.sqlite3")
                store = ControlStore(store_path, create=True)
                if job["settings"].get("automation", False):
                    self._run_automation_chapter_mode(job, structure, glossary, units, configuration, store)
                else:
                    self._run_configured_mode(job, structure, glossary, units, policies, configuration, store)

            job["status"], job["stage_label"] = "rebuilding", "בניית המסמך המתורגם"
            self._persist(job)
            translations = _build_translations_mapping(job["units"])
            if job["source_kind"] == "epub":
                result = _export_epub(self._folder(job["job_id"]) / "source.epub", structure, translations)
            else:
                result = _export_pdf(structure, translations, title=job["filename"], font_id=job['settings'].get('font_id'))
            job["export_limitations"] = result.limitations
            job["export_page_count"] = getattr(result, "page_count", 0)

            job["status"], job["stage_label"] = "completed", "הושלם"
        except DocumentDraftError as exc:
            job["status"], job["error"] = "failed", str(exc)
        except (TranslationRequestError, TranslationBudgetError) as exc:
            job["status"], job["error"] = "failed", f"התרגום נעצר: {exc}"
        except chapter_pipeline.PipelinePaused:
            job["status"], job["stage_label"] = "paused", "מושהה — התוצאות נשמרו"
        except chapter_pipeline.ChapterPipelineError as exc:
            job["status"], job["error"] = "failed", f"התרגום האוטומטי נעצר: {exc}"
        except OpenAIConfigurationError as exc:
            job["status"], job["error"] = "failed", f"תצורת הספק שגויה: {exc}"
        except RuntimeControlsError as exc:
            job["status"], job["error"] = "failed", f"בקרת התקציב/המטמון נכשלה: {exc}"
        except Exception:
            job["status"], job["error"] = "failed", "התרגום לא הושלם. בדקו חיבור, הרשאת המודל ומפתח API. התוצאה החלקית נשמרה."
        finally:
            if store is not None:
                store.close()
            try:
                self._persist(job)
            finally:
                with self.lock:
                    self.active = None
        self._auto_continue(job)

    def _read_scanned_pages(self, job, path, document):
        """OCR stage for scanned PDF pages (None when every page has digital text):
        local Tesseract, then -- for configured models with ocr_review "vision" --
        one journaled, budgeted vision-review call per page."""
        pages = scanned_ocr.scanned_pages(document)
        if not pages:
            return None
        folder = self._folder(job["job_id"])
        settings = job["settings"]

        def progress(label):
            def report(done, total):
                job["ocr_progress"] = {"phase": label, "done": done, "total": total}
                if done == total or done % 5 == 0:
                    self._persist(job)
            return report

        job["stage_label"] = "זיהוי טקסט (OCR) בעמודים סרוקים"
        self._persist(job)
        try:
            bundle = scanned_ocr.run_local_ocr(path, document, folder, progress("ocr"))
        except scanned_ocr.ScannedOcrError as exc:
            raise DocumentDraftError(str(exc)) from None
        if settings["model"] == "configured" and settings.get("ocr_review", "vision") == "vision":
            bundle = self._vision_review(job, bundle, document, progress("vision"))
        (folder / "ocr" / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        summary = scanned_ocr.ocr_summary(bundle)
        job["ocr_summary"] = summary
        for page_number in summary["disagreement_pages"]:
            exception = {"type": "ocr_vision_disagreement", "page": page_number}
            if exception not in job.setdefault("exceptions", []):
                job["exceptions"].append(exception)
        for page_number in summary["errors"]:
            exception = {"type": "ocr_page_failed", "page": page_number}
            if exception not in job.setdefault("exceptions", []):
                job["exceptions"].append(exception)
        job.pop("ocr_progress", None)
        self._persist(job)
        return bundle

    def _vision_review(self, job, bundle, document, progress):
        settings = job["settings"]
        configuration = ModelConfiguration.from_dict(settings["model_config"])
        selection, _ = configuration.resolve("translator")
        folder = self._folder(job["job_id"])
        # The task's call policy is fixed by its first call; units do not exist yet, so a
        # scanned job's call limit comes from its page count (the pipeline honours it).
        settings.setdefault("max_calls", len(document.pages) * 24 + 64)
        shared_cap = max(sel.capabilities.max_output_tokens or 4096 for sel in configuration.models.values())
        job["stage_label"] = "בדיקת ה־OCR בעזרת המודל"
        self._persist(job)
        store = ControlStore(validate_store_path(folder / "controls.sqlite3"), create=True)
        try:
            with WorkJournal(folder / "journal.sqlite3", create=True) as journal:
                def run_call(entry, prompt):
                    cap = scanned_ocr.vision_output_cap(entry, selection.capabilities.max_output_tokens)
                    parsed, replay = chapter_pipeline._controlled(
                        job["job_id"], "translator", scanned_ocr.VISION_STAGE, prompt, configuration, cap,
                        store, journal, settings["budget_usd"], settings["max_calls"], shared_cap,
                        lambda result: scanned_ocr.parse_vision_text(result.text),
                        {"page": entry["page_number"], "image": entry["image_hash"],
                         "ocr": text_hash(entry["transcription"])},
                        self._job_adapter_factories.get(job["job_id"], self.adapter_factory))
                    job["local_replays"] = job.get("local_replays", 0) + int(replay)
                    job["budget_status"] = store.status(job["job_id"])
                    return parsed
                return scanned_ocr.review_with_vision(bundle, document.language, run_call, selection.model, progress)
        finally:
            store.close()

    def _run_auto_mode(self, job, structure, glossary, units):
        """Auto/mock mode: no configured provider, so no real cost and no
        real Hebrew text -- kept as the original simple flat translation
        loop (no persistent budget/cache, no document state/chapter QA
        wiring, all of which exist only to control and connect *real*
        provider spend)."""
        for index, unit in enumerate(units):
            request = build_translation_request(
                structure, glossary, unit["unit_id"], job["settings"]["profile"], "mock", "mock-translation-1",
            )
            adapter = self._translation_adapter(request)
            draft = run_translation(request, adapter=adapter, budget=None)
            job["units"].append({
                "unit_id": unit["unit_id"], "order": index, "page_id": unit["page_id"],
                "chapter_node_id": draft["chapter_node_id"], "source_text": unit["text"],
                "target_text": draft["draft_text"] or "", "translation_note": draft["translation_note"],
                "status": draft["status"], "findings": draft["findings"],
                "document_state_version": draft["document_state_version"],
                "approved": False, "human_edited": False, "review": None,
            })
            job["completed_units"] = index + 1
            self._persist(job)

        policies = _QUALITY_POLICIES[job["settings"]["quality"]]
        if policies["unit_review"] != "off":
            job["status"], job["stage_label"] = "reviewing", "בבדיקה"
            self._persist(job)
            self._run_unit_reviews(job, None, policies["unit_review"])
        if policies["chapter_qa"] == "on":
            job["status"], job["stage_label"] = "reviewing", "בבדיקת פרקים"
            self._persist(job)
            job["review_notes"].append("מצב Auto/ללא ספק מוגדר: בדיקת פרקים נדלגה (אין תרגום עברי אמיתי לבדוק).")

    def _run_configured_mode(self, job, structure, glossary, units, policies, configuration, store):
        """The real, controlled path (Session G): translate chapter by
        chapter so each chapter's QA-proposed persistent-state updates are
        committed and visible to the *next* chapter's translation (the
        2026-10-05 addendum's required flow), and route every live
        translation/review/QA call for this document through one shared
        ControlStore task -- one persistent budget and cache, not a
        separate uncontrolled path for review/QA."""
        job_id = job["job_id"]
        selection, _translator_definition = configuration.resolve("translator")
        output_cap = self._shared_output_cap(configuration)
        max_calls = len(units) * 3 + 10
        hard_list_usd = job["settings"]["budget_usd"]

        translate_budget = PersistentBudget(
            store, job_id, max_calls=max_calls, hard_list_usd=hard_list_usd, stage="translate",
            provider=selection.provider, model=selection.model, output_cap=output_cap,
        )
        translate_cache = RuntimeCache(store, stage="translate", provider=selection.provider, model=selection.model)

        document_state = document_state_module.new_document_state(structure["document_id"])
        job["document_state"] = document_state
        groups = self._chapter_groups(structure, units)

        chapter_qa_resolved = None
        if policies["chapter_qa"] == "on":
            chapter_qa_resolved = self._resolve_role(configuration, "chapter_qa")
            if chapter_qa_resolved is None:
                job["review_notes"].append("תפקיד chapter_qa אינו מוגדר; בדיקת פרקים נדלגה.")

        for group_index, group in enumerate(groups, start=1):
            job["chapter_progress"] = {"current": group_index, "total": len(groups)}
            self._persist(job)
            for unit in group:
                request = build_translation_request_for_role(
                    structure, glossary, unit["unit_id"], job["settings"]["profile"], configuration,
                    document_state=document_state,
                )
                adapter = self._translation_adapter(request)
                draft = run_translation(request, adapter=adapter, cache=translate_cache, budget=translate_budget)
                job["units"].append({
                    "unit_id": unit["unit_id"], "order": len(job["units"]), "page_id": unit["page_id"],
                    "chapter_node_id": draft["chapter_node_id"], "source_text": unit["text"],
                    "target_text": draft["draft_text"] or "", "translation_note": draft["translation_note"],
                    "status": draft["status"], "findings": draft["findings"],
                    "document_state_version": draft["document_state_version"],
                    "approved": False, "human_edited": False, "review": None,
                })
                job["completed_units"] = len(job["units"])
                job["estimated_cost_usd"] = self._store_cost(store, job_id)
                self._persist(job)

            if policies["chapter_qa"] == "on" and chapter_qa_resolved is not None:
                job["status"], job["stage_label"] = "reviewing", "בבדיקת פרקים"
                self._persist(job)
                chapter_records = job["units"][-len(group):]
                document_state = self._run_chapter_qa_for_group(
                    job, configuration, chapter_qa_resolved, chapter_records, document_state,
                    store, output_cap, max_calls, hard_list_usd,
                )
                job["document_state"] = document_state
                job["estimated_cost_usd"] = self._store_cost(store, job_id)
                job["status"], job["stage_label"] = "translating", "מתרגם"
                self._persist(job)

        if policies["unit_review"] != "off":
            job["status"], job["stage_label"] = "reviewing", "בבדיקה"
            self._persist(job)
            self._run_unit_reviews(job, configuration, policies["unit_review"],
                                    store, output_cap, max_calls, hard_list_usd)
            job["estimated_cost_usd"] = self._store_cost(store, job_id)
            self._persist(job)

    def _risk_flags_for(self, unit_record, profile=None):
        return chapter_pipeline.detect_risk_triggers(unit_record, profile)

    def _run_unit_reviews(self, job, configuration, policy, store=None, output_cap=None,
                          max_calls=None, hard_list_usd=None):
        if configuration is None:
            # Auto/mock mode never produces real Hebrew text (the mock
            # translation adapter's placeholder is deliberately conspicuous,
            # non-Hebrew text); review_qa.py rightly refuses to "review" that,
            # so Auto-mode review is a graceful, documented no-op, not a crash.
            job["review_notes"].append("מצב Auto/ללא ספק מוגדר: בדיקת מקטעים נדלגה (אין תרגום עברי אמיתי לבדוק).")
            return
        resolved = self._resolve_role(configuration, "semantic_reviewer")
        if resolved is None:
            job["review_notes"].append("תפקיד semantic_reviewer אינו מוגדר; בדיקת מקטעים נדלגה.")
            return
        provider, model, provider_definition, capabilities = resolved
        make_generate = self._resolve_review_controls(
            "semantic_reviewer", "unit-review", provider, model, provider_definition, capabilities,
            store, output_cap, max_calls, hard_list_usd, job["job_id"],
        )
        budget_exhausted_noted = False
        for unit_record in job["units"]:
            risk_flags = self._risk_flags_for(unit_record, job["settings"].get("profile"))
            request = build_unit_review_request_for_role(
                unit_record["source_text"], unit_record["target_text"] or unit_record["source_text"],
                configuration, policy=policy, risk_flags=risk_flags,
            )
            generate = make_generate(("unit-review", unit_record["unit_id"]), unit_record["unit_id"])
            result = run_unit_review(request, generate=generate)
            unit_record["review"] = {
                "status": result["status"], "verdict": result.get("verdict"), "issues": result.get("issues", []),
            }
            if not budget_exhausted_noted and (result.get("call") or {}).get("error") == "document_budget_exhausted":
                job["review_notes"].append("תקציב המסמך הגיע למגבלה; בדיקות מקטעים נוספות נדלגו.")
                budget_exhausted_noted = True
            self._persist(job)

    def _run_chapter_qa_for_group(self, job, configuration, resolved, chapter_records, document_state,
                                   store, output_cap, max_calls, hard_list_usd):
        """Run chapter-level QA for one already-translated chapter, then
        (Session G) adapt any ``proposed_state_updates`` it returns into
        document_state.py candidates, surface contradictions against the
        existing state rather than silently overwrite them, and commit
        the rest -- returning the (possibly updated) document_state for
        the *next* chapter to use. The caller resolves the chapter_qa role
        (or decides to skip it) once for the whole document, not once per
        chapter, so a "not configured" note is never duplicated per chapter."""
        provider, model, provider_definition, capabilities = resolved

        chapter_node_id = chapter_records[0]["chapter_node_id"]
        unit_ids = [u["unit_id"] for u in chapter_records]
        source_chapter = "\n\n".join(u["source_text"] for u in chapter_records)
        hebrew_chapter = "\n\n".join((u["target_text"] or u["source_text"]) for u in chapter_records)
        request = build_chapter_qa_request_for_role(
            source_chapter, hebrew_chapter, configuration,
            profile=job["settings"]["profile"], policy="on",
        )
        make_generate = self._resolve_review_controls(
            "chapter_qa", "chapter-qa", provider, model, provider_definition, capabilities,
            store, output_cap, max_calls, hard_list_usd, job["job_id"],
        )
        identity = ("chapter-qa", chapter_node_id or "flat", len(job["chapter_qa_results"]))
        generate = make_generate(identity, chapter_node_id or "document")
        result = run_chapter_qa(request, generate=generate)

        entry = {
            "unit_ids": unit_ids, "status": result["status"],
            "verdict": result.get("verdict"), "issues": result.get("issues", []),
            "chapter_level_notes": result.get("chapter_level_notes"),
            "state_proposed": 0, "state_committed": 0, "state_conflicts": [],
        }
        new_state = document_state
        if result["status"] == "completed" and chapter_node_id is not None:
            candidates = _state_candidates_from_chapter_qa(
                result.get("proposed_state_updates") or [], document_id=document_state["document_id"],
                chapter_node_id=chapter_node_id, unit_ids=unit_ids, source_chapter=source_chapter,
            )
            entry["state_proposed"] = len(candidates)
            if candidates:
                conflicts = document_state_module.find_conflicts(new_state, candidates)
                conflict_keys = {(c["category"], c["label"]) for c in conflicts}
                entry["state_conflicts"] = conflicts
                accepted = [c for c in candidates if (c["category"], c["label"]) not in conflict_keys]
                if accepted:
                    new_state = document_state_module.commit_update(
                        new_state, accepted, chapter_node_id=chapter_node_id,
                        actor="chapter_qa:" + (provider_definition.provider_type if provider_definition else provider),
                        actor_kind="model", reason="chapter-level QA proposed update",
                    )
                    entry["state_committed"] = len(accepted)
        job["chapter_qa_results"].append(entry)
        if (result.get("call") or {}).get("error") == "document_budget_exhausted":
            job["review_notes"].append("תקציב המסמך הגיע למגבלה; בדיקת פרקים נוספת נדלגה.")
        self._persist(job)
        return new_state

    def _run_automation_chapter_mode(self, job, structure, glossary, units, configuration, store):
        chapter_pipeline.execute_document_chapters(job, structure, glossary, units, configuration,
            store, self._folder(job["job_id"]), self._persist,
            self._job_adapter_factories.get(job["job_id"], self.adapter_factory))

    def blocker(self, job_id, job=None):
        """Why this automation job cannot continue and the user's choices, or None."""
        job = job or self.get(job_id)
        folder = self._folder(job_id)
        controls, journal_path = folder / "controls.sqlite3", folder / "journal.sqlite3"
        if not job.get("settings", {}).get("automation") or not controls.is_file() or not journal_path.is_file():
            return None
        try:
            with ControlStore(controls, create=False) as store, WorkJournal(journal_path, create=False) as journal:
                return job_blocks.diagnose(job, store, journal)
        except (RuntimeControlsError, ValueError):
            return None

    def decide(self, job_id, option_id, value=None):
        """Apply the user's explicit choice for the current block. Sends nothing;
        the caller resumes afterwards."""
        folder = self._folder(job_id)
        controls, journal_path = folder / "controls.sqlite3", folder / "journal.sqlite3"
        with self.lock:
            if self.active is not None:
                raise DocumentDraftError("מסמך מתורגם כרגע. המתינו לסיום או השהו אותו.")
            job = self.get(job_id)
            if job["status"] == "completed" or not controls.is_file() or not journal_path.is_file():
                raise DocumentDraftError("אין חסימה שדורשת החלטה בעבודה זו.")
            try:
                with ControlStore(controls, create=True) as store, WorkJournal(journal_path, create=False) as journal:
                    job_blocks.apply_decision(job, store, journal, option_id, value)
            except job_blocks.BlockDecisionError as exc:
                raise DocumentDraftError(str(exc)) from None
            for transient in ("budget_status", "remaining_budget_usd", "estimated_cost_usd"):
                job.pop(transient, None)
            self._persist(job)
        job = self.get(job_id)
        job["blocker"] = self.blocker(job_id, job)
        return job

    def recheck_saved_reviews(self, job_id):
        """Re-read saved review/QA answers with the current parser (no provider call)
        and reopen chapters whose results changed; the caller resumes afterwards."""
        with target_languages.use(target_languages.settings_code(self._target_settings(job_id))):
            return self._recheck_saved_reviews(job_id)

    def _recheck_saved_reviews(self, job_id):
        folder = self._folder(job_id)
        journal_path = folder / "journal.sqlite3"
        with self.lock:
            if self.active is not None:
                raise DocumentDraftError("מסמך מתורגם כרגע. המתינו לסיום או השהו אותו.")
            job = self.get(job_id)
            if not job["settings"].get("automation") or not journal_path.is_file() or not job.get("chapter_groups"):
                raise DocumentDraftError("אין תשובות בקורת שמורות לבדיקה בעבודה זו.")
            with WorkJournal(journal_path, create=False) as journal:
                report = review_salvage.recheck_saved_reviews(job, journal)
            for transient in ("budget_status", "remaining_budget_usd", "estimated_cost_usd"):
                job.pop(transient, None)
            self._persist(job)
        job = self.get(job_id)
        job["blocker"] = self.blocker(job_id, job)
        job["recheck_report"] = report
        return job

    def cross_chapter_review(self, job_id):
        """Prepare a cross-chapter review (name table + windows of chapters) for an existing
        notebook job. Sends nothing to any provider: the job is left paused and the normal
        ``resume`` runs the review."""
        folder = self._folder(job_id)
        journal_path = folder / "journal.sqlite3"
        with self.lock:
            if self.active is not None:
                raise DocumentDraftError("מסמך מתורגם כרגע. המתינו לסיום או השהו אותו.")
            job = self.get(job_id)
            if (not job.get("settings", {}).get("automation") or not job.get("book_notebook")
                    or not journal_path.is_file()):
                raise DocumentDraftError("הבדיקה הרוחבית זמינה רק לעבודה אוטומטית עם מחברת ספר.")
            try:
                report = chapter_pipeline.enable_cross_review(job)
            except chapter_pipeline.ChapterPipelineError as exc:
                raise DocumentDraftError(str(exc)) from None
            job["status"], job["stage_label"] = "paused", "ממתין לבדיקה רוחבית"
            for transient in ("budget_status", "remaining_budget_usd", "estimated_cost_usd"):
                job.pop(transient, None)
            self._persist(job)
        job = self.get(job_id)
        job["blocker"] = self.blocker(job_id, job)
        job["cross_review_report"] = report
        return job

    def delete(self, job_id):
        """Permanently remove a saved job folder (source copy, translation, journal,
        cost log). Refused while that job is running. Sends nothing to any provider."""
        folder = self._folder(job_id)
        with self.lock:
            if self.active == job_id:
                raise DocumentDraftError("המסמך מתורגם כרגע. השהו אותו לפני המחיקה.")
            if not (folder / "job.json").is_file():
                raise DocumentDraftError("מסמך לא נמצא.")
            if folder.resolve().parent != self.root.resolve():
                raise DocumentDraftError("מסמך לא נמצא.")
            self._job_adapter_factories.pop(job_id, None)
            shutil.rmtree(folder)
        return {"deleted": job_id}

    def pause(self, job_id):
        """Request a safe pause of a running automation job: the in-flight
        step finishes and persists its result, then the worker stops before any further
        provider call. Journal-flag only; ``resume`` is the actual job
        operation that continues the work. A job with no journal (not an
        automation job, or not yet started) has nothing to pause."""
        job = self.get(job_id)
        if not job['settings'].get('automation'):
            raise DocumentDraftError('השהיה זמינה במסלול האוטומטי בלבד.')
        journal_path = self._folder(job_id) / "journal.sqlite3"
        with WorkJournal(journal_path, create=True) as journal:
            journal.pause(job_id)
        with self.lock:
            if self.active != job_id and job["status"] in (
                "queued", "reading", "translating", "reviewing",
            ):
                job["status"], job["stage_label"] = "paused", "הופסק"
                self._persist(job)
        return self.get(job_id)

    def resume(self, job_id, path=None, adapter_factory=None):
        """Resume a paused (or interrupted) automation job from its saved
        structure/units/document_state -- never from a fresh extraction.
        An already-completed job returns unchanged, making zero provider
        calls. ``adapter_factory`` may supply fresh memory-only credentials
        for this resume without changing the job's persisted configured
        model selection."""
        job = self.get(job_id)
        if job["status"] == "completed":
            return job
        if job["settings"]["model"] != "configured" or not job["settings"].get("automation"):
            raise DocumentDraftError("ניתן להמשיך רק עבודת אוטומציה שהתחילה עם מודל מוגדר.")
        journal_path = self._folder(job_id) / "journal.sqlite3"
        # Stopped before its structure existed (e.g. during OCR/vision review): rerun the
        # reading stage -- cached OCR pages and journaled vision answers are reused, not resent.
        rerun_reading = job["structure"] is None
        if not rerun_reading and not journal_path.is_file():
            raise DocumentDraftError("לא נמצא יומן עבודה להמשך.")
        with self.lock:
            if self.active:
                raise DocumentDraftError("מסמך אחר מתורגם כרגע. המתינו לסיום.")
            if journal_path.is_file():
                with WorkJournal(journal_path, create=False) as journal:
                    journal.resume(job_id)
            if adapter_factory is not None:
                self._job_adapter_factories[job_id] = adapter_factory
            job["status"], job["error"] = "translating", None
            self._persist(job)
            self.active = job_id
        source_path = self.source_path(job_id, job["source_kind"])
        target = self._run if rerun_reading else self._resume_run
        threading.Thread(target=target, args=(job, source_path), daemon=True).start()
        return {"job_id": job_id}

    def _resume_run(self, job, source_path):
        with target_languages.use(target_languages.settings_code(job.get("settings"))):
            return self._resume_run_body(job, source_path)

    def _resume_run_body(self, job, source_path):
        """Continue an automation job from its persisted structure/units/
        document_state, using its already-configured model/budget/quality
        settings unchanged. Completed journal steps replay with zero
        provider calls; already-recorded units are never re-appended."""
        store = None
        try:
            structure = job["structure"]
            page_number_by_id = {r["page_id"]: r["page_number"] for r in structure["readings"]}
            units = sorted(
                structure["units"],
                key=lambda u: (page_number_by_id[u["page_id"]], u["source_char_start"]),
            )
            configuration = ModelConfiguration.from_dict(job["settings"]["model_config"])
            glossary = job.get("glossary") or _new_glossary_store()
            document_state = job["document_state"] or document_state_module.new_document_state(structure["document_id"])
            store_path = validate_store_path(self._folder(job["job_id"]) / "controls.sqlite3")
            if not store_path.is_file():
                raise DocumentDraftError('לא נמצאה בקרת התקציב המקורית; ההמשך נעצר ללא שליחה.')
            store = ControlStore(store_path, create=True)
            job["status"], job["stage_label"] = "translating", "מתרגם"
            self._persist(job)
            self._run_automation_chapter_mode(job, structure, glossary, units, configuration, store)
            if job["status"] == "paused":
                return

            job["status"], job["stage_label"] = "rebuilding", "בניית המסמך המתורגם"
            self._persist(job)
            translations = _build_translations_mapping(job["units"])
            if job["source_kind"] == "epub":
                result = _export_epub(source_path, structure, translations)
            else:
                result = _export_pdf(structure, translations, title=job["filename"], font_id=job['settings'].get('font_id'))
            job["export_limitations"] = result.limitations
            job["export_page_count"] = getattr(result, "page_count", 0)
            job["status"], job["stage_label"] = "completed", "הושלם"
        except DocumentDraftError as exc:
            job["status"], job["error"] = "failed", str(exc)
        except (TranslationRequestError, TranslationBudgetError) as exc:
            job["status"], job["error"] = "failed", f"התרגום נעצר: {exc}"
        except chapter_pipeline.PipelinePaused:
            job["status"], job["stage_label"] = "paused", "מושהה — התוצאות נשמרו"
        except chapter_pipeline.ChapterPipelineError as exc:
            job["status"], job["error"] = "failed", f"התרגום האוטומטי נעצר: {exc}"
        except OpenAIConfigurationError as exc:
            job["status"], job["error"] = "failed", f"תצורת הספק שגויה: {exc}"
        except RuntimeControlsError as exc:
            job["status"], job["error"] = "failed", f"בקרת התקציב/המטמון נכשלה: {exc}"
        except Exception:
            job["status"], job["error"] = "failed", "התרגום לא הושלם. בדקו חיבור, הרשאת המודל ומפתח API. התוצאה החלקית נשמרה."
        finally:
            if store is not None:
                store.close()
            try:
                self._persist(job)
            finally:
                with self.lock:
                    self.active = None
        self._auto_continue(job)

    def _auto_continue(self, job):
        """Apply the user's standing rule (job_blocks.auto_decision) to a job that
        just stopped, then resume it after a short wait (job_blocks.auto_retry_delay);
        any other block waits for the user."""
        if job["status"] != "failed" or not job["settings"].get("automation"):
            return
        folder = self._folder(job["job_id"])
        controls, journal_path = folder / "controls.sqlite3", folder / "journal.sqlite3"
        if not controls.is_file() or not journal_path.is_file():
            return
        with self.lock:
            if self.active is not None:
                return
            try:
                # Writable (create=True; the file exists): settling the held charge writes.
                with ControlStore(controls, create=True) as store, WorkJournal(journal_path, create=False) as journal:
                    option = job_blocks.auto_decision(job, store, journal)
                    if option is None:
                        return
                    job_blocks.apply_decision(job, store, journal, option, auto=True)
            except (RuntimeControlsError, ValueError):
                return
            for transient in ("budget_status", "remaining_budget_usd", "estimated_cost_usd"):
                job.pop(transient, None)
            delay = job_blocks.auto_retry_delay(job)
            token = secrets.token_hex(8)
            job["status"], job["auto_retry"] = "paused", token
            job["stage_label"] = "החיבור לספק נותק; ניסיון חוזר אוטומטי בעוד %d שניות" % delay
            self._persist(job)
        timer = threading.Timer(delay, self._auto_resume, (job["job_id"], token))
        timer.daemon = True
        timer.start()

    def _auto_resume(self, job_id, token):
        """Resume after the automatic wait, unless the user acted meanwhile (resumed,
        paused or decided otherwise) or another document holds the slot."""
        try:
            job = self.get(job_id)
            if job.get("auto_retry") != token or job["status"] != "paused":
                return
            with WorkJournal(self._folder(job_id) / "journal.sqlite3", create=False) as journal:
                if journal.is_paused(job_id):
                    return
            self.resume(job_id)
        except (DocumentDraftError, RuntimeControlsError, ValueError):
            pass   # the user resumes this one

    def preview(self, path, settings):
        """Thin cost/plan preview for a prospective automation run: no job
        is created, no provider/network/journal/budget side effects occur.
        Raises the same validation errors ``start`` would."""
        settings = validate_settings(settings)
        with target_languages.use(target_languages.settings_code(settings)):
            return self._preview(path, settings)

    def _preview(self, path, settings):
        if settings["model"] != "configured":
            raise DocumentDraftError("תצוגה מקדימה של עלות דורשת מודל מוגדר.")
        configuration = ModelConfiguration.from_dict(settings["model_config"])
        document = extract_document(path, settings["language"])
        _check_source_differs(document, settings)
        if document.source_kind == "pdf" and scanned_ocr.scanned_pages(document):
            return self._scanned_preview(document, settings, configuration)
        structure = _planned_structure(path, settings["language"], configuration, document=document)
        glossary = _new_glossary_store()
        page_number_by_id = {r["page_id"]: r["page_number"] for r in structure["readings"]}
        units = sorted(
            structure["units"], key=lambda u: (page_number_by_id[u["page_id"]], u["source_char_start"]),
        )
        try:
            groups = chapter_pipeline.fit_chapter_groups(
                structure, glossary, chapter_groups(structure, units), configuration,
                settings["quality"], settings["profile"],
            )
        except chapter_pipeline.ChapterPipelineError as exc:
            raise DocumentDraftError(f"לא ניתן לתכנן את התרגום עם המודלים שנבחרו: {exc}") from None
        chapters = []
        total_expected, total_conservative = 0.0, 0.0
        for group in groups:
            unit_ids = [u["unit_id"] for u in group]
            preview = chapter_pipeline.estimate_preview(
                structure, glossary, unit_ids, configuration, settings["quality"], settings["profile"],
            )
            chapters.append(preview)
            total_expected += preview["expected_total_cost_usd"]
            total_conservative += preview["conservative_total_ceiling_usd"]
        return {
            "chapter_count": len(groups), "chapters": chapters,
            "expected_total_cost_usd": total_expected,
            "conservative_total_ceiling_usd": total_conservative,
        }

    def _scanned_preview(self, document, settings, configuration):
        """Preview for a PDF with scanned pages: the text does not exist before OCR,
        so only the OCR/vision-review part is estimated; translation is planned after
        OCR against the same budget (over budget -> a decision for the user)."""
        from .model_catalog import estimate_cost
        pages = scanned_ocr.scanned_pages(document)
        ready, reason = scanned_ocr.ocr_ready(document.language)
        review = settings.get("ocr_review", "vision") == "vision"
        expected = ceiling = 0.0
        if review:
            selection, definition = configuration.resolve("translator")
            image = scanned_ocr.IMAGE_TOKEN_ALLOWANCE
            for usage, bound in (({"input": 1500 + image, "output": 1500}, False),
                                 ({"input": 3000 + image, "output": 4096}, True)):
                quote = estimate_cost(definition.provider_type, selection.model, usage,
                                      custom_rates=selection.capabilities.custom_pricing)
                if quote is None:
                    raise DocumentDraftError("אין מחיר ידוע למודל עבור בדיקת ה־OCR.")
                if bound:
                    ceiling = quote["cost_usd"] * len(pages)
                else:
                    expected = quote["cost_usd"] * len(pages)
        return {
            "scanned": True, "scanned_pages": len(pages), "total_pages": len(document.pages),
            "ocr_ready": ready, "ocr_problem": reason, "vision_review": review,
            "chapter_count": 0, "chapters": [],
            "expected_total_cost_usd": expected, "conservative_total_ceiling_usd": ceiling,
        }

    def review(self, job_id, unit_index, target_text, expected_revision):
        with self.lock:
            return self._review_locked(job_id, unit_index, target_text, expected_revision)

    def _review_locked(self, job_id, unit_index, target_text, expected_revision):
        with target_languages.use(target_languages.settings_code(self._target_settings(job_id))):
            return self._review_locked_body(job_id, unit_index, target_text, expected_revision)

    def _review_locked_body(self, job_id, unit_index, target_text, expected_revision):
        with self.lock:
            if self.active == job_id:
                raise DocumentDraftError("המתינו לסיום התרגום לפני עריכה.")
        job = self.get(job_id)
        if job["status"] != "completed" or type(unit_index) is not int or not 0 <= unit_index < len(job["units"]):
            raise DocumentDraftError("מקטע זה אינו זמין לעריכה.")
        if type(expected_revision) is not int or expected_revision != job["revision"]:
            raise DocumentDraftError("המסמך השתנה. רעננו את התוצאה לפני שמירה.")
        if not isinstance(target_text, str) or not target_text.strip() or len(target_text) > 30000:
            raise DocumentDraftError("יש להזין טקסט תקין עד 30,000 תווים למקטע.")
        folder = self._folder(job_id)
        revision = job["revision"] + 1
        (folder / f"revision-{job['revision']}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        unit_record = job["units"][unit_index]
        unit_record["target_text"], unit_record["human_edited"] = target_text, True
        unit_record['review_stale'] = True
        unit_record['findings'] = run_formal_checks(unit_record['source_text'], target_text,
                                                  unit_record.get('source_language', 'en'))
        job['quality_status'] = 'edited_draft_review_stale'
        job["revision"] = revision
        self._persist(job)
        return job
