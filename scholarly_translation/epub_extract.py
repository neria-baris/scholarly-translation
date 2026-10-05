"""Digital-text EPUB extraction: pure archive/XHTML-block extraction into
Document records, mirroring pdf_extract.py's Document/Page construction
pattern for the new non-geometric "digital-text" source-evidence origin
(see audit/contracts/session_epub_digital_text_schema.md).

EPUB text is already digital and already encodes its own block structure
unambiguously in XHTML markup (h1-h6/p/li/blockquote); unlike PDF, there is
no page geometry (no bbox) and no OCR path. Each discovered HTML block
becomes one Segment carrying an explicit node_kind/node_level (from the
small TAG_NODE_KIND table below) instead of PDF line geometry, so
document_structure.py can build logical nodes directly from that known
structure rather than re-deriving it heuristically from flattened text.

Reuses export_epub.py's defensive archive/XML parsing primitives (factored
into epub_archive.py) rather than re-implementing EPUB archive safety
checks a second time. Extraction establishes byte-for-byte source spans; it
is not semantic acceptance. Output documents are always status=needs_human.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import List

from .epub_archive import (
    BLOCK_TAGS, EpubArchiveError, archive_path, block_text, encrypted_paths,
    local_tag, open_validated_archive, parse_xml, resolve_package, resolve_reading_order,
)
from .records import Document, Page, Segment
from .store import deterministic_id

STAGE_ID = "digital-text-epub"
STAGE_VERSION = 1
SOURCE_KIND = "epub"

# Small, explicit tag -> (node_kind, node_level) table. node_kind values are
# drawn from document_structure.NODE_KINDS; level numbers mirror
# classify_line's own heading/subheading numbering so a heading/subheading
# nests the same way regardless of source origin. Deliberately small: EPUB
# markup does not encode part/chapter/section distinctions, so none are
# guessed here (h2..h6 all map to the same "subheading" kind/level).
TAG_NODE_KIND = {
    "h1": ("heading", 5),
    "h2": ("subheading", 6),
    "h3": ("subheading", 6),
    "h4": ("subheading", 6),
    "h5": ("subheading", 6),
    "h6": ("subheading", 6),
    "p": ("paragraph", None),
    "li": ("list", None),
    "blockquote": ("quotation", None),
}


class EpubExtractionError(Exception):
    """Raised for invalid, empty, encrypted or malformed EPUB input. Never carries page content.

    ``code`` is a stable machine identifier: ``empty_spine``, ``empty_chapters``,
    ``drm``, ``bad_spine_item``, ``no_text`` or ``None`` for other failures."""

    def __init__(self, message: str, code=None):
        super().__init__(message)
        self.code = code


def _require_positive_int(value, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EpubExtractionError(f"{name} must be a positive integer")


def _read_bytes(path_or_bytes) -> bytes:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        if not path_or_bytes:
            raise EpubExtractionError("EPUB file is empty")
        return bytes(path_or_bytes)
    path = Path(path_or_bytes)
    if not path.exists() or not path.is_file():
        raise EpubExtractionError("EPUB not found")
    try:
        raw = path.read_bytes()
    except OSError:
        raise EpubExtractionError("EPUB could not be accessed") from None
    if not raw:
        raise EpubExtractionError("EPUB file is empty")
    return raw


def _source_uri(path_or_bytes, file_hash: str) -> str:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return f"urn:sha256:{file_hash}"
    return Path(path_or_bytes).resolve().as_uri()


def extract_epub(path_or_bytes, language: str, document_version: int = 1) -> Document:
    """Extract an EPUB's own spine/XHTML block structure into a schema-3
    Document (source_kind == "epub"). Raises EpubExtractionError on
    invalid, empty, encrypted or malformed input; never carries page
    content in the error message.
    """
    _require_positive_int(document_version, "document_version")
    if not isinstance(language, str) or not language.strip():
        raise EpubExtractionError("language must be a nonempty string")

    raw_bytes = _read_bytes(path_or_bytes)
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    document_id = deterministic_id("digital-text-epub-source", file_hash, str(document_version))

    pages: List[Page] = []
    warnings: List[str] = []
    try:
        archive = open_validated_archive(io.BytesIO(raw_bytes))
        with archive:
            package_path, package, base = resolve_package(archive)
            spine_paths, fallback = resolve_reading_order(archive, package, base)
            if fallback:
                warnings.append(f"EPUB spine is empty; reading order taken from {fallback}")
            blank_chapters = 0

            for page_number, chapter_path in enumerate(spine_paths, start=1):
                chapter_bytes = archive.read(chapter_path)
                if not chapter_bytes.strip():
                    blank_chapters += 1
                    root = None
                else:
                    root = parse_xml(chapter_bytes)
                body = next((e for e in root.iter() if local_tag(e.tag) == "body"), root) if root is not None else None

                page_id = deterministic_id(document_id, "page", str(page_number))
                source_text_parts: List[str] = []
                segments: List[Segment] = []
                offset = 0
                order = 0
                for el in (body.iter() if body is not None else ()):
                    tag = local_tag(el.tag)
                    if tag not in BLOCK_TAGS:
                        continue
                    text = block_text(el)
                    if not text:
                        continue
                    order += 1
                    if order > 1:
                        source_text_parts.append("\n")
                        offset += 1
                    start = offset
                    end = start + len(text)
                    source_text_parts.append(text)
                    offset = end
                    kind, level = TAG_NODE_KIND[tag]
                    segment_id = deterministic_id(page_id, "segment", str(order))
                    segments.append(Segment(
                        segment_id=segment_id, page_id=page_id, order=order, text=text,
                        source_char_start=start, source_char_end=end,
                        node_kind=kind, node_level=level,
                    ))
                source_text = "".join(source_text_parts)
                pages.append(Page(
                    page_id=page_id, document_id=document_id, page_number=page_number,
                    segments=segments, width=None, height=None, source_text=source_text,
                ))
            if not any(page.segments for page in pages):
                if blank_chapters == len(pages):
                    raise EpubExtractionError(
                        "EPUB chapter files are empty; the file appears damaged or incompletely converted",
                        code="empty_chapters")
                raise EpubExtractionError("EPUB chapters contain no extractable text", code="no_text")
    except EpubExtractionError:
        raise
    except EpubArchiveError as exc:
        raise EpubExtractionError(str(exc), code=exc.code) from None
    except KeyError as exc:
        raise EpubExtractionError(f"EPUB archive is missing an expected member: {exc}") from None
    except Exception as exc:
        raise EpubExtractionError(f"EPUB could not be read ({exc.__class__.__name__})") from None

    return Document(
        schema_version=3,
        document_id=document_id,
        document_version=document_version,
        language=language,
        source_kind=SOURCE_KIND,
        source_uri=_source_uri(path_or_bytes, file_hash),
        pages=pages,
        stage_id=STAGE_ID,
        stage_version=STAGE_VERSION,
        input_hash=file_hash,
        status="needs_human",
        warnings=warnings,
    )
