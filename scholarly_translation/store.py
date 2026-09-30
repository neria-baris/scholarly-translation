"""Atomic JSON persistence for Document records."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .records import Document, RecordValidationError


def deterministic_id(*parts: str) -> str:
    """Stable ID derived from source identity/version/page/segment identity.

    Parts are length-prefixed before joining so that no combination of
    part boundaries can collide (e.g. ("a|b", "c") vs ("a", "b|c")).
    """
    canonical = "".join(f"{len(str(p))}:{p}|" for p in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return digest


def save_document(document: Document, path: Path) -> None:
    """Write document as JSON, replacing any existing file atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(document.to_dict(), handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_document(path: Path) -> Document:
    """Read and validate a document JSON file. Raises RecordValidationError on invalid data."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise RecordValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RecordValidationError(f"document root must be an object in {path}")
    return Document.from_dict(data)
