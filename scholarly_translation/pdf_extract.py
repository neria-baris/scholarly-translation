"""Digital PDF extraction: pdfplumber-based text and geometry extraction into Document records.

Extraction establishes byte-for-byte source spans and page geometry; it is not
semantic acceptance. Output documents are always status=needs_human with a
layout_unverified warning.
"""
from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import List

import pdfplumber

from .records import Document, Page, Segment
from .store import deterministic_id

STAGE_ID = "digital-pdf"
STAGE_VERSION = 1
SOURCE_KIND = "pdf"
RENDER_DPI = 110


class ExtractionError(Exception):
    """Raised for invalid, empty, encrypted or missing PDF input. Never carries page content."""


def _require_positive_int(value, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExtractionError(f"{name} must be a positive integer")


def _extract_page_lines(page) -> List[dict]:
    lines = page.extract_text_lines(layout=False, strip=True) or []
    return sorted(lines, key=lambda ln: (round(ln["top"], 2), round(ln["x0"], 2)))


def extract_pdf(path, language: str, document_version: int = 1) -> Document:
    """Extract a digital PDF into a Document. Raises ExtractionError on invalid input."""
    path = Path(path)
    _require_positive_int(document_version, "document_version")
    if not isinstance(language, str) or not language.strip():
        raise ExtractionError("language must be a nonempty string")
    if not path.exists() or not path.is_file():
        raise ExtractionError("PDF not found")
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        raise ExtractionError("PDF could not be accessed") from None
    if not raw_bytes:
        raise ExtractionError("PDF file is empty")

    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    document_id = deterministic_id("digital-pdf-source", file_hash, str(document_version))

    warnings = ["layout_unverified"]
    pages: List[Page] = []

    try:
        with pdfplumber.open(path) as pdf:
            pdf_pages = pdf.pages
            if not pdf_pages:
                raise ExtractionError("PDF has no pages")
            for page_number, pdf_page in enumerate(pdf_pages, start=1):
                page_id = deterministic_id(document_id, "page", str(page_number))
                lines = _extract_page_lines(pdf_page)

                source_text_parts = []
                segments = []
                offset = 0
                for order, line in enumerate(lines, start=1):
                    text = line["text"]
                    if order > 1:
                        source_text_parts.append("\n")
                        offset += 1
                    start = offset
                    end = start + len(text)
                    source_text_parts.append(text)
                    offset = end
                    segment_id = deterministic_id(page_id, "segment", str(order))
                    segments.append(
                        Segment(
                            segment_id=segment_id,
                            page_id=page_id,
                            order=order,
                            text=text,
                            source_char_start=start,
                            source_char_end=end,
                            bbox=(line["x0"], line["top"], line["x1"], line["bottom"]),
                        )
                    )
                source_text = "".join(source_text_parts)
                if not segments:
                    warnings.append(f"page_{page_number}_empty_needs_ocr")

                pages.append(
                    Page(
                        page_id=page_id,
                        document_id=document_id,
                        page_number=page_number,
                        segments=segments,
                        width=float(pdf_page.width),
                        height=float(pdf_page.height),
                        source_text=source_text,
                    )
                )
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"PDF could not be read ({exc.__class__.__name__})") from None

    return Document(
        schema_version=3,
        document_id=document_id,
        document_version=document_version,
        language=language,
        source_kind=SOURCE_KIND,
        source_uri=path.resolve().as_uri(),
        pages=pages,
        stage_id=STAGE_ID,
        stage_version=STAGE_VERSION,
        input_hash=file_hash,
        status="needs_human",
        warnings=warnings,
    )


def render_pages(path, output_dir) -> List[Path]:
    """Render each PDF page to a PNG at RENDER_DPI for visual comparison. No network."""
    path = Path(path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    try:
        with pdfplumber.open(path) as pdf:
            for page_number, pdf_page in enumerate(pdf.pages, start=1):
                image_path = output_dir / f"page-{page_number}.png"
                pdf_page.to_image(resolution=RENDER_DPI).save(str(image_path))
                image_paths.append(image_path)
    except Exception as exc:
        raise ExtractionError(f"PDF could not be rendered ({exc.__class__.__name__})") from None
    return image_paths


def write_comparison_html(document: Document, image_paths: List[Path], output_path) -> None:
    """Write a static, escaped HTML page comparing rendered PDF pages to extracted source_text."""
    by_number = {p.page_number: p for p in document.pages}
    sections = []
    for image_path in image_paths:
        page_number = int(Path(image_path).stem.split("-")[-1])
        page = by_number.get(page_number)
        escaped_text = html.escape(page.source_text or "") if page else ""
        sections.append(
            "<section>"
            f"<h2>Page {page_number}</h2>"
            f"<img src=\"{html.escape(Path(image_path).name)}\" alt=\"Page {page_number} render\">"
            f"<pre>{escaped_text}</pre>"
            "</section>"
        )
    html_doc = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(document.document_id)} extraction comparison</title>"
        "<style>section{display:grid;grid-template-columns:1fr 1fr;gap:1rem}"
        "h2{grid-column:1/-1}img{max-width:100%}pre{white-space:pre-wrap}</style></head>"
        f"<body><h1>Digital PDF extraction comparison</h1>{''.join(sections)}</body></html>"
    )
    Path(output_path).write_text(html_doc, encoding="utf-8")
