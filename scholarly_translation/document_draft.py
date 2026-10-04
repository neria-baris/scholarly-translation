"""Automated whole-document drafts, driven by the canonical translation
backend (Session F). No source or scholarly approval is inferred beyond the
single, explicitly-logged auto-accept decision described below.

PDF jobs flow: pdf_extract.extract_pdf -> (auto-accept the sole digital
candidate per page, since this simple flow offers no OCR/alternative to
choose between) -> segmentation.build_structure -> per-unit
translation.build_translation_request(_for_role) -> translation.run_translation
-> (quality-mode-gated) review_qa unit review / chapter QA ->
export_pdf.export_pdf. EPUB input is intentionally not supported by this
job runner yet -- see the module-level ``EPUB_BLOCKED_MESSAGE`` docstring
below for why.
"""
from __future__ import annotations

import json
import math
import os
import re
import secrets
import threading
from dataclasses import replace as _dc_replace
from datetime import datetime, timezone
from pathlib import Path

from . import pdf_extract, segmentation
from .export_common import ExportError
from .export_pdf import export_pdf as _export_pdf
from .glossary import new_store as _new_glossary_store
from .model_adapter import OpenAIConfigurationError, TextGenerationResult
from .model_config import ModelConfigError, ModelConfiguration
from .review_qa import (
    build_chapter_qa_request,
    build_chapter_qa_request_for_role,
    build_unit_review_request,
    build_unit_review_request_for_role,
    run_chapter_qa,
    run_unit_review,
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

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_SOURCE_CHARS = 150_000
MAX_PAGES = 200
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

# EPUB cannot honestly be routed through this same canonical path yet: the
# shared segmentation.validate_structure()/source_reading.py evidence schema
# hard-requires a "digital" source candidate whose *literal* provenance
# stage string is "digital-pdf@1" (source_reading.validate_candidate), plus
# real page geometry (pdf_width/pdf_height/bbox) for every anchor. EPUB text
# never went through PDF digital extraction and has no page geometry at all
# (it reflows); satisfying that validator for EPUB would require either (a)
# fabricating a false "digital-pdf@1" provenance claim for text that was
# never PDF-extracted, or (b) adding a new, legitimate non-PDF origin type
# to source_reading.py/document_structure.py's schema -- explicitly out of
# scope for this session ("do not change document_structure.py's schema-2
# contract... to accommodate it"). This is the exact "EPUB adapter needs a
# much larger reinterpretation than smallest adapter can cover" case the
# Session F contract's own stop_condition names; see the Session F delivery
# report for the full writeup. EPUB upload is refused with a clear message
# rather than silently faking provenance or guessing at a schema change.
EPUB_BLOCKED_MESSAGE = (
    "תרגום קובצי EPUB דרך ממשק זה מושבת כעת: אין דרך ישרה וכנה לבנות עבור "
    "EPUB את אותה סכימת ראיות (מקור PDF/OCR עם גיאומטריית עמוד) שה-pipeline "
    "המרכזי דורש, מבלי לזייף נתוני מקור. זהו חוסם ארכיטקטוני שדווח למוביל; "
    "PDF נתמך במלואו."
)


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
        status="mock_placeholder", text="VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: (none)",
        token_usage="not_metered", observed_model=model, duration_seconds=0.0,
        observed_provider="mock",
    )


_LANGUAGE_WORD_RE = re.compile(r"\b(?:les|des|une|dans|pour|avec|est|qui)\b")
_CJK_RE = re.compile(r"[぀-ヿ一-鿿]")


def _detect_language(document) -> str:
    sample = "\n".join(p.source_text or "" for p in document.pages)[:10000]
    if _CJK_RE.search(sample):
        return "ja"
    if len(_LANGUAGE_WORD_RE.findall(sample.lower())) >= 3:
        return "fr"
    return "en"


def _auto_accept_decisions(document):
    """Resolve each page's sole usable (digital) candidate automatically.

    This simple flow offers no OCR and no alternative source candidate to
    choose between, so there is no real choice for a human to make; the
    uploading user, by starting translation, is the accepting human. A page
    with no usable digital text (e.g. scanned, no extractable text) is left
    unresolved -- same unsupported spirit as before, surfaced later as a
    clear error if it leaves the whole document with no translatable text.
    """
    draft_structure = segmentation.build_structure(document)
    decisions = {}
    for reading in draft_structure["readings"]:
        if reading["status"] == "resolved":
            continue
        usable = next((c for c in reading["alternatives"] if c["usable"]), None)
        if usable is None:
            continue
        decisions[reading["page_id"]] = {
            "origin": usable["origin"], "candidate_hash": usable["candidate_hash"],
            "actor": "simple-upload-flow (initiating user)", "actor_kind": "human",
            "reason": "single available digital-extraction candidate; automatically accepted by "
                      "the simple upload-and-translate flow (no OCR offered, no alternative to choose between)",
        }
    if not decisions:
        return draft_structure
    return segmentation.build_structure(document, decisions=decisions, previous=draft_structure)


def extract_structure(path, language="auto"):
    """Extract a PDF into the canonical schema-2 document_structure, with
    every resolvable page's sole candidate auto-accepted. Raises
    DocumentDraftError for anything invalid, oversized, or with no
    extractable text at all (same spirit as the historical OCR-required
    message)."""
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
        raise DocumentDraftError("בחרו קובץ תקין עד 25 MB.")
    if path.suffix.lower() == ".epub":
        raise DocumentDraftError(EPUB_BLOCKED_MESSAGE)
    if path.suffix.lower() != ".pdf":
        raise DocumentDraftError("ניתן לתרגם קובצי PDF בלבד כרגע.")
    if language not in LANGUAGES:
        raise DocumentDraftError("שפת מקור לא נתמכת.")
    try:
        document = pdf_extract.extract_pdf(path, language if language != "auto" else "en")
    except pdf_extract.ExtractionError as exc:
        raise DocumentDraftError(f"לא ניתן לקרוא את הקובץ: {exc}") from None
    if len(document.pages) > MAX_PAGES:
        raise DocumentDraftError("המסמך מוגבל כרגע ל־200 עמודים.")
    total_chars = sum(len(p.source_text or "") for p in document.pages)
    if total_chars > MAX_SOURCE_CHARS:
        raise DocumentDraftError("המסמך ארוך מדי כרגע. חלקו אותו לקבצים עד 150,000 תווים.")
    if language == "auto":
        document = _dc_replace(document, language=_detect_language(document))
    try:
        structure = _auto_accept_decisions(document)
    except segmentation.StructureError as exc:
        raise DocumentDraftError(f"מבנה המסמך אינו תקין: {exc}") from None
    if not structure["units"]:
        raise DocumentDraftError("ה־PDF מכיל עמודים סרוקים ללא טקסט. נדרש OCR לפני התרגום.")
    return structure


def validate_settings(settings):
    profile = settings.get("profile", "scholarly")
    quality = settings.get("quality", "fast")
    language = settings.get("language", "auto")
    budget = settings.get("budget_usd", 2.0)
    model_choice = settings.get("model", "auto")
    model_config_data = settings.get("model_config")
    if profile not in SUPPORTED_PROFILE_IDS:
        raise DocumentDraftError("בחרו פרופיל תרגום נתמך (אקדמי/ספרותי).")
    if quality not in QUALITY_MODES:
        raise DocumentDraftError("בחרו רמת בדיקה נתמכת.")
    if language not in LANGUAGES:
        raise DocumentDraftError("הגדרות תרגום לא תקינות.")
    if type(budget) not in (int, float) or isinstance(budget, bool) or not math.isfinite(budget) or not 0.01 <= budget <= 30:
        raise DocumentDraftError("תקציב המסמך חייב להיות בין $0.01 ל־$30.")
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
    }


def _write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _build_translations_mapping(units):
    return {
        u["unit_id"]: {"text": u["target_text"] or u["source_text"], "approved": u["approved"], "status": u["status"]}
        for u in units
    }


def render_download(job, kind):
    """Rebuild the translated PDF from the job's current (possibly
    human-edited) unit texts; never a frozen completion-time snapshot."""
    if kind != "pdf":
        raise DocumentDraftError("סוג הורדה לא נתמך.")
    if job["status"] not in ("completed",) or not job.get("units"):
        raise DocumentDraftError("עדיין אין תוצאה להורדה.")
    translations = _build_translations_mapping(job["units"])
    try:
        result = _export_pdf(job["structure"], translations, title=job["filename"])
    except ExportError as exc:
        raise DocumentDraftError(f"בנייית ה-PDF נכשלה: {exc}") from None
    return result.content


class DocumentJobs:
    """One active document worker; durable local results, no background retries."""

    def __init__(self, root, adapter_factory=None):
        self.root = Path(root) / "documents"
        self.adapter_factory = adapter_factory
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
        return job

    def _persist(self, job):
        with self.lock:
            _write_json(self._folder(job["job_id"]) / "job.json", job)

    def start(self, path, settings, paid_confirm=False):
        settings = validate_settings(settings)
        if settings["model"] == "configured" and paid_confirm is not True:
            raise DocumentDraftError("נדרש אישור לשליחת המסמך לספק המודל המוגדר.")
        if settings["model"] == "configured" and self.adapter_factory is None:
            configuration = ModelConfiguration.from_dict(settings["model_config"])
            _, definition = configuration.resolve("translator")
            try:
                definition.require_credential(os.environ)
            except ModelConfigError as exc:
                raise DocumentDraftError(str(exc)) from None
        with self.lock:
            if self.active:
                raise DocumentDraftError("מסמך אחר מתורגם כרגע. המתינו לסיום.")
            job_id = secrets.token_hex(16)
            folder = self._folder(job_id)
            folder.mkdir(parents=True, exist_ok=False)
            job = {
                "schema_version": 2, "stage": "document-draft@2", "job_id": job_id,
                "filename": Path(path).name, "settings": settings, "status": "queued",
                "stage_label": None, "completed_units": 0, "total_units": 0, "chapter_progress": None,
                "units": [], "structure": None, "approved": False, "source_reviewed": False,
                "revision": 0, "created_at": datetime.now(timezone.utc).isoformat(),
                "error": None, "estimated_cost_usd": 0.0,
                "export_limitations": [], "export_page_count": 0, "review_notes": [],
                "chapter_qa_results": [],
            }
            self._persist(job)
            self.active = job_id
        threading.Thread(target=self._run, args=(job, Path(path)), daemon=True).start()
        return {"job_id": job_id}

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

    def _review_generate(self, role, provider_definition):
        if self.adapter_factory is not None:
            return self.adapter_factory(role, None).generate
        if provider_definition is None:
            return _mock_review_generate if role == "semantic_reviewer" else _mock_chapter_qa_generate
        return None  # let review_qa build the real adapter from provider_definition

    def _run(self, job, path):
        try:
            job["status"], job["stage_label"] = "reading", "קריאת המסמך"
            self._persist(job)
            structure = extract_structure(path, job["settings"]["language"])
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
            budget = (
                TranslationBudget(max_calls=len(units) + 5, hard_list_usd=job["settings"]["budget_usd"])
                if configuration is not None else None
            )
            policies = _QUALITY_POLICIES[job["settings"]["quality"]]

            job["status"], job["stage_label"] = "translating", "מתרגם"
            self._persist(job)
            for index, unit in enumerate(units):
                if configuration is not None:
                    request = build_translation_request_for_role(
                        structure, glossary, unit["unit_id"], job["settings"]["profile"], configuration,
                    )
                else:
                    request = build_translation_request(
                        structure, glossary, unit["unit_id"], job["settings"]["profile"], "mock", "mock-translation-1",
                    )
                adapter = self._translation_adapter(request)
                draft = run_translation(request, adapter=adapter, budget=budget)
                job["units"].append({
                    "unit_id": unit["unit_id"], "order": index, "page_id": unit["page_id"],
                    "chapter_node_id": draft["chapter_node_id"], "source_text": unit["text"],
                    "target_text": draft["draft_text"] or "", "translation_note": draft["translation_note"],
                    "status": draft["status"], "findings": draft["findings"],
                    "approved": False, "human_edited": False, "review": None,
                })
                job["completed_units"] = index + 1
                self._persist(job)

            if policies["unit_review"] != "off":
                job["status"], job["stage_label"] = "reviewing", "בבדיקה"
                self._persist(job)
                self._run_unit_reviews(job, configuration, policies["unit_review"])

            if policies["chapter_qa"] == "on":
                job["status"], job["stage_label"] = "reviewing", "בבדיקת פרקים"
                self._persist(job)
                self._run_chapter_qa(job, configuration)

            job["status"], job["stage_label"] = "rebuilding", "בניית המסמך המתורגם"
            self._persist(job)
            translations = _build_translations_mapping(job["units"])
            result = _export_pdf(structure, translations, title=job["filename"])
            job["export_limitations"] = result.limitations
            job["export_page_count"] = result.page_count

            job["status"], job["stage_label"] = "completed", "הושלם"
        except DocumentDraftError as exc:
            job["status"], job["error"] = "failed", str(exc)
        except (TranslationRequestError, TranslationBudgetError) as exc:
            job["status"], job["error"] = "failed", f"התרגום נעצר: {exc}"
        except OpenAIConfigurationError as exc:
            job["status"], job["error"] = "failed", f"תצורת הספק שגויה: {exc}"
        except Exception:
            job["status"], job["error"] = "failed", "התרגום לא הושלם. בדקו חיבור, הרשאת המודל ומפתח API. התוצאה החלקית נשמרה."
        finally:
            try:
                self._persist(job)
            finally:
                with self.lock:
                    self.active = None

    def _risk_flags_for(self, unit_record):
        return {
            "configured_risk_flags": [],
            "translation_notes": bool(unit_record["translation_note"]),
            "formal_check_failure": bool(unit_record["findings"]),
            "extraction_or_ocr_risk": False,
        }

    def _run_unit_reviews(self, job, configuration, policy):
        if configuration is None:
            # Auto/mock mode never produces real Hebrew text (the mock
            # translation adapter's placeholder is deliberately conspicuous,
            # non-Hebrew text); review_qa.py rightly refuses to "review" that,
            # so Auto-mode review is a graceful, documented no-op, not a crash.
            job["review_notes"].append("מצב Auto/ללא ספק מוגדר: בדיקת מקטעים נדלגה (אין תרגום עברי אמיתי לבדוק).")
            return
        provider_definition = None
        if configuration is not None:
            resolved = self._resolve_role(configuration, "semantic_reviewer")
            if resolved is None:
                job["review_notes"].append("תפקיד semantic_reviewer אינו מוגדר; בדיקת מקטעים נדלגה.")
                return
            provider, model, provider_definition, capabilities = resolved
        for unit_record in job["units"]:
            risk_flags = self._risk_flags_for(unit_record)
            if configuration is not None:
                request = build_unit_review_request_for_role(
                    unit_record["source_text"], unit_record["target_text"] or unit_record["source_text"],
                    configuration, policy=policy, risk_flags=risk_flags,
                )
            else:
                request = build_unit_review_request(
                    unit_record["source_text"], unit_record["target_text"] or unit_record["source_text"],
                    policy=policy, risk_flags=risk_flags, provider="mock", model="mock-review-1",
                )
            generate = self._review_generate("semantic_reviewer", provider_definition)
            result = run_unit_review(request, generate=generate)
            unit_record["review"] = {
                "status": result["status"], "verdict": result.get("verdict"), "issues": result.get("issues", []),
            }
            self._persist(job)

    def _run_chapter_qa(self, job, configuration):
        if configuration is None:
            job["review_notes"].append("מצב Auto/ללא ספק מוגדר: בדיקת פרקים נדלגה (אין תרגום עברי אמיתי לבדוק).")
            return
        provider_definition = None
        if configuration is not None:
            resolved = self._resolve_role(configuration, "chapter_qa")
            if resolved is None:
                job["review_notes"].append("תפקיד chapter_qa אינו מוגדר; בדיקת פרקים נדלגה.")
                return
            provider, model, provider_definition, capabilities = resolved
        groups, current_key, current = [], object(), []
        for unit_record in job["units"]:
            key = unit_record["chapter_node_id"]
            if current and key != current_key:
                groups.append(current)
                current = []
            current_key, current = key, current + [unit_record]
        if current:
            groups.append(current)

        total = len(groups)
        for group_index, group in enumerate(groups, start=1):
            job["chapter_progress"] = {"current": group_index, "total": total}
            self._persist(job)
            source_chapter = "\n\n".join(u["source_text"] for u in group)
            hebrew_chapter = "\n\n".join((u["target_text"] or u["source_text"]) for u in group)
            if configuration is not None:
                request = build_chapter_qa_request_for_role(
                    source_chapter, hebrew_chapter, configuration,
                    profile=job["settings"]["profile"], policy="on",
                )
            else:
                request = build_chapter_qa_request(
                    source_chapter, hebrew_chapter, profile=job["settings"]["profile"],
                    policy="on", provider="mock", model="mock-review-1",
                )
            generate = self._review_generate("chapter_qa", provider_definition)
            result = run_chapter_qa(request, generate=generate)
            job["chapter_qa_results"].append({
                "unit_ids": [u["unit_id"] for u in group], "status": result["status"],
                "verdict": result.get("verdict"), "issues": result.get("issues", []),
                "chapter_level_notes": result.get("chapter_level_notes"),
            })
            self._persist(job)

    def review(self, job_id, unit_index, target_text, expected_revision):
        with self.lock:
            return self._review_locked(job_id, unit_index, target_text, expected_revision)

    def _review_locked(self, job_id, unit_index, target_text, expected_revision):
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
        job["revision"] = revision
        self._persist(job)
        return job
