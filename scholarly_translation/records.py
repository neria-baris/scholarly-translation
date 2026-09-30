"""Validated record types for documents, pages and segments.

Schema version is explicit and separate from document version so the
store can evolve without silently reinterpreting older documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import hashlib
import math
import re

SCHEMA_VERSION = 3


class RecordValidationError(ValueError):
    """Raised when a loaded or constructed record violates the record contract."""


def _require_nonempty_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RecordValidationError(f"{field_name} must be a nonempty string")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RecordValidationError(f"{field_name} must be a positive integer")


@dataclass(frozen=True)
class Segment:
    segment_id: str
    page_id: str
    order: int
    text: str
    source_char_start: int
    source_char_end: int
    region_id: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None

    def __post_init__(self) -> None:
        _require_nonempty_id(self.segment_id, "segment_id")
        _require_nonempty_id(self.page_id, "page_id")
        _require_positive_int(self.order, "order")
        if not self.region_id:
            identity = f"{self.page_id}:{self.source_char_start}:{self.source_char_end}"
            object.__setattr__(self, "region_id", hashlib.sha256(identity.encode()).hexdigest()[:16])
        _require_nonempty_id(self.region_id, "region_id")
        if not isinstance(self.text, str):
            raise RecordValidationError("segment text must be a string")
        if not isinstance(self.source_char_start, int) or isinstance(self.source_char_start, bool):
            raise RecordValidationError("source_char_start must be an integer")
        if not isinstance(self.source_char_end, int) or isinstance(self.source_char_end, bool):
            raise RecordValidationError("source_char_end must be an integer")
        if self.source_char_start < 0 or self.source_char_end < self.source_char_start:
            raise RecordValidationError("segment source span is invalid")
        if self.source_char_end - self.source_char_start != len(self.text):
            raise RecordValidationError(
                "segment source span length must equal text length"
            )
        if self.bbox is not None:
            if not isinstance(self.bbox, (list, tuple)) or len(self.bbox) != 4:
                raise RecordValidationError("segment bbox must be a 4-element [x0,top,x1,bottom]")
            values = []
            for v in self.bbox:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise RecordValidationError("segment bbox values must be numeric")
                if not math.isfinite(v):
                    raise RecordValidationError("segment bbox values must be finite")
                values.append(float(v))
            x0, top, x1, bottom = values
            if x0 > x1 or top > bottom:
                raise RecordValidationError("segment bbox must have x0<=x1 and top<=bottom")
            object.__setattr__(self, "bbox", tuple(values))

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "page_id": self.page_id,
            "order": self.order,
            "text": self.text,
            "source_char_start": self.source_char_start,
            "source_char_end": self.source_char_end,
            "region_id": self.region_id,
            "bbox": list(self.bbox) if self.bbox is not None else None,
        }

    @staticmethod
    def from_dict(data: dict) -> "Segment":
        if not isinstance(data, dict):
            raise RecordValidationError("segment must be an object")
        try:
            return Segment(
                segment_id=data["segment_id"],
                page_id=data["page_id"],
                order=data["order"],
                text=data["text"],
                source_char_start=data["source_char_start"],
                source_char_end=data["source_char_end"],
                region_id=data.get("region_id", ""),
                bbox=data.get("bbox"),
            )
        except KeyError as exc:
            raise RecordValidationError(f"segment missing field: {exc}") from exc


@dataclass(frozen=True)
class Page:
    page_id: str
    document_id: str
    page_number: int
    segments: List[Segment] = field(default_factory=list)
    width: Optional[float] = None
    height: Optional[float] = None
    source_text: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_id(self.page_id, "page_id")
        _require_nonempty_id(self.document_id, "document_id")
        _require_positive_int(self.page_number, "page_number")
        if (self.width is None) != (self.height is None):
            raise RecordValidationError("page width and height must be set together")
        if self.width is not None:
            for dim_name, dim_value in (("width", self.width), ("height", self.height)):
                if (
                    isinstance(dim_value, bool)
                    or not isinstance(dim_value, (int, float))
                    or not math.isfinite(dim_value)
                    or dim_value <= 0
                ):
                    raise RecordValidationError(f"page {dim_name} must be a finite positive number")
        if self.source_text is not None and not isinstance(self.source_text, str):
            raise RecordValidationError("page source_text must be a string")
        seen_ids = set()
        seen_orders = set()
        for segment in self.segments:
            if segment.page_id != self.page_id:
                raise RecordValidationError(
                    f"segment {segment.segment_id} references page_id "
                    f"{segment.page_id!r}, expected {self.page_id!r}"
                )
            if segment.segment_id in seen_ids:
                raise RecordValidationError(
                    f"duplicate segment_id {segment.segment_id!r} in page {self.page_id!r}"
                )
            seen_ids.add(segment.segment_id)
            if segment.order in seen_orders:
                raise RecordValidationError(
                    f"duplicate segment order {segment.order!r} in page {self.page_id!r}"
                )
            seen_orders.add(segment.order)
            if self.source_text is not None:
                if segment.source_char_start < 0 or segment.source_char_end > len(self.source_text):
                    raise RecordValidationError(
                        f"segment {segment.segment_id} span exceeds page source_text bounds"
                    )
                if self.source_text[segment.source_char_start:segment.source_char_end] != segment.text:
                    raise RecordValidationError(
                        f"segment {segment.segment_id} text does not match page source_text span"
                    )
            if segment.bbox is not None and self.width is not None:
                x0, top, x1, bottom = segment.bbox
                if x0 < 0 or top < 0 or x1 > self.width or bottom > self.height:
                    raise RecordValidationError(
                        f"segment {segment.segment_id} bbox exceeds page bounds"
                    )

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "segments": [s.to_dict() for s in self.segments],
            "width": self.width,
            "height": self.height,
            "source_text": self.source_text,
        }

    @staticmethod
    def from_dict(data: dict) -> "Page":
        if not isinstance(data, dict):
            raise RecordValidationError("page must be an object")
        try:
            raw_segments = data["segments"]
            if not isinstance(raw_segments, list):
                raise RecordValidationError("page segments must be a list")
            segments = [Segment.from_dict(s) for s in raw_segments]
            return Page(
                page_id=data["page_id"],
                document_id=data["document_id"],
                page_number=data["page_number"],
                segments=segments,
                width=data.get("width"),
                height=data.get("height"),
                source_text=data.get("source_text"),
            )
        except KeyError as exc:
            raise RecordValidationError(f"page missing field: {exc}") from exc


@dataclass(frozen=True)
class Document:
    schema_version: int
    document_id: str
    document_version: int
    language: str
    source_kind: str
    source_uri: str
    pages: List[Page] = field(default_factory=list)
    stage_id: str = "legacy-import"
    stage_version: int = 1
    input_hash: str = "unknown"
    status: str = "unreviewed"
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version not in (1, 2, SCHEMA_VERSION)
        ):
            raise RecordValidationError(
                f"unsupported schema_version {self.schema_version!r}; "
                f"expected {SCHEMA_VERSION}"
            )
        _require_nonempty_id(self.document_id, "document_id")
        _require_positive_int(self.document_version, "document_version")
        _require_nonempty_id(self.language, "language")
        _require_nonempty_id(self.source_kind, "source_kind")
        _require_nonempty_id(self.source_uri, "source_uri")
        _require_nonempty_id(self.stage_id, "stage_id")
        _require_positive_int(self.stage_version, "stage_version")
        if self.status not in {"unreviewed", "needs_human", "synthetic"}:
            raise RecordValidationError("invalid document status")
        if not isinstance(self.warnings, list) or any(not isinstance(w, str) for w in self.warnings):
            raise RecordValidationError("warnings must be a list of strings")
        if not isinstance(self.input_hash, str) or (
            not re.fullmatch(r"[0-9a-f]{64}", self.input_hash)
            and not (self.schema_version == 1 and self.input_hash == "unknown")
        ):
            raise RecordValidationError("input_hash must be SHA-256 (or unknown for schema 1)")
        seen_page_ids = set()
        seen_page_numbers = set()
        for page in self.pages:
            if self.schema_version == 3 and self.source_kind == "pdf":
                if page.width is None or page.height is None or page.source_text is None:
                    raise RecordValidationError("schema 3 PDF page requires geometry and source_text")
                if any(s.bbox is None for s in page.segments):
                    raise RecordValidationError("schema 3 PDF segments require source bbox")
            if page.document_id != self.document_id:
                raise RecordValidationError(
                    f"page {page.page_id} references document_id "
                    f"{page.document_id!r}, expected {self.document_id!r}"
                )
            if page.page_id in seen_page_ids:
                raise RecordValidationError(f"duplicate page_id {page.page_id!r}")
            seen_page_ids.add(page.page_id)
            if page.page_number in seen_page_numbers:
                raise RecordValidationError(
                    f"duplicate page_number {page.page_number!r}"
                )
            seen_page_numbers.add(page.page_number)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version": self.document_version,
            "language": self.language,
            "source_kind": self.source_kind,
            "source_uri": self.source_uri,
            "pages": [p.to_dict() for p in self.pages],
            "stage_id": self.stage_id,
            "stage_version": self.stage_version,
            "input_hash": self.input_hash,
            "status": self.status,
            "warnings": self.warnings,
        }

    @staticmethod
    def from_dict(data: dict) -> "Document":
        if not isinstance(data, dict):
            raise RecordValidationError("document must be an object")
        try:
            legacy = data["schema_version"] == 1
            metadata = (
                {k: data[k] for k in ("stage_id", "stage_version", "input_hash", "status", "warnings")}
                if not legacy else
                dict(stage_id=data.get("stage_id", "legacy-import"),
                     stage_version=data.get("stage_version", 1),
                     input_hash=data.get("input_hash", "unknown"),
                     status=data.get("status", "unreviewed"),
                     warnings=data.get("warnings", ["legacy_input_hash_unavailable"]))
            )
            raw_pages = data["pages"]
            if not isinstance(raw_pages, list):
                raise RecordValidationError("document pages must be a list")
            pages = [Page.from_dict(p) for p in raw_pages]
            return Document(
                schema_version=data["schema_version"],
                document_id=data["document_id"],
                document_version=data["document_version"],
                language=data["language"],
                source_kind=data["source_kind"],
                source_uri=data["source_uri"],
                pages=pages,
                **metadata,
            )
        except KeyError as exc:
            raise RecordValidationError(f"document missing field: {exc}") from exc
