"""Local Tesseract OCR fallback for image-only or failed-text pages.

Produces a separate OCR bundle (schema 1); never edits the base Document
or its source_text. OCR confidence is not proof of accuracy.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import List, Optional

import pdfplumber
from PIL import Image

from .records import Document

STAGE_ID = "local-ocr"
STAGE_VERSION = 1
SCHEMA_VERSION = 1
RENDER_DPI = 200
LOW_CONFIDENCE_THRESHOLD = 60.0

LANGUAGE_MAP = {"en": "eng", "fr": "fra", "ja": "jpn"}

_TSV_HEADER = [
    "level", "page_num", "block_num", "par_num", "line_num", "word_num",
    "left", "top", "width", "height", "conf", "text",
]


class OCRInputError(Exception):
    """Raised for invalid input, detected before any OCR work is attempted."""


def _require_positive_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise OCRInputError(f"{name} must be a positive number")
    return float(value)


def _tesseract_language(language: str) -> str:
    if not isinstance(language, str) or language not in LANGUAGE_MAP:
        raise OCRInputError(
            f"unsupported language; expected one of {sorted(LANGUAGE_MAP)}"
        )
    return LANGUAGE_MAP[language]


def _select_pages(document: Document, requested_pages: Optional[List[int]]):
    """Return (selected pages in document order, set of page numbers forced by explicit selection)."""
    by_number = {p.page_number: p for p in document.pages}
    if requested_pages is None:
        selected = [p for p in document.pages if not (p.source_text or "").strip()]
        return selected, set()
    if not requested_pages:
        raise OCRInputError("explicit page selection must not be empty")
    seen = set()
    for number in requested_pages:
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise OCRInputError(f"invalid page number {number!r}")
        if number in seen:
            raise OCRInputError(f"duplicate page number {number!r} in selection")
        if number not in by_number:
            raise OCRInputError(f"page {number} not found in document")
        seen.add(number)
    selected = [p for p in document.pages if p.page_number in seen]
    return selected, seen


def _canonical_document_hash(document: Document) -> str:
    canonical = json.dumps(
        document.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _engine_version(tesseract_path: str, timeout: float) -> str:
    try:
        result = subprocess.run(
            [tesseract_path, "--version"], capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    lines = (result.stdout or b"").decode("utf-8", errors="replace").splitlines()
    return lines[0].strip() if lines else "unknown"


def _model_file_hash(tessdata_dir: Optional[str], tess_language: str) -> Optional[str]:
    if not tessdata_dir:
        return None
    model_path = Path(tessdata_dir) / f"{tess_language}.traineddata"
    if not model_path.is_file():
        return None
    try:
        return hashlib.sha256(model_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _render_page_image(pdf_path: Path, page_number: int, output_dir: Path) -> Path:
    image_path = output_dir / f"ocr-page-{page_number}.png"
    with pdfplumber.open(pdf_path) as pdf:
        pdf_page = pdf.pages[page_number - 1]
        pdf_page.to_image(resolution=RENDER_DPI).save(str(image_path))
    return image_path


def _run_tesseract_tsv(tesseract_path, image_path, tess_language, tessdata_dir, timeout):
    args = [tesseract_path, str(image_path), "stdout", "-l", tess_language]
    if tessdata_dir:
        args.extend(["--tessdata-dir", str(tessdata_dir)])
    # Explicit renderer selection works with standalone traineddata directories,
    # which need not contain the optional configs/tsv file.
    args.extend(["-c", "tessedit_create_tsv=1"])
    return subprocess.run(args, capture_output=True, timeout=timeout, check=False)


def _parse_tsv(tsv_text: str) -> List[dict]:
    """Deterministically parse Tesseract TSV word-level rows. Raises ValueError on malformed input."""
    lines = tsv_text.splitlines()
    if not lines:
        raise ValueError("empty TSV output")
    header = lines[0].split("\t")
    if header != _TSV_HEADER:
        raise ValueError("unexpected TSV header")
    words = []
    for row in lines[1:]:
        if not row.strip():
            continue
        fields = row.split("\t")
        if len(fields) != len(_TSV_HEADER):
            raise ValueError("malformed TSV row")
        record = dict(zip(_TSV_HEADER, fields))
        try:
            level = int(record["level"])
            block_num = int(record["block_num"])
            par_num = int(record["par_num"])
            line_num = int(record["line_num"])
            word_num = int(record["word_num"])
            left = float(record["left"])
            top = float(record["top"])
            width = float(record["width"])
            height = float(record["height"])
            conf = float(record["conf"])
        except ValueError:
            raise ValueError("malformed TSV numeric field") from None
        text = record["text"]
        if level != 5 or not text.strip():
            continue
        if not math.isfinite(conf) or not (0.0 <= conf <= 100.0):
            raise ValueError(f"confidence out of range: {conf}")
        if any(not math.isfinite(v) for v in (left, top, width, height)) or left < 0 or top < 0 or width <= 0 or height <= 0:
            raise ValueError("negative word dimensions")
        words.append(
            {
                "block_num": block_num,
                "par_num": par_num,
                "line_num": line_num,
                "word_num": word_num,
                "text": text,
                "confidence": conf,
                "pixel_bbox": [left, top, left + width, top + height],
            }
        )
    return words


def _reconstruct_text_and_spans(words, pdf_width, pdf_height, image_width, image_height):
    """Group words into lines by block/par/line IDs; join words with a space and
    lines with a newline, tracking exact word offsets. No silent text repair."""
    text_parts: List[str] = []
    word_records = []
    offset = 0
    prev_key = None
    for w in words:
        x0, top, x1, bottom = w["pixel_bbox"]
        if x0 < 0 or top < 0 or x1 > image_width or bottom > image_height:
            raise ValueError("word bbox outside rendered source image")
        key = (w["block_num"], w["par_num"], w["line_num"])
        if prev_key is not None:
            separator = "\n" if key != prev_key else " "
            text_parts.append(separator)
            offset += len(separator)
        start = offset
        text_parts.append(w["text"])
        offset += len(w["text"])
        end = offset
        x0, top, x1, bottom = w["pixel_bbox"]
        pdf_bbox = None
        if pdf_width and pdf_height:
            pdf_bbox = [
                x0 / image_width * pdf_width,
                top / image_height * pdf_height,
                x1 / image_width * pdf_width,
                bottom / image_height * pdf_height,
            ]
        word_records.append(
            {
                "text": w["text"],
                "confidence": w["confidence"],
                "source_char_start": start,
                "source_char_end": end,
                "pixel_bbox": w["pixel_bbox"],
                "pdf_bbox": pdf_bbox,
            }
        )
        prev_key = key
    return "".join(text_parts), word_records


def _error_page_result(page, image_path, image_hash, image_width, image_height, warnings, forced, code, message):
    return {
        "page_id": page.page_id,
        "page_number": page.page_number,
        "image_uri": image_path.resolve().as_uri() if image_path else None,
        "image_hash": image_hash,
        "image_width": image_width,
        "image_height": image_height,
        "pdf_width": page.width,
        "pdf_height": page.height,
        "transcription": "",
        "words": [],
        "status": "needs_human",
        "eligible_for_translation": False,
        "warnings": warnings + ["error"],
        "forced_page_review": forced,
        "error": {"code": code, "message": message},
    }


def _ocr_page(pdf_path, page, tess_language, tesseract_path, tessdata_dir, timeout, output_dir, forced_page_review):
    warnings = ["ocr_unreviewed"]
    if forced_page_review:
        warnings.append("forced_page_review")

    try:
        image_path = _render_page_image(pdf_path, page.page_number, output_dir)
        image_bytes = image_path.read_bytes()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        with Image.open(image_path) as im:
            image_width, image_height = im.size
    except Exception as exc:
        return _error_page_result(
            page, None, None, None, None, warnings, forced_page_review,
            "render_failed", exc.__class__.__name__,
        )

    try:
        result = _run_tesseract_tsv(tesseract_path, image_path, tess_language, tessdata_dir, timeout)
    except subprocess.TimeoutExpired:
        return _error_page_result(
            page, image_path, image_hash, image_width, image_height, warnings,
            forced_page_review, "timeout", "engine timed out",
        )
    except OSError:
        return _error_page_result(
            page, image_path, image_hash, image_width, image_height, warnings,
            forced_page_review, "engine_unavailable", "engine could not be started",
        )

    if result.returncode != 0:
        return _error_page_result(
            page, image_path, image_hash, image_width, image_height, warnings,
            forced_page_review, "engine_error", "engine exited nonzero",
        )

    tsv_text = (result.stdout or b"").decode("utf-8", errors="replace")
    try:
        words = _parse_tsv(tsv_text)
    except ValueError:
        return _error_page_result(
            page, image_path, image_hash, image_width, image_height, warnings,
            forced_page_review, "malformed_output", "engine output could not be parsed",
        )

    base_result = {
        "page_id": page.page_id,
        "page_number": page.page_number,
        "image_uri": image_path.resolve().as_uri(),
        "image_hash": image_hash,
        "image_width": image_width,
        "image_height": image_height,
        "pdf_width": page.width,
        "pdf_height": page.height,
        "status": "needs_human",
        "eligible_for_translation": False,
        "forced_page_review": forced_page_review,
        "error": None,
    }

    if not words:
        return {
            **base_result,
            "transcription": "",
            "words": [],
            "warnings": warnings + ["empty"],
        }

    try:
        transcription, word_records = _reconstruct_text_and_spans(
            words, page.width, page.height, image_width, image_height
        )
    except ValueError:
        return _error_page_result(page, image_path, image_hash, image_width, image_height,
                                  warnings, forced_page_review, "malformed_output", "invalid word geometry")
    confidences = [w["confidence"] for w in word_records]
    if min(confidences) < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("low_confidence")

    return {
        **base_result,
        "transcription": transcription,
        "words": word_records,
        "warnings": warnings,
    }


def run_ocr(
    pdf_path,
    document: Document,
    language: str,
    tesseract_path: str,
    output_dir,
    tessdata_dir: Optional[str] = None,
    timeout: float = 30.0,
    pages: Optional[List[int]] = None,
) -> dict:
    """Run local OCR on selected pages of a validated schema-3 Document. Never mutates document."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    timeout = _require_positive_number(timeout, "timeout")
    if timeout > 120:
        raise OCRInputError("timeout exceeds 120-second local limit")
    if document.schema_version != 3 or document.source_kind != "pdf":
        raise OCRInputError("OCR requires a schema 3 PDF extraction")
    tess_language = _tesseract_language(language)

    if not pdf_path.exists() or not pdf_path.is_file():
        raise OCRInputError("PDF not found")
    try:
        raw_bytes = pdf_path.read_bytes()
    except OSError:
        raise OCRInputError("PDF could not be accessed") from None
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    if file_hash != document.input_hash:
        raise OCRInputError("PDF bytes do not match document input_hash")

    selected_pages, forced_numbers = _select_pages(document, pages)

    output_dir.mkdir(parents=True, exist_ok=True)

    engine_version = _engine_version(tesseract_path, timeout)
    model_hash = _model_file_hash(tessdata_dir, tess_language)
    base_extraction_hash = _canonical_document_hash(document)

    selected_numbers = {p.page_number for p in selected_pages}
    skipped = [
        {"page_number": p.page_number,
         "reason": "digital_text_available" if (p.source_text or "").strip() else "not_selected"}
        for p in document.pages
        if p.page_number not in selected_numbers
    ]

    page_results = [
        _ocr_page(
            pdf_path, page, tess_language, tesseract_path, tessdata_dir, timeout,
            output_dir, forced_page_review=page.page_number in forced_numbers,
        )
        for page in selected_pages
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": f"{STAGE_ID}@{STAGE_VERSION}",
        "document_id": document.document_id,
        "source_uri": pdf_path.resolve().as_uri(),
        "source_hash": file_hash,
        "base_extraction_hash": base_extraction_hash,
        "language": language,
        "tesseract_language": tess_language,
        "engine_version": engine_version,
        "model_file_hash": model_hash,
        "pages": page_results,
        "skipped_pages": skipped,
    }
