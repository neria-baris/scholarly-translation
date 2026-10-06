"""SCANNED-OCR (audit/contracts/scanned_ocr_vision.md): scanned PDF pages in the
simple translation flow.

Pages without usable digital text are recognised by the local Tesseract engine
(parallel, cached per page in the job folder) into a standard OCR bundle. An
optional vision review then sends each page image with the Tesseract text to the
configured model, which returns the exact page text (formulas as ⟦Unicode⟧); the
reviewed text is aligned back onto the Tesseract word boxes so the result stays
valid, traceable source evidence. Provider calls are made only through the
caller-supplied ``run_call`` (journaled and budgeted by the chapter pipeline).
"""
from __future__ import annotations

import concurrent.futures
import difflib
import hashlib
import io
import json
import os
import re
import shutil
from pathlib import Path

from PIL import Image

from . import ocr as ocr_module
from .model_adapter import IMAGE_TOKEN_ALLOWANCE, ImagePrompt  # noqa: F401 (re-exported)
from .source_reading import OCR_VISION_STAGE

BUNDLED_TESSDATA = Path(__file__).resolve().parent / "assets" / "tessdata"
PROMPT_PATH = Path(__file__).resolve().parent / "runtime_prompts" / "08_ocr_vision_review.md"
VISION_STAGE = "ocr-vision"              # journal/budget stage of the review calls
DISAGREEMENT_RATIO = 0.6                 # word-sequence similarity below this is surfaced
VISION_IMAGE_LONG_EDGE = 1800            # page image sent to the model (JPEG)
OCR_PAGE_TIMEOUT_SECONDS = 90.0
_LANGUAGE_NAMES = {"en": "English", "fr": "French", "ja": "Japanese"}
_FENCE_RE = re.compile(r"^```[A-Za-z]*\s*|\s*```$")
_HEBREW_RE = re.compile(r"[֐-׿]")


class ScannedOcrError(Exception):
    """Clear, user-facing reason why scanned pages cannot be recognised."""


def find_tesseract():
    """Path of a usable Tesseract executable, or None."""
    candidates = [os.environ.get("SCHOLARLY_TESSERACT"), shutil.which("tesseract")]
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA") and str(Path(os.environ["LOCALAPPDATA"]) / "Programs")):
        if root:
            candidates.append(str(Path(root) / "Tesseract-OCR" / "tesseract.exe"))
    return next((c for c in candidates if c and Path(c).is_file()), None)


def tessdata_for(language, tesseract_path):
    """None to use the system models, else the bundled tessdata folder; raises when
    neither has the language."""
    tess_language = ocr_module.LANGUAGE_MAP.get(language)
    if tess_language is None:
        raise ScannedOcrError("אין מודל OCR לשפת המקור שנבחרה.")
    system = Path(tesseract_path).resolve().parent / "tessdata"
    if (system / f"{tess_language}.traineddata").is_file():
        return None
    if (BUNDLED_TESSDATA / f"{tess_language}.traineddata").is_file():
        return str(BUNDLED_TESSDATA)
    raise ScannedOcrError(f"מודל ה־OCR לשפה {tess_language} אינו מותקן.")


def ocr_ready(language):
    """(ok, reason) for the preview and settings: can scanned pages be read here?"""
    tesseract = find_tesseract()
    if tesseract is None:
        return False, "Tesseract לא נמצא במחשב. התקינו אותו כדי לתרגם ספרים סרוקים."
    try:
        tessdata_for(language, tesseract)
    except ScannedOcrError as exc:
        return False, str(exc)
    return True, None


def scanned_pages(document):
    """PDF pages that have no usable digital text."""
    return [page for page in document.pages if not (page.source_text or "").strip()]


def run_local_ocr(pdf_path, document, folder, progress=None):
    """Tesseract every scanned page (cached per page) and return a ``local-ocr@1`` bundle."""
    tesseract = find_tesseract()
    if tesseract is None:
        raise ScannedOcrError("Tesseract לא נמצא במחשב. התקינו אותו כדי לתרגם ספרים סרוקים.")
    tessdata = tessdata_for(document.language, tesseract)
    tess_language = ocr_module.LANGUAGE_MAP[document.language]
    engine_version = ocr_module._engine_version(tesseract, 30)
    model_hash = ocr_module._model_file_hash(tessdata, tess_language)
    pages = scanned_pages(document)
    cache_dir = Path(folder) / "ocr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(json.dumps([document.input_hash, tess_language, engine_version, model_hash],
                                          sort_keys=True).encode("utf-8")).hexdigest()[:16]
    done = [0]

    def one(page):
        cached = cache_dir / f"page-{page.page_number}-{cache_key}.json"
        if cached.is_file():
            try:
                result = json.loads(cached.read_text(encoding="utf-8"))
                image_ok = result.get("image_uri") is None or Path(_uri_path(result["image_uri"])).is_file()
                if result.get("page_id") == page.page_id and image_ok:
                    return result
            except (OSError, ValueError):
                pass
        result = ocr_module._ocr_page(Path(pdf_path), page, tess_language, tesseract, tessdata,
                                      OCR_PAGE_TIMEOUT_SECONDS, cache_dir, forced_page_review=False)
        cached.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result

    workers = max(1, min(4, (os.cpu_count() or 2) // 2))
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, page): page for page in pages}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future].page_number] = future.result()
            done[0] += 1
            if progress:
                progress(done[0], len(pages))
    selected = {p.page_number for p in pages}
    return {
        "schema_version": ocr_module.SCHEMA_VERSION,
        "stage": f"{ocr_module.STAGE_ID}@{ocr_module.STAGE_VERSION}",
        "document_id": document.document_id,
        "source_uri": Path(pdf_path).resolve().as_uri(),
        "source_hash": document.input_hash,
        "base_extraction_hash": ocr_module._canonical_document_hash(document),
        "language": document.language,
        "tesseract_language": tess_language,
        "engine_version": engine_version,
        "model_file_hash": model_hash,
        "pages": [results[n] for n in sorted(results)],
        "skipped_pages": [{"page_number": p.page_number, "reason": "digital_text_available"}
                          for p in document.pages if p.page_number not in selected],
    }


def _uri_path(uri):
    from urllib.parse import unquote, urlparse
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    return path[1:] if re.match(r"^/[A-Za-z]:", path) else path


def page_image_for_model(entry):
    """Deterministic JPEG of the page (long edge <= VISION_IMAGE_LONG_EDGE)."""
    with Image.open(_uri_path(entry["image_uri"])) as image:
        image = image.convert("RGB")
        scale = min(1.0, VISION_IMAGE_LONG_EDGE / max(image.size))
        if scale < 1.0:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                 Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=False)
        return buffer.getvalue()


def vision_prompt(entry, language):
    text = PROMPT_PATH.read_text(encoding="utf-8")
    text = text.replace("{{LANGUAGE}}", _LANGUAGE_NAMES.get(language, language))
    text = text.replace("{{OCR_TEXT}}", entry["transcription"] or "(the OCR engine found no text)")
    return ImagePrompt(text, page_image_for_model(entry), "image/jpeg")


def vision_output_cap(entry, max_output_tokens):
    """Generous output bound: the page text plus room for repairs and formulas."""
    wanted = max(4096, len(entry["transcription"] or "") + 2048)
    return min(max_output_tokens or 16384, wanted)


def parse_vision_text(raw_text):
    """Validator for the reviewer's answer: non-empty source-language page text."""
    if not isinstance(raw_text, str):
        raise ValueError("vision review returned no text")
    text = _FENCE_RE.sub("", raw_text.replace("\r\n", "\n").strip()).strip()
    if not text:
        raise ValueError("vision review returned an empty page")
    letters = sum(ch.isalpha() for ch in text)
    if letters and len(_HEBREW_RE.findall(text)) / letters > 0.3:
        raise ValueError("vision review answered in Hebrew instead of transcribing the source")
    return {"text": text}


def merge_reviewed_entry(entry, reviewed_text):
    """OCR page entry carrying the reviewed text. Words that match the Tesseract
    sequence keep their boxes and confidence; changed or added words get the page
    box and confidence 0. Strong disagreement is flagged, never hidden."""
    old = entry["words"]
    tokens = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", reviewed_text)]
    matcher = difflib.SequenceMatcher(a=[w["text"] for w in old], b=[t[0] for t in tokens], autojunk=False)
    page_pixel = [0, 0, entry["image_width"], entry["image_height"]]
    page_pdf = [0, 0, entry["pdf_width"], entry["pdf_height"]]
    words, kept = [], 0
    for tag, i1, _i2, j1, j2 in matcher.get_opcodes():
        for j in range(j1, j2):
            text, start, end = tokens[j]
            if tag == "equal":
                source = old[i1 + (j - j1)]
                pixel, pdf, confidence = source["pixel_bbox"], source["pdf_bbox"], source["confidence"]
                kept += 1
            else:
                pixel, pdf, confidence = list(page_pixel), list(page_pdf), 0.0
            words.append({"text": text, "confidence": confidence, "source_char_start": start,
                          "source_char_end": end, "pixel_bbox": pixel, "pdf_bbox": pdf})
    ratio = matcher.ratio() if old else 0.0
    warnings = [w for w in entry["warnings"] if w != "empty"] + ["vision_reviewed"]
    if old and ratio < DISAGREEMENT_RATIO:
        warnings.append("ocr_vision_disagreement")
    merged = dict(entry, transcription=reviewed_text, words=words, warnings=list(dict.fromkeys(warnings)))
    merged["vision_agreement"] = round(ratio, 3)
    merged["vision_changed_words"] = len(words) - kept
    return merged


def review_with_vision(bundle, language, run_call, vision_model, progress=None):
    """Vision-review every readable OCR page via ``run_call(entry, prompt)`` (which
    returns ``{"text": ...}``) and return a ``local-ocr+vision@1`` bundle."""
    pages = []
    reviewable = [e for e in bundle["pages"] if e["error"] is None and e.get("image_uri")]
    for index, entry in enumerate(bundle["pages"]):
        if entry["error"] is not None or not entry.get("image_uri"):
            pages.append(entry)
            continue
        parsed = run_call(entry, vision_prompt(entry, language))
        pages.append(merge_reviewed_entry(entry, parsed["text"]))
        if progress:
            progress(sum(1 for e in pages if "vision_agreement" in e), len(reviewable))
    reviewed = dict(bundle, stage=OCR_VISION_STAGE, vision_model=vision_model, pages=pages)
    return reviewed


def ocr_summary(bundle):
    """Small per-job report: pages, errors, low agreement pages."""
    pages = bundle["pages"]
    return {
        "pages": len(pages),
        "errors": [e["page_number"] for e in pages if e["error"] is not None],
        "vision_reviewed": bundle["stage"] == OCR_VISION_STAGE,
        "disagreement_pages": [e["page_number"] for e in pages if "ocr_vision_disagreement" in e["warnings"]],
        "low_confidence_pages": [e["page_number"] for e in pages if "low_confidence" in e["warnings"]],
    }
