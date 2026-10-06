"""Load the deterministic, explicit language learning catalogs (LEARN builder A)."""
from __future__ import annotations

import json
from pathlib import Path

from .learning_contracts import LearningError, SUPPORTED_LANGUAGE_CODES, validate_catalog

_DATA_DIR = Path(__file__).resolve().parent / "learning_data"

# Only languages with an actually implemented, hand-curated catalog file are
# listed here. The user selected fr/de/es/yi/it as candidates; French is the
# first implemented slice. Listing a language in SUPPORTED_LANGUAGE_CODES is
# not authorization to fake support for the other four.
_CATALOG_FILES = {
    "fr": "fr_common_v2.json",
}


def load_catalog(language="fr", *, version=None):
    """Load and validate the catalog for ``language``; pure, read-only."""
    if language not in SUPPORTED_LANGUAGE_CODES or language not in _CATALOG_FILES:
        raise LearningError("unsupported_language", f"unsupported language: {language!r}")
    if version is None:
        filename = _CATALOG_FILES[language]
    elif language == 'fr' and version in ('fr-common@1', 'fr-common@2'):
        filename = 'fr_common_v' + version[-1] + '.json'
    else:
        raise LearningError('catalog_changed', 'catalog version is unavailable')
    path = _DATA_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise LearningError("unsupported_language", f"catalog unavailable for {language!r}") from exc
    catalog = validate_catalog(raw)
    if catalog["language"] != language:
        raise LearningError("invalid_record", "catalog file language mismatch")
    if version is not None and catalog['version'] != version:
        raise LearningError('catalog_changed', 'catalog version mismatch')
    return catalog
