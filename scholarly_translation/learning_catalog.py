"""Load the deterministic, explicit language learning catalogs (LEARN builder A)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .learning_contracts import LearningError, DEFAULT_LEVELS, SUPPORTED_LANGUAGE_CODES, validate_catalog

_DATA_DIR = Path(__file__).resolve().parent / "learning_data"

# French retains its previous teaching definitions; other languages start from
# frequency hints and obtain teaching definitions in the same generation call.
_CATALOG_FILES = {
    "fr": "fr_common_v2.json",
}


def load_catalog(language="fr", *, version=None):
    """Load and validate the catalog for ``language``; pure, read-only."""
    if language not in SUPPORTED_LANGUAGE_CODES:
        raise LearningError("unsupported_language", f"unsupported language: {language!r}")
    dataset_path = _DATA_DIR.parents[1] / 'prompts/language_learning/wordlists/european_500.json'
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    seed = [{'rank': row['rank'], 'word': row['word']} for row in dataset['languages'][language]['words']]
    if language != 'fr':
        current_version = language + '-seed@1'
        if version not in (None, current_version):
            raise LearningError('catalog_changed', 'catalog version is unavailable')
        return validate_catalog({'schema_version': 1, 'language': language, 'version': current_version,
            'provenance': {'basis': 'Frequency candidates, not a reviewed teaching dictionary; model chooses contextually.',
                           'source': dataset['languages'][language]['source_url'], 'license': dataset['license']},
            'frequency_seed': seed, 'items': [], 'levels': deepcopy(DEFAULT_LEVELS)})
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
    catalog['frequency_seed'] = seed
    if catalog["language"] != language:
        raise LearningError("invalid_record", "catalog file language mismatch")
    if version is not None and catalog['version'] != version:
        raise LearningError('catalog_changed', 'catalog version mismatch')
    return catalog
